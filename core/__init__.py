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
from .settings_store import PersistedSettings, default_settings_path, load_settings, save_settings
from .system_probe import generate_system_report_markdown, probe_external_ai_environment, probe_system

__all__ = [
    "AudioConfig",
    "AudioProcessInfo",
    "CaptureMode",
    "CaptureStats",
    "PersistedSettings",
    "ResourceLimits",
    "ResourceManager",
    "ResourceSnapshot",
    "ResourceStatus",
    "SystemHardwareReport",
    "TargetHardwareSpec",
    "default_settings_path",
    "generate_system_report_markdown",
    "load_settings",
    "probe_external_ai_environment",
    "probe_system",
    "save_settings",
]

