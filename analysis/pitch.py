"""CPU-only spectral peak & harmonic pitch estimator."""

from __future__ import annotations

import numpy as np

from core.models import PitchEstimate

from .chroma import PITCH_CLASSES


def freq_to_note_and_cents(freq_hz: float) -> tuple[str, float]:
    midi = 69.0 + 12.0 * np.log2(freq_hz / 440.0)
    nearest = int(round(midi))
    cents = float((midi - nearest) * 100.0)
    note_name = f"{PITCH_CLASSES[nearest % 12]}{(nearest // 12) - 1}"
    return note_name, cents


class PitchEstimator:
    """Fast harmonic-product / spectral peak fundamental frequency estimator (CPU-only)."""

    def __init__(self, sample_rate: int = 48000, fft_size: int = 4096) -> None:
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self._freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
        self._bin_hz = sample_rate / float(fft_size)

    def estimate_from_magnitude(self, fft_mag: np.ndarray, *, is_silent: bool) -> PitchEstimate:
        if is_silent or fft_mag.size == 0:
            return PitchEstimate(frequency_hz=None, note_name="-", cents_offset=0.0, confidence=0.0)

        min_bin = max(1, int(round(40.0 / self._bin_hz)))
        max_bin = min(fft_mag.shape[0] - 2, int(round(1600.0 / self._bin_hz)))
        if max_bin <= min_bin:
            return PitchEstimate(frequency_hz=None, note_name="-", cents_offset=0.0, confidence=0.0)

        # Harmonic sum across 1st, 2nd, and 3rd harmonics to prefer f0 over overtones
        cand_bins = np.arange(min_bin, max_bin + 1)
        h1 = fft_mag[cand_bins]
        h2_idx = np.minimum(cand_bins * 2, fft_mag.shape[0] - 1)
        h3_idx = np.minimum(cand_bins * 3, fft_mag.shape[0] - 1)
        score = h1 + 0.5 * fft_mag[h2_idx] + 0.25 * fft_mag[h3_idx]

        rel_idx = int(np.argmax(score))
        peak_bin = min_bin + rel_idx
        peak_val = float(score[rel_idx])
        median_val = float(np.median(score)) + 1e-9
        prominence = min(1.0, max(0.0, (peak_val / median_val - 1.0) / 15.0))

        if prominence < 0.15:
            return PitchEstimate(frequency_hz=None, note_name="Unknown", cents_offset=0.0, confidence=prominence)

        # Parabolic interpolation around peak bin
        alpha = float(score[rel_idx - 1]) if rel_idx > 0 else peak_val
        beta = peak_val
        gamma = float(score[rel_idx + 1]) if rel_idx + 1 < score.shape[0] else peak_val
        denom = alpha - 2.0 * beta + gamma
        delta = 0.5 * (alpha - gamma) / denom if abs(denom) > 1e-9 else 0.0
        freq = float((peak_bin + delta) * self._bin_hz)

        note_name, cents = freq_to_note_and_cents(freq)
        return PitchEstimate(
            frequency_hz=round(freq, 2),
            note_name=note_name,
            cents_offset=round(cents, 1),
            confidence=round(prominence, 3),
        )
