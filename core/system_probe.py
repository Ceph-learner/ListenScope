"""Phase 0 hardware, OS, CUDA, PyTorch, and ONNX Runtime diagnostic probe."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Optional

import psutil

from .config import AudioConfig, ResourceLimits, TargetHardwareSpec
from .models import (
    GPUInfo,
    OnnxRuntimeProbeInfo,
    PyTorchProbeInfo,
    SystemHardwareReport,
)


def _run_cmd_line(cmd: list[str], timeout: float = 5.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _detect_cpu_model() -> str:
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        _, val = line.split(":", 1)
                        return val.strip()
        except OSError:
            pass
    proc = platform.processor().strip()
    return proc or platform.machine() or "Unknown CPU"


def _detect_windows_build() -> Optional[int]:
    if platform.system() != "Windows":
        return None
    get_winver = getattr(sys, "getwindowsversion", None)
    if callable(get_winver):
        try:
            return int(get_winver().build)
        except Exception:
            return None
    return None


def _probe_gpus_nvml() -> tuple[list[GPUInfo], Optional[str], bool]:
    try:
        import pynvml  # type: ignore[import-untyped]
    except ImportError:
        return [], None, False

    gpus: list[GPUInfo] = []
    driver_version: Optional[str] = None
    initialized = False
    try:
        pynvml.nvmlInit()
        initialized = True
        raw_driver = pynvml.nvmlSystemGetDriverVersion()
        driver_version = raw_driver.decode("utf-8", errors="replace") if isinstance(raw_driver, bytes) else str(raw_driver)
        count = int(pynvml.nvmlDeviceGetCount())
        for idx in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            name = raw_name.decode("utf-8", errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util_pct: Optional[float] = None
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                util_pct = float(util.gpu)
            except Exception:
                util_pct = None
            gpus.append(
                GPUInfo(
                    index=idx,
                    name=name,
                    total_vram_mb=mem.total / (1024.0 * 1024.0),
                    used_vram_mb=mem.used / (1024.0 * 1024.0),
                    free_vram_mb=mem.free / (1024.0 * 1024.0),
                    utilization_pct=util_pct,
                    driver_version=driver_version,
                    source="nvml",
                )
            )
        return gpus, driver_version, True
    except Exception:
        return [], None, False
    finally:
        if initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


def _probe_gpus_nvidia_smi() -> tuple[list[GPUInfo], Optional[str], bool]:
    smi_path = shutil.which("nvidia-smi")
    if not smi_path:
        return [], None, False
    out = _run_cmd_line(
        [
            smi_path,
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if out is None:
        return [], None, True
    gpus: list[GPUInfo] = []
    driver_version: Optional[str] = None
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            idx = int(parts[0])
            name = parts[1]
            total_mb = float(parts[2])
            used_mb = float(parts[3])
            free_mb = float(parts[4])
            util_pct = float(parts[5]) if parts[5] not in ("", "N/A", "[N/A]") else None
            driver = parts[6] if parts[6] not in ("", "N/A") else None
            if driver and driver_version is None:
                driver_version = driver
            gpus.append(
                GPUInfo(
                    index=idx,
                    name=name,
                    total_vram_mb=total_mb,
                    used_vram_mb=used_mb,
                    free_vram_mb=free_mb,
                    utilization_pct=util_pct,
                    driver_version=driver,
                    source="nvidia-smi",
                )
            )
        except ValueError:
            continue
    return gpus, driver_version, True


def _probe_pytorch() -> PyTorchProbeInfo:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError as exc:
        return PyTorchProbeInfo(installed=False, error=f"torch not installed: {exc}")
    except Exception as exc:
        return PyTorchProbeInfo(installed=False, error=f"torch import error: {exc}")

    info = PyTorchProbeInfo(
        installed=True,
        version=str(getattr(torch, "__version__", "unknown")),
        cuda_available=bool(torch.cuda.is_available()),
        cuda_build=getattr(getattr(torch, "version", None), "cuda", None),
    )

    get_arch_list = getattr(torch.cuda, "get_arch_list", None)
    if callable(get_arch_list):
        try:
            info.arch_list = list(get_arch_list())
        except Exception:
            info.arch_list = []

    if not info.cuda_available:
        return info

    try:
        info.device_count = int(torch.cuda.device_count())
        if info.device_count > 0:
            info.device_name = str(torch.cuda.get_device_name(0))
            cap = torch.cuda.get_device_capability(0)
            info.compute_capability = (int(cap[0]), int(cap[1]))
            if info.arch_list:
                info.supports_sm_120 = any(
                    a in ("sm_120", "compute_120", "sm_120a") for a in info.arch_list
                )
            # Small kernel smoke test to detect "no kernel image available" on Blackwell sm_120
            x = torch.ones((4,), dtype=torch.float32, device="cuda")
            val = float((x * 2.0).sum().item())
            del x
            torch.cuda.synchronize()
            info.kernel_smoke_test_passed = abs(val - 8.0) < 1e-5
    except Exception as exc:
        info.kernel_smoke_test_passed = False
        info.error = str(exc)

    return info


def _probe_onnxruntime() -> OnnxRuntimeProbeInfo:
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]
    except ImportError as exc:
        return OnnxRuntimeProbeInfo(installed=False, error=f"onnxruntime not installed: {exc}")
    except Exception as exc:
        return OnnxRuntimeProbeInfo(installed=False, error=f"onnxruntime import error: {exc}")

    try:
        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls()
            except Exception:
                pass
        providers = list(ort.get_available_providers())
    except Exception as exc:
        return OnnxRuntimeProbeInfo(
            installed=True,
            version=str(getattr(ort, "__version__", "unknown")),
            error=f"get_available_providers() failed: {exc}",
        )

    return OnnxRuntimeProbeInfo(
        installed=True,
        version=str(getattr(ort, "__version__", "unknown")),
        providers=providers,
        cuda_provider_available="CUDAExecutionProvider" in providers,
    )


def evaluate_gpu_ai_readiness(
    gpus: list[GPUInfo],
    pytorch: PyTorchProbeInfo,
    ort_info: OnnxRuntimeProbeInfo,
    target: TargetHardwareSpec = TargetHardwareSpec(),
) -> tuple[bool, Optional[str]]:
    """Determine if GPU AI inference is genuinely safe and ready.

    Strictly follows Section 3 & 22:
    - Never silently degrade GPU AI while pretending GPU works.
    - Verify both PyTorch CUDA kernel execution (including sm_120 for RTX 5060 Ti)
      and ONNX Runtime CUDAExecutionProvider presence.
    """
    if not gpus:
        return False, "No NVIDIA GPU detected via NVML/nvidia-smi; GPU AI inference disabled."

    primary_gpu = gpus[0]
    if not pytorch.installed:
        return (
            False,
            "PyTorch is not installed in this environment (expected in Core-only env; "
            "AI Worker requires PyTorch >= 2.7.0 with CUDA >= 12.8 for RTX 5060 Ti sm_120).",
        )

    if not pytorch.cuda_available:
        return (
            False,
            f"NVIDIA GPU '{primary_gpu.name}' detected, but torch.cuda.is_available() is False "
            f"(torch={pytorch.version}, cuda_build={pytorch.cuda_build}). "
            "Install Windows PyTorch CUDA >= 12.8 build before enabling GPU AI.",
        )

    if pytorch.compute_capability == target.gpu_compute_capability:
        if pytorch.supports_sm_120 is False:
            return (
                False,
                f"GPU '{pytorch.device_name or primary_gpu.name}' requires sm_120 (Blackwell), "
                f"but PyTorch arch_list={pytorch.arch_list} lacks sm_120. "
                "Upgrade to PyTorch >= 2.7.0+cu128 (or cu130+).",
            )

    if pytorch.kernel_smoke_test_passed is False:
        return (
            False,
            f"PyTorch CUDA kernel smoke test failed on '{pytorch.device_name or primary_gpu.name}': "
            f"{pytorch.error or 'unknown CUDA kernel error'}. Refuse GPU AI until PyTorch/CUDA build is fixed.",
        )

    if not ort_info.installed:
        return (
            False,
            "onnxruntime-gpu is not installed; 2-stem MDX ONNX models require onnxruntime-gpu with CUDAExecutionProvider.",
        )

    if not ort_info.cuda_provider_available:
        return (
            False,
            f"ONNX Runtime {ort_info.version} is installed, but CUDAExecutionProvider is absent "
            f"(available={ort_info.providers}). Install matching onnxruntime-gpu + CUDA/cuDNN 9.x.",
        )

    return True, None


def probe_system(target: TargetHardwareSpec = TargetHardwareSpec()) -> SystemHardwareReport:
    """Collect real OS, CPU, RAM, GPU/VRAM, PyTorch, and ONNX Runtime status."""
    vm = psutil.virtual_memory()
    os_system = platform.system()
    is_windows = os_system == "Windows"
    win_build = _detect_windows_build()
    wasapi_proc_loopback_ok = bool(
        is_windows and win_build is not None and win_build >= target.min_windows_build_for_process_loopback
    )

    git_ver = _run_cmd_line(["git", "--version"]) if shutil.which("git") else None
    gpus_nvml, driver_nvml, nvml_ok = _probe_gpus_nvml()
    gpus_smi, driver_smi, smi_ok = _probe_gpus_nvidia_smi()

    gpus = gpus_nvml if gpus_nvml else gpus_smi
    driver_version = driver_nvml or driver_smi

    pytorch_info = _probe_pytorch()
    ort_info = _probe_onnxruntime()
    gpu_ready, gpu_block_reason = evaluate_gpu_ai_readiness(gpus, pytorch_info, ort_info, target=target)

    warnings: list[str] = []
    if not is_windows:
        warnings.append(
            f"当前运行环境为 {os_system} ({platform.machine()})，并非目标 Windows PC；"
            "Windows WASAPI Process Loopback 与 RTX 5060 Ti CUDA 推理均未在 Windows 真机验证。"
        )
    elif win_build is not None and win_build < target.min_windows_build_for_process_loopback:
        warnings.append(
            f"Windows build {win_build} < {target.min_windows_build_for_process_loopback} (20H1)；"
            "WASAPI Process Loopback 不可用，将退回系统 WASAPI Loopback。"
        )

    ram_total_mb = vm.total / (1024.0 * 1024.0)
    if gpus:
        # Warn clearly if detected VRAM differs from expected 8GB target
        vram_gb_approx = gpus[0].total_vram_mb / 1024.0
        if vram_gb_approx < 7.5:
            warnings.append(f"检测到主 GPU 显存约 {vram_gb_approx:.1f} GB，低于目标 RTX 5060 Ti 8GB 预算基线。")

    return SystemHardwareReport(
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        os_system=os_system,
        os_release=platform.release(),
        os_version=platform.version(),
        architecture=platform.machine(),
        is_windows=is_windows,
        windows_build=win_build,
        wasapi_process_loopback_supported=wasapi_proc_loopback_ok,
        python_version=platform.python_version(),
        git_version=git_ver,
        cpu_model=_detect_cpu_model(),
        cpu_cores_logical=os.cpu_count() or 1,
        ram_total_mb=ram_total_mb,
        ram_available_mb=vm.available / (1024.0 * 1024.0),
        gpus=gpus,
        nvidia_driver_version=driver_version,
        nvml_available=nvml_ok,
        nvidia_smi_available=smi_ok,
        pytorch=pytorch_info,
        onnxruntime=ort_info,
        gpu_ai_ready=gpu_ready,
        gpu_ai_block_reason=gpu_block_reason,
        warnings=warnings,
    )


def generate_system_report_markdown(
    report: SystemHardwareReport,
    target: TargetHardwareSpec = TargetHardwareSpec(),
    limits: ResourceLimits = ResourceLimits(),
    audio_cfg: AudioConfig = AudioConfig(),
    output_path: Optional[Path] = None,
) -> str:
    """Render a transparent Phase 0 SYSTEM_REPORT.md distinguishing target spec vs actual host."""
    lines: list[str] = [
        "# ListenScope 系统与硬件检测报告 (Phase 0)",
        "",
        f"- **检测时间**: `{report.timestamp_utc}`",
        "",
        "## 1. 目标用户真机硬性规格（不可更改）",
        "",
        "所有内存、显存预算与 AI 分轨保护策略均严格以下列目标硬件为准：",
        "",
        f"- **目标系统**: Windows 10/11 (Build >= {target.min_windows_build_for_process_loopback}, 20H1+ 以支持 WASAPI Process Loopback)",
        f"- **目标 GPU**: `{target.gpu_name}` ({target.gpu_architecture})",
        f"- **GPU 显存**: **{target.vram_gb}GB VRAM**（严禁误写作 16GB VRAM）",
        f"- **系统内存**: **{target.ram_gb}GB RAM**",
        f"- **CUDA / PyTorch 最低兼容要求**: CUDA >= `{target.min_cuda_version}`，PyTorch >= `{target.min_pytorch_version_for_blackwell}` (需包含 `sm_120` 支持)",
        "",
        "## 2. 当前执行环境实测结果",
        "",
    ]

    if not report.is_windows:
        lines.extend(
            [
                "> [!WARNING]",
                f"> **当前环境为 `{report.os_system} {report.os_release} ({report.architecture})`，不是 Windows 真机。**",
                "> **状态：未在 Windows 真机验证。** 下方数据仅反映当前开发/测试沙箱的真实探测结果，绝不伪装为 RTX 5060 Ti Windows 实测结果。",
                "",
            ]
        )

    lines.extend(
        [
            "| 项目 | 当前环境实测值 | 目标真机要求 |",
            "| :--- | :--- | :--- |",
            f"| 操作系统 | `{report.os_system} {report.os_release}` (`{report.architecture}`) | Windows 10/11 20H1+ (`build >= {target.min_windows_build_for_process_loopback}`) |",
            f"| Windows Build | `{report.windows_build if report.windows_build is not None else 'N/A (非 Windows)'}` | `>= {target.min_windows_build_for_process_loopback}` |",
            f"| WASAPI Process Loopback | `{'支持' if report.wasapi_process_loopback_supported else '不可用 / 未在 Windows 真机验证'}` | 需要 Windows 20H1+ |",
            f"| Python 版本 | `{report.python_version}` | `>= 3.11` (建议 3.11/3.12) |",
            f"| Git 版本 | `{report.git_version or '未检测到'}` | 已安装 |",
            f"| CPU | `{report.cpu_model}` ({report.cpu_cores_logical} 逻辑核) | Windows PC CPU (实时分析默认 CPU 运行) |",
            f"| 系统总 RAM | `{report.ram_total_mb:.1f} MB` ({report.ram_total_mb / 1024.0:.2f} GB) | **16GB RAM** |",
            f"| 当前可用 RAM (`psutil.available`) | `{report.ram_available_mb:.1f} MB` ({report.ram_available_mb / 1024.0:.2f} GB) | AI 前建议 >= 5GB，低于 3GB 拒绝启动 |",
            f"| NVML (`pynvml`) | `{'可用' if report.nvml_available else '不可用'}` | 可用 (用于监控 8GB VRAM) |",
            f"| `nvidia-smi` | `{'可用' if report.nvidia_smi_available else '未找到'}` | 可用 |",
            f"| NVIDIA 驱动 | `{report.nvidia_driver_version or '未检测到'}` | 支持 CUDA >= {target.min_cuda_version} |",
        ]
    )

    if report.gpus:
        for gpu in report.gpus:
            lines.extend(
                [
                    f"| GPU #{gpu.index} 型号 | `{gpu.name}` | `{target.gpu_name}` |",
                    f"| GPU #{gpu.index} 总显存 | `{gpu.total_vram_mb:.1f} MB` ({gpu.total_vram_mb / 1024.0:.2f} GB) | **8GB VRAM** |",
                    f"| GPU #{gpu.index} 空闲显存 | `{gpu.free_vram_mb:.1f} MB` | 2-stem >= {limits.min_vram_2stem_mb:.0f} MB / 4-stem >= {limits.min_vram_4stem_mb:.0f} MB |",
                ]
            )
    else:
        lines.append(f"| GPU / VRAM | `未检测到 NVIDIA GPU` | `{target.gpu_name}` (**8GB VRAM**) |")

    lines.extend(
        [
            "",
            "## 3. PyTorch / CUDA / ONNX Runtime 环境核对",
            "",
            f"- **PyTorch 已安装**: `{'是' if report.pytorch.installed else '否'}`"
            + (f" (`{report.pytorch.version}`)" if report.pytorch.version else ""),
            f"- **torch.cuda.is_available()**: `{'可用' if report.pytorch.cuda_available else '不可用'}`",
            f"- **PyTorch CUDA Build**: `{report.pytorch.cuda_build or 'N/A'}`",
            f"- **GPU Compute Capability**: `{report.pytorch.compute_capability or 'N/A'}`",
            f"- **sm_120 (Blackwell) 支持**: `{report.pytorch.supports_sm_120 if report.pytorch.supports_sm_120 is not None else '未验证'}`",
            f"- **CUDA Kernel 冒烟测试**: `{report.pytorch.kernel_smoke_test_passed if report.pytorch.kernel_smoke_test_passed is not None else '未执行'}`",
            f"- **ONNX Runtime 已安装**: `{'是' if report.onnxruntime.installed else '否'}`"
            + (f" (`{report.onnxruntime.version}`)" if report.onnxruntime.version else ""),
            f"- **ONNX Runtime Providers**: `{report.onnxruntime.providers or []}`",
            f"- **CUDAExecutionProvider 是否存在**: `{'是' if report.onnxruntime.cuda_provider_available else '否'}`",
            f"- **GPU AI 推理准入状态 (`gpu_ai_ready`)**: `{'READY' if report.gpu_ai_ready else 'BLOCKED'}`",
        ]
    )

    if report.gpu_ai_block_reason:
        lines.append(f"- **GPU AI 阻断原因（拒绝静默伪装 GPU 正常）**: {report.gpu_ai_block_reason}")

    lines.extend(
        [
            "",
            "## 4. 默认资源安全预算 (`ResourceLimits` & `AudioConfig`)",
            "",
            "| 参数 | 默认安全值 | 说明 |",
            "| :--- | :--- | :--- |",
            f"| 内部统一 PCM 格式 | `{audio_cfg.sample_rate} Hz / {audio_cfg.channels}ch / {audio_cfg.dtype}` | 120s 原始环形缓冲约 `{audio_cfg.ring_buffer_raw_bytes / (1024*1024):.2f} MiB` (`{audio_cfg.ring_buffer_raw_bytes / 1e6:.2f} MB`) |",
            f"| 音频捕获队列上限 | `{audio_cfg.capture_queue_maxsize}` chunks | 有界队列，满时丢弃最旧帧并计数 `overrun` |",
            f"| 主程序 RAM 目标 / 警戒 | `< {limits.max_main_process_ram_mb:.0f} MB` / `{limits.warn_main_process_ram_mb:.0f} MB` | 核心分析全 CPU 轻量运行 |",
            f"| AI 启动前可用 RAM 提示 / 拒绝 / 急停 | `< {limits.min_ram_before_ai_mb:.0f} MB` 提示 / `< {limits.pause_ram_before_ai_mb:.0f} MB` 拒绝 / `< {limits.critical_ram_mb:.0f} MB` 急停 | 以 `psutil.virtual_memory().available` 为准 |",
            f"| GPU 空闲显存阈值 (2-stem / 4-stem) | `>= {limits.min_vram_2stem_mb:.0f} MB` / `>= {limits.min_vram_4stem_mb:.0f} MB` | 保留 >= `{limits.critical_vram_free_mb:.0f} MB` 给桌面、QQ 音乐、浏览器 |",
            f"| 最大并发 AI 任务 / 加载模型数 | `{limits.max_concurrent_ai_jobs}` / `{limits.max_loaded_models}` | 严格串行单模型，独立子进程运行（后期阶段启用） |",
            "",
            "## 5. 告警与未验证项",
            "",
        ]
    )

    if report.warnings:
        for w in report.warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- 无额外告警。")

    lines.extend(
        [
            "",
            "### Windows 真机部署建议（Stage 5+ AI 环境启用前核对）",
            "",
            "1. Core 与 AI Worker 环境隔离：Core 仅安装 `requirements-windows.txt`，不引入 PyTorch。",
            "2. 在 Windows PC 上运行 `python scripts/check_env.py --write-report` 更新本报告为真机实测值。",
            "3. 后续建立 AI Worker 独立虚拟环境时，安装支持 Blackwell `sm_120` 的 PyTorch (`>= 2.7.0`, CUDA `>= 12.8`, 例如 `--index-url https://download.pytorch.org/whl/cu128` 或 `cu130`+) 与匹配的 `onnxruntime-gpu` (`CUDAExecutionProvider` + cuDNN 9.x)。",
        ]
    )

    content = "\n".join(lines) + "\n"
    if output_path is not None:
        output_path.write_text(content, encoding="utf-8")
    return content


def probe_external_ai_environment(
    python_executable: str,
    *,
    timeout_sec: float = 20.0,
) -> dict[str, Any]:
    """Safely inspect an isolated AI worker Python interpreter via subprocess JSON probe."""
    exe = str(python_executable or "").strip()
    if not exe:
        exe = sys.executable
    exe_path = Path(exe)
    if not exe_path.exists():
        return {
            "ok": False,
            "error": f"找不到 Python 可执行文件: {exe}",
            "python_executable": exe,
        }

    bundle_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{bundle_root}{os.pathsep}{existing_pp}" if existing_pp else str(bundle_root)
    cmd = [str(exe_path), "-m", "scripts.check_env", "--json", "--check-ai-packages", "--no-write"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(bundle_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"启动 AI 环境探针失败: {exc}",
            "python_executable": str(exe_path),
        }

    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        return {
            "ok": False,
            "error": f"AI 环境探针返回退出码 {proc.returncode}: {' | '.join(err_tail)}",
            "python_executable": str(exe_path),
        }

    try:
        raw_out = proc.stdout.strip()
        brace_idx = raw_out.find("{")
        if brace_idx > 0:
            raw_out = raw_out[brace_idx:]
        data = json.loads(raw_out)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"解析 AI 环境探针输出失败: {exc}",
            "python_executable": str(exe_path),
        }
    data["ok"] = True
    data["python_executable"] = str(exe_path)
    return data

