"""Native Qt appearance, with painted highlights and no backdrop capture."""

import re

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import Appearance, LAYOUTS, PRESETS


def _blend(left, right, amount):
    a, b = QtGui.QColor(left), QtGui.QColor(right)
    return QtGui.QColor(*(
        round(x + (y - x) * amount)
        for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])
    )).name()


def appearance_stylesheet(base, appearance):
    background, foreground, accent = appearance.colors
    surface = _blend(background, foreground, 0.055)
    rim = _blend(background, foreground, 0.18)
    colors = {
        "#14161A": background, "#E6EAF0": foreground, "#7EE2B8": accent,
        "#2C323C": rim, "#303742": rim, "#38414E": rim,
        "#B4BECB": _blend(background, foreground, 0.82),
        "#6B7480": _blend(background, foreground, 0.49),
        "#1C2026": surface, "#1A1E24": _blend(background, foreground, 0.035),
        "#1B1E24": surface, "#232830": _blend(background, foreground, 0.085),
        "#2E3540": _blend(background, foreground, 0.14),
        "#28303B": _blend(background, accent, 0.15),
        "#1F6FEB": _blend(background, accent, 0.32), "#4EA8DE": accent,
    }
    qss = re.sub(r"#[0-9A-F]{6}", lambda match: colors.get(match[0], match[0]), base)
    qss = qss.replace("font-size: 12px", f"font-size: {appearance.font_size}px")
    qss += f"""
QGroupBox, QFrame[trackCard=true] {{ background: {surface}; }}
QFrame[trackCard=true] {{ border: 1px solid {rim}; border-radius: 6px; }}
QGroupBox QLabel, QFrame[trackCard=true] QLabel {{ background: transparent; }}
QPushButton#analysisAction:enabled {{ background: {colors["#28303B"]}; border-color: {accent}; font-weight: 600; }}
QPushButton#analysisAction:hover:enabled {{ background: {colors["#1F6FEB"]}; }}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QLabel#settingsHeading {{ font-size: {appearance.font_size + 12}px; font-weight: 700; }}
QLabel#settingsSubtitle {{ color: {colors["#B4BECB"]}; }}
QPushButton#settingsCategory {{
    background: {surface};
    border: 1px solid {rim};
    border-radius: 10px;
    padding: 0;
}}
QPushButton#settingsCategory:hover, QPushButton#settingsCategory:focus {{
    background: {colors["#28303B"]};
    border-color: {accent};
}}
QPushButton#settingsCategory:pressed {{ background: {colors["#1F6FEB"]}; }}
QPushButton#settingsCategory QLabel {{ background: transparent; }}
QPushButton#settingsCategory QLabel#settingsCategoryIcon {{ background: #23394A; border-radius: 8px; }}
QLabel#settingsCategoryTitle {{ font-size: {appearance.font_size + 4}px; font-weight: 700; }}
QLabel#settingsCategoryArrow {{ color: {accent}; font-size: {appearance.font_size + 9}px; }}
QPushButton#settingsSave {{
    background: {colors["#28303B"]}; border: 1px solid {accent};
    font-weight: 700; padding: 7px 18px;
}}
QPushButton#settingsSave:hover, QPushButton#settingsSave:focus {{ background: {colors["#1F6FEB"]}; }}
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


def apply_plot_appearance(plot, appearance):
    background, foreground, _ = appearance.colors
    plot.setBackground(background)
    axis_color = _blend(background, foreground, 0.72)
    tick_font = QtGui.QFont(QtWidgets.QApplication.font())
    tick_font.setPixelSize(appearance.font_size)
    title = plot.getPlotItem().titleLabel
    title.setText(title.text, color=foreground, family=tick_font.family(), size=f"{appearance.font_size}px")
    for name in ("left", "right", "top", "bottom"):
        axis = plot.getAxis(name)
        axis.setTickFont(tick_font)
        axis.setPen(_blend(background, foreground, 0.45))
        axis.setTextPen(axis_color)


class AppearanceDialog(QtWidgets.QDialog):
    """Preview in a sample panel and apply the window theme once on acceptance."""

    def __init__(self, appearance, base_stylesheet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("外观主题")
        self._base_stylesheet = base_stylesheet
        root = QtWidgets.QVBoxLayout(self)
        presets = QtWidgets.QHBoxLayout()
        self._presets = QtWidgets.QButtonGroup(self)
        for key, (label, *_colors) in PRESETS.items():
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            self._presets.addButton(button)
            button.clicked.connect(lambda _checked, key=key: self._show_values(
                Appearance(preset=key, scope="floating" if key == "lenso" else "off",
                           layout=self._layout.currentData())
            ))
            button.setProperty("preset", key)
            presets.addWidget(button)
        root.addLayout(presets)

        form = QtWidgets.QFormLayout()
        self._layout = QtWidgets.QComboBox()
        for key, (label, _description) in LAYOUTS.items():
            self._layout.addItem(label, key)
        self._layout.currentIndexChanged.connect(self._refresh_sample)
        form.addRow("界面布局", self._layout)
        self._layout_hint = QtWidgets.QLabel()
        self._layout_hint.setWordWrap(True)
        form.addRow("", self._layout_hint)
        self._font = QtWidgets.QSpinBox()
        self._font.setRange(11, 16)
        self._font.setSuffix(" px")
        self._font.valueChanged.connect(self._refresh_sample)
        form.addRow("字号", self._font)
        self._colors = {}
        for key, label in (("background", "背景色"), ("text", "字色"), ("accent", "强调色")):
            row = QtWidgets.QHBoxLayout()
            field = QtWidgets.QLineEdit()
            field.setPlaceholderText("使用预设颜色")
            field.setMaxLength(7)
            field.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"(#[0-9a-fA-F]{6})?"), field))
            field.textChanged.connect(self._refresh_sample)
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
        self._scope.currentIndexChanged.connect(self._refresh_sample)
        optics.addRow("光学效果范围", self._scope)
        self._sliders = {}
        for key, label in (("strength", "折射观感"), ("softness", "玻璃柔化"), ("dispersion", "边缘色散观感")):
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.valueChanged.connect(self._refresh_sample)
            self._sliders[key] = slider
            optics.addRow(label, slider)
        root.addWidget(glass)
        hint = QtWidgets.QLabel("玻璃材质使用渐变模拟，切换范围不会采样实时波形或窗口背景。")
        hint.setWordWrap(True)
        root.addWidget(hint)

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
        self._buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("保存")
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)
        self.setMinimumWidth(500)
        self._show_values(appearance)

    def values(self):
        return Appearance.from_mapping({
            "preset": self._presets.checkedButton().property("preset"),
            "font_size": self._font.value(),
            "scope": self._scope.currentData(),
            "layout": self._layout.currentData(),
            **{key: field.text() for key, field in self._colors.items()},
            **{key: slider.value() for key, slider in self._sliders.items()},
        })

    def _show_values(self, values):
        controls = [self._layout, self._font, self._scope, *self._colors.values(), *self._sliders.values()]
        blockers = [QtCore.QSignalBlocker(widget) for widget in controls]
        for button in self._presets.buttons():
            button.setChecked(button.property("preset") == values.preset)
        self._font.setValue(values.font_size)
        self._layout.setCurrentIndex(self._layout.findData(values.layout))
        self._scope.setCurrentIndex(self._scope.findData(values.scope))
        for key, field in self._colors.items():
            field.setText(getattr(values, key))
        for key, slider in self._sliders.items():
            slider.setValue(getattr(values, key))
        del blockers
        self._refresh_sample()

    def _refresh_sample(self):
        appearance = self.values()
        self._layout_hint.setText(LAYOUTS[appearance.layout][1])
        for slider in self._sliders.values():
            slider.setEnabled(appearance.scope != "off")
            slider.setToolTip(f"{slider.value()}%")
        self._sample.setStyleSheet(appearance_stylesheet(self._base_stylesheet, appearance))
        self._buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(
            all(field.hasAcceptableInput() for field in self._colors.values())
        )

    def _pick_color(self, key):
        initial = dict(zip(self._colors, self.values().colors))[key]
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(initial), self)
        if color.isValid():
            self._colors[key].setText(color.name().upper())
