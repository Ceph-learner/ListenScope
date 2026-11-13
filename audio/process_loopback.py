"""Windows WASAPI Process Loopback backend (primary Phase 1 capture path)."""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Any, Callable, Optional

import numpy as np
import psutil

from core.config import AudioConfig, TargetHardwareSpec
from core.models import CaptureMode, CaptureStats

from .capture_base import AudioCaptureBackend, CaptureStatsTracker
from .pcm_utils import normalize_to_canonical_pcm

logger = logging.getLogger(__name__)


class WasapiProcessLoopbackBackend(AudioCaptureBackend):
    """Per-process WASAPI loopback capture backed by `proctap` on Windows.

    Features:
    - Verifies whether native capture is genuinely process-specific (`is_process_specific()`)
      and raises/warns explicitly if Windows fell back to system-wide loopback.
    - Computes true frame counts from PCM byte lengths (48kHz, 2ch, float32).
    - Monitors target process liveness via `psutil` so closing QQ Music (or any target)
      stops capture cleanly without crashing.
    - Detects pause/silence cleanly and prevents unbounded queueing via `BoundedAudioQueue`.
    """

    def __init__(
        self,
        pid: int,
        process_name: str,
        *,
        audio_config: Optional[AudioConfig] = None,
        resample_quality: str = "best",
        tap_factory: Optional[Callable[..., Any]] = None,
        pid_exists_fn: Optional[Callable[[int], bool]] = None,
        allow_non_windows: bool = False,
    ) -> None:
        super().__init__(audio_config=audio_config)
        self._pid = int(pid)
        self._process_name = process_name
        self._resample_quality = resample_quality
        self._tap_factory = tap_factory
        self._pid_exists_fn = pid_exists_fn or psutil.pid_exists
        self._allow_non_windows = allow_non_windows

        self._tap: Any = None
        self._cached_fmt: dict[str, Any] = {}
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._timing_lock = threading.Lock()
        self._last_chunk_time: float = 0.0
        self._was_active_audio: bool = False

        self._stats = CaptureStatsTracker(
            mode=CaptureMode.PROCESS_LOOPBACK,
            pid=self._pid,
            process_name=self._process_name,
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
            dtype=self.audio_config.dtype,
            queue_maxsize=self.audio_config.capture_queue_maxsize,
        )

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def is_running(self) -> bool:
        with self._lock:
            return (
                not self._stop_event.is_set()
                and self._tap is not None
                and bool(getattr(self._tap, "is_running", True))
            )

    def start(self) -> None:
        with self._lock:
            if self._tap is not None:
                return

            if not self._allow_non_windows and platform.system() != "Windows":
                raise RuntimeError(
                    f"WASAPI Process Loopback 需要 Windows Build "
                    f"{TargetHardwareSpec().min_windows_build_for_process_loopback}+（当前系统为 {platform.system()}）。"
                )

            if not self._pid_exists_fn(self._pid):
                raise RuntimeError(f"目标进程 PID={self._pid} ({self._process_name}) 不存在。")

            self.queue.reset_open()
            self._stop_event.clear()
            with self._timing_lock:
                self._last_chunk_time = time.monotonic()
                self._was_active_audio = False

            if self._tap_factory is not None:
                tap = self._tap_factory(
                    pid=self._pid,
                    on_data=self._on_proctap_data,
                    resample_quality=self._resample_quality,
                )
            else:
                try:
                    from proctap import ProcessAudioCapture  # type: ignore[import-not-found]
                except ImportError as exc:
                    self.queue.close()
                    raise RuntimeError(
                        "未安装 proc-tap，无法启动 WASAPI Process Loopback。请运行: pip install proc-tap"
                    ) from exc

                try:
                    tap = ProcessAudioCapture(
                        pid=self._pid,
                        on_data=self._on_proctap_data,
                        resample_quality=self._resample_quality,  # type: ignore[arg-type]
                    )
                except Exception as exc:
                    self.queue.close()
                    raise RuntimeError(f"初始化 WASAPI Process Loopback 失败 (PID={self._pid}): {exc}") from exc

            # Inspect native process-specific flag & cache format before audio callback begins firing
            is_proc_specific = self._check_is_process_specific(tap)
            try:
                fmt = tap.get_format()
                self._cached_fmt = dict(fmt) if isinstance(fmt, dict) else {}
            except Exception:
                self._cached_fmt = {}

            if is_proc_specific is False:
                self._stats.set_mode_and_warning(
                    CaptureMode.SYSTEM_LOOPBACK,
                    "⚠️ 底层 WASAPI 退回全系统 Loopback：其他应用声音可能被混入。",
                )
            else:
                self._stats.set_mode_and_warning(CaptureMode.PROCESS_LOOPBACK, None)

            try:
                tap.start()
            except Exception as exc:
                try:
                    if hasattr(tap, "close"):
                        tap.close()
                    elif hasattr(tap, "stop"):
                        tap.stop()
                except Exception:
                    pass
                self._cached_fmt = {}
                self.queue.close()
                self._stats.set_running(False)
                self._stats.set_error(f"启动 Process Loopback 失败: {exc}")
                raise RuntimeError(f"启动 WASAPI Process Loopback 失败: {exc}") from exc

            # Re-query format and native loopback isolation AFTER tap.start(), as WASAPI format/fallback
            # may finalize only once the capture stream starts.
            try:
                post_fmt = tap.get_format()
                if isinstance(post_fmt, dict) and post_fmt:
                    self._cached_fmt = dict(post_fmt)
            except Exception:
                pass

            post_proc_specific = self._check_is_process_specific(tap)
            if post_proc_specific is not None:
                is_proc_specific = post_proc_specific
            if is_proc_specific is False:
                self._stats.set_mode_and_warning(
                    CaptureMode.SYSTEM_LOOPBACK,
                    "⚠️ 底层 WASAPI 退回全系统 Loopback：其他应用声音可能被混入。",
                )
            elif is_proc_specific is True:
                self._stats.set_mode_and_warning(CaptureMode.PROCESS_LOOPBACK, None)

            self._tap = tap
            self._stats.set_error(None)
            self._stats.set_running(True)

            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name=f"ListenScope-ProcLoopbackWatchdog-{self._pid}",
                daemon=True,
            )
            self._watchdog_thread.start()

    def _get_native_handle(self, tap: Any) -> Any:
        backend = getattr(tap, "_backend", None)
        return getattr(backend, "_native", None) if backend is not None else None

    def _check_is_process_specific(self, tap: Any) -> Optional[bool]:
        native = self._get_native_handle(tap)
        fn = getattr(native, "is_process_specific", None) if native is not None else None
        if callable(fn):
            try:
                return bool(fn())
            except Exception:
                return None
        return None

    def _on_proctap_data(self, pcm_bytes: bytes, _frames_ignored: int) -> None:
        """Callback invoked from ProcTap worker thread. Must never crash or allocate unbounded memory."""
        if self._stop_event.is_set() or not pcm_bytes:
            return

        try:
            now = time.monotonic()
            with self._timing_lock:
                was_active = self._was_active_audio
                last_chunk_t = self._last_chunk_time
            # Measure unexpected gap while audio was actively flowing (vs normal pause)
            if was_active and last_chunk_t > 0.0:
                gap_ms = (now - last_chunk_t) * 1000.0
                if gap_ms > self.audio_config.underrun_gap_threshold_ms:
                    self._stats.record_underrun(1)

            # Use cached format captured cleanly in start() (avoids lock-free _tap deref during teardown)
            fmt = self._cached_fmt
            src_rate = max(1, int(fmt.get("sample_rate", self.audio_config.sample_rate) or self.audio_config.sample_rate))
            src_channels = max(1, int(fmt.get("channels", self.audio_config.channels) or self.audio_config.channels))
            src_dtype = str(fmt.get("sample_format", self.audio_config.dtype) or self.audio_config.dtype)

            if (
                src_rate == self.audio_config.sample_rate
                and src_channels == self.audio_config.channels
                and src_dtype == "float32"
            ):
                # View bytes directly, then copy single bounded chunk into queue
                usable_b = (len(pcm_bytes) // 4) * 4
                if usable_b == 0:
                    return
                arr = np.frombuffer(memoryview(pcm_bytes)[:usable_b], dtype=np.float32)
                usable = (arr.size // 2) * 2
                if usable == 0:
                    return
                chunk = np.array(arr[:usable].reshape(-1, 2), dtype=np.float32, copy=True)
                if not np.all(np.isfinite(chunk)):
                    chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
            else:
                chunk = normalize_to_canonical_pcm(
                    pcm_bytes,
                    src_rate=src_rate,
                    src_channels=src_channels,
                    src_dtype=src_dtype,
                    dst_rate=self.audio_config.sample_rate,
                    dst_channels=self.audio_config.channels,
                )

            if chunk.shape[0] == 0:
                return

            self.queue.put_drop_oldest(chunk)
            is_silent = self._stats.record_chunk(
                chunk,
                queue_size=len(self.queue),
                overruns=self.queue.overruns,
            )
            with self._timing_lock:
                self._was_active_audio = not is_silent
                self._last_chunk_time = now
        except Exception as exc:
            logger.exception("Error processing WASAPI process loopback chunk")
            self._stats.set_error(f"音频块处理异常: {exc}")

    def _watchdog_loop(self) -> None:
        """Monitors target process exit, native WASAPI errors, and decays live meter during pause/silence."""
        last_native_err: str = ""
        while not self._stop_event.wait(timeout=0.25):
            try:
                if not self._pid_exists_fn(self._pid):
                    msg = f"目标进程已退出 (PID={self._pid}, {self._process_name})，已安全停止捕获。"
                    logger.info(msg)
                    self._stats.set_error(msg)
                    self._stop_internal(clear_error=False)
                    break

                with self._lock:
                    tap_obj = self._tap
                    tap_running = bool(getattr(tap_obj, "is_running", True)) if tap_obj is not None else False
                    native = self._get_native_handle(tap_obj) if tap_obj is not None else None
                err_fn = getattr(native, "get_last_error", None) if native is not None else None
                if callable(err_fn):
                    try:
                        err = str(err_fn() or "").strip()
                        if err and err != last_native_err:
                            last_native_err = err
                            self._stats.set_error(f"底层 WASAPI 提示: {err}")
                    except Exception:
                        pass

                if tap_obj is not None and not tap_running:
                    msg = (
                        f"WASAPI Process Loopback 捕获流已断开或结束 ({last_native_err})"
                        if last_native_err
                        else f"WASAPI Process Loopback 捕获流已断开或结束 (PID={self._pid})，已自动停止捕获。"
                    )
                    logger.warning(msg)
                    self._stats.set_error(msg)
                    self._stop_internal(clear_error=False)
                    break

                # If paused and WASAPI stops pushing packets for >350ms, decay meter to silence
                now = time.monotonic()
                decay_needed = False
                with self._timing_lock:
                    if self._last_chunk_time > 0.0 and (now - self._last_chunk_time) > 0.35:
                        self._was_active_audio = False
                        decay_needed = True
                if decay_needed:
                    silent_stub = np.empty((0, self.audio_config.channels), dtype=np.float32)
                    self._stats.record_chunk(
                        silent_stub,
                        queue_size=len(self.queue),
                        overruns=self.queue.overruns,
                    )
            except Exception as exc:
                logger.debug("Watchdog loop error: %s", exc)

    def _stop_internal(self, *, clear_error: bool) -> None:
        self._stop_event.set()
        with self._lock:
            tap = self._tap
            self._tap = None
        if tap is not None:
            try:
                if hasattr(tap, "close"):
                    tap.close()
                elif hasattr(tap, "stop"):
                    tap.stop()
            except Exception as exc:
                logger.warning("Error closing ProcTap backend: %s", exc)
        self.queue.close()
        self._stats.set_running(False)
        if clear_error:
            self._stats.set_error(None)

    def stop(self) -> None:
        self._stop_internal(clear_error=False)
        thread = self._watchdog_thread
        self._watchdog_thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def get_stats(self) -> CaptureStats:
        self._stats.sync_queue_state(
            queue_size=len(self.queue),
            overruns=self.queue.overruns,
        )
        return self._stats.snapshot()
