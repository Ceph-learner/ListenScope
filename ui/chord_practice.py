"""On-demand practice reference built from a frozen live-analysis snapshot."""

from PySide6 import QtCore, QtWidgets

from analysis.chord_practice import PRACTICE_KEYS, practice_key, recommend_progressions
from analysis.chords import transpose_chord_symbol, transpose_key_label
from core.models import KeyEstimate


class ChordPracticeDialog(QtWidgets.QDialog):
    def __init__(self, recent: list[str], estimate: KeyEstimate | None, transpose: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("练习和弦")
        self.resize(570, 330)
        self._recent = tuple(transpose_chord_symbol(chord, transpose) for chord in recent)
        suggested = None
        if estimate and estimate.stability == "High" and not estimate.modulation_hint and len(set(recent)) >= 3:
            suggested = practice_key(transpose_key_label(estimate.primary, transpose))

        root = QtWidgets.QVBoxLayout(self)
        scope = QtWidgets.QLabel("练习模板 · 参考打开窗口时的最近和弦")
        root.addWidget(scope)
        self._key = QtWidgets.QComboBox()
        self._key.addItem("请选择大调或小调", None)
        for key in PRACTICE_KEYS:
            self._key.addItem(key.replace(" major", " 大调").replace(" minor", " 小调"), key)
        self._key.setAccessibleName("练习调")
        form = QtWidgets.QFormLayout()
        form.addRow("练习调", self._key)
        root.addLayout(form)
        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        self._results = QtWidgets.QTableWidget(0, 3)
        self._results.setAccessibleName("和弦练习模板")
        self._results.setHorizontalHeaderLabels(["罗马级数", "和弦", "最近和弦匹配"])
        self._results.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._results.verticalHeader().hide()
        self._results.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self._results, 1)
        close = QtWidgets.QPushButton("关闭")
        close.clicked.connect(self.close)
        root.addWidget(close, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self._estimated_key_selected = suggested is not None
        self._insufficient_history = len(set(recent)) < 3
        self._transpose = transpose
        if suggested:
            self._key.setCurrentIndex(self._key.findData(suggested))
        self._key.activated.connect(self._on_key_selected)
        self._key.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _on_key_selected(self) -> None:
        self._estimated_key_selected = False
        self._refresh()

    def _refresh(self) -> None:
        key = self._key.currentData()
        if key is None:
            reason = "近期和弦不足" if self._insufficient_history else "检测调性尚不稳定"
            self._status.setText(f"{reason}，请手动选择练习调。")
            self._results.setRowCount(0)
            return
        items = recommend_progressions(key, self._recent)
        basis = "按稳定检测调性选中，可切换" if self._estimated_key_selected else "手动选调"
        if self._transpose:
            basis += f" · 当前指型偏移 {self._transpose:+d} 半音"
        self._status.setText(basis)
        self._results.setRowCount(len(items))
        for row, item in enumerate(items):
            match = f"{item.matched_steps} 步" if item.matched_steps else "通用练习"
            for column, text in enumerate((" → ".join(item.degrees), " → ".join(item.chords), match)):
                self._results.setItem(row, column, QtWidgets.QTableWidgetItem(text))
