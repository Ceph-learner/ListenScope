"""Resource safety, leak, OOM, low RAM, 30-min streaming, worker kill, and Emergency Stop verification (Tests A-J equivalents)."""

from __future__ import annotations

import gc
import os
import signal
import time
import wave

import numpy as np
import psutil

from ai.job_manager import AIJobManager
from analysis.worker import AnalysisWorker
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import SyntheticSimulationBackend
from core.config import AIConfig, AnalysisConfig, AudioConfig, ResourceLimits
from core.logging import PerformanceLogger
from core.models import AIJobRequest, AIJobState, OOMRecoveryAction
from core.resource_manager import ResourceManager, SimulationOverrides


def _stream_generate_long_wav(path, total_seconds: float, sr: int = 48000, chunk_seconds: float = 20.0) -> None:
    """Write a multi-minute stereo WAV to disk chunk-by-chunk without holding full song in RAM."""
    chunk_frames = int(chunk_seconds * sr)
    t = np.arange(chunk_frames, dtype=np.float32) / float(sr)
    tone = (0.25 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    chunk_i16 = (np.column_stack([tone, tone * 0.7]) * 32767.0).astype(np.int16).tobytes()

    total_frames = int(total_seconds * sr)
    written = 0
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        while written < total_frames:
            take = min(chunk_frames, total_frames - written)
            if take == chunk_frames:
                wf.writeframes(chunk_i16)
            else:
                wf.writeframes(chunk_i16[: take * 4])
            written += take


def test_accelerated_30min_cpu_dsp_and_ring_buffer_zero_leak() -> None:
    """Accelerated Linux equivalent of Tests A/B/C endurance (>30 min audio processed, strictly bounded memory).

    NOTE: Real Windows WASAPI 30-minute capture & device switching remain `未在 Windows 真机验证`.
    """
    aud_cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=120)
    an_cfg = AnalysisConfig(spectrum_history_seconds=30, chroma_history_seconds=120, analysis_rate_hz=15.0)
    rb = FixedRingBuffer(aud_cfg)
    worker = AnalysisWorker(rb, audio_config=aud_cfg, analysis_config=an_cfg)
    rm = ResourceManager(ResourceLimits(monitor_history_maxlen=60))

    proc = psutil.Process(os.getpid())
    # Warm all 120s demand-zero OS virtual pages of FixedRingBuffer + DSP history first
    t = np.arange(48000, dtype=np.float32) / 48000.0
    one_sec = np.column_stack([
        (0.2 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32),
        (0.2 * np.sin(2.0 * np.pi * 329.63 * t)).astype(np.float32),
    ])
    for _ in range(120):
        rb.write(one_sec)
    for _ in range(60):
        worker.analyze_latest_once()
        rm.sample()
    gc.collect()
    base_rss = proc.memory_info().rss / (1024.0 * 1024.0)

    # Simulate an additional 32 minutes (1920 seconds) wrapping the full 120s buffer 16x over
    for sec_idx in range(1920):
        rb.write(one_sec)
        if sec_idx % 4 == 0:
            worker.analyze_latest_once()
            rm.sample()

    gc.collect()
    end_rss = proc.memory_info().rss / (1024.0 * 1024.0)
    assert rb.buffer_nbytes == 46_080_000
    assert rb.available_frames == 48000 * 120
    assert len(rm.history) <= 60
    assert worker.spectrum.recent_log_spectrogram().shape[0] <= worker.spectrum.history_maxlen
    assert worker.chroma.recent_chroma_matrix().shape[0] <= worker.chroma.history_maxlen
    assert (end_rss - base_rss) < 35.0, f"Unexpected memory growth: {base_rss:.1f} -> {end_rss:.1f} MB"
    rm.close()


def test_5x_consecutive_ai_separations_release_memory_and_exit_workers(tmp_path) -> None:
    """Test D: Run 5 consecutive spawn AI separations on a 30s WAV and check worker exit & no cumulative leak."""
    wav_path = tmp_path / "sample_30s.wav"
    _stream_generate_long_wav(wav_path, total_seconds=30.0)

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    parent_proc = psutil.Process(os.getpid())
    gc.collect()
    parent_start_mb = parent_proc.memory_info().rss / (1024.0 * 1024.0)
    worker_peaks: list[float] = []

    for i in range(5):
        req = AIJobRequest(
            task_id=f"rep_{i}",
            input_wav_path=str(wav_path),
            output_dir=str(tmp_path / f"out_{i}"),
            stem_mode="2stem" if i % 2 == 0 else "4stem",
            model_id="mdx_low_vram_2stem" if i % 2 == 0 else "htdemucs_4stem",
            use_gpu=False,
            chunk_seconds=15.0,
            use_mock_backend=True,
        )
        ok, _ = mgr.submit_job(req)
        assert ok is True
        res = mgr.wait_for_completion(timeout=30.0)
        assert res is not None and res.state == AIJobState.COMPLETED
        assert rm.sample().active_ai_jobs == 0
        assert rm.sample().ai_worker_ram_mb == 0.0
        worker_peaks.append(res.peak_ram_mb)

    gc.collect()
    parent_end_mb = parent_proc.memory_info().rss / (1024.0 * 1024.0)
    # Main process did not load models; child workers exited cleanly after each run
    assert (parent_end_mb - parent_start_mb) < 30.0
    assert max(worker_peaks) < 350.0
    rm.close()


def test_gpu_oom_reports_3_recovery_options_without_infinite_retry(tmp_path) -> None:
    """Test F: Trigger OOM inside worker -> AIJobState.OOM_ERROR, 3 options, no retry loop, main app healthy."""
    wav_path = tmp_path / "oom_in.wav"
    _stream_generate_long_wav(wav_path, total_seconds=4.0)

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    req = AIJobRequest(
        task_id="oom_job",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "oom_out"),
        stem_mode="4stem",
        model_id="htdemucs_4stem",
        use_gpu=False,
        simulate_oom=True,
        use_mock_backend=True,
    )
    ok, _ = mgr.submit_job(req)
    assert ok is True
    res = mgr.wait_for_completion(timeout=15.0)
    assert res is not None
    assert res.state == AIJobState.OOM_ERROR
    assert res.oom_occurred is True
    assert res.recovery_options == [
        OOMRecoveryAction.REDUCE_SEGMENT,
        OOMRecoveryAction.LIGHTER_MODEL,
        OOMRecoveryAction.CPU_FALLBACK,
    ]
    assert not (tmp_path / "oom_out" / ".tmp_oom_job").exists()
    assert mgr.is_busy is False
    rm.close()


def test_low_ram_blocks_and_auto_triggers_emergency_stop(tmp_path) -> None:
    """Test G: Available RAM < 3GB refuses start; available RAM dropping < 2GB mid-job triggers Emergency Stop."""
    wav_path = tmp_path / "ram_in.wav"
    _stream_generate_long_wav(wav_path, total_seconds=6.0)

    rm = ResourceManager(ResourceLimits())
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    # < 3GB -> refuse start
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=2500.0))
    req = AIJobRequest(
        task_id="ram_blocked",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "out_ram"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
    )
    ok, reason = mgr.submit_job(req)
    assert ok is False
    assert "3072" in reason or "拒绝" in reason

    # Start healthy, then inject critical RAM (< 2048 MB) mid-job -> auto emergency stop
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    slow_req = AIJobRequest(
        task_id="ram_crit",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "out_ram_crit"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        chunk_seconds=2.0,
        simulate_delay_sec=0.4,
        use_mock_backend=True,
    )
    ok2, _ = mgr.submit_job(slow_req)
    assert ok2 is True
    time.sleep(0.25)
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=1800.0))

    res = mgr.wait_for_completion(timeout=15.0)
    assert res is not None and res.state == AIJobState.EMERGENCY_STOPPED
    assert not (tmp_path / "out_ram_crit" / ".tmp_ram_crit").exists()
    assert mgr.is_busy is False
    rm.close()


def test_30_minute_long_audio_streaming_chunked_separation_low_ram(tmp_path) -> None:
    """Test H: Stream-separate an 1800-second (30-min) stereo WAV chunk-by-chunk with tiny bounded peak RAM."""
    wav_path = tmp_path / "song_30min.wav"
    _stream_generate_long_wav(wav_path, total_seconds=1800.0, chunk_seconds=20.0)
    assert wav_path.stat().st_size > 300_000_000  # ~345 MB WAV on disk

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    out_dir = tmp_path / "out_30min"
    req = AIJobRequest(
        task_id="long_30min",
        input_wav_path=str(wav_path),
        output_dir=str(out_dir),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        chunk_seconds=20.0,  # 90 chunks streamed sequentially
        use_mock_backend=True,
    )
    ok, note = mgr.submit_job(req)
    assert ok is True
    assert "长音频" in note or "分块" in note

    res = mgr.wait_for_completion(timeout=120.0)
    assert res is not None and res.state == AIJobState.COMPLETED
    assert abs(res.input_duration_sec - 1800.0) < 1.0
    # Full 30-min uncompressed float32 + 2 stems would consume > 1000 MB; streaming chunk I/O stays < 350 MB RSS
    assert res.peak_ram_mb < 350.0, f"Peak worker RAM too high for 30-min streaming: {res.peak_ram_mb:.1f} MB"

    with wave.open(res.stem_paths["vocals"], "rb") as wf:
        assert wf.getnframes() == 1800 * 48000
    assert not (out_dir / ".tmp_long_30min").exists()
    rm.close()


def test_ai_worker_kill_resilience_and_emergency_stop_keep_capture_running(tmp_path) -> None:
    """Tests I & J: Kill AI worker abruptly OR click Emergency Stop AI; main capture + CPU DSP keep running."""
    wav_path = tmp_path / "kill_in.wav"
    _stream_generate_long_wav(wav_path, total_seconds=8.0)

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    rb = FixedRingBuffer(AudioConfig())
    an = AnalysisWorker(rb)
    cap = SyntheticSimulationBackend(pattern="switching")
    cap.start()
    an.start()
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    try:
        # Test I: force-kill AI worker PID mid-inference
        out_i = tmp_path / "out_i"
        req_i = AIJobRequest(
            task_id="kill_test",
            input_wav_path=str(wav_path),
            output_dir=str(out_i),
            stem_mode="2stem",
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            chunk_seconds=2.0,
            simulate_delay_sec=0.5,
            use_mock_backend=True,
        )
        ok_i, _ = mgr.submit_job(req_i)
        assert ok_i is True
        time.sleep(0.25)
        wpid = mgr.worker_pid
        assert wpid is not None
        os.kill(wpid, signal.SIGKILL)

        res_i = mgr.wait_for_completion(timeout=10.0)
        assert res_i is not None and res_i.state == AIJobState.FAILED
        assert not (out_i / ".tmp_kill_test").exists()
        assert cap.is_running and an.is_running

        # Feed live capture chunks to ring buffer & confirm DSP keeps running
        for _ in range(3):
            ch = cap.read_chunk(timeout=0.2)
            if ch is not None:
                rb.write(ch)
        snap_before = an.analyze_latest_once()
        assert snap_before.rms_dbfs > -50.0

        # Test J: Emergency Stop AI mid-job
        out_j = tmp_path / "out_j"
        req_j = AIJobRequest(
            task_id="estop_test",
            input_wav_path=str(wav_path),
            output_dir=str(out_j),
            stem_mode="4stem",
            model_id="htdemucs_4stem",
            use_gpu=False,
            chunk_seconds=2.0,
            simulate_delay_sec=0.5,
            use_mock_backend=True,
        )
        ok_j, _ = mgr.submit_job(req_j)
        assert ok_j is True
        time.sleep(0.25)

        rsnap = mgr.emergency_stop("Test J 紧急停止")
        assert rsnap.active_ai_jobs == 0
        assert mgr.is_busy is False
        assert not (out_j / ".tmp_estop_test").exists()
        assert mgr.last_result().state == AIJobState.EMERGENCY_STOPPED

        # Capture + CPU analysis continue normally and accept new AI jobs after recovery
        assert cap.is_running and an.is_running
    finally:
        mgr.shutdown()
        an.stop()
        cap.stop()
        rm.close()
