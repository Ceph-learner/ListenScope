"""Persistent process-level turnkey AI/MIDI bootstrap coordinator (survives Settings close/tab switches)."""

from __future__ import annotations

from collections import deque
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Any, Callable, Optional

from PySide6 import QtCore

from .paths import default_work_dir, get_app_root, launch_detached, subprocess_no_window_kwargs

logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\[(?:\d{1,3};)*\d{1,3}m"
)
_PS_TILDE_LINE_RE = re.compile(r"^\|?\s*~+\s*$")
_PROGRESS_MARKER_RE = re.compile(r"@@LS_PROGRESS\|([^@]+)@@")


def decode_bootstrap_bytes(raw: bytes) -> str:
    """Decode PowerShell/console subprocess output (UTF-8 first, CP936/GBK fallback)."""
    for enc in ("utf-8", "cp936", "gbk"):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def clean_bootstrap_line(text: str) -> str:
    """Strip VT100/ANSI escapes and PowerShell diagnostic tilde underlines."""
    cleaned = _ANSI_ESCAPE_RE.sub("", str(text)).replace("\x1b", "").replace("\r", "")
    cleaned = re.sub(r"^\s*\|\s*", "", cleaned).strip()
    if not cleaned or _PS_TILDE_LINE_RE.match(cleaned):
        return ""
    return cleaned


def parse_progress_marker(line: str) -> Optional[dict[str, Any]]:
    """Parse structured `@@LS_PROGRESS|pct=...|stage=...|speed=...|mirror=...@@` marker."""
    m = _PROGRESS_MARKER_RE.search(line)
    if not m:
        return None
    payload: dict[str, Any] = {}
    for token in m.group(1).split("|"):
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k == "pct":
            try:
                payload["pct"] = max(0, min(100, int(v)))
            except ValueError:
                pass
        elif k in ("stage", "speed", "mirror"):
            payload[k] = v
    return payload


def discover_installed_runtime_pythons(app_root: Path) -> tuple[str, str]:
    """Locate newly bootstrapped AI and MIDI Python executables beside app root or short Windows paths."""
    ai_candidates = [
        app_root / "runtime" / "ai" / "python.exe",
        app_root / "runtime" / "ai" / "Scripts" / "python.exe",
        app_root / "runtimes" / "ai" / "python.exe",
        app_root / "runtimes" / "ai" / "Scripts" / "python.exe",
        app_root / ".venv-ai" / "Scripts" / "python.exe",
        app_root / "runtime" / "ai" / "bin" / "python",
        app_root / ".venv-ai" / "bin" / "python",
    ]
    midi_candidates = [
        app_root / "m" / "python.exe",
        app_root / "m" / "Scripts" / "python.exe",
        app_root / "runtime" / "midi" / "python.exe",
        app_root / "runtime" / "midi" / "Scripts" / "python.exe",
        app_root / "runtimes" / "midi" / "python.exe",
        app_root / "runtimes" / "midi" / "Scripts" / "python.exe",
        app_root / ".venv-midi" / "Scripts" / "python.exe",
        app_root / "m" / "bin" / "python",
        app_root / "runtime" / "midi" / "bin" / "python",
        app_root / ".venv-midi" / "bin" / "python",
    ]
    if sys.platform == "win32":
        for drive in ("D:", "C:", "E:"):
            midi_candidates.append(Path(f"{drive}\\LS-midi\\.venv-midi\\Scripts\\python.exe"))
            midi_candidates.append(Path(f"{drive}\\LS-midi\\m\\Scripts\\python.exe"))

    ai_found = next((str(p) for p in ai_candidates if p.exists()), "")
    midi_found = next((str(p) for p in midi_candidates if p.exists()), "")
    return ai_found, midi_found


class BootstrapCoordinator(QtCore.QObject):
    """Application-scoped bootstrap runner whose state survives dialog closing/tab switching."""

    state_changed = QtCore.Signal(object)
    completed = QtCore.Signal(bool, str, str, str)  # (ok, status_msg, ai_python, midi_python)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._running = False
        self._canceled = False
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._progress_pct = 0
        self._stage = ""
        self._speed = ""
        self._mirror = ""
        self._tone = "info"
        self._status_text = (
            "准备就绪：点击「扫描本机 PyTorch 环境」自动查找电脑已安装的 PyTorch；"
            "若未安装可点击「一键自动配置 AI + MIDI」在同级目录自动下载配置（切换页面不会中断）。"
        )
        self._logs: deque[str] = deque(maxlen=200)
        self._finished_ok: Optional[bool] = None
        self._ai_python = ""
        self._midi_python = ""
        self._target_root: Optional[Path] = None
        self._needs_restart_hint = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "progress_pct": self._progress_pct,
                "stage": self._stage,
                "speed": self._speed,
                "mirror": self._mirror,
                "tone": self._tone,
                "status_text": self._status_text,
                "log_lines": list(self._logs),
                "finished_ok": self._finished_ok,
                "ai_python": self._ai_python,
                "midi_python": self._midi_python,
                "needs_restart_hint": self._needs_restart_hint,
            }

    def set_status_message(self, text: str, *, tone: str = "info", finished_ok: Optional[bool] = None) -> None:
        with self._lock:
            self._status_text = text
            self._tone = tone
            if finished_ok is not None:
                self._finished_ok = finished_ok
            snap = self.snapshot()
        self.state_changed.emit(snap)

    def start(
        self,
        *,
        cmd: list[str],
        cwd: str,
        env: dict[str, str],
        target_root: Path,
        popen_factory: Optional[Callable[..., Any]] = None,
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._canceled = False
            self._proc = None
            self._progress_pct = 2
            self._stage = "正在启动独立环境初始化流程..."
            self._speed = ""
            self._mirror = ""
            self._tone = "info"
            self._status_text = "[BUSY] 正在执行一键环境初始化（切换页面或关闭设置窗口不会中断下载）..."
            self._logs.clear()
            self._finished_ok = None
            self._ai_python = ""
            self._midi_python = ""
            self._target_root = target_root
            self._needs_restart_hint = False
            snap = self.snapshot()
        self.state_changed.emit(snap)

        factory = popen_factory if popen_factory is not None else launch_detached

        def _worker() -> None:
            last_lines: list[str] = []
            try:
                proc = factory(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    **subprocess_no_window_kwargs(),
                )
                with self._lock:
                    self._proc = proc
                assert proc.stdout is not None
                for raw_bytes in iter(proc.stdout.readline, b""):
                    raw_line = decode_bootstrap_bytes(raw_bytes)
                    line = clean_bootstrap_line(raw_line)
                    if not line:
                        continue
                    marker = parse_progress_marker(line)
                    if marker is not None:
                        with self._lock:
                            if "pct" in marker:
                                self._progress_pct = max(self._progress_pct, int(marker["pct"]))
                            if marker.get("stage"):
                                self._stage = str(marker["stage"])
                            if "speed" in marker:
                                self._speed = str(marker["speed"])
                            if "mirror" in marker:
                                self._mirror = str(marker["mirror"])
                            meta_parts = [f"{self._progress_pct}%", self._stage]
                            if self._speed:
                                meta_parts.append(self._speed)
                            if self._mirror:
                                meta_parts.append(self._mirror)
                            self._status_text = "[BUSY] " + " | ".join(p for p in meta_parts if p)
                            snap = self.snapshot()
                        self.state_changed.emit(snap)
                        continue

                    last_lines.append(line)
                    if len(last_lines) > 12:
                        last_lines = last_lines[-12:]
                    with self._lock:
                        self._logs.append(line)
                        # Infer mild progress ticks when pip writes lines inside fallback
                        low = line.lower()
                        if "downloading " in low and self._progress_pct < 60:
                            self._progress_pct = min(94, self._progress_pct + 1)
                        elif "installing collected packages" in low and self._progress_pct < 90:
                            self._progress_pct = max(self._progress_pct, 76)
                        if not self._stage:
                            self._stage = line[:72]
                        self._status_text = "[BUSY] 初始化进度:\n" + "\n".join(last_lines[-3:])
                        snap = self.snapshot()
                    self.state_changed.emit(snap)

                rc = proc.wait()
                with self._lock:
                    was_canceled = self._canceled
                    self._proc = None
                    self._running = False

                if was_canceled:
                    msg = "[WARN] 已取消环境初始化，你可以随时重新开始。"
                    with self._lock:
                        self._tone = "warn"
                        self._stage = ""
                        self._speed = ""
                        self._mirror = ""
                        self._status_text = msg
                        self._finished_ok = False
                        snap = self.snapshot()
                    self.state_changed.emit(snap)
                    self.completed.emit(False, msg, "", "")
                    return

                if rc == 0:
                    app_root = get_app_root()
                    ai_py, midi_py = discover_installed_runtime_pythons(app_root)
                    if target_root != app_root:
                        fb_ai, fb_midi = discover_installed_runtime_pythons(target_root)
                        ai_py = ai_py or fb_ai
                        midi_py = midi_py or fb_midi
                    if not ai_py and not midi_py:
                        alt_root = default_work_dir().parent
                        alt_ai, alt_midi = discover_installed_runtime_pythons(alt_root)
                        ai_py = ai_py or alt_ai
                        midi_py = midi_py or alt_midi

                    msg = (
                        "[OK] 环境初始化已完成并已自动写入配置！"
                        "正在刷新验证环境；若刚通过 winget 新装 Python 或硬件状态未即时更新，可点击「立即重启应用」快速生效。"
                    )
                    with self._lock:
                        self._progress_pct = 100
                        self._stage = "初始化完成，已自动写入配置"
                        self._speed = ""
                        self._tone = "ok"
                        self._status_text = msg
                        self._finished_ok = True
                        self._ai_python = ai_py
                        self._midi_python = midi_py
                        self._needs_restart_hint = True
                        snap = self.snapshot()
                    logger.info("Turnkey bootstrap finished cleanly: ai=%s midi=%s", ai_py, midi_py)
                    self.state_changed.emit(snap)
                    self.completed.emit(True, msg, ai_py, midi_py)
                else:
                    tail = "\n".join(last_lines[-6:])
                    msg = f"[ERR] 初始化失败 (exit={rc}):\n{tail}"
                    with self._lock:
                        self._tone = "error"
                        self._status_text = msg
                        self._finished_ok = False
                        snap = self.snapshot()
                    logger.error("Turnkey bootstrap failed (exit=%s): %s", rc, tail)
                    self.state_changed.emit(snap)
                    self.completed.emit(False, msg, "", "")
            except Exception as exc:
                with self._lock:
                    self._proc = None
                    self._running = False
                    msg = f"[ERR] 启动初始化脚本失败: {exc}"
                    self._tone = "error"
                    self._status_text = msg
                    self._finished_ok = False
                    snap = self.snapshot()
                logger.exception("Turnkey bootstrap launch error")
                self.state_changed.emit(snap)
                self.completed.emit(False, msg, "", "")

        threading.Thread(target=_worker, name="ListenScope-TurnkeySetup", daemon=True).start()
        return True

    def cancel(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._canceled = True
            proc = self._proc
        if proc is not None:
            pid = getattr(proc, "pid", None)
            if sys.platform == "win32" and pid:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        timeout=5.0,
                        check=False,
                        **subprocess_no_window_kwargs(),
                    )
                except Exception:
                    pass
            try:
                proc.kill()
            except Exception:
                pass


_SINGLETON_LOCK = threading.Lock()
_BOOTSTRAP_MANAGER: Optional[BootstrapCoordinator] = None


def get_bootstrap_manager() -> BootstrapCoordinator:
    global _BOOTSTRAP_MANAGER
    with _SINGLETON_LOCK:
        if _BOOTSTRAP_MANAGER is None:
            _BOOTSTRAP_MANAGER = BootstrapCoordinator()
        return _BOOTSTRAP_MANAGER
