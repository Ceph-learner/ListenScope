"""Lightweight contextual `[?]` help badge widget (no QGraphicsEffect)."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class HelpBadge(QtWidgets.QToolButton):
    """Compact circular `?` button showing detailed explanation on hover or click."""

    def __init__(
        self,
        title: str,
        explanation: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = str(title).strip()
        self._explanation = str(explanation).strip()
        self.setObjectName("helpBadge")
        self.setText("?")
        self.setAutoRaise(False)
        self.setFixedSize(18, 18)
        self.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"{self._title} 说明")
        self.setAccessibleDescription(self._explanation)
        rich_tip = f"<b>{self._title}</b><br/>{self._explanation}" if self._title else self._explanation
        self.setToolTip(rich_tip)
        self.clicked.connect(self._show_help_popup)

    @property
    def explanation(self) -> str:
        return self._explanation

    def _show_help_popup(self) -> None:
        pos = self.mapToGlobal(QtCore.QPoint(self.width() // 2, self.height() + 2))
        QtWidgets.QToolTip.showText(pos, self.toolTip(), self, self.rect(), 9000)


def wrap_with_help(
    widget: QtWidgets.QWidget,
    title: str,
    explanation: str,
    parent: QtWidgets.QWidget | None = None,
) -> tuple[QtWidgets.QWidget, HelpBadge]:
    """Return a compact zero-margin container placing a `[?]` badge directly after `widget`."""
    holder = QtWidgets.QWidget(parent)
    holder.setObjectName("helpHolder")
    layout = QtWidgets.QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(widget, 1)
    badge = HelpBadge(title, explanation, holder)
    layout.addWidget(badge)
    return holder, badge
