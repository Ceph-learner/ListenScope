"""Regression tests covering all audit findings and cross-platform/resource hardening fixes."""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import soundfile as sf
from PySide6 import QtWidgets

from ai.job_manager import AIJobManager
from ai.resource_guard import inspect_wav_header, stream_chunked_separation
from analysis.fft import SpectrumAnalyzer
from analysis.midi_transcription import transcribe_stem_to_midi
from audio.pcm_utils import normalize_to_canonical_pcm
from audio.playback import StemMixerEngine
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import SYSTEM_LOOPBACK_WARNING, WasapiSystemLoopbackBackend
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.logging import PerformanceLogger
from core.models import AIJobRequest, AIJobState, CaptureMode, CaptureStats, SystemHardwareReport
from core.resource_manager import ResourceManager, SimulationOverrides
from main import ListenScopeController
from streaming.live_separator import ExperimentalLiveSeparator
from ui.main_window import ListenScopeMainWindow


def test_capture_test_cli_runs_from_outside_repo() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "/home/antigravity/ListenScope/capture_test.py",
            "--simulate",
            "switching",
            "--duration",
            "0.6",
        ],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=15.0,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Synthetic" in proc.stdout or "capture_test" in proc.stdout or "Frames" in proc.stdout


def test_midi_transcription_model_path_float32_24bit_and_cli(tmp_path) -> None:
    sr = 48000
    t = np.arange(int(sr * 0.8), dtype=np.float32) / float(sr)
    tone = (0.3 * np.sin(2.0 * np.pi * 110.0 * t)).astype(np.float32)
    stereo = np.column_stack([tone, tone])

    wav_f32 = tmp_path / "bass_f32.wav"
    wav_24 = tmp_path / "bass_pcm24.wav"
    sf.write(str(wav_f32), stereo, sr, subtype="FLOAT")
    sf.write(str(wav_24), stereo, sr, subtype="PCM_24")

    res_f32 = transcribe_stem_to_midi(
        wav_f32,
        tmp_path / "f32.mid",
        stem_name="bass",
        allow_cpu_pitch_fallback=True,
    )
    assert res_f32.output_midi_path is not None and res_f32.output_midi_path.exists()
    assert any(abs(n.pitch_midi - 45) <= 1 for n in res_f32.notes)

    res_24 = transcribe_stem_to_midi(
        wav_24,
        tmp_path / "p24.mid",
        stem_name="bass",
        allow_cpu_pitch_fallback=True,
    )
    assert any(abs(n.pitch_midi - 45) <= 1 for n in res_24.notes)

    # Mock Basic Pitch verifying explicit `model_or_model_path=ICASSP_2022_MODEL_PATH`
    seen: dict[str, object] = {}

    class _FakeMidiData:
        def write(self, path: str) -> None:
            Path(path).write_bytes(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0MTrk\x00\x00\x00\x04\x00\xff/\x00")

    def _fake_predict(audio_path: str, model_or_model_path=None):
        seen["audio_path"] = audio_path
        seen["model_or_model_path"] = model_or_model_path
        return {}, _FakeMidiData(), [(0.0, 0.5, 45, 0.85, None)]

    fake_bp = types.ModuleType("basic_pitch")
    fake_bp.ICASSP_2022_MODEL_PATH = "/mock/icassp_2022_nmp"
    fake_bp_inf = types.ModuleType("basic_pitch.inference")
    fake_bp_inf.predict = _fake_predict

    orig_bp = sys.modules.get("basic_pitch")
    orig_bp_inf = sys.modules.get("basic_pitch.inference")
    sys.modules["basic_pitch"] = fake_bp
    sys.modules["basic_pitch.inference"] = fake_bp_inf
    try:
        res_bp = transcribe_stem_to_midi(
            wav_f32,
            tmp_path / "bp.mid",
            stem_name="bass",
            allow_cpu_pitch_fallback=False,
        )
        assert seen["model_or_model_path"] == "/mock/icassp_2022_nmp"
        assert res_bp.backend_used == "basic-pitch"
        assert len(res_bp.notes) == 1 and res_bp.notes[0].pitch_midi == 45
    finally:
        if orig_bp is None:
            sys.modules.pop("basic_pitch", None)
        else:
            sys.modules["basic_pitch"] = orig_bp
        if orig_bp_inf is None:
            sys.modules.pop("basic_pitch.inference", None)
        else:
            sys.modules["basic_pitch.inference"] = orig_bp_inf

    # CLI execution `-m analysis.midi_transcription --json`
    cli_mid = tmp_path / "cli_out.mid"
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "analysis.midi_transcription",
            "--audio",
            str(wav_24),
            "--output-midi",
            str(cli_mid),
            "--stem-name",
            "bass",
            "--allow-cpu-fallback",
            "--json",
        ],
        cwd="/home/antigravity/ListenScope",
        capture_output=True,
        text=True,
        timeout=15.0,
        check=True,
    )
    payload = json.loads(cli.stdout.strip().splitlines()[-1])
    assert payload["source_stem_name"] == "bass"
    assert cli_mid.exists()


def test_resource_guard_and_stem_mixer_float32_24bit_and_resample(tmp_path) -> None:
    sr_src = 44100
    t = np.arange(sr_src, dtype=np.float32) / float(sr_src)
    tone = (0.25 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    stereo = np.column_stack([tone, tone * 0.5])

    wav_f32 = tmp_path / "mix_f32_44k.wav"
    wav_24 = tmp_path / "voc_24_44k.wav"
    sf.write(str(wav_f32), stereo, sr_src, subtype="FLOAT")
    sf.write(str(wav_24), stereo, sr_src, subtype="PCM_24")

    meta_f32 = inspect_wav_header(wav_f32)
    meta_24 = inspect_wav_header(wav_24)
    assert abs(meta_f32.duration_sec - 1.0) < 0.02
    assert meta_24.sample_width == 3

    out_dir = tmp_path / "chunked_out"
    stems = stream_chunked_separation(
        wav_f32,
        out_dir,
        ("vocals", "instrumental"),
        lambda pcm, _sr: {"vocals": pcm * 0.5, "instrumental": pcm * 0.5},
        chunk_seconds=0.5,
        overlap_seconds=0.1,
    )
    assert Path(stems["vocals"]).exists() and Path(stems["instrumental"]).exists()

    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    try:
        tracks = mixer.load_stems({"vocals": wav_f32, "bass": wav_24})
        assert set(tracks.keys()) == {"vocals", "bass"}
        # Resampled track length aligns to 48000 frames (~1s)
        assert abs(tracks["vocals"].total_frames - 48000) <= 5
        mixer.play(open_audio_device=False)
        blk = mixer.render_block(2048)
        assert blk.shape == (2048, 2)
        assert np.all(np.isfinite(blk)) and float(np.max(np.abs(blk))) > 0.01

        exp_wav = tmp_path / "exported_48k.wav"
        mixer.export_mix_streaming(exp_wav)
        exp_info = sf.info(str(exp_wav))
        assert exp_info.samplerate == 48000

        # Mock 30-min native_total_frames to ensure envelope stays bounded in read size and returns immediately
        tracks["vocals"].native_total_frames = 44100 * 1800
        t0 = time.monotonic()
        mins, maxs = mixer.get_stem_waveform_envelope("vocals", num_points=240)
        assert time.monotonic() - t0 < 0.5
        assert mins.shape == (240,) and maxs.shape == (240,)
    finally:
        mixer.clear()


def test_live_separator_nonblocking_benchmark_and_cancel_during_start(monkeypatch) -> None:
    rb = FixedRingBuffer(AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10))
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    live = ExperimentalLiveSeparator(rb, rm)

    entered_bench = threading.Event()
    release_bench = threading.Event()

    def _slow_bench(*_args, **_kwargs):
        entered_bench.set()
        release_bench.wait(timeout=3.0)
        from streaming.benchmark import LiveBenchmarkResult

        return LiveBenchmarkResult(
            model_id="mdx_low_vram_2stem",
            device_used="MockCPU",
            test_duration_sec=2.0,
            elapsed_sec=0.2,
            rtf=0.1,
            can_run_realtime=True,
            message="ok",
        )

    monkeypatch.setattr(live, "run_benchmark", _slow_bench)

    result_holder: list[tuple[bool, str]] = []

    def _starter() -> None:
        result_holder.append(
            live.start(model_id="mdx_low_vram_2stem", use_gpu=False, use_mock_backend=True, skip_benchmark=False)
        )

    th = threading.Thread(target=_starter, daemon=True)
    th.start()
    assert entered_bench.wait(timeout=2.0)

    # Non-blocking telemetry query while benchmark runs
    t0 = time.monotonic()
    _ = live.is_active
    metrics = live.latest_metrics()
    assert time.monotonic() - t0 < 0.1
    assert metrics.active is False

    # User clicks stop while benchmark is still running -> must cancel cleanly with no spawned zombie worker
    live.stop(status_message="cancelled")
    release_bench.set()
    th.join(timeout=3.0)
    assert len(result_holder) == 1 and result_holder[0][0] is False
    assert live.is_active is False
    assert live._proc is None
    rm.close()


def test_process_loopback_nan_sanitization_and_fft_finite_guard() -> None:
    spec = SpectrumAnalyzer(48000)
    bad = np.ones((spec.fft_size,), dtype=np.float32)
    bad[100] = np.nan
    bad[200] = np.inf
    mag, fft_db, log_db = spec.analyze_frame(bad)
    assert np.all(np.isfinite(mag)) and np.all(np.isfinite(fft_db)) and np.all(np.isfinite(log_db))

    class _FmtTap:
        def __init__(self, pid, on_data=None, resample_quality="best"):
            self.on_data = on_data
            self._backend = types.SimpleNamespace(_native=types.SimpleNamespace(is_process_specific=lambda: True))
            self.closed = False

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            self.closed = True

        def get_format(self):
            return {"sample_rate": 48000, "channels": 2, "bits_per_sample": 32, "sample_format": "float32"}

    holder = {}
    backend = WasapiProcessLoopbackBackend(
        pid=999,
        process_name="QQMusic.exe",
        tap_factory=lambda pid, on_data=None, resample_quality="best": holder.setdefault(
            "t", _FmtTap(pid, on_data, resample_quality)
        ),
        pid_exists_fn=lambda _p: True,
        allow_non_windows=True,
    )
    backend.start()
    try:
        arr = np.full((480, 2), np.nan, dtype=np.float32)
        arr[:10, :] = 0.2
        holder["t"].on_data(arr.tobytes(), -1)
        out = backend.read_chunk(timeout=0.5)
        assert out is not None
        assert np.all(np.isfinite(out))
    finally:
        backend.stop()


def test_system_loopback_output_channels_and_int16_fallback() -> None:
    class _Int16OnlyStream:
        def __init__(self):
            self.closed = False

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            tone = np.full((frames, 2), 4000, dtype=np.int16)
            return tone.tobytes()

        def stop_stream(self):
            pass

        def close(self):
            self.closed = True

    class _FallbackPyAudio:
        paFloat32 = 1
        paInt16 = 8

        def get_default_wasapi_loopback(self):
            return {
                "index": 1,
                "name": "Bluetooth Headset [Loopback]",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 0,
                "maxOutputChannels": 2,
            }

        def open(self, **kwargs):
            if kwargs["format"] == self.paFloat32:
                raise OSError("Invalid sample format paFloat32")
            assert kwargs["channels"] == 2
            return _Int16OnlyStream()

        def terminate(self):
            pass

    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=lambda: _FallbackPyAudio(),
        allow_non_windows=True,
    )
    backend.start()
    try:
        chunk = backend.read_chunk(timeout=1.5)
        assert chunk is not None
        assert chunk.dtype == np.float32
        assert np.all(np.isfinite(chunk))
        assert float(np.mean(np.abs(chunk))) > 0.05
        assert backend.get_stats().warning_message == SYSTEM_LOOPBACK_WARNING
    finally:
        backend.stop()


def test_job_manager_external_stdout_retains_terminal_result_when_queue_full(tmp_path) -> None:
    """Emit >280 progress JSON lines before terminal result over external AI stdout protocol."""
    wav_path = tmp_path / "short.wav"
    sf.write(str(wav_path), np.zeros((48000, 2), dtype=np.float32), 48000, subtype="PCM_16")

    # Create a tiny python wrapper that forwards everything EXCEPT ai.worker flood test
    flood_pkg = tmp_path / "flood_runner.py"
    flood_pkg.write_text(
        """
import json, sys, pathlib
# Emit 320 progress lines immediately without pause, then result
for i in range(320):
    print(json.dumps({
        "type": "progress",
        "payload": {
            "task_id": "flood_job",
            "state": "Inferring",
            "progress": i / 320.0,
            "message": f"chunk {i}",
        }
    }), flush=True)
print(json.dumps({
    "type": "result",
    "payload": {
        "task_id": "flood_job",
        "state": "Completed",
        "stem_paths": {},
        "elapsed_sec": 0.1,
        "input_duration_sec": 1.0,
        "device_used": "MockCPU",
        "model_id": "mdx_low_vram_2stem",
        "architecture": "MDX-ONNX"
    }
}), flush=True)
""".strip(),
        encoding="utf-8",
    )

    # Create wrapper executable pointing to sys.executable `-u` behavior by monkeypatching Popen in AIJobManager test
    wrapper = tmp_path / "fake_ai_py.sh"
    wrapper.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{flood_pkg}" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)

    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"), ai_python_executable=str(wrapper))
    req = AIJobRequest(
        task_id="flood_job",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "out"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
    )
    ok, _ = mgr.submit_job(req)
    assert ok is True
    res = mgr.wait_for_completion(timeout=10.0)
    assert res is not None and res.state == AIJobState.COMPLETED
    rm.close()


def test_main_window_does_not_clobber_transient_banner_and_controller_bridges(tmp_path) -> None:
    from core.system_probe import probe_system

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mixer = StemMixerEngine()
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        sys_stats = CaptureStats(
            mode=CaptureMode.SYSTEM_LOOPBACK,
            pid=None,
            process_name="SystemLoopback",
            sample_rate=48000,
            channels=2,
            dtype="float32",
            is_running=True,
            warning_message=SYSTEM_LOOPBACK_WARNING,
        )
        win.update_capture_stats(sys_stats, 5.0)
        assert SYSTEM_LOOPBACK_WARNING in win.notice_banner.text()
        assert "[混入警告]" in win.capture_status_lbl.text()

        # Subsequent transient banner must NOT be clobbered on repeated stats refresh ticks!
        win.show_banner_message("已选定最近 10.0s 历史片段")
        win.update_capture_stats(sys_stats, 6.0)
        assert win.notice_banner.text() == "已选定最近 10.0s 历史片段"
        assert "[混入警告]" in win.capture_status_lbl.text()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()

    # Controller bridge: _on_send_stem_to_analysis loads 44.1kHz IEEE float32 WAV and pauses playback safely
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws2")
    try:
        f32_stem = tmp_path / "stem_bass_f32.wav"
        t = np.arange(44100, dtype=np.float32) / 44100.0
        tone = (0.3 * np.sin(2.0 * np.pi * 110.0 * t)).astype(np.float32)
        sf.write(str(f32_stem), np.column_stack([tone, tone]), 44100, subtype="FLOAT")

        ctrl._on_send_stem_to_analysis("bass", str(f32_stem))
        assert ctrl.ring_buffer.available_seconds > 0.9
        assert "bass" in ctrl.window.notice_banner.text()

        # Verify mutual playback exclusion: ab_player -> mixer_widget play_btn -> ab_play
        ctrl.window.mixer_widget.load_stem_paths({"bass": str(f32_stem)})
        ctrl._on_ab_play()
        assert ctrl.ab_player.is_playing is True
        ctrl.window.mixer_widget.play_btn.click()
        app.processEvents()
        assert ctrl.ab_player.is_playing is False
        assert ctrl.mixer_engine.is_playing is True
        ctrl._on_ab_play()
        assert ctrl.mixer_engine.is_playing is False
        assert ctrl.ab_player.is_playing is True
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()
