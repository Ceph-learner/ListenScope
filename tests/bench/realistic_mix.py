"""W11 realistic_mix tempo benchmark (added by Verifier Neon; frozen algo_benchmark.py untouched).

Synthesizes realistic compressed mixes (drums + bass + chord pad + vocal-like formant melody +
noise floor + master limiter) at 70 / 95 / 120 / 128 / 150 BPM, plus non-rhythmic negative
controls (steady sine and pure chord pad), and evaluates ListenScope's real-time TempoEstimator
pipeline (FixedRingBuffer + AnalysisWorker) for BPM Acc1/Acc2 and onset-envelope peakiness.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from analysis.worker import AnalysisWorker
from audio.ring_buffer import FixedRingBuffer
from core.config import AnalysisConfig, AudioConfig

SR = 48000
REALISTIC_BPMS: tuple[float, ...] = (70.0, 95.0, 120.0, 128.0, 150.0)
REALISTIC_STYLES: tuple[str, ...] = ("pop_compressed", "dense_loud", "streaming_wash")


def _soft_limit(x: np.ndarray, drive: float = 2.4) -> np.ndarray:
    return (np.tanh(x * drive) / np.tanh(drive)).astype(np.float32)


def _rms_compress(x: np.ndarray, *, sr: int = SR, threshold: float = 0.22, ratio: float = 4.0) -> np.ndarray:
    """Simple deterministic feed-forward compressor to simulate mastered streaming loudness."""
    win = max(1, int(0.025 * sr))
    sq = np.square(x.astype(np.float64))
    kernel = np.ones(win, dtype=np.float64) / float(win)
    env = np.sqrt(np.convolve(sq, kernel, mode="same") + 1e-12)
    gain = np.ones_like(env)
    over = env > threshold
    gain[over] = (threshold + (env[over] - threshold) / ratio) / env[over]
    return (x * gain).astype(np.float32)


def synth_realistic_mix(
    bpm: float,
    *,
    style: str = "pop_compressed",
    dur_sec: float = 20.0,
    sr: int = SR,
    seed: int = 2026,
) -> np.ndarray:
    """Synthesize a mastered pop/electronic mix with compressed drums, bass, pad, vocal formants, and noise."""
    n = int(round(dur_sec * sr))
    t = np.arange(n, dtype=np.float64) / float(sr)
    style_off = {"pop_compressed": 0, "dense_loud": 97, "streaming_wash": 211}.get(style, 0)
    rng = np.random.default_rng(seed + int(bpm * 10) + style_off)
    beat_sec = 60.0 / float(bpm)

    # 1. Compressed drums (kick + snare + continuous 8th/16th hi-hats)
    drums = np.zeros(n, dtype=np.float64)
    kick_len = int(0.14 * sr)
    tk = np.arange(kick_len, dtype=np.float64) / float(sr)
    kick_f = 52.0 + 115.0 * np.exp(-tk * 38.0)
    kick = np.sin(2.0 * np.pi * np.cumsum(kick_f) / float(sr)) * np.exp(-tk * 16.0)

    snare_len = int(0.12 * sr)
    ts = np.arange(snare_len, dtype=np.float64) / float(sr)
    snare = (
        0.55 * np.sin(2.0 * np.pi * 190.0 * ts) * np.exp(-ts * 24.0)
        + 0.45 * rng.standard_normal(snare_len) * np.exp(-ts * 28.0)
    )

    hat_len = int(0.045 * sr)
    th = np.arange(hat_len, dtype=np.float64) / float(sr)
    hat_noise = rng.standard_normal(hat_len)
    hat_hp = np.diff(hat_noise, prepend=0.0)
    hat = hat_hp * np.exp(-th * 65.0)

    def _mix_in(buf: np.ndarray, start_sec: float, sample: np.ndarray, gain: float) -> None:
        i0 = int(round(start_sec * sr))
        if i0 >= n:
            return
        i1 = min(n, i0 + sample.shape[0])
        buf[i0:i1] += gain * sample[: i1 - i0]

    subdiv = 4 if style in ("dense_loud", "streaming_wash") else 2
    step_sec = beat_sec / float(subdiv)
    k = 0
    while k * step_sec < dur_sec:
        pos = k * step_sec
        beat_idx = k // subdiv
        sub_idx = k % subdiv
        bar_beat = beat_idx % 4
        if sub_idx == 0:
            if style in ("dense_loud", "streaming_wash") or bar_beat in (0, 2):
                _mix_in(drums, pos, kick, 0.72)
            if bar_beat in (1, 3):
                _mix_in(drums, pos, snare, 0.58)
        elif sub_idx == subdiv // 2 and bar_beat == 2 and style == "pop_compressed":
            _mix_in(drums, pos, kick, 0.45)
        hat_gain = 0.16 if sub_idx == 0 else (0.11 if sub_idx == subdiv // 2 else 0.08)
        _mix_in(drums, pos, hat, hat_gain)
        k += 1
    drums = _rms_compress(drums.astype(np.float32), sr=sr, threshold=0.20, ratio=5.0).astype(np.float64)

    # 2. Sustained bass line (changes root every bar, continuous low-end energy)
    bass_freqs = (82.41, 65.41, 98.00, 73.42)  # E2, C2, G2, D2
    bar_idx = (t / (4.0 * beat_sec)).astype(np.int64) % len(bass_freqs)
    f_bass = np.array([bass_freqs[i] for i in bar_idx], dtype=np.float64)
    ph_bass = 2.0 * np.pi * np.cumsum(f_bass) / float(sr)
    bass = 0.28 * (0.65 * np.sin(ph_bass) + 0.25 * np.sin(2.0 * ph_bass) + 0.10 * np.sin(3.0 * ph_bass))

    # 3. Warm chord pad (continuous dense harmonic bed)
    pad = np.zeros(n, dtype=np.float64)
    for f_pad in (164.81, 196.00, 246.94, 329.63, 392.00):
        detune = 1.0 + 0.002 * np.sin(2.0 * np.pi * 0.35 * t)
        ph = 2.0 * np.pi * np.cumsum(f_pad * detune) / float(sr)
        pad += 0.065 * (0.7 * np.sin(ph) + 0.22 * np.sin(2.0 * ph) + 0.08 * np.sin(3.0 * ph))
    if style == "dense_loud":
        pad *= 1.35
    elif style == "streaming_wash":
        pad *= 1.65

    # 4. Vocal-like formant melody (continuous sustained harmonics + vibrato)
    mel_freqs = (329.63, 392.00, 440.00, 392.00, 329.63, 293.66, 329.63, 246.94)
    mel_idx = (t / (2.0 * beat_sec)).astype(np.int64) % len(mel_freqs)
    f_mel = np.array([mel_freqs[i] for i in mel_idx], dtype=np.float64) * (1.0 + 0.006 * np.sin(2.0 * np.pi * 5.4 * t))
    ph_mel = 2.0 * np.pi * np.cumsum(f_mel) / float(sr)
    vocal = 0.16 * (
        0.55 * np.sin(ph_mel)
        + 0.30 * np.sin(2.0 * ph_mel)
        + 0.22 * np.sin(3.0 * ph_mel)
        + 0.12 * np.sin(5.0 * ph_mel)
    )

    # 5. Noise floor / broadband reverb wash + master compression & limiter
    if style == "streaming_wash":
        # Continuous broadband shimmer/reverb bed typical of loud streaming pop masters
        raw_n = rng.standard_normal(n)
        wash = 0.095 * (raw_n - np.roll(raw_n, 1) * 0.35)
        mix = 0.38 * drums + 1.15 * bass + pad + 1.35 * vocal + wash
        mix = _rms_compress(mix.astype(np.float32), sr=sr, threshold=0.16, ratio=8.0)
        mix = _soft_limit(mix, drive=3.6)
    else:
        noise = 0.0055 * rng.standard_normal(n)
        mix = (0.62 if style == "pop_compressed" else 0.55) * drums + bass + pad + vocal + noise
        mix = _rms_compress(mix.astype(np.float32), sr=sr, threshold=0.25, ratio=4.5)
        mix = _soft_limit(mix, drive=2.6 if style == "dense_loud" else 2.1)
    return (0.75 * mix).astype(np.float32)


def synth_steady_sine(*, freq_hz: float = 440.0, dur_sec: float = 12.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(round(dur_sec * sr)), dtype=np.float32) / float(sr)
    return (0.35 * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def synth_pure_chord_pad(*, dur_sec: float = 12.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(round(dur_sec * sr)), dtype=np.float64) / float(sr)
    sig = np.zeros_like(t)
    for f in (261.63, 329.63, 392.00, 523.25):
        sig += 0.12 * (0.75 * np.sin(2.0 * np.pi * f * t) + 0.25 * np.sin(4.0 * np.pi * f * t))
    return sig.astype(np.float32)


def _bpm_acc(pred: float | None, target: float) -> tuple[bool, bool]:
    if pred is None or pred <= 0:
        return False, False
    acc1 = abs(pred - target) / target <= 0.04
    acc2 = any(abs(pred - target * mult) / (target * mult) <= 0.04 for mult in (0.5, 1.0, 2.0))
    return acc1, acc2


def _eval_realtime_pcm(mono: np.ndarray, *, sr: int = SR, period_ms: float = 66.67) -> dict[str, Any]:
    acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=25)
    rb = FixedRingBuffer(acfg)
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    stereo = np.stack([mono, mono], axis=1).astype(np.float32)
    step = int(round(sr * period_ms / 1000.0))
    snap = None
    for pos in range(0, stereo.shape[0], step):
        chunk = stereo[pos : pos + step]
        if chunk.shape[0] == 0:
            break
        rb.write(chunk)
        snap = worker.analyze_latest_once()

    env = np.asarray(worker.tempo._onsets, dtype=np.float32)
    peakiness = float(np.percentile(env, 95)) / (float(np.median(env)) + 1e-9) if env.size else 0.0
    return {
        "estimated_bpm": snap.tempo.bpm if snap is not None else None,
        "stability": snap.tempo.stability if snap is not None else "Unknown",
        "acf_peak": round(float(snap.tempo.confidence_score), 4) if snap is not None else 0.0,
        "peakiness": round(peakiness, 4),
    }


def run_realistic_mix_benchmark() -> dict[str, Any]:
    """Run all 10 realistic_mix cases (5 BPMs x 2 styles) + 2 non-rhythmic negative controls."""
    cases: list[dict[str, Any]] = []
    peakiness_vals: list[float] = []
    a1_hits = 0
    a2_hits = 0

    for bpm in REALISTIC_BPMS:
        for style in REALISTIC_STYLES:
            mono = synth_realistic_mix(bpm, style=style, dur_sec=20.0, sr=SR)
            res = _eval_realtime_pcm(mono, sr=SR)
            a1, a2 = _bpm_acc(res["estimated_bpm"], bpm)
            a1_hits += int(a1)
            a2_hits += int(a2)
            peakiness_vals.append(float(res["peakiness"]))
            cases.append(
                {
                    "bpm": bpm,
                    "style": style,
                    **res,
                    "acc1": a1,
                    "acc2": a2,
                }
            )

    neg_controls: list[dict[str, Any]] = []
    for name, mono in (
        ("steady_sine_440hz", synth_steady_sine()),
        ("pure_chord_pad", synth_pure_chord_pad()),
    ):
        res = _eval_realtime_pcm(mono, sr=SR)
        neg_controls.append({"name": name, **res, "returned_none": res["estimated_bpm"] is None})

    n = len(cases)
    neg_ok = sum(1 for c in neg_controls if c["returned_none"])
    return {
        "summary": {
            "total_cases": n,
            "acc1_pct": round(100.0 * a1_hits / max(1, n), 2),
            "acc2_pct": round(100.0 * a2_hits / max(1, n), 2),
            "peakiness_p50": round(float(np.percentile(peakiness_vals, 50)), 4),
            "peakiness_p95": round(float(np.percentile(peakiness_vals, 95)), 4),
            "peakiness_min": round(float(np.min(peakiness_vals)), 4),
            "peakiness_max": round(float(np.max(peakiness_vals)), 4),
            "neg_controls_none_pct": round(100.0 * neg_ok / max(1, len(neg_controls)), 2),
        },
        "cases": cases,
        "negative_controls": neg_controls,
    }


def main() -> None:
    report = run_realistic_mix_benchmark()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
