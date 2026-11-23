"""ListenScope MainWindow: desktop UI uniting capture, real-time DSP, 120s A/B, AI separation, mixer, and Emergency Stop."""

from __future__ import annotations

import ctypes
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtSvg
except Exception:  # pragma: no cover
    QtSvg = None  # type: ignore[assignment]

try:
    import shiboken6
except Exception:  # pragma: no cover
    shiboken6 = None  # type: ignore[assignment]


def _is_qt_valid(obj: object) -> bool:
    if obj is None:
        return False
    if shiboken6 is not None:
        try:
            return bool(shiboken6.isValid(obj))
        except Exception:
            return False
    return True

from ai.models import MODEL_REGISTRY, list_models
from audio.playback import StemMixerEngine
from core.appearance import Appearance
from core.config import AIConfig, ResourceLimits
from core.i18n import get_current_language, tr, tr_telemetry, translate_text, translate_widget_tree
from core.logging import PerformanceRecord
from core.models import (
    AIJobProgress,
    AIJobResult,
    AIJobState,
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
from core.paths import default_export_dir, get_bundle_root

from .appearance import (
    AppearanceDialog,
    _blend,
    appearance_stylesheet,
    apply_plot_appearance,
    detect_system_is_dark,
    set_widget_tone,
)
from .chroma_widget import ChromaAndHarmonyWidget
from .help_badge import (
    HelpBadge,
    install_focus_animations,
    install_tooltip_guard,
    set_focus_animations_enabled,
    set_focus_ring_style,
    set_help_language,
    set_help_mode_enabled,
    set_help_theme,
)
from .acid_style import (
    AcidBarcodeFooter,
    AcidTabBar,
    ChamferBadge,
    ElidedLabel,
    FlowLayout,
    HazardStripeBar,
    MarqueeComboBox,
    SignalLockDot,
    TelemetryHeader,
    TelemetryPulseStrip,
    WindowGlyphButton,
    WorkspaceRailHandle,
    acid_stylesheet,
    apply_acid_plot_theme,
    get_acid_palette,
    is_acid_eligible,
    resolve_acid_variant,
)
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
QCheckBox { spacing: 8px; padding: 2px 8px 2px 2px; }
QCheckBox::indicator {
    width: 15px;
    height: 15px;
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


_CACHED_APP_ICON: Optional[QtGui.QIcon] = None


def _load_app_icon() -> QtGui.QIcon:
    """Load the Acid Telemetry emblem as explicit multi-DPI pixmaps + ICO for reliable Windows taskbar & tray icons."""
    global _CACHED_APP_ICON
    if _CACHED_APP_ICON is not None and not _CACHED_APP_ICON.isNull():
        return _CACHED_APP_ICON
    assets_dir = get_bundle_root() / "ui" / "assets"
    if not (assets_dir / "listenscope.svg").exists() and not (assets_dir / "listenscope.ico").exists():
        assets_dir = Path(__file__).resolve().parent / "assets"
    icon = QtGui.QIcon()
    svg_path = assets_dir / "listenscope.svg"
    ico_path = assets_dir / "listenscope.ico"
    if svg_path.exists() and QtSvg is not None:
        try:
            renderer = QtSvg.QSvgRenderer(str(svg_path))
            if renderer.isValid():
                for px in (16, 20, 24, 32, 48, 64, 128, 256):
                    pm = QtGui.QPixmap(px, px)
                    pm.fill(QtCore.Qt.GlobalColor.transparent)
                    painter = QtGui.QPainter(pm)
                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                    renderer.render(painter, QtCore.QRectF(0, 0, px, px))
                    painter.end()
                    if not pm.isNull():
                        icon.addPixmap(pm)
        except Exception:
            pass
    if ico_path.exists():
        icon.addFile(str(ico_path))
    if svg_path.exists() and icon.isNull():
        icon.addFile(str(svg_path))
    _CACHED_APP_ICON = icon
    return icon


def _set_label_cached(label: QtWidgets.QLabel, text: str) -> None:
    label.setProperty("_ls_orig_text", text)
    rendered = translate_text(text, get_current_language()) if text else text
    if label.text() != rendered:
        label.setText(rendered)


def _infer_banner_tone(text: str) -> str:
    if text.startswith("❌") or text.startswith("[ERR]") or "失败" in text or "错误" in text:
        return "error"
    if (
        text.startswith("⚠️")
        or text.startswith("[WARN]")
        or "紧急停止" in text
        or "系统环回" in text
        or "阻塞" in text
    ):
        return "warn"
    if text.startswith("✅") or text.startswith("[OK]"):
        return "ok"
    return "info"


class _MainShellFrame(QtWidgets.QFrame):
    """Outer shell frame supporting rounded frameless clipping and optional custom background wallpaper (non-Acid only)."""

    def __init__(self, main_win: "ListenScopeMainWindow", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._main_win = main_win
        self.setObjectName("mainShellFrame")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._wallpaper_path: str = ""
        self._wallpaper_pix: Optional[QtGui.QPixmap] = None

    def set_wallpaper_path(self, path: str) -> None:
        norm = str(path or "").strip()
        if norm == self._wallpaper_path:
            return
        self._wallpaper_path = norm
        self._wallpaper_pix = None
        if norm and Path(norm).is_file():
            pix = QtGui.QPixmap(norm)
            if not pix.isNull():
                self._wallpaper_pix = pix
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if self._wallpaper_pix is not None and not self._wallpaper_pix.isNull():
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            rect = QtCore.QRectF(self.rect())
            is_frameless_rounded = bool(self.property("frameless")) and not self._main_win.isMaximized()
            if is_frameless_rounded:
                clip = QtGui.QPainterPath()
                clip.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10.0, 10.0)
                painter.setClipPath(clip)
            scaled = self._wallpaper_pix.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            sx = max(0, (scaled.width() - self.width()) // 2)
            sy = max(0, (scaled.height() - self.height()) // 2)
            painter.drawPixmap(0, 0, scaled, sx, sy, self.width(), self.height())
            appearance = getattr(self._main_win, "appearance", Appearance())
            bg_hex, _, _ = appearance.effective_colors(system_is_dark=self._main_win._system_is_dark)
            scrim = QtGui.QColor(bg_hex)
            scrim.setAlpha(182)
            painter.fillRect(self.rect(), scrim)
            painter.end()
        super().paintEvent(event)


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
        root.setSpacing(6)
        hdr_row = QtWidgets.QHBoxLayout()
        hdr_row.addWidget(TelemetryHeader("LIVE ENGINE // 2-STEM STREAMING", "实验性近实时人声 / 伴奏分离"), 1)
        hdr_row.addWidget(
            HelpBadge(
                "实验性近实时二轨分离说明",
                "• 原理：按滑动窗口将实时捕获的音频送入轻量 MDX 2-Stem 模型分离为人声与伴奏，实时混音输出。\n"
                "• 为什么必须选「按进程捕获」？若使用系统环回 (System Loopback)，软件自己播放出的分离声音会被再次录回造成回授啸叫。\n"
                "• RTF 速度基准：RTF < 1.0 表示显卡推理速度比音频实时播放更快，可流畅开启近实时分轨。",
            )
        )
        root.addLayout(hdr_row)

        banner = QtWidgets.QLabel(
            "实验性近实时二轨分离（人声 + 伴奏）。监听前请选择按进程捕获，系统环回会把监听输出再次录入。\n"
            "速度基准用于判断模型能否跟上实时播放。资源告警时自动停止分轨，频谱分析继续运行。"
        )
        banner.setWordWrap(True)
        banner.setObjectName("bannerNotice")
        set_widget_tone(banner, "warn")
        root.addWidget(banner)

        ctrl = QtWidgets.QHBoxLayout()
        self.model_combo = MarqueeComboBox()
        self.model_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for m in list_models(stem_mode="2stem", ai_config=ai_config, include_experimental=False):
            self.model_combo.addItem(f"{m.display_name} [{m.architecture}]", m.model_id)

        self.bench_btn = QtWidgets.QPushButton("运行 RTF 速度基准测试")
        self.bench_btn.clicked.connect(lambda: self.benchmark_requested.emit(self.selected_model_id()))
        self.toggle_btn = QtWidgets.QPushButton("开启实验性近实时分轨")
        self.toggle_btn.setObjectName("acidPrimaryBtn")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self._on_toggle)

        ctrl.addWidget(QtWidgets.QLabel("2-Stem 模型:"))
        ctrl.addWidget(self.model_combo, 1)
        ctrl.addWidget(self.bench_btn)
        ctrl.addWidget(self.toggle_btn)
        root.addLayout(ctrl)

        self.bench_lbl = QtWidgets.QLabel("基准测试结果: 尚未运行")
        self.bench_lbl.setObjectName("monoTelemetry")
        self.bench_lbl.setWordWrap(True)
        root.addWidget(self.bench_lbl)

        # Balance sliders
        bal_box = QtWidgets.QGroupBox("MIX BALANCE // 实时人声与伴奏混音比例")
        bal_form = QtWidgets.QFormLayout(bal_box)
        bal_form.setContentsMargins(8, 5, 8, 5)
        bal_form.setVerticalSpacing(4)
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
        met_box = QtWidgets.QGroupBox("STREAM TELEMETRY // 实时分轨监控指标")
        met_grid = QtWidgets.QGridLayout(met_box)
        met_grid.setContentsMargins(8, 5, 8, 5)
        met_grid.setVerticalSpacing(3)
        self.lbl_state = QtWidgets.QLabel("状态: 已关闭 (默认关闭)")
        self.lbl_latency = QtWidgets.QLabel("延迟: 0.0 ms")
        self.lbl_rtf = QtWidgets.QLabel("RTF: 0.000")
        self.lbl_mem = QtWidgets.QLabel("RAM (主/Worker): -")
        self.lbl_vram = QtWidgets.QLabel("空闲 VRAM / GPU%: -")
        self.lbl_buf = QtWidgets.QLabel("输出缓冲: 0.00 s")
        for lbl in (self.lbl_state, self.lbl_latency, self.lbl_rtf, self.lbl_mem, self.lbl_vram, self.lbl_buf):
            lbl.setObjectName("monoTelemetry")
        self.lbl_playback_health = QtWidgets.QLabel("输入跳段 0 次 | 输出溢出丢弃 0 帧 | 输出重缓冲 0 次 | 声卡报告欠载 0 次")
        self.lbl_playback_health.setObjectName("mutedCaption")
        self.lbl_playback_health.setWordWrap(True)
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

    @property
    def pending_start(self) -> bool:
        return self._pending_start

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
        _set_label_cached(self.bench_lbl, text)

    def update_metrics(self, m: LiveSeparationMetrics) -> None:
        if m.active:
            self._pending_start = False
        self.toggle_btn.blockSignals(True)
        if self._pending_start and not m.active:
            if self.toggle_btn.isEnabled():
                self.toggle_btn.setEnabled(False)
            if not self.toggle_btn.isChecked():
                self.toggle_btn.setChecked(True)
            if self.toggle_btn.text() != "基准测试 / 启动中...":
                self.toggle_btn.setText("基准测试 / 启动中...")
        else:
            if not self.toggle_btn.isEnabled():
                self.toggle_btn.setEnabled(True)
            if self.toggle_btn.isChecked() != m.active:
                self.toggle_btn.setChecked(m.active)
            target_btn_txt = "停止实验性近实时分轨" if m.active else "开启实验性近实时分轨"
            if self.toggle_btn.text() != target_btn_txt:
                self.toggle_btn.setText(target_btn_txt)
        self.toggle_btn.blockSignals(False)

        _set_label_cached(self.lbl_state, f"状态: {m.status_message}")
        _set_label_cached(self.lbl_latency, f"分块估计延迟: {m.latency_ms:.1f} ms")
        _set_label_cached(self.lbl_rtf, f"实时率 RTF: {m.rtf:.3f} {'(可实时)' if 0 < m.rtf < 1.0 else ''}")
        _set_label_cached(self.lbl_mem, f"RAM (主={m.main_ram_mb:.1f} MB / Worker={m.worker_ram_mb:.1f} MB)")
        vram_txt = f"{m.vram_free_mb:.0f} MB" if m.vram_free_mb is not None else "N/A"
        util_txt = f"{m.gpu_util_pct:.0f}%" if m.gpu_util_pct is not None else "N/A"
        _set_label_cached(self.lbl_vram, f"空闲 VRAM={vram_txt} | GPU={util_txt}")
        _set_label_cached(self.lbl_buf, f"输出缓冲: {m.buffer_seconds:.2f} / {m.max_buffer_seconds:.1f} s")
        _set_label_cached(
            self.lbl_playback_health,
            f"输入跳段 {m.dropped_chunks} 次 | 输出溢出丢弃 {m.output_overwritten_frames} 帧 | "
            f"输出重缓冲 {m.playback_rebuffers} 次 | 声卡报告欠载 {m.device_underflows} 次",
        )


class ListenScopeMainWindow(QtWidgets.QMainWindow):
    """Primary desktop interface for ListenScope."""

    capture_toggle_requested = QtCore.Signal(bool, object)  # (start_bool, source_descriptor_dict)
    refresh_sources_requested = QtCore.Signal()
    ab_select_recent_requested = QtCore.Signal(float)
    ab_set_range_sec_requested = QtCore.Signal(float, float)
    ab_snap_requested = QtCore.Signal()
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
    restart_requested = QtCore.Signal()

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
        self.setWindowTitle("ListenScope — AUDIO TELEMETRY · A/B LOOP · SAFE AI SEPARATION")
        self.setMinimumSize(760, 520)
        self.setMouseTracking(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        app_icon = _load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            app_inst_gui = QtWidgets.QApplication.instance()
            if isinstance(app_inst_gui, QtWidgets.QApplication) and app_inst_gui.windowIcon().isNull():
                app_inst_gui.setWindowIcon(app_icon)

        self._tearing_down = False
        self._hardware_report = hardware_report
        self._resource_limits = resource_limits
        self._ai_config = ai_config
        self._ai_python_executable = ai_python_executable
        self._midi_python_executable = midi_python_executable
        self._last_verified_ai_probe: Optional[dict[str, Any]] = None
        self._closing_handler = None
        self._last_capture_banner: Optional[str] = None
        self._syncing_ab_region = False
        self._system_is_dark = detect_system_is_dark()
        self._acid_variant: Optional[str] = None
        self._static_lock: bool = False
        self._bottom_panel_collapsed: bool = False
        self._ab_more_user_override: Optional[bool] = None
        self._compact_window_mode: bool = False
        self._active_settings_dialog: Optional[SettingsDialog] = None
        self._style_hints_connected = False
        self._frameless_applied: Optional[bool] = None
        self._drag_offset: Optional[QtCore.QPoint] = None
        self._resize_edges = QtCore.Qt.Edge(0)
        self._resize_start_global: Optional[QtCore.QPoint] = None
        self._resize_start_geom: Optional[QtCore.QRect] = None
        self._win11_dwm_rounded: bool = False
        self._force_quit: bool = False
        self._tray_icon: Optional[QtWidgets.QSystemTrayIcon] = None
        self._tray_notified: bool = False
        self._telemetry_phase: float = 0.0
        self._initial_centered = False

        self._last_capture_status_txt = "未捕获"
        self._last_coverage_txt = "已缓冲: 0.0 / 120.0 s"
        self._last_ai_badge_txt = "AI: Idle"
        self._hist_x_key: Optional[tuple[int, float, float]] = None
        self._hist_x_buf: Optional[np.ndarray] = None
        self._last_hist_empty = False

        app_inst = QtGui.QGuiApplication.instance()
        if app_inst is not None:
            try:
                app_inst.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
                self._style_hints_connected = True
            except Exception:
                pass

        self._play_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Space"), self)
        self._play_shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self._play_shortcut.activated.connect(self.toggle_playback_requested.emit)
        self._setup_practice_shortcuts()

        self._shell_frame = _MainShellFrame(self)
        self._shell_frame.setMouseTracking(True)
        self._shell_frame.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self._shell_frame.installEventFilter(self)
        self.setCentralWidget(self._shell_frame)
        main_layout = QtWidgets.QVBoxLayout(self._shell_frame)
        self._workspace_layout = main_layout
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(5)

        # 1. TWO-TIER COMMAND HEADER: Brand Badge + Telemetry + Segmented Skin Switcher + Audio Input + Hazard/Emergency Stop + Window Controls
        self._topbar_frame = topbar_frame = QtWidgets.QFrame()
        topbar_frame.setObjectName("acidTopbar")
        topbar_frame.installEventFilter(self)
        self._topbar_v = topbar_v = QtWidgets.QVBoxLayout(topbar_frame)
        topbar_v.setContentsMargins(10, 6, 10, 5)
        topbar_v.setSpacing(5)

        row_cmd = QtWidgets.QHBoxLayout()
        row_cmd.setContentsMargins(0, 0, 0, 0)
        row_cmd.setSpacing(5)

        self._brand_badge = ChamferBadge("LS", size=QtCore.QSize(36, 34), chamfer=7)
        brand_txt = QtWidgets.QVBoxLayout()
        brand_txt.setContentsMargins(1, 0, 4, 0)
        brand_txt.setSpacing(3)
        self._brand_eye = ElidedLabel("LISTENSCOPE // AUDIO TELEMETRY")
        self._brand_eye.setObjectName("brandEyebrow")
        self._brand_eye.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        brand_title_row = QtWidgets.QHBoxLayout()
        brand_title_row.setContentsMargins(0, 0, 0, 0)
        brand_title_row.setSpacing(7)
        self._brand_title = QtWidgets.QLabel("实时音频分析与吉他扒谱工作台")
        self._brand_title.setObjectName("telemetryTitle")
        self._brand_title.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._header_pulse = TelemetryPulseStrip(bar_count=6)
        self._acid_hero_echo_lbl = QtWidgets.QLabel("WORKBENCH")
        self._acid_hero_echo_lbl.setObjectName("acidEchoTitle")
        self._acid_hero_echo_lbl.setVisible(False)
        self._acid_hero_sub_lbl = QtWidgets.QLabel("实时频谱 · 120s 分轨终端")
        self._acid_hero_sub_lbl.setObjectName("acidHeroSub")
        self._acid_hero_sub_lbl.setVisible(False)
        brand_title_row.addWidget(self._brand_title)
        brand_title_row.addWidget(self._header_pulse)
        brand_title_row.addStretch(1)
        brand_txt.addWidget(self._brand_eye)
        brand_txt.addLayout(brand_title_row)

        row_cmd.addWidget(self._brand_badge)
        row_cmd.addLayout(brand_txt, 1)

        self._topbar_vdiv = QtWidgets.QFrame()
        self._topbar_vdiv.setObjectName("topbarVDivider")
        self._topbar_vdiv.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self._topbar_vdiv.setFixedHeight(30)
        row_cmd.addWidget(self._topbar_vdiv)

        self.resource_bar = ResourceMonitorBar()
        self.ai_status_badge = QtWidgets.QLabel("AI: Idle")
        self.ai_status_badge.setObjectName("aiStatusBadge")
        set_widget_tone(self.ai_status_badge, "info")

        self._skin_switcher = QtWidgets.QWidget()
        self._skin_switcher.setObjectName("acidModeGroup")
        skin_l = QtWidgets.QHBoxLayout(self._skin_switcher)
        skin_l.setContentsMargins(2, 2, 2, 2)
        skin_l.setSpacing(2)
        self._skin_group = QtWidgets.QButtonGroup(self)
        self._skin_group.setExclusive(True)
        self._pill_dark = QtWidgets.QPushButton("VOID // 黑夜")
        self._pill_light = QtWidgets.QPushButton("LIGHT // 白天")
        for btn, skin_key in ((self._pill_dark, "acid_dark"), (self._pill_light, "acid_light")):
            btn.setObjectName("acidPillBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c=False, k=skin_key: self.set_acid_skin(k))
            self._skin_group.addButton(btn)
            skin_l.addWidget(btn)
        self._pill_light.setChecked(True)

        self.settings_btn = QtWidgets.QPushButton("CONFIG // 设置")
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        self._hazard_bar = HazardStripeBar()
        self._hazard_bar.setVisible(False)

        self.emergency_stop_btn = QtWidgets.QPushButton("E-STOP // 紧急停止")
        self.emergency_stop_btn.setObjectName("emergencyStopBtn")
        self.emergency_stop_btn.clicked.connect(self.emergency_stop_requested.emit)

        # Frameless Window Control Buttons (Minimize / Maximize-Restore / Close)
        self._win_ctrl_box = QtWidgets.QWidget()
        win_ctrl_l = QtWidgets.QHBoxLayout(self._win_ctrl_box)
        win_ctrl_l.setContentsMargins(4, 0, 0, 0)
        win_ctrl_l.setSpacing(4)
        self.win_min_btn = WindowGlyphButton("min", "—")
        self.win_min_btn.setObjectName("windowCtrlBtn")
        self.win_min_btn.setAccessibleName("最小化窗口")
        self.win_min_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.win_min_btn.clicked.connect(self.showMinimized)

        self.win_max_btn = WindowGlyphButton("max", "□")
        self.win_max_btn.setObjectName("windowCtrlBtn")
        self.win_max_btn.setAccessibleName("最大化 / 还原窗口")
        self.win_max_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.win_max_btn.clicked.connect(self._toggle_maximize_restore)

        self.win_close_btn = WindowGlyphButton("close", "×")
        self.win_close_btn.setObjectName("windowCloseBtn")
        self.win_close_btn.setAccessibleName("关闭 ListenScope")
        self.win_close_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.win_close_btn.clicked.connect(self.close)

        win_ctrl_l.addWidget(self.win_min_btn)
        win_ctrl_l.addWidget(self.win_max_btn)
        win_ctrl_l.addWidget(self.win_close_btn)

        row_cmd.addWidget(self.resource_bar)
        row_cmd.addWidget(self.ai_status_badge)
        row_cmd.addWidget(self._skin_switcher)
        row_cmd.addWidget(self.settings_btn)
        row_cmd.addWidget(self._hazard_bar)
        row_cmd.addWidget(self.emergency_stop_btn)
        row_cmd.addWidget(self._win_ctrl_box)
        topbar_v.addLayout(row_cmd)

        self._topbar_divider = divider = QtWidgets.QFrame()
        divider.setObjectName("acidDivider")
        divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        topbar_v.addWidget(divider)

        row_io = QtWidgets.QHBoxLayout()
        row_io.setContentsMargins(0, 0, 0, 0)
        row_io.setSpacing(6)
        self._src_pill = QtWidgets.QLabel("AUDIO_IN // 音源")
        self._src_pill.setObjectName("telemetryPill")
        self.source_combo = MarqueeComboBox()
        self.source_combo.setMinimumWidth(140)
        self.source_combo.setMaximumWidth(400)
        self.source_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.refresh_btn = QtWidgets.QPushButton("刷新进程")
        self.refresh_btn.clicked.connect(self.refresh_sources_requested.emit)

        self.capture_btn = QtWidgets.QPushButton("CAPTURE_START // 开始捕获")
        self.capture_btn.setObjectName("captureBtn")
        self.capture_btn.setCheckable(True)
        self.capture_btn.clicked.connect(self._on_capture_clicked)

        self._capture_dot = SignalLockDot()
        self.capture_status_lbl = QtWidgets.QLabel("未捕获")
        self.capture_status_lbl.setObjectName("captureStatus")
        set_widget_tone(self.capture_status_lbl, "info")

        self._shortcut_pill = QtWidgets.QLabel("SPACE // 快捷键")
        self._shortcut_pill.setObjectName("telemetryPill")
        self._skin_badge = QtWidgets.QLabel("ACID // CLINICAL_LIGHT")
        self._skin_badge.setObjectName("telemetryPill")

        row_io.addWidget(self._src_pill)
        row_io.addWidget(self.source_combo)
        row_io.addWidget(
            HelpBadge(
                "按进程捕获说明",
                "优先选择正在播放音乐的进程（如 QQMusic.exe），仅捕获该应用输出，避免把混音或节拍器再次录回；"
                "若系统 Build < 20348 或列表未找到播放器，可改用系统环回。",
            )
        )
        row_io.addWidget(self.refresh_btn)
        row_io.addWidget(self.capture_btn)
        row_io.addWidget(self._capture_dot)
        row_io.addWidget(self.capture_status_lbl)
        row_io.addStretch(1)
        row_io.addWidget(self._shortcut_pill)
        row_io.addWidget(self._skin_badge)
        topbar_v.addLayout(row_io)

        main_layout.addWidget(topbar_frame)

        # Dismissible warning / notice banner
        self._notice_bar = QtWidgets.QFrame()
        self._notice_bar.setObjectName("bannerNoticeBox")
        self._notice_bar.setVisible(False)
        notice_l = QtWidgets.QHBoxLayout(self._notice_bar)
        notice_l.setContentsMargins(6, 2, 4, 2)
        notice_l.setSpacing(6)
        self.notice_banner = QtWidgets.QLabel("")
        self.notice_banner.setObjectName("bannerNotice")
        self.notice_banner.setProperty("inlineBanner", True)
        self.notice_banner.setWordWrap(True)
        self.notice_banner.setVisible(False)
        self.notice_dismiss_btn = QtWidgets.QPushButton("×")
        self.notice_dismiss_btn.setObjectName("noticeDismissBtn")
        self.notice_dismiss_btn.setAccessibleName("关闭提示横幅")
        self.notice_dismiss_btn.setFixedSize(22, 22)
        self.notice_dismiss_btn.clicked.connect(self.dismiss_banner)
        notice_l.addWidget(self.notice_banner, 1)
        notice_l.addWidget(self.notice_dismiss_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        set_widget_tone(self._notice_bar, "warn")
        set_widget_tone(self.notice_banner, "warn")
        main_layout.addWidget(self._notice_bar)

        # 2. CENTER TABS (Slash-indexed Telemetry navigation with animated signal-lock rail)
        self.tabs = QtWidgets.QTabWidget()
        self._main_tab_bar = AcidTabBar(self.tabs)
        self.tabs.setTabBar(self._main_tab_bar)
        self.spectrum_widget = SpectrumAnalysisWidget()
        self.spectrum_widget.view_combo.activated.connect(self._on_analysis_layout_selected)
        self.chroma_widget = ChromaAndHarmonyWidget()
        self.mixer_widget = StemMixerWidget(mixer_engine)
        self.resource_panel = ResourceStatusPanel()
        self.live_widget = ExperimentalLiveWidget(ai_config)

        self.tabs.addTab(self.spectrum_widget, "// 01 SPECTRUM · 实时频谱")
        self.tabs.addTab(self.chroma_widget, "// 02 CHROMA & HARMONY · 和弦调性")
        self.tabs.addTab(self.mixer_widget, "// 03 STEM MIXER & MIDI · 分轨与MIDI")
        self.tabs.addTab(self.resource_panel, "// 04 TELEMETRY & LOGS · 资源与日志")
        self.tabs.addTab(self.live_widget, "// 05 LIVE ENGINE · 近实时分轨")
        self._bottom_collapse_btn = QtWidgets.QPushButton("▾ 收起 A/B")
        self._bottom_collapse_btn.setCheckable(True)
        self._bottom_collapse_btn.setToolTip("折叠或展开底部 120 秒历史缓冲与 A/B 分轨面板")
        self._bottom_collapse_btn.toggled.connect(self.set_bottom_panel_collapsed)
        self.tabs.setCornerWidget(self._bottom_collapse_btn, QtCore.Qt.Corner.TopRightCorner)

        self._main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.addWidget(self.tabs)

        self._bottom_dock = QtWidgets.QWidget()
        bottom_dock_l = QtWidgets.QVBoxLayout(self._bottom_dock)
        bottom_dock_l.setContentsMargins(0, 0, 0, 0)
        bottom_dock_l.setSpacing(2)

        self._workspace_rail = WorkspaceRailHandle()
        self._workspace_rail.rail_dragged.connect(self._on_workspace_rail_dragged)
        self._workspace_rail.rail_reset_requested.connect(self._on_workspace_rail_reset)
        bottom_dock_l.addWidget(self._workspace_rail)

        # 3. BOTTOM 120s HISTORY TIMELINE + A/B LOOP + AI TRIGGER BAR
        self._history_box = bottom_box = QtWidgets.QGroupBox("RING BUFFER // 120秒历史缓冲与 A/B 片段 (~46MB) + AI 离线分轨")
        self._bottom_l = bottom_l = QtWidgets.QVBoxLayout(bottom_box)
        bottom_l.setContentsMargins(8, 4, 8, 4)
        bottom_l.setSpacing(3)

        row_a = FlowLayout(margin=0, h_spacing=6, v_spacing=3)
        self.history_coverage_lbl = QtWidgets.QLabel("已缓冲: 0.0 / 120.0 s")
        self.history_coverage_lbl.setObjectName("monoTelemetry")
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
        self.ab_a_back_btn.clicked.connect(lambda: self._nudge_ab("a", -1.0))
        self.ab_a_fwd_btn = QtWidgets.QPushButton("A+1s")
        self.ab_a_fwd_btn.clicked.connect(lambda: self._nudge_ab("a", +1.0))
        self.ab_b_back_btn = QtWidgets.QPushButton("B-1s")
        self.ab_b_back_btn.clicked.connect(lambda: self._nudge_ab("b", -1.0))
        self.ab_b_fwd_btn = QtWidgets.QPushButton("B+1s")
        self.ab_b_fwd_btn.clicked.connect(lambda: self._nudge_ab("b", +1.0))

        row_a_transport = QtWidgets.QHBoxLayout()
        row_a_transport.setSpacing(8)
        self.ab_play_btn = QtWidgets.QPushButton("A/B 播放")
        self.ab_play_btn.setObjectName("acidPrimaryBtn")
        self.ab_stop_btn = QtWidgets.QPushButton("停止回放")
        self.ab_loop_chk = QtWidgets.QCheckBox("A/B 循环")
        self.ab_loop_chk.setChecked(True)
        self.ab_loop_chk.toggled.connect(self.ab_loop_toggled.emit)

        self.ab_speed_combo = QtWidgets.QComboBox()
        self.ab_speed_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for lbl, spd in [("0.5x", 0.5), ("0.65x", 0.65), ("0.75x", 0.75), ("0.85x", 0.85), ("1.0x", 1.0), ("1.25x", 1.25)]:
            self.ab_speed_combo.addItem(lbl, spd)
        self.ab_speed_combo.setCurrentIndex(4)
        self.ab_speed_combo.currentIndexChanged.connect(self._on_ab_speed_changed)

        self.ab_export_wav_btn = QtWidgets.QPushButton("导出 A/B 片段 WAV")
        self.import_audio_btn = QtWidgets.QPushButton("导入本地音频(<=120s)")
        self.ab_play_btn.clicked.connect(self.ab_play_requested.emit)
        self.ab_stop_btn.clicked.connect(self.ab_stop_requested.emit)
        self.ab_export_wav_btn.clicked.connect(self._on_ab_export_clicked)
        self.import_audio_btn.clicked.connect(self._on_import_audio_clicked)

        self.ab_more_btn = QtWidgets.QPushButton("⋯ 更多")
        self.ab_more_btn.setCheckable(True)
        self.ab_more_btn.setToolTip("展开或收起 A/B 微调、导出、缩放与书签控件")
        self.ab_more_btn.clicked.connect(self._on_ab_more_toggled)

        row_a.addWidget(self.history_coverage_lbl)
        row_a.addWidget(
            HelpBadge(
                "120 秒历史缓冲与 A/B 选区用法",
                "• 环形缓冲始终在内存中保留最近 120 秒音频（固定约 46MB，绝不无限增长）。\n"
                "• 听到想练的乐句时，直接点「选最近 10s / 30s / 60s」或在下方波形轴上拖动绿色 A/B 边界线。\n"
                "• 选好后既可慢速（0.5x–1.25x）不变调循环精听，也可直接把该 A/B 片段送入下方 AI 2-Stem / 4-Stem 分轨。",
            )
        )
        row_a.addWidget(self.recent_10_btn)
        row_a.addWidget(self.recent_30_btn)
        row_a.addWidget(self.recent_60_btn)
        row_a.addWidget(self.ab_play_btn)
        row_a.addWidget(self.ab_stop_btn)
        row_a.addWidget(self.ab_loop_chk)
        row_a.addWidget(self.ab_speed_combo)
        row_a.addWidget(self.ab_more_btn)
        bottom_l.addLayout(row_a)

        self._ab_more_panel = QtWidgets.QWidget()
        more_v = QtWidgets.QVBoxLayout(self._ab_more_panel)
        more_v.setContentsMargins(0, 0, 0, 0)
        more_v.setSpacing(3)
        more_flow = FlowLayout(margin=0, h_spacing=6, v_spacing=3)
        more_flow.addWidget(self.start_ago_spin)
        more_flow.addWidget(self.end_ago_spin)
        more_flow.addWidget(self.apply_ab_btn)
        more_flow.addWidget(self.ab_a_back_btn)
        more_flow.addWidget(self.ab_a_fwd_btn)
        more_flow.addWidget(self.ab_b_back_btn)
        more_flow.addWidget(self.ab_b_fwd_btn)
        self.ab_snap_btn = QtWidgets.QPushButton("贴近零点")
        self.ab_snap_btn.clicked.connect(self.ab_snap_requested.emit)
        more_flow.addWidget(self.ab_snap_btn)
        more_flow.addWidget(
            HelpBadge(
                "贴近零点微调与不变调变速",
                "• 贴近零点：停止回放后点击，将在当前 A 与 B 边界各 ±5ms 范围内寻找最接近 0 的采样点对齐，消除循环端点咔哒声。\n"
                "• 不变调倍速 (0.5x–1.25x)：基于纯 CPU WSOLA 时域拉伸算法，放慢听清快速贝斯/吉他十六分音符跑动而不改变音高。",
            )
        )
        more_flow.addWidget(self.ab_export_wav_btn)
        more_flow.addWidget(self.import_audio_btn)
        more_v.addLayout(more_flow)
        bottom_l.addWidget(self._ab_more_panel)

        # Interactive 120s Waveform Overview + Draggable A/B Selector + Live Playhead
        self.history_overview_plot = pg.PlotWidget()
        try:
            self.history_overview_plot.hideButtons()
        except Exception:
            pass
        self.history_overview_plot.setMinimumHeight(56)
        self.history_overview_plot.setMaximumHeight(70)
        self.history_overview_plot.setBackground("#F8FAFC")
        history_view = self.history_overview_plot.getViewBox()
        history_view.setLimits(xMin=-120.0, xMax=0.0, minXRange=0.25, maxXRange=120.0)
        self.history_overview_plot.setXRange(-120.0, 0.0, padding=0)
        self.history_overview_plot.setYRange(-1.05, 1.05)
        self.history_overview_plot.hideAxis("left")
        self.history_overview_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.history_overview_plot.setAccessibleName("历史波形时间轴（秒）")
        self.history_overview_plot.setMouseEnabled(x=True, y=False)
        self.history_overview_plot.setMenuEnabled(False)
        self.history_overview_plot.hideButtons()
        self._history_view_timer = QtCore.QTimer(self)
        self._history_view_timer.setSingleShot(True)
        self._history_view_timer.setInterval(60)
        self._history_view_timer.timeout.connect(self.history_view_changed.emit)
        history_view.sigXRangeChanged.connect(lambda *_: self._history_view_timer.start())
        self._hist_max_curve = self.history_overview_plot.plot(pen=pg.mkPen("#0F766E", width=1.0))
        self._hist_min_curve = self.history_overview_plot.plot(pen=pg.mkPen("#0F766E", width=1.0))
        self.ab_region = pg.LinearRegionItem(
            values=(-30.0, 0.0),
            bounds=(-120.0, 0.0),
            brush=(0, 168, 120, 36),
            pen=pg.mkPen("#00A878", width=1.5),
        )
        self.ab_region.setZValue(10)
        self.history_overview_plot.addItem(self.ab_region)
        self._ab_playhead_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#0284C7", width=1.8),
        )
        self._ab_playhead_line.setVisible(False)
        self._ab_playhead_line.setZValue(15)
        self.history_overview_plot.addItem(self._ab_playhead_line)
        self.ab_region.sigRegionChanged.connect(self._on_ab_region_dragged)
        self.ab_region.sigRegionChangeFinished.connect(self._on_ab_region_finished)
        bottom_l.addWidget(self.history_overview_plot)
        for text, label, factor in (("−", "缩小横轴", 1.6), ("+", "放大横轴", 0.625)):
            button = QtWidgets.QToolButton()
            button.setText(text)
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, factor=factor: self.zoom_history(factor))
            more_flow.addWidget(button)
        self.history_reset = QtWidgets.QPushButton("120 秒总览")
        self.history_reset.clicked.connect(lambda: self.history_overview_plot.setXRange(-120, 0, padding=0))
        more_flow.addWidget(self.history_reset)

        bookmark_row = FlowLayout(margin=0, h_spacing=6, v_spacing=3)
        bookmark_row.addWidget(QtWidgets.QLabel("A/B 书签(<=12):"))
        self.bookmark_label_edit = QtWidgets.QLineEdit()
        self.bookmark_label_edit.setPlaceholderText("书签名称 (如 副歌/Solo，可留空)")
        self.bookmark_label_edit.setMaxLength(40)
        self.bookmark_label_edit.setMaximumWidth(210)
        self.bookmark_save_btn = QtWidgets.QPushButton("保存当前 A/B")
        self.bookmark_save_btn.clicked.connect(self._on_bookmark_save_clicked)

        self.bookmark_combo = MarqueeComboBox()
        self.bookmark_combo.setMinimumWidth(160)
        self.bookmark_jump_btn = QtWidgets.QPushButton("跳转此书签")
        self.bookmark_jump_btn.setEnabled(False)
        self.bookmark_jump_btn.clicked.connect(self._on_bookmark_jump_clicked)
        self.bookmark_del_btn = QtWidgets.QPushButton("删除书签")
        self.bookmark_del_btn.setEnabled(False)
        self.bookmark_del_btn.clicked.connect(self._on_bookmark_del_clicked)

        bookmark_row.addWidget(self.bookmark_label_edit)
        bookmark_row.addWidget(self.bookmark_save_btn)
        bookmark_row.addWidget(self.bookmark_combo)
        bookmark_row.addWidget(self.bookmark_jump_btn)
        bookmark_row.addWidget(self.bookmark_del_btn)
        bookmark_row.addWidget(
            HelpBadge(
                "A/B 实时书签说明",
                "保存的书签会绑定到采样帧绝对时间戳：即使音乐继续播放、缓冲向前滚动，点击「跳转此书签」仍能精准跟随后移的音频段落，直到该片段滑出 120 秒窗口。",
            )
        )
        more_v.addLayout(bookmark_row)

        row_b = FlowLayout(margin=0, h_spacing=6, v_spacing=3)
        self.ai_2stem_combo = MarqueeComboBox()
        self.ai_2stem_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.ai_2stem_combo.setMinimumContentsLength(18)
        self.ai_2stem_combo.setMaximumWidth(260)
        self._refresh_model_combos()
        self.ai_gpu_chk = QtWidgets.QCheckBox("优先 GPU")
        self.update_hardware_report(hardware_report, auto_sync_gpu_chk=True)

        self.segment_spin = QtWidgets.QSpinBox()
        self.segment_spin.setRange(4, 10)
        self.segment_spin.setValue(max(4, min(10, int(ai_config.demucs_default_segment_sec))))
        self.segment_spin.setPrefix("Demucs seg=")
        self.segment_spin.setSuffix("s")

        self.sep_2stem_btn = QtWidgets.QPushButton("AI 2-Stem 分轨 (人声/伴奏)")
        self.sep_2stem_btn.setObjectName("acidPrimaryBtn")
        self.sep_2stem_btn.clicked.connect(self._on_sep_2stem)
        self.sep_4stem_btn = QtWidgets.QPushButton("AI 4-Stem 分轨 (HTDemucs)")
        self.sep_4stem_btn.clicked.connect(self._on_sep_4stem)

        row_b.addWidget(QtWidgets.QLabel("2-Stem 模型:"))
        row_b.addWidget(self.ai_2stem_combo)
        row_b.addWidget(self.segment_spin)
        row_b.addWidget(self.ai_gpu_chk)
        row_b.addWidget(
            HelpBadge(
                "8GB 显存防护与分轨模型",
                "AI 分轨全部在独立子进程执行，按 6s 分块逐段流式推理并自动清理中间缓存；"
                "若 GPU 显存或系统内存接近保护阈值，将自动拦截或停止以保护播放器不卡顿。",
            )
        )
        row_b.addWidget(self.sep_2stem_btn)
        row_b.addWidget(self.sep_4stem_btn)
        bottom_l.addLayout(row_b)

        bottom_dock_l.addWidget(bottom_box)
        self._main_splitter.addWidget(self._bottom_dock)
        self._main_splitter.setStretchFactor(0, 3)
        self._main_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self._main_splitter, 1)

        self._acid_footer = AcidBarcodeFooter()
        self._acid_footer.setVisible(False)
        self._acid_footer.static_lock_toggled.connect(self._on_static_lock_toggled)
        main_layout.addWidget(self._acid_footer)

        self.center_on_screen()
        self._init_system_tray()
        install_tooltip_guard(self)
        self.apply_appearance(appearance, force_theme=True)

    def center_on_screen(self) -> None:
        """Adapt initial window size to screen available geometry and center cleanly on the primary screen."""
        screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1360, 870)
            return
        avail = screen.availableGeometry()
        if avail.width() <= 0 or avail.height() <= 0:
            self.resize(1360, 870)
            return
        target_w = max(1120, min(1420, int(avail.width() * 0.90)))
        target_h = max(740, min(900, int(avail.height() * 0.88)))
        target_w = min(target_w, avail.width())
        target_h = min(target_h, avail.height())
        x = avail.x() + max(0, (avail.width() - target_w) // 2)
        y = avail.y() + max(0, (avail.height() - target_h) // 2)
        self.setGeometry(x, y, target_w, target_h)
        self._initial_centered = True

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._initial_centered:
            self.center_on_screen()
        self._apply_windows_taskbar_and_rounding()

    def _init_system_tray(self) -> None:
        if self._tray_icon is not None:
            return
        try:
            if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
                return
        except Exception:
            return
        tray = QtWidgets.QSystemTrayIcon(_load_app_icon(), self)
        tray.setToolTip("ListenScope")
        menu = QtWidgets.QMenu(self)
        act_show = menu.addAction("显示主界面")
        act_show.triggered.connect(self.show_from_tray)
        act_settings = menu.addAction("打开设置")
        act_settings.triggered.connect(lambda: (self.show_from_tray(), self.open_settings_dialog()))
        menu.addSeparator()
        act_quit = menu.addAction("退出 ListenScope")
        act_quit.triggered.connect(self.force_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray

    def _on_tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def force_quit(self) -> None:
        self._force_quit = True
        app = QtWidgets.QApplication.instance()
        if isinstance(app, QtWidgets.QApplication):
            app.setQuitOnLastWindowClosed(True)
        self.close()

    def _apply_windows_taskbar_and_rounding(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if not hwnd:
            return
        # Re-apply explicit Win32 WM_SETICON so frameless windows still render the taskbar emblem crisp & non-generic
        try:
            user32 = ctypes.windll.user32
            hicons = getattr(self, "_win32_hicons", None)
            if not hicons:
                assets_dir = get_bundle_root() / "ui" / "assets"
                ico_path = assets_dir / "listenscope.ico"
                if not ico_path.exists():
                    ico_path = Path(__file__).resolve().parent / "assets" / "listenscope.ico"
                if ico_path.exists():
                    lr_loadfromfile = 0x0010
                    image_icon = 1
                    h_big = user32.LoadImageW(None, str(ico_path), image_icon, 48, 48, lr_loadfromfile)
                    h_small = user32.LoadImageW(None, str(ico_path), image_icon, 16, 16, lr_loadfromfile)
                    hicons = (h_big, h_small)
                    self._win32_hicons = hicons
            if hicons:
                h_big, h_small = hicons
                if h_big:
                    user32.SendMessageW(hwnd, 0x0080, 1, h_big)
                if h_small:
                    user32.SendMessageW(hwnd, 0x0080, 0, h_small)
        except Exception:
            pass
        # Enable native Windows 11 DWM rounded corners (DWMWCP_ROUND=2) when available
        try:
            win_ver = sys.getwindowsversion()
            if getattr(win_ver, "build", 0) >= 22000 and getattr(self, "_frameless_applied", False):
                dwmapi = ctypes.windll.dwmapi
                pref = ctypes.c_int(2)
                hr = dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
                if hr == 0:
                    self._win11_dwm_rounded = True
                    self.clearMask()
        except Exception:
            pass

    def _toggle_maximize_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.win_max_btn.setText("□")
            self.win_max_btn.set_maximized(False)
        else:
            self.showMaximized()
            self.win_max_btn.setText("❐")
            self.win_max_btn.set_maximized(True)
        self._update_rounded_mask()

    def _apply_frameless_mode(self, frameless: bool) -> None:
        want_frameless = bool(frameless)
        self._shell_frame.setProperty("frameless", want_frameless)
        self._win_ctrl_box.setVisible(want_frameless)
        if self._frameless_applied == want_frameless:
            self._update_rounded_mask()
            return
        was_visible = self.isVisible()
        saved_geom = self.geometry() if was_visible else None
        self._frameless_applied = want_frameless
        self._win11_dwm_rounded = False
        flags = (
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowSystemMenuHint
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
            | QtCore.Qt.WindowType.WindowCloseButtonHint
        )
        if want_frameless:
            flags |= QtCore.Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        icon = _load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        if was_visible:
            self.show()
            if saved_geom is not None and saved_geom.isValid():
                self.setGeometry(saved_geom)
        self._apply_windows_taskbar_and_rounding()
        self._update_rounded_mask()

    def _update_rounded_mask(self) -> None:
        """Apply a clean anti-aliased rounded mask in frameless mode unless Win11 DWM handles native rounding."""
        if not getattr(self, "_frameless_applied", False) or self.isMaximized() or getattr(self, "_win11_dwm_rounded", False):
            self.clearMask()
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(0, 0, w, h), 10.0, 10.0)
        region = QtGui.QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def _hit_test_resize_edges(self, local_pos: QtCore.QPoint) -> QtCore.Qt.Edge:
        """Return Qt.Edge flags if `local_pos` (in MainWindow coordinates) lies inside the 8px resize rim."""
        if not getattr(self, "_frameless_applied", False) or self.isMaximized():
            return QtCore.Qt.Edge(0)
        m = 8
        w, h = self.width(), self.height()
        if w <= m * 2 or h <= m * 2:
            return QtCore.Qt.Edge(0)
        x, y = local_pos.x(), local_pos.y()
        edges = QtCore.Qt.Edge(0)
        if 0 <= x < m:
            edges |= QtCore.Qt.Edge.LeftEdge
        elif w - m <= x <= w:
            edges |= QtCore.Qt.Edge.RightEdge
        if 0 <= y < m:
            edges |= QtCore.Qt.Edge.TopEdge
        elif h - m <= y <= h:
            edges |= QtCore.Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for_edges(edges: QtCore.Qt.Edge) -> Optional[QtCore.Qt.CursorShape]:
        left = bool(edges & QtCore.Qt.Edge.LeftEdge)
        right = bool(edges & QtCore.Qt.Edge.RightEdge)
        top = bool(edges & QtCore.Qt.Edge.TopEdge)
        bottom = bool(edges & QtCore.Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            return QtCore.Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return QtCore.Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return QtCore.Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return QtCore.Qt.CursorShape.SizeVerCursor
        return None

    def _apply_software_resize(self, global_pos: QtCore.QPoint) -> None:
        if not self._resize_edges or self._resize_start_global is None or self._resize_start_geom is None:
            return
        delta = global_pos - self._resize_start_global
        geom = QtCore.QRect(self._resize_start_geom)
        min_w = max(640, self.minimumWidth())
        min_h = max(480, self.minimumHeight())
        if self._resize_edges & QtCore.Qt.Edge.LeftEdge:
            new_left = min(geom.right() - min_w + 1, geom.left() + delta.x())
            geom.setLeft(new_left)
        if self._resize_edges & QtCore.Qt.Edge.RightEdge:
            new_right = max(geom.left() + min_w - 1, geom.right() + delta.x())
            geom.setRight(new_right)
        if self._resize_edges & QtCore.Qt.Edge.TopEdge:
            new_top = min(geom.bottom() - min_h + 1, geom.top() + delta.y())
            geom.setTop(new_top)
        if self._resize_edges & QtCore.Qt.Edge.BottomEdge:
            new_bottom = max(geom.top() + min_h - 1, geom.bottom() + delta.y())
            geom.setBottom(new_bottom)
        self.setGeometry(geom)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._update_rounded_mask()

    def _on_ab_more_toggled(self, checked: bool) -> None:
        self._ab_more_user_override = bool(checked)
        self._ab_more_panel.setVisible(bool(checked))

    def set_bottom_panel_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        self._bottom_panel_collapsed = collapsed
        self._bottom_dock.setVisible(not collapsed)
        self._bottom_collapse_btn.blockSignals(True)
        self._bottom_collapse_btn.setChecked(collapsed)
        self._bottom_collapse_btn.setText("▸ 展开 A/B" if collapsed else "▾ 收起 A/B")
        self._bottom_collapse_btn.blockSignals(False)
        if not collapsed:
            self._apply_responsive_layout()

    def toggle_bottom_panel(self, collapsed: Optional[bool] = None) -> None:
        target = (not self._bottom_panel_collapsed) if collapsed is None else bool(collapsed)
        self.set_bottom_panel_collapsed(target)

    def _apply_responsive_layout(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        compact_h = h < 760
        compact_w = w <= 500
        self._compact_window_mode = compact_h or compact_w

        # Tighten shell and topbar padding on short/narrow screens
        self._workspace_layout.setContentsMargins(4 if compact_h else 8, 2 if compact_h else 6, 4 if compact_h else 8, 2 if compact_h else 6)
        self._workspace_layout.setSpacing(2 if compact_h else 5)
        self._topbar_v.setContentsMargins(8 if compact_h else 10, 2 if compact_h else 6, 8 if compact_h else 10, 2 if compact_h else 5)
        self._topbar_v.setSpacing(2 if compact_h else 5)
        self._brand_eye.setVisible(not compact_h)
        self._topbar_divider.setVisible(not compact_h)
        self._shortcut_pill.setVisible(not compact_h and not compact_w)
        self._skin_badge.setVisible(not compact_h and not compact_w)

        # Collapse secondary A/B controls on short screens unless user explicitly expanded them
        if self._ab_more_user_override is None:
            show_more = not compact_h
            self._ab_more_panel.setVisible(show_more)
            self.ab_more_btn.blockSignals(True)
            self.ab_more_btn.setChecked(show_more)
            self.ab_more_btn.blockSignals(False)

        if not self._bottom_panel_collapsed:
            practice = getattr(self.appearance, "layout", "split") == "practice"
            if compact_h and not practice:
                self.history_overview_plot.setMinimumHeight(34)
                self.history_overview_plot.setMaximumHeight(44)
                self._bottom_l.setContentsMargins(6, 2, 6, 2)
                self._bottom_l.setSpacing(2)
            else:
                self.history_overview_plot.setMinimumHeight(112 if practice else 48)
                self.history_overview_plot.setMaximumHeight(140 if practice else 64)
                self._bottom_l.setContentsMargins(8, 4, 8, 4)
                self._bottom_l.setSpacing(3)

        if hasattr(self, "spectrum_widget"):
            self.spectrum_widget.set_compact_mode(compact_h or self.spectrum_widget.height() < 420)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if (
            not getattr(self, "_tearing_down", False)
            and getattr(self, "_frameless_applied", False)
            and event.button() == QtCore.Qt.MouseButton.LeftButton
        ):
            local = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = self._hit_test_resize_edges(local)
            if edges:
                win_handle = self.windowHandle()
                if win_handle is not None and hasattr(win_handle, "startSystemResize"):
                    try:
                        if win_handle.startSystemResize(edges):
                            event.accept()
                            return
                    except Exception:
                        pass
                self._resize_edges = edges
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geom = QtCore.QRect(self.geometry())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if not getattr(self, "_tearing_down", False) and getattr(self, "_frameless_applied", False):
            if self._resize_edges and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                self._apply_software_resize(event.globalPosition().toPoint())
                event.accept()
                return
            if not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                local = self.mapFromGlobal(event.globalPosition().toPoint())
                cur = self._cursor_for_edges(self._hit_test_resize_edges(local))
                if cur is not None:
                    self.setCursor(cur)
                else:
                    self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        self._resize_edges = QtCore.Qt.Edge(0)
        self._resize_start_global = None
        self._resize_start_geom = None
        if not getattr(self, "_tearing_down", False):
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def changeEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            m = self.isMaximized()
            if hasattr(self, "win_max_btn"):
                self.win_max_btn.set_maximized(m)
                self.win_max_btn.setText("❐" if m else "□")
            if hasattr(self, "_update_rounded_mask"):
                self._update_rounded_mask()

    def restore_saved_geometry(self, b64_geometry: str) -> None:
        raw = (b64_geometry or "").strip()
        if not raw:
            return
        try:
            ba = QtCore.QByteArray.fromBase64(raw.encode("ascii"))
            if not ba.isEmpty() and self.restoreGeometry(ba):
                fg = self.frameGeometry()
                if any(s.availableGeometry().intersects(fg) for s in QtWidgets.QApplication.screens()):
                    return
        except Exception:
            pass
        self.center_on_screen()

    def _step_ab_speed(self, delta: int) -> None:
        if not hasattr(self, "ab_speed_combo"):
            return
        idx = self.ab_speed_combo.currentIndex()
        new_idx = max(0, min(self.ab_speed_combo.count() - 1, idx + delta))
        if new_idx != idx:
            self.ab_speed_combo.setCurrentIndex(new_idx)

    def _setup_practice_shortcuts(self) -> None:
        class _TextInputGuard(QtCore.QObject):
            def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
                if event.type() == QtCore.QEvent.Type.ShortcutOverride:
                    fw = QtWidgets.QApplication.focusWidget()
                    if isinstance(fw, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QPlainTextEdit)):
                        kev = event  # type: ignore[assignment]
                        mods = kev.modifiers()
                        if not (mods & (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.AltModifier)):
                            event.accept()
                            return True
                return super().eventFilter(watched, event)

        self._text_input_guard = _TextInputGuard(self)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self._text_input_guard)

        self._practice_shortcuts: list[QtGui.QShortcut] = []
        bindings = [
            ("Space", self.toggle_playback_requested.emit),
            ("L", lambda: self.ab_loop_chk.toggle() if hasattr(self, "ab_loop_chk") else None),
            ("[", lambda: self.start_ago_spin.setValue(min(120.0, self.start_ago_spin.value() + 0.5)) if hasattr(self, "start_ago_spin") else None),
            ("]", lambda: self.end_ago_spin.setValue(max(0.0, self.end_ago_spin.value() - 0.5)) if hasattr(self, "end_ago_spin") else None),
            ("Alt+Left", lambda: self.start_ago_spin.setValue(min(120.0, self.start_ago_spin.value() + 0.25)) if hasattr(self, "start_ago_spin") else None),
            ("Alt+Right", lambda: self.start_ago_spin.setValue(max(0.5, self.start_ago_spin.value() - 0.25)) if hasattr(self, "start_ago_spin") else None),
            ("Shift+Alt+Left", lambda: self.end_ago_spin.setValue(min(119.5, self.end_ago_spin.value() + 0.25)) if hasattr(self, "end_ago_spin") else None),
            ("Shift+Alt+Right", lambda: self.end_ago_spin.setValue(max(0.0, self.end_ago_spin.value() - 0.25)) if hasattr(self, "end_ago_spin") else None),
            ("-", lambda: self._step_ab_speed(-1)),
            ("=", lambda: self._step_ab_speed(1)),
            ("0", lambda: self.ab_speed_combo.setCurrentIndex(4) if hasattr(self, "ab_speed_combo") and self.ab_speed_combo.count() > 4 else None),
            ("T", lambda: self.chroma_widget.tap_tempo_btn.click() if hasattr(self, "chroma_widget") and hasattr(self.chroma_widget, "tap_tempo_btn") else None),
            ("M", lambda: self.chroma_widget.metronome_standalone_btn.click() if hasattr(self, "chroma_widget") and hasattr(self.chroma_widget, "metronome_standalone_btn") else None),
            ("Ctrl+B", lambda: self.ab_bookmark_save_requested.emit(self.bookmark_label_edit.text().strip()) if hasattr(self, "bookmark_label_edit") else None),
        ]
        for seq, slot in bindings:
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
            sc.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            self._practice_shortcuts.append(sc)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if getattr(self, "_tearing_down", False) or not _is_qt_valid(self) or not _is_qt_valid(watched):
            return False
        etype = event.type()
        if etype == QtCore.QEvent.Type.Destroy:
            return False
        is_frameless = bool(getattr(self, "_frameless_applied", False))
        shell = getattr(self, "_shell_frame", None)
        if is_frameless and shell is not None and _is_qt_valid(shell) and watched is shell:
            if etype == QtCore.QEvent.Type.HoverMove and not self._resize_edges:
                hev = event  # type: ignore[assignment]
                if hasattr(hev, "globalPosition"):
                    local = self.mapFromGlobal(hev.globalPosition().toPoint())
                else:
                    local = hev.position().toPoint()
                edges = self._hit_test_resize_edges(local)
                cur = self._cursor_for_edges(edges)
                if cur is not None:
                    self.setCursor(cur)
                else:
                    self.unsetCursor()
            elif etype == QtCore.QEvent.Type.MouseButtonPress:
                mouse_ev = event  # type: ignore[assignment]
                if isinstance(mouse_ev, QtGui.QMouseEvent) and mouse_ev.button() == QtCore.Qt.MouseButton.LeftButton:
                    local = self.mapFromGlobal(mouse_ev.globalPosition().toPoint())
                    edges = self._hit_test_resize_edges(local)
                    if edges:
                        win_handle = self.windowHandle()
                        if win_handle is not None and hasattr(win_handle, "startSystemResize"):
                            try:
                                if win_handle.startSystemResize(edges):
                                    return True
                            except Exception:
                                pass
                        self._resize_edges = edges
                        self._resize_start_global = mouse_ev.globalPosition().toPoint()
                        self._resize_start_geom = QtCore.QRect(self.geometry())
                        return True
            elif etype == QtCore.QEvent.Type.MouseMove:
                mouse_ev = event  # type: ignore[assignment]
                if isinstance(mouse_ev, QtGui.QMouseEvent):
                    if self._resize_edges and (mouse_ev.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        self._apply_software_resize(mouse_ev.globalPosition().toPoint())
                        return True
                    if not (mouse_ev.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        local = self.mapFromGlobal(mouse_ev.globalPosition().toPoint())
                        cur = self._cursor_for_edges(self._hit_test_resize_edges(local))
                        if cur is not None:
                            self.setCursor(cur)
                        else:
                            self.unsetCursor()
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                self._resize_edges = QtCore.Qt.Edge(0)
                self._resize_start_global = None
                self._resize_start_geom = None
                self.unsetCursor()

        topbar = getattr(self, "_topbar_frame", None)
        if topbar is not None and _is_qt_valid(topbar) and watched is topbar and is_frameless:
            if etype == QtCore.QEvent.Type.MouseButtonDblClick:
                mouse_ev = event  # type: ignore[assignment]
                if isinstance(mouse_ev, QtGui.QMouseEvent) and mouse_ev.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._toggle_maximize_restore()
                    return True
            elif etype == QtCore.QEvent.Type.MouseButtonPress:
                mouse_ev = event  # type: ignore[assignment]
                if isinstance(mouse_ev, QtGui.QMouseEvent) and mouse_ev.button() == QtCore.Qt.MouseButton.LeftButton:
                    local_win = self.mapFromGlobal(mouse_ev.globalPosition().toPoint())
                    edges = self._hit_test_resize_edges(local_win)
                    if edges:
                        self._resize_edges = edges
                        self._resize_start_global = mouse_ev.globalPosition().toPoint()
                        self._resize_start_geom = QtCore.QRect(self.geometry())
                        return True
                    child = self._topbar_frame.childAt(mouse_ev.position().toPoint())
                    if not isinstance(child, (QtWidgets.QAbstractButton, QtWidgets.QComboBox)):
                        win_handle = self.windowHandle()
                        if win_handle is not None and hasattr(win_handle, "startSystemMove"):
                            try:
                                if win_handle.startSystemMove():
                                    return True
                            except Exception:
                                pass
                        if not self.isMaximized():
                            self._drag_offset = mouse_ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                            return True
            elif etype == QtCore.QEvent.Type.MouseMove:
                mouse_ev = event  # type: ignore[assignment]
                if isinstance(mouse_ev, QtGui.QMouseEvent):
                    if self._resize_edges and (mouse_ev.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        self._apply_software_resize(mouse_ev.globalPosition().toPoint())
                        return True
                    if (
                        self._drag_offset is not None
                        and (mouse_ev.buttons() & QtCore.Qt.MouseButton.LeftButton)
                        and not self.isMaximized()
                    ):
                        self.move(mouse_ev.globalPosition().toPoint() - self._drag_offset)
                        return True
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                self._resize_edges = QtCore.Qt.Edge(0)
                self._resize_start_global = None
                self._resize_start_geom = None
        return super().eventFilter(watched, event)

    def _on_static_lock_toggled(self, locked: bool) -> None:
        self._static_lock = bool(locked)
        self.update_music_telemetry(0.0, 0.0)

    def update_music_telemetry(self, energy: float = 0.0, climax: float = 0.0) -> None:
        """Drive header/card telemetry micro-animations scaled by user intensity & music dynamics."""
        app = getattr(self, "appearance", Appearance())
        strength = max(0.0, min(1.0, float(getattr(app, "telemetry_animation_strength", 70)) / 100.0))
        reactive = bool(getattr(app, "music_reactive_animations", True))
        locked = bool(getattr(self, "_static_lock", False))
        if not locked and strength > 0.02:
            step = 0.22 + (0.28 * energy + 0.35 * climax if reactive else 0.08) * strength
            self._telemetry_phase = (self._telemetry_phase + step) % 628.0
        phase = self._telemetry_phase
        self._header_pulse.set_telemetry(
            energy=energy,
            climax=climax,
            strength=strength,
            reactive=reactive,
            locked=locked,
            phase=phase,
        )
        self._capture_dot.set_pulse(
            phase=phase,
            energy=energy if reactive else 0.35,
            strength=strength,
            locked=locked,
        )
        self.spectrum_widget.update_telemetry(
            energy=energy,
            climax=climax,
            strength=strength,
            reactive=reactive,
            locked=locked,
            phase=phase,
        )
        self.chroma_widget.update_telemetry_pulse(
            energy=energy,
            climax=climax,
            strength=strength,
            reactive=reactive,
            locked=locked,
            phase=phase,
        )
        self.mixer_widget.update_telemetry(
            energy=energy,
            climax=climax,
            strength=strength,
            reactive=reactive,
            locked=locked,
            phase=phase,
        )

    def set_acid_skin(self, skin: str) -> None:
        skin_map = {
            "acid_light": "light",
            "light": "light",
            "acid_dark": "dark",
            "dark": "dark",
        }
        target_mode = skin_map.get(skin)
        if target_mode is None:
            return
        base = getattr(self, "appearance", Appearance())
        updated = replace(
            base,
            preset="acid_telemetry",
            background="",
            text="",
            accent="",
            theme_mode=target_mode,
        )
        self.apply_appearance(updated, force_theme=True)
        self.appearance_applied.emit()

    @QtCore.Slot(object)
    def _on_system_color_scheme_changed(self, _scheme: Any = None) -> None:
        new_dark = detect_system_is_dark()
        if new_dark == self._system_is_dark:
            return
        self._system_is_dark = new_dark
        if getattr(self, "appearance", None) is not None and self.appearance.theme_mode == "system":
            self.apply_appearance(self.appearance, force_theme=True)

    def _apply_history_plot_theme(
        self,
        appearance: Appearance,
        *,
        acid_variant: Optional[str] = None,
    ) -> None:
        if acid_variant in ("light", "dark"):
            p = get_acid_palette(acid_variant)
            apply_acid_plot_theme(self.history_overview_plot, appearance, acid_variant, is_history=True)
            wave_color = p.hist_plot_wave
            reg_brush = p.plot_region_rgba
            reg_pen = p.plot_region_pen
            playhead_pen = p.plot_playhead
        else:
            mode = appearance.resolve_theme_mode(system_is_dark=self._system_is_dark)
            bg, fg, accent = appearance.effective_colors(system_is_dark=self._system_is_dark)
            if mode == "light":
                wave_color = _blend(fg, accent, 0.45)
                reg_brush = (22, 163, 74, 42)
                reg_pen = "#15803D"
                playhead_pen = "#D97706"
            else:
                wave_color = _blend("#4EA8DE", accent, 0.35)
                reg_brush = (46, 194, 126, 48)
                reg_pen = "#2EC27E"
                playhead_pen = "#FFD166"
        pen = pg.mkPen(wave_color, width=1.0)
        self._hist_max_curve.setPen(pen)
        self._hist_min_curve.setPen(pen)
        self.ab_region.setBrush(reg_brush)
        self.ab_region.setHoverBrush(reg_brush)
        for line in self.ab_region.lines:
            line.setPen(pg.mkPen(reg_pen, width=1.5))
        self._ab_playhead_line.setPen(pg.mkPen(playhead_pen, width=1.8))

    def _sync_acid_chrome(self, is_acid: bool, variant: Optional[str]) -> None:
        is_active = bool(is_acid and variant in ("light", "dark"))
        lang = getattr(getattr(self, "appearance", Appearance()), "language", "zh")
        if is_active:
            eye_txt = {
                "zh": "LISTENSCOPE · 实时频谱",
                "en": "LISTENSCOPE · SPECTRUM",
                "ko": "LISTENSCOPE · 실시간 스펙트럼",
                "ja": "LISTENSCOPE · スペクトル",
            }.get(lang, "LISTENSCOPE · 实时频谱")
            self._brand_eye.setText(eye_txt)
            self._brand_title.setText("SIGNAL_GRID")
            self._brand_title.setObjectName("acidHeroTitle")
            self._acid_hero_echo_lbl.setVisible(False)
            self._acid_hero_sub_lbl.setVisible(False)
            self._src_pill.setText(tr_telemetry("AUDIO_IN", lang, zh="音源", ko="오디오 입력", ja="音声入力"))
            self._shortcut_pill.setText(tr_telemetry("SPACE", lang, zh="快捷键", ko="단축키", ja="ショートカット"))
            self._pill_dark.setText(tr_telemetry("VOID", lang, zh="黑夜", ko="다크", ja="ダーク"))
            self._pill_light.setText(tr_telemetry("LIGHT", lang, zh="白天", ko="라이트", ja="ライト"))
            self.settings_btn.setText(tr_telemetry("CONFIG", lang, zh="设置", ko="설정", ja="設定"))
            self.emergency_stop_btn.setText(tr_telemetry("E-STOP", lang, zh="紧急停止", ko="긴급 정지", ja="緊急停止"))
            self._history_box.setTitle(
                tr_telemetry(
                    "RING BUFFER // 120S HISTORY · A/B LOOP + AI DISPATCH (~46MB)",
                    lang,
                    zh="120秒历史缓冲与 A/B 片段 + AI 分轨",
                    ko="120초 히스토리 버퍼 · A/B 구간 + AI 분리",
                    ja="120秒履歴バッファ · A/B ループ + AI 分離",
                )
            )
            self._history_box.setObjectName("historyPaperDock")
            self._skin_badge.setObjectName("acidMicroTag")
            tab_titles = (
                tr_telemetry("// 01 SPECTRUM", lang, zh="实时频谱", ko="실시간 스펙트럼", ja="スペクトル"),
                tr_telemetry("// 02 CHROMA && HARMONY", lang, zh="和弦与调性", ko="코드 && 조성", ja="コードと調性"),
                tr_telemetry("// 03 STEM MIXER && MIDI", lang, zh="分轨与MIDI", ko="스템 믹서 && MIDI", ja="ステムとMIDI"),
                tr_telemetry("// 04 TELEMETRY && LOGS", lang, zh="资源与日志", ko="리소스 && 로그", ja="リソースとログ"),
                tr_telemetry("// 05 LIVE ENGINE", lang, zh="近实时分轨", ko="준실시간 분리", ja="準リアルタイム分離"),
            )
        else:
            self._static_lock = False
            self._acid_footer.set_locked(False)
            self._brand_eye.setText("LISTENSCOPE // AUDIO TELEMETRY")
            self._brand_title.setText(
                tr("title_workbench", lang)
            )
            self._brand_title.setObjectName("telemetryTitle")
            self._acid_hero_echo_lbl.setVisible(False)
            self._acid_hero_sub_lbl.setVisible(False)
            self._src_pill.setText(tr_telemetry("AUDIO INPUT", lang, zh="音源", ko="오디오 입력", ja="音声入力"))
            self._shortcut_pill.setText(tr_telemetry("SPACE", lang, zh="快捷键", ko="단축키", ja="ショートカット"))
            self.settings_btn.setText(tr("btn_settings", lang))
            self.emergency_stop_btn.setText(tr("btn_estop", lang))
            self._history_box.setTitle(
                tr_telemetry(
                    "120S HISTORY BUFFER · A/B LOOP (~46MB) + AI SEPARATION",
                    lang,
                    zh="120秒历史缓冲与 A/B 片段 (零溢出固定上限 ~46MB) + AI 离线分轨",
                    ko="120초 히스토리 버퍼 · A/B 구간 (~46MB) + AI 분리",
                    ja="120秒履歴バッファ · A/B 区間 (~46MB) + AI 分離",
                )
            )
            self._history_box.setObjectName("")
            self._skin_badge.setObjectName("telemetryPill")
            tab_titles = (
                tr("tab_spectrum", lang),
                tr("tab_chroma", lang),
                tr("tab_mixer", lang),
                tr("tab_resources", lang),
                tr("tab_live", lang),
            )
        for idx, title in enumerate(tab_titles):
            if idx < self.tabs.count():
                self.tabs.setTabText(idx, title)
        self._hazard_bar.setVisible(is_active)
        self._acid_footer.setVisible(is_active)
        if is_active:
            p = get_acid_palette(variant or "light")
            self._hazard_bar.set_color(p.danger)
            self._acid_footer.set_colors(p.micro_tag_bg, "#090D10")
        if is_active:
            self.capture_btn.setText(
                tr_telemetry("CAPTURE_ACTIVE", lang, zh="停止捕获", ko="캡처 중지", ja="キャプチャ停止")
                if self.capture_btn.isChecked()
                else tr_telemetry("CAPTURE_START", lang, zh="开始捕获", ko="캡처 시작", ja="キャプチャ開始")
            )
        else:
            self.capture_btn.setText(
                tr("btn_stop_capture", lang) if self.capture_btn.isChecked() else tr("btn_start_capture", lang)
            )
        for widget in (self._brand_title, self._history_box, self._skin_badge, self._shell_frame):
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
            widget.update()

    def apply_appearance(self, appearance: Appearance, *, force_theme: bool = False) -> None:
        old = getattr(self, "appearance", None)
        if appearance == old and not force_theme:
            return
        was_visible = self.isVisible()
        saved_geom = self.geometry() if was_visible else None
        self.appearance = appearance
        self.mixer_widget.plot_appearance = appearance
        set_help_mode_enabled(appearance.help_mode)
        set_focus_animations_enabled(appearance.focus_animations)
        set_focus_ring_style(appearance.focus_style)
        set_help_language(appearance.language)
        self._apply_frameless_mode(appearance.frameless)
        self._shell_frame.set_wallpaper_path(appearance.effective_background_image())
        if old is None or appearance.layout != old.layout:
            self._apply_workspace_layout(appearance.layout)
        analysis_view = self.spectrum_widget.view_combo
        analysis_view.setCurrentIndex(analysis_view.findData(appearance.analysis_layout))
        if (
            old is not None
            and not force_theme
            and replace(
                appearance,
                layout=old.layout,
                analysis_layout=old.analysis_layout,
                help_mode=old.help_mode,
                focus_animations=old.focus_animations,
                focus_style=old.focus_style,
                telemetry_animation_strength=old.telemetry_animation_strength,
                music_reactive_animations=old.music_reactive_animations,
                close_to_tray=old.close_to_tray,
            )
            == old
        ):
            self.update_music_telemetry(0.0, 0.0)
            if was_visible and saved_geom is not None and saved_geom.isValid() and not self.isMaximized():
                if self.geometry() != saved_geom:
                    self.setGeometry(saved_geom)
            self._sync_active_settings_dialog()
            return

        eligible = is_acid_eligible(appearance)
        variant = resolve_acid_variant(appearance, system_is_dark=self._system_is_dark)
        self._acid_variant = variant
        self._skin_switcher.setVisible(eligible)
        for btn, checked in (
            (self._pill_light, variant == "light"),
            (self._pill_dark, variant == "dark"),
        ):
            btn.blockSignals(True)
            btn.setChecked(checked)
            btn.blockSignals(False)

        if variant in ("light", "dark"):
            p = get_acid_palette(variant)
            self._header_pulse.set_theme_color(p.accent)
            self._capture_dot.set_colors(p.accent, p.text_muted)
            self._main_tab_bar.set_rail_colors(
                p.accent if variant == "light" else p.ribbon_bg,
                p.accent_secondary,
            )
            self._workspace_rail.set_grip_colors(
                grip=p.text_muted,
                accent=p.accent,
                line=p.border,
            )
            self.win_min_btn.set_glyph_colors(p.text_secondary, p.text_inverse)
            self.win_max_btn.set_glyph_colors(p.text_secondary, p.text_inverse)
            self.win_close_btn.set_glyph_colors(p.text_secondary, "#FFFFFF")
            set_help_theme(
                bg=p.bg_panel,
                fg=p.text_primary,
                accent=p.accent,
                border=p.border,
                muted=p.text_muted,
                is_dark=(variant == "dark"),
                is_acid=True,
            )
            self._skin_badge.setText(
                "ACID // CLINICAL_LIGHT" if variant == "light" else "ACID // VOID_V2"
            )
            self._brand_badge.set_palette_colors(
                fill=p.accent,
                border=p.accent_strong if variant == "light" else p.accent,
                fg=p.text_inverse,
                secondary="#77DCE4" if variant == "dark" else "#38BDF8",
                peak="#CEFF18",
                chassis="#0B0D0F",
            )
            self._sync_acid_chrome(True, variant)
            self.setStyleSheet(acid_stylesheet(appearance, variant))
            for plot in self.findChildren(pg.PlotWidget):
                if plot is self.history_overview_plot:
                    continue
                apply_acid_plot_theme(plot, appearance, variant)
            self._apply_history_plot_theme(appearance, acid_variant=variant)
            self.spectrum_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=variant
            )
            self.chroma_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=variant
            )
            self.mixer_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=variant
            )
        else:
            self._sync_acid_chrome(False, None)
            bg, fg, accent = appearance.effective_colors(system_is_dark=self._system_is_dark)
            self._header_pulse.set_theme_color(accent)
            mode = appearance.resolve_theme_mode(system_is_dark=self._system_is_dark)
            muted_col = "#94A3B8" if mode == "dark" else "#475569"
            border_col = "#3A4254" if mode == "dark" else "#CBD5E1"
            self._capture_dot.set_colors(accent, muted_col)
            self._main_tab_bar.set_rail_colors(accent, muted_col)
            self._workspace_rail.set_grip_colors(grip=muted_col, accent=accent, line=border_col)
            self.win_min_btn.set_glyph_colors(fg, fg)
            self.win_max_btn.set_glyph_colors(fg, fg)
            self.win_close_btn.set_glyph_colors(fg, "#FFFFFF")
            set_help_theme(
                bg=bg,
                fg=fg,
                accent=accent,
                border=border_col,
                muted=muted_col,
                is_dark=(mode == "dark"),
                is_acid=False,
            )
            has_custom = bool(appearance.background or appearance.text or appearance.accent)
            badge_prefix = "CUSTOM" if has_custom else "THEME"
            self._skin_badge.setText(f"{badge_prefix} // {appearance.preset.upper()}")
            acc_c = QtGui.QColor(accent)
            luma = (0.299 * acc_c.red() + 0.587 * acc_c.green() + 0.114 * acc_c.blue()) / 255.0
            badge_fg = "#FFFFFF" if luma < 0.55 else "#14161A"
            self._brand_badge.set_palette_colors(
                fill=accent,
                border=accent,
                fg=badge_fg,
                secondary=acc_c.lighter(135).name(),
                peak="#FFFFFF",
                chassis="#14181F" if mode == "dark" else "#1E293B",
            )
            self.setStyleSheet(
                appearance_stylesheet(DARK_STYLESHEET, appearance, system_is_dark=self._system_is_dark)
            )
            for plot in self.findChildren(pg.PlotWidget):
                apply_plot_appearance(plot, appearance, system_is_dark=self._system_is_dark)
            self._apply_history_plot_theme(appearance, acid_variant=None)
            self.spectrum_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=None
            )
            self.chroma_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=None
            )
            self.mixer_widget.apply_theme(
                appearance, system_is_dark=self._system_is_dark, acid_variant=None
            )
        install_focus_animations(self)
        translate_widget_tree(self, appearance.language)
        if self._tray_icon is not None and self._tray_icon.contextMenu() is not None:
            translate_widget_tree(self._tray_icon.contextMenu(), appearance.language)
        # Re-apply Acid telemetry tab/header labels so fixed English + single localized caption stays crisp
        self._sync_acid_chrome(variant in ("light", "dark"), variant)
        if was_visible and saved_geom is not None and saved_geom.isValid() and not self.isMaximized():
            if self.geometry() != saved_geom:
                self.setGeometry(saved_geom)
        self._sync_active_settings_dialog()

    def _sync_active_settings_dialog(self) -> None:
        dlg = getattr(self, "_active_settings_dialog", None)
        if dlg is None:
            return
        try:
            dlg.update_appearance_summary(self.appearance)
            dlg.apply_skin(self.appearance, acid_variant=self._acid_variant or "")
        except RuntimeError:
            self._active_settings_dialog = None

    def _on_analysis_layout_selected(self) -> None:
        layout = self.spectrum_widget.view_combo.currentData()
        if layout != self.appearance.analysis_layout:
            self.apply_appearance(replace(self.appearance, analysis_layout=layout))
            self.appearance_applied.emit()

    def _on_workspace_rail_dragged(self, dy: int) -> None:
        practice = getattr(self.appearance, "layout", "split") == "practice"
        cur_h = max(48, self.history_overview_plot.height())
        target_h = max(48, min(220, cur_h + (dy if practice else -dy)))
        self.history_overview_plot.setMinimumHeight(target_h)
        self.history_overview_plot.setMaximumHeight(max(target_h, target_h + 12))

    def _on_workspace_rail_reset(self) -> None:
        practice = getattr(self.appearance, "layout", "split") == "practice"
        self.history_overview_plot.setMinimumHeight(112 if practice else 56)
        self.history_overview_plot.setMaximumHeight(140 if practice else 70)

    def _apply_workspace_layout(self, layout: str) -> None:
        was_visible = self.isVisible()
        saved_geom = self.geometry() if was_visible else None
        practice = layout == "practice"
        splitter = self._main_splitter
        if practice:
            if splitter.indexOf(self._bottom_dock) != 0:
                splitter.insertWidget(0, self._bottom_dock)
        else:
            if splitter.indexOf(self.tabs) != 0:
                splitter.insertWidget(0, self.tabs)
        self._apply_responsive_layout()
        self.mixer_widget.apply_workspace_layout(layout)
        if was_visible and saved_geom is not None and saved_geom.isValid() and not self.isMaximized():
            if self.geometry() != saved_geom:
                self.setGeometry(saved_geom)

    def open_appearance_dialog(self, parent: QtWidgets.QWidget | None = None) -> None:
        initial = self.appearance
        dialog = AppearanceDialog(
            initial,
            DARK_STYLESHEET,
            parent or self,
            on_preview=self.apply_appearance,
            system_is_dark=self._system_is_dark,
        )
        try:
            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                appearance = dialog.values()
                self.apply_appearance(appearance)
                if appearance != initial:
                    self.appearance_applied.emit()
        finally:
            dialog.setParent(None)
            dialog.deleteLater()

    @property
    def last_verified_ai_probe(self) -> Optional[dict[str, Any]]:
        return self._last_verified_ai_probe

    def set_closing_handler(self, fn) -> None:
        self._closing_handler = fn

    def prepare_for_shutdown(self) -> None:
        """Stop child timers/animations, detach event filters, clear plots, and hide tray before C++ destruction."""
        if getattr(self, "_tearing_down", False):
            return
        self._tearing_down = True

        for w_name in ("_shell_frame", "_topbar_frame"):
            w = getattr(self, w_name, None)
            if _is_qt_valid(w):
                try:
                    w.removeEventFilter(self)
                except RuntimeError:
                    pass

        for anim in list(getattr(self, "__dict__", {}).values()):
            if hasattr(anim, "teardown") and callable(getattr(anim, "teardown")):
                try:
                    anim.teardown()
                except Exception:
                    pass

        for child in self.findChildren(QtWidgets.QDialog):
            if _is_qt_valid(child):
                for helper_attr in ("_focus_ring_animator", "_chrome"):
                    helper = getattr(child, helper_attr, None)
                    if helper is not None and hasattr(helper, "teardown"):
                        try:
                            helper.teardown()
                        except Exception:
                            pass
                try:
                    if hasattr(child, "stop_preview"):
                        child.stop_preview()
                    child.close()
                except Exception:
                    pass

        for timer in self.findChildren(QtCore.QTimer):
            if _is_qt_valid(timer):
                try:
                    timer.stop()
                except RuntimeError:
                    pass
        for anim in self.findChildren(QtCore.QAbstractAnimation):
            if _is_qt_valid(anim):
                try:
                    anim.stop()
                except RuntimeError:
                    pass

        if self._tray_icon is not None:
            if hasattr(self._tray_icon, "setContextMenu"):
                try:
                    self._tray_icon.setContextMenu(None)
                except Exception:
                    pass
            try:
                self._tray_icon.hide()
            except Exception:
                pass

        if self._style_hints_connected:
            app_inst = QtGui.QGuiApplication.instance()
            if app_inst is not None:
                try:
                    app_inst.styleHints().colorSchemeChanged.disconnect(self._on_system_color_scheme_changed)
                except Exception:
                    pass
            self._style_hints_connected = False

        try:
            self.history_overview_plot.getViewBox().sigXRangeChanged.disconnect()
        except Exception:
            pass

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
            if _is_qt_valid(pw):
                try:
                    pw.clear()
                except Exception:
                    pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        want_tray = (
            not self._force_quit
            and bool(getattr(self.appearance, "close_to_tray", True))
            and self._tray_icon is not None
            and self._tray_icon.isVisible()
        )
        if want_tray:
            try:
                want_tray = bool(QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())
            except Exception:
                want_tray = False
        if want_tray:
            app_q = QtWidgets.QApplication.instance()
            if isinstance(app_q, QtWidgets.QApplication):
                app_q.setQuitOnLastWindowClosed(False)
            event.ignore()
            self.hide()
            if not self._tray_notified and self._tray_icon is not None:
                self._tray_notified = True
                try:
                    self._tray_icon.showMessage(
                        "ListenScope",
                        translate_text(
                            "已最小化到系统托盘，双击图标可恢复主窗口（可在「外观与字体」中关闭此项）。",
                            get_current_language(),
                        ),
                        QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                        2500,
                    )
                except Exception:
                    pass
            return

        app_q = QtWidgets.QApplication.instance()
        if isinstance(app_q, QtWidgets.QApplication):
            app_q.setQuitOnLastWindowClosed(True)
        self.prepare_for_shutdown()
        hicons = getattr(self, "_win32_hicons", None)
        if hicons and sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                for h in hicons:
                    if h:
                        user32.DestroyIcon(h)
            except Exception:
                pass
            self._win32_hicons = None
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
        gpus = getattr(report, "gpus", None) or []
        if gpus:
            gpu = gpus[0]
            vram_gb = gpu.total_vram_mb / 1024.0
            chk_text = f"优先 GPU ({gpu.name} · {vram_gb:.0f} GB)"
        else:
            chk_text = "优先 GPU (未检测到可用 NVIDIA GPU)"
        self.ai_gpu_chk.setProperty("_ls_orig_text", chk_text)
        self.ai_gpu_chk.setText(translate_text(chk_text, get_current_language()))
        if auto_sync_gpu_chk:
            self.ai_gpu_chk.setChecked(bool(report.gpu_ai_ready))

    def _set_ab_region_from_ago(self, start_ago: float, end_ago: float) -> None:
        s_ago = max(0.5, min(120.0, float(start_ago)))
        e_ago = max(0.0, min(s_ago - 0.5, float(end_ago)))
        self._show_ab_region(s_ago, e_ago)

    def show_snapped_ab(self, start_ago: float, end_ago: float) -> None:
        self.start_ago_spin.setValue(start_ago)
        self.end_ago_spin.setValue(end_ago)
        self._show_ab_region(start_ago, end_ago)

    def _show_ab_region(self, start_ago: float, end_ago: float) -> None:
        self._syncing_ab_region = True
        try:
            self.ab_region.setRegion((-start_ago, -end_ago))
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

    def zoom_history(self, factor: float) -> None:
        start, end = self.history_overview_plot.viewRange()[0]
        center = (start + end) / 2
        span = max(0.25, min(120.0, (end - start) * factor))
        left = min(-span, max(-120.0, center - span / 2))
        self.history_overview_plot.setXRange(left, left + span, padding=0)

    def update_history_overview(
        self, mins: np.ndarray, maxs: np.ndarray, avail_sec: float, *, end_ago: float = 0,
    ) -> None:
        if avail_sec <= 0.0 or mins.size == 0 or maxs.size == 0:
            if not self._last_hist_empty:
                self._hist_max_curve.setData([], [])
                self._hist_min_curve.setData([], [])
                self._last_hist_empty = True
            return
        self._last_hist_empty = False
        n = int(mins.shape[0])
        key = (n, round(float(avail_sec), 4), round(float(end_ago), 4))
        if self._hist_x_buf is None or self._hist_x_key != key:
            self._hist_x_buf = np.linspace(-end_ago - avail_sec, -end_ago, n, dtype=np.float32)
            self._hist_x_key = key
        self._hist_max_curve.setData(self._hist_x_buf, np.asarray(maxs, dtype=np.float32))
        self._hist_min_curve.setData(self._hist_x_buf, np.asarray(mins, dtype=np.float32))

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
        is_acid = self._acid_variant in ("light", "dark")
        lang = get_current_language()
        self.capture_btn.blockSignals(True)
        self.capture_btn.setChecked(active)
        self._capture_dot.set_active(active)
        if is_acid:
            self.capture_btn.setText(
                tr_telemetry("CAPTURE_ACTIVE", lang, zh="停止捕获", ko="캡처 중지", ja="キャプチャ停止")
                if active
                else tr_telemetry("CAPTURE_START", lang, zh="开始捕获", ko="캡처 시작", ja="キャプチャ開始")
            )
        else:
            self.capture_btn.setText(translate_text("停止捕获" if active else "开始捕获", lang))
        self.capture_btn.blockSignals(False)
        if not active:
            self._last_capture_banner = None
            set_widget_tone(self.capture_status_lbl, "info")
            _set_label_cached(self.capture_status_lbl, "未捕获")
            self._last_capture_status_txt = self.capture_status_lbl.text()

    def dismiss_banner(self) -> None:
        self._last_capture_banner = None
        if self._notice_bar.isVisible():
            self._notice_bar.setVisible(False)
        if self.notice_banner.isVisible():
            self.notice_banner.setVisible(False)
        _set_label_cached(self.notice_banner, "")

    def show_banner_message(self, text: str, *, tone: Optional[str] = None) -> None:
        if not text:
            if self._notice_bar.isVisible():
                self._notice_bar.setVisible(False)
            if self.notice_banner.isVisible():
                self.notice_banner.setVisible(False)
            _set_label_cached(self.notice_banner, "")
        else:
            resolved_tone = tone if tone is not None else _infer_banner_tone(text)
            set_widget_tone(self._notice_bar, resolved_tone)
            set_widget_tone(self.notice_banner, resolved_tone)
            _set_label_cached(self.notice_banner, text)
            if not self.notice_banner.isVisible():
                self.notice_banner.setVisible(True)
            if not self._notice_bar.isVisible():
                self._notice_bar.setVisible(True)

    def update_capture_stats(self, stats: CaptureStats, ring_available_sec: float) -> None:
        if self.capture_btn.isChecked() != stats.is_running:
            self.set_capture_active_ui(stats.is_running)
        lang = get_current_language()
        silence = "静音" if stats.is_silent else "有信号"
        if stats.mode == CaptureMode.SYSTEM_LOOPBACK:
            tone = "warn"
            prefix = "[混入警告] "
        elif stats.is_running and not stats.is_silent:
            tone = "ok"
            prefix = ""
        else:
            tone = "info"
            prefix = ""
        set_widget_tone(self.capture_status_lbl, tone)
        raw_status = f"{prefix}{silence} · {stats.rms_dbfs:.1f} dBFS" if stats.is_running else "未捕获"
        status_txt = translate_text(raw_status, lang)
        if status_txt != self._last_capture_status_txt:
            self.capture_status_lbl.setProperty("_ls_orig_text", raw_status)
            self.capture_status_lbl.setText(status_txt)
            self._last_capture_status_txt = status_txt
        raw_cov = f"已缓冲: {ring_available_sec:.1f} / 120.0 s"
        cov_txt = translate_text(raw_cov, lang)
        if cov_txt != self._last_coverage_txt:
            self.history_coverage_lbl.setProperty("_ls_orig_text", raw_cov)
            self.history_coverage_lbl.setText(cov_txt)
            self._last_coverage_txt = cov_txt

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
        if self._static_lock:
            return
        self.spectrum_widget.update_analysis(snap, spectrogram=spectrogram)
        self.chroma_widget.update_analysis(snap, chroma_history=chroma_history)

    def update_ai_progress(self, prog: AIJobProgress) -> None:
        txt = f"AI: {prog.state.value} ({int(round(prog.progress * 100))}%)"
        if txt != self._last_ai_badge_txt:
            self.ai_status_badge.setText(txt)
            self._last_ai_badge_txt = txt
        set_widget_tone(self.ai_status_badge, "info")
        self.mixer_widget.update_ai_progress(prog)

    def handle_ai_result(self, res: AIJobResult) -> None:
        txt = f"AI: {res.state.value}"
        if txt != self._last_ai_badge_txt:
            self.ai_status_badge.setText(txt)
            self._last_ai_badge_txt = txt
        if res.state == AIJobState.COMPLETED:
            tone = "ok"
        elif res.state in (AIJobState.FAILED, AIJobState.REJECTED_RESOURCE):
            tone = "error"
        elif res.state in (AIJobState.CANCELED, AIJobState.EMERGENCY_STOPPED):
            tone = "warn"
        else:
            tone = "info"
        set_widget_tone(self.ai_status_badge, tone)
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
        initial_appearance = self.appearance
        dlg = SettingsDialog(
            self._hardware_report,
            self._resource_limits,
            self._ai_config,
            ai_python_executable=self._ai_python_executable,
            midi_python_executable=self._midi_python_executable,
            appearance=self.appearance,
            acid_variant=self._acid_variant or "",
            parent=self,
        )

        def edit_appearance(parent: QtWidgets.QWidget) -> None:
            self.open_appearance_dialog(parent)
            dlg.update_appearance_summary(self.appearance)
            dlg.apply_skin(self.appearance, acid_variant=self._acid_variant or "")

        def on_quick_appearance(updated_app: Appearance) -> None:
            self.apply_appearance(updated_app)
            self.appearance_applied.emit()

        def on_bootstrap_runtimes_ready(ai_py: str, midi_py: str) -> None:
            if ai_py:
                self._ai_python_executable = ai_py
            if midi_py:
                self._midi_python_executable = midi_py

        dlg.appearance_requested.connect(edit_appearance)
        dlg.appearance_changed.connect(on_quick_appearance)
        dlg.restart_requested.connect(self.restart_requested.emit)
        dlg.bootstrap_runtimes_ready.connect(on_bootstrap_runtimes_ready)
        if focus_midi:
            QtCore.QTimer.singleShot(0, dlg.focus_midi)
        self._active_settings_dialog = dlg
        try:
            accepted = dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
            if accepted:
                if dlg.updated_appearance != self.appearance:
                    self.apply_appearance(dlg.updated_appearance)
                    self.appearance_applied.emit()
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
            else:
                if self.appearance != initial_appearance:
                    self.apply_appearance(initial_appearance)
                    self.appearance_applied.emit()
        finally:
            self._active_settings_dialog = None
            dlg.setParent(None)
            dlg.deleteLater()

