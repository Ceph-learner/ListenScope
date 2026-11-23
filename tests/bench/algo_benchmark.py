"""Reproducible synthetic algorithm benchmark (A-BENCH) for ListenScope Phase 2B.

Run directly:
    python -m tests.bench.algo_benchmark
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.chords import ChordDetector
from analysis.chroma import PITCH_CLASSES, ChromaExtractor
from analysis.key_detection import KeyDetector
from analysis.pitch import PitchEstimator, freq_to_note_and_cents
from analysis.fft import SpectrumAnalyzer
from analysis.stem_analyzer import _estimate_offline_bpm_from_flux
from analysis.tempo import TempoEstimator
from core.config import AnalysisConfig

SR = 48000


def _midi_to_hz(midi: float) -> float:
    return float(440.0 * (2.0 ** ((midi - 69.0) / 12.0)))


def _synth_chord_segment(
    bass_midi: int,
    upper_midis: list[int],
    dur_sec: float,
    *,
    sr: int = SR,
    bass_gain: float = 0.45,
) -> np.ndarray:
    n = int(round(dur_sec * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    sig = np.zeros(n, dtype=np.float32)
    # Bass note in C2 octave with gentle 2nd/3rd harmonics
    fb = _midi_to_hz(bass_midi)
    sig += bass_gain * (
        0.75 * np.sin(2.0 * np.pi * fb * t)
        + 0.25 * np.sin(2.0 * np.pi * 2.0 * fb * t)
        + 0.10 * np.sin(2.0 * np.pi * 3.0 * fb * t)
    )
    # Upper voicing
    ug = 0.28 / max(1, len(upper_midis))
    for m in upper_midis:
        f = _midi_to_hz(m)
        sig += ug * (
            0.70 * np.sin(2.0 * np.pi * f * t)
            + 0.22 * np.sin(2.0 * np.pi * 2.0 * f * t)
            + 0.08 * np.sin(2.0 * np.pi * 3.0 * f * t)
        )
    # Soft attack/release envelope
    fade = min(int(0.015 * sr), n // 4)
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        sig[:fade] *= ramp
        sig[-fade:] *= ramp[::-1]
    return sig.astype(np.float32)


def _synth_progression(
    chords: list[tuple[int, list[int]]],
    chord_sec: float = 1.0,
    sr: int = SR,
) -> np.ndarray:
    return np.concatenate([_synth_chord_segment(b, u, chord_sec, sr=sr) for b, u in chords], axis=0)


def _synth_scale(root_pc: int, intervals: list[int], note_sec: float = 0.28, sr: int = SR) -> np.ndarray:
    seq = intervals + intervals[-2::-1]
    parts = []
    for iv in seq:
        m = 60 + root_pc + iv
        parts.append(_synth_chord_segment(36 + ((root_pc + iv) % 12), [m], note_sec, sr=sr, bass_gain=0.22))
    return np.concatenate(parts, axis=0)


def _mirex_key_weight(pred: str, true_key: str) -> float:
    if pred == true_key:
        return 1.0
    if " " not in pred or " " not in true_key:
        return 0.0
    pr, pm = pred.split()
    tr, tm = true_key.split()
    if pr not in PITCH_CLASSES or tr not in PITCH_CLASSES:
        return 0.0
    p_pc = PITCH_CLASSES.index(pr)
    t_pc = PITCH_CLASSES.index(tr)
    if pm == tm and ((p_pc - t_pc) % 12 in (5, 7)):
        return 0.5
    if pm != tm:
        if (tm == "major" and (t_pc + 9) % 12 == p_pc) or (tm == "minor" and (t_pc + 3) % 12 == p_pc):
            return 0.3
        if p_pc == t_pc:
            return 0.2
    return 0.0


def _eval_key_pcm(pcm: np.ndarray, *, sr: int = SR) -> str:
    ce = ChromaExtractor(sample_rate=sr)
    kd = KeyDetector()
    win = 16384
    hop = 2048
    chromas: list[np.ndarray] = []
    basses: list[np.ndarray] = []
    for s in range(0, max(1, pcm.shape[0] - win + 1), hop):
        seg = pcm[s : s + win]
        if seg.shape[0] < win:
            break
        c12 = ce.extract_from_pcm(seg, record_history=True)
        chromas.append(c12)
    mat, weights, bass_mat = ce.recent_chroma_bundle(seconds=30.0)
    est = kd.estimate(mat, frame_weights=weights, bass_window=bass_mat)
    return est.primary


def run_key_benchmark() -> dict[str, float]:
    """24 keys x (cadence + pop progression + scale) = 72 cases with C2 bass roots."""
    total_w = 0.0
    exact = 0
    total = 0
    maj_cad_hits = 0
    min_cad_hits = 0

    for root in range(12):
        r_name = PITCH_CLASSES[root]
        b0 = 36 + root  # C2..B2

        # Major I-IV-V-I
        ch_maj_cad = [
            (b0, [60 + root, 64 + root, 67 + root]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 64 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
            (b0, [60 + root, 64 + root, 67 + root]),
        ]
        # Major vi-IV-I-V
        ch_maj_pop = [
            (36 + (root + 9) % 12, [60 + (root + 9) % 12, 63 + (root + 9) % 12, 67 + (root + 9) % 12]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 64 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (b0, [60 + root, 64 + root, 67 + root]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
        ]
        # Minor i-iv-V-i (harmonic minor V)
        ch_min_cad = [
            (b0, [60 + root, 63 + root, 67 + root]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 63 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
            (b0, [60 + root, 63 + root, 67 + root]),
        ]
        # Minor i-VI-III-VII
        ch_min_pop = [
            (b0, [60 + root, 63 + root, 67 + root]),
            (36 + (root + 8) % 12, [60 + (root + 8) % 12, 64 + (root + 8) % 12, 67 + (root + 8) % 12]),
            (36 + (root + 3) % 12, [60 + (root + 3) % 12, 64 + (root + 3) % 12, 67 + (root + 3) % 12]),
            (36 + (root + 10) % 12, [60 + (root + 10) % 12, 64 + (root + 10) % 12, 67 + (root + 10) % 12]),
        ]

        cases = [
            (f"{r_name} major", _synth_progression(ch_maj_cad, 1.0), "maj_cad"),
            (f"{r_name} major", _synth_progression(ch_maj_pop, 1.0), "maj_pop"),
            (f"{r_name} major", _synth_scale(root, [0, 2, 4, 5, 7, 9, 11, 12]), "maj_scale"),
            (f"{r_name} minor", _synth_progression(ch_min_cad, 1.0), "min_cad"),
            (f"{r_name} minor", _synth_progression(ch_min_pop, 1.0), "min_pop"),
            (f"{r_name} minor", _synth_scale(root, [0, 2, 3, 5, 7, 8, 10, 12]), "min_scale"),
        ]
        for true_key, pcm, tag in cases:
            pred = _eval_key_pcm(pcm)
            w = _mirex_key_weight(pred, true_key)
            total_w += w
            if pred == true_key:
                exact += 1
                if tag == "maj_cad":
                    maj_cad_hits += 1
                elif tag == "min_cad":
                    min_cad_hits += 1
            total += 1

    return {
        "mirex_score": round(100.0 * total_w / max(1, total), 2),
        "exact_acc": round(100.0 * exact / max(1, total), 2),
        "major_I_IV_V_I_acc": round(100.0 * maj_cad_hits / 12.0, 2),
        "minor_i_iv_V_i_acc": round(100.0 * min_cad_hits / 12.0, 2),
    }


def run_chord_benchmark() -> dict[str, float]:
    """Triads (24), first inversions (12), and triads with sevenths enabled (24)."""
    ce = ChromaExtractor(sample_rate=SR)
    triad_hits = 0
    triad_with_7_hits = 0
    inv_hits = 0

    for root in range(12):
        r_name = PITCH_CLASSES[root]
        for is_minor in (False, True):
            expected = f"{r_name}m" if is_minor else r_name
            third = 3 if is_minor else 4
            pcm = _synth_chord_segment(36 + root, [60 + root, 60 + root + third, 60 + root + 7], 0.8)
            c12 = ce.extract_from_pcm(pcm[-16384:], record_history=False)

            cd_triad = ChordDetector(include_sevenths=False)
            est_t = cd_triad.update(c12, is_silent=False)
            if est_t.primary == expected:
                triad_hits += 1

            cd_7 = ChordDetector(include_sevenths=True)
            est_7 = cd_7.update(c12, is_silent=False)
            if est_7.primary == expected:
                triad_with_7_hits += 1

        # First inversion major triad (e.g. C/E: bass=E2, upper=C4,E4,G4)
        bass_pc = (root + 4) % 12
        pcm_inv = _synth_chord_segment(36 + bass_pc, [60 + root, 64 + root, 67 + root], 0.8, bass_gain=0.60)
        c_inv = ce.extract_from_pcm(pcm_inv[-16384:], record_history=False)
        cd_inv = ChordDetector(include_sevenths=False)
        est_inv = cd_inv.update(c_inv, is_silent=False)
        # Accept either exact triad root or slash chord `Root/3rd`
        if est_inv.primary in (r_name, f"{r_name}/{PITCH_CLASSES[bass_pc]}"):
            inv_hits += 1

    return {
        "triad_acc": round(100.0 * triad_hits / 24.0, 2),
        "triad_with_sevenths_on_acc": round(100.0 * triad_with_7_hits / 24.0, 2),
        "inversion_acc": round(100.0 * inv_hits / 12.0, 2),
    }


def _synth_click_track(bpm: float, dur_sec: float = 10.0, *, style: str = "click", sr: int = SR) -> np.ndarray:
    n = int(round(dur_sec * sr))
    sig = np.zeros(n, dtype=np.float32)
    beat_sec = 60.0 / bpm
    rng = np.random.default_rng(42)

    def _add_kick(t0: float) -> None:
        idx = int(round(t0 * sr))
        ln = min(int(0.08 * sr), n - idx)
        if ln <= 0:
            return
        t = np.arange(ln, dtype=np.float32) / sr
        f = 120.0 * np.exp(-t * 28.0) + 48.0
        sig[idx : idx + ln] += 0.8 * np.sin(2.0 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 22.0)

    def _add_snare(t0: float) -> None:
        idx = int(round(t0 * sr))
        ln = min(int(0.07 * sr), n - idx)
        if ln <= 0:
            return
        t = np.arange(ln, dtype=np.float32) / sr
        noise = rng.standard_normal(ln).astype(np.float32)
        sig[idx : idx + ln] += 0.55 * (0.5 * noise + 0.5 * np.sin(2.0 * np.pi * 220.0 * t)) * np.exp(-t * 30.0)

    def _add_click(t0: float) -> None:
        idx = int(round(t0 * sr))
        ln = min(int(0.02 * sr), n - idx)
        if ln <= 0:
            return
        t = np.arange(ln, dtype=np.float32) / sr
        sig[idx : idx + ln] += 0.85 * np.sin(2.0 * np.pi * 1200.0 * t) * np.exp(-t * 140.0)

    t = 0.05
    beat = 0
    while t < dur_sec - 0.1:
        if style == "click":
            _add_click(t)
        elif style == "rock":
            if beat % 2 == 0:
                _add_kick(t)
            else:
                _add_snare(t)
        elif style == "dnb":
            bar_pos = beat % 4
            if bar_pos == 0:
                _add_kick(t)
            elif bar_pos in (1, 3):
                _add_snare(t)
            elif bar_pos == 2:
                _add_kick(t + 0.5 * beat_sec)
        t += beat_sec
        beat += 1
    return np.clip(sig, -1.0, 1.0)


def _bpm_acc(pred: float | None, target: float) -> tuple[bool, bool]:
    if pred is None or pred <= 0:
        return False, False
    acc1 = abs(pred - target) / target <= 0.04
    acc2 = any(abs(pred - target * mult) / (target * mult) <= 0.04 for mult in (0.5, 1.0, 2.0))
    return acc1, acc2


def run_tempo_benchmark() -> dict[str, float]:
    """Click / Rock / DnB across 60..174 BPM for real-time TempoEstimator and offline flux BPM."""
    cases = [
        (60.0, "click"),
        (90.0, "click"),
        (120.0, "click"),
        (140.0, "click"),
        (174.0, "click"),
        (60.0, "rock"),
        (90.0, "rock"),
        (120.0, "rock"),
        (140.0, "rock"),
        (174.0, "dnb"),
    ]
    cfg = AnalysisConfig()
    rt_a1 = rt_a2 = off_a1 = off_a2 = 0
    step_rt = int(round(SR / cfg.analysis_rate_hz))  # 3200 samples @ 15 Hz
    fft_size = cfg.fft_size

    for bpm, style in cases:
        pcm = _synth_click_track(bpm, dur_sec=10.0, style=style)
        # Real-time TempoEstimator at nominal 15 Hz
        spec_an = SpectrumAnalyzer(sample_rate=SR, config=cfg)
        te = TempoEstimator(config=cfg)
        est = None
        for pos in range(0, pcm.shape[0] - fft_size + 1, step_rt):
            _, _, log_db = spec_an.analyze_frame(pcm[pos : pos + fft_size])
            est = te.update(log_db, is_silent=False)
        a1, a2 = _bpm_acc(est.bpm if est else None, bpm)
        rt_a1 += int(a1)
        rt_a2 += int(a2)

        # Offline flux BPM at 93.75 Hz (hop=512)
        hop = 512
        win = np.hanning(2048).astype(np.float32)
        prev_lm = None
        flux_list: list[float] = []
        for pos in range(0, pcm.shape[0] - 2048 + 1, hop):
            lm = np.log1p(np.abs(np.fft.rfft(pcm[pos : pos + 2048] * win)).astype(np.float32))
            flux_list.append(0.0 if prev_lm is None else float(np.mean(np.maximum(0.0, lm - prev_lm))))
            prev_lm = lm
        off_est = _estimate_offline_bpm_from_flux(np.asarray(flux_list, dtype=np.float32), rate_hz=SR / float(hop))
        oa1, oa2 = _bpm_acc(off_est.bpm, bpm)
        off_a1 += int(oa1)
        off_a2 += int(oa2)

    n = len(cases)
    return {
        "rt_acc1": round(100.0 * rt_a1 / n, 2),
        "rt_acc2": round(100.0 * rt_a2 / n, 2),
        "offline_acc1": round(100.0 * off_a1 / n, 2),
        "offline_acc2": round(100.0 * off_a2 / n, 2),
    }


def run_pitch_benchmark() -> dict[str, float]:
    """E1-C6 harmonic sweep + weak-f0 E1-E3 octave-error benchmark."""
    fft_size = 4096
    win = np.hanning(fft_size).astype(np.float32)
    pe = PitchEstimator(sample_rate=SR, fft_size=fft_size)

    # 1. Standard 1/k harmonic sweep E1 (28) to C6 (84) step 2
    std_hits = 0
    std_errs: list[float] = []
    std_midis = list(range(28, 85, 2))
    t = np.arange(fft_size, dtype=np.float32) / float(SR)
    for m in std_midis:
        f0 = _midi_to_hz(m)
        sig = sum((1.0 / k) * np.sin(2.0 * np.pi * k * f0 * t) for k in range(1, 5) if k * f0 < SR * 0.45)
        sig = (sig / (np.max(np.abs(sig)) + 1e-9) * 0.5).astype(np.float32)
        mag = np.abs(np.fft.rfft(sig * win)).astype(np.float32)
        est = pe.estimate_from_magnitude(mag, is_silent=False)
        true_name, _ = freq_to_note_and_cents(f0)
        if est.note_name == true_name and est.frequency_hz is not None:
            std_hits += 1
            std_errs.append(abs(1200.0 * np.log2(est.frequency_hz / f0)))

    # 2. Weak fundamental (f0 amp=0.15) across E1..E3 (MIDI 28..52)
    weak_hits = 0
    weak_midis = list(range(28, 53))
    for m in weak_midis:
        f0 = _midi_to_hz(m)
        sig = (
            0.15 * np.sin(2.0 * np.pi * f0 * t)
            + 1.00 * np.sin(2.0 * np.pi * 2.0 * f0 * t)
            + 0.70 * np.sin(2.0 * np.pi * 3.0 * f0 * t)
            + 0.40 * np.sin(2.0 * np.pi * 4.0 * f0 * t)
        ).astype(np.float32)
        sig *= 0.5 / (float(np.max(np.abs(sig))) + 1e-9)
        mag = np.abs(np.fft.rfft(sig * win)).astype(np.float32)
        est = pe.estimate_from_magnitude(mag, is_silent=False)
        true_name, _ = freq_to_note_and_cents(f0)
        if est.note_name == true_name:
            weak_hits += 1

    return {
        "pitch_std_acc": round(100.0 * std_hits / len(std_midis), 2),
        "pitch_std_median_cents": round(float(np.median(std_errs)) if std_errs else 999.0, 2),
        "pitch_weak_f0_acc": round(100.0 * weak_hits / len(weak_midis), 2),
    }


def run_all_benchmarks() -> dict[str, Any]:
    return {
        "key": run_key_benchmark(),
        "chord": run_chord_benchmark(),
        "tempo": run_tempo_benchmark(),
        "pitch": run_pitch_benchmark(),
    }


if __name__ == "__main__":
    results = run_all_benchmarks()
    print(json.dumps(results, indent=2, ensure_ascii=False))
