"""RTF benchmark gate for Phase 8 experimental near-real-time 2-stem separation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Optional

import numpy as np

from ai.backend import build_separation_backend
from ai.models import MODEL_REGISTRY
from ai.resource_guard import release_torch_and_memory
from core.config import AIConfig, AudioConfig, TargetHardwareSpec
from core.paths import get_bundle_root, popen_external_python, prepend_ffmpeg_path_env, subprocess_no_window_kwargs
from core.system_probe import (
    _probe_gpus_nvml,
    _probe_gpus_nvidia_smi,
    _probe_onnxruntime,
    _probe_pytorch,
    evaluate_gpu_ai_readiness,
)


@dataclass
class LiveBenchmarkResult:
    model_id: str
    device_used: str
    test_duration_sec: float
    elapsed_sec: float
    rtf: float
    can_run_realtime: bool
    message: str


def live_frame_sizes(ai_config: AIConfig, sample_rate: int) -> tuple[int, int, int]:
    """Return input chunk, overlap and newly playable frames per live inference."""
    chunk = max(1, sample_rate // 2, int(round(ai_config.live_chunk_seconds * sample_rate)))
    overlap = min(chunk // 2, max(0, int(round(ai_config.live_overlap_seconds * sample_rate))))
    return chunk, overlap, chunk - overlap


def benchmark_live_model(
    model_id: str = "mdx_low_vram_2stem",
    *,
    use_gpu: bool = True,
    use_mock_backend: bool = False,
    simulate_delay_sec: float = 0.0,
    test_duration_sec: float = 4.0,
    ai_config: Optional[AIConfig] = None,
    audio_config: Optional[AudioConfig] = None,
) -> LiveBenchmarkResult:
    """Measure inference time per second of newly playable audio for 2-stem live mode.

    Explicitly warns and blocks if RTF >= 1.0 ("当前模型无法实时运行").
    """
    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        raise ValueError(f"未知模型 ID: {model_id}")
    if spec.stem_mode != "2stem":
        raise ValueError("实验性近实时分轨仅支持 2-stem (人声 + 伴奏) 模型，不支持 4-stem 模型。")

    ai_cfg = ai_config or AIConfig()
    aud_cfg = audio_config or AudioConfig()
    sr = aud_cfg.sample_rate
    chunk_frames, _, hop_frames = live_frame_sizes(ai_cfg, sr)
    # The requested duration sizes the test work, never the production chunk.
    n_chunks = max(1, int(round(test_duration_sec * sr / chunk_frames)))
    playable_duration = n_chunks * hop_frames / sr

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
            raise RuntimeError(reason or "PyTorch/CUDA 或 ONNX Runtime GPU 未就绪，拒绝 GPU 基准测试。")

    t = np.arange(chunk_frames, dtype=np.float32) / float(sr)
    wave_sig = (0.25 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    chunk = np.repeat(wave_sig[:, None], aud_cfg.channels, axis=1)

    backend = build_separation_backend(
        model_id,
        use_gpu=use_gpu,
        segment_seconds=spec.default_segment_sec,
        overlap=ai_cfg.mdx_overlap,
        ai_config=ai_cfg,
        use_mock_backend=use_mock_backend,
        simulate_delay_sec=simulate_delay_sec,
    )

    device_label = "MockCPU" if use_mock_backend else ("GPU-CUDA" if use_gpu else "CPU")
    try:
        backend.load_model()
        t0 = time.monotonic()
        for _ in range(n_chunks):
            _ = backend.separate_chunk(chunk, sr)
        elapsed = max(0.0001, time.monotonic() - t0)
        rtf = elapsed / playable_duration
        can_rt = rtf < 1.0
        if can_rt:
            msg = f"✅ 基准通过: {spec.display_name} ({device_label}) RTF={rtf:.2f} < 1.0 (耗时 {elapsed:.2f}s / 可播放音频 {playable_duration:.2f}s)"
        else:
            msg = (
                f"⚠️ 当前模型无法实时运行: {spec.display_name} RTF={rtf:.2f} >= 1.0 "
                f"(耗时 {elapsed:.2f}s / 可播放音频 {playable_duration:.2f}s)，请改用历史片段离线分轨。"
            )
        return LiveBenchmarkResult(
            model_id=model_id,
            device_used=device_label,
            test_duration_sec=playable_duration,
            elapsed_sec=elapsed,
            rtf=rtf,
            can_run_realtime=can_rt,
            message=msg,
        )
    finally:
        try:
            backend.unload_model()
        except Exception:
            pass
        del backend
        release_torch_and_memory()


def benchmark_live_model_isolated(
    model_id: str = "mdx_low_vram_2stem",
    *,
    ai_python_executable: Optional[str | Path] = None,
    use_gpu: bool = True,
    use_mock_backend: bool = False,
    simulate_delay_sec: float = 0.0,
    test_duration_sec: float = 4.0,
    ai_config: Optional[AIConfig] = None,
    audio_config: Optional[AudioConfig] = None,
    timeout_sec: float = 60.0,
    cancel_event: Optional[threading.Event] = None,
) -> LiveBenchmarkResult:
    """Execute `benchmark_live_model` cleanly in an isolated subprocess (never inside GUI main process)."""
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("实时分轨基准测试已被取消")

    exe = str(ai_python_executable).strip() if ai_python_executable else ""
    if not exe:
        if getattr(sys, "frozen", False) and not use_mock_backend:
            raise RuntimeError(
                "独立 AI 环境 (.venv-ai) 未配置：Windows 打包版主程序不包含 PyTorch/ONNX Runtime，"
                "请在「设置 -> 资源安全阈值 & AI 配置」中指定 .venv-ai\\Scripts\\python.exe。"
            )
        exe = sys.executable

    exe_path = Path(exe)
    if not exe_path.exists():
        raise FileNotFoundError(f"找不到 AI Python 解释器: {exe}")

    bundle_root = get_bundle_root()
    env = prepend_ffmpeg_path_env(os.environ.copy())
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)

    ai_cfg_payload = json.dumps(asdict(ai_config or AIConfig()))
    aud_cfg_payload = json.dumps(asdict(audio_config or AudioConfig()))

    cmd = [
        str(exe_path),
        "-m",
        "streaming.benchmark",
        "--json",
        "--model-id",
        model_id,
        "--simulate-delay-sec",
        str(float(simulate_delay_sec)),
        "--test-duration-sec",
        str(float(test_duration_sec)),
        "--ai-config-json-str",
        ai_cfg_payload,
        "--audio-config-json-str",
        aud_cfg_payload,
    ]
    cmd.append("--use-gpu" if use_gpu else "--no-gpu")
    if use_mock_backend:
        cmd.append("--use-mock-backend")

    proc = popen_external_python(
        cmd,
        cwd=str(bundle_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **subprocess_no_window_kwargs(),
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _drain(pipe, sink: list[str]) -> None:
        if pipe is None:
            return
        try:
            sink.append(pipe.read() or "")
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), name="ListenScope-BenchOut", daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), name="ListenScope-BenchErr", daemon=True)
    t_out.start()
    t_err.start()

    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    canceled = False
    timed_out = False
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            canceled = True
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(0.05)

    if canceled or timed_out:
        try:
            proc.terminate()
            proc.wait(timeout=0.6)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=0.4)
            except Exception:
                pass
        t_out.join(timeout=0.5)
        t_err.join(timeout=0.5)
        if canceled:
            raise InterruptedError("实时分轨基准测试已被紧急停止/取消")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_sec)

    t_out.join(timeout=1.0)
    t_err.join(timeout=1.0)
    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)

    if proc.returncode != 0:
        err_tail = (stderr_text or stdout_text).strip().splitlines()[-5:]
        raise RuntimeError(
            f"RTF 基准子进程失败 (exitcode={proc.returncode}): {' | '.join(err_tail) or '未知错误'}"
        )

    raw_out = stdout_text.strip()
    lines = [ln.strip() for ln in raw_out.splitlines() if ln.strip()]
    candidate = lines[-1] if lines else raw_out
    brace = candidate.find("{")
    if brace > 0:
        candidate = candidate[brace:]
    payload = json.loads(candidate)
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return LiveBenchmarkResult(
        model_id=str(payload["model_id"]),
        device_used=str(payload["device_used"]),
        test_duration_sec=float(payload["test_duration_sec"]),
        elapsed_sec=float(payload["elapsed_sec"]),
        rtf=float(payload["rtf"]),
        can_run_realtime=bool(payload["can_run_realtime"]),
        message=str(payload["message"]),
    )


def _cli_main() -> int:
    ipc_out = sys.stdout
    parser = argparse.ArgumentParser(description="ListenScope Isolated Live 2-Stem RTF Benchmark")
    parser.add_argument("--model-id", type=str, default="mdx_low_vram_2stem")
    parser.add_argument("--use-gpu", dest="use_gpu", action="store_true", default=True)
    parser.add_argument("--no-gpu", dest="use_gpu", action="store_false")
    parser.add_argument("--use-mock-backend", action="store_true")
    parser.add_argument("--simulate-delay-sec", type=float, default=0.0)
    parser.add_argument("--test-duration-sec", type=float, default=4.0)
    parser.add_argument("--ai-config-json-str", type=str, default=None)
    parser.add_argument("--audio-config-json-str", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ai_cfg = AIConfig(**json.loads(args.ai_config_json_str)) if args.ai_config_json_str else AIConfig()
    aud_cfg = AudioConfig(**json.loads(args.audio_config_json_str)) if args.audio_config_json_str else AudioConfig()

    if args.json:
        sys.stdout = sys.stderr
    try:
        res = benchmark_live_model(
            model_id=args.model_id,
            use_gpu=args.use_gpu,
            use_mock_backend=args.use_mock_backend,
            simulate_delay_sec=args.simulate_delay_sec,
            test_duration_sec=args.test_duration_sec,
            ai_config=ai_cfg,
            audio_config=aud_cfg,
        )
        if args.json:
            print(json.dumps(asdict(res)), file=ipc_out, flush=True)
        else:
            print(res.message)
        return 0
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}), file=ipc_out, flush=True)
        else:
            print(f"Benchmark error: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.stdout = ipc_out


if __name__ == "__main__":
    raise SystemExit(_cli_main())
