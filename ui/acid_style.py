"""Acid Telemetry v2 Graphic Realism UI tokens, QSS generator, PyQtGraph LUTs, and signature Qt widgets."""

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
class AcidPalette:
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
    ribbon_bg: str
    ribbon_ink: str
    danger: str
    border: str
    border_strong: str
    dock_bg: str
    dock_card: str
    dock_ink: str
    dock_border: str
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
    hist_plot_bg: str
    hist_plot_axis: str
    hist_plot_wave: str
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
    micro_tag_bg: str


ACID_PALETTES: dict[str, AcidPalette] = {
    "dark": AcidPalette(
        variant="dark",
        bg_base="#0B0D0F",
        bg_panel="#14181C",
        bg_elevated="#1D2328",
        bg_hover="#273036",
        bg_code="#0E1216",
        text_primary="#F1F2EC",
        text_secondary="#89918F",
        text_muted="#6E7876",
        text_inverse="#090D10",
        accent="#CEFF18",
        accent_hover="#D9FF4D",
        accent_strong="#9ECA08",
        accent_soft="#202814",
        accent_border="#CEFF18",
        accent_secondary="#77DCE4",
        ribbon_bg="#2211FF",
        ribbon_ink="#FFFFFF",
        danger="#FF2442",
        border="#2D3438",
        border_strong="#4B565B",
        dock_bg="#E9EBE7",
        dock_card="#F4F5F2",
        dock_ink="#0B0D0F",
        dock_border="#9EA6A1",
        status_ok_bg="#142310",
        status_ok_fg="#CEFF18",
        status_ok_bd="#CEFF18",
        status_warn_bg="#0E2230",
        status_warn_fg="#77DCE4",
        status_warn_bd="#77DCE4",
        status_danger_bg="#331118",
        status_danger_fg="#FF8FA0",
        status_danger_bd="#FF2442",
        plot_bg="#0E1216",
        plot_axis="#89918F",
        plot_tick_pen="#2D3438",
        plot_wave="#CEFF18",
        plot_fft="#77DCE4",
        plot_log="#CEFF18",
        hist_plot_bg="#F4F5F2",
        hist_plot_axis="#0B0D0F",
        hist_plot_wave="#0B0D0F",
        plot_region_rgba=(34, 17, 255, 34),
        plot_region_pen="#2211FF",
        plot_playhead="#FF2442",
        plot_pr_cursor="#FF2442",
        cents_track_bg="#0B0D0F",
        cents_track_bd="#2D3438",
        cents_center_tick="#89918F",
        cents_in_tune="#CEFF18",
        cents_slight="#77DCE4",
        cents_off="#FF2442",
        cents_idle="#525A58",
        micro_tag_bg="#CEFF18",
    ),
    "light": AcidPalette(
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
        accent_border="#090D14",
        accent_secondary="#0284C7",
        ribbon_bg="#090D14",
        ribbon_ink="#FFFFFF",
        danger="#E11D48",
        border="#CBD5E1",
        border_strong="#090D14",
        dock_bg="#FFFFFF",
        dock_card="#F8FAFC",
        dock_ink="#090D14",
        dock_border="#CBD5E1",
        status_ok_bg="#E2E8F0",
        status_ok_fg="#065F46",
        status_ok_bd="#00A878",
        status_warn_bg="#E0F2FE",
        status_warn_fg="#0369A1",
        status_warn_bd="#0284C7",
        status_danger_bg="#FFE4E6",
        status_danger_fg="#BE123C",
        status_danger_bd="#E11D48",
        plot_bg="#F8FAFC",
        plot_axis="#334155",
        plot_tick_pen="#94A3B8",
        plot_wave="#00A878",
        plot_fft="#0284C7",
        plot_log="#00A878",
        hist_plot_bg="#F8FAFC",
        hist_plot_axis="#334155",
        hist_plot_wave="#0F766E",
        plot_region_rgba=(0, 168, 120, 34),
        plot_region_pen="#00A878",
        plot_playhead="#0284C7",
        plot_pr_cursor="#E11D48",
        cents_track_bg="#E2E8F0",
        cents_track_bd="#CBD5E1",
        cents_center_tick="#334155",
        cents_in_tune="#00A878",
        cents_slight="#0284C7",
        cents_off="#E11D48",
        cents_idle="#64748B",
        micro_tag_bg="#C5FF00",
    ),
}

_FONT_SANS = '"Segoe UI", "Microsoft YaHei UI", "Roboto", "Noto Sans CJK SC", "DejaVu Sans", sans-serif'
_FONT_DISPLAY = '"Segoe UI", "Roboto Condensed", "Microsoft YaHei UI", "Noto Sans CJK SC", "DejaVu Sans", sans-serif'
_FONT_MONO = '"Cascadia Code", "Consolas", "Liberation Mono", "DejaVu Sans Mono", "Noto Sans CJK SC", monospace'

_LUT_CACHE: dict[tuple[str, str], np.ndarray] = {}


def is_acid_eligible(appearance: Appearance) -> bool:
    """Return True when the active theme is the Acid Telemetry preset (custom colors/fonts are locked in Acid mode)."""
    return appearance.preset == "acid_telemetry"


def resolve_acid_variant(
    appearance: Appearance,
    *,
    acid_skin: Optional[str] = None,
    system_is_dark: Optional[bool] = None,
) -> Optional[str]:
    """Return 'dark' or 'light' when Acid Telemetry UI should style this view, else None."""
    if not is_acid_eligible(appearance):
        return None
    if acid_skin == "acid_light":
        return "light"
    if acid_skin == "acid_dark":
        return "dark"
    return appearance.resolve_theme_mode(system_is_dark=system_is_dark)


def get_acid_palette(variant: str = "dark") -> AcidPalette:
    return ACID_PALETTES["light" if variant == "light" else "dark"]


def acid_colormap_lut(kind: str, variant: str = "dark") -> np.ndarray:
    """Return a cool high-contrast 256-entry RGBA LUT for Spectrogram and Chroma heatmaps."""
    key = (kind, "light" if variant == "light" else "dark")
    cached = _LUT_CACHE.get(key)
    if cached is not None:
        return cached

    stops = np.array([0.0, 0.25, 0.55, 0.80, 1.0], dtype=np.float32)
    if key[1] == "dark":
        colors = (
            ["#0E1216", "#16202A", "#2211FF", "#77DCE4", "#CEFF18"]
            if kind == "spectrogram"
            else ["#0E1216", "#16202A", "#2211FF", "#77DCE4", "#CEFF18"]
        )
    else:
        colors = (
            ["#F8FAFC", "#E2E8F0", "#7DD3FC", "#0284C7", "#00A878"]
            if kind == "spectrogram"
            else ["#F8FAFC", "#E2E8F0", "#7DD3FC", "#0284C7", "#00A878"]
        )
    cmap = pg.ColorMap(pos=stops, color=[pg.mkColor(c) for c in colors])
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    _LUT_CACHE[key] = lut
    return lut


class ChamferBadge(QtWidgets.QWidget):
    """45-degree chamfered telemetry emblem with precision crosshair & pulse trace (zero QGraphicsEffect)."""

    def __init__(
        self,
        text: str = "LS",
        parent: QtWidgets.QWidget | None = None,
        *,
        size: QtCore.QSize = QtCore.QSize(36, 30),
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
        c = min(float(self._chamfer), w * 0.35, h * 0.35)
        if w <= 4 or h <= 4:
            return

        # Dual-chamfered industrial plate (top-right + bottom-left cut)
        path = QtGui.QPainterPath()
        path.moveTo(0.5, 0.5)
        path.lineTo(w - c, 0.5)
        path.lineTo(w - 0.5, c)
        path.lineTo(w - 0.5, h - 0.5)
        path.lineTo(c * 0.65, h - 0.5)
        path.lineTo(0.5, h - c * 0.65)
        path.closeSubpath()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(path, self._fill)
        painter.setPen(QtGui.QPen(self._border, 1.2))
        painter.drawPath(path)

        # Top-left micro registration pip + bottom-right spectrum bar accent
        sub_fg = QtGui.QColor(self._fg)
        sub_fg.setAlpha(185)
        painter.fillRect(QtCore.QRectF(3.0, 3.0, 2.5, 2.5), sub_fg)
        painter.fillRect(QtCore.QRectF(w - 6.0, h - 6.5, 2.5, 3.5), sub_fg)

        font = QtGui.QFont("Consolas")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        font.setBold(True)
        font.setPixelSize(max(10, min(13, round(h * 0.42))))
        painter.setFont(font)
        painter.setPen(self._fg)
        painter.drawText(QtCore.QRectF(0, -1, w - 1, h), QtCore.Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


class TelemetryHeader(QtWidgets.QFrame):
    """Bilingual Telemetry Header: uppercase monospace eyebrow + bold title + optional right strip."""

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
        self.eyebrow_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setObjectName("telemetryTitle")
        self.title_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

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


class AcidGraphicOverlay(QtWidgets.QWidget):
    """Mouse-agnostic Graphic Realism card overlay painting registration +, 2x2 checkerboard & tall stencil."""

    def __init__(self, parent: QtWidgets.QWidget, *, stencil: str = "") -> None:
        super().__init__(parent)
        self._stencil = stencil
        self._cross = QtGui.QColor(241, 242, 236, 65)
        self._stencil_col = QtGui.QColor(241, 242, 236, 15)
        self._checker_col = QtGui.QColor(206, 255, 24, 190)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        self.raise_()

    def set_colors(self, cross: QtGui.QColor, stencil: QtGui.QColor, checker: QtGui.QColor) -> None:
        self._cross = cross
        self._stencil_col = stencil
        self._checker_col = checker
        self.update()

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:
        if obj is self.parent() and ev.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            self.setGeometry(self.parentWidget().rect())
            if self.isVisible():
                self.raise_()
        return False

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        w, h = self.width(), self.height()
        if not self.isVisible() or w < 24 or h < 24:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        if self._stencil:
            font = QtGui.QFont("Segoe UI")
            font.setBold(True)
            font.setPixelSize(min(58, max(36, int(h * 0.36))))
            p.setFont(font)
            p.setPen(self._stencil_col)
            p.drawText(
                QtCore.QRect(max(0, w - 74), 30, 64, 66),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop,
                self._stencil,
            )

        # Crisp 7x7 registration crosshairs at top-left & bottom-right interior anchors
        p.setPen(QtGui.QPen(self._cross, 1))
        for cx, cy in ((8, 8), (w - 9, h - 9)):
            p.drawLine(cx - 3, cy, cx + 3, cy)
            p.drawLine(cx, cy - 3, cx, cy + 3)

        # Crisp 2x2 pixel checkerboard patch in bottom-right corner
        bx, by = w - 18, h - 18
        p.fillRect(bx, by, 4, 4, self._checker_col)
        p.fillRect(bx + 4, by + 4, 4, 4, self._checker_col)
        p.end()


class DotMatrixWidget(QtWidgets.QWidget):
    """Five-pip hardware telemetry confidence indicator (e.g. ●●●●○)."""

    def __init__(
        self,
        filled: int = 0,
        total: int = 5,
        color: str = "#CEFF18",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._total = max(1, int(total))
        self._filled = max(0, min(self._total, int(filled)))
        self._color = QtGui.QColor(color)
        self.setFixedSize(self._total * 11 + 2, 12)

    @property
    def filled_count(self) -> int:
        return self._filled

    def set_state(self, filled: int, color: Optional[str] = None) -> None:
        clamped = max(0, min(self._total, int(filled)))
        col = QtGui.QColor(color) if color else self._color
        if clamped == self._filled and col == self._color:
            return
        self._filled = clamped
        self._color = col
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        off_pen = QtGui.QColor(self._color)
        off_pen.setAlpha(110)
        for i in range(self._total):
            x = 2 + i * 11
            y = 2
            rect = QtCore.QRectF(x, y, 7.0, 7.0)
            if i < self._filled:
                p.setPen(QtGui.QPen(self._color, 1.1))
                p.setBrush(self._color)
            else:
                p.setPen(QtGui.QPen(off_pen, 1.1))
                p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawEllipse(rect)
        p.end()


class HazardStripeBar(QtWidgets.QWidget):
    """45-degree diagonal crimson warning accent bar placed next to Emergency Stop."""

    def __init__(self, color: str = "#FF2442", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self.setFixedSize(14, 26)

    def set_color(self, color: str) -> None:
        self._color = QtGui.QColor(color)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        p.setClipRect(self.rect())
        p.fillRect(self.rect(), QtGui.QColor("#090D10"))
        pen = QtGui.QPen(self._color, 3)
        p.setPen(pen)
        for offset in range(-28, 48, 7):
            p.drawLine(offset, self.height(), offset + self.height(), 0)
        p.setPen(QtGui.QPen(self._color, 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.end()


class AcidBarcodeFooter(QtWidgets.QWidget):
    """High-contrast acid telemetry footer strip with stencil, [STATIC_LOCK] toggle, and barcode."""

    static_lock_toggled = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._bg = QtGui.QColor("#CEFF18")
        self._fg = QtGui.QColor("#090D10")
        self._locked = False
        self.setFixedHeight(24)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(12, 2, 114, 2)
        row.setSpacing(8)
        row.addStretch(1)

        self.lock_btn = QtWidgets.QPushButton("[STATIC_LOCK: OFF]")
        self.lock_btn.setObjectName("acidStaticLockBtn")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setFixedHeight(18)
        self.lock_btn.toggled.connect(self._on_lock_btn_toggled)
        row.addWidget(self.lock_btn)

    def _on_lock_btn_toggled(self, checked: bool) -> None:
        self._locked = bool(checked)
        self.lock_btn.setText("[STATIC_LOCK: ON]" if self._locked else "[STATIC_LOCK: OFF]")
        self.update()
        self.static_lock_toggled.emit(self._locked)

    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        val = bool(locked)
        self._locked = val
        self.lock_btn.blockSignals(True)
        self.lock_btn.setChecked(val)
        self.lock_btn.setText("[STATIC_LOCK: ON]" if val else "[STATIC_LOCK: OFF]")
        self.lock_btn.blockSignals(False)
        self.update()

    def set_colors(self, bg: str, fg: str = "#090D10") -> None:
        self._bg = QtGui.QColor(bg)
        self._fg = QtGui.QColor(fg)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self._bg)
        p.setPen(QtGui.QPen(self._fg, 1))
        p.drawLine(0, 0, w, 0)

        f_tall = QtGui.QFont("Segoe UI")
        f_tall.setBold(True)
        f_tall.setPixelSize(12)
        p.setFont(f_tall)
        p.setPen(self._fg)
        p.drawText(QtCore.QRect(12, 0, 148, h), QtCore.Qt.AlignmentFlag.AlignVCenter, "SIGNAL_GRID // V2")

        # Keep center telemetry text strictly left of interactive [STATIC_LOCK] button
        text_left = 154
        text_right = max(text_left, self.lock_btn.x() - 10)
        avail_w = text_right - text_left
        if avail_w >= 48:
            f_mono = QtGui.QFont("Consolas")
            f_mono.setStyleHint(QtGui.QFont.StyleHint.Monospace)
            f_mono.setBold(True)
            f_mono.setPixelSize(10)
            p.setFont(f_mono)
            raw = "LISTENSCOPE_V0.2.4 :: 85/15_ANTI_FATIGUE: OK :: ZERO_GLOW: TRUE"
            elided = QtGui.QFontMetrics(f_mono).elidedText(raw, QtCore.Qt.TextElideMode.ElideRight, avail_w)
            p.drawText(QtCore.QRect(text_left, 0, avail_w, h), QtCore.Qt.AlignmentFlag.AlignVCenter, elided)

        # Crisp vertical barcode on right
        bars = [2, 1, 3, 1, 4, 1, 2, 3, 1, 2, 4, 1, 2, 3, 1, 2, 4, 1, 3]
        bx = w - 104
        for idx, bw in enumerate(bars):
            if bx + bw >= w - 8:
                break
            p.fillRect(bx, 4, bw, h - 8, self._fg)
            bx += bw + (2 if idx % 2 == 0 else 3)
        p.end()


def _acid_asset_url(filename: str) -> str:
    """Resolve an Acid Telemetry SVG asset path from PyInstaller bundle or source checkout."""
    path = get_bundle_root() / "ui" / "assets" / filename
    if not path.exists():
        path = Path(__file__).resolve().parent / "assets" / filename
    return path.as_posix() if path.exists() else ""


def _acid_controls_qss(
    p: AcidPalette,
    *,
    variant: str,
    base_px: int,
    mono_family: str,
) -> str:
    """Dedicated flat v2 Acid Telemetry control QSS (zero 3D bevel, zero Glow, sharp 0px edges)."""
    is_light = variant == "light"
    btn_px = max(10, base_px - 1)
    chev_down = _acid_asset_url("acid_chevron_down_light.svg" if is_light else "acid_chevron_down_dark.svg")
    chev_up = _acid_asset_url("acid_chevron_up_light.svg" if is_light else "acid_chevron_up_dark.svg")
    chk_svg = _acid_asset_url("acid_check_light.svg" if is_light else "acid_check_dark.svg")

    dock_chev_down = _acid_asset_url("acid_chevron_down_light.svg")
    dock_chev_up = _acid_asset_url("acid_chevron_up_light.svg")
    dock_chk_svg = _acid_asset_url("acid_check_light.svg" if is_light else "acid_check_dark.svg")

    tab_sel_bg = "#090D14" if is_light else p.accent
    tab_sel_fg = "#FFFFFF" if is_light else p.text_inverse
    table_sel_fg = "#065F46" if is_light else p.accent

    return f"""
/* Acid Segmented Pill Track (Topbar Skin Switcher) */
QWidget#acidModeGroup {{
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
}}
QPushButton#acidPillBtn {{
    background-color: transparent;
    color: {p.text_secondary};
    border: none;
    border-radius: 0px;
    padding: 3px 9px;
    min-height: 18px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 700;
    outline: none;
}}
QPushButton#acidPillBtn:hover {{
    color: {p.text_primary};
    background-color: {p.bg_elevated};
}}
QPushButton#acidPillBtn:checked {{
    background-color: {p.accent};
    color: {p.text_inverse};
    font-weight: 800;
}}

/* Global Zero-Bevel Flat Buttons & Action Rails */
QPushButton, QToolButton {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 4px 10px;
    min-height: 20px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    font-weight: 600;
    outline: none;
}}
QPushButton:hover:enabled {{
    background-color: {p.text_primary};
    color: {p.bg_base};
    border-color: {p.text_primary};
}}
QPushButton:pressed:enabled {{
    background-color: {p.bg_hover};
    color: {p.text_primary};
    border-color: {p.accent};
}}
QPushButton:checked {{
    background-color: {p.accent_soft};
    border: 1px solid {p.accent};
    color: {table_sel_fg};
    font-weight: 700;
}}
QPushButton:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QPushButton#analysisAction:enabled,
QPushButton#settingsSave:enabled,
QPushButton#acidPrimaryBtn:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border: 1px solid {p.accent};
    font-weight: 800;
}}
QPushButton#analysisAction:hover:enabled,
QPushButton#settingsSave:hover:enabled,
QPushButton#acidPrimaryBtn:hover:enabled {{
    background-color: {p.accent_hover};
    color: {p.text_inverse};
    border-color: {p.accent_hover};
}}
QPushButton#analysisAction:disabled,
QPushButton#settingsSave:disabled,
QPushButton#acidPrimaryBtn:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border: 1px solid {p.border};
}}
QPushButton#settingsSave {{
    padding: 4px 18px;
}}
QPushButton#appearanceEntry:enabled {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    font-weight: 700;
}}
QPushButton#appearanceEntry:hover:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border-color: {p.accent};
}}
QPushButton#captureBtn:checked {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    color: {p.text_inverse};
    font-weight: 800;
}}
QPushButton#captureBtn:checked:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
    color: {p.text_inverse};
}}
QPushButton#emergencyStopBtn {{
    background-color: {p.danger};
    color: #FFFFFF;
    border: 1px solid {p.danger};
    border-radius: 0px;
    min-height: 20px;
    padding: 4px 12px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    font-weight: 800;
    outline: none;
}}
QPushButton#emergencyStopBtn:hover {{
    background-color: #D91432;
    border-color: #FFFFFF;
    color: #FFFFFF;
}}
QPushButton#acidStaticLockBtn {{
    background-color: transparent;
    color: #090D10;
    border: 1px solid #090D10;
    border-radius: 0px;
    min-height: 16px;
    max-height: 18px;
    padding: 0px 6px;
    font-family: {mono_family};
    font-size: {max(9, base_px - 3)}px;
    font-weight: 800;
}}
QPushButton#acidStaticLockBtn:hover {{
    background-color: rgba(9, 13, 16, 28);
    color: #090D10;
    border-color: #090D10;
}}
QPushButton#acidStaticLockBtn:checked {{
    background-color: #090D10;
    color: {p.micro_tag_bg};
    border: 1px solid #090D10;
}}
QToolButton:hover:enabled {{
    background-color: {p.accent_soft};
    border-color: {p.accent};
    color: {p.text_primary};
}}
QToolButton#helpBadge {{
    background-color: {p.bg_code};
    color: {p.accent_secondary if is_light else p.accent};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 0px;
    min-height: 0px;
    width: 18px;
    height: 18px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 800;
}}
QToolButton#helpBadge:hover {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border-color: {p.accent};
}}

/* Flat Checkboxes, Radios & Caliper Sliders */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {p.text_primary};
    background-color: transparent;
    outline: none;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    background-color: {p.bg_code};
}}
QCheckBox::indicator:hover {{
    border-color: {p.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
    image: url("{chk_svg}");
}}
QCheckBox::indicator:disabled {{
    border-color: {p.border};
    background-color: {p.bg_elevated};
}}
QCheckBox::indicator:checked:disabled {{
    background-color: {p.text_muted};
    image: url("{chk_svg}");
}}
QRadioButton::indicator {{
    width: 12px;
    height: 12px;
    border-radius: 0px;
    border: 1px solid {p.border_strong};
    background-color: {p.bg_code};
}}
QRadioButton::indicator:checked {{
    background-color: {p.accent};
    border: 2px solid {p.bg_code};
    outline: 1px solid {p.accent};
}}
QSlider::groove:horizontal {{
    border: none;
    height: 3px;
    background: {p.border};
}}
QSlider::sub-page:horizontal {{
    background: {p.accent};
    border: none;
    height: 3px;
}}
QSlider::handle:horizontal {{
    background: {p.text_primary};
    border: 1px solid {p.accent};
    width: 7px;
    height: 14px;
    margin: -6px 0;
    border-radius: 0px;
}}
QSlider::handle:horizontal:hover {{
    background: {p.accent};
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

/* Flush Inputs, Custom Vector-Chevron Dropdowns & Flat Steppers */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 3px 7px;
    min-height: 20px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    selection-background-color: {p.accent};
    selection-color: {p.text_inverse};
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
    border-color: {p.accent};
}}
QComboBox, QFontComboBox {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 3px 26px 3px 8px;
    min-height: 20px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    outline: none;
}}
QComboBox:hover, QComboBox:on, QFontComboBox:hover {{
    border-color: {p.accent};
}}
QComboBox:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QComboBox::drop-down, QFontComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    background-color: transparent;
    border: none;
    border-left: 1px solid {p.border};
}}
QComboBox::drop-down:hover, QFontComboBox::drop-down:hover {{
    background-color: {p.accent_soft};
}}
QComboBox::down-arrow, QFontComboBox::down-arrow {{
    image: url("{chev_down}");
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 2px;
    outline: 0;
    selection-background-color: {p.accent};
    selection-color: {p.text_inverse};
}}
QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
    min-height: 20px;
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 3px 22px 3px 8px;
    min-height: 20px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    outline: none;
    selection-background-color: {p.accent};
    selection-color: {p.text_inverse};
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.accent};
}}
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {p.bg_elevated};
    color: {p.text_muted};
    border-color: {p.border};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    background-color: transparent;
    border: none;
    border-left: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    background-color: transparent;
    border: none;
    border-left: 1px solid {p.border};
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
    image: url("{chev_up}");
    width: 8px;
    height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{chev_down}");
    width: 8px;
    height: 8px;
}}

/* Clinical Paper Contrast Dock Override for 120s History GroupBox */
QGroupBox#historyPaperDock {{
    background-color: {p.dock_bg};
    color: {p.dock_ink};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
}}
QGroupBox#historyPaperDock::title {{
    background-color: {p.dock_ink};
    color: {'#FFFFFF' if is_light else '#CEFF18'};
    border-left: 3px solid {p.accent};
    padding: 1px 8px;
}}
QGroupBox#historyPaperDock QLabel {{
    color: {p.dock_ink};
    background-color: transparent;
}}
QGroupBox#historyPaperDock QPushButton,
QGroupBox#historyPaperDock QToolButton {{
    background-color: {p.dock_card};
    color: {p.dock_ink};
    border: 1px solid {p.dock_border};
}}
QGroupBox#historyPaperDock QPushButton:hover:enabled,
QGroupBox#historyPaperDock QToolButton:hover:enabled {{
    background-color: {p.dock_ink};
    color: #FFFFFF;
    border-color: {p.dock_ink};
}}
QGroupBox#historyPaperDock QToolButton#helpBadge {{
    padding: 0px;
    min-height: 0px;
    width: 18px;
    height: 18px;
    background-color: {p.dock_card};
    color: {p.dock_ink};
    border: 1px solid {p.dock_ink};
    font-family: {mono_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 800;
}}
QGroupBox#historyPaperDock QToolButton#helpBadge:hover {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border-color: {p.dock_ink};
}}
QGroupBox#historyPaperDock QPushButton#acidPrimaryBtn:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border: 1px solid #090D10;
    font-weight: 800;
}}
QGroupBox#historyPaperDock QPushButton#acidPrimaryBtn:hover:enabled {{
    background-color: {p.accent_hover};
    color: {p.text_inverse};
    border: 1px solid #090D10;
}}
QGroupBox#historyPaperDock QComboBox,
QGroupBox#historyPaperDock QSpinBox,
QGroupBox#historyPaperDock QDoubleSpinBox,
QGroupBox#historyPaperDock QLineEdit {{
    background-color: {p.dock_card};
    color: {p.dock_ink};
    border: 1px solid {p.dock_border};
}}
QGroupBox#historyPaperDock QComboBox::down-arrow {{
    image: url("{dock_chev_down}");
}}
QGroupBox#historyPaperDock QSpinBox::up-arrow,
QGroupBox#historyPaperDock QDoubleSpinBox::up-arrow {{
    image: url("{dock_chev_up}");
}}
QGroupBox#historyPaperDock QSpinBox::down-arrow,
QGroupBox#historyPaperDock QDoubleSpinBox::down-arrow {{
    image: url("{dock_chev_down}");
}}
QGroupBox#historyPaperDock QCheckBox {{
    color: {p.dock_ink};
    background-color: transparent;
}}
QGroupBox#historyPaperDock QCheckBox::indicator {{
    background-color: {p.dock_card};
    border: 1px solid {p.dock_ink};
}}
QGroupBox#historyPaperDock QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border: 1px solid {p.dock_ink};
    image: url("{dock_chk_svg}");
}}

/* Slash-Indexed Navigation Tabs */
QTabWidget::pane {{
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    background-color: {p.bg_base};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {p.bg_panel};
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-bottom: none;
    border-radius: 0px;
    padding: 6px 14px;
    margin-right: 2px;
    font-family: {mono_family};
    font-size: {btn_px}px;
    font-weight: 600;
    outline: none;
}}
QTabBar::tab:hover {{
    background-color: {p.bg_hover};
    color: {p.text_primary};
}}
QTabBar::tab:selected {{
    background-color: {tab_sel_bg};
    color: {tab_sel_fg};
    border: 1px solid {tab_sel_bg};
    border-top: 2px solid {p.ribbon_bg};
    font-weight: 800;
}}

/* Tables, Scrollbars & Menus */
QTableWidget {{
    background-color: {p.bg_panel};
    alternate-background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    gridline-color: {p.bg_elevated};
    selection-background-color: {p.bg_elevated};
    selection-color: {table_sel_fg};
    font-family: {mono_family};
    font-size: {btn_px}px;
    outline: 0;
}}
QHeaderView::section {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 0px;
    border-bottom: 1px solid {p.border_strong};
    border-right: 1px solid {p.border};
    padding: 4px 8px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 800;
}}
QTableWidget#practiceTable {{
    background-color: {p.bg_panel};
    alternate-background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    gridline-color: {p.bg_elevated};
    selection-background-color: {p.bg_elevated};
    selection-color: {table_sel_fg};
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
    background-color: {p.bg_elevated};
    color: {table_sel_fg};
}}
QMenu {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 3px;
}}
QMenu::item {{
    padding: 5px 14px;
}}
QMenu::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text_primary};
}}
QToolTip {{
    background-color: {p.bg_panel};
    color: {p.text_primary};
    border: 1px solid {p.accent};
    border-radius: 0px;
    padding: 5px 8px;
}}
QTableWidget#practiceTable QScrollBar:vertical,
QScrollBar:vertical {{
    background: {p.bg_code};
    width: 8px;
    margin: 1px;
}}
QTableWidget#practiceTable QScrollBar::handle:vertical,
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    min-height: 20px;
}}
QScrollBar:horizontal {{
    background: {p.bg_code};
    height: 8px;
    margin: 1px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    min-width: 20px;
}}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background: {p.accent};
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
QSplitter::handle {{
    background-color: {p.border};
    height: 3px;
    width: 3px;
}}
QSplitter::handle:hover {{
    background-color: {p.accent};
}}
"""


def acid_stylesheet(appearance: Appearance, variant: str = "dark") -> str:
    """Build the Acid Telemetry v2 Graphic Realism QSS stylesheet (font family & palette locked; font size adjustable)."""
    p = get_acid_palette(variant)
    is_light = p.variant == "light"
    base_px = max(11, int(appearance.font_size or 12))
    mono_px = max(10, base_px - 1)
    eye_px = max(9, base_px - 2)
    sans_family = _FONT_SANS
    display_family = _FONT_DISPLAY
    mono_family = _FONT_MONO
    controls_qss = _acid_controls_qss(p, variant=p.variant, base_px=base_px, mono_family=mono_family)
    primary_tone_fg = "#065F46" if is_light else p.accent
    return f"""
QMainWindow, QDialog {{
    background-color: {p.bg_base};
}}
QWidget#mainShellFrame[frameless="true"] {{
    background-color: {p.bg_base};
    border: 1px solid {p.border_strong};
    border-radius: 10px;
}}
QPushButton#windowCtrlBtn {{
    background-color: {p.bg_code};
    color: {p.text_secondary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 0px;
    min-width: 26px;
    max-width: 26px;
    min-height: 22px;
    max-height: 22px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 800;
}}
QPushButton#windowCtrlBtn:hover {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border-color: {p.accent};
}}
QPushButton#windowCloseBtn {{
    background-color: {p.bg_code};
    color: {p.text_secondary};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 0px;
    min-width: 26px;
    max-width: 26px;
    min-height: 22px;
    max-height: 22px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 800;
}}
QPushButton#windowCloseBtn:hover {{
    background-color: {p.danger};
    color: #FFFFFF;
    border-color: {p.danger};
}}
QMainWindow, QDialog, QWidget {{
    color: {p.text_primary};
    font-family: {sans_family};
    font-size: {base_px}px;
}}
QScrollArea,
QScrollArea > QWidget,
QScrollArea > QWidget > QWidget,
QScrollArea QWidget#qt_scrollarea_viewport,
QWidget#settingsScrollPage,
QStackedWidget,
QTabWidget::pane > QWidget,
QFrame#telemetryHeader,
QLabel,
QWidget#helpHolder,
QWidget#telemetryCell {{
    background-color: transparent;
}}

/* Stepped Sharp Architectural Cards & GroupBoxes */
QGroupBox {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    margin-top: 10px;
    padding: 12px 10px 9px 10px;
    font-family: {mono_family};
    font-size: {mono_px}px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0px 7px;
    background-color: {p.bg_base};
    color: {p.text_primary};
    border: none;
    border-left: 3px solid {p.accent};
}}

QFrame#acidTopbar {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
}}
QFrame#acidDivider {{
    background-color: {p.border};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLabel#acidHeroTitle {{
    color: {p.ribbon_ink};
    background-color: {p.ribbon_bg};
    font-family: {display_family};
    font-size: {base_px + 3}px;
    font-weight: 700;
    padding: 2px 8px;
    border: 1px solid {p.ribbon_bg};
}}
QLabel#acidEchoTitle {{
    color: {p.text_muted};
    background-color: transparent;
    font-family: {display_family};
    font-size: {base_px + 3}px;
    font-weight: 700;
    padding: 2px 4px;
}}
QLabel#acidHeroSub {{
    color: {p.text_secondary};
    font-family: {sans_family};
    font-size: {mono_px}px;
    font-weight: 500;
}}
QFrame#telemetryHeader {{
    background-color: transparent;
}}
QFrame#telemetryHeader[divider="true"] {{
    border-bottom: 1px solid {p.border};
}}
QLabel#telemetryEyebrow {{
    color: {p.text_secondary};
    font-family: {mono_family};
    font-size: {eye_px}px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#telemetryTitle {{
    color: {p.text_primary};
    font-family: {display_family};
    font-size: {base_px + 3}px;
    font-weight: 700;
}}
QLabel#telemetryPill {{
    background-color: {p.bg_elevated};
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 2px 7px;
    font-family: {mono_family};
    font-size: {eye_px}px;
    font-weight: 700;
}}
QLabel#acidMicroTag {{
    background-color: {p.micro_tag_bg};
    color: #090D10;
    border: 1px solid #090D10;
    border-radius: 0px;
    padding: 2px 6px;
    font-family: {mono_family};
    font-size: {eye_px}px;
    font-weight: 800;
}}

QFrame[acidCard="true"],
QFrame#analysisMetric,
QFrame#analysisChart,
QFrame#practiceCard,
QFrame[trackCard="true"] {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
}}
QFrame[acidCard="true"][accentRail="primary"],
QFrame#analysisMetric[accentRail="primary"],
QFrame[trackCard="true"],
QFrame#practiceCard {{
    border-left: 3px solid {p.accent};
}}
QFrame[acidCard="true"][accentRail="secondary"],
QFrame#analysisMetric[accentRail="secondary"] {{
    border-left: 3px solid {p.accent_secondary};
}}
QFrame[acidCard="true"][accentRail="obsidian"] {{
    border-left: 3px solid {p.ribbon_bg};
}}
{controls_qss}

/* Semantic Status Pills & Notice Banners */
QLabel#statusBadge, QLabel#captureStatus, QLabel#aiStatusBadge, QLabel#bannerNotice {{
    border-radius: 0px;
    padding: 3px 8px;
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    font-family: {mono_family};
    font-size: {mono_px}px;
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
    border-radius: 0px;
    padding-top: 14px;
}}

/* Typography Hierarchy, Hero Blocks & Cards */
QLabel#mutedCaption, QLabel#stemMetaDuration, QLabel#chromaCaption, QLabel#analysisCaption {{
    color: {p.text_secondary};
    font-size: {mono_px}px;
}}
QLabel#stemTrackTitle {{
    color: {p.text_primary};
    font-family: {display_family};
    font-weight: 800;
    font-size: {base_px + 1}px;
}}
QLabel#chromaPrimary {{
    color: {p.ribbon_ink};
    background-color: {p.ribbon_bg};
    font-family: {display_family};
    font-size: {base_px + 14}px;
    font-weight: 800;
    padding: 2px 10px;
}}
QLabel#chromaEcho {{
    color: {p.text_muted};
    background-color: transparent;
    font-family: {display_family};
    font-size: {base_px + 9}px;
    font-weight: 700;
}}
QLabel#chromaSecondaryHero {{
    color: {p.text_primary};
    font-family: {display_family};
    font-size: {base_px + 10}px;
    font-weight: 700;
}}
QLabel#chromaWarnHero {{
    color: {p.accent_secondary};
    font-family: {display_family};
    font-size: {base_px + 10}px;
    font-weight: 700;
}}
QLabel#chromaSubtle {{
    color: {p.text_primary};
    font-family: {mono_family};
    font-size: {mono_px}px;
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
    border: 1px solid {p.border_strong};
    border-left: 3px solid {p.accent};
    border-radius: 0px;
    color: {p.text_primary};
    font-family: {mono_family};
    font-weight: 600;
}}
QLabel#chromaTrackStatus {{
    padding: 4px 10px;
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 0px;
    color: {p.text_secondary};
    font-family: {mono_family};
    font-size: {mono_px}px;
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
QLabel#analysisChartHeading {{
    font-family: {mono_family};
    font-size: {mono_px}px;
    font-weight: 700;
    color: {p.text_primary};
}}
QLabel#analysisPitch {{
    color: {p.accent_secondary if is_light else p.accent};
    font-family: {display_family};
    font-size: {base_px + 10}px;
    font-weight: 800;
}}
QLabel#analysisValue {{
    color: {p.text_primary};
    font-family: {mono_family};
    font-size: {base_px + 6}px;
    font-weight: 700;
}}
QProgressBar {{
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    text-align: center;
    font-family: {mono_family};
    font-size: {max(10, base_px - 2)}px;
    color: {p.text_primary};
}}
QProgressBar::chunk {{
    background-color: {p.accent};
}}
QProgressBar#analysisLevel {{
    background-color: {p.bg_elevated};
    border: 0px;
    min-height: 4px;
    max-height: 4px;
}}
QProgressBar#analysisLevel::chunk {{
    background-color: {p.accent};
}}

/* Practice & Settings Dialog Telemetry */
QLabel#practiceSectionTitle {{
    color: {primary_tone_fg};
    font-family: {mono_family};
    font-weight: 700;
}}
QLabel#practiceMeta {{
    color: {p.text_primary};
}}
QLabel#practicePill {{
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-radius: 0px;
    padding: 3px 8px;
    color: {p.text_secondary};
    font-family: {mono_family};
}}
QLabel#practiceConvention {{
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-left: 3px solid {p.accent_secondary};
    border-radius: 0px;
    padding: 6px 10px;
    color: {p.text_secondary};
    font-family: {mono_family};
}}
QLabel#practiceFeedback {{
    color: {p.text_secondary};
    font-size: {mono_px}px;
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
    border: 1px solid {p.border_strong};
    border-radius: 0px;
}}
QPushButton#settingsNavButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 7px 9px;
    color: {p.text_secondary};
    font-family: {mono_family};
    font-size: {mono_px}px;
    font-weight: 600;
}}
QPushButton#settingsNavButton:hover {{
    background-color: {p.bg_elevated};
    border-color: {p.border};
    color: {p.text_primary};
}}
QPushButton#settingsNavButton:checked {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border_strong};
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
    font-family: {mono_family};
    font-weight: 700;
}}
QPushButton#stemSoloBtn:checked {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border: 1px solid {p.accent};
    font-family: {mono_family};
    font-weight: 700;
}}
QPlainTextEdit#diagnosticLogStream {{
    background-color: {p.bg_code};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
    border-left: 3px solid {p.accent_secondary};
    font-family: {mono_family};
    font-size: {mono_px}px;
}}
QLabel#monoTelemetry {{
    font-family: {mono_family};
    font-weight: 700;
    color: {p.text_primary};
}}
"""


def apply_acid_plot_theme(
    plot: pg.PlotWidget,
    appearance: Appearance,
    variant: str = "dark",
    *,
    is_history: bool = False,
) -> None:
    p = get_acid_palette(variant)
    bg = p.hist_plot_bg if is_history else p.plot_bg
    axis_col = p.hist_plot_axis if is_history else p.plot_axis
    title_col = p.dock_ink if is_history else p.text_primary
    plot.setBackground(bg)
    base_px = max(10, int(appearance.font_size or 12) - 1)
    tick_font = QtGui.QFont("Consolas")
    tick_font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
    tick_font.setPixelSize(base_px)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=title_col, family=tick_font.family(), size=f"{max(11, int(appearance.font_size or 12))}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(tick_font)
        axis.setPen(p.plot_tick_pen)
        axis.setTextPen(axis_col)

