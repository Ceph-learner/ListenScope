"""Phase 0/1 RAM and VRAM ResourceManager PoC with bounded history and AI admission guards."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
import threading
import time
from typing import Optional

import psutil

from .config import ResourceLimits, TargetHardwareSpec
from .models import ResourceSnapshot, ResourceStatus
from .system_probe import _probe_gpus_nvidia_smi


@dataclass
class SimulationOverrides:
    """Safe test overrides for simulating low RAM/VRAM without exhausting host memory."""

    system_ram_available_mb: Optional[float] = None
    system_ram_total_mb: Optional[float] = None
    main_ram_mb: Optional[float] = None
    ai_worker_ram_mb: Optional[float] = None
    vram_total_mb: Optional[float] = None
    vram_used_mb: Optional[float] = None
    vram_free_mb: Optional[float] = None
    gpu_utilization_pct: Optional[float] = None
    gpu_name: Optional[str] = None


class ResourceManager:
    """Monitors RAM and GPU VRAM using psutil and NVML (with nvidia-smi fallback).

    Enforces:
    - Bounded history (`deque(maxlen=limits.monitor_history_maxlen)`)
    - Single concurrent AI job & single loaded model
    - Conservative 8GB VRAM + 16GB RAM admission thresholds
    """

    def __init__(
        self,
        limits: Optional[ResourceLimits] = None,
        target: Optional[TargetHardwareSpec] = None,
    ) -> None:
        self.limits = limits or ResourceLimits()
        self.target = target or TargetHardwareSpec()
        self._lock = threading.RLock()
        self._process = psutil.Process(os.getpid())
        self._history: deque[ResourceSnapshot] = deque(maxlen=self.limits.monitor_history_maxlen)

        self._active_ai_jobs = 0
        self._loaded_models = 0
        self._current_model: Optional[str] = None
        self._current_task: Optional[str] = None
        self._ai_worker_pid: Optional[int] = None
        self._ai_buffer_seconds: float = 0.0
        self._audio_queue_size: int = 0
        self._audio_queue_maxsize: int = 0

        self._simulation: Optional[SimulationOverrides] = None

        self._pynvml = None
        self._nvml_initialized = False
        self._init_nvml()

    def _init_nvml(self) -> None:
        try:
            import pynvml  # type: ignore[import-untyped]

            pynvml.nvmlInit()
            self._pynvml = pynvml
            self._nvml_initialized = True
        except Exception:
            self._pynvml = None
            self._nvml_initialized = False

    def close(self) -> None:
        with self._lock:
            if self._nvml_initialized and self._pynvml is not None:
                try:
                    self._pynvml.nvmlShutdown()
                except Exception:
                    pass
                self._nvml_initialized = False

    def __enter__(self) -> "ResourceManager":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def set_simulation_overrides(self, overrides: Optional[SimulationOverrides]) -> None:
        with self._lock:
            self._simulation = overrides

    def update_runtime_state(
        self,
        *,
        active_ai_jobs: Optional[int] = None,
        loaded_models: Optional[int] = None,
        current_model: Optional[str] = None,
        current_task: Optional[str] = None,
        ai_worker_pid: Optional[int] = None,
        audio_queue_size: Optional[int] = None,
        audio_queue_maxsize: Optional[int] = None,
        ai_buffer_seconds: Optional[float] = None,
    ) -> None:
        with self._lock:
            if active_ai_jobs is not None:
                self._active_ai_jobs = max(0, active_ai_jobs)
            if loaded_models is not None:
                self._loaded_models = max(0, loaded_models)
            if current_model is not None or active_ai_jobs == 0:
                self._current_model = current_model
            if current_task is not None or active_ai_jobs == 0:
                self._current_task = current_task
            if ai_worker_pid is not None or active_ai_jobs == 0:
                self._ai_worker_pid = ai_worker_pid
            if audio_queue_size is not None:
                self._audio_queue_size = max(0, audio_queue_size)
            if audio_queue_maxsize is not None:
                self._audio_queue_maxsize = max(0, audio_queue_maxsize)
            if ai_buffer_seconds is not None:
                self._ai_buffer_seconds = max(0.0, ai_buffer_seconds)

    def _read_gpu_metrics(self) -> tuple[Optional[str], Optional[float], Optional[float], Optional[float], Optional[float]]:
        if self._nvml_initialized and self._pynvml is not None:
            try:
                count = int(self._pynvml.nvmlDeviceGetCount())
                if count > 0:
                    handle = self._pynvml.nvmlDeviceGetHandleByIndex(0)
                    raw_name = self._pynvml.nvmlDeviceGetName(handle)
                    name = raw_name.decode("utf-8", errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
                    mem = self._pynvml.nvmlDeviceGetMemoryInfo(handle)
                    util_pct: Optional[float] = None
                    try:
                        util = self._pynvml.nvmlDeviceGetUtilizationRates(handle)
                        util_pct = float(util.gpu)
                    except Exception:
                        util_pct = None
                    return (
                        name,
                        mem.total / (1024.0 * 1024.0),
                        mem.used / (1024.0 * 1024.0),
                        mem.free / (1024.0 * 1024.0),
                        util_pct,
                    )
            except Exception:
                pass

        gpus, _, _ = _probe_gpus_nvidia_smi()
        if gpus:
            g = gpus[0]
            return g.name, g.total_vram_mb, g.used_vram_mb, g.free_vram_mb, g.utilization_pct
        return None, None, None, None, None

    def _read_ai_worker_ram_mb(self) -> float:
        if self._ai_worker_pid is None:
            return 0.0
        try:
            proc = psutil.Process(self._ai_worker_pid)
            return proc.memory_info().rss / (1024.0 * 1024.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0

    def sample(self) -> ResourceSnapshot:
        """Take a point-in-time RAM/VRAM sample and append to bounded history."""
        with self._lock:
            vm = psutil.virtual_memory()
            system_total_mb = vm.total / (1024.0 * 1024.0)
            system_avail_mb = vm.available / (1024.0 * 1024.0)
            main_ram_mb = self._process.memory_info().rss / (1024.0 * 1024.0)
            ai_worker_ram_mb = self._read_ai_worker_ram_mb()

            gpu_name, vram_total_mb, vram_used_mb, vram_free_mb, gpu_util = self._read_gpu_metrics()

            simulated = False
            if self._simulation is not None:
                simulated = True
                if self._simulation.system_ram_total_mb is not None:
                    system_total_mb = self._simulation.system_ram_total_mb
                if self._simulation.system_ram_available_mb is not None:
                    system_avail_mb = self._simulation.system_ram_available_mb
                if self._simulation.main_ram_mb is not None:
                    main_ram_mb = self._simulation.main_ram_mb
                if self._simulation.ai_worker_ram_mb is not None:
                    ai_worker_ram_mb = self._simulation.ai_worker_ram_mb
                if self._simulation.gpu_name is not None:
                    gpu_name = self._simulation.gpu_name
                if self._simulation.vram_total_mb is not None:
                    vram_total_mb = self._simulation.vram_total_mb
                if self._simulation.vram_used_mb is not None:
                    vram_used_mb = self._simulation.vram_used_mb
                if self._simulation.vram_free_mb is not None:
                    vram_free_mb = self._simulation.vram_free_mb
                if self._simulation.gpu_utilization_pct is not None:
                    gpu_util = self._simulation.gpu_utilization_pct

            status, reasons = self._evaluate_status(
                main_ram_mb=main_ram_mb,
                system_avail_mb=system_avail_mb,
                vram_free_mb=vram_free_mb,
            )

            snapshot = ResourceSnapshot(
                timestamp=time.time(),
                main_ram_mb=main_ram_mb,
                ai_worker_ram_mb=ai_worker_ram_mb,
                system_ram_total_mb=system_total_mb,
                system_ram_available_mb=system_avail_mb,
                gpu_name=gpu_name,
                vram_total_mb=vram_total_mb,
                vram_used_mb=vram_used_mb,
                vram_free_mb=vram_free_mb,
                gpu_utilization_pct=gpu_util,
                active_ai_jobs=self._active_ai_jobs,
                loaded_models=self._loaded_models,
                current_model=self._current_model,
                current_task=self._current_task,
                audio_queue_size=self._audio_queue_size,
                audio_queue_maxsize=self._audio_queue_maxsize,
                ai_buffer_seconds=self._ai_buffer_seconds,
                status=status,
                status_reasons=reasons,
                simulated=simulated,
            )
            self._history.append(snapshot)
            return snapshot

    def _evaluate_status(
        self,
        *,
        main_ram_mb: float,
        system_avail_mb: float,
        vram_free_mb: Optional[float],
    ) -> tuple[ResourceStatus, list[str]]:
        status = ResourceStatus.NORMAL
        reasons: list[str] = []

        if system_avail_mb < self.limits.critical_ram_mb:
            status = ResourceStatus.CRITICAL
            reasons.append(
                f"系统可用 RAM 极低 ({system_avail_mb:.0f} MB < {self.limits.critical_ram_mb:.0f} MB)，应立即紧急停止 AI 任务"
            )
        elif system_avail_mb < self.limits.pause_ram_before_ai_mb:
            status = ResourceStatus.CRITICAL
            reasons.append(
                f"系统可用 RAM 不足 ({system_avail_mb:.0f} MB < {self.limits.pause_ram_before_ai_mb:.0f} MB)，禁止启动新 AI 分轨"
            )
        elif system_avail_mb < self.limits.min_ram_before_ai_mb:
            if status == ResourceStatus.NORMAL:
                status = ResourceStatus.WARNING
            reasons.append(
                f"系统可用 RAM 偏紧 ({system_avail_mb:.0f} MB < {self.limits.min_ram_before_ai_mb:.0f} MB)"
            )

        if main_ram_mb >= self.limits.warn_main_process_ram_mb:
            if status == ResourceStatus.NORMAL:
                status = ResourceStatus.WARNING
            reasons.append(
                f"主进程 RAM 占用偏高 ({main_ram_mb:.0f} MB >= {self.limits.warn_main_process_ram_mb:.0f} MB)"
            )
        elif main_ram_mb >= self.limits.max_main_process_ram_mb:
            if status == ResourceStatus.NORMAL:
                status = ResourceStatus.WARNING
            reasons.append(
                f"主进程 RAM 超过 1GB 目标 ({main_ram_mb:.0f} MB >= {self.limits.max_main_process_ram_mb:.0f} MB)"
            )

        if vram_free_mb is not None:
            if vram_free_mb < self.limits.critical_vram_free_mb:
                status = ResourceStatus.CRITICAL
                reasons.append(
                    f"GPU 空闲显存低于安全预留 ({vram_free_mb:.0f} MB < {self.limits.critical_vram_free_mb:.0f} MB)"
                )
            elif vram_free_mb < self.limits.min_vram_2stem_mb:
                if status == ResourceStatus.NORMAL:
                    status = ResourceStatus.WARNING
                reasons.append(
                    f"GPU 空闲显存低于 2-stem 建议阈值 ({vram_free_mb:.0f} MB < {self.limits.min_vram_2stem_mb:.0f} MB)"
                )

        return status, reasons

    def should_emergency_stop_ai(self, snapshot: Optional[ResourceSnapshot] = None) -> tuple[bool, str]:
        snap = snapshot or self.sample()
        if snap.system_ram_available_mb < self.limits.critical_ram_mb:
            return True, (
                f"可用 RAM 跌破紧急阈值 ({snap.system_ram_available_mb:.0f} MB < {self.limits.critical_ram_mb:.0f} MB)"
            )
        if snap.vram_free_mb is not None and snap.vram_free_mb < self.limits.critical_vram_free_mb:
            return True, (
                f"空闲 VRAM 跌破桌面保护余量 ({snap.vram_free_mb:.0f} MB < {self.limits.critical_vram_free_mb:.0f} MB)"
            )
        return False, "OK"

    def can_start_ai_job(
        self,
        stem_mode: str = "2stem",
        *,
        require_gpu: bool = True,
        gpu_ai_ready: Optional[bool] = None,
        gpu_block_reason: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Admission gate called before launching any AI separation task."""
        snap = self.sample()

        if snap.active_ai_jobs >= self.limits.max_concurrent_ai_jobs:
            return False, (
                f"已有 {snap.active_ai_jobs} 个 AI 分轨任务运行中（硬限制={self.limits.max_concurrent_ai_jobs}），禁止并行。"
            )

        if snap.loaded_models >= self.limits.max_loaded_models:
            return False, (
                f"当前已有 {snap.loaded_models} 个 AI 模型加载中（硬限制={self.limits.max_loaded_models}）。"
            )

        if snap.system_ram_available_mb < self.limits.pause_ram_before_ai_mb:
            return False, (
                f"系统可用 RAM 不足 ({snap.system_ram_available_mb:.0f} MB < {self.limits.pause_ram_before_ai_mb:.0f} MB)，"
                "默认拒绝启动新的 AI 分轨。"
            )

        if require_gpu:
            if gpu_ai_ready is False:
                return False, gpu_block_reason or "PyTorch/CUDA 或 ONNX Runtime GPU 环境未通过验证，禁止 GPU AI 推理。"

            if snap.vram_free_mb is None:
                return False, "未检测到可用 NVIDIA GPU / NVML 显存信息，禁止默认进入 GPU AI 推理。"

            required_vram = (
                self.limits.min_vram_4stem_mb if stem_mode == "4stem" else self.limits.min_vram_2stem_mb
            )
            if snap.vram_free_mb < required_vram:
                return False, (
                    f"{stem_mode} GPU 模式要求至少 {required_vram:.0f} MB 空闲显存，"
                    f"当前仅剩 {snap.vram_free_mb:.0f} MB（8GB 显存需为桌面和 QQ 音乐保留余量）。"
                )
            if snap.vram_free_mb <= self.limits.critical_vram_free_mb:
                return False, (
                    f"空闲显存接近紧急线 ({snap.vram_free_mb:.0f} MB <= {self.limits.critical_vram_free_mb:.0f} MB)。"
                )

        if snap.system_ram_available_mb < self.limits.min_ram_before_ai_mb:
            return True, (
                f"允许启动但资源偏紧：可用 RAM={snap.system_ram_available_mb:.0f} MB "
                f"(< {self.limits.min_ram_before_ai_mb:.0f} MB 建议值)。"
            )

        return True, "OK"

    @property
    def history(self) -> list[ResourceSnapshot]:
        with self._lock:
            return list(self._history)
