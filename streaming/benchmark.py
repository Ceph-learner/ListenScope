"""RTF benchmark gate for Phase 8 experimental near-real-time 2-stem separation."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional

import numpy as np

from ai.backend import build_separation_backend
from ai.models import MODEL_REGISTRY
from ai.resource_guard import release_torch_and_memory
from core.config import AIConfig, AudioConfig


@dataclass
class LiveBenchmarkResult:
    model_id: str
    device_used: str
    test_duration_sec: float
    elapsed_sec: float
    rtf: float
    can_run_realtime: bool
    message: str


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
    """Measure Real-Time Factor (RTF = inference_time / audio_duration) for 2-stem live mode.

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
    chunk_sec = min(ai_cfg.live_chunk_seconds, max(1.0, test_duration_sec))
    chunk_frames = int(round(chunk_sec * sr))
    n_chunks = max(1, int(round(test_duration_sec / chunk_sec)))
    actual_dur = (n_chunks * chunk_frames) / float(sr)

    t = np.arange(chunk_frames, dtype=np.float32) / float(sr)
    wave_sig = (0.25 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    chunk = np.column_stack([wave_sig, wave_sig]).astype(np.float32, copy=False)

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
        # Warm-up 1 chunk before timing real steady-state throughput if > 1 chunk
        t0 = time.monotonic()
        for _ in range(n_chunks):
            _ = backend.separate_chunk(chunk, sr)
        elapsed = max(0.0001, time.monotonic() - t0)
        rtf = elapsed / max(0.001, actual_dur)
        can_rt = rtf < 1.0
        if can_rt:
            msg = f"✅ 基准通过: {spec.display_name} ({device_label}) RTF={rtf:.2f} < 1.0 (耗时 {elapsed:.2f}s / 音频 {actual_dur:.1f}s)"
        else:
            msg = (
                f"⚠️ 当前模型无法实时运行: {spec.display_name} RTF={rtf:.2f} >= 1.0 "
                f"(耗时 {elapsed:.2f}s / 音频 {actual_dur:.1f}s)，请改用历史片段离线分轨。"
            )
        return LiveBenchmarkResult(
            model_id=model_id,
            device_used=device_label,
            test_duration_sec=actual_dur,
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
