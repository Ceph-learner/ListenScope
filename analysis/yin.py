"""FFT-accelerated YIN (CMNDF) fundamental frequency estimator."""

from __future__ import annotations

from typing import Optional

import numpy as np


def yin_frame_f0(
    frame: np.ndarray,
    mag: Optional[np.ndarray] = None,
    *,
    sample_rate: int = 48000,
    bin_hz: Optional[float] = None,
    min_hz: float = 28.0,
    max_hz: float = 350.0,
) -> tuple[float, float]:
    """Estimate fundamental frequency using FFT-accelerated YIN (CMNDF) + octave-up guard."""
    n = int(frame.shape[0])
    w = n // 2
    tau_min = max(2, int(round(sample_rate / float(max_hz))))
    tau_max = min(w - 2, int(round(sample_rate / float(min_hz))))
    if tau_max <= tau_min + 2:
        return 0.0, 0.0

    xf = frame.astype(np.float64)
    xf = xf - float(np.mean(xf))
    e0 = float(np.dot(xf[:w], xf[:w]))
    if e0 <= 1e-12:
        return 0.0, 0.0

    fft_n = n * 2
    acf = np.fft.irfft(np.conj(np.fft.rfft(xf[:w], n=fft_n)) * np.fft.rfft(xf, n=fft_n), n=fft_n)
    cs = np.empty(n + 1, dtype=np.float64)
    cs[0] = 0.0
    np.cumsum(xf * xf, out=cs[1:])

    e_tau = cs[w : w + tau_max + 1] - cs[: tau_max + 1]
    diff = np.maximum(0.0, e0 + e_tau - 2.0 * acf[: tau_max + 1])

    cmndf = np.ones(tau_max + 1, dtype=np.float64)
    running = np.cumsum(diff[1:])
    taus = np.arange(1, tau_max + 1, dtype=np.float64)
    valid = running > 1e-12
    cmndf[1:][valid] = diff[1:][valid] * taus[valid] / running[valid]

    thresh = 0.18
    tau = -1
    idx = tau_min
    while idx < tau_max:
        if cmndf[idx] < thresh:
            while idx + 1 < tau_max and cmndf[idx + 1] < cmndf[idx]:
                idx += 1
            tau = idx
            break
        idx += 1

    if tau < 0:
        rel = int(np.argmin(cmndf[tau_min : tau_max + 1]))
        tau = tau_min + rel
        if cmndf[tau] > 0.42:
            return 0.0, 0.0

    # Guard against octave-up lock on overtone-heavy notes where 2nd harmonic momentarily dips <0.18
    cand2 = tau * 2
    if cand2 + 3 <= tau_max:
        if mag is None:
            win = np.hanning(n).astype(np.float32)
            mag = np.abs(np.fft.rfft(frame.astype(np.float32, copy=False) * win)).astype(np.float32)
        eff_bin_hz = float(bin_hz) if bin_hz is not None else float(sample_rate) / float(max(1, n))
        win2 = cmndf[cand2 - 3 : cand2 + 4]
        local_off = int(np.argmin(win2)) - 3
        c2 = cand2 + local_off
        if cmndf[c2] < 0.08 and cmndf[c2] < cmndf[tau] * 0.65:
            sub_bin = max(1, min(mag.shape[0] - 1, int(round((sample_rate / float(c2)) / eff_bin_hz))))
            spec_med = float(np.median(mag[1 : min(mag.shape[0], int(round(max_hz / eff_bin_hz)) + 2)])) + 1e-9
            lo_b = max(1, sub_bin - 1)
            hi_b = min(mag.shape[0], sub_bin + 2)
            if float(np.max(mag[lo_b:hi_b])) > max(1.8 * spec_med, 0.1 * float(np.max(mag))):
                tau = c2

    if tau_min < tau < tau_max:
        alpha = float(cmndf[tau - 1])
        beta = float(cmndf[tau])
        gamma = float(cmndf[tau + 1])
        denom = alpha - 2.0 * beta + gamma
        delta = max(-0.5, min(0.5, 0.5 * (alpha - gamma) / denom)) if abs(denom) > 1e-12 else 0.0
        tau_est = float(tau) + delta
    else:
        tau_est = float(tau)

    if tau_est <= 0.0:
        return 0.0, 0.0
    freq = float(sample_rate) / tau_est
    conf = min(1.0, max(0.0, 1.0 - float(cmndf[tau])))
    if not np.isfinite(freq) or freq < min_hz - 1.0 or freq > max_hz + 5.0 or conf < 0.50:
        return 0.0, 0.0
    return freq, conf
