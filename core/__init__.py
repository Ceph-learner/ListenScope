"""Core configuration, models, system probe, and resource management for ListenScope."""

from .config import AudioConfig, ResourceLimits, TargetHardwareSpec
from .models import (
    AudioProcessInfo,
    CaptureMode,
    CaptureStats,
    ResourceSnapshot,
    ResourceStatus,
    SystemHardwareReport,
)
from .resource_manager import ResourceManager
from .system_probe import generate_system_report_markdown, probe_system

__all__ = [
    "AudioConfig",
    "AudioProcessInfo",
    "CaptureMode",
    "CaptureStats",
    "ResourceLimits",
    "ResourceManager",
    "ResourceSnapshot",
    "ResourceStatus",
    "SystemHardwareReport",
    "TargetHardwareSpec",
    "generate_system_report_markdown",
    "probe_system",
]
