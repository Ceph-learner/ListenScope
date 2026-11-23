"""Phase 2B Algorithm verification tests (Issue #32, 19 items: A-BENCH + 18 algorithm fixes).

`A-BENCH` is an executable baseline smoke test (passes now).
The 18 algorithm defect reproductions are marked `@pytest.mark.xfail(strict=True, reason="<ID>")`.
Implementers remove each xfail marker as the item is fixed.
"""

from __future__ import annotations

import inspect
import wave
from pathlib import Path

import mido
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SR = 48000


def _write_wav_pcm16(path: Path, mono_or_stereo: np.ndarray, sr: int = SR) -> None:
    arr = np.asarray(mono_or_stereo, dtype=np.float32)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    pcm16 = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(arr.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def _midi_to_hz(midi: float) -> float:
    return float(440.0 * (2.0 ** ((midi - 69.0) / 12.0)))


def test_abench_benchmark_suite_runs_and_returns_all_metrics() -> None:
    """A-BENCH prerequisite: frozen benchmark module runs deterministically and returns expected metric groups."""
    from tests.bench.algo_benchmark import run_chord_benchmark, run_pitch_benchmark

    chord_res = run_chord_benchmark()
    pitch_res = run_pitch_benchmark()
    assert "rt_progression_acc" in chord_res and "rt_inversion_acc" in chord_res
    assert "pure_sine_acc" in pitch_res and "harmonic_acc" in pitch_res and "weak_f0_acc" in pitch_res


@pytest.mark.xfail(strict=True, reason="A-H1")
def test_ah1_realtime_bpm_decoupled_from_scheduler_rate() -> None:
    """NEEDS_TARGET contract: TempoEstimator & AnalysisWorker must advance onset envelope on sample clock, not 15Hz timer."""
    from analysis.tempo import TempoEstimator

    te = TempoEstimator()
    # Sample-clock driven onset rate should be >= 60 Hz (e.g. 48000 / 512 = 93.75 Hz) and expose push_frame or sample-clock API
    assert te._rate_hz >= 60.0 or hasattr(te, "push_frame"), (
        f"TempoEstimator still tied to 15 Hz scheduler clock (_rate_hz={te._rate_hz})"
    )


@pytest.mark.xfail(strict=True, reason="A-H2")
def test_ah2_realtime_bpm_140_bpm_rock_within_1_percent() -> None:
    """Real-time TempoEstimator must measure 140 BPM rock groove within 1% (not half-time ~70.7 BPM)."""
    from analysis.fft import SpectrumAnalyzer
    from analysis.tempo import TempoEstimator
    from core.config import AnalysisConfig
    from tests.bench.algo_benchmark import _synth_click_track

    cfg = AnalysisConfig()
    pcm = _synth_click_track(140.0, dur_sec=10.0, style="rock")
    spec_an = SpectrumAnalyzer(sample_rate=SR, config=cfg)
    te = TempoEstimator(config=cfg)
    hop = 512 if te._rate_hz >= 60.0 else int(round(SR / cfg.analysis_rate_hz))
    est = None
    for pos in range(0, pcm.shape[0] - cfg.fft_size + 1, hop):
        _, _, log_db = spec_an.analyze_frame(pcm[pos : pos + cfg.fft_size])
        est = te.update(log_db, is_silent=False)
    assert est is not None and est.bpm is not None
    assert abs(est.bpm - 140.0) / 140.0 < 0.01, f"140 BPM rock measured as {est.bpm}"


@pytest.mark.xfail(strict=True, reason="A-M6")
def test_am6_high_tempo_174_bpm_not_locked_to_half_time() -> None:
    """Offline and real-time BPM estimators must not lock 174 BPM click to 87 BPM."""
    from analysis.stem_analyzer import _estimate_offline_bpm_from_flux
    from tests.bench.algo_benchmark import _synth_click_track

    pcm = _synth_click_track(174.0, dur_sec=10.0, style="click")
    hop = 512
    win = np.hanning(2048).astype(np.float32)
    prev_lm = None
    flux = []
    for pos in range(0, pcm.shape[0] - 2048 + 1, hop):
        lm = np.log1p(np.abs(np.fft.rfft(pcm[pos : pos + 2048] * win)).astype(np.float32))
        flux.append(0.0 if prev_lm is None else float(np.mean(np.maximum(0.0, lm - prev_lm))))
        prev_lm = lm
    est = _estimate_offline_bpm_from_flux(np.asarray(flux, dtype=np.float32), rate_hz=SR / float(hop))
    assert est.bpm is not None and abs(est.bpm - 174.0) / 174.0 < 0.03, f"174 BPM click measured as {est.bpm}"


@pytest.mark.xfail(strict=True, reason="A-H3")
def test_ah3_realtime_pitch_weak_fundamental_e1_to_e3_accuracy() -> None:
    """PitchEstimator must handle weak fundamental (f0 amp=0.15) across E1..E3 with >=95% note accuracy via YIN."""
    from analysis.pitch import PitchEstimator, freq_to_note_and_cents

    pe = PitchEstimator(sample_rate=SR, fft_size=4096)
    assert hasattr(pe, "estimate_from_pcm"), "PitchEstimator missing YIN-based estimate_from_pcm()"
    hits = 0
    midis = list(range(28, 53))
    t = np.arange(7200, dtype=np.float32) / float(SR)
    for m in midis:
        f0 = _midi_to_hz(m)
        sig = (
            0.15 * np.sin(2.0 * np.pi * f0 * t)
            + 1.00 * np.sin(2.0 * np.pi * 2.0 * f0 * t)
            + 0.70 * np.sin(2.0 * np.pi * 3.0 * f0 * t)
            + 0.40 * np.sin(2.0 * np.pi * 4.0 * f0 * t)
        ).astype(np.float32)
        est = pe.estimate_from_pcm(sig, is_silent=False)
        true_name, _ = freq_to_note_and_cents(f0)
        if est.note_name == true_name:
            hits += 1
    assert hits / len(midis) >= 0.95, f"Weak-f0 accuracy only {hits}/{len(midis)}"


@pytest.mark.xfail(strict=True, reason="A-M2")
def test_am2_red_noise_returns_unknown_not_fake_e1_with_saturated_confidence() -> None:
    """Red/pink noise must be rejected as Unknown (tonality gate), not reported as E1 with confidence ~1.0."""
    from analysis.pitch import PitchEstimator

    rng = np.random.default_rng(123)
    white = rng.standard_normal(7200).astype(np.float32)
    red = np.cumsum(white).astype(np.float32)
    red -= float(np.mean(red))
    red /= float(np.max(np.abs(red)) + 1e-9)
    red *= 0.3

    pe = PitchEstimator(sample_rate=SR, fft_size=4096)
    if hasattr(pe, "estimate_from_pcm"):
        est = pe.estimate_from_pcm(red, is_silent=False)
    else:
        mag = np.abs(np.fft.rfft(red[:4096] * np.hanning(4096))).astype(np.float32)
        est = pe.estimate_from_magnitude(mag, is_silent=False)
    assert est.frequency_hz is None and est.note_name in ("Unknown", "-"), (
        f"Red noise misclassified as {est.note_name} ({est.frequency_hz} Hz, conf={est.confidence})"
    )


@pytest.mark.xfail(strict=True, reason="A-L9")
def test_al9_short_256_sample_buffer_returns_unknown_not_bogus_pitch() -> None:
    """Short 256-sample buffer must return Unknown instead of zero-padded bogus pitch."""
    from analysis.pitch import PitchEstimator

    t = np.arange(256, dtype=np.float32) / float(SR)
    short_a4 = (0.4 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    pe = PitchEstimator(sample_rate=SR, fft_size=4096)
    if hasattr(pe, "estimate_from_pcm"):
        est = pe.estimate_from_pcm(short_a4, is_silent=False)
    else:
        padded = np.zeros(4096, dtype=np.float32)
        padded[-256:] = short_a4
        mag = np.abs(np.fft.rfft(padded * np.hanning(4096))).astype(np.float32)
        est = pe.estimate_from_magnitude(mag, is_silent=False, valid_len=256)
    assert est.frequency_hz is None and est.note_name in ("Unknown", "-"), (
        f"256-sample short buffer returned bogus pitch {est.note_name} ({est.frequency_hz} Hz)"
    )


@pytest.mark.xfail(strict=True, reason="A-H4")
def test_ah4_repeated_same_pitch_bass_notes_not_merged(tmp_path: Path) -> None:
    """Four consecutive re-articulated A1 bass notes (20ms decay/re-attack) must yield 4 events, not 1."""
    from analysis.stem_analyzer import analyze_bass_stem

    f0 = _midi_to_hz(33)  # A1 = 55 Hz
    note_n = int(0.45 * SR)
    t = np.arange(note_n, dtype=np.float32) / float(SR)
    parts = []
    for _ in range(4):
        env = np.exp(-t * 6.5).astype(np.float32)
        env[:200] *= np.linspace(0.0, 1.0, 200, dtype=np.float32)
        note = (0.65 * np.sin(2.0 * np.pi * f0 * t) + 0.25 * np.sin(2.0 * np.pi * 2.0 * f0 * t)) * env
        parts.append(note.astype(np.float32))
    wav_path = tmp_path / "repeated_a1.wav"
    _write_wav_pcm16(wav_path, np.concatenate(parts, axis=0))

    res = analyze_bass_stem(wav_path)
    assert len(res.notes) == 4, f"Expected 4 repeated A1 notes, got {len(res.notes)}: {res.notes}"


@pytest.mark.xfail(strict=True, reason="A-L6")
def test_al6_bass_note_onset_timestamp_not_systematically_late(tmp_path: Path) -> None:
    """Bass note starting at 0.510s must have detected start_sec within +/- 15 ms (currently +23 ms)."""
    from analysis.stem_analyzer import analyze_bass_stem

    f0 = _midi_to_hz(40)  # E2 = 82.41 Hz
    sig = np.zeros(int(2.0 * SR), dtype=np.float32)
    t = np.arange(int(0.8 * SR), dtype=np.float32) / float(SR)
    tone = (0.6 * np.sin(2.0 * np.pi * f0 * t) + 0.2 * np.sin(2.0 * np.pi * 2.0 * f0 * t)).astype(np.float32)
    t0 = 0.510
    start_idx = int(round(t0 * SR))
    sig[start_idx : start_idx + tone.shape[0]] = tone
    wav_path = tmp_path / "onset_0510s.wav"
    _write_wav_pcm16(wav_path, sig)

    res = analyze_bass_stem(wav_path)
    assert len(res.notes) >= 1
    err_ms = abs(res.notes[0].start_sec - t0) * 1000.0
    assert err_ms <= 15.0, f"Bass onset timestamp off by {err_ms:.1f} ms (got {res.notes[0].start_sec}s)"


@pytest.mark.xfail(strict=True, reason="A-H5")
def test_ah5_minor_cadence_with_c2_bass_not_misclassified_as_parallel_major() -> None:
    """24-key minor i-iv-V-i cadences with C2 bass must achieve >=90% accuracy (currently 0%)."""
    from tests.bench.algo_benchmark import run_key_benchmark

    res = run_key_benchmark()
    assert res["minor_i_iv_V_i_acc"] >= 90.0, f"Minor i-iv-V-i accuracy only {res['minor_i_iv_V_i_acc']}%"
    assert res["major_I_IV_V_I_acc"] >= 90.0, f"Major I-IV-V-I accuracy dropped to {res['major_I_IV_V_I_acc']}%"


@pytest.mark.xfail(strict=True, reason="A-L7")
def test_al7_key_modulation_returns_second_half_key_not_third_key() -> None:
    """When C major modulates to Eb major mid-window, primary key must be Eb major (second half), not C minor."""
    from analysis.chroma import ChromaExtractor
    from analysis.key_detection import KeyDetector
    from tests.bench.algo_benchmark import _synth_progression

    c_maj = _synth_progression([(36, [60, 64, 67]), (41, [65, 69, 72]), (43, [67, 71, 74]), (36, [60, 64, 67])], 0.8)
    eb_maj = _synth_progression([(39, [63, 67, 70]), (44, [68, 72, 75]), (46, [70, 74, 77]), (39, [63, 67, 70])], 0.8)
    pcm = np.concatenate([c_maj, eb_maj], axis=0)

    ce = ChromaExtractor(sample_rate=SR)
    for s in range(0, pcm.shape[0] - 16384 + 1, 2048):
        ce.extract_from_pcm(pcm[s : s + 16384], record_history=True)
    mat, w, bass = ce.recent_chroma_bundle(seconds=30.0)
    est = KeyDetector().estimate(mat, frame_weights=w, bass_window=bass)
    assert est.primary == "D# major", f"C->Eb modulation returned {est.primary} ({est.relation_note})"


@pytest.mark.xfail(strict=True, reason="A-L3")
def test_al3_bass_modulation_does_not_false_positive_on_diatonic_verse_chorus() -> None:
    """A diatonic C major verse (A-F) -> chorus (C-G) bass line must not false-positive as modulation."""
    from analysis.stem_analyzer import _detect_bass_modulation
    from core.models import StemNoteEvent

    # First half: Am -> F (A1, F1); Second half: C -> G (C2, G1) — all strictly C major
    events = [
        StemNoteEvent(0.0, 1.0, 33, "A1", 55.0, 0.9),
        StemNoteEvent(1.0, 2.0, 29, "F1", 43.65, 0.9),
        StemNoteEvent(2.0, 3.0, 33, "A1", 55.0, 0.9),
        StemNoteEvent(3.0, 4.0, 29, "F1", 43.65, 0.9),
        StemNoteEvent(4.0, 5.0, 36, "C2", 65.41, 0.9),
        StemNoteEvent(5.0, 6.0, 31, "G1", 49.0, 0.9),
        StemNoteEvent(6.0, 7.0, 36, "C2", 65.41, 0.9),
        StemNoteEvent(7.0, 8.0, 31, "G1", 49.0, 0.9),
    ]
    mod, note = _detect_bass_modulation(events)
    assert mod is False, f"Diatonic C major vi-IV -> I-V falsely flagged as modulation: {note}"


@pytest.mark.xfail(strict=True, reason="A-M4")
def test_am4_first_inversion_chords_not_misclassified_as_relative_minor() -> None:
    """C/E and F/A with prominent bass must not be misclassified as Em or Am."""
    from analysis.chords import ChordDetector
    from analysis.chroma import ChromaExtractor
    from tests.bench.algo_benchmark import _synth_chord_segment

    ce = ChromaExtractor(sample_rate=SR)
    # C/E: bass=E2 (40), upper=C4,E4,G4 (60,64,67)
    pcm_ce = _synth_chord_segment(40, [60, 64, 67], 0.8, bass_gain=0.60)
    c_ce = ce.extract_from_pcm(pcm_ce[-16384:], record_history=False)
    est_ce = ChordDetector().update(c_ce, is_silent=False)
    assert est_ce.primary in ("C", "C/E"), f"C/E misclassified as {est_ce.primary}"

    # F/A: bass=A2 (45), upper=F4,A4,C5 (65,69,72)
    pcm_fa = _synth_chord_segment(45, [65, 69, 72], 0.8, bass_gain=0.60)
    c_fa = ce.extract_from_pcm(pcm_fa[-16384:], record_history=False)
    est_fa = ChordDetector().update(c_fa, is_silent=False)
    assert est_fa.primary in ("F", "F/A"), f"F/A misclassified as {est_fa.primary}"


@pytest.mark.xfail(strict=True, reason="A-L10")
def test_al10_sevenths_enabled_preserves_triad_accuracy_and_supports_dim() -> None:
    """Enabling include_sevenths must keep triad accuracy >= 95% and recognize Bdim."""
    from analysis.chords import ChordDetector
    from analysis.chroma import ChromaExtractor
    from tests.bench.algo_benchmark import _synth_chord_segment, run_chord_benchmark

    res = run_chord_benchmark()
    assert res["triad_with_sevenths_on_acc"] >= 95.0, (
        f"Triad accuracy dropped to {res['triad_with_sevenths_on_acc']}% with sevenths enabled"
    )
    ce = ChromaExtractor(sample_rate=SR)
    pcm_bdim = _synth_chord_segment(47, [59, 62, 65], 0.8)  # B-D-F
    c_bdim = ce.extract_from_pcm(pcm_bdim[-16384:], record_history=False)
    est = ChordDetector(include_sevenths=True).update(c_bdim, is_silent=False)
    assert est.primary == "Bdim", f"Bdim classified as {est.primary}"


@pytest.mark.xfail(strict=True, reason="A-M5")
def test_am5_drum_band_crosstalk_1500hz_click_does_not_trigger_kick(tmp_path: Path) -> None:
    """Pure 1.5 kHz clicks (snare band) must not trigger false Kick hits."""
    from analysis.stem_analyzer import analyze_drums_stem

    sig = np.zeros(int(4.0 * SR), dtype=np.float32)
    click_t = np.arange(int(0.025 * SR), dtype=np.float32) / float(SR)
    click = (0.85 * np.sin(2.0 * np.pi * 1500.0 * click_t) * np.exp(-click_t * 120.0)).astype(np.float32)
    for k in range(6):
        idx = int((0.4 + k * 0.5) * SR)
        sig[idx : idx + click.shape[0]] += click
    wav_path = tmp_path / "click_1500hz.wav"
    _write_wav_pcm16(wav_path, sig)

    res = analyze_drums_stem(wav_path)
    assert len(res.kick_times_sec) == 0, f"1.5 kHz clicks triggered {len(res.kick_times_sec)} false kicks: {res.kick_times_sec}"


def test_al2_midi_normalize_preserves_multi_tempo_onset_timing(tmp_path: Path) -> None:
    """Normalizing a 120->60 BPM multi-tempo MIDI must preserve real onset times in seconds."""
    from analysis.midi_common import normalize_midi_file_for_cubase

    src = tmp_path / "var_tempo.mid"
    mid = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    # 120 BPM (0.5s/beat): note 1 at t=0.0s, note 2 at t=0.5s (480 ticks)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    tr.append(mido.Message("note_on", note=60, velocity=90, time=0))
    tr.append(mido.Message("note_off", note=60, velocity=0, time=240))
    tr.append(mido.Message("note_on", note=62, velocity=90, time=240))
    tr.append(mido.Message("note_off", note=62, velocity=0, time=240))
    # Change to 60 BPM (1.0s/beat) at beat 2 (t=1.0s): note 3 at t=1.0s, note 4 at t=2.0s (480 ticks later)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(60), time=240))
    tr.append(mido.Message("note_on", note=64, velocity=90, time=0))
    tr.append(mido.Message("note_off", note=64, velocity=0, time=240))
    tr.append(mido.Message("note_on", note=65, velocity=90, time=240))
    tr.append(mido.Message("note_off", note=65, velocity=0, time=240))
    mid.save(str(src))

    out = normalize_midi_file_for_cubase(src, tmp_path / "norm.mid", stem_name="bass")
    norm_mid = mido.MidiFile(str(out))
    onsets_sec: list[float] = []
    cur_t = 0.0
    for msg in norm_mid:
        cur_t += float(msg.time)
        if msg.type == "note_on" and msg.velocity > 0:
            onsets_sec.append(round(cur_t, 3))
    expected = [0.0, 0.5, 1.0, 2.0]
    assert len(onsets_sec) == 4
    for got, exp in zip(onsets_sec, expected):
        assert abs(got - exp) < 0.05, f"Multi-tempo onset drift: got {onsets_sec}, expected {expected}"


def test_al4_bass_median_filter_does_not_average_two_neighbors_to_1_5f() -> None:
    """analyze_bass_stem must only take median when 3 neighbors exist, never np.median([f, 2f]) = 1.5f."""
    src = (REPO_ROOT / "analysis" / "stem_analyzer.py").read_text("utf-8")
    # Locate the 3-frame median filter block
    assert "len(nbrs) == 3" in src or "len(nbrs) >= 3" in src, (
        "analyze_bass_stem applies np.median to 2-element nbrs, producing 1.5f on edge octave glitches"
    )


def test_al5_iter_aligned_mono_48k_frames_uses_streaming_resampler_without_chunk_glitches(tmp_path: Path) -> None:
    """44.1kHz input to _iter_aligned_mono_48k_frames must use StreamingResampler with no 0.5s chunk boundary glitches."""
    from analysis.stem_analyzer import _iter_aligned_mono_48k_frames
    from audio.pcm_utils import normalize_to_canonical_pcm

    sr_in = 44100
    t = np.arange(int(1.6 * sr_in), dtype=np.float32) / float(sr_in)
    sine = (0.5 * np.sin(2.0 * np.pi * 433.0 * t + 1.1)).astype(np.float32)
    ref = normalize_to_canonical_pcm(sine, src_rate=sr_in, src_channels=1, dst_rate=SR, dst_channels=1)[:, 0]
    wav_path = tmp_path / "sine_44k.wav"
    _write_wav_pcm16(wav_path, sine, sr=sr_in)

    _, it = _iter_aligned_mono_48k_frames([(wav_path, 1.0)], fft_size=2048, hop_size=2048, max_seconds=2.0)
    got = np.concatenate([f for _, f in it], axis=0)
    n = min(len(ref), len(got)) - 2000
    max_err = float(np.max(np.abs(got[1000 : 1000 + n] - ref[1000 : 1000 + n])))
    assert max_err < 0.005, f"44.1kHz offline resampling has 0.5s chunk-boundary glitch (max_err={max_err:.4f})"


def test_aperf_spectrum_analyze_frame_supports_record_false() -> None:
    """SpectrumAnalyzer.analyze_frame must accept record=False to avoid writing UI spectrogram history during offline analysis."""
    from analysis.fft import SpectrumAnalyzer

    sig = inspect.signature(SpectrumAnalyzer.analyze_frame)
    assert "record" in sig.parameters, "SpectrumAnalyzer.analyze_frame missing `record: bool = True` switch"
