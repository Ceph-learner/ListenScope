"""Audit Pass 3 regression tests covering worker launch/monitor safety, UI lifecycles, capture watchdog, A/B rollover, and alignment."""

from __future__ import annotations

import gc
import json
import os
import queue
import sys
import threading
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

from ai.job_manager import AIJobManager
from ai.resource_guard import stream_chunked_separation
from analysis.stem_analyzer import export_transcription_sheet
from audio.playback import HistoryABPlayer
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.logging import PerformanceLogger
from core.models import (
    AIJobRequest,
    AIJobState,
    ChordTimelineSegment,
    KeyEstimate,
    StemDeepAnalysisReport,
    SystemHardwareReport,
    TempoEstimate,
)
from core.resource_manager import ResourceManager
from core.settings_store import load_settings
from main import ListenScopeController
from streaming.benchmark import benchmark_live_model_isolated
from streaming.live_separator import ExperimentalLiveSeparator
from ui.settings_dialog import SettingsDialog


def _write_test_wav(path: Path, seconds: float = 1.2, sr: int = 48000, freq: float = 440.0) -> Path:
    n = int(round(seconds * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    sig = (0.35 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)
    stereo = np.column_stack([sig, sig])
    i16 = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(i16.tobytes())
    return path


def test_ai_job_manager_recovers_cleanly_on_launch_failure_and_monitor_error(tmp_path: Path) -> None:
    wav_path = _write_test_wav(tmp_path / "excerpt.wav", seconds=1.0)
    rm = ResourceManager()
    perf = PerformanceLogger(log_dir=tmp_path / "perf")
    bad_py = str(tmp_path / "nonexistent_python_bin")
    mgr = AIJobManager(rm, performance_logger=perf, ai_python_executable=bad_py)
    try:
        req = AIJobRequest(
            task_id="bad_launch",
            input_wav_path=str(wav_path),
            output_dir=str(tmp_path / "out_bad"),
            stem_mode="2stem",
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
        )
        ok, msg = mgr.submit_job(req)
        assert not ok
        assert "启动 AI Worker 子进程失败" in msg
        assert mgr.is_busy is False
        assert rm.sample().active_ai_jobs == 0

        # Subsequent valid job using current interpreter must still succeed
        mgr.ai_python_executable = None
        results = []
        done = threading.Event()
        mgr.add_completion_callback(lambda r: (results.append(r), done.set()))
        req2 = AIJobRequest(
            task_id="good_after_bad",
            input_wav_path=str(wav_path),
            output_dir=str(tmp_path / "out_good"),
            stem_mode="2stem",
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
        )
        ok2, _ = mgr.submit_job(req2)
        assert ok2
        assert done.wait(timeout=15.0)
        assert results and results[0].state == AIJobState.COMPLETED
        assert mgr.is_busy is False

        # Monitor loop exception (e.g., malformed payload) must finalize cleanly instead of leaving is_busy stuck
        done2 = threading.Event()
        results2 = []
        mgr2 = AIJobManager(rm, performance_logger=perf)
        try:
            mgr2.add_completion_callback(lambda r: (results2.append(r), done2.set()))
            q: queue.Queue[dict[str, object]] = queue.Queue()
            q.put({"type": "progress", "payload": {"bad_missing_task_id": True}})
            req3 = AIJobRequest(
                task_id="bad_msg",
                input_wav_path=str(wav_path),
                output_dir=str(tmp_path / "out_bad_msg"),
                stem_mode="2stem",
                model_id="mdx_low_vram_2stem",
                use_gpu=False,
                use_mock_backend=True,
            )
            mgr2._active_request = req3
            mgr2._result_dispatched = False
            mgr2._done_event.clear()
            mgr2._stop_monitor.clear()
            mgr2._msg_queue = q
            mgr2._monitor_loop(req3)
            assert done2.is_set()
            assert results2 and results2[0].state == AIJobState.FAILED
            assert mgr2.is_busy is False
        finally:
            mgr2.shutdown()
    finally:
        mgr.shutdown()
        rm.close()


def test_ai_job_manager_serialized_emergency_stop_concurrency(tmp_path: Path) -> None:
    rm = ResourceManager()
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))
    try:
        barrier = threading.Barrier(2)

        def _call() -> None:
            barrier.wait(timeout=2.0)
            mgr.emergency_stop("concurrent check")

        t1 = threading.Thread(target=_call)
        t2 = threading.Thread(target=_call)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        assert not t1.is_alive() and not t2.is_alive()
        assert mgr.is_busy is False
        assert mgr._accepting_jobs is True
        assert mgr._emergency_stopping is False
    finally:
        mgr.shutdown()
        rm.close()


def _make_dummy_hw_report(*, gpu_ai_ready: bool = False) -> SystemHardwareReport:
    return SystemHardwareReport(
        timestamp_utc="2026-11-13 00:00:00 UTC",
        os_system="Windows",
        os_release="11",
        os_version="10.0.22631",
        architecture="AMD64",
        is_windows=True,
        windows_build=22631,
        wasapi_process_loopback_supported=True,
        python_version="3.11.9",
        git_version="git version 2.45.0",
        cpu_model="Test CPU",
        cpu_cores_logical=16,
        ram_total_mb=16384.0,
        ram_available_mb=12288.0,
        gpu_ai_ready=gpu_ai_ready,
        gpu_ai_block_reason=None if gpu_ai_ready else "test",
    )


def test_settings_dialog_done_guards_probe_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    started = threading.Event()
    release = threading.Event()

    def _slow_probe(_py: str, **_kw):
        started.set()
        release.wait(timeout=2.0)
        return {"ok": False, "error": "delayed"}

    monkeypatch.setattr("ui.settings_dialog.probe_external_ai_environment", _slow_probe)

    dlg = SettingsDialog(_make_dummy_hw_report(), ResourceLimits(), AIConfig())
    dlg.show()
    dlg._verify_ai_environment()
    assert started.wait(timeout=2.0)
    # QDialog.reject() invokes done(), not closeEvent()
    dlg.reject()
    assert dlg._dialog_closed is True
    dlg.deleteLater()
    _app.processEvents()
    release.set()
    time.sleep(0.08)
    _app.processEvents()


def test_process_loopback_watchdog_stops_when_tap_disconnects() -> None:
    class _FakeTap:
        def __init__(self) -> None:
            self.is_running = True

        def get_format(self) -> dict[str, object]:
            return {"sample_rate": 48000, "channels": 2, "sample_format": "float32"}

        def start(self) -> None:
            self.is_running = True

        def close(self) -> None:
            self.is_running = False

    fake_tap = _FakeTap()
    backend = WasapiProcessLoopbackBackend(
        pid=4242,
        process_name="QQMusic.exe",
        tap_factory=lambda **_kw: fake_tap,
        pid_exists_fn=lambda _pid: True,
        allow_non_windows=True,
    )
    try:
        backend.start()
        assert backend.is_running is True
        # Underlying tap silently drops without target process exiting
        fake_tap.is_running = False
        deadline = time.monotonic() + 2.0
        while backend.get_stats().is_running and time.monotonic() < deadline:
            time.sleep(0.05)
        st = backend.get_stats()
        assert st.is_running is False
        assert st.last_error is not None and "断开" in st.last_error
    finally:
        backend.stop()


def test_ab_player_rejects_rolled_out_range_and_controller_syncs_stems(tmp_path: Path) -> None:
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        work_dir=tmp_path / "ws",
        settings_path=tmp_path / "settings.json",
    )
    try:
        small_cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=2)
        rb = FixedRingBuffer(audio_config=small_cfg)
        player = HistoryABPlayer(rb, audio_config=small_cfg)
        rb.write(np.zeros((48000, 2), dtype=np.float32))
        player.set_ab_range(0, 24000)
        # Overwrite ring buffer past frame 24000 (oldest becomes > 24000)
        rb.write(np.zeros((48000 * 2, 2), dtype=np.float32))
        assert rb.oldest_abs_frame > 24000
        with pytest.raises(ValueError, match="滚出"):
            player.start_playback(open_audio_device=False)

        # Controller: out-of-buffer A/B range shows banner warning instead of 1-sample collapse
        ctrl.ring_buffer.write(np.zeros((48000 * 3, 2), dtype=np.float32))
        ctrl.ab_player.select_recent_seconds(2.0)
        prev_range = ctrl.ab_player.loop_range
        ctrl._on_ab_set_range(60.0, 40.0)
        assert ctrl.ab_player.loop_range == prev_range
        assert "超出当前已缓冲范围" in ctrl.window.notice_banner.text()

        # Controller: failed submit cleans orphan task_dir
        rm_before = list((ctrl.work_dir / "stems").glob("job_*")) if (ctrl.work_dir / "stems").exists() else []
        assert len(rm_before) == 0
        ctrl.ai_job_manager._accepting_jobs = False
        try:
            ctrl._on_start_ai_separation("2stem", "mdx_low_vram_2stem", 256, False)
        finally:
            ctrl.ai_job_manager._accepting_jobs = True
        assert list((ctrl.work_dir / "stems").glob("job_*")) == []

        # Controller: _on_send_stem_to_analysis keeps ab_player and coverage synced
        stem_wav = _write_test_wav(tmp_path / "vocals.wav", seconds=2.0, freq=523.25)
        ctrl._on_send_stem_to_analysis("vocals", str(stem_wav))
        a, b = ctrl.ab_player.loop_range
        assert (b - a) == pytest.approx(2.0 * 48000, abs=128)
        assert "2.0" in ctrl.window.history_coverage_lbl.text()

        # Controller: invalid missing ai_python clears prior gpu_ai_ready=True
        ctrl.hardware_report = _make_dummy_hw_report(gpu_ai_ready=True)
        ctrl.window.update_hardware_report(ctrl.hardware_report, auto_sync_gpu_chk=True)
        assert ctrl.window.ai_gpu_chk.isChecked() is True
        ctrl._on_settings_applied(ctrl.resource_limits, ctrl.ai_config, str(tmp_path / "missing_py.exe"))
        assert ctrl.hardware_report.gpu_ai_ready is False
        assert ctrl.window.ai_gpu_chk.isChecked() is False
    finally:
        ctrl.shutdown()
        del ctrl
        _app.processEvents()
        gc.collect()


def test_benchmark_cancel_event_and_chunk_stem_alignment(tmp_path: Path) -> None:
    cancel_ev = threading.Event()
    threading.Timer(0.15, cancel_ev.set).start()
    with pytest.raises(InterruptedError):
        benchmark_live_model_isolated(
            model_id="mdx_low_vram_2stem",
            ai_python_executable=sys.executable,
            use_gpu=False,
            use_mock_backend=True,
            simulate_delay_sec=1.5,
            test_duration_sec=2.0,
            cancel_event=cancel_ev,
        )

    # Short output on one stem must zero-pad to exact core_len so stems stay frame-aligned
    in_wav = _write_test_wav(tmp_path / "align_in.wav", seconds=1.2)
    out_dir = tmp_path / "align_out"

    def _short_sep(pcm: np.ndarray, _sr: int) -> dict[str, np.ndarray]:
        n = pcm.shape[0]
        return {
            "vocals": np.ones((n, 2), dtype=np.float32) * 0.2,
            "instrumental": np.ones((max(1, n // 4), 2), dtype=np.float32) * 0.3,
        }

    stems = stream_chunked_separation(
        in_wav,
        out_dir,
        ("vocals", "instrumental"),
        _short_sep,
        chunk_seconds=1.0,
        overlap_seconds=0.1,
    )
    with wave.open(stems["vocals"], "rb") as wv, wave.open(stems["instrumental"], "rb") as wi:
        assert wv.getnframes() == wi.getnframes() == int(round(1.2 * 48000))


def test_csv_utf8_sig_bom_and_config_finite_validation(tmp_path: Path) -> None:
    report = StemDeepAnalysisReport(
        duration_sec=1.0,
        harmonic_source_label="instrumental",
        estimated_key=KeyEstimate("C major", "A minor", "Stable", 0.8, 0.2, "相对大小调", "0"),
        estimated_bpm=TempoEstimate(120.0, "Stable", 0.7),
        chord_timeline=[ChordTimelineSegment(0.0, 1.0, "C", "Am", 0.9, "Stable")],
    )
    csv_path = export_transcription_sheet(report, tmp_path / "chords.csv")
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")

    with pytest.raises(ValueError, match="finite and positive"):
        ResourceLimits(min_ram_before_ai_mb=float("nan"))
    with pytest.raises(ValueError, match="demucs_segment_ladder"):
        AIConfig(demucs_segment_ladder=())
    with pytest.raises(ValueError, match="finite and positive"):
        AIConfig(long_audio_chunk_seconds=0.0)

    bad_json = tmp_path / "bad_settings.json"
    bad_json.write_text(
        json.dumps(
            {
                "resource_limits": {"min_ram_before_ai_mb": -100.0},
                "ai_config": {"long_audio_chunk_seconds": 0.0, "demucs_segment_ladder": []},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_settings(bad_json)
    assert loaded.resource_limits == ResourceLimits()
    assert loaded.ai_config == AIConfig()
