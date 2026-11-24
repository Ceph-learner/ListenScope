"""Typed data models for system probes, resource monitoring, audio capture, DSP analysis, AI jobs, and MIDI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ResourceStatus(str, Enum):
    NORMAL = "Normal"
    WARNING = "Warning"
    CRITICAL = "Critical"


class CaptureMode(str, Enum):
    PROCESS_LOOPBACK = "process_loopback"
    SYSTEM_LOOPBACK = "system_loopback"
    SYNTHETIC_SIMULATION = "synthetic_simulation"


class AIJobState(str, Enum):
    IDLE = "Idle"
    PREPARING = "Preparing"
    LOADING_MODEL = "LoadingModel"
    INFERRING = "Inferring"
    WRITING = "Writing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    OOM_ERROR = "OOMError"
    FAILED = "Failed"
    EMERGENCY_STOPPED = "EmergencyStopped"


class OOMRecoveryAction(str, Enum):
    REDUCE_SEGMENT = "reduce_segment"
    LIGHTER_MODEL = "lighter_model"
    CPU_FALLBACK = "cpu_fallback"


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
    session_state: str = "unknown"
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


@dataclass
class ChordEstimate:
    primary: str
    secondary: str
    stability: str  # High, Medium, Low, Silent
    correlation: float
    margin: float
    is_silent: bool = False


@dataclass
class KeyEstimate:
    primary: str
    secondary: str
    stability: str  # High, Medium, Low, Insufficient
    correlation: float
    margin: float
    relation_note: str = ""
    key_signature_note: str = "注意：调性中心(Key)与调号(Key Signature)不同，关系大小调/调式混合可能共享调号"
    modulation_hint: bool = False


@dataclass
class TempoEstimate:
    bpm: Optional[float]
    stability: str  # High, Medium, Low, Unknown
    confidence_score: float
    alt_bpm: Optional[float] = None


@dataclass
class PitchEstimate:
    frequency_hz: Optional[float]
    note_name: Optional[str]
    cents_offset: float
    confidence: float
    is_polyphonic: bool = False
    source_band: str = "full"


@dataclass
class AnalysisSnapshot:
    timestamp: float
    waveform_min: list[float]
    waveform_max: list[float]
    fft_freqs_hz: list[float]
    fft_db: list[float]
    log_freqs_hz: list[float]
    log_spectrum_db: list[float]
    chroma_12: list[float]
    chord: ChordEstimate
    key: KeyEstimate
    tempo: TempoEstimate
    pitch: PitchEstimate
    rms_dbfs: float
    peak_dbfs: float
    window_seconds: float
    latency_ms: Optional[float] = None


@dataclass
class AIJobRequest:
    task_id: str
    input_wav_path: str
    output_dir: str
    stem_mode: str  # "2stem" or "4stem"
    model_id: str
    use_gpu: bool = True
    segment_seconds: int = 6
    overlap: float = 0.25
    chunk_seconds: float = 6.0
    simulate_oom: bool = False
    simulate_delay_sec: float = 0.0
    use_mock_backend: bool = False


@dataclass
class AIJobProgress:
    task_id: str
    state: AIJobState
    progress: float  # 0.0 to 1.0
    message: str = ""
    current_chunk: int = 0
    total_chunks: int = 0
    worker_pid: Optional[int] = None
    peak_ram_mb: float = 0.0
    peak_vram_mb: Optional[float] = None


@dataclass
class AIJobResult:
    task_id: str
    state: AIJobState
    stem_paths: dict[str, str] = field(default_factory=dict)
    elapsed_sec: float = 0.0
    input_duration_sec: float = 0.0
    rtf: Optional[float] = None
    device_used: str = "CPU"
    model_id: str = ""
    architecture: str = ""
    oom_occurred: bool = False
    fallback_used: bool = False
    recovery_options: list[OOMRecoveryAction] = field(default_factory=list)
    start_ram_mb: float = 0.0
    peak_ram_mb: float = 0.0
    end_ram_mb: float = 0.0
    start_vram_mb: Optional[float] = None
    peak_vram_mb: Optional[float] = None
    end_vram_mb: Optional[float] = None
    error: Optional[str] = None


@dataclass
class LiveSeparationMetrics:
    active: bool
    model_id: str
    latency_ms: float
    rtf: float
    main_ram_mb: float
    worker_ram_mb: float
    vram_free_mb: Optional[float]
    gpu_util_pct: Optional[float]
    buffer_seconds: float
    max_buffer_seconds: float
    dropped_chunks: int
    status_message: str
    playback_rebuffers: int = 0
    device_underflows: int = 0
    output_overwritten_frames: int = 0


@dataclass
class MidiNoteCandidate:
    pitch_midi: int
    note_name: str
    start_sec: float
    end_sec: float
    velocity: int
    confidence: float


@dataclass
class MidiTranscriptionResult:
    source_stem_name: str
    output_midi_path: Optional[Path]
    notes: list[MidiNoteCandidate] = field(default_factory=list)
    backend_used: str = "basic-pitch"
    warning: Optional[str] = None


@dataclass
class ChordTimelineSegment:
    start_sec: float
    end_sec: float
    chord: str
    secondary: str
    correlation: float
    stability: str


@dataclass
class StemNoteEvent:
    start_sec: float
    end_sec: float
    pitch_midi: int
    note_name: str
    frequency_hz: float
    confidence: float


@dataclass
class BassAnalysisResult:
    stem_path: Path
    duration_sec: float
    lowest_note: Optional[str]
    highest_note: Optional[str]
    root_pitch_classes: list[str] = field(default_factory=list)
    notes: list[StemNoteEvent] = field(default_factory=list)
    signal_detected: Optional[bool] = None
    lowest_midi: Optional[int] = None
    highest_midi: Optional[int] = None
    lowest_freq_hz: Optional[float] = None
    lowest_note_time_sec: Optional[float] = None
    modulation_detected: bool = False
    modulation_note: str = ""


@dataclass
class DrumsAnalysisResult:
    stem_path: Path
    duration_sec: float
    estimated_bpm: Optional[float]
    bpm_stability: str
    kick_times_sec: list[float] = field(default_factory=list)
    snare_times_sec: list[float] = field(default_factory=list)
    hihat_times_sec: list[float] = field(default_factory=list)
    groove_16_step: list[str] = field(default_factory=list)


@dataclass
class MelodyAnalysisResult:
    stem_path: Path
    stem_name: str
    duration_sec: float
    lowest_note: Optional[str]
    highest_note: Optional[str]
    median_note: Optional[str]
    voiced_ratio: float
    notes: list[StemNoteEvent] = field(default_factory=list)


@dataclass
class StemDeepAnalysisReport:
    duration_sec: float
    harmonic_source_label: str
    estimated_key: KeyEstimate
    estimated_bpm: TempoEstimate
    chord_timeline: list[ChordTimelineSegment] = field(default_factory=list)
    bass: Optional[BassAnalysisResult] = None
    drums: Optional[DrumsAnalysisResult] = None
    melody: Optional[MelodyAnalysisResult] = None
    notes: list[str] = field(default_factory=list)

