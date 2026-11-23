"""CPU-only 12-bin chroma extractor with bounded 120s history."""

from __future__ import annotations

from collections import deque
import threading
from typing import Optional

import numpy as np
from scipy.signal import resample_poly

from core.config import AnalysisConfig

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_DEFAULT_OCTAVE_WEIGHTS: dict[int, float] = {
    2: 0.75,
    3: 1.10,
    4: 1.15,
    5: 0.85,
    6: 0.40,
}

_BASS_OCTAVE_WEIGHTS: dict[int, float] = {
    1: 0.65,
    2: 1.50,
    3: 0.35,
}


class ChromaExtractor:
    """Maps rFFT magnitude or PCM audio to L2-normalized 12-bin pitch classes."""

    def __init__(
        self,
        sample_rate: int = 48000,
        config: Optional[AnalysisConfig] = None,
        *,
        fmin_hz: float = 65.41,   # C2
        fmax_hz: float = 1200.0,  # ~D6 (avoids cymbal/snare bleed)
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.config = config or AnalysisConfig()
        self._freqs = np.fft.rfftfreq(self.config.fft_size, d=1.0 / self.sample_rate).astype(np.float32)
        self._chroma_fb = self._build_chroma_filterbank(self._freqs, fmin_hz=fmin_hz, fmax_hz=fmax_hz)
        self._bass_fb = self._build_chroma_filterbank(
            self._freqs,
            fmin_hz=41.20,   # E1
            fmax_hz=246.94,  # B3
            octave_weights=_BASS_OCTAVE_WEIGHTS,
        )
        self._sfm_mask = (self._freqs >= 120.0) & (self._freqs <= 3000.0)

        # High-resolution 4x downsampled analyzer for eliminating Octave 2 FFT blind spots
        self._hr_factor = 4 if self.sample_rate >= 24000 else 1
        self._hr_sr = self.sample_rate / float(self._hr_factor)
        self._hr_fft_size = 4096
        self._hr_window = np.hanning(self._hr_fft_size).astype(np.float32)
        self._hr_window_scale = float(np.sum(self._hr_window)) * 0.5 + 1e-9
        self._hr_freqs = np.fft.rfftfreq(self._hr_fft_size, d=1.0 / self._hr_sr).astype(np.float32)
        self._hr_chroma_fb = self._build_chroma_filterbank(
            self._hr_freqs,
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
        )
        self._hr_bass_fb = self._build_chroma_filterbank(
            self._hr_freqs,
            fmin_hz=41.20,   # E1
            fmax_hz=246.94,  # B3
            octave_weights=_BASS_OCTAVE_WEIGHTS,
        )
        self._hr_sfm_mask = (self._hr_freqs >= 120.0) & (self._hr_freqs <= 3000.0)

        max_hist = max(1, int(self.config.chroma_history_seconds * self.config.analysis_rate_hz))
        self._lock = threading.Lock()
        self._hist_cap = max_hist
        self._history = np.zeros((max_hist, 12), dtype=np.float32)
        self._weight_history = np.zeros(max_hist, dtype=np.float32)
        self._bass_history = np.zeros((max_hist, 12), dtype=np.float32)
        self._hist_pos = 0
        self._hist_len = 0

    def _build_chroma_filterbank(
        self,
        freqs: Optional[np.ndarray] = None,
        *,
        fmin_hz: float,
        fmax_hz: float,
        octave_weights: Optional[dict[int, float]] = None,
    ) -> np.ndarray:
        freq_axis = self._freqs if freqs is None else freqs
        fb = np.zeros((12, freq_axis.shape[0]), dtype=np.float32)
        valid = (freq_axis >= fmin_hz) & (freq_axis <= fmax_hz) & (freq_axis > 0.0)
        valid_idx = np.where(valid)[0]
        if valid_idx.size == 0:
            return fb

        valid_freqs = freq_axis[valid_idx]
        valid_midi = 69.0 + 12.0 * np.log2(valid_freqs / 440.0)
        midi_min = int(np.floor(np.min(valid_midi)))
        midi_max = int(np.ceil(np.max(valid_midi)))
        oct_weights = _DEFAULT_OCTAVE_WEIGHTS if octave_weights is None else octave_weights

        for m in range(midi_min, midi_max + 1):
            dist = np.abs(valid_midi - float(m))
            mask = dist <= 0.55
            if not np.any(mask):
                continue
            w = np.exp(-0.5 * (dist[mask] / 0.24) ** 2)
            w_sum = float(np.sum(w))
            if w_sum <= 1e-12:
                continue
            w = w / (w_sum + 1e-9)
            octave = (m // 12) - 1
            ow = float(oct_weights.get(octave, 0.50))
            fb[m % 12, valid_idx[mask]] += (w * ow).astype(np.float32)

        return fb

    @staticmethod
    def _compute_tonality(mag: np.ndarray, mask: np.ndarray) -> float:
        if not np.any(mask):
            return 0.5
        band = np.maximum(mag[mask], 1e-12)
        arith_mean = float(np.mean(band))
        if arith_mean <= 1e-12:
            return 0.05
        geo_mean = float(np.exp(np.mean(np.log(band))))
        sfm = geo_mean / arith_mean
        return max(0.05, 1.0 - sfm * 3.0)

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> tuple[np.ndarray, float]:
        norm = float(np.linalg.norm(vec))
        if np.isfinite(norm) and norm > 1e-9:
            return (vec / norm).astype(np.float32), norm
        return np.zeros(12, dtype=np.float32), 0.0

    @property
    def history_maxlen(self) -> int:
        return self._hist_cap

    def clear(self) -> None:
        with self._lock:
            self._hist_pos = 0
            self._hist_len = 0

    def _append_history_locked(self, chroma: np.ndarray, weight: float, bass_chroma: np.ndarray) -> None:
        idx = self._hist_pos
        self._history[idx] = chroma
        self._weight_history[idx] = np.float32(weight)
        self._bass_history[idx] = bass_chroma
        self._hist_pos = (idx + 1) % self._hist_cap
        if self._hist_len < self._hist_cap:
            self._hist_len += 1

    def extract_from_magnitude(
        self,
        fft_mag: np.ndarray,
        *,
        record_history: bool = True,
        is_silent: bool = False,
    ) -> np.ndarray:
        if (
            is_silent
            or fft_mag.size == 0
            or fft_mag.shape[0] != self._chroma_fb.shape[1]
            or not np.all(np.isfinite(fft_mag))
        ):
            chroma = np.zeros(12, dtype=np.float32)
            bass_chroma = np.zeros(12, dtype=np.float32)
            weight = 0.0
        else:
            mag_pos = np.maximum(fft_mag, 0.0).astype(np.float32, copy=False)
            max_mag = float(np.max(mag_pos))
            if max_mag <= 1e-12:
                chroma = np.zeros(12, dtype=np.float32)
                bass_chroma = np.zeros(12, dtype=np.float32)
                weight = 0.0
            else:
                norm_mag = mag_pos / max_mag
                comp = np.log1p(12.0 * norm_mag).astype(np.float32)
                comp_bass = np.log1p(6.0 * norm_mag).astype(np.float32)
                chroma, norm = self._l2_normalize(self._chroma_fb @ comp)
                bass_chroma, _ = self._l2_normalize(self._bass_fb @ comp_bass)
                weight = self._compute_tonality(mag_pos, self._sfm_mask) if norm > 1e-9 else 0.0

        if record_history:
            with self._lock:
                self._append_history_locked(chroma, weight, bass_chroma)
        return chroma

    def extract_from_pcm(
        self,
        mono: np.ndarray,
        *,
        record_history: bool = True,
        is_silent: bool = False,
    ) -> np.ndarray:
        chroma, _bass = self.extract_with_bass_from_pcm(
            mono, record_history=record_history, is_silent=is_silent
        )
        return chroma

    def extract_with_bass_from_pcm(
        self,
        mono: np.ndarray,
        *,
        record_history: bool = True,
        is_silent: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        if is_silent or mono is None or mono.size == 0 or not np.all(np.isfinite(mono)):
            chroma = np.zeros(12, dtype=np.float32)
            bass_chroma = np.zeros(12, dtype=np.float32)
            weight = 0.0
        else:
            x = np.asarray(mono, dtype=np.float32).ravel()
            need = self._hr_fft_size * self._hr_factor
            if x.shape[0] > need:
                x = x[-need:]
            elif x.shape[0] < need:
                x = np.pad(x, (need - x.shape[0], 0), mode="constant")

            rms = float(np.sqrt(np.mean(np.square(x))))
            if not np.isfinite(rms) or rms <= 1e-9:
                chroma = np.zeros(12, dtype=np.float32)
                bass_chroma = np.zeros(12, dtype=np.float32)
                weight = 0.0
            else:
                if self._hr_factor > 1:
                    x_ds = resample_poly(x, 1, self._hr_factor).astype(np.float32, copy=False)
                    if x_ds.shape[0] > self._hr_fft_size:
                        x_ds = x_ds[-self._hr_fft_size:]
                    elif x_ds.shape[0] < self._hr_fft_size:
                        x_ds = np.pad(x_ds, (self._hr_fft_size - x_ds.shape[0], 0), mode="constant")
                else:
                    x_ds = x[-self._hr_fft_size:]

                hr_mag = np.abs(np.fft.rfft(x_ds * self._hr_window)).astype(np.float32)
                max_mag = float(np.max(hr_mag))
                if max_mag <= 1e-12:
                    chroma = np.zeros(12, dtype=np.float32)
                    bass_chroma = np.zeros(12, dtype=np.float32)
                    weight = 0.0
                else:
                    norm_mag = hr_mag / max_mag
                    comp = np.log1p(12.0 * norm_mag).astype(np.float32)
                    comp_bass = np.log1p(6.0 * norm_mag).astype(np.float32)
                    raw_c = np.power(np.maximum(self._hr_chroma_fb @ comp, 0.0), 1.3).astype(np.float32)
                    chroma, norm_c = self._l2_normalize(raw_c)
                    bass_chroma, norm_b = self._l2_normalize(self._hr_bass_fb @ comp_bass)
                    if norm_b < 0.25 * max(norm_c, 1e-6):
                        bass_chroma = np.zeros(12, dtype=np.float32)
                    if norm_c > 1e-9:
                        tonality = self._compute_tonality(hr_mag, self._hr_sfm_mask)
                        weight = float(tonality * np.sqrt(rms))
                    else:
                        weight = 0.0

        if record_history:
            with self._lock:
                self._append_history_locked(chroma, weight, bass_chroma)
        return chroma, bass_chroma

    def _ordered_slice_locked(self, buf: np.ndarray, take: Optional[int]) -> np.ndarray:
        n = self._hist_len
        if n == 0:
            return np.empty((0,) + buf.shape[1:], dtype=buf.dtype)
        count = n if take is None else min(n, max(1, take))
        if self._hist_len < self._hist_cap:
            start = n - count
            return np.array(buf[start:n], dtype=buf.dtype, copy=True)
        # Full ring: oldest is at self._hist_pos
        start = (self._hist_pos - count) % self._hist_cap
        if start + count <= self._hist_cap:
            return np.array(buf[start : start + count], dtype=buf.dtype, copy=True)
        first = self._hist_cap - start
        return np.concatenate([buf[start:], buf[: count - first]], axis=0).astype(buf.dtype, copy=False)

    def recent_chroma_matrix(self, seconds: Optional[float] = None) -> np.ndarray:
        take = max(1, int(seconds * self.config.analysis_rate_hz)) if seconds is not None else None
        with self._lock:
            return self._ordered_slice_locked(self._history, take)

    def recent_chroma_bundle(
        self, seconds: Optional[float] = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        take = max(1, int(seconds * self.config.analysis_rate_hz)) if seconds is not None else None
        with self._lock:
            return (
                self._ordered_slice_locked(self._history, take),
                self._ordered_slice_locked(self._weight_history, take),
                self._ordered_slice_locked(self._bass_history, take),
            )
