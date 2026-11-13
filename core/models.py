"""Typed data models for system probes, resource monitoring, and audio capture."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ResourceStatus(str, Enum):
    NORMAL = "Normal"
    WARNING = "Warning"
    CRITICAL = "Critical"


class CaptureMode(str, Enum):
    PROCESS_LOOPBACK = "process_loopback"
    SYSTEM_LOOPBACK = "system_loopback"
    SYNTHETIC_SIMULATION = "synthetic_simulation"


@dataclass
class GPUInfo:
    index: int
    name: str
    total_vram_mb: float
    used_vram_mb: float
    free_vram_mb: float
    utilization_pct: Optional[float] = None
    driver_version: Optional[str] = None
    source: str = "nvml"


@dataclass
class PyTorchProbeInfo:
    installed: bool
    version: Optional[str] = None
    cuda_available: bool = False
    cuda_build: Optional[str] = None
    device_count: int = 0
    device_name: Optional[str] = None
    compute_capability: Optional[tuple[int, int]] = None
    arch_list: list[str] = field(default_factory=list)
    supports_sm_120: Optional[bool] = None
    kernel_smoke_test_passed: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class OnnxRuntimeProbeInfo:
    installed: bool
    version: Optional[str] = None
    providers: list[str] = field(default_factory=list)
    cuda_provider_available: bool = False
    error: Optional[str] = None


@dataclass
class SystemHardwareReport:
    timestamp_utc: str
    os_system: str
    os_release: str
    os_version: str
    architecture: str
    is_windows: bool
    windows_build: Optional[int]
    wasapi_process_loopback_supported: bool
    python_version: str
    git_version: Optional[str]
    cpu_model: str
    cpu_cores_logical: int
    ram_total_mb: float
    ram_available_mb: float
    gpus: list[GPUInfo] = field(default_factory=list)
    nvidia_driver_version: Optional[str] = None
    nvml_available: bool = False
    nvidia_smi_available: bool = False
    pytorch: PyTorchProbeInfo = field(default_factory=lambda: PyTorchProbeInfo(installed=False))
    onnxruntime: OnnxRuntimeProbeInfo = field(default_factory=lambda: OnnxRuntimeProbeInfo(installed=False))
    gpu_ai_ready: bool = False
    gpu_ai_block_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceSnapshot:
    timestamp: float
    main_ram_mb: float
    ai_worker_ram_mb: float
    system_ram_total_mb: float
    system_ram_available_mb: float
    gpu_name: Optional[str]
    vram_total_mb: Optional[float]
    vram_used_mb: Optional[float]
    vram_free_mb: Optional[float]
    gpu_utilization_pct: Optional[float]
    active_ai_jobs: int
    loaded_models: int
    current_model: Optional[str]
    current_task: Optional[str]
    audio_queue_size: int
    audio_queue_maxsize: int
    ai_buffer_seconds: float
    status: ResourceStatus
    status_reasons: list[str] = field(default_factory=list)
    simulated: bool = False


@dataclass
class AudioProcessInfo:
    pid: int
    name: str
    exe: Optional[str] = None
    session_state: str = "unknown"  # active, inactive, expired, unknown
    parent_pid: Optional[int] = None
    parent_name: Optional[str] = None
    child_pids: list[int] = field(default_factory=list)
    rss_mb: float = 0.0
    source: str = "psutil"

    @property
    def display_label(self) -> str:
        state_tag = f"[{self.session_state}]" if self.session_state != "unknown" else ""
        return f"PID {self.pid:<7} {self.name:<28} {state_tag} (RSS {self.rss_mb:.1f} MB)"


@dataclass
class CaptureStats:
    mode: CaptureMode
    pid: Optional[int]
    process_name: str
    sample_rate: int
    channels: int
    dtype: str
    rms_linear: float = 0.0
    rms_dbfs: float = -120.0
    peak_linear: float = 0.0
    peak_dbfs: float = -120.0
    frames_per_sec: float = 0.0
    total_frames: int = 0
    total_chunks: int = 0
    buffer_underruns: int = 0
    buffer_overruns: int = 0
    queue_size: int = 0
    queue_maxsize: int = 0
    is_silent: bool = True
    is_running: bool = False
    warning_message: Optional[str] = None
    last_error: Optional[str] = None
