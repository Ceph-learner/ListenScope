"""ListenScope MainWindow: desktop UI uniting capture, real-time DSP, 120s A/B, AI separation, mixer, and Emergency Stop."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ai.models import MODEL_REGISTRY, list_models
from audio.playback import StemMixerEngine
from core.appearance import Appearance
from core.config import AIConfig, ResourceLimits
from core.logging import PerformanceRecord
from core.paths import default_export_dir
from core.models import (
    AIJobProgress,
    AIJobResult,
    AnalysisSnapshot,
    AudioProcessInfo,
    CaptureMode,
    CaptureStats,
    LiveSeparationMetrics,
    MidiTranscriptionResult,
    ResourceSnapshot,
    StemDeepAnalysisReport,
    SystemHardwareReport,
)

from .appearance import AppearanceDialog, appearance_stylesheet, apply_plot_appearance
from .chroma_widget import ChromaAndHarmonyWidget
from .mixer_widget import StemMixerWidget
from .resource_widget import ResourceMonitorBar, ResourceStatusPanel
from .settings_dialog import SettingsDialog
from .spectrum_widget import SpectrumAnalysisWidget


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #14161A;
    color: #E6EAF0;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #2C323C;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #B4BECB;
}
QPushButton {
    background-color: #232830;
    border: 1px solid #38414E;
    border-radius: 5px;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #2E3540;
}
QPushButton:checked {
    background-color: #1F6FEB;
    border-color: #4EA8DE;
}
QPushButton:disabled {
    color: #6B7480;
    background-color: #1B1E24;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 13px;
    height: 13px;
    border: 1px solid #B4BECB;
    border-radius: 3px;
    background: #1A1E24;
}
QCheckBox::indicator:checked {
    border: 1px solid #7EE2B8;
    background: #7EE2B8;
}
QCheckBox::indicator:disabled { border-color: #6B7480; }
QCheckBox::indicator:checked:disabled { background: #6B7480; }
QComboBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTableWidget {
    background-color: #1A1E24;
    border: 1px solid #303742;
    border-radius: 4px;
    padding: 3px 6px;
}
QTabWidget::pane {
    border: 1px solid #2C323C;
}
QTabBar::tab {
    background: #1C2026;
    padding: 7px 14px;
    border: 1px solid #2C323C;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #28303B;
    color: #7EE2B8;
    font-weight: 600;
}
"""


class ExperimentalLiveWidget(QtWidgets.QWidget):
    """Phase 8 Experimental Near-Real-Time 2-Stem tab (default OFF)."""

    benchmark_requested = QtCore.Signal(str)
    start_requested = QtCore.Signal(str)
    stop_requested = QtCore.Signal()
    balance_changed = QtCore.Signal(float, float)

    def __init__(self, ai_config: AIConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_config = ai_config
        self._pending_start = False
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        banner = QtWidgets.QLabel(
            "实验性近实时二轨分离（人声 + 伴奏）。监听前请选择按进程捕获，系统环回会把监听输出再次录入。\n"
            "速度基准用于判断模型能否跟上实时播放。资源告警时自动停止分轨，频谱分析继续运行。"
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "padding: 10px; background: #2A2310; color: #FFD166; border: 1px solid #F5A623; border-radius: 6px;"
        )
        root.addWidget(banner)

        ctrl = QtWidgets.QHBoxLayout()
        self.model_combo = QtWidgets.QComboBox()
        for m in list_models(stem_mode="2stem", ai_config=ai_config, include_experimental=False):
            self.model_combo.addItem(f"{m.display_name} [{m.architecture}]", m.model_id)

        self.bench_btn = QtWidgets.QPushButton("运行 RTF 速度基准测试")
        self.bench_btn.clicked.connect(lambda: self.benchmark_requested.emit(self.selected_model_id()))
        self.toggle_btn = QtWidgets.QPushButton("开启实验性近实时分轨")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self._on_toggle)

        ctrl.addWidget(QtWidgets.QLabel("2-Stem 模型:"))
        ctrl.addWidget(self.model_combo, 1)
        ctrl.addWidget(self.bench_btn)
        ctrl.addWidget(self.toggle_btn)
        root.addLayout(ctrl)

        self.bench_lbl = QtWidgets.QLabel("基准测试结果: 尚未运行")
        self.bench_lbl.setWordWrap(True)
        root.addWidget(self.bench_lbl)

        # Balance sliders
        bal_box = QtWidgets.QGroupBox("实时人声 / 伴奏混音比例")
        bal_form = QtWidgets.QFormLayout(bal_box)
        self.vocals_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vocals_slider.setRange(0, 150)
        self.vocals_slider.setValue(100)
        self.inst_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.inst_slider.setRange(0, 150)
        self.inst_slider.setValue(100)
        self.vocals_slider.valueChanged.connect(self._emit_balance)
        self.inst_slider.valueChanged.connect(self._emit_balance)
        bal_form.addRow("人声 (Vocals):", self.vocals_slider)
        bal_form.addRow("伴奏 (Instrumental):", self.inst_slider)
        root.addWidget(bal_box)

        # Telemetry metrics
        met_box = QtWidgets.QGroupBox("实时分轨监控指标")
        met_grid = QtWidgets.QGridLayout(met_box)
        self.lbl_state = QtWidgets.QLabel("状态: 已关闭 (默认关闭)")
        self.lbl_latency = QtWidgets.QLabel("延迟: 0.0 ms")
        self.lbl_rtf = QtWidgets.QLabel("RTF: 0.000")
        self.lbl_mem = QtWidgets.QLabel("RAM (主/Worker): -")
        self.lbl_vram = QtWidgets.QLabel("空闲 VRAM / GPU%: -")
        self.lbl_buf = QtWidgets.QLabel("输出缓冲: 0.00 s")
        self.lbl_playback_health = QtWidgets.QLabel("输入跳段 0 次 | 输出溢出丢弃 0 帧 | 输出重缓冲 0 次 | 声卡报告欠载 0 次")
        self.lbl_playback_health.setWordWrap(True)
        self.lbl_playback_health.setToolTip("同一次分轨内累计。输出溢出按来不及播放的帧统计，启动预缓冲不计入重缓冲，声卡欠载按驱动报告统计。")
        met_grid.addWidget(self.lbl_state, 0, 0, 1, 2)
        met_grid.addWidget(self.lbl_latency, 1, 0)
        met_grid.addWidget(self.lbl_rtf, 1, 1)
        met_grid.addWidget(self.lbl_mem, 2, 0)
        met_grid.addWidget(self.lbl_vram, 2, 1)
        met_grid.addWidget(self.lbl_buf, 3, 0, 1, 2)
        met_grid.addWidget(self.lbl_playback_health, 4, 0, 1, 2)
        root.addWidget(met_box)
        root.addStretch(1)

    def selected_model_id(self) -> str:
        return str(self.model_combo.currentData() or "mdx_low_vram_2stem")

    def set_pending_start(self, pending: bool) -> None:
        self._pending_start = bool(pending)
        self.toggle_btn.blockSignals(True)
        if pending:
            self.toggle_btn.setEnabled(False)
            self.toggle_btn.setChecked(True)
            self.toggle_btn.setText("基准测试 / 启动中...")
        else:
            self.toggle_btn.setEnabled(True)
        self.toggle_btn.blockSignals(False)

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self.set_pending_start(True)
            self.start_requested.emit(self.selected_model_id())
        else:
            self.set_pending_start(False)
            self.stop_requested.emit()

    def _emit_balance(self) -> None:
        self.balance_changed.emit(self.vocals_slider.value() / 100.0, self.inst_slider.value() / 100.0)

    @QtCore.Slot(str)
    def set_benchmark_text(self, text: str) -> None:
        self.bench_lbl.setText(text)

    def update_metrics(self, m: LiveSeparationMetrics) -> None:
        if m.active:
            self._pending_start = False
        self.toggle_btn.blockSignals(True)
        if self._pending_start and not m.active:
            self.toggle_btn.setEnabled(False)
            self.toggle_btn.setChecked(True)
            self.toggle_btn.setText("基准测试 / 启动中...")
        else:
            self.toggle_btn.setEnabled(True)
            self.toggle_btn.setChecked(m.active)
            self.toggle_btn.setText("停止实验性近实时分轨" if m.active else "开启实验性近实时分轨")
        self.toggle_btn.blockSignals(False)

        self.lbl_state.setText(f"状态: {m.status_message}")
        self.lbl_latency.setText(f"分块估计延迟: {m.latency_ms:.1f} ms")
        self.lbl_rtf.setText(f"实时率 RTF: {m.rtf:.3f} {'(可实时)' if 0 < m.rtf < 1.0 else ''}")
        self.lbl_mem.setText(f"RAM (主={m.main_ram_mb:.1f} MB / Worker={m.worker_ram_mb:.1f} MB)")
        vram_txt = f"{m.vram_free_mb:.0f} MB" if m.vram_free_mb is not None else "N/A"
        util_txt = f"{m.gpu_util_pct:.0f}%" if m.gpu_util_pct is not None else "N/A"
        self.lbl_vram.setText(f"空闲 VRAM={vram_txt} | GPU={util_txt}")
        self.lbl_buf.setText(
            f"输出缓冲: {m.buffer_seconds:.2f} / {m.max_buffer_seconds:.1f} s"
        )
        self.lbl_playback_health.setText(
            f"输入跳段 {m.dropped_chunks} 次 | 输出溢出丢弃 {m.output_overwritten_frames} 帧 | "
            f"输出重缓冲 {m.playback_rebuffers} 次 | 声卡报告欠载 {m.device_underflows} 次"
        )


class ListenScopeMainWindow(QtWidgets.QMainWindow):
    """Primary desktop interface for ListenScope."""

    capture_toggle_requested = QtCore.Signal(bool, object)  # (start_bool, source_descriptor_dict)
    refresh_sources_requested = QtCore.Signal()
    ab_select_recent_requested = QtCore.Signal(float)
    ab_set_range_sec_requested = QtCore.Signal(float, float)
    ab_play_requested = QtCore.Signal()
    ab_stop_requested = QtCore.Signal()
    ab_loop_toggled = QtCore.Signal(bool)
    ab_speed_changed = QtCore.Signal(float)
    ab_export_wav_requested = QtCore.Signal(str)
    ai_separate_requested = QtCore.Signal(str, str, int, bool)  # (stem_mode, model_id, segment, use_gpu)
    emergency_stop_requested = QtCore.Signal()
    settings_applied = QtCore.Signal(object, object, str)
    appearance_applied = QtCore.Signal()
    history_view_changed = QtCore.Signal()
    import_audio_requested = QtCore.Signal(str)
    toggle_playback_requested = QtCore.Signal()
    ab_bookmark_save_requested = QtCore.Signal(str)
    ab_bookmark_select_requested = QtCore.Signal(int)
    ab_bookmark_delete_requested = QtCore.Signal(int)

    def __init__(
        self,
        *,
        hardware_report: SystemHardwareReport,
        resource_limits: ResourceLimits,
        ai_config: AIConfig,
        mixer_engine: StemMixerEngine,
        ai_python_executable: str = "",
        midi_python_executable: str = "",
        parent: QtWidgets.QWidget | None = None,
        appearance: Appearance = Appearance(),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ListenScope — 本地音乐分析 · A/B 循环 · 安全资源防护 AI 分轨")
        self.resize(1360, 870)

        self._hardware_report = hardware_report
        self._resource_limits = resource_limits
        self._ai_config = ai_config
        self._ai_python_executable = ai_python_executable
        self._midi_python_executable = midi_python_executable
        self._last_verified_ai_probe: Optional[dict[str, Any]] = None
        self._closing_handler = None
        self._last_capture_banner: Optional[str] = None
        self._syncing_ab_region = False

        self._play_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Space"), self)
        self._play_shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self._play_shortcut.activated.connect(self.toggle_playback_requested.emit)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. TOP BAR: Source selector + Capture + RAM/VRAM + AI status + Settings + ALWAYS-VISIBLE Emergency Stop
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        top_bar.addWidget(QtWidgets.QLabel("音频源:"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.setMinimumWidth(260)
        self.refresh_btn = QtWidgets.QPushButton("刷新进程")
        self.refresh_btn.clicked.connect(self.refresh_sources_requested.emit)

        self.capture_btn = QtWidgets.QPushButton("开始捕获")
        self.capture_btn.setCheckable(True)
        self.capture_btn.clicked.connect(self._on_capture_clicked)

        self.capture_status_lbl = QtWidgets.QLabel("未捕获")

        self.resource_bar = ResourceMonitorBar()

        self.ai_status_badge = QtWidgets.QLabel("AI: Idle")
        self.ai_status_badge.setStyleSheet("padding: 3px 8px; background: #1C2026; border: 1px solid #303742; border-radius: 4px;")

        self.settings_btn = QtWidgets.QPushButton("设置 / 系统状态")
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        self.emergency_stop_btn = QtWidgets.QPushButton("紧急停止 AI")
        self.emergency_stop_btn.setStyleSheet(
            "QPushButton { background-color: #B81D24; color: #FFFFFF; border: 2px solid #FF6B6B; "
            "font-weight: 700; padding: 6px 14px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #D9262E; }"
        )
        self.emergency_stop_btn.clicked.connect(self.emergency_stop_requested.emit)

        top_bar.addWidget(self.source_combo)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.capture_btn)
        top_bar.addWidget(self.capture_status_lbl)
        top_bar.addStretch(1)
        top_bar.addWidget(self.resource_bar)
        top_bar.addWidget(self.ai_status_badge)
        top_bar.addWidget(self.settings_btn)
        top_bar.addWidget(self.emergency_stop_btn)
        main_layout.addLayout(top_bar)

        # Dismissible warning / notice banner (QQ Music A/B hint, System Loopback warning, GPU block)
        self.notice_banner = QtWidgets.QLabel("")
        self.notice_banner.setWordWrap(True)
        self.notice_banner.setVisible(False)
        self.notice_banner.setStyleSheet(
            "padding: 6px 10px; background: #332400; color: #FFD166; border: 1px solid #F5A623; border-radius: 5px;"
        )
        main_layout.addWidget(self.notice_banner)

        # 2. CENTER TABS
        self.tabs = QtWidgets.QTabWidget()
        self.spectrum_widget = SpectrumAnalysisWidget()
        self.chroma_widget = ChromaAndHarmonyWidget()
        self.mixer_widget = StemMixerWidget(mixer_engine)
        self.resource_panel = ResourceStatusPanel()
        self.live_widget = ExperimentalLiveWidget(ai_config)

        self.tabs.addTab(self.spectrum_widget, "1. 实时频谱 & 波形")
        self.tabs.addTab(self.chroma_widget, "2. Chroma / 和弦 / 调性 / BPM")
        self.tabs.addTab(self.mixer_widget, "3. 分轨混音 & MIDI 扒谱")
        self.tabs.addTab(self.resource_panel, "4. 系统资源 & 性能日志")
        self.tabs.addTab(self.live_widget, "5. 实验功能: 近实时分轨 (默认关闭)")
        main_layout.addWidget(self.tabs, 1)

        # 3. BOTTOM 120s HISTORY TIMELINE + A/B LOOP + AI TRIGGER BAR
        bottom_box = QtWidgets.QGroupBox("最近 120s 播放历史环形缓冲 · A/B 循环与片段 AI 分轨 (仅保留最近 120s / ~46MB)")
        bottom_l = QtWidgets.QVBoxLayout(bottom_box)

        row_a = QtWidgets.QHBoxLayout()
        self.history_coverage_lbl = QtWidgets.QLabel("已缓冲: 0.0 / 120.0 s")
        self.recent_10_btn = QtWidgets.QPushButton("选最近 10s")
        self.recent_30_btn = QtWidgets.QPushButton("选最近 30s")
        self.recent_60_btn = QtWidgets.QPushButton("选最近 60s")
        self.recent_10_btn.clicked.connect(lambda: self._pick_recent(10.0))
        self.recent_30_btn.clicked.connect(lambda: self._pick_recent(30.0))
        self.recent_60_btn.clicked.connect(lambda: self._pick_recent(60.0))

        self.start_ago_spin = QtWidgets.QDoubleSpinBox()
        self.start_ago_spin.setRange(0.5, 120.0)
        self.start_ago_spin.setValue(30.0)
        self.start_ago_spin.setPrefix("倒退 ")
        self.start_ago_spin.setSuffix(" s")

        self.end_ago_spin = QtWidgets.QDoubleSpinBox()
        self.end_ago_spin.setRange(0.0, 119.5)
        self.end_ago_spin.setValue(0.0)
        self.end_ago_spin.setPrefix("至倒退 ")
        self.end_ago_spin.setSuffix(" s")

        self.apply_ab_btn = QtWidgets.QPushButton("设定 A/B 区间")
        self.apply_ab_btn.clicked.connect(self._on_apply_ab_clicked)

        self.ab_a_back_btn = QtWidgets.QPushButton("A-1s")
        self.ab_a_back_btn.setToolTip("将 A 点提前 1 秒（区间起点向左扩展 1s）")
        self.ab_a_back_btn.clicked.connect(lambda: self._nudge_ab("a", -1.0))
        self.ab_a_fwd_btn = QtWidgets.QPushButton("A+1s")
        self.ab_a_fwd_btn.setToolTip("将 A 点延后 1 秒（至少保留 0.5s 片段）")
        self.ab_a_fwd_btn.clicked.connect(lambda: self._nudge_ab("a", +1.0))
        self.ab_b_back_btn = QtWidgets.QPushButton("B-1s")
        self.ab_b_back_btn.setToolTip("将 B 点提前 1 秒（至少保留 0.5s 片段）")
        self.ab_b_back_btn.clicked.connect(lambda: self._nudge_ab("b", -1.0))
        self.ab_b_fwd_btn = QtWidgets.QPushButton("B+1s")
        self.ab_b_fwd_btn.setToolTip("将 B 点延后 1 秒（最晚至 0.0s 最新位置）")
        self.ab_b_fwd_btn.clicked.connect(lambda: self._nudge_ab("b", +1.0))

        row_a_transport = QtWidgets.QHBoxLayout()
        self.ab_play_btn = QtWidgets.QPushButton("A/B 播放")
        self.ab_stop_btn = QtWidgets.QPushButton("停止回放")
        self.ab_loop_chk = QtWidgets.QCheckBox("A/B 循环")
        self.ab_loop_chk.setChecked(True)
        self.ab_loop_chk.setToolTip("关闭后 A/B 片段播完一次自动停在 B 点")
        self.ab_loop_chk.toggled.connect(self.ab_loop_toggled.emit)

        self.ab_speed_combo = QtWidgets.QComboBox()
        self.ab_speed_combo.setToolTip("A/B 历史片段不变调倍速回放 (纯 CPU WSOLA)")
        for lbl, spd in [("0.5x", 0.5), ("0.65x", 0.65), ("0.75x", 0.75), ("0.85x", 0.85), ("1.0x", 1.0), ("1.25x", 1.25)]:
            self.ab_speed_combo.addItem(lbl, spd)
        self.ab_speed_combo.setCurrentIndex(4)
        self.ab_speed_combo.currentIndexChanged.connect(self._on_ab_speed_changed)

        self.ab_export_wav_btn = QtWidgets.QPushButton("导出 A/B 片段 WAV")
        self.ab_export_wav_btn.setToolTip("流式导出当前 A/B 片段 WAV（自动应用当前不变调倍速与随播节拍器）")
        self.import_audio_btn = QtWidgets.QPushButton("导入本地音频(<=120s)")
        self.import_audio_btn.setToolTip("流式读取本地 WAV/FLAC/OGG 的前 <=120s 至历史环形缓冲（禁止全文件一次加载）")
        self.ab_play_btn.clicked.connect(self.ab_play_requested.emit)
        self.ab_stop_btn.clicked.connect(self.ab_stop_requested.emit)
        self.ab_export_wav_btn.clicked.connect(self._on_ab_export_clicked)
        self.import_audio_btn.clicked.connect(self._on_import_audio_clicked)

        row_a.addWidget(self.history_coverage_lbl)
        row_a.addWidget(self.recent_10_btn)
        row_a.addWidget(self.recent_30_btn)
        row_a.addWidget(self.recent_60_btn)
        row_a.addWidget(self.start_ago_spin)
        row_a.addWidget(self.end_ago_spin)
        row_a.addWidget(self.apply_ab_btn)
        row_a.addWidget(self.ab_a_back_btn)
        row_a.addWidget(self.ab_a_fwd_btn)
        row_a.addWidget(self.ab_b_back_btn)
        row_a.addWidget(self.ab_b_fwd_btn)
        row_a.addStretch(1)

        row_a_transport.addWidget(self.ab_play_btn)
        row_a_transport.addWidget(self.ab_stop_btn)
        row_a_transport.addWidget(self.ab_loop_chk)
        row_a_transport.addWidget(self.ab_speed_combo)
        row_a_transport.addWidget(self.ab_export_wav_btn)
        row_a_transport.addWidget(self.import_audio_btn)
        row_a_transport.addStretch(1)
        bottom_l.addLayout(row_a)
        bottom_l.addLayout(row_a_transport)

        # Interactive 120s Waveform Overview + Draggable A/B Selector + Live Playhead
        self.history_overview_plot = pg.PlotWidget()
        self.history_overview_plot.setMinimumHeight(58)
        self.history_overview_plot.setMaximumHeight(72)
        self.history_overview_plot.setBackground("#14161A")
        history_view = self.history_overview_plot.getViewBox()
        history_view.setLimits(xMin=-120.0, xMax=0.0, minXRange=0.25, maxXRange=120.0)
        self.history_overview_plot.setXRange(-120.0, 0.0, padding=0)
        self.history_overview_plot.setYRange(-1.05, 1.05)
        self.history_overview_plot.hideAxis("left")
        self.history_overview_plot.setLabel("bottom", "历史波形 · 滚轮缩放 / 拖动平移", units="s")
        self.history_overview_plot.setMouseEnabled(x=True, y=False)
        self.history_overview_plot.setMenuEnabled(False)
        self.history_overview_plot.hideButtons()
        self.history_overview_plot.setToolTip("0 秒为最新。拖动波形空白处平移，拖动 A/B 线调整选区。")
        self._history_view_timer = QtCore.QTimer(self)
        self._history_view_timer.setSingleShot(True)
        self._history_view_timer.setInterval(60)
        self._history_view_timer.timeout.connect(self.history_view_changed.emit)
        history_view.sigXRangeChanged.connect(lambda *_: self._history_view_timer.start())
        self._hist_max_curve = self.history_overview_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.0))
        self._hist_min_curve = self.history_overview_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.0))
        self.ab_region = pg.LinearRegionItem(
            values=(-30.0, 0.0),
            bounds=(-120.0, 0.0),
            brush=(46, 194, 126, 48),
            pen=pg.mkPen("#2EC27E", width=1.5),
        )
        self.ab_region.setZValue(10)
        self.history_overview_plot.addItem(self.ab_region)
        self._ab_playhead_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#FFD166", width=1.8),
        )
        self._ab_playhead_line.setVisible(False)
        self._ab_playhead_line.setZValue(15)
        self.history_overview_plot.addItem(self._ab_playhead_line)
        self.ab_region.sigRegionChanged.connect(self._on_ab_region_dragged)
        self.ab_region.sigRegionChangeFinished.connect(self._on_ab_region_finished)
        bottom_l.addWidget(self.history_overview_plot)
        history_reset = QtWidgets.QPushButton("120 秒总览")
        history_reset.clicked.connect(lambda: self.history_overview_plot.setXRange(-120, 0, padding=0))
        row_a.addWidget(history_reset)

        bookmark_row = QtWidgets.QHBoxLayout()
        bookmark_row.addWidget(QtWidgets.QLabel("A/B 书签(<=12):"))
        self.bookmark_label_edit = QtWidgets.QLineEdit()
        self.bookmark_label_edit.setPlaceholderText("书签名称 (如 副歌/Solo，可留空)")
        self.bookmark_label_edit.setMaxLength(40)
        self.bookmark_label_edit.setMaximumWidth(210)
        self.bookmark_save_btn = QtWidgets.QPushButton("保存当前 A/B")
        self.bookmark_save_btn.clicked.connect(self._on_bookmark_save_clicked)

        self.bookmark_combo = QtWidgets.QComboBox()
        self.bookmark_combo.setMinimumWidth(260)
        self.bookmark_jump_btn = QtWidgets.QPushButton("跳转此书签")
        self.bookmark_jump_btn.setEnabled(False)
        self.bookmark_jump_btn.clicked.connect(self._on_bookmark_jump_clicked)
        self.bookmark_del_btn = QtWidgets.QPushButton("删除书签")
        self.bookmark_del_btn.setEnabled(False)
        self.bookmark_del_btn.clicked.connect(self._on_bookmark_del_clicked)

        bookmark_row.addWidget(self.bookmark_label_edit)
        bookmark_row.addWidget(self.bookmark_save_btn)
        bookmark_row.addWidget(self.bookmark_combo, 1)
        bookmark_row.addWidget(self.bookmark_jump_btn)
        bookmark_row.addWidget(self.bookmark_del_btn)
        bottom_l.addLayout(bookmark_row)

        row_b = QtWidgets.QHBoxLayout()
        self.ai_2stem_combo = QtWidgets.QComboBox()
        self._refresh_model_combos()
        self.ai_gpu_chk = QtWidgets.QCheckBox("优先 GPU (需通过 RTX 5060 Ti 检查)")
        self.update_hardware_report(hardware_report, auto_sync_gpu_chk=True)

        self.segment_spin = QtWidgets.QSpinBox()
        self.segment_spin.setRange(4, 10)
        self.segment_spin.setValue(max(4, min(10, int(ai_config.demucs_default_segment_sec))))
        self.segment_spin.setPrefix("Demucs seg=")
        self.segment_spin.setSuffix("s")
        self.segment_spin.setToolTip(
            "HTDemucs 4-Stem 模型分段 (RTX 5060 Ti 实测默认 6s)；仅作用于 4-Stem HTDemucs。\n"
            "离线流式分块长度 (long_audio_chunk_seconds，默认 6.0s) 在「设置」单独配置；"
            "MDX 2-Stem 内部 segment_size=256 保持独立。"
        )

        self.sep_2stem_btn = QtWidgets.QPushButton("AI 2-Stem 分轨 (人声/伴奏)")
        self.sep_2stem_btn.clicked.connect(self._on_sep_2stem)
        self.sep_4stem_btn = QtWidgets.QPushButton("AI 4-Stem 分轨 (HTDemucs)")
        self.sep_4stem_btn.clicked.connect(self._on_sep_4stem)

        row_b.addWidget(QtWidgets.QLabel("2-Stem 模型:"))
        row_b.addWidget(self.ai_2stem_combo)
        row_b.addWidget(self.segment_spin)
        row_b.addWidget(self.ai_gpu_chk)
        row_b.addStretch(1)
        row_b.addWidget(self.sep_2stem_btn)
        row_b.addWidget(self.sep_4stem_btn)
        bottom_l.addLayout(row_b)

        main_layout.addWidget(bottom_box)
        self.apply_appearance(appearance)

    def apply_appearance(self, appearance: Appearance) -> None:
        if appearance == getattr(self, "appearance", None):
            return
        self.appearance = appearance
        self.setStyleSheet(appearance_stylesheet(DARK_STYLESHEET, appearance))
        self.mixer_widget.plot_appearance = appearance
        for plot in self.findChildren(pg.PlotWidget):
            apply_plot_appearance(plot, appearance)
        self.chroma_widget.refresh_chroma_note_ticks()

    def open_appearance_dialog(self, parent: QtWidgets.QWidget | None = None) -> None:
        dialog = AppearanceDialog(self.appearance, DARK_STYLESHEET, parent or self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            appearance = dialog.values()
            if appearance != self.appearance:
                self.apply_appearance(appearance)
                self.appearance_applied.emit()

    @property
    def last_verified_ai_probe(self) -> Optional[dict[str, Any]]:
        return self._last_verified_ai_probe

    def set_closing_handler(self, fn) -> None:
        self._closing_handler = fn

    def closeEvent(self, event) -> None:  # type: ignore[override]
        plot_widgets = (
            self.history_overview_plot,
            self.spectrum_widget.wave_plot,
            self.spectrum_widget.fft_plot,
            self.spectrum_widget.log_plot,
            self.spectrum_widget.spec_plot,
            self.chroma_widget.chroma_bar_plot,
            self.chroma_widget.chroma_hist_plot,
            self.mixer_widget.piano_roll_plot,
        )
        for pw in plot_widgets:
            try:
                pw.clear()
            except Exception:
                pass
        if self._closing_handler is not None:
            try:
                self._closing_handler()
            except Exception:
                pass
        super().closeEvent(event)

    def _refresh_model_combos(self) -> None:
        self.ai_2stem_combo.clear()
        for m in list_models(stem_mode="2stem", ai_config=self._ai_config):
            self.ai_2stem_combo.addItem(m.display_name, m.model_id)

    def update_hardware_report(
        self,
        report: SystemHardwareReport,
        *,
        auto_sync_gpu_chk: bool = False,
    ) -> None:
        self._hardware_report = report
        if report.gpu_ai_ready:
            self.ai_gpu_chk.setText("优先 GPU")
            dev_name = report.pytorch.device_name or (report.gpus[0].name if report.gpus else "NVIDIA GPU")
            self.ai_gpu_chk.setToolTip(f"GPU AI 已就绪：{dev_name} (CUDA={report.pytorch.cuda_build}, ONNX CUDA=OK)")
        else:
            self.ai_gpu_chk.setText("优先 GPU（未就绪）")
            reason = report.gpu_ai_block_reason or "未通过 CUDA/ONNX 检查"
            self.ai_gpu_chk.setToolTip(
                f"GPU AI 当前受阻：{reason}\n请在「设置 / 系统状态」中配置并验证独立 AI Worker 环境。"
            )
        if auto_sync_gpu_chk:
            self.ai_gpu_chk.setChecked(bool(report.gpu_ai_ready))

    def _set_ab_region_from_ago(self, start_ago: float, end_ago: float) -> None:
        s_ago = max(0.5, min(120.0, float(start_ago)))
        e_ago = max(0.0, min(s_ago - 0.5, float(end_ago)))
        self._syncing_ab_region = True
        try:
            self.ab_region.setRegion((-s_ago, -e_ago))
        finally:
            self._syncing_ab_region = False

    def _on_ab_region_dragged(self) -> None:
        if self._syncing_ab_region:
            return
        lo, hi = self.ab_region.getRegion()
        start_ago = max(0.5, min(120.0, -float(lo)))
        end_ago = max(0.0, min(start_ago - 0.5, -float(hi)))
        self._syncing_ab_region = True
        try:
            self.start_ago_spin.setValue(round(start_ago, 2))
            self.end_ago_spin.setValue(round(end_ago, 2))
        finally:
            self._syncing_ab_region = False

    def _on_ab_region_finished(self) -> None:
        if self._syncing_ab_region:
            return
        self._on_ab_region_dragged()
        start_ago = float(self.start_ago_spin.value())
        end_ago = float(self.end_ago_spin.value())
        if start_ago - end_ago < 0.5:
            start_ago = min(120.0, end_ago + 0.5)
            end_ago = max(0.0, start_ago - 0.5)
            self._set_ab_region_from_ago(start_ago, end_ago)
        self.ab_set_range_sec_requested.emit(start_ago, end_ago)

    def _on_apply_ab_clicked(self) -> None:
        raw_a = max(0.0, min(120.0, float(self.start_ago_spin.value())))
        raw_b = max(0.0, min(120.0, float(self.end_ago_spin.value())))
        start_ago = max(0.5, max(raw_a, raw_b))
        end_ago = max(0.0, min(start_ago - 0.5, min(raw_a, raw_b)))
        self.start_ago_spin.blockSignals(True)
        self.end_ago_spin.blockSignals(True)
        self.start_ago_spin.setValue(round(start_ago, 2))
        self.end_ago_spin.setValue(round(end_ago, 2))
        self.start_ago_spin.blockSignals(False)
        self.end_ago_spin.blockSignals(False)
        self._set_ab_region_from_ago(start_ago, end_ago)
        self.ab_set_range_sec_requested.emit(start_ago, end_ago)

    def _nudge_ab(self, which: str, delta_song_sec: float) -> None:
        start_ago = max(0.5, min(120.0, float(self.start_ago_spin.value())))
        end_ago = max(0.0, min(start_ago - 0.5, float(self.end_ago_spin.value())))
        if which == "a":
            start_ago = max(end_ago + 0.5, min(120.0, start_ago - float(delta_song_sec)))
        else:
            end_ago = max(0.0, min(start_ago - 0.5, end_ago - float(delta_song_sec)))
        self.start_ago_spin.blockSignals(True)
        self.end_ago_spin.blockSignals(True)
        self.start_ago_spin.setValue(round(start_ago, 2))
        self.end_ago_spin.setValue(round(end_ago, 2))
        self.start_ago_spin.blockSignals(False)
        self.end_ago_spin.blockSignals(False)
        self._set_ab_region_from_ago(start_ago, end_ago)
        self.ab_set_range_sec_requested.emit(start_ago, end_ago)

    def _pick_recent(self, sec: float) -> None:
        self.start_ago_spin.setValue(sec)
        self.end_ago_spin.setValue(0.0)
        self._set_ab_region_from_ago(sec, 0.0)
        self.ab_select_recent_requested.emit(sec)

    @property
    def history_ago_range(self) -> tuple[float, float]:
        start, end = self.history_overview_plot.viewRange()[0]
        return -start, -end

    def update_history_overview(
        self, mins: np.ndarray, maxs: np.ndarray, avail_sec: float, *, end_ago: float = 0,
    ) -> None:
        if avail_sec <= 0.0 or mins.size == 0 or maxs.size == 0:
            self._hist_max_curve.setData([], [])
            self._hist_min_curve.setData([], [])
            return
        x = np.linspace(-end_ago - avail_sec, -end_ago, int(mins.shape[0]), dtype=np.float32)
        self._hist_max_curve.setData(x, np.asarray(maxs, dtype=np.float32))
        self._hist_min_curve.setData(x, np.asarray(mins, dtype=np.float32))

    def _on_ab_speed_changed(self) -> None:
        self.ab_speed_changed.emit(float(self.ab_speed_combo.currentData() or 1.0))

    def update_ab_playhead(self, *, active: bool, ago_sec: float = 0.0) -> None:
        if not active:
            if self._ab_playhead_line.isVisible():
                self._ab_playhead_line.setVisible(False)
            return
        x = max(-120.0, min(0.0, -float(ago_sec)))
        self._ab_playhead_line.setValue(x)
        if not self._ab_playhead_line.isVisible():
            self._ab_playhead_line.setVisible(True)

    def _on_bookmark_save_clicked(self) -> None:
        label = self.bookmark_label_edit.text().strip()
        self.ab_bookmark_save_requested.emit(label)

    def _on_bookmark_jump_clicked(self) -> None:
        bid = self.bookmark_combo.currentData()
        if bid is not None:
            self.ab_bookmark_select_requested.emit(int(bid))

    def _on_bookmark_del_clicked(self) -> None:
        bid = self.bookmark_combo.currentData()
        if bid is not None:
            self.ab_bookmark_delete_requested.emit(int(bid))

    def update_ab_bookmarks(self, items: list[dict[str, Any]]) -> None:
        if self.bookmark_combo.view().isVisible():
            return
        formatted: list[tuple[int, str]] = [
            (
                int(it["bookmark_id"]),
                f"{it['label']} (-{it['start_ago_sec']:.1f}s~-{it['end_ago_sec']:.1f}s, 长{it['duration_sec']:.1f}s)",
            )
            for it in items
        ]
        existing_ids = [
            int(self.bookmark_combo.itemData(i))
            for i in range(self.bookmark_combo.count())
            if self.bookmark_combo.itemData(i) is not None
        ]
        new_ids = [bid for bid, _ in formatted]
        if existing_ids == new_ids:
            for idx, (_bid, txt) in enumerate(formatted):
                if self.bookmark_combo.itemText(idx) != txt:
                    self.bookmark_combo.setItemText(idx, txt)
        else:
            prev_bid = self.bookmark_combo.currentData()
            self.bookmark_combo.blockSignals(True)
            self.bookmark_combo.clear()
            for bid, txt in formatted:
                self.bookmark_combo.addItem(txt, bid)
            if prev_bid is not None:
                idx = self.bookmark_combo.findData(prev_bid)
                if idx >= 0:
                    self.bookmark_combo.setCurrentIndex(idx)
            self.bookmark_combo.blockSignals(False)
        has_items = len(formatted) > 0
        self.bookmark_jump_btn.setEnabled(has_items)
        self.bookmark_del_btn.setEnabled(has_items)

    def _on_sep_2stem(self) -> None:
        model_id = str(self.ai_2stem_combo.currentData() or "mdx_low_vram_2stem")
        spec = MODEL_REGISTRY.get(model_id)
        segment = spec.default_segment_sec if spec is not None else 256
        self.ai_separate_requested.emit("2stem", model_id, segment, self.ai_gpu_chk.isChecked())

    def _on_sep_4stem(self) -> None:
        self.ai_separate_requested.emit("4stem", "htdemucs_4stem", self.segment_spin.value(), self.ai_gpu_chk.isChecked())

    def _on_capture_clicked(self, checked: bool) -> None:
        desc = self.source_combo.currentData() or {"kind": "synthetic", "pattern": "switching"}
        self.capture_toggle_requested.emit(checked, desc)

    def _on_ab_export_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出 A/B 历史片段 WAV",
            str(default_export_dir() / "ab_excerpt.wav"),
            "WAV Audio (*.wav)",
        )
        if file_path:
            self.ab_export_wav_requested.emit(file_path)

    def _on_import_audio_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "流式载入本地音频片段 (最多截取前 120s)",
            "",
            "Audio Files (*.wav *.flac *.ogg *.aiff);;All Files (*)",
        )
        if file_path:
            self.import_audio_requested.emit(file_path)

    def populate_audio_sources(self, processes: list[AudioProcessInfo], *, include_synthetic: bool = True) -> None:
        prev = self.source_combo.currentData()
        self.source_combo.clear()
        for p in processes:
            self.source_combo.addItem(
                f"[进程] {p.name} (PID {p.pid}, RSS {p.rss_mb:.0f}MB)",
                {"kind": "process", "pid": p.pid, "name": p.name},
            )
        self.source_combo.addItem(
            "[兜底] 系统 WASAPI Loopback (会混入其他应用声音)",
            {"kind": "system_loopback"},
        )
        if include_synthetic:
            self.source_combo.addItem(
                "[测试信号] Synthetic Switching (440Hz/静音/659Hz)",
                {"kind": "synthetic", "pattern": "switching"},
            )
        if prev is not None:
            for idx in range(self.source_combo.count()):
                if self.source_combo.itemData(idx) == prev:
                    self.source_combo.setCurrentIndex(idx)
                    break

    def set_capture_active_ui(self, active: bool) -> None:
        self.capture_btn.blockSignals(True)
        self.capture_btn.setChecked(active)
        self.capture_btn.setText("停止捕获" if active else "开始捕获")
        self.capture_btn.blockSignals(False)
        if not active:
            self._last_capture_banner = None
            self.capture_status_lbl.setStyleSheet("")
            self.capture_status_lbl.setText("未捕获")
            self.capture_status_lbl.setToolTip("")

    def show_banner_message(self, text: str) -> None:
        if not text:
            self.notice_banner.setVisible(False)
            self.notice_banner.setText("")
        else:
            self.notice_banner.setText(text)
            self.notice_banner.setVisible(True)

    def update_capture_stats(self, stats: CaptureStats, ring_available_sec: float) -> None:
        if self.capture_btn.isChecked() != stats.is_running:
            self.set_capture_active_ui(stats.is_running)
        silence = "静音" if stats.is_silent else "有信号"
        if stats.mode == CaptureMode.SYSTEM_LOOPBACK:
            style = "padding: 3px 8px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 4px;"
            prefix = "[混入警告] "
        else:
            style = ""
            prefix = ""
        if self.capture_status_lbl.styleSheet() != style:
            self.capture_status_lbl.setStyleSheet(style)
        self.capture_status_lbl.setText(f"{prefix}{silence} · {stats.rms_dbfs:.1f} dBFS" if stats.is_running else "未捕获")
        self.capture_status_lbl.setToolTip(
            f"{prefix}{stats.mode.value} | {stats.process_name} | RMS {stats.rms_dbfs:.1f} dBFS [{silence}] | "
            f"Drop(Over)={stats.buffer_overruns} Under={stats.buffer_underruns}"
        )
        self.history_coverage_lbl.setText(f"已缓冲: {ring_available_sec:.1f} / 120.0 s")

        banner_msg: Optional[str] = None
        if stats.last_error:
            banner_msg = stats.last_error
        elif stats.mode == CaptureMode.SYSTEM_LOOPBACK and stats.warning_message:
            banner_msg = stats.warning_message

        if banner_msg != self._last_capture_banner:
            self._last_capture_banner = banner_msg
            if banner_msg:
                self.show_banner_message(banner_msg)

    def update_resource_snapshot(
        self,
        snap: ResourceSnapshot,
        perf_records: list[PerformanceRecord],
        logs: list[str],
    ) -> None:
        self.resource_bar.update_snapshot(snap)
        self.resource_panel.update_snapshot(snap)
        self.resource_panel.update_performance_records(perf_records)
        self.resource_panel.update_logs(logs)

    def update_analysis_snapshot(
        self,
        snap: AnalysisSnapshot,
        spectrogram: Optional[np.ndarray],
        chroma_history: Optional[np.ndarray],
    ) -> None:
        self.spectrum_widget.update_analysis(snap, spectrogram=spectrogram)
        self.chroma_widget.update_analysis(snap, chroma_history=chroma_history)

    def update_ai_progress(self, prog: AIJobProgress) -> None:
        self.ai_status_badge.setText(f"AI: {prog.state.value} ({int(round(prog.progress * 100))}%)")
        self.mixer_widget.update_ai_progress(prog)

    def handle_ai_result(self, res: AIJobResult) -> None:
        self.ai_status_badge.setText(f"AI: {res.state.value}")
        self.mixer_widget.handle_ai_result(res)

    def update_live_metrics(self, metrics: LiveSeparationMetrics) -> None:
        self.live_widget.update_metrics(metrics)

    def display_midi_result(self, result: MidiTranscriptionResult) -> None:
        self.mixer_widget.display_midi_result(result)

    def display_deep_analysis(self, report: StemDeepAnalysisReport) -> None:
        self.mixer_widget.display_deep_analysis(report)

    def sync_mixer_position(self) -> None:
        self.mixer_widget.sync_playback_position()

    def open_settings_dialog(self, *, focus_midi: bool = False) -> None:
        dlg = SettingsDialog(
            self._hardware_report,
            self._resource_limits,
            self._ai_config,
            ai_python_executable=self._ai_python_executable,
            midi_python_executable=self._midi_python_executable,
            parent=self,
        )
        dlg.appearance_requested.connect(self.open_appearance_dialog)
        if focus_midi:
            dlg._tabs.setCurrentIndex(1)
            dlg.midi_python_edit.setFocus()
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            if dlg.updated_limits is not None and dlg.updated_ai_config is not None:
                self._resource_limits = dlg.updated_limits
                self._ai_config = dlg.updated_ai_config
                self._ai_python_executable = dlg.updated_ai_python
                self._midi_python_executable = dlg.updated_midi_python
                self._last_verified_ai_probe = dlg.verified_ai_probe
                if dlg.verified_ai_probe is not None:
                    self.update_hardware_report(dlg.verified_report, auto_sync_gpu_chk=True)
                self.segment_spin.setValue(max(4, min(10, int(self._ai_config.demucs_default_segment_sec))))
                self._refresh_model_combos()
                self.settings_applied.emit(self._resource_limits, self._ai_config, self._ai_python_executable)
