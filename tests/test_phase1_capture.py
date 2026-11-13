"""Phase 1 tests: PCM normalization, bounded queue, capture stats, mocked Windows backends, and lifecycle."""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

import numpy as np

from audio.capture_base import BoundedAudioQueue
from audio.pcm_utils import DBFS_FLOOR, compute_rms_and_peak, normalize_to_canonical_pcm
from audio.process_enum import enumerate_audio_processes, resolve_target_pid
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.system_loopback import (
    SYSTEM_LOOPBACK_WARNING,
    SyntheticSimulationBackend,
    WasapiSystemLoopbackBackend,
)
from core.config import AudioConfig
from core.models import CaptureMode


def test_normalize_to_canonical_pcm_and_metering() -> None:
    # 1. int16 mono 44100Hz -> float32 stereo 48000Hz
    sr = 44100
    t = np.arange(sr // 10, dtype=np.float32) / sr
    tone = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    raw_i16 = (tone * 32767.0).astype(np.int16).tobytes()

    stereo = normalize_to_canonical_pcm(
        raw_i16, src_rate=44100, src_channels=1, src_dtype="int16", dst_rate=48000, dst_channels=2
    )
    assert stereo.dtype == np.float32
    assert stereo.ndim == 2 and stereo.shape[1] == 2
    assert abs(stereo.shape[0] - 4800) <= 4
    rms, rms_db, peak, peak_db = compute_rms_and_peak(stereo)
    assert 0.30 < rms < 0.40  # 0.5 / sqrt(2) ~= 0.3535
    assert 0.45 < peak < 0.55
    assert -12.0 < rms_db < -7.0
    assert -7.0 < peak_db < -4.5

    # 2. Silence produces 0.0 / -120 dBFS
    silent = np.zeros((480, 2), dtype=np.float32)
    s_rms, s_rms_db, s_peak, s_peak_db = compute_rms_and_peak(silent)
    assert s_rms == 0.0 and s_peak == 0.0
    assert s_rms_db == DBFS_FLOOR and s_peak_db == DBFS_FLOOR


def test_bounded_audio_queue_drops_oldest_on_overflow() -> None:
    q = BoundedAudioQueue(maxsize=8)
    for i in range(50):
        chunk = np.full((100, 2), float(i), dtype=np.float32)
        q.put_drop_oldest(chunk)

    assert len(q) == 8
    assert q.overruns == 42
    assert q.dropped_frames == 4200
    first = q.get(timeout=0.1)
    assert first is not None
    assert float(first[0, 0]) == 42.0


class _MockNative:
    def __init__(self, proc_specific: bool) -> None:
        self._proc_specific = proc_specific

    def is_process_specific(self) -> bool:
        return self._proc_specific


class _MockBackend:
    def __init__(self, proc_specific: bool) -> None:
        self._native = _MockNative(proc_specific)


class _MockProcTap:
    def __init__(
        self,
        pid: int,
        on_data: Optional[Callable[[bytes, int], None]] = None,
        resample_quality: str = "best",
        proc_specific: bool = True,
    ) -> None:
        self.pid = pid
        self.on_data = on_data
        self.resample_quality = resample_quality
        self._backend = _MockBackend(proc_specific)
        self.is_running = False
        self.closed = False

    def start(self) -> None:
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def close(self) -> None:
        self.is_running = False
        self.closed = True

    def get_format(self) -> dict[str, int | str]:
        return {
            "sample_rate": 48000,
            "channels": 2,
            "bits_per_sample": 32,
            "sample_format": "float32",
        }

    def push_pcm(self, chunk: np.ndarray) -> None:
        assert self.on_data is not None
        # Mimic ProcTap's real behavior of passing -1 as frame count!
        self.on_data(chunk.astype(np.float32).tobytes(), -1)


def test_process_loopback_wrapper_handles_audio_silence_fallback_and_exit() -> None:
    holder: dict[str, _MockProcTap] = {}
    alive = {"flag": True}

    def factory(pid: int, on_data=None, resample_quality: str = "best") -> _MockProcTap:
        tap = _MockProcTap(pid, on_data=on_data, resample_quality=resample_quality, proc_specific=True)
        holder["tap"] = tap
        return tap

    backend = WasapiProcessLoopbackBackend(
        pid=12345,
        process_name="QQMusic.exe",
        tap_factory=factory,
        pid_exists_fn=lambda _pid: alive["flag"],
        allow_non_windows=True,
    )
    backend.start()
    try:
        assert backend.is_running is True
        tap = holder["tap"]

        # Play audio -> non-silent level & real frame count despite ProcTap -1 stub
        t = np.arange(480, dtype=np.float32) / 48000.0
        sine = (0.3 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
        stereo = np.column_stack([sine, sine])
        tap.push_pcm(stereo)
        tap.push_pcm(stereo)

        stats = backend.get_stats()
        assert stats.mode == CaptureMode.PROCESS_LOOPBACK
        assert stats.warning_message is None
        assert stats.total_frames == 960
        assert stats.is_silent is False
        assert stats.rms_linear > 0.15

        # Pause audio -> near silence
        tap.push_pcm(np.zeros((480, 2), dtype=np.float32))
        stats_silent = backend.get_stats()
        assert stats_silent.is_silent is True
        assert stats_silent.rms_dbfs == DBFS_FLOOR

        # Target process exits -> watchdog cleanly stops without crashing
        alive["flag"] = False
        deadline = time.monotonic() + 2.0
        while backend.is_running and time.monotonic() < deadline:
            time.sleep(0.05)
        assert backend.is_running is False
        assert tap.closed is True
        assert "退出" in (backend.get_stats().last_error or "")
    finally:
        backend.stop()


def test_process_loopback_detects_system_fallback_warning() -> None:
    def fallback_factory(pid: int, on_data=None, resample_quality: str = "best") -> _MockProcTap:
        return _MockProcTap(pid, on_data=on_data, resample_quality=resample_quality, proc_specific=False)

    backend = WasapiProcessLoopbackBackend(
        pid=9999,
        process_name="AnyApp.exe",
        tap_factory=fallback_factory,
        pid_exists_fn=lambda _pid: True,
        allow_non_windows=True,
    )
    backend.start()
    try:
        stats = backend.get_stats()
        assert stats.mode == CaptureMode.SYSTEM_LOOPBACK
        assert stats.warning_message is not None and "混入" in stats.warning_message
    finally:
        backend.stop()


class _FakeStream:
    def __init__(self, fail_once: bool = True) -> None:
        self._calls = 0
        self._fail_once = fail_once
        self.closed = False

    def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
        self._calls += 1
        if self._fail_once and self._calls == 2:
            raise OSError("AUDCLNT_E_DEVICE_INVALIDATED")
        time.sleep(0.01)
        arr = np.full((frames, 2), 0.1, dtype=np.float32)
        return arr.tobytes()

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakePyAudio:
    paFloat32 = 1

    def __init__(self) -> None:
        self._open_count = 0

    def get_default_wasapi_loopback(self) -> dict:
        return {
            "index": 0,
            "name": "Speakers (Realtek Audio) [Loopback]",
            "defaultSampleRate": 48000.0,
            "maxInputChannels": 2,
        }

    def open(self, **_kwargs) -> _FakeStream:
        self._open_count += 1
        return _FakeStream(fail_once=(self._open_count == 1))

    def terminate(self) -> None:
        pass


def test_system_loopback_warns_and_survives_device_switch() -> None:
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=lambda: _FakePyAudio(),
        max_device_reconnects=2,
        allow_non_windows=True,
    )
    backend.start()
    try:
        time.sleep(0.6)
        stats = backend.get_stats()
        assert stats.mode == CaptureMode.SYSTEM_LOOPBACK
        assert stats.warning_message == SYSTEM_LOOPBACK_WARNING
        assert stats.buffer_underruns >= 1
        assert stats.total_frames > 0
        assert stats.is_running is True
    finally:
        backend.stop()
    assert backend.is_running is False


def test_synthetic_simulation_lifecycle_and_thread_cleanup() -> None:
    before_threads = threading.active_count()
    cfg = AudioConfig(capture_queue_maxsize=4)
    backend = SyntheticSimulationBackend(pattern="sine", audio_config=cfg)
    backend.start()
    time.sleep(0.25)
    stats = backend.get_stats()
    assert stats.mode == CaptureMode.SYNTHETIC_SIMULATION
    assert stats.total_frames > 0
    assert stats.rms_linear > 0.1
    assert stats.buffer_overruns > 0  # Producer faster than unread maxsize=4 queue
    assert len(backend.queue) <= 4
    backend.stop()
    time.sleep(0.05)
    assert backend.is_running is False
    assert threading.active_count() <= before_threads


def test_process_enum_resolves_current_python_process() -> None:
    procs = enumerate_audio_processes(include_all_running=True)
    assert len(procs) > 0
    pid, name, _ = resolve_target_pid(pid=os.getpid())
    assert pid == os.getpid()
    assert len(name) > 0
