"""Fallback Windows System WASAPI Loopback backend + synthetic test simulation backend."""

from __future__ import annotations

import logging
from pathlib import Path
import platform
import sys
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


def get_portaudio_runtime_info() -> dict[str, Any]:
    """Return PyAudioWPatch / PortAudio version and binary file metadata safely."""
    info: dict[str, Any] = {
        "pyaudiowpatch_version": "",
        "portaudio_version_text": "",
        "portaudio_pyd_path": "",
        "portaudio_pyd_size": 0,
    }
    try:
        import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]
    except Exception:
        return info

    pkg_ver = getattr(pyaudio, "__version__", "") or ""
    if not pkg_ver:
        try:
            from importlib.metadata import version as _pkg_version

            pkg_ver = _pkg_version("PyAudioWPatch")
        except Exception:
            pkg_ver = ""
    info["pyaudiowpatch_version"] = str(pkg_ver)

    pa_cmod = getattr(pyaudio, "_portaudiowpatch", None) or getattr(pyaudio, "pa", None) or sys.modules.get("pyaudiowpatch._portaudiowpatch")
    ver_text = ""
    for holder in (pyaudio, pa_cmod):
        if holder is None:
            continue
        fn = getattr(holder, "get_portaudio_version_text", None)
        if callable(fn):
            try:
                raw = fn()
                ver_text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw or "")
                if ver_text.strip():
                    break
            except Exception:
                pass
    if not ver_text.strip():
        fn_num = getattr(pyaudio, "get_portaudio_version", None)
        if callable(fn_num):
            try:
                ver_text = f"PortAudio {fn_num()}"
            except Exception:
                ver_text = ""
    info["portaudio_version_text"] = ver_text.strip()

    pyd_file: Optional[str] = None
    for cand_mod in (
        getattr(pyaudio, "_portaudiowpatch", None),
        getattr(pyaudio, "pa", None),
        sys.modules.get("pyaudiowpatch._portaudiowpatch"),
    ):
        if cand_mod is None:
            continue
        cand_file = getattr(cand_mod, "__file__", None)
        if cand_file and str(cand_file).lower().endswith((".pyd", ".so", ".dll")):
            pyd_file = str(cand_file)
            break
    if not pyd_file and getattr(pyaudio, "__file__", None):
        try:
            pkg_dir = Path(str(pyaudio.__file__)).resolve().parent
            for pat in ("_portaudiowpatch*.pyd", "_portaudio*.pyd", "_portaudiowpatch*.so", "_portaudio*.so"):
                matches = sorted(pkg_dir.glob(pat))
                if matches:
                    pyd_file = str(matches[0])
                    break
        except Exception:
            pass
    if pyd_file:
        try:
            p = Path(pyd_file).resolve()
            info["portaudio_pyd_path"] = str(p)
            if p.is_file():
                info["portaudio_pyd_size"] = int(p.stat().st_size)
        except Exception:
            pass
    return info


class _SwitchSilenceKeepalive:
    """Pushes ~20ms zero-PCM chunks during proactive device-switch backoff/reopen."""

    def __init__(
        self,
        backend: "WasapiSystemLoopbackBackend",
        *,
        target_sr: int,
        dev_name: str,
        chunk_frames: int,
    ) -> None:
        self._backend = backend
        self._target_sr = max(1, int(target_sr))
        self._dev_name = str(dev_name or "")
        self._chunk_frames = max(1, int(chunk_frames))
        self._interval_sec = max(0.005, self._chunk_frames / float(self._target_sr))
        self._local_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._local_stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ListenScope-SwitchSilenceKeepalive",
            daemon=True,
        )
        self._thread.start()

    def signal_stop(self) -> None:
        self._local_stop.set()

    def _run(self) -> None:
        while (
            not self._local_stop.is_set()
            and not self._backend._stop_event.is_set()
            and not self._backend._closing.is_set()
        ):
            t0 = time.monotonic()
            self._backend._emit_silence_chunk(self._target_sr, self._dev_name, self._chunk_frames)
            elapsed = time.monotonic() - t0
            rem = self._interval_sec - elapsed
            if rem > 0.0:
                if self._local_stop.wait(timeout=rem):
                    break

    def stop(self, timeout: float = 0.25) -> None:
        self._local_stop.set()
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=min(0.3, max(0.01, float(timeout))))


class WasapiSystemLoopbackBackend(AudioCaptureBackend):
    """Fallback Windows system-wide WASAPI loopback using PyAudioWPatch.

    Always surfaces `SYSTEM_LOOPBACK_WARNING` so the user knows other apps' audio
    may be mixed in. Separates proactive default-device switching from unexpected
    disconnect reconnects and re-enumerates fresh PyAudio instances on startup.
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
        startup_open_retries: int = 2,
        startup_retry_delay_sec: float = 0.15,
        startup_per_attempt_timeout_sec: float = 5.0,
        idle_silence_grace_sec: float = 0.15,
        switch_backoff_initial_sec: float = 0.05,
        switch_backoff_max_sec: float = 2.0,
    ) -> None:
        super().__init__(audio_config=audio_config)
        self._pyaudio_factory = pyaudio_factory
        self._max_device_reconnects = max_device_reconnects
        self._allow_non_windows = allow_non_windows
        self._follow_default_device = bool(follow_default_device)
        self._default_device_probe = default_device_probe
        self._device_poll_interval_sec = max(0.05, float(device_poll_interval_sec))
        self._device_switch_ttl_sec = max(0.05, float(device_switch_ttl_sec))
        self._startup_open_retries = max(0, int(startup_open_retries))
        self._startup_retry_delay_sec = max(0.0, float(startup_retry_delay_sec))
        self._startup_per_attempt_timeout_sec = max(0.01, float(startup_per_attempt_timeout_sec))
        self._idle_silence_grace_sec = max(0.0, float(idle_silence_grace_sec))
        self._switch_backoff_initial_sec = max(0.0, float(switch_backoff_initial_sec))
        self._switch_backoff_max_sec = max(self._switch_backoff_initial_sec, float(switch_backoff_max_sec))

        self._stop_event = threading.Event()
        self._closing = threading.Event()
        self._device_switch_requested = threading.Event()
        self._startup_ready = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._startup_stage: str = "idle"
        self._startup_stage_ts: float = 0.0
        self._lock = threading.RLock()
        self._wakeup_cond = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._watcher_thread: Optional[threading.Thread] = None
        self._active_keepalive: Optional[_SwitchSilenceKeepalive] = None
        self._pa: Any = None
        self._stream: Any = None
        self._device_name = "System Default WASAPI Loopback"
        self._active_dev_index: Optional[int] = None
        self._active_dev_name: str = self._device_name
        self._watcher_observed_name: str = ""
        self._current_endpoint_id: Optional[str] = None
        self._switch_generation: int = 0
        self._last_probe_warn_ts: dict[int, float] = {}
        self._last_open_attempts: int = 0
        self._last_open_errors: tuple[str, ...] = ()
        self._last_open_timings: list[dict[str, Any]] = []
        self._unexpected_disconnect_attempts: int = 0
        self._proactive_switch_attempts: int = 0
        self._proactive_switch_success_count: int = 0
        self._proactive_switch_retry_total: int = 0
        self._unexpected_disconnect_retry_total: int = 0

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

    @property
    def last_open_attempts(self) -> int:
        return self._last_open_attempts

    @property
    def last_open_errors(self) -> tuple[str, ...]:
        return self._last_open_errors

    @property
    def last_open_timings(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._last_open_timings]

    @property
    def proactive_switch_success_count(self) -> int:
        return self._proactive_switch_success_count

    @property
    def proactive_switch_retry_total(self) -> int:
        return self._proactive_switch_retry_total

    @property
    def unexpected_disconnect_retry_total(self) -> int:
        return self._unexpected_disconnect_retry_total

    @property
    def unexpected_disconnect_attempts(self) -> int:
        return self._unexpected_disconnect_attempts

    @property
    def proactive_switch_attempts(self) -> int:
        return self._proactive_switch_attempts

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

    @staticmethod
    def _find_matching_default_loopbacks(
        pa: Any,
        *,
        preferred_name: str,
        seen_indices: set[int],
    ) -> list[dict[str, Any]]:
        if not hasattr(pa, "get_loopback_device_info_generator"):
            return []
        try:
            loopbacks = list(pa.get_loopback_device_info_generator())
        except Exception:
            return []
        if not loopbacks:
            return []

        target_names: list[str] = []
        pa_wasapi = getattr(pa, "paWASAPI", None)
        if pa_wasapi is None:
            try:
                import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]

                pa_wasapi = getattr(pyaudio, "paWASAPI", None)
            except Exception:
                pa_wasapi = None
        if pa_wasapi is not None and hasattr(pa, "get_host_api_info_by_type") and hasattr(pa, "get_device_info_by_index"):
            try:
                wasapi_info = pa.get_host_api_info_by_type(pa_wasapi)
                default_out_idx = wasapi_info.get("defaultOutputDevice") if isinstance(wasapi_info, dict) else None
                if default_out_idx is not None and int(default_out_idx) >= 0:
                    out_info = pa.get_device_info_by_index(int(default_out_idx))
                    out_name = str(out_info.get("name", "")).strip() if isinstance(out_info, dict) else ""
                    if out_name:
                        target_names.append(out_name)
            except Exception:
                pass

        pref = preferred_name.strip()
        if pref and pref not in target_names:
            target_names.append(pref)
        if not target_names:
            return []

        matched: list[dict[str, Any]] = []
        for target in target_names:
            t_low = target.lower()
            t_loop = f"{t_low} [loopback]"
            exact_hits: list[dict[str, Any]] = []
            substr_hits: list[dict[str, Any]] = []
            for dev in loopbacks:
                if not isinstance(dev, dict) or dev.get("index") is None:
                    continue
                idx = int(dev["index"])
                if idx in seen_indices:
                    continue
                cname = str(dev.get("name", "")).strip()
                clow = cname.lower()
                if not clow:
                    continue
                if clow == t_loop or clow == t_low:
                    exact_hits.append(dev)
                else:
                    base_cname = clow[:-11].strip() if clow.endswith("[loopback]") else clow
                    if t_low in clow or (base_cname and base_cname in t_low):
                        substr_hits.append(dev)
            for dev in exact_hits + substr_hits:
                idx = int(dev["index"])
                if idx not in seen_indices:
                    seen_indices.add(idx)
                    matched.append(dev)
            if matched:
                break
        return matched

    def _set_startup_stage(self, stage: str) -> None:
        with self._lock:
            self._startup_stage = stage
            self._startup_stage_ts = time.monotonic()

    def _compute_startup_wait_sec(self) -> float:
        total_attempts = 1 + max(0, int(self._startup_open_retries))
        per_attempt = max(0.01, float(self._startup_per_attempt_timeout_sec))
        retry_sleeps = sum(self._startup_retry_delay_sec * i for i in range(1, total_attempts))
        guard = 1.0 if per_attempt >= 1.0 else 0.1
        return max(0.05, total_attempts * per_attempt + retry_sleeps + guard)

    def _emit_silence_chunk(self, target_sr: int, dev_name: str, chunk_frames: int) -> None:
        if self._stop_event.is_set() or self._closing.is_set():
            return
        _ = (target_sr, dev_name)
        frames = max(1, int(chunk_frames))
        chunk = np.zeros((frames, self.audio_config.channels), dtype=np.float32)
        self.queue.put_drop_oldest(chunk)
        if self._stop_event.is_set() or self._closing.is_set():
            return
        self._stats.record_chunk(
            chunk,
            queue_size=len(self.queue),
            overruns=self.queue.overruns,
        )

    def _open_candidate_stream(
        self,
        pa: Any,
        dev_info: dict[str, Any],
        *,
        attempt: int,
        pa_version_text: str,
        timing_entry: Optional[dict[str, Any]] = None,
    ) -> tuple[Any, int, str]:
        src_rate = int(dev_info["defaultSampleRate"])
        raw_ch = int(dev_info.get("maxInputChannels") or 0) or int(
            dev_info.get("maxOutputChannels") or 0
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

        dev_index = int(dev_info["index"])
        dev_name = str(dev_info.get("name", ""))
        is_loopback = dev_info.get("isLoopbackDevice")
        if timing_entry is not None and dev_name:
            timing_entry["device_name"] = dev_name

        self._set_startup_stage("open_f32")
        t_f32 = time.perf_counter()
        try:
            stream = pa.open(
                format=pa_f32,
                channels=src_channels,
                rate=src_rate,
                frames_per_buffer=frames_per_buffer,
                input=True,
                input_device_index=dev_index,
            )
            if timing_entry is not None:
                timing_entry["open_f32_ms"] = round(
                    float(timing_entry.get("open_f32_ms", 0.0)) + (time.perf_counter() - t_f32) * 1000.0,
                    3,
                )
            return stream, frames_per_buffer, "float32"
        except Exception as f32_exc:
            if timing_entry is not None:
                timing_entry["open_f32_ms"] = round(
                    float(timing_entry.get("open_f32_ms", 0.0)) + (time.perf_counter() - t_f32) * 1000.0,
                    3,
                )
            logger.info(
                "WASAPI system loopback float32 open failed (attempt=%d pa=%s index=%s name=%r isLoopbackDevice=%r rate=%s ch=%s err=%s); falling back to int16",
                attempt,
                pa_version_text or "unknown",
                dev_index,
                dev_name,
                is_loopback,
                src_rate,
                src_channels,
                f32_exc,
            )
            self._set_startup_stage("open_i16")
            t_i16 = time.perf_counter()
            try:
                stream = pa.open(
                    format=pa_i16,
                    channels=src_channels,
                    rate=src_rate,
                    frames_per_buffer=frames_per_buffer,
                    input=True,
                    input_device_index=dev_index,
                )
                if timing_entry is not None:
                    timing_entry["open_i16_ms"] = round(
                        float(timing_entry.get("open_i16_ms", 0.0)) + (time.perf_counter() - t_i16) * 1000.0,
                        3,
                    )
                return stream, frames_per_buffer, "int16"
            except Exception as i16_exc:
                if timing_entry is not None:
                    timing_entry["open_i16_ms"] = round(
                        float(timing_entry.get("open_i16_ms", 0.0)) + (time.perf_counter() - t_i16) * 1000.0,
                        3,
                    )
                logger.warning(
                    "WASAPI system loopback open failed (attempt=%d pa=%s index=%s name=%r isLoopbackDevice=%r rate=%s ch=%s f32=%s i16=%s)",
                    attempt,
                    pa_version_text or "unknown",
                    dev_index,
                    dev_name,
                    is_loopback,
                    src_rate,
                    src_channels,
                    f32_exc,
                    i16_exc,
                )
                raise

    def _open_default_loopback(
        self,
        *,
        preferred_name: str = "",
        max_attempts: Optional[int] = None,
        retry_delay_sec: Optional[float] = None,
    ) -> tuple[Any, Any, dict[str, Any], int, str]:
        total_attempts = max(1, int(max_attempts) if max_attempts is not None else (1 + self._startup_open_retries))
        base_delay = self._startup_retry_delay_sec if retry_delay_sec is None else max(0.0, float(retry_delay_sec))
        attempt_errors: list[str] = []
        timings: list[dict[str, Any]] = []
        last_exc: Optional[BaseException] = None
        pa_version_text = ""

        for attempt in range(1, total_attempts + 1):
            if self._stop_event.is_set() or self._closing.is_set():
                break
            attempt_t0 = time.perf_counter()
            timing_entry: dict[str, Any] = {
                "attempt": attempt,
                "pa_init_ms": 0.0,
                "enum_default_ms": 0.0,
                "fallback_enum_ms": 0.0,
                "open_f32_ms": 0.0,
                "open_i16_ms": 0.0,
                "terminate_ms": 0.0,
                "total_ms": 0.0,
                "status": "failed",
                "device_name": "",
                "error": "",
            }
            pa: Any = None
            opened_ok = False
            attempt_exc: Optional[BaseException] = None
            try:
                self._set_startup_stage("pa_init")
                t_init = time.perf_counter()
                pa = self._create_pa()
                timing_entry["pa_init_ms"] = round((time.perf_counter() - t_init) * 1000.0, 3)

                if not pa_version_text:
                    pa_ver_fn = getattr(pa, "get_portaudio_version_text", None)
                    if callable(pa_ver_fn):
                        try:
                            raw_v = pa_ver_fn()
                            pa_version_text = raw_v.decode("utf-8", errors="replace") if isinstance(raw_v, bytes) else str(raw_v or "")
                        except Exception:
                            pa_version_text = ""
                    if not pa_version_text:
                        pa_version_text = str(get_portaudio_runtime_info().get("portaudio_version_text", ""))

                candidates: list[dict[str, Any]] = []
                seen_indices: set[int] = set()
                self._set_startup_stage("enum_default")
                t_enum = time.perf_counter()
                try:
                    default_loopback = pa.get_default_wasapi_loopback()
                    if isinstance(default_loopback, dict) and default_loopback.get("index") is not None:
                        seen_indices.add(int(default_loopback["index"]))
                        candidates.append(default_loopback)
                    elif default_loopback:
                        candidates.append(default_loopback)
                except Exception as def_exc:
                    attempt_exc = def_exc
                    logger.info(
                        "get_default_wasapi_loopback failed (attempt=%d pa=%s): %s",
                        attempt,
                        pa_version_text or "unknown",
                        def_exc,
                    )
                finally:
                    timing_entry["enum_default_ms"] = round((time.perf_counter() - t_enum) * 1000.0, 3)

                for cand in candidates:
                    try:
                        stream, frames_per_buffer, src_dtype = self._open_candidate_stream(
                            pa,
                            cand,
                            attempt=attempt,
                            pa_version_text=pa_version_text,
                            timing_entry=timing_entry,
                        )
                        opened_ok = True
                        timing_entry["status"] = "opened"
                        timing_entry["error"] = ""
                        timing_entry["total_ms"] = round((time.perf_counter() - attempt_t0) * 1000.0, 3)
                        timings.append(timing_entry)
                        with self._lock:
                            self._last_open_timings = list(timings)
                        self._last_open_attempts = attempt
                        self._last_open_errors = tuple(attempt_errors)
                        self._set_startup_stage("ready")
                        return pa, stream, cand, frames_per_buffer, src_dtype
                    except Exception as open_exc:
                        attempt_exc = open_exc

                self._set_startup_stage("fallback_enum")
                t_fb = time.perf_counter()
                fallback_candidates = self._find_matching_default_loopbacks(
                    pa,
                    preferred_name=preferred_name,
                    seen_indices=seen_indices,
                )
                timing_entry["fallback_enum_ms"] = round((time.perf_counter() - t_fb) * 1000.0, 3)
                for cand in fallback_candidates:
                    try:
                        stream, frames_per_buffer, src_dtype = self._open_candidate_stream(
                            pa,
                            cand,
                            attempt=attempt,
                            pa_version_text=pa_version_text,
                            timing_entry=timing_entry,
                        )
                        opened_ok = True
                        timing_entry["status"] = "opened"
                        timing_entry["error"] = ""
                        timing_entry["total_ms"] = round((time.perf_counter() - attempt_t0) * 1000.0, 3)
                        timings.append(timing_entry)
                        with self._lock:
                            self._last_open_timings = list(timings)
                        self._last_open_attempts = attempt
                        self._last_open_errors = tuple(attempt_errors)
                        self._set_startup_stage("ready")
                        return pa, stream, cand, frames_per_buffer, src_dtype
                    except Exception as open_exc:
                        attempt_exc = open_exc

                if attempt_exc is None:
                    attempt_exc = RuntimeError("未找到默认 WASAPI Loopback 输出设备。")
                last_exc = attempt_exc
                timing_entry["error"] = str(attempt_exc)
                attempt_errors.append(f"attempt {attempt}: {attempt_exc}")
            except Exception as exc:
                last_exc = exc
                timing_entry["error"] = str(exc)
                attempt_errors.append(f"attempt {attempt}: {exc}")
            finally:
                if not opened_ok:
                    if pa is not None:
                        self._set_startup_stage("terminate")
                        t_term = time.perf_counter()
                        try:
                            pa.terminate()
                        except Exception:
                            pass
                        timing_entry["terminate_ms"] = round((time.perf_counter() - t_term) * 1000.0, 3)
                    timing_entry["total_ms"] = round((time.perf_counter() - attempt_t0) * 1000.0, 3)
                    timings.append(timing_entry)
                    with self._lock:
                        self._last_open_timings = list(timings)

            self._last_open_attempts = attempt
            self._last_open_errors = tuple(attempt_errors)
            if attempt < total_attempts and base_delay > 0.0:
                self._set_startup_stage("retry_sleep")
                if self._stop_event.wait(timeout=base_delay * attempt):
                    break

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("未找到默认 WASAPI Loopback 输出设备。")

    def _invoke_open_default_loopback(
        self,
        *,
        preferred_name: str = "",
        max_attempts: Optional[int] = None,
        retry_delay_sec: Optional[float] = None,
    ) -> tuple[Any, Any, dict[str, Any], int, str]:
        fn = self._open_default_loopback
        if getattr(fn, "__func__", None) is WasapiSystemLoopbackBackend._open_default_loopback:
            return fn(
                preferred_name=preferred_name,
                max_attempts=max_attempts,
                retry_delay_sec=retry_delay_sec,
            )
        return fn()

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
        if self._thread is not None or self._watcher_thread is not None:
            self.stop()

        self.queue.reset_open()
        self._closing.clear()
        self._stop_event.clear()
        with self._wakeup_cond:
            self._device_switch_requested.clear()
            self._switch_generation = 0
            self._current_endpoint_id = None
            self._watcher_observed_name = ""
        self._startup_ready.clear()
        self._startup_error = None
        self._set_startup_stage("idle")
        self._last_open_attempts = 0
        self._last_open_errors = ()
        with self._lock:
            self._last_open_timings = []
        self._unexpected_disconnect_attempts = 0
        self._proactive_switch_attempts = 0
        self._proactive_switch_success_count = 0
        self._proactive_switch_retry_total = 0
        self._unexpected_disconnect_retry_total = 0

        self._thread = threading.Thread(
            target=self._capture_loop,
            name="ListenScope-SystemLoopback",
            daemon=True,
        )
        self._thread.start()
        startup_wait_sec = self._compute_startup_wait_sec()
        if not self._startup_ready.wait(timeout=startup_wait_sec):
            with self._lock:
                stalled_stage = self._startup_stage
                stalled_ts = self._startup_stage_ts
                attempts_so_far = self._last_open_attempts
            stage_elapsed_ms = max(0.0, (time.monotonic() - stalled_ts) * 1000.0) if stalled_ts > 0.0 else 0.0
            logger.warning(
                "WASAPI system loopback startup timed out after %.2fs (stage=%s stage_elapsed_ms=%.1f attempts=%d)",
                startup_wait_sec,
                stalled_stage,
                stage_elapsed_ms,
                attempts_so_far,
            )
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
            with self._wakeup_cond:
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
                if not self._follow_default_device:
                    continue
                ep_id, ep_name, hr = self._probe_for_watcher()
                if not ep_id:
                    if self._default_device_probe is not None or platform.system() == "Windows":
                        self._warn_probe_failure(hr)
                    continue
                with self._wakeup_cond:
                    if self._current_endpoint_id is None:
                        self._current_endpoint_id = ep_id
                        self._watcher_observed_name = ep_name
                    elif ep_id != self._current_endpoint_id:
                        self._current_endpoint_id = ep_id
                        self._watcher_observed_name = ep_name
                        self._switch_generation += 1
                        self._device_switch_requested.set()
                        self._wakeup_cond.notify_all()
        finally:
            if should_uninit and ole32_to_uninit is not None:
                try:
                    ole32_to_uninit.CoUninitialize()
                except Exception:
                    pass

    def _wait_interruptible(self, timeout: float, target_gen: int) -> bool:
        """Wait for timeout unless stopped or a newer switch generation arrives.

        Returns True if stopped/closing, False otherwise.
        """
        if self._stop_event.is_set() or self._closing.is_set():
            return True
        if timeout <= 0.0:
            return False
        if "wait" in getattr(self._stop_event, "__dict__", {}):
            self._stop_event.wait(timeout=timeout)
            return self._stop_event.is_set() or self._closing.is_set()
        with self._wakeup_cond:
            self._wakeup_cond.wait_for(
                lambda: (
                    self._stop_event.is_set()
                    or self._closing.is_set()
                    or self._device_switch_requested.is_set()
                    or self._switch_generation != target_gen
                ),
                timeout=timeout,
            )
        return self._stop_event.is_set() or self._closing.is_set()

    def _compute_switch_backoff_sec(self, attempt: int) -> float:
        exp = min(max(0, attempt - 1), 6)
        return min(self._switch_backoff_max_sec, self._switch_backoff_initial_sec * (2**exp))

    def _capture_loop(self, dev_info: Optional[dict[str, Any]] = None, frames_per_buffer: int = 0, src_dtype: str = "float32") -> None:
        if dev_info is None:
            try:
                pa, stream, dev_info, frames_per_buffer, src_dtype = self._invoke_open_default_loopback(
                    max_attempts=1 + self._startup_open_retries,
                    retry_delay_sec=self._startup_retry_delay_sec,
                )
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
        current_dev_name: str = str(dev_info.get("name") or "").strip() or self._device_name
        with self._lock:
            self._active_dev_index = current_dev_index
            self._active_dev_name = current_dev_name
        self._device_name = current_dev_name
        self._stats.set_process_name(self._device_name)
        self._stats.set_device_switch_message(None)
        self._stats.set_error(None)
        self._stats.set_running(True)
        self._set_startup_stage("ready")
        self._startup_ready.set()

        self._unexpected_disconnect_attempts = 0
        self._proactive_switch_attempts = 0
        clean_chunks_since_reconnect = 0
        has_transient_reconnect_notice = False
        keepalive_frames = max(256, int(round(self.audio_config.sample_rate * 0.02)))
        keepalive_step_sec = keepalive_frames / float(max(1, self.audio_config.sample_rate))
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
                        idle_started_at = time.monotonic()
                        next_keepalive_at: Optional[float] = None
                        while not self._stop_event.is_set() and not self._closing.is_set():
                            if self._follow_default_device and self._device_switch_requested.is_set():
                                raise RuntimeError("DEFAULT_DEVICE_CHANGED")
                            if int(read_avail_fn()) >= frames_per_buffer:
                                break
                            now = time.monotonic()
                            if (now - idle_started_at) >= self._idle_silence_grace_sec:
                                if next_keepalive_at is None or now >= next_keepalive_at:
                                    self._emit_silence_chunk(
                                        self.audio_config.sample_rate,
                                        current_dev_name,
                                        keepalive_frames,
                                    )
                                    next_keepalive_at = now + keepalive_step_sec
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
                    self._unexpected_disconnect_attempts = 0
                    self._proactive_switch_attempts = 0
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
                    with self._wakeup_cond:
                        is_device_switch = str(exc) == "DEFAULT_DEVICE_CHANGED" or self._device_switch_requested.is_set()
                        target_gen = self._switch_generation
                        target_name = self._watcher_observed_name
                        self._device_switch_requested.clear()

                    old_dev_name = current_dev_name
                    if is_device_switch:
                        logger.info("检测到默认输出设备变更，正在无感切换 WASAPI Loopback 设备...")
                        self._unexpected_disconnect_attempts = 0
                    else:
                        logger.warning("WASAPI system loopback read error (device switch?): %s", exc)
                        self._stats.record_underrun(1)

                    self._close_stream()
                    clean_chunks_since_reconnect = 0
                    if resampler is not None:
                        resampler.reset()

                    keepalive: Optional[_SwitchSilenceKeepalive] = None

                    def _ensure_keepalive() -> None:
                        nonlocal keepalive
                        if keepalive is None and not self._stop_event.is_set() and not self._closing.is_set():
                            ka = _SwitchSilenceKeepalive(
                                self,
                                target_sr=self.audio_config.sample_rate,
                                dev_name=current_dev_name,
                                chunk_frames=keepalive_frames,
                            )
                            with self._lock:
                                self._active_keepalive = ka
                            ka.start()
                            keepalive = ka

                    reconnected = False
                    self._proactive_switch_attempts = 0
                    try:
                        if is_device_switch:
                            _ensure_keepalive()
                        while not self._stop_event.is_set() and not self._closing.is_set():
                            with self._wakeup_cond:
                                if self._device_switch_requested.is_set() or self._switch_generation != target_gen:
                                    target_gen = self._switch_generation
                                    target_name = self._watcher_observed_name
                                    self._device_switch_requested.clear()
                                    is_device_switch = True
                                    self._unexpected_disconnect_attempts = 0
                                    self._proactive_switch_attempts = 0

                            if is_device_switch:
                                _ensure_keepalive()
                                self._proactive_switch_attempts += 1
                                wait_sec = self._compute_switch_backoff_sec(self._proactive_switch_attempts)
                                if self._wait_interruptible(wait_sec, target_gen):
                                    break
                                with self._wakeup_cond:
                                    if self._device_switch_requested.is_set() or self._switch_generation != target_gen:
                                        target_gen = self._switch_generation
                                        target_name = self._watcher_observed_name
                                        self._device_switch_requested.clear()
                                        self._proactive_switch_attempts = 0
                                        continue
                            else:
                                if self._unexpected_disconnect_attempts >= self._max_device_reconnects:
                                    break
                                self._unexpected_disconnect_attempts += 1
                                self._unexpected_disconnect_retry_total += 1
                                wait_sec = 0.35 * self._unexpected_disconnect_attempts
                                if self._wait_interruptible(wait_sec, target_gen):
                                    break
                                with self._wakeup_cond:
                                    if self._device_switch_requested.is_set() or self._switch_generation != target_gen:
                                        target_gen = self._switch_generation
                                        target_name = self._watcher_observed_name
                                        self._device_switch_requested.clear()
                                        is_device_switch = True
                                        self._unexpected_disconnect_attempts = 0
                                        self._proactive_switch_attempts = 0
                                        continue

                            try:
                                new_pa, new_stream, new_dev, frames_per_buffer, src_dtype = self._invoke_open_default_loopback(
                                    preferred_name=target_name,
                                    max_attempts=1,
                                    retry_delay_sec=0.0,
                                )
                                with self._wakeup_cond:
                                    if self._stop_event.is_set() or self._closing.is_set():
                                        self._close_pa_pair(new_pa, new_stream)
                                        break
                                    if self._device_switch_requested.is_set() or self._switch_generation != target_gen:
                                        self._close_pa_pair(new_pa, new_stream)
                                        target_gen = self._switch_generation
                                        target_name = self._watcher_observed_name
                                        self._device_switch_requested.clear()
                                        is_device_switch = True
                                        self._unexpected_disconnect_attempts = 0
                                        self._proactive_switch_attempts = 0
                                        continue

                                src_rate = int(new_dev["defaultSampleRate"])
                                new_ch = int(new_dev.get("maxInputChannels") or 0) or int(new_dev.get("maxOutputChannels") or 0)
                                src_channels = max(1, new_ch)
                                current_dev_index = int(new_dev["index"]) if "index" in new_dev and new_dev["index"] is not None else None
                                resolved_name = str(new_dev.get("name") or "").strip() or target_name.strip() or current_dev_name or self._device_name
                                current_dev_name = resolved_name
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
                                    self._proactive_switch_attempts = 0
                                    self._proactive_switch_success_count += 1
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
                                if is_device_switch:
                                    self._proactive_switch_retry_total += 1
                                    target_label = target_name or self._device_name
                                    self._stats.set_device_switch_message(
                                        f"正在切换默认播放设备至 {target_label}，等待设备就绪 (第 {self._proactive_switch_attempts} 次尝试)...",
                                        ttl_sec=max(self._device_switch_ttl_sec, 3.0),
                                    )
                                    if self._proactive_switch_attempts <= 5 or self._proactive_switch_attempts % 10 == 0:
                                        logger.warning(
                                            "默认播放设备切换重连尚未就绪 (第 %d 次, target=%s): %s",
                                            self._proactive_switch_attempts,
                                            target_label,
                                            rec_exc,
                                        )
                                    else:
                                        logger.debug(
                                            "默认播放设备切换重连等待中 (第 %d 次, target=%s): %s",
                                            self._proactive_switch_attempts,
                                            target_label,
                                            rec_exc,
                                        )
                                else:
                                    logger.warning(
                                        "播放设备重连尝试失败 (%d/%d): %s",
                                        self._unexpected_disconnect_attempts,
                                        self._max_device_reconnects,
                                        rec_exc,
                                    )
                    finally:
                        if keepalive is not None:
                            keepalive.stop(timeout=0.25)
                            with self._lock:
                                if self._active_keepalive is keepalive:
                                    self._active_keepalive = None
                            keepalive = None

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
            self._stop_event.set()
            with self._wakeup_cond:
                self._wakeup_cond.notify_all()

    def stop(self) -> None:
        self._closing.set()
        self._stop_event.set()
        with self._lock:
            ka = self._active_keepalive
        if ka is not None:
            ka.signal_stop()
        with self._wakeup_cond:
            self._wakeup_cond.notify_all()
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
