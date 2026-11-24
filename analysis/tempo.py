"""CPU-only real-time onset-autocorrelation BPM estimator with bounded history."""

from __future__ import annotations

from collections import deque
import logging
import threading
import time
from typing import Optional

import numpy as np

from core.config import AnalysisConfig
from core.models import TempoEstimate

logger = logging.getLogger(__name__)


class TempoEstimator:
    """Estimates BPM from bounded sample-clock spectral-flux onset envelope."""

    def __init__(
        self,
        config: Optional[AnalysisConfig] = None,
        *,
        sample_rate: int = 48000,
        hop_frames: int = 512,
        min_bpm: float = 55.0,
        max_bpm: float = 190.0,
    ) -> None:
        self.config = config or AnalysisConfig()
        self.sample_rate = max(8000, int(sample_rate))
        self.hop_frames = max(64, int(hop_frames))
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self._rate_hz = float(self.sample_rate) / float(self.hop_frames)
        max_frames = max(16, int(self.config.tempo_window_seconds * self._rate_hz))

        self._lock = threading.Lock()
        self._onsets: deque[float] = deque(maxlen=max_frames)
        self._prev_log_spec: Optional[np.ndarray] = None
        self._previous_silence = False
        self._frames_since_est = 0
        self._est_interval_frames = max(1, int(round(0.5 * self._rate_hz)))
        self._last_debug_log_ts: float = 0.0
        self._cached_estimate = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)

    def reset(self) -> None:
        with self._lock:
            self._onsets.clear()
            self._prev_log_spec = None
            self._previous_silence = False
            self._frames_since_est = 0
            self._cached_estimate = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)

    def push_frame(self, log_spectrum_db: np.ndarray, *, is_silent: bool = False) -> None:
        with self._lock:
            if is_silent or log_spectrum_db.size == 0 or not np.all(np.isfinite(log_spectrum_db)):
                self._onsets.append(0.0)
                self._prev_log_spec = None
                self._previous_silence = is_silent
            else:
                clipped_db = np.clip(log_spectrum_db, -120.0, 20.0)
                mag_like = np.power(10.0, clipped_db / 20.0)
                if self._previous_silence:
                    flux = float(np.sum(mag_like - 1e-6))
                elif self._prev_log_spec is None or self._prev_log_spec.shape != mag_like.shape:
                    flux = 0.0
                else:
                    diff = mag_like - self._prev_log_spec
                    flux = float(np.sum(np.maximum(0.0, diff)))
                self._prev_log_spec = mag_like.astype(np.float32, copy=True)
                self._previous_silence = False
                self._onsets.append(flux)
            self._frames_since_est += 1

    def estimate(self) -> TempoEstimate:
        with self._lock:
            env = np.asarray(self._onsets, dtype=np.float32)

        min_samples = max(24, int(4.0 * self._rate_hz))
        if env.shape[0] < min_samples or float(np.max(env)) < 1e-4 or float(np.std(env)) < 1e-3:
            est = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)
            with self._lock:
                self._cached_estimate = est
                self._frames_since_est = 0
            return est
        peakiness = float(np.percentile(env, 95)) / (float(np.median(env)) + 1e-9)
        if peakiness < 1.8:
            est = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)
            with self._lock:
                self._cached_estimate = est
                self._frames_since_est = 0
            return est

        if env.size >= 3:
            env = np.convolve(env, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")

        centered = env - float(np.mean(env))
        energy = float(np.dot(centered, centered))
        if energy < 1e-6:
            est = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)
            with self._lock:
                self._cached_estimate = est
                self._frames_since_est = 0
            return est

        n_fft = 1 << (2 * centered.size - 1).bit_length()
        spec = np.fft.rfft(centered, n=n_fft)
        acf = np.fft.irfft(np.square(np.abs(spec)), n=n_fft)[: centered.size]
        acf = acf / max(energy, 1e-9)

        min_lag = max(2, int(round((60.0 / self.max_bpm) * self._rate_hz)))
        max_lag = min(acf.shape[0] - 1, int(round((60.0 / self.min_bpm) * self._rate_hz)))
        if max_lag <= min_lag:
            est = TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0, alt_bpm=None)
            with self._lock:
                self._cached_estimate = est
                self._frames_since_est = 0
            return est

        lags = np.arange(min_lag, max_lag + 1, dtype=np.float32)
        bpms = 60.0 * self._rate_hz / lags
        prior = np.maximum(
            np.exp(-0.5 * (np.log2(bpms / 100.0) / 0.45) ** 2),
            0.8 * np.exp(-0.5 * (np.log2(bpms / 170.0) / 0.15) ** 2),
        ).astype(np.float32)
        acf_slice = acf[min_lag : max_lag + 1]
        weighted = acf_slice * prior
        best_rel = int(np.argmax(weighted))
        best_lag = min_lag + best_rel
        raw_acf = float(acf[best_lag])
        acf_prominence = raw_acf - float(np.median(acf_slice))

        if raw_acf < 0.12 or acf_prominence < 0.08:
            est = TempoEstimate(bpm=None, stability="Unknown", confidence_score=raw_acf, alt_bpm=None)
            with self._lock:
                self._cached_estimate = est
                self._frames_since_est = 0
            return est

        # Disambiguate half-time lock (e.g. 140 BPM rock -> 70 BPM, 174 BPM -> 87 BPM) when half-lag ACF is strong
        cand_bpm = 60.0 * self._rate_hz / max(1, best_lag)
        if cand_bpm < 95.0:
            half_lag = int(round(best_lag * 0.5))
            if min_lag <= half_lag <= max_lag:
                lo_h = max(min_lag, half_lag - 1)
                hi_h = min(max_lag, half_lag + 1)
                sub_rel = lo_h + int(np.argmax(acf[lo_h : hi_h + 1]))
                sub_acf = float(acf[sub_rel])
                if (cand_bpm < 68.0 and sub_acf >= 0.06) or (sub_acf >= max(0.12, 0.35 * raw_acf)):
                    best_lag = sub_rel
                    best_rel = best_lag - min_lag
                    raw_acf = float(acf[best_lag])

        refined_lag = float(best_lag)
        if 0 < best_rel < weighted.shape[0] - 1:
            y0, y1, y2 = float(weighted[best_rel - 1]), float(weighted[best_rel]), float(weighted[best_rel + 1])
            denom = y0 - 2.0 * y1 + y2
            if abs(denom) > 1e-9:
                delta = max(-0.5, min(0.5, 0.5 * (y0 - y2) / denom))
                refined_lag += delta

        bpm = round(60.0 * self._rate_hz / max(1.0, refined_lag), 1)
        alt_bpm: Optional[float] = None
        if bpm * 2.0 <= self.max_bpm:
            alt_bpm = round(bpm * 2.0, 1)
        elif bpm * 0.5 >= self.min_bpm:
            alt_bpm = round(bpm * 0.5, 1)

        now = time.monotonic()
        if now - self._last_debug_log_ts >= 5.0:
            self._last_debug_log_ts = now
            logger.debug(
                "TempoEstimator: peakiness=%.2f acf_peak=%.3f prominence=%.3f bpm=%.1f alt_bpm=%s",
                peakiness,
                raw_acf,
                acf_prominence,
                bpm,
                alt_bpm,
            )

        stability = "High" if raw_acf >= 0.35 else ("Medium" if raw_acf >= 0.2 else "Low")
        est = TempoEstimate(bpm=bpm, stability=stability, confidence_score=raw_acf, alt_bpm=alt_bpm)
        with self._lock:
            self._cached_estimate = est
            self._frames_since_est = 0
        return est

    def maybe_estimate(self) -> TempoEstimate:
        with self._lock:
            due = self._frames_since_est >= self._est_interval_frames or self._cached_estimate.bpm is None
            cached = self._cached_estimate
        if due:
            return self.estimate()
        return cached

    def update(self, log_spectrum_db: np.ndarray, *, is_silent: bool) -> TempoEstimate:
        self.push_frame(log_spectrum_db, is_silent=is_silent)
        return self.maybe_estimate()
