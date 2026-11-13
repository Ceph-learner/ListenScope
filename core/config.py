"""Centralized configuration and conservative resource limits for ListenScope.

All RAM, VRAM, and audio buffer thresholds live here rather than being scattered
across modules. Conservative defaults are calibrated for the target user PC:
- OS: Windows 10/11 (20H1+ for WASAPI Process Loopback)
- GPU: NVIDIA GeForce RTX 5060 Ti with 8GB VRAM (NOT 16GB VRAM)
- System RAM: 16GB RAM
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetHardwareSpec:
    """Hard target specification that all ListenScope budgets are designed around."""

    os_name: str = "Windows"
    min_windows_build_for_process_loopback: int = 19041  # Windows 10 20H1
    gpu_name: str = "NVIDIA GeForce RTX 5060 Ti"
    gpu_architecture: str = "Blackwell (sm_120)"
    gpu_compute_capability: tuple[int, int] = (12, 0)
    vram_gb: int = 8  # IMPORTANT: 8GB VRAM, NOT 16GB VRAM
    ram_gb: int = 16  # 16GB system RAM
    min_cuda_version: str = "12.8"
    min_pytorch_version_for_blackwell: str = "2.7.0"


@dataclass(frozen=True)
class ResourceLimits:
    """Configurable RAM and VRAM guardrails for ListenScope."""

    # Main GUI / core process RAM targets
    max_main_process_ram_mb: float = 1024.0
    warn_main_process_ram_mb: float = 1536.0

    # System available RAM gates (using psutil.virtual_memory().available)
    min_ram_before_ai_mb: float = 5120.0    # >= 5.0 GB recommended before AI job
    pause_ram_before_ai_mb: float = 3072.0  # < 3.0 GB refuses new AI separation
    critical_ram_mb: float = 2048.0         # < 2.0 GB triggers immediate AI emergency stop

    # GPU VRAM gates for RTX 5060 Ti 8GB VRAM
    min_vram_2stem_mb: float = 4096.0       # >= 4.0 GB free VRAM for 2-stem GPU mode
    min_vram_4stem_mb: float = 5632.0       # >= 5.5 GB free VRAM for 4-stem GPU mode
    critical_vram_free_mb: float = 768.0    # Reserve >= 768 MB for Windows desktop / QQ Music / browser

    # Concurrency & model loading limits
    max_concurrent_ai_jobs: int = 1
    max_loaded_models: int = 1

    # Bounded monitoring history (prevents unbounded UI/log growth)
    monitor_history_maxlen: int = 300

    def __post_init__(self) -> None:
        if self.critical_ram_mb >= self.pause_ram_before_ai_mb:
            raise ValueError("critical_ram_mb must be smaller than pause_ram_before_ai_mb")
        if self.pause_ram_before_ai_mb > self.min_ram_before_ai_mb:
            raise ValueError("pause_ram_before_ai_mb must not exceed min_ram_before_ai_mb")
        if self.max_main_process_ram_mb >= self.warn_main_process_ram_mb:
            raise ValueError("max_main_process_ram_mb must be smaller than warn_main_process_ram_mb")
        if self.min_vram_2stem_mb > self.min_vram_4stem_mb:
            raise ValueError("min_vram_2stem_mb must not exceed min_vram_4stem_mb")
        if self.critical_vram_free_mb <= 0:
            raise ValueError("critical_vram_free_mb must be positive")
        if self.max_concurrent_ai_jobs != 1:
            raise ValueError("max_concurrent_ai_jobs must be 1 for 8GB VRAM / 16GB RAM safety")
        if self.max_loaded_models != 1:
            raise ValueError("max_loaded_models must be 1 for 8GB VRAM safety")
        if self.monitor_history_maxlen <= 0:
            raise ValueError("monitor_history_maxlen must be positive")


@dataclass(frozen=True)
class AudioConfig:
    """Canonical internal PCM specification and bounded queue/buffer limits."""

    sample_rate: int = 48000
    channels: int = 2
    dtype: str = "float32"
    bytes_per_sample: int = 4
    ring_buffer_seconds: int = 120          # ~46.08 MB decimal / 43.95 MiB raw PCM
    capture_queue_maxsize: int = 64         # Bounded queue (~0.6-1.3s depending on chunk size)
    default_chunk_frames: int = 480         # 10ms @ 48kHz
    underrun_gap_threshold_ms: float = 250.0

    @property
    def frame_bytes(self) -> int:
        return self.channels * self.bytes_per_sample

    @property
    def ring_buffer_raw_bytes(self) -> int:
        return self.sample_rate * self.ring_buffer_seconds * self.frame_bytes

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels not in (1, 2):
            raise ValueError("channels must be 1 or 2")
        if self.dtype != "float32":
            raise ValueError("Canonical internal PCM format must be float32")
        if self.capture_queue_maxsize <= 0:
            raise ValueError("capture_queue_maxsize must be positive")
        if self.ring_buffer_seconds <= 0:
            raise ValueError("ring_buffer_seconds must be positive")
