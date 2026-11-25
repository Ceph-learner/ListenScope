"""ListenScope application entry point & non-blocking controller wiring capture, ring buffer, CPU DSP, A/B playback, AI worker, and UI."""

from __future__ import annotations

import argparse
import gc
import json
import logging
import multiprocessing
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional
import uuid
import wave

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from core.paths import (
    default_work_dir,
    ensure_current_process_in_kill_job,
    get_bundle_root,
    kill_all_active_subprocesses,
    launch_detached,
    prepend_ffmpeg_path_env,
    run_external_python,
    subprocess_no_window_kwargs,
    terminate_all_active_subprocesses,
)

ROOT = get_bundle_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.job_manager import AIJobManager
from analysis.midi_transcription import transcribe_stem_to_midi
from analysis.stem_analyzer import analyze_stems_offline, export_transcription_sheet
from analysis.worker import AnalysisWorker
from audio.bookmarks import ABBookmarkManager
from audio.capture_base import AudioCaptureBackend
from audio.drum_preview import DrumPreviewPlayer, render_drum_preview
from audio.metronome import PracticeMetronome
from audio.pcm_utils import decode_wave_bytes, normalize_to_canonical_pcm
from audio.playback import AB_PAUSE_PLAYER_HINT, HistoryABPlayer, StemMixerEngine
from audio.process_enum import enumerate_audio_processes
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import (
    SYSTEM_LOOPBACK_WARNING,
    SyntheticSimulationBackend,
    WasapiSystemLoopbackBackend,
)
from core.bootstrap_manager import get_bootstrap_manager
from core.config import AIConfig, AnalysisConfig, AudioConfig, ResourceLimits
from core.diagnostics import export_diagnostic_bundle
from core.logging import (
    BoundedMemoryLogHandler,
    PerformanceLogger,
    resolve_log_dir,
    setup_application_file_logging,
    teardown_application_file_logging,
)
from core.media_session import (
    MediaSessionSnapshot,
    TrackChangeTracker,
    TrackTrackerDecision,
    WindowsMediaSessionReader,
    is_python_winrt_smtc_available,
)
from core.models import (
    AIJobProgress,
    AIJobRequest,
    AIJobResult,
    AIJobState,
    CaptureMode,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    OOMRecoveryAction,
    StemDeepAnalysisReport,
)
from core.resource_manager import ResourceManager
from core.settings_store import PersistedSettings, default_settings_path, load_settings, save_settings
from core.system_probe import (
    MIDI_ENV_SETUP_GUIDE,
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_external_midi_environment,
    probe_system,
    scan_local_pytorch_installations,
)
from streaming.live_separator import ExperimentalLiveSeparator
from ui.main_window import ListenScopeMainWindow, _load_app_icon


def _discover_ai_python_executable(*, allow_broad_scan: bool = True) -> Optional[str]:
    """Locate isolated `.venv-ai`, bundled `runtime/ai`, or local PyTorch Python executable."""
    env_override = os.environ.get("LISTENSCOPE_AI_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    exe_dir = Path(sys.executable).resolve().parent
    roots = [ROOT, exe_dir, exe_dir.parent, exe_dir.parent.parent, Path.home() / ".listenscope"]
    candidates: list[Path] = []
    for base in roots:
        candidates.append(base / ".venv-ai" / "Scripts" / "python.exe")
        candidates.append(base / ".venv-ai" / "bin" / "python")
    for base in roots:
        for rel in (("runtime", "ai"), ("runtimes", "ai")):
            candidates.append(base.joinpath(*rel, "python.exe"))
            candidates.append(base.joinpath(*rel, "Scripts", "python.exe"))
            candidates.append(base.joinpath(*rel, "bin", "python"))
    try:
        cur_resolved = Path(sys.executable).resolve()
    except Exception:
        cur_resolved = None
    for cand in candidates:
        if cand.exists():
            try:
                if cur_resolved is not None and cand.resolve() == cur_resolved:
                    continue
            except Exception:
                pass
            return str(cand)
    if allow_broad_scan:
        scanned = scan_local_pytorch_installations(tuple(roots), timeout_per_env_sec=2.5)
        for item in scanned:
            py_exe = str(item.get("python_executable", "")).strip()
            if py_exe and Path(py_exe).exists():
                return py_exe
    return None



def _discover_midi_python_executable() -> Optional[str]:
    """Locate isolated CPU `.venv-midi` or bundled short-path `m` / `runtime/midi` Python 3.11 executable."""
    env_override = os.environ.get("LISTENSCOPE_MIDI_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    exe_dir = Path(sys.executable).resolve().parent
    roots = [ROOT, exe_dir, exe_dir.parent, exe_dir.parent.parent, Path.home() / ".listenscope"]
    candidates: list[Path] = []
    for base in roots:
        candidates.append(base / ".venv-midi" / "Scripts" / "python.exe")
        candidates.append(base / ".venv-midi" / "bin" / "python")
    for base in roots:
        for rel in (("m",), ("runtime", "midi"), ("runtimes", "midi")):
            candidates.append(base.joinpath(*rel, "python.exe"))
            candidates.append(base.joinpath(*rel, "Scripts", "python.exe"))
            candidates.append(base.joinpath(*rel, "bin", "python"))
    if sys.platform == "win32":
        for drive in ("D:", "C:", "E:"):
            candidates.append(Path(f"{drive}\\LS-midi\\.venv-midi\\Scripts\\python.exe"))
            candidates.append(Path(f"{drive}\\LS-midi\\m\\Scripts\\python.exe"))
    try:
        cur_resolved = Path(sys.executable).resolve()
    except Exception:
        cur_resolved = None
    for cand in candidates:
        if cand.exists():
            try:
                if cur_resolved is not None and cand.resolve() == cur_resolved:
                    continue
            except Exception:
                pass
            return str(cand)
    return None


def _read_wav_excerpt_f32(wav_path: Path, *, max_seconds: float = 30.0) -> tuple[np.ndarray, int, int]:
    """Read up to `max_seconds` of a WAV file (16/24/32-bit int or IEEE float32) cleanly."""
    try:
        import soundfile as sf  # type: ignore[import-untyped]

        with sf.SoundFile(str(wav_path), "r") as sf_file:
            sr = int(sf_file.samplerate)
            ch = max(1, int(sf_file.channels))
            take = min(int(sf_file.frames), max(1, int(sr * max_seconds)))
            arr = np.asarray(sf_file.read(take, dtype="float32", always_2d=True), dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            if arr.size > 0 and not np.all(np.isfinite(arr)):
                arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
            return arr, sr, ch
    except Exception:
        with wave.open(str(wav_path), "rb") as wf:
            sr = int(wf.getframerate())
            ch = max(1, int(wf.getnchannels()))
            sw = int(wf.getsampwidth())
            take = min(int(wf.getnframes()), max(1, int(sr * max_seconds)))
            raw = wf.readframes(take)

        arr = decode_wave_bytes(raw, sw, ch)
        return arr, sr, ch


def prune_old_stem_job_dirs(
    work_root: Path,
    keep_recent: int = 5,
    active_dirs: Optional[set[Path]] = None,
) -> int:
    """Prune old stem job subdirectories under `work_root`, keeping the most recent `keep_recent` and `active_dirs`."""
    if not work_root.exists() or not work_root.is_dir():
        return 0
    active_resolved: set[Path] = set()
    for p in active_dirs or ():
        try:
            active_resolved.add(Path(p).resolve())
        except OSError:
            pass
    subdirs: list[tuple[float, Path]] = []
    for entry in work_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            mtime = 0.0
        subdirs.append((mtime, entry))
    subdirs.sort(key=lambda item: item[0], reverse=True)
    keep_n = max(0, int(keep_recent))
    removed = 0
    for idx, (_mtime, d) in enumerate(subdirs):
        if idx < keep_n:
            continue
        try:
            if d.resolve() in active_resolved:
                continue
        except OSError:
            pass
        shutil.rmtree(d, ignore_errors=True)
        logger.info("Pruned old stem job directory: %s", d)
        removed += 1
    return removed


class ListenScopeController:
    """Owns background threads/subprocesses and bridges immutable snapshots to the Qt UI thread."""

    def __init__(
        self,
        *,
        use_mock_ai_for_demo: bool = False,
        ai_python_executable: Optional[str] = None,
        midi_python_executable: Optional[str] = None,
        work_dir: Optional[Path | str] = None,
        settings_path: Optional[Path | str] = None,
    ) -> None:
        self.work_dir = Path(work_dir) if work_dir is not None else default_work_dir()
        self.use_mock_ai_for_demo = use_mock_ai_for_demo
        if settings_path is not None:
            self._settings_path = Path(settings_path)
        elif work_dir is not None and Path(work_dir) != Path("workspace_outputs"):
            self._settings_path = self.work_dir / "settings.json"
        else:
            self._settings_path = default_settings_path()

        saved_settings = load_settings(self._settings_path)
        ai_python_executable_explicit = ai_python_executable is not None
        if ai_python_executable is None:
            cand_py = saved_settings.ai_python_executable
            if cand_py and Path(cand_py).exists():
                ai_python_executable = cand_py
            else:
                ai_python_executable = _discover_ai_python_executable(allow_broad_scan=False)
        if midi_python_executable is None:
            cand_midi = saved_settings.midi_python_executable
            if cand_midi and Path(cand_midi).exists():
                midi_python_executable = cand_midi
            else:
                midi_python_executable = _discover_midi_python_executable()
        self._midi_python_executable: str = str(midi_python_executable or "").strip()

        # Rotating file + bounded diagnostic logging
        setup_application_file_logging(resolve_log_dir(self.work_dir))
        prune_old_stem_job_dirs(self.work_dir / "stems", keep_recent=5)
        self.log_handler = BoundedMemoryLogHandler(maxlen=500)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        self._telem_energy: float = 0.0
        self._telem_avg: float = 0.08
        self._telem_climax: float = 0.0

        self.audio_config = AudioConfig()
        self.analysis_config = AnalysisConfig()
        self.resource_limits = saved_settings.resource_limits
        self.ai_config = saved_settings.ai_config
        self.hardware_report = probe_system()

        self.resource_manager = ResourceManager(limits=self.resource_limits)
        self.ring_buffer = FixedRingBuffer(audio_config=self.audio_config)
        self.analysis_worker = AnalysisWorker(
            self.ring_buffer,
            audio_config=self.audio_config,
            analysis_config=self.analysis_config,
        )
        self.metronome = PracticeMetronome(
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
        )
        self.drum_preview = DrumPreviewPlayer(self.audio_config.sample_rate, self.audio_config.channels)
        self.chord_preview = DrumPreviewPlayer(self.audio_config.sample_rate, self.audio_config.channels)
        self.bookmark_manager = ABBookmarkManager(max_bookmarks=12)
        self.ab_player = HistoryABPlayer(
            self.ring_buffer,
            audio_config=self.audio_config,
            metronome=self.metronome,
        )
        self.mixer_engine = StemMixerEngine(
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
            metronome=self.metronome,
        )
        self.perf_logger = PerformanceLogger(log_dir=self.work_dir / "logs" / "performance")

        self.ai_job_manager = AIJobManager(
            self.resource_manager,
            ai_config=self.ai_config,
            performance_logger=self.perf_logger,
            ai_python_executable=ai_python_executable,
            gpu_readiness_provider=lambda: (
                self.hardware_report.gpu_ai_ready,
                self.hardware_report.gpu_ai_block_reason,
            ),
        )
        self.live_separator = ExperimentalLiveSeparator(
            self.ring_buffer,
            self.resource_manager,
            ai_config=self.ai_config,
            audio_config=self.audio_config,
            is_offline_job_busy_fn=lambda: self.ai_job_manager.is_busy,
            ai_python_executable=ai_python_executable,
        )

        self._capture_backend: Optional[AudioCaptureBackend] = None
        self._drain_stop = threading.Event()
        self._drain_thread: Optional[threading.Thread] = None

        self._ui_ai_progress_q: queue.Queue[AIJobProgress] = queue.Queue(maxsize=64)
        self._ui_ai_result_q: queue.Queue[AIJobResult] = queue.Queue(maxsize=16)
        self._ui_banner_q: queue.Queue[str] = queue.Queue(maxsize=16)
        self._ui_live_bench_q: queue.Queue[str] = queue.Queue(maxsize=8)
        self._ui_live_pending_q: queue.Queue[bool] = queue.Queue(maxsize=8)
        self._ui_midi_result_q: queue.Queue[tuple[int, Optional[MidiTranscriptionResult], Optional[str]]] = queue.Queue(
            maxsize=8
        )
        self._ui_deep_analysis_q: queue.Queue[tuple[int, Optional[StemDeepAnalysisReport], Optional[str]]] = queue.Queue(
            maxsize=4
        )
        self._ui_hw_probe_q: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue(maxsize=4)
        self._ui_ai_discover_q: queue.Queue[str] = queue.Queue(maxsize=2)
        self._ui_track_decision_q: queue.Queue[TrackTrackerDecision] = queue.Queue(maxsize=32)
        self._ui_callbacks_q: queue.Queue[Callable[[], None]] = queue.Queue(maxsize=32)
        self._io_lock = threading.Lock()
        self._io_busy_flags: dict[str, bool] = {"export_ab": False, "export_mix": False, "import_audio": False}
        self._io_threads: list[threading.Thread] = []
        self._probe_seq = 0
        self._stem_generation = 0
        self._cleared_ai_task_id = ""
        self._practice_dirty = False
        self._auto_reset_on_track_change = bool(saved_settings.auto_reset_on_track_change)
        self._auto_track_reset_count = 0
        self._track_tracker = TrackChangeTracker(confirm_polls=2)
        self._track_monitor_stop = threading.Event()
        self._track_monitor_thread: Optional[threading.Thread] = None
        self._track_target_process: Optional[str] = None
        self._last_ai_request: Optional[AIJobRequest] = None
        self._latest_deep_report: Optional[StemDeepAnalysisReport] = None
        self._latest_midi_result: Optional[MidiTranscriptionResult] = None

        self.ai_job_manager.add_progress_callback(self._enqueue_progress)
        self.ai_job_manager.add_completion_callback(self._enqueue_result)

        self.window = ListenScopeMainWindow(
            hardware_report=self.hardware_report,
            resource_limits=self.resource_limits,
            ai_config=self.ai_config,
            mixer_engine=self.mixer_engine,
            ai_python_executable=ai_python_executable or "",
            midi_python_executable=self._midi_python_executable,
            appearance=saved_settings.appearance,
        )
        self.window.close_behavior = str(getattr(saved_settings, "close_behavior", "ask") or "ask")
        if getattr(saved_settings, "window_geometry", ""):
            self.window.restore_saved_geometry(saved_settings.window_geometry)
        self.window.mixer_widget._open_audio_device = not self.use_mock_ai_for_demo
        self.metronome.set_bpm(saved_settings.metronome_bpm)
        self.metronome.set_beats_per_bar(saved_settings.metronome_beats_per_bar)
        self.metronome.set_volume(saved_settings.metronome_volume)
        self.metronome.set_count_in_enabled(saved_settings.metronome_count_in)
        self.window.chroma_widget.sync_metronome_ui(
            bpm=self.metronome.bpm,
            beats_per_bar=self.metronome.beats_per_bar,
            count_in_enabled=self.metronome.count_in_enabled,
            volume=self.metronome.volume,
        )
        self.window.chroma_widget.set_transpose_semitones(saved_settings.transpose_semitones)
        self.window.chroma_widget.set_progression_mode(saved_settings.progression_mode)
        self.window.mixer_widget.set_transpose_semitones(saved_settings.transpose_semitones)
        self.window.chroma_widget.sync_auto_reset_ui(enabled=self._auto_reset_on_track_change)
        self.window.chroma_widget.configure_chord_practice(
            preview_player=self.chord_preview,
            before_play=self._on_before_chord_preview,
        )

        self.window.set_closing_handler(self.shutdown)
        self._connect_signals()
        self.refresh_sources()

        # Start lightweight CPU analysis worker immediately (always CPU-only)
        self.analysis_worker.start()

        # Qt UI refresh timer: consumes snapshots only, zero blocking work
        self._timer = QtCore.QTimer(self.window)
        self._timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._timer.setInterval(45)  # ~22 Hz UI refresh
        self._timer.timeout.connect(self._on_ui_tick)
        self._timer.start()
        self._tick_counter = 0
        self._last_snap_ts: float = 0.0
        self._latest_rsnap: Optional[ResourceSnapshot] = None
        self._res_stop_event = threading.Event()
        self._shutdown_done = False

        def _resource_sampler_loop() -> None:
            while not self._res_stop_event.is_set() and not self._shutdown_done:
                try:
                    self._latest_rsnap = self.resource_manager.sample()
                except Exception:
                    pass
                self._res_stop_event.wait(1.2)

        threading.Thread(
            target=_resource_sampler_loop,
            name="ListenScope-ResourceSampler",
            daemon=True,
        ).start()

        if ai_python_executable:
            self._schedule_external_ai_probe(ai_python_executable)
        elif not self.use_mock_ai_for_demo and not ai_python_executable_explicit:
            def _startup_scan_worker() -> None:
                found_py = _discover_ai_python_executable(allow_broad_scan=True)
                if found_py and not getattr(self, "_shutdown_done", False):
                    self._put_latest(self._ui_ai_discover_q, found_py)

            threading.Thread(
                target=_startup_scan_worker,
                name="ListenScope-StartupPyTorchScan",
                daemon=True,
            ).start()

    @staticmethod
    def _is_external_python(ai_python: Optional[str]) -> bool:
        if not ai_python:
            return False
        try:
            if Path(ai_python).resolve() == Path(sys.executable).resolve():
                return False
        except Exception:
            return True
        return True

    def _schedule_external_ai_probe(self, ai_python: str) -> None:
        if not ai_python:
            return
        if not Path(ai_python).exists():
            self._probe_seq += 1
            self.hardware_report = apply_external_ai_probe_to_report(
                self.hardware_report,
                {"ok": False, "error": f"找不到 AI Worker Python 解释器: {ai_python}"},
            )
            self.window.update_hardware_report(self.hardware_report, auto_sync_gpu_chk=True)
            return
        if not self._is_external_python(ai_python):
            return
        self._probe_seq += 1
        seq = self._probe_seq

        def _run() -> None:
            res = probe_external_ai_environment(ai_python, timeout_sec=15.0)
            if not getattr(self, "_shutdown_done", False):
                self._put_latest(self._ui_hw_probe_q, (seq, res))

        threading.Thread(target=_run, name="ListenScope-ExtAIProbe", daemon=True).start()

    @staticmethod
    def _put_latest(q: queue.Queue[Any], item: Any) -> None:
        while True:
            try:
                q.put_nowait(item)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass

    def _enqueue_progress(self, prog: AIJobProgress) -> None:
        self._put_latest(self._ui_ai_progress_q, prog)

    def _enqueue_result(self, res: AIJobResult) -> None:
        self._put_latest(self._ui_ai_result_q, res)

    def _connect_signals(self) -> None:
        w = self.window
        self._last_mixer_playing = False
        w.refresh_sources_requested.connect(self.refresh_sources)
        w.capture_toggle_requested.connect(self._on_capture_toggle)
        w.ab_select_recent_requested.connect(self._on_ab_select_recent)
        w.ab_set_range_sec_requested.connect(self._on_ab_set_range)
        w.ab_snap_requested.connect(self._on_ab_snap)
        w.ab_play_requested.connect(self._on_ab_play)
        w.history_view_changed.connect(self._refresh_history_overview)
        w.ab_stop_requested.connect(self.ab_player.stop)
        w.ab_loop_toggled.connect(self.ab_player.set_loop)
        w.ab_speed_changed.connect(self.ab_player.set_speed)
        w.ab_export_wav_requested.connect(self._on_export_ab_wav)
        w.import_audio_requested.connect(self._on_import_audio_file)
        w.ai_separate_requested.connect(self._on_start_ai_separation)
        w.emergency_stop_requested.connect(self._on_emergency_stop)
        w.chroma_widget.reset_harmony_requested.connect(self._on_reset_harmony)
        w.chroma_widget.auto_reset_toggled.connect(self._on_auto_reset_toggled)
        w.toggle_playback_requested.connect(self._on_toggle_active_playback)
        w.mixer_widget.before_play_requested.connect(self._on_mixer_before_play)
        w.mixer_widget.cancel_ai_requested.connect(self._on_cancel_ai)
        w.mixer_widget.oom_action_requested.connect(self._on_oom_action)
        w.mixer_widget.export_mix_requested.connect(self._on_export_mix)
        w.mixer_widget.drum_preview_requested.connect(self._on_drum_preview)
        w.mixer_widget.deep_analyze_requested.connect(self._on_deep_analyze_stems)
        w.mixer_widget.midi_settings_requested.connect(lambda: w.open_settings_dialog(focus_midi=True))
        w.mixer_widget.clear_results_requested.connect(self._on_clear_stem_results)
        w.mixer_widget.export_sheet_requested.connect(self._on_export_transcription_sheet)
        w.mixer_widget.save_midi_requested.connect(self._on_save_midi_as)
        w.mixer_widget.send_stem_to_analysis.connect(self._on_send_stem_to_analysis)
        w.mixer_widget.transcribe_stem_midi.connect(self._on_transcribe_stem_midi)
        w.mixer_widget.open_single_stem_midi_requested.connect(self._on_open_single_stem_midi)
        w.live_widget.benchmark_requested.connect(self._on_live_benchmark)
        w.live_widget.start_requested.connect(self._on_live_start)
        w.live_widget.stop_requested.connect(self._on_live_stop)
        w.live_widget.balance_changed.connect(self.live_separator.set_gains)
        w.settings_applied.connect(self._on_settings_applied)
        w.appearance_applied.connect(self._on_appearance_applied)
        w.close_behavior_changed.connect(self._on_close_behavior_changed)
        w.ab_bookmark_save_requested.connect(self._on_ab_bookmark_save)
        w.ab_bookmark_select_requested.connect(self._on_ab_bookmark_select)
        w.ab_bookmark_delete_requested.connect(self._on_ab_bookmark_delete)
        w.chroma_widget.metronome_bpm_changed.connect(self._on_metronome_bpm_changed)
        w.chroma_widget.progression_mode_changed.connect(self._on_progression_mode_changed)
        w.chroma_widget.metronome_beats_changed.connect(self._on_metronome_beats_changed)
        w.chroma_widget.metronome_overlay_toggled.connect(self._on_metronome_overlay_toggled)
        w.chroma_widget.metronome_standalone_toggled.connect(self._on_metronome_standalone_toggled)
        w.chroma_widget.metronome_count_in_toggled.connect(self._on_metronome_count_in_toggled)
        w.chroma_widget.metronome_volume_changed.connect(self._on_metronome_volume_changed)
        w.chroma_widget.transpose_semitones_changed.connect(self._on_transpose_semitones_changed)
        w.mixer_widget.metronome_overlay_toggled.connect(self._on_metronome_overlay_toggled)
        w.resource_panel.export_diagnostics_requested.connect(self._on_export_diagnostic_bundle)
        w.restart_requested.connect(self.restart_application)
        get_bootstrap_manager().completed.connect(self._on_bootstrap_completed)

    def refresh_sources(self) -> None:
        procs = enumerate_audio_processes(include_all_running=False)
        self.window.populate_audio_sources(procs, include_synthetic=True)

    def start_capture(self, source_desc: dict[str, Any]) -> None:
        self.stop_capture()
        kind = source_desc.get("kind", "synthetic")
        target_proc_name: Optional[str] = None
        if kind == "synthetic":
            backend: AudioCaptureBackend = SyntheticSimulationBackend(
                pattern=str(source_desc.get("pattern", "switching")),
                audio_config=self.audio_config,
            )
            self.window.show_banner_message("🧪 当前运行合成测试信号源（非 Windows 真机 WASAPI 捕获）。")
        elif kind == "system_loopback":
            self._stop_drum_preview()
            self._stop_chord_preview()
            backend = WasapiSystemLoopbackBackend(audio_config=self.audio_config)
            self.window.show_banner_message(SYSTEM_LOOPBACK_WARNING)
        else:
            pid = int(source_desc["pid"])
            name = str(source_desc["name"])
            target_proc_name = name
            backend = WasapiProcessLoopbackBackend(pid=pid, process_name=name, audio_config=self.audio_config)
            self.window.show_banner_message("")

        try:
            backend.start()
        except Exception as exc:
            self.window.set_capture_active_ui(False)
            self.window.show_banner_message(f"启动音频捕获失败: {exc}")
            return

        if backend.get_stats().mode == CaptureMode.SYSTEM_LOOPBACK:
            self._stop_drum_preview()
            self._stop_chord_preview()
        self._capture_backend = backend
        self._drain_stop.clear()
        self._drain_thread = threading.Thread(
            target=self._capture_drain_loop,
            args=(backend,),
            name="ListenScope-RingDrain",
            daemon=True,
        )
        self._drain_thread.start()
        self.window.set_capture_active_ui(True)

        if kind == "synthetic":
            self._track_tracker.reset(target_process_name=None)
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text="曲目会话监测 (SMTC): 当前为合成测试信号源（可手动点「换歌重置」或注入 SMTC 模拟测试）"
            )
        else:
            self._start_track_monitor(target_proc_name)

    def stop_capture(self, *, live_stop_reason: str = "捕获已停止，实时分轨已关闭") -> None:
        backend = self._capture_backend
        # Invalidate queued live starts before checking whether the separator has started.
        self._capture_backend = None
        self._drain_stop.set()
        if self.live_separator.is_active or self.live_separator.is_starting:
            self.live_separator.stop(status_message=live_stop_reason)
            self._put_latest(self._ui_live_pending_q, False)
        else:
            self.live_separator.close_output_stream()
        self._stop_track_monitor()
        if backend is not None:
            try:
                backend.stop()
            except Exception:
                pass
        if self._drain_thread is not None and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=2.0)
        self._drain_thread = None
        self.window.set_capture_active_ui(False)
        self.window.chroma_widget.sync_auto_reset_ui(
            track_status_text="曲目会话监测 (SMTC): 已停止捕获（待重新开始后监测）"
        )

    def _on_auto_reset_toggled(self, enabled: bool) -> None:
        self._auto_reset_on_track_change = bool(enabled)
        self._practice_dirty = True
        active_track = self._track_tracker.active_track
        if active_track is not None:
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=(
                    f"曲目监测 (SMTC): {active_track.display_label} "
                    f"(自动切歌重置={'开' if self._auto_reset_on_track_change else '关'})"
                )
            )
        else:
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=(
                    f"曲目会话监测 (SMTC): 自动切歌重置已{'开启' if self._auto_reset_on_track_change else '关闭'}（保留手动重置）"
                )
            )
        self.window.show_banner_message(
            f"{'✅ 已开启自动切歌重置：仅在 SMTC 确认换歌后清空历史，暂停/恢复/拖动进度条不会触发' if self._auto_reset_on_track_change else '已关闭自动切歌重置（可随时手动点击「换歌重置」）'}"
        )

    def _start_track_monitor(self, target_process_name: Optional[str]) -> None:
        self._stop_track_monitor()
        self._track_target_process = target_process_name
        self._track_tracker.reset(target_process_name=target_process_name)
        winrt_ok, backend_name = is_python_winrt_smtc_available()
        if not winrt_ok:
            if sys.platform != "win32":
                msg = "曲目会话监测 (SMTC): 非 Windows 环境未启用 WinRT（可手动「换歌重置」）"
            else:
                msg = (
                    "曲目会话监测 (SMTC): 未检测到 winrt-Windows.Media.Control，"
                    "仅保留手动「换歌重置」（可用 scripts\\setup_windows.ps1 重装 .venv-core）"
                )
            self.window.chroma_widget.sync_auto_reset_ui(track_status_text=msg)
            return

        stop_event = threading.Event()
        self._track_monitor_stop = stop_event
        self.window.chroma_widget.sync_auto_reset_ui(
            track_status_text=f"曲目监测 (SMTC/{backend_name}): 正在等待 {target_process_name or '播放会话'} 元数据..."
        )
        self._track_monitor_thread = threading.Thread(
            target=self._track_monitor_loop,
            args=(target_process_name, stop_event),
            name="ListenScope-SmtcTrackWatch",
            daemon=True,
        )
        self._track_monitor_thread.start()

    def _stop_track_monitor(self) -> None:
        self._track_monitor_stop.set()
        if self._track_monitor_thread is not None and self._track_monitor_thread.is_alive():
            self._track_monitor_thread.join(timeout=1.5)
        self._track_monitor_thread = None
        self._track_target_process = None
        while True:
            try:
                self._ui_track_decision_q.get_nowait()
            except queue.Empty:
                break
        self._track_tracker.reset(target_process_name=None)

    def _enqueue_track_decision(self, decision: TrackTrackerDecision) -> None:
        try:
            self._ui_track_decision_q.put_nowait(decision)
        except queue.Full:
            # Make room only for newest decision if consumer lagged
            try:
                self._ui_track_decision_q.get_nowait()
                self._ui_track_decision_q.put_nowait(decision)
            except Exception:
                pass

    def _track_monitor_loop(
        self,
        _target_process_name: Optional[str],
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        ev = stop_event if stop_event is not None else self._track_monitor_stop
        reader = WindowsMediaSessionReader()
        last_status_key: Optional[tuple[Any, ...]] = None
        try:
            while not ev.is_set() and not getattr(self, "_shutdown_done", False):
                snaps, _backend = reader.query_sessions()
                decision = self._track_tracker.update(snaps)
                cur_sess = decision.selected_session
                key = (
                    decision.triggered_reset,
                    decision.reason,
                    decision.active_track.title_norm if decision.active_track else "",
                    decision.active_track.artist_norm if decision.active_track else "",
                    cur_sess.playback_status if cur_sess else "",
                    decision.pending_count,
                )
                if decision.triggered_reset or key != last_status_key:
                    last_status_key = key
                    self._enqueue_track_decision(decision)
                if ev.wait(1.0):
                    break
        finally:
            reader.close()

    def process_media_session_snapshots(
        self,
        sessions: list[MediaSessionSnapshot] | MediaSessionSnapshot,
    ) -> TrackTrackerDecision:
        """Synchronously evaluate SMTC snapshots and apply guarded reset (used by tests & diagnostics)."""
        decision = self._track_tracker.update(sessions)
        self._apply_track_decision(decision)
        return decision

    def _apply_track_decision(self, decision: TrackTrackerDecision) -> None:
        track_label = decision.active_track.display_label if decision.active_track else "-"
        sess_st = decision.selected_session.playback_status if decision.selected_session else "unknown"
        auto_tag = "开" if self._auto_reset_on_track_change else "关"

        if decision.triggered_reset:
            prev_label = decision.previous_track.display_label if decision.previous_track else "上一首"
            if self._auto_reset_on_track_change:
                self.analysis_worker.reset_harmony()
                self.window.chroma_widget.clear_progression()
                self._auto_track_reset_count += 1
                logging.getLogger(__name__).info("SMTC automatic harmony resets: %d", self._auto_track_reset_count)
                self.window.chroma_widget.sync_auto_reset_ui(
                    track_status_text=f"曲目监测 (SMTC): {track_label} [已自动重置旧曲 {prev_label}]"
                )
                self.window.show_banner_message(
                    f"🎵 检测到切歌（{prev_label} -> {track_label}），已自动重置和弦/调性/BPM 分析历史，实时捕获继续运行。"
                )
            else:
                self.window.chroma_widget.sync_auto_reset_ui(
                    track_status_text=f"曲目监测 (SMTC): {track_label} [自动重置已关闭，可点右侧手动重置]"
                )
            return

        if decision.reason == "no_matching_session":
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text="曲目监测 (SMTC): 未检测到匹配会话，可继续使用右侧「换歌重置」"
            )
        elif decision.reason == "transient_empty_or_changing":
            base_msg = f"曲目监测 (SMTC): {track_label} (切歌/缓冲过渡中，保留当前历史)" if decision.active_track else "曲目监测 (SMTC): 元数据过渡中，保留当前历史"
            self.window.chroma_widget.sync_auto_reset_ui(track_status_text=base_msg)
        elif decision.reason == "same_track_paused":
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=f"曲目监测 (SMTC): {track_label} (paused · 同曲暂停不清空历史)"
            )
        elif decision.reason == "same_track_resumed":
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=f"曲目监测 (SMTC): {track_label} (playing · 恢复播放保留历史)"
            )
        elif decision.reason == "same_track_seek":
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=f"曲目监测 (SMTC): {track_label} (拖动进度条 · 保留和弦历史)"
            )
        elif decision.reason == "pending_confirmation":
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=f"曲目监测 (SMTC): 检测到新曲切换，二次确认中 ({decision.pending_count}/{decision.confirm_polls})..."
            )
        else:
            self.window.chroma_widget.sync_auto_reset_ui(
                track_status_text=f"曲目监测 (SMTC): {track_label} ({sess_st} · 自动重置={auto_tag})"
            )

    def _capture_drain_loop(self, backend: AudioCaptureBackend) -> None:
        while not self._drain_stop.is_set() and backend.is_running:
            chunk = backend.read_chunk(timeout=0.05)
            if chunk is not None and chunk.shape[0] > 0:
                self.ring_buffer.write(chunk)

    def _on_capture_toggle(self, checked: bool, source_desc: dict[str, Any]) -> None:
        if checked:
            self.start_capture(source_desc)
        else:
            self.stop_capture()

    def _on_ab_select_recent(self, seconds: float) -> None:
        try:
            self.ab_player.select_recent_seconds(seconds)
            self.window.show_banner_message(f"已选定最近 {seconds:.1f}s 历史片段。播放前{AB_PAUSE_PLAYER_HINT}")
        except Exception as exc:
            self.window.show_banner_message(f"选择片段提示: {exc}")

    def _on_ab_set_range(self, start_ago_sec: float, end_ago_sec: float) -> None:
        sr = self.ring_buffer.sample_rate
        newest = self.ring_buffer.total_written_frames
        oldest = self.ring_buffer.oldest_abs_frame
        if newest - oldest < int(0.2 * sr):
            self.window.show_banner_message("当前 120s 环形缓冲可用音频不足 0.2s，请先捕获或导入音频。")
            return

        req_start_ago = max(float(start_ago_sec), float(end_ago_sec) + 0.5)
        req_end_ago = min(float(start_ago_sec), float(end_ago_sec))
        raw_a = newest - int(round(req_start_ago * sr))
        raw_b = newest - int(round(req_end_ago * sr))
        if raw_b <= oldest + int(0.2 * sr):
            avail = self.ring_buffer.available_seconds
            self.window.show_banner_message(
                f"⚠️ 所选倒退区间 ({req_start_ago:.1f}s ~ {req_end_ago:.1f}s) 已超出当前已缓冲范围 (仅最近 {avail:.1f}s)，请重新调整 A/B 区间。"
            )
            return

        a = max(oldest, raw_a)
        b = min(newest, raw_b)
        if b - a < int(0.2 * sr):
            a = max(oldest, b - int(round(0.5 * sr)))
        actual_start_ago = (newest - a) / float(sr)
        actual_end_ago = (newest - b) / float(sr)
        self.ab_player.set_ab_range(a, b)
        self.window.show_banner_message(
            f"已设定 A/B 区间（倒退 {actual_start_ago:.1f}s ~ {actual_end_ago:.1f}s，共 {(b - a) / float(sr):.1f}s）。"
        )

    def _on_ab_snap(self) -> None:
        try:
            a, b, newest, delta_a, delta_b = self.ab_player.snap_ab_to_zero()
        except ValueError as exc:
            self.window.show_banner_message(str(exc))
            return
        sr = self.ring_buffer.sample_rate
        self.window.show_snapped_ab((newest - a) / sr, (newest - b) / sr)
        if delta_a or delta_b:
            self.window.show_banner_message(
                f"已微调 A/B 边界（A {delta_a * 1000 / sr:+.2f} ms，B {delta_b * 1000 / sr:+.2f} ms）。"
            )
        else:
            self.window.show_banner_message("附近没有更安静的过零点，A/B 边界保持原样。")

    def _refresh_history_overview(self) -> None:
        older, newer = self.window.history_ago_range
        mins, maxs, span = self.ring_buffer.snapshot_envelope(300, ago_range=(older, newer))
        self.window.update_history_overview(mins, maxs, span, end_ago=newer)

    def _on_drum_preview(self) -> None:
        if self._stop_drum_preview():
            return
        report = self._latest_deep_report
        if report is None or report.drums is None:
            return
        backend = self._capture_backend
        if backend is not None and backend.is_running and backend.get_stats().mode == CaptureMode.SYSTEM_LOOPBACK:
            self.window.show_banner_message("请先停止系统环回捕获，再试听鼓点，避免把试听声录入历史。")
            return
        if self.live_separator.is_active or self.live_separator.is_starting or self.window.live_widget.pending_start:
            self.window.show_banner_message("请先停止近实时分轨监听，再试听鼓点。")
            return
        pcm = render_drum_preview(report.drums, self.drum_preview.sample_rate)
        if not pcm.size:
            self.window.show_banner_message("当前分析没有可试听的鼓点。")
            return
        self._stop_chord_preview()
        self.ab_player.pause()
        self.mixer_engine.pause()
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        try:
            self.drum_preview.play(pcm)
        except Exception as exc:
            self.window.show_banner_message(f"无法打开鼓点试听设备：{exc}")
            return
        self.window.mixer_widget.set_drum_preview_playing(True)

    def _stop_drum_preview(self) -> bool:
        if self.drum_preview.stop():
            self.window.mixer_widget.set_drum_preview_playing(False)
            return True
        return False

    def _stop_chord_preview(self) -> bool:
        stopped = self.chord_preview.stop()
        self.window.chroma_widget.sync_chord_preview_stopped(natural=False)
        return stopped

    def _on_before_chord_preview(self) -> Optional[str]:
        backend = self._capture_backend
        if backend is not None and backend.is_running and backend.get_stats().mode == CaptureMode.SYSTEM_LOOPBACK:
            msg = "请先停止系统环回捕获，再试听练习和弦，避免把试听声录入历史。"
            self.window.show_banner_message(msg)
            return msg
        if self.live_separator.is_active or self.live_separator.is_starting or self.window.live_widget.pending_start:
            msg = "请先停止近实时分轨监听，再试听练习和弦。"
            self.window.show_banner_message(msg)
            return msg
        self._stop_drum_preview()
        self.ab_player.pause()
        self.mixer_engine.pause()
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.live_separator.close_output_stream()
        return None

    def _on_ab_play(self) -> None:
        self._stop_drum_preview()
        self._stop_chord_preview()
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, max(1.0, self.ring_buffer.available_seconds)))
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.mixer_engine.pause()
        self.live_separator.close_output_stream()
        try:
            device_options = {} if self.use_mock_ai_for_demo else {"require_device": True}
            hint = self.ab_player.start_playback(open_audio_device=True, **device_options)
            self.window.show_banner_message(hint)
        except Exception as exc:
            self.window.show_banner_message(f"A/B 回放失败: {exc}")

    def _post_ui_callback(self, fn: Callable[[], None]) -> None:
        if getattr(self, "_shutdown_done", False):
            return
        try:
            self._ui_callbacks_q.put_nowait(fn)
        except queue.Full:
            pass

    def wait_pending_io(self, timeout: float = 10.0) -> None:
        """Wait for any background export/import threads and flush their UI callbacks (for tests/shutdown)."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            with self._io_lock:
                alive = [t for t in self._io_threads if t.is_alive()]
                self._io_threads = alive
            if not alive:
                break
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            alive[0].join(timeout=min(0.1, rem))
        self._drain_ui_callbacks()

    def _drain_ui_callbacks(self) -> None:
        while not getattr(self, "_shutdown_done", False):
            try:
                cb = self._ui_callbacks_q.get_nowait()
            except queue.Empty:
                break
            try:
                cb()
            except Exception:
                logger.exception("Error in deferred UI callback")

    def _on_export_ab_wav(self, out_path: str) -> None:
        if not out_path:
            return
        if self.ring_buffer.available_seconds < 0.2:
            self.window.show_banner_message("当前 120s 环形缓冲可用音频不足，请先捕获或导入本地音频。")
            return
        with self._io_lock:
            if self._io_busy_flags["export_ab"]:
                self.window.show_banner_message("正在导出 A/B 片段，请稍候...")
                return
            self._io_busy_flags["export_ab"] = True
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, self.ring_buffer.available_seconds))
        a_frame, b_frame = self.ab_player.loop_range
        spd = self.ab_player.speed
        inc_met = bool(self.metronome.overlay_enabled)
        bpm = float(self.metronome.bpm)
        beats_per_bar = int(self.metronome.beats_per_bar)
        met_vol = float(self.metronome.volume)
        self.window.show_banner_message("正在后台流式导出 A/B 片段 WAV...")

        def _worker() -> None:
            try:
                saved, dur = self.ab_player.export_ab_practice_wav_streaming(
                    out_path,
                    a_frame,
                    b_frame,
                    speed=spd,
                    include_metronome=inc_met,
                    bpm=bpm,
                    beats_per_bar=beats_per_bar,
                    metronome_volume=met_vol,
                )
                tags: list[str] = []
                if abs(spd - 1.0) >= 1e-3:
                    tags.append(f"{spd:.2f}x不变调")
                if inc_met:
                    tags.append(f"节拍器{bpm:.0f}BPM")
                tag_txt = f" | {'+'.join(tags)}" if tags else ""
                msg = f"✅ 已流式导出 A/B 片段 WAV ({dur:.2f}s{tag_txt}): {saved}"
            except Exception as exc:
                msg = f"导出 A/B 片段失败: {exc}"
            finally:
                with self._io_lock:
                    self._io_busy_flags["export_ab"] = False
            self._post_ui_callback(lambda m=msg: self.window.show_banner_message(m))

        t = threading.Thread(target=_worker, name="ListenScope-ExportAB", daemon=True)
        with self._io_lock:
            self._io_threads = [th for th in self._io_threads if th.is_alive()]
            self._io_threads.append(t)
        t.start()

    def _on_mixer_before_play(self) -> None:
        self._stop_drum_preview()
        self._stop_chord_preview()
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.ab_player.pause()
        self.live_separator.close_output_stream()

    def _on_metronome_bpm_changed(self, bpm: float) -> None:
        self.metronome.set_bpm(bpm)
        self._practice_dirty = True

    def _on_metronome_beats_changed(self, beats: int) -> None:
        self.metronome.set_beats_per_bar(beats)
        self._practice_dirty = True

    def _on_metronome_count_in_toggled(self, enabled: bool) -> None:
        self.metronome.set_count_in_enabled(bool(enabled))
        self._practice_dirty = True

    def _on_metronome_volume_changed(self, volume: float) -> None:
        self.metronome.set_volume(volume)
        self._practice_dirty = True

    def _on_transpose_semitones_changed(self, semitones: int) -> None:
        self.window.mixer_widget.set_transpose_semitones(int(semitones))
        self._practice_dirty = True

    def _on_progression_mode_changed(self, _mode: str) -> None:
        self._practice_dirty = True

    def _on_metronome_overlay_toggled(self, enabled: bool) -> None:
        self.metronome.set_overlay_enabled(bool(enabled))
        self.window.chroma_widget.sync_metronome_ui(overlay_enabled=bool(enabled))
        self.window.mixer_widget.sync_metronome_ui(bool(enabled))

    def _on_metronome_standalone_toggled(self, enabled: bool) -> None:
        if enabled:
            self._stop_drum_preview()
            self._stop_chord_preview()
            self.ab_player.pause()
            self.mixer_engine.pause()
            self.live_separator.close_output_stream()
            self.metronome.start_standalone(open_audio_device=not self.use_mock_ai_for_demo)
            self.window.chroma_widget.sync_metronome_ui(standalone_playing=True)
            self.window.show_banner_message(
                f"✅ 纯 CPU 独立练习节拍器已开启 ({self.metronome.bpm:.1f} BPM, {self.metronome.beats_per_bar} 拍/小节)。"
            )
        else:
            self.metronome.stop_standalone()
            self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)

    def _sync_ab_bookmarks(self) -> None:
        items = self.bookmark_manager.list_bookmarks(
            oldest_abs_frame=self.ring_buffer.oldest_abs_frame,
            newest_abs_frame=self.ring_buffer.total_written_frames,
            sample_rate=self.ring_buffer.sample_rate,
        )
        self.window.update_ab_bookmarks(items)

    def _on_ab_bookmark_save(self, label: str) -> None:
        avail = self.ring_buffer.available_seconds
        if avail < 0.5:
            self.window.show_banner_message("当前 120s 环形缓冲可用音频不足 0.5s，无法保存 A/B 书签。")
            return
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, avail))
        a, b = self.ab_player.loop_range
        oldest = self.ring_buffer.oldest_abs_frame
        a = max(oldest, a)
        if b <= a:
            self.window.show_banner_message("当前 A/B 区间已失效，请重新设定区间后再保存书签。")
            return
        bm = self.bookmark_manager.add_bookmark(a, b, label=label, oldest_abs_frame=oldest)
        self.window.bookmark_label_edit.clear()
        self._sync_ab_bookmarks()
        idx = self.window.bookmark_combo.findData(bm.bookmark_id)
        if idx >= 0:
            self.window.bookmark_combo.setCurrentIndex(idx)
        self.window.show_banner_message(
            f"✅ 已保存 A/B 书签「{bm.label}」({(b - a) / float(self.ring_buffer.sample_rate):.1f}s，上限 12 个)。"
        )

    def _on_ab_bookmark_select(self, bookmark_id: int) -> None:
        oldest = self.ring_buffer.oldest_abs_frame
        newest = self.ring_buffer.total_written_frames
        sr = float(max(1, self.ring_buffer.sample_rate))
        bm = self.bookmark_manager.get_bookmark(bookmark_id, oldest_abs_frame=oldest)
        if bm is None or bm.end_abs_frame <= oldest:
            self._sync_ab_bookmarks()
            self.window.show_banner_message("⚠️ 所选 A/B 书签已滚出最近 120s 环形缓冲并自动清理。")
            return
        a = max(oldest, bm.start_abs_frame)
        b = min(newest, bm.end_abs_frame)
        if b <= a:
            self._sync_ab_bookmarks()
            self.window.show_banner_message("⚠️ 所选 A/B 书签范围无效，已移除。")
            return
        self.ab_player.set_ab_range(a, b)
        start_ago = max(0.5, (newest - a) / sr)
        end_ago = max(0.0, (newest - b) / sr)
        if start_ago - end_ago < 0.5:
            start_ago = min(120.0, end_ago + 0.5)
        self.window.start_ago_spin.setValue(round(start_ago, 2))
        self.window.end_ago_spin.setValue(round(end_ago, 2))
        self.window._set_ab_region_from_ago(start_ago, end_ago)
        self.window.show_banner_message(
            f"✅ 已跳转书签「{bm.label}」(倒退 {start_ago:.1f}s ~ {end_ago:.1f}s，共 {(b - a) / sr:.1f}s)。"
        )

    def _on_ab_bookmark_delete(self, bookmark_id: int) -> None:
        removed = self.bookmark_manager.remove_bookmark(bookmark_id)
        self._sync_ab_bookmarks()
        if removed:
            self.window.show_banner_message("已删除选定 A/B 书签。")

    def _on_export_diagnostic_bundle(self, out_path: str) -> None:
        if not out_path:
            return
        snap = self.resource_manager.latest_snapshot or self.resource_manager.sample()
        hw_rep = self.hardware_report
        limits = self.resource_limits
        ai_cfg = self.ai_config
        ai_py = self.ai_job_manager.ai_python_executable or ""
        midi_py = self._midi_python_executable
        perf_logger = self.perf_logger
        log_handler = self.log_handler
        settings_path = self._settings_path
        live_metrics = self.live_separator.latest_metrics()

        def _run() -> None:
            try:
                saved = export_diagnostic_bundle(
                    out_path,
                    hardware_report=hw_rep,
                    resource_snapshot=snap,
                    resource_limits=limits,
                    ai_config=ai_cfg,
                    ai_python_executable=ai_py,
                    midi_python_executable=midi_py,
                    perf_logger=perf_logger,
                    log_handler=log_handler,
                    settings_path=settings_path,
                    live_separation_metrics=live_metrics,
                )
                msg = f"✅ 已生成离线排障诊断包 (.zip): {saved}"
            except Exception as exc:
                msg = f"导出诊断包失败: {exc}"
            self._put_latest(self._ui_banner_q, msg)

        threading.Thread(target=_run, name="ListenScope-ExportDiag", daemon=True).start()

    def _on_reset_harmony(self) -> None:
        self.analysis_worker.reset_harmony()
        self.window.show_banner_message("✅ 已重置和弦/调性/BPM 分析历史，实时捕获继续运行。")

    def _on_toggle_active_playback(self) -> None:
        stopped_drum = self._stop_drum_preview()
        stopped_chord = self._stop_chord_preview()
        if stopped_drum or stopped_chord:
            return
        if self.window.tabs.currentWidget() is self.window.mixer_widget:
            if self.mixer_engine.is_playing:
                self.mixer_engine.pause()
            elif self.mixer_engine.max_frames > 0:
                self._on_mixer_before_play()
                self.mixer_engine.play(open_audio_device=not self.use_mock_ai_for_demo)
        else:
            if self.ab_player.is_playing:
                self.ab_player.pause()
            elif self.ring_buffer.available_seconds >= 0.2:
                self._on_ab_play()

    def _refresh_resource_ui_now(self) -> None:
        snap = self.resource_manager.latest_snapshot or self.resource_manager.sample()
        self.window.update_resource_snapshot(
            snap,
            self.perf_logger.recent_records(),
            self.log_handler.recent(),
        )

    def _on_start_ai_separation(self, stem_mode: str, model_id: str, segment: int, use_gpu: bool) -> None:
        if self.live_separator.is_active or self.live_separator.is_starting:
            self.window.show_banner_message("请先停止实验性近实时分轨，系统禁止并行运行多个人工智能分轨任务。")
            return
        if self.ring_buffer.available_seconds < 0.5:
            self.window.show_banner_message("当前历史环形缓冲尚不足 0.5s，请先捕获一段音频后再分离。")
            return

        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, self.ring_buffer.available_seconds))

        a_frame, b_frame = self.ab_player.loop_range
        task_id = f"job_{uuid.uuid4().hex[:8]}"
        task_dir = self._prepare_stem_work_dir(task_id)
        in_wav = task_dir / "excerpt_input.wav"
        try:
            _, dur = self.ring_buffer.export_wav_streaming(in_wav, a_frame, b_frame)
        except Exception as exc:
            shutil.rmtree(task_dir, ignore_errors=True)
            self.window.show_banner_message(f"导出待分轨片段失败: {exc}")
            return

        if dur > self.ai_config.default_max_history_ai_seconds:
            self.window.show_banner_message(
                f"⚠️ 所选片段 ({dur:.1f}s) 超过默认 {self.ai_config.default_max_history_ai_seconds:.0f}s 历史建议上限，将启用分块流式推理控制内存。"
            )

        req = AIJobRequest(
            task_id=task_id,
            input_wav_path=str(in_wav),
            output_dir=str(task_dir),
            stem_mode=stem_mode,
            model_id=model_id,
            use_gpu=bool(use_gpu and not self.use_mock_ai_for_demo),
            segment_seconds=segment,
            overlap=self.ai_config.demucs_overlap if stem_mode == "4stem" else self.ai_config.mdx_overlap,
            chunk_seconds=self.ai_config.long_audio_chunk_seconds,
            use_mock_backend=self.use_mock_ai_for_demo,
        )
        ok, msg = self.ai_job_manager.submit_job(req)
        if not ok:
            shutil.rmtree(task_dir, ignore_errors=True)
            self.window.ai_status_badge.setText("AI: Blocked")
            self.window.mixer_widget.job_progress.setValue(0)
            from core.i18n import set_i18n_text
            set_i18n_text(self.window.mixer_widget.job_status_lbl, f"❌ 拒绝启动 AI 分轨: {msg}")
            self._refresh_resource_ui_now()
            self.window.show_banner_message(f"拒绝启动 AI 分轨: {msg}")
        else:
            self._last_ai_request = req
            self.window.tabs.setCurrentWidget(self.window.mixer_widget)
            self.window.show_banner_message(msg)

    def _active_stem_dirs(self) -> set[Path]:
        active: set[Path] = set()
        if self._last_ai_request is not None and self._last_ai_request.output_dir:
            active.add(Path(self._last_ai_request.output_dir))
        for track in getattr(self.mixer_engine, "_tracks", {}).values():
            if getattr(track, "path", None) is not None:
                active.add(Path(track.path).parent)
        return active

    def _prepare_stem_work_dir(self, task_id: str) -> Path:
        stems_root = self.work_dir / "stems"
        prune_old_stem_job_dirs(stems_root, keep_recent=5, active_dirs=self._active_stem_dirs())
        task_dir = stems_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def _on_cancel_ai(self) -> None:
        threading.Thread(target=self.ai_job_manager.cancel_job, name="ListenScope-AICancel", daemon=True).start()

    def _on_emergency_stop(self) -> None:
        def _run() -> None:
            if self.live_separator.is_active or self.live_separator.is_starting:
                self.live_separator.stop(status_message="用户触发紧急停止 AI")
                try:
                    self._ui_live_pending_q.put_nowait(False)
                except queue.Full:
                    pass
            snap = self.ai_job_manager.emergency_stop("用户点击 紧急停止 AI")
            try:
                self._ui_banner_q.put_nowait(
                    f"🛑 用户手动紧急停止 AI：子进程与临时输出已清理，当前可用 RAM={snap.system_ram_available_mb:.0f} MB，"
                    "音频捕获与实时频谱继续正常运行。"
                )
            except queue.Full:
                pass

        threading.Thread(target=_run, name="ListenScope-EmergencyStop", daemon=True).start()

    def _on_oom_action(self, action_val: str) -> None:
        if self._last_ai_request is None:
            return
        prev = self._last_ai_request
        action = OOMRecoveryAction(action_val)
        new_id = f"job_{uuid.uuid4().hex[:8]}"
        new_dir = self._prepare_stem_work_dir(new_id)
        new_req = AIJobRequest(
            task_id=new_id,
            input_wav_path=prev.input_wav_path,
            output_dir=str(new_dir),
            stem_mode=prev.stem_mode,
            model_id=prev.model_id,
            use_gpu=prev.use_gpu,
            segment_seconds=prev.segment_seconds,
            overlap=prev.overlap,
            chunk_seconds=prev.chunk_seconds,
            use_mock_backend=prev.use_mock_backend,
        )
        if action == OOMRecoveryAction.REDUCE_SEGMENT:
            new_req.segment_seconds = max(4, min(prev.segment_seconds - 2, 128))
        elif action == OOMRecoveryAction.LIGHTER_MODEL:
            new_req.stem_mode = "2stem"
            new_req.model_id = "mdx_low_vram_2stem"
            new_req.segment_seconds = 192
        elif action == OOMRecoveryAction.CPU_FALLBACK:
            new_req.use_gpu = False

        ok, msg = self.ai_job_manager.submit_job(new_req)
        if not ok:
            self.window.ai_status_badge.setText("AI: Blocked")
            self.window.mixer_widget.job_progress.setValue(0)
            from core.i18n import set_i18n_text
            set_i18n_text(self.window.mixer_widget.job_status_lbl, f"❌ OOM 恢复启动失败: {msg}")
            self._refresh_resource_ui_now()
            self.window.show_banner_message(f"OOM 恢复启动失败: {msg}")
        else:
            self._last_ai_request = new_req

    def _on_export_mix(self, out_path: str) -> None:
        if not out_path:
            return
        with self._io_lock:
            if self._io_busy_flags["export_mix"]:
                self.window.show_banner_message("正在导出混音，请稍候...")
                return
            self._io_busy_flags["export_mix"] = True
        use_loop = self.mixer_engine.loop_region_sec is not None
        spd = self.mixer_engine.speed
        inc_met = bool(self.metronome.overlay_enabled)
        bpm = float(self.metronome.bpm)
        beats_per_bar = int(self.metronome.beats_per_bar)
        met_vol = float(self.metronome.volume)
        self.window.show_banner_message("正在后台流式导出混合音轨 WAV...")

        def _worker() -> None:
            try:
                saved = self.mixer_engine.export_mix_streaming(
                    out_path,
                    use_loop_region=use_loop,
                    speed=spd,
                    include_metronome=inc_met,
                    bpm=bpm,
                    beats_per_bar=beats_per_bar,
                    metronome_volume=met_vol,
                )
                tags: list[str] = []
                if use_loop:
                    tags.append("局部循环区")
                if abs(spd - 1.0) >= 1e-3:
                    tags.append(f"{spd:.2f}x不变调")
                if inc_met:
                    tags.append(f"节拍器{bpm:.0f}BPM")
                tag_txt = f" ({'+'.join(tags)})" if tags else ""
                msg = f"✅ 已流式导出混合音轨 WAV{tag_txt}: {saved}"
            except Exception as exc:
                msg = f"导出混音失败: {exc}"
            finally:
                with self._io_lock:
                    self._io_busy_flags["export_mix"] = False
            self._post_ui_callback(lambda m=msg: self.window.show_banner_message(m))

        t = threading.Thread(target=_worker, name="ListenScope-ExportMix", daemon=True)
        with self._io_lock:
            self._io_threads = [th for th in self._io_threads if th.is_alive()]
            self._io_threads.append(t)
        t.start()

    def _on_import_audio_file(self, file_path: str) -> None:
        """Stream up to 120s of a local WAV/FLAC/OGG file into the bounded ring buffer."""
        if not file_path:
            return
        src_path = Path(file_path)
        if not src_path.exists():
            self.window.show_banner_message(f"导入本地音频失败: 文件不存在 ({src_path})")
            return
        with self._io_lock:
            if self._io_busy_flags["import_audio"]:
                self.window.show_banner_message("正在导入本地音频，请稍候...")
                return
            self._io_busy_flags["import_audio"] = True

        self.stop_capture(live_stop_reason="已导入本地音频，自动停止实验性实时分轨")
        self._stop_chord_preview()
        self.ab_player.stop()
        self.mixer_engine.pause()
        self.window.show_banner_message(f"正在后台流式载入本地音频: {src_path.name}...")
        max_sec = float(self.audio_config.ring_buffer_seconds)

        def _worker() -> None:
            try:
                imported_sec, truncated = self.ring_buffer.import_audio_file_streaming(
                    src_path,
                    max_seconds=max_sec,
                )

                def _finish_ok() -> None:
                    self.analysis_worker.reset_harmony(include_buffered_audio=True)
                    self.window.chroma_widget.clear_progression()
                    self.bookmark_manager.clear()
                    self._sync_ab_bookmarks()
                    avail = self.ring_buffer.available_seconds
                    if avail >= 0.5:
                        sel = min(30.0, avail)
                        self.ab_player.select_recent_seconds(sel)
                        self.window.start_ago_spin.setValue(round(sel, 2))
                        self.window.end_ago_spin.setValue(0.0)
                        self.window._set_ab_region_from_ago(sel, 0.0)
                    self.window.history_coverage_lbl.setText(
                        f"已缓冲: {avail:.1f} / {self.audio_config.ring_buffer_seconds:.0f}.0 s"
                    )
                    self._refresh_history_overview()
                    if truncated:
                        self.window.show_banner_message(
                            f"⚠️ 本地音频已流式载入前 {imported_sec:.1f}s（超过 {self.audio_config.ring_buffer_seconds:.0f}s 上限已自动截断以保护内存），可直接 A/B 播放或 AI 分轨。"
                        )
                    else:
                        self.window.show_banner_message(
                            f"✅ 已流式载入本地音频 {imported_sec:.1f}s 到环形缓冲，可直接 A/B 播放、实时分析或 AI 分轨。"
                        )

                self._post_ui_callback(_finish_ok)
            except Exception as exc:
                err_msg = f"导入本地音频失败: {exc}"
                self._post_ui_callback(lambda m=err_msg: self.window.show_banner_message(m))
            finally:
                with self._io_lock:
                    self._io_busy_flags["import_audio"] = False

        t = threading.Thread(target=_worker, name="ListenScope-ImportAudio", daemon=True)
        with self._io_lock:
            self._io_threads = [th for th in self._io_threads if th.is_alive()]
            self._io_threads.append(t)
        t.start()

    def _on_send_stem_to_analysis(self, stem_name: str, stem_path: str) -> None:
        """Load selected stem WAV excerpt cleanly into canonical 48kHz stereo ring buffer."""
        try:
            arr, sr, ch = _read_wav_excerpt_f32(Path(stem_path), max_seconds=30.0)
            canon = normalize_to_canonical_pcm(
                arr,
                src_rate=sr,
                src_channels=ch,
                dst_rate=self.audio_config.sample_rate,
                dst_channels=self.audio_config.channels,
            )
            if canon.shape[0] == 0:
                self.window.show_banner_message(f"单轨 `{stem_name}` 不包含有效音频帧。")
                return
            self.stop_capture(live_stop_reason="已载入单轨分析，自动停止实验性实时分轨")
            self._stop_chord_preview()
            self.ab_player.stop()
            self.mixer_engine.pause()
            self.ring_buffer.clear()
            self.ab_player.set_ab_range(0, 0)
            self.bookmark_manager.clear()
            self._sync_ab_bookmarks()
            self.analysis_worker.reset_harmony()
            self.window.chroma_widget.clear_progression()
            self.ring_buffer.write(canon)
            avail = self.ring_buffer.available_seconds
            if avail >= 0.5:
                sel = min(30.0, avail)
                self.ab_player.select_recent_seconds(sel)
                self.window.start_ago_spin.setValue(round(sel, 2))
                self.window.end_ago_spin.setValue(0.0)
                self.window._set_ab_region_from_ago(sel, 0.0)
            self.window.history_coverage_lbl.setText(
                f"已缓冲: {avail:.1f} / {self.audio_config.ring_buffer_seconds:.0f}.0 s"
            )
            self._refresh_history_overview()
            self.window.tabs.setCurrentWidget(self.window.chroma_widget)
            self.window.show_banner_message(f"已将单轨 `{stem_name}` 载入实时和弦/音高分析视图（仅截取前 <=30s）。")
        except Exception as exc:
            self.window.show_banner_message(f"送入分析失败: {exc}")

    def _on_clear_stem_results(self) -> None:
        if self.ai_job_manager.is_busy:
            return
        self._stem_generation += 1
        self._latest_deep_report = None
        self._latest_midi_result = None
        self._cleared_ai_task_id = self.ai_job_manager.latest_progress().task_id
        self._stop_drum_preview()
        self.window.mixer_widget.clear_results()
        self.window.show_banner_message("已清除本次分轨、分析和 MIDI 预览。")

    def _on_deep_analyze_stems(
        self,
        stem_paths: dict[str, str],
        include_sevenths: Optional[bool] = None,
    ) -> None:
        """Run non-destructive CPU streaming analysis over separated stems without touching live capture."""
        if not stem_paths:
            self.window.show_banner_message("当前没有可供深度分析的分轨 WAV 文件。")
            return
        use_7ths = (
            bool(self.window.mixer_widget.include_sevenths)
            if include_sevenths is None
            else bool(include_sevenths)
        )
        mode_tag = "扩展 7 和弦" if use_7ths else "标准三和弦"
        self.window.show_banner_message(
            f"⏳ 正在后台离线流式深度分析分轨 ({mode_tag} / Bass / 鼓组 / 主旋律)..."
        )
        paths_copy = dict(stem_paths)
        max_sec = float(self.audio_config.ring_buffer_seconds)
        req_gen = self._stem_generation

        def _run() -> None:
            try:
                report = analyze_stems_offline(
                    paths_copy,
                    max_seconds=max_sec,
                    include_sevenths=use_7ths,
                )
                msg = (
                    f"✅ 深度分轨分析完成 ({report.duration_sec:.1f}s | {mode_tag})："
                    f"识别 {len(report.chord_timeline)} 段和弦 | 调性={report.estimated_key.primary}"
                )
                self._put_latest(self._ui_deep_analysis_q, (req_gen, report, msg))
            except Exception as exc:
                self._put_latest(self._ui_deep_analysis_q, (req_gen, None, f"深度分轨分析失败: {exc}"))

        threading.Thread(target=_run, name="ListenScope-StemDeepAnalyze", daemon=True).start()

    def _on_export_transcription_sheet(self, out_path: str) -> None:
        if not out_path:
            return
        if self._latest_deep_report is None:
            self.window.show_banner_message("请先点击「深度分析分轨 (和弦/Bass/鼓/旋律)」后再导出扒谱报告。")
            return
        try:
            saved = export_transcription_sheet(
                self._latest_deep_report,
                out_path,
                midi_result=self._latest_midi_result,
                transpose_semitones=self.window.chroma_widget.transpose_semitones,
            )
            self.window.show_banner_message(f"✅ 已导出扒谱与深度分析报告: {saved}")
        except Exception as exc:
            self.window.show_banner_message(f"导出扒谱报告失败: {exc}")

    def _on_save_midi_as(self, out_path: str) -> None:
        if not out_path:
            return
        if self._latest_midi_result is None or self._latest_midi_result.output_midi_path is None:
            self.window.show_banner_message("暂无可另存的 MIDI 文件，请先对某个分轨执行「转 MIDI」。")
            return
        src = Path(self._latest_midi_result.output_midi_path)
        if not src.exists():
            self.window.show_banner_message(f"源 MIDI 文件不存在: {src}")
            return
        try:
            dst = Path(out_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            self.window.show_banner_message(f"✅ 已另存 MIDI 文件: {dst}")
        except Exception as exc:
            self.window.show_banner_message(f"另存 MIDI 失败: {exc}")

    @staticmethod
    def _infer_single_stem_name(wav_path: Path) -> str:
        stem_raw = wav_path.stem.strip()
        low = stem_raw.lower()
        canonical = (
            "vocals",
            "bass",
            "drums",
            "other",
            "instrumental",
            "accompaniment",
            "guitar",
            "piano",
            "melody",
        )
        aliases = {
            "vocal": "vocals",
            "drum": "drums",
            "inst": "instrumental",
            "no_vocals": "instrumental",
            "keys": "piano",
        }
        mix_names = {"mix", "full", "full_mix", "original"}
        tokens = [tok for tok in re.split(r"[^a-z0-9]+", low) if tok]
        if low in mix_names or (tokens and tokens[-1] in mix_names):
            return "mix"
        if low in canonical:
            return low
        if low in aliases:
            return aliases[low]
        for tok in reversed(tokens):
            if tok in canonical:
                return tok
            if tok in aliases:
                return aliases[tok]
        cleaned = re.sub(r'[<>:"/\\|?*]+', "_", stem_raw).strip(" ._") or "stem"
        if cleaned.lower() in mix_names:
            return "mix"
        return cleaned

    def _on_open_single_stem_midi(self, file_path: str) -> None:
        """Load an arbitrary external single-stem WAV into the mixer and start MIDI transcription non-destructively."""
        if not file_path:
            return
        src = Path(file_path)
        if not src.exists():
            msg = f"打开单轨 WAV 失败: 文件不存在 ({src})"
            self.window.mixer_widget.set_midi_error(msg)
            self.window.show_banner_message(msg)
            return

        stem_name = self._infer_single_stem_name(src)
        if stem_name.lower() in ("mix", "full", "full_mix", "original"):
            msg = (
                f"拒绝直接对完整混音 `{src.name}` 转录 MIDI：Basic Pitch 仅建议用于分轨后的单轨 WAV（如 bass.wav / vocals.wav / guitar.wav）。"
            )
            self.window.tabs.setCurrentWidget(self.window.mixer_widget)
            self.window.mixer_widget.analysis_tabs.setCurrentIndex(2)
            self.window.mixer_widget.set_midi_error(msg)
            self.window.show_banner_message(msg)
            return

        try:
            self._stop_drum_preview()
            self._stop_chord_preview()
            self._stem_generation += 1
            self._latest_deep_report = None
            self._latest_midi_result = None
            # Intentionally do NOT call stop_capture() or clear ring_buffer: single-stem MIDI works standalone or alongside capture
            self.window.mixer_widget.load_stem_paths({stem_name: str(src)})
            if stem_name not in self.window.mixer_widget._rows:
                raise ValueError(f"无法读取单轨 WAV 音频帧: {src}")
        except Exception as exc:
            msg = f"载入单轨 WAV 失败 ({src.name}): {exc}"
            self.window.tabs.setCurrentWidget(self.window.mixer_widget)
            self.window.mixer_widget.analysis_tabs.setCurrentIndex(2)
            self.window.mixer_widget.set_midi_error(msg)
            self.window.show_banner_message(msg)
            return

        self.window.tabs.setCurrentWidget(self.window.mixer_widget)
        self.window.mixer_widget.analysis_tabs.setCurrentIndex(2)
        self._on_transcribe_stem_midi(stem_name, str(src))

    def _on_transcribe_stem_midi(self, stem_name: str, stem_path: str) -> None:
        midi_py = str(self._midi_python_executable or "").strip()
        mock_mode = self.use_mock_ai_for_demo
        bundle_root = get_bundle_root()
        req_gen = self._stem_generation

        self.window.mixer_widget.set_midi_transcribing(stem_name, midi_py)
        if midi_py and Path(midi_py).exists():
            self.window.show_banner_message(
                f"⏳ 正在通过独立 MIDI 环境执行 `{stem_name}` 转录 ({midi_py})..."
            )
        else:
            self.window.show_banner_message(
                f"⏳ 未检测到可用独立 `.venv-midi`，正在后台执行 `{stem_name}` 轻量回退 MIDI 转录..."
            )

        def _run() -> None:
            try:
                source_path = Path(stem_path).absolute()
                out_mid = self.work_dir.absolute() / "midi" / f"{uuid.uuid4().hex}.mid"
                can_run_subproc = bool(
                    not mock_mode
                    and midi_py
                    and Path(midi_py).exists()
                    and (not getattr(sys, "frozen", False) or self._is_external_python(midi_py))
                )

                if can_run_subproc:
                    env = prepend_ffmpeg_path_env(os.environ.copy())
                    existing_pp = env.get("PYTHONPATH", "")
                    env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)
                    cmd = [
                        midi_py,
                        "-m",
                        "analysis.midi_transcription",
                        "--audio",
                        str(source_path),
                        "--output-midi",
                        str(out_mid),
                        "--stem-name",
                        stem_name,
                        "--allow-cpu-fallback",
                        "--json",
                    ]
                    try:
                        proc = run_external_python(
                            cmd,
                            cwd=str(bundle_root),
                            env=env,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=180.0,
                            check=True,
                            **subprocess_no_window_kwargs(),
                        )
                    except subprocess.CalledProcessError as exc:
                        tail = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip().splitlines()[-4:]
                        tail_txt = " | ".join(t.strip() for t in tail if t.strip())
                        raise RuntimeError(
                            f"MIDI 子进程退出码={exc.returncode} ({midi_py}): {tail_txt or exc}。{MIDI_ENV_SETUP_GUIDE}"
                        ) from exc

                    data: Optional[dict[str, Any]] = None
                    for ln in reversed(proc.stdout.splitlines()):
                        s = ln.strip()
                        brace = s.find("{")
                        if brace < 0:
                            continue
                        try:
                            parsed = json.loads(s[brace:])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict) and "source_stem_name" in parsed:
                            data = parsed
                            break
                    if data is None:
                        raise RuntimeError(
                            f"无法解析 MIDI 子进程 JSON 输出: {proc.stdout.strip()[-200:]!r}"
                        )
                    warn_txt = data.get("warning")
                    backend_used = str(data.get("backend_used", "basic-pitch"))
                    if backend_used != "basic-pitch":
                        extra = (
                            f"独立 MIDI 解释器 ({midi_py}) 未安装完整 `basic-pitch` 依赖，已自动回退为 `{backend_used}`。"
                            f" {MIDI_ENV_SETUP_GUIDE}"
                        )
                        warn_txt = f"{warn_txt}；{extra}" if warn_txt else extra
                    res = MidiTranscriptionResult(
                        source_stem_name=str(data["source_stem_name"]),
                        output_midi_path=Path(data["output_midi_path"]) if data.get("output_midi_path") else None,
                        notes=[MidiNoteCandidate(**n) for n in (data.get("notes") or [])],
                        backend_used=backend_used,
                        warning=warn_txt,
                    )
                else:
                    missing_reason = ""
                    if not mock_mode:
                        if midi_py and not Path(midi_py).exists():
                            missing_reason = f"找不到配置的 MIDI Python 解释器: {midi_py}"
                        elif getattr(sys, "frozen", False):
                            missing_reason = "打包版尚未配置独立 Python 3.11 CPU MIDI 解释器 (.venv-midi)"
                        elif not midi_py:
                            missing_reason = "未配置独立 Python 3.11 CPU MIDI 解释器 (.venv-midi)"

                    res = transcribe_stem_to_midi(
                        source_path,
                        out_mid,
                        stem_name=stem_name,
                        allow_full_mix=False,
                        allow_cpu_pitch_fallback=True,
                    )
                    if res.backend_used != "basic-pitch" and missing_reason:
                        guide_note = f"{missing_reason}，已使用轻量算法 `{res.backend_used}`。{MIDI_ENV_SETUP_GUIDE}"
                        res = MidiTranscriptionResult(
                            source_stem_name=res.source_stem_name,
                            output_midi_path=res.output_midi_path,
                            notes=res.notes,
                            backend_used=res.backend_used,
                            warning=f"{res.warning} | {guide_note}" if res.warning else guide_note,
                        )

                if res.backend_used == "basic-pitch":
                    done_msg = f"✅ MIDI 转录完成 (实际算法={res.backend_used}, 音符数={len(res.notes)}): {out_mid}"
                else:
                    done_msg = (
                        f"⚠️ MIDI 已生成，实际触发轻量回退算法 `{res.backend_used}` (音符数={len(res.notes)}): {out_mid}"
                        + (f" | {res.warning}" if res.warning else "")
                    )
                self._put_latest(self._ui_midi_result_q, (req_gen, res, done_msg))
            except Exception as exc:
                self._put_latest(self._ui_midi_result_q, (req_gen, None, f"MIDI 转录失败: {exc}"))

        threading.Thread(target=_run, name="ListenScope-MidiTranscribe", daemon=True).start()

    def _on_live_benchmark(self, model_id: str) -> None:
        def _run() -> None:
            try:
                res = self.live_separator.run_benchmark(
                    model_id=model_id,
                    use_gpu=not self.use_mock_ai_for_demo,
                    use_mock_backend=self.use_mock_ai_for_demo,
                )
                msg = res.message
            except Exception as exc:
                msg = f"基准测试失败: {exc}"
            for q in (self._ui_banner_q, self._ui_live_bench_q):
                self._put_latest(q, msg)

        threading.Thread(target=_run, name="ListenScope-LiveBench", daemon=True).start()

    def _on_live_start(self, model_id: str) -> None:
        backend = self._capture_backend
        blocked_reason = ""
        if backend is None or not backend.is_running:
            blocked_reason = "请先开始按进程捕获，再开启近实时分轨监听。"
        elif backend.get_stats().mode == CaptureMode.SYSTEM_LOOPBACK:
            blocked_reason = "系统环回会重新捕获分轨监听输出。请切换到按进程环回后再开启近实时分轨。"
        if blocked_reason:
            self.window.live_widget.set_pending_start(False)
            self.window.update_live_metrics(self.live_separator.latest_metrics())
            self.window.show_banner_message(blocked_reason)
            return

        self._stop_drum_preview()
        self._stop_chord_preview()
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.ab_player.pause()
        self.mixer_engine.pause()

        def _run() -> None:
            try:
                ok, msg = self.live_separator.start(
                    model_id=model_id,
                    use_gpu=not self.use_mock_ai_for_demo,
                    use_mock_backend=self.use_mock_ai_for_demo,
                    open_audio_device=True,
                    gpu_ai_ready=self.hardware_report.gpu_ai_ready,
                    gpu_block_reason=self.hardware_report.gpu_ai_block_reason,
                    source_is_current=lambda: self._capture_backend is backend,
                )
                if self._capture_backend is backend:
                    self._put_latest(self._ui_banner_q, msg if not ok else f"✅ {msg}")
            finally:
                self._put_latest(self._ui_live_pending_q, False)

        threading.Thread(target=_run, name="ListenScope-LiveStart", daemon=True).start()

    def _on_live_stop(self) -> None:
        def _run() -> None:
            self.live_separator.stop()
            self._put_latest(self._ui_live_pending_q, False)

        threading.Thread(target=_run, name="ListenScope-LiveStop", daemon=True).start()

    def _build_persisted_settings(
        self,
        limits: Optional[ResourceLimits] = None,
        ai_cfg: Optional[AIConfig] = None,
        ai_python: Optional[str] = None,
        midi_python: Optional[str] = None,
    ) -> PersistedSettings:
        lim = self.resource_limits if limits is None else limits
        cfg = self.ai_config if ai_cfg is None else ai_cfg
        py = (self.ai_job_manager.ai_python_executable or "") if ai_python is None else ai_python
        mpy = self._midi_python_executable if midi_python is None else str(midi_python or "").strip()
        return PersistedSettings(
            resource_limits=lim,
            ai_config=cfg,
            ai_python_executable=py,
            midi_python_executable=mpy,
            metronome_bpm=self.metronome.bpm,
            metronome_beats_per_bar=self.metronome.beats_per_bar,
            metronome_volume=self.metronome.volume,
            metronome_count_in=self.metronome.count_in_enabled,
            transpose_semitones=self.window.chroma_widget.transpose_semitones,
            auto_reset_on_track_change=self._auto_reset_on_track_change,
            appearance=self.window.appearance,
            progression_mode=self.window.chroma_widget.progression_mode,
            window_geometry=bytes(self.window.saveGeometry().toBase64()).decode("ascii"),
            close_behavior=str(getattr(self.window, "close_behavior", "ask") or "ask"),
        )

    def _on_close_behavior_changed(self, _behavior: str = "ask") -> None:
        try:
            save_settings(self._build_persisted_settings(), self._settings_path)
        except OSError as exc:
            logging.getLogger(__name__).warning("Failed to save close_behavior: %s", exc)

    def _on_appearance_applied(self) -> None:
        try:
            save_settings(self._build_persisted_settings(), self._settings_path)
            self._practice_dirty = False
        except OSError as exc:
            self._practice_dirty = True
            self.window.show_banner_message(f"⚠️ 外观已生效，但写入本地设置失败: {exc}")

    @QtCore.Slot(bool, str, str, str)
    def _on_bootstrap_completed(self, ok: bool, message: str, ai_py: str, midi_py: str) -> None:
        if not ok:
            return
        changed = False
        if ai_py:
            self.ai_job_manager.ai_python_executable = ai_py
            self.live_separator.ai_python_executable = ai_py
            self.window._ai_python_executable = ai_py
            changed = True
        if midi_py:
            self._midi_python_executable = midi_py
            self.window._midi_python_executable = midi_py
            changed = True
        if changed:
            try:
                save_settings(self._build_persisted_settings(), self._settings_path)
                self._practice_dirty = False
            except OSError as exc:
                self._practice_dirty = True
                logging.getLogger(__name__).warning("Failed to save settings after bootstrap: %s", exc)
            if ai_py and not self.use_mock_ai_for_demo:
                self._schedule_external_ai_probe(ai_py)
        self.window.show_banner_message(
            "✅ 一键环境配置已完成并自动保存路径。若未立即刷新或刚安装 Python，可在设置页点击「立即重启」或手动重启应用。",
            tone="ok",
        )

    def restart_application(self) -> None:
        """Persist state, cleanly shut down workers/devices, spawn fresh process, and exit."""
        try:
            save_settings(self._build_persisted_settings(), self._settings_path)
        except Exception:
            pass
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, *sys.argv]
        restart_cwd = str(self.work_dir.parent if self.work_dir.name == "workspace_outputs" else os.getcwd())
        try:
            launch_detached(cmd, cwd=restart_cwd, allow_job_relax=True)
        except Exception as exc:
            logging.getLogger(__name__).exception("Failed to relaunch ListenScope: %s", exc)
            if hasattr(self, "window") and self.window is not None:
                try:
                    self.window.show_banner_message("重启失败，请手动重新打开", tone="warn")
                except Exception:
                    pass
            return
        self.shutdown()
        if hasattr(self, "window") and self.window is not None:
            try:
                self.window.force_quit()
            except Exception:
                pass
        app = QtWidgets.QApplication.instance()
        if isinstance(app, QtWidgets.QApplication):
            app.quit()

    def _on_settings_applied(
        self,
        limits: ResourceLimits,
        ai_cfg: AIConfig,
        ai_python: str,
        midi_python: Optional[str] = None,
    ) -> None:
        self.resource_limits = limits
        self.ai_config = ai_cfg
        self.resource_manager.limits = limits
        self.ai_job_manager.ai_config = ai_cfg
        self.ai_job_manager.ai_python_executable = ai_python or None
        self.live_separator.ai_config = ai_cfg
        self.live_separator.ai_python_executable = ai_python or None

        resolved_midi = (
            str(getattr(self.window, "_midi_python_executable", self._midi_python_executable) or "").strip()
            if midi_python is None
            else str(midi_python or "").strip()
        )
        self._midi_python_executable = resolved_midi
        if hasattr(self.window, "_midi_python_executable"):
            self.window._midi_python_executable = resolved_midi

        verified_probe = self.window.last_verified_ai_probe
        if (
            verified_probe is not None
            and str(verified_probe.get("python_executable", "")) == ai_python
            and (not ai_python or Path(ai_python).exists())
        ):
            self._probe_seq += 1
            self.hardware_report = apply_external_ai_probe_to_report(self.hardware_report, verified_probe)
            self.window.update_hardware_report(self.hardware_report, auto_sync_gpu_chk=True)
        elif ai_python and (not Path(ai_python).exists() or self._is_external_python(ai_python)):
            self._schedule_external_ai_probe(ai_python)
        else:
            self._probe_seq += 1
            self.hardware_report = probe_system()
            self.window.update_hardware_report(self.hardware_report, auto_sync_gpu_chk=True)

        try:
            saved = save_settings(
                self._build_persisted_settings(limits, ai_cfg, ai_python, resolved_midi),
                self._settings_path,
            )
            self._practice_dirty = False
            self.window.show_banner_message(f"✅ 资源安全阈值、AI 与 MIDI 环境配置已保存至 {saved}")
        except Exception as exc:
            self.window.show_banner_message(f"⚠️ 配置已生效，但写入本地设置文件失败: {exc}")

    def _on_ui_tick(self) -> None:
        self._tick_counter += 1

        # Drain thread-safe UI notification queues
        while True:
            try:
                found_py = self._ui_ai_discover_q.get_nowait()
            except queue.Empty:
                break
            try:
                if (
                    found_py
                    and not getattr(self, "_shutdown_done", False)
                    and not self.ai_job_manager.ai_python_executable
                    and Path(found_py).exists()
                ):
                    self.ai_job_manager.ai_python_executable = found_py
                    self.live_separator.ai_python_executable = found_py
                    if hasattr(self.window, "_ai_python_executable"):
                        self.window._ai_python_executable = found_py
                    self._schedule_external_ai_probe(found_py)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_ai_discover_q item")
        while True:
            try:
                seq, probe_data = self._ui_hw_probe_q.get_nowait()
            except queue.Empty:
                break
            try:
                if seq == self._probe_seq:
                    self.hardware_report = apply_external_ai_probe_to_report(self.hardware_report, probe_data)
                    self.window.update_hardware_report(self.hardware_report, auto_sync_gpu_chk=True)
                    if self.hardware_report.gpu_ai_ready:
                        self.window.show_banner_message(
                            "✅ 独立 AI 环境已通过 GPU / CUDA / ONNX 检测，GPU AI 推理已解锁。"
                        )
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_hw_probe_q item")
        while True:
            try:
                progress = self._ui_ai_progress_q.get_nowait()
            except queue.Empty:
                break
            try:
                if not self._cleared_ai_task_id or progress.task_id != self._cleared_ai_task_id:
                    self.window.update_ai_progress(progress)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_ai_progress_q item")
        while True:
            try:
                ai_res = self._ui_ai_result_q.get_nowait()
            except queue.Empty:
                break
            try:
                if self._cleared_ai_task_id and ai_res.task_id == self._cleared_ai_task_id:
                    continue
                if ai_res.state == AIJobState.COMPLETED:
                    self._stop_drum_preview()
                    self._stem_generation += 1
                    self._latest_deep_report = None
                    self._latest_midi_result = None
                self.window.handle_ai_result(ai_res)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_ai_result_q item")
        try:
            self._drain_ui_callbacks()
        except Exception:
            logging.getLogger(__name__).exception("Error in _drain_ui_callbacks")
        while True:
            try:
                banner_msg = self._ui_banner_q.get_nowait()
            except queue.Empty:
                break
            try:
                self.window.show_banner_message(banner_msg)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_banner_q item")
        while True:
            try:
                dec = self._ui_track_decision_q.get_nowait()
            except queue.Empty:
                break
            try:
                self._apply_track_decision(dec)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_track_decision_q item")
        while True:
            try:
                bench_txt = self._ui_live_bench_q.get_nowait()
            except queue.Empty:
                break
            try:
                self.window.live_widget.set_benchmark_text(bench_txt)
            except Exception:
                logging.getLogger(__name__).exception("Error handling _ui_live_bench_q item")
        while True:
            try:
                pending_val = self._ui_live_pending_q.get_nowait()
            except queue.Empty:
                break
            try:
                self.window.live_widget.set_pending_start(pending_val)
            except Exception:
                logger.exception("Error handling _ui_live_pending_q item")
        while True:
            try:
                gen, midi_res, midi_msg = self._ui_midi_result_q.get_nowait()
            except queue.Empty:
                break
            try:
                if gen != self._stem_generation:
                    continue
                if midi_res is not None:
                    self._latest_midi_result = midi_res
                    self.window.display_midi_result(midi_res)
                elif midi_msg:
                    self.window.mixer_widget.set_midi_error(midi_msg)
                if midi_msg:
                    self.window.show_banner_message(midi_msg)
            except Exception:
                logger.exception("Error handling _ui_midi_result_q item")
        while True:
            try:
                gen, deep_res, deep_msg = self._ui_deep_analysis_q.get_nowait()
            except queue.Empty:
                break
            try:
                if gen != self._stem_generation:
                    continue
                if deep_res is not None:
                    self._stop_drum_preview()
                    self._latest_deep_report = deep_res
                    self.window.display_deep_analysis(deep_res)
                if deep_msg:
                    self.window.show_banner_message(deep_msg)
            except Exception:
                logger.exception("Error handling _ui_deep_analysis_q item")

        if self.drum_preview.close_if_finished():
            self.window.mixer_widget.set_drum_preview_playing(False)
        elif self.drum_preview.is_playing:
            self.window.mixer_widget.update_drum_preview_progress(
                self.drum_preview.position_sec,
                self.drum_preview.duration_sec,
            )
        if self.chord_preview.close_if_finished():
            self.window.chroma_widget.sync_chord_preview_stopped(natural=True)
        self.ab_player.close_if_finished()
        self.mixer_engine.close_if_finished()
        self.window.update_ab_playhead(
            active=self.ab_player.is_playing,
            ago_sec=self.ab_player.position_ago_sec,
        )

        mixer_playing = self.mixer_engine.is_playing
        if mixer_playing or getattr(self, "_last_mixer_playing", False) or self._tick_counter % 4 == 0:
            self.window.sync_mixer_position()
        self._last_mixer_playing = mixer_playing

        hidden = (not self.window.isVisible()) or self.window.isMinimized()
        target_interval = 250 if hidden else 45
        if self._timer.interval() != target_interval:
            self._timer.setInterval(target_interval)
        if self.window.isMinimized():
            return
        if (not self.window.isVisible()) and (self._tick_counter % 4 != 0):
            return

        cur_tab = self.window.tabs.currentWidget()

        # Update real-time CPU DSP analysis snapshots (deduplicated by timestamp)
        asnap = self.analysis_worker.latest_snapshot()
        if asnap is not None and float(asnap.timestamp) != self._last_snap_ts:
            self._last_snap_ts = float(asnap.timestamp)
            spec_hist = (
                self.analysis_worker.spectrum.recent_log_spectrogram()
                if (cur_tab is self.window.spectrum_widget and self._tick_counter % 3 == 0)
                else None
            )
            chroma_hist = (
                self.analysis_worker.chroma.recent_chroma_matrix(seconds=30.0)
                if (cur_tab is self.window.chroma_widget and self._tick_counter % 4 == 0)
                else None
            )
            self.window.update_analysis_snapshot(asnap, spectrogram=spec_hist, chroma_history=chroma_hist)
            raw_e = max(0.0, min(1.0, (float(asnap.rms_dbfs) + 52.0) / 46.0)) if asnap.rms_dbfs > -68.0 else 0.0
            raw_p = max(0.0, min(1.0, (float(asnap.peak_dbfs) + 38.0) / 36.0)) if asnap.peak_dbfs > -60.0 else 0.0
            self._telem_energy = 0.55 * self._telem_energy + 0.45 * raw_e
            self._telem_avg = 0.96 * self._telem_avg + 0.04 * self._telem_energy
            surge = max(0.0, (self._telem_energy - self._telem_avg) * 2.8)
            target_climax = max(0.0, min(1.0, 0.55 * surge + 0.45 * max(0.0, raw_p - 0.35)))
            self._telem_climax = 0.60 * self._telem_climax + 0.40 * target_climax
            self.window.update_music_telemetry(self._telem_energy, self._telem_climax)
        elif asnap is None:
            self._telem_energy *= 0.88
            self._telem_climax *= 0.85
            if self._tick_counter % 2 == 0:
                self.window.update_music_telemetry(self._telem_energy, self._telem_climax)

        # Update capture stats, 120s history overview waveform & cached resource monitor on tick 1 and every ~4 ticks (~200ms)
        if self._tick_counter == 1 or self._tick_counter % 4 == 0:
            if self._capture_backend is not None:
                cstats = self._capture_backend.get_stats()
                self.resource_manager.update_runtime_state(
                    audio_queue_size=cstats.queue_size,
                    audio_queue_maxsize=cstats.queue_maxsize,
                )
                self.window.update_capture_stats(cstats, self.ring_buffer.available_seconds)
            else:
                cov_txt = f"已缓冲: {self.ring_buffer.available_seconds:.1f} / 120.0 s"
                if self.window.history_coverage_lbl.text() != cov_txt:
                    self.window.history_coverage_lbl.setText(cov_txt)

            self._refresh_history_overview()
            self._sync_ab_bookmarks()

            rsnap = self._latest_rsnap
            if rsnap is not None:
                self.window.update_resource_snapshot(
                    rsnap,
                    self.perf_logger.recent_records() if cur_tab is self.window.resource_panel else [],
                    self.log_handler.recent() if cur_tab is self.window.resource_panel else [],
                )
            if self.live_separator.is_active or self.live_separator.is_starting or (
                cur_tab is self.window.live_widget and self._tick_counter % 12 == 0
            ):
                self.window.update_live_metrics(self.live_separator.latest_metrics())

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        t_shutdown_start = time.monotonic()
        deadline = t_shutdown_start + 1.6
        s_logger = logging.getLogger("listenscope.shutdown")

        def _run_bounded(stage: str, fn, max_timeout_s: float = 0.35, *, min_timeout_s: float = 0.05) -> None:
            t0 = time.monotonic()
            budget = max(min_timeout_s, min(float(max_timeout_s), deadline - t0))
            done = threading.Event()
            err_box: list[BaseException] = []

            def _target() -> None:
                try:
                    fn()
                except BaseException as exc:
                    err_box.append(exc)
                finally:
                    done.set()

            th = threading.Thread(target=_target, name=f"ListenScope-Shutdown-{stage}", daemon=True)
            th.start()
            finished = done.wait(timeout=budget)
            dt_ms = (time.monotonic() - t0) * 1000.0
            if not finished:
                s_logger.warning("shutdown stage=%s timed out after %.1f ms", stage, dt_ms)
            elif err_box:
                s_logger.warning("shutdown stage=%s error after %.1f ms: %s", stage, dt_ms, err_box[0])
            else:
                s_logger.info("shutdown stage=%s elapsed_ms=%.1f", stage, dt_ms)

        if hasattr(self, "_res_stop_event"):
            self._res_stop_event.set()
        if hasattr(self, "_track_monitor_stop") and self._track_monitor_stop is not None:
            self._track_monitor_stop.set()
        self._probe_seq += 1
        try:
            get_bootstrap_manager().completed.disconnect(self._on_bootstrap_completed)
        except (RuntimeError, TypeError):
            pass
        try:
            get_bootstrap_manager().cancel()
        except Exception:
            pass
        if getattr(self, "_practice_dirty", False) and hasattr(self, "window") and self.window is not None:
            try:
                save_settings(self._build_persisted_settings(), self._settings_path)
                self._practice_dirty = False
            except Exception:
                pass
        if hasattr(self, "_timer"):
            self._timer.stop()
        _run_bounded("previews", lambda: (self._stop_drum_preview(), self._stop_chord_preview()), max_timeout_s=0.15)
        _run_bounded("capture", self.stop_capture, max_timeout_s=0.35)
        _run_bounded("playback", lambda: (self.metronome.stop_standalone(), self.ab_player.stop(), self.mixer_engine.clear()), max_timeout_s=0.20)
        _run_bounded("analysis_worker", self.analysis_worker.stop, max_timeout_s=0.20)
        if self.live_separator.is_active or self.live_separator.is_starting:
            _run_bounded("live_separator", self.live_separator.stop, max_timeout_s=0.20)
        _run_bounded("ai_job_manager", self.ai_job_manager.shutdown, max_timeout_s=0.20)
        _run_bounded(
            "subprocesses",
            lambda: terminate_all_active_subprocesses(timeout=0.18),
            max_timeout_s=0.35,
            min_timeout_s=0.25,
        )
        _run_bounded("resource_manager", self.resource_manager.close, max_timeout_s=0.15)
        s_logger.info("shutdown total elapsed_ms=%.1f", (time.monotonic() - t_shutdown_start) * 1000.0)
        logging.getLogger().removeHandler(self.log_handler)
        teardown_application_file_logging()
        if hasattr(self, "window") and self.window is not None:
            self.window.set_closing_handler(None)
            try:
                self.window.prepare_for_shutdown()
            except Exception:
                pass
            self.window.deleteLater()


def main(argv: Optional[list[str]] = None) -> int:
    multiprocessing.freeze_support()
    ensure_current_process_in_kill_job()
    parser = argparse.ArgumentParser(description="ListenScope Desktop Application")
    parser.add_argument("--simulate", action="store_true", help="启动合成信号 + Mock 测试模式（用于无真机调试）")
    parser.add_argument("--ai-python", type=str, default=None, help="独立 AI Worker 虚拟环境 python.exe 路径")
    parser.add_argument("--midi-python", type=str, default=None, help="独立 CPU Basic Pitch MIDI 虚拟环境 python.exe 路径")
    parser.add_argument("--settings", type=str, default=None, help="自定义持久化 settings.json 路径")
    parser.add_argument("--headless-smoke", action="store_true", help="短时运行后干净退出（测试用途）")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        import ctypes

        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        set_app_id("ListenScope.Desktop")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app_icon = _load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=args.simulate,
        ai_python_executable=args.ai_python,
        midi_python_executable=args.midi_python,
        settings_path=args.settings,
    )
    if args.simulate:
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})

    ctrl.window.show()
    if args.headless_smoke:
        QtCore.QTimer.singleShot(300, ctrl.window.force_quit)
    ret = app.exec()
    shutdown_done = threading.Event()

    def _exit_watchdog() -> None:
        if not shutdown_done.wait(timeout=2.0):
            kill_all_active_subprocesses()
            os._exit(0)

    threading.Thread(
        target=_exit_watchdog,
        name="ListenScope-ExitWatchdog",
        daemon=True,
    ).start()
    try:
        ctrl.shutdown()
        del ctrl
        app.processEvents()
        gc.collect()
        app.processEvents()
    finally:
        shutdown_done.set()
    return int(ret)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
