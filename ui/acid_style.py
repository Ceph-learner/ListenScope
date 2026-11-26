"""Acid Telemetry v2 Graphic Realism UI tokens, QSS generator, PyQtGraph LUTs, and signature Qt widgets."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

try:
    import shiboken6
except Exception:  # pragma: no cover
    shiboken6 = None  # type: ignore[assignment]

from core.appearance import Appearance
from core.paths import get_bundle_root


def _is_qt_valid(obj: object) -> bool:
    if obj is None:
        return False
    if shiboken6 is not None:
        try:
            return bool(shiboken6.isValid(obj))
        except Exception:
            return False
    return True


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
        dock_bg="#14181C",
        dock_card="#1D2328",
        dock_ink="#F1F2EC",
        dock_border="#4B565B",
        status_ok_bg="#142310",
        status_ok_fg="#CEFF18",
        status_ok_bd="#CEFF18",
        status_warn_bg="#2B2108",
        status_warn_fg="#FFB020",
        status_warn_bd="#FFB020",
        status_danger_bg="#331118",
        status_danger_fg="#FF8FA0",
        status_danger_bd="#FF2442",
        plot_bg="#0E1216",
        plot_axis="#B8C2C0",
        plot_tick_pen="#2D3438",
        plot_wave="#CEFF18",
        plot_fft="#77DCE4",
        plot_log="#CEFF18",
        hist_plot_bg="#0E1216",
        hist_plot_axis="#B8C2C0",
        hist_plot_wave="#CEFF18",
        plot_region_rgba=(206, 255, 24, 38),
        plot_region_pen="#CEFF18",
        plot_playhead="#FF2442",
        plot_pr_cursor="#FF2442",
        cents_track_bg="#0B0D0F",
        cents_track_bd="#2D3438",
        cents_center_tick="#89918F",
        cents_in_tune="#CEFF18",
        cents_slight="#F59E0B",
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
        accent="#007A57",
        accent_hover="#008F66",
        accent_strong="#006648",
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
        status_ok_bd="#007A57",
        status_warn_bg="#FEF3C7",
        status_warn_fg="#92400E",
        status_warn_bd="#D97706",
        status_danger_bg="#FFE4E6",
        status_danger_fg="#BE123C",
        status_danger_bd="#E11D48",
        plot_bg="#F8FAFC",
        plot_axis="#334155",
        plot_tick_pen="#94A3B8",
        plot_wave="#007A57",
        plot_fft="#0284C7",
        plot_log="#007A57",
        hist_plot_bg="#F8FAFC",
        hist_plot_axis="#334155",
        hist_plot_wave="#0F766E",
        plot_region_rgba=(0, 122, 87, 34),
        plot_region_pen="#007A57",
        plot_playhead="#0284C7",
        plot_pr_cursor="#E11D48",
        cents_track_bg="#E2E8F0",
        cents_track_bd="#CBD5E1",
        cents_center_tick="#334155",
        cents_in_tune="#007A57",
        cents_slight="#D97706",
        cents_off="#E11D48",
        cents_idle="#64748B",
        micro_tag_bg="#C5FF00",
    ),
}

_FONT_SANS = '"Segoe UI", "Microsoft YaHei UI", "Malgun Gothic", "Yu Gothic UI", "Noto Sans CJK SC", "DejaVu Sans", sans-serif'
_FONT_DISPLAY = '"Segoe UI", "Microsoft YaHei UI", "Malgun Gothic", "Yu Gothic UI", "Noto Sans CJK SC", "DejaVu Sans", sans-serif'
_FONT_MONO = '"Cascadia Code", "Consolas", "Microsoft YaHei UI", "Malgun Gothic", "Yu Gothic UI", "DejaVu Sans Mono", monospace'
_FONT_UI_CJK = '"Segoe UI", "Microsoft YaHei UI", "Malgun Gothic", "Yu Gothic UI", "Cascadia Code", "Consolas", sans-serif'

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


def _oklab_light_colormap_lut(n: int = 256) -> np.ndarray:
    """Generate a 256-entry perceptual light-theme LUT in OKLab space with monotonically decreasing lightness."""
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)
    # Monotonic L from 0.97 (near paper white) down to 0.24 (deep teal-ink)
    L = 0.97 - 0.73 * np.power(t, 0.92)
    a = -0.065 * np.sin(np.pi * t) - 0.015 * t
    b = -0.070 * np.sin(np.pi * np.power(t, 0.85)) - 0.025 * t

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l3 = l_ * l_ * l_
    m3 = m_ * m_ * m_
    s3 = s_ * s_ * s_

    r_lin = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    g_lin = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    b_lin = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

    rgb_lin = np.clip(np.stack([r_lin, g_lin, b_lin], axis=-1), 0.0, 1.0)
    rgb = np.where(
        rgb_lin <= 0.0031308,
        12.92 * rgb_lin,
        1.055 * np.power(rgb_lin, 1.0 / 2.4) - 0.055,
    )
    rgb_u8 = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    alpha = np.full((n, 1), 255, dtype=np.uint8)
    return np.concatenate([rgb_u8, alpha], axis=1)


def acid_colormap_lut(kind: str, variant: str = "dark") -> np.ndarray:
    """Return a perceptual 256-entry RGBA LUT (dark: pyqtgraph inferno / matplotlib CC0; light: OKLab monotonic ramp)."""
    key = (kind, "light" if variant == "light" else "dark")
    cached = _LUT_CACHE.get(key)
    if cached is not None:
        return cached

    if key[1] == "dark":
        try:
            cmap = pg.colormap.get("inferno") if hasattr(pg, "colormap") else None
            if cmap is not None:
                lut = cmap.getLookupTable(0.0, 1.0, 256)
                _LUT_CACHE[key] = lut
                return lut
        except Exception:
            pass
        stops = np.array([0.0, 0.25, 0.55, 0.80, 1.0], dtype=np.float32)
        colors = ["#000004", "#420A68", "#932667", "#DD513A", "#FCFFA4"]
        lut = pg.ColorMap(pos=stops, color=[pg.mkColor(c) for c in colors]).getLookupTable(0.0, 1.0, 256)
    else:
        lut = _oklab_light_colormap_lut(256)
    _LUT_CACHE[key] = lut
    return lut


class ChamferBadge(QtWidgets.QWidget):
    """Dual-chamfered acoustic scope emblem cohesive with listenscope.svg (pure QPainter, zero QGraphicsEffect)."""

    def __init__(
        self,
        text: str = "LS",
        parent: QtWidgets.QWidget | None = None,
        *,
        size: QtCore.QSize = QtCore.QSize(36, 34),
        chamfer: int = 7,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._chamfer = max(4, int(chamfer))
        self._fill = QtGui.QColor("#00A878")
        self._border = QtGui.QColor("#00A878")
        self._fg = QtGui.QColor("#FFFFFF")
        self._secondary = QtGui.QColor("#77DCE4")
        self._peak = QtGui.QColor("#CEFF18")
        self._chassis = QtGui.QColor("#0B0D0F")
        self.setFixedSize(size)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_palette_colors(
        self,
        *,
        fill: str,
        border: str,
        fg: str = "#FFFFFF",
        secondary: str = "#77DCE4",
        peak: str = "#CEFF18",
        chassis: str = "#0B0D0F",
    ) -> None:
        self._fill = QtGui.QColor(fill)
        self._border = QtGui.QColor(border)
        self._fg = QtGui.QColor(fg)
        self._secondary = QtGui.QColor(secondary)
        self._peak = QtGui.QColor(peak)
        self._chassis = QtGui.QColor(chassis)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        w = float(self.width())
        h = float(self.height())
        c = min(float(self._chamfer), w * 0.32, h * 0.32)
        if w <= 8 or h <= 8:
            return

        # Outer dual-chamfered carbon chassis (top-right + bottom-left bevel)
        outer = QtGui.QPainterPath()
        outer.moveTo(0.75, 0.75)
        outer.lineTo(w - c, 0.75)
        outer.lineTo(w - 0.75, c)
        outer.lineTo(w - 0.75, h - 0.75)
        outer.lineTo(c * 0.72, h - 0.75)
        outer.lineTo(0.75, h - c * 0.72)
        outer.closeSubpath()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(outer, self._chassis)

        # Recessed telemetry instrument deck
        inset = 2.6
        ic = max(2.0, c - 1.4)
        inner = QtGui.QPainterPath()
        inner.moveTo(inset, inset)
        inner.lineTo(w - ic - 1.2, inset)
        inner.lineTo(w - inset, ic + 1.2)
        inner.lineTo(w - inset, h - inset)
        inner.lineTo(ic * 0.72 + 1.2, h - inset)
        inner.lineTo(inset, h - ic * 0.72 - 1.2)
        inner.closeSubpath()
        deck_col = QtGui.QColor(self._chassis).lighter(145)
        if deck_col == self._chassis:
            deck_col = QtGui.QColor("#141920")
        painter.fillPath(inner, deck_col)

        # Subtle oscilloscope baseline
        cy = h * 0.52
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QtGui.QPen(QtGui.QColor("#26323B"), 1.0))
        painter.drawLine(QtCore.QPointF(5.0, cy), QtCore.QPointF(w - 5.0, cy))

        # Top-left micro registration crosshair pip & bottom-left checkerboard hint
        pip = QtGui.QColor(self._secondary)
        pip.setAlpha(215)
        painter.fillRect(QtCore.QRectF(4.0, 4.0, 2.0, 2.0), pip)
        painter.fillRect(QtCore.QRectF(w - 6.0, h - 6.0, 2.0, 2.0), pip)

        # 5-bar sculpted acoustic frequency crest matching listenscope.svg
        ratios = (0.30, 0.58, 0.78, 0.50, 0.28)
        colors = (self._fill, self._fill, self._peak, self._secondary, self._fill)
        n_bars = len(ratios)
        pad_x = 5.5
        avail_w = max(10.0, w - 2.0 * pad_x)
        gap = 2.0
        bar_w = max(2.0, (avail_w - gap * (n_bars - 1)) / n_bars)
        total_w = bar_w * n_bars + gap * (n_bars - 1)
        start_x = (w - total_w) * 0.5
        max_bar_h = max(6.0, h - 13.0)

        for idx, (ratio, col) in enumerate(zip(ratios, colors)):
            bx = round(start_x + idx * (bar_w + gap))
            bh = max(3.0, round(max_bar_h * ratio))
            by = round(cy - bh * 0.5)
            painter.fillRect(QtCore.QRectF(bx, by, bar_w, bh), col)
            if idx == 2:
                # Crisp white scan-head peak cap above center frequency crest
                cap_y = max(4.0, by - 3.0)
                painter.fillRect(QtCore.QRectF(bx, cap_y, bar_w, 1.8), QtGui.QColor("#FFFFFF"))

        # Crisp outer contour stroke drawn last so bevel stays razor sharp
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(self._border, 1.35)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(outer)
        painter.end()


class ElidedLabel(QtWidgets.QLabel):
    """Single-line label that paints a clean trailing ellipsis instead of hard-clipping glyphs.

    `text()` always keeps the full original string (tests / i18n rely on it); only painting is elided.
    """

    def _cjk_height(self) -> int:
        fm = self.fontMetrics()
        return max(fm.height(), fm.lineSpacing(), fm.boundingRect("国Ag").height()) + 3

    def sizeHint(self) -> QtCore.QSize:  # type: ignore[override]
        hint = super().sizeHint()
        fm_h = self._cjk_height()
        return QtCore.QSize(min(hint.width(), 180), max(hint.height(), fm_h))

    def minimumSizeHint(self) -> QtCore.QSize:  # type: ignore[override]
        hint = super().minimumSizeHint()
        fm_h = self._cjk_height()
        return QtCore.QSize(min(hint.width(), 24), max(hint.height(), fm_h))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        txt = self.text()
        cr = self.contentsRect()
        fm = self.fontMetrics()
        if (
            self.wordWrap()
            or not txt
            or fm.horizontalAdvance(txt) <= cr.width()
            or self.textFormat() == QtCore.Qt.TextFormat.RichText
        ):
            super().paintEvent(event)
            return
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        p = QtGui.QPainter(self)
        self.style().drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        p.setFont(self.font())
        p.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        elided = fm.elidedText(txt, QtCore.Qt.TextElideMode.ElideRight, max(8, cr.width()))
        align = self.alignment() or (QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        p.drawText(cr, int(align), elided)
        p.end()


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
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 4 if divider else 0)
        outer.setSpacing(1)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        stack = QtWidgets.QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(2)

        self.eyebrow_lbl = ElidedLabel(eyebrow.upper())
        self.eyebrow_lbl.setObjectName("telemetryEyebrow")
        self.eyebrow_lbl.setMinimumHeight(16)
        self.eyebrow_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.title_lbl = ElidedLabel(title)
        self.title_lbl.setObjectName("telemetryTitle")
        self.title_lbl.setMinimumHeight(28)
        self.title_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
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

    def set_compact_mode(self, compact: bool) -> None:
        if self.badge_lbl is not None:
            self.badge_lbl.setVisible(not compact)
            if compact and self.badge_lbl.text():
                self.setToolTip(f"{self.eyebrow_lbl.text()} · {self.badge_lbl.text()}")
        self.eyebrow_lbl.setMinimumHeight(11 if compact else 16)
        self.title_lbl.setMinimumHeight(16 if compact else 28)


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
        if not _is_qt_valid(self):
            return False
        parent = self.parentWidget()
        if parent is not None and _is_qt_valid(parent) and obj is parent:
            et = ev.type()
            if et == QtCore.QEvent.Type.Destroy:
                try:
                    parent.removeEventFilter(self)
                except RuntimeError:
                    pass
                return False
            if et in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
                self.setGeometry(parent.rect())
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
    """Five-pip telemetry pulse confidence indicator (遥测微动画点阵，支持音乐动态脉冲)."""

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
        self._pulse_phase: float = 0.0
        self._energy: float = 0.0
        self._climax: float = 0.0
        self._strength: float = 0.70
        self._locked: bool = False
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

    def set_reactive_pulse(
        self,
        *,
        energy: float,
        climax: float,
        strength: float,
        phase: float,
        locked: bool = False,
    ) -> None:
        self._energy = max(0.0, min(1.0, float(energy)))
        self._climax = max(0.0, min(1.0, float(climax)))
        self._strength = max(0.0, min(1.0, float(strength)))
        self._pulse_phase = float(phase)
        self._locked = bool(locked)
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        eff_strength = 0.0 if self._locked else self._strength
        amp = eff_strength * (0.25 + 0.55 * self._energy + 0.40 * self._climax)
        for i in range(self._total):
            x = 2.0 + i * 11.0
            y = 2.0
            scale = 1.0
            if i < self._filled and eff_strength > 0.02 and self._energy > 0.04:
                wave = 0.5 + 0.5 * math.sin(self._pulse_phase * (1.4 + self._climax * 1.6) - i * 0.65)
                scale = 0.88 + 0.24 * amp * wave
            dia = 7.0 * scale
            off = (7.0 - dia) * 0.5
            rect = QtCore.QRectF(x + off, y + off, dia, dia)
            if i < self._filled:
                col = QtGui.QColor(self._color)
                alpha = 210 + int(45 * min(1.0, amp))
                col.setAlpha(min(255, alpha))
                p.setPen(QtGui.QPen(col, 1.1))
                p.setBrush(col)
            else:
                off_pen = QtGui.QColor(self._color)
                off_pen.setAlpha(95)
                p.setPen(QtGui.QPen(off_pen, 1.05))
                p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawEllipse(rect)
        p.end()


class TelemetryPulseStrip(QtWidgets.QWidget):
    """Compact vertical segmented micro-pulse bars reacting to music dynamics and animation strength."""

    def __init__(
        self,
        bar_count: int = 6,
        color: str = "#00A878",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bars = max(3, int(bar_count))
        self._color = QtGui.QColor(color)
        self._track = QtGui.QColor(color)
        self._track.setAlpha(45)
        self._energy: float = 0.0
        self._climax: float = 0.0
        self._strength: float = 0.70
        self._reactive: bool = True
        self._locked: bool = False
        self._phase: float = 0.0
        self._level_db: float = -120.0
        self._bands: list[float] | None = None
        self.setFixedSize(self._bars * 5 + 2, 14)

    def set_theme_color(self, color: str) -> None:
        self._color = QtGui.QColor(color)
        self._track = QtGui.QColor(color)
        self._track.setAlpha(42)
        if self.isVisible():
            self.update()

    def set_level(self, rms_db: float) -> None:
        self._level_db = float(rms_db)
        self._bands = None
        self._energy = max(0.0, min(1.0, (self._level_db + 60.0) / 60.0))
        if self.isVisible():
            self.update()

    def set_bands(self, levels) -> None:
        vals = [max(0.0, min(1.0, float(v))) for v in levels]
        if vals:
            self._bands = vals
            self._energy = max(vals)
        else:
            self._bands = None
            self._energy = 0.0
        if self.isVisible():
            self.update()

    def set_telemetry(
        self,
        *,
        energy: float,
        climax: float,
        strength: float,
        reactive: bool,
        locked: bool,
        phase: float,
    ) -> None:
        self._energy = max(0.0, min(1.0, float(energy)))
        self._climax = max(0.0, min(1.0, float(climax)))
        self._strength = max(0.0, min(1.0, float(strength)))
        self._reactive = bool(reactive)
        self._locked = bool(locked)
        self._phase = float(phase)
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        eff = 0.0 if self._locked else self._strength
        h_max = float(self.height() - 2)
        for i in range(self._bars):
            if self._bands is not None:
                idx = min(len(self._bands) - 1, int(i * len(self._bands) / self._bars))
                frac = max(0.10, min(1.0, self._bands[idx]))
            elif eff <= 0.02 or self._energy <= 0.01:
                frac = 0.14
            else:
                taper = 1.0 - 0.18 * abs(i - (self._bars - 1) * 0.5) / max(1.0, self._bars * 0.5)
                frac = max(0.14, min(1.0, (0.18 + 0.72 * self._energy + 0.20 * self._climax) * taper * max(0.25, eff)))
            bh = max(2.0, h_max * frac)
            x = 1 + i * 5
            p.fillRect(QtCore.QRectF(x, 1.0, 3.0, h_max), self._track)
            p.fillRect(QtCore.QRectF(x, 1.0 + (h_max - bh), 3.0, bh), self._color)
        p.end()


class SegmentedBatteryProgressBar(QtWidgets.QWidget):
    """Segmented battery-cell progress gauge with inter-cell gaps and sweeping telemetry pulse."""

    def __init__(
        self,
        cells: int = 16,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cells = max(6, int(cells))
        self._min = 0
        self._max = 100
        self._value = 0
        self._text_visible = True
        self._format = "%p%"
        self._active = False
        self._phase = 0.0
        self._strength = 0.70
        self._energy = 0.0
        self._climax = 0.0
        self._locked = False
        self._accent = QtGui.QColor("#00A878")
        self._accent_hi = QtGui.QColor("#77DCE4")
        self._shell_bg = QtGui.QColor("#F8FAFC")
        self._shell_border = QtGui.QColor("#090D14")
        self._empty_cell = QtGui.QColor("#E2E8F0")
        self._text_fg = QtGui.QColor("#090D14")
        self._is_acid = True

        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.setInterval(55)
        self._anim_timer.timeout.connect(self._on_tick)

        self.setMinimumHeight(22)
        self.setMaximumHeight(24)
        self.setMinimumWidth(160)

    def minimum(self) -> int:
        return self._min

    def maximum(self) -> int:
        return self._max

    def setRange(self, minimum: int, maximum: int) -> None:
        self._min = int(minimum)
        self._max = max(self._min + 1, int(maximum))
        self.setValue(self._value)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int) -> None:
        clamped = max(self._min, min(self._max, int(val)))
        if clamped != self._value:
            self._value = clamped
            self.update()

    def setTextVisible(self, visible: bool) -> None:
        self._text_visible = bool(visible)
        self.update()

    def setFormat(self, fmt: str) -> None:
        self._format = str(fmt or "%p%")
        self.update()

    def set_active(self, active: bool) -> None:
        want = bool(active)
        if want == self._active:
            return
        self._active = want
        if want and not self._locked and self._strength > 0.02:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_timer.stop()
        self.update()

    def set_theme_colors(
        self,
        *,
        accent: str,
        accent_hi: str,
        shell_bg: str,
        shell_border: str,
        empty_cell: str,
        text_fg: str,
        is_acid: bool = True,
    ) -> None:
        self._accent = QtGui.QColor(accent)
        self._accent_hi = QtGui.QColor(accent_hi)
        self._shell_bg = QtGui.QColor(shell_bg)
        self._shell_border = QtGui.QColor(shell_border)
        self._empty_cell = QtGui.QColor(empty_cell)
        self._text_fg = QtGui.QColor(text_fg)
        self._is_acid = bool(is_acid)
        self.update()

    def set_telemetry_params(
        self,
        *,
        strength: float,
        energy: float = 0.0,
        climax: float = 0.0,
        locked: bool = False,
    ) -> None:
        self._strength = max(0.0, min(1.0, float(strength)))
        self._energy = max(0.0, min(1.0, float(energy)))
        self._climax = max(0.0, min(1.0, float(climax)))
        self._locked = bool(locked)
        if self._active and not self._locked and self._strength > 0.02:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        elif not self._active or self._locked or self._strength <= 0.02:
            self._anim_timer.stop()
        if self.isVisible():
            self.update()

    def _on_tick(self) -> None:
        if not self.isVisible() or not self._active or self._locked or self._strength <= 0.02:
            return
        step = 0.16 + 0.14 * self._strength + 0.14 * self._climax
        self._phase = (self._phase + step) % max(1.0, float(self._cells))
        self.update()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # type: ignore[override]
        self._anim_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        if self._active and not self._locked and self._strength > 0.02 and not self._anim_timer.isActive():
            self._anim_timer.start()
        super().showEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, not self._is_acid)

        w = float(self.width())
        h = float(self.height())
        if w < 30 or h < 12:
            p.end()
            return

        txt_w = 38.0 if self._text_visible else 0.0
        cap_w = 4.0
        body_rect = QtCore.QRectF(1.0, 2.0, max(12.0, w - txt_w - cap_w - 6.0), h - 4.0)
        radius = 1.5 if self._is_acid else 4.0

        # Outer battery body
        p.setPen(QtGui.QPen(self._shell_border, 1.2))
        p.setBrush(self._shell_bg)
        p.drawRoundedRect(body_rect, radius, radius)

        # Positive battery terminal nub
        cap_h = max(6.0, body_rect.height() * 0.46)
        cap_rect = QtCore.QRectF(
            body_rect.right(),
            body_rect.center().y() - cap_h * 0.5,
            cap_w,
            cap_h,
        )
        p.setBrush(self._shell_border)
        p.drawRect(cap_rect)

        # Inner segmented cells with clean 2.5px spacing
        inner = body_rect.adjusted(3.0, 3.0, -3.0, -3.0)
        gap = 2.5
        cell_w = max(2.0, (inner.width() - gap * (self._cells - 1)) / self._cells)
        ratio = max(0.0, min(1.0, (self._value - self._min) / max(1, self._max - self._min)))
        filled_exact = ratio * self._cells
        filled_full = int(filled_exact)

        sweep_idx = self._phase if (self._active and not self._locked and self._strength > 0.02) else -1.0
        for idx in range(self._cells):
            cx = inner.left() + idx * (cell_w + gap)
            crect = QtCore.QRectF(cx, inner.top(), cell_w, inner.height())
            if idx < filled_full:
                col = QtGui.QColor(self._accent)
                if sweep_idx >= 0.0:
                    dist = abs(idx - (sweep_idx % max(1, filled_full)))
                    if dist < 1.5:
                        k = (1.5 - dist) / 1.5 * self._strength
                        col = QtGui.QColor(
                            int(col.red() + (self._accent_hi.red() - col.red()) * k),
                            int(col.green() + (self._accent_hi.green() - col.green()) * k),
                            int(col.blue() + (self._accent_hi.blue() - col.blue()) * k),
                        )
                p.fillRect(crect, col)
            elif idx == filled_full and self._active and not self._locked and self._strength > 0.02:
                pulse_a = int(70 + 135 * (0.5 + 0.5 * math.sin(self._phase * 1.4)) * self._strength)
                col = QtGui.QColor(self._accent)
                col.setAlpha(pulse_a)
                p.fillRect(crect, col)
            else:
                p.fillRect(crect, self._empty_cell)

        if self._text_visible:
            pct = int(round(ratio * 100))
            txt = self._format.replace("%p", str(pct))
            f = QtGui.QFont(self.font())
            f.setBold(True)
            f.setPixelSize(max(10, min(12, int(h * 0.55))))
            p.setFont(f)
            p.setPen(self._text_fg)
            p.drawText(
                QtCore.QRectF(cap_rect.right() + 4.0, 0.0, txt_w, h),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                txt,
            )
        p.end()


class MarqueeLabel(QtWidgets.QLabel):
    """Single-line label that scrolls smoothly at a moderate speed only when text overflows width."""

    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._offset: float = 0.0
        self._pause_ticks: int = 28
        self._gap_px: int = 44
        self._speed_px_per_tick: float = 1.25  # ~35 px/s @ 35ms -> moderate, readable
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._on_tick)

    def setText(self, text: str) -> None:  # type: ignore[override]
        if text != self.text():
            self._offset = 0.0
            self._pause_ticks = 28
        super().setText(text)
        self._update_scroll_state()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_scroll_state()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._update_scroll_state()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)

    def _needs_scroll(self) -> bool:
        if self.wordWrap() or not self.text():
            return False
        cr = self.contentsRect()
        if cr.width() <= 16:
            return False
        return self.fontMetrics().horizontalAdvance(self.text()) > cr.width() + 2

    def _update_scroll_state(self) -> None:
        if self.isVisible() and self._needs_scroll():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            if self._offset != 0.0:
                self._offset = 0.0
                self.update()

    def _on_tick(self) -> None:
        if not self.isVisible() or not self._needs_scroll():
            self._timer.stop()
            return
        if self._pause_ticks > 0:
            self._pause_ticks -= 1
            return
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        cycle = text_w + self._gap_px
        self._offset += self._speed_px_per_tick
        if self._offset >= cycle:
            self._offset = 0.0
            self._pause_ticks = 30
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self._needs_scroll():
            super().paintEvent(event)
            return
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        p = QtGui.QPainter(self)
        self.style().drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        cr = self.contentsRect()
        p.setClipRect(cr)
        p.setFont(self.font())
        p.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        txt = self.text()
        text_w = self.fontMetrics().horizontalAdvance(txt)
        x = float(cr.left()) - self._offset
        y_rect = QtCore.QRectF(x, float(cr.top()), float(text_w + 4), float(cr.height()))
        p.drawText(y_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, txt)
        second_x = x + text_w + self._gap_px
        if second_x < cr.right():
            p.drawText(
                QtCore.QRectF(second_x, float(cr.top()), float(text_w + 4), float(cr.height())),
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                txt,
            )
        p.end()


class FlowLayout(QtWidgets.QLayout):
    """Responsive wrapping layout so horizontal button/control rows never clip on narrow screens."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 4,
    ) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self._h_space = int(h_spacing)
        self._v_space = int(v_spacing)
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self) -> None:
        while self._items:
            self.takeAt(0)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:  # type: ignore[override]
        self._items.append(item)

    def count(self) -> int:  # type: ignore[override]
        return len(self._items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:  # type: ignore[override]
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:  # type: ignore[override]
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientation:  # type: ignore[override]
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QtCore.QRect) -> None:  # type: ignore[override]
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QtCore.QSize:  # type: ignore[override]
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:  # type: ignore[override]
        size = QtCore.QSize()
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, *, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_h = 0
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            sz = item.sizeHint()
            next_x = x + sz.width() + self._h_space
            if next_x - self._h_space > effective.right() and line_h > 0:
                x = effective.x()
                y += line_h + self._v_space
                next_x = x + sz.width() + self._h_space
                line_h = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), sz))
            x = next_x
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()


class MarqueeComboBox(QtWidgets.QComboBox):
    """ComboBox that smoothly scrolls overflowing current name & widens popup so items avoid '...'."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._offset: float = 0.0
        self._pause_ticks: int = 28
        self._cycles_done: int = 0
        self._max_cycles: int = 2
        self._hovered: bool = False
        self._kbd_focused: bool = False
        self._gap_px: int = 40
        self._speed_px_per_tick: float = 1.25  # ~35 px/s @ 35ms
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._on_tick)
        self._hover_intent_timer = QtCore.QTimer(self)
        self._hover_intent_timer.setSingleShot(True)
        self._hover_intent_timer.setInterval(150)
        self._hover_intent_timer.timeout.connect(self._on_hover_intent)
        self.currentIndexChanged.connect(self._reset_scroll)
        try:
            self.view().setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        except Exception:
            pass

    def _on_hover_intent(self) -> None:
        if self.isVisible() and self.underMouse():
            self._hovered = True
            self._cycles_done = 0
            self._pause_ticks = 8
            self._update_scroll_state()

    def _reset_scroll(self, *_args) -> None:
        self._offset = 0.0
        self._pause_ticks = 12
        self._cycles_done = 0
        txt = self.currentText()
        if txt:
            self.setToolTip(txt)
        self._update_scroll_state()

    def _text_rect(self) -> QtCore.QRect:
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        r = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            opt,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        return r.adjusted(2, 0, -2, 0)

    def _needs_scroll(self) -> bool:
        txt = self.currentText()
        if not txt:
            return False
        tr_rect = self._text_rect()
        if tr_rect.width() <= 16:
            return False
        return self.fontMetrics().horizontalAdvance(txt) > tr_rect.width() + 2

    def _update_scroll_state(self) -> None:
        active_trigger = self._hovered or self._kbd_focused
        if (
            self.isVisible()
            and self._needs_scroll()
            and active_trigger
            and _motion_enabled()
            and self._cycles_done < self._max_cycles
        ):
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            if self._offset != 0.0:
                self._offset = 0.0
                self.update()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:  # type: ignore[override]
        super().enterEvent(event)
        self._hover_intent_timer.start()

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        self._hover_intent_timer.stop()
        self._hovered = False
        super().leaveEvent(event)
        self._update_scroll_state()

    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        self._kbd_focused = event.reason() in (
            QtCore.Qt.FocusReason.TabFocusReason,
            QtCore.Qt.FocusReason.BacktabFocusReason,
        )
        if self._kbd_focused:
            self._cycles_done = 0
            self._pause_ticks = 8
        super().focusInEvent(event)
        self._update_scroll_state()

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        self._kbd_focused = False
        super().focusOutEvent(event)
        self._update_scroll_state()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._needs_scroll() and self.currentText():
            self.setToolTip(self.currentText())
        self._update_scroll_state()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._needs_scroll() and self.currentText():
            self.setToolTip(self.currentText())
        self._update_scroll_state()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # type: ignore[override]
        self._hovered = False
        self._timer.stop()
        super().hideEvent(event)

    def _on_tick(self) -> None:
        if not self.isVisible() or not self._needs_scroll() or not (self._hovered or self._kbd_focused):
            self._timer.stop()
            self._offset = 0.0
            self.update()
            return
        if self._pause_ticks > 0:
            self._pause_ticks -= 1
            return
        txt_w = self.fontMetrics().horizontalAdvance(self.currentText())
        if txt_w <= 0:
            return
        cycle = txt_w + self._gap_px
        self._offset += self._speed_px_per_tick
        if self._offset >= cycle:
            self._offset = 0.0
            self._pause_ticks = 24
            self._cycles_done += 1
            if self._cycles_done >= self._max_cycles:
                self._timer.stop()
        self.update()

    def showPopup(self) -> None:  # type: ignore[override]
        try:
            view = self.view()
            fm = view.fontMetrics()
            max_w = self.width()
            for i in range(self.count()):
                w = fm.horizontalAdvance(self.itemText(i)) + 36
                if w > max_w:
                    max_w = w
            view.setMinimumWidth(min(720, max_w))
        except Exception:
            pass
        super().showPopup()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self._needs_scroll():
            ph = self.placeholderText() if self.currentIndex() < 0 and not self.currentText() else ""
            if ph:
                tr_rect = self._text_rect()
                if tr_rect.width() > 0 and self.fontMetrics().horizontalAdvance(ph) > tr_rect.width():
                    opt = QtWidgets.QStyleOptionComboBox()
                    self.initStyleOption(opt)
                    opt.currentText = ""
                    p = QtWidgets.QStylePainter(self)
                    p.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, opt)
                    p.setClipRect(tr_rect)
                    p.setFont(self.font())
                    color = self.palette().color(
                        QtGui.QPalette.ColorGroup.Active if self.isEnabled() else QtGui.QPalette.ColorGroup.Disabled,
                        QtGui.QPalette.ColorRole.PlaceholderText,
                    )
                    p.setPen(color)
                    elided_ph = self.fontMetrics().elidedText(ph, QtCore.Qt.TextElideMode.ElideRight, tr_rect.width())
                    p.drawText(
                        tr_rect,
                        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                        elided_ph,
                    )
                    p.end()
                    return
            super().paintEvent(event)
            return
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ""
        p = QtWidgets.QStylePainter(self)
        p.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, opt)

        tr_rect = self._text_rect()
        p.setClipRect(tr_rect)
        p.setFont(self.font())
        color = self.palette().color(
            QtGui.QPalette.ColorGroup.Active if self.isEnabled() else QtGui.QPalette.ColorGroup.Disabled,
            QtGui.QPalette.ColorRole.Text,
        )
        p.setPen(color)
        txt = self.currentText()
        if not self._timer.isActive() and self._offset == 0.0:
            elided = self.fontMetrics().elidedText(txt, QtCore.Qt.TextElideMode.ElideRight, tr_rect.width())
            p.drawText(
                tr_rect,
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elided,
            )
            p.end()
            return
        txt_w = self.fontMetrics().horizontalAdvance(txt)
        x = float(tr_rect.left()) - self._offset
        p.drawText(
            QtCore.QRectF(x, float(tr_rect.top()), float(txt_w + 4), float(tr_rect.height())),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            txt,
        )
        second_x = x + txt_w + self._gap_px
        if second_x < tr_rect.right():
            p.drawText(
                QtCore.QRectF(second_x, float(tr_rect.top()), float(txt_w + 4), float(tr_rect.height())),
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                txt,
            )
        p.end()


def _motion_enabled() -> bool:
    """Respect the global「交互聚焦动画」switch for chrome micro-motion (lazy import avoids cycles)."""
    try:
        from ui.help_badge import is_focus_animations_enabled

        return bool(is_focus_animations_enabled())
    except Exception:
        return True


class AcidTabBar(QtWidgets.QTabBar):
    """Tab bar with a sliding 'signal-lock' rail that glides to the selected channel.

    The rail eases (OutCubic, 220 ms) from the previous tab to the new one — the motion reads as a
    tuner locking onto a new channel. Respects the global focus-animation switch (instant jump when off).
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rail_color = QtGui.QColor("#00A878")
        self._hover_color = QtGui.QColor("#94A3B8")
        self._rail_rect = QtCore.QRectF()
        self._from_rect = QtCore.QRectF()
        self._to_rect = QtCore.QRectF()
        self._hover_idx = -1
        self.setMouseTracking(True)
        self.setDrawBase(False)
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(220 if _motion_enabled() else 0)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim)
        self.currentChanged.connect(self._on_current_changed)

    def set_rail_colors(self, rail: str, hover: str) -> None:
        self._rail_color = QtGui.QColor(rail)
        self._hover_color = QtGui.QColor(hover)
        self.update()

    def _target_rect(self, idx: int) -> QtCore.QRectF:
        if idx < 0 or idx >= self.count():
            return QtCore.QRectF()
        r = QtCore.QRectF(self.tabRect(idx))
        return QtCore.QRectF(r.left() + 1.0, r.top(), max(0.0, r.width() - 2.0), 3.0)

    def _on_current_changed(self, idx: int) -> None:
        if not _is_qt_valid(self):
            return
        target = self._target_rect(idx)
        anim_on = _motion_enabled()
        self._anim.setDuration(220 if anim_on else 0)
        if not anim_on or self._rail_rect.isEmpty() or not self.isVisible():
            self._anim.stop()
            self._rail_rect = target
            self.update()
            return
        self._from_rect = QtCore.QRectF(self._rail_rect)
        self._to_rect = target
        self._anim.stop()
        self._anim.start()

    def _on_anim(self, value: object) -> None:
        if not _is_qt_valid(self):
            return
        try:
            t = float(value)  # type: ignore[arg-type]
        except Exception:
            t = 1.0
        a, b = self._from_rect, self._to_rect
        self._rail_rect = QtCore.QRectF(
            a.left() + (b.left() - a.left()) * t,
            b.top(),
            a.width() + (b.width() - a.width()) * t,
            b.height(),
        )
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._anim.state() != QtCore.QAbstractAnimation.State.Running:
            self._rail_rect = self._target_rect(self.currentIndex())

    def tabLayoutChange(self) -> None:  # type: ignore[override]
        super().tabLayoutChange()
        if _is_qt_valid(self) and self._anim.state() != QtCore.QAbstractAnimation.State.Running:
            self._rail_rect = self._target_rect(self.currentIndex())
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        idx = self.tabAt(event.position().toPoint())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.update()
        super().leaveEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # type: ignore[override]
        self._anim.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self.count() == 0:
            return
        if self._rail_rect.isEmpty():
            self._rail_rect = self._target_rect(self.currentIndex())
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        if 0 <= self._hover_idx < self.count() and self._hover_idx != self.currentIndex():
            hr = self._target_rect(self._hover_idx)
            hc = QtGui.QColor(self._hover_color)
            hc.setAlpha(200)
            p.fillRect(QtCore.QRectF(hr.left(), hr.top(), hr.width(), 2.0), hc)
        p.fillRect(self._rail_rect, self._rail_color)
        # Tiny leading notch (registration tick) at the rail head for an instrument-grade finish
        head = QtCore.QRectF(self._rail_rect.left(), self._rail_rect.bottom(), 3.0, 3.0)
        p.fillRect(head, self._rail_color)
        p.end()


class _AcidSplitterHandle(QtWidgets.QSplitterHandle):
    """Splitter handle painting a dot-matrix grip that lights up with the accent on hover / drag."""

    def __init__(self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QSplitter) -> None:
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self._hot = 0.0
        self._dragging = False
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, value: object) -> None:
        if not _is_qt_valid(self):
            return
        try:
            self._hot = float(value)  # type: ignore[arg-type]
        except Exception:
            self._hot = 0.0
        self.update()

    def _animate(self, target: float) -> None:
        if not _is_qt_valid(self):
            return
        if not _motion_enabled():
            self._anim.stop()
            self._hot = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._hot)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:  # type: ignore[override]
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        if not self._dragging:
            self._animate(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        self._dragging = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        self._dragging = False
        if not self.underMouse():
            self._animate(0.0)
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        sp = self.splitter()
        grip = QtGui.QColor(getattr(sp, "_grip_color", QtGui.QColor("#94A3B8")))
        accent = QtGui.QColor(getattr(sp, "_grip_accent", QtGui.QColor("#00A878")))
        line = QtGui.QColor(getattr(sp, "_grip_line", QtGui.QColor("#CBD5E1")))
        t = 1.0 if self._dragging else max(0.0, min(1.0, self._hot))
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        horizontal_bar = self.orientation() == QtCore.Qt.Orientation.Vertical  # handle runs horizontally
        mix = QtGui.QColor(
            int(grip.red() + (accent.red() - grip.red()) * t),
            int(grip.green() + (accent.green() - grip.green()) * t),
            int(grip.blue() + (accent.blue() - grip.blue()) * t),
        )
        if horizontal_bar:
            cy = h // 2
            if t > 0.02:
                rail = QtGui.QColor(accent)
                rail.setAlpha(int(70 * t))
                p.fillRect(0, cy, w, 1, rail)
            else:
                p.fillRect(0, cy, w, 1, line)
            n = 7
            span = n * 5
            x0 = w // 2 - span // 2
            for i in range(n):
                p.fillRect(x0 + i * 5, cy - 1, 2, 3 if i % 3 == 0 else 2, mix)
        else:
            cx = w // 2
            p.fillRect(cx, 0, 1, h, line if t <= 0.02 else QtGui.QColor(accent.red(), accent.green(), accent.blue(), int(70 * t)))
            n = 7
            span = n * 5
            y0 = h // 2 - span // 2
            for i in range(n):
                p.fillRect(cx - 1, y0 + i * 5, 3 if i % 3 == 0 else 2, 2, mix)
        p.end()


class AcidSplitter(QtWidgets.QSplitter):
    """QSplitter whose handles paint a dot-matrix grip (upper/lower & left/right rails)."""

    def __init__(self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._grip_color = QtGui.QColor("#94A3B8")
        self._grip_accent = QtGui.QColor("#00A878")
        self._grip_line = QtGui.QColor("#CBD5E1")
        self.setHandleWidth(9)
        self.setObjectName("acidSplitter")

    def createHandle(self) -> QtWidgets.QSplitterHandle:  # type: ignore[override]
        return _AcidSplitterHandle(self.orientation(), self)

    def set_grip_colors(self, *, grip: str, accent: str, line: str) -> None:
        self._grip_color = QtGui.QColor(grip)
        self._grip_accent = QtGui.QColor(accent)
        self._grip_line = QtGui.QColor(line)
        for i in range(self.count()):
            handle = self.handle(i)
            if handle is not None and _is_qt_valid(handle):
                handle.update()


class WorkspaceRailHandle(QtWidgets.QWidget):
    """Interactive horizontal grip rail between main workspace tabs and 120s history dock.

    Allows dragging to adjust the 120s history waveform height (or double-clicking to reset),
    while keeping `tabs` and `_history_box` as direct siblings in `_workspace_layout`.
    """

    rail_dragged = QtCore.Signal(int)
    rail_reset_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workspaceRailHandle")
        self.setFixedHeight(7)
        self.setCursor(QtCore.Qt.CursorShape.SplitVCursor)
        self.setMouseTracking(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self._grip = QtGui.QColor("#94A3B8")
        self._accent = QtGui.QColor("#00A878")
        self._line = QtGui.QColor("#CBD5E1")
        self._hot = 0.0
        self._dragging = False
        self._last_global_y = 0
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def set_grip_colors(self, *, grip: str, accent: str, line: str) -> None:
        self._grip = QtGui.QColor(grip)
        self._accent = QtGui.QColor(accent)
        self._line = QtGui.QColor(line)
        self.update()

    def _on_anim(self, value: object) -> None:
        if not _is_qt_valid(self):
            return
        try:
            self._hot = float(value)  # type: ignore[arg-type]
        except Exception:
            self._hot = 0.0
        self.update()

    def _animate(self, target: float) -> None:
        if not _is_qt_valid(self):
            return
        if not _motion_enabled():
            self._anim.stop()
            self._hot = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._hot)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:  # type: ignore[override]
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        if not self._dragging:
            self._animate(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_global_y = int(event.globalPosition().y())
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._dragging:
            gy = int(event.globalPosition().y())
            dy = gy - self._last_global_y
            if dy != 0:
                self._last_global_y = gy
                self.rail_dragged.emit(dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._dragging:
            self._dragging = False
            if not self.underMouse():
                self._animate(0.0)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.rail_reset_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        cy = h // 2
        t = 1.0 if self._dragging else max(0.0, min(1.0, self._hot))
        mix = QtGui.QColor(
            int(self._grip.red() + (self._accent.red() - self._grip.red()) * t),
            int(self._grip.green() + (self._accent.green() - self._grip.green()) * t),
            int(self._grip.blue() + (self._accent.blue() - self._grip.blue()) * t),
        )
        if t > 0.02:
            rail = QtGui.QColor(self._accent)
            rail.setAlpha(int(120 * t))
            p.fillRect(0, cy, w, 1, rail)
        else:
            p.fillRect(0, cy, w, 1, self._line)
        n = 9
        span = n * 5
        x0 = w // 2 - span // 2
        for i in range(n):
            p.fillRect(x0 + i * 5, cy - 1, 2, 3 if i % 4 == 0 else 2, mix)
        p.end()


def load_lucide_icon(name: str, color: str, size: int = 15) -> QtGui.QIcon:
    """Load a Lucide SVG from ui/assets/icons/ and replace currentColor at runtime."""
    try:
        from PySide6 import QtSvg
    except Exception:
        return QtGui.QIcon()

    icon_path = get_bundle_root() / "ui" / "assets" / "icons" / f"{name}.svg"
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parent / "assets" / "icons" / f"{name}.svg"
    if not icon_path.exists():
        return QtGui.QIcon()
    svg_data = icon_path.read_text("utf-8").replace("currentColor", color)
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_data.encode("utf-8")))
    if not renderer.isValid():
        return QtGui.QIcon()
    icon = QtGui.QIcon()
    for scale in (1, 2):
        px = size * scale
        pm = QtGui.QPixmap(px, px)
        pm.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QtCore.QRectF(0, 0, px, px))
        painter.end()
        pm.setDevicePixelRatio(float(scale))
        icon.addPixmap(pm)
    return icon


class WindowGlyphButton(QtWidgets.QPushButton):
    """Frameless window control painting unified Lucide SVG icons (minimize / maximize / restore / close)."""

    def __init__(self, kind: str, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._kind = kind
        self._maximized = False
        self._idle = QtGui.QColor("#334155")
        self._hover = QtGui.QColor("#FFFFFF")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

    def set_glyph_colors(self, idle: str, hover: str) -> None:
        self._idle = QtGui.QColor(idle)
        self._hover = QtGui.QColor(hover)
        self.update()

    def set_maximized(self, maximized: bool) -> None:
        if bool(maximized) != self._maximized:
            self._maximized = bool(maximized)
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        opt = QtWidgets.QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = ""
        sp = QtWidgets.QStylePainter(self)
        sp.drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, opt)
        col = self._hover if (self.underMouse() or self.isDown()) else self._idle
        if self._kind == "min":
            icon_name = "minus"
        elif self._kind == "max":
            icon_name = "copy" if self._maximized else "square"
        else:
            icon_name = "x"
        icon = load_lucide_icon(icon_name, col.name(), size=14)
        if not icon.isNull():
            pm = icon.pixmap(14, 14)
            x = int((self.width() - 14) / 2)
            y = int((self.height() - 14) / 2)
            sp.drawPixmap(x, y, pm)
        sp.end()


class FramelessDialogChrome(QtCore.QObject):
    """Reusable frameless rounded shell controller for QDialogs (Settings / Appearance / ChordPractice).

    Mirrors ListenScopeMainWindow's frameless behavior without causing stray Show events during __init__:
    - Applies FramelessWindowHint + 10px rounded shell border when `frameless=True`
    - Uses native Windows 11 DWM rounded corners (DWMWCP_ROUND=2) when available, with QRegion mask fallback
    - Supports dragging via `drag_header` and optional 8-edge resize via `shell_frame`
    - Owns a crisp vector `WindowGlyphButton("close", "×")` synced to theme colors
    """

    def __init__(
        self,
        dialog: QtWidgets.QDialog,
        shell_frame: QtWidgets.QFrame,
        drag_header: QtWidgets.QWidget,
        *,
        resizable: bool = True,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._shell = shell_frame
        self._drag_header = drag_header
        self._resizable = bool(resizable)
        self._frameless_applied: Optional[bool] = None
        self._win11_dwm_rounded = False
        self._torn_down = False
        self._drag_offset: Optional[QtCore.QPoint] = None
        self._resize_edges = QtCore.Qt.Edge(0)
        self._resize_start_global: Optional[QtCore.QPoint] = None
        self._resize_start_geom: Optional[QtCore.QRect] = None

        self._shell.setObjectName("dialogShellFrame")
        self._shell.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        if self._resizable:
            self._shell.setMouseTracking(True)
            self._shell.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

        self.close_btn = WindowGlyphButton("close", "×", drag_header)
        self.close_btn.setObjectName("windowCloseBtn")
        self.close_btn.setAccessibleName("关闭窗口")
        self.close_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.close_btn.setAutoDefault(False)
        self.close_btn.setDefault(False)
        self.close_btn.clicked.connect(dialog.reject)

        self._dialog.installEventFilter(self)
        self._shell.installEventFilter(self)
        if self._drag_header is not self._shell:
            self._drag_header.installEventFilter(self)

    @property
    def is_frameless(self) -> bool:
        return bool(self._frameless_applied)

    def sync_colors(self, idle: str, hover: str = "#FFFFFF") -> None:
        if _is_qt_valid(self.close_btn):
            self.close_btn.set_glyph_colors(idle, hover)

    def apply_frameless(self, frameless: bool) -> None:
        if self._torn_down or not _is_qt_valid(self._dialog) or not _is_qt_valid(self._shell):
            return
        want = bool(frameless)
        self._shell.setProperty("frameless", want)
        style = self._shell.style()
        if style is not None:
            style.unpolish(self._shell)
            style.polish(self._shell)
        self._shell.update()
        if _is_qt_valid(self.close_btn):
            self.close_btn.setVisible(want)

        if self._frameless_applied == want:
            if self._dialog.isVisible():
                self._update_rounded_mask()
            return

        was_visible = self._dialog.isVisible()
        saved_geom = QtCore.QRect(self._dialog.geometry()) if was_visible else None
        self._frameless_applied = want
        self._win11_dwm_rounded = False

        flags = (
            QtCore.Qt.WindowType.Dialog
            | QtCore.Qt.WindowType.WindowSystemMenuHint
            | QtCore.Qt.WindowType.WindowCloseButtonHint
        )
        if want:
            flags |= QtCore.Qt.WindowType.FramelessWindowHint
        self._dialog.setWindowFlags(flags)

        # Only re-show if dialog was already visible (prevents stray top-level Show events during __init__)
        if was_visible:
            self._dialog.show()
            if saved_geom is not None and saved_geom.isValid():
                self._dialog.setGeometry(saved_geom)
            self._apply_win11_dwm_rounding()
            self._update_rounded_mask()

    def _apply_win11_dwm_rounding(self) -> None:
        if sys.platform != "win32" or not self._frameless_applied or not _is_qt_valid(self._dialog):
            return
        if not self._dialog.isVisible():
            return
        try:
            win_ver = sys.getwindowsversion()
            if getattr(win_ver, "build", 0) >= 22000:
                hwnd = int(self._dialog.winId())
                if hwnd:
                    dwmapi = ctypes.windll.dwmapi
                    pref = ctypes.c_int(2)
                    hr = dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
                    if hr == 0:
                        self._win11_dwm_rounded = True
                        self._dialog.clearMask()
        except Exception:
            pass

    def _update_rounded_mask(self) -> None:
        if not _is_qt_valid(self._dialog):
            return
        if not self._frameless_applied or self._win11_dwm_rounded or self._dialog.isMaximized():
            self._dialog.clearMask()
            return
        w, h = self._dialog.width(), self._dialog.height()
        if w <= 0 or h <= 0:
            return
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(0, 0, w, h), 10.0, 10.0)
        self._dialog.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))

    def _hit_test_edges(self, local_pos: QtCore.QPoint) -> QtCore.Qt.Edge:
        if not self._frameless_applied or not self._resizable or not _is_qt_valid(self._dialog):
            return QtCore.Qt.Edge(0)
        m = 7
        w, h = self._dialog.width(), self._dialog.height()
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
        min_w = max(460, self._dialog.minimumWidth())
        min_h = max(360, self._dialog.minimumHeight())
        if self._resize_edges & QtCore.Qt.Edge.LeftEdge:
            geom.setLeft(min(geom.right() - min_w + 1, geom.left() + delta.x()))
        if self._resize_edges & QtCore.Qt.Edge.RightEdge:
            geom.setRight(max(geom.left() + min_w - 1, geom.right() + delta.x()))
        if self._resize_edges & QtCore.Qt.Edge.TopEdge:
            geom.setTop(min(geom.bottom() - min_h + 1, geom.top() + delta.y()))
        if self._resize_edges & QtCore.Qt.Edge.BottomEdge:
            geom.setBottom(max(geom.top() + min_h - 1, geom.bottom() + delta.y()))
        self._dialog.setGeometry(geom)

    def _is_interactive_child(self, child: Optional[QtWidgets.QWidget]) -> bool:
        cur = child
        while cur is not None and cur is not self._drag_header:
            if isinstance(
                cur,
                (
                    QtWidgets.QAbstractButton,
                    QtWidgets.QComboBox,
                    QtWidgets.QLineEdit,
                    QtWidgets.QAbstractSpinBox,
                    QtWidgets.QSlider,
                ),
            ):
                return True
            cur = cur.parentWidget()
        return False

    def teardown(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        for obj in (self._dialog, self._shell, self._drag_header):
            if _is_qt_valid(obj):
                try:
                    obj.removeEventFilter(self)
                except RuntimeError:
                    pass

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if self._torn_down or not _is_qt_valid(self) or not _is_qt_valid(watched) or not _is_qt_valid(self._dialog):
            return False
        etype = event.type()
        if etype == QtCore.QEvent.Type.Destroy:
            return False

        if watched is self._dialog:
            if etype == QtCore.QEvent.Type.Show:
                self._apply_win11_dwm_rounding()
                self._update_rounded_mask()
            elif etype == QtCore.QEvent.Type.Resize:
                self._update_rounded_mask()
            return False

        if not self._frameless_applied:
            return False

        if watched is self._shell and self._resizable:
            if etype == QtCore.QEvent.Type.HoverMove and not self._resize_edges:
                hev = event  # type: ignore[assignment]
                local = (
                    self._dialog.mapFromGlobal(hev.globalPosition().toPoint())
                    if hasattr(hev, "globalPosition")
                    else hev.position().toPoint()
                )
                cur = self._cursor_for_edges(self._hit_test_edges(local))
                if cur is not None:
                    self._dialog.setCursor(cur)
                else:
                    self._dialog.unsetCursor()
            elif etype == QtCore.QEvent.Type.MouseButtonPress:
                if isinstance(event, QtGui.QMouseEvent) and event.button() == QtCore.Qt.MouseButton.LeftButton:
                    local = self._dialog.mapFromGlobal(event.globalPosition().toPoint())
                    edges = self._hit_test_edges(local)
                    if edges:
                        wh = self._dialog.windowHandle()
                        if wh is not None and hasattr(wh, "startSystemResize"):
                            try:
                                if wh.startSystemResize(edges):
                                    return True
                            except Exception:
                                pass
                        self._resize_edges = edges
                        self._resize_start_global = event.globalPosition().toPoint()
                        self._resize_start_geom = QtCore.QRect(self._dialog.geometry())
                        return True
            elif etype == QtCore.QEvent.Type.MouseMove:
                if isinstance(event, QtGui.QMouseEvent):
                    if self._resize_edges and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        self._apply_software_resize(event.globalPosition().toPoint())
                        return True
                    if not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        local = self._dialog.mapFromGlobal(event.globalPosition().toPoint())
                        cur = self._cursor_for_edges(self._hit_test_edges(local))
                        if cur is not None:
                            self._dialog.setCursor(cur)
                        else:
                            self._dialog.unsetCursor()
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                self._resize_edges = QtCore.Qt.Edge(0)
                self._resize_start_global = None
                self._resize_start_geom = None
                self._dialog.unsetCursor()

        if watched is self._drag_header:
            if etype == QtCore.QEvent.Type.MouseButtonPress:
                if isinstance(event, QtGui.QMouseEvent) and event.button() == QtCore.Qt.MouseButton.LeftButton:
                    local_dlg = self._dialog.mapFromGlobal(event.globalPosition().toPoint())
                    edges = self._hit_test_edges(local_dlg)
                    if edges:
                        self._resize_edges = edges
                        self._resize_start_global = event.globalPosition().toPoint()
                        self._resize_start_geom = QtCore.QRect(self._dialog.geometry())
                        return True
                    child = self._drag_header.childAt(event.position().toPoint())
                    if not self._is_interactive_child(child):
                        wh = self._dialog.windowHandle()
                        if wh is not None and hasattr(wh, "startSystemMove"):
                            try:
                                if wh.startSystemMove():
                                    return True
                            except Exception:
                                pass
                        self._drag_offset = event.globalPosition().toPoint() - self._dialog.frameGeometry().topLeft()
                        return True
            elif etype == QtCore.QEvent.Type.MouseMove:
                if isinstance(event, QtGui.QMouseEvent):
                    if self._resize_edges and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        self._apply_software_resize(event.globalPosition().toPoint())
                        return True
                    if self._drag_offset is not None and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                        self._dialog.move(event.globalPosition().toPoint() - self._drag_offset)
                        return True
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                self._resize_edges = QtCore.Qt.Edge(0)
                self._resize_start_global = None
                self._resize_start_geom = None

        return False


class SignalLockDot(QtWidgets.QWidget):
    """Capture 'signal lock' indicator: hollow when idle, solid + breathing ring when listening.

    Driven by the existing telemetry phase tick (no extra timer). STATIC_LOCK freezes it solid.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self._phase = 0.0
        self._energy = 0.0
        self._locked = False
        self._strength = 0.7
        self._color = QtGui.QColor("#00A878")
        self._idle = QtGui.QColor("#94A3B8")
        self.setFixedSize(16, 16)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_colors(self, active: str, idle: str) -> None:
        self._color = QtGui.QColor(active)
        self._idle = QtGui.QColor(idle)
        self.update()

    def set_active(self, active: bool) -> None:
        if bool(active) != self._active:
            self._active = bool(active)
            self.update()

    def is_active(self) -> bool:
        return self._active

    def set_pulse(self, *, phase: float, energy: float, strength: float, locked: bool) -> None:
        self._phase = float(phase)
        self._energy = max(0.0, min(1.0, float(energy)))
        self._strength = max(0.0, min(1.0, float(strength)))
        self._locked = bool(locked)
        if self._active and self.isVisible():
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        c = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)
        if not self._active:
            p.setPen(QtGui.QPen(self._idle, 1.2))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawRect(QtCore.QRectF(c.x() - 3.5, c.y() - 3.5, 7.0, 7.0))
            p.end()
            return
        animate = not self._locked and self._strength > 0.02
        if animate:
            wave = 0.5 + 0.5 * math.sin(self._phase * 1.3)
            ring_r = 4.5 + 2.8 * wave * (0.5 + 0.5 * self._energy)
            ring = QtGui.QColor(self._color)
            ring.setAlpha(int(150 * (1.0 - wave) * self._strength) + 30)
            p.setPen(QtGui.QPen(ring, 1.1))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawRect(QtCore.QRectF(c.x() - ring_r, c.y() - ring_r, 2 * ring_r, 2 * ring_r))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawRect(QtCore.QRectF(c.x() - 3.5, c.y() - 3.5, 7.0, 7.0))
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
    """24px real telemetry status bar (version, capture source/rate, p50 ms, buffer, CPU%, reduce-motion toggle)."""

    static_lock_toggled = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._bg = QtGui.QColor("#1C2026")
        self._fg = QtGui.QColor("#B4BECB")
        self._border = QtGui.QColor("#2C323C")
        self._locked = False
        self._show_barcode = False
        self._source_name = "--"
        self._sample_rate_hz = 48000
        self._p50_ms: float | None = None
        self._buffer_sec: float = 0.0
        self._cpu_pct: float | None = None
        self.setFixedHeight(24)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 2, 10, 2)
        row.setSpacing(8)
        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setObjectName("monoTelemetry")
        row.addWidget(self.status_lbl, 1)

        self.lock_btn = QtWidgets.QPushButton("减少动效")
        self.lock_btn.setObjectName("acidStaticLockBtn")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.lock_btn.setFixedHeight(18)
        self.lock_btn.setToolTip("冻结界面遥测微动画（不影响实时频谱与和弦分析）")
        self.lock_btn.toggled.connect(self._on_lock_btn_toggled)
        row.addWidget(self.lock_btn)
        self._refresh_text()

    def _refresh_text(self) -> None:
        from core.version import get_app_version_display

        ver = get_app_version_display()
        p50_txt = f"{self._p50_ms:.1f}ms" if self._p50_ms is not None else "--"
        cpu_txt = f"{self._cpu_pct:.0f}%" if self._cpu_pct is not None else "--"
        khz = self._sample_rate_hz / 1000.0
        rate_txt = f"{khz:g}kHz"
        self.status_lbl.setText(
            f"v{ver}  |  {self._source_name} · {rate_txt}  |  p50: {p50_txt}  |  Buf: {self._buffer_sec:.1f}s  |  CPU: {cpu_txt}"
        )

    def set_telemetry(
        self,
        *,
        source_name: str | None = None,
        sample_rate_hz: int | None = None,
        p50_ms: float | None = None,
        buffer_sec: float | None = None,
        cpu_pct: float | None = None,
    ) -> None:
        if source_name is not None:
            self._source_name = source_name or "--"
        if sample_rate_hz is not None and sample_rate_hz > 0:
            self._sample_rate_hz = int(sample_rate_hz)
        if p50_ms is not None:
            self._p50_ms = float(p50_ms)
        if buffer_sec is not None:
            self._buffer_sec = float(buffer_sec)
        if cpu_pct is not None:
            self._cpu_pct = float(cpu_pct)
        self._refresh_text()

    def _on_lock_btn_toggled(self, checked: bool) -> None:
        self._locked = bool(checked)
        self.static_lock_toggled.emit(self._locked)

    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        val = bool(locked)
        self._locked = val
        self.lock_btn.blockSignals(True)
        self.lock_btn.setChecked(val)
        self.lock_btn.blockSignals(False)

    def set_colors(self, bg: str, fg: str = "#090D10", border: str | None = None) -> None:
        self._bg = QtGui.QColor(bg)
        self._fg = QtGui.QColor(fg)
        self._border = QtGui.QColor(border) if border else self._fg
        self.status_lbl.setStyleSheet(f"color: {self._fg.name()}; background: transparent;")
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        if not self.isVisible():
            return
        p = QtGui.QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self._bg)
        p.setPen(QtGui.QPen(self._border, 1))
        p.drawLine(0, 0, w, 0)
        p.end()


def _acid_asset_url(filename: str) -> str:
    """Resolve an Acid Telemetry SVG asset path from PyInstaller bundle or source checkout."""
    path = get_bundle_root() / "ui" / "assets" / filename
    if not path.exists():
        path = Path(__file__).resolve().parent / "assets" / filename
    return path.as_posix() if path.exists() else ""


def _mix_hex(hex_a: str, hex_b: str, t: float) -> str:
    """Linearly interpolate two hex colors (`#RRGGBB`) by weight `t` in [0, 1]."""
    ca = QtGui.QColor(hex_a)
    cb = QtGui.QColor(hex_b)
    if not ca.isValid() or not cb.isValid():
        return hex_a
    w = max(0.0, min(1.0, float(t)))
    r = int(round(ca.red() * (1.0 - w) + cb.red() * w))
    g = int(round(ca.green() * (1.0 - w) + cb.green() * w))
    b = int(round(ca.blue() * (1.0 - w) + cb.blue() * w))
    return f"#{r:02X}{g:02X}{b:02X}"


def _acid_controls_qss(
    p: AcidPalette,
    *,
    variant: str,
    base_px: int,
    mono_family: str,
    cjk_family: str = _FONT_UI_CJK,
    surface_style: str = "tactile",
) -> str:
    """Dedicated Acid Telemetry control QSS supporting tactile/beveled/flat edge finishes and balanced CJK fonts."""
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

    surf = surface_style if surface_style in ("tactile", "flat", "beveled") else "tactile"
    if surf == "tactile":
        rim_hi = "#FFFFFF" if is_light else _mix_hex(p.border_strong, "#FFFFFF", 0.34)
        rim_lo = _mix_hex(p.border_strong, "#000000", 0.28)
        btn_border = (
            f"border-top: 1px solid {rim_hi};"
            f" border-left: 1px solid {rim_hi};"
            f" border-right: 1px solid {rim_lo};"
            f" border-bottom: 2px solid {rim_lo};"
        )
        btn_pressed_border = (
            f"border-top: 2px solid {rim_lo};"
            f" border-left: 1px solid {rim_lo};"
            f" border-right: 1px solid {rim_hi};"
            f" border-bottom: 1px solid {rim_hi};"
            f" padding: 5px 9px 3px 11px;"
        )
        primary_hi = _mix_hex(p.accent, "#FFFFFF", 0.42)
        primary_lo = _mix_hex(p.accent, "#090D10", 0.38)
        primary_border = (
            f"border-top: 1px solid {primary_hi};"
            f" border-left: 1px solid {primary_hi};"
            f" border-right: 1px solid {primary_lo};"
            f" border-bottom: 2px solid {primary_lo};"
        )
    elif surf == "beveled":
        btn_border = f"border: 1px solid {p.border_strong}; border-bottom: 2px solid {p.border_strong};"
        btn_pressed_border = f"border: 1px solid {p.accent}; padding: 5px 9px 3px 11px;"
        primary_lo = _mix_hex(p.accent, "#090D10", 0.35)
        primary_border = f"border: 1px solid {p.accent}; border-bottom: 2px solid {primary_lo};"
    else:
        btn_border = f"border: 1px solid {p.border_strong};"
        btn_pressed_border = f"border: 1px solid {p.accent};"
        primary_border = f"border: 1px solid {p.accent};"

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
    padding: 3px 7px;
    min-height: 18px;
    font-family: {cjk_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 700;
    letter-spacing: 0px;
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

/* Crisp Tactile Action Rails & Buttons */
QPushButton, QToolButton {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    {btn_border}
    border-radius: 0px;
    padding: 4px 10px;
    min-height: 20px;
    font-family: {cjk_family};
    font-size: {btn_px}px;
    font-weight: 600;
    letter-spacing: 0px;
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
    {btn_pressed_border}
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
    border: 1px solid {p.border};
}}
QPushButton#analysisAction:enabled,
QPushButton#settingsSave:enabled,
QPushButton#acidPrimaryBtn:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    {primary_border}
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
    {btn_border}
    font-weight: 700;
}}
QPushButton#appearanceEntry:hover:enabled {{
    background-color: {p.accent};
    color: {p.text_inverse};
    border-color: {p.accent};
}}
QPushButton#captureBtn:checked {{
    background-color: {p.accent};
    {primary_border}
    color: {p.text_inverse};
    font-weight: 800;
}}
QPushButton#captureBtn:checked:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
    color: {p.text_inverse};
}}
QPushButton#emergencyStopBtn {{
    background-color: transparent;
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-radius: 0px;
    min-height: 20px;
    padding: 3px 9px;
    font-family: {cjk_family};
    font-size: {btn_px}px;
    font-weight: 700;
    outline: none;
}}
QPushButton#emergencyStopBtn:hover {{
    background-color: {p.bg_hover};
    border-color: {p.danger};
    color: {p.danger};
}}
QPushButton#emergencyStopBtn[ai_active="true"] {{
    background-color: {p.danger};
    color: #FFFFFF;
    border: 1px solid {p.danger};
    border-bottom: 2px solid #9A0E22;
    font-weight: 800;
}}
QPushButton#emergencyStopBtn[ai_active="true"]:hover {{
    background-color: #D91432;
    border-color: #FFFFFF;
    color: #FFFFFF;
}}
QPushButton#noticeDismissBtn {{
    background-color: transparent;
    color: {p.text_secondary};
    border: 1px solid transparent;
    border-radius: 0px;
    padding: 0px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    font-family: {mono_family};
    font-size: {base_px}px;
    font-weight: 800;
}}
QPushButton#noticeDismissBtn:hover {{
    background-color: {p.bg_hover};
    color: {p.text_primary};
    border: 1px solid {p.border_strong};
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
    spacing: 8px;
    padding: 2px 8px 2px 2px;
    color: {p.text_primary};
    background-color: transparent;
    outline: none;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
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
    width: 13px;
    height: 13px;
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
QCheckBox:focus,
QRadioButton:focus,
QSlider:focus,
QTabBar::tab:focus,
QToolButton#helpBadge:focus {{
    border: 2px solid {p.accent_secondary};
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
    font-family: {cjk_family};
    font-size: {btn_px}px;
    letter-spacing: 0px;
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
    font-family: {cjk_family};
    font-size: {btn_px}px;
    letter-spacing: 0px;
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
    font-family: {cjk_family};
    font-size: {btn_px}px;
    letter-spacing: 0px;
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
    background-color: {p.dock_ink if is_light else p.bg_elevated};
    color: {'#FFFFFF' if is_light else p.accent};
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
    color: {'#FFFFFF' if is_light else p.text_inverse};
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
    spacing: 8px;
    padding: 2px 8px 2px 2px;
}}
QGroupBox#historyPaperDock QCheckBox::indicator {{
    width: 15px;
    height: 15px;
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
    font-family: {cjk_family};
    font-size: {btn_px}px;
    font-weight: 600;
    letter-spacing: 0px;
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
    font-family: {cjk_family};
    font-size: {btn_px}px;
    letter-spacing: 0px;
    outline: 0;
}}
QHeaderView::section {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 0px;
    border-bottom: 1px solid {p.border_strong};
    border-right: 1px solid {p.border};
    padding: 4px 8px;
    font-family: {cjk_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 800;
    letter-spacing: 0px;
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
    background: {'#94A3B8' if is_light else p.border_strong};
    min-height: 20px;
}}
QScrollBar:horizontal {{
    background: {p.bg_code};
    height: 8px;
    margin: 1px;
}}
QScrollBar::handle:horizontal {{
    background: {'#94A3B8' if is_light else p.border_strong};
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
QSplitter#acidSplitter::handle,
QSplitter#acidSplitter::handle:hover {{
    background-color: transparent;
}}
QScrollArea#stemTrackScroll {{
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-left: 3px solid {p.accent};
    border-radius: 0px;
}}
QFrame#emptyStemBay {{
    background-color: {p.bg_panel};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent_secondary};
    border-radius: 0px;
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
    cjk_family = _FONT_UI_CJK
    surface_style = getattr(appearance, "ui_surface_style", "tactile")
    controls_qss = _acid_controls_qss(
        p,
        variant=p.variant,
        base_px=base_px,
        mono_family=mono_family,
        cjk_family=cjk_family,
        surface_style=surface_style,
    )
    primary_tone_fg = "#065F46" if is_light else p.accent
    return f"""
QMainWindow, QDialog {{
    background-color: {p.bg_base};
}}
QFrame#dialogShellFrame {{
    background-color: {p.bg_base};
    border: none;
}}
QWidget#mainShellFrame[frameless="true"],
QFrame#dialogShellFrame[frameless="true"] {{
    background-color: {p.bg_base};
    border: 1px solid {p.border_strong};
    border-radius: 10px;
}}
QPushButton#windowCtrlBtn {{
    background-color: transparent;
    color: {p.text_secondary};
    border: 1px solid transparent;
    border-radius: 0px;
    padding: 0px;
    min-width: 46px;
    max-width: 46px;
    min-height: 32px;
    max-height: 32px;
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
    background-color: transparent;
    color: {p.text_secondary};
    border: 1px solid transparent;
    border-radius: 0px;
    padding: 0px;
    min-width: 46px;
    max-width: 46px;
    min-height: 32px;
    max-height: 32px;
    font-family: {mono_family};
    font-size: {max(10, base_px - 1)}px;
    font-weight: 800;
}}
QPushButton#windowCloseBtn:hover {{
    background-color: #C42B1C;
    color: #FFFFFF;
    border-color: #C42B1C;
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
    font-family: {cjk_family};
    font-size: {mono_px}px;
    font-weight: 700;
    letter-spacing: 0px;
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
QFrame#topbarVDivider {{
    background-color: {p.border};
    min-width: 1px;
    max-width: 1px;
    border: none;
}}
QFrame#resourceCapsule {{
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-left: 3px solid {p.accent_secondary};
    border-radius: 0px;
}}
QFrame#resourceCapsule QLabel#monoTelemetry {{
    background-color: transparent;
    font-size: {max(10, base_px - 1)}px;
}}
QLabel#acidHeroTitle {{
    color: {p.ribbon_ink};
    background-color: {p.ribbon_bg};
    font-family: {display_family};
    font-size: {base_px + 2}px;
    font-weight: 700;
    padding: 1px 8px;
    border: 1px solid {p.ribbon_bg};
}}
QLabel#acidEchoTitle {{
    color: {p.text_muted};
    background-color: transparent;
    font-family: {display_family};
    font-size: {base_px + 2}px;
    font-weight: 700;
    padding: 1px 4px;
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
QLabel#brandEyebrow {{
    color: {p.text_secondary};
    font-family: {cjk_family};
    font-size: {max(10, base_px - 2)}px;
    font-weight: 700;
    letter-spacing: 0.25px;
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
    font-family: {cjk_family};
    font-size: {mono_px}px;
    letter-spacing: 0px;
}}
QFrame#bannerNoticeBox {{
    border-radius: 0px;
    background-color: {p.bg_code};
    border: 1px solid {p.border_strong};
    border-left: 4px solid {p.accent_secondary};
    padding: 1px 4px;
}}
QFrame#bannerNoticeBox[tone="ok"] {{
    background-color: {p.status_ok_bg};
    border: 1px solid {p.status_ok_bd};
    border-left: 4px solid {p.accent};
}}
QFrame#bannerNoticeBox[tone="warn"] {{
    background-color: {p.status_warn_bg};
    border: 1px solid {p.status_warn_bd};
    border-left: 4px solid {p.accent_secondary};
}}
QFrame#bannerNoticeBox[tone="error"] {{
    background-color: {p.status_danger_bg};
    border: 1px solid {p.status_danger_bd};
    border-left: 4px solid {p.status_danger_bd};
}}
QFrame#bannerNoticeBox[tone="info"] {{
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-left: 4px solid {p.accent_secondary};
}}
QLabel#bannerNotice[inlineBanner="true"] {{
    border: none;
    background-color: transparent;
    padding: 3px 6px;
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
QLabel#bannerNotice[inlineBanner="true"][tone="ok"],
QLabel#bannerNotice[inlineBanner="true"][tone="warn"],
QLabel#bannerNotice[inlineBanner="true"][tone="error"],
QLabel#bannerNotice[inlineBanner="true"][tone="info"] {{
    border: none;
    background-color: transparent;
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
    font-family: {cjk_family};
    font-size: {mono_px}px;
    font-weight: 600;
    letter-spacing: 0px;
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
    font-family: {cjk_family};
    font-weight: 600;
    letter-spacing: 0px;
}}
QLabel#chromaTrackStatus {{
    padding: 4px 10px;
    background-color: {p.bg_code};
    border: 1px solid {p.border};
    border-radius: 0px;
    color: {p.text_secondary};
    font-family: {cjk_family};
    font-size: {mono_px}px;
    letter-spacing: 0px;
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
    font-family: {cjk_family};
    font-size: {mono_px}px;
    font-weight: 600;
    letter-spacing: 0px;
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
    try:
        plot.hideButtons()
    except Exception:
        pass
    bg = p.hist_plot_bg if is_history else p.plot_bg
    axis_col = p.hist_plot_axis if is_history else p.plot_axis
    title_col = p.dock_ink if is_history else p.text_primary
    plot.setBackground(bg)
    tick_font = QtGui.QFont("Cascadia Mono")
    tick_font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
    tick_font.setPixelSize(10)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=title_col, family=tick_font.family(), size=f"{max(11, int(appearance.font_size or 12))}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(tick_font)
        axis.setPen(p.plot_tick_pen)
        axis.setTextPen(axis_col)
        try:
            axis.labelStyle["color"] = axis_col
            if axis.labelText:
                axis.setLabel(
                    text=axis.labelText,
                    units=axis.labelUnits,
                    unitPrefix=axis.labelUnitPrefix,
                    color=axis_col,
                )
        except Exception:
            pass

