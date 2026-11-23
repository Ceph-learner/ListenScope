"""Frozen black-box synthetic algorithm benchmark (A-BENCH) for ListenScope Phase 2B.

DO NOT MODIFY `tests/bench/` DURING ALGORITHM IMPLEMENTATION.
Run:
    python -m tests.bench.algo_benchmark --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.chords import ChordDetector
from analysis.chroma import PITCH_CLASSES, ChromaExtractor
from analysis.key_detection import KeyDetector
from analysis.pitch import freq_to_note_and_cents
from analysis.stem_analyzer import analyze_bass_stem, analyze_drums_stem
from analysis.worker import AnalysisWorker
from audio.ring_buffer import FixedRingBuffer
from core.config import AnalysisConfig, AudioConfig

SR = 48000


def _midi_to_hz(midi: float) -> float:
    return float(440.0 * (2.0 ** ((midi - 69.0) / 12.0)))


def _to_stereo(mono: np.ndarray) -> np.ndarray:
    arr = np.asarray(mono, dtype=np.float32)
    if arr.ndim == 2:
        return np.ascontiguousarray(arr, dtype=np.float32)
    return np.ascontiguousarray(np.stack([arr, arr], axis=1), dtype=np.float32)


def _write_wav_pcm16(path: Path, mono: np.ndarray, sr: int) -> None:
    stereo = _to_stereo(mono)
    pcm16 = np.clip(stereo * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm16.tobytes())


def _new_realtime_worker(ring_seconds: int = 30) -> tuple[FixedRingBuffer, AnalysisWorker]:
    acfg = AudioConfig(sample_rate=SR, channels=2, ring_buffer_seconds=ring_seconds)
    rb = FixedRingBuffer(acfg)
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    return rb, worker


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
    fb = _midi_to_hz(bass_midi)
    sig += bass_gain * (
        0.75 * np.sin(2.0 * np.pi * fb * t)
        + 0.25 * np.sin(2.0 * np.pi * 2.0 * fb * t)
        + 0.10 * np.sin(2.0 * np.pi * 3.0 * fb * t)
    )
    ug = 0.28 / max(1, len(upper_midis))
    for m in upper_midis:
        f = _midi_to_hz(m)
        sig += ug * (
            0.70 * np.sin(2.0 * np.pi * f * t)
            + 0.22 * np.sin(2.0 * np.pi * 2.0 * f * t)
            + 0.08 * np.sin(2.0 * np.pi * 3.0 * f * t)
        )
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
    for s in range(0, max(1, pcm.shape[0] - win + 1), hop):
        seg = pcm[s : s + win]
        if seg.shape[0] < win:
            break
        ce.extract_from_pcm(seg, record_history=True)
    mat, weights, bass_mat = ce.recent_chroma_bundle(seconds=30.0)
    est = kd.estimate(mat, frame_weights=weights, bass_window=bass_mat)
    return est.primary


def run_key_benchmark() -> dict[str, float]:
    """24 keys x (cadence + pop progression + scale) = 72 cases with C2 bass roots (unchanged)."""
    total_w = 0.0
    exact = 0
    total = 0
    maj_cad_hits = 0
    min_cad_hits = 0

    for root in range(12):
        r_name = PITCH_CLASSES[root]
        b0 = 36 + root

        ch_maj_cad = [
            (b0, [60 + root, 64 + root, 67 + root]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 64 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
            (b0, [60 + root, 64 + root, 67 + root]),
        ]
        ch_maj_pop = [
            (36 + (root + 9) % 12, [60 + (root + 9) % 12, 63 + (root + 9) % 12, 67 + (root + 9) % 12]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 64 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (b0, [60 + root, 64 + root, 67 + root]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
        ]
        ch_min_cad = [
            (b0, [60 + root, 63 + root, 67 + root]),
            (36 + (root + 5) % 12, [60 + (root + 5) % 12, 63 + (root + 5) % 12, 67 + (root + 5) % 12]),
            (36 + (root + 7) % 12, [60 + (root + 7) % 12, 64 + (root + 7) % 12, 67 + (root + 7) % 12]),
            (b0, [60 + root, 63 + root, 67 + root]),
        ]
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


def _synth_click_track(bpm: float, dur_sec: float = 20.0, *, style: str = "click", sr: int = SR) -> np.ndarray:
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


_TEMPO_CASES: list[tuple[float, str]] = [
    (60.0, "click"),
    (90.0, "click"),
    (120.0, "click"),
    (140.0, "click"),
    (174.0, "click"),
    (60.0, "rock"),
    (90.0, "rock"),
    (120.0, "rock"),
    (140.0, "rock"),
    (174.0, "rock"),
    (174.0, "dnb"),
]


def run_realtime_tempo_benchmark() -> dict[str, Any]:
    """11 cases x 20s through FixedRingBuffer + AnalysisWorker at 66.67, 62.5, 78.1 ms scheduler periods."""
    periods_ms = (66.67, 62.5, 78.1)
    by_period: dict[str, dict[str, float]] = {}
    precomputed = [(bpm, style, _to_stereo(_synth_click_track(bpm, dur_sec=20.0, style=style, sr=SR))) for bpm, style in _TEMPO_CASES]

    for p_ms in periods_ms:
        step = int(round(SR * p_ms / 1000.0))
        a1_hits = 0
        a2_hits = 0
        for bpm, _style, stereo in precomputed:
            rb, worker = _new_realtime_worker(ring_seconds=25)
            snap = None
            for pos in range(0, stereo.shape[0], step):
                chunk = stereo[pos : pos + step]
                if chunk.shape[0] == 0:
                    break
                rb.write(chunk)
                snap = worker.analyze_latest_once()
            pred = snap.tempo.bpm if snap is not None else None
            a1, a2 = _bpm_acc(pred, bpm)
            a1_hits += int(a1)
            a2_hits += int(a2)
        n = len(precomputed)
        by_period[f"{p_ms}ms"] = {
            "acc1": round(100.0 * a1_hits / n, 2),
            "acc2": round(100.0 * a2_hits / n, 2),
        }
    return by_period


def run_offline_tempo_benchmark() -> dict[str, float]:
    """11 cases x 20s WAV through analyze_drums_stem at both 44.1kHz and 48kHz."""
    out: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="ls_bench_drums_") as td:
        td_path = Path(td)
        for sr in (48000, 44100):
            a1_hits = 0
            a2_hits = 0
            for idx, (bpm, style) in enumerate(_TEMPO_CASES):
                wav_path = td_path / f"drums_{sr}_{idx}_{int(bpm)}_{style}.wav"
                pcm = _synth_click_track(bpm, dur_sec=20.0, style=style, sr=sr)
                _write_wav_pcm16(wav_path, pcm, sr=sr)
                res = analyze_drums_stem(wav_path, max_seconds=25.0)
                a1, a2 = _bpm_acc(res.estimated_bpm, bpm)
                a1_hits += int(a1)
                a2_hits += int(a2)
            n = len(_TEMPO_CASES)
            tag = "48k" if sr == 48000 else "44k"
            out[f"acc1_{tag}"] = round(100.0 * a1_hits / n, 2)
            out[f"acc2_{tag}"] = round(100.0 * a2_hits / n, 2)
    out["acc1"] = round(0.5 * (out["acc1_48k"] + out["acc1_44k"]), 2)
    out["acc2"] = round(0.5 * (out["acc2_48k"] + out["acc2_44k"]), 2)
    return out


def _eval_rt_pitch_note(mono_055s: np.ndarray, f0: float) -> tuple[bool, float | None]:
    rb, worker = _new_realtime_worker(ring_seconds=5)
    stereo = _to_stereo(mono_055s)
    step = int(round(SR * 66.67 / 1000.0))
    snap = None
    for pos in range(0, stereo.shape[0], step):
        chunk = stereo[pos : pos + step]
        if chunk.shape[0] == 0:
            break
        rb.write(chunk)
        snap = worker.analyze_latest_once()
    true_name, _ = freq_to_note_and_cents(f0)
    if snap is not None and snap.pitch.note_name == true_name and snap.pitch.frequency_hz is not None:
        return True, abs(1200.0 * np.log2(snap.pitch.frequency_hz / f0))
    return False, None


def run_pitch_benchmark() -> dict[str, float]:
    """Real-time pitch via FixedRingBuffer + AnalysisWorker: E1-C6 pure sine & 1/k harmonics + E1-E3 weak f0."""
    dur_n = int(round(0.55 * SR))
    t = np.arange(dur_n, dtype=np.float32) / float(SR)
    sweep_midis = list(range(28, 85, 2))  # E1..C6 (29 notes)

    sine_hits = 0
    sine_errs: list[float] = []
    harm_hits = 0
    harm_errs: list[float] = []

    for m in sweep_midis:
        f0 = _midi_to_hz(m)
        sig_sine = (0.5 * np.sin(2.0 * np.pi * f0 * t)).astype(np.float32)
        ok, err = _eval_rt_pitch_note(sig_sine, f0)
        if ok and err is not None:
            sine_hits += 1
            sine_errs.append(err)

        sig_harm = sum((1.0 / k) * np.sin(2.0 * np.pi * k * f0 * t) for k in range(1, 5) if k * f0 < SR * 0.45)
        sig_harm = (sig_harm / (float(np.max(np.abs(sig_harm))) + 1e-9) * 0.5).astype(np.float32)
        ok_h, err_h = _eval_rt_pitch_note(sig_harm, f0)
        if ok_h and err_h is not None:
            harm_hits += 1
            harm_errs.append(err_h)

    weak_midis = list(range(28, 53))  # E1..E3 (25 notes)
    weak_hits = 0
    weak_errs: list[float] = []
    for m in weak_midis:
        f0 = _midi_to_hz(m)
        sig_w = (
            0.15 * np.sin(2.0 * np.pi * f0 * t)
            + 1.00 * np.sin(2.0 * np.pi * 2.0 * f0 * t)
            + 0.70 * np.sin(2.0 * np.pi * 3.0 * f0 * t)
            + 0.40 * np.sin(2.0 * np.pi * 4.0 * f0 * t)
        ).astype(np.float32)
        sig_w *= 0.5 / (float(np.max(np.abs(sig_w))) + 1e-9)
        ok_w, err_w = _eval_rt_pitch_note(sig_w, f0)
        if ok_w and err_w is not None:
            weak_hits += 1
            weak_errs.append(err_w)

    return {
        "pure_sine_acc": round(100.0 * sine_hits / len(sweep_midis), 2),
        "pure_sine_median_cents": round(float(np.median(sine_errs)) if sine_errs else 999.0, 2),
        "harmonic_acc": round(100.0 * harm_hits / len(sweep_midis), 2),
        "harmonic_median_cents": round(float(np.median(harm_errs)) if harm_errs else 999.0, 2),
        "weak_f0_acc": round(100.0 * weak_hits / len(weak_midis), 2),
        "weak_f0_median_cents": round(float(np.median(weak_errs)) if weak_errs else 999.0, 2),
    }


def run_chord_benchmark() -> dict[str, float]:
    """Real-time chord via FixedRingBuffer + AnalysisWorker (C-G-Am-F, C/E-F/A-G/B) + 24-triad 7th-mode check."""
    step = int(round(SR * 66.67 / 1000.0))

    # 1. Real-time progression: C - G - Am - F (2s each)
    prog_specs = [
        ("C", 36, [60, 64, 67]),
        ("G", 43, [67, 71, 74]),
        ("Am", 33, [57, 60, 64]),
        ("F", 41, [65, 69, 72]),
    ]
    rb, worker = _new_realtime_worker(ring_seconds=15)
    prog_hits = 0
    prog_total = 0
    for expected, bass_m, uppers in prog_specs:
        seg = _to_stereo(_synth_chord_segment(bass_m, uppers, 2.0, sr=SR))
        for pos in range(0, seg.shape[0], step):
            chunk = seg[pos : pos + step]
            if chunk.shape[0] == 0:
                break
            rb.write(chunk)
            snap = worker.analyze_latest_once()
            prog_total += 1
            if snap.chord.primary == expected:
                prog_hits += 1

    # 2. Real-time inversions: C/E - F/A - G/B (2s each)
    inv_specs = [
        (("C", "C/E"), 40, [60, 64, 67]),
        (("F", "F/A"), 45, [65, 69, 72]),
        (("G", "G/B"), 47, [67, 71, 74]),
    ]
    rb_inv, worker_inv = _new_realtime_worker(ring_seconds=15)
    inv_hits = 0
    inv_total = 0
    for accepted, bass_m, uppers in inv_specs:
        seg = _to_stereo(_synth_chord_segment(bass_m, uppers, 2.0, sr=SR, bass_gain=0.60))
        for pos in range(0, seg.shape[0], step):
            chunk = seg[pos : pos + step]
            if chunk.shape[0] == 0:
                break
            rb_inv.write(chunk)
            snap = worker_inv.analyze_latest_once()
            inv_total += 1
            if snap.chord.primary in accepted:
                inv_hits += 1

    # 3. 24-triad accuracy with include_sevenths=True (tracks A-L10 regression)
    ce = ChromaExtractor(sample_rate=SR)
    triad_with_7_hits = 0
    for root in range(12):
        r_name = PITCH_CLASSES[root]
        for is_minor in (False, True):
            expected = f"{r_name}m" if is_minor else r_name
            third = 3 if is_minor else 4
            pcm = _synth_chord_segment(36 + root, [60 + root, 60 + root + third, 60 + root + 7], 0.8)
            c12 = ce.extract_from_pcm(pcm[-16384:], record_history=False)
            est_7 = ChordDetector(include_sevenths=True).update(c12, is_silent=False)
            if est_7.primary == expected:
                triad_with_7_hits += 1

    return {
        "rt_progression_acc": round(100.0 * prog_hits / max(1, prog_total), 2),
        "rt_inversion_acc": round(100.0 * inv_hits / max(1, inv_total), 2),
        "triad_with_sevenths_on_acc": round(100.0 * triad_with_7_hits / 24.0, 2),
    }


def _synth_808_note(f0: float, dur_sec: float, sr: int) -> np.ndarray:
    n = int(round(dur_sec * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    # Classic 808: fast pitch drop on first 25ms + sustained sub fundamental + light saturation harmonics
    freq = f0 * (1.0 + 0.8 * np.exp(-t * 95.0))
    phase = 2.0 * np.pi * np.cumsum(freq) / float(sr)
    env = np.exp(-t * 2.6).astype(np.float32)
    fade_in = min(int(0.005 * sr), n // 4)
    if fade_in > 1:
        env[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    sig = (0.78 * np.sin(phase) + 0.16 * np.sin(2.0 * phase) + 0.06 * np.sin(3.0 * phase)) * env
    return sig.astype(np.float32)


def run_offline_bass_benchmark() -> dict[str, Any]:
    """Offline analyze_bass_stem: E1-C4 pure sine & 808 + 4 consecutive A1 notes at 44.1k and 48k."""
    sweep_midis = list(range(28, 61, 2))  # E1 (28) .. C4 (60), 17 notes
    note_sec = 0.45
    gap_sec = 0.08
    out: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="ls_bench_bass_") as td:
        td_path = Path(td)
        for sr in (48000, 44100):
            tag = "48k" if sr == 48000 else "44k"
            gap = np.zeros(int(round(gap_sec * sr)), dtype=np.float32)
            for timbre in ("pure_sine", "808"):
                parts: list[np.ndarray] = []
                expected_centers: list[tuple[float, str]] = []
                cursor = 0.0
                for m in sweep_midis:
                    f0 = _midi_to_hz(m)
                    name, _ = freq_to_note_and_cents(f0)
                    if timbre == "pure_sine":
                        n = int(round(note_sec * sr))
                        t = np.arange(n, dtype=np.float32) / float(sr)
                        tone = (0.6 * np.sin(2.0 * np.pi * f0 * t)).astype(np.float32)
                    else:
                        tone = _synth_808_note(f0, note_sec, sr)
                    parts.append(tone)
                    parts.append(gap)
                    expected_centers.append((cursor + note_sec * 0.5, name))
                    cursor += note_sec + gap_sec
                wav_path = td_path / f"bass_{timbre}_{tag}.wav"
                _write_wav_pcm16(wav_path, np.concatenate(parts, axis=0), sr=sr)
                res = analyze_bass_stem(wav_path, max_seconds=30.0)
                hits = 0
                for center_t, exp_name in expected_centers:
                    matched = any(ev.start_sec <= center_t <= ev.end_sec and ev.note_name == exp_name for ev in res.notes)
                    hits += int(matched)
                out[f"{timbre}_acc_{tag}"] = round(100.0 * hits / len(sweep_midis), 2)

            # 4 consecutive A1 notes
            f_a1 = _midi_to_hz(33)
            note_n = int(round(0.45 * sr))
            t_a1 = np.arange(note_n, dtype=np.float32) / float(sr)
            rep_parts = []
            for _ in range(4):
                env = np.exp(-t_a1 * 6.5).astype(np.float32)
                env[: int(0.005 * sr)] *= np.linspace(0.0, 1.0, int(0.005 * sr), dtype=np.float32)
                rep_parts.append(
                    ((0.65 * np.sin(2.0 * np.pi * f_a1 * t_a1) + 0.25 * np.sin(4.0 * np.pi * f_a1 * t_a1)) * env).astype(
                        np.float32
                    )
                )
            rep_path = td_path / f"bass_rep_a1_{tag}.wav"
            _write_wav_pcm16(rep_path, np.concatenate(rep_parts, axis=0), sr=sr)
            rep_res = analyze_bass_stem(rep_path, max_seconds=10.0)
            out[f"repeated_a1_count_{tag}"] = len(rep_res.notes)

    return out


def run_all_benchmarks() -> dict[str, Any]:
    return {
        "key": run_key_benchmark(),
        "rt_chord": run_chord_benchmark(),
        "rt_tempo": run_realtime_tempo_benchmark(),
        "offline_tempo": run_offline_tempo_benchmark(),
        "rt_pitch": run_pitch_benchmark(),
        "offline_bass": run_offline_bass_benchmark(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ListenScope A-BENCH frozen algorithm benchmark")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON only")
    args = parser.parse_args()
    results = run_all_benchmarks()
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
