"""Fixed-size 120-second PCM ring buffer (48kHz, stereo, float32).

Preallocates a single contiguous NumPy array (~43.95 MiB / 46.08 MB) once.
Strictly prohibits list.append(), growing np.concatenate(), or full-session
history retention.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from math import gcd
from operator import index
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
import wave
from typing import Optional

import numpy as np

from core.config import AudioConfig


@contextmanager
def atomic_pcm16_wav(path: Path, sample_rate: int, channels: int) -> Iterator[wave.Wave_write]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as file:
            tmp_path = Path(file.name)
            with wave.open(file, "wb") as writer:
                writer.setnchannels(channels)
                writer.setsampwidth(2)
                writer.setframerate(sample_rate)
                yield writer
        tmp_path.replace(path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


class FixedRingBuffer:
    """Thread-safe fixed-capacity stereo float32 PCM ring buffer."""

    def __init__(self, audio_config: Optional[AudioConfig] = None) -> None:
        self.audio_config = audio_config or AudioConfig()
        self.sample_rate = self.audio_config.sample_rate
        self.channels = self.audio_config.channels
        self.capacity_frames = max(1, int(round(self.sample_rate * float(self.audio_config.ring_buffer_seconds))))

        # Single preallocated buffer: 120s * 48000 * 2 * 4 = 46,080,000 bytes
        self._buffer = np.zeros((self.capacity_frames, self.channels), dtype=np.float32)
        self._write_pos = 0
        self._total_written_frames = 0
        self._generation = 0
        self._lock = threading.RLock()

    @property
    def buffer_nbytes(self) -> int:
        return int(self._buffer.nbytes)

    @property
    def total_written_frames(self) -> int:
        with self._lock:
            return self._total_written_frames

    @property
    def available_frames(self) -> int:
        with self._lock:
            return min(self._total_written_frames, self.capacity_frames)

    @property
    def available_seconds(self) -> float:
        return self.available_frames / float(self.sample_rate)

    @property
    def oldest_abs_frame(self) -> int:
        with self._lock:
            return max(0, self._total_written_frames - self.capacity_frames)

    def clear(self) -> None:
        with self._lock:
            self._buffer.fill(0.0)
            self._write_pos = 0
            self._total_written_frames = 0
            self._generation += 1

    def write(self, chunk: np.ndarray) -> int:
        """Write a (frames, channels) float32 chunk into the preallocated ring buffer."""
        if chunk.size == 0:
            return 0
        arr = np.asarray(chunk, dtype=np.float32)
        if arr.ndim == 1:
            usable = (arr.size // self.channels) * self.channels
            if usable == 0:
                return 0
            arr = arr[:usable].reshape(-1, self.channels)
        elif arr.ndim != 2:
            raise ValueError(f"Expected 1D or 2D array, got shape {arr.shape}")
        if arr.shape[1] != self.channels:
            raise ValueError(f"Expected {self.channels} channels, got {arr.shape[1]}")
        if not np.all(np.isfinite(arr)):
            arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)

        n = int(arr.shape[0])
        with self._lock:
            if n >= self.capacity_frames:
                # Only keep the newest capacity_frames without resizing self._buffer
                arr = arr[-self.capacity_frames :]
                self._buffer[:, :] = arr
                self._write_pos = 0
                self._total_written_frames += n
                return n

            end_pos = self._write_pos + n
            if end_pos <= self.capacity_frames:
                self._buffer[self._write_pos : end_pos] = arr
            else:
                first_part = self.capacity_frames - self._write_pos
                self._buffer[self._write_pos :] = arr[:first_part]
                self._buffer[: n - first_part] = arr[first_part:]

            self._write_pos = end_pos % self.capacity_frames
            self._total_written_frames += n
            return n

    def read_recent(self, seconds: float) -> tuple[np.ndarray, int, int]:
        """Return (pcm_f32_copy, start_abs_frame, end_abs_frame) for the last N seconds."""
        req_frames = max(0, int(round(seconds * self.sample_rate)))
        with self._lock:
            end_abs = self._total_written_frames
            avail = min(self._total_written_frames, self.capacity_frames)
            take = min(req_frames, avail)
            start_abs = end_abs - take
            return self._read_range_locked(start_abs, end_abs), start_abs, end_abs

    def read_range(self, start_abs_frame: int, end_abs_frame: int) -> np.ndarray:
        """Read an absolute frame range [start_abs_frame, end_abs_frame) if still retained."""
        with self._lock:
            return self._read_range_locked(start_abs_frame, end_abs_frame)

    def read_positioned(self, start_abs_frame: int, end_abs_frame: int) -> tuple[np.ndarray, int]:
        """Read a range and report where the retained samples actually begin."""
        with self._lock:
            start = max(0, self._total_written_frames - self.capacity_frames, start_abs_frame)
            return self._read_range_locked(start, end_abs_frame), start

    def _read_range_locked(self, start_abs_frame: int, end_abs_frame: int) -> np.ndarray:
        oldest = max(0, self._total_written_frames - self.capacity_frames)
        newest = self._total_written_frames
        s = max(oldest, int(start_abs_frame))
        e = min(newest, int(end_abs_frame))
        if e <= s:
            return np.empty((0, self.channels), dtype=np.float32)

        count = e - s
        out = np.empty((count, self.channels), dtype=np.float32)

        # Compute ring offset of s relative to current write cursor
        frames_from_newest_to_s = newest - s
        start_ring = (self._write_pos - frames_from_newest_to_s) % self.capacity_frames
        if start_ring + count <= self.capacity_frames:
            out[:, :] = self._buffer[start_ring : start_ring + count]
        else:
            first_part = self.capacity_frames - start_ring
            out[:first_part] = self._buffer[start_ring:]
            out[first_part:] = self._buffer[: count - first_part]
        return out

    def snapshot_envelope(self, num_points: int = 300) -> tuple[np.ndarray, np.ndarray, float]:
        """Compute bounded chronological min/max waveform envelope without copying the 46MB ring buffer."""
        n_pts = max(1, int(num_points))
        mins = np.zeros(n_pts, dtype=np.float32)
        maxs = np.zeros(n_pts, dtype=np.float32)
        with self._lock:
            avail = min(self._total_written_frames, self.capacity_frames)
            if avail <= 0:
                return mins, maxs, 0.0
            avail_sec = avail / float(self.sample_rate)
            start_ring = (self._write_pos - avail) % self.capacity_frames
            cap = self.capacity_frames
            buf = self._buffer
            for i in range(n_pts):
                b0 = (i * avail) // n_pts
                b1 = ((i + 1) * avail) // n_pts
                if b1 <= b0:
                    b1 = min(avail, b0 + 1)
                span = b1 - b0
                if span <= 0:
                    continue
                if span <= 96:
                    idxs = (start_ring + np.arange(b0, b1, dtype=np.int64)) % cap
                else:
                    idxs = (start_ring + np.linspace(b0, b1 - 1, 96, dtype=np.int64)) % cap
                seg = buf[idxs]
                mono = 0.5 * (seg[:, 0] + seg[:, 1])
                mins[i] = float(np.min(mono))
                maxs[i] = float(np.max(mono))
            return mins, maxs, avail_sec

    def prepare_export(
        self, start_abs_frame: int, end_abs_frame: int
    ) -> tuple[int, int, Callable[[int, int], np.ndarray]]:
        """Clip the requested interval once and return a bounded exact reader for that capture."""
        with self._lock:
            generation = self._generation
            newest = self._total_written_frames
            start = max(0, newest - self.capacity_frames, int(start_abs_frame))
            end = min(newest, int(end_abs_frame))
        if end <= start:
            raise ValueError("导出区间为空，或已被历史缓冲覆盖。")

        def read(first: int, stop: int) -> np.ndarray:
            with self._lock:
                if generation != self._generation:
                    raise ValueError("导出期间音频历史已重置，请重新选择 A/B 区间。")
                chunk = self._read_range_locked(first, stop)
                if chunk.shape[0] != stop - first:
                    raise ValueError("导出期间部分音频已被历史缓冲覆盖，请重新选择 A/B 区间。")
                return chunk

        return start, end, read

    def export_wav_streaming(
        self,
        out_path: Path | str,
        start_abs_frame: int,
        end_abs_frame: int,
        *,
        chunk_frames: int = 48000,
    ) -> tuple[Path, float]:
        """Stream an A/B excerpt directly to a 16-bit PCM WAV file in fixed chunks.

        Avoids holding duplicate full-excerpt arrays in RAM.
        Returns (output_path, exported_duration_seconds).
        """
        chunk_frames = index(chunk_frames)
        if chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")
        chunk_frames = min(chunk_frames, self.sample_rate)
        start, end, read = self.prepare_export(start_abs_frame, end_abs_frame)
        path = Path(out_path)
        with atomic_pcm16_wav(path, self.sample_rate, self.channels) as writer:
            for cursor in range(start, end, chunk_frames):
                chunk = read(cursor, min(end, cursor + chunk_frames))
                pcm_i16 = (np.clip(chunk, -1.0, 1.0) * 32767.0).astype("<i2")
                writer.writeframesraw(pcm_i16.tobytes())
        return path, (end - start) / float(self.sample_rate)

    def import_audio_file_streaming(
        self,
        audio_path: Path | str,
        *,
        max_seconds: Optional[float] = None,
        chunk_seconds: float = 1.0,
    ) -> tuple[float, bool]:
        """Stream an audio file into the 120s ring buffer in small chunks, capped to capacity.

        Never materializes an entire long audio file in RAM. Returns `(imported_sec, truncated)`.
        """
        from .pcm_utils import decode_wave_bytes, normalize_to_canonical_pcm

        src = Path(audio_path)
        if not src.exists():
            raise FileNotFoundError(f"音频文件不存在: {src}")

        cap_sec = float(self.audio_config.ring_buffer_seconds)
        limit_sec = cap_sec if max_seconds is None else min(cap_sec, max(0.5, float(max_seconds)))

        max_dst_frames = min(self.capacity_frames, int(round(limit_sec * self.sample_rate)))

        def import_frames(
            read: Callable[[int], np.ndarray], rate: int, channels: int, total: int,
        ) -> tuple[float, bool]:
            if rate <= 0:
                raise ValueError(f"无效音频采样率: {rate}")
            if total <= 0:
                raise ValueError(f"音频文件不包含有效帧: {src.name}")

            divisor = gcd(rate, self.sample_rate)
            up, down = self.sample_rate // divisor, rate // divisor
            # resample_poly's default FIR extends 10 * max(up, down) samples
            # to either side on the upsampled grid.
            halo = (10 * max(up, down) + up - 1) // up + 1 if rate != self.sample_rate else 0
            step = max(256, int(round(chunk_seconds * rate)))
            source_limit = min(total, (max_dst_frames * down + up - 1) // up)
            full_output = (total * up + down - 1) // down
            written = 0
            window = np.empty((0, channels), dtype=np.float32)
            start = window_start = available_end = 0
            eof = False
            while start < source_limit:
                stop = min(source_limit, start + step)
                # Put the read origin on the same output phase as the start of the file.
                left = max(0, (start - halo) // down * down)
                right = min(total, stop + halo)
                # Keep the overlap and read only new samples, including for compressed audio.
                tail = window[left - window_start:]
                parts = [tail] if len(tail) else []
                while not eof and available_end < right:
                    incoming = read(right - available_end)
                    if not len(incoming):
                        eof = True
                        break
                    parts.append(incoming)
                    available_end += len(incoming)
                    if not halo:
                        # Same-rate reads can emit partial blocks without any right context.
                        break
                if available_end <= start:
                    break
                window = parts[0] if len(parts) == 1 else np.concatenate(parts)
                window_start = left
                converted = normalize_to_canonical_pcm(
                    window, src_rate=rate, src_channels=channels,
                    dst_rate=self.sample_rate, dst_channels=self.channels,
                )
                origin = left * up // down
                first_frame = (start * up + down - 1) // down
                start_next = min(stop, available_end)
                last_frame = min(max_dst_frames, (start_next * up + down - 1) // down)
                block = converted[first_frame - origin:last_frame - origin]
                if len(block):
                    if written == 0:
                        self.clear()
                    written += self.write(block)
                start = start_next
            if written == 0:
                raise ValueError(f"音频文件未能解码出有效帧: {src.name}")
            return written / float(self.sample_rate), full_output > max_dst_frames

        try:
            import soundfile as sf  # type: ignore[import-untyped]

            with sf.SoundFile(str(src), "r") as sf_file:
                def read_soundfile(count: int) -> np.ndarray:
                    return sf_file.read(count, dtype="float32", always_2d=True)

                return import_frames(read_soundfile, sf_file.samplerate, sf_file.channels, sf_file.frames)
        except Exception as sf_exc:
            if src.suffix.lower() not in (".wav", ".wave") or isinstance(sf_exc, ValueError):
                raise RuntimeError(f"无法读取音频文件 {src.name}: {sf_exc}") from sf_exc

        with wave.open(str(src), "rb") as wf:
            channels, width = wf.getnchannels(), wf.getsampwidth()
            if width not in (1, 2, 3, 4):
                raise ValueError(f"Unsupported WAV sample width: {width}")

            def read_wave(count: int) -> np.ndarray:
                return decode_wave_bytes(wf.readframes(count), width, channels)

            return import_frames(read_wave, wf.getframerate(), channels, wf.getnframes())
