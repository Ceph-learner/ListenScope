"""Phase 2A Engine verification tests (Issue #32, 13 engine items).

Every test is a minimal reproduction marked `@pytest.mark.xfail(strict=True, reason="<ID>")`.
Implementers remove the xfail marker as each item is fixed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import types
import wave
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_wav_pcm16(path: Path, data: np.ndarray, sr: int) -> None:
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    pcm16 = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(arr.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def test_e2_ai_subprocesses_use_popen_external_python_not_raw_popen() -> None:
    """NEEDS_TARGET contract test: core/paths.py must provide popen_external_python and AI launchers must use it."""
    from core import paths

    assert hasattr(paths, "popen_external_python"), "core/paths.py missing popen_external_python"
    for rel in ("ai/job_manager.py", "streaming/live_separator.py", "streaming/benchmark.py"):
        src = (REPO_ROOT / rel).read_text("utf-8")
        assert "subprocess.Popen(" not in src, f"{rel} still calls raw subprocess.Popen instead of popen_external_python"


@pytest.mark.xfail(strict=True, reason="E3")
def test_e3_streaming_resampler_matches_whole_signal_without_chunk_boundary_clicks() -> None:
    """Stateful scipy StreamingResampler must match whole-signal 44.1k->48k resample with SNR > 70 dB."""
    from audio import pcm_utils

    assert hasattr(pcm_utils, "StreamingResampler"), "audio/pcm_utils.py missing stateful StreamingResampler"

    sr_in, sr_out = 44100, 48000
    t = np.arange(sr_in, dtype=np.float32) / sr_in
    src = np.stack([0.5 * np.sin(2 * np.pi * 440.0 * t)] * 2, axis=1).astype(np.float32)

    ref = pcm_utils.normalize_to_canonical_pcm(src, src_rate=sr_in, src_channels=2, dst_rate=sr_out, dst_channels=2)
    rs = pcm_utils.StreamingResampler(src_rate=sr_in, dst_rate=sr_out, channels=2)
    outs = [rs.process(src[i : i + 882]) for i in range(0, src.shape[0], 882)]
    got = np.concatenate([o for o in outs if o.shape[0] > 0], axis=0)

    n = min(ref.shape[0], got.shape[0]) - 2000
    ref_mid = ref[1000 : 1000 + n, 0]
    got_mid = got[1000 : 1000 + n, 0]
    err = ref_mid - got_mid
    snr_db = 10.0 * np.log10(float(np.mean(ref_mid ** 2)) / max(float(np.mean(err ** 2)), 1e-12))
    assert snr_db > 70.0, f"Chunked resampling SNR too low: {snr_db:.1f} dB"


@pytest.mark.xfail(strict=True, reason="E4")
def test_e4_stem_mixer_44k_stem_playback_has_no_callback_boundary_clicks(tmp_path: Path) -> None:
    """Loading a 44.1kHz stem into StemMixerEngine must render cleanly without ~94Hz boundary clicks."""
    from audio.playback import StemMixerEngine

    sr_in = 44100
    t = np.arange(sr_in, dtype=np.float32) / sr_in
    sine = np.stack([0.5 * np.sin(2 * np.pi * 440.0 * t)] * 2, axis=1).astype(np.float32)
    wav_path = tmp_path / "other.wav"
    _write_wav_pcm16(wav_path, sine, sr_in)

    engine = StemMixerEngine(sample_rate=48000, channels=2)
    try:
        engine.load_stems({"other": wav_path})
        engine._is_playing = True
        blocks = [engine.render_block(512, advance=True) for _ in range(80)]
        y = np.concatenate(blocks, axis=0)[:, 0]
        # Steady region should be a clean 440Hz sine (THD/noise floor well below -50 dB)
        seg = y[4096 : 4096 + 16384]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        peak_idx = int(np.argmax(spec))
        sig_pow = float(np.sum(spec[max(0, peak_idx - 4) : peak_idx + 5] ** 2))
        tot_pow = float(np.sum(spec ** 2))
        noise_pow = max(tot_pow - sig_pow, 1e-12)
        snr_db = 10.0 * np.log10(sig_pow / noise_pow)
        assert snr_db > 55.0, f"44.1kHz mixer playback SNR only {snr_db:.1f} dB (boundary clicks)"
    finally:
        engine.close()


@pytest.mark.xfail(strict=True, reason="E6")
def test_e6_resource_manager_caches_nvidia_smi_outside_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """ResourceManager.sample() must cache nvidia-smi >= 2s and must not hold self._lock during subprocess."""
    from core import resource_manager as rm_mod
    from core.models import GPUInfo
    from core.resource_manager import ResourceManager

    rm = ResourceManager()
    rm._nvml_handle = None
    rm._nvml_mod = None
    calls = {"n": 0, "lock_held": False}

    def _fake_smi():
        calls["n"] += 1
        # If lock is held by caller thread, non-blocking acquire fails
        acquired = rm._lock.acquire(blocking=False)
        if not acquired:
            calls["lock_held"] = True
        else:
            rm._lock.release()
        return ([GPUInfo(0, "MockGPU", 8192.0, 1024.0, 7168.0, 10.0)], None, "nvidia-smi")

    monkeypatch.setattr(rm_mod, "_probe_gpus_nvidia_smi", _fake_smi)
    rm.sample()
    rm.sample()
    assert calls["lock_held"] is False, "nvidia-smi was invoked while holding ResourceManager._lock"
    assert calls["n"] == 1, f"nvidia-smi was called {calls['n']} times within <2s instead of cached"


@pytest.mark.xfail(strict=True, reason="E7")
def test_e7_heavy_export_and_import_handlers_dispatch_off_gui_thread() -> None:
    """_on_export_ab_wav / _on_export_mix / _on_import_audio_file must run heavy work on background thread."""
    src = (REPO_ROOT / "main.py").read_text("utf-8")
    # Extract _on_export_ab_wav body and check it spawns a background thread
    m = re.search(r"def _on_export_ab_wav\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "threading.Thread(" in m.group(0), "_on_export_ab_wav still blocks GUI thread synchronously"
    m2 = re.search(r"def _on_export_mix\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m2 is not None
    assert "threading.Thread(" in m2.group(0), "_on_export_mix still blocks GUI thread synchronously"


@pytest.mark.xfail(strict=True, reason="E8")
def test_e8_stem_work_dir_prunes_old_job_directories(tmp_path: Path) -> None:
    """Stems work directory must provide bounded cleanup keeping only recent jobs."""
    import main as main_mod

    assert hasattr(main_mod, "prune_old_stem_job_dirs") or hasattr(
        main_mod.ListenScopeController, "_prune_old_stem_dirs"
    ), "Missing stem job directory retention/pruning helper"


@pytest.mark.xfail(strict=True, reason="E11")
def test_e11_track_monitor_uses_per_thread_stop_event() -> None:
    """_start_track_monitor must create a fresh stop Event per thread instead of calling .clear() on a shared one."""
    src = (REPO_ROOT / "main.py").read_text("utf-8")
    m = re.search(r"def _start_track_monitor\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "_track_monitor_stop.clear()" not in m.group(0), (
        "_start_track_monitor reuses and clears shared _track_monitor_stop, allowing old thread to revive"
    )


def test_e12_worker_ipc_duplicates_fd1_to_isolate_native_stdout() -> None:
    """ai/worker.py and streaming/live_separator.py must redirect OS fd 1 (os.dup / os.dup2) for IPC safety."""
    for rel in ("ai/worker.py", "streaming/live_separator.py", "streaming/benchmark.py"):
        src = (REPO_ROOT / rel).read_text("utf-8")
        assert "os.dup(" in src and "os.dup2(" in src, f"{rel} only redirects sys.stdout, not OS fd 1"


@pytest.mark.xfail(strict=True, reason="E14")
def test_e14_corrupt_settings_backed_up_and_save_uses_unique_temp_with_fsync(tmp_path: Path) -> None:
    """load_settings must preserve corrupt JSON as .corrupt-*.json, and save_settings must fsync temp file."""
    from core.settings_store import load_settings

    bad = tmp_path / "settings.json"
    bad.write_text("{corrupt json!!!", encoding="utf-8")
    loaded = load_settings(bad)
    assert loaded.schema_version == 2
    backups = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(backups) == 1, "Corrupt settings.json was not backed up before returning defaults"
    src = (REPO_ROOT / "core" / "settings_store.py").read_text("utf-8")
    assert "os.fsync(" in src, "save_settings does not call os.fsync before replace"


@pytest.mark.xfail(strict=True, reason="E15")
def test_e15_live_separator_does_not_reuse_cleared_stop_event() -> None:
    """LiveTwoStemSeparator.start() must create a per-run stop Event instead of clearing a shared _stop_event."""
    src = (REPO_ROOT / "streaming" / "live_separator.py").read_text("utf-8")
    assert "self._stop_event.clear()" not in src, (
        "LiveTwoStemSeparator.start() clears shared _stop_event across runs"
    )


@pytest.mark.xfail(strict=True, reason="E16")
def test_e16_demucs_direct_path_standardizes_input_and_destandardizes_output() -> None:
    """_separate_with_demucs must standardize (x - mean)/std before apply_model and restore * std + mean."""
    src = (REPO_ROOT / "separation" / "demucs_backend.py").read_text("utf-8")
    m = re.search(r"def _separate_with_demucs\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    body = m.group(0)
    assert ".std(" in body and ".mean(" in body, "_separate_with_demucs missing reference mean/std normalization"


def test_e17_normalize_to_canonical_pcm_uint8_centering_and_channel_validation() -> None:
    """uint8 must center around 128 into [-1, 1], and 2D channel mismatch must raise ValueError."""
    from audio.pcm_utils import normalize_to_canonical_pcm

    u8 = np.array([[128, 128], [255, 0]], dtype=np.uint8)
    out = normalize_to_canonical_pcm(u8, src_rate=48000, src_channels=2, dst_rate=48000, dst_channels=2)
    assert abs(float(out[0, 0])) < 0.02, f"uint8 128 was not centered to ~0.0 (got {out[0, 0]})"
    assert float(out[1, 0]) <= 1.01 and float(out[1, 1]) >= -1.01

    wrong_shape = np.zeros((100, 1), dtype=np.float32)
    with pytest.raises(ValueError):
        normalize_to_canonical_pcm(wrong_shape, src_rate=48000, src_channels=2, dst_rate=48000, dst_channels=2)


@pytest.mark.xfail(strict=True, reason="E18")
def test_e18_mono_audio_config_does_not_crash_ring_buffer_snapshot() -> None:
    """If AudioConfig allows channels=1, FixedRingBuffer.snapshot_envelope must not raise IndexError."""
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AudioConfig

    try:
        cfg = AudioConfig(channels=1, ring_buffer_seconds=2)
    except ValueError:
        # Alternative valid fix per Issue: disallow channels=1 in AudioConfig
        return
    rb = FixedRingBuffer(cfg)
    rb.write(np.zeros((4800, 1), dtype=np.float32))
    mins, maxs, span = rb.snapshot_envelope(64)
    assert mins.shape == (64,) and maxs.shape == (64,) and span > 0
