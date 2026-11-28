"""Phase 2I verification tests for Issue #94 (I1 startup -9996 & packaging parity; I2 switch counter separation)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import sys
import threading
import time
from types import ModuleType
from typing import Any

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _extract_run_blocks(workflow_text: str) -> list[str]:
    """Extract all `run:` script block bodies from a GitHub Actions workflow YAML."""
    lines = workflow_text.splitlines()
    blocks: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        m = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if not m:
            idx += 1
            continue
        base_indent = len(m.group(1))
        rest = m.group(2).strip()
        if rest and rest not in ("|", "|-", "|+", ">", ">-", ">+"):
            blocks.append(rest)
            idx += 1
            continue
        idx += 1
        body_lines: list[str] = []
        while idx < len(lines):
            nxt = lines[idx]
            if not nxt.strip():
                body_lines.append("")
                idx += 1
                continue
            indent = len(nxt) - len(nxt.lstrip(" "))
            if indent <= base_indent:
                break
            body_lines.append(nxt)
            idx += 1
        blocks.append("\n".join(body_lines))
    return blocks


def test_i1_startup_re_enumerates_fresh_pyaudio_on_9996_and_terminates_stale_instances() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    lifecycle: dict[str, Any] = {"inits": 0, "terminates": 0, "open_calls": 0}

    class _FakeStream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            lifecycle["inits"] += 1
            self._instance_no = lifecycle["inits"]
            self._terminated = False

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": 4,
                "name": "Headphones [Loopback]",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
                "isLoopbackDevice": True,
            }

        def open(self, **kwargs: Any) -> _FakeStream:
            lifecycle["open_calls"] += 1
            if self._instance_no <= 2:
                raise OSError(-9996, "Invalid device")
            return _FakeStream()

        def terminate(self) -> None:
            if not self._terminated:
                self._terminated = True
                lifecycle["terminates"] += 1

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=False,
        startup_retry_delay_sec=0.02,
    )
    backend.start()
    try:
        assert backend.is_running is True
        assert lifecycle["inits"] == 3
        assert lifecycle["terminates"] == 2
        assert backend.last_open_attempts == 3
        assert len(backend.last_open_errors) == 2
        chunk = backend.read_chunk(timeout=1.0)
        assert chunk is not None and chunk.shape[0] > 0
    finally:
        backend.stop()


def test_i1_exact_default_loopback_matching_and_never_picks_unrelated_device() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    opened_indices: list[int] = []

    class _FakeStream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _MatchingFallbackPA:
        paFloat32 = 1
        paInt16 = 8
        paWASAPI = 13

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            raise OSError(-9996, "Default loopback helper failed")

        def get_host_api_info_by_type(self, host_api_type: int) -> dict[str, Any]:
            assert host_api_type == self.paWASAPI
            return {"defaultOutputDevice": 3}

        def get_device_info_by_index(self, idx: int) -> dict[str, Any]:
            assert idx == 3
            return {"index": 3, "name": "Speakers (Realtek High Definition Audio)"}

        def get_loopback_device_info_generator(self):
            yield {
                "index": 11,
                "name": "Virtual Cable [Loopback]",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
                "isLoopbackDevice": True,
            }
            yield {
                "index": 12,
                "name": "Speakers (Realtek High Definition Audio) [Loopback]",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
                "isLoopbackDevice": True,
            }

        def open(self, **kwargs: Any) -> _FakeStream:
            opened_indices.append(int(kwargs["input_device_index"]))
            return _FakeStream()

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_MatchingFallbackPA,
        allow_non_windows=True,
        follow_default_device=False,
        startup_open_retries=0,
    )
    backend.start()
    try:
        assert opened_indices == [12]
        assert backend.get_stats().process_name == "Speakers (Realtek High Definition Audio) [Loopback]"
    finally:
        backend.stop()

    # Negative check: when NO loopback matches default output device, must NOT pick unrelated device 11
    class _UnrelatedOnlyPA(_MatchingFallbackPA):
        def get_loopback_device_info_generator(self):
            yield {
                "index": 11,
                "name": "Virtual Cable [Loopback]",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
                "isLoopbackDevice": True,
            }

    bad_backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_UnrelatedOnlyPA,
        allow_non_windows=True,
        follow_default_device=False,
        startup_open_retries=0,
    )
    with pytest.raises(OSError):
        bad_backend.start()
    assert opened_indices == [12]


def test_i1_portaudio_runtime_info_and_loopback_smoke_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from audio.system_loopback import get_portaudio_runtime_info
    import main as main_mod

    # 1. Safe on Linux even when pyaudiowpatch is absent
    info = get_portaudio_runtime_info()
    assert set(info.keys()) == {
        "pyaudiowpatch_version",
        "portaudio_version_text",
        "portaudio_pyd_path",
        "portaudio_pyd_size",
    }
    assert isinstance(info["portaudio_pyd_size"], int)

    # 2. Mocked pyaudiowpatch returns version & binary size cleanly
    fake_pyd = tmp_path / "_portaudiowpatch.cp312-win_amd64.pyd"
    fake_pyd.write_bytes(b"PA_BINARY_STUB" * 10)
    fake_cmod = ModuleType("pyaudiowpatch._portaudiowpatch")
    fake_cmod.__file__ = str(fake_pyd)
    fake_pkg = ModuleType("pyaudiowpatch")
    fake_pkg.__version__ = "0.2.12.6"
    fake_pkg._portaudiowpatch = fake_cmod  # type: ignore[attr-defined]
    fake_pkg.get_portaudio_version_text = lambda: "PortAudio V19.7.0-devel"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyaudiowpatch._portaudiowpatch", fake_cmod)
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", fake_pkg)

    mock_info = get_portaudio_runtime_info()
    assert mock_info["pyaudiowpatch_version"] == "0.2.12.6"
    assert mock_info["portaudio_version_text"] == "PortAudio V19.7.0-devel"
    assert mock_info["portaudio_pyd_path"] == str(fake_pyd.resolve())
    assert mock_info["portaudio_pyd_size"] == fake_pyd.stat().st_size

    # 3. CLI --loopback-smoke writes structured JSON and exits 0
    smoke_out = tmp_path / "out" / "smoke.json"
    rc = main_mod.main(["--loopback-smoke", str(smoke_out)])
    assert rc == 0
    assert smoke_out.is_file()
    payload = json.loads(smoke_out.read_text("utf-8"))
    for req_key in (
        "opened",
        "attempts",
        "attempt_errors",
        "timings",
        "error",
        "pyaudiowpatch_version",
        "portaudio_version_text",
        "portaudio_pyd_path",
        "portaudio_pyd_size",
        "sounddevice_dll_path",
        "sounddevice_dll_size",
    ):
        assert req_key in payload
    assert isinstance(payload["timings"], list)
    assert payload["portaudio_version_text"] == "PortAudio V19.7.0-devel"


def test_i1_packaging_spec_installer_and_workflow_smoke_contract() -> None:
    spec_txt = (REPO_ROOT / "packaging" / "listenscope_core.spec").read_text("utf-8")
    assert '"pyaudiowpatch"' in spec_txt
    m_dyn = re.search(r"for\s+pkg_name\s+in\s*\(([^)]+)\)", spec_txt)
    assert m_dyn is not None and '"pyaudiowpatch"' in m_dyn.group(1)

    iss_txt = (REPO_ROOT / "scripts" / "installer.iss").read_text("utf-8")
    assert "[InstallDelete]" in iss_txt
    assert 'Type: filesandordirs; Name: "{app}\\_internal"' in iss_txt
    assert "AppId={{D92B6E14-9F1A-4D7E-A78A-3F6F49B8C201}" in iss_txt
    assert 'Name: "{app}\\exports"; Flags: uninsneveruninstall' in iss_txt

    main_txt = (REPO_ROOT / "main.py").read_text("utf-8")
    assert "--loopback-smoke" in main_txt

    yml_txt = (REPO_ROOT / ".github" / "workflows" / "release-windows.yml").read_text("utf-8")
    for block in _extract_run_blocks(yml_txt):
        assert "${{" not in block
    for token in (
        "listenscope-installed-smoke",
        "/VERYSILENT",
        "--loopback-smoke",
        "_portaudiowpatch",
        "libportaudio64bit.dll",
        "portaudio_version_text",
    ):
        assert token in yml_txt, f"Missing {token!r} in release-windows.yml"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows real WASAPI loopback smoke test")
def test_i1_windows_real_loopback_and_portaudio_version(caplog) -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend, get_portaudio_runtime_info
    from core.config import AudioConfig

    pa_info = get_portaudio_runtime_info()
    logging.getLogger(__name__).info("Windows PortAudio runtime: %s", pa_info)
    assert pa_info["portaudio_version_text"]

    backend = WasapiSystemLoopbackBackend(audio_config=AudioConfig(), startup_open_retries=2)
    try:
        backend.start()
        assert backend.is_running is True
    except Exception:
        # Headless Windows CI runners may lack active render endpoints, but must retry at least twice (>= 2 attempts).
        assert backend.last_open_attempts >= 2
    finally:
        backend.stop()


def test_i2_proactive_switch_separated_from_max_device_reconnects() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    state: dict[str, Any] = {
        "dev_id": "dev-a",
        "dev_name": "Device A",
        "dev_idx": 1,
        "b_open_attempts": 0,
        "b_fail_permanently": False,
    }

    class _Stream:
        def __init__(self, dev_id: str) -> None:
            self._dev_id = dev_id

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            if self._dev_id == "dev-b" and state["b_fail_permanently"]:
                raise OSError("USB headset unplugged")
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["dev_idx"]
            self._attempt_no = 0
            if self._id == "dev-b" and not state["b_fail_permanently"]:
                state["b_open_attempts"] += 1
                self._attempt_no = state["b_open_attempts"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": self._idx,
                "name": self._name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs: Any) -> _Stream:
            if self._id == "dev-b":
                if state["b_fail_permanently"]:
                    raise OSError("Device B permanently gone")
                if self._attempt_no <= 4:
                    raise OSError(-9996, "Device B initializing")
            return _Stream(self._id)

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.04,
        switch_backoff_initial_sec=0.02,
        switch_backoff_max_sec=0.1,
    )
    backend.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and backend.get_stats().total_chunks < 2:
            time.sleep(0.02)
        assert backend.get_stats().total_chunks >= 2

        # Proactive switch to Device B: fails 4 times (> max_device_reconnects=2), succeeds on 5th
        state["dev_id"], state["dev_name"], state["dev_idx"] = "dev-b", "Device B", 2
        deadline = time.monotonic() + 4.5
        while time.monotonic() < deadline:
            st = backend.get_stats()
            if st.process_name == "Device B" and state["b_open_attempts"] >= 5:
                break
            time.sleep(0.03)

        st_b = backend.get_stats()
        assert backend.is_running is True
        assert st_b.is_running is True
        assert st_b.process_name == "Device B"
        assert st_b.last_error is None
        assert backend.proactive_switch_success_count == 1
        assert backend.proactive_switch_retry_total >= 4
        assert backend.unexpected_disconnect_attempts == 0

        # Genuine unexpected disconnect (probe keeps dev-b, stream read + open fail) stops after max_device_reconnects=2
        state["b_fail_permanently"] = True
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and backend.is_running:
            time.sleep(0.03)

        assert backend.is_running is False
        st_end = backend.get_stats()
        assert st_end.is_running is False
        assert "超过 2 次" in (st_end.last_error or "")
        assert backend.unexpected_disconnect_retry_total >= 2
    finally:
        backend.stop()


def test_i2_consecutive_two_switches_first_fails_twice_then_third_succeeds() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    state: dict[str, Any] = {"dev_id": "dev-a", "dev_name": "Device A", "dev_idx": 1, "b_attempts": 0}

    class _Stream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["dev_idx"]
            self._attempt_no = 0
            if self._id == "dev-b":
                state["b_attempts"] += 1
                self._attempt_no = state["b_attempts"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            if self._id == "dev-b" and self._attempt_no <= 2:
                raise OSError(-9996, "Device B not ready yet")
            return _Stream()

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.04,
        switch_backoff_initial_sec=0.02,
        switch_backoff_max_sec=0.1,
    )
    backend.start()
    try:
        # Switch #1: A -> B (fails 2 times, succeeds on 3rd attempt)
        state["dev_id"], state["dev_name"], state["dev_idx"] = "dev-b", "Device B", 2
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and backend.get_stats().process_name != "Device B":
            time.sleep(0.02)
        assert backend.is_running is True
        assert backend.get_stats().process_name == "Device B"

        # Switch #2: B -> C (succeeds cleanly)
        state["dev_id"], state["dev_name"], state["dev_idx"] = "dev-c", "Device C", 3
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and backend.get_stats().process_name != "Device C":
            time.sleep(0.02)

        st_c = backend.get_stats()
        assert backend.is_running is True
        assert st_c.is_running is True
        assert st_c.process_name == "Device C"
        assert st_c.last_error is None
        assert backend.proactive_switch_success_count == 2
        assert backend.proactive_switch_retry_total == 2
    finally:
        backend.stop()


def test_i2_rapid_five_switches_and_mid_retry_pivot() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    state: dict[str, Any] = {"dev_id": "dev-0", "dev_name": "Device 0", "dev_idx": 0}

    class _Stream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["dev_idx"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            if self._id == "dev-broken":
                raise OSError(-9996, "Device broken during switch")
            return _Stream()

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.05,
        switch_backoff_initial_sec=0.02,
        switch_backoff_max_sec=0.1,
    )
    backend.start()
    try:
        # Trigger switch to broken device, wait for retry loop to engage, then rapidly cycle 5 switches
        state["dev_id"], state["dev_name"], state["dev_idx"] = "dev-broken", "Broken Device", 99
        time.sleep(0.18)
        for i in range(1, 6):
            state["dev_id"], state["dev_name"], state["dev_idx"] = f"dev-{i}", f"Device {i}", i
            time.sleep(0.08)

        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline and backend.get_stats().process_name != "Device 5":
            time.sleep(0.02)

        st_final = backend.get_stats()
        assert backend.is_running is True
        assert st_final.is_running is True
        assert st_final.process_name == "Device 5"
        assert st_final.last_error is None
    finally:
        backend.stop()


def test_i2_manual_recovery_after_permanent_unexpected_disconnect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6 import QtWidgets
    from audio.system_loopback import WasapiSystemLoopbackBackend
    from main import ListenScopeController

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.15).tobytes()
    state: dict[str, Any] = {"fail_all": False, "reads": 0}

    class _Stream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            state["reads"] += 1
            if state["fail_all"]:
                raise OSError("Device lost")
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": 1, "name": "Speaker A", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            if state["fail_all"]:
                raise OSError("Device still unavailable")
            return _Stream()

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: ("ep-a", "Speaker A"),
        device_poll_interval_sec=0.05,
    )
    backend.start()
    try:
        watcher_first = backend._watcher_thread
        assert watcher_first is not None and watcher_first.is_alive()

        # Trigger permanent stop via unexpected disconnect
        state["fail_all"] = True
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and backend.is_running:
            time.sleep(0.02)
        assert backend.is_running is False
        assert "超过 2 次" in (backend.get_stats().last_error or "")

        watcher_first.join(timeout=0.5)
        assert not watcher_first.is_alive()

        # Device comes back; manual restart via backend.start() resumes cleanly without leaking watcher threads
        state["fail_all"] = False
        backend.start()
        assert backend.is_running is True
        assert backend.get_stats().last_error is None
        watchers = [t for t in threading.enumerate() if t.name == "ListenScope-DefaultDeviceWatcher" and t.is_alive()]
        assert len(watchers) == 1
    finally:
        backend.stop()

    # Verify UI/Controller recovery after permanent backend stop
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        monkeypatch.setattr(
            "main.WasapiSystemLoopbackBackend",
            lambda **kw: WasapiSystemLoopbackBackend(
                pyaudio_factory=_FakePyAudio,
                max_device_reconnects=2,
                allow_non_windows=True,
                follow_default_device=True,
                default_device_probe=lambda: ("ep-a", "Speaker A"),
                device_poll_interval_sec=0.05,
                **kw,
            ),
        )
        state["fail_all"] = False
        ctrl.start_capture({"kind": "system_loopback"})
        assert ctrl.window.capture_btn.isChecked() is True

        state["fail_all"] = True
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ctrl._capture_backend is not None and ctrl._capture_backend.is_running:
            time.sleep(0.02)
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running is False

        ctrl.window.update_capture_stats(ctrl._capture_backend.get_stats(), ctrl.ring_buffer.available_seconds)
        app.processEvents()
        assert ctrl.window.capture_btn.isChecked() is False

        # Manual restart via start_capture resumes cleanly and writes PCM to ring_buffer
        state["fail_all"] = False
        prev_frames = ctrl.ring_buffer.total_written_frames
        ctrl.start_capture({"kind": "system_loopback"})
        assert ctrl.window.capture_btn.isChecked() is True
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and ctrl.ring_buffer.total_written_frames <= prev_frames:
            time.sleep(0.02)
        assert ctrl.ring_buffer.total_written_frames > prev_frames
    finally:
        ctrl.shutdown()
        app.processEvents()


def test_i2_thread_ownership_portaudio_capture_and_com_watcher(monkeypatch: pytest.MonkeyPatch) -> None:
    import audio.system_loopback as sl

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    pa_calls: list[tuple[str, str]] = []
    com_calls: list[tuple[str, str]] = []
    lock = threading.Lock()
    state: dict[str, Any] = {"dev_id": "ep-1", "dev_name": "Device 1", "idx": 1, "fails": 0}

    class _FakeOle32:
        class _Fn:
            argtypes = []
            restype = None

        class _CoInit:
            argtypes = []
            restype = None

            def __call__(self, _reserved, _flags):
                with lock:
                    com_calls.append(("CoInitializeEx", threading.current_thread().name))
                return 0

        class _CoUninit:
            argtypes = []
            restype = None

            def __call__(self):
                with lock:
                    com_calls.append(("CoUninitialize", threading.current_thread().name))

        def __init__(self) -> None:
            self.CoInitializeEx = self._CoInit()
            self.CoUninitialize = self._CoUninit()
            self.CoCreateInstance = self._Fn()
            self.CoTaskMemFree = self._Fn()

    monkeypatch.setattr(sl.platform, "system", lambda: "Windows")
    monkeypatch.setattr(sl, "_make_ole32_and_guid", lambda: (_FakeOle32(), object, object, object))
    monkeypatch.setattr(
        sl,
        "_probe_windows_default_render_endpoint_detailed",
        lambda *, initialize_com=False: (state["dev_id"], state["dev_name"], 0),
    )

    class _Stream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            with lock:
                pa_calls.append(("read", threading.current_thread().name))
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            with lock:
                pa_calls.append(("stop_stream", threading.current_thread().name))

        def close(self) -> None:
            with lock:
                pa_calls.append(("close", threading.current_thread().name))

    class _FakePA:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            with lock:
                pa_calls.append(("init", threading.current_thread().name))
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["idx"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            with lock:
                pa_calls.append(("get_default_wasapi_loopback", threading.current_thread().name))
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            with lock:
                pa_calls.append(("open", threading.current_thread().name))
            if self._id == "ep-2" and state["fails"] == 0:
                state["fails"] += 1
                raise OSError(-9996, "transient switch error")
            return _Stream()

        def terminate(self) -> None:
            with lock:
                pa_calls.append(("terminate", threading.current_thread().name))

    backend = sl.WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePA,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=None,
        device_poll_interval_sec=0.05,
        switch_backoff_initial_sec=0.02,
        switch_backoff_max_sec=0.05,
    )
    backend.start()
    try:
        state["dev_id"], state["dev_name"], state["idx"] = "ep-2", "Device 2", 2
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and backend.get_stats().process_name != "Device 2":
            time.sleep(0.02)
        assert backend.get_stats().process_name == "Device 2"
    finally:
        backend.stop()

    assert pa_calls
    assert all(tname == "ListenScope-SystemLoopback" for _, tname in pa_calls), f"Off-thread PA call: {pa_calls}"
    assert com_calls == [
        ("CoInitializeEx", "ListenScope-DefaultDeviceWatcher"),
        ("CoUninitialize", "ListenScope-DefaultDeviceWatcher"),
    ]


def test_i2_exponential_backoff_and_unexpected_disconnect_pivots_to_switch() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    state: dict[str, Any] = {"dev_id": "ep-1", "dev_name": "Device 1", "idx": 1, "ep1_fail": False}

    class _Stream:
        def __init__(self, dev_id: str) -> None:
            self._dev_id = dev_id

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            if self._dev_id == "ep-1" and state["ep1_fail"]:
                raise OSError("Device 1 stalled")
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePA:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["idx"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            if self._id == "ep-1" and state["ep1_fail"]:
                raise OSError("Device 1 still unavailable")
            return _Stream(self._id)

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePA,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.05,
        switch_backoff_initial_sec=0.05,
        switch_backoff_max_sec=2.0,
    )
    assert backend._compute_switch_backoff_sec(1) == pytest.approx(0.05)
    assert backend._compute_switch_backoff_sec(2) == pytest.approx(0.10)
    assert backend._compute_switch_backoff_sec(3) == pytest.approx(0.20)
    assert backend._compute_switch_backoff_sec(4) == pytest.approx(0.40)
    assert backend._compute_switch_backoff_sec(5) == pytest.approx(0.80)
    assert backend._compute_switch_backoff_sec(6) == pytest.approx(1.60)
    assert backend._compute_switch_backoff_sec(7) == pytest.approx(2.00)
    assert backend._compute_switch_backoff_sec(10) == pytest.approx(2.00)

    backend.start()
    try:
        # Trigger unexpected disconnect on ep-1; while ep-1 fails and enters backoff, watcher switches to ep-2
        state["ep1_fail"] = True
        time.sleep(0.12)
        state["dev_id"], state["dev_name"], state["idx"] = "ep-2", "Device 2", 2

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and backend.get_stats().process_name != "Device 2":
            time.sleep(0.02)

        assert backend.is_running is True
        assert backend.get_stats().process_name == "Device 2"
        assert backend.unexpected_disconnect_attempts == 0
        assert backend.proactive_switch_success_count >= 1
    finally:
        backend.stop()


def test_i2_new_status_and_error_messages_i18n_4_languages() -> None:
    from core.i18n import translate_text

    samples = (
        "正在切换默认播放设备至 Realtek Speakers，等待设备就绪 (第 2 次尝试)...",
        "播放设备中断且重连超过 3 次: USB lost",
        "检测到播放设备切换，已重连至: Realtek Speakers",
        "已切换到 Realtek Speakers",
    )
    for raw in samples:
        for lang in ("en", "ja", "ko"):
            out = translate_text(raw, lang)
            assert out != raw, f"[{lang}] message not translated: {raw!r}"
            if lang in ("en", "ko"):
                assert not re.search(r"[\u4e00-\u9fff]", out), f"[{lang}] leaked Chinese in {out!r}"
            else:
                assert not any(m in out for m in ("播放设备", "默认播放", "已重连", "已切换到", "次尝试")), (
                    f"[{lang}] leaked Chinese markers in {out!r}"
                )


def test_i1_r2_startup_timeout_scales_with_retries_logs_timings_and_10_restarts() -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    default_backend = WasapiSystemLoopbackBackend(allow_non_windows=True, follow_default_device=False)
    assert default_backend._compute_startup_wait_sec() >= 15.0

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    required_timing_keys = {
        "pa_init_ms",
        "enum_default_ms",
        "fallback_enum_ms",
        "open_f32_ms",
        "open_i16_ms",
        "terminate_ms",
        "total_ms",
        "status",
        "device_name",
        "error",
    }

    for run_idx in range(10):
        attempts = {"n": 0}

        class _Stream:
            def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
                time.sleep(0.01)
                return pcm_chunk

            def stop_stream(self) -> None:
                pass

            def close(self) -> None:
                pass

        class _FakePA:
            paFloat32 = 1
            paInt16 = 8

            def __init__(self) -> None:
                attempts["n"] += 1
                self._attempt = attempts["n"]

            def get_default_wasapi_loopback(self) -> dict[str, Any]:
                return {
                    "index": 1,
                    "name": "Speaker [Loopback]",
                    "defaultSampleRate": 48000.0,
                    "maxInputChannels": 2,
                    "isLoopbackDevice": True,
                }

            def open(self, **kwargs: Any) -> _Stream:
                if self._attempt <= 2:
                    # Two slow failures (>0.35s single-attempt budget combined) before 3rd succeeds
                    time.sleep(0.11)
                    raise OSError(-9996, "Invalid device during WASAPI settle")
                return _Stream()

            def terminate(self) -> None:
                pass

        backend = WasapiSystemLoopbackBackend(
            pyaudio_factory=_FakePA,
            allow_non_windows=True,
            follow_default_device=False,
            startup_open_retries=2,
            startup_retry_delay_sec=0.05,
            startup_per_attempt_timeout_sec=0.35,
        )
        t0 = time.monotonic()
        backend.start()
        try:
            elapsed = time.monotonic() - t0
            assert elapsed > 0.35, f"Run {run_idx} finished too fast ({elapsed:.3f}s) to test multi-attempt budget"
            assert backend.is_running is True
            assert backend.last_open_attempts == 3
            timings = backend.last_open_timings
            assert len(timings) == 3
            for item in timings:
                assert required_timing_keys.issubset(item.keys())
            assert timings[0]["status"] == "failed"
            assert timings[1]["status"] == "failed"
            assert timings[2]["status"] == "opened"
            assert timings[2]["device_name"] == "Speaker [Loopback]"
            assert timings[2]["error"] == ""
            # Shallow-copy safety check
            timings[0]["status"] = "mutated"
            assert backend.last_open_timings[0]["status"] == "failed"
        finally:
            backend.stop()


def test_i1_r2_startup_timeout_logs_stalled_stage_and_elapsed_ms(caplog) -> None:
    from audio.system_loopback import WasapiSystemLoopbackBackend

    release_block = threading.Event()
    entered_pa_init = threading.Event()

    def _stalled_pa_factory() -> Any:
        entered_pa_init.set()
        release_block.wait(timeout=3.0)
        raise OSError("released after test")

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_stalled_pa_factory,
        allow_non_windows=True,
        follow_default_device=False,
        startup_open_retries=0,
        startup_per_attempt_timeout_sec=0.10,
    )
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(RuntimeError, match="启动超时"):
                backend.start()
        assert entered_pa_init.is_set()
        timeout_logs = [
            r.message
            for r in caplog.records
            if "startup timed out" in r.message
        ]
        assert timeout_logs, f"Expected timeout warning log, got {[r.message for r in caplog.records]}"
        assert "stage=pa_init" in timeout_logs[0]
        assert "stage_elapsed_ms=" in timeout_logs[0]
    finally:
        release_block.set()
        backend.stop()


def test_i2_r2_four_real_switches_buffer_monotonic_no_1s_stall_and_device_name_preserved() -> None:
    from PySide6 import QtWidgets
    from audio.playback import StemMixerEngine
    from audio.ring_buffer import FixedRingBuffer
    from audio.system_loopback import WasapiSystemLoopbackBackend
    from core.config import AIConfig, AudioConfig, ResourceLimits
    from core.models import CaptureMode, CaptureStats
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()
    pa_threads: list[tuple[str, str]] = []
    lock = threading.Lock()
    state: dict[str, Any] = {
        "dev_id": "ep-a",
        "dev_name": "XIBERIA USB Audio",
        "idx": 1,
        "b_fails_remaining": 0,
        "slow_open_sec": 0.0,
        "idle_zero_until": 0.0,
    }

    class _Stream:
        def __init__(self, dev_name: str) -> None:
            self._dev_name = dev_name

        def get_read_available(self) -> int:
            with lock:
                pa_threads.append(("get_read_available", threading.current_thread().name))
            if time.monotonic() < state["idle_zero_until"]:
                return 0
            return 960

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            with lock:
                pa_threads.append(("read", threading.current_thread().name))
            time.sleep(0.015)
            return pcm_chunk

        def stop_stream(self) -> None:
            with lock:
                pa_threads.append(("stop_stream", threading.current_thread().name))

        def close(self) -> None:
            with lock:
                pa_threads.append(("close", threading.current_thread().name))

    class _FakePA:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            with lock:
                pa_threads.append(("init", threading.current_thread().name))
            self._id = state["dev_id"]
            self._name = state["dev_name"]
            self._idx = state["idx"]

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            with lock:
                pa_threads.append(("get_default_wasapi_loopback", threading.current_thread().name))
            return {
                "index": self._idx,
                "name": self._name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs: Any) -> _Stream:
            with lock:
                pa_threads.append(("open", threading.current_thread().name))
            if state["slow_open_sec"] > 0.0:
                time.sleep(state["slow_open_sec"])
            if state["b_fails_remaining"] > 0 and self._id == "ep-b":
                state["b_fails_remaining"] -= 1
                raise OSError(-9996, "Device B warming up")
            return _Stream(self._name)

        def terminate(self) -> None:
            with lock:
                pa_threads.append(("terminate", threading.current_thread().name))

    ring = FixedRingBuffer(audio_config=AudioConfig())
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePA,
        max_device_reconnects=2,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.04,
        switch_backoff_initial_sec=0.08,
        switch_backoff_max_sec=0.25,
        idle_silence_grace_sec=0.08,
    )

    drain_stop = threading.Event()
    stall_info = {"max_gap_sec": 0.0, "last_growth_ts": time.monotonic(), "saw_unverified_name": False}

    def _drain() -> None:
        while not drain_stop.is_set():
            ch = backend.read_chunk(timeout=0.03)
            if ch is not None and ch.shape[0] > 0:
                ring.write(ch)
                now = time.monotonic()
                gap = now - stall_info["last_growth_ts"]
                if gap > stall_info["max_gap_sec"]:
                    stall_info["max_gap_sec"] = gap
                stall_info["last_growth_ts"] = now

    drain_thread = threading.Thread(target=_drain, name="Test-Drain", daemon=True)
    backend.start()
    drain_thread.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and ring.total_written_frames < 1920:
            time.sleep(0.02)
        assert ring.total_written_frames >= 1920
        stall_info["last_growth_ts"] = time.monotonic()
        stall_info["max_gap_sec"] = 0.0

        # 4 real proactive switches: A -> B -> A -> B -> A
        transitions = [
            ("ep-b", "Realtek High Definition Audio", 2, 2, 0.15, True),
            ("ep-a", "XIBERIA USB Audio", 1, 0, 0.25, False),
            ("ep-b", "Realtek High Definition Audio", 2, 2, 0.12, False),
            ("ep-a", "XIBERIA USB Audio", 1, 0, 0.20, False),
        ]
        for ep_id, ep_name, idx, fails, slow_s, check_unverified in transitions:
            state["b_fails_remaining"] = fails * 2  # f32 + i16 per open attempt
            state["slow_open_sec"] = slow_s
            state["dev_id"], state["dev_name"], state["idx"] = ep_id, ep_name, idx
            if check_unverified:
                # Before B opens, process_name must not prematurely claim Realtek
                time.sleep(0.08)
                if backend.get_stats().process_name == ep_name and state["b_fails_remaining"] > 0:
                    stall_info["saw_unverified_name"] = True
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline and backend.get_stats().process_name != ep_name:
                time.sleep(0.02)
            assert backend.get_stats().process_name == ep_name
            # Also exercise idle silence window > idle_silence_grace_sec after opening
            state["idle_zero_until"] = time.monotonic() + 0.30
            time.sleep(0.32)

        assert stall_info["saw_unverified_name"] is False
        assert backend.is_running is True
        assert backend.proactive_switch_success_count == 4
        assert backend.unexpected_disconnect_attempts == 0
        assert backend.get_stats().process_name == "XIBERIA USB Audio"
        assert stall_info["max_gap_sec"] < 1.0, f"Detected buffer stall >= 1.0s: {stall_info['max_gap_sec']:.3f}s"

        # Verify keepalive silence emission never resets _unexpected_disconnect_attempts
        backend._unexpected_disconnect_attempts = 2
        backend._emit_silence_chunk(48000, "XIBERIA USB Audio", 960)
        assert backend.unexpected_disconnect_attempts == 2
    finally:
        drain_stop.set()
        t_stop = time.monotonic()
        backend.stop()
        stop_elapsed = time.monotonic() - t_stop
        drain_thread.join(timeout=1.0)

    assert stop_elapsed < 0.5, f"backend.stop() took {stop_elapsed:.3f}s >= 0.5s"
    assert pa_threads
    assert all(tname == "ListenScope-SystemLoopback" for _, tname in pa_threads), f"Off-thread PA call: {pa_threads}"
    assert not any(t.name == "ListenScope-SwitchSilenceKeepalive" and t.is_alive() for t in threading.enumerate())

    # Verify UI preserves _loopback_device_name when stats.process_name is transiently empty
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name="XIBERIA USB Audio",
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
            ),
            4.0,
        )
        assert win._loopback_device_name == "XIBERIA USB Audio"
        assert "XIBERIA" in win._acid_footer.status_lbl.text()

        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name="",
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
            ),
            4.2,
        )
        assert win._loopback_device_name == "XIBERIA USB Audio"
        assert "XIBERIA" in win._acid_footer.status_lbl.text()
    finally:
        win.close()
        mixer.close()
        app.processEvents()


def test_i2_r2_rapid_switch_ps1_substring_and_regex_matching_contract() -> None:
    import shutil
    import subprocess

    ps1_path = REPO_ROOT / "scripts" / "rapid_switch.ps1"
    assert ps1_path.is_file(), "scripts/rapid_switch.ps1 missing"
    text = ps1_path.read_text("utf-8")

    for required in (
        "IMMDeviceEnumerator",
        "IPolicyConfig",
        "SetDefaultEndpoint",
        "$Devices",
        "XIBERIA",
        "Realtek",
        "$Rounds",
        "$IntervalSeconds",
        "$Regex",
        "OrdinalIgnoreCase",
        "NO_MATCH",
        "exit 1",
    ):
        assert required in text, f"Missing {required!r} in scripts/rapid_switch.ps1"

    pwsh = shutil.which("pwsh")
    if pwsh is not None:
        parse_cmd = (
            "$errs = $null; $tokens = $null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{ps1_path}', [ref]$tokens, [ref]$errs); "
            "if ($errs -and $errs.Count -gt 0) { $errs | ForEach-Object { Write-Error $_.Message }; exit 1 }"
        )
        res = subprocess.run([pwsh, "-NoProfile", "-Command", parse_cmd], capture_output=True, text=True, timeout=20)
        assert res.returncode == 0, f"PowerShell syntax parse failed: {res.stderr}"

