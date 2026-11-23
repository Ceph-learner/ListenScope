"""Fallback Windows System WASAPI Loopback backend + synthetic test simulation backend."""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Any, Callable, Optional

import numpy as np

from core.config import AudioConfig
from core.models import CaptureMode, CaptureStats

from .capture_base import AudioCaptureBackend, CaptureStatsTracker
from .pcm_utils import normalize_to_canonical_pcm

logger = logging.getLogger(__name__)

SYSTEM_LOOPBACK_WARNING = "⚠️ 当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。"


class WasapiSystemLoopbackBackend(AudioCaptureBackend):
    """Fallback Windows system-wide WASAPI loopback using PyAudioWPatch.

    Always surfaces `SYSTEM_LOOPBACK_WARNING` so the user knows other apps' audio
    may be mixed in. Handles playback device switches with bounded reconnects.
    """

    def __init__(
        self,
        *,
        audio_config: Optional[AudioConfig] = None,
        pyaudio_factory: Optional[Callable[[], Any]] = None,
        max_device_reconnects: int = 3,
        allow_non_windows: bool = False,
    ) -> None:
        super().__init__(audio_config=audio_config)
        self._pyaudio_factory = pyaudio_factory
        self._max_device_reconnects = max_device_reconnects
        self._allow_non_windows = allow_non_windows

        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._pa: Any = None
        self._stream: Any = None
        self._device_name = "System Default WASAPI Loopback"

        self._stats = CaptureStatsTracker(
            mode=CaptureMode.SYSTEM_LOOPBACK,
            pid=None,
            process_name=self._device_name,
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
            dtype=self.audio_config.dtype,
            queue_maxsize=self.audio_config.capture_queue_maxsize,
        )
        self._stats.set_mode_and_warning(CaptureMode.SYSTEM_LOOPBACK, SYSTEM_LOOPBACK_WARNING)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def _create_pa(self) -> Any:
        if self._pyaudio_factory is not None:
            return self._pyaudio_factory()
        try:
            import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "未安装 PyAudioWPatch，无法启用系统 WASAPI Loopback fallback。请运行: pip install PyAudioWPatch"
            ) from exc
        return pyaudio.PyAudio()

    def _open_default_loopback(self) -> tuple[Any, Any, dict[str, Any], int, str]:
        pa = self._create_pa()
        try:
            default_loopback = pa.get_default_wasapi_loopback()
            if not default_loopback:
                raise RuntimeError("未找到默认 WASAPI Loopback 输出设备。")
            src_rate = int(default_loopback["defaultSampleRate"])
            raw_ch = int(default_loopback.get("maxInputChannels") or 0) or int(
                default_loopback.get("maxOutputChannels") or 0
            )
            src_channels = max(1, raw_ch)
            frames_per_buffer = max(256, int(src_rate * 0.02))  # ~20ms chunks

            pa_f32 = getattr(pa, "paFloat32", None)
            pa_i16 = getattr(pa, "paInt16", None)
            if pa_f32 is None or pa_i16 is None:
                try:
                    import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]

                    pa_f32 = pa_f32 if pa_f32 is not None else pyaudio.paFloat32
                    pa_i16 = pa_i16 if pa_i16 is not None else pyaudio.paInt16
                except Exception:
                    pa_f32 = 1 if pa_f32 is None else pa_f32
                    pa_i16 = 8 if pa_i16 is None else pa_i16

            try:
                stream = pa.open(
                    format=pa_f32,
                    channels=src_channels,
                    rate=src_rate,
                    frames_per_buffer=frames_per_buffer,
                    input=True,
                    input_device_index=int(default_loopback["index"]),
                )
                return pa, stream, default_loopback, frames_per_buffer, "float32"
            except Exception as f32_exc:
                logger.info("WASAPI system loopback float32 open failed (%s); falling back to int16", f32_exc)
                stream = pa.open(
                    format=pa_i16,
                    channels=src_channels,
                    rate=src_rate,
                    frames_per_buffer=frames_per_buffer,
                    input=True,
                    input_device_index=int(default_loopback["index"]),
                )
                return pa, stream, default_loopback, frames_per_buffer, "int16"
        except Exception:
            try:
                pa.terminate()
            except Exception:
                pass
            raise

    @staticmethod
    def _close_pa_pair(pa: Any, stream: Any) -> None:
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass

    def start(self) -> None:
        if self.is_running:
            return
        if not self._allow_non_windows and platform.system() != "Windows":
            raise RuntimeError(
                f"系统 WASAPI Loopback 仅支持 Windows (当前系统为 {platform.system()})。"
            )

        self.queue.reset_open()
        self._stop_event.clear()
        pa, stream, dev_info, frames_per_buffer, src_dtype = self._open_default_loopback()
        with self._lock:
            self._pa = pa
            self._stream = stream
        self._device_name = str(dev_info.get("name", self._device_name))
        self._stats.set_error(None)
        self._stats.set_running(True)

        self._thread = threading.Thread(
            target=self._capture_loop,
            args=(dev_info, frames_per_buffer, src_dtype),
            name="ListenScope-SystemLoopback",
            daemon=True,
        )
        self._thread.start()

    def _close_stream(self) -> None:
        with self._lock:
            stream = self._stream
            pa = self._pa
            self._stream = None
            self._pa = None
        self._close_pa_pair(pa, stream)

    def _capture_loop(self, dev_info: dict[str, Any], frames_per_buffer: int, src_dtype: str = "float32") -> None:
        src_rate = int(dev_info["defaultSampleRate"])
        raw_ch = int(dev_info.get("maxInputChannels") or 0) or int(dev_info.get("maxOutputChannels") or 0)
        src_channels = max(1, raw_ch)
        reconnects = 0
        clean_chunks_since_reconnect = 0
        has_transient_reconnect_notice = False

        while not self._stop_event.is_set():
            with self._lock:
                stream = self._stream
            if stream is None:
                break
            try:
                raw_bytes = stream.read(frames_per_buffer, exception_on_overflow=False)
                reconnects = 0
                if has_transient_reconnect_notice:
                    clean_chunks_since_reconnect += 1
                    if clean_chunks_since_reconnect >= 25:
                        self._stats.set_error(None)
                        has_transient_reconnect_notice = False
                chunk = normalize_to_canonical_pcm(
                    raw_bytes,
                    src_rate=src_rate,
                    src_channels=src_channels,
                    src_dtype=src_dtype,
                    dst_rate=self.audio_config.sample_rate,
                    dst_channels=self.audio_config.channels,
                )
                if chunk.shape[0] > 0:
                    self.queue.put_drop_oldest(chunk)
                    self._stats.record_chunk(
                        chunk,
                        queue_size=len(self.queue),
                        overruns=self.queue.overruns,
                    )
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("WASAPI system loopback read error (device switch?): %s", exc)
                self._stats.record_underrun(1)
                self._close_stream()
                clean_chunks_since_reconnect = 0
                reconnected = False
                while reconnects < self._max_device_reconnects and not self._stop_event.is_set():
                    reconnects += 1
                    if self._stop_event.wait(timeout=0.35 * reconnects):
                        break
                    if self._stop_event.is_set():
                        break
                    try:
                        new_pa, new_stream, new_dev, frames_per_buffer, src_dtype = self._open_default_loopback()
                        if self._stop_event.is_set():
                            self._close_pa_pair(new_pa, new_stream)
                            break
                        with self._lock:
                            if self._stop_event.is_set():
                                self._close_pa_pair(new_pa, new_stream)
                                break
                            self._pa = new_pa
                            self._stream = new_stream
                        src_rate = int(new_dev["defaultSampleRate"])
                        new_ch = int(new_dev.get("maxInputChannels") or 0) or int(new_dev.get("maxOutputChannels") or 0)
                        src_channels = max(1, new_ch)
                        self._device_name = str(new_dev.get("name", self._device_name))
                        self._stats.set_process_name(self._device_name)
                        self._stats.set_error(f"检测到播放设备切换，已重连至: {self._device_name}")
                        has_transient_reconnect_notice = True
                        clean_chunks_since_reconnect = 0
                        reconnected = True
                        break
                    except Exception as rec_exc:
                        has_transient_reconnect_notice = False
                        self._stats.set_error(f"播放设备重连失败 ({reconnects}/{self._max_device_reconnects}): {rec_exc}")
                if self._stop_event.is_set():
                    break
                if not reconnected:
                    has_transient_reconnect_notice = False
                    self._stats.set_error(f"播放设备中断且重连超过 {self._max_device_reconnects} 次: {exc}")
                    break

        self._close_stream()
        self.queue.close()
        self._stats.set_running(False)

    def stop(self) -> None:
        self._stop_event.set()
        self.queue.close()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._close_stream()
        self._stats.set_running(False)

    def get_stats(self) -> CaptureStats:
        self._stats.sync_queue_state(
            queue_size=len(self.queue),
            overruns=self.queue.overruns,
        )
        return self._stats.snapshot()


class SyntheticSimulationBackend(AudioCaptureBackend):
    """Non-Windows synthetic PCM generator ONLY for verifying pipeline math & lifecycle.

    Explicitly marks CaptureMode.SYNTHETIC_SIMULATION and never masquerades as real
    Windows WASAPI capture.
    """

    def __init__(
        self,
        *,
        pattern: str = "switching",  # sine | silence | switching
        audio_config: Optional[AudioConfig] = None,
    ) -> None:
        super().__init__(audio_config=audio_config)
        self._pattern = pattern
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stats = CaptureStatsTracker(
            mode=CaptureMode.SYNTHETIC_SIMULATION,
            pid=0,
            process_name=f"SyntheticSignal({pattern})",
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
            dtype=self.audio_config.dtype,
            queue_maxsize=self.audio_config.capture_queue_maxsize,
        )
        self._stats.set_mode_and_warning(
            CaptureMode.SYNTHETIC_SIMULATION,
            "🧪 合成测试信号模式（非 Windows 真机 WASAPI 捕获）。",
        )

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start(self) -> None:
        if self.is_running:
            return
        self.queue.reset_open()
        self._stop_event.clear()
        self._stats.set_running(True)
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ListenScope-SyntheticSim",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        sr = self.audio_config.sample_rate
        frames = self.audio_config.default_chunk_frames
        dt = frames / float(sr)
        phase = 0.0
        chunk_idx = 0
        # Preallocate single reusable time vector to avoid repeated large allocations
        t_offsets = np.arange(frames, dtype=np.float64) / float(sr)

        while not self._stop_event.is_set():
            t0 = time.monotonic()
            freq = 440.0
            amp = 0.25
            if self._pattern == "silence":
                amp = 0.0
            elif self._pattern == "switching":
                # Cycle: 2s A4 (440Hz) -> 1s pause/silence -> 2s E5 (659.25Hz)
                sec = (chunk_idx * frames) / float(sr)
                slot = sec % 5.0
                if 2.0 <= slot < 3.0:
                    amp = 0.0
                elif slot >= 3.0:
                    freq = 659.25

            if amp == 0.0:
                chunk = np.zeros((frames, self.audio_config.channels), dtype=np.float32)
            else:
                wave = (amp * np.sin(2.0 * np.pi * freq * t_offsets + phase)).astype(np.float32)
                phase = (phase + 2.0 * np.pi * freq * dt) % (2.0 * np.pi)
                chunk = np.column_stack([wave, wave]).astype(np.float32, copy=False)

            self.queue.put_drop_oldest(chunk)
            self._stats.record_chunk(
                chunk,
                queue_size=len(self.queue),
                overruns=self.queue.overruns,
            )
            chunk_idx += 1
            elapsed = time.monotonic() - t0
            sleep_for = max(0.0, dt - elapsed)
            if sleep_for > 0:
                self._stop_event.wait(timeout=sleep_for)

        self.queue.close()
        self._stats.set_running(False)

    def stop(self) -> None:
        self._stop_event.set()
        self.queue.close()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._stats.set_running(False)

    def get_stats(self) -> CaptureStats:
        self._stats.sync_queue_state(
            queue_size=len(self.queue),
            overruns=self.queue.overruns,
        )
        return self._stats.snapshot()
