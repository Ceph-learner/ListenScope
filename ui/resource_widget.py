"""Real-time RAM, VRAM, queue, AI worker telemetry, and performance log UI widgets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from core.logging import PerformanceRecord
from core.models import ResourceSnapshot, ResourceStatus
from core.paths import default_export_dir


def _status_badge_style(status: ResourceStatus) -> str:
    if status == ResourceStatus.NORMAL:
        return "background-color: #1B4D3E; color: #7EE2B8; border: 1px solid #2EC27E; border-radius: 4px; padding: 2px 8px; font-weight: 600;"
    if status == ResourceStatus.WARNING:
        return "background-color: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 4px; padding: 2px 8px; font-weight: 600;"
    return "background-color: #5C1A1A; color: #FF9B9B; border: 1px solid #E03E3E; border-radius: 4px; padding: 2px 8px; font-weight: 700;"


class ResourceMonitorBar(QtWidgets.QWidget):
    """Compact top-bar resource health strip."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        self.ram_label = QtWidgets.QLabel("RAM: -")
        self.vram_label = QtWidgets.QLabel("VRAM: -")
        self.status_badge = QtWidgets.QLabel("Normal")
        self.status_badge.setStyleSheet(_status_badge_style(ResourceStatus.NORMAL))

        layout.addWidget(self.ram_label)
        layout.addWidget(self.vram_label)
        layout.addWidget(self.status_badge)

    def update_snapshot(self, snap: ResourceSnapshot) -> None:
        self.ram_label.setText(
            f"主={snap.main_ram_mb:.0f}MB | AI={snap.ai_worker_ram_mb:.0f}MB | 可用={snap.system_ram_available_mb:.0f}MB"
        )
        if snap.vram_total_mb is not None and snap.vram_free_mb is not None:
            self.vram_label.setText(f"VRAM 空闲={snap.vram_free_mb:.0f}/{snap.vram_total_mb:.0f}MB")
        else:
            self.vram_label.setText("VRAM: 未检测到 GPU")
        self.status_badge.setText(snap.status.value)
        self.status_badge.setStyleSheet(_status_badge_style(snap.status))
        self.status_badge.setToolTip("\n".join(snap.status_reasons) if snap.status_reasons else "资源状态正常")


class ResourceStatusPanel(QtWidgets.QWidget):
    """Full dashboard tab showing detailed RAM/VRAM telemetry, AI perf history, bounded logs, and diagnostic zip export."""

    export_diagnostics_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        # Telemetry grid card
        grid_group = QtWidgets.QGroupBox("实时资源监控 (主进程 RAM / AI Worker RAM / 系统 RAM / RTX 5060 Ti 8GB VRAM)")
        grid = QtWidgets.QGridLayout(grid_group)

        self._fields: dict[str, QtWidgets.QLabel] = {}
        specs = [
            ("main_ram", "主进程 RAM:"),
            ("worker_ram", "AI Worker RAM:"),
            ("sys_ram", "系统可用 / 总 RAM:"),
            ("vram", "GPU 空闲 / 总 VRAM:"),
            ("gpu_util", "GPU 利用率:"),
            ("ai_model_task", "当前 AI 模型 / 任务:"),
            ("audio_queue", "音频捕获队列:"),
            ("ai_buffer", "AI 待处理 / 分块缓冲:"),
            ("status", "资源保护状态:"),
        ]
        for idx, (key, title) in enumerate(specs):
            r, c = divmod(idx, 3)
            title_lbl = QtWidgets.QLabel(title)
            title_lbl.setStyleSheet("color: #9AA4B2;")
            val_lbl = QtWidgets.QLabel("-")
            val_lbl.setStyleSheet("font-weight: 600;")
            cell = QtWidgets.QHBoxLayout()
            cell.addWidget(title_lbl)
            cell.addWidget(val_lbl, 1)
            holder = QtWidgets.QWidget()
            holder.setLayout(cell)
            grid.addWidget(holder, r, c)
            self._fields[key] = val_lbl

        self.reasons_label = QtWidgets.QLabel("状态说明: 正常")
        self.reasons_label.setWordWrap(True)
        grid.addWidget(self.reasons_label, 3, 0, 1, 3)
        root.addWidget(grid_group)

        # Performance log table
        perf_group = QtWidgets.QGroupBox("本地 AI 性能记录 (logs/performance/)")
        perf_layout = QtWidgets.QVBoxLayout(perf_group)
        self.perf_table = QtWidgets.QTableWidget(0, 9)
        self.perf_table.setHorizontalHeaderLabels(
            ["时间(UTC)", "模型", "设备", "输入(s)", "分段(s)", "峰值RAM(MB)", "峰值VRAM(MB)", "RTF", "状态"]
        )
        self.perf_table.horizontalHeader().setStretchLastSection(True)
        self.perf_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        perf_layout.addWidget(self.perf_table)
        root.addWidget(perf_group, 2)

        # Bounded diagnostic log viewer + one-click ZIP bundle export
        log_group = QtWidgets.QGroupBox("有界运行日志 (仅保留最近 500 条)")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        diag_bar = QtWidgets.QHBoxLayout()
        diag_note = QtWidgets.QLabel("日志与性能摘要严格有界；如在 Windows 遇到 CUDA/WASAPI 故障可一键导出脱敏诊断包：")
        diag_note.setStyleSheet("color: #9AA4B2;")
        self.export_diag_btn = QtWidgets.QPushButton("导出诊断包 (.zip)")
        self.export_diag_btn.setToolTip("打包 SYSTEM_REPORT、最近 500 条有界日志、性能记录与脱敏 settings.json")
        self.export_diag_btn.clicked.connect(self._on_export_diag_clicked)
        diag_bar.addWidget(diag_note, 1)
        diag_bar.addWidget(self.export_diag_btn)
        log_layout.addLayout(diag_bar)

        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(500)
        log_layout.addWidget(self.log_text)
        root.addWidget(log_group, 1)

    def _on_export_diag_clicked(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出 ListenScope 诊断排障压缩包 (.zip)",
            str(default_export_dir() / f"listenscope_diag_{stamp}.zip"),
            "ZIP Archives (*.zip)",
        )
        if file_path:
            self.export_diagnostics_requested.emit(file_path)

    def update_snapshot(self, snap: ResourceSnapshot) -> None:
        self._fields["main_ram"].setText(f"{snap.main_ram_mb:.1f} MB")
        self._fields["worker_ram"].setText(f"{snap.ai_worker_ram_mb:.1f} MB")
        self._fields["sys_ram"].setText(
            f"{snap.system_ram_available_mb:.0f} / {snap.system_ram_total_mb:.0f} MB"
        )
        if snap.vram_total_mb is not None and snap.vram_free_mb is not None:
            self._fields["vram"].setText(f"{snap.vram_free_mb:.0f} / {snap.vram_total_mb:.0f} MB")
        else:
            self._fields["vram"].setText("N/A (未检测到 GPU)")
        self._fields["gpu_util"].setText(
            f"{snap.gpu_utilization_pct:.0f}%" if snap.gpu_utilization_pct is not None else "N/A"
        )
        model_task = f"{snap.current_model or '-'} / {snap.current_task or '-'}"
        self._fields["ai_model_task"].setText(model_task)
        self._fields["audio_queue"].setText(f"{snap.audio_queue_size} / {snap.audio_queue_maxsize}")
        self._fields["ai_buffer"].setText(f"{snap.ai_buffer_seconds:.1f} s")

        st_lbl = self._fields["status"]
        st_lbl.setText(snap.status.value)
        st_lbl.setStyleSheet(_status_badge_style(snap.status))
        self.reasons_label.setText(
            "状态说明: " + ("；".join(snap.status_reasons) if snap.status_reasons else "各项内存与显存指标安全")
        )

    def update_performance_records(self, records: list[PerformanceRecord]) -> None:
        recent = list(reversed(records[-30:]))
        self.perf_table.setRowCount(len(recent))
        for row, rec in enumerate(recent):
            vals = [
                rec.timestamp_utc,
                rec.model_name,
                rec.device,
                f"{rec.input_duration_sec:.1f}",
                str(rec.segment),
                f"{rec.peak_ram_mb:.1f}",
                f"{rec.peak_vram_mb:.1f}" if rec.peak_vram_mb is not None else "N/A",
                f"{rec.rtf:.2f}" if rec.rtf is not None else "-",
                rec.status,
            ]
            for col, text in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.perf_table.setItem(row, col, item)

    def update_logs(self, lines: list[str]) -> None:
        joined = "\n".join(lines[-200:])
        if self.log_text.toPlainText() != joined:
            self.log_text.setPlainText(joined)
            bar = self.log_text.verticalScrollBar()
            bar.setValue(bar.maximum())
