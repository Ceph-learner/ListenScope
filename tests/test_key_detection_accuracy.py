"""Regression and accuracy tests for the 3-part key detection upgrade."""

from __future__ import annotations

from pathlib import Path
import wave

import numpy as np

from analysis.chords import ChordDetector, chord_scale_degree, transpose_key_label
from analysis.chroma import ChromaExtractor
from analysis.key_detection import KeyDetector
from analysis.stem_analyzer import analyze_stems_offline
from core.config import AnalysisConfig
from ui.chroma_widget import _format_key_display


_NOTE_SEMITONES = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def _midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def _rich_tone(freq_hz: float, t: np.ndarray, *, amp: float = 1.0, harmonics: int = 6) -> np.ndarray:
    sig = np.zeros_like(t, dtype=np.float32)
    for k in range(1, harmonics + 1):
        if freq_hz * k >= 18000.0:
            break
        sig += (amp / (k ** 1.15)) * np.sin(2.0 * np.pi * (freq_hz * k) * t, dtype=np.float32)
    return sig


def _synth_pop_progression(
    chords: list[tuple[str, list[int]]],
    *,
    chord_sec: float = 0.8,
    sr: int = 48000,
    bass_boost_db: float = 10.0,
    add_drums: bool = True,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthesize (full_mix, harmonic_other, bass_only) with harmonics, +10 dB bass, drums, and tanh limiting."""
    rng = np.random.default_rng(seed)
    bass_gain = 10.0 ** (bass_boost_db / 20.0)
    other_parts: list[np.ndarray] = []
    bass_parts: list[np.ndarray] = []
    drum_parts: list[np.ndarray] = []

    n_per_chord = int(round(chord_sec * sr))
    t = np.arange(n_per_chord, dtype=np.float32) / float(sr)
    env = np.minimum(1.0, t / 0.015) * np.exp(-1.1 * t)

    for bass_name, upper_midis in chords:
        bass_pc = _NOTE_SEMITONES[bass_name]
        # Place bass in Octave 2 (MIDI 36..47: C2..B2)
        bass_midi = 36 + bass_pc
        bass_sig = _rich_tone(_midi_to_hz(bass_midi), t, amp=0.28 * bass_gain, harmonics=4) * env
        bass_parts.append(bass_sig.astype(np.float32))

        chord_sig = np.zeros_like(t, dtype=np.float32)
        for m in upper_midis:
            chord_sig += _rich_tone(_midi_to_hz(m), t, amp=0.14, harmonics=6) * env
        other_parts.append(chord_sig.astype(np.float32))

        if add_drums:
            d_sig = np.zeros_like(t, dtype=np.float32)
            # Kick at 0.0s, 0.4s; snare at 0.2s, 0.6s; hi-hat every 0.1s
            for beat_t in (0.0, 0.4):
                idx = int(beat_t * sr)
                k_len = min(int(0.14 * sr), n_per_chord - idx)
                if k_len > 0:
                    kt = np.arange(k_len, dtype=np.float32) / float(sr)
                    f_sweep = 115.0 * np.exp(-28.0 * kt) + 46.0
                    phase = 2.0 * np.pi * np.cumsum(f_sweep) / float(sr)
                    d_sig[idx : idx + k_len] += 0.95 * np.sin(phase) * np.exp(-16.0 * kt)
            for beat_t in (0.2, 0.6):
                idx = int(beat_t * sr)
                s_len = min(int(0.12 * sr), n_per_chord - idx)
                if s_len > 0:
                    st = np.arange(s_len, dtype=np.float32) / float(sr)
                    noise = rng.standard_normal(s_len).astype(np.float32)
                    d_sig[idx : idx + s_len] += 0.45 * noise * np.exp(-24.0 * st)
            for hat_i in range(int(chord_sec / 0.1)):
                idx = int(hat_i * 0.1 * sr)
                h_len = min(int(0.03 * sr), n_per_chord - idx)
                if h_len > 0:
                    ht = np.arange(h_len, dtype=np.float32) / float(sr)
                    noise = rng.standard_normal(h_len).astype(np.float32)
                    # Simple high-pass character via diff
                    hp = np.diff(noise, prepend=0.0)
                    d_sig[idx : idx + h_len] += 0.25 * hp * np.exp(-75.0 * ht)
            drum_parts.append(d_sig)
        else:
            drum_parts.append(np.zeros_like(t, dtype=np.float32))

    other_all = np.concatenate(other_parts)
    bass_all = np.concatenate(bass_parts)
    drums_all = np.concatenate(drum_parts)
    mix_all = np.tanh(other_all + bass_all + drums_all).astype(np.float32)
    return mix_all, other_all.astype(np.float32), bass_all.astype(np.float32)


def _estimate_key_from_pcm(pcm: np.ndarray, *, sr: int = 48000, hop: int = 2048) -> str:
    cfg = AnalysisConfig(chroma_history_seconds=30, analysis_rate_hz=sr / float(hop))
    ce = ChromaExtractor(sample_rate=sr, config=cfg)
    kd = KeyDetector(min_active_frames=12)
    win = 16384
    if pcm.shape[0] < win:
        pcm = np.pad(pcm, (0, win - pcm.shape[0]))
    for start in range(0, pcm.shape[0] - win + 1, hop):
        seg = pcm[start : start + win]
        ce.extract_from_pcm(seg, record_history=True, is_silent=False)
    chroma_win, weight_win, bass_win = ce.recent_chroma_bundle()
    return kd.estimate(chroma_win, frame_weights=weight_win, bass_window=bass_win).primary


def _write_wav(path: Path, mono: np.ndarray, sr: int = 48000) -> None:
    clipped = np.clip(mono, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def test_octave2_no_blind_spots_in_hr_filterbank() -> None:
    ce = ChromaExtractor(sample_rate=48000)
    oct2_mask = (ce._hr_freqs >= 65.41) & (ce._hr_freqs <= 130.81)
    oct2_weights = np.sum(ce._hr_chroma_fb[:, oct2_mask], axis=1)
    assert np.all(oct2_weights > 0.0), f"Blind spot in Octave 2: {oct2_weights}"
    ratio = float(np.min(oct2_weights) / np.max(oct2_weights))
    assert ratio >= 0.45, f"Octave 2 pitch-class imbalance too high: min/max={ratio:.3f}, weights={oct2_weights}"


def test_heavy_bass_and_drums_pop_jazz_key_accuracy() -> None:
    # 1. A minor jazz / Marunouchi-style (Rakuen Toshi): FM7 - E7 - Am7 - C7 / Dm7 - G7 - CM7 - E7/G#
    am_jazz = [
        ("F", [65, 69, 72, 76]),      # FM7
        ("E", [64, 68, 71, 74]),      # E7
        ("A", [69, 72, 76, 79]),      # Am7
        ("C", [60, 64, 67, 70]),      # C7
        ("D", [62, 65, 69, 72]),      # Dm7
        ("G", [67, 71, 74, 77]),      # G7
        ("C", [60, 64, 67, 71]),      # CM7
        ("G#", [64, 68, 71, 74]),     # E7/G#
        ("A", [69, 72, 76, 79]),      # Am7 cadence
    ] * 2

    # 2. Ab (G#) major J-Pop Royal Road (Pi): Db - Eb - Cm - Fm - Db - Eb - Ab - Bbm
    ab_royal = [
        ("Db", [61, 65, 68]),
        ("Eb", [63, 67, 70]),
        ("C", [60, 63, 67]),
        ("F", [65, 68, 72]),
        ("Db", [61, 65, 68]),
        ("Eb", [63, 67, 70]),
        ("Ab", [68, 72, 75]),
        ("Bb", [70, 73, 77]),
    ] * 2

    # 3. E minor rock: Em - C - G - D - Em
    em_rock = [
        ("E", [64, 67, 71]),
        ("C", [60, 64, 67]),
        ("G", [67, 71, 74]),
        ("D", [62, 66, 69]),
        ("E", [64, 67, 71]),
    ] * 3

    # 4. A minor natural pop: Am - F - C - G - Am
    am_natural = [
        ("A", [69, 72, 76]),
        ("F", [65, 69, 72]),
        ("C", [60, 64, 67]),
        ("G", [67, 71, 74]),
        ("A", [69, 72, 76]),
    ] * 3

    # 5. C major
    c_maj = [
        ("C", [60, 64, 67]),
        ("F", [65, 69, 72]),
        ("G", [67, 71, 74]),
        ("C", [60, 64, 67]),
    ] * 3

    # 6. D major
    d_maj = [
        ("D", [62, 66, 69]),
        ("G", [67, 71, 74]),
        ("A", [69, 73, 76]),
        ("D", [62, 66, 69]),
    ] * 3

    # 7. D minor
    d_min = [
        ("D", [62, 65, 69]),
        ("Bb", [70, 74, 77]),
        ("C", [60, 64, 67]),
        ("A", [69, 73, 76]),
        ("D", [62, 65, 69]),
    ] * 3

    # 8. F# minor
    fs_min = [
        ("F#", [66, 69, 73]),
        ("D", [62, 66, 69]),
        ("E", [64, 68, 71]),
        ("C#", [61, 65, 68]),
        ("F#", [66, 69, 73]),
    ] * 3

    # 9. Bb major
    bb_maj = [
        ("Bb", [70, 74, 77]),
        ("Eb", [63, 67, 70]),
        ("F", [65, 69, 72]),
        ("Bb", [70, 74, 77]),
    ] * 3

    cases = [
        ("A minor (jazz)", am_jazz, "A minor"),
        ("G# major (royal road)", ab_royal, "G# major"),
        ("E minor (rock)", em_rock, "E minor"),
        ("A minor (natural)", am_natural, "A minor"),
        ("C major", c_maj, "C major"),
        ("D major", d_maj, "D major"),
        ("D minor", d_min, "D minor"),
        ("F# minor", fs_min, "F# minor"),
        ("Bb major", bb_maj, "A# major"),
    ]

    assert KeyDetector()._profile == "shaath"
    results: dict[str, str] = {}
    hits = 0
    for label, prog, expected in cases:
        mix, _, _ = _synth_pop_progression(prog, bass_boost_db=10.0, add_drums=True)
        got = _estimate_key_from_pcm(mix)
        results[label] = got
        if got == expected:
            hits += 1

    # Mandatory specific regression assertions
    assert results["A minor (jazz)"] == "A minor", f"Got {results['A minor (jazz)']}"
    assert results["G# major (royal road)"] == "G# major", f"Got {results['G# major (royal road)']}"
    assert results["E minor (rock)"] == "E minor", f"Got {results['E minor (rock)']}"
    assert results["A minor (natural)"] == "A minor", f"Got {results['A minor (natural)']}"

    accuracy = hits / float(len(cases))
    assert accuracy >= 0.85, f"Accuracy {accuracy:.2%} < 85%: {results}"


def test_chord_detector_with_harmonics_heavy_bass_and_drums() -> None:
    chord_cases = [
        ("C", ("C", [60, 64, 67]), (0, 4, 7)),
        ("Am", ("A", [69, 72, 76]), (9, 0, 4)),
        ("G", ("G", [67, 71, 74]), (7, 11, 2)),
        ("Em", ("E", [64, 67, 71]), (4, 7, 11)),
        ("F", ("F", [65, 69, 72]), (5, 9, 0)),
        ("Dm", ("D", [62, 65, 69]), (2, 5, 9)),
    ]
    ce = ChromaExtractor(sample_rate=48000)
    for expected_chord, prog_item, chord_pcs in chord_cases:
        mix, _, _ = _synth_pop_progression([prog_item] * 3, bass_boost_db=10.0, add_drums=True)
        cd = ChordDetector()
        chromas = []
        est = None
        for start in range(0, mix.shape[0] - 16384 + 1, 2048):
            c12 = ce.extract_from_pcm(mix[start : start + 16384], record_history=False, is_silent=False)
            est = cd.update(c12, is_silent=False)
            chromas.append(c12)
        assert est is not None
        assert est.primary == expected_chord, f"Expected {expected_chord}, got {est}"
        assert est.correlation >= 0.72, f"Low correlation for {expected_chord}: {est.correlation}"
        mean_c = np.mean(np.stack(chromas, axis=0), axis=0)
        in_mean = float(np.mean([mean_c[i] for i in chord_pcs]))
        out_mean = float(np.mean([mean_c[i] for i in range(12) if i not in chord_pcs]))
        contrast = in_mean / max(out_mean, 1e-6)
        assert contrast >= 3.0, f"Low chroma contrast for {expected_chord}: {contrast:.2f}x"


def test_offline_stem_analysis_excludes_drums_and_uses_bass_prior(tmp_path: Path) -> None:
    em_prog = [
        ("E", [64, 67, 71]),
        ("C", [60, 64, 67]),
        ("G", [67, 71, 74]),
        ("D", [62, 66, 69]),
        ("E", [64, 67, 71]),
    ] * 3
    _, other_pcm, bass_pcm = _synth_pop_progression(em_prog, bass_boost_db=6.0, add_drums=False)

    # Create an overwhelming, pitch-polluting drum stem tuned around C#2 (69.3 Hz)
    t = np.arange(other_pcm.shape[0], dtype=np.float32) / 48000.0
    drums_pcm = (0.95 * np.sin(2.0 * np.pi * 69.3 * t) + 0.35 * np.random.default_rng(7).standard_normal(t.shape[0])).astype(np.float32)

    other_wav = tmp_path / "other.wav"
    bass_wav = tmp_path / "bass.wav"
    drums_wav = tmp_path / "drums.wav"
    _write_wav(other_wav, other_pcm)
    _write_wav(bass_wav, bass_pcm)
    _write_wav(drums_wav, drums_pcm)

    report = analyze_stems_offline(
        {"other": other_wav, "bass": bass_wav, "drums": drums_wav},
        max_seconds=20.0,
    )
    assert report.estimated_key.primary == "E minor", f"Expected E minor, got {report.estimated_key}"


def test_ui_enharmonic_display_and_chord_compatibility() -> None:
    assert _format_key_display("G# major") == "G# / Ab major"
    assert _format_key_display("C# major") == "C# / Db major"
    assert _format_key_display("D# minor") == "D# / Eb minor"
    assert _format_key_display("A minor") == "A minor"

    assert chord_scale_degree("Db", "G# major") == "IV"
    assert transpose_key_label("G# major", 2) == "A# major"
