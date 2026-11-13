"""Phase 1-4 audio capture, ring buffer, playback, and stem mixer package."""

from .capture_base import AudioCaptureBackend, BoundedAudioQueue, CaptureStatsTracker
from .pcm_utils import compute_rms_and_peak, normalize_to_canonical_pcm
from .playback import AB_PAUSE_PLAYER_HINT, HistoryABPlayer, StemMixerEngine, StemTrackState
from .process_enum import enumerate_audio_processes, resolve_target_pid
from .process_loopback import WasapiProcessLoopbackBackend
from .ring_buffer import FixedRingBuffer
from .system_loopback import SyntheticSimulationBackend, WasapiSystemLoopbackBackend

__all__ = [
    "AB_PAUSE_PLAYER_HINT",
    "AudioCaptureBackend",
    "BoundedAudioQueue",
    "CaptureStatsTracker",
    "FixedRingBuffer",
    "HistoryABPlayer",
    "StemMixerEngine",
    "StemTrackState",
    "SyntheticSimulationBackend",
    "WasapiProcessLoopbackBackend",
    "WasapiSystemLoopbackBackend",
    "compute_rms_and_peak",
    "enumerate_audio_processes",
    "normalize_to_canonical_pcm",
    "resolve_target_pid",
]
