"""Settings dialog: Phase 0 System Status hardware inspector + ResourceLimits/AIConfig editor."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Optional

from PySide6 import QtCore, QtWidgets

from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.models import SystemHardwareReport
from core.system_probe import probe_external_ai_environment


class SettingsDialog(QtWidgets.QDialog):
    """Shows real SystemHardwareReport (`设置 -> 系统状态`) and configurable guardrails."""

    _probe_finished = QtCore.Signal(object)

    def __init__(
        self,
        hardware_report: SystemHardwareReport,
        resource_limits: ResourceLimits,
        ai_config: AIConfig,
        *,
        ai_python_executable: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ListenScope 设置 -> 系统状态 & 资源安全策略")
        self.resize(780, 600)

        self._report = hardware_report
        self._updated_limits: Optional[ResourceLimits] = None
        self._updated_ai_config: Optional[AIConfig] = None
        self._updated_ai_python: str = ai_python_executable
        self._dialog_closed = False
        self._probe_finished.connect(self._on_ai_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)

        root = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()

        # Tab 1: System Status (Prompt Section 3 explicit requirement)
        status_tab = QtWidgets.QWidget()
        st_layout = QtWidgets.QVBoxLayout(status_tab)

        target = TargetHardwareSpec()
        target_lbl = QtWidgets.QLabel(
            f"目标真机基线规格: Windows 10/11 (Build >= {target.min_windows_build_for_process_loopback}) | "
            f"GPU: {target.gpu_name} | 显存: {target.vram_gb}GB VRAM (非 16GB) | 系统内存: {target.ram_gb}GB RAM"
        )
        target_lbl.setWordWrap(True)
        target_lbl.setStyleSheet("padding: 8px; background: #1C2026; border: 1px solid #2C323C; border-radius: 6px; font-weight: 600;")
        st_layout.addWidget(target_lbl)

        self.status_table = QtWidgets.QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(["检测项", "当前环境实测状态"])
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.setColumnWidth(0, 250)
        self.status_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._populate_status_table(hardware_report)
        st_layout.addWidget(self.status_table, 1)

        if not hardware_report.gpu_ai_ready or not hardware_report.is_windows:
            warn_text = hardware_report.gpu_ai_block_reason or ""
            if not hardware_report.is_windows:
                warn_text = (
                    f"⚠️ 当前在 {hardware_report.os_system} 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。\n"
                    + warn_text
                )
            alert = QtWidgets.QLabel(warn_text.strip())
            alert.setWordWrap(True)
            alert.setStyleSheet("padding: 8px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 6px;")
            st_layout.addWidget(alert)

        tabs.addTab(status_tab, "系统状态")

        # Tab 2: ResourceLimits & AIConfig
        cfg_tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(cfg_tab)

        self.min_ram_spin = QtWidgets.QDoubleSpinBox()
        self.min_ram_spin.setRange(2560, 32768)
        self.min_ram_spin.setSuffix(" MB")
        self.min_ram_spin.setValue(resource_limits.min_ram_before_ai_mb)

        self.pause_ram_spin = QtWidgets.QDoubleSpinBox()
        self.pause_ram_spin.setRange(1536, 16384)
        self.pause_ram_spin.setSuffix(" MB")
        self.pause_ram_spin.setValue(resource_limits.pause_ram_before_ai_mb)

        self.crit_ram_spin = QtWidgets.QDoubleSpinBox()
        self.crit_ram_spin.setRange(512, 8192)
        self.crit_ram_spin.setSuffix(" MB")
        self.crit_ram_spin.setValue(resource_limits.critical_ram_mb)

        self.vram_2s_spin = QtWidgets.QDoubleSpinBox()
        self.vram_2s_spin.setRange(1024, 7800)
        self.vram_2s_spin.setSuffix(" MB")
        self.vram_2s_spin.setValue(resource_limits.min_vram_2stem_mb)

        self.vram_4s_spin = QtWidgets.QDoubleSpinBox()
        self.vram_4s_spin.setRange(2048, 7800)
        self.vram_4s_spin.setSuffix(" MB")
        self.vram_4s_spin.setValue(resource_limits.min_vram_4stem_mb)

        self.crit_vram_spin = QtWidgets.QDoubleSpinBox()
        self.crit_vram_spin.setRange(256, 4096)
        self.crit_vram_spin.setSuffix(" MB")
        self.crit_vram_spin.setValue(resource_limits.critical_vram_free_mb)

        self.chunk_sec_spin = QtWidgets.QDoubleSpinBox()
        self.chunk_sec_spin.setRange(5.0, 45.0)
        self.chunk_sec_spin.setSuffix(" s")
        self.chunk_sec_spin.setValue(ai_config.long_audio_chunk_seconds)

        py_row = QtWidgets.QHBoxLayout()
        self.ai_python_edit = QtWidgets.QLineEdit(ai_python_executable)
        self.ai_python_edit.setPlaceholderText("留空使用当前 Python；建议 Windows 分环境打包时填写 .venv-ai\\Scripts\\python.exe")
        self.browse_ai_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_ai_py_btn.clicked.connect(self._browse_ai_python)
        self.verify_ai_env_btn = QtWidgets.QPushButton("验证 AI 环境")
        self.verify_ai_env_btn.clicked.connect(self._verify_ai_environment)
        py_row.addWidget(self.ai_python_edit, 1)
        py_row.addWidget(self.browse_ai_py_btn)
        py_row.addWidget(self.verify_ai_env_btn)

        self.ai_probe_result_lbl = QtWidgets.QLabel("配置会持久化保存至 ~/.listenscope/settings.json；可点击“验证 AI 环境”检测 CUDA / ONNX / Demucs / Basic Pitch。")
        self.ai_probe_result_lbl.setWordWrap(True)
        self.ai_probe_result_lbl.setStyleSheet("padding: 6px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px; color: #D7DCE2;")

        self.roformer_chk = QtWidgets.QCheckBox("允许实验性 BS-RoFormer 模型 (仅在 RTX 5060 Ti 8GB 实测峰值通过后手动启用)")
        self.roformer_chk.setChecked(ai_config.allow_experimental_roformer)

        form.addRow("AI 启动提示可用 RAM 阈值 (min_ram_before_ai):", self.min_ram_spin)
        form.addRow("拒绝新 AI 分轨 RAM 阈值 (pause_ram_before_ai):", self.pause_ram_spin)
        form.addRow("立即紧急停止 AI RAM 阈值 (critical_ram):", self.crit_ram_spin)
        form.addRow("GPU 2-Stem 最低空闲显存 (min_vram_2stem):", self.vram_2s_spin)
        form.addRow("GPU 4-Stem 最低空闲显存 (min_vram_4stem):", self.vram_4s_spin)
        form.addRow("桌面/QQ音乐保留最低空闲显存 (critical_vram_free):", self.crit_vram_spin)
        form.addRow("长音频流式分块长度 (long_audio_chunk_seconds):", self.chunk_sec_spin)
        form.addRow("独立 AI Worker Python 路径:", py_row)
        form.addRow("AI 环境验证结果:", self.ai_probe_result_lbl)
        form.addRow("高显存模型解锁:", self.roformer_chk)

        tabs.addTab(cfg_tab, "资源安全阈值 & AI 配置")
        root.addWidget(tabs, 1)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._orig_limits = resource_limits
        self._orig_ai_cfg = ai_config

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._dialog_closed = True
        super().closeEvent(event)

    def _browse_ai_python(self) -> None:
        start_dir = str(Path(self.ai_python_edit.text().strip()).parent) if self.ai_python_edit.text().strip() else str(Path.cwd())
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择独立 AI Worker Python 解释器",
            start_dir,
            "Python Executable (python.exe python python3*);;All Files (*)",
        )
        if selected:
            self.ai_python_edit.setText(selected)

    def _verify_ai_environment(self) -> None:
        target_py = self.ai_python_edit.text().strip()
        self.verify_ai_env_btn.setEnabled(False)
        self.ai_probe_result_lbl.setText("⏳ 正在启动子进程检测 AI Python 环境 (CUDA / sm_120 / ONNX / Demucs / Basic Pitch)...")

        def _worker() -> None:
            res = probe_external_ai_environment(target_py)
            if not self._dialog_closed:
                self._probe_finished.emit(res)

        threading.Thread(target=_worker, name="ListenScope-VerifyAIEnv", daemon=True).start()

    @QtCore.Slot(object)
    def _on_ai_probe_finished(self, result: Any) -> None:
        if self._dialog_closed:
            return
        self.verify_ai_env_btn.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            err = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
            self.ai_probe_result_lbl.setText(f"❌ 检测失败: {err}")
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D1D1D; color: #FF9B9B; border: 1px solid #E03E3E; border-radius: 5px;"
            )
            return

        pt = result.get("pytorch") or {}
        ort = result.get("onnxruntime") or {}
        pkgs = result.get("ai_packages") or {}
        gpu_ready = bool(result.get("gpu_ai_ready"))
        block_reason = result.get("gpu_ai_block_reason") or ""
        pkg_summary = ", ".join(
            f"{k}={'OK' if (v or {}).get('installed') else 'MISS'}"
            for k, v in pkgs.items()
        )
        summary = (
            f"Python: {result.get('python_executable')}\n"
            f"PyTorch: {pt.get('version') or 'N/A'} (CUDA={pt.get('cuda_available')}, sm_120={pt.get('supports_sm_120')}) | "
            f"ONNX CUDA: {ort.get('cuda_provider_available')}\n"
            f"AI 包: {pkg_summary}\n"
            f"GPU AI 准入: {'READY' if gpu_ready else f'BLOCKED ({block_reason})'}"
        )
        self.ai_probe_result_lbl.setText(summary)
        if gpu_ready:
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #1B4D3E; color: #7EE2B8; border: 1px solid #2EC27E; border-radius: 5px;"
            )
        else:
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 5px;"
            )

    def _populate_status_table(self, r: SystemHardwareReport) -> None:
        gpu0 = r.gpus[0] if r.gpus else None
        rows = [
            ("操作系统", f"{r.os_system} {r.os_release} ({r.architecture})"),
            ("Windows Build / WASAPI 进程捕获", f"{r.windows_build or 'N/A'} / {'支持' if r.wasapi_process_loopback_supported else '不可用 / 未在 Windows 真机验证'}"),
            ("系统 RAM (总量 / 当前可用)", f"{r.ram_total_mb / 1024.0:.2f} GB ({r.ram_total_mb:.0f} MB) / {r.ram_available_mb:.0f} MB"),
            ("GPU 型号", gpu0.name if gpu0 else "未检测到 NVIDIA GPU"),
            ("VRAM (总量 / 空闲)", f"{gpu0.total_vram_mb:.0f} MB / {gpu0.free_vram_mb:.0f} MB" if gpu0 else "N/A (目标真机为 8GB VRAM)"),
            ("NVIDIA Driver / NVML", f"{r.nvidia_driver_version or '未检测到'} / {'可用' if r.nvml_available else '不可用'}"),
            ("PyTorch", f"{r.pytorch.version} (CUDA build={r.pytorch.cuda_build})" if r.pytorch.installed else "未安装 (Core 环境隔离正常)"),
            ("torch.cuda.is_available() / Compute Cap", f"{'可用' if r.pytorch.cuda_available else '不可用'} / {r.pytorch.compute_capability or 'N/A'}"),
            ("RTX 5060 Ti sm_120 支持 / Kernel 测试", f"{r.pytorch.supports_sm_120} / {r.pytorch.kernel_smoke_test_passed}"),
            ("ONNX Runtime / CUDAExecutionProvider", f"{r.onnxruntime.version or '未安装'} / {'存在' if r.onnxruntime.cuda_provider_available else '不存在'} ({r.onnxruntime.providers})"),
            ("GPU AI 准入状态 (gpu_ai_ready)", f"{'READY' if r.gpu_ai_ready else 'BLOCKED'} {f'({r.gpu_ai_block_reason})' if r.gpu_ai_block_reason else ''}"),
        ]
        self.status_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.status_table.setItem(i, 0, QtWidgets.QTableWidgetItem(k))
            self.status_table.setItem(i, 1, QtWidgets.QTableWidgetItem(v))

    def _on_accept(self) -> None:
        try:
            self._updated_limits = ResourceLimits(
                max_main_process_ram_mb=self._orig_limits.max_main_process_ram_mb,
                warn_main_process_ram_mb=self._orig_limits.warn_main_process_ram_mb,
                min_ram_before_ai_mb=float(self.min_ram_spin.value()),
                pause_ram_before_ai_mb=float(self.pause_ram_spin.value()),
                critical_ram_mb=float(self.crit_ram_spin.value()),
                min_vram_2stem_mb=float(self.vram_2s_spin.value()),
                min_vram_4stem_mb=float(self.vram_4s_spin.value()),
                critical_vram_free_mb=float(self.crit_vram_spin.value()),
                max_concurrent_ai_jobs=1,
                max_loaded_models=1,
                monitor_history_maxlen=self._orig_limits.monitor_history_maxlen,
            )
            self._updated_ai_config = AIConfig(
                default_max_history_ai_seconds=self._orig_ai_cfg.default_max_history_ai_seconds,
                long_audio_chunk_seconds=float(self.chunk_sec_spin.value()),
                long_audio_overlap_seconds=self._orig_ai_cfg.long_audio_overlap_seconds,
                demucs_jobs=1,
                demucs_shifts=1,
                demucs_overlap=self._orig_ai_cfg.demucs_overlap,
                demucs_segment_ladder=self._orig_ai_cfg.demucs_segment_ladder,
                mdx_batch_size=self._orig_ai_cfg.mdx_batch_size,
                mdx_segment_size=self._orig_ai_cfg.mdx_segment_size,
                mdx_overlap=self._orig_ai_cfg.mdx_overlap,
                worker_graceful_cancel_timeout_sec=self._orig_ai_cfg.worker_graceful_cancel_timeout_sec,
                max_oom_retries=self._orig_ai_cfg.max_oom_retries,
                allow_experimental_roformer=bool(self.roformer_chk.isChecked()),
                live_chunk_seconds=self._orig_ai_cfg.live_chunk_seconds,
                live_overlap_seconds=self._orig_ai_cfg.live_overlap_seconds,
                live_max_buffer_seconds=self._orig_ai_cfg.live_max_buffer_seconds,
            )
            self._updated_ai_python = self.ai_python_edit.text().strip()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "参数无效", str(exc))
            return
        self.accept()

    @property
    def updated_limits(self) -> Optional[ResourceLimits]:
        return self._updated_limits

    @property
    def updated_ai_config(self) -> Optional[AIConfig]:
        return self._updated_ai_config

    @property
    def updated_ai_python(self) -> str:
        return self._updated_ai_python
