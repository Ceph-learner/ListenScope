from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _make_window():
    from PySide6 import QtWidgets
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    return app, win, mixer


def _contains_chinese_for_lang(text: str, lang: str) -> bool:
    if not text:
        return False
    if lang in ("en", "ko"):
        return bool(re.search(r"[\u4e00-\u9fff]", text))
    if lang == "ja":
        cn_markers = (
            "当前使用", "其他应用", "低音 ", "多声部", "曲目监测", "未检测到",
            "已缓冲", "请先", "点击", "展开", "收起", "换歌重置", "分轨",
            "低显存默认", "用户点击", "紧急停止", "已切换到",
        )
        return any(m in text for m in cn_markers)
    return False


def test_h1_system_loopback_follows_default_device_change_preserves_buffer_and_logs(caplog) -> None:
    import numpy as np
    from audio.playback import HistoryABPlayer
    from audio.ring_buffer import FixedRingBuffer
    from audio.system_loopback import WasapiSystemLoopbackBackend

    state = {"dev_idx": 1, "dev_id": "dev-xiberia", "dev_name": "XIBERIA", "reads": 0}
    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()

    class _FakeStream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            state["reads"] += 1
            time.sleep(0.02)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            # Simulate PortAudio caching default device at init time!
            self._cached_idx = state["dev_idx"]
            self._cached_name = state["dev_name"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": self._cached_idx,
                "name": self._cached_name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs) -> _FakeStream:
            return _FakeStream()

        def terminate(self) -> None:
            pass

    ring = FixedRingBuffer()
    ab = HistoryABPlayer(ring_buffer=ring)
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
    )

    with caplog.at_level(logging.INFO):
        backend.start()
        try:
            deadline = time.monotonic() + 1.0
            while ring.available_seconds < 0.1 and time.monotonic() < deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
            assert ring.available_seconds >= 0.05
            ab.select_recent_seconds(0.05)
            prev_frames = ring.total_written_frames
            prev_loop = ab.loop_range

            # Switch Windows default playback device
            state["dev_idx"] = 2
            state["dev_id"] = "dev-realtek"
            state["dev_name"] = "Realtek Digital Output"

            switch_deadline = time.monotonic() + 1.5
            switched = False
            while time.monotonic() < switch_deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
                if backend.get_stats().process_name == "Realtek Digital Output":
                    switched = True
                    break

            assert switched, f"Did not switch within 1.5s; stats={backend.get_stats()}"
            assert ring.total_written_frames >= prev_frames
            assert ab.loop_range == prev_loop
            assert any(
                "loopback default device changed old=XIBERIA new=Realtek Digital Output" in r.message
                for r in caplog.records
            )
            stats = backend.get_stats()
            assert "Realtek Digital Output" in (stats.device_switch_message or stats.warning_message or "")
        finally:
            backend.stop()


def test_h1a_blocked_read_switches_within_1_5s_and_preserves_buffer() -> None:
    import threading
    import numpy as np
    from audio.playback import HistoryABPlayer
    from audio.ring_buffer import FixedRingBuffer
    from audio.system_loopback import WasapiSystemLoopbackBackend

    state = {"dev_idx": 1, "dev_id": "dev-xiberia", "dev_name": "XIBERIA", "reads": 0}
    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    block_forever_after_switch = threading.Event()

    class _BlockingStream:
        def __init__(self, dev_id: str) -> None:
            self._dev_id = dev_id
            self._unblock = threading.Event()
            self._reads = 0

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            self._reads += 1
            if self._dev_id == "dev-xiberia" and self._reads >= 4:
                # Simulate WASAPI loopback blocking forever once old endpoint goes silent
                block_forever_after_switch.set()
                self._unblock.wait()
                raise RuntimeError("stream interrupted")
            time.sleep(0.02)
            return pcm_chunk

        def stop_stream(self) -> None:
            self._unblock.set()

        def close(self) -> None:
            self._unblock.set()

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._idx = state["dev_idx"]
            self._id = state["dev_id"]
            self._name = state["dev_name"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": self._idx,
                "name": self._name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs) -> _BlockingStream:
            return _BlockingStream(self._id)

        def terminate(self) -> None:
            pass

    ring = FixedRingBuffer()
    ab = HistoryABPlayer(ring_buffer=ring)
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.1,
    )
    backend.start()
    try:
        deadline = time.monotonic() + 1.5
        while (ring.available_seconds < 0.05 or not block_forever_after_switch.is_set()) and time.monotonic() < deadline:
            ch = backend.read_chunk(timeout=0.05)
            if ch is not None:
                ring.write(ch)
        assert ring.available_seconds >= 0.04
        assert block_forever_after_switch.is_set(), "Old stream did not enter blocked read()"
        ab.select_recent_seconds(0.04)
        prev_frames = ring.total_written_frames
        prev_loop = ab.loop_range

        # Switch device while read() is permanently blocked
        state["dev_idx"] = 2
        state["dev_id"] = "dev-realtek"
        state["dev_name"] = "Realtek Digital Output"

        switch_deadline = time.monotonic() + 1.5
        switched = False
        while time.monotonic() < switch_deadline:
            ch = backend.read_chunk(timeout=0.05)
            if ch is not None:
                ring.write(ch)
            if backend.get_stats().process_name == "Realtek Digital Output":
                switched = True
                break
        assert switched, f"Blocked read() did not switch within 1.5s; stats={backend.get_stats()}"
        assert ring.total_written_frames >= prev_frames
        assert ab.loop_range == prev_loop
    finally:
        backend.stop()


def test_h1b_com_init_uninit_once_per_watcher_and_rpc_e_changed_mode(monkeypatch) -> None:
    import audio.system_loopback as sl

    calls: list[str] = []

    class _FakeOle32:
        def __init__(self, hr: int) -> None:
            self._hr = hr
            self.CoInitializeEx = self._CoInit(self)
            self.CoUninitialize = self._CoUninit(self)
            self.CoCreateInstance = self._DummyFn()
            self.CoTaskMemFree = self._DummyFn()

        class _DummyFn:
            argtypes = []
            restype = None

        class _CoInit:
            argtypes = []
            restype = None

            def __init__(self, parent) -> None:
                self._p = parent

            def __call__(self, _reserved, _flags):
                calls.append(f"CoInitializeEx:{self._p._hr}")
                return self._p._hr

        class _CoUninit:
            argtypes = []
            restype = None

            def __init__(self, parent) -> None:
                self._p = parent

            def __call__(self):
                calls.append("CoUninitialize")

    monkeypatch.setattr(sl.platform, "system", lambda: "Windows")

    # Case 1: S_OK -> should_uninit=True
    fake_ok = _FakeOle32(0)
    monkeypatch.setattr(sl, "_make_ole32_and_guid", lambda: (fake_ok, object))
    ole, uninit = sl._com_initialize_thread()
    assert ole is fake_ok and uninit is True

    # Case 2: RPC_E_CHANGED_MODE -> should_uninit=False, continues normally
    fake_changed = _FakeOle32(sl._RPC_E_CHANGED_MODE)
    monkeypatch.setattr(sl, "_make_ole32_and_guid", lambda: (fake_changed, object))
    ole2, uninit2 = sl._com_initialize_thread()
    assert ole2 is fake_changed and uninit2 is False

    # Case 3: Watcher loop initializes once and uninitializes once on exit
    calls.clear()
    monkeypatch.setattr(sl, "_make_ole32_and_guid", lambda: (fake_ok, object))

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def get_default_wasapi_loopback(self):
            return {"index": 1, "name": "DevA", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs):
            class _S:
                def read(self, frames, exception_on_overflow=False):
                    time.sleep(0.02)
                    return b"\x00" * (frames * 8)

                def stop_stream(self):
                    pass

                def close(self):
                    pass

            return _S()

        def terminate(self):
            pass

    backend = sl.WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=None,
        device_poll_interval_sec=0.05,
    )
    # Prevent actual COM CoCreateInstance in _query_windows_default_render_endpoint
    monkeypatch.setattr(sl, "_query_windows_default_render_endpoint", lambda *, initialize_com=True: ("id-a", "DevA"))
    backend.start()
    time.sleep(0.2)
    backend.stop()
    # Watcher thread inits COM once at start and uninits once on exit (across multiple 50ms polls)
    assert calls == ["CoInitializeEx:0", "CoUninitialize"]


def test_h1c_device_switch_message_clears_and_aba_round_trip() -> None:
    import numpy as np
    from audio.system_loopback import SYSTEM_LOOPBACK_WARNING, WasapiSystemLoopbackBackend

    state = {"dev_idx": 1, "dev_id": "dev-a", "dev_name": "DeviceA"}
    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()

    class _FakeStream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.02)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._idx = state["dev_idx"]
            self._name = state["dev_name"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs) -> _FakeStream:
            return _FakeStream()

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.08,
        device_switch_ttl_sec=0.25,
    )
    app, win, mixer = _make_window()
    try:
        backend.start()
        # A -> B
        state["dev_idx"], state["dev_id"], state["dev_name"] = 2, "dev-b", "DeviceB"
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and backend.get_stats().process_name != "DeviceB":
            time.sleep(0.02)
        st_b = backend.get_stats()
        assert st_b.process_name == "DeviceB"
        assert "DeviceB" in (st_b.device_switch_message or "")
        win.update_capture_stats(st_b, 1.0)
        assert "DeviceB" in win._last_capture_banner

        # Wait for TTL expiry -> message clears and warning banner restores
        time.sleep(0.3)
        st_b_expired = backend.get_stats()
        assert st_b_expired.device_switch_message is None
        win.update_capture_stats(st_b_expired, 1.0)
        assert win._last_capture_banner == SYSTEM_LOOPBACK_WARNING

        # B -> A (round-trip back to A must show switch message again!)
        state["dev_idx"], state["dev_id"], state["dev_name"] = 1, "dev-a", "DeviceA"
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and backend.get_stats().process_name != "DeviceA":
            time.sleep(0.02)
        st_a = backend.get_stats()
        assert st_a.process_name == "DeviceA"
        assert "DeviceA" in (st_a.device_switch_message or "")
        win.update_capture_stats(st_a, 1.0)
        assert "DeviceA" in win._last_capture_banner
    finally:
        backend.stop()
        win.close()
        mixer.close()



def test_h2_chroma_narrow_125_with_banner_and_ab_dock_shows_chroma_bars_and_tempo_buttons() -> None:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = "1.25"
    code = (
        "from PySide6 import QtCore, QtWidgets\n"
        "from audio.playback import StemMixerEngine\n"
        "from core.appearance import Appearance\n"
        "from core.config import AIConfig, ResourceLimits\n"
        "from core.system_probe import probe_system\n"
        "from ui.main_window import ListenScopeMainWindow\n"
        "app = QtWidgets.QApplication([])\n"
        "m = StemMixerEngine(sample_rate=48000, channels=2)\n"
        "w = ListenScopeMainWindow(hardware_report=probe_system(), resource_limits=ResourceLimits(), ai_config=AIConfig(), mixer_engine=m)\n"
        "for lang in ('zh', 'en'):\n"
        "    w.apply_appearance(Appearance(theme_mode='light', language=lang))\n"
        "    w.show_banner_message('⚠️ 当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。', tone='warn')\n"
        "    w.set_bottom_panel_collapsed(False)\n"
        "    w.resize(874, 453)\n"
        "    w.show()\n"
        "    w.tabs.setCurrentWidget(w.chroma_widget)\n"
        "    app.processEvents()\n"
        "    vp = w.chroma_widget.findChild(QtWidgets.QScrollArea).viewport()\n"
        "    bar = w.chroma_widget.chroma_bar_plot\n"
        "    bar_tl = bar.mapTo(vp, QtCore.QPoint(0, 0))\n"
        "    bar_br = bar.mapTo(vp, QtCore.QPoint(bar.width(), bar.height()))\n"
        "    assert bar.height() >= 30 and bar_tl.y() >= -1 and bar_br.y() <= vp.height() + 2, f'[{lang}] bar {bar_tl}..{bar_br} vp={vp.height()}'\n"
        "    assert w.chroma_widget.chroma_hist_plot.height() >= 96, f'[{lang}] hist height={w.chroma_widget.chroma_hist_plot.height()}'\n"
        "    for btn in (w.chroma_widget.tempo_half_btn, w.chroma_widget.tempo_double_btn):\n"
        "        assert btn.isVisible()\n"
        "        br = btn.mapTo(w, QtCore.QPoint(btn.width(), btn.height()))\n"
        "        assert br.x() <= w.width() + 1 and br.y() <= w.height() + 1, f'[{lang}] {btn.text()} clipped {br}'\n"
        "w.close(); m.close()\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=45)
    assert proc.returncode == 0, f"H2 1.25x banner+dock check failed: {proc.stderr}"


def test_h3_ast_expanded_packages_chinese_strings_covered_by_i18n() -> None:
    from core.i18n import UI_PHRASE_MAP, translate_text

    zh_re = re.compile(r"[\u4e00-\u9fff]")
    targets: list[Path] = []
    for folder in ("ai", "analysis", "separation", "streaming", "audio"):
        for p in sorted((REPO_ROOT / folder).rglob("*.py")):
            targets.append(p)

    missing: list[str] = []
    for path in targets:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            val = node.value.strip()
            if not val or not zh_re.search(val):
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Expr):
                gp = parents.get(parent)
                if isinstance(gp, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if gp.body and gp.body[0] is parent:
                        continue
            skip = False
            cur: ast.AST | None = node
            while cur is not None:
                if isinstance(cur, ast.Call):
                    fn = cur.func
                    fn_name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                    if fn_name in ("debug", "info", "warning", "error", "exception", "critical", "tr", "tr_telemetry"):
                        skip = True
                        break
                cur = parents.get(cur)
            if skip or isinstance(parent, ast.JoinedStr):
                continue
            entry = UI_PHRASE_MAP.get(val)
            for lang in ("en", "ja", "ko"):
                if entry is not None and lang in entry:
                    continue
                if translate_text(val, lang) == val:
                    missing.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} [{lang}] {val!r}")
                    break

    assert not missing, f"Untranslated Chinese literals in backend packages ({len(missing)}): {missing[:10]}"


def test_h3_runtime_combos_tables_and_emergency_stop_no_chinese_leak() -> None:
    from PySide6 import QtWidgets
    from core.appearance import Appearance
    from core.models import AIJobResult, AIJobState

    app, win, mixer = _make_window()
    try:
        for lang in ("en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.handle_ai_result(
                AIJobResult(
                    task_id="t_estop",
                    state=AIJobState.EMERGENCY_STOPPED,
                    error="用户点击 紧急停止 AI",
                    stop_reason="user",
                )
            )
            app.processEvents()

            assert not _contains_chinese_for_lang(win.mixer_widget.job_status_lbl.text(), lang), (
                f"[{lang}] job_status_lbl leaked Chinese: {win.mixer_widget.job_status_lbl.text()!r}"
            )
            for combo in win.findChildren(QtWidgets.QComboBox):
                if not combo.isVisible():
                    continue
                for idx in range(combo.count()):
                    txt = combo.itemText(idx)
                    assert not _contains_chinese_for_lang(txt, lang), (
                        f"[{lang}] QComboBox {combo.objectName()!r} item {idx} leaked Chinese: {txt!r}"
                    )
            for tbl in win.findChildren(QtWidgets.QTableWidget):
                for r in range(tbl.rowCount()):
                    for c in range(tbl.columnCount()):
                        it = tbl.item(r, c)
                        if it is not None:
                            assert not _contains_chinese_for_lang(it.text(), lang), (
                                f"[{lang}] QTableWidget cell ({r},{c}) leaked Chinese: {it.text()!r}"
                            )
    finally:
        win.close()
        mixer.close()


def test_h4_status_bar_device_name_elided_with_tooltip_and_actual_device() -> None:
    from core.appearance import Appearance
    from core.models import CaptureMode, CaptureStats

    app, win, mixer = _make_window()
    try:
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        long_dev = "Realtek Digital Output (High Definition Audio Device Very Long Name)"
        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name=long_dev,
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
            ),
            12.0,
        )
        app.processEvents()
        status_txt = win._acid_footer.status_lbl.text()
        assert "Realtek Digital Output" in status_txt
        assert "…" in status_txt or "..." in status_txt, f"Expected ellipsis in {status_txt!r}"
        assert long_dev in win._acid_footer.status_lbl.toolTip()
    finally:
        win.close()
        mixer.close()
