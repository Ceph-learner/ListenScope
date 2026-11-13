"""ListenScope application entry point & non-blocking controller wiring capture, ring buffer, CPU DSP, A/B playback, AI worker, and UI."""

from __future__ import annotations

import argparse
import gc
import logging
from pathlib import Path
import queue
import sys
import threading
import time
from typing import Any, Optional
import uuid

from PySide6 import QtCore, QtWidgets

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.job_manager import AIJobManager
from analysis.midi_transcription import transcribe_stem_to_midi
from analysis.worker import AnalysisWorker
from audio.capture_base import AudioCaptureBackend
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
from core.logging import BoundedMemoryLogHandler, PerformanceLogger
from core.models import AIJobProgress, AIJobRequest, AIJobResult, OOMRecoveryAction
from core.resource_manager import ResourceManager
from core.system_probe import probe_system
from streaming.live_separator import ExperimentalLiveSeparator
from ui.main_window import ListenScopeMainWindow


class ListenScopeController:
    """Owns background threads/subprocesses and bridges immutable snapshots to the Qt UI thread."""

    def __init__(
        self,
        *,
        use_mock_ai_for_demo: bool = False,
        ai_python_executable: Optional[str] = None,
        work_dir: Path | str = Path("workspace_outputs"),
    ) -> None:
        self.work_dir = Path(work_dir)
        self.use_mock_ai_for_demo = use_mock_ai_for_demo
        if ai_python_executable is None:
            win_ai_py = ROOT / ".venv-ai" / "Scripts" / "python.exe"
            if win_ai_py.exists():
                ai_python_executable = str(win_ai_py)

        # Bounded diagnostic logging
        self.log_handler = BoundedMemoryLogHandler(maxlen=500)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.audio_config = AudioConfig()
        self.analysis_config = AnalysisConfig()
        self.resource_limits = ResourceLimits()
        self.ai_config = AIConfig()
        self.hardware_report = probe_system()

        self.resource_manager = ResourceManager(limits=self.resource_limits)
        self.ring_buffer = FixedRingBuffer(audio_config=self.audio_config)
        self.analysis_worker = AnalysisWorker(
            self.ring_buffer,
            audio_config=self.audio_config,
            analysis_config=self.analysis_config,
        )
        self.ab_player = HistoryABPlayer(self.ring_buffer, audio_config=self.audio_config)
        self.mixer_engine = StemMixerEngine(sample_rate=self.audio_config.sample_rate, channels=self.audio_config.channels)
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
        )

        self._capture_backend: Optional[AudioCaptureBackend] = None
        self._drain_stop = threading.Event()
        self._drain_thread: Optional[threading.Thread] = None

        self._ui_ai_progress_q: queue.Queue[AIJobProgress] = queue.Queue(maxsize=64)
        self._ui_ai_result_q: queue.Queue[AIJobResult] = queue.Queue(maxsize=16)
        self._ui_banner_q: queue.Queue[str] = queue.Queue(maxsize=16)
        self._ui_live_bench_q: queue.Queue[str] = queue.Queue(maxsize=8)
        self._last_ai_request: Optional[AIJobRequest] = None

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

    def _enqueue_progress(self, prog: AIJobProgress) -> None:
        try:
            self._ui_ai_progress_q.put_nowait(prog)
        except queue.Full:
            pass

    def _enqueue_result(self, res: AIJobResult) -> None:
        try:
            self._ui_ai_result_q.put_nowait(res)
        except queue.Full:
            pass

    def _connect_signals(self) -> None:
        w = self.window
        w.refresh_sources_requested.connect(self.refresh_sources)
        w.capture_toggle_requested.connect(self._on_capture_toggle)
        w.ab_select_recent_requested.connect(self._on_ab_select_recent)
        w.ab_set_range_sec_requested.connect(self._on_ab_set_range)
        w.ab_play_requested.connect(self._on_ab_play)
        w.ab_stop_requested.connect(self.ab_player.stop)
        w.ai_separate_requested.connect(self._on_start_ai_separation)
        w.emergency_stop_requested.connect(self._on_emergency_stop)
        w.mixer_widget.cancel_ai_requested.connect(self._on_cancel_ai)
        w.mixer_widget.oom_action_requested.connect(self._on_oom_action)
        w.mixer_widget.export_mix_requested.connect(self._on_export_mix)
        w.mixer_widget.send_stem_to_analysis.connect(self._on_send_stem_to_analysis)
        w.mixer_widget.transcribe_stem_midi.connect(self._on_transcribe_stem_midi)
        w.live_widget.benchmark_requested.connect(self._on_live_benchmark)
        w.live_widget.start_requested.connect(self._on_live_start)
        w.live_widget.stop_requested.connect(self._on_live_stop)
        w.live_widget.balance_changed.connect(self.live_separator.set_gains)
        w.settings_applied.connect(self._on_settings_applied)

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
        a = max(oldest, newest - int(round(max(start_ago_sec, end_ago_sec + 0.5) * sr)))
        b = max(a + 1, newest - int(round(min(start_ago_sec, end_ago_sec) * sr)))
        self.ab_player.set_ab_range(a, b)
        self.window.show_banner_message(f"已设定 A/B 区间（倒退 {start_ago_sec:.1f}s ~ {end_ago_sec:.1f}s）。")

    def _on_ab_play(self) -> None:
        if self.ab_player.loop_range[1] <= self.ab_player.loop_range[0]:
            self.ab_player.select_recent_seconds(min(30.0, max(1.0, self.ring_buffer.available_seconds)))
        try:
            hint = self.ab_player.start_playback(open_audio_device=True)
            self.window.show_banner_message(hint)
        except Exception as exc:
            self.window.show_banner_message(f"A/B 回放失败: {exc}")

    def _on_start_ai_separation(self, stem_mode: str, model_id: str, segment: int, use_gpu: bool) -> None:
        if self.live_separator.is_active:
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
            self.window.show_banner_message(f"拒绝启动 AI 分轨: {msg}")
        else:
            self._last_ai_request = req
            self.window.tabs.setCurrentWidget(self.window.mixer_widget)
            self.window.show_banner_message(msg)

    def _on_cancel_ai(self) -> None:
        threading.Thread(target=self.ai_job_manager.cancel_job, name="ListenScope-AICancel", daemon=True).start()

    def _on_emergency_stop(self) -> None:
        def _run() -> None:
            if self.live_separator.is_active:
                self.live_separator.stop(status_message="用户触发紧急停止 AI")
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

    def _on_send_stem_to_analysis(self, stem_name: str, stem_path: str) -> None:
        """Load selected stem WAV excerpt cleanly into ring buffer for CPU spectrum/chroma/chord analysis."""
        try:
            import wave
            import numpy as np

            self.stop_capture()
            self.ring_buffer.clear()
            with wave.open(stem_path, "rb") as wf:
                sr = int(wf.getframerate())
                ch = int(wf.getnchannels())
                raw = wf.readframes(min(int(wf.getnframes()), sr * 30))
            flat = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            arr = flat[: (flat.size // ch) * ch].reshape(-1, ch)
            if ch == 1:
                arr = np.repeat(arr, 2, axis=1)
            self.ring_buffer.write(arr)
            self.window.tabs.setCurrentWidget(self.window.chroma_widget)
            self.window.show_banner_message(f"已将单轨 `{stem_name}` 载入实时和弦/音高分析视图（仅截取前 <=30s）。")
        except Exception as exc:
            self.window.show_banner_message(f"送入分析失败: {exc}")

    def _on_transcribe_stem_midi(self, stem_name: str, stem_path: str) -> None:
        out_mid = Path(stem_path).with_suffix(".mid")
        try:
            res = transcribe_stem_to_midi(
                stem_path,
                out_mid,
                stem_name=stem_name,
                allow_full_mix=False,
                allow_cpu_pitch_fallback=True,
            )
            self.window.display_midi_result(res)
        except Exception as exc:
            self.window.show_banner_message(f"MIDI 转录失败: {exc}")

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
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

        threading.Thread(target=_run, name="ListenScope-LiveBench", daemon=True).start()

    def _on_live_start(self, model_id: str) -> None:
        def _run() -> None:
            ok, msg = self.live_separator.start(
                model_id=model_id,
                use_gpu=not self.use_mock_ai_for_demo,
                use_mock_backend=self.use_mock_ai_for_demo,
                gpu_ai_ready=self.hardware_report.gpu_ai_ready,
                gpu_block_reason=self.hardware_report.gpu_ai_block_reason,
            )
            try:
                self._ui_banner_q.put_nowait(msg if not ok else f"✅ {msg}")
            except queue.Full:
                pass

        threading.Thread(target=_run, name="ListenScope-LiveStart", daemon=True).start()

    def _on_live_stop(self) -> None:
        threading.Thread(target=self.live_separator.stop, name="ListenScope-LiveStop", daemon=True).start()

    def _on_settings_applied(self, limits: ResourceLimits, ai_cfg: AIConfig, ai_python: str) -> None:
        self.resource_limits = limits
        self.ai_config = ai_cfg
        self.resource_manager.limits = limits
        self.ai_job_manager.ai_config = ai_cfg
        self.ai_job_manager.ai_python_executable = ai_python or None
        self.live_separator.ai_config = ai_cfg

    def _on_ui_tick(self) -> None:
        self._tick_counter += 1

        # Drain thread-safe UI notification queues
        while True:
            try:
                self.window.update_ai_progress(self._ui_ai_progress_q.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                self.window.handle_ai_result(self._ui_ai_result_q.get_nowait())
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

        # Update capture stats & resource monitor every ~4 ticks (~180-250ms)
        if self._tick_counter % 4 == 0:
            if self._capture_backend is not None:
                cstats = self._capture_backend.get_stats()
                self.resource_manager.update_runtime_state(
                    audio_queue_size=cstats.queue_size,
                    audio_queue_maxsize=cstats.queue_maxsize,
                )
                self.window.update_capture_stats(cstats, self.ring_buffer.available_seconds)
            else:
                self.window.history_coverage_lbl.setText(f"已缓冲: {self.ring_buffer.available_seconds:.1f} / 120.0 s")

            rsnap = self.resource_manager.sample()
            self.window.update_resource_snapshot(
                rsnap,
                self.perf_logger.recent_records(),
                self.log_handler.recent(),
            )
            if self.live_separator.is_active or self._tick_counter % 12 == 0:
                self.window.update_live_metrics(self.live_separator.latest_metrics())

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.stop_capture()
        self.ab_player.stop()
        self.mixer_engine.clear()
        self.analysis_worker.stop()
        if self.live_separator.is_active:
            self.live_separator.stop()
        self.ai_job_manager.shutdown()
        self.resource_manager.close()
        logging.getLogger().removeHandler(self.log_handler)
        if hasattr(self, "window") and self.window is not None:
            self.window.set_closing_handler(None)
            self.window.deleteLater()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ListenScope Desktop Application")
    parser.add_argument("--simulate", action="store_true", help="启动合成信号 + Mock 测试模式（用于无真机调试）")
    parser.add_argument("--ai-python", type=str, default=None, help="独立 AI Worker 虚拟环境 python.exe 路径")
    parser.add_argument("--headless-smoke", action="store_true", help="短时运行后干净退出（测试用途）")
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=args.simulate,
        ai_python_executable=args.ai_python,
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
    raise SystemExit(main())
