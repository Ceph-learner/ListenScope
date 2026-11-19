"""Lightweight self-painted `[?]` contextual help badge, hover popover, and focus animator.

Zero QGraphicsEffect usage for minimal RAM and smooth 60fps interaction.
"""

from __future__ import annotations

from dataclasses import dataclass
import weakref
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


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
_CURRENT_LANGUAGE: str = "zh"
_CURRENT_THEME: _HelpTheme = _HelpTheme()
_LIVE_BADGES: "weakref.WeakSet[HelpBadge]" = weakref.WeakSet()
_LIVE_ANIMATORS: "weakref.WeakSet[FocusRingAnimator]" = weakref.WeakSet()
_SHARED_POPOVER: Optional["_HelpPopover"] = None


def is_help_mode_enabled() -> bool:
    return _HELP_MODE_ENABLED


def is_focus_animations_enabled() -> bool:
    return _FOCUS_ANIMATIONS_ENABLED


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
        if self.underMouse():
            return
        if self._anchor is not None:
            try:
                if self._anchor.underMouse():
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
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)
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
        self.setVisible(_HELP_MODE_ENABLED)

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
        if _HELP_MODE_ENABLED:
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
        self._animate_to(1.0)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        if not self.underMouse():
            self._animate_to(0.0)
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
        if not _HELP_MODE_ENABLED:
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
    """Transparent click-through overlay that draws a crisp animated focus/hover outline."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._rect = QtCore.QRectF()
        self._alpha: float = 0.0
        self._accent = QtGui.QColor(_CURRENT_THEME.accent)
        self._is_acid: bool = _CURRENT_THEME.is_acid
        self.hide()

    def set_state(self, rect: QtCore.QRectF, alpha: float) -> None:
        self._rect = rect
        self._alpha = max(0.0, min(1.0, alpha))
        if self._alpha <= 0.01 or self._rect.isEmpty():
            self.hide()
            return
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
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
        r = self._rect.adjusted(-1.0, -1.0, 1.0, 1.0)
        radius = 2.0 if self._is_acid else 6.0

        # Outer subtle halo
        halo = QtGui.QColor(self._accent)
        halo.setAlpha(int(48 * self._alpha))
        p.setPen(QtGui.QPen(halo, 3.0))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, radius, radius)

        # Crisp inner focus edge
        edge = QtGui.QColor(self._accent)
        edge.setAlpha(int(185 * self._alpha))
        p.setPen(QtGui.QPen(edge, 1.25))
        p.drawRoundedRect(r, radius, radius)

        # Acid corner ticks for graphic realism feel
        if self._is_acid and r.width() >= 28 and r.height() >= 20:
            tick = 4.0
            tick_col = QtGui.QColor(self._accent)
            tick_col.setAlpha(int(235 * self._alpha))
            p.setPen(QtGui.QPen(tick_col, 1.8))
            # Top-left & bottom-right micro brackets
            p.drawLine(QtCore.QPointF(r.left(), r.top()), QtCore.QPointF(r.left() + tick, r.top()))
            p.drawLine(QtCore.QPointF(r.left(), r.top()), QtCore.QPointF(r.left(), r.top() + tick))
            p.drawLine(QtCore.QPointF(r.right(), r.bottom()), QtCore.QPointF(r.right() - tick, r.bottom()))
            p.drawLine(QtCore.QPointF(r.right(), r.bottom()), QtCore.QPointF(r.right(), r.bottom() - tick))
        p.end()


_INTERACTIVE_TYPES = (
    QtWidgets.QPushButton,
    QtWidgets.QCheckBox,
    QtWidgets.QComboBox,
    QtWidgets.QAbstractSpinBox,
)


class FocusRingAnimator(QtCore.QObject):
    """Lightweight hover/focus micro-animation controller for interactive controls in a window."""

    def __init__(self, root: QtWidgets.QWidget) -> None:
        super().__init__(root)
        self._root = root
        self._enabled = _FOCUS_ANIMATIONS_ENABLED
        self._overlay = _FocusOverlay(root)
        self._current_target: Optional[QtWidgets.QWidget] = None
        self._start_rect = QtCore.QRectF()
        self._end_rect = QtCore.QRectF()
        self._alpha: float = 0.0

        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(135)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_step)

        self._fade_anim = QtCore.QVariantAnimation(self)
        self._fade_anim.setDuration(130)
        self._fade_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fade_anim.valueChanged.connect(self._on_fade)

        self._install_recursive(root)
        _LIVE_ANIMATORS.add(self)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self._anim.stop()
            self._fade_anim.stop()
            self._current_target = None
            self._overlay.hide()

    def set_accent(self, accent: str, *, is_acid: bool) -> None:
        self._overlay.set_accent(accent, is_acid=is_acid)

    def refresh_children(self) -> None:
        self._install_recursive(self._root)

    def _install_recursive(self, widget: QtWidgets.QWidget) -> None:
        widget.installEventFilter(self)
        for child in widget.findChildren(QtWidgets.QWidget):
            if isinstance(child, _INTERACTIVE_TYPES) and not isinstance(child, HelpBadge):
                child.installEventFilter(self)

    def _widget_rect_in_root(self, w: QtWidgets.QWidget) -> QtCore.QRectF:
        top_left = w.mapTo(self._root, QtCore.QPoint(0, 0))
        return QtCore.QRectF(float(top_left.x()), float(top_left.y()), float(w.width()), float(w.height()))

    def _focus_widget(self, w: QtWidgets.QWidget) -> None:
        if not self._enabled or not w.isVisible() or not w.isEnabled():
            return
        if w.objectName() in ("winCloseBtn", "winMinBtn", "winMaxBtn"):
            return
        target_rect = self._widget_rect_in_root(w)
        if target_rect.width() < 16 or target_rect.height() < 14:
            return
        self._current_target = w
        if self._overlay.isVisible() and not self._overlay._rect.isEmpty():
            self._start_rect = QtCore.QRectF(self._overlay._rect)
        else:
            self._start_rect = target_rect.adjusted(2.0, 2.0, -2.0, -2.0)
        self._end_rect = target_rect

        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._alpha)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _clear_focus(self, w: QtWidgets.QWidget) -> None:
        if self._current_target is not w:
            return
        self._current_target = None
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._alpha)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_step(self, val: object) -> None:
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
        self._alpha = float(val)  # type: ignore[arg-type]
        rect = self._overlay._rect if not self._overlay._rect.isEmpty() else self._end_rect
        self._overlay.set_state(rect, self._alpha)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        root = getattr(self, "_root", None)
        overlay = getattr(self, "_overlay", None)
        if root is None or overlay is None:
            return False
        try:
            et = event.type()
            if obj is root and et in (
                QtCore.QEvent.Type.Resize,
                QtCore.QEvent.Type.Hide,
                QtCore.QEvent.Type.StyleChange,
                QtCore.QEvent.Type.LayoutRequest,
            ):
                self._active_widget = None
                overlay.hide()
                return False
            if not getattr(self, "_enabled", False):
                return False
            if isinstance(obj, _INTERACTIVE_TYPES) and not isinstance(obj, HelpBadge):
                if et in (QtCore.QEvent.Type.Enter, QtCore.QEvent.Type.FocusIn):
                    self._focus_widget(obj)
                elif et in (QtCore.QEvent.Type.Leave, QtCore.QEvent.Type.FocusOut, QtCore.QEvent.Type.Hide):
                    self._clear_focus(obj)
        except RuntimeError:
            return False
        return False


def install_focus_animations(root: QtWidgets.QWidget) -> FocusRingAnimator:
    """Attach (or reuse) a FocusRingAnimator on `root` window/dialog."""
    existing = getattr(root, "_focus_ring_animator", None)
    if isinstance(existing, FocusRingAnimator):
        existing._active_widget = None
        existing._overlay.hide()
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
