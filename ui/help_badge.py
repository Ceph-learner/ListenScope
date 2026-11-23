"""Lightweight self-painted `[?]` contextual help badge, hover popover, and focus animator.

Zero QGraphicsEffect usage for minimal RAM and smooth 60fps interaction.
"""

from __future__ import annotations

from dataclasses import dataclass
import weakref
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

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


@dataclass
class _HelpTheme:
    bg: str = "#FFFFFF"
    fg: str = "#090D14"
    accent: str = "#00A859"
    border: str = "#11161F"
    muted: str = "#526071"
    is_dark: bool = False
    is_acid: bool = True


_HELP_MODE_ENABLED: bool = True
_FOCUS_ANIMATIONS_ENABLED: bool = True
_FOCUS_STYLE: str = "sleek"
_CURRENT_LANGUAGE: str = "zh"
_CURRENT_THEME: _HelpTheme = _HelpTheme()
_LIVE_BADGES: "weakref.WeakSet[HelpBadge]" = weakref.WeakSet()
_LIVE_ANIMATORS: "weakref.WeakSet[FocusRingAnimator]" = weakref.WeakSet()
_SHARED_POPOVER: Optional["_HelpPopover"] = None


def is_help_mode_enabled() -> bool:
    return _HELP_MODE_ENABLED


def is_focus_animations_enabled() -> bool:
    return _FOCUS_ANIMATIONS_ENABLED


def get_focus_ring_style() -> str:
    return _FOCUS_STYLE


def set_focus_ring_style(style: str) -> None:
    """Set focus ring visual mode ('sleek', 'brackets', 'underline') across live windows."""
    global _FOCUS_STYLE
    norm = str(style or "sleek").strip().lower()
    if norm not in ("sleek", "brackets", "underline"):
        norm = "sleek"
    _FOCUS_STYLE = norm
    for anim in list(_LIVE_ANIMATORS):
        try:
            anim.set_style(norm)
        except RuntimeError:
            pass


def set_help_mode_enabled(enabled: bool) -> None:
    """Globally show or hide all HelpBadge instances (说明模式)."""
    global _HELP_MODE_ENABLED
    _HELP_MODE_ENABLED = bool(enabled)
    for badge in list(_LIVE_BADGES):
        try:
            badge._sync_help_mode()
        except RuntimeError:
            pass
    if not _HELP_MODE_ENABLED and _SHARED_POPOVER is not None:
        try:
            _SHARED_POPOVER.hide()
        except RuntimeError:
            pass


def set_focus_animations_enabled(enabled: bool) -> None:
    """Globally enable or disable hover/focus micro-animations."""
    global _FOCUS_ANIMATIONS_ENABLED
    _FOCUS_ANIMATIONS_ENABLED = bool(enabled)
    for badge in list(_LIVE_BADGES):
        try:
            if not _FOCUS_ANIMATIONS_ENABLED:
                badge._hover_anim.stop()
                badge._hover_progress = 1.0 if badge.underMouse() else 0.0
                badge.update()
        except RuntimeError:
            pass
    for anim in list(_LIVE_ANIMATORS):
        try:
            anim.set_enabled(_FOCUS_ANIMATIONS_ENABLED)
        except RuntimeError:
            pass


def set_help_language(lang: str) -> None:
    """Translate all live HelpBadge titles/explanations to the target language."""
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = str(lang or "zh").strip().lower() or "zh"
    for badge in list(_LIVE_BADGES):
        try:
            badge.apply_language(_CURRENT_LANGUAGE)
        except RuntimeError:
            pass


def set_help_theme(
    *,
    bg: str,
    fg: str,
    accent: str,
    border: str,
    muted: str = "#64748B",
    is_dark: bool = False,
    is_acid: bool = True,
) -> None:
    """Update theme palette for all HelpBadge instances, hover popovers, and focus rings."""
    global _CURRENT_THEME
    _CURRENT_THEME = _HelpTheme(
        bg=bg,
        fg=fg,
        accent=accent,
        border=border,
        muted=muted,
        is_dark=is_dark,
        is_acid=is_acid,
    )
    for badge in list(_LIVE_BADGES):
        try:
            badge.update()
        except RuntimeError:
            pass
    if _SHARED_POPOVER is not None:
        try:
            _SHARED_POPOVER.apply_theme(_CURRENT_THEME)
        except RuntimeError:
            pass
    for anim in list(_LIVE_ANIMATORS):
        try:
            anim.set_accent(accent, is_acid=is_acid)
        except RuntimeError:
            pass


def _translate_help_pair(title: str, explanation: str, lang: str) -> tuple[str, str]:
    try:
        from core.i18n import translate_help
        return translate_help(title, explanation, lang)
    except Exception:
        return title, explanation


class _HelpPopover(QtWidgets.QFrame):
    """Lightweight themed hover card that appears automatically on HelpBadge hover."""

    def __init__(self) -> None:
        super().__init__(
            None,
            QtCore.Qt.WindowType.ToolTip
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("helpPopoverCard")
        self._anchor: Optional["HelpBadge"] = None
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(170)
        self._hide_timer.timeout.connect(self._check_and_hide)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        self._title_lbl = QtWidgets.QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._body_lbl = QtWidgets.QLabel()
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._body_lbl.setMaximumWidth(360)

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._body_lbl)
        self.apply_theme(_CURRENT_THEME)

    def apply_theme(self, theme: _HelpTheme) -> None:
        radius = 2 if theme.is_acid else 8
        accent_border = theme.accent if theme.is_dark else theme.border
        self.setStyleSheet(
            f"QFrame#helpPopoverCard {{"
            f"  background-color: {theme.bg};"
            f"  color: {theme.fg};"
            f"  border: 1.5px solid {accent_border};"
            f"  border-radius: {radius}px;"
            f"}}"
            f"QFrame#helpPopoverCard QLabel {{"
            f"  background: transparent;"
            f"  border: none;"
            f"  color: {theme.fg};"
            f"}}"
        )
        title_color = theme.accent if theme.is_dark else theme.fg
        self._title_lbl.setStyleSheet(
            f"font-weight: 700; font-size: 12px; color: {title_color};"
            f"border-bottom: 1px solid {theme.border}; padding-bottom: 4px;"
        )
        self._body_lbl.setStyleSheet(
            f"font-size: 11.5px; line-height: 1.45; color: {theme.fg};"
        )

    def show_for(self, badge: "HelpBadge", title: str, explanation: str) -> None:
        win = badge.window()
        if (
            not _HELP_MODE_ENABLED
            or badge.isHidden()
            or badge.parentWidget() is None
            or (win is not None and (not badge.isVisibleTo(win) or not win.isVisible() or not win.isActiveWindow()))
        ):
            self.hide()
            return
        self._hide_timer.stop()
        self._anchor = badge
        self.apply_theme(_CURRENT_THEME)
        self._title_lbl.setVisible(bool(title))
        self._title_lbl.setText(f"{title}")
        formatted_body = explanation.replace("\n", "<br/>")
        self._body_lbl.setText(formatted_body)
        self.adjustSize()

        anchor_rect = QtCore.QRect(
            badge.mapToGlobal(QtCore.QPoint(0, 0)),
            badge.size(),
        )
        screen = QtWidgets.QApplication.screenAt(anchor_rect.center()) or QtWidgets.QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QtCore.QRect(0, 0, 1920, 1080)

        x = anchor_rect.center().x() - self.width() // 2
        y = anchor_rect.bottom() + 6
        if y + self.height() > avail.bottom() - 8:
            y = anchor_rect.top() - self.height() - 6
        x = max(avail.left() + 8, min(x, avail.right() - self.width() - 8))
        y = max(avail.top() + 8, min(y, avail.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()

    def schedule_hide(self) -> None:
        self._hide_timer.start()

    def cancel_hide(self) -> None:
        self._hide_timer.stop()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:  # type: ignore[override]
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        self.schedule_hide()
        super().leaveEvent(event)

    def _check_and_hide(self) -> None:
        if not _is_qt_valid(self):
            return
        if self.underMouse():
            return
        anchor = self._anchor
        if anchor is not None:
            if not _is_qt_valid(anchor):
                self._anchor = None
            else:
                try:
                    if anchor.underMouse():
                        return
                except RuntimeError:
                    self._anchor = None
        self.hide()


def _get_popover() -> _HelpPopover:
    global _SHARED_POPOVER
    if _SHARED_POPOVER is None:
        _SHARED_POPOVER = _HelpPopover()
    else:
        try:
            _SHARED_POPOVER.isVisible()
        except RuntimeError:
            _SHARED_POPOVER = _HelpPopover()
    return _SHARED_POPOVER


class HelpBadge(QtWidgets.QAbstractButton):
    """Self-painted crisp `[?]` help badge with instant hover popover & focus animation."""

    def __init__(
        self,
        title: str,
        explanation: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._orig_title = str(title).strip()
        self._orig_explanation = str(explanation).strip()
        self._title = self._orig_title
        self._explanation = self._orig_explanation
        self._hover_progress: float = 0.0
        self._pressed: bool = False

        self.setObjectName("helpBadge")
        self.setText("?")
        self.setFixedSize(22, 22)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

        self._hover_anim = QtCore.QVariantAnimation(self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_anim_value)

        self._hover_show_timer = QtCore.QTimer(self)
        self._hover_show_timer.setSingleShot(True)
        self._hover_show_timer.setInterval(110)
        self._hover_show_timer.timeout.connect(self._show_help_popup)

        self.clicked.connect(self._show_help_popup)
        _LIVE_BADGES.add(self)
        self.apply_language(_CURRENT_LANGUAGE)
        self._sync_help_mode()

    def _sync_help_mode(self) -> None:
        self.setVisible(bool(_HELP_MODE_ENABLED and self.parentWidget() is not None))

    def changeEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        et = event.type()
        if et == QtCore.QEvent.Type.ParentAboutToChange:
            self._hover_show_timer.stop()
            self._hover_anim.stop()
        elif et == QtCore.QEvent.Type.ParentChange:
            self._sync_help_mode()
        super().changeEvent(event)

    def event(self, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if event.type() == QtCore.QEvent.Type.ToolTip:
            event.accept()
            if _HELP_MODE_ENABLED and not self.isHidden() and self.parentWidget() is not None:
                self._show_help_popup()
            return True
        return super().event(event)

    def apply_language(self, lang: str) -> None:
        t, e = _translate_help_pair(self._orig_title, self._orig_explanation, lang)
        self._title = t
        self._explanation = e
        self.setAccessibleName(f"{self._title} Help" if lang == "en" else f"{self._title}")
        self.setAccessibleDescription(self._explanation)
        rich_tip = f"<b>{self._title}</b><br/>{self._explanation}" if self._title else self._explanation
        self.setToolTip(rich_tip)

    @property
    def explanation(self) -> str:
        return self._explanation

    @property
    def title(self) -> str:
        return self._title

    def _on_anim_value(self, value: object) -> None:
        try:
            self._hover_progress = float(value)  # type: ignore[arg-type]
        except Exception:
            self._hover_progress = 0.0
        self.update()

    def _animate_to(self, target: float) -> None:
        if not _FOCUS_ANIMATIONS_ENABLED:
            self._hover_anim.stop()
            self._hover_progress = target
            self.update()
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:  # type: ignore[override]
        self._animate_to(1.0)
        win = self.window()
        can_show = (
            _HELP_MODE_ENABLED
            and not self.isHidden()
            and self.parentWidget() is not None
            and (win is None or (self.isVisibleTo(win) and win.isVisible() and win.isActiveWindow()))
        )
        if can_show:
            if _SHARED_POPOVER is not None:
                try:
                    _SHARED_POPOVER.cancel_hide()
                except RuntimeError:
                    pass
            self._hover_show_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        self._hover_show_timer.stop()
        self._pressed = False
        self._animate_to(0.0)
        if _SHARED_POPOVER is not None:
            try:
                _SHARED_POPOVER.schedule_hide()
            except RuntimeError:
                pass
        super().leaveEvent(event)

    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        # Never auto-open _HelpPopover on focusInEvent (prevents spurious popup on Qt focus fallback).
        super().focusInEvent(event)

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        self._hover_show_timer.stop()
        if not self.underMouse():
            self._animate_to(0.0)
            if _SHARED_POPOVER is not None:
                try:
                    if _SHARED_POPOVER._anchor is self:
                        _SHARED_POPOVER.schedule_hide()
                except RuntimeError:
                    pass
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def _show_help_popup(self) -> None:
        if not _HELP_MODE_ENABLED or self.isHidden() or self.parentWidget() is None:
            return
        pop = _get_popover()
        pop.show_for(self, self._title, self._explanation)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        theme = _CURRENT_THEME
        t = max(0.0, min(1.0, self._hover_progress))
        accent = QtGui.QColor(theme.accent)
        fg = QtGui.QColor(theme.fg)
        bg = QtGui.QColor(theme.bg)
        border_idle = QtGui.QColor(theme.border)
        if not theme.is_dark and theme.is_acid:
            border_idle = QtGui.QColor("#6E7781")
        elif theme.is_dark and theme.is_acid:
            border_idle = QtGui.QColor("#525866")

        # Interpolate border and fill cleanly without any QSS clipping
        def _mix(c1: QtGui.QColor, c2: QtGui.QColor, k: float) -> QtGui.QColor:
            return QtGui.QColor(
                int(c1.red() + (c2.red() - c1.red()) * k),
                int(c1.green() + (c2.green() - c1.green()) * k),
                int(c1.blue() + (c2.blue() - c1.blue()) * k),
                int(c1.alpha() + (c2.alpha() - c1.alpha()) * k),
            )

        rect = QtCore.QRectF(2.0, 2.0, self.width() - 4.0, self.height() - 4.0)
        radius = 2.0 if theme.is_acid else rect.width() / 2.0

        # Subtle focus halo ring during hover/focus animation
        if t > 0.02:
            halo_color = QtGui.QColor(accent)
            halo_color.setAlpha(int(95 * t))
            p.setPen(QtGui.QPen(halo_color, 1.5))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            halo_rect = rect.adjusted(-1.2 * t, -1.2 * t, 1.2 * t, 1.2 * t)
            p.drawRoundedRect(halo_rect, radius + 1.0, radius + 1.0)

        # Fill
        hover_fill = QtGui.QColor(accent)
        hover_fill.setAlpha(235 if theme.is_acid else 42)
        idle_fill = QtGui.QColor(bg)
        idle_fill.setAlpha(220)
        fill = _mix(idle_fill, hover_fill, t)
        if self._pressed:
            fill = accent

        border_col = _mix(border_idle, accent, t)
        p.setBrush(fill)
        p.setPen(QtGui.QPen(border_col, 1.25))
        p.drawRoundedRect(rect, radius, radius)

        # Crisp "?" glyph centered inside the box
        font = QtGui.QFont(self.font())
        font.setBold(True)
        font.setPixelSize(11)
        p.setFont(font)
        if (t > 0.45 and theme.is_acid) or self._pressed:
            # High-contrast dark glyph on bright acid/clinical accent fill
            text_col = QtGui.QColor("#0A0D12") if accent.lightness() > 120 else QtGui.QColor("#FFFFFF")
        else:
            text_col = _mix(fg, accent, t * 0.8)
        p.setPen(text_col)
        p.drawText(rect.adjusted(0, -0.5, 0, 0), QtCore.Qt.AlignmentFlag.AlignCenter, "?")
        p.end()


class _FocusOverlay(QtWidgets.QWidget):
    """Transparent click-through overlay that draws a sleek animated focus/hover highlight."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._rect = QtCore.QRectF()
        self._alpha: float = 0.0
        self._accent = QtGui.QColor(_CURRENT_THEME.accent)
        self._is_acid: bool = _CURRENT_THEME.is_acid
        self._style: str = _FOCUS_STYLE
        self.hide()

    def set_style(self, style: str) -> None:
        self._style = style
        if self.isVisible():
            self.update()

    def set_state(self, rect: QtCore.QRectF, alpha: float) -> None:
        parent = self.parentWidget()
        if parent is None or not parent.isVisible():
            self._alpha = 0.0
            if self.isVisible():
                self.hide()
            return
        self._rect = rect
        self._alpha = max(0.0, min(1.0, alpha))
        if self._alpha <= 0.01 or self._rect.isEmpty():
            if self.isVisible():
                self.hide()
            return
        target_geom = parent.rect()
        if self.geometry() != target_geom:
            self.setGeometry(target_geom)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.update()

    def set_accent(self, accent: str, *, is_acid: bool) -> None:
        self._accent = QtGui.QColor(accent)
        self._is_acid = is_acid
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        del event
        if self._alpha <= 0.01 or self._rect.isEmpty():
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        r = self._rect.adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 1.5 if self._is_acid else 5.0

        if self._style == "underline":
            rail = QtGui.QColor(self._accent)
            rail.setAlpha(int(225 * self._alpha))
            p.setPen(QtGui.QPen(rail, 2.0, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.SquareCap))
            inset = min(6.0, r.width() * 0.12)
            cx = r.center().x()
            half = max(2.0, (r.width() * 0.5 - inset) * (0.35 + 0.65 * self._alpha))
            y = r.bottom() - 0.5
            p.drawLine(QtCore.QPointF(cx - half, y), QtCore.QPointF(cx + half, y))
        elif self._style == "brackets":
            tick = max(4.0, min(7.5, min(r.width(), r.height()) * 0.28))
            col = QtGui.QColor(self._accent)
            col.setAlpha(int(225 * self._alpha))
            p.setPen(QtGui.QPen(col, 1.5, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.SquareCap))
            spread = 1.5 + (1.0 - self._alpha) * 2.2
            br = r.adjusted(-spread, -spread, spread, spread)
            # Four optical corner calipers contracting inward onto the control
            p.drawLine(QtCore.QPointF(br.left(), br.top()), QtCore.QPointF(br.left() + tick, br.top()))
            p.drawLine(QtCore.QPointF(br.left(), br.top()), QtCore.QPointF(br.left(), br.top() + tick))
            p.drawLine(QtCore.QPointF(br.right(), br.top()), QtCore.QPointF(br.right() - tick, br.top()))
            p.drawLine(QtCore.QPointF(br.right(), br.top()), QtCore.QPointF(br.right(), br.top() + tick))
            p.drawLine(QtCore.QPointF(br.left(), br.bottom()), QtCore.QPointF(br.left() + tick, br.bottom()))
            p.drawLine(QtCore.QPointF(br.left(), br.bottom()), QtCore.QPointF(br.left(), br.bottom() - tick))
            p.drawLine(QtCore.QPointF(br.right(), br.bottom()), QtCore.QPointF(br.right() - tick, br.bottom()))
            p.drawLine(QtCore.QPointF(br.right(), br.bottom()), QtCore.QPointF(br.right(), br.bottom() - tick))
        else:
            # 'sleek': subtle hairline edge + sweeping top optical glint + corner registration pip
            wash = QtGui.QColor(self._accent)
            wash.setAlpha(int(18 * self._alpha))
            edge = QtGui.QColor(self._accent)
            edge.setAlpha(int(180 * self._alpha))
            p.setBrush(wash)
            p.setPen(QtGui.QPen(edge, 1.25))
            p.drawRoundedRect(r, radius, radius)

            glint = QtGui.QColor(self._accent)
            glint.setAlpha(int(230 * self._alpha))
            p.setPen(QtGui.QPen(glint, 1.7))
            glint_span = min(22.0, r.width() * 0.38) * (0.3 + 0.7 * self._alpha)
            p.drawLine(QtCore.QPointF(r.left() + radius, r.top()), QtCore.QPointF(r.left() + radius + glint_span, r.top()))
            if self._is_acid and r.width() >= 28 and r.height() >= 18:
                p.fillRect(QtCore.QRectF(r.right() - 3.5, r.bottom() - 3.5, 2.5, 2.5), glint)
        p.end()


_INTERACTIVE_TYPES = (
    QtWidgets.QPushButton,
    QtWidgets.QCheckBox,
    QtWidgets.QComboBox,
    QtWidgets.QAbstractSpinBox,
)


class _TooltipOnlyOnHelpBadgeFilter(QtCore.QObject):
    """Global event filter blocking native Qt tooltips outside `[?]` HelpBadge controls."""

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        try:
            et = event.type()
            if et == QtCore.QEvent.Type.ToolTip:
                if bool(obj.property("lsSuppressTip")):
                    QtWidgets.QToolTip.hideText()
                    event.accept()
                    return True
                return False
            if _SHARED_POPOVER is not None and _is_qt_valid(_SHARED_POPOVER) and _SHARED_POPOVER.isVisible():
                if et in (
                    QtCore.QEvent.Type.WindowDeactivate,
                    QtCore.QEvent.Type.ApplicationDeactivate,
                ):
                    _SHARED_POPOVER.hide()
                elif et == QtCore.QEvent.Type.MouseButtonPress and not isinstance(obj, HelpBadge):
                    if obj is not _SHARED_POPOVER and (
                        not isinstance(obj, QtWidgets.QWidget) or not _SHARED_POPOVER.isAncestorOf(obj)
                    ):
                        _SHARED_POPOVER.hide()
        except RuntimeError:
            return False
        return False


def install_tooltip_guard(root: QtWidgets.QWidget) -> _TooltipOnlyOnHelpBadgeFilter:
    """Ensure only `[?]` HelpBadge triggers explanatory popovers; suppress all native tooltips."""
    app = QtWidgets.QApplication.instance()
    target: QtCore.QObject = app if app is not None else root
    existing = getattr(target, "_ls_tooltip_guard", None)
    if isinstance(existing, _TooltipOnlyOnHelpBadgeFilter):
        return existing
    guard = _TooltipOnlyOnHelpBadgeFilter(target)
    target.removeEventFilter(guard)
    target.installEventFilter(guard)
    setattr(target, "_ls_tooltip_guard", guard)
    return guard


class FocusRingAnimator(QtCore.QObject):
    """Lightweight hover/focus micro-animation controller for interactive controls in a window."""

    def __init__(self, root: QtWidgets.QWidget) -> None:
        super().__init__(root)
        self._root = root
        self._torn_down: bool = False
        self._enabled = _FOCUS_ANIMATIONS_ENABLED
        self._overlay = _FocusOverlay(root)
        self._current_target: Optional[QtWidgets.QWidget] = None
        self._start_rect = QtCore.QRectF()
        self._end_rect = QtCore.QRectF()
        self._alpha: float = 0.0

        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(115)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_step)

        self._fade_anim = QtCore.QVariantAnimation(self)
        self._fade_anim.setDuration(115)
        self._fade_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fade_anim.valueChanged.connect(self._on_fade)

        try:
            root.destroyed.connect(self._on_root_destroyed)
        except Exception:
            pass
        self._install_recursive(root)
        _LIVE_ANIMATORS.add(self)

    def _on_root_destroyed(self, *_args) -> None:
        self._torn_down = True
        self._current_target = None
        _LIVE_ANIMATORS.discard(self)

    def teardown(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        self._current_target = None
        _LIVE_ANIMATORS.discard(self)
        for anim_attr in ("_anim", "_fade_anim"):
            anim = getattr(self, anim_attr, None)
            if _is_qt_valid(anim):
                try:
                    anim.stop()
                except RuntimeError:
                    pass
        overlay = getattr(self, "_overlay", None)
        if _is_qt_valid(overlay):
            try:
                overlay.hide()
            except RuntimeError:
                pass
        root = getattr(self, "_root", None)
        if _is_qt_valid(root):
            try:
                root.removeEventFilter(self)
            except RuntimeError:
                pass
            try:
                for child in root.findChildren(QtWidgets.QWidget):
                    if _is_qt_valid(child):
                        child.removeEventFilter(self)
            except RuntimeError:
                pass

    def _reset_focus_state(self) -> None:
        if self._torn_down or not _is_qt_valid(self):
            return
        if _is_qt_valid(self._anim):
            self._anim.stop()
        if _is_qt_valid(self._fade_anim):
            self._fade_anim.stop()
        self._current_target = None
        self._alpha = 0.0
        if _is_qt_valid(self._overlay):
            self._overlay.set_state(QtCore.QRectF(), 0.0)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self._reset_focus_state()

    def set_style(self, style: str) -> None:
        if not self._torn_down and _is_qt_valid(self._overlay):
            self._overlay.set_style(style)

    def set_accent(self, accent: str, *, is_acid: bool) -> None:
        if not self._torn_down and _is_qt_valid(self._overlay):
            self._overlay.set_accent(accent, is_acid=is_acid)

    def refresh_children(self) -> None:
        if not self._torn_down and _is_qt_valid(self._root):
            self._install_recursive(self._root)

    def _on_tab_changed(self, *_args) -> None:
        self._reset_focus_state()
        if _SHARED_POPOVER is not None and _is_qt_valid(_SHARED_POPOVER):
            try:
                _SHARED_POPOVER.hide()
            except RuntimeError:
                pass

    def _install_recursive(self, widget: QtWidgets.QWidget) -> None:
        if self._torn_down or not _is_qt_valid(widget):
            return
        widget.removeEventFilter(self)
        widget.installEventFilter(self)
        if not hasattr(self, "_connected_tabs"):
            self._connected_tabs: "weakref.WeakSet[QtWidgets.QTabWidget]" = weakref.WeakSet()
        for child in widget.findChildren(QtWidgets.QWidget):
            if not _is_qt_valid(child) or isinstance(child, HelpBadge):
                continue
            if isinstance(child, QtWidgets.QTabWidget) and child not in self._connected_tabs:
                try:
                    child.currentChanged.connect(self._on_tab_changed)
                    self._connected_tabs.add(child)
                except RuntimeError:
                    pass
            if isinstance(child, _INTERACTIVE_TYPES) or isinstance(
                child, (QtWidgets.QTabWidget, QtWidgets.QAbstractScrollArea)
            ):
                child.removeEventFilter(self)
                child.installEventFilter(self)
            if isinstance(child, QtWidgets.QAbstractScrollArea):
                vp = child.viewport()
                if _is_qt_valid(vp):
                    vp.removeEventFilter(self)
                    vp.installEventFilter(self)

    def _widget_rect_in_root(self, w: QtWidgets.QWidget) -> QtCore.QRectF:
        top_left = w.mapTo(self._root, QtCore.QPoint(0, 0))
        return QtCore.QRectF(float(top_left.x()), float(top_left.y()), float(w.width()), float(w.height()))

    def _focus_widget(self, w: QtWidgets.QWidget) -> None:
        if self._torn_down or not _is_qt_valid(self) or not _is_qt_valid(self._root) or not _is_qt_valid(w):
            return
        if not self._enabled or not self._root.isVisible() or not w.isVisible() or not w.isEnabled():
            return
        if w.objectName() in (
            "winCloseBtn",
            "winMinBtn",
            "winMaxBtn",
            "windowCtrlBtn",
            "windowCloseBtn",
            "acidStaticLockBtn",
            "noticeDismissBtn",
        ):
            return
        if isinstance(w, QtWidgets.QCheckBox):
            # Avoid boxing wide checkbox label text; subtly underline indicator+label instead if small
            target_rect = self._widget_rect_in_root(w)
            if target_rect.width() > 260:
                return
        else:
            target_rect = self._widget_rect_in_root(w)
        if target_rect.width() < 16 or target_rect.height() < 14:
            return
        self._current_target = w
        if _is_qt_valid(self._overlay) and self._overlay.isVisible() and not self._overlay._rect.isEmpty():
            self._start_rect = QtCore.QRectF(self._overlay._rect)
        else:
            self._start_rect = target_rect.adjusted(1.5, 1.5, -1.5, -1.5)
        self._end_rect = target_rect

        if _is_qt_valid(self._anim):
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()

        if _is_qt_valid(self._fade_anim):
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self._alpha)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

    def _clear_focus(self, w: QtWidgets.QWidget) -> None:
        if self._torn_down or self._current_target is not w:
            return
        self._current_target = None
        if _is_qt_valid(self._fade_anim):
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self._alpha)
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.start()

    def _on_step(self, val: object) -> None:
        if self._torn_down or not _is_qt_valid(self) or not _is_qt_valid(self._overlay):
            return
        t = float(val)  # type: ignore[arg-type]
        s, e = self._start_rect, self._end_rect
        cur = QtCore.QRectF(
            s.x() + (e.x() - s.x()) * t,
            s.y() + (e.y() - s.y()) * t,
            s.width() + (e.width() - s.width()) * t,
            s.height() + (e.height() - s.height()) * t,
        )
        self._overlay.set_state(cur, self._alpha)

    def _on_fade(self, val: object) -> None:
        if self._torn_down or not _is_qt_valid(self) or not _is_qt_valid(self._overlay):
            return
        self._alpha = float(val)  # type: ignore[arg-type]
        rect = self._overlay._rect if not self._overlay._rect.isEmpty() else self._end_rect
        self._overlay.set_state(rect, self._alpha)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if getattr(self, "_torn_down", False) or not _is_qt_valid(self):
            return False
        root = getattr(self, "_root", None)
        overlay = getattr(self, "_overlay", None)
        if not _is_qt_valid(root) or not _is_qt_valid(overlay) or not _is_qt_valid(obj):
            return False
        try:
            et = event.type()
            if obj is root:
                if et == QtCore.QEvent.Type.Destroy:
                    self.teardown()
                    return False
                if et in (
                    QtCore.QEvent.Type.Resize,
                    QtCore.QEvent.Type.Hide,
                    QtCore.QEvent.Type.StyleChange,
                    QtCore.QEvent.Type.WindowDeactivate,
                ):
                    self._reset_focus_state()
                    return False
            if not getattr(self, "_enabled", False):
                return False
            if et == QtCore.QEvent.Type.Wheel:
                self._reset_focus_state()
                return False
            if et == QtCore.QEvent.Type.MouseButtonPress:
                if not isinstance(obj, _INTERACTIVE_TYPES) or obj is not self._current_target:
                    self._reset_focus_state()
                return False
            if isinstance(obj, _INTERACTIVE_TYPES) and not isinstance(obj, HelpBadge):
                if et == QtCore.QEvent.Type.Enter:
                    if root.isVisible() and obj.isVisibleTo(root) and obj.isEnabled():
                        self._focus_widget(obj)
                elif et == QtCore.QEvent.Type.FocusIn:
                    if (
                        root.isVisible()
                        and obj.isVisibleTo(root)
                        and isinstance(event, QtGui.QFocusEvent)
                        and event.reason()
                        in (
                            QtCore.Qt.FocusReason.TabFocusReason,
                            QtCore.Qt.FocusReason.BacktabFocusReason,
                        )
                    ):
                        self._focus_widget(obj)
                elif et in (QtCore.QEvent.Type.Leave, QtCore.QEvent.Type.FocusOut, QtCore.QEvent.Type.Hide):
                    self._clear_focus(obj)
        except RuntimeError:
            return False
        return False


def install_focus_animations(root: QtWidgets.QWidget) -> FocusRingAnimator:
    """Attach (or reuse) a FocusRingAnimator on `root` window/dialog."""
    install_tooltip_guard(root)
    existing = getattr(root, "_focus_ring_animator", None)
    if isinstance(existing, FocusRingAnimator):
        existing._reset_focus_state()
        existing.refresh_children()
        return existing
    animator = FocusRingAnimator(root)
    setattr(root, "_focus_ring_animator", animator)
    return animator


def wrap_with_help(
    widget: QtWidgets.QWidget,
    title: str,
    explanation: str,
    parent: QtWidgets.QWidget | None = None,
) -> tuple[QtWidgets.QWidget, HelpBadge]:
    """Return a compact container placing a crisp `[?]` badge directly after `widget`."""
    holder = QtWidgets.QWidget(parent)
    holder.setObjectName("helpHolder")
    layout = QtWidgets.QHBoxLayout(holder)
    layout.setContentsMargins(0, 1, 2, 1)
    layout.setSpacing(6)
    layout.addWidget(widget, 1)
    badge = HelpBadge(title, explanation, holder)
    layout.addWidget(badge, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    return holder, badge
