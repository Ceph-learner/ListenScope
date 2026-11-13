"""Fixed-size 120-second PCM ring buffer (48kHz, stereo, float32).

Preallocates a single contiguous NumPy array (~43.95 MiB / 46.08 MB) once.
Strictly prohibits list.append(), growing np.concatenate(), or full-session
history retention.
"""

from __future__ import annotations

from pathlib import Path
import threading
import wave
from typing import Optional

import numpy as np

from core.config import AudioConfig


class FixedRingBuffer:
    """Thread-safe fixed-capacity stereo float32 PCM ring buffer."""

    def __init__(self, audio_config: Optional[AudioConfig] = None) -> None:
        self.audio_config = audio_config or AudioConfig()
        self.sample_rate = self.audio_config.sample_rate
        self.channels = self.audio_config.channels
        self.capacity_frames = self.sample_rate * self.audio_config.ring_buffer_seconds

        # Single preallocated buffer: 120s * 48000 * 2 * 4 = 46,080,000 bytes
        self._buffer = np.zeros((self.capacity_frames, self.channels), dtype=np.float32)
        self._write_pos = 0
        self._total_written_frames = 0
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

    def write(self, chunk: np.ndarray) -> int:
        """Write a (frames, channels) float32 chunk into the preallocated ring buffer."""
        if chunk.size == 0:
            return 0
        arr = np.asarray(chunk, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, self.channels)
        if arr.shape[1] != self.channels:
            raise ValueError(f"Expected {self.channels} channels, got {arr.shape[1]}")

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
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            oldest = max(0, self._total_written_frames - self.capacity_frames)
            newest = self._total_written_frames
            s = max(oldest, int(start_abs_frame))
            e = min(newest, int(end_abs_frame))

        if e <= s:
            raise ValueError("Selected time range is empty or already overwritten in the 120s ring buffer.")

        total_written = 0
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM WAV for broad audio-separator/Cubase compatibility
            wf.setframerate(self.sample_rate)

            cursor = s
            while cursor < e:
                stop = min(e, cursor + chunk_frames)
                chunk = self.read_range(cursor, stop)
                if chunk.shape[0] == 0:
                    break
                pcm_i16 = (np.clip(chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
                wf.writeframes(pcm_i16.tobytes())
                total_written += int(chunk.shape[0])
                cursor = stop

        return path, total_written / float(self.sample_rate)

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
        from .pcm_utils import normalize_to_canonical_pcm

        src = Path(audio_path)
        if not src.exists():
            raise FileNotFoundError(f"音频文件不存在: {src}")

        cap_sec = float(self.audio_config.ring_buffer_seconds)
        limit_sec = cap_sec if max_seconds is None else min(cap_sec, max(0.5, float(max_seconds)))

        total_dst_frames = 0
        max_dst_frames = int(round(limit_sec * self.sample_rate))
        truncated = False

        try:
            import soundfile as sf  # type: ignore[import-untyped]

            with sf.SoundFile(str(src), "r") as sf_file:
                src_sr = int(sf_file.samplerate)
                src_ch = max(1, int(sf_file.channels))
                src_total = int(sf_file.frames)
                max_src_frames = int(round(limit_sec * src_sr))
                truncated = src_total > max_src_frames
                step = max(256, int(round(chunk_seconds * src_sr)))

                self.clear()
                read_so_far = 0
                while read_so_far < min(src_total, max_src_frames) and total_dst_frames < max_dst_frames:
                    take = min(step, max_src_frames - read_so_far)
                    arr = np.asarray(sf_file.read(take, dtype="float32", always_2d=True), dtype=np.float32)
                    if arr.size == 0:
                        break
                    read_so_far += int(arr.shape[0])
                    canon = normalize_to_canonical_pcm(
                        arr,
                        src_rate=src_sr,
                        src_channels=src_ch,
                        dst_rate=self.sample_rate,
                        dst_channels=self.channels,
                    )
                    remain = max_dst_frames - total_dst_frames
                    if canon.shape[0] > remain:
                        canon = canon[:remain]
                        truncated = True
                    if canon.shape[0] > 0:
                        self.write(canon)
                        total_dst_frames += int(canon.shape[0])
                return total_dst_frames / float(self.sample_rate), truncated
        except Exception as sf_exc:
            if src.suffix.lower() not in (".wav", ".wave"):
                raise RuntimeError(f"无法读取音频文件 {src.name}: {sf_exc}") from sf_exc

        with wave.open(str(src), "rb") as wf:
            src_sr = int(wf.getframerate())
            src_ch = max(1, int(wf.getnchannels()))
            sw = int(wf.getsampwidth())
            src_total = int(wf.getnframes())
            max_src_frames = int(round(limit_sec * src_sr))
            truncated = src_total > max_src_frames
            dtype_map = {1: "int16", 2: "int16", 3: "int24", 4: "int32"}
            if sw not in dtype_map:
                raise ValueError(f"Unsupported WAV sample width: {sw}")
            self.clear()
            step = max(256, int(round(chunk_seconds * src_sr)))
            read_so_far = 0
            while read_so_far < min(src_total, max_src_frames) and total_dst_frames < max_dst_frames:
                take = min(step, max_src_frames - read_so_far)
                raw = wf.readframes(take)
                if not raw:
                    break
                if sw == 1:
                    u8 = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                    arr = u8[: (u8.size // src_ch) * src_ch].reshape(-1, src_ch)
                    canon = normalize_to_canonical_pcm(
                        arr,
                        src_rate=src_sr,
                        src_channels=src_ch,
                        dst_rate=self.sample_rate,
                        dst_channels=self.channels,
                    )
                else:
                    canon = normalize_to_canonical_pcm(
                        raw,
                        src_rate=src_sr,
                        src_channels=src_ch,
                        src_dtype=dtype_map[sw],
                        dst_rate=self.sample_rate,
                        dst_channels=self.channels,
                    )
                read_so_far += take
                remain = max_dst_frames - total_dst_frames
                if canon.shape[0] > remain:
                    canon = canon[:remain]
                    truncated = True
                if canon.shape[0] > 0:
                    self.write(canon)
                    total_dst_frames += int(canon.shape[0])
        return total_dst_frames / float(self.sample_rate), truncated

