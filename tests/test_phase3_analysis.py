"""Phase 3 tests: CPU-only FFT/spectrum, 12-bin chroma, chords, Krumhansl-Schmuckler key, BPM, pitch, bounded history."""

from __future__ import annotations

import numpy as np

from analysis.chords import ChordDetector
from analysis.chroma import ChromaExtractor
from analysis.fft import SpectrumAnalyzer
from analysis.key_detection import KeyDetector
from analysis.pitch import PitchEstimator
from analysis.tempo import TempoEstimator
from core.config import AnalysisConfig


def _chord_signal(freqs_hz: list[float], duration_sec: float = 0.4, sr: int = 48000) -> np.ndarray:
    t = np.arange(int(duration_sec * sr), dtype=np.float32) / float(sr)
    sig = np.zeros_like(t)
    for f in freqs_hz:
        sig += 0.22 * np.sin(2.0 * np.pi * f * t) + 0.08 * np.sin(4.0 * np.pi * f * t)
    return sig.astype(np.float32)


def test_fft_chroma_chords_and_silence_gating() -> None:
    cfg = AnalysisConfig(spectrum_history_seconds=2, chroma_history_seconds=3, analysis_rate_hz=15.0)
    spec = SpectrumAnalyzer(sample_rate=48000, config=cfg)
    chroma_ext = ChromaExtractor(sample_rate=48000, config=cfg)
    chord_det = ChordDetector()
    pitch_est = PitchEstimator(sample_rate=48000, fft_size=cfg.fft_size)

    # C major triad: C4 (261.63), E4 (329.63), G4 (392.00)
    cmaj_pcm = _chord_signal([261.63, 329.63, 392.00])
    for _ in range(5):
        mag, fft_db, log_db = spec.analyze_frame(cmaj_pcm)
        c12 = chroma_ext.extract_from_magnitude(mag, is_silent=False)
        chord = chord_det.update(c12, is_silent=False)

    assert chord.primary == "C"
    assert chord.is_silent is False
    assert chord.stability in ("Medium", "High")

    # A minor triad: A3 (220.0), C4 (261.63), E4 (329.63)
    chord_det.reset()
    amin_pcm = _chord_signal([220.0, 261.63, 329.63])
    for _ in range(5):
        mag, _, _ = spec.analyze_frame(amin_pcm)
        c12 = chroma_ext.extract_from_magnitude(mag, is_silent=False)
        chord_am = chord_det.update(c12, is_silent=False)
    assert chord_am.primary == "Am"

    # Silence -> must report N / Silent
    silent_chord = chord_det.update(np.zeros(12, dtype=np.float32), is_silent=True)
    assert silent_chord.is_silent is True
    assert "N" in silent_chord.primary

    # White/flat chroma noise -> low correlation -> Unknown
    chord_det.reset()
    flat_chord = chord_det.update(np.ones(12, dtype=np.float32) / np.sqrt(12.0), is_silent=False)
    assert flat_chord.primary == "Unknown"

    # Pure 440Hz tone pitch detection
    a4_pcm = _chord_signal([440.0])
    mag_a4, _, _ = spec.analyze_frame(a4_pcm)
    p = pitch_est.estimate_from_magnitude(mag_a4, is_silent=False)
    assert p.frequency_hz is not None
    assert abs(p.frequency_hz - 440.0) < 12.0
    assert p.note_name == "A4"

    # Bounded history check: push > history_maxlen frames and ensure deque caps size cleanly
    for _ in range(80):
        mag, _, _ = spec.analyze_frame(cmaj_pcm)
        chroma_ext.extract_from_magnitude(mag, is_silent=False)
    assert spec.recent_log_spectrogram().shape[0] <= spec.history_maxlen
    assert chroma_ext.recent_chroma_matrix().shape[0] <= chroma_ext.history_maxlen


def test_pitch_refines_both_search_edges_without_half_bin_bias():
    estimator = PitchEstimator(sample_rate=40960, fft_size=4096)
    for peak_bin in (4, 160):
        magnitude = np.zeros(2049, dtype=np.float32)
        magnitude[peak_bin - 1:peak_bin + 2] = [0.6, 1.0, 0.6]
        estimate = estimator.estimate_from_magnitude(magnitude, is_silent=False)
        assert estimate.frequency_hz == peak_bin * 10.0


def test_krumhansl_schmuckler_key_detection_and_modulation() -> None:
    spec = SpectrumAnalyzer(sample_rate=48000)
    chroma_ext = ChromaExtractor(sample_rate=48000)
    key_det = KeyDetector(min_active_frames=16)

    # Feed C major progression: C - F - G - C
    chords = [
        [261.63, 329.63, 392.00],  # C
        [174.61, 220.00, 261.63],  # F
        [196.00, 246.94, 293.66],  # G
        [261.63, 329.63, 392.00],  # C
    ]
    rows = []
    for notes in chords:
        mag, _, _ = spec.analyze_frame(_chord_signal(notes))
        vec = chroma_ext.extract_from_magnitude(mag, record_history=False)
        for _ in range(8):
            rows.append(vec)
    res_c = key_det.estimate(np.stack(rows, axis=0))
    assert res_c.primary == "C major"
    assert "调号" in res_c.key_signature_note

    # Progression modulating from C major half -> E major half
    e_chords = [
        [164.81, 207.65, 246.94],  # E
        [220.00, 277.18, 329.63],  # A
        [246.94, 311.13, 369.99],  # B
        [164.81, 207.65, 246.94],  # E
    ]
    e_rows = []
    for notes in e_chords:
        mag, _, _ = spec.analyze_frame(_chord_signal(notes))
        vec = chroma_ext.extract_from_magnitude(mag, record_history=False)
        for _ in range(8):
            e_rows.append(vec)
    res_mod = key_det.estimate(np.vstack([np.stack(rows, axis=0), np.stack(e_rows, axis=0)]))
    assert res_mod.modulation_hint is True

    # Insufficient frames -> Unknown / Insufficient
    res_empty = key_det.estimate(np.empty((0, 12), dtype=np.float32))
    assert res_empty.primary == "Unknown"
    assert res_empty.stability == "Insufficient"


def test_tempo_estimator_tracks_120_bpm_pulses() -> None:
    cfg = AnalysisConfig(analysis_rate_hz=15.0, tempo_window_seconds=16)
    tempo = TempoEstimator(config=cfg)

    # Simulate periodic drum beats every 0.5s (= 120 BPM) at 15 Hz frame rate
    total_frames = 180  # 12 seconds
    for idx in range(total_frames):
        t = idx / 15.0
        # Sharp beat transient every 0.5s (t % 0.5 near 0)
        phase = t % 0.5
        is_beat = phase < 0.07
        log_db = np.full(cfg.log_freq_bins, -10.0 if is_beat else -60.0, dtype=np.float32)
        est = tempo.update(log_db, is_silent=False)

    assert est.bpm is not None
    assert 112.0 <= est.bpm <= 128.0
    assert est.stability in ("Medium", "High")

    tempo.reset()
    sil = tempo.update(np.zeros(cfg.log_freq_bins, dtype=np.float32), is_silent=True)
    assert sil.bpm is None
    assert sil.stability == "Unknown"


def test_tempo_detects_beats_with_silent_gaps():
    config = AnalysisConfig(analysis_rate_hz=16.0, tempo_window_seconds=12)
    estimator = TempoEstimator(config=config)
    silent = np.full(config.log_freq_bins, -120.0, dtype=np.float32)
    attack = np.full_like(silent, -15.0)
    for frame in range(160):
        beat = frame % 8 == 0
        estimate = estimator.update(attack if beat else silent, is_silent=not beat)
    assert estimate.bpm is not None
    assert 118.0 <= estimate.bpm <= 122.0
    assert estimate.stability == "High"
