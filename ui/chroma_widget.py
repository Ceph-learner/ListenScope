"""PyQtGraph 12-bin chroma, chord candidate, Krumhansl-Schmuckler key, BPM, and pitch display."""

from __future__ import annotations

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from analysis.chroma import PITCH_CLASSES
from audio.metronome import TapTempoTracker
from core.models import AnalysisSnapshot


class ChromaAndHarmonyWidget(QtWidgets.QWidget):
    """Displays 12-bin chroma, chord candidates, bounded transition strip, key candidates, BPM, and pitch readout."""

    reset_harmony_requested = QtCore.Signal()
    metronome_bpm_changed = QtCore.Signal(float)
    metronome_beats_changed = QtCore.Signal(int)
    metronome_overlay_toggled = QtCore.Signal(bool)
    metronome_standalone_toggled = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._chord_history: deque[str] = deque(maxlen=12)
        self._tap_tracker = TapTempoTracker()
        self._latest_detected_bpm: float | None = None
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

        # BPM + Pitch + CPU Practice Metronome card
        rhythm_box = QtWidgets.QGroupBox("BPM · 主音高 · 纯 CPU 练习节拍器")
        rhythm_l = QtWidgets.QVBoxLayout(rhythm_box)
        self.bpm_lbl = QtWidgets.QLabel("BPM: Unknown")
        self.bpm_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFD166;")
        self.bpm_stab_lbl = QtWidgets.QLabel("节拍稳定度: Unknown")
        self.pitch_lbl = QtWidgets.QLabel("主音高: -")

        met_row = QtWidgets.QHBoxLayout()
        self.tap_tempo_btn = QtWidgets.QPushButton("Tap 定速")
        self.tap_tempo_btn.setToolTip("按曲子节奏连续点击 2 次以上估算 BPM")
        self.tap_tempo_btn.clicked.connect(self._on_tap_tempo_clicked)

        self.adopt_bpm_btn = QtWidgets.QPushButton("同步检测BPM")
        self.adopt_bpm_btn.setEnabled(False)
        self.adopt_bpm_btn.setToolTip("将上方检测到的歌曲 BPM 应用到练习节拍器")
        self.adopt_bpm_btn.clicked.connect(self._on_adopt_bpm_clicked)

        self.metronome_bpm_spin = QtWidgets.QDoubleSpinBox()
        self.metronome_bpm_spin.setRange(30.0, 240.0)
        self.metronome_bpm_spin.setDecimals(1)
        self.metronome_bpm_spin.setSingleStep(1.0)
        self.metronome_bpm_spin.setValue(120.0)
        self.metronome_bpm_spin.setSuffix(" BPM")
        self.metronome_bpm_spin.valueChanged.connect(self.metronome_bpm_changed.emit)

        self.metronome_sig_combo = QtWidgets.QComboBox()
        for sig_lbl, beats in [("4/4", 4), ("3/4", 3), ("2/4", 2), ("6/8", 6)]:
            self.metronome_sig_combo.addItem(sig_lbl, beats)
        self.metronome_sig_combo.currentIndexChanged.connect(
            lambda: self.metronome_beats_changed.emit(int(self.metronome_sig_combo.currentData() or 4))
        )

        self.metronome_overlay_chk = QtWidgets.QCheckBox("随播节拍器")
        self.metronome_overlay_chk.setToolTip("在 A/B 回放或分轨混音（含变速练习）中混入同步节拍器 Click")
        self.metronome_overlay_chk.toggled.connect(self.metronome_overlay_toggled.emit)

        self.metronome_standalone_btn = QtWidgets.QPushButton("独立节拍器")
        self.metronome_standalone_btn.setCheckable(True)
        self.metronome_standalone_btn.setToolTip("单独播放纯 CPU 节拍器 Click 用于跟练（播放 A/B 或分轨时会自动切回随播模式）")
        self.metronome_standalone_btn.toggled.connect(self.metronome_standalone_toggled.emit)

        met_row.addWidget(self.tap_tempo_btn)
        met_row.addWidget(self.adopt_bpm_btn)
        met_row.addWidget(self.metronome_bpm_spin)
        met_row.addWidget(self.metronome_sig_combo)
        met_row2 = QtWidgets.QHBoxLayout()
        met_row2.addWidget(self.metronome_overlay_chk)
        met_row2.addWidget(self.metronome_standalone_btn)
        self.tap_status_lbl = QtWidgets.QLabel("")
        self.tap_status_lbl.setStyleSheet("color: #9AA4B2; font-size: 11px;")
        met_row2.addWidget(self.tap_status_lbl, 1)

        rhythm_l.addWidget(self.bpm_lbl)
        rhythm_l.addWidget(self.bpm_stab_lbl)
        rhythm_l.addWidget(self.pitch_lbl)
        rhythm_l.addLayout(met_row)
        rhythm_l.addLayout(met_row2)
        cards.addWidget(rhythm_box, 2)

        root.addLayout(cards)

        # Recent bounded chord transition strip + Reset button for song switches
        prog_bar = QtWidgets.QHBoxLayout()
        self.chord_progression_lbl = QtWidgets.QLabel("最近和弦进行 (最多 12 步): -")
        self.chord_progression_lbl.setStyleSheet(
            "padding: 5px 10px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px; color: #E6EAF0;"
        )
        self.chord_progression_lbl.setWordWrap(True)
        self.reset_harmony_btn = QtWidgets.QPushButton("换歌重置 (和弦/调性/BPM)")
        self.reset_harmony_btn.setToolTip("切歌后一键清空和弦轨迹、调性滑动窗口与 BPM 累积，不中断当前捕获")
        self.reset_harmony_btn.clicked.connect(self._on_reset_clicked)
        prog_bar.addWidget(self.chord_progression_lbl, 1)
        prog_bar.addWidget(self.reset_harmony_btn)
        root.addLayout(prog_bar)

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

    @property
    def recent_progression(self) -> list[str]:
        return list(self._chord_history)

    def _on_tap_tempo_clicked(self) -> None:
        tap_bpm = self._tap_tracker.tap()
        if tap_bpm is None:
            self.tap_status_lbl.setText(f"Tap x{self._tap_tracker.tap_count} (继续点击...)")
            return
        self.tap_status_lbl.setText(f"Tap={tap_bpm:.1f} BPM")
        self.metronome_bpm_spin.setValue(tap_bpm)

    def _on_adopt_bpm_clicked(self) -> None:
        if self._latest_detected_bpm is not None:
            self.metronome_bpm_spin.setValue(round(self._latest_detected_bpm, 1))
            self.tap_status_lbl.setText(f"已同步 {self._latest_detected_bpm:.1f} BPM")

    def sync_metronome_ui(self, *, overlay_enabled: bool | None = None, standalone_playing: bool | None = None) -> None:
        if overlay_enabled is not None:
            self.metronome_overlay_chk.blockSignals(True)
            self.metronome_overlay_chk.setChecked(bool(overlay_enabled))
            self.metronome_overlay_chk.blockSignals(False)
        if standalone_playing is not None:
            self.metronome_standalone_btn.blockSignals(True)
            self.metronome_standalone_btn.setChecked(bool(standalone_playing))
            self.metronome_standalone_btn.setText("停止独立节拍器" if standalone_playing else "独立节拍器")
            self.metronome_standalone_btn.blockSignals(False)

    def _on_reset_clicked(self) -> None:
        self.clear_progression()
        self.reset_harmony_requested.emit()

    def clear_progression(self) -> None:
        self._chord_history.clear()
        self._tap_tracker.reset()
        self._latest_detected_bpm = None
        self.adopt_bpm_btn.setEnabled(False)
        self.tap_status_lbl.setText("")
        self.chord_progression_lbl.setText("最近和弦进行 (最多 12 步): -")
        self.chord_primary_lbl.setText("N (静音)")
        self.chord_secondary_lbl.setText("第二候选: -")
        self.chord_stability_lbl.setText("稳定度: Silent | 相关度: 0.00")
        self.key_primary_lbl.setText("Unknown")
        self.key_secondary_lbl.setText("第二候选: -")
        self.key_relation_lbl.setText("稳定度: Insufficient | 关系说明: 已重置，等待新音频")
        self.bpm_lbl.setText("BPM: Unknown")
        self.bpm_stab_lbl.setText("节拍稳定度: Unknown")
        self.pitch_lbl.setText("主音高: -")

    def update_analysis(self, snap: AnalysisSnapshot, chroma_history: np.ndarray | None = None) -> None:
        ch = snap.chord
        self.chord_primary_lbl.setText(ch.primary)
        self.chord_secondary_lbl.setText(f"第二候选: {ch.secondary}")
        self.chord_stability_lbl.setText(
            f"稳定度: {ch.stability} | 相关度: {ch.correlation:.2f} | 领先差值: {ch.margin:.2f}"
        )
        if not ch.is_silent and ch.primary not in ("Unknown", "N (静音)", "-"):
            if not self._chord_history or self._chord_history[-1] != ch.primary:
                self._chord_history.append(ch.primary)
                self.chord_progression_lbl.setText(
                    f"最近和弦进行 (最多 12 步): {' -> '.join(self._chord_history)}"
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
        if tp.bpm is not None:
            self._latest_detected_bpm = float(tp.bpm)
            self.adopt_bpm_btn.setEnabled(True)
            self.bpm_lbl.setText(f"BPM: {tp.bpm:.1f}")
        else:
            self._latest_detected_bpm = None
            self.adopt_bpm_btn.setEnabled(False)
            self.bpm_lbl.setText("BPM: Unknown")
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
