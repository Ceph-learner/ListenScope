"""Phase 1 audio capture abstractions, PCM normalization, and loopback backends."""

from .capture_base import AudioCaptureBackend, BoundedAudioQueue, CaptureStatsTracker
from .pcm_utils import compute_rms_and_peak, normalize_to_canonical_pcm
from .process_enum import enumerate_audio_processes, resolve_target_pid
from .process_loopback import WasapiProcessLoopbackBackend
from .system_loopback import SyntheticSimulationBackend, WasapiSystemLoopbackBackend

__all__ = [
    "AudioCaptureBackend",
    "BoundedAudioQueue",
    "CaptureStatsTracker",
    "SyntheticSimulationBackend",
    "WasapiProcessLoopbackBackend",
    "WasapiSystemLoopbackBackend",
    "compute_rms_and_peak",
    "enumerate_audio_processes",
    "normalize_to_canonical_pcm",
    "resolve_target_pid",
]
