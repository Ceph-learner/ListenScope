"""Isolated AI separation worker process (spawn multiprocessing or standalone AI venv CLI).

Strict resource lifecycle:
1. Executes completely outside the GUI / audio-capture main process.
2. Loads at most 1 model on demand.
3. Streams chunk-by-chunk read -> infer -> write via `stream_chunked_separation`.
4. Unloads model, runs gc + cuda cache cleanup, cleans temp staging on abort/OOM,
   reports structured progress/result via IPC, and exits so OS reclaims 100% memory.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Callable, Optional

import psutil

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.backend import build_separation_backend
from ai.models import MODEL_REGISTRY
from ai.resource_guard import (
    cleanup_temp_outputs,
    inspect_wav_header,
    is_oom_exception,
    release_torch_and_memory,
    stream_chunked_separation,
)
from core.config import AIConfig, TargetHardwareSpec
from core.models import AIJobProgress, AIJobRequest, AIJobResult, AIJobState, OOMRecoveryAction
from core.system_probe import (
    _probe_gpus_nvml,
    _probe_gpus_nvidia_smi,
    _probe_onnxruntime,
    _probe_pytorch,
    evaluate_gpu_ai_readiness,
)


def _sample_process_rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)


def _sample_vram_used_mb() -> Optional[float]:
    gpus, _, _ = _probe_gpus_nvml()
    if not gpus:
        gpus, _, _ = _probe_gpus_nvidia_smi()
    if gpus:
        return gpus[0].used_vram_mb
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            return torch.cuda.memory_allocated(0) / (1024.0 * 1024.0)
    except Exception:
        pass
    return None


def _sleep_cancellable(seconds: float, cancel_check: Callable[[], bool]) -> bool:
    """Sleep in tiny steps so cancellation interrupts promptly. Returns True if cancelled."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if cancel_check():
            return True
        time.sleep(min(0.03, max(0.005, deadline - time.monotonic())))
    return cancel_check()


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    data = asdict(obj)
    if "state" in data and hasattr(obj.state, "value"):
        data["state"] = obj.state.value
    if "recovery_options" in data:
        data["recovery_options"] = [
            opt.value if hasattr(opt, "value") else str(opt) for opt in obj.recovery_options
        ]
    return data


def _deserialize_request(data: dict[str, Any]) -> AIJobRequest:
    return AIJobRequest(
        task_id=str(data["task_id"]),
        input_wav_path=str(data["input_wav_path"]),
        output_dir=str(data["output_dir"]),
        stem_mode=str(data["stem_mode"]),
        model_id=str(data["model_id"]),
        use_gpu=bool(data.get("use_gpu", True)),
        segment_seconds=int(data.get("segment_seconds", 10)),
        overlap=float(data.get("overlap", 0.25)),
        chunk_seconds=float(data.get("chunk_seconds", 20.0)),
        simulate_oom=bool(data.get("simulate_oom", False)),
        simulate_delay_sec=float(data.get("simulate_delay_sec", 0.0)),
        use_mock_backend=bool(data.get("use_mock_backend", False)),
    )


def execute_worker_job(
    request: AIJobRequest,
    *,
    cancel_check: Optional[Callable[[], bool]] = None,
    emit_progress: Optional[Callable[[AIJobProgress], None]] = None,
    ai_config: Optional[AIConfig] = None,
) -> AIJobResult:
    """Run one complete separation job inside the worker process."""
    cfg = ai_config or AIConfig()
    is_cancelled = cancel_check or (lambda: False)
    pid = os.getpid()

    t_start = time.monotonic()
    start_ram = _sample_process_rss_mb()
    peak_ram = start_ram
    start_vram = _sample_vram_used_mb()
    peak_vram = start_vram

    model_spec = MODEL_REGISTRY.get(request.model_id)
    architecture = model_spec.architecture if model_spec else "unknown"
    device_label = "MockCPU" if request.use_mock_backend else ("GPU-CUDA" if request.use_gpu else "CPU")

    out_dir = Path(request.output_dir)
    staging_dir = out_dir / f".tmp_{request.task_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    input_duration_sec = 0.0
    backend = None
    final_paths: dict[str, str] = {}

    def _track_peaks() -> None:
        nonlocal peak_ram, peak_vram
        cur_ram = _sample_process_rss_mb()
        if cur_ram > peak_ram:
            peak_ram = cur_ram
        cur_vram = _sample_vram_used_mb()
        if cur_vram is not None:
            if peak_vram is None or cur_vram > peak_vram:
                peak_vram = cur_vram

    def _emit(
        state: AIJobState,
        progress: float,
        message: str,
        *,
        current_chunk: int = 0,
        total_chunks: int = 0,
    ) -> None:
        _track_peaks()
        if emit_progress is not None:
            emit_progress(
                AIJobProgress(
                    task_id=request.task_id,
                    state=state,
                    progress=max(0.0, min(1.0, float(progress))),
                    message=message,
                    current_chunk=current_chunk,
                    total_chunks=total_chunks,
                    worker_pid=pid,
                    peak_ram_mb=peak_ram,
                    peak_vram_mb=peak_vram,
                )
            )

    def _build_abort_result(
        state: AIJobState,
        *,
        oom: bool = False,
        recovery: Optional[list[OOMRecoveryAction]] = None,
        error: Optional[str] = None,
    ) -> AIJobResult:
        elapsed = max(0.001, time.monotonic() - t_start)
        end_ram = _sample_process_rss_mb()
        end_vram = _sample_vram_used_mb()
        return AIJobResult(
            task_id=request.task_id,
            state=state,
            stem_paths={},
            elapsed_sec=elapsed,
            input_duration_sec=input_duration_sec,
            rtf=None,
            device_used=device_label,
            model_id=request.model_id,
            architecture=architecture,
            oom_occurred=oom,
            fallback_used=not request.use_gpu,
            recovery_options=recovery or [],
            start_ram_mb=start_ram,
            peak_ram_mb=peak_ram,
            end_ram_mb=end_ram,
            start_vram_mb=start_vram,
            peak_vram_mb=peak_vram,
            end_vram_mb=end_vram,
            error=error,
        )

    try:
        if model_spec is None:
            raise ValueError(f"未知 AI 模型 ID: {request.model_id}")

        _emit(AIJobState.PREPARING, 0.02, f"检查音频与模型 {model_spec.display_name}...")
        meta = inspect_wav_header(request.input_wav_path, ai_config=cfg)
        input_duration_sec = meta.duration_sec

        if not request.use_mock_backend and request.use_gpu:
            gpus, _, _ = _probe_gpus_nvml()
            if not gpus:
                gpus, _, _ = _probe_gpus_nvidia_smi()
            pt_info = _probe_pytorch()
            ort_info = _probe_onnxruntime()
            gpu_ready, block_reason = evaluate_gpu_ai_readiness(
                gpus,
                pt_info,
                ort_info,
                target=TargetHardwareSpec(),
            )
            if not gpu_ready:
                raise RuntimeError(block_reason or "PyTorch/CUDA 或 ONNX Runtime GPU 未就绪，拒绝进入 GPU AI 推理。")

        if is_cancelled():
            cleanup_temp_outputs(staging_dir)
            return _build_abort_result(AIJobState.CANCELLED, error="任务在准备阶段被取消")

        _emit(AIJobState.LOADING_MODEL, 0.08, f"按需加载单模型: {model_spec.display_name}...")
        backend = build_separation_backend(
            request.model_id,
            use_gpu=request.use_gpu,
            segment_seconds=request.segment_seconds,
            overlap=request.overlap,
            ai_config=cfg,
            use_mock_backend=request.use_mock_backend,
            simulate_oom=request.simulate_oom,
            simulate_delay_sec=request.simulate_delay_sec,
            output_dir=staging_dir,
        )

        # Allow cancellation to be tested reliably during LoadingModel when delay is active
        if request.simulate_delay_sec > 0.0:
            if _sleep_cancellable(min(0.4, request.simulate_delay_sec), is_cancelled):
                cleanup_temp_outputs(staging_dir)
                return _build_abort_result(AIJobState.CANCELLED, error="任务在加载模型阶段被取消")

        backend.load_model()
        _track_peaks()

        if is_cancelled():
            cleanup_temp_outputs(staging_dir)
            return _build_abort_result(AIJobState.CANCELLED, error="任务在模型加载完成后被取消")

        total_chunks_ref = [max(1, int((meta.duration_sec + max(0.5, request.chunk_seconds) - 0.01) // max(0.5, request.chunk_seconds)))]
        _emit(
            AIJobState.INFERRING,
            0.12,
            f"开始分块流式推理 (chunk={request.chunk_seconds:.0f}s)...",
            current_chunk=0,
            total_chunks=total_chunks_ref[0],
        )

        def _on_chunk_progress(chunk_idx: int, total_chunks: int, msg: str) -> None:
            total_chunks_ref[0] = total_chunks
            frac = 0.12 + 0.78 * (chunk_idx / float(max(1, total_chunks)))
            _emit(
                AIJobState.INFERRING,
                frac,
                msg,
                current_chunk=chunk_idx,
                total_chunks=total_chunks,
            )

        staged_stems = stream_chunked_separation(
            request.input_wav_path,
            staging_dir,
            model_spec.stems,
            backend.separate_chunk,
            chunk_seconds=request.chunk_seconds,
            overlap_seconds=cfg.long_audio_overlap_seconds,
            cancel_check=is_cancelled,
            progress_cb=_on_chunk_progress,
        )

        _emit(
            AIJobState.WRITING,
            0.94,
            "正在完成音轨写入与输出校验...",
            current_chunk=total_chunks_ref[0],
            total_chunks=total_chunks_ref[0],
        )
        if request.simulate_delay_sec > 0.0:
            if _sleep_cancellable(min(0.35, request.simulate_delay_sec), is_cancelled):
                cleanup_temp_outputs(staging_dir)
                _emit(AIJobState.CANCELLED, 0.0, "任务在写入输出阶段被取消")
                return _build_abort_result(AIJobState.CANCELLED, error="任务在写入输出阶段被取消")

        if is_cancelled():
            cleanup_temp_outputs(staging_dir)
            _emit(AIJobState.CANCELLED, 0.0, "任务在写入输出阶段被取消")
            return _build_abort_result(AIJobState.CANCELLED, error="任务在写入输出阶段被取消")

        # Release model cleanly before finalizing & sampling end memory
        backend.unload_model()
        del backend
        backend = None
        release_torch_and_memory()

        out_dir.mkdir(parents=True, exist_ok=True)
        for stem_name, staged_path_str in staged_stems.items():
            staged_file = Path(staged_path_str)
            dst_file = out_dir / staged_file.name
            shutil.move(str(staged_file), str(dst_file))
            final_paths[stem_name] = str(dst_file)
        cleanup_temp_outputs(staging_dir)

        elapsed = max(0.001, time.monotonic() - t_start)
        rtf = (elapsed / input_duration_sec) if input_duration_sec > 0 else None
        end_ram = _sample_process_rss_mb()
        end_vram = _sample_vram_used_mb()
        _track_peaks()

        _emit(
            AIJobState.COMPLETED,
            1.0,
            f"分离完成 ({len(final_paths)} 轨, 用时 {elapsed:.2f}s)",
            current_chunk=total_chunks_ref[0],
            total_chunks=total_chunks_ref[0],
        )
        return AIJobResult(
            task_id=request.task_id,
            state=AIJobState.COMPLETED,
            stem_paths=final_paths,
            elapsed_sec=elapsed,
            input_duration_sec=input_duration_sec,
            rtf=rtf,
            device_used=device_label,
            model_id=request.model_id,
            architecture=architecture,
            oom_occurred=False,
            fallback_used=not request.use_gpu,
            recovery_options=[],
            start_ram_mb=start_ram,
            peak_ram_mb=peak_ram,
            end_ram_mb=end_ram,
            start_vram_mb=start_vram,
            peak_vram_mb=peak_vram,
            end_vram_mb=end_vram,
        )
    except InterruptedError:
        cleanup_temp_outputs(staging_dir)
        _emit(AIJobState.CANCELLED, 0.0, "AI 分轨任务已取消")
        return _build_abort_result(AIJobState.CANCELLED, error="AI 分轨任务已取消")
    except Exception as exc:
        cleanup_temp_outputs(staging_dir)
        for p in final_paths.values():
            cleanup_temp_outputs(p)
        if is_oom_exception(exc):
            opts = getattr(
                exc,
                "recovery_options",
                [
                    OOMRecoveryAction.REDUCE_SEGMENT,
                    OOMRecoveryAction.LIGHTER_MODEL,
                    OOMRecoveryAction.CPU_FALLBACK,
                ],
            )
            _emit(AIJobState.OOM_ERROR, 0.0, f"显存/内存不足 (OOM): {exc}")
            return _build_abort_result(
                AIJobState.OOM_ERROR,
                oom=True,
                recovery=list(opts),
                error=str(exc),
            )
        _emit(AIJobState.FAILED, 0.0, f"AI 分轨失败: {exc}")
        return _build_abort_result(AIJobState.FAILED, error=str(exc))
    finally:
        if backend is not None:
            try:
                backend.unload_model()
            except Exception:
                pass
            del backend
        release_torch_and_memory()


def spawn_worker_entry(
    req_dict: dict[str, Any],
    ai_cfg_dict: dict[str, Any],
    msg_queue: Any,
    cancel_event: Any,
) -> None:
    """Entry point executed inside `multiprocessing.get_context('spawn').Process`."""
    req = _deserialize_request(req_dict)
    cfg = AIConfig(**ai_cfg_dict)

    def _emit(prog: AIJobProgress) -> None:
        try:
            msg_queue.put({"type": "progress", "payload": _serialize_dataclass(prog)})
        except Exception:
            pass

    try:
        res = execute_worker_job(
            req,
            cancel_check=cancel_event.is_set,
            emit_progress=_emit,
            ai_config=cfg,
        )
        msg_queue.put({"type": "result", "payload": _serialize_dataclass(res)})
    except Exception as exc:
        msg_queue.put(
            {
                "type": "result",
                "payload": _serialize_dataclass(
                    AIJobResult(
                        task_id=req.task_id,
                        state=AIJobState.FAILED,
                        error=f"Worker top-level exception: {exc}",
                    )
                ),
            }
        )


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="ListenScope isolated AI Worker CLI runner")
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--cancel-flag", type=Path, required=True)
    args = parser.parse_args()

    req_dict = json.loads(args.request_json.read_text(encoding="utf-8"))
    cfg_dict = json.loads(args.config_json.read_text(encoding="utf-8"))
    req = _deserialize_request(req_dict)
    cfg = AIConfig(**cfg_dict)

    def _emit(prog: AIJobProgress) -> None:
        print(
            json.dumps({"type": "progress", "payload": _serialize_dataclass(prog)}, ensure_ascii=False),
            flush=True,
        )

    res = execute_worker_job(
        req,
        cancel_check=args.cancel_flag.exists,
        emit_progress=_emit,
        ai_config=cfg,
    )
    print(
        json.dumps({"type": "result", "payload": _serialize_dataclass(res)}, ensure_ascii=False),
        flush=True,
    )
    return 0 if res.state in (AIJobState.COMPLETED, AIJobState.CANCELLED) else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
