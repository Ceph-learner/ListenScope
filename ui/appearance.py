"""Native Qt appearance: Dark/Light/Follow-System palettes, OS font scanning, live preview, and no QGraphicsEffect."""

from __future__ import annotations

import re
from typing import Callable, Optional

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import (
    ANALYSIS_LAYOUTS,
    DEFAULT_ANALYSIS_LAYOUT,
    FOCUS_STYLES,
    Appearance,
    LAYOUTS,
    PRESETS,
    THEME_MODES,
    UI_SURFACE_STYLES,
)
from core.i18n import LANGUAGES, translate_widget_tree
from ui.help_badge import (
    HelpBadge,
    install_focus_animations,
    set_focus_animations_enabled,
    set_focus_ring_style,
    set_help_language,
    set_help_mode_enabled,
    set_help_theme,
)
from ui.acid_style import (
    TelemetryHeader,
    acid_stylesheet,
    get_acid_palette,
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
    eff_font = appearance.effective_font_family()
    if eff_font:
        qss = qss.replace(
            'font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;',
            f'font-family: "{eff_font}", "Segoe UI", "Microsoft YaHei UI", sans-serif;',
        )

    has_bg_image = bool(appearance.effective_background_image())
    card_bg = f"rgba({QtGui.QColor(surface).red()}, {QtGui.QColor(surface).green()}, {QtGui.QColor(surface).blue()}, 212)" if has_bg_image else surface
    shell_bg = "transparent" if has_bg_image else background

    btn_checked_fg = foreground if is_light else foreground
    qss += f"""
QWidget#mainShellFrame {{
    background-color: {shell_bg};
    color: {foreground};
}}
QWidget#mainShellFrame[frameless="true"] {{
    border: 1px solid {rim};
    border-radius: 10px;
}}
QPushButton#windowCtrlBtn {{
    background: transparent;
    color: {subtle_fg};
    border: 1px solid {rim};
    border-radius: 5px;
    padding: 0px;
    min-width: 28px;
    max-width: 28px;
    min-height: 24px;
    max-height: 24px;
    font-weight: 700;
}}
QPushButton#windowCtrlBtn:hover {{
    background: {hover};
    color: {foreground};
    border-color: {accent};
}}
QPushButton#windowCloseBtn {{
    background: transparent;
    color: {subtle_fg};
    border: 1px solid {rim};
    border-radius: 5px;
    padding: 0px;
    min-width: 28px;
    max-width: 28px;
    min-height: 24px;
    max-height: 24px;
    font-weight: 700;
}}
QPushButton#windowCloseBtn:hover {{
    background: #D9262E;
    color: #FFFFFF;
    border-color: #FF6B6B;
}}
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
QGroupBox, QFrame[trackCard=true], QFrame#practiceCard {{ background: {card_bg}; }}
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
QFrame#bannerNoticeBox {{
    border-radius: 5px;
    background: {surface};
    border: 1px solid {rim};
    padding: 1px 4px;
}}
QFrame#bannerNoticeBox[tone="ok"] {{
    background: {sem["ok_bg"]};
    border: 1px solid {sem["ok_bd"]};
}}
QFrame#bannerNoticeBox[tone="warn"] {{
    background: {sem["warn_bg"]};
    border: 1px solid {sem["warn_bd"]};
}}
QFrame#bannerNoticeBox[tone="error"] {{
    background: {sem["err_bg"]};
    border: 1px solid {sem["err_bd"]};
}}
QFrame#bannerNoticeBox[tone="info"] {{
    background: {sem["info_bg"]};
    border: 1px solid {rim};
}}
QLabel#bannerNotice[inlineBanner="true"],
QLabel#bannerNotice[inlineBanner="true"][tone="ok"],
QLabel#bannerNotice[inlineBanner="true"][tone="warn"],
QLabel#bannerNotice[inlineBanner="true"][tone="error"],
QLabel#bannerNotice[inlineBanner="true"][tone="info"] {{
    border: none;
    background: transparent;
    padding: 3px 6px;
}}
QPushButton#noticeDismissBtn {{
    background: transparent;
    color: {subtle_fg};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    font-weight: 800;
}}
QPushButton#noticeDismissBtn:hover {{
    background: {hover};
    color: {foreground};
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
QFrame#analysisMetric {{ background: {card_bg}; border: 1px solid {rim}; border-radius: 8px; }}
QFrame#analysisMetric QLabel {{ background: transparent; }}
QFrame#analysisChart {{ background: {card_bg}; border: 1px solid {rim}; border-radius: 7px; }}
QFrame#analysisChart QLabel {{ background: transparent; }}
QLabel#analysisChartHeading {{ font-weight: 600; }}
QLabel#analysisCaption {{ color: {subtle_fg}; }}
QLabel#analysisPitch {{ color: {accent}; font-size: {appearance.font_size + 15}px; font-weight: 700; }}
QLabel#analysisValue {{ font-size: {appearance.font_size + 5}px; font-weight: 600; }}
QProgressBar#analysisLevel {{ background: {sunk}; border: 0; border-radius: 2px; }}
QProgressBar#analysisLevel::chunk {{ background: {accent}; border-radius: 2px; }}
QLabel#settingsPageHeading {{ font-size: {appearance.font_size + 6}px; font-weight: 700; }}
QLabel#settingsSubtitle {{ color: {subtle_fg}; }}
QWidget#settingsNavigation {{ background: {card_bg}; border: 1px solid {rim}; border-radius: 9px; }}
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
    background: {card_bg};
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
    background: {card_bg};
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
    surface_style = getattr(appearance, "ui_surface_style", "tactile")
    if surface_style == "tactile":
        rim_hi = _blend(rim, "#FFFFFF", 0.55 if is_light else 0.28)
        rim_lo = _blend(rim, "#000000", 0.22 if is_light else 0.35)
        qss += f"""
QPushButton:enabled {{
    border-top: 1px solid {rim_hi};
    border-left: 1px solid {rim_hi};
    border-right: 1px solid {rim_lo};
    border-bottom: 2px solid {rim_lo};
}}
QPushButton:pressed:enabled {{
    border-top: 2px solid {rim_lo};
    border-left: 1px solid {rim_lo};
    border-right: 1px solid {rim_hi};
    border-bottom: 1px solid {rim_hi};
}}
"""
    elif surface_style == "beveled":
        rim_lo = _blend(rim, "#000000", 0.20 if is_light else 0.35)
        qss += f"""
QPushButton:enabled {{
    border: 1px solid {rim};
    border-bottom: 2px solid {rim_lo};
}}
QPushButton:pressed:enabled {{
    border: 1px solid {accent};
}}
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
    try:
        plot.hideButtons()
    except Exception:
        pass
    background, foreground, _ = appearance.effective_colors(system_is_dark=system_is_dark)
    plot.setBackground(background)
    axis_color = _blend(background, foreground, 0.72)
    eff_font = appearance.effective_font_family()
    base_font = QtGui.QFont(eff_font) if eff_font else QtGui.QFont(QtWidgets.QApplication.font())
    base_font.setPixelSize(appearance.font_size)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=foreground, family=base_font.family(), size=f"{appearance.font_size}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(base_font)
        axis.setPen(_blend(background, foreground, 0.45))
        axis.setTextPen(axis_color)


class AppearanceDialog(QtWidgets.QDialog):
    """Preview theme, Dark/Light/Follow-System mode, OS font/size, wallpaper, language, and layout live."""

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
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        root.addWidget(TelemetryHeader("APPEARANCE // THEME & TYPOGRAPHY", "主题风格 · 字体字号 · 多语言与交互"))

        presets = QtWidgets.QHBoxLayout()
        self._presets = QtWidgets.QButtonGroup(self)
        for key, (label, *_colors) in PRESETS.items():
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            self._presets.addButton(button)
            button.clicked.connect(lambda _checked, key=key: self._apply_preset(key))
            button.setProperty("preset", key)
            presets.addWidget(button)
        root.addLayout(presets)

        self._acid_lock_banner = QtWidgets.QLabel(
            "🔒 酸性遥测风格已锁定标准工业字体、官方配色、玻璃高光与背景图（字号 11–20px、黑夜/白天/跟随系统、语言与布局仍可自由调节）。"
        )
        self._acid_lock_banner.setObjectName("bannerNotice")
        self._acid_lock_banner.setProperty("tone", "info")
        self._acid_lock_banner.setWordWrap(True)
        root.addWidget(self._acid_lock_banner)

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
                "「白天」默认启用清爽高对比的临床浅色工作台；「黑夜」切换为深邃低眩光配色；「跟随系统」自动同步 Windows 深浅色设置。",
            )
        )
        form.addRow("主题模式", mode_row)

        # Language + Frameless window row
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setSpacing(8)
        self._language_combo = QtWidgets.QComboBox()
        self._language_combo.setProperty("lsKeepItems", True)
        self._language_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for lang_code, lang_label in LANGUAGES.items():
            self._language_combo.addItem(lang_label, lang_code)
        self._language_combo.currentIndexChanged.connect(self._on_control_changed)
        self._frameless_chk = QtWidgets.QCheckBox("无边框圆角窗口 (推荐)")
        self._frameless_chk.toggled.connect(self._on_control_changed)
        lang_row.addWidget(self._language_combo, 1)
        lang_row.addWidget(self._frameless_chk)
        lang_row.addWidget(
            HelpBadge(
                "多语言与无边框圆角壳体",
                "支持简体中文、English、한국어、日本語 四种语言实时切换（固定工业英文代号保留，English 模式下仅显示英文不重复）。"
                "无边框圆角窗口消除传统系统粗边框，四角圆润丝滑。",
            )
        )
        form.addRow("界面语言", lang_row)

        # Help mode + Focus hover animation + style
        assist_row = QtWidgets.QHBoxLayout()
        assist_row.setSpacing(8)
        self._help_mode_chk = QtWidgets.QCheckBox("说明模式 (显示 [?] 悬浮说明)")
        self._help_mode_chk.toggled.connect(self._on_control_changed)
        self._focus_anim_chk = QtWidgets.QCheckBox("交互聚焦动画")
        self._focus_anim_chk.toggled.connect(self._on_control_changed)
        self._focus_style_combo = QtWidgets.QComboBox()
        for fkey, flabel in FOCUS_STYLES.items():
            self._focus_style_combo.addItem(flabel, fkey)
        self._focus_style_combo.currentIndexChanged.connect(self._on_control_changed)
        assist_row.addWidget(self._help_mode_chk)
        assist_row.addWidget(self._focus_anim_chk)
        assist_row.addWidget(self._focus_style_combo)
        assist_row.addStretch(1)
        assist_row.addWidget(
            HelpBadge(
                "说明模式与交互聚焦动画",
                "• 说明模式：开启后在各功能旁显示 [?] 徽标，鼠标悬浮即可即时弹出功能解释；关闭后不再弹出任何悬停说明。\n"
                "• 交互聚焦动画：仅对按钮与下拉框等交互控件绘制轻量级极细描边 / 护栏角框 / 底线动效（零显存占用），复选框与极简开关默认保持克制。",
            )
        )
        form.addRow("交互与聚焦", assist_row)

        # Button/card surface edge style + close-to-tray toggle
        surface_row = QtWidgets.QHBoxLayout()
        surface_row.setSpacing(8)
        self._surface_style_combo = QtWidgets.QComboBox()
        for skey, slabel in UI_SURFACE_STYLES.items():
            self._surface_style_combo.addItem(slabel, skey)
        self._surface_style_combo.currentIndexChanged.connect(self._on_control_changed)
        self._close_to_tray_chk = QtWidgets.QCheckBox("点击右上角 × 时最小化到系统托盘")
        self._close_to_tray_chk.toggled.connect(self._on_control_changed)
        surface_row.addWidget(self._surface_style_combo)
        surface_row.addWidget(self._close_to_tray_chk, 1)
        surface_row.addWidget(
            HelpBadge(
                "控件边框质感与托盘驻留",
                "• 边框质感：提供「立体微棱边」「微倒角框」「纯粹扁平」三种按钮/卡片边缘手感，即便在酸性遥测主题下也可自由微调。\n"
                "• 系统托盘：开启后点击窗口右上角关闭按钮（×）会最小化到 Windows 托盘后台保活运行；右键托盘菜单可彻底退出。",
            )
        )
        form.addRow("质感与托盘", surface_row)

        # Telemetry micro-animations intensity + music-reactive toggle
        telem_row = QtWidgets.QHBoxLayout()
        telem_row.setSpacing(8)
        self._telemetry_strength_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._telemetry_strength_slider.setRange(0, 100)
        self._telemetry_strength_slider.valueChanged.connect(self._on_control_changed)
        self._telemetry_strength_lbl = QtWidgets.QLabel("70%")
        self._telemetry_strength_lbl.setMinimumWidth(36)
        self._music_reactive_chk = QtWidgets.QCheckBox("随音乐高潮动态变化")
        self._music_reactive_chk.toggled.connect(self._on_control_changed)
        telem_row.addWidget(self._telemetry_strength_slider, 1)
        telem_row.addWidget(self._telemetry_strength_lbl)
        telem_row.addWidget(self._music_reactive_chk)
        telem_row.addWidget(
            HelpBadge(
                "遥测微动画强度与音乐联动",
                "调节界面点阵、顶部电平条与电池分段进度条的动态呼吸强度（0% = 完全静止，100% = 饱满脉冲）。\n"
                "勾选「随音乐高潮动态变化」后，动画幅度会随实时音量与高潮能量自适应起伏；点击底部 [STATIC_LOCK] 可随时一键冻结所有动画。",
            )
        )
        form.addRow("遥测微动画", telem_row)

        self._layout = QtWidgets.QComboBox()
        self._layout.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for key, (label, _description) in LAYOUTS.items():
            self._layout.addItem(label, key)
        self._layout.currentIndexChanged.connect(self._on_control_changed)
        form.addRow("界面布局", self._layout)

        self._layout_hint = QtWidgets.QLabel()
        self._layout_hint.setWordWrap(True)
        self._layout_hint.setObjectName("mutedCaption")
        form.addRow("", self._layout_hint)

        self._analysis_layout = QtWidgets.QComboBox()
        self._analysis_layout.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
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
                "系统字体扫描与字号",
                "在酸性遥测主题下字体家族锁定为标准工业体系以保证排版对齐，但字号（11–20 px）仍可自由缩放；切换到其他主题后可自定义任意系统已安装字体。",
            )
        )
        form.addRow("字体与大小", font_row)

        self._colors: dict[str, QtWidgets.QLineEdit] = {}
        self._color_pickers: dict[str, QtWidgets.QPushButton] = {}
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
            self._color_pickers[key] = picker
            form.addRow(label, row)

        # Custom background image (non-Acid themes only)
        bg_row = QtWidgets.QHBoxLayout()
        bg_row.setSpacing(6)
        self._bg_image_edit = QtWidgets.QLineEdit()
        self._bg_image_edit.setPlaceholderText("未设置自定义背景图（仅非酸性主题可用）")
        self._bg_image_edit.textChanged.connect(self._on_control_changed)
        self._bg_image_btn = QtWidgets.QPushButton("选择背景图…")
        self._bg_image_btn.clicked.connect(self._pick_background_image)
        self._bg_image_clear_btn = QtWidgets.QPushButton("清除")
        self._bg_image_clear_btn.clicked.connect(lambda: self._bg_image_edit.setText(""))
        bg_row.addWidget(self._bg_image_edit, 1)
        bg_row.addWidget(self._bg_image_btn)
        bg_row.addWidget(self._bg_image_clear_btn)
        bg_row.addWidget(
            HelpBadge(
                "自定义背景壁纸（非酸性主题专享）",
                "在经典深色、Lenso 液态玻璃、Codex 石墨、Claude 暖砂四种主题下，支持上传 PNG/JPG/WebP 图片作为主窗口背景壁纸，并自动叠加柔和可读性遮罩。酸性遥测主题为保持纯粹图形写实主义对比度，禁用自定义背景图。",
            )
        )
        form.addRow("自定义背景图", bg_row)
        root.addLayout(form)

        self._glass_group = QtWidgets.QGroupBox("液态玻璃卡片")
        optics = QtWidgets.QFormLayout(self._glass_group)
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
        root.addWidget(self._glass_group)

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

        self.setMinimumWidth(590)
        install_focus_animations(self)
        self._show_values(appearance, emit_preview=False)

    def _apply_preset(self, key: str) -> None:
        current = self.values()
        is_acid = key == "acid_telemetry"
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
            font_family="" if is_acid else current.font_family,
            background_image="" if is_acid else current.background_image,
            language=current.language,
            frameless=current.frameless,
            help_mode=current.help_mode,
            focus_animations=current.focus_animations,
            telemetry_animation_strength=current.telemetry_animation_strength,
            music_reactive_animations=current.music_reactive_animations,
            focus_style=current.focus_style,
            ui_surface_style=current.ui_surface_style,
            close_to_tray=current.close_to_tray,
        )
        self._show_values(updated)

    def reset_to_defaults(self) -> None:
        self._show_values(Appearance())

    def values(self) -> Appearance:
        checked_preset = self._presets.checkedButton()
        checked_mode = self._theme_modes.checkedButton()
        preset_key = checked_preset.property("preset") if checked_preset else "acid_telemetry"
        return Appearance.from_mapping({
            "preset": preset_key,
            "theme_mode": checked_mode.property("themeMode") if checked_mode else "light",
            "font_family": "" if preset_key == "acid_telemetry" else (self._font_family.currentData() or ""),
            "font_size": self._font.value(),
            "scope": self._scope.currentData(),
            "layout": self._layout.currentData(),
            "analysis_layout": self._analysis_layout.currentData(),
            "background_image": "" if preset_key == "acid_telemetry" else self._bg_image_edit.text().strip(),
            "language": self._language_combo.currentData() or "zh",
            "frameless": self._frameless_chk.isChecked(),
            "help_mode": self._help_mode_chk.isChecked(),
            "focus_animations": self._focus_anim_chk.isChecked(),
            "telemetry_animation_strength": self._telemetry_strength_slider.value(),
            "music_reactive_animations": self._music_reactive_chk.isChecked(),
            "focus_style": self._focus_style_combo.currentData() or "sleek",
            "ui_surface_style": self._surface_style_combo.currentData() or "tactile",
            "close_to_tray": self._close_to_tray_chk.isChecked(),
            **{key: ("" if preset_key == "acid_telemetry" else field.text()) for key, field in self._colors.items()},
            **{key: slider.value() for key, slider in self._sliders.items()},
        })

    def _show_values(self, values: Appearance, *, emit_preview: bool = True) -> None:
        controls = [
            self._layout,
            self._analysis_layout,
            self._font_family,
            self._font,
            self._scope,
            self._language_combo,
            self._frameless_chk,
            self._help_mode_chk,
            self._focus_anim_chk,
            self._focus_style_combo,
            self._surface_style_combo,
            self._telemetry_strength_slider,
            self._music_reactive_chk,
            self._close_to_tray_chk,
            self._bg_image_edit,
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
        lang_idx = self._language_combo.findData(values.language)
        self._language_combo.setCurrentIndex(max(0, lang_idx))
        self._frameless_chk.setChecked(bool(values.frameless))
        self._help_mode_chk.setChecked(bool(values.help_mode))
        self._focus_anim_chk.setChecked(bool(values.focus_animations))
        self._focus_style_combo.setCurrentIndex(max(0, self._focus_style_combo.findData(values.focus_style)))
        self._surface_style_combo.setCurrentIndex(max(0, self._surface_style_combo.findData(values.ui_surface_style)))
        self._telemetry_strength_slider.setValue(int(values.telemetry_animation_strength))
        self._telemetry_strength_lbl.setText(f"{int(values.telemetry_animation_strength)}%")
        self._music_reactive_chk.setChecked(bool(values.music_reactive_animations))
        self._close_to_tray_chk.setChecked(bool(values.close_to_tray))
        self._bg_image_edit.setText(values.background_image)
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

    def _update_acid_lock_state(self, is_acid: bool) -> None:
        self._acid_lock_banner.setVisible(is_acid)
        self._font_family.setEnabled(not is_acid)
        for key, field in self._colors.items():
            field.setEnabled(not is_acid)
            self._color_pickers[key].setEnabled(not is_acid)
        self._bg_image_edit.setEnabled(not is_acid)
        self._bg_image_btn.setEnabled(not is_acid)
        self._bg_image_clear_btn.setEnabled(not is_acid)
        self._glass_group.setEnabled(not is_acid)

    def _refresh_sample(self, *, emit_preview: bool = True) -> None:
        appearance = self.values()
        is_acid = appearance.is_acid_locked()
        self._update_acid_lock_state(is_acid)
        self._focus_style_combo.setEnabled(bool(appearance.focus_animations))
        self._music_reactive_chk.setEnabled(appearance.telemetry_animation_strength > 0)
        self._telemetry_strength_lbl.setText(f"{appearance.telemetry_animation_strength}%")
        self._layout_hint.setText(LAYOUTS[appearance.layout][1])
        for slider in self._sliders.values():
            slider.setEnabled((not is_acid) and appearance.scope != "off")
        if is_acid_eligible(appearance):
            variant = resolve_acid_variant(appearance, system_is_dark=self._system_is_dark) or "light"
            sample_qss = acid_stylesheet(appearance, variant)
            pal = get_acid_palette(variant)
            set_help_theme(
                bg=pal.bg_panel,
                fg=pal.text_primary,
                accent=pal.accent,
                border=pal.border,
                muted=pal.text_muted,
                is_dark=(variant == "dark"),
                is_acid=True,
            )
        else:
            sample_qss = appearance_stylesheet(
                self._base_stylesheet, appearance, system_is_dark=self._system_is_dark
            )
            bg, fg, accent = appearance.effective_colors(system_is_dark=self._system_is_dark)
            mode = appearance.resolve_theme_mode(system_is_dark=self._system_is_dark)
            set_help_theme(
                bg=bg,
                fg=fg,
                accent=accent,
                border=_blend(bg, fg, 0.28),
                muted=_blend(bg, fg, 0.65),
                is_dark=(mode == "dark"),
                is_acid=False,
            )
        # Theme the entire AppearanceDialog consistently with the selected preset & mode
        self.setStyleSheet(sample_qss)
        self._sample.setStyleSheet(sample_qss)
        set_help_mode_enabled(appearance.help_mode)
        set_focus_animations_enabled(appearance.focus_animations)
        set_focus_ring_style(appearance.focus_style)
        set_help_language(appearance.language)
        translate_widget_tree(self, appearance.language)
        valid_colors = is_acid or all(field.hasAcceptableInput() for field in self._colors.values())
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(valid_colors)
        if emit_preview and valid_colors and self._on_preview is not None and self._live_preview_chk.isChecked():
            self._on_preview(appearance)

    def _pick_color(self, key: str) -> None:
        if self.values().is_acid_locked():
            return
        initial = dict(zip(self._colors, self.values().effective_colors(system_is_dark=self._system_is_dark)))[key]
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(initial), self)
        if color.isValid():
            self._colors[key].setText(color.name().upper())

    def _pick_background_image(self) -> None:
        if self.values().is_acid_locked():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择自定义背景图",
            self._bg_image_edit.text().strip(),
            "图像文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)",
        )
        if path:
            self._bg_image_edit.setText(path)

    def done(self, result: int) -> None:  # type: ignore[override]
        if result != QtWidgets.QDialog.DialogCode.Accepted:
            set_help_mode_enabled(self._initial_appearance.help_mode)
            set_focus_animations_enabled(self._initial_appearance.focus_animations)
            set_focus_ring_style(self._initial_appearance.focus_style)
            set_help_language(self._initial_appearance.language)
            if self._on_preview is not None:
                self._on_preview(self._initial_appearance)
        super().done(result)

