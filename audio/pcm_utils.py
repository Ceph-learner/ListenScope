"""Canonical PCM normalization (48kHz, stereo, float32) and level metering."""

from __future__ import annotations

from math import gcd
import numpy as np
from scipy.signal import resample_poly


DBFS_FLOOR = -120.0
MIN_AMP = 1e-6  # -120 dBFS


def normalize_to_canonical_pcm(
    data: bytes | np.ndarray,
    *,
    src_rate: int,
    src_channels: int,
    src_dtype: str = "float32",
    dst_rate: int = 48000,
    dst_channels: int = 2,
) -> np.ndarray:
    """Convert raw PCM bytes or ndarray into canonical (frames, 2) float32 [-1.0, 1.0].

    Minimizes unnecessary intermediate copies: when input is already 48kHz,
    2ch, float32 bytes, returns a clean reshaped float32 view/copy without
    resampling overhead.
    """
    if src_channels <= 0:
        raise ValueError(f"src_channels must be positive, got {src_channels}")
    if src_rate <= 0:
        raise ValueError(f"src_rate must be positive, got {src_rate}")

    if isinstance(data, (bytes, bytearray, memoryview)):
        if len(data) == 0:
            return np.empty((0, dst_channels), dtype=np.float32)

        dtype_key = src_dtype.lower()
        if dtype_key in ("float32", "f32"):
            usable_b = (len(data) // 4) * 4
            if usable_b == 0:
                return np.empty((0, dst_channels), dtype=np.float32)
            arr = np.frombuffer(memoryview(data)[:usable_b], dtype=np.float32)
        elif dtype_key in ("int16", "s16"):
            usable_b = (len(data) // 2) * 2
            if usable_b == 0:
                return np.empty((0, dst_channels), dtype=np.float32)
            raw = np.frombuffer(memoryview(data)[:usable_b], dtype=np.int16)
            arr = raw.astype(np.float32) / 32768.0
        elif dtype_key in ("int24", "s24"):
            raw_u8 = np.frombuffer(data, dtype=np.uint8)
            usable_b = (raw_u8.size // 3) * 3
            if usable_b == 0:
                return np.empty((0, dst_channels), dtype=np.float32)
            triplets = raw_u8[:usable_b].reshape(-1, 3).astype(np.int32)
            signed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
            signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
            arr = signed.astype(np.float32) / 8388608.0
        elif dtype_key in ("int32", "s32"):
            usable_b = (len(data) // 4) * 4
            if usable_b == 0:
                return np.empty((0, dst_channels), dtype=np.float32)
            raw = np.frombuffer(memoryview(data)[:usable_b], dtype=np.int32)
            arr = raw.astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported src_dtype: {src_dtype}")
    else:
        arr = np.asarray(data)
        if arr.size == 0:
            return np.empty((0, dst_channels), dtype=np.float32)
        if arr.dtype != np.float32:
            if arr.dtype == np.uint8:
                arr = (arr.astype(np.float32) - 128.0) / 128.0
            elif np.issubdtype(arr.dtype, np.unsignedinteger):
                half = float(2 ** (arr.dtype.itemsize * 8 - 1))
                arr = (arr.astype(np.float32) - half) / half
            elif np.issubdtype(arr.dtype, np.signedinteger):
                max_val = float(2 ** (arr.dtype.itemsize * 8 - 1))
                arr = arr.astype(np.float32) / max_val
            else:
                arr = arr.astype(np.float32)

    if arr.ndim == 1:
        usable = (arr.size // src_channels) * src_channels
        if usable == 0:
            return np.empty((0, dst_channels), dtype=np.float32)
        arr = arr[:usable].reshape(-1, src_channels)
    elif arr.ndim == 2:
        if arr.shape[1] != src_channels:
            if arr.shape[0] == src_channels:
                arr = arr.T
            else:
                raise ValueError(f"Expected {src_channels} channels, got shape {arr.shape}")
    else:
        raise ValueError(f"Expected 1D or 2D PCM array, got shape {arr.shape}")

    # Channel conversion
    if src_channels == dst_channels:
        stereo = arr
    elif src_channels == 1 and dst_channels == 2:
        stereo = np.repeat(arr, 2, axis=1)
    elif src_channels > 2 and dst_channels == 2:
        # Standard L/R front channels when multichannel audio arrives
        stereo = arr[:, :2]
    elif src_channels >= 2 and dst_channels == 1:
        stereo = np.mean(arr[:, :2], axis=1, keepdims=True)
    else:
        raise ValueError(f"Unsupported channel conversion: {src_channels} -> {dst_channels}")

    # Sample rate conversion using polyphase filtering
    if src_rate != dst_rate and stereo.shape[0] > 0:
        g = gcd(dst_rate, src_rate)
        up = dst_rate // g
        down = src_rate // g
        stereo = resample_poly(stereo, up, down, axis=0).astype(np.float32, copy=False)

    # Ensure finite float32 contiguous chunk (guards against Windows driver glitch NaNs)
    if stereo.dtype != np.float32:
        stereo = stereo.astype(np.float32)
    if stereo.size > 0 and not np.all(np.isfinite(stereo)):
        stereo = np.nan_to_num(stereo, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
    if not stereo.flags["C_CONTIGUOUS"]:
        stereo = np.ascontiguousarray(stereo)
    return stereo


class StreamingResampler:
    """Stateful polyphase resampler using `scipy.signal.resample_poly` without chunk-boundary clicks."""

    def __init__(self, src_rate: int, dst_rate: int, channels: int = 2) -> None:
        if src_rate <= 0:
            raise ValueError(f"src_rate must be positive, got {src_rate}")
        if dst_rate <= 0:
            raise ValueError(f"dst_rate must be positive, got {dst_rate}")
        if channels <= 0:
            raise ValueError(f"channels must be positive, got {channels}")
        self.src_rate = int(src_rate)
        self.dst_rate = int(dst_rate)
        self.channels = int(channels)
        g = gcd(self.dst_rate, self.src_rate)
        self._up = self.dst_rate // g
        self._down = self.src_rate // g
        self._halo_in = (10 * max(self._up, self._down) + self._up - 1) // self._up + 2 if self._up != self._down else 0
        self._buf = np.empty((0, self.channels), dtype=np.float32)
        self._buf_start_in = 0
        self._emitted_out = 0

    def reset(self) -> None:
        self._buf = np.empty((0, self.channels), dtype=np.float32)
        self._buf_start_in = 0
        self._emitted_out = 0

    def process(self, chunk: np.ndarray) -> np.ndarray:
        arr = np.asarray(chunk, dtype=np.float32)
        if arr.size == 0:
            return np.empty((0, self.channels), dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
            if self.channels > 1 and arr.shape[1] == 1:
                arr = np.repeat(arr, self.channels, axis=1)
        if arr.shape[1] != self.channels:
            raise ValueError(f"Expected {self.channels} channels, got shape {arr.shape}")

        if self._up == self._down:
            return np.ascontiguousarray(arr, dtype=np.float32)

        self._buf = arr if self._buf.shape[0] == 0 else np.concatenate([self._buf, arr], axis=0)
        total_in = self._buf_start_in + self._buf.shape[0]
        safe_in_end = total_in - self._halo_in
        if safe_in_end <= self._buf_start_in:
            return np.empty((0, self.channels), dtype=np.float32)

        target_out = (safe_in_end * self._up) // self._down
        if target_out <= self._emitted_out:
            return np.empty((0, self.channels), dtype=np.float32)

        approx_in = (self._emitted_out * self._down) // self._up
        left_in = max(self._buf_start_in, ((approx_in - self._halo_in) // self._down) * self._down)
        # Align left_in to down-grid if possible
        if left_in > self._buf_start_in:
            left_in = (left_in // self._down) * self._down
            if left_in < self._buf_start_in:
                left_in = self._buf_start_in

        window = self._buf[left_in - self._buf_start_in :]
        converted = resample_poly(window, self._up, self._down, axis=0).astype(np.float32, copy=False)
        origin_out = (left_in * self._up) // self._down
        start_idx = self._emitted_out - origin_out
        end_idx = target_out - origin_out
        if start_idx < 0:
            start_idx = 0
        if end_idx <= start_idx:
            return np.empty((0, self.channels), dtype=np.float32)

        out = np.ascontiguousarray(converted[start_idx:end_idx], dtype=np.float32)
        self._emitted_out = target_out

        next_approx_in = (self._emitted_out * self._down) // self._up
        keep_from_in = max(self._buf_start_in, ((next_approx_in - self._halo_in - self._down) // self._down) * self._down)
        if keep_from_in > self._buf_start_in:
            drop = keep_from_in - self._buf_start_in
            self._buf = np.ascontiguousarray(self._buf[drop:])
            self._buf_start_in = keep_from_in

        return out

    def flush(self) -> np.ndarray:
        if self._up == self._down or self._buf.shape[0] == 0:
            self.reset()
            return np.empty((0, self.channels), dtype=np.float32)
        total_in = self._buf_start_in + self._buf.shape[0]
        target_out = (total_in * self._up + self._down - 1) // self._down
        if target_out <= self._emitted_out:
            self.reset()
            return np.empty((0, self.channels), dtype=np.float32)
        approx_in = (self._emitted_out * self._down) // self._up
        left_in = max(self._buf_start_in, ((approx_in - self._halo_in) // self._down) * self._down)
        window = self._buf[left_in - self._buf_start_in :]
        converted = resample_poly(window, self._up, self._down, axis=0).astype(np.float32, copy=False)
        origin_out = (left_in * self._up) // self._down
        start_idx = max(0, self._emitted_out - origin_out)
        end_idx = target_out - origin_out
        out = np.ascontiguousarray(converted[start_idx:end_idx], dtype=np.float32)
        self.reset()
        return out


def compute_rms_and_peak(pcm_f32: np.ndarray) -> tuple[float, float, float, float]:
    """Compute (rms_linear, rms_dbfs, peak_linear, peak_dbfs) for a float32 PCM chunk."""
    if pcm_f32.size == 0:
        return 0.0, DBFS_FLOOR, 0.0, DBFS_FLOOR

    clean = pcm_f32 if np.all(np.isfinite(pcm_f32)) else np.nan_to_num(pcm_f32, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(clean)))
    rms = float(np.sqrt(np.mean(np.square(clean, dtype=np.float32))))
    if not np.isfinite(rms):
        rms = 0.0
    if not np.isfinite(peak):
        peak = 0.0

    rms_db = float(20.0 * np.log10(max(rms, MIN_AMP)))
    peak_db = float(20.0 * np.log10(max(peak, MIN_AMP)))
    return rms, max(DBFS_FLOOR, rms_db), peak, max(DBFS_FLOOR, peak_db)


def decode_wave_bytes(raw: bytes, sample_width: int, channels: int) -> np.ndarray:
    """Decode raw PCM WAV bytes (1/2/3/4-byte sample width) into finite `(frames, channels)` float32."""
    ch = max(1, int(channels))
    sw = int(sample_width)
    if not raw or sw <= 0:
        return np.empty((0, ch), dtype=np.float32)

    frame_bytes = sw * ch
    usable_b = (len(raw) // frame_bytes) * frame_bytes
    if usable_b <= 0:
        return np.empty((0, ch), dtype=np.float32)

    mv = memoryview(raw)[:usable_b]
    if sw == 2:
        flat = np.frombuffer(mv, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        raw_u8 = np.frombuffer(mv, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        signed = raw_u8[:, 0] | (raw_u8[:, 1] << 8) | (raw_u8[:, 2] << 16)
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        flat = signed.astype(np.float32) / 8388608.0
    elif sw == 4:
        flat = np.frombuffer(mv, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sw == 1:
        flat = (np.frombuffer(mv, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw} bytes")

    arr = flat.reshape(-1, ch)
    if arr.size > 0 and not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
    return arr

