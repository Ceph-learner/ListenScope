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
from .pcm_utils import StreamingResampler, normalize_to_canonical_pcm

logger = logging.getLogger(__name__)

SYSTEM_LOOPBACK_WARNING = "⚠️ 当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。"


_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106


class _WindowsGuid(object):
    pass


def _make_ole32_and_guid():
    import ctypes
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _PROPERTYKEY(ctypes.Structure):
        _fields_ = [
            ("fmtid", _GUID),
            ("pid", wintypes.DWORD),
        ]

    class _PROPVARIANT(ctypes.Structure):
        _fields_ = [
            ("vt", wintypes.WORD),
            ("wReserved1", wintypes.WORD),
            ("wReserved2", wintypes.WORD),
            ("wReserved3", wintypes.WORD),
            ("pwszVal", ctypes.c_void_p),
            ("pad", ctypes.c_void_p),
        ]

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    if hasattr(ole32, "PropVariantClear"):
        ole32.PropVariantClear.argtypes = [ctypes.POINTER(_PROPVARIANT)]
        ole32.PropVariantClear.restype = ctypes.c_long
    return ole32, _GUID, _PROPERTYKEY, _PROPVARIANT


def _com_initialize_thread() -> tuple[Any, bool]:
    """Initialize COM on the current thread (COINIT_MULTITHREADED).

    Returns (ole32, should_uninit). Handles RPC_E_CHANGED_MODE gracefully.
    """
    if platform.system() != "Windows":
        return None, False
    try:
        ole32, *_ = _make_ole32_and_guid()
        hr = int(ole32.CoInitializeEx(None, 0x0))
        if hr in (0, 1):  # S_OK, S_FALSE
            return ole32, True
        if hr == _RPC_E_CHANGED_MODE:
            return ole32, False
        return ole32, False
    except Exception:
        return None, False


def _guid_from_str(guid_cls: Any, s: str) -> Any:
    import ctypes
    import uuid

    u = uuid.UUID(s)
    g = guid_cls()
    ctypes.memmove(ctypes.byref(g), u.bytes_le, 16)
    return g


def _create_mmdevice_enumerator() -> tuple[Any, int]:
    """Create Windows IMMDeviceEnumerator COM instance. Returns (enum_ptr_or_None, hr)."""
    if platform.system() != "Windows":
        return None, -1
    import ctypes

    ole32, _GUID, *_ = _make_ole32_and_guid()
    clsid_enum = _guid_from_str(_GUID, "BCDE0395-E52F-467C-8E3D-C4579291692E")
    iid_enum = _guid_from_str(_GUID, "A95664D2-9614-4F35-A746-DE8DB63617E6")
    enum_ptr = ctypes.c_void_p()
    hr = int(
        ole32.CoCreateInstance(
            ctypes.byref(clsid_enum),
            None,
            1 | 4,  # CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER
            ctypes.byref(iid_enum),
            ctypes.byref(enum_ptr),
        )
    )
    if hr != 0 or not enum_ptr.value:
        return None, hr
    return enum_ptr, hr


def _probe_windows_default_render_endpoint_detailed(
    *, initialize_com: bool = False
) -> tuple[Optional[str], str, int]:
    """Query active Windows default render endpoint ID and optional FriendlyName.

    Returns (endpoint_id_or_None, friendly_name, hresult). Never swallows HRESULT silently.
    """
    if platform.system() != "Windows":
        return None, "", -1
    ole32_to_uninit: Any = None
    should_uninit = False
    try:
        import ctypes

        ole32, _GUID, _PROPERTYKEY, _PROPVARIANT = _make_ole32_and_guid()
        if initialize_com:
            ole32_to_uninit, should_uninit = _com_initialize_thread()

        enum_ptr, hr = _create_mmdevice_enumerator()
        if enum_ptr is None:
            return None, "", hr

        vtbl_enum = ctypes.cast(enum_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        try:
            # IMMDeviceEnumerator::GetDefaultAudioEndpoint (slot 4): (this, eRender=0, eConsole=0, ppDevice)
            get_default_fn = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            )(vtbl_enum[4])
            dev_ptr = ctypes.c_void_p()
            hr = int(get_default_fn(enum_ptr, 0, 0, ctypes.byref(dev_ptr)))
            if hr != 0 or not dev_ptr.value:
                return None, "", hr
            vtbl_dev = ctypes.cast(dev_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            try:
                # IMMDevice::GetId (slot 5): (this, ppstrId)
                get_id_fn = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_wchar_p),
                )(vtbl_dev[5])
                dev_id_ptr = ctypes.c_wchar_p()
                hr_id = int(get_id_fn(dev_ptr, ctypes.byref(dev_id_ptr)))
                if hr_id != 0 or not dev_id_ptr.value:
                    return None, "", hr_id
                dev_id = str(dev_id_ptr.value)
                ole32.CoTaskMemFree(dev_id_ptr)

                friendly_name = ""
                try:
                    # IMMDevice::OpenPropertyStore (slot 4): (this, stgmAccess=0, ppProperties)
                    open_store_fn = ctypes.WINFUNCTYPE(
                        ctypes.c_long,
                        ctypes.c_void_p,
                        ctypes.c_ulong,
                        ctypes.POINTER(ctypes.c_void_p),
                    )(vtbl_dev[4])
                    store_ptr = ctypes.c_void_p()
                    if int(open_store_fn(dev_ptr, 0, ctypes.byref(store_ptr))) == 0 and store_ptr.value:
                        vtbl_store = ctypes.cast(store_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                        try:
                            # IPropertyStore::GetValue (slot 5): (this, key, pv)
                            get_val_fn = ctypes.WINFUNCTYPE(
                                ctypes.c_long,
                                ctypes.c_void_p,
                                ctypes.POINTER(_PROPERTYKEY),
                                ctypes.POINTER(_PROPVARIANT),
                            )(vtbl_store[5])
                            pkey = _PROPERTYKEY(_guid_from_str(_GUID, "A45C254E-DF1C-4EFD-8020-67D146A850E0"), 14)
                            pv = _PROPVARIANT()
                            if int(get_val_fn(store_ptr, ctypes.byref(pkey), ctypes.byref(pv))) == 0:
                                try:
                                    if pv.vt == 31 and pv.pwszVal:  # VT_LPWSTR
                                        friendly_name = str(ctypes.wstring_at(pv.pwszVal))
                                finally:
                                    if hasattr(ole32, "PropVariantClear"):
                                        ole32.PropVariantClear(ctypes.byref(pv))
                        finally:
                            release_store = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_store[2])
                            release_store(store_ptr)
                except Exception:
                    friendly_name = ""

                return dev_id, friendly_name, 0
            finally:
                release_dev = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_dev[2])
                release_dev(dev_ptr)
        finally:
            release_enum = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_enum[2])
            release_enum(enum_ptr)
    except Exception as exc:
        logger.debug("_probe_windows_default_render_endpoint_detailed failed: %s", exc)
        return None, "", -1
    finally:
        if should_uninit and ole32_to_uninit is not None:
            try:
                ole32_to_uninit.CoUninitialize()
            except Exception:
                pass


def _query_windows_default_render_endpoint(*, initialize_com: bool = True) -> Optional[tuple[str, str]]:
    """Query active Windows default render endpoint ID via IMMDeviceEnumerator (bypasses PortAudio cache)."""
    dev_id, friendly_name, _hr = _probe_windows_default_render_endpoint_detailed(initialize_com=initialize_com)
    if dev_id:
        return (dev_id, friendly_name)
    return None


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
        follow_default_device: bool = True,
        default_device_probe: Optional[Callable[[], Optional[tuple[str, str]]]] = None,
        device_poll_interval_sec: float = 0.5,
        device_switch_ttl_sec: float = 5.0,
    ) -> None:
        super().__init__(audio_config=audio_config)
        self._pyaudio_factory = pyaudio_factory
        self._max_device_reconnects = max_device_reconnects
        self._allow_non_windows = allow_non_windows
        self._follow_default_device = bool(follow_default_device)
        self._default_device_probe = default_device_probe
        self._device_poll_interval_sec = max(0.05, float(device_poll_interval_sec))
        self._device_switch_ttl_sec = max(0.05, float(device_switch_ttl_sec))

        self._stop_event = threading.Event()
        self._closing = threading.Event()
        self._device_switch_requested = threading.Event()
        self._startup_ready = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._watcher_thread: Optional[threading.Thread] = None
        self._pa: Any = None
        self._stream: Any = None
        self._device_name = "System Default WASAPI Loopback"
        self._active_dev_index: Optional[int] = None
        self._active_dev_name: str = self._device_name
        self._watcher_observed_name: str = ""
        self._current_endpoint_id: Optional[str] = None
        self._last_probe_warn_ts: dict[int, float] = {}

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
        self._closing.clear()
        self._stop_event.clear()
        self._device_switch_requested.clear()
        self._startup_ready.clear()
        self._startup_error = None
        self._current_endpoint_id = None
        self._watcher_observed_name = ""

        self._thread = threading.Thread(
            target=self._capture_loop,
            name="ListenScope-SystemLoopback",
            daemon=True,
        )
        self._thread.start()
        if not self._startup_ready.wait(timeout=5.0):
            self.stop()
            raise RuntimeError("系统 WASAPI Loopback 启动超时。")
        if self._startup_error is not None:
            err = self._startup_error
            self.stop()
            raise err

        if self._follow_default_device:
            self._watcher_thread = threading.Thread(
                target=self._device_watcher_loop,
                name="ListenScope-DefaultDeviceWatcher",
                daemon=True,
            )
            self._watcher_thread.start()

    def _close_stream(self) -> None:
        with self._lock:
            stream = self._stream
            pa = self._pa
            self._stream = None
            self._pa = None
        self._close_pa_pair(pa, stream)

    def _probe_for_watcher(self) -> tuple[Optional[str], str, int]:
        """Probe current default render endpoint ID on watcher thread (COM already initialized)."""
        if self._default_device_probe is not None:
            try:
                res = self._default_device_probe()
                if res is None:
                    return None, "", -1
                return str(res[0]) if res[0] else None, str(res[1] or ""), 0
            except Exception:
                return None, "", -1
        if platform.system() == "Windows":
            return _probe_windows_default_render_endpoint_detailed(initialize_com=False)
        return None, "", -1

    def _warn_probe_failure(self, hr: int) -> None:
        now = time.monotonic()
        last = self._last_probe_warn_ts.get(hr)
        if last is None or (now - last) >= 60.0:
            self._last_probe_warn_ts[hr] = now
            logger.warning("default endpoint probe failed hr=0x%08X", hr & 0xFFFFFFFF)

    def _device_watcher_loop(self) -> None:
        """Dedicated watcher thread that polls default render endpoint ID independently of PortAudio."""
        ole32_to_uninit: Any = None
        should_uninit = False
        if self._default_device_probe is None and platform.system() == "Windows":
            ole32_to_uninit, should_uninit = _com_initialize_thread()
        try:
            init_id, init_name, init_hr = self._probe_for_watcher()
            if init_id:
                self._current_endpoint_id = init_id
                self._watcher_observed_name = init_name
                logger.info("default endpoint watcher started id=%s", init_id[:40])
            else:
                self._current_endpoint_id = None
                if self._default_device_probe is not None or platform.system() == "Windows":
                    self._warn_probe_failure(init_hr)
                logger.info("default endpoint watcher started id=<none>")

            while not self._stop_event.wait(timeout=self._device_poll_interval_sec):
                if self._closing.is_set() or self._stop_event.is_set():
                    break
                if not self._follow_default_device or self._device_switch_requested.is_set():
                    continue
                ep_id, ep_name, hr = self._probe_for_watcher()
                if not ep_id:
                    if self._default_device_probe is not None or platform.system() == "Windows":
                        self._warn_probe_failure(hr)
                    continue
                if self._current_endpoint_id is None:
                    self._current_endpoint_id = ep_id
                    self._watcher_observed_name = ep_name
                elif ep_id != self._current_endpoint_id:
                    self._current_endpoint_id = ep_id
                    self._watcher_observed_name = ep_name
                    self._device_switch_requested.set()
        finally:
            if should_uninit and ole32_to_uninit is not None:
                try:
                    ole32_to_uninit.CoUninitialize()
                except Exception:
                    pass

    def _capture_loop(
        self,
        dev_info: Optional[dict[str, Any]] = None,
        frames_per_buffer: int = 0,
        src_dtype: str = "float32",
    ) -> None:
        if dev_info is None:
            try:
                pa, stream, dev_info, frames_per_buffer, src_dtype = self._open_default_loopback()
            except BaseException as exc:
                self._startup_error = exc
                self._startup_ready.set()
                self.queue.close()
                self._stats.set_running(False)
                return
            with self._lock:
                self._pa = pa
                self._stream = stream

        src_rate = int(dev_info["defaultSampleRate"])
        raw_ch = int(dev_info.get("maxInputChannels") or 0) or int(dev_info.get("maxOutputChannels") or 0)
        src_channels = max(1, raw_ch)
        current_dev_index: Optional[int] = int(dev_info["index"]) if "index" in dev_info and dev_info["index"] is not None else None
        current_dev_name: str = str(dev_info.get("name", self._device_name))
        with self._lock:
            self._active_dev_index = current_dev_index
            self._active_dev_name = current_dev_name
        self._device_name = current_dev_name
        self._stats.set_process_name(self._device_name)
        self._stats.set_device_switch_message(None)
        self._stats.set_error(None)
        self._stats.set_running(True)
        self._startup_ready.set()

        reconnects = 0
        clean_chunks_since_reconnect = 0
        has_transient_reconnect_notice = False
        resampler: Optional[StreamingResampler] = (
            StreamingResampler(src_rate, self.audio_config.sample_rate, self.audio_config.channels)
            if src_rate != self.audio_config.sample_rate
            else None
        )

        try:
            while not self._stop_event.is_set() and not self._closing.is_set():
                with self._lock:
                    stream = self._stream
                if stream is None:
                    break
                try:
                    if self._follow_default_device and self._device_switch_requested.is_set():
                        raise RuntimeError("DEFAULT_DEVICE_CHANGED")
                    read_avail_fn = getattr(stream, "get_read_available", None)
                    if callable(read_avail_fn):
                        while not self._stop_event.is_set() and not self._closing.is_set():
                            if self._follow_default_device and self._device_switch_requested.is_set():
                                raise RuntimeError("DEFAULT_DEVICE_CHANGED")
                            if int(read_avail_fn()) >= frames_per_buffer:
                                break
                            if self._stop_event.wait(timeout=0.01):
                                break
                        if self._closing.is_set() or self._stop_event.is_set():
                            break
                        if self._follow_default_device and self._device_switch_requested.is_set():
                            raise RuntimeError("DEFAULT_DEVICE_CHANGED")
                    raw_bytes = stream.read(frames_per_buffer, exception_on_overflow=False)
                    if self._closing.is_set() or self._stop_event.is_set():
                        break
                    if self._follow_default_device and self._device_switch_requested.is_set():
                        raise RuntimeError("DEFAULT_DEVICE_CHANGED")
                    reconnects = 0
                    if has_transient_reconnect_notice:
                        clean_chunks_since_reconnect += 1
                        if clean_chunks_since_reconnect >= 25:
                            self._stats.set_error(None)
                            has_transient_reconnect_notice = False
                    if resampler is not None:
                        decoded = normalize_to_canonical_pcm(
                            raw_bytes,
                            src_rate=src_rate,
                            src_channels=src_channels,
                            src_dtype=src_dtype,
                            dst_rate=src_rate,
                            dst_channels=self.audio_config.channels,
                        )
                        chunk = resampler.process(decoded)
                    else:
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
                    if self._stop_event.is_set() or self._closing.is_set():
                        break
                    is_device_switch = str(exc) == "DEFAULT_DEVICE_CHANGED" or self._device_switch_requested.is_set()
                    old_dev_name = current_dev_name
                    if is_device_switch:
                        logger.info("检测到默认输出设备变更，正在无感切换 WASAPI Loopback 设备...")
                    else:
                        logger.warning("WASAPI system loopback read error (device switch?): %s", exc)
                        self._stats.record_underrun(1)
                    self._close_stream()
                    self._device_switch_requested.clear()
                    clean_chunks_since_reconnect = 0
                    if resampler is not None:
                        resampler.reset()
                    reconnected = False
                    while reconnects < self._max_device_reconnects and not self._stop_event.is_set() and not self._closing.is_set():
                        reconnects += 1
                        wait_sec = 0.05 if (is_device_switch and reconnects == 1) else 0.35 * reconnects
                        if self._stop_event.wait(timeout=wait_sec):
                            break
                        if self._stop_event.is_set() or self._closing.is_set():
                            break
                        try:
                            new_pa, new_stream, new_dev, frames_per_buffer, src_dtype = self._open_default_loopback()
                            if self._stop_event.is_set() or self._closing.is_set():
                                self._close_pa_pair(new_pa, new_stream)
                                break
                            src_rate = int(new_dev["defaultSampleRate"])
                            new_ch = int(new_dev.get("maxInputChannels") or 0) or int(new_dev.get("maxOutputChannels") or 0)
                            src_channels = max(1, new_ch)
                            current_dev_index = int(new_dev["index"]) if "index" in new_dev and new_dev["index"] is not None else None
                            current_dev_name = str(new_dev.get("name") or self._watcher_observed_name or self._device_name)
                            with self._lock:
                                if self._stop_event.is_set() or self._closing.is_set():
                                    self._close_pa_pair(new_pa, new_stream)
                                    break
                                self._pa = new_pa
                                self._stream = new_stream
                                self._active_dev_index = current_dev_index
                                self._active_dev_name = current_dev_name
                            if src_rate != self.audio_config.sample_rate:
                                if resampler is not None and resampler.src_rate == src_rate:
                                    resampler.reset()
                                else:
                                    resampler = StreamingResampler(
                                        src_rate, self.audio_config.sample_rate, self.audio_config.channels
                                    )
                            else:
                                resampler = None
                            self._device_name = current_dev_name
                            self._stats.set_process_name(self._device_name)
                            if is_device_switch:
                                self._stats.set_error(None)
                                self._stats.set_device_switch_message(
                                    f"已切换到 {self._device_name}",
                                    ttl_sec=self._device_switch_ttl_sec,
                                )
                                has_transient_reconnect_notice = False
                                logger.info("loopback default device changed old=%s new=%s", old_dev_name, self._device_name)
                            else:
                                self._stats.set_error(f"检测到播放设备切换，已重连至: {self._device_name}")
                                has_transient_reconnect_notice = True
                                if current_dev_name != old_dev_name:
                                    self._stats.set_device_switch_message(
                                        f"已切换到 {self._device_name}",
                                        ttl_sec=self._device_switch_ttl_sec,
                                    )
                                    logger.info("loopback default device changed old=%s new=%s", old_dev_name, self._device_name)
                            clean_chunks_since_reconnect = 0
                            reconnected = True
                            break
                        except Exception as rec_exc:
                            has_transient_reconnect_notice = False
                            logger.warning("播放设备重连尝试失败 (%d/%d): %s", reconnects, self._max_device_reconnects, rec_exc)
                    if self._stop_event.is_set() or self._closing.is_set():
                        break
                    if not reconnected:
                        has_transient_reconnect_notice = False
                        self._stats.set_error(f"播放设备中断且重连超过 {self._max_device_reconnects} 次: {exc}")
                        break
        finally:
            self._close_stream()
            self.queue.close()
            self._stats.set_running(False)

    def stop(self) -> None:
        self._closing.set()
        self._stop_event.set()
        self.queue.close()
        watcher = self._watcher_thread
        self._watcher_thread = None
        if watcher is not None and watcher.is_alive() and watcher is not threading.current_thread():
            watcher.join(timeout=0.5)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
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


def _run_probe_default_cli(seconds: float = 15.0) -> int:
    """Print Windows default render endpoint ID, name, and HRESULT once per second."""
    duration = max(1, int(round(seconds)))
    ole32_to_uninit, should_uninit = _com_initialize_thread()
    try:
        for i in range(duration):
            now_txt = time.strftime("%H:%M:%S")
            dev_id, friendly_name, hr = _probe_windows_default_render_endpoint_detailed(initialize_com=False)
            print(
                f"[{now_txt}] hr=0x{(hr & 0xFFFFFFFF):08X} id={dev_id or '<none>'} name={friendly_name or '<unknown>'}",
                flush=True,
            )
            if i + 1 < duration:
                time.sleep(1.0)
    finally:
        if should_uninit and ole32_to_uninit is not None:
            try:
                ole32_to_uninit.CoUninitialize()
            except Exception:
                pass
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="WASAPI System Loopback diagnostics")
    parser.add_argument("--probe-default", action="store_true", help="Poll default render endpoint ID every 1s")
    parser.add_argument("--seconds", type=float, default=15.0, help="Duration in seconds for --probe-default")
    args = parser.parse_args(argv)
    if args.probe_default:
        return _run_probe_default_cli(seconds=args.seconds)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
