"""Native Qt appearance: Dark/Light/Follow-System palettes, OS font scanning, live preview, and no QGraphicsEffect."""

from __future__ import annotations

import re
from typing import Callable, Optional

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import (
    ANALYSIS_LAYOUTS,
    DEFAULT_ANALYSIS_LAYOUT,
    Appearance,
    LAYOUTS,
    PRESETS,
    THEME_MODES,
)
from ui.help_badge import HelpBadge
from ui.acid_style import (
    acid_stylesheet,
    is_acid_eligible,
    resolve_acid_variant,
)

_CACHED_OS_FONTS: Optional[tuple[str, ...]] = None


def list_installed_font_families() -> tuple[str, ...]:
    """Scan installed OS font families once per session for smooth dialog opening."""
    global _CACHED_OS_FONTS
    if _CACHED_OS_FONTS is None:
        try:
            families = sorted({f.strip() for f in QtGui.QFontDatabase.families() if str(f).strip()}, key=str.casefold)
        except Exception:
            families = []
        _CACHED_OS_FONTS = tuple(families)
    return _CACHED_OS_FONTS


def detect_system_is_dark(app: Optional[QtGui.QGuiApplication] = None) -> bool:
    """Inspect Qt 6.8 QStyleHints.colorScheme() safely without platform-specific hacks."""
    inst = app if app is not None else QtGui.QGuiApplication.instance()
    if inst is not None:
        try:
            scheme = inst.styleHints().colorScheme()
            if scheme == QtCore.Qt.ColorScheme.Light:
                return False
            if scheme == QtCore.Qt.ColorScheme.Dark:
                return True
        except Exception:
            pass
    return True


def set_widget_tone(widget: QtWidgets.QWidget, tone: str) -> None:
    """Update dynamic `[tone=...]` property only when it changes (avoids expensive repolish churn)."""
    norm = str(tone or "info")
    if widget.property("tone") == norm:
        return
    widget.setProperty("tone", norm)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def _blend(left: str, right: str, amount: float) -> str:
    a, b = QtGui.QColor(left), QtGui.QColor(right)
    return QtGui.QColor(
        *(round(x + (y - x) * amount) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3]))
    ).name()


def _semantic_palette(mode: str, background: str, foreground: str, accent: str) -> dict[str, str]:
    if mode == "light":
        return {
            "ok_bg": _blend(background, "#15803D", 0.11),
            "ok_fg": "#14532D",
            "ok_bd": "#16A34A",
            "warn_bg": _blend(background, "#D97706", 0.13),
            "warn_fg": "#92400E",
            "warn_bd": "#D97706",
            "err_bg": _blend(background, "#DC2626", 0.12),
            "err_fg": "#991B1B",
            "err_bd": "#DC2626",
            "info_bg": _blend(background, accent, 0.09),
            "info_fg": _blend(foreground, accent, 0.35),
            "warn_hero": "#B45309",
            "err_text": "#B91C1C",
            "muted": _blend(background, foreground, 0.56),
            "check_fg": "#FFFFFF",
        }
    return {
        "ok_bg": _blend(background, "#2EC27E", 0.22),
        "ok_fg": _blend("#7EE2B8", accent, 0.25),
        "ok_bd": "#2EC27E",
        "warn_bg": _blend(background, "#F5A623", 0.20),
        "warn_fg": "#FFD166",
        "warn_bd": "#F5A623",
        "err_bg": _blend(background, "#E03E3E", 0.26),
        "err_fg": "#FF9B9B",
        "err_bd": "#E03E3E",
        "info_bg": _blend(background, foreground, 0.055),
        "info_fg": _blend(foreground, accent, 0.35),
        "warn_hero": _blend(foreground, "#FFD166", 0.72),
        "err_text": "#FF7B7B",
        "muted": _blend(background, foreground, 0.68),
        "check_fg": "#14161A",
    }


def appearance_stylesheet(
    base: str,
    appearance: Appearance,
    *,
    system_is_dark: Optional[bool] = None,
) -> str:
    mode = appearance.resolve_theme_mode(system_is_dark=system_is_dark)
    background, foreground, accent = appearance.effective_colors(system_is_dark=system_is_dark)
    is_light = mode == "light"
    surface = _blend(background, foreground, 0.045 if is_light else 0.055)
    rim = _blend(background, foreground, 0.22 if is_light else 0.18)
    sunk = _blend(background, foreground, 0.025 if is_light else 0.035)
    raised = _blend(background, foreground, 0.075 if is_light else 0.085)
    hover = _blend(background, foreground, 0.12 if is_light else 0.14)
    checked_bg = _blend(background, accent, 0.22 if is_light else 0.32)
    sel_bg = _blend(background, accent, 0.16 if is_light else 0.15)
    subtle_fg = _blend(background, foreground, 0.78 if is_light else 0.82)
    disabled_fg = _blend(background, foreground, 0.45 if is_light else 0.49)
    sem = _semantic_palette(mode, background, foreground, accent)

    colors = {
        "#14161A": background,
        "#E6EAF0": foreground,
        "#7EE2B8": accent,
        "#2C323C": rim,
        "#303742": rim,
        "#38414E": rim,
        "#B4BECB": subtle_fg,
        "#6B7480": disabled_fg,
        "#1C2026": surface,
        "#1A1E24": sunk,
        "#1B1E24": surface,
        "#232830": raised,
        "#2E3540": hover,
        "#28303B": sel_bg,
        "#1F6FEB": checked_bg,
        "#4EA8DE": accent,
    }
    qss = re.sub(r"#[0-9A-F]{6}", lambda match: colors.get(match[0], match[0]), base)
    qss = qss.replace("font-size: 12px", f"font-size: {appearance.font_size}px")
    if appearance.font_family:
        qss = qss.replace(
            'font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;',
            f'font-family: "{appearance.font_family}", "Segoe UI", "Microsoft YaHei UI", sans-serif;',
        )

    btn_checked_fg = foreground if is_light else foreground
    qss += f"""
QToolTip {{
    background-color: {surface};
    color: {foreground};
    border: 1px solid {rim};
    padding: 5px 8px;
    border-radius: 5px;
}}
QComboBox QAbstractItemView {{
    background-color: {surface};
    color: {foreground};
    border: 1px solid {rim};
    selection-background-color: {sel_bg};
    selection-color: {foreground};
}}
QTableWidget {{
    gridline-color: {hover};
    alternate-background-color: {_blend(background, foreground, 0.03)};
    selection-background-color: {sel_bg};
    selection-color: {foreground};
}}
QPushButton:checked {{ color: {btn_checked_fg}; }}
QGroupBox, QFrame[trackCard=true], QFrame#practiceCard {{ background: {surface}; }}
QFrame[trackCard=true], QFrame#practiceCard {{ border: 1px solid {rim}; border-radius: 7px; }}
QGroupBox QLabel, QFrame[trackCard=true] QLabel, QFrame#practiceCard QLabel {{ background: transparent; }}
QPushButton#analysisAction:enabled {{ background: {sel_bg}; border-color: {accent}; font-weight: 600; color: {foreground}; }}
QPushButton#analysisAction:hover:enabled {{ background: {checked_bg}; }}
QPushButton#analysisAction:checked:enabled {{ background: {checked_bg}; border-color: {accent}; }}
QPushButton#emergencyStopBtn {{
    background-color: #B81D24;
    color: #FFFFFF;
    border: 1px solid #FF6B6B;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 5px;
}}
QPushButton#emergencyStopBtn:hover {{ background-color: #D9262E; }}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTableWidget:focus, QToolButton#helpBadge:focus {{
    border: 1px solid {accent};
}}
QSplitter::handle {{ background: {sunk}; border-radius: 1px; }}
QSplitter::handle:hover {{ background: {accent}; }}
QHeaderView::section {{
    background: {surface};
    color: {subtle_fg};
    border: 0px;
    border-bottom: 1px solid {rim};
    padding: 2px 4px;
    font-weight: 600;
}}
QTableWidget#practiceTable {{
    background-color: {sunk};
    alternate-background-color: {_blend(background, foreground, 0.04)};
    border: 1px solid {rim};
    border-radius: 7px;
    gridline-color: {hover};
    selection-background-color: {sel_bg};
    selection-color: {foreground};
    outline: 0;
}}
QTableWidget#practiceTable::item,
QTableWidget#practiceTable::item:selected,
QTableWidget#practiceTable::item:focus,
QTableWidget#practiceTable::item:selected:focus,
QTableWidget#practiceTable::item:hover {{
    padding: 5px 10px;
    margin: 0px;
    border: 0px;
    outline: 0;
}}
QTableWidget#practiceTable::item:selected,
QTableWidget#practiceTable::item:selected:focus {{
    background-color: {sel_bg};
    color: {foreground};
}}
QTableWidget#practiceTable QScrollBar:vertical {{
    background: {sunk};
    width: 8px;
    margin: 2px;
    border-radius: 4px;
}}
QTableWidget#practiceTable QScrollBar::handle:vertical {{
    background: {rim};
    border-radius: 4px;
    min-height: 20px;
}}
QTableWidget#practiceTable QHeaderView::section {{
    background: {surface};
    color: {subtle_fg};
    border: 0px;
    border-bottom: 1px solid {rim};
    border-right: 1px solid {sunk};
    padding: 5px 10px;
    font-weight: 600;
}}
QLabel#practiceSectionTitle {{ color: {accent}; font-weight: 600; }}
QLabel#practiceMeta {{ color: {subtle_fg}; }}
QLabel#practicePill {{
    background: {sunk};
    border: 1px solid {rim};
    border-radius: 5px;
    padding: 4px 9px;
    color: {subtle_fg};
}}
QLabel#practiceConvention {{
    background: {sunk};
    border: 1px solid {rim};
    border-radius: 6px;
    padding: 6px 10px;
    color: {subtle_fg};
}}
QLabel#practiceFeedback {{ color: {subtle_fg}; font-size: {max(10, appearance.font_size - 1)}px; }}
QLabel#practiceFeedback[tone="ok"] {{ color: {sem["ok_fg"] if is_light else accent}; font-weight: 600; }}
QLabel#practiceFeedback[tone="error"] {{ color: {sem["err_text"]}; font-weight: 600; }}

QToolButton#helpBadge {{
    background: {surface};
    color: {sem["muted"]};
    border: 1px solid {rim};
    border-radius: 9px;
    padding: 0px;
    font-size: {max(10, min(13, appearance.font_size - 1))}px;
    font-weight: 700;
}}
QToolButton#helpBadge:hover {{
    background: {sel_bg};
    color: {foreground};
    border-color: {accent};
}}

QLabel#mutedCaption, QLabel#stemMetaDuration {{ color: {sem["muted"]}; font-size: {max(10, appearance.font_size - 1)}px; }}
QLabel#stemTrackTitle {{ color: {foreground}; font-weight: 700; font-size: {appearance.font_size + 1}px; }}

QLabel#statusBadge, QLabel#captureStatus, QLabel#aiStatusBadge, QLabel#bannerNotice {{
    border-radius: 5px;
    padding: 3px 8px;
    background: {surface};
    color: {foreground};
    border: 1px solid {rim};
}}
QLabel#statusBadge[tone="normal"], QLabel#statusBadge[tone="ok"], QLabel#bannerNotice[tone="ok"], QLabel#captureStatus[tone="ok"], QLabel#aiStatusBadge[tone="ok"] {{
    background: {sem["ok_bg"]};
    color: {sem["ok_fg"]};
    border: 1px solid {sem["ok_bd"]};
    font-weight: 600;
}}
QLabel#statusBadge[tone="warn"], QLabel#bannerNotice[tone="warn"], QLabel#captureStatus[tone="warn"], QLabel#aiStatusBadge[tone="warn"] {{
    background: {sem["warn_bg"]};
    color: {sem["warn_fg"]};
    border: 1px solid {sem["warn_bd"]};
    font-weight: 600;
}}
QLabel#statusBadge[tone="error"], QLabel#bannerNotice[tone="error"], QLabel#captureStatus[tone="error"], QLabel#aiStatusBadge[tone="error"] {{
    background: {sem["err_bg"]};
    color: {sem["err_fg"]};
    border: 1px solid {sem["err_bd"]};
    font-weight: 700;
}}
QLabel#bannerNotice[tone="info"], QLabel#aiStatusBadge[tone="info"], QLabel#captureStatus[tone="info"] {{
    background: {sem["info_bg"]};
    color: {sem["info_fg"]};
    border: 1px solid {rim};
}}
QGroupBox#oomBanner {{
    background: {sem["warn_bg"]};
    color: {sem["warn_fg"]};
    border: 1px solid {sem["warn_bd"]};
    border-radius: 6px;
    padding-top: 14px;
}}

QLabel#chromaPrimary {{ font-size: {appearance.font_size + 12}px; font-weight: 700; color: {accent}; }}
QLabel#chromaSecondaryHero {{ font-size: {appearance.font_size + 10}px; font-weight: 700; color: {foreground}; }}
QLabel#chromaWarnHero {{ font-size: {appearance.font_size + 10}px; font-weight: 700; color: {sem["warn_hero"]}; }}
QLabel#chromaSubtle {{ color: {subtle_fg}; font-weight: 600; }}
QLabel#chromaSubtle[tone="warn"] {{ color: {sem["warn_hero"]}; font-weight: 700; }}
QLabel#chromaCaption {{ color: {sem["muted"]}; font-size: {max(10, appearance.font_size - 1)}px; }}
QLabel#chromaCaption[tone="warn"] {{ color: {sem["warn_hero"]}; font-weight: 600; }}
QLabel#chromaProgression {{
    padding: 5px 10px;
    background: {sunk};
    border: 1px solid {rim};
    border-radius: 6px;
    color: {foreground};
    font-weight: 600;
}}
QLabel#chromaTrackStatus {{
    padding: 4px 10px;
    background: {sunk};
    border: 1px solid {hover};
    border-radius: 5px;
    color: {sem["muted"]};
    font-size: {max(10, appearance.font_size - 1)}px;
}}
QLabel#chromaTrackStatus[tone="warn"] {{
    background: {sem["warn_bg"]};
    color: {sem["warn_fg"]};
    border-color: {sem["warn_bd"]};
    font-weight: 600;
}}
QLabel#settingsHeading {{ font-size: {appearance.font_size + 12}px; font-weight: 700; }}
QLabel#analysisHeading {{ font-size: {appearance.font_size + 7}px; font-weight: 700; }}
QFrame#analysisMetric {{ background: {surface}; border: 1px solid {rim}; border-radius: 8px; }}
QFrame#analysisMetric QLabel {{ background: transparent; }}
QFrame#analysisChart {{ background: {surface}; border: 1px solid {rim}; border-radius: 7px; }}
QFrame#analysisChart QLabel {{ background: transparent; }}
QLabel#analysisChartHeading {{ font-weight: 600; }}
QLabel#analysisCaption {{ color: {subtle_fg}; }}
QLabel#analysisPitch {{ color: {accent}; font-size: {appearance.font_size + 15}px; font-weight: 700; }}
QLabel#analysisValue {{ font-size: {appearance.font_size + 5}px; font-weight: 600; }}
QProgressBar#analysisLevel {{ background: {sunk}; border: 0; border-radius: 2px; }}
QProgressBar#analysisLevel::chunk {{ background: {accent}; border-radius: 2px; }}
QLabel#settingsPageHeading {{ font-size: {appearance.font_size + 6}px; font-weight: 700; }}
QLabel#settingsSubtitle {{ color: {subtle_fg}; }}
QWidget#settingsNavigation {{ background: {surface}; border: 1px solid {rim}; border-radius: 9px; }}
QPushButton#settingsNavButton {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    text-align: left; padding: 6px 8px;
}}
QPushButton#settingsNavButton:hover {{ background: {hover}; }}
QPushButton#settingsNavButton:checked {{
    background: {sel_bg}; border-left: 3px solid {accent}; font-weight: 700;
}}
QPushButton#settingsNavButton:focus {{ border-color: {accent}; }}
QPushButton#settingsSave {{
    background: {sel_bg}; border: 1px solid {accent};
    font-weight: 700; padding: 7px 18px;
}}
QPushButton#settingsSave:hover, QPushButton#settingsSave:focus {{ background: {checked_bg}; }}
QFrame#acidTopbar {{
    background: {surface};
    border: 1px solid {rim};
    border-left: 3px solid {accent};
    border-radius: 7px;
}}
QFrame#telemetryHeader {{ background: transparent; }}
QFrame#telemetryHeader[divider="true"] {{ border-bottom: 1px solid {hover}; }}
QFrame#acidTopbar QLabel, QFrame[acidCard="true"] QLabel, QFrame#telemetryHeader QLabel {{
    background: transparent;
}}
QLabel#telemetryEyebrow {{
    color: {accent};
    font-size: {max(9, appearance.font_size - 2)}px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#telemetryTitle, QLabel#acidHeroTitle {{
    color: {foreground};
    font-size: {appearance.font_size + 2}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#acidEchoTitle, QLabel#acidHeroSub, QLabel#acidMicroTag {{
    color: {subtle_fg};
    background: transparent;
}}
QLabel#chromaEcho {{
    color: {sem["muted"]};
    font-weight: 700;
}}
QLabel#telemetryPill {{
    background: {sunk};
    color: {subtle_fg};
    border: 1px solid {rim};
    border-radius: 4px;
    padding: 2px 7px;
    font-size: {max(10, appearance.font_size - 1)}px;
    font-weight: 600;
}}
QFrame[acidCard="true"] {{
    background: {surface};
    border: 1px solid {rim};
    border-radius: 7px;
}}
QFrame#acidDivider {{
    background: {rim};
    min-height: 1px;
    max-height: 1px;
}}
QPushButton#acidPrimaryBtn:enabled {{
    background: {sel_bg};
    border-color: {accent};
    font-weight: 600;
    color: {foreground};
}}
QPushButton#acidPrimaryBtn:hover:enabled {{ background: {checked_bg}; }}
QPushButton#acidPrimaryBtn:checked:enabled {{
    background: {checked_bg};
    border-color: {accent};
}}
QPlainTextEdit#diagnosticLogStream {{
    background-color: {sunk};
    color: {foreground};
    border: 1px solid {rim};
    font-family: "Cascadia Code", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: {max(10, appearance.font_size - 1)}px;
}}
QLabel#monoTelemetry {{ font-weight: 600; color: {foreground}; }}
"""
    if appearance.scope == "off":
        return qss

    # These fills are Qt gradients. Their source is the theme, independent of the pixels below.
    glow = _blend(surface, accent, appearance.strength / 260)
    edge = _blend(rim, accent, appearance.dispersion / 100)
    fade = 0.15 + 0.7 * appearance.softness / 100
    targets = "QTabBar::tab:selected, QPushButton#appearanceEntry"
    if appearance.scope == "panels":
        targets += ", QGroupBox, QFrame[trackCard=true]"
    return qss + f"""
{targets} {{
    background: qlineargradient(x1:0, y1:0, x2:0.85, y2:1,
        stop:0 {glow}, stop:{fade} {surface}, stop:1 {background});
    border: 1px solid {edge};
}}
"""


def apply_plot_appearance(
    plot: pg.PlotWidget,
    appearance: Appearance,
    *,
    system_is_dark: Optional[bool] = None,
) -> None:
    background, foreground, _ = appearance.effective_colors(system_is_dark=system_is_dark)
    plot.setBackground(background)
    axis_color = _blend(background, foreground, 0.72)
    base_font = QtGui.QFont(appearance.font_family) if appearance.font_family else QtGui.QFont(QtWidgets.QApplication.font())
    base_font.setPixelSize(appearance.font_size)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=foreground, family=base_font.family(), size=f"{appearance.font_size}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(base_font)
        axis.setPen(_blend(background, foreground, 0.45))
        axis.setTextPen(axis_color)


class AppearanceDialog(QtWidgets.QDialog):
    """Preview theme, Dark/Light/Follow-System mode, OS font/size, and layout live with safe revert on cancel."""

    def __init__(
        self,
        appearance: Appearance,
        base_stylesheet: str,
        parent: QtWidgets.QWidget | None = None,
        *,
        on_preview: Optional[Callable[[Appearance], None]] = None,
        system_is_dark: Optional[bool] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("外观主题")
        self._base_stylesheet = base_stylesheet
        self._initial_appearance = appearance
        self._on_preview = on_preview
        self._system_is_dark = system_is_dark

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        presets = QtWidgets.QHBoxLayout()
        self._presets = QtWidgets.QButtonGroup(self)
        for key, (label, *_colors) in PRESETS.items():
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            self._presets.addButton(button)
            button.clicked.connect(lambda _checked, key=key: self._apply_preset(key))
            button.setProperty("preset", key)
            if key == "acid_telemetry":
                button.setToolTip(
                    "酸性遥测高对比工业视觉风格：45° 切角标识、双语遥测标题栏与精密平面网格；"
                    "配合上方「黑夜 / 白天 / 跟随系统」切换酸性暗夜与临床浅色，选中后主窗口顶栏也可一键切换。"
                )
            presets.addWidget(button)
        root.addLayout(presets)

        form = QtWidgets.QFormLayout()
        form.setVerticalSpacing(8)

        # Theme mode: Dark / Light / Follow System
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(6)
        self._theme_modes = QtWidgets.QButtonGroup(self)
        self._theme_mode_buttons: dict[str, QtWidgets.QPushButton] = {}
        for mode_key, mode_label in THEME_MODES.items():
            btn = QtWidgets.QPushButton(mode_label)
            btn.setCheckable(True)
            btn.setProperty("themeMode", mode_key)
            btn.clicked.connect(lambda _checked, _k=mode_key: self._on_control_changed())
            self._theme_modes.addButton(btn)
            self._theme_mode_buttons[mode_key] = btn
            mode_row.addWidget(btn)
        mode_row.addWidget(
            HelpBadge(
                "明暗主题与跟随系统",
                "「黑夜」与「白天」分别使用匹配的高对比深/浅色调板；「跟随系统」会实时侦测 Windows 系统深浅色切换并自动更新界面与图表。",
            )
        )
        form.addRow("主题模式", mode_row)

        self._layout = QtWidgets.QComboBox()
        for key, (label, _description) in LAYOUTS.items():
            self._layout.addItem(label, key)
        self._layout.currentIndexChanged.connect(self._on_control_changed)
        form.addRow("界面布局", self._layout)

        self._layout_hint = QtWidgets.QLabel()
        self._layout_hint.setWordWrap(True)
        self._layout_hint.setObjectName("mutedCaption")
        form.addRow("", self._layout_hint)

        self._analysis_layout = QtWidgets.QComboBox()
        for key, label in ANALYSIS_LAYOUTS.items():
            self._analysis_layout.addItem(f"{label}（默认）" if key == DEFAULT_ANALYSIS_LAYOUT else label, key)
        self._analysis_layout.currentIndexChanged.connect(self._on_control_changed)
        form.addRow("实时分析布局", self._analysis_layout)

        # OS installed font scanner + font size
        font_row = QtWidgets.QHBoxLayout()
        font_row.setSpacing(8)
        self._font_family = QtWidgets.QComboBox()
        self._font_family.setMinimumWidth(220)
        self._font_family.addItem("默认系统字体 (Segoe UI / 微软雅黑)", "")
        for family in list_installed_font_families():
            self._font_family.addItem(family, family)
        self._font_family.setAccessibleName("界面字体")
        self._font_family.currentIndexChanged.connect(self._on_control_changed)

        self._font = QtWidgets.QSpinBox()
        self._font.setRange(11, 20)
        self._font.setSuffix(" px")
        self._font.setAccessibleName("字号")
        self._font.valueChanged.connect(self._on_control_changed)

        font_row.addWidget(self._font_family, 1)
        font_row.addWidget(self._font)
        font_row.addWidget(
            HelpBadge(
                "系统字体扫描与实时预览",
                "自动扫描本机已安装的字体。勾选「实时预览」后，调整字体、字号或明暗模式时主界面会同步刷新；点「取消」会安全恢复原样。",
            )
        )
        form.addRow("字体与大小", font_row)

        self._colors: dict[str, QtWidgets.QLineEdit] = {}
        for key, label in (("background", "背景色"), ("text", "字色"), ("accent", "强调色")):
            row = QtWidgets.QHBoxLayout()
            field = QtWidgets.QLineEdit()
            field.setPlaceholderText("使用预设颜色")
            field.setMaxLength(7)
            field.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"(#[0-9a-fA-F]{6})?"), field))
            field.textChanged.connect(self._on_control_changed)
            picker = QtWidgets.QPushButton("选色")
            picker.clicked.connect(lambda _checked, key=key: self._pick_color(key))
            row.addWidget(field, 1)
            row.addWidget(picker)
            self._colors[key] = field
            form.addRow(label, row)
        root.addLayout(form)

        glass = QtWidgets.QGroupBox("液态玻璃卡片")
        optics = QtWidgets.QFormLayout(glass)
        self._scope = QtWidgets.QComboBox()
        for label, key in (("仅悬浮小件（推荐）", "floating"), ("全部面板", "panels"), ("关闭光学高光", "off")):
            self._scope.addItem(label, key)
        self._scope.currentIndexChanged.connect(self._on_control_changed)
        optics.addRow("光学效果范围", self._scope)
        self._sliders: dict[str, QtWidgets.QSlider] = {}
        for key, label in (("strength", "折射观感"), ("softness", "玻璃柔化"), ("dispersion", "边缘色散观感")):
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.valueChanged.connect(self._on_control_changed)
            self._sliders[key] = slider
            optics.addRow(label, slider)
        root.addWidget(glass)

        hint_row = QtWidgets.QHBoxLayout()
        hint = QtWidgets.QLabel("玻璃材质使用渐变模拟，不采样背景像素。")
        hint.setWordWrap(True)
        hint.setObjectName("mutedCaption")
        self._live_preview_chk = QtWidgets.QCheckBox("实时预览主界面")
        self._live_preview_chk.setChecked(self._on_preview is not None)
        self._live_preview_chk.toggled.connect(self._on_live_preview_toggled)
        hint_row.addWidget(hint, 1)
        hint_row.addWidget(self._live_preview_chk)
        root.addLayout(hint_row)

        self._sample = QtWidgets.QGroupBox("外观预览")
        preview = QtWidgets.QHBoxLayout(self._sample)
        preview.addWidget(QtWidgets.QLabel("实时分析 · 音符 / 和弦"), 1)
        action = QtWidgets.QPushButton("A/B 循环")
        action.setObjectName("appearanceEntry")
        action.setCheckable(True)
        action.setChecked(True)
        action.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        action.clicked.connect(lambda: action.setChecked(True))
        preview.addWidget(action)
        root.addWidget(self._sample)

        footer = QtWidgets.QHBoxLayout()
        self._reset_btn = QtWidgets.QPushButton("恢复默认")
        self._reset_btn.setToolTip("一键将主题模式、预设配色、字体、字号与布局恢复为出厂默认值")
        self._reset_btn.clicked.connect(self.reset_to_defaults)
        footer.addWidget(self._reset_btn)
        footer.addStretch(1)

        self._buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("保存")
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        footer.addWidget(self._buttons)
        root.addLayout(footer)

        self.setMinimumWidth(540)
        self._show_values(appearance, emit_preview=False)

    def _apply_preset(self, key: str) -> None:
        current = self.values()
        updated = Appearance(
            preset=key,
            font_size=current.font_size,
            background="",
            text="",
            accent="",
            scope="floating" if key == "lenso" else "off",
            strength=current.strength,
            softness=current.softness,
            dispersion=current.dispersion,
            layout=current.layout,
            analysis_layout=current.analysis_layout,
            theme_mode=current.theme_mode,
            font_family=current.font_family,
        )
        self._show_values(updated)

    def reset_to_defaults(self) -> None:
        self._show_values(Appearance())

    def values(self) -> Appearance:
        checked_preset = self._presets.checkedButton()
        checked_mode = self._theme_modes.checkedButton()
        return Appearance.from_mapping({
            "preset": checked_preset.property("preset") if checked_preset else "classic",
            "theme_mode": checked_mode.property("themeMode") if checked_mode else "dark",
            "font_family": self._font_family.currentData() or "",
            "font_size": self._font.value(),
            "scope": self._scope.currentData(),
            "layout": self._layout.currentData(),
            "analysis_layout": self._analysis_layout.currentData(),
            **{key: field.text() for key, field in self._colors.items()},
            **{key: slider.value() for key, slider in self._sliders.items()},
        })

    def _show_values(self, values: Appearance, *, emit_preview: bool = True) -> None:
        controls = [
            self._layout,
            self._analysis_layout,
            self._font_family,
            self._font,
            self._scope,
            *self._colors.values(),
            *self._sliders.values(),
        ]
        blockers = [QtCore.QSignalBlocker(widget) for widget in controls]
        for button in self._presets.buttons():
            button.setChecked(button.property("preset") == values.preset)
        for mode_key, btn in self._theme_mode_buttons.items():
            btn.setChecked(mode_key == values.theme_mode)
        self._font.setValue(values.font_size)
        font_idx = self._font_family.findData(values.font_family)
        if font_idx < 0 and values.font_family:
            self._font_family.addItem(values.font_family, values.font_family)
            font_idx = self._font_family.findData(values.font_family)
        self._font_family.setCurrentIndex(max(0, font_idx))
        self._layout.setCurrentIndex(max(0, self._layout.findData(values.layout)))
        self._analysis_layout.setCurrentIndex(max(0, self._analysis_layout.findData(values.analysis_layout)))
        self._scope.setCurrentIndex(max(0, self._scope.findData(values.scope)))
        for key, field in self._colors.items():
            field.setText(getattr(values, key))
        for key, slider in self._sliders.items():
            slider.setValue(getattr(values, key))
        del blockers
        self._refresh_sample(emit_preview=emit_preview)

    def _on_live_preview_toggled(self, checked: bool) -> None:
        if self._on_preview is None:
            return
        if checked:
            self._on_preview(self.values())
        else:
            self._on_preview(self._initial_appearance)

    def _on_control_changed(self, *_args) -> None:
        self._refresh_sample(emit_preview=True)

    def _refresh_sample(self, *, emit_preview: bool = True) -> None:
        appearance = self.values()
        self._layout_hint.setText(LAYOUTS[appearance.layout][1])
        for slider in self._sliders.values():
            slider.setEnabled(appearance.scope != "off")
            slider.setToolTip(f"{slider.value()}%")
        if is_acid_eligible(appearance):
            variant = resolve_acid_variant(appearance, system_is_dark=self._system_is_dark) or "dark"
            sample_qss = acid_stylesheet(appearance, variant)
        else:
            sample_qss = appearance_stylesheet(
                self._base_stylesheet, appearance, system_is_dark=self._system_is_dark
            )
        self._sample.setStyleSheet(sample_qss)
        valid_colors = all(field.hasAcceptableInput() for field in self._colors.values())
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(valid_colors)
        if emit_preview and valid_colors and self._on_preview is not None and self._live_preview_chk.isChecked():
            self._on_preview(appearance)

    def _pick_color(self, key: str) -> None:
        initial = dict(zip(self._colors, self.values().effective_colors(system_is_dark=self._system_is_dark)))[key]
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(initial), self)
        if color.isValid():
            self._colors[key].setText(color.name().upper())

    def done(self, result: int) -> None:  # type: ignore[override]
        if result != QtWidgets.QDialog.DialogCode.Accepted and self._on_preview is not None:
            self._on_preview(self._initial_appearance)
        super().done(result)
