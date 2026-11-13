"""Phase 12 regression & feature tests covering audit fixes (#1-#8) and new UX capabilities."""

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
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import soundfile as sf
from PySide6 import QtWidgets

from ai.job_manager import AIJobManager
from analysis.chords import ChordDetector
from analysis.chroma import ChromaExtractor
from analysis.midi_transcription import _fallback_monophonic_stem_to_notes
from analysis.stem_analyzer import analyze_stems_offline
from audio.playback import StemMixerEngine
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import WasapiSystemLoopbackBackend
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.logging import PerformanceLogger
from core.models import (
    AIJobRequest,
    AIJobState,
    ChordTimelineSegment,
    KeyEstimate,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    StemDeepAnalysisReport,
    TempoEstimate,
)
from core.paths import get_bundle_root
from core.resource_manager import ResourceManager, SimulationOverrides
from core.system_probe import (
    GPUInfo,
    OnnxRuntimeProbeInfo,
    PyTorchProbeInfo,
    SystemHardwareReport,
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_system,
)
from main import ListenScopeController, _discover_ai_python_executable
from streaming.live_separator import ExperimentalLiveSeparator
from ui.settings_dialog import SettingsDialog


def _write_stereo_wav(path: Path, mono: np.ndarray, *, sr: int = 48000) -> Path:
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    sf.write(str(path), stereo, sr, subtype="PCM_16")
    return path


def _make_py_wrapper(tmp_path: Path, name: str = "ext_ai_py.sh") -> Path:
    wrapper = tmp_path / name
    wrapper.write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def test_bug1_ai_job_manager_heavy_stderr_no_deadlock_and_crash_surface(tmp_path: Path) -> None:
    wav_path = tmp_path / "short.wav"
    sf.write(str(wav_path), np.zeros((24000, 2), dtype=np.float32), 48000, subtype="PCM_16")

    # 1. Script writing >150KB to stderr before terminal JSON result must not deadlock stdout/stderr pipes
    heavy_script = tmp_path / "heavy_stderr_worker.py"
    heavy_script.write_text(
        """
import json, sys
for i in range(1600):
    sys.stderr.write(f"warning chunk {i}: " + ("X" * 90) + "\\n")
sys.stderr.flush()
print(json.dumps({
    "type": "result",
    "payload": {
        "task_id": "heavy_err_job",
        "state": "Completed",
        "stem_paths": {},
        "elapsed_sec": 0.1,
        "input_duration_sec": 0.5,
        "device_used": "MockCPU",
        "model_id": "mdx_low_vram_2stem",
        "architecture": "MDX-ONNX"
    }
}), flush=True)
""".strip(),
        encoding="utf-8",
    )
    wrapper_ok = tmp_path / "ext_heavy_ok.sh"
    wrapper_ok.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{heavy_script}" "$@"\n', encoding="utf-8")
    wrapper_ok.chmod(0o755)

    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    try:
        mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf1"), ai_python_executable=str(wrapper_ok))
        ok, _ = mgr.submit_job(
            AIJobRequest(
                task_id="heavy_err_job",
                input_wav_path=str(wav_path),
                output_dir=str(tmp_path / "out1"),
                stem_mode="2stem",
                model_id="mdx_low_vram_2stem",
                use_gpu=False,
                use_mock_backend=True,
            )
        )
        assert ok is True
        res = mgr.wait_for_completion(timeout=10.0)
        assert res is not None and res.state == AIJobState.COMPLETED

        # 2. Crashing external worker without JSON output surfaces stderr tail cleanly in AIJobResult.error
        crash_script = tmp_path / "crash_worker.py"
        crash_script.write_text(
            'import sys; sys.stderr.write("FATAL: synthetic CUDA DLL mismatch\\n"); sys.stderr.flush(); sys.exit(2)\n',
            encoding="utf-8",
        )
        wrapper_crash = tmp_path / "ext_crash.sh"
        wrapper_crash.write_text(
            f'#!/usr/bin/env bash\nexec "{sys.executable}" "{crash_script}" "$@"\n', encoding="utf-8"
        )
        wrapper_crash.chmod(0o755)
        mgr.ai_python_executable = str(wrapper_crash)
        ok2, _ = mgr.submit_job(
            AIJobRequest(
                task_id="crash_job",
                input_wav_path=str(wav_path),
                output_dir=str(tmp_path / "out2"),
                stem_mode="2stem",
                model_id="mdx_low_vram_2stem",
                use_gpu=False,
                use_mock_backend=True,
            )
        )
        assert ok2 is True
        res2 = mgr.wait_for_completion(timeout=10.0)
        assert res2 is not None and res2.state == AIJobState.FAILED
        assert res2.error is not None and "synthetic CUDA DLL mismatch" in res2.error
    finally:
        rm.close()


def test_bug2_external_probe_report_merge_and_live_ui_sync(tmp_path: Path, monkeypatch) -> None:
    core_report = SystemHardwareReport(
        timestamp_utc="2026-01-01 00:00:00 UTC",
        os_system="Windows",
        os_release="11",
        os_version="10.0.22631",
        architecture="AMD64",
        is_windows=True,
        windows_build=22631,
        wasapi_process_loopback_supported=True,
        python_version="3.11.9",
        git_version=None,
        cpu_model="Test CPU",
        cpu_cores_logical=16,
        ram_total_mb=16384.0,
        ram_available_mb=12000.0,
        gpus=[],
        nvidia_driver_version=None,
        nvml_available=False,
        nvidia_smi_available=False,
        pytorch=PyTorchProbeInfo(installed=False),
        onnxruntime=OnnxRuntimeProbeInfo(installed=False),
        gpu_ai_ready=False,
        gpu_ai_block_reason="Core has no torch",
    )

    ready_probe = {
        "ok": True,
        "python_executable": str(tmp_path / "ai_py"),
        "gpus": [
            {
                "index": 0,
                "name": "NVIDIA GeForce RTX 5060 Ti",
                "total_vram_mb": 8192.0,
                "used_vram_mb": 512.0,
                "free_vram_mb": 7680.0,
                "utilization_pct": 5.0,
                "driver_version": "572.60",
                "source": "nvml",
            }
        ],
        "nvidia_driver_version": "572.60",
        "nvml_available": True,
        "nvidia_smi_available": True,
        "pytorch": {
            "installed": True,
            "version": "2.7.0+cu128",
            "cuda_available": True,
            "cuda_build": "12.8",
            "device_count": 1,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "compute_capability": [12, 0],
            "arch_list": ["sm_90", "sm_120"],
            "supports_sm_120": True,
            "kernel_smoke_test_passed": True,
            "error": None,
        },
        "onnxruntime": {
            "installed": True,
            "version": "1.21.0",
            "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "cuda_provider_available": True,
            "error": None,
        },
        "ai_packages": {"demucs": {"installed": True, "version": "4.0.1"}},
    }
    merged_ready = apply_external_ai_probe_to_report(core_report, ready_probe)
    assert merged_ready.gpu_ai_ready is True
    assert merged_ready.gpu_ai_block_reason is None
    assert merged_ready.gpus[0].total_vram_mb == 8192.0

    # Must stay BLOCKED when sm_120 is missing or CUDAExecutionProvider is absent
    bad_sm120 = json.loads(json.dumps(ready_probe))
    bad_sm120["pytorch"]["supports_sm_120"] = False
    merged_bad_sm = apply_external_ai_probe_to_report(core_report, bad_sm120)
    assert merged_bad_sm.gpu_ai_ready is False
    assert "sm_120" in (merged_bad_sm.gpu_ai_block_reason or "")

    bad_ort = json.loads(json.dumps(ready_probe))
    bad_ort["onnxruntime"]["cuda_provider_available"] = False
    bad_ort["onnxruntime"]["providers"] = ["CPUExecutionProvider"]
    merged_bad_ort = apply_external_ai_probe_to_report(core_report, bad_ort)
    assert merged_bad_ort.gpu_ai_ready is False
    assert "CUDAExecutionProvider" in (merged_bad_ort.gpu_ai_block_reason or "")

    # SettingsDialog live status_table update + Controller async external probe update
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr("ui.settings_dialog.probe_external_ai_environment", lambda _py: dict(ready_probe))
    dlg = SettingsDialog(core_report, ResourceLimits(), AIConfig(), ai_python_executable=ready_probe["python_executable"])
    try:
        dlg._verify_ai_environment()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not dlg.verify_ai_env_btn.isEnabled():
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()
        assert dlg.verified_report.gpu_ai_ready is True
        assert any("READY" in (dlg.status_table.item(r, 1).text()) for r in range(dlg.status_table.rowCount()))
    finally:
        dlg.close()

    # Controller startup async external probe merges READY status into ai_gpu_chk
    ext_wrapper = _make_py_wrapper(tmp_path)
    monkeypatch.setattr(
        "main.probe_external_ai_environment",
        lambda _py, **_kw: {**ready_probe, "python_executable": str(ext_wrapper)},
    )
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        ai_python_executable=str(ext_wrapper),
        work_dir=tmp_path / "ws_probe",
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not ctrl.hardware_report.gpu_ai_ready:
            app.processEvents()
            time.sleep(0.03)
        app.processEvents()
        assert ctrl.hardware_report.gpu_ai_ready is True
        assert ctrl.window.ai_gpu_chk.isChecked() is True
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()
        gc.collect()
        app.processEvents()


def test_bug3_live_separator_external_python_and_benchmark_isolation(tmp_path: Path) -> None:
    ext_wrapper = _make_py_wrapper(tmp_path)
    rb = FixedRingBuffer(AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10))
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))

    # Write 2.5s of 440Hz stereo tone
    sr = 48000
    t = np.arange(int(sr * 2.5), dtype=np.float32) / float(sr)
    tone = (0.35 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    rb.write(np.column_stack([tone, tone]))

    live = ExperimentalLiveSeparator(
        rb,
        rm,
        ai_config=AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.2, live_max_buffer_seconds=4.0),
        ai_python_executable=str(ext_wrapper),
    )
    try:
        bench = live.run_benchmark("mdx_low_vram_2stem", use_gpu=False, use_mock_backend=True)
        assert bench.can_run_realtime is True
        assert bench.rtf < 1.0

        ok, msg = live.start(
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
            skip_benchmark=True,
        )
        assert ok is True, msg
        assert live._proc is None
        assert live._subproc is not None

        # Feed additional fresh audio frames and confirm separated output arrives over JSON+b64 pipe
        rb.write(np.column_stack([tone, tone]))
        deadline = time.monotonic() + 8.0
        got_audio = False
        while time.monotonic() < deadline:
            blk = live.pull_mixed_block(2048)
            if float(np.max(np.abs(blk))) > 0.01:
                got_audio = True
                break
            time.sleep(0.05)
        assert got_audio is True
    finally:
        live.stop()
        assert live._subproc is None
        assert live.is_active is False
        rm.close()


def test_bug4_frozen_paths_discovery_and_non_mock_guard(tmp_path: Path, monkeypatch) -> None:
    fake_meipass = tmp_path / "ListenScopeCore" / "_internal"
    fake_exe = tmp_path / "ListenScopeCore" / "ListenScope.exe"
    fake_meipass.mkdir(parents=True)
    fake_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_exe.write_bytes(b"")

    ext_py = tmp_path / ".venv-ai" / "bin" / "python"
    ext_py.parent.mkdir(parents=True, exist_ok=True)
    ext_py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr("main.ROOT", fake_meipass)

    assert get_bundle_root() == fake_meipass.resolve()
    discovered = _discover_ai_python_executable()
    assert discovered == str(ext_py)

    # Probe & AI jobs refuse frozen execution cleanly if .venv-ai is empty (no recursive exe launch!)
    res_probe = probe_external_ai_environment("")
    assert res_probe["ok"] is False
    assert ".venv-ai" in res_probe["error"]

    wav_path = tmp_path / "x.wav"
    sf.write(str(wav_path), np.zeros((24000, 2), dtype=np.float32), 48000, subtype="PCM_16")
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    try:
        mgr = AIJobManager(rm, ai_python_executable=None)
        ok, msg = mgr.submit_job(
            AIJobRequest(
                task_id="frozen_no_env",
                input_wav_path=str(wav_path),
                output_dir=str(tmp_path / "out"),
                stem_mode="2stem",
                model_id="mdx_low_vram_2stem",
                use_gpu=False,
                use_mock_backend=False,
            )
        )
        assert ok is False
        assert ".venv-ai" in msg

        rb = FixedRingBuffer(AudioConfig())
        live = ExperimentalLiveSeparator(rb, rm, ai_python_executable=None)
        ok_live, msg_live = live.start(model_id="mdx_low_vram_2stem", use_gpu=False, use_mock_backend=False)
        assert ok_live is False
        assert ".venv-ai" in msg_live
    finally:
        rm.close()


def test_bug5_json_clis_redirect_noisy_stdout_to_stderr(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    t = np.arange(24000, dtype=np.float32) / 48000.0
    _write_stereo_wav(wav_path, (0.3 * np.sin(2.0 * np.pi * 110.0 * t)).astype(np.float32))
    out_mid = tmp_path / "out.mid"

    runner = tmp_path / "noisy_runner.py"
    runner.write_text(
        """
import os, runpy, sys
import soundfile as sf
sys.path.insert(0, os.getcwd())
orig_sf = sf.SoundFile
def noisy_sf(*a, **kw):
    print("BANNER NOISE INSIDE LIBRARY CALL!", flush=True)
    return orig_sf(*a, **kw)
sf.SoundFile = noisy_sf
sys.argv = ["analysis.midi_transcription"] + sys.argv[1:]
runpy.run_module("analysis.midi_transcription", run_name="__main__")
""".strip(),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--audio",
            str(wav_path),
            "--output-midi",
            str(out_mid),
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
    assert "BANNER NOISE" not in proc.stdout
    assert "BANNER NOISE" in proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["source_stem_name"] == "bass"


def test_bug6_capture_reconnect_interrupts_fast_and_failed_start_closes_tap() -> None:
    # 1. System loopback stop interrupts reconnect wait quickly instead of sleeping full backoff
    class _FailingStream:
        def read(self, _frames: int, exception_on_overflow: bool = False) -> bytes:
            raise OSError("Device disconnected")

        def stop_stream(self):
            pass

        def close(self):
            pass

    class _FailingPA:
        paFloat32 = 1
        paInt16 = 8

        def get_default_wasapi_loopback(self):
            return {
                "index": 0,
                "name": "Dummy Out",
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **_kw):
            return _FailingStream()

        def terminate(self):
            pass

    sys_be = WasapiSystemLoopbackBackend(
        pyaudio_factory=lambda: _FailingPA(),
        max_device_reconnects=10,
        allow_non_windows=True,
    )
    sys_be.start()
    time.sleep(0.06)
    t0 = time.monotonic()
    sys_be.stop()
    assert time.monotonic() - t0 < 0.5
    assert sys_be.is_running is False

    # 2. Process loopback start failure closes tap & leaves queue/stats cleanly closed
    holder = {}

    class _BrokenStartTap:
        def __init__(self, pid, on_data=None, resample_quality="best"):
            self.closed = False

        def get_format(self):
            return {"sample_rate": 48000, "channels": 2, "sample_format": "float32"}

        def start(self):
            raise RuntimeError("WASAPI activate failed")

        def close(self):
            self.closed = True

    proc_be = WasapiProcessLoopbackBackend(
        pid=1234,
        process_name="QQMusic.exe",
        tap_factory=lambda pid, on_data=None, resample_quality="best": holder.setdefault(
            "t", _BrokenStartTap(pid, on_data, resample_quality)
        ),
        pid_exists_fn=lambda _p: True,
        allow_non_windows=True,
    )
    with pytest.raises(RuntimeError):
        proc_be.start()
    assert holder["t"].closed is True
    assert proc_be.is_running is False
    assert proc_be.get_stats().is_running is False
    assert proc_be._cached_fmt == {}


def test_bug7_mixer_nonblocking_export_load_cleanup_and_ring_buffer_empty_guard(tmp_path: Path) -> None:
    sr = 48000
    t = np.arange(sr * 2, dtype=np.float32) / float(sr)
    tone = (0.3 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    wav_ok = _write_stereo_wav(tmp_path / "ok.wav", tone, sr=sr)
    bad_wav = tmp_path / "bad.wav"
    bad_wav.write_bytes(b"NOT_A_WAV_FILE")

    mixer = StemMixerEngine(sample_rate=sr, channels=2)
    try:
        # Bad second stem triggers clean rollback closing already opened handles
        with pytest.raises(Exception):
            mixer.load_stems({"ok": wav_ok, "bad": bad_wav})
        assert mixer.tracks == {}
        assert mixer._wave_handles == {}

        mixer.load_stems({"vocals": wav_ok})
        mixer.seek(sr // 2)
        mixer.play(open_audio_device=False)

        # Slow down _read_track_chunk_from_handle slightly only for export test? No need:
        # Run concurrent export + property/render reads and assert zero position corruption
        out_mix = tmp_path / "mix.wav"
        pos_before = mixer.position_frame
        exc_holder: list[Exception] = []

        def _exp() -> None:
            try:
                mixer.export_mix_streaming(out_mix, chunk_frames=16384)
            except Exception as exc:
                exc_holder.append(exc)

        th = threading.Thread(target=_exp, daemon=True)
        th.start()
        t0 = time.monotonic()
        _ = mixer.position_sec
        blk = mixer.render_block(256, advance=False)
        elapsed_read = time.monotonic() - t0
        th.join(timeout=5.0)

        assert not exc_holder
        assert out_mix.exists()
        assert elapsed_read < 0.2
        assert blk.shape == (256, 2)
        assert mixer.position_frame == pos_before
        assert mixer.is_playing is True
    finally:
        mixer.clear()

    # Empty WAV must fail BEFORE clearing existing ring buffer frames
    empty_wav = tmp_path / "empty.wav"
    with wave.open(str(empty_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(b"")

    rb = FixedRingBuffer(AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10))
    rb.write(np.ones((48000, 2), dtype=np.float32) * 0.2)
    avail_before = rb.available_frames
    with pytest.raises(Exception):
        rb.import_audio_file_streaming(empty_wav)
    assert rb.available_frames == avail_before


def test_bug8_midi_fallback_splits_notes_across_unpitched_noise_gap(tmp_path: Path) -> None:
    sr = 48000
    t_tone = np.arange(int(0.5 * sr), dtype=np.float32) / float(sr)
    note_a2 = (0.35 * np.sin(2.0 * np.pi * 110.0 * t_tone) + 0.12 * np.sin(2.0 * np.pi * 220.0 * t_tone)).astype(np.float32)
    rng = np.random.default_rng(7)
    noise_gap = (0.28 * rng.normal(0.0, 1.0, int(0.45 * sr))).astype(np.float32)
    combined = np.concatenate([note_a2, noise_gap, note_a2])
    wav_path = _write_stereo_wav(tmp_path / "two_notes_noise_gap.wav", combined, sr=sr)

    notes = _fallback_monophonic_stem_to_notes(wav_path)
    a2_notes = [n for n in notes if abs(n.pitch_midi - 45) <= 1]
    assert len(a2_notes) >= 2
    assert a2_notes[-1].start_sec >= 0.85


def test_phase12_overview_ab_drag_wav_export_sevenths_and_table_seek(tmp_path: Path) -> None:
    # 1. FixedRingBuffer.snapshot_envelope chronological accuracy across wrap-around
    rb = FixedRingBuffer(AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=4))
    # Write 3s quiet + 3s loud (capacity=4s -> retains 1s quiet followed by 3s loud)
    rb.write(np.full((48000 * 3, 2), 0.1, dtype=np.float32))
    rb.write(np.full((48000 * 3, 2), 0.7, dtype=np.float32))
    mins, maxs, avail_sec = rb.snapshot_envelope(200)
    assert mins.shape == (200,) and maxs.shape == (200,)
    assert avail_sec == pytest.approx(4.0, abs=0.02)
    assert float(np.mean(maxs[:35])) < 0.2
    assert float(np.mean(maxs[65:])) > 0.6

    # 2. Extended 7th / sus4 chord detection (and default strict major/minor invariant)
    chroma_ext = ChromaExtractor(sample_rate=48000)
    det_triad = ChordDetector(ema_alpha=0.95, include_sevenths=False)
    det_7th = ChordDetector(ema_alpha=0.95, include_sevenths=True)

    sr = 48000
    t = np.arange(4096, dtype=np.float32) / float(sr)

    def _chord_vec(freqs: list[float]) -> np.ndarray:
        sig = np.zeros_like(t)
        for f in freqs:
            sig += (0.25 * np.sin(2.0 * np.pi * f * t)).astype(np.float32)
        mag = np.abs(np.fft.rfft(sig * np.hanning(4096).astype(np.float32))).astype(np.float32)
        return chroma_ext.extract_from_magnitude(mag, record_history=False, is_silent=False)

    cmaj7_c = _chord_vec([261.63, 329.63, 392.00, 493.88])
    g7_c = _chord_vec([196.00, 246.94, 293.66, 349.23])
    dm7_c = _chord_vec([293.66, 349.23, 440.00, 523.25])
    csus4_c = _chord_vec([261.63, 349.23, 392.00])

    # Default triad detector never outputs 7th/sus4 labels
    res_triad_only = det_triad.update(cmaj7_c, is_silent=False)
    assert res_triad_only.primary in ("C", "Em")
    assert det_7th.update(cmaj7_c, is_silent=False).primary == "Cmaj7"
    det_7th.reset()
    assert det_7th.update(g7_c, is_silent=False).primary == "G7"
    det_7th.reset()
    assert det_7th.update(dm7_c, is_silent=False).primary == "Dm7"
    det_7th.reset()
    assert det_7th.update(csus4_c, is_silent=False).primary == "Csus4"

    # End-to-end offline deep analysis with include_sevenths=True
    parts = []
    for freqs in ([261.63, 329.63, 392.00, 493.88], [196.00, 246.94, 293.66, 349.23]):
        t2 = np.arange(sr, dtype=np.float32) / float(sr)
        s = np.zeros_like(t2)
        for f in freqs:
            s += (0.22 * np.sin(2.0 * np.pi * f * t2)).astype(np.float32)
        parts.append(s)
    wav_7 = _write_stereo_wav(tmp_path / "other_7th.wav", np.concatenate(parts), sr=sr)
    rep_7 = analyze_stems_offline({"other": wav_7}, include_sevenths=True)
    chords_found = {c.chord for c in rep_7.chord_timeline}
    assert "Cmaj7" in chords_found
    assert "G7" in chords_found

    # 3. GUI timeline region drag/pick, A/B WAV export, and click-to-seek on Chord + MIDI tables
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws12")
    try:
        t3 = np.arange(sr * 3, dtype=np.float32) / float(sr)
        sig3 = (0.3 * np.sin(2.0 * np.pi * 330.0 * t3)).astype(np.float32)
        ctrl.ring_buffer.write(np.column_stack([sig3, sig3]))
        for _ in range(4):
            ctrl._on_ui_tick()

        # Overview curve populated
        x_d, y_d = ctrl.window._hist_max_curve.getData()
        assert x_d is not None and len(x_d) > 10

        # Drag ab_region -> updates spinboxes & triggers ab_player range update
        ctrl.window.ab_region.setRegion((-2.2, -0.4))
        ctrl.window._on_ab_region_finished()
        app.processEvents()
        assert ctrl.window.start_ago_spin.value() == pytest.approx(2.2, abs=0.05)
        assert ctrl.window.end_ago_spin.value() == pytest.approx(0.4, abs=0.05)
        a_f, b_f = ctrl.ab_player.loop_range
        assert (b_f - a_f) / float(sr) == pytest.approx(1.8, abs=0.05)

        # Export A/B excerpt WAV directly
        ab_out = tmp_path / "exports" / "ab_clip.wav"
        ctrl._on_export_ab_wav(str(ab_out))
        assert ab_out.exists()
        info = sf.info(str(ab_out))
        assert info.samplerate == 48000 and info.channels == 2
        assert info.duration == pytest.approx(1.8, abs=0.06)

        # Mixer click-to-seek on chord_timeline_table & midi_table + Piano Roll cursor update
        mw = ctrl.window.mixer_widget
        mw.sevenths_chk.setChecked(True)
        assert mw.include_sevenths is True
        stem_wav = _write_stereo_wav(tmp_path / "stem_seek.wav", sig3, sr=sr)
        mw.load_stem_paths({"other": str(stem_wav)})
        mw.display_deep_analysis(
            StemDeepAnalysisReport(
                duration_sec=3.0,
                harmonic_source_label="other",
                estimated_key=KeyEstimate(primary="C major", secondary="A minor", stability="High", correlation=0.8, margin=0.2, relation_note="", key_signature_note=""),
                estimated_bpm=TempoEstimate(bpm=120.0, stability="High", confidence_score=0.6),
                chord_timeline=[
                    ChordTimelineSegment(start_sec=0.0, end_sec=1.5, chord="Cmaj7", secondary="C", correlation=0.95, stability="High"),
                    ChordTimelineSegment(start_sec=1.5, end_sec=3.0, chord="G7", secondary="G", correlation=0.92, stability="High"),
                ],
            )
        )
        mw.display_midi_result(
            MidiTranscriptionResult(
                source_stem_name="other",
                output_midi_path=None,
                notes=[
                    MidiNoteCandidate(pitch_midi=60, note_name="C4", start_sec=0.25, end_sec=1.0, velocity=90, confidence=0.9),
                    MidiNoteCandidate(pitch_midi=67, note_name="G4", start_sec=2.10, end_sec=2.8, velocity=90, confidence=0.9),
                ],
                backend_used="cpu_monophonic_fallback_test",
            )
        )

        # Click row 1 of chord timeline (1.50s)
        mw.chord_timeline_table.cellClicked.emit(1, 2)
        app.processEvents()
        assert ctrl.mixer_engine.position_sec == pytest.approx(1.5, abs=0.02)
        assert float(mw._piano_roll_cursor.value()) == pytest.approx(1.5, abs=0.02)
        assert mw.seek_slider.value() == pytest.approx(500, abs=5)

        # Click row 1 of MIDI table (2.10s)
        mw.midi_table.cellClicked.emit(1, 0)
        app.processEvents()
        assert ctrl.mixer_engine.position_sec == pytest.approx(2.1, abs=0.02)
        assert float(mw._piano_roll_cursor.value()) == pytest.approx(2.1, abs=0.02)
        assert mw.seek_slider.value() == pytest.approx(700, abs=5)
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()
