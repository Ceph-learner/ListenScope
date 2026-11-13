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
            arr = np.frombuffer(data, dtype=np.float32)
        elif dtype_key in ("int16", "s16"):
            raw = np.frombuffer(data, dtype=np.int16)
            arr = raw.astype(np.float32) / 32768.0
        elif dtype_key in ("int32", "s32"):
            raw = np.frombuffer(data, dtype=np.int32)
            arr = raw.astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported src_dtype: {src_dtype}")
    else:
        arr = np.asarray(data)
        if arr.size == 0:
            return np.empty((0, dst_channels), dtype=np.float32)
        if arr.dtype != np.float32:
            if np.issubdtype(arr.dtype, np.signedinteger):
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
        if arr.shape[1] != src_channels and arr.shape[0] == src_channels:
            arr = arr.T
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

    # Ensure finite float32 contiguous chunk
    if stereo.dtype != np.float32:
        stereo = stereo.astype(np.float32)
    if not stereo.flags["C_CONTIGUOUS"]:
        stereo = np.ascontiguousarray(stereo)
    return stereo


def compute_rms_and_peak(pcm_f32: np.ndarray) -> tuple[float, float, float, float]:
    """Compute (rms_linear, rms_dbfs, peak_linear, peak_dbfs) for a float32 PCM chunk."""
    if pcm_f32.size == 0:
        return 0.0, DBFS_FLOOR, 0.0, DBFS_FLOOR

    peak = float(np.max(np.abs(pcm_f32)))
    rms = float(np.sqrt(np.mean(np.square(pcm_f32, dtype=np.float32))))

    rms_db = float(20.0 * np.log10(max(rms, MIN_AMP)))
    peak_db = float(20.0 * np.log10(max(peak, MIN_AMP)))
    return rms, max(DBFS_FLOOR, rms_db), peak, max(DBFS_FLOOR, peak_db)
