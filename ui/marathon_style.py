"""Marathon Industrial Clinical UI tokens, QSS generator, PyQtGraph LUTs, and signature Qt widgets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import Appearance
from core.paths import get_bundle_root


@dataclass(frozen=True)
class MarathonPalette:
    variant: str
    bg_base: str
    bg_panel: str
    bg_elevated: str
    bg_hover: str
    bg_code: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str
    accent: str
    accent_hover: str
    accent_strong: str
    accent_soft: str
    accent_border: str
    accent_secondary: str
    border: str
    border_strong: str
    status_ok_bg: str
    status_ok_fg: str
    status_ok_bd: str
    status_warn_bg: str
    status_warn_fg: str
    status_warn_bd: str
    status_danger_bg: str
    status_danger_fg: str
    status_danger_bd: str
    plot_bg: str
    plot_axis: str
    plot_tick_pen: str
    plot_wave: str
    plot_fft: str
    plot_log: str
    plot_region_rgba: tuple[int, int, int, int]
    plot_region_pen: str
    plot_playhead: str
    plot_pr_cursor: str
    cents_track_bg: str
    cents_track_bd: str
    cents_center_tick: str
    cents_in_tune: str
    cents_slight: str
    cents_off: str
    cents_idle: str


MARATHON_PALETTES: dict[str, MarathonPalette] = {
    "light": MarathonPalette(
        variant="light",
        bg_base="#EEF2F6",
        bg_panel="#FFFFFF",
        bg_elevated="#E2E8F0",
        bg_hover="#CBD5E1",
        bg_code="#F8FAFC",
        text_primary="#090D14",
        text_secondary="#334155",
        text_muted="#64748B",
        text_inverse="#FFFFFF",
        accent="#00A878",
        accent_hover="#00BC86",
        accent_strong="#008F66",
        accent_soft="#DCEFE9",
        accent_border="#54BFA1",
        accent_secondary="#0284C7",
        border="#CBD5E1",
        border_strong="#090D14",
        status_ok_bg="#DCF5EC",
        status_ok_fg="#065F46",
        status_ok_bd="#10B981",
        status_warn_bg="#E0F2FE",
        status_warn_fg="#0369A1",
        status_warn_bd="#0284C7",
        status_danger_bg="#FEE2E2",
        status_danger_fg="#B91C1C",
        status_danger_bd="#EF4444",
        plot_bg="#F8FAFC",
        plot_axis="#334155",
        plot_tick_pen="#94A3B8",
        plot_wave="#0F766E",
        plot_fft="#00A878",
        plot_log="#0284C7",
        plot_region_rgba=(0, 168, 120, 36),
        plot_region_pen="#00A878",
        plot_playhead="#0284C7",
        plot_pr_cursor="#EF4444",
        cents_track_bg="#E2E8F0",
        cents_track_bd="#CBD5E1",
        cents_center_tick="#334155",
        cents_in_tune="#00A878",
        cents_slight="#0284C7",
        cents_off="#EF4444",
        cents_idle="#64748B",
    ),
    "dark": MarathonPalette(
        variant="dark",
        bg_base="#0B1016",
        bg_panel="#121923",
        bg_elevated="#1A2330",
        bg_hover="#243040",
        bg_code="#0E141C",
        text_primary="#E8EEF5",
        text_secondary="#A3B4C7",
        text_muted="#72859C",
        text_inverse="#FFFFFF",
        accent="#00A878",
        accent_hover="#00C28A",
        accent_strong="#008F66",
        accent_soft="#12312B",
        accent_border="#00A878",
        accent_secondary="#38BDF8",
        border="#263344",
        border_strong="#00A878",
        status_ok_bg="#0F2D25",
        status_ok_fg="#34D399",
        status_ok_bd="#10B981",
        status_warn_bg="#0E273B",
        status_warn_fg="#38BDF8",
        status_warn_bd="#0284C7",
        status_danger_bg="#33151B",
        status_danger_fg="#FCA5A5",
        status_danger_bd="#EF4444",
        plot_bg="#0E141C",
        plot_axis="#A3B4C7",
        plot_tick_pen="#334155",
        plot_wave="#38BDF8",
        plot_fft="#00C28A",
        plot_log="#38BDF8",
        plot_region_rgba=(0, 194, 138, 42),
        plot_region_pen="#00C28A",
        plot_playhead="#38BDF8",
        plot_pr_cursor="#EF4444",
        cents_track_bg="#1A2330",
        cents_track_bd="#263344",
        cents_center_tick="#A3B4C7",
        cents_in_tune="#00C28A",
        cents_slight="#38BDF8",
        cents_off="#EF4444",
        cents_idle="#64748B",
    ),
}

_FONT_SANS = '"Inter", "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif'
_FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono", monospace'

_LUT_CACHE: dict[tuple[str, str], np.ndarray] = {}


def is_marathon_eligible(appearance: Appearance) -> bool:
    """Return True when the active theme is the uncustomized Marathon industrial clinical preset."""
    return (
        appearance.preset == "marathon"
        and not appearance.background
        and not appearance.text
        and not appearance.accent
    )


def resolve_marathon_variant(
    appearance: Appearance,
    *,
    marathon_skin: Optional[str] = None,
    system_is_dark: Optional[bool] = None,
) -> Optional[str]:
    """Return 'light' or 'dark' when Marathon UI should style this view, else None."""
    if not is_marathon_eligible(appearance):
        return None
    if marathon_skin == "marathon_light":
        return "light"
    if marathon_skin == "marathon_dark":
        return "dark"
    return appearance.resolve_theme_mode(system_is_dark=system_is_dark)


def get_marathon_palette(variant: str = "light") -> MarathonPalette:
    return MARATHON_PALETTES["dark" if variant == "dark" else "light"]


def marathon_colormap_lut(kind: str, variant: str = "light") -> np.ndarray:
    """Return a cool clinical 256-entry RGBA LUT (strictly free of warm yellow/amber)."""
    key = (kind, "dark" if variant == "dark" else "light")
    cached = _LUT_CACHE.get(key)
    if cached is not None:
        return cached

    if key[1] == "dark":
        stops = np.array([0.0, 0.22, 0.48, 0.74, 0.90, 1.0], dtype=np.float32)
        colors = (
            ["#0E141C", "#162230", "#0369A1", "#0284C7", "#00A878", "#6EE7B7"]
            if kind == "spectrogram"
            else ["#0E141C", "#172330", "#0369A1", "#0284C7", "#00C28A", "#A7F3D0"]
        )
    else:
        stops = np.array([0.0, 0.22, 0.48, 0.74, 0.90, 1.0], dtype=np.float32)
        colors = (
            ["#F8FAFC", "#E2E8F0", "#7DD3FC", "#0284C7", "#00A878", "#065F46"]
            if kind == "spectrogram"
            else ["#F8FAFC", "#E2E8F0", "#7DD3FC", "#0284C7", "#00A878", "#064E3B"]
        )
    cmap = pg.ColorMap(pos=stops, color=[pg.mkColor(c) for c in colors])
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    _LUT_CACHE[key] = lut
    return lut


class ChamferBadge(QtWidgets.QWidget):
    """45-degree top-right chamfered industrial nameplate badge (zero QGraphicsEffect)."""

    def __init__(
        self,
        text: str = "LS",
        parent: QtWidgets.QWidget | None = None,
        *,
        size: QtCore.QSize = QtCore.QSize(34, 30),
        chamfer: int = 7,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._chamfer = max(4, int(chamfer))
        self._fill = QtGui.QColor("#00A878")
        self._border = QtGui.QColor("#008F66")
        self._fg = QtGui.QColor("#FFFFFF")
        self.setFixedSize(size)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_palette_colors(self, *, fill: str, border: str, fg: str = "#FFFFFF") -> None:
        self._fill = QtGui.QColor(fill)
        self._border = QtGui.QColor(border)
        self._fg = QtGui.QColor(fg)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        w = float(self.width())
        h = float(self.height())
        c = min(float(self._chamfer), w * 0.4, h * 0.4)
        if w <= 4 or h <= 4:
            return

        path = QtGui.QPainterPath()
        path.moveTo(0.5, 0.5)
        path.lineTo(w - c, 0.5)
        path.lineTo(w - 0.5, c)
        path.lineTo(w - 0.5, h - 0.5)
        path.lineTo(0.5, h - 0.5)
        path.closeSubpath()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(path, self._fill)
        painter.setPen(QtGui.QPen(self._border, 1.0))
        painter.drawPath(path)

        font = QtGui.QFont("JetBrains Mono")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        font.setBold(True)
        font.setPixelSize(max(10, min(13, round(h * 0.40))))
        painter.setFont(font)
        painter.setPen(self._fg)
        painter.drawText(QtCore.QRectF(0, 0, w - 1, h), QtCore.Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


class TelemetryHeader(QtWidgets.QFrame):
    """Bilingual Marathon Telemetry Header: uppercase monospace eyebrow + bold title + optional right strip."""

    def __init__(
        self,
        eyebrow: str,
        title: str,
        parent: QtWidgets.QWidget | None = None,
        *,
        badge_text: str = "",
        divider: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("telemetryHeader")
        self.setProperty("divider", divider)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 5 if divider else 0)
        outer.setSpacing(2)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        stack = QtWidgets.QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(1)

        self.eyebrow_lbl = QtWidgets.QLabel(eyebrow.upper())
        self.eyebrow_lbl.setObjectName("telemetryEyebrow")
        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setObjectName("telemetryTitle")

        stack.addWidget(self.eyebrow_lbl)
        stack.addWidget(self.title_lbl)
        row.addLayout(stack, 1)

        self._right_layout = QtWidgets.QHBoxLayout()
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(6)
        row.addLayout(self._right_layout)

        self.badge_lbl: Optional[QtWidgets.QLabel] = None
        if badge_text:
            self.badge_lbl = QtWidgets.QLabel(badge_text)
            self.badge_lbl.setObjectName("telemetryPill")
            self._right_layout.addWidget(self.badge_lbl)

        outer.addLayout(row)

    def add_right_widget(self, widget: QtWidgets.QWidget) -> None:
        self._right_layout.addWidget(widget)


def _marathon_asset_url(filename: str) -> str:
    """Resolve a Marathon UI SVG asset path from PyInstaller bundle or source checkout."""
    path = get_bundle_root() / "ui" / "assets" / filename
    if not path.exists():
        path = Path(__file__).resolve().parent / "assets" / filename
    return path.as_posix() if path.exists() else ""


def _marathon_controls_qss(
    p: MarathonPalette,
    *,
    variant: str,
    base_px: int,
) -> str:
    """Dedicated flat Industrial Clinical widget-control QSS isolated to Marathon mode.

    Explicitly styles buttons, QComboBox dropdowns/arrows, spinboxes, checkboxes, radios,
    sliders, scrollbars, and menus so Qt Fusion never falls back to 3D Win98/XP bevel caps.
    """
    is_light = variant == "light"
    btn_surface = p.bg_code if is_light else p.bg_elevated
    btn_hover_fg = p.accent_strong if is_light else p.accent_hover
    btn_checked_fg = p.accent_strong if is_light else p.text_primary
    indicator_bd = p.border_strong if is_light else p.text_muted
    h_btn_border = p.accent_strong
    slider_thumb = p.text_primary if is_light else p.text_inverse

    check_url = _marathon_asset_url("marathon_check.svg")
    chev_down_url = _marathon_asset_url(
        "marathon_chevron_down_light.svg" if is_light else "marathon_chevron_down_dark.svg"
    )
    chev_up_url = _marathon_asset_url(
        "marathon_chevron_up_light.svg" if is_light else "marathon_chevron_up_dark.svg"
    )
    check_img_qss = f"image: url({check_url});" if check_url else ""
    chev_down_qss = f"image: url({chev_down_url});" if chev_down_url else ""
    chev_up_qss = f"image: url({chev_up_url});" if chev_up_url else ""

    return f"""
/* Marathon Segmented Pill Track (Topbar Skin Switcher) */
QWidget#marathonModeGroup {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: 2px;
}}
QPushButton#marathonPillBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    min-height: 18px;
    padding: 2px 8px;
    color: {p.text_secondary};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 600;
    outline: none;
}}
QPushButton#marathonPillBtn:hover {{
    color: {p.text_primary};
    border-color: {p.accent_border};
}}
QPushButton#marathonPillBtn:checked {{
    background-color: {p.accent};
    border: 1px solid {h_btn_border};
    color: {p.text_inverse};
    font-weight: 700;
}}

/* Flat Clinical Buttons (Zero 3D bevel, zero chunky weights, matched baseline height) */
QPushButton {{
    background-color: {btn_surface};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    min-height: 20px;
    padding: 3px 10px;
    font-weight: 500;
    outline: none;
}}
QPushButton:hover {{
    background-color: {p.accent_soft};
    border-color: {p.accent};
    color: {btn_hover_fg};
}}
QPushButton:pressed {{
    background-color: {p.bg_hover};
    border-color: {p.accent_strong};
}}
QPushButton:checked {{
    background-color: {p.accent_soft};
    border: 1px solid {p.accent};
    color: {btn_checked_fg};
    font-weight: 700;
}}
QPushButton:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QPushButton#analysisAction:enabled,
QPushButton#settingsSave:enabled,
QPushButton#marathonPrimaryBtn:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border: 1px solid {h_btn_border};
    font-weight: 700;
}}
QPushButton#analysisAction:hover:enabled,
QPushButton#settingsSave:hover:enabled,
QPushButton#marathonPrimaryBtn:hover:enabled {{
    background-color: {p.accent_hover};
    border-color: {h_btn_border};
    color: {p.text_inverse};
}}
QPushButton#analysisAction:disabled,
QPushButton#settingsSave:disabled,
QPushButton#marathonPrimaryBtn:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border: 1px solid {p.border};
}}
QPushButton#settingsSave {{
    padding: 4px 18px;
}}
QPushButton#captureBtn:checked {{
    background-color: {p.accent};
    border: 1px solid {h_btn_border};
    color: {p.text_inverse};
    font-weight: 700;
}}
QPushButton#emergencyStopBtn {{
    background-color: {p.status_danger_bd};
    color: #FFFFFF;
    border: 1px solid #DC2626;
    border-radius: 2px;
    min-height: 20px;
    font-weight: 700;
    padding: 3px 12px;
    font-family: {_FONT_MONO};
    outline: none;
}}
QPushButton#emergencyStopBtn:hover {{
    background-color: #DC2626;
    border-color: #B91C1C;
    color: #FFFFFF;
}}
QToolButton {{
    background-color: {btn_surface};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 2px 6px;
    font-weight: 500;
    outline: none;
}}
QToolButton:hover {{
    background-color: {p.accent_soft};
    border-color: {p.accent};
    color: {btn_hover_fg};
}}
QToolButton#helpBadge {{
    background-color: {p.bg_code};
    color: {p.text_muted};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 0px;
    font-family: {_FONT_MONO};
    font-size: {max(10, min(13, base_px - 1))}px;
    font-weight: 700;
}}
QToolButton#helpBadge:hover {{
    background-color: {p.accent_soft};
    color: {btn_checked_fg};
    border-color: {p.accent};
}}

/* Flat Checkboxes, Radios & Caliper Sliders */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {p.text_primary};
    outline: none;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {indicator_bd};
    border-radius: 2px;
    background-color: {p.bg_panel};
}}
QCheckBox::indicator:hover {{
    border-color: {p.accent};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {h_btn_border};
    background-color: {p.accent};
    {check_img_qss}
}}
QCheckBox::indicator:disabled {{
    border-color: {p.border};
    background-color: {p.bg_elevated};
}}
QCheckBox::indicator:checked:disabled {{
    background-color: {p.text_muted};
    {check_img_qss}
}}
QRadioButton::indicator {{
    width: 13px;
    height: 13px;
    border-radius: 7px;
    border: 1px solid {indicator_bd};
    background-color: {p.bg_panel};
}}
QRadioButton::indicator:hover {{
    border-color: {p.accent};
}}
QRadioButton::indicator:checked {{
    background-color: {p.accent};
    border: 3px solid {p.bg_panel};
    outline: 1px solid {h_btn_border};
}}
QSlider::groove:horizontal {{
    border: none;
    height: 3px;
    background: {p.border};
    border-radius: 1px;
}}
QSlider::sub-page:horizontal {{
    background: {p.accent};
    border: none;
    height: 3px;
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: {slider_thumb};
    border: 1px solid {p.accent};
    width: 7px;
    height: 14px;
    margin: -6px 0;
    border-radius: 1px;
}}
QSlider::handle:horizontal:hover {{
    background: {p.accent};
    border-color: {h_btn_border};
}}
QPushButton:focus,
QComboBox:focus,
QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QTableWidget:focus,
QToolButton#helpBadge:focus {{
    border: 1px solid {p.accent};
    outline: none;
}}

/* Flush Inputs, Custom Vector-Chevron Dropdowns & Flat Steppers (Zero Win98 Bevels) */
QLineEdit, QPlainTextEdit {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 3px 8px;
    min-height: 20px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text_primary};
}}
QLineEdit:hover, QPlainTextEdit:hover {{
    border-color: {p.accent_border};
    background-color: {p.bg_panel};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {p.accent};
    background-color: {p.bg_panel};
}}
QComboBox {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 3px 26px 3px 8px;
    min-height: 20px;
    outline: none;
}}
QComboBox:hover, QComboBox:on {{
    border-color: {p.accent};
    background-color: {p.bg_panel};
}}
QComboBox:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    background-color: transparent;
    border: none;
    border-left: 1px solid transparent;
    border-top-right-radius: 2px;
    border-bottom-right-radius: 2px;
}}
QComboBox::drop-down:hover {{
    background-color: {p.accent_soft};
    border-left: 1px solid {p.accent_border};
}}
QComboBox::down-arrow {{
    {chev_down_qss}
    width: 11px;
    height: 11px;
}}
QComboBox::down-arrow:on {{
    top: 0px;
    left: 0px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.accent};
    border-radius: 2px;
    padding: 3px;
    outline: 0;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text_primary};
}}
QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
    min-height: 20px;
    border-radius: 2px;
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 3px 24px 3px 8px;
    min-height: 20px;
    font-family: {_FONT_MONO};
    outline: none;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text_primary};
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.accent};
    background-color: {p.bg_panel};
}}
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 19px;
    background-color: transparent;
    border: none;
    border-left: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    margin-top: 1px;
    margin-right: 1px;
    border-top-right-radius: 1px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 19px;
    background-color: transparent;
    border: none;
    border-left: 1px solid {p.border};
    margin-bottom: 1px;
    margin-right: 1px;
    border-bottom-right-radius: 1px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {p.accent_soft};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background-color: {p.accent};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    {chev_up_qss}
    width: 8px;
    height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    {chev_down_qss}
    width: 8px;
    height: 8px;
}}
QPlainTextEdit#diagnosticLogStream {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent_secondary};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
}}
QMenu {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 3px;
}}
QMenu::item {{
    padding: 5px 14px;
    border-radius: 2px;
}}
QMenu::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text_primary};
}}
QToolTip {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.accent};
    border-radius: 2px;
    padding: 5px 8px;
}}

/* Slash-Indexed Navigation Tabs */
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: 2px;
    background-color: {p.bg_base};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {p.bg_elevated};
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-bottom: none;
    border-top-left-radius: 2px;
    border-top-right-radius: 2px;
    padding: 6px 13px;
    margin-right: 3px;
    font-weight: 500;
    outline: none;
}}
QTabBar::tab:hover {{
    background-color: {p.bg_hover};
    color: {p.text_primary};
}}
QTabBar::tab:selected {{
    background-color: {p.accent_soft};
    color: {p.text_primary};
    border: 1px solid {p.accent};
    border-top: 2px solid {p.accent};
    border-bottom: 1px solid {p.accent_soft};
    font-weight: 700;
}}

/* Tables & Sticky-Feel Telemetry Headers */
QTableWidget {{
    background-color: {p.bg_panel};
    alternate-background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 2px;
    gridline-color: {p.bg_elevated};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text_primary};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
    outline: 0;
}}
QHeaderView::section {{
    background-color: {p.bg_elevated};
    color: {btn_hover_fg};
    border: 0px;
    border-bottom: 1px solid {p.border};
    border-right: 1px solid {p.border};
    padding: 4px 8px;
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 700;
}}
QTableWidget#practiceTable {{
    background-color: {p.bg_panel};
    alternate-background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 2px;
    gridline-color: {p.bg_elevated};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text_primary};
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
    background-color: {p.accent_soft};
    color: {p.text_primary};
}}
QTableWidget#practiceTable QScrollBar:vertical,
QScrollBar:vertical {{
    background: {p.bg_code};
    width: 8px;
    margin: 1px;
    border-radius: 2px;
}}
QTableWidget#practiceTable QScrollBar::handle:vertical,
QScrollBar::handle:vertical {{
    background: {p.border};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar:horizontal {{
    background: {p.bg_code};
    height: 8px;
    margin: 1px;
    border-radius: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border};
    border-radius: 2px;
    min-width: 20px;
}}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background: {p.text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QSplitter::handle {{
    background: {p.border};
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background: {p.accent};
}}
"""


def marathon_stylesheet(appearance: Appearance, variant: str = "light") -> str:
    """Build the cohesive Marathon Industrial Clinical QSS stylesheet."""
    p = get_marathon_palette(variant)
    base_px = max(11, int(appearance.font_size or 12))
    sans_family = (
        f'"{appearance.font_family}", {_FONT_SANS}'
        if appearance.font_family
        else _FONT_SANS
    )
    h_btn_border = p.accent_strong
    controls_qss = _marathon_controls_qss(p, variant=variant, base_px=base_px)
    return f"""
QMainWindow, QDialog, QWidget {{
    background-color: {p.bg_base};
    color: {p.text_primary};
    font-family: {sans_family};
    font-size: {base_px}px;
}}

/* Stepped Card Surfaces & Flush Swiss 1px Borders */
QGroupBox {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-radius: 2px;
    margin-top: 11px;
    padding: 13px 11px 10px 11px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 1px;
    padding: 0px 6px;
    background-color: {p.bg_base};
    border: none;
    border-left: 3px solid {p.accent};
    color: {p.accent_strong if variant == "light" else p.accent_hover};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 700;
}}
QGroupBox QLabel,
QFrame[trackCard=true] QLabel,
QFrame#practiceCard QLabel,
QFrame#marathonTopbar QLabel,
QFrame[marathonCard="true"] QLabel,
QFrame#telemetryHeader QLabel,
QFrame#analysisMetric QLabel,
QFrame#analysisChart QLabel {{
    background: transparent;
}}

QFrame#marathonTopbar {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent};
    border-radius: 2px;
}}
QFrame#telemetryHeader {{
    background-color: transparent;
}}
QFrame#telemetryHeader[divider="true"] {{
    border-bottom: 1px solid {p.border};
}}
QLabel#telemetryEyebrow {{
    color: {p.accent};
    font-family: {_FONT_MONO};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#telemetryTitle {{
    color: {p.text_primary};
    font-size: {base_px + 3}px;
    font-weight: 700;
}}
QLabel#telemetryPill {{
    background-color: {p.bg_code};
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-radius: 2px;
    padding: 2px 7px;
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 600;
}}
QFrame[marathonCard="true"] {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-radius: 2px;
}}
QFrame[marathonCard="true"][accentRail="primary"] {{
    border-left: 3px solid {p.accent};
}}
QFrame[marathonCard="true"][accentRail="secondary"] {{
    border-left: 3px solid {p.accent_secondary};
}}
QFrame[marathonCard="true"][accentRail="obsidian"] {{
    border-left: 3px solid {p.border_strong};
}}
QFrame[trackCard=true], QFrame#practiceCard {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent};
    border-radius: 2px;
}}
QFrame#marathonDivider {{
    background-color: {p.border};
    max-height: 1px;
    min-height: 1px;
}}
{controls_qss}


/* Semantic Badges & Notice Banners (Cool Tech Blue warn, Signal Cyan ok, Red danger only) */
QLabel#statusBadge, QLabel#captureStatus, QLabel#aiStatusBadge, QLabel#bannerNotice {{
    border-radius: 3px;
    padding: 3px 8px;
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
}}
QLabel#bannerNotice {{
    border-left: 4px solid {p.accent_secondary};
    padding: 5px 10px;
}}
QLabel#statusBadge[tone="normal"],
QLabel#statusBadge[tone="ok"],
QLabel#bannerNotice[tone="ok"],
QLabel#captureStatus[tone="ok"],
QLabel#aiStatusBadge[tone="ok"] {{
    background-color: {p.status_ok_bg};
    color: {p.status_ok_fg};
    border: 1px solid {p.status_ok_bd};
    border-left: 4px solid {p.accent};
    font-weight: 700;
}}
QLabel#statusBadge[tone="warn"],
QLabel#bannerNotice[tone="warn"],
QLabel#captureStatus[tone="warn"],
QLabel#aiStatusBadge[tone="warn"] {{
    background-color: {p.status_warn_bg};
    color: {p.status_warn_fg};
    border: 1px solid {p.status_warn_bd};
    border-left: 4px solid {p.accent_secondary};
    font-weight: 700;
}}
QLabel#statusBadge[tone="error"],
QLabel#bannerNotice[tone="error"],
QLabel#captureStatus[tone="error"],
QLabel#aiStatusBadge[tone="error"] {{
    background-color: {p.status_danger_bg};
    color: {p.status_danger_fg};
    border: 1px solid {p.status_danger_bd};
    border-left: 4px solid {p.status_danger_bd};
    font-weight: 700;
}}
QLabel#bannerNotice[tone="info"],
QLabel#aiStatusBadge[tone="info"],
QLabel#captureStatus[tone="info"] {{
    background-color: {p.bg_code};
    color: {p.text_secondary};
    border: 1px solid {p.border};
}}
QLabel#bannerNotice[tone="info"] {{
    border-left: 4px solid {p.accent_secondary};
}}
QGroupBox#oomBanner {{
    background-color: {p.status_warn_bg};
    color: {p.status_warn_fg};
    border: 1px solid {p.status_warn_bd};
    border-left: 4px solid {p.status_warn_bd};
    border-radius: 3px;
    padding-top: 14px;
}}

/* Monospace Metrics, Typography Hierarchy & Cards */
QLabel#mutedCaption, QLabel#stemMetaDuration, QLabel#chromaCaption, QLabel#analysisCaption {{
    color: {p.text_muted};
    font-size: {max(10, base_px - 1)}px;
}}
QLabel#stemTrackTitle {{
    color: {p.text_primary};
    font-family: {_FONT_MONO};
    font-weight: 700;
    font-size: {base_px + 1}px;
}}
QLabel#chromaPrimary {{
    font-family: {_FONT_MONO};
    font-size: {base_px + 11}px;
    font-weight: 700;
    color: {p.accent};
}}
QLabel#chromaSecondaryHero {{
    font-family: {_FONT_MONO};
    font-size: {base_px + 9}px;
    font-weight: 700;
    color: {p.text_primary};
}}
QLabel#chromaWarnHero {{
    font-family: {_FONT_MONO};
    font-size: {base_px + 9}px;
    font-weight: 700;
    color: {p.accent_secondary};
}}
QLabel#chromaSubtle {{
    color: {p.text_secondary};
    font-weight: 600;
}}
QLabel#chromaSubtle[tone="warn"] {{
    color: {p.accent_secondary};
    font-weight: 700;
}}
QLabel#chromaCaption[tone="warn"] {{
    color: {p.accent_secondary};
    font-weight: 600;
}}
QLabel#chromaProgression {{
    padding: 5px 10px;
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent};
    border-radius: 3px;
    color: {p.text_primary};
    font-family: {_FONT_MONO};
    font-weight: 600;
}}
QLabel#chromaTrackStatus {{
    padding: 4px 10px;
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 3px;
    color: {p.text_muted};
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 1)}px;
}}
QLabel#chromaTrackStatus[tone="warn"] {{
    background-color: {p.status_warn_bg};
    color: {p.status_warn_fg};
    border-color: {p.status_warn_bd};
    font-weight: 700;
}}

QLabel#analysisHeading {{
    font-size: {base_px + 6}px;
    font-weight: 700;
    color: {p.text_primary};
}}
QFrame#analysisMetric {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent};
    border-radius: 3px;
}}
QFrame#analysisMetric[accentRail="secondary"] {{
    border-left: 3px solid {p.accent_secondary};
}}
QFrame#analysisChart {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-radius: 3px;
}}
QLabel#analysisChartHeading {{
    font-weight: 700;
    color: {p.text_primary};
}}
QLabel#analysisPitch {{
    color: {p.accent};
    font-family: {_FONT_MONO};
    font-size: {base_px + 13}px;
    font-weight: 700;
}}
QLabel#analysisValue {{
    color: {p.text_primary};
    font-family: {_FONT_MONO};
    font-size: {base_px + 4}px;
    font-weight: 700;
}}
QProgressBar {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: 3px;
    text-align: center;
    font-family: {_FONT_MONO};
    font-size: {max(10, base_px - 2)}px;
    color: {p.text_primary};
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 2px;
}}
QProgressBar#analysisLevel {{
    background-color: {p.bg_elevated};
    border: 0;
    border-radius: 2px;
}}
QProgressBar#analysisLevel::chunk {{
    background-color: {p.accent};
    border-radius: 2px;
}}

/* Practice & Settings Dialog Telemetry */
QLabel#practiceSectionTitle {{
    color: {p.accent};
    font-family: {_FONT_MONO};
    font-weight: 700;
}}
QLabel#practiceMeta {{
    color: {p.text_secondary};
}}
QLabel#practicePill {{
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 3px;
    padding: 3px 8px;
    color: {p.text_secondary};
    font-family: {_FONT_MONO};
}}
QLabel#practiceConvention {{
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent_secondary};
    border-radius: 3px;
    padding: 6px 10px;
    color: {p.text_secondary};
    font-family: {_FONT_MONO};
}}
QLabel#practiceFeedback {{
    color: {p.text_secondary};
    font-size: {max(10, base_px - 1)}px;
}}
QLabel#practiceFeedback[tone="ok"] {{
    color: {p.status_ok_fg};
    font-weight: 700;
}}
QLabel#practiceFeedback[tone="error"] {{
    color: {p.status_danger_fg};
    font-weight: 700;
}}

QLabel#settingsHeading {{
    font-size: {base_px + 9}px;
    font-weight: 700;
    color: {p.text_primary};
}}
QLabel#settingsPageHeading {{
    font-size: {base_px + 5}px;
    font-weight: 700;
    color: {p.text_primary};
}}
QLabel#settingsSubtitle {{
    color: {p.text_secondary};
}}
QWidget#settingsNavigation {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-radius: 3px;
}}
QPushButton#settingsNavButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    text-align: left;
    padding: 7px 9px;
    color: {p.text_secondary};
}}
QPushButton#settingsNavButton:hover {{
    background-color: {p.bg_code};
    border-color: {p.border};
    color: {p.text_primary};
}}
QPushButton#settingsNavButton:checked {{
    background-color: {p.accent_soft};
    border: 1px solid {p.accent_border};
    border-left: 3px solid {p.accent};
    color: {p.text_primary};
    font-weight: 700;
}}
QPushButton#settingsNavButton:focus {{
    border-color: {p.accent};
}}
QPushButton#stemMuteBtn:checked {{
    background-color: {p.status_warn_bg};
    color: {p.status_warn_fg};
    border: 1px solid {p.status_warn_bd};
    font-family: {_FONT_MONO};
    font-weight: 700;
}}
QPushButton#stemSoloBtn:checked {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border: 1px solid {h_btn_border};
    font-family: {_FONT_MONO};
    font-weight: 700;
}}
QLabel#monoTelemetry {{
    font-family: {_FONT_MONO};
    font-weight: 700;
    color: {p.text_primary};
}}
"""


def apply_marathon_plot_theme(
    plot: pg.PlotWidget,
    appearance: Appearance,
    variant: str = "light",
) -> None:
    p = get_marathon_palette(variant)
    plot.setBackground(p.plot_bg)
    base_px = max(10, int(appearance.font_size or 12) - 1)
    tick_font = QtGui.QFont(appearance.font_family) if appearance.font_family else QtGui.QFont("JetBrains Mono")
    tick_font.setPixelSize(base_px)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=p.text_primary, family=tick_font.family(), size=f"{max(11, int(appearance.font_size or 12))}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(tick_font)
        axis.setPen(p.plot_tick_pen)
        axis.setTextPen(p.plot_axis)
