"""Phase 8 Experimental near-real-time 2-stem separator (disabled by default).

Strict safeguards:
- Default OFF; must be explicitly started by the user.
- 2-stem only (vocals + instrumental), default low-VRAM MDX model.
- Inference runs inside a dedicated isolated subprocess (`spawn` OR external `.venv-ai`).
- Strictly bounded input lag and bounded output ring buffer (`live_max_buffer_seconds`).
- Automatically stops if ResourceManager enters Warning or Critical state, or if
  RTF exceeds real-time safety cleanly, leaving CPU capture & spectrum untouched.
"""

from __future__ import annotations

import argparse
import base64
from collections import deque
from dataclasses import asdict
import json
import logging
import multiprocessing
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.backend import build_separation_backend
from ai.models import MODEL_REGISTRY
from ai.resource_guard import release_torch_and_memory
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, TargetHardwareSpec
from core.models import LiveSeparationMetrics, ResourceStatus
from core.paths import get_bundle_root, prepend_ffmpeg_path_env, subprocess_no_window_kwargs
from core.resource_manager import ResourceManager
from core.system_probe import (
    _probe_gpus_nvml,
    _probe_gpus_nvidia_smi,
    _probe_onnxruntime,
    _probe_pytorch,
    evaluate_gpu_ai_readiness,
)

from .benchmark import LiveBenchmarkResult, benchmark_live_model, benchmark_live_model_isolated
from .overlap_add import OverlapAddAccumulator

logger = logging.getLogger(__name__)


def _live_worker_entry(
    ai_cfg_dict: dict[str, Any],
    model_id: str,
    sample_rate: int,
    use_gpu: bool,
    use_mock_backend: bool,
    simulate_delay_sec: float,
    req_q: Any,
    res_q: Any,
    stop_ev: Any,
) -> None:
    """Subprocess running single 2-stem model continuously while live mode is enabled."""
    cfg = AIConfig(**ai_cfg_dict)
    backend = None
    try:
        if use_gpu and not use_mock_backend:
            gpus, _, _ = _probe_gpus_nvml()
            if not gpus:
                gpus, _, _ = _probe_gpus_nvidia_smi()
            ready, reason = evaluate_gpu_ai_readiness(
                gpus,
                _probe_pytorch(),
                _probe_onnxruntime(),
                target=TargetHardwareSpec(),
            )
            if not ready:
                res_q.put({"type": "error", "error": reason or "GPU AI 环境未就绪"})
                return

        backend = build_separation_backend(
            model_id,
            use_gpu=use_gpu,
            overlap=cfg.mdx_overlap,
            ai_config=cfg,
            use_mock_backend=use_mock_backend,
            simulate_delay_sec=simulate_delay_sec,
        )
        backend.load_model()
        res_q.put({"type": "ready"})

        while not stop_ev.is_set():
            try:
                item = req_q.get(timeout=0.08)
            except queue.Empty:
                continue
            if item is None:
                break
            seq, chunk_bytes, shape = item
            chunk = np.frombuffer(chunk_bytes, dtype=np.float32).reshape(shape)
            t0 = time.monotonic()
            stems = backend.separate_chunk(chunk, sample_rate)
            infer_sec = time.monotonic() - t0
            voc = np.asarray(stems["vocals"], dtype=np.float32)
            inst = np.asarray(stems["instrumental"], dtype=np.float32)
            try:
                res_q.put_nowait(
                    {
                        "type": "chunk",
                        "seq": seq,
                        "vocals": voc.tobytes(),
                        "instrumental": inst.tobytes(),
                        "shape": voc.shape,
                        "infer_sec": infer_sec,
                    }
                )
            except queue.Full:
                pass
    except Exception as exc:
        try:
            res_q.put({"type": "error", "error": f"实时分轨 worker 异常: {exc}"})
        except Exception:
            pass
    finally:
        if backend is not None:
            try:
                backend.unload_model()
            except Exception:
                pass
            del backend
        release_torch_and_memory()


def _external_worker_cli(config_json: Path) -> int:
    """External `.venv-ai` live 2-stem worker communicating via JSON + base64 over stdin/stdout."""
    ipc_out = sys.stdout
    sys.stdout = sys.stderr

    def _send(obj: dict[str, Any]) -> None:
        print(json.dumps(obj), file=ipc_out, flush=True)

    backend = None
    try:
        cfg_payload = json.loads(config_json.read_text(encoding="utf-8"))
        ai_cfg = AIConfig(**(cfg_payload.get("ai_config") or {}))
        model_id = str(cfg_payload["model_id"])
        sample_rate = int(cfg_payload["sample_rate"])
        use_gpu = bool(cfg_payload.get("use_gpu", True))
        use_mock_backend = bool(cfg_payload.get("use_mock_backend", False))
        simulate_delay_sec = float(cfg_payload.get("simulate_delay_sec", 0.0))

        if use_gpu and not use_mock_backend:
            gpus, _, _ = _probe_gpus_nvml()
            if not gpus:
                gpus, _, _ = _probe_gpus_nvidia_smi()
            ready, reason = evaluate_gpu_ai_readiness(
                gpus,
                _probe_pytorch(),
                _probe_onnxruntime(),
                target=TargetHardwareSpec(),
            )
            if not ready:
                _send({"type": "error", "error": reason or "GPU AI 环境未就绪"})
                return 1

        backend = build_separation_backend(
            model_id,
            use_gpu=use_gpu,
            overlap=ai_cfg.mdx_overlap,
            ai_config=ai_cfg,
            use_mock_backend=use_mock_backend,
            simulate_delay_sec=simulate_delay_sec,
        )
        backend.load_model()
        _send({"type": "ready"})

        for line in sys.stdin:
            text = line.strip()
            if not text:
                continue
            try:
                req = json.loads(text)
            except Exception:
                continue
            mtype = req.get("type")
            if mtype == "stop":
                break
            if mtype != "chunk":
                continue

            seq = int(req["seq"])
            shape = tuple(int(x) for x in req["shape"])
            raw = base64.b64decode(req["pcm_b64"])
            chunk = np.frombuffer(raw, dtype=np.float32).reshape(shape)
            t0 = time.monotonic()
            stems = backend.separate_chunk(chunk, sample_rate)
            infer_sec = time.monotonic() - t0
            voc = np.asarray(stems["vocals"], dtype=np.float32)
            inst = np.asarray(stems["instrumental"], dtype=np.float32)
            _send(
                {
                    "type": "chunk",
                    "seq": seq,
                    "shape": list(voc.shape),
                    "infer_sec": infer_sec,
                    "vocals_b64": base64.b64encode(voc.tobytes()).decode("ascii"),
                    "instrumental_b64": base64.b64encode(inst.tobytes()).decode("ascii"),
                }
            )
        return 0
    except Exception as exc:
        _send({"type": "error", "error": f"实时分轨 worker 异常: {exc}"})
        return 1
    finally:
        if backend is not None:
            try:
                backend.unload_model()
            except Exception:
                pass
            del backend
        release_torch_and_memory()
        sys.stdout = ipc_out


class ExperimentalLiveSeparator:
    """Near-real-time 2-stem processor reading recent chunks from FixedRingBuffer."""

    def __init__(
        self,
        ring_buffer: FixedRingBuffer,
        resource_manager: ResourceManager,
        *,
        ai_config: Optional[AIConfig] = None,
        audio_config: Optional[AudioConfig] = None,
        is_offline_job_busy_fn: Optional[Callable[[], bool]] = None,
        ai_python_executable: Optional[str | Path] = None,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.resource_manager = resource_manager
        self.ai_config = ai_config or AIConfig()
        self.audio_config = audio_config or ring_buffer.audio_config
        self._is_offline_job_busy_fn = is_offline_job_busy_fn
        self.ai_python_executable = str(ai_python_executable) if ai_python_executable else None

        sr = self.audio_config.sample_rate
        ch = self.audio_config.channels
        self._chunk_frames = max(sr // 2, int(round(self.ai_config.live_chunk_seconds * sr)))
        self._overlap_frames = max(0, int(round(self.ai_config.live_overlap_seconds * sr)))
        self._hop_frames = max(sr // 4, self._chunk_frames - self._overlap_frames)

        # Bounded output circular storage for assembled vocals & instrumental
        self._out_cap_frames = max(sr * 2, int(round(self.ai_config.live_max_buffer_seconds * sr)))
        self._out_vocals = np.zeros((self._out_cap_frames, ch), dtype=np.float32)
        self._out_inst = np.zeros((self._out_cap_frames, ch), dtype=np.float32)
        self._out_write_pos = 0
        self._out_available = 0

        self._lock = threading.RLock()
        self._active = False
        self._starting = False
        self._cancel_start_requested = False
        self._stop_event = threading.Event()
        self._feed_thread: Optional[threading.Thread] = None
        self._stream: Any = None

        # Spawn multiprocessing worker handles
        self._proc: Optional[multiprocessing.Process] = None
        self._req_q: Any = None
        self._res_q: Any = None
        self._proc_stop_ev: Any = None

        # External AI venv Popen worker handles
        self._subproc: Optional[subprocess.Popen[str]] = None
        self._subproc_tmp: Optional[tempfile.TemporaryDirectory[str]] = None
        self._subproc_writer_thread: Optional[threading.Thread] = None
        self._subproc_reader_thread: Optional[threading.Thread] = None
        self._subproc_stderr_thread: Optional[threading.Thread] = None
        self._subproc_stderr_tail: deque[str] = deque(maxlen=30)
        self._worker_pid: Optional[int] = None

        self._model_id = "mdx_low_vram_2stem"
        self._last_read_abs_frame = 0
        self._dropped_chunks = 0
        self._latest_rtf = 0.0
        self._latest_latency_ms = 0.0
        self._vocals_gain = 1.0
        self._inst_gain = 1.0
        self._status_message = "实验功能已关闭 (默认关闭)"
        self._overlap_add = OverlapAddAccumulator(channels=ch, overlap_frames=self._overlap_frames)

    def _uses_external_python(self) -> bool:
        if not self.ai_python_executable:
            return False
        try:
            return Path(self.ai_python_executable).resolve() != Path(sys.executable).resolve()
        except Exception:
            return str(self.ai_python_executable).strip() != str(sys.executable).strip()

    def set_gains(self, vocals_gain: float, inst_gain: float) -> None:
        with self._lock:
            self._vocals_gain = max(0.0, min(1.5, float(vocals_gain)))
            self._inst_gain = max(0.0, min(1.5, float(inst_gain)))

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def is_starting(self) -> bool:
        with self._lock:
            return self._starting

    def latest_metrics(self) -> LiveSeparationMetrics:
        snap = self.resource_manager.sample()
        with self._lock:
            buf_sec = self._out_available / float(self.audio_config.sample_rate)
            status = self._status_message
            if self._starting and not self._active and not status:
                status = "正在运行基准测试 / 初始化..."
            return LiveSeparationMetrics(
                active=self._active,
                model_id=self._model_id,
                latency_ms=round(self._latest_latency_ms, 1),
                rtf=round(self._latest_rtf, 3),
                main_ram_mb=round(snap.main_ram_mb, 1),
                worker_ram_mb=round(snap.ai_worker_ram_mb, 1),
                vram_free_mb=round(snap.vram_free_mb, 1) if snap.vram_free_mb is not None else None,
                gpu_util_pct=snap.gpu_utilization_pct,
                buffer_seconds=round(buf_sec, 2),
                max_buffer_seconds=self.ai_config.live_max_buffer_seconds,
                dropped_chunks=self._dropped_chunks,
                status_message=status,
            )

    def run_benchmark(
        self,
        model_id: str = "mdx_low_vram_2stem",
        *,
        use_gpu: bool = True,
        use_mock_backend: bool = False,
        simulate_delay_sec: float = 0.0,
    ) -> LiveBenchmarkResult:
        if self._uses_external_python() or not use_mock_backend:
            return benchmark_live_model_isolated(
                model_id=model_id,
                ai_python_executable=self.ai_python_executable,
                use_gpu=use_gpu,
                use_mock_backend=use_mock_backend,
                simulate_delay_sec=simulate_delay_sec,
                ai_config=self.ai_config,
                audio_config=self.audio_config,
                cancel_event=self._stop_event,
            )
        return benchmark_live_model(
            model_id=model_id,
            use_gpu=use_gpu,
            use_mock_backend=use_mock_backend,
            simulate_delay_sec=simulate_delay_sec,
            ai_config=self.ai_config,
            audio_config=self.audio_config,
        )

    def _is_worker_alive(self) -> bool:
        if self._proc is not None:
            return self._proc.is_alive()
        if self._subproc is not None:
            return self._subproc.poll() is None
        return False

    def _worker_exitcode(self) -> Optional[int]:
        if self._proc is not None:
            return self._proc.exitcode
        if self._subproc is not None:
            return self._subproc.poll()
        return None

    def _launch_external_worker_locked(
        self,
        *,
        model_id: str,
        use_gpu: bool,
        use_mock_backend: bool,
        simulate_delay_sec: float,
    ) -> tuple[queue.Queue[Any], queue.Queue[dict[str, Any]], int]:
        assert self.ai_python_executable is not None
        bundle_root = get_bundle_root()
        tmp_dir = tempfile.TemporaryDirectory(prefix="ls_live_ipc_")
        cfg_path = Path(tmp_dir.name) / "live_config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "ai_config": asdict(self.ai_config),
                    "model_id": model_id,
                    "sample_rate": self.audio_config.sample_rate,
                    "use_gpu": use_gpu,
                    "use_mock_backend": use_mock_backend,
                    "simulate_delay_sec": simulate_delay_sec,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        env = prepend_ffmpeg_path_env(os.environ.copy())
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)

        self._subproc_stderr_tail.clear()
        proc = subprocess.Popen(
            [
                self.ai_python_executable,
                "-m",
                "streaming.live_separator",
                "--worker",
                "--config-json",
                str(cfg_path),
            ],
            cwd=str(bundle_root),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **subprocess_no_window_kwargs(),
        )
        req_q: queue.Queue[Any] = queue.Queue(maxsize=2)
        res_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=4)

        def _write_stdin() -> None:
            pipe = proc.stdin
            if pipe is None:
                return
            try:
                while not self._stop_event.is_set() and proc.poll() is None:
                    try:
                        item = req_q.get(timeout=0.08)
                    except queue.Empty:
                        continue
                    if item is None:
                        pipe.write(json.dumps({"type": "stop"}) + "\n")
                        pipe.flush()
                        break
                    seq, chunk_bytes, shape = item
                    line = json.dumps(
                        {
                            "type": "chunk",
                            "seq": int(seq),
                            "shape": list(shape),
                            "pcm_b64": base64.b64encode(chunk_bytes).decode("ascii"),
                        }
                    )
                    pipe.write(line + "\n")
                    pipe.flush()
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

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
                        msg = json.loads(text)
                    except Exception:
                        brace = text.find("{")
                        if brace <= 0:
                            continue
                        try:
                            msg = json.loads(text[brace:])
                        except Exception:
                            continue
                    if not isinstance(msg, dict):
                        continue
                    mtype = msg.get("type")
                    if mtype == "chunk":
                        try:
                            raw_shape = msg["shape"]
                            decoded = {
                                "type": "chunk",
                                "seq": msg.get("seq"),
                                "vocals": base64.b64decode(msg["vocals_b64"]),
                                "instrumental": base64.b64decode(msg["instrumental_b64"]),
                                "shape": tuple(int(x) for x in raw_shape),
                                "infer_sec": float(msg.get("infer_sec", 0.0)),
                            }
                        except Exception:
                            logger.warning("Ignoring malformed external live stdout chunk JSON")
                            continue
                        out_item = decoded
                    else:
                        out_item = msg
                    try:
                        res_q.put_nowait(out_item)
                    except queue.Full:
                        if out_item.get("type") in ("ready", "error"):
                            try:
                                res_q.get_nowait()
                            except queue.Empty:
                                pass
                            try:
                                res_q.put_nowait(out_item)
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

        self._subproc = proc
        self._subproc_tmp = tmp_dir
        self._req_q = req_q
        self._res_q = res_q
        self._worker_pid = proc.pid
        self._subproc_writer_thread = threading.Thread(
            target=_write_stdin, name="ListenScope-LiveStdinWriter", daemon=True
        )
        self._subproc_reader_thread = threading.Thread(
            target=_read_stdout, name="ListenScope-LiveStdoutReader", daemon=True
        )
        self._subproc_stderr_thread = threading.Thread(
            target=_read_stderr, name="ListenScope-LiveStderrDrain", daemon=True
        )
        self._subproc_writer_thread.start()
        self._subproc_reader_thread.start()
        self._subproc_stderr_thread.start()
        return req_q, res_q, proc.pid

    def start(
        self,
        *,
        model_id: str = "mdx_low_vram_2stem",
        use_gpu: bool = True,
        use_mock_backend: bool = False,
        simulate_delay_sec: float = 0.0,
        skip_benchmark: bool = False,
        open_audio_device: bool = False,
        gpu_ai_ready: Optional[bool] = None,
        gpu_block_reason: Optional[str] = None,
    ) -> tuple[bool, str]:
        with self._lock:
            if self._active:
                return True, "实验性实时分轨已在运行中。"
            if self._starting:
                return False, "实验性实时分轨正在启动或运行基准测试中，请稍候。"
            if self._is_offline_job_busy_fn is not None and self._is_offline_job_busy_fn():
                return False, "已有离线 AI 分轨任务运行中（硬限制=1），请先停止或等待其完成。"

            spec = MODEL_REGISTRY.get(model_id)
            if spec is None or spec.stem_mode != "2stem":
                return False, "实验性实时分轨仅支持 2-stem 模型。"

            if getattr(sys, "frozen", False) and not self._uses_external_python() and not use_mock_backend:
                msg = (
                    "独立 AI 环境 (.venv-ai) 未配置：Windows 打包版主程序不包含 PyTorch/ONNX Runtime，"
                    "请在「设置 -> 资源安全阈值 & AI 配置」中指定 .venv-ai\\Scripts\\python.exe。"
                )
                self._status_message = msg
                return False, msg

            allowed, reason = self.resource_manager.can_start_ai_job(
                stem_mode="2stem",
                require_gpu=(use_gpu and not use_mock_backend),
                gpu_ai_ready=gpu_ai_ready,
                gpu_block_reason=gpu_block_reason,
            )
            if not allowed:
                self._status_message = f"拒绝启动: {reason}"
                return False, reason

            pre_snap = self.resource_manager.sample()
            if pre_snap.status != ResourceStatus.NORMAL:
                detail = "；".join(pre_snap.status_reasons) or pre_snap.status.value
                msg = f"当前资源处于 {pre_snap.status.value} 状态（{detail}），禁止开启实验性持续实时分轨。"
                self._status_message = msg
                return False, msg

            self._starting = True
            self._cancel_start_requested = False
            self._stop_event.clear()
            self._status_message = "正在运行基准测试与启动实时分轨..."

        try:
            if not skip_benchmark:
                bench = self.run_benchmark(
                    model_id=model_id,
                    use_gpu=use_gpu,
                    use_mock_backend=use_mock_backend,
                    simulate_delay_sec=simulate_delay_sec,
                )
                with self._lock:
                    self._latest_rtf = bench.rtf
                    if self._cancel_start_requested:
                        msg = "实时分轨启动已被用户取消"
                        self._status_message = msg
                        return False, msg
                    if not bench.can_run_realtime:
                        self._status_message = bench.message
                        return False, bench.message

            with self._lock:
                if self._cancel_start_requested or self._stop_event.is_set():
                    msg = "实时分轨启动已被用户取消"
                    self._status_message = msg
                    return False, msg
                if self._is_offline_job_busy_fn is not None and self._is_offline_job_busy_fn():
                    msg = "已有离线 AI 分轨任务运行中（硬限制=1），请先停止或等待其完成。"
                    self._status_message = msg
                    return False, msg

                self._model_id = model_id
                self._dropped_chunks = 0
                self._latest_latency_ms = 0.0
                self._out_vocals.fill(0.0)
                self._out_inst.fill(0.0)
                self._out_write_pos = 0
                self._out_available = 0
                self._overlap_add.reset()
                self._last_read_abs_frame = self.ring_buffer.total_written_frames

                if self._uses_external_python():
                    req_q, res_q, worker_pid = self._launch_external_worker_locked(
                        model_id=model_id,
                        use_gpu=use_gpu,
                        use_mock_backend=use_mock_backend,
                        simulate_delay_sec=simulate_delay_sec,
                    )
                else:
                    ctx = multiprocessing.get_context("spawn")
                    req_q = ctx.Queue(maxsize=2)
                    res_q = ctx.Queue(maxsize=4)
                    stop_ev = ctx.Event()
                    proc = ctx.Process(
                        target=_live_worker_entry,
                        args=(
                            asdict(self.ai_config),
                            model_id,
                            self.audio_config.sample_rate,
                            use_gpu,
                            use_mock_backend,
                            simulate_delay_sec,
                            req_q,
                            res_q,
                            stop_ev,
                        ),
                        name="ListenScope-LiveSepWorker",
                        daemon=True,
                    )
                    proc.start()

                    self._proc = proc
                    self._req_q = req_q
                    self._res_q = res_q
                    self._proc_stop_ev = stop_ev
                    worker_pid = proc.pid or 0
                    self._worker_pid = proc.pid

            # Wait briefly for worker model ready signal (up to 15s) without holding self._lock
            ready_deadline = time.monotonic() + 15.0
            ready_ok = False
            err_msg = "实时分轨 worker 启动超时"
            while time.monotonic() < ready_deadline:
                with self._lock:
                    if self._cancel_start_requested or self._stop_event.is_set():
                        err_msg = "实时分轨启动已被用户取消"
                        break
                try:
                    msg = res_q.get(timeout=0.1)
                    if msg.get("type") == "ready":
                        ready_ok = True
                        break
                    if msg.get("type") == "error":
                        err_msg = str(msg.get("error", err_msg))
                        break
                except queue.Empty:
                    if not self._is_worker_alive():
                        if self._subproc_reader_thread is not None and self._subproc_reader_thread.is_alive():
                            self._subproc_reader_thread.join(timeout=0.3)
                        if self._subproc_stderr_thread is not None and self._subproc_stderr_thread.is_alive():
                            self._subproc_stderr_thread.join(timeout=0.3)
                        try:
                            msg = res_q.get_nowait()
                            if msg.get("type") == "ready":
                                ready_ok = True
                                break
                            if msg.get("type") == "error":
                                err_msg = str(msg.get("error", err_msg))
                                break
                        except queue.Empty:
                            pass
                        code = self._worker_exitcode()
                        err_tail = list(self._subproc_stderr_tail)[-5:]
                        detail = f" ({' | '.join(err_tail)})" if err_tail else ""
                        err_msg = f"实时分轨 worker 意外退出 (exitcode={code}){detail}"
                        break

            if not ready_ok:
                self._cleanup_worker_only()
                with self._lock:
                    self._active = False
                    self._status_message = err_msg
                return False, err_msg

            with self._lock:
                if self._cancel_start_requested or self._stop_event.is_set():
                    ready_ok = False
                    err_msg = "实时分轨启动已被用户取消"
                else:
                    self._active = True
                    self._status_message = f"实验性 2-stem 近实时分轨运行中 ({model_id})"
                    self.resource_manager.update_runtime_state(
                        active_ai_jobs=1,
                        loaded_models=1,
                        current_model=model_id,
                        current_task="experimental_live_2stem",
                        ai_worker_pid=worker_pid or self._worker_pid,
                        ai_buffer_seconds=0.0,
                    )
                    self._feed_thread = threading.Thread(
                        target=self._run_loop,
                        name="ListenScope-LiveSepCoordinator",
                        daemon=True,
                    )
                    self._feed_thread.start()

            if not ready_ok:
                self._cleanup_worker_only()
                with self._lock:
                    self._active = False
                    self._status_message = err_msg
                return False, err_msg

            if open_audio_device:
                self._ensure_output_stream()

            return True, self._status_message
        except Exception as exc:
            self._cleanup_worker_only()
            with self._lock:
                self._active = False
                self._status_message = f"实时分轨启动失败: {exc}"
            return False, self._status_message
        finally:
            with self._lock:
                self._starting = False

    def _append_output(self, vocals: np.ndarray, inst: np.ndarray) -> None:
        n = int(min(vocals.shape[0], inst.shape[0]))
        if n <= 0:
            return
        with self._lock:
            if n >= self._out_cap_frames:
                self._out_vocals[:, :] = vocals[-self._out_cap_frames :]
                self._out_inst[:, :] = inst[-self._out_cap_frames :]
                self._out_write_pos = 0
                self._out_available = self._out_cap_frames
                return
            end = self._out_write_pos + n
            if end <= self._out_cap_frames:
                self._out_vocals[self._out_write_pos : end] = vocals[:n]
                self._out_inst[self._out_write_pos : end] = inst[:n]
            else:
                first = self._out_cap_frames - self._out_write_pos
                self._out_vocals[self._out_write_pos :] = vocals[:first]
                self._out_inst[self._out_write_pos :] = inst[:first]
                self._out_vocals[: n - first] = vocals[first:n]
                self._out_inst[: n - first] = inst[first:n]
            self._out_write_pos = end % self._out_cap_frames
            self._out_available = min(self._out_cap_frames, self._out_available + n)

    def pull_mixed_block(
        self,
        num_frames: int,
        *,
        vocals_gain: Optional[float] = None,
        inst_gain: Optional[float] = None,
    ) -> np.ndarray:
        """Consume the oldest unread frames and pad the tail with silence if needed."""
        with self._lock:
            vg = self._vocals_gain if vocals_gain is None else float(vocals_gain)
            ig = self._inst_gain if inst_gain is None else float(inst_gain)
            take = min(num_frames, self._out_available)
            out = np.zeros((num_frames, self.audio_config.channels), dtype=np.float32)
            if take <= 0:
                return out
            start = (self._out_write_pos - self._out_available) % self._out_cap_frames
            if start + take <= self._out_cap_frames:
                voc = self._out_vocals[start : start + take]
                inst = self._out_inst[start : start + take]
            else:
                first = self._out_cap_frames - start
                voc = np.vstack([self._out_vocals[start:], self._out_vocals[: take - first]])
                inst = np.vstack([self._out_inst[start:], self._out_inst[: take - first]])
            mixed = np.clip(voc * vg + inst * ig, -1.0, 1.0)
            out[:take] = mixed
            self._out_available -= take
            return out

    def _run_loop(self) -> None:
        sr = self.audio_config.sample_rate
        chunk_duration = self._chunk_frames / float(sr)
        seq = 0

        while not self._stop_event.is_set():
            snap = self.resource_manager.sample()
            if snap.status in (ResourceStatus.WARNING, ResourceStatus.CRITICAL):
                reason = "；".join(snap.status_reasons) or f"资源状态进入 {snap.status.value}"
                logger.warning("ExperimentalLiveSeparator auto-stopping: %s", reason)
                self.close_output_stream()
                self._cleanup_worker_only()
                with self._lock:
                    self._active = False
                    self._status_message = f"已自动停止实时分轨（{reason}）；基础频谱分析继续运行。"
                self.resource_manager.update_runtime_state(
                    active_ai_jobs=0,
                    loaded_models=0,
                    current_model=None,
                    current_task=None,
                    ai_worker_pid=None,
                    ai_buffer_seconds=0.0,
                )
                return

            # Drain any completed separated chunks from worker
            if self._res_q is not None:
                while True:
                    try:
                        msg = self._res_q.get_nowait()
                    except queue.Empty:
                        break
                    except Exception:
                        break
                    if not isinstance(msg, dict):
                        logger.warning("Ignoring non-dict live IPC payload")
                        continue
                    mtype = msg.get("type")
                    if mtype == "error":
                        err = str(msg.get("error", "Worker 异常"))
                        self.close_output_stream()
                        self._cleanup_worker_only()
                        with self._lock:
                            self._active = False
                            self._status_message = f"实时分轨异常停止: {err}"
                        self.resource_manager.update_runtime_state(
                            active_ai_jobs=0,
                            loaded_models=0,
                            current_model=None,
                            current_task=None,
                            ai_worker_pid=None,
                            ai_buffer_seconds=0.0,
                        )
                        return
                    if mtype == "chunk":
                        raw_shape = msg.get("shape")
                        voc_bytes = msg.get("vocals")
                        inst_bytes = msg.get("instrumental")
                        if (
                            not isinstance(raw_shape, (list, tuple))
                            or len(raw_shape) != 2
                            or not isinstance(voc_bytes, (bytes, bytearray, memoryview))
                            or not isinstance(inst_bytes, (bytes, bytearray, memoryview))
                        ):
                            logger.warning("Ignoring malformed live IPC chunk payload")
                            continue
                        try:
                            shape = (int(raw_shape[0]), int(raw_shape[1]))
                            infer_sec = float(msg.get("infer_sec", 0.0))
                        except (TypeError, ValueError):
                            logger.warning("Ignoring unparseable live IPC chunk metadata")
                            continue
                        if not np.isfinite(infer_sec) or infer_sec < 0.0:
                            infer_sec = 0.0
                        expected_bytes = shape[0] * shape[1] * 4
                        if (
                            shape[0] <= 0
                            or shape[1] != self.audio_config.channels
                            or len(voc_bytes) != expected_bytes
                            or len(inst_bytes) != expected_bytes
                        ):
                            logger.warning(
                                "Ignoring mismatched live IPC chunk bytes (shape=%s, voc=%d, inst=%d)",
                                shape,
                                len(voc_bytes),
                                len(inst_bytes),
                            )
                            continue
                        voc = np.frombuffer(voc_bytes, dtype=np.float32).reshape(shape)
                        inst = np.frombuffer(inst_bytes, dtype=np.float32).reshape(shape)
                        if not np.all(np.isfinite(voc)):
                            voc = np.nan_to_num(voc, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
                        if not np.all(np.isfinite(inst)):
                            inst = np.nan_to_num(inst, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
                        assembled = self._overlap_add.process_chunk({"vocals": voc, "instrumental": inst})
                        self._append_output(assembled["vocals"], assembled["instrumental"])
                        rtf = infer_sec / max(0.01, chunk_duration)
                        with self._lock:
                            self._latest_rtf = rtf
                            self._latest_latency_ms = infer_sec * 1000.0 + (self._overlap_frames / float(sr)) * 1000.0
                        if rtf >= 1.25:
                            logger.warning("Live separation RTF=%.2f >= 1.25, dropping stale backlog", rtf)

            if not self._is_worker_alive():
                if self._subproc_reader_thread is not None and self._subproc_reader_thread.is_alive():
                    self._subproc_reader_thread.join(timeout=0.3)
                if self._subproc_stderr_thread is not None and self._subproc_stderr_thread.is_alive():
                    self._subproc_stderr_thread.join(timeout=0.3)
                err = ""
                if self._res_q is not None:
                    while True:
                        try:
                            msg = self._res_q.get_nowait()
                        except Exception:
                            break
                        if isinstance(msg, dict) and msg.get("type") == "error":
                            err = str(msg.get("error", ""))
                code = self._worker_exitcode()
                tail = list(self._subproc_stderr_tail)[-5:]
                detail = err or (f"worker 意外退出 (exitcode={code})" + (f" ({' | '.join(tail)})" if tail else ""))
                self.close_output_stream()
                self._cleanup_worker_only()
                with self._lock:
                    self._active = False
                    self._status_message = f"实时分轨异常停止: {detail}"
                self.resource_manager.update_runtime_state(
                    active_ai_jobs=0,
                    loaded_models=0,
                    current_model=None,
                    current_task=None,
                    ai_worker_pid=None,
                    ai_buffer_seconds=0.0,
                )
                return

            newest = self.ring_buffer.total_written_frames
            oldest = self.ring_buffer.oldest_abs_frame
            if newest < self._last_read_abs_frame:
                # Ring buffer was cleared/reset; resync OLA state and cursor cleanly
                self._overlap_add.reset()
                self._last_read_abs_frame = max(oldest, newest - self._chunk_frames)
            elif self._last_read_abs_frame < oldest:
                self._overlap_add.reset()
                self._last_read_abs_frame = oldest

            backlog_frames = newest - self._last_read_abs_frame
            max_buf_frames = int(round(self.ai_config.live_max_buffer_seconds * sr))

            if backlog_frames > max_buf_frames:
                # Drop older buffered audio so memory/latency never exceed cap; reset OLA on jump
                with self._lock:
                    self._dropped_chunks += 1
                self._overlap_add.reset()
                self._last_read_abs_frame = max(oldest, newest - self._chunk_frames)
                backlog_frames = newest - self._last_read_abs_frame

            if backlog_frames >= self._chunk_frames and self._req_q is not None:
                read_start = max(oldest, self._last_read_abs_frame)
                read_end = min(newest, read_start + self._chunk_frames)
                pcm = self.ring_buffer.read_range(read_start, read_end)
                if pcm.shape[0] >= self._chunk_frames:
                    try:
                        self._req_q.put_nowait((seq, pcm.tobytes(), pcm.shape))
                        seq += 1
                        self._last_read_abs_frame = read_start + self._hop_frames
                    except queue.Full:
                        with self._lock:
                            self._dropped_chunks += 1
                        self._overlap_add.reset()
                        self._last_read_abs_frame = max(oldest, newest - self._overlap_frames)

            backlog_sec = max(0.0, (newest - self._last_read_abs_frame) / float(sr))
            self.resource_manager.update_runtime_state(
                ai_buffer_seconds=min(self.ai_config.live_max_buffer_seconds, backlog_sec)
            )
            self._stop_event.wait(timeout=0.05)

    def _ensure_output_stream(self) -> None:
        with self._lock:
            if self._stream is not None or self._stop_event.is_set() or not self._active:
                return
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
        except ImportError:
            return

        def _callback(outdata, frames, _time_info, _status) -> None:
            outdata[:] = self.pull_mixed_block(frames)

        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=self.audio_config.sample_rate,
                channels=self.audio_config.channels,
                dtype="float32",
                callback=_callback,
            )
            stream.start()
            discard = False
            with self._lock:
                if self._stream is not None or self._stop_event.is_set() or not self._active:
                    discard = True
                else:
                    self._stream = stream
            if discard:
                stream.stop()
                stream.close()
        except Exception:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            with self._lock:
                self._stream = None

    def close_output_stream(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _cleanup_worker_only(self) -> None:
        if self._proc_stop_ev is not None:
            try:
                self._proc_stop_ev.set()
            except Exception:
                pass
        if self._req_q is not None:
            try:
                self._req_q.put_nowait(None)
            except Exception:
                pass
        if self._proc is not None:
            proc = self._proc
            proc.join(timeout=1.0)
            if proc.is_alive():
                try:
                    proc.terminate()
                except Exception:
                    pass
                proc.join(timeout=0.5)
            if proc.is_alive():
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(timeout=0.3)
            self._proc = None

        if self._subproc is not None:
            sub = self._subproc
            if sub.poll() is None:
                try:
                    sub.wait(timeout=0.5)
                except Exception:
                    try:
                        sub.terminate()
                        sub.wait(timeout=0.5)
                    except Exception:
                        try:
                            sub.kill()
                            sub.wait(timeout=0.3)
                        except Exception:
                            pass
            for pipe_name in ("stdin", "stdout", "stderr"):
                pipe = getattr(sub, pipe_name, None)
                if pipe is not None:
                    try:
                        pipe.close()
                    except Exception:
                        pass
            self._subproc = None

        for attr in ("_subproc_writer_thread", "_subproc_reader_thread", "_subproc_stderr_thread"):
            th = getattr(self, attr, None)
            if th is not None and th.is_alive() and th is not threading.current_thread():
                th.join(timeout=0.4)
            setattr(self, attr, None)

        if self._subproc_tmp is not None:
            try:
                self._subproc_tmp.cleanup()
            except Exception:
                pass
            self._subproc_tmp = None

        for q in (self._req_q, self._res_q):
            if q is not None:
                try:
                    while True:
                        q.get_nowait()
                except Exception:
                    pass
                close_fn = getattr(q, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
        self._req_q = None
        self._res_q = None
        self._proc_stop_ev = None
        self._worker_pid = None

    def stop(self, *, status_message: str = "实验功能已停止") -> None:
        with self._lock:
            self._cancel_start_requested = True
            self._stop_event.set()
            thread = self._feed_thread
            self._feed_thread = None
        self.close_output_stream()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._cleanup_worker_only()
        with self._lock:
            self._active = False
            self._status_message = status_message
        self.resource_manager.update_runtime_state(
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            ai_worker_pid=None,
            ai_buffer_seconds=0.0,
        )


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="ListenScope Isolated Live 2-Stem Worker")
    parser.add_argument("--worker", action="store_true", help="Run external live worker stdin/stdout loop")
    parser.add_argument("--config-json", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        return _external_worker_cli(args.config_json)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
