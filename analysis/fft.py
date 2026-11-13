"""CPU-only waveform envelope, FFT power spectrum, and log-frequency spectrogram with bounded history."""

from __future__ import annotations

from collections import deque
import threading
from typing import Optional

import numpy as np

from core.config import AnalysisConfig


class SpectrumAnalyzer:
    """Computes real-time FFT / log-frequency spectrum with fixed bounded history."""

    def __init__(self, sample_rate: int = 48000, config: Optional[AnalysisConfig] = None) -> None:
        self.sample_rate = sample_rate
        self.config = config or AnalysisConfig()
        self.fft_size = self.config.fft_size
        self._window = np.hanning(self.fft_size).astype(np.float32)
        self._window_norm = float(np.sum(self._window)) or 1.0
        self._freqs = np.fft.rfftfreq(self.fft_size, d=1.0 / self.sample_rate).astype(np.float32)

        # Precompute triangular log-frequency filterbank matrix (log_bins x rfft_bins)
        self._log_freqs = np.geomspace(
            self.config.min_freq_hz,
            min(self.config.max_freq_hz, self.sample_rate * 0.48),
            num=self.config.log_freq_bins,
        ).astype(np.float32)
        self._log_fb = self._build_log_filterbank()

        max_hist_frames = max(1, int(self.config.spectrum_history_seconds * self.config.analysis_rate_hz))
        self._history_lock = threading.Lock()
        self._log_history: deque[np.ndarray] = deque(maxlen=max_hist_frames)

    def _build_log_filterbank(self) -> np.ndarray:
        n_bins = self._freqs.shape[0]
        n_log = self._log_freqs.shape[0]
        fb = np.zeros((n_log, n_bins), dtype=np.float32)
        edges = np.geomspace(
            self._log_freqs[0] * 0.94,
            min(self._log_freqs[-1] * 1.06, self.sample_rate * 0.49),
            num=n_log + 2,
        )
        for i in range(n_log):
            left, center, right = edges[i], edges[i + 1], edges[i + 2]
            up = (self._freqs - left) / max(1e-6, center - left)
            down = (right - self._freqs) / max(1e-6, right - center)
            tri = np.maximum(0.0, np.minimum(up, down))
            s = float(np.sum(tri))
            if s > 0.0:
                fb[i] = tri / s
            else:
                nearest = int(np.argmin(np.abs(self._freqs - center)))
                fb[i, nearest] = 1.0
        return fb

    @property
    def fft_freqs(self) -> np.ndarray:
        return self._freqs

    @property
    def log_freqs(self) -> np.ndarray:
        return self._log_freqs

    @property
    def history_maxlen(self) -> int:
        return self._log_history.maxlen or 0

    def compute_waveform_envelope(self, mono: np.ndarray, num_points: Optional[int] = None) -> tuple[np.ndarray, np.ndarray]:
        pts = num_points or self.config.waveform_display_points
        if mono.size == 0:
            zeros = np.zeros(pts, dtype=np.float32)
            return zeros, zeros
        n = mono.shape[0]
        if n <= pts:
            padded = np.zeros(pts, dtype=np.float32)
            padded[-n:] = mono
            return padded, padded
        step = n // pts
        trimmed = mono[: step * pts].reshape(pts, step)
        return np.min(trimmed, axis=1).astype(np.float32), np.max(trimmed, axis=1).astype(np.float32)

    def analyze_frame(self, mono: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (fft_mag_linear, fft_db, log_spectrum_db) for the latest mono slice."""
        if mono.shape[0] < self.fft_size:
            frame = np.zeros(self.fft_size, dtype=np.float32)
            if mono.shape[0] > 0:
                frame[-mono.shape[0] :] = mono
        else:
            frame = mono[-self.fft_size :]

        if not np.all(np.isfinite(frame)):
            frame = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)

        windowed = frame * self._window
        spec = np.fft.rfft(windowed)
        mag = (np.abs(spec) * 2.0 / self._window_norm).astype(np.float32)
        power = np.square(mag)
        fft_db = (10.0 * np.log10(np.maximum(power, 1e-12))).astype(np.float32)

        log_power = self._log_fb @ power
        log_db = (10.0 * np.log10(np.maximum(log_power, 1e-12))).astype(np.float32)

        with self._history_lock:
            self._log_history.append(log_db)

        return mag, fft_db, log_db

    def recent_log_spectrogram(self) -> np.ndarray:
        with self._history_lock:
            if not self._log_history:
                return np.empty((0, self.config.log_freq_bins), dtype=np.float32)
            return np.stack(list(self._log_history), axis=0)
