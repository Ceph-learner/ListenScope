"""Unified separation backend interface, mock test backend, and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import time
from typing import Optional

import numpy as np
from scipy.signal import butter, sosfilt

from core.config import AIConfig

from .models import AIModelSpec, MODEL_REGISTRY


class SeparationBackend(ABC):
    """Abstract single-model separation backend executed inside AIWorkerProcess."""

    def __init__(
        self,
        model_spec: AIModelSpec,
        *,
        use_gpu: bool = True,
        segment_seconds: Optional[int] = None,
        overlap: float = 0.25,
        ai_config: Optional[AIConfig] = None,
    ) -> None:
        self.model_spec = model_spec
        self.use_gpu = use_gpu
        self.segment_seconds = segment_seconds or model_spec.default_segment_sec
        self.overlap = overlap
        self.ai_config = ai_config or AIConfig()
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load_model(self) -> None:
        ...

    @abstractmethod
    def separate_chunk(self, chunk_f32: np.ndarray, sample_rate: int) -> dict[str, np.ndarray]:
        ...

    @abstractmethod
    def unload_model(self) -> None:
        ...


class MockSeparationBackend(SeparationBackend):
    """Deterministic DSP stem separator used ONLY for unit/leak/OOM/cancel testing.

    Never disguises itself as real MDX/Demucs neural separation.
    """

    def __init__(
        self,
        model_spec: AIModelSpec,
        *,
        use_gpu: bool = False,
        segment_seconds: Optional[int] = None,
        overlap: float = 0.25,
        ai_config: Optional[AIConfig] = None,
        simulate_oom: bool = False,
        simulate_delay_sec: float = 0.0,
    ) -> None:
        super().__init__(
            model_spec,
            use_gpu=use_gpu,
            segment_seconds=segment_seconds,
            overlap=overlap,
            ai_config=ai_config,
        )
        self.simulate_oom = simulate_oom
        self.simulate_delay_sec = simulate_delay_sec
        self._sos_low = None
        self._sos_high = None

    def load_model(self) -> None:
        if self.simulate_delay_sec > 0:
            time.sleep(min(0.5, self.simulate_delay_sec * 0.3))
        if self.simulate_oom:
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.50 GiB (Simulated RTX 5060 Ti OOM)")
        self._loaded = True

    def separate_chunk(self, chunk_f32: np.ndarray, sample_rate: int) -> dict[str, np.ndarray]:
        if not self._loaded:
            raise RuntimeError("Model not loaded")
        if self.simulate_delay_sec > 0:
            time.sleep(self.simulate_delay_sec)

        if self._sos_low is None:
            nyq = sample_rate * 0.5
            self._sos_low = butter(4, min(220.0 / nyq, 0.9), btype="low", output="sos")
            self._sos_high = butter(4, min(2500.0 / nyq, 0.9), btype="high", output="sos")

        # Mid/Side split for clean 2-stem test separation
        mid = 0.5 * (chunk_f32[:, 0] + chunk_f32[:, 1])
        side = 0.5 * (chunk_f32[:, 0] - chunk_f32[:, 1])
        vocals = np.column_stack([mid, mid]).astype(np.float32)
        inst = np.column_stack([side, -side]).astype(np.float32)

        if self.model_spec.stem_mode == "2stem":
            return {"vocals": vocals, "instrumental": inst}

        bass_mono = sosfilt(self._sos_low, mid).astype(np.float32)
        hi_mono = sosfilt(self._sos_high, mid).astype(np.float32)
        bass = np.column_stack([bass_mono, bass_mono])
        drums = np.column_stack([hi_mono, hi_mono])
        other = np.clip(chunk_f32 - vocals * 0.5 - bass * 0.5 - drums * 0.5, -1.0, 1.0).astype(np.float32)
        return {
            "vocals": vocals,
            "drums": drums,
            "bass": bass,
            "other": other,
        }

    def unload_model(self) -> None:
        self._sos_low = None
        self._sos_high = None
        self._loaded = False


def build_separation_backend(
    model_id: str,
    *,
    use_gpu: bool = True,
    segment_seconds: Optional[int] = None,
    overlap: float = 0.25,
    ai_config: Optional[AIConfig] = None,
    use_mock_backend: bool = False,
    simulate_oom: bool = False,
    simulate_delay_sec: float = 0.0,
    output_dir: Optional[Path] = None,
) -> SeparationBackend:
    if model_id not in MODEL_REGISTRY:
        raise ValueError(f"未知模型 ID: {model_id}")
    spec = MODEL_REGISTRY[model_id]
    cfg = ai_config or AIConfig()
    if spec.experimental_only and not cfg.allow_experimental_roformer and not use_mock_backend:
        raise PermissionError(
            f"模型 {model_id} 为高显存实验性 RoFormer，默认禁用；仅在 RTX 5060 Ti 8GB 实测通过后手动开启。"
        )

    if use_mock_backend:
        return MockSeparationBackend(
            spec,
            use_gpu=use_gpu,
            segment_seconds=segment_seconds,
            overlap=overlap,
            ai_config=cfg,
            simulate_oom=simulate_oom,
            simulate_delay_sec=simulate_delay_sec,
        )

    if spec.architecture == "MDX-ONNX":
        from separation.mdx_backend import MDXSeparatorBackend

        return MDXSeparatorBackend(
            spec,
            use_gpu=use_gpu,
            segment_seconds=segment_seconds,
            overlap=overlap,
            ai_config=cfg,
            output_dir=output_dir,
        )
    if spec.architecture == "Demucs":
        from separation.demucs_backend import DemucsSeparatorBackend

        return DemucsSeparatorBackend(
            spec,
            use_gpu=use_gpu,
            segment_seconds=segment_seconds,
            overlap=overlap,
            ai_config=cfg,
            output_dir=output_dir,
        )

    from separation.mdx_backend import MDXSeparatorBackend

    return MDXSeparatorBackend(
        spec,
        use_gpu=use_gpu,
        segment_seconds=segment_seconds,
        overlap=overlap,
        ai_config=cfg,
        output_dir=output_dir,
    )
