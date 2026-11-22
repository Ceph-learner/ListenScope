"""CPU-only spectral peak & harmonic pitch estimator."""

from __future__ import annotations

import numpy as np

from core.models import PitchEstimate

from .chroma import PITCH_CLASSES


def freq_to_note_and_cents(freq_hz: float) -> tuple[str, float]:
    if not np.isfinite(freq_hz) or freq_hz <= 0.0:
        return "-", 0.0
    midi = 69.0 + 12.0 * np.log2(freq_hz / 440.0)
    if not np.isfinite(midi):
        return "-", 0.0
    nearest_raw = int(round(midi))
    nearest = max(0, min(127, nearest_raw))
    cents = float((midi - nearest_raw) * 100.0)
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
        if is_silent or fft_mag.size == 0 or not np.all(np.isfinite(fft_mag)):
            return PitchEstimate(frequency_hz=None, note_name="-", cents_offset=0.0, confidence=0.0)

        min_bin = max(1, int(round(40.0 / self._bin_hz)))
        max_bin = min(fft_mag.shape[0] - 2, int(round(1600.0 / self._bin_hz)))
        if max_bin <= min_bin:
            return PitchEstimate(frequency_hz=None, note_name="-", cents_offset=0.0, confidence=0.0)

        # Harmonic sum across 1st, 2nd, and 3rd harmonics to prefer f0 over overtones
        # Keep one real neighbor on each side for interpolation. Only search the interior.
        cand_bins = np.arange(min_bin - 1, max_bin + 2)
        h1 = fft_mag[cand_bins]
        h2_idx = np.minimum(cand_bins * 2, fft_mag.shape[0] - 1)
        h3_idx = np.minimum(cand_bins * 3, fft_mag.shape[0] - 1)
        score = h1 + 0.5 * fft_mag[h2_idx] + 0.25 * fft_mag[h3_idx]

        candidates = score[1:-1]
        rel_idx = int(np.argmax(candidates)) + 1
        peak_bin = min_bin + rel_idx - 1
        peak_val = float(score[rel_idx])
        median_val = float(np.median(candidates)) + 1e-9
        prominence = min(1.0, max(0.0, (peak_val / median_val - 1.0) / 15.0))

        if prominence < 0.15:
            return PitchEstimate(frequency_hz=None, note_name="Unknown", cents_offset=0.0, confidence=prominence)

        # Locate local fundamental peak and interpolate log-magnitude around it
        lo = max(0, peak_bin - 1)
        hi = min(fft_mag.shape[0], peak_bin + 2)
        k = lo + int(np.argmax(fft_mag[lo:hi]))
        if 1 <= k < fft_mag.shape[0] - 1:
            a, b, c = np.log(np.maximum(fft_mag[k - 1 : k + 2], 1e-12))
            denom = float(a - 2.0 * b + c)
            raw_delta = 0.5 * float(a - c) / denom if abs(denom) > 1e-9 else 0.0
            delta = max(-0.5, min(0.5, raw_delta))
        else:
            delta = 0.0
        freq = float((k + delta) * self._bin_hz)
        if not np.isfinite(freq) or freq <= 0.0:
            return PitchEstimate(frequency_hz=None, note_name="-", cents_offset=0.0, confidence=0.0)

        note_name, cents = freq_to_note_and_cents(freq)
        return PitchEstimate(
            frequency_hz=round(freq, 2),
            note_name=note_name,
            cents_offset=round(cents, 1),
            confidence=round(prominence, 3),
        )
