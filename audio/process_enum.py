"""Cross-platform and Windows WASAPI audio session / process enumeration.

Does NOT hardcode QQMusic.exe or any single player: discovers active Windows
audio sessions via pycaw (IAudioSessionControl2) merged with psutil process-tree
metadata so users can pick QQ Music, Chrome/Edge, foobar2000, Cubase, or any
other audio-producing application.
"""

from __future__ import annotations

import platform
from typing import Optional

import psutil

from core.models import AudioProcessInfo


_STATE_MAP = {
    0: "inactive",
    1: "active",
    2: "expired",
}


def _safe_proc_details(pid: int) -> tuple[str, Optional[str], Optional[int], Optional[str], list[int], float]:
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        exe = None
        try:
            exe = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            exe = None
        ppid = proc.ppid()
        pname = None
        try:
            if ppid > 0:
                pname = psutil.Process(ppid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pname = None
        child_pids = []
        try:
            child_pids = [c.pid for c in proc.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            child_pids = []
        rss_mb = proc.memory_info().rss / (1024.0 * 1024.0)
        return name, exe, ppid, pname, child_pids, rss_mb
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return f"pid-{pid}", None, None, None, [], 0.0


def _enumerate_windows_wasapi_sessions() -> list[AudioProcessInfo]:
    """Query actual Windows Audio Sessions via pycaw + COM."""
    try:
        import comtypes  # type: ignore[import-not-found]
        from pycaw.pycaw import AudioUtilities  # type: ignore[import-not-found]
    except ImportError:
        return []

    com_initialized = False
    try:
        comtypes.CoInitialize()
        com_initialized = True
    except Exception:
        com_initialized = False

    by_pid: dict[int, AudioProcessInfo] = {}
    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            proc = getattr(session, "Process", None)
            if proc is None:
                continue
            pid = getattr(proc, "pid", None)
            if not pid:
                continue

            raw_state = getattr(session, "State", None)
            state_str = _STATE_MAP.get(int(raw_state), "unknown") if raw_state is not None else "unknown"

            # Prefer 'active' if the same PID holds multiple audio sessions
            existing = by_pid.get(int(pid))
            if existing is not None:
                if existing.session_state != "active" and state_str == "active":
                    existing.session_state = "active"
                continue

            name, exe, ppid, pname, child_pids, rss_mb = _safe_proc_details(int(pid))
            by_pid[int(pid)] = AudioProcessInfo(
                pid=int(pid),
                name=name,
                exe=exe,
                session_state=state_str,
                parent_pid=ppid,
                parent_name=pname,
                child_pids=child_pids,
                rss_mb=rss_mb,
                source="wasapi_session",
            )
    except Exception:
        return list(by_pid.values())
    finally:
        if com_initialized:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    results = list(by_pid.values())
    state_rank = {"active": 0, "inactive": 1, "expired": 2, "unknown": 3}
    results.sort(key=lambda p: (state_rank.get(p.session_state, 9), -p.rss_mb, p.name.lower()))
    return results


def _enumerate_linux_pulse_sessions() -> list[AudioProcessInfo]:
    """Best-effort PulseAudio/PipeWire sink-input enumeration on Linux dev environments."""
    try:
        import pulsectl  # type: ignore[import-not-found]
    except ImportError:
        return []

    results: list[AudioProcessInfo] = []
    seen: set[int] = set()
    try:
        with pulsectl.Pulse("listenscope-enum") as pulse:
            for sink_input in pulse.sink_input_list():
                proplist = getattr(sink_input, "proplist", {}) or {}
                raw_pid = proplist.get("application.process.id")
                if not raw_pid:
                    continue
                pid = int(raw_pid)
                if pid in seen:
                    continue
                seen.add(pid)
                name, exe, ppid, pname, child_pids, rss_mb = _safe_proc_details(pid)
                corked = bool(getattr(sink_input, "corked", False))
                results.append(
                    AudioProcessInfo(
                        pid=pid,
                        name=name,
                        exe=exe,
                        session_state="inactive" if corked else "active",
                        parent_pid=ppid,
                        parent_name=pname,
                        child_pids=child_pids,
                        rss_mb=rss_mb,
                        source="pulsectl",
                    )
                )
    except Exception:
        return []
    return results


def enumerate_audio_processes(include_all_running: bool = False) -> list[AudioProcessInfo]:
    """Enumerate processes currently registered/active on the audio mixer.

    On Windows, prioritizes WASAPI audio sessions (`pycaw`). If `include_all_running`
    is True (or no audio session API is available), also exposes running processes
    via `psutil` so any arbitrary application can be selected.
    """
    system = platform.system()
    if system == "Windows":
        sessions = _enumerate_windows_wasapi_sessions()
    elif system == "Linux":
        sessions = _enumerate_linux_pulse_sessions()
    else:
        sessions = []

    if not include_all_running and sessions:
        return sessions

    seen_pids = {p.pid for p in sessions}
    extra: list[AudioProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "ppid", "memory_info"]):
        try:
            pid = int(proc.info["pid"])
            if pid <= 0 or pid in seen_pids:
                continue
            name = proc.info.get("name") or f"pid-{pid}"
            mem = proc.info.get("memory_info")
            rss_mb = (mem.rss / (1024.0 * 1024.0)) if mem else 0.0
            extra.append(
                AudioProcessInfo(
                    pid=pid,
                    name=name,
                    parent_pid=proc.info.get("ppid"),
                    rss_mb=rss_mb,
                    source="psutil",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, KeyError):
            continue

    extra.sort(key=lambda p: (-p.rss_mb, p.name.lower()))
    return sessions + extra


def resolve_target_pid(
    *,
    pid: Optional[int] = None,
    process_name: Optional[str] = None,
) -> tuple[int, str, Optional[str]]:
    """Resolve user-selected target PID / process name cleanly.

    Returns (resolved_pid, resolved_name, diagnostic_note).
    When resolving by process name for multi-process apps (e.g. QQMusic.exe, Chrome,
    Edge), checks WASAPI audio sessions and process tree ancestry so the root
    or active audio process is selected predictably.
    """
    if pid is not None:
        if not psutil.pid_exists(pid):
            raise ValueError(f"目标 PID {pid} 不存在或已退出。")
        name, _, _, _, _, _ = _safe_proc_details(pid)
        return pid, name, None

    if not process_name:
        raise ValueError("必须指定 --pid 或 --name。")

    target_norm = process_name.strip().lower()
    target_exe = target_norm if target_norm.endswith(".exe") else f"{target_norm}.exe"

    # 1. Check active/registered audio sessions first
    sessions = enumerate_audio_processes(include_all_running=False)
    matching_sessions = [
        s
        for s in sessions
        if s.name.lower() in (target_norm, target_exe)
        or (s.parent_name and s.parent_name.lower() in (target_norm, target_exe))
    ]
    if matching_sessions:
        # Prefer active audio session; if its parent shares the same exe name,
        # prefer the root process when on Windows tree loopback.
        chosen = matching_sessions[0]
        note: Optional[str] = None
        if (
            chosen.parent_pid
            and chosen.parent_name
            and chosen.parent_name.lower() in (target_norm, target_exe)
            and psutil.pid_exists(chosen.parent_pid)
        ):
            note = (
                f"检测到音频会话 PID={chosen.pid} ({chosen.name}, {chosen.session_state})，"
                f"同时选择同源父进程 PID={chosen.parent_pid} 以覆盖子进程树。"
            )
            return chosen.parent_pid, chosen.parent_name, note
        return chosen.pid, chosen.name, note

    # 2. Fall back to psutil process scan
    candidates: list[tuple[int, str, Optional[int], float]] = []
    for proc in psutil.process_iter(["pid", "name", "ppid", "memory_info"]):
        try:
            pname = proc.info.get("name") or ""
            if pname.lower() in (target_norm, target_exe) or target_norm in pname.lower():
                mem = proc.info.get("memory_info")
                rss_mb = (mem.rss / (1024.0 * 1024.0)) if mem else 0.0
                candidates.append((int(proc.info["pid"]), pname, proc.info.get("ppid"), rss_mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, KeyError):
            continue

    if not candidates:
        raise ValueError(f"未找到匹配的运行中进程: '{process_name}'")

    candidate_pids = {c[0] for c in candidates}
    roots = [c for c in candidates if c[2] not in candidate_pids]
    chosen_cand = max(roots or candidates, key=lambda c: c[3])
    return chosen_cand[0], chosen_cand[1], "通过进程名匹配（目标当前可能尚未产生活跃 WASAPI 音频会话）。"
