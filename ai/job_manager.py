"""Single-job AI separation orchestrator with spawn/external-venv subprocess isolation and Emergency Stop."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import json
import logging
import multiprocessing
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional

from core.config import AIConfig, TargetHardwareSpec
from core.logging import PerformanceLogger
from core.models import (
    AIJobProgress,
    AIJobRequest,
    AIJobResult,
    AIJobState,
    OOMRecoveryAction,
    ResourceSnapshot,
)
from core.paths import get_bundle_root, subprocess_no_window_kwargs
from core.resource_manager import ResourceManager

from .models import MODEL_REGISTRY
from .resource_guard import cleanup_temp_outputs, inspect_wav_header
from .worker import spawn_worker_entry

logger = logging.getLogger(__name__)


def _parse_progress(payload: dict[str, Any]) -> AIJobProgress:
    return AIJobProgress(
        task_id=str(payload["task_id"]),
        state=AIJobState(str(payload["state"])),
        progress=float(payload.get("progress", 0.0)),
        message=str(payload.get("message", "")),
        current_chunk=int(payload.get("current_chunk", 0)),
        total_chunks=int(payload.get("total_chunks", 0)),
        worker_pid=payload.get("worker_pid"),
        peak_ram_mb=float(payload.get("peak_ram_mb", 0.0)),
        peak_vram_mb=payload.get("peak_vram_mb"),
    )


def _parse_result(payload: dict[str, Any]) -> AIJobResult:
    raw_opts = payload.get("recovery_options") or []
    recovery_opts = [OOMRecoveryAction(str(o)) for o in raw_opts]
    return AIJobResult(
        task_id=str(payload["task_id"]),
        state=AIJobState(str(payload["state"])),
        stem_paths=dict(payload.get("stem_paths") or {}),
        elapsed_sec=float(payload.get("elapsed_sec", 0.0)),
        input_duration_sec=float(payload.get("input_duration_sec", 0.0)),
        rtf=payload.get("rtf"),
        device_used=str(payload.get("device_used", "CPU")),
        model_id=str(payload.get("model_id", "")),
        architecture=str(payload.get("architecture", "")),
        oom_occurred=bool(payload.get("oom_occurred", False)),
        fallback_used=bool(payload.get("fallback_used", False)),
        recovery_options=recovery_opts,
        start_ram_mb=float(payload.get("start_ram_mb", 0.0)),
        peak_ram_mb=float(payload.get("peak_ram_mb", 0.0)),
        end_ram_mb=float(payload.get("end_ram_mb", 0.0)),
        start_vram_mb=payload.get("start_vram_mb"),
        peak_vram_mb=payload.get("peak_vram_mb"),
        end_vram_mb=payload.get("end_vram_mb"),
        error=payload.get("error"),
    )


class AIJobManager:
    """Enforces single-job, single-model AI isolation and instant Emergency Stop recovery."""

    def __init__(
        self,
        resource_manager: ResourceManager,
        *,
        ai_config: Optional[AIConfig] = None,
        performance_logger: Optional[PerformanceLogger] = None,
        ai_python_executable: Optional[str | Path] = None,
        gpu_readiness_provider: Optional[Callable[[], tuple[bool, Optional[str]]]] = None,
    ) -> None:
        self.resource_manager = resource_manager
        self.ai_config = ai_config or AIConfig()
        self.performance_logger = performance_logger or PerformanceLogger()
        self.ai_python_executable = str(ai_python_executable) if ai_python_executable else None
        self._gpu_readiness_provider = gpu_readiness_provider

        self._lock = threading.RLock()
        self._accepting_jobs = True
        self._emergency_stopping = False

        self._active_request: Optional[AIJobRequest] = None
        self._latest_progress = AIJobProgress(task_id="", state=AIJobState.IDLE, progress=0.0, message="空闲")
        self._last_result: Optional[AIJobResult] = None
        self._worker_pid: Optional[int] = None

        # Spawn multiprocessing handles
        self._spawn_proc: Optional[multiprocessing.Process] = None
        self._msg_queue: Any = None
        self._cancel_event: Any = None

        # External AI venv Popen handles
        self._subproc: Optional[subprocess.Popen[str]] = None
        self._subproc_tmp: Optional[tempfile.TemporaryDirectory[str]] = None
        self._cancel_flag_path: Optional[Path] = None
        self._subproc_reader_thread: Optional[threading.Thread] = None
        self._subproc_stderr_thread: Optional[threading.Thread] = None
        self._subproc_stderr_tail: deque[str] = deque(maxlen=30)

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._done_event = threading.Event()
        self._done_event.set()
        self._result_dispatched = True

        self._progress_callbacks: list[Callable[[AIJobProgress], None]] = []
        self._completion_callbacks: list[Callable[[AIJobResult], None]] = []

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return not self._done_event.is_set()

    @property
    def worker_pid(self) -> Optional[int]:
        with self._lock:
            return self._worker_pid

    def latest_progress(self) -> AIJobProgress:
        with self._lock:
            return self._latest_progress

    def last_result(self) -> Optional[AIJobResult]:
        with self._lock:
            return self._last_result

    def add_progress_callback(self, cb: Callable[[AIJobProgress], None]) -> None:
        with self._lock:
            self._progress_callbacks.append(cb)

    def add_completion_callback(self, cb: Callable[[AIJobResult], None]) -> None:
        with self._lock:
            self._completion_callbacks.append(cb)

    def _dispatch_progress(self, prog: AIJobProgress) -> None:
        with self._lock:
            self._latest_progress = prog
            cbs = list(self._progress_callbacks)
        for cb in cbs:
            try:
                cb(prog)
            except Exception:
                logger.exception("Progress callback failed")

    def _dispatch_result(self, req: AIJobRequest, res: AIJobResult) -> None:
        with self._lock:
            if self._result_dispatched:
                return
            self._result_dispatched = True
            self._last_result = res
            self._latest_progress = AIJobProgress(
                task_id=res.task_id,
                state=res.state,
                progress=1.0 if res.state == AIJobState.COMPLETED else 0.0,
                message=res.error or f"状态: {res.state.value}",
                worker_pid=None,
                peak_ram_mb=res.peak_ram_mb,
                peak_vram_mb=res.peak_vram_mb,
            )
            cbs = list(self._completion_callbacks)
            self._active_request = None
            self._worker_pid = None

        try:
            self.performance_logger.log_job(req, res)
        except Exception:
            logger.exception("Failed to write PerformanceRecord")

        self.resource_manager.update_runtime_state(
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            ai_worker_pid=None,
            ai_buffer_seconds=0.0,
        )
        self.resource_manager.sample()

        # Wake wait_for_completion() and allow new submit_job() ONLY after log + ResourceManager reset
        self._done_event.set()

        for cb in cbs:
            try:
                cb(res)
            except Exception:
                logger.exception("Completion callback failed")

    def submit_job(
        self,
        request: AIJobRequest,
        *,
        gpu_ai_ready: Optional[bool] = None,
        gpu_block_reason: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Validate resource gates and launch one isolated AI worker subprocess."""
        with self._lock:
            if not self._accepting_jobs or self._emergency_stopping:
                return False, "紧急停止执行中，当前禁止启动新的 AI 分轨任务。"
            if not self._done_event.is_set():
                return False, "已有 AI 分轨任务运行中（硬限制=1），禁止并行。"

            spec = MODEL_REGISTRY.get(request.model_id)
            if spec is None:
                return False, f"未知模型 ID: {request.model_id}"
            if spec.experimental_only and not self.ai_config.allow_experimental_roformer and not request.use_mock_backend:
                return False, f"模型 {spec.display_name} 为高显存实验性模型，默认禁用；请在设置中通过风险确认后启用。"

            ready = gpu_ai_ready
            block_reason = gpu_block_reason
            if ready is None and self._gpu_readiness_provider is not None and request.use_gpu and not request.use_mock_backend:
                ready, block_reason = self._gpu_readiness_provider()

            if getattr(sys, "frozen", False) and not self._uses_external_python() and not request.use_mock_backend:
                return (
                    False,
                    "独立 AI 环境 (.venv-ai) 未配置：Windows 打包版不含 PyTorch/CUDA，请在「设置 -> 资源安全阈值 & AI 配置」中指定 .venv-ai\\Scripts\\python.exe。",
                )

            allowed, reason = self.resource_manager.can_start_ai_job(
                stem_mode=request.stem_mode,
                require_gpu=(request.use_gpu and not request.use_mock_backend),
                gpu_ai_ready=ready,
                gpu_block_reason=block_reason,
            )
            if not allowed:
                return False, reason

            meta = inspect_wav_header(request.input_wav_path, ai_config=self.ai_config)

            self._active_request = request
            self._result_dispatched = False
            self._done_event.clear()
            self._stop_monitor.clear()
            self._last_result = None

            self._launch_worker_locked(request)
            self.resource_manager.update_runtime_state(
                active_ai_jobs=1,
                loaded_models=1,
                current_model=request.model_id,
                current_task=request.task_id,
                ai_worker_pid=self._worker_pid,
                ai_buffer_seconds=min(meta.duration_sec, request.chunk_seconds),
            )
            init_prog = AIJobProgress(
                task_id=request.task_id,
                state=AIJobState.PREPARING,
                progress=0.01,
                message=meta.resource_estimate_note,
                worker_pid=self._worker_pid,
            )
            self._latest_progress = init_prog
            init_cbs = list(self._progress_callbacks)
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(request,),
                name=f"ListenScope-AIMonitor-{request.task_id}",
                daemon=True,
            )
            self._monitor_thread.start()

        for cb in init_cbs:
            try:
                cb(init_prog)
            except Exception:
                logger.exception("Progress callback failed")
        return True, meta.resource_estimate_note

    def _uses_external_python(self) -> bool:
        if not self.ai_python_executable:
            return False
        try:
            return Path(self.ai_python_executable).resolve() != Path(sys.executable).resolve()
        except Exception:
            return str(self.ai_python_executable).strip() != str(sys.executable).strip()

    def _launch_worker_locked(self, request: AIJobRequest) -> None:
        req_dict = asdict(request)
        cfg_dict = asdict(self.ai_config)

        use_external = self._uses_external_python()
        if use_external and self.ai_python_executable is not None:
            import os

            bundle_root = get_bundle_root()
            tmp_dir = tempfile.TemporaryDirectory(prefix="ls_ai_ipc_")
            tmp_path = Path(tmp_dir.name)
            req_path = tmp_path / "request.json"
            cfg_path = tmp_path / "config.json"
            cancel_path = tmp_path / "cancel.flag"
            req_path.write_text(json.dumps(req_dict, ensure_ascii=False), encoding="utf-8")
            cfg_path.write_text(json.dumps(cfg_dict, ensure_ascii=False), encoding="utf-8")

            env = os.environ.copy()
            existing_pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)

            msg_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
            self._subproc_stderr_tail.clear()
            proc = subprocess.Popen(
                [
                    self.ai_python_executable,
                    "-m",
                    "ai.worker",
                    "--request-json",
                    str(req_path),
                    "--config-json",
                    str(cfg_path),
                    "--cancel-flag",
                    str(cancel_path),
                ],
                cwd=str(bundle_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **subprocess_no_window_kwargs(),
            )
            self._subproc = proc
            self._subproc_tmp = tmp_dir
            self._cancel_flag_path = cancel_path
            self._msg_queue = msg_q
            self._worker_pid = proc.pid

            def _read_stdout() -> None:
                pipe = proc.stdout
                if pipe is None:
                    return
                try:
                    for line in pipe:
                        text = line.strip()
                        if not text:
                            continue
                        try:
                            item = json.loads(text)
                        except Exception:
                            brace = text.find("{")
                            if brace <= 0:
                                continue
                            try:
                                item = json.loads(text[brace:])
                            except Exception:
                                continue
                        try:
                            msg_q.put_nowait(item)
                        except queue.Full:
                            if isinstance(item, dict) and item.get("type") == "result":
                                try:
                                    msg_q.get_nowait()
                                except queue.Empty:
                                    pass
                                try:
                                    msg_q.put_nowait(item)
                                except queue.Full:
                                    pass
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            def _read_stderr() -> None:
                pipe = proc.stderr
                if pipe is None:
                    return
                try:
                    for line in pipe:
                        text = line.strip()
                        if text:
                            self._subproc_stderr_tail.append(text[-400:])
                except Exception:
                    pass
                finally:
                    try:
                        pipe.close()
                    except Exception:
                        pass

            self._subproc_reader_thread = threading.Thread(
                target=_read_stdout,
                name="ListenScope-AIStdoutReader",
                daemon=True,
            )
            self._subproc_stderr_thread = threading.Thread(
                target=_read_stderr,
                name="ListenScope-AIStderrDrain",
                daemon=True,
            )
            self._subproc_reader_thread.start()
            self._subproc_stderr_thread.start()
            return

        ctx = multiprocessing.get_context("spawn")
        mp_q = ctx.Queue(maxsize=256)
        cancel_ev = ctx.Event()
        mp_proc = ctx.Process(
            target=spawn_worker_entry,
            args=(req_dict, cfg_dict, mp_q, cancel_ev),
            name=f"ListenScope-AIWorker-{request.task_id}",
            daemon=True,
        )
        mp_proc.start()
        self._spawn_proc = mp_proc
        self._msg_queue = mp_q
        self._cancel_event = cancel_ev
        self._worker_pid = mp_proc.pid

    def _is_worker_alive(self) -> bool:
        if self._spawn_proc is not None:
            return self._spawn_proc.is_alive()
        if self._subproc is not None:
            return self._subproc.poll() is None
        return False

    def _worker_exitcode(self) -> Optional[int]:
        if self._spawn_proc is not None:
            return self._spawn_proc.exitcode
        if self._subproc is not None:
            return self._subproc.poll()
        return None

    def _signal_worker_cancel(self) -> None:
        if self._cancel_event is not None:
            try:
                self._cancel_event.set()
            except Exception:
                pass
        if self._cancel_flag_path is not None:
            try:
                self._cancel_flag_path.write_text("cancel", encoding="utf-8")
            except Exception:
                pass

    def _terminate_and_cleanup_ipc(self, grace_timeout: float) -> None:
        self._signal_worker_cancel()
        deadline = time.monotonic() + max(0.05, grace_timeout)
        while self._is_worker_alive() and time.monotonic() < deadline:
            time.sleep(0.04)

        if self._spawn_proc is not None:
            proc = self._spawn_proc
            if proc.is_alive():
                try:
                    proc.terminate()
                except Exception:
                    pass
                proc.join(timeout=0.6)
            if proc.is_alive():
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(timeout=0.5)
            else:
                proc.join(timeout=0.2)
            self._spawn_proc = None

        if self._subproc is not None:
            sub = self._subproc
            if sub.poll() is None:
                try:
                    sub.terminate()
                    sub.wait(timeout=0.6)
                except Exception:
                    try:
                        sub.kill()
                        sub.wait(timeout=0.5)
                    except Exception:
                        pass
            for pipe in (sub.stdout, sub.stderr):
                if pipe is not None:
                    try:
                        pipe.close()
                    except Exception:
                        pass
            self._subproc = None

        if self._subproc_reader_thread is not None and self._subproc_reader_thread.is_alive():
            self._subproc_reader_thread.join(timeout=0.4)
        self._subproc_reader_thread = None
        if self._subproc_stderr_thread is not None and self._subproc_stderr_thread.is_alive():
            self._subproc_stderr_thread.join(timeout=0.4)
        self._subproc_stderr_thread = None

        if self._msg_queue is not None:
            try:
                while True:
                    self._msg_queue.get_nowait()
            except Exception:
                pass
            close_fn = getattr(self._msg_queue, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
        self._msg_queue = None
        self._cancel_event = None
        self._cancel_flag_path = None

        if self._subproc_tmp is not None:
            try:
                self._subproc_tmp.cleanup()
            except Exception:
                pass
            self._subproc_tmp = None

    def _cleanup_task_staging(self, req: AIJobRequest) -> None:
        cleanup_temp_outputs(Path(req.output_dir) / f".tmp_{req.task_id}")

    def _monitor_loop(self, req: AIJobRequest) -> None:
        final_result: Optional[AIJobResult] = None
        try:
            while not self._stop_monitor.is_set():
                # Drain pending IPC messages
                if self._msg_queue is not None:
                    for _ in range(32):
                        try:
                            msg = self._msg_queue.get_nowait()
                        except queue.Empty:
                            break
                        except Exception:
                            break
                        mtype = msg.get("type")
                        payload = msg.get("payload") or {}
                        if mtype == "progress":
                            self._dispatch_progress(_parse_progress(payload))
                        elif mtype == "result":
                            final_result = _parse_result(payload)

                if final_result is not None:
                    break

                # Guard against mid-job host RAM/VRAM exhaustion
                should_stop, stop_reason = self.resource_manager.should_emergency_stop_ai()
                if should_stop:
                    logger.error("Automatic AI emergency stop triggered: %s", stop_reason)
                    # Trigger on separate thread or handle inline cleanly:
                    self._perform_emergency_stop_inline(req, stop_reason)
                    return

                if not self._is_worker_alive():
                    # Wait briefly for stdout/stderr reader threads to drain EOF before inspecting queue/tail
                    if self._subproc_reader_thread is not None and self._subproc_reader_thread.is_alive():
                        self._subproc_reader_thread.join(timeout=0.4)
                    if self._subproc_stderr_thread is not None and self._subproc_stderr_thread.is_alive():
                        self._subproc_stderr_thread.join(timeout=0.4)
                    time.sleep(0.03)
                    if self._msg_queue is not None:
                        while True:
                            try:
                                msg = self._msg_queue.get_nowait()
                                if msg.get("type") == "progress":
                                    self._dispatch_progress(_parse_progress(msg["payload"]))
                                elif msg.get("type") == "result":
                                    final_result = _parse_result(msg["payload"])
                            except Exception:
                                break
                    if final_result is None:
                        code = self._worker_exitcode()
                        self._cleanup_task_staging(req)
                        err_tail = list(self._subproc_stderr_tail)[-5:]
                        detail = f" ({' | '.join(err_tail)})" if err_tail else ""
                        final_result = AIJobResult(
                            task_id=req.task_id,
                            state=AIJobState.FAILED,
                            model_id=req.model_id,
                            device_used="MockCPU" if req.use_mock_backend else ("GPU-CUDA" if req.use_gpu else "CPU"),
                            error=f"AI worker 子进程异常终止 (exitcode={code}){detail}，主程序捕获与频谱保持正常。",
                        )
                    break

                self._stop_monitor.wait(timeout=0.05)
        finally:
            if not self._stop_monitor.is_set() and final_result is not None:
                self._terminate_and_cleanup_ipc(grace_timeout=0.1)
                self._dispatch_result(req, final_result)

    def _perform_emergency_stop_inline(self, req: AIJobRequest, reason: str) -> ResourceSnapshot:
        with self._lock:
            self._accepting_jobs = False
            self._emergency_stopping = True
            self._stop_monitor.set()
        try:
            self._terminate_and_cleanup_ipc(grace_timeout=min(0.6, self.ai_config.worker_graceful_cancel_timeout_sec))
            self._cleanup_task_staging(req)
            snap = self.resource_manager.sample()
            res = AIJobResult(
                task_id=req.task_id,
                state=AIJobState.EMERGENCY_STOPPED,
                model_id=req.model_id,
                device_used="MockCPU" if req.use_mock_backend else ("GPU-CUDA" if req.use_gpu else "CPU"),
                error=reason,
            )
            self._dispatch_result(req, res)
            return snap
        finally:
            with self._lock:
                self._emergency_stopping = False
                self._accepting_jobs = True

    def cancel_job(self, timeout: Optional[float] = None) -> Optional[AIJobResult]:
        """Gracefully cancel the active AI separation job, escalating to terminate if needed."""
        with self._lock:
            req = self._active_request
            if req is None or self._done_event.is_set():
                return self._last_result
            self._signal_worker_cancel()

        wait_sec = timeout if timeout is not None else self.ai_config.worker_graceful_cancel_timeout_sec + 1.0
        self._done_event.wait(timeout=wait_sec)
        if not self._done_event.is_set():
            with self._lock:
                self._stop_monitor.set()
            self._terminate_and_cleanup_ipc(grace_timeout=0.3)
            self._cleanup_task_staging(req)
            res = AIJobResult(
                task_id=req.task_id,
                state=AIJobState.CANCELLED,
                model_id=req.model_id,
                error="AI 分轨任务已取消并清理临时文件",
            )
            self._dispatch_result(req, res)
            return res
        return self._last_result

    def emergency_stop(self, reason: str = "用户触发紧急停止 AI") -> ResourceSnapshot:
        """Section 5 Emergency Stop:
        1. Block new jobs
        2. Signal worker graceful cancel
        3. Wait short grace period
        4. Force terminate/kill if still running
        5. Clean IPC & remove incomplete temp files
        6. Re-read RAM and VRAM
        7. Restore main program ready state without interrupting capture/DSP/GUI
        """
        with self._lock:
            self._accepting_jobs = False
            self._emergency_stopping = True
            req = self._active_request
            self._stop_monitor.set()
            mon = self._monitor_thread

        if req is not None:
            self._terminate_and_cleanup_ipc(grace_timeout=min(0.6, self.ai_config.worker_graceful_cancel_timeout_sec))
            if mon is not None and mon.is_alive() and mon is not threading.current_thread():
                mon.join(timeout=1.0)
            self._cleanup_task_staging(req)
            res = AIJobResult(
                task_id=req.task_id,
                state=AIJobState.EMERGENCY_STOPPED,
                model_id=req.model_id,
                device_used="MockCPU" if req.use_mock_backend else ("GPU-CUDA" if req.use_gpu else "CPU"),
                error=reason,
            )
            self._dispatch_result(req, res)
        else:
            self.resource_manager.update_runtime_state(
                active_ai_jobs=0,
                loaded_models=0,
                current_model=None,
                current_task=None,
                ai_worker_pid=None,
                ai_buffer_seconds=0.0,
            )

        snap = self.resource_manager.sample()
        with self._lock:
            self._emergency_stopping = False
            self._accepting_jobs = True
        return snap

    def wait_for_completion(self, timeout: Optional[float] = None) -> Optional[AIJobResult]:
        self._done_event.wait(timeout=timeout)
        with self._lock:
            return self._last_result

    def shutdown(self) -> None:
        if self.is_busy:
            self.emergency_stop("ListenScope 关闭，清理 AI Worker")
