"""Phase 2I verification tests for Issue #94 (I1 startup -9996 & packaging parity; I2 switch counter separation)."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import threading
import time
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


@pytest.mark.xfail(strict=True, reason="I1: startup does not re-enumerate fresh PyAudio instances on -9996")
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


@pytest.mark.xfail(strict=True, reason="I1: spec/installer/workflow lack pyaudiowpatch dynamic libs, InstallDelete, and installed smoke")
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


@pytest.mark.xfail(strict=True, reason="I2: proactive switch shares max_device_reconnects budget with unexpected disconnects")
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
                state["b_open_attempts"] += 1
                if state["b_open_attempts"] <= 4:
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
    )
    backend.start()
    try:
        # Confirm Device A is streaming
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


@pytest.mark.xfail(strict=True, reason="I2: consecutive switches fail when 1st switch exceeds shared reconnect budget")
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

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {"index": self._idx, "name": self._name, "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs: Any) -> _Stream:
            if self._id == "dev-b":
                state["b_attempts"] += 1
                if state["b_attempts"] <= 2:
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
    finally:
        backend.stop()


@pytest.mark.xfail(strict=True, reason="I2: watcher skips polling while switch pending and capture exhausts reconnects")
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
        device_poll_interval_sec=0.03,
    )
    backend.start()
    try:
        # Trigger switch to broken device, wait long enough for retry loop to engage, then rapidly cycle 5 switches
        state["dev_id"], state["dev_name"], state["dev_idx"] = "dev-broken", "Broken Device", 99
        time.sleep(0.15)
        for i in range(1, 6):
            state["dev_id"], state["dev_name"], state["dev_idx"] = f"dev-{i}", f"Device {i}", i
            time.sleep(0.06)

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


@pytest.mark.xfail(strict=True, reason="I2: permanent stop leaves watcher thread alive and restarts leak duplicate watcher")
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
        device_poll_interval_sec=0.04,
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

        # Wait briefly for watcher to wind down cleanly (must not leak after permanent stop)
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
                device_poll_interval_sec=0.04,
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
