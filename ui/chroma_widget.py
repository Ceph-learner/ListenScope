"""PyQtGraph 12-bin chroma, chord candidate, Krumhansl-Schmuckler key, BPM, and pitch display."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from analysis.chroma import PITCH_CLASSES
from core.models import AnalysisSnapshot


class ChromaAndHarmonyWidget(QtWidgets.QWidget):
    """Displays 12-bin chroma, chord candidates, key candidates, BPM, and pitch readout."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        # Harmonic summary cards (top)
        cards = QtWidgets.QHBoxLayout()

        # Chord card
        chord_box = QtWidgets.QGroupBox("和弦推测 (12 Major / 12 Minor / N / Unknown)")
        chord_l = QtWidgets.QVBoxLayout(chord_box)
        self.chord_primary_lbl = QtWidgets.QLabel("N (静音)")
        self.chord_primary_lbl.setStyleSheet("font-size: 24px; font-weight: 700; color: #7EE2B8;")
        self.chord_secondary_lbl = QtWidgets.QLabel("第二候选: -")
        self.chord_stability_lbl = QtWidgets.QLabel("稳定度: Silent | 相关度: 0.00")
        chord_l.addWidget(self.chord_primary_lbl)
        chord_l.addWidget(self.chord_secondary_lbl)
        chord_l.addWidget(self.chord_stability_lbl)
        cards.addWidget(chord_box, 1)

        # Key card
        key_box = QtWidgets.QGroupBox("调性推测 (Krumhansl-Schmuckler 滑动窗口)")
        key_l = QtWidgets.QVBoxLayout(key_box)
        self.key_primary_lbl = QtWidgets.QLabel("Unknown")
        self.key_primary_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #74C0FC;")
        self.key_secondary_lbl = QtWidgets.QLabel("第二候选: -")
        self.key_relation_lbl = QtWidgets.QLabel("稳定度: Insufficient | 关系说明: 等待音频")
        self.key_relation_lbl.setWordWrap(True)
        self.key_sig_note_lbl = QtWidgets.QLabel(
            "说明: 调性中心(Key)与调号(Key Signature)并不完全等同，关系大小调/调式混合可能共用调号。"
        )
        self.key_sig_note_lbl.setWordWrap(True)
        self.key_sig_note_lbl.setStyleSheet("color: #9AA4B2; font-size: 11px;")
        key_l.addWidget(self.key_primary_lbl)
        key_l.addWidget(self.key_secondary_lbl)
        key_l.addWidget(self.key_relation_lbl)
        key_l.addWidget(self.key_sig_note_lbl)
        cards.addWidget(key_box, 2)

        # BPM + Pitch card
        rhythm_box = QtWidgets.QGroupBox("BPM 与 主音高 (CPU 轻量估算)")
        rhythm_l = QtWidgets.QVBoxLayout(rhythm_box)
        self.bpm_lbl = QtWidgets.QLabel("BPM: Unknown")
        self.bpm_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFD166;")
        self.bpm_stab_lbl = QtWidgets.QLabel("节拍稳定度: Unknown")
        self.pitch_lbl = QtWidgets.QLabel("主音高: -")
        rhythm_l.addWidget(self.bpm_lbl)
        rhythm_l.addWidget(self.bpm_stab_lbl)
        rhythm_l.addWidget(self.pitch_lbl)
        rhythm_l.addStretch(1)
        cards.addWidget(rhythm_box, 1)

        root.addLayout(cards)

        # Plots splitter: 12-bin Chroma Bar + Bounded Chroma History Heatmap
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self.chroma_bar_plot = pg.PlotWidget(title="实时 12-Bin Chroma 分布")
        self.chroma_bar_plot.setBackground("#14161A")
        self.chroma_bar_plot.setYRange(0.0, 1.05)
        self.chroma_bar_plot.showGrid(x=False, y=True, alpha=0.25)
        ax = self.chroma_bar_plot.getAxis("bottom")
        ax.setTicks([[(i, name) for i, name in enumerate(PITCH_CLASSES)]])
        self._bar_item = pg.BarGraphItem(
            x=np.arange(12, dtype=np.float32),
            height=np.zeros(12, dtype=np.float32),
            width=0.65,
            brush="#4EA8DE",
        )
        self.chroma_bar_plot.addItem(self._bar_item)
        splitter.addWidget(self.chroma_bar_plot)

        self.chroma_hist_plot = pg.PlotWidget(title="有界 Chroma 时序热图 (最多保留 120s)")
        self.chroma_hist_plot.setBackground("#14161A")
        ay = self.chroma_hist_plot.getAxis("left")
        ay.setTicks([[(i + 0.5, name) for i, name in enumerate(PITCH_CLASSES)]])
        self._chroma_img = pg.ImageItem()
        try:
            cmap = pg.colormap.get("viridis") if hasattr(pg, "colormap") else None
        except Exception:
            cmap = None
        if cmap is not None:
            self._chroma_img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
        self.chroma_hist_plot.addItem(self._chroma_img)
        splitter.addWidget(self.chroma_hist_plot)

        splitter.setSizes([210, 240])
        root.addWidget(splitter, 1)

    def update_analysis(self, snap: AnalysisSnapshot, chroma_history: np.ndarray | None = None) -> None:
        ch = snap.chord
        self.chord_primary_lbl.setText(ch.primary)
        self.chord_secondary_lbl.setText(f"第二候选: {ch.secondary}")
        self.chord_stability_lbl.setText(
            f"稳定度: {ch.stability} | 相关度: {ch.correlation:.2f} | 领先差值: {ch.margin:.2f}"
        )

        ky = snap.key
        self.key_primary_lbl.setText(ky.primary)
        self.key_secondary_lbl.setText(f"第二候选: {ky.secondary}")
        mod_tag = " [可能转调]" if ky.modulation_hint else ""
        self.key_relation_lbl.setText(
            f"稳定度: {ky.stability}{mod_tag} | {ky.relation_note}"
        )
        self.key_sig_note_lbl.setText(ky.key_signature_note)

        tp = snap.tempo
        self.bpm_lbl.setText(f"BPM: {tp.bpm:.1f}" if tp.bpm is not None else "BPM: Unknown")
        self.bpm_stab_lbl.setText(f"节拍稳定度: {tp.stability} (自相关峰: {tp.confidence_score:.2f})")

        pt = snap.pitch
        if pt.frequency_hz is not None:
            self.pitch_lbl.setText(
                f"主音高: {pt.note_name} ({pt.frequency_hz:.1f} Hz, {pt.cents_offset:+.1f} cents)"
            )
        else:
            self.pitch_lbl.setText(f"主音高: {pt.note_name}")

        if snap.chroma_12:
            self._bar_item.setOpts(height=np.asarray(snap.chroma_12, dtype=np.float32))

        if chroma_history is not None and chroma_history.size > 0:
            self._chroma_img.setImage(chroma_history, autoLevels=False, levels=(0.0, 0.9))
