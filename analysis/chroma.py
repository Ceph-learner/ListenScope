"""CPU-only 12-bin chroma extractor with bounded 120s history."""

from __future__ import annotations

from collections import deque
import threading
from typing import Optional

import numpy as np

from core.config import AnalysisConfig

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class ChromaExtractor:
    """Maps rFFT magnitude/power spectrum to L2-normalized 12-bin pitch classes."""

    def __init__(
        self,
        sample_rate: int = 48000,
        config: Optional[AnalysisConfig] = None,
        *,
        fmin_hz: float = 65.41,   # C2
        fmax_hz: float = 2093.0,  # C7
    ) -> None:
        self.sample_rate = sample_rate
        self.config = config or AnalysisConfig()
        self._freqs = np.fft.rfftfreq(self.config.fft_size, d=1.0 / self.sample_rate).astype(np.float32)
        self._chroma_fb = self._build_chroma_filterbank(fmin_hz=fmin_hz, fmax_hz=fmax_hz)

        max_hist = max(1, int(self.config.chroma_history_seconds * self.config.analysis_rate_hz))
        self._lock = threading.Lock()
        self._history: deque[np.ndarray] = deque(maxlen=max_hist)

    def _build_chroma_filterbank(self, *, fmin_hz: float, fmax_hz: float) -> np.ndarray:
        fb = np.zeros((12, self._freqs.shape[0]), dtype=np.float32)
        valid = (self._freqs >= fmin_hz) & (self._freqs <= fmax_hz)
        valid_idx = np.where(valid)[0]
        valid_freqs = self._freqs[valid_idx]

        # MIDI pitch: 69 = A4 = 440 Hz; C = 0 mod 12
        midi = 69.0 + 12.0 * np.log2(valid_freqs / 440.0)
        for idx, m in zip(valid_idx, midi):
            # Soft Gaussian weighting across pitch-class centers
            pc = m % 12.0
            for c in range(12):
                dist = min(abs(pc - c), 12.0 - abs(pc - c))
                if dist <= 0.75:
                    w = float(np.exp(-0.5 * (dist / 0.35) ** 2))
                    fb[c, idx] += w

        # Normalize per pitch class so treble bin density doesn't dominate bass bins
        row_sums = np.sum(fb, axis=1, keepdims=True)
        fb = np.divide(fb, np.maximum(row_sums, 1e-6))
        return fb

    @property
    def history_maxlen(self) -> int:
        return self._history.maxlen or 0

    def clear(self) -> None:
        with self._lock:
            self._history.clear()

    def extract_from_magnitude(self, fft_mag: np.ndarray, *, record_history: bool = True, is_silent: bool = False) -> np.ndarray:
        if (
            is_silent
            or fft_mag.size == 0
            or fft_mag.shape[0] != self._chroma_fb.shape[1]
            or not np.all(np.isfinite(fft_mag))
        ):
            chroma = np.zeros(12, dtype=np.float32)
        else:
            power = np.square(fft_mag, dtype=np.float32)
            raw = self._chroma_fb @ power
            norm = float(np.linalg.norm(raw))
            chroma = (raw / norm).astype(np.float32) if np.isfinite(norm) and norm > 1e-9 else np.zeros(12, dtype=np.float32)

        if record_history:
            with self._lock:
                self._history.append(chroma)
        return chroma

    def recent_chroma_matrix(self, seconds: Optional[float] = None) -> np.ndarray:
        with self._lock:
            if not self._history:
                return np.empty((0, 12), dtype=np.float32)
            items = list(self._history)
        if seconds is not None:
            take = max(1, int(seconds * self.config.analysis_rate_hz))
            items = items[-take:]
        return np.stack(items, axis=0)
