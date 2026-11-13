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
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional
import uuid
import wave

import numpy as np
from PySide6 import QtCore, QtWidgets

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from core.paths import get_bundle_root, subprocess_no_window_kwargs

ROOT = get_bundle_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.job_manager import AIJobManager
from analysis.midi_transcription import transcribe_stem_to_midi
from analysis.stem_analyzer import analyze_stems_offline, export_transcription_sheet
from analysis.worker import AnalysisWorker
from audio.bookmarks import ABBookmarkManager
from audio.capture_base import AudioCaptureBackend
from audio.metronome import PracticeMetronome
from audio.pcm_utils import normalize_to_canonical_pcm
from audio.playback import AB_PAUSE_PLAYER_HINT, HistoryABPlayer, StemMixerEngine
from audio.process_enum import enumerate_audio_processes
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import (
    SYSTEM_LOOPBACK_WARNING,
    SyntheticSimulationBackend,
    WasapiSystemLoopbackBackend,
)
from core.config import AIConfig, AnalysisConfig, AudioConfig, ResourceLimits
from core.diagnostics import export_diagnostic_bundle
from core.logging import BoundedMemoryLogHandler, PerformanceLogger
from core.models import (
    AIJobProgress,
    AIJobRequest,
    AIJobResult,
    AIJobState,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    OOMRecoveryAction,
    StemDeepAnalysisReport,
)
from core.resource_manager import ResourceManager
from core.settings_store import PersistedSettings, default_settings_path, load_settings, save_settings
from core.system_probe import (
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_system,
)
from streaming.live_separator import ExperimentalLiveSeparator
from ui.main_window import ListenScopeMainWindow


def _discover_ai_python_executable() -> Optional[str]:
    """Locate isolated `.venv-ai` Python executable across source & frozen PyInstaller layouts."""
    exe_dir = Path(sys.executable).resolve().parent
    roots = [ROOT, exe_dir, exe_dir.parent, exe_dir.parent.parent]
    candidates: list[Path] = []
    for base in roots:
        candidates.append(base / ".venv-ai" / "Scripts" / "python.exe")
        candidates.append(base / ".venv-ai" / "bin" / "python")
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
            ch = int(sf_file.channels)
            take = min(int(sf_file.frames), max(1, int(sr * max_seconds)))
            arr = np.asarray(sf_file.read(take, dtype="float32", always_2d=True), dtype=np.float32)
            return arr, sr, ch
    except Exception:
        with wave.open(str(wav_path), "rb") as wf:
            sr = int(wf.getframerate())
            ch = max(1, int(wf.getnchannels()))
            sw = int(wf.getsampwidth())
            take = min(int(wf.getnframes()), max(1, int(sr * max_seconds)))
            raw = wf.readframes(take)

        if sw == 2:
            flat = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 3:
            raw_u8 = np.frombuffer(raw, dtype=np.uint8)
            usable_b = (raw_u8.size // 3) * 3
            triplets = raw_u8[:usable_b].reshape(-1, 3).astype(np.int32)
            signed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
            signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
            flat = signed.astype(np.float32) / 8388608.0
        elif sw == 4:
            flat = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            flat = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        usable = (flat.size // ch) * ch
        return flat[:usable].reshape(-1, ch), sr, ch


class ListenScopeController:
    """Owns background threads/subprocesses and bridges immutable snapshots to the Qt UI thread."""

    def __init__(
        self,
        *,
        use_mock_ai_for_demo: bool = False,
        ai_python_executable: Optional[str] = None,
        work_dir: Path | str = Path("workspace_outputs"),
        settings_path: Optional[Path | str] = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.use_mock_ai_for_demo = use_mock_ai_for_demo
        if settings_path is not None:
            self._settings_path = Path(settings_path)
        elif self.work_dir != Path("workspace_outputs"):
            self._settings_path = self.work_dir / "settings.json"
        else:
            self._settings_path = default_settings_path()

        saved_settings = load_settings(self._settings_path)
        if ai_python_executable is None:
            cand_py = saved_settings.ai_python_executable
            if cand_py and Path(cand_py).exists():
                ai_python_executable = cand_py
            else:
                ai_python_executable = _discover_ai_python_executable()

        # Bounded diagnostic logging
        self.log_handler = BoundedMemoryLogHandler(maxlen=500)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

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
        self._ui_midi_result_q: queue.Queue[tuple[Optional[MidiTranscriptionResult], Optional[str]]] = queue.Queue(maxsize=8)
        self._ui_deep_analysis_q: queue.Queue[tuple[Optional[StemDeepAnalysisReport], Optional[str]]] = queue.Queue(maxsize=4)
        self._ui_hw_probe_q: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue(maxsize=4)
        self._probe_seq = 0
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
        )
        self.window.set_closing_handler(self.shutdown)
        self._connect_signals()
        self.refresh_sources()

        # Start lightweight CPU analysis worker immediately (always CPU-only)
        self.analysis_worker.start()

        # Qt UI refresh timer: consumes snapshots only, zero blocking work
        self._timer = QtCore.QTimer(self.window)
        self._timer.setInterval(45)  # ~22 Hz UI refresh
        self._timer.timeout.connect(self._on_ui_tick)
        self._timer.start()
        self._tick_counter = 0
        self._shutdown_done = False

        if ai_python_executable:
            self._schedule_external_ai_probe(ai_python_executable)

    @staticmethod
    def _is_external_python(ai_python: Optional[str]) -> bool:
        if not ai_python:
            return False
        if getattr(sys, "frozen", False):
            return True
        try:
            return Path(ai_python).resolve() != Path(sys.executable).resolve()
        except Exception:
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
        w.ab_play_requested.connect(self._on_ab_play)
        w.ab_stop_requested.connect(self.ab_player.stop)
        w.ab_loop_toggled.connect(self.ab_player.set_loop)
        w.ab_speed_changed.connect(self.ab_player.set_speed)
        w.ab_export_wav_requested.connect(self._on_export_ab_wav)
        w.import_audio_requested.connect(self._on_import_audio_file)
        w.ai_separate_requested.connect(self._on_start_ai_separation)
        w.emergency_stop_requested.connect(self._on_emergency_stop)
        w.chroma_widget.reset_harmony_requested.connect(self._on_reset_harmony)
        w.toggle_playback_requested.connect(self._on_toggle_active_playback)
        w.mixer_widget.before_play_requested.connect(self._on_mixer_before_play)
        w.mixer_widget.cancel_ai_requested.connect(self._on_cancel_ai)
        w.mixer_widget.oom_action_requested.connect(self._on_oom_action)
        w.mixer_widget.export_mix_requested.connect(self._on_export_mix)
        w.mixer_widget.deep_analyze_requested.connect(self._on_deep_analyze_stems)
        w.mixer_widget.export_sheet_requested.connect(self._on_export_transcription_sheet)
        w.mixer_widget.save_midi_requested.connect(self._on_save_midi_as)
        w.mixer_widget.send_stem_to_analysis.connect(self._on_send_stem_to_analysis)
        w.mixer_widget.transcribe_stem_midi.connect(self._on_transcribe_stem_midi)
        w.live_widget.benchmark_requested.connect(self._on_live_benchmark)
        w.live_widget.start_requested.connect(self._on_live_start)
        w.live_widget.stop_requested.connect(self._on_live_stop)
        w.live_widget.balance_changed.connect(self.live_separator.set_gains)
        w.settings_applied.connect(self._on_settings_applied)
        w.ab_bookmark_save_requested.connect(self._on_ab_bookmark_save)
        w.ab_bookmark_select_requested.connect(self._on_ab_bookmark_select)
        w.ab_bookmark_delete_requested.connect(self._on_ab_bookmark_delete)
        w.chroma_widget.metronome_bpm_changed.connect(self.metronome.set_bpm)
        w.chroma_widget.metronome_beats_changed.connect(self.metronome.set_beats_per_bar)
        w.chroma_widget.metronome_overlay_toggled.connect(self._on_metronome_overlay_toggled)
        w.chroma_widget.metronome_standalone_toggled.connect(self._on_metronome_standalone_toggled)
        w.mixer_widget.metronome_overlay_toggled.connect(self._on_metronome_overlay_toggled)
        w.resource_panel.export_diagnostics_requested.connect(self._on_export_diagnostic_bundle)

    def refresh_sources(self) -> None:
        procs = enumerate_audio_processes(include_all_running=False)
        self.window.populate_audio_sources(procs, include_synthetic=True)

    def start_capture(self, source_desc: dict[str, Any]) -> None:
        self.stop_capture()
        kind = source_desc.get("kind", "synthetic")
        if kind == "synthetic":
            backend: AudioCaptureBackend = SyntheticSimulationBackend(
                pattern=str(source_desc.get("pattern", "switching")),
                audio_config=self.audio_config,
            )
            self.window.show_banner_message("🧪 当前运行合成测试信号源（非 Windows 真机 WASAPI 捕获）。")
        elif kind == "system_loopback":
            backend = WasapiSystemLoopbackBackend(audio_config=self.audio_config)
            self.window.show_banner_message(SYSTEM_LOOPBACK_WARNING)
        else:
            pid = int(source_desc["pid"])
            name = str(source_desc["name"])
            backend = WasapiProcessLoopbackBackend(pid=pid, process_name=name, audio_config=self.audio_config)
            self.window.show_banner_message("")

        try:
            backend.start()
        except Exception as exc:
            self.window.set_capture_active_ui(False)
            self.window.show_banner_message(f"启动音频捕获失败: {exc}")
            return

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

    def stop_capture(self) -> None:
        self._drain_stop.set()
        if self._capture_backend is not None:
            try:
                self._capture_backend.stop()
            except Exception:
                pass
            self._capture_backend = None
        if self._drain_thread is not None and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=2.0)
        self._drain_thread = None
        self.window.set_capture_active_ui(False)

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

    def _on_ab_play(self) -> None:
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, max(1.0, self.ring_buffer.available_seconds)))
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.mixer_engine.pause()
        self.live_separator.close_output_stream()
        try:
            hint = self.ab_player.start_playback(open_audio_device=True)
            self.window.show_banner_message(hint)
        except Exception as exc:
            self.window.show_banner_message(f"A/B 回放失败: {exc}")

    def _on_export_ab_wav(self, out_path: str) -> None:
        if not out_path:
            return
        if self.ring_buffer.available_seconds < 0.2:
            self.window.show_banner_message("当前 120s 环形缓冲可用音频不足，请先捕获或导入本地音频。")
            return
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, self.ring_buffer.available_seconds))
        a_frame, b_frame = self.ab_player.loop_range
        try:
            saved, dur = self.ring_buffer.export_wav_streaming(out_path, a_frame, b_frame)
            self.window.show_banner_message(f"✅ 已流式导出 A/B 片段 WAV ({dur:.2f}s): {saved}")
        except Exception as exc:
            self.window.show_banner_message(f"导出 A/B 片段失败: {exc}")

    def _on_mixer_before_play(self) -> None:
        self.metronome.stop_standalone()
        self.window.chroma_widget.sync_metronome_ui(standalone_playing=False)
        self.ab_player.pause()
        self.live_separator.close_output_stream()

    def _on_metronome_overlay_toggled(self, enabled: bool) -> None:
        self.metronome.set_overlay_enabled(bool(enabled))
        self.window.chroma_widget.sync_metronome_ui(overlay_enabled=bool(enabled))
        self.window.mixer_widget.sync_metronome_ui(bool(enabled))

    def _on_metronome_standalone_toggled(self, enabled: bool) -> None:
        if enabled:
            self.ab_player.pause()
            self.mixer_engine.pause()
            self.live_separator.close_output_stream()
            self.metronome.start_standalone(open_audio_device=True)
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
        perf_logger = self.perf_logger
        log_handler = self.log_handler
        settings_path = self._settings_path

        def _run() -> None:
            try:
                saved = export_diagnostic_bundle(
                    out_path,
                    hardware_report=hw_rep,
                    resource_snapshot=snap,
                    resource_limits=limits,
                    ai_config=ai_cfg,
                    ai_python_executable=ai_py,
                    perf_logger=perf_logger,
                    log_handler=log_handler,
                    settings_path=settings_path,
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
        if self.window.tabs.currentWidget() is self.window.mixer_widget:
            if self.mixer_engine.is_playing:
                self.mixer_engine.pause()
            elif self.mixer_engine.max_frames > 0:
                self._on_mixer_before_play()
                self.mixer_engine.play(open_audio_device=True)
        else:
            if self.ab_player.is_playing:
                self.ab_player.pause()
            elif self.ring_buffer.available_seconds >= 0.2:
                self._on_ab_play()

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
        task_dir = self.work_dir / "stems" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
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
            self.window.show_banner_message(f"拒绝启动 AI 分轨: {msg}")
        else:
            self._last_ai_request = req
            self.window.tabs.setCurrentWidget(self.window.mixer_widget)
            self.window.show_banner_message(msg)

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
                    f"🛑 已执行紧急停止 AI：子进程与临时输出已清理，当前可用 RAM={snap.system_ram_available_mb:.0f} MB，"
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
        new_req = AIJobRequest(
            task_id=new_id,
            input_wav_path=prev.input_wav_path,
            output_dir=str(self.work_dir / "stems" / new_id),
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
            self.window.show_banner_message(f"OOM 恢复启动失败: {msg}")
        else:
            self._last_ai_request = new_req

    def _on_export_mix(self, out_path: str) -> None:
        try:
            saved = self.mixer_engine.export_mix_streaming(out_path)
            self.window.show_banner_message(f"✅ 已流式导出混合音轨 WAV: {saved}")
        except Exception as exc:
            self.window.show_banner_message(f"导出混音失败: {exc}")

    def _on_import_audio_file(self, file_path: str) -> None:
        """Stream up to 120s of a local WAV/FLAC/OGG file into the bounded ring buffer."""
        if not file_path:
            return
        try:
            self.stop_capture()
            self.ab_player.stop()
            self.mixer_engine.pause()
            self.live_separator.close_output_stream()
            imported_sec, truncated = self.ring_buffer.import_audio_file_streaming(
                file_path,
                max_seconds=float(self.audio_config.ring_buffer_seconds),
            )
            self.analysis_worker.reset_harmony()
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
            mins, maxs, avail_sec = self.ring_buffer.snapshot_envelope(300)
            self.window.update_history_overview(mins, maxs, avail_sec)
            if truncated:
                self.window.show_banner_message(
                    f"⚠️ 本地音频已流式载入前 {imported_sec:.1f}s（超过 {self.audio_config.ring_buffer_seconds:.0f}s 上限已自动截断以保护内存），可直接 A/B 播放或 AI 分轨。"
                )
            else:
                self.window.show_banner_message(
                    f"✅ 已流式载入本地音频 {imported_sec:.1f}s 到环形缓冲，可直接 A/B 播放、实时分析或 AI 分轨。"
                )
        except Exception as exc:
            self.window.show_banner_message(f"导入本地音频失败: {exc}")

    def _on_send_stem_to_analysis(self, stem_name: str, stem_path: str) -> None:
        """Load selected stem WAV excerpt cleanly into canonical 48kHz stereo ring buffer."""
        try:
            self.stop_capture()
            self.ab_player.stop()
            self.ring_buffer.clear()
            self.ab_player.set_ab_range(0, 0)
            self.bookmark_manager.clear()
            self._sync_ab_bookmarks()
            self.analysis_worker.reset_harmony()
            self.window.chroma_widget.clear_progression()
            arr, sr, ch = _read_wav_excerpt_f32(Path(stem_path), max_seconds=30.0)
            canon = normalize_to_canonical_pcm(
                arr,
                src_rate=sr,
                src_channels=ch,
                dst_rate=self.audio_config.sample_rate,
                dst_channels=self.audio_config.channels,
            )
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
            mins, maxs, avail_sec = self.ring_buffer.snapshot_envelope(300)
            self.window.update_history_overview(mins, maxs, avail_sec)
            self.window.tabs.setCurrentWidget(self.window.chroma_widget)
            self.window.show_banner_message(f"已将单轨 `{stem_name}` 载入实时和弦/音高分析视图（仅截取前 <=30s）。")
        except Exception as exc:
            self.window.show_banner_message(f"送入分析失败: {exc}")

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
                self._put_latest(self._ui_deep_analysis_q, (report, msg))
            except Exception as exc:
                self._put_latest(self._ui_deep_analysis_q, (None, f"深度分轨分析失败: {exc}"))

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

    def _on_transcribe_stem_midi(self, stem_name: str, stem_path: str) -> None:
        out_mid = Path(stem_path).with_suffix(".mid")
        self.window.show_banner_message(f"⏳ 正在后台执行 `{stem_name}` MIDI 转录...")
        ai_py = self.ai_job_manager.ai_python_executable
        mock_mode = self.use_mock_ai_for_demo
        bundle_root = get_bundle_root()

        def _run() -> None:
            try:
                use_ext = bool(ai_py and not mock_mode and self._is_external_python(ai_py))

                if use_ext and ai_py is not None:
                    env = os.environ.copy()
                    existing_pp = env.get("PYTHONPATH", "")
                    env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)
                    cmd = [
                        ai_py,
                        "-m",
                        "analysis.midi_transcription",
                        "--audio",
                        str(stem_path),
                        "--output-midi",
                        str(out_mid),
                        "--stem-name",
                        stem_name,
                        "--allow-cpu-fallback",
                        "--json",
                    ]
                    proc = subprocess.run(
                        cmd,
                        cwd=str(bundle_root),
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=180.0,
                        check=True,
                        **subprocess_no_window_kwargs(),
                    )
                    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
                    candidate = lines[-1] if lines else proc.stdout.strip()
                    brace = candidate.find("{")
                    if brace > 0:
                        candidate = candidate[brace:]
                    data = json.loads(candidate)
                    res = MidiTranscriptionResult(
                        source_stem_name=str(data["source_stem_name"]),
                        output_midi_path=Path(data["output_midi_path"]) if data.get("output_midi_path") else None,
                        notes=[MidiNoteCandidate(**n) for n in (data.get("notes") or [])],
                        backend_used=str(data.get("backend_used", "basic-pitch")),
                        warning=data.get("warning"),
                    )
                else:
                    res = transcribe_stem_to_midi(
                        stem_path,
                        out_mid,
                        stem_name=stem_name,
                        allow_full_mix=False,
                        allow_cpu_pitch_fallback=True,
                    )
                self._put_latest(self._ui_midi_result_q, (res, f"✅ MIDI 转录完成: {out_mid}"))
            except Exception as exc:
                self._put_latest(self._ui_midi_result_q, (None, f"MIDI 转录失败: {exc}"))

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
                )
                self._put_latest(self._ui_banner_q, msg if not ok else f"✅ {msg}")
            finally:
                self._put_latest(self._ui_live_pending_q, False)

        threading.Thread(target=_run, name="ListenScope-LiveStart", daemon=True).start()

    def _on_live_stop(self) -> None:
        def _run() -> None:
            self.live_separator.stop()
            self._put_latest(self._ui_live_pending_q, False)

        threading.Thread(target=_run, name="ListenScope-LiveStop", daemon=True).start()

    def _on_settings_applied(self, limits: ResourceLimits, ai_cfg: AIConfig, ai_python: str) -> None:
        self.resource_limits = limits
        self.ai_config = ai_cfg
        self.resource_manager.limits = limits
        self.ai_job_manager.ai_config = ai_cfg
        self.ai_job_manager.ai_python_executable = ai_python or None
        self.live_separator.ai_config = ai_cfg
        self.live_separator.ai_python_executable = ai_python or None

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
                PersistedSettings(
                    resource_limits=limits,
                    ai_config=ai_cfg,
                    ai_python_executable=ai_python,
                ),
                self._settings_path,
            )
            self.window.show_banner_message(f"✅ 资源安全阈值与 AI 环境配置已保存至 {saved}")
        except Exception as exc:
            self.window.show_banner_message(f"⚠️ 配置已生效，但写入本地设置文件失败: {exc}")

    def _on_ui_tick(self) -> None:
        self._tick_counter += 1

        # Drain thread-safe UI notification queues
        while True:
            try:
                seq, probe_data = self._ui_hw_probe_q.get_nowait()
                if seq == self._probe_seq:
                    self.hardware_report = apply_external_ai_probe_to_report(self.hardware_report, probe_data)
                    self.window.update_hardware_report(self.hardware_report, auto_sync_gpu_chk=True)
                    if self.hardware_report.gpu_ai_ready:
                        self.window.show_banner_message(
                            f"✅ 独立 AI 环境已通过 RTX 5060 Ti / CUDA / ONNX 检测，GPU AI 推理已解锁。"
                        )
            except queue.Empty:
                break
        while True:
            try:
                self.window.update_ai_progress(self._ui_ai_progress_q.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                ai_res = self._ui_ai_result_q.get_nowait()
                if ai_res.state == AIJobState.COMPLETED:
                    self._latest_deep_report = None
                    self._latest_midi_result = None
                self.window.handle_ai_result(ai_res)
            except queue.Empty:
                break
        while True:
            try:
                self.window.show_banner_message(self._ui_banner_q.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                self.window.live_widget.set_benchmark_text(self._ui_live_bench_q.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                self.window.live_widget.set_pending_start(self._ui_live_pending_q.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                midi_res, midi_msg = self._ui_midi_result_q.get_nowait()
                if midi_res is not None:
                    self._latest_midi_result = midi_res
                    self.window.display_midi_result(midi_res)
                if midi_msg:
                    self.window.show_banner_message(midi_msg)
            except queue.Empty:
                break
        while True:
            try:
                deep_res, deep_msg = self._ui_deep_analysis_q.get_nowait()
                if deep_res is not None:
                    self._latest_deep_report = deep_res
                    self.window.display_deep_analysis(deep_res)
                if deep_msg:
                    self.window.show_banner_message(deep_msg)
            except queue.Empty:
                break

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

        # Update real-time CPU DSP analysis snapshots
        asnap = self.analysis_worker.latest_snapshot()
        if asnap is not None:
            spec_hist = self.analysis_worker.spectrum.recent_log_spectrogram() if self._tick_counter % 3 == 0 else None
            chroma_hist = (
                self.analysis_worker.chroma.recent_chroma_matrix(seconds=30.0)
                if self._tick_counter % 4 == 0
                else None
            )
            self.window.update_analysis_snapshot(asnap, spectrogram=spec_hist, chroma_history=chroma_hist)

        # Update capture stats, 120s history overview waveform & resource monitor on tick 1 and every ~4 ticks (~200ms)
        if self._tick_counter == 1 or self._tick_counter % 4 == 0:
            if self._capture_backend is not None:
                cstats = self._capture_backend.get_stats()
                self.resource_manager.update_runtime_state(
                    audio_queue_size=cstats.queue_size,
                    audio_queue_maxsize=cstats.queue_maxsize,
                )
                self.window.update_capture_stats(cstats, self.ring_buffer.available_seconds)
            else:
                self.window.history_coverage_lbl.setText(f"已缓冲: {self.ring_buffer.available_seconds:.1f} / 120.0 s")

            mins, maxs, avail_sec = self.ring_buffer.snapshot_envelope(300)
            self.window.update_history_overview(mins, maxs, avail_sec)
            self._sync_ab_bookmarks()

            rsnap = self.resource_manager.sample()
            self.window.update_resource_snapshot(
                rsnap,
                self.perf_logger.recent_records(),
                self.log_handler.recent(),
            )
            if self.live_separator.is_active or self.live_separator.is_starting or self._tick_counter % 12 == 0:
                self.window.update_live_metrics(self.live_separator.latest_metrics())

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        self._probe_seq += 1
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.stop_capture()
        self.metronome.stop_standalone()
        self.ab_player.stop()
        self.mixer_engine.clear()
        self.analysis_worker.stop()
        if self.live_separator.is_active or self.live_separator.is_starting:
            self.live_separator.stop()
        self.ai_job_manager.shutdown()
        self.resource_manager.close()
        logging.getLogger().removeHandler(self.log_handler)
        if hasattr(self, "window") and self.window is not None:
            self.window.set_closing_handler(None)
            self.window.deleteLater()


def main(argv: Optional[list[str]] = None) -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="ListenScope Desktop Application")
    parser.add_argument("--simulate", action="store_true", help="启动合成信号 + Mock 测试模式（用于无真机调试）")
    parser.add_argument("--ai-python", type=str, default=None, help="独立 AI Worker 虚拟环境 python.exe 路径")
    parser.add_argument("--settings", type=str, default=None, help="自定义持久化 settings.json 路径")
    parser.add_argument("--headless-smoke", action="store_true", help="短时运行后干净退出（测试用途）")
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=args.simulate,
        ai_python_executable=args.ai_python,
        settings_path=args.settings,
    )
    if args.simulate:
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})

    ctrl.window.show()
    if args.headless_smoke:
        QtCore.QTimer.singleShot(300, ctrl.window.close)
    ret = app.exec()
    ctrl.shutdown()
    del ctrl
    app.processEvents()
    gc.collect()
    app.processEvents()
    return int(ret)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
