"""Real-time RAM, VRAM, queue, AI worker telemetry, and performance log UI widgets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.i18n import translate_text
from core.logging import PerformanceRecord, active_log_dir
from core.models import ResourceSnapshot, ResourceStatus
from core.paths import default_export_dir
from ui.appearance import set_widget_tone
from ui.acid_style import TelemetryHeader, TopbarElideLabel
from ui.help_badge import HelpBadge


def _status_to_tone(status: ResourceStatus) -> str:
    if status == ResourceStatus.NORMAL:
        return "normal"
    if status == ResourceStatus.WARNING:
        return "warn"
    return "error"


class ResourceMonitorBar(QtWidgets.QFrame):
    """Compact top-bar resource health capsule."""

    size_hint_widened = QtCore.Signal(int)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        critical_ram_mb: float = 2048.0,
        critical_vram_free_mb: float = 1024.0,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("resourceCapsule")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cached_texts: dict[str, str] = {}
        self._compact_mode: bool = False
        self._last_snap: Optional[ResourceSnapshot] = None
        self._lang: str = "zh"
        self._last_hint_w: int = 0
        self._critical_ram_mb = float(critical_ram_mb)
        self._critical_vram_free_mb = float(critical_vram_free_mb)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        self.ram_label = TopbarElideLabel("RAM -")
        self.ram_label.setObjectName("monoTelemetry")
        self._sep_lbl = QtWidgets.QLabel("·")
        self._sep_lbl.setObjectName("mutedCaption")
        self._sep_lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        self.vram_label = TopbarElideLabel("VRAM -")
        self.vram_label.setObjectName("monoTelemetry")
        self.status_badge = TopbarElideLabel("Normal")
        self.status_badge.setObjectName("statusBadge")
        set_widget_tone(self.status_badge, "normal")
        for w in (self.ram_label, self.vram_label, self.status_badge):
            w.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)

        layout.addWidget(self.ram_label)
        layout.addWidget(self._sep_lbl)
        layout.addWidget(self.vram_label)
        layout.addSpacing(2)
        layout.addWidget(self.status_badge)
        self.setToolTip("RAM / VRAM")
        self.ram_label.setToolTip("RAM -")
        self.vram_label.setToolTip("VRAM -")
        self.status_badge.setToolTip("Normal")
        self._last_hint_w = self.sizeHint().width()

    def estimate_worst_case_width(self, compact: bool, lang: str) -> int:
        """Estimate worst-case capsule width for `compact` and `lang` using sample long telemetry strings."""
        lay = self.layout()
        lm = lay.contentsMargins() if lay is not None else QtCore.QMargins(6, 2, 6, 2)
        sp = max(0, lay.spacing()) if lay is not None else 4
        cm = self.contentsMargins()
        frame_w = self.frameWidth() * 2
        # Left accent border in QSS is 3px + right border 1px + padding
        outer_w = max(frame_w + cm.left() + cm.right(), 4) + lm.left() + lm.right()

        badge_fm = self.status_badge.fontMetrics()
        badge_chrome = max(18, self.status_badge._horizontal_chrome())
        if compact:
            badge_samples = (
                "Normal",
                "Warn",
                "Crit",
                translate_text("低内存", lang),
            )
            badge_w = max(badge_fm.horizontalAdvance(s) for s in badge_samples) + badge_chrome
            est = outer_w + badge_w + 2
        else:
            ram_name = "内存" if lang == "zh" else "RAM"
            vram_name = "显存" if lang == "zh" else "VRAM"
            ram_fm = self.ram_label.fontMetrics()
            vram_fm = self.vram_label.fontMetrics()
            ram_w = ram_fm.horizontalAdvance(f"{ram_name} 99.9G") + self.ram_label._horizontal_chrome()
            vram_w = vram_fm.horizontalAdvance(f"{vram_name} 99.9/99.9G") + self.vram_label._horizontal_chrome()
            sep_w = self._sep_lbl.sizeHint().width()
            badge_samples = (
                translate_text("Normal", lang),
                translate_text("Warning", lang),
                translate_text("Critical", lang),
                translate_text("内存偏低", lang),
            )
            badge_w = max(badge_fm.horizontalAdvance(s) for s in badge_samples) + badge_chrome
            est = outer_w + ram_w + sep_w + vram_w + badge_w + sp * 3 + 2
        if bool(compact) == self._compact_mode and lang == self._lang:
            est = max(est, self.sizeHint().width())
        return est

    def set_compact_mode(self, compact: bool, *, lang: Optional[str] = None) -> None:
        compact_b = bool(compact)
        if lang is not None:
            self._lang = lang
        if compact_b == self._compact_mode and lang is None:
            return
        self._compact_mode = compact_b
        self.ram_label.setVisible(not compact_b)
        self._sep_lbl.setVisible(not compact_b)
        self.vram_label.setVisible(not compact_b)
        self.setMinimumWidth(0)
        if self._last_snap is not None:
            self.update_snapshot(self._last_snap)
        lay = self.layout()
        if lay is not None:
            lay.activate()
        self.updateGeometry()
        self._last_hint_w = self.sizeHint().width()

    def _set_text_if_changed(self, key: str, lbl: QtWidgets.QLabel, text: str) -> None:
        if self._cached_texts.get(key) != text:
            self._cached_texts[key] = text
            lbl.setText(text)
            lbl.updateGeometry()
            lay = self.layout()
            if lay is not None:
                lay.activate()
            new_hint_w = self.sizeHint().width()
            self.updateGeometry()
            if new_hint_w > self._last_hint_w:
                self._last_hint_w = new_hint_w
                self.size_hint_widened.emit(new_hint_w)
            else:
                self._last_hint_w = new_hint_w
            parent = self.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.layout().activate()

    def update_snapshot(
        self,
        snap: ResourceSnapshot,
        *,
        critical_ram_mb: Optional[float] = None,
        critical_vram_free_mb: Optional[float] = None,
    ) -> None:
        self._last_snap = snap
        ram_name = "内存" if self._lang == "zh" else "RAM"
        vram_name = "显存" if self._lang == "zh" else "VRAM"
        avail_gb = snap.system_ram_available_mb / 1024.0
        ram_txt = f"{ram_name} {avail_gb:.1f}G"
        self._set_text_if_changed("ram", self.ram_label, ram_txt)
        vram_txt = (
            f"{vram_name} {snap.vram_free_mb / 1024.0:.1f}/{snap.vram_total_mb / 1024.0:.1f}G"
            if snap.vram_total_mb is not None and snap.vram_free_mb is not None
            else f"{vram_name} N/A"
        )
        self._set_text_if_changed("vram", self.vram_label, vram_txt)
        detail_tip = (
            f"Main RAM: {snap.main_ram_mb:.0f} MB | AI RAM: {snap.ai_worker_ram_mb:.0f} MB | "
            f"Free RAM: {snap.system_ram_available_mb:.0f} MB"
        )
        if snap.vram_total_mb is not None and snap.vram_free_mb is not None:
            detail_tip += f" | VRAM Free: {snap.vram_free_mb:.0f}/{snap.vram_total_mb:.0f} MB"
        self.setToolTip(detail_tip)
        self.ram_label.setToolTip(detail_tip)
        self.vram_label.setToolTip(detail_tip)

        crit_ram = self._critical_ram_mb if critical_ram_mb is None else float(critical_ram_mb)
        crit_vram = self._critical_vram_free_mb if critical_vram_free_mb is None else float(critical_vram_free_mb)
        ai_idle = snap.ai_worker_ram_mb < 1.0
        vram_critical = snap.vram_free_mb is not None and snap.vram_free_mb < crit_vram
        low_ram_idle = (
            ai_idle
            and snap.status in (ResourceStatus.WARNING, ResourceStatus.CRITICAL)
            and snap.system_ram_available_mb >= crit_ram
            and not vram_critical
        )
        if low_ram_idle:
            raw_lbl = "低内存" if self._compact_mode else "内存偏低"
            self._set_text_if_changed("status", self.status_badge, translate_text(raw_lbl, self._lang))
            set_widget_tone(self.status_badge, "warn")
            tip_raw = (
                f"当前可用内存 {snap.system_ram_available_mb:.0f} MB：实时分析与 A/B 练习正常，"
                "启动新 AI 分轨前建议关闭占用内存的程序，或在设置中调整 pause_ram_before_ai_mb。"
            )
            self.status_badge.setToolTip(translate_text(tip_raw, self._lang))
        else:
            if self._compact_mode:
                short_map = {
                    ResourceStatus.NORMAL: ResourceStatus.NORMAL.value,
                    ResourceStatus.WARNING: "Warn",
                    ResourceStatus.CRITICAL: "Crit",
                }
                badge_txt = short_map.get(snap.status, snap.status.value)
            else:
                badge_txt = translate_text(snap.status.value, self._lang)
            self._set_text_if_changed("status", self.status_badge, badge_txt)
            set_widget_tone(self.status_badge, _status_to_tone(snap.status))
            self.status_badge.setToolTip(f"{snap.status.value} — {detail_tip}")


class ResourceStatusPanel(QtWidgets.QWidget):
    """Full dashboard tab showing detailed RAM/VRAM telemetry, AI perf history, bounded logs, and diagnostic zip export."""

    export_diagnostics_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._cached_texts: dict[str, str] = {}
        self._last_perf_sig: Optional[tuple[int, Optional[str]]] = None
        self._last_log_sig: Optional[tuple[int, str]] = None

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        content = QtWidgets.QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        root = QtWidgets.QVBoxLayout(content)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        hdr = TelemetryHeader("SYSTEM TELEMETRY // 8GB GUARDRAIL", "硬件资源遥测 · 性能日志 · 诊断包")
        hdr.add_right_widget(
            HelpBadge(
                "16GB RAM / 8GB VRAM 资源看门狗说明",
                "• <b>三进程内存隔离</b>：主界面 Core 仅占极低内存；AI 分轨与 Basic Pitch MIDI 均在独立子进程运行，任务结束立即释放全部 PyTorch / TensorFlow 显存与内存。<br/>"
                "• <b>三级内存护栏</b>：系统可用 RAM 低于提示阈值时黄灯告警，低于暂停阈值时拒绝新启动 AI，低于急停阈值时自动终止子进程保护 Windows 桌面与宿主不卡死。<br/>"
                "• <b>RTF (Real-Time Factor)</b>：AI 处理耗时与音频时长之比（RTF &lt; 1.0 代表处理速度比实时播放更快）。",
            )
        )
        root.addWidget(hdr)

        # Telemetry grid card
        grid_group = QtWidgets.QGroupBox("MEMORY + VRAM GRID // 实时资源监控 (主 RAM / AI RAM / RTX 5060 Ti 8GB VRAM)")
        grid_group.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        grid = QtWidgets.QGridLayout(grid_group)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setVerticalSpacing(4)

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
            title_lbl.setObjectName("mutedCaption")
            val_lbl = QtWidgets.QLabel("-")
            if key == "status":
                val_lbl.setObjectName("statusBadge")
                set_widget_tone(val_lbl, "normal")
            else:
                val_lbl.setObjectName("monoTelemetry")
            cell = QtWidgets.QHBoxLayout()
            cell.setContentsMargins(6, 2, 6, 2)
            cell.addWidget(title_lbl)
            cell.addWidget(val_lbl, 1)
            holder = QtWidgets.QWidget()
            holder.setObjectName("telemetryCell")
            holder.setLayout(cell)
            grid.addWidget(holder, r, c)
            self._fields[key] = val_lbl

        self.reasons_label = QtWidgets.QLabel("状态说明: 正常")
        self.reasons_label.setWordWrap(True)
        grid.addWidget(self.reasons_label, 3, 0, 1, 3)
        root.addWidget(grid_group)

        # Performance log table
        perf_group = QtWidgets.QGroupBox("PERFORMANCE LEDGER // 本地 AI 性能记录 (logs/performance/)")
        perf_layout = QtWidgets.QVBoxLayout(perf_group)
        perf_layout.setContentsMargins(6, 4, 6, 4)
        self.perf_table = QtWidgets.QTableWidget(0, 9)
        self.perf_table.setHorizontalHeaderLabels(
            ["时间(UTC)", "模型", "设备", "输入(s)", "分段(s)", "峰值RAM(MB)", "峰值VRAM(MB)", "RTF", "状态"]
        )
        self.perf_table.horizontalHeader().setStretchLastSection(True)
        self.perf_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.perf_table.setMinimumHeight(48)
        self.perf_table.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        perf_layout.addWidget(self.perf_table)
        root.addWidget(perf_group, 2)

        # Bounded diagnostic log viewer + one-click ZIP bundle export
        log_group = QtWidgets.QGroupBox("BOUNDED DIAGNOSTIC LOG // 有界运行日志 (仅保留最近 500 条)")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 4, 6, 4)
        diag_bar = QtWidgets.QHBoxLayout()
        diag_note = QtWidgets.QLabel("日志与性能摘要严格有界；如在 Windows 遇到 CUDA/WASAPI 故障可一键导出脱敏诊断包：")
        diag_note.setObjectName("mutedCaption")
        self.open_logs_btn = QtWidgets.QPushButton("打开日志目录")
        self.open_logs_btn.clicked.connect(self._on_open_logs_clicked)
        self.export_diag_btn = QtWidgets.QPushButton("导出诊断包 (.zip)")
        self.export_diag_btn.clicked.connect(self._on_export_diag_clicked)
        diag_bar.addWidget(diag_note, 1)
        diag_bar.addWidget(self.open_logs_btn)
        diag_bar.addWidget(self.export_diag_btn)
        log_layout.addLayout(diag_bar)

        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setObjectName("diagnosticLogStream")
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(500)
        self.log_text.setMinimumHeight(40)
        self.log_text.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        log_layout.addWidget(self.log_text)
        root.addWidget(log_group, 1)

    def _on_open_logs_clicked(self) -> None:
        log_dir = active_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(log_dir)))

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

    def _set_field_text(self, key: str, lbl: QtWidgets.QLabel, text: str) -> None:
        if self._cached_texts.get(key) != text:
            self._cached_texts[key] = text
            lbl.setText(text)

    def update_snapshot(self, snap: ResourceSnapshot) -> None:
        self._set_field_text("main_ram", self._fields["main_ram"], f"{snap.main_ram_mb:.1f} MB")
        self._set_field_text("worker_ram", self._fields["worker_ram"], f"{snap.ai_worker_ram_mb:.1f} MB")
        self._set_field_text(
            "sys_ram",
            self._fields["sys_ram"],
            f"{snap.system_ram_available_mb:.0f} / {snap.system_ram_total_mb:.0f} MB",
        )
        vram_txt = (
            f"{snap.vram_free_mb:.0f} / {snap.vram_total_mb:.0f} MB"
            if snap.vram_total_mb is not None and snap.vram_free_mb is not None
            else "N/A (未检测到 GPU)"
        )
        self._set_field_text("vram", self._fields["vram"], vram_txt)
        self._set_field_text(
            "gpu_util",
            self._fields["gpu_util"],
            f"{snap.gpu_utilization_pct:.0f}%" if snap.gpu_utilization_pct is not None else "N/A",
        )
        self._set_field_text(
            "ai_model_task",
            self._fields["ai_model_task"],
            f"{snap.current_model or '-'} / {snap.current_task or '-'}",
        )
        self._set_field_text(
            "audio_queue",
            self._fields["audio_queue"],
            f"{snap.audio_queue_size} / {snap.audio_queue_maxsize}",
        )
        self._set_field_text("ai_buffer", self._fields["ai_buffer"], f"{snap.ai_buffer_seconds:.1f} s")

        st_lbl = self._fields["status"]
        self._set_field_text("status", st_lbl, snap.status.value)
        set_widget_tone(st_lbl, _status_to_tone(snap.status))
        reasons_txt = "状态说明: " + ("；".join(snap.status_reasons) if snap.status_reasons else "各项内存与显存指标安全")
        self._set_field_text("reasons", self.reasons_label, reasons_txt)

    def update_performance_records(self, records: list[PerformanceRecord]) -> None:
        recent = list(reversed(records[-30:]))
        sig = (len(recent), recent[0].timestamp_utc if recent else None)
        if sig == self._last_perf_sig:
            return
        self._last_perf_sig = sig
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
        tail = lines[-200:]
        sig = (len(lines), tail[-1] if tail else "")
        if sig == self._last_log_sig:
            return
        self._last_log_sig = sig
        joined = "\n".join(tail)
        if self.log_text.toPlainText() != joined:
            bar = self.log_text.verticalScrollBar()
            at_bottom = bar.value() >= max(0, bar.maximum() - 2)
            prev_val = bar.value()
            self.log_text.setPlainText(joined)
            if at_bottom:
                bar.setValue(bar.maximum())
            else:
                bar.setValue(min(prev_val, bar.maximum()))
