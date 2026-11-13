"""Base capture interface, bounded audio queue, and rolling capture statistics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
import threading
import time
from typing import Optional

import numpy as np

from core.config import AudioConfig
from core.models import CaptureMode, CaptureStats

from .pcm_utils import DBFS_FLOOR, compute_rms_and_peak


class BoundedAudioQueue:
    """Thread-safe fixed-capacity PCM chunk queue that drops oldest chunks on overflow.

    Strictly forbids unbounded buffering; tracks overrun count whenever a full
    queue causes an old chunk to be evicted.
    """

    def __init__(self, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("BoundedAudioQueue maxsize must be positive")
        self._maxsize = maxsize
        self._buf: deque[np.ndarray] = deque()
        self._cond = threading.Condition()
        self._overruns = 0
        self._dropped_frames = 0
        self._closed = False

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def overruns(self) -> int:
        with self._cond:
            return self._overruns

    @property
    def dropped_frames(self) -> int:
        with self._cond:
            return self._dropped_frames

    def __len__(self) -> int:
        with self._cond:
            return len(self._buf)

    def put_drop_oldest(self, chunk: np.ndarray) -> bool:
        """Push a chunk; evict the oldest chunk if at capacity.

        Returns True if pushed without eviction, False if an old chunk was evicted.
        """
        with self._cond:
            if self._closed:
                return False
            evicted = False
            while len(self._buf) >= self._maxsize:
                old = self._buf.popleft()
                self._overruns += 1
                self._dropped_frames += int(old.shape[0]) if old.ndim >= 1 else 0
                evicted = True
            self._buf.append(chunk)
            self._cond.notify()
            return not evicted

    def get(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        with self._cond:
            if not self._buf and not self._closed:
                self._cond.wait(timeout=timeout)
            if not self._buf:
                return None
            return self._buf.popleft()

    def clear(self) -> None:
        with self._cond:
            self._buf.clear()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def reset_open(self) -> None:
        with self._cond:
            self._closed = False
            self._buf.clear()


class CaptureStatsTracker:
    """Thread-safe rolling statistics tracker for real-time audio capture PoC."""

    def __init__(
        self,
        *,
        mode: CaptureMode,
        pid: Optional[int],
        process_name: str,
        sample_rate: int,
        channels: int,
        dtype: str,
        queue_maxsize: int,
        silence_threshold_dbfs: float = -70.0,
        fps_window_sec: float = 1.0,
        max_fps_events: int = 512,
    ) -> None:
        self._lock = threading.Lock()
        self._mode = mode
        self._pid = pid
        self._process_name = process_name
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._queue_maxsize = queue_maxsize
        self._silence_threshold_dbfs = silence_threshold_dbfs
        self._fps_window_sec = fps_window_sec

        # Bounded sliding window of (monotonic_time, frame_count)
        self._fps_events: deque[tuple[float, int]] = deque(maxlen=max_fps_events)

        self._rms_linear = 0.0
        self._rms_dbfs = DBFS_FLOOR
        self._peak_linear = 0.0
        self._peak_dbfs = DBFS_FLOOR
        self._total_frames = 0
        self._total_chunks = 0
        self._buffer_underruns = 0
        self._buffer_overruns = 0
        self._queue_size = 0
        self._is_silent = True
        self._is_running = False
        self._warning_message: Optional[str] = None
        self._last_error: Optional[str] = None

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._is_running = running

    def set_mode_and_warning(self, mode: CaptureMode, warning_message: Optional[str]) -> None:
        with self._lock:
            self._mode = mode
            self._warning_message = warning_message

    def set_error(self, error_message: Optional[str]) -> None:
        with self._lock:
            self._last_error = error_message

    def record_chunk(self, pcm_f32: np.ndarray, *, queue_size: int, overruns: int) -> None:
        num_frames = int(pcm_f32.shape[0]) if pcm_f32.ndim >= 1 else 0
        rms_lin, rms_db, peak_lin, peak_db = compute_rms_and_peak(pcm_f32)
        now = time.monotonic()

        with self._lock:
            self._rms_linear = rms_lin
            self._rms_dbfs = rms_db
            self._peak_linear = peak_lin
            self._peak_dbfs = peak_db
            self._total_frames += num_frames
            self._total_chunks += 1
            self._queue_size = queue_size
            self._buffer_overruns = overruns
            self._is_silent = rms_db < self._silence_threshold_dbfs
            self._fps_events.append((now, num_frames))

    def record_underrun(self, count: int = 1) -> None:
        with self._lock:
            self._buffer_underruns += max(0, count)

    def sync_queue_state(self, *, queue_size: int, overruns: int) -> None:
        with self._lock:
            self._queue_size = queue_size
            self._buffer_overruns = overruns

    def snapshot(self) -> CaptureStats:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self._fps_window_sec
            while self._fps_events and self._fps_events[0][0] < cutoff:
                self._fps_events.popleft()

            window_frames = sum(frames for _, frames in self._fps_events)
            if len(self._fps_events) >= 2:
                span = max(0.05, now - self._fps_events[0][0])
                fps = window_frames / min(self._fps_window_sec, span)
            elif len(self._fps_events) == 1:
                fps = window_frames / self._fps_window_sec
            else:
                fps = 0.0

            return CaptureStats(
                mode=self._mode,
                pid=self._pid,
                process_name=self._process_name,
                sample_rate=self._sample_rate,
                channels=self._channels,
                dtype=self._dtype,
                rms_linear=self._rms_linear,
                rms_dbfs=self._rms_dbfs,
                peak_linear=self._peak_linear,
                peak_dbfs=self._peak_dbfs,
                frames_per_sec=fps,
                total_frames=self._total_frames,
                total_chunks=self._total_chunks,
                buffer_underruns=self._buffer_underruns,
                buffer_overruns=self._buffer_overruns,
                queue_size=self._queue_size,
                queue_maxsize=self._queue_maxsize,
                is_silent=self._is_silent,
                is_running=self._is_running,
                warning_message=self._warning_message,
                last_error=self._last_error,
            )


class AudioCaptureBackend(ABC):
    """Abstract base class for Phase 1+ audio capture backends."""

    def __init__(self, audio_config: Optional[AudioConfig] = None) -> None:
        self.audio_config = audio_config or AudioConfig()
        self.queue = BoundedAudioQueue(self.audio_config.capture_queue_maxsize)

    @property
    @abstractmethod
    def is_running(self) -> bool:
        ...

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def get_stats(self) -> CaptureStats:
        ...

    def read_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        chunk = self.queue.get(timeout=timeout)
        return chunk
