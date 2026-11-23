"""Audit Pass 4 regression tests covering freeze-safe paths, NaN/Inf resilience, atomic IO, post-start WASAPI sync, and live/worker lifecycle safety."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtWidgets

from ai.job_manager import AIJobManager
from ai.models import MODEL_REGISTRY
from ai.resource_guard import inspect_wav_header, stream_chunked_separation
from ai.worker import spawn_worker_entry
from analysis.chords import ChordDetector
from analysis.chroma import ChromaExtractor
from analysis.key_detection import KeyDetector
from analysis.midi_transcription import _write_notes_to_midi
from analysis.pitch import PitchEstimator, freq_to_note_and_cents
from analysis.stem_analyzer import (
    analyze_bass_stem,
    analyze_drums_stem,
    analyze_harmony_and_chords,
    analyze_melody_stem,
    export_transcription_sheet,
)
from analysis.tempo import TempoEstimator
from audio.pcm_utils import compute_rms_and_peak, normalize_to_canonical_pcm
from audio.playback import StemMixerEngine
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig
from core.logging import PerformanceLogger
from core.models import (
    AIJobRequest,
    AIJobState,
    CaptureMode,
    ChordTimelineSegment,
    KeyEstimate,
    MidiNoteCandidate,
    StemDeepAnalysisReport,
    TempoEstimate,
)
from core.paths import default_export_dir, default_work_dir
from core.resource_manager import ResourceManager, SimulationOverrides
from main import ListenScopeController
from streaming.live_separator import ExperimentalLiveSeparator


def _write_pcm_wav(path: Path, samples_2ch: np.ndarray, *, sr: int = 48000) -> Path:
    arr = np.asarray(samples_2ch, dtype=np.float32)
    if arr.ndim == 1:
        arr = np.column_stack([arr, arr])
    i16 = (np.clip(np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0), -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(arr.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(i16.tobytes())
    return path


def _write_ieee_float_wav(path: Path, samples_2ch: np.ndarray, *, sr: int = 48000) -> Path:
    import soundfile as sf  # type: ignore[import-untyped]

    sf.write(str(path), samples_2ch.astype(np.float32), sr, subtype="FLOAT")
    return path


def test_default_work_and_export_dirs_fallback_when_frozen_or_readonly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "user_home"
    fake_docs = fake_home / "Documents"
    fake_docs.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Writable frozen installation folder prefers sibling directories (keeps files beside app, away from C:\)
    writable_app = tmp_path / "portable_app"
    writable_app.mkdir()
    monkeypatch.setattr(sys, "executable", str(writable_app / "ListenScope.exe"), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert default_work_dir() == writable_app.resolve() / "workspace_outputs"
    assert default_export_dir() == writable_app.resolve() / "exports"

    # Read-only frozen dir safely falls back to ~/.listenscope and Documents/ListenScope/exports
    readonly_app = tmp_path / "ro_program_files"
    readonly_app.mkdir()
    monkeypatch.setattr(sys, "executable", str(readonly_app / "ListenScope.exe"), raising=False)
    monkeypatch.setattr(
        "core.paths._is_writable_dir",
        lambda d: Path(d) in (fake_home, fake_docs),
    )
    assert default_work_dir() == fake_home / ".listenscope" / "workspace_outputs"
    assert default_export_dir() == fake_docs / "ListenScope" / "exports"

    # Non-frozen with read-only CWD also falls back safely
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        "core.paths._is_writable_dir",
        lambda d: Path(d) == fake_home,
    )
    assert default_work_dir() == fake_home / ".listenscope" / "workspace_outputs"
    assert default_export_dir() == fake_home / ".listenscope" / "exports"


def test_ring_buffer_odd_1d_write_nan_safety_and_atomic_exports(tmp_path: Path) -> None:
    cfg = AudioConfig(ring_buffer_seconds=4)
    rb = FixedRingBuffer(audio_config=cfg)

    # Odd 1D array + NaN/Inf values
    odd = np.array([0.2, -0.2, float("nan"), float("inf"), 0.5], dtype=np.float32)
    written = rb.write(odd)
    assert written == 2
    pcm, s, e = rb.read_recent(1.0)
    assert e - s == 2
    assert pcm.shape == (2, 2)
    assert np.all(np.isfinite(pcm))

    # Truncated byte buffer fast-path & compute_rms_and_peak NaN protection
    norm_chunk = normalize_to_canonical_pcm(b"\x01\x02\x03", src_rate=48000, src_channels=2, src_dtype="float32")
    assert norm_chunk.shape == (0, 2)
    rms, rms_db, pk, pk_db = compute_rms_and_peak(np.array([[float("nan"), 0.2]], dtype=np.float32))
    assert np.isfinite(rms) and np.isfinite(rms_db) and np.isfinite(pk) and np.isfinite(pk_db)

    # Write 0.5s clean audio and verify atomic WAV export leaves no .tmp behind
    t = np.arange(24000, dtype=np.float32) / 48000.0
    sig = 0.25 * np.sin(2.0 * np.pi * 440.0 * t)
    rb.write(np.column_stack([sig, sig]))
    out_wav = tmp_path / "ab_atomic.wav"
    saved, dur = rb.export_wav_streaming(out_wav, rb.oldest_abs_frame, rb.total_written_frames)
    assert saved == out_wav and out_wav.exists() and dur >= 0.49
    assert not out_wav.with_name(out_wav.name + ".tmp").exists()

    # Mixer atomic WAV export + transcription sheet + MIDI write leave no stale .tmp
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    try:
        mixer.load_stems({"vocals": out_wav})
        mix_wav = tmp_path / "mix_atomic.wav"
        mixer.export_mix_streaming(mix_wav)
        assert mix_wav.exists() and not mix_wav.with_name(mix_wav.name + ".tmp").exists()
    finally:
        mixer.clear()

    rep = StemDeepAnalysisReport(
        duration_sec=0.5,
        harmonic_source_label="vocals",
        estimated_key=KeyEstimate(
            primary="C Major", secondary="A Minor", stability="High", correlation=0.8, margin=0.2
        ),
        estimated_bpm=TempoEstimate(bpm=120.0, stability="High", confidence_score=0.5),
        chord_timeline=[ChordTimelineSegment(0.0, 0.5, "C", "Am", 0.85, "High")],
    )
    for ext in (".md", ".csv"):
        p = tmp_path / f"sheet{ext}"
        export_transcription_sheet(rep, p)
        assert p.exists() and not p.with_name(p.name + ".tmp").exists()

    mid_out = tmp_path / "atomic.mid"
    _write_notes_to_midi([MidiNoteCandidate(60, "C4", 0.0, 0.3, 90, 0.9)], mid_out)
    assert mid_out.exists() and not mid_out.with_name(mid_out.name + ".tmp").exists()


def test_ring_buffer_wave_fallback_short_read_counts_actual_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wav_path = tmp_path / "short.wav"
    data = np.zeros((48000, 2), dtype=np.float32)
    _write_pcm_wav(wav_path, data, sr=48000)

    # Force soundfile failure so stdlib wave fallback path executes
    import builtins

    real_import = builtins.__import__

    def _no_sf(name: str, *args: Any, **kwargs: Any):
        if name == "soundfile":
            raise ImportError("forced wave fallback")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_sf)

    # Mock wave header claiming more frames than bytes returned in each readframes call
    real_wave_open = wave.open

    class _ShortWaveProxy:
        def __init__(self, inner: wave.Wave_read) -> None:
            self._inner = inner
            self._calls = 0

        def __enter__(self) -> "_ShortWaveProxy":
            return self

        def __exit__(self, *a: Any) -> None:
            self._inner.close()

        def getframerate(self) -> int:
            return 48000

        def getnchannels(self) -> int:
            return 2

        def getsampwidth(self) -> int:
            return 2

        def getnframes(self) -> int:
            return 48000

        def readframes(self, n: int) -> bytes:
            self._calls += 1
            if self._calls > 4:
                return b""
            # Always return half the requested frames to test actual_src_frames accounting
            return self._inner.readframes(max(1, n // 2))

    monkeypatch.setattr("audio.ring_buffer.wave.open", lambda p, m="rb": _ShortWaveProxy(real_wave_open(p, m)))

    rb = FixedRingBuffer(audio_config=AudioConfig(ring_buffer_seconds=4))
    imported_sec, truncated = rb.import_audio_file_streaming(wav_path, max_seconds=1.0, chunk_seconds=0.25)
    # 4 calls * (12000 // 2) = 24000 frames = 0.5s
    assert 0.45 <= imported_sec <= 0.55
    assert truncated is False


def test_dsp_and_stem_analyzers_handle_nan_inf_and_extreme_values(tmp_path: Path) -> None:
    # Chroma, Chord, Tempo, Key, Pitch safety
    chroma_ext = ChromaExtractor(sample_rate=48000)
    nan_mag = np.full(chroma_ext._chroma_fb.shape[1], float("nan"), dtype=np.float32)
    c12 = chroma_ext.extract_from_magnitude(nan_mag, record_history=True, is_silent=False)
    assert c12.shape == (12,) and np.all(np.isfinite(c12))

    # Mismatched bin shape must safely return zero chroma instead of crashing dot product
    bad_shape_mag = np.ones(16, dtype=np.float32)
    c_bad = chroma_ext.extract_from_magnitude(bad_shape_mag, record_history=False, is_silent=False)
    assert np.allclose(c_bad, 0.0)

    chord_det = ChordDetector()
    ce = chord_det.update(np.full(12, float("nan"), dtype=np.float32), is_silent=False)
    assert ce.is_silent is True and ce.primary == "N (静音)"

    tempo = TempoEstimator()
    te_nan = tempo.update(np.array([float("nan"), 1000.0], dtype=np.float32), is_silent=False)
    assert te_nan.bpm is None
    # Extreme dB values clipped safely without float32 overflow warnings/NaNs
    te_extreme = tempo.update(np.full(48, 500.0, dtype=np.float32), is_silent=False)
    assert np.isfinite(te_extreme.confidence_score)

    kd = KeyDetector()
    ke = kd.estimate(np.full((40, 12), float("nan"), dtype=np.float32))
    assert ke.primary == "Unknown"

    note, cents = freq_to_note_and_cents(float("nan"))
    assert note == "-" and cents == 0.0
    note2, _ = freq_to_note_and_cents(500000.0)
    assert note2 != "-"

    pitch_est = PitchEstimator(sample_rate=48000, fft_size=4096)
    pe = pitch_est.estimate_from_magnitude(np.array([float("inf"), 1.0], dtype=np.float32), is_silent=False)
    assert pe.frequency_hz is None and pe.note_name == "-"

    # Float32 IEEE WAV containing NaN / Inf frames analyzed cleanly across all stem analyzers
    n = 48000
    arr = np.zeros((n, 2), dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / 48000.0
    arr[:, 0] = 0.2 * np.sin(2.0 * np.pi * 110.0 * t)
    arr[:, 1] = arr[:, 0]
    arr[1000:1200, :] = float("nan")
    arr[3000:3050, :] = float("inf")
    nan_wav = _write_ieee_float_wav(tmp_path / "nan_stem.wav", arr, sr=48000)

    bass = analyze_bass_stem(nan_wav)
    drums = analyze_drums_stem(nan_wav)
    mel = analyze_melody_stem(nan_wav)
    _, dur, k_out, t_out, segs = analyze_harmony_and_chords([(nan_wav, 1.0)], source_label="vocals")
    assert bass.duration_sec > 0.5
    assert drums.duration_sec > 0.5
    assert mel.duration_sec > 0.5
    assert dur > 0.5 and k_out is not None and t_out is not None and isinstance(segs, list)


def test_process_loopback_refreshes_format_and_fallback_after_start() -> None:
    class _PostNative:
        def __init__(self) -> None:
            self.started = False

        def is_process_specific(self) -> bool:
            # Simulates WASAPI reporting True before start(), then falling back to system loopback on start()
            return not self.started

    class _PostTap:
        def __init__(self, on_data: Any) -> None:
            self._on_data = on_data
            self.is_running = True
            self._native = _PostNative()
            self._backend = type("_B", (), {"_native": self._native})()

        def get_format(self) -> dict[str, Any]:
            # Before start: 44100 Hz; after start: finalized at 48000 Hz stereo float32
            sr = 48000 if self._native.started else 44100
            return {"sample_rate": sr, "channels": 2, "sample_format": "float32"}

        def start(self) -> None:
            self._native.started = True

        def close(self) -> None:
            self.is_running = False

    holder: dict[str, Any] = {}

    def _factory(**kw: Any) -> _PostTap:
        holder["tap"] = _PostTap(kw["on_data"])
        return holder["tap"]

    backend = WasapiProcessLoopbackBackend(
        pid=9999,
        process_name="QQMusic.exe",
        tap_factory=_factory,
        pid_exists_fn=lambda _pid: True,
        allow_non_windows=True,
    )
    try:
        backend.start()
        st = backend.get_stats()
        assert backend._cached_fmt["sample_rate"] == 48000
        assert st.mode == CaptureMode.SYSTEM_LOOPBACK
        assert st.warning_message is not None and "混入" in st.warning_message

        # Truncated 3-byte packet must be dropped harmlessly without raising
        backend._on_proctap_data(b"\x01\x02\x03", 1)
    finally:
        backend.stop()


def test_ai_job_manager_and_worker_resilience(tmp_path: Path) -> None:
    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    perf = PerformanceLogger(log_dir=tmp_path / "perf")
    mgr = AIJobManager(rm, performance_logger=perf)
    try:
        # Unreadable/corrupt WAV must fail cleanly with (False, msg) rather than raising
        bad_wav = tmp_path / "corrupt.wav"
        bad_wav.write_bytes(b"NOT_A_RIFF_WAV")
        ok, msg = mgr.submit_job(
            AIJobRequest(
                task_id="bad_hdr",
                input_wav_path=str(bad_wav),
                output_dir=str(tmp_path / "bad_out"),
                stem_mode="2stem",
                model_id="mdx_low_vram_2stem",
                use_gpu=False,
                use_mock_backend=True,
            )
        )
        assert not ok and "无效" in msg

        # Zero-frame WAV must fail cleanly in stream_chunked_separation
        empty_wav = tmp_path / "zero_frames.wav"
        with wave.open(str(empty_wav), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(b"")
        meta = inspect_wav_header(empty_wav)
        assert meta.total_frames == 0
        with pytest.raises(ValueError):
            stream_chunked_separation(
                empty_wav,
                tmp_path / "z_out",
                ["vocals", "instrumental"],
                lambda c, _sr: {"vocals": c, "instrumental": c},
            )

        # Bounded full queue in spawn_worker_entry must still deliver terminal result via stale eviction
        valid_wav = _write_pcm_wav(tmp_path / "ok.wav", np.zeros((24000, 2), dtype=np.float32))
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2)
        q.put({"type": "stale", "payload": 1})
        q.put({"type": "stale", "payload": 2})
        ev = threading.Event()
        req = AIJobRequest(
            task_id="full_q",
            input_wav_path=str(valid_wav),
            output_dir=str(tmp_path / "full_q_out"),
            stem_mode="2stem",
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
        )
        spawn_worker_entry(
            {
                "task_id": req.task_id,
                "input_wav_path": req.input_wav_path,
                "output_dir": req.output_dir,
                "stem_mode": req.stem_mode,
                "model_id": req.model_id,
                "use_gpu": req.use_gpu,
                "use_mock_backend": req.use_mock_backend,
            },
            AIConfig().__dict__,
            q,
            ev,
        )
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert any(it.get("type") == "result" for it in items)

        # cancel_job timeout path must join monitor thread BEFORE tearing down IPC handles
        order: list[str] = []
        slow_mon = threading.Thread(target=lambda: (time.sleep(0.08), order.append("mon_done")))
        mgr._active_request = req
        mgr._done_event.clear()
        mgr._stop_monitor.clear()
        mgr._monitor_thread = slow_mon
        slow_mon.start()
        orig_cleanup = mgr._cleanup_ipc_handles
        mgr._cleanup_ipc_handles = lambda: (order.append("ipc_clean"), orig_cleanup())[1]  # type: ignore[method-assign]
        res = mgr.cancel_job(timeout=0.01)
        assert res is not None and res.state == AIJobState.CANCELLED
        assert order == ["mon_done", "ipc_clean"]
    finally:
        mgr.shutdown()
        rm.close()


def test_live_separator_survives_ring_clear_and_controller_stops_on_reset(tmp_path: Path) -> None:
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        ai_python_executable=sys.executable,
        work_dir=tmp_path / "ws",
        settings_path=tmp_path / "settings.json",
    )
    try:
        # 1. Verify 2-stem models pass their registry default segment (not 4-stem spin=10)
        emitted: list[tuple[str, str, int, bool]] = []
        ctrl.window.ai_separate_requested.connect(lambda m, mid, seg, gpu: emitted.append((m, mid, seg, gpu)))
        ctrl.window._on_sep_2stem()
        assert emitted and emitted[-1][1] == "mdx_low_vram_2stem"
        assert emitted[-1][2] == MODEL_REGISTRY["mdx_low_vram_2stem"].default_segment_sec

        from dataclasses import replace

        ctrl.window._ai_config = replace(ctrl.window._ai_config, allow_experimental_roformer=True)
        ctrl.window._refresh_model_combos()
        idx = ctrl.window.ai_2stem_combo.findData("bs_roformer_experimental")
        assert idx >= 0
        ctrl.window.ai_2stem_combo.setCurrentIndex(idx)
        ctrl.window._on_sep_2stem()
        assert emitted[-1][1] == "bs_roformer_experimental"
        assert emitted[-1][2] == MODEL_REGISTRY["bs_roformer_experimental"].default_segment_sec

        ctrl.resource_manager.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
        # 2. Direct ExperimentalLiveSeparator unit resiliency across ring_buffer.clear()
        rb = FixedRingBuffer(audio_config=AudioConfig(ring_buffer_seconds=10))
        t = np.arange(48000 * 3, dtype=np.float32) / 48000.0
        rb.write(np.column_stack([0.2 * np.sin(2.0 * np.pi * 440.0 * t)] * 2))
        sep = ExperimentalLiveSeparator(rb, ctrl.resource_manager, ai_config=AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.25))
        ok, _ = sep.start(model_id="mdx_low_vram_2stem", use_gpu=False, use_mock_backend=True, open_audio_device=False)
        assert ok
        try:
            time.sleep(0.15)
            assert sep._last_read_abs_frame > 0
            rb.clear()
            rb.write(np.column_stack([0.2 * np.sin(2.0 * np.pi * 220.0 * t)] * 2))
            deadline = time.monotonic() + 2.0
            while sep.is_active and sep._last_read_abs_frame > 48000 * 3 and time.monotonic() < deadline:
                time.sleep(0.05)
            # Coordinator must remain alive and have resynced cursor inside new [0, 144000] bounds
            assert sep.is_active is True
            assert sep._last_read_abs_frame <= rb.total_written_frames
        finally:
            sep.stop()

        # 3. Missing stem path sent to analysis must preserve existing ring buffer
        ctrl.ring_buffer.write(np.ones((24000, 2), dtype=np.float32) * 0.1)
        prev_frames = ctrl.ring_buffer.total_written_frames
        ctrl._on_send_stem_to_analysis("vocals", str(tmp_path / "does_not_exist.wav"))
        assert ctrl.ring_buffer.total_written_frames == prev_frames

        # 4. Importing audio must cleanly stop active live separator
        ok_live, _ = ctrl.live_separator.start(
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
            open_audio_device=False,
        )
        assert ok_live and ctrl.live_separator.is_active
        wav_imp = _write_pcm_wav(tmp_path / "imp.wav", np.ones((48000, 2), dtype=np.float32) * 0.2)
        ctrl._on_import_audio_file(str(wav_imp))
        ctrl.wait_pending_io()
        assert ctrl.live_separator.is_active is False
        assert ctrl.ring_buffer.available_seconds >= 0.9
    finally:
        ctrl.shutdown()
        _app.processEvents()
