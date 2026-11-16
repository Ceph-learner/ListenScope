"""CPU-only real-time onset-autocorrelation BPM estimator with bounded history."""

from __future__ import annotations

from collections import deque
import threading
from typing import Optional

import numpy as np

from core.config import AnalysisConfig
from core.models import TempoEstimate


class TempoEstimator:
    """Estimates BPM from bounded spectral-flux onset envelope."""

    def __init__(
        self,
        config: Optional[AnalysisConfig] = None,
        *,
        min_bpm: float = 55.0,
        max_bpm: float = 190.0,
    ) -> None:
        self.config = config or AnalysisConfig()
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self._rate_hz = self.config.analysis_rate_hz
        max_frames = max(16, int(self.config.tempo_window_seconds * self._rate_hz))

        self._lock = threading.Lock()
        self._onsets: deque[float] = deque(maxlen=max_frames)
        self._prev_log_spec: Optional[np.ndarray] = None
        self._previous_silence = False

    def reset(self) -> None:
        with self._lock:
            self._onsets.clear()
            self._prev_log_spec = None
            self._previous_silence = False

    def update(self, log_spectrum_db: np.ndarray, *, is_silent: bool) -> TempoEstimate:
        with self._lock:
            if is_silent or log_spectrum_db.size == 0 or not np.all(np.isfinite(log_spectrum_db)):
                self._onsets.append(0.0)
                self._prev_log_spec = None
                self._previous_silence = is_silent
            else:
                # Positive spectral flux across log bands (clipped dB avoids 10**x overflow)
                clipped_db = np.clip(log_spectrum_db, -120.0, 20.0)
                mag_like = np.power(10.0, clipped_db / 20.0)
                if self._previous_silence:
                    # A beat can follow a genuinely silent frame. Compare to the dB floor.
                    flux = float(np.sum(mag_like - 1e-6))
                elif self._prev_log_spec is None or self._prev_log_spec.shape != mag_like.shape:
                    flux = 0.0
                else:
                    diff = mag_like - self._prev_log_spec
                    flux = float(np.sum(np.maximum(0.0, diff)))
                self._prev_log_spec = mag_like.astype(np.float32, copy=True)
                self._previous_silence = False
                self._onsets.append(flux)

            env = np.asarray(self._onsets, dtype=np.float32)

        min_samples = max(24, int(4.0 * self._rate_hz))
        if env.shape[0] < min_samples or float(np.max(env)) < 1e-4:
            return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)

        # Light temporal smoothing bridges fractional-frame beat intervals cleanly for ACF
        if env.size >= 3:
            env = np.convolve(env, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")

        # Normalize and subtract local mean
        centered = env - float(np.mean(env))
        energy = float(np.dot(centered, centered))
        if energy < 1e-6:
            return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)

        acf = np.correlate(centered, centered, mode="full")[centered.size - 1 :]
        acf = acf / max(energy, 1e-9)

        min_lag = max(2, int(round((60.0 / self.max_bpm) * self._rate_hz)))
        max_lag = min(acf.shape[0] - 1, int(round((60.0 / self.min_bpm) * self._rate_hz)))
        if max_lag <= min_lag:
            return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)

        lags = np.arange(min_lag, max_lag + 1, dtype=np.float32)
        bpms = 60.0 * self._rate_hz / lags
        # Log-normal human tempo prior centered around 115 BPM to limit octave lock (e.g. 60 vs 120 BPM)
        prior = np.exp(-0.5 * (np.log2(bpms / 115.0) / 0.55) ** 2).astype(np.float32)
        weighted = acf[min_lag : max_lag + 1] * prior
        best_rel = int(np.argmax(weighted))
        best_lag = min_lag + best_rel
        raw_acf = float(acf[best_lag])

        if raw_acf < 0.12:
            return TempoEstimate(bpm=None, stability="Unknown", confidence_score=raw_acf)

        # Parabolic refinement around best lag (clamped strictly to +/- 0.5 bin)
        refined_lag = float(best_lag)
        if 0 < best_rel < weighted.shape[0] - 1:
            y0, y1, y2 = float(weighted[best_rel - 1]), float(weighted[best_rel]), float(weighted[best_rel + 1])
            denom = y0 - 2.0 * y1 + y2
            if abs(denom) > 1e-9:
                delta = max(-0.5, min(0.5, 0.5 * (y0 - y2) / denom))
                refined_lag += delta

        bpm = round(60.0 * self._rate_hz / max(1.0, refined_lag), 1)
        stability = "High" if raw_acf >= 0.35 else ("Medium" if raw_acf >= 0.2 else "Low")
        return TempoEstimate(bpm=bpm, stability=stability, confidence_score=raw_acf)
