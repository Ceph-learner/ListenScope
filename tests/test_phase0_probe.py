"""Phase 0 tests: hardware constraints, ResourceLimits, PyTorch sm_120/ORT guards, and report generation."""

from pathlib import Path

import pytest

from core.config import AudioConfig, ResourceLimits, TargetHardwareSpec
from core.models import GPUInfo, OnnxRuntimeProbeInfo, PyTorchProbeInfo
from core.system_probe import (
    evaluate_gpu_ai_readiness,
    generate_system_report_markdown,
    probe_system,
)


def test_target_hardware_spec_never_confuses_vram_with_ram() -> None:
    spec = TargetHardwareSpec()
    assert "5060 Ti" in spec.gpu_name
    assert spec.vram_gb == 8  # MUST NOT be 16GB
    assert spec.ram_gb == 16
    assert spec.gpu_compute_capability == (12, 0)


def test_audio_config_canonical_format_and_120s_buffer_size() -> None:
    cfg = AudioConfig()
    assert cfg.sample_rate == 48000
    assert cfg.channels == 2
    assert cfg.dtype == "float32"
    assert cfg.ring_buffer_seconds == 120
    # 120s * 48000 * 2 * 4 = 46,080,000 bytes (~46.08 MB decimal / ~43.95 MiB)
    assert cfg.ring_buffer_raw_bytes == 46_080_000


def test_resource_limits_validation() -> None:
    with pytest.raises(ValueError):
        ResourceLimits(critical_ram_mb=4096, pause_ram_before_ai_mb=3072)
    with pytest.raises(ValueError):
        ResourceLimits(max_concurrent_ai_jobs=2)
    with pytest.raises(ValueError):
        ResourceLimits(max_loaded_models=2)


def test_gpu_ai_readiness_blocks_missing_sm120_and_missing_ort_cuda() -> None:
    gpu = [
        GPUInfo(
            index=0,
            name="NVIDIA GeForce RTX 5060 Ti",
            total_vram_mb=8192.0,
            used_vram_mb=512.0,
            free_vram_mb=7680.0,
        )
    ]

    # Case 1: PyTorch lacks sm_120
    pt_no_sm120 = PyTorchProbeInfo(
        installed=True,
        version="2.6.0+cu124",
        cuda_available=True,
        cuda_build="12.4",
        device_count=1,
        device_name="NVIDIA GeForce RTX 5060 Ti",
        compute_capability=(12, 0),
        arch_list=["sm_80", "sm_86", "sm_90"],
        supports_sm_120=False,
    )
    ort_ok = OnnxRuntimeProbeInfo(
        installed=True,
        version="1.22.0",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        cuda_provider_available=True,
    )
    ready, reason = evaluate_gpu_ai_readiness(gpu, pt_no_sm120, ort_ok)
    assert ready is False
    assert reason is not None and "sm_120" in reason

    # Case 2: PyTorch OK, but onnxruntime lacks CUDAExecutionProvider
    pt_ok = PyTorchProbeInfo(
        installed=True,
        version="2.8.0+cu128",
        cuda_available=True,
        cuda_build="12.8",
        device_count=1,
        device_name="NVIDIA GeForce RTX 5060 Ti",
        compute_capability=(12, 0),
        arch_list=["sm_80", "sm_90", "sm_120"],
        supports_sm_120=True,
        kernel_smoke_test_passed=True,
    )
    ort_cpu_only = OnnxRuntimeProbeInfo(
        installed=True,
        version="1.22.0",
        providers=["CPUExecutionProvider"],
        cuda_provider_available=False,
    )
    ready, reason = evaluate_gpu_ai_readiness(gpu, pt_ok, ort_cpu_only)
    assert ready is False
    assert reason is not None and "CUDAExecutionProvider" in reason

    # Case 3: Both PyTorch sm_120 and ONNX Runtime CUDAExecutionProvider verified
    ready, reason = evaluate_gpu_ai_readiness(gpu, pt_ok, ort_ok)
    assert ready is True
    assert reason is None


def test_probe_and_markdown_generation(tmp_path: Path) -> None:
    report = probe_system()
    assert report.ram_total_mb > 0
    assert report.ram_available_mb > 0
    out_file = tmp_path / "SYSTEM_REPORT.md"
    md = generate_system_report_markdown(report, output_path=out_file)
    assert out_file.exists()
    assert "RTX 5060 Ti" in md
    assert "8GB VRAM" in md
    assert "16GB RAM" in md
    if not report.is_windows:
        assert "未在 Windows 真机验证" in md
