"""AI separation model catalog with strict priority and 8GB VRAM safety tiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.config import AIConfig


@dataclass(frozen=True)
class AIModelSpec:
    model_id: str
    display_name: str
    architecture: str  # "MDX-ONNX", "Demucs", "RoFormer"
    stem_mode: str     # "2stem" or "4stem"
    stems: tuple[str, ...]
    priority: int      # 1 = highest default priority
    separator_filename: str
    min_vram_mb: float
    default_segment_sec: int
    experimental_only: bool = False
    notes: str = ""


MODEL_REGISTRY: dict[str, AIModelSpec] = {
    "mdx_low_vram_2stem": AIModelSpec(
        model_id="mdx_low_vram_2stem",
        display_name="2-Stem 低显存默认 (MDX-Net ONNX)",
        architecture="MDX-ONNX",
        stem_mode="2stem",
        stems=("vocals", "instrumental"),
        priority=1,
        separator_filename="UVR-MDX-NET-Inst_HQ_3.onnx",
        min_vram_mb=4096.0,
        default_segment_sec=256,
        experimental_only=False,
        notes="第一优先级：轻量 2-stem MDX/ONNX，低显存占用、速度快，不借用 Demucs 4轨混合假两轨。",
    ),
    "htdemucs_4stem": AIModelSpec(
        model_id="htdemucs_4stem",
        display_name="4-Stem 标准分轨 (HTDemucs)",
        architecture="Demucs",
        stem_mode="4stem",
        stems=("vocals", "drums", "bass", "other"),
        priority=2,
        separator_filename="htdemucs.yaml",
        min_vram_mb=5632.0,
        default_segment_sec=10,
        experimental_only=False,
        notes="第二优先级：4-stem 标准方案；强制 jobs=1, shifts=1, segment<=10s, OOM 时自动降 segment。",
    ),
    "mdx_hq_2stem": AIModelSpec(
        model_id="mdx_hq_2stem",
        display_name="2-Stem 高质量人声 (MDX-Net Voc FT)",
        architecture="MDX-ONNX",
        stem_mode="2stem",
        stems=("vocals", "instrumental"),
        priority=3,
        separator_filename="UVR-MDX-NET-Voc_FT.onnx",
        min_vram_mb=4608.0,
        default_segment_sec=256,
        experimental_only=False,
        notes="第三优先级：高质量人声分离，显存需求略高于默认低资源 MDX。",
    ),
    "bs_roformer_experimental": AIModelSpec(
        model_id="bs_roformer_experimental",
        display_name="2-Stem BS-RoFormer [Experimental]",
        architecture="RoFormer",
        stem_mode="2stem",
        stems=("vocals", "instrumental"),
        priority=4,
        separator_filename="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        min_vram_mb=6656.0,
        default_segment_sec=8,
        experimental_only=True,
        notes="第四优先级（默认关闭）：仅在 RTX 5060 Ti 8GB 实测峰值 VRAM/RAM 合格后才建议手动开启。",
    ),
}


def list_models(
    *,
    stem_mode: Optional[str] = None,
    ai_config: Optional[AIConfig] = None,
    include_experimental: Optional[bool] = None,
) -> list[AIModelSpec]:
    cfg = ai_config or AIConfig()
    allow_exp = cfg.allow_experimental_roformer if include_experimental is None else include_experimental
    items = [
        m
        for m in MODEL_REGISTRY.values()
        if (stem_mode is None or m.stem_mode == stem_mode) and (allow_exp or not m.experimental_only)
    ]
    items.sort(key=lambda m: m.priority)
    return items


def get_default_model_for_mode(stem_mode: str) -> AIModelSpec:
    if stem_mode == "4stem":
        return MODEL_REGISTRY["htdemucs_4stem"]
    return MODEL_REGISTRY["mdx_low_vram_2stem"]
