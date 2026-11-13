"""PyQtGraph 12-bin chroma, chord candidate, Krumhansl-Schmuckler key, BPM, and pitch display."""

from __future__ import annotations

from collections import deque
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from analysis.chords import (
    spell_chord_tones,
    transpose_chord_symbol,
    transpose_key_label,
    transpose_note_name,
)
from analysis.chroma import PITCH_CLASSES
from audio.metronome import TapTempoTracker
from core.models import AnalysisSnapshot


TRANSPOSE_PRESETS: list[tuple[str, int]] = [
    ("原调 / 实音 (0)", 0),
    ("Capo 1 (-1 半音指型)", -1),
    ("Capo 2 (-2 半音指型)", -2),
    ("Capo 3 (-3 半音指型)", -3),
    ("Capo 4 (-4 半音指型)", -4),
    ("Capo 5 (-5 半音指型)", -5),
    ("Capo 6 (-6 半音指型)", -6),
    ("Capo 7 (-7 半音指型)", -7),
    ("降半音 / Eb调弦 (+1)", 1),
    ("降B乐器 (+2: 小号/单簧管)", 2),
    ("F调圆号 (+7)", 7),
    ("降E乐器 (+9: 中音萨克斯)", 9),
]


class TuningCentsBar(QtWidgets.QWidget):
    """Lightweight horizontal -50c..+50c pitch-accuracy needle indicator for instrument/vocal tuning."""

    COLOR_IN_TUNE = "#2EC27E"
    COLOR_SLIGHT = "#F5A623"
    COLOR_OFF = "#FF6B6B"
    COLOR_IDLE = "#5A6370"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_signal: bool = False
        self._cents: float = 0.0
        self.setFixedHeight(18)
        self.setMinimumWidth(140)
        self.setToolTip("实时主音高音准偏离条 (-50 ~ +50 cents；绿色 ±10c 为准音区间)")

    @property
    def has_signal(self) -> bool:
        return self._has_signal

    @property
    def cents_offset(self) -> float:
        return self._cents

    @property
    def zone_color(self) -> str:
        if not self._has_signal:
            return self.COLOR_IDLE
        ac = abs(self._cents)
        if ac <= 10.0:
            return self.COLOR_IN_TUNE
        if ac <= 25.0:
            return self.COLOR_SLIGHT
        return self.COLOR_OFF

    def set_pitch(self, frequency_hz: float | None, cents_offset: float = 0.0) -> None:
        if frequency_hz is None:
            self._has_signal = False
            self._cents = 0.0
            self.update()
            return
        freq = float(frequency_hz)
        if not math.isfinite(freq) or freq <= 0.0:
            self._has_signal = False
            self._cents = 0.0
            self.update()
            return
        cents = float(cents_offset)
        if not math.isfinite(cents):
            cents = 0.0
        self._has_signal = True
        self._cents = max(-50.0, min(50.0, cents))
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        rect = self.rect()
        if rect.width() <= 6 or rect.height() <= 4:
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        pad = 6
        track = QtCore.QRectF(pad, 3.0, max(1.0, rect.width() - 2 * pad), max(4.0, rect.height() - 6.0))
        p.setPen(QtGui.QPen(QtGui.QColor("#2C323C"), 1.0))
        p.setBrush(QtGui.QColor("#1C2026"))
        p.drawRoundedRect(track, 4.0, 4.0)

        # Green center ±10 cents band
        band_w = track.width() * 0.20
        center_x = track.center().x()
        band_rect = QtCore.QRectF(center_x - band_w * 0.5, track.top() + 1.0, band_w, max(2.0, track.height() - 2.0))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(46, 194, 126, 48))
        p.drawRect(band_rect)

        # Center 0c tick & side ticks
        p.setPen(QtGui.QPen(QtGui.QColor("#9AA4B2"), 1.0))
        p.drawLine(QtCore.QPointF(center_x, track.top() + 1.0), QtCore.QPointF(center_x, track.bottom() - 1.0))

        if self._has_signal:
            ratio = (self._cents + 50.0) / 100.0
            nx = track.left() + ratio * track.width()
            col = QtGui.QColor(self.zone_color)
            p.setPen(QtGui.QPen(col, 2.0))
            p.drawLine(QtCore.QPointF(nx, track.top() + 1.0), QtCore.QPointF(nx, track.bottom() - 1.0))
            p.setBrush(col)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawEllipse(QtCore.QPointF(nx, track.center().y()), 4.0, 4.0)

        p.end()


class ChromaAndHarmonyWidget(QtWidgets.QWidget):
    """Displays 12-bin chroma, chord candidates, bounded transition strip, key candidates, BPM, and pitch readout."""

    reset_harmony_requested = QtCore.Signal()
    metronome_bpm_changed = QtCore.Signal(float)
    metronome_beats_changed = QtCore.Signal(int)
    metronome_overlay_toggled = QtCore.Signal(bool)
    metronome_standalone_toggled = QtCore.Signal(bool)
    metronome_count_in_toggled = QtCore.Signal(bool)
    metronome_volume_changed = QtCore.Signal(float)
    transpose_semitones_changed = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._chord_history: deque[str] = deque(maxlen=12)
        self._tap_tracker = TapTempoTracker()
        self._latest_detected_bpm: float | None = None
        self._transpose_semitones: int = 0
        self._last_snapshot: AnalysisSnapshot | None = None
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        # Harmonic summary cards (top)
        cards = QtWidgets.QHBoxLayout()

        # Chord card
        chord_box = QtWidgets.QGroupBox("和弦推测 (12 Major / 12 Minor / N / Unknown)")
        chord_l = QtWidgets.QVBoxLayout(chord_box)
        self.chord_primary_lbl = QtWidgets.QLabel("N (静音)")
        self.chord_primary_lbl.setStyleSheet("font-size: 24px; font-weight: 700; color: #7EE2B8;")
        self.chord_tones_lbl = QtWidgets.QLabel("构成音: -")
        self.chord_tones_lbl.setStyleSheet("color: #B8C2D0; font-weight: 600;")
        self.chord_secondary_lbl = QtWidgets.QLabel("第二候选: -")
        self.chord_stability_lbl = QtWidgets.QLabel("稳定度: Silent | 相关度: 0.00")
        chord_l.addWidget(self.chord_primary_lbl)
        chord_l.addWidget(self.chord_tones_lbl)
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
        self.tuning_bar = TuningCentsBar()

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

        self.metronome_count_in_chk = QtWidgets.QCheckBox("预备拍 (1小节)")
        self.metronome_count_in_chk.setToolTip("开始 A/B 回放或分轨混音前，先打一小节纯 CPU 预备拍再进入音乐")
        self.metronome_count_in_chk.toggled.connect(self.metronome_count_in_toggled.emit)

        self.metronome_standalone_btn = QtWidgets.QPushButton("独立节拍器")
        self.metronome_standalone_btn.setCheckable(True)
        self.metronome_standalone_btn.setToolTip("单独播放纯 CPU 节拍器 Click 用于跟练（播放 A/B 或分轨时会自动切回随播模式）")
        self.metronome_standalone_btn.toggled.connect(self.metronome_standalone_toggled.emit)

        self.metronome_vol_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.metronome_vol_slider.setRange(0, 150)
        self.metronome_vol_slider.setValue(70)
        self.metronome_vol_slider.setMinimumWidth(80)
        self.metronome_vol_slider.setMaximumWidth(120)
        self.metronome_vol_slider.setToolTip("调节练习节拍器（含预备拍/独立/随播）Click 音量 (0% - 150%)")
        self.metronome_vol_lbl = QtWidgets.QLabel("音量: 70%")
        self.metronome_vol_lbl.setMinimumWidth(68)
        self.metronome_vol_slider.valueChanged.connect(self._on_metronome_vol_slider_changed)

        met_row.addWidget(self.tap_tempo_btn)
        met_row.addWidget(self.adopt_bpm_btn)
        met_row.addWidget(self.metronome_bpm_spin)
        met_row.addWidget(self.metronome_sig_combo)

        met_row2 = QtWidgets.QHBoxLayout()
        met_row2.addWidget(self.metronome_overlay_chk)
        met_row2.addWidget(self.metronome_count_in_chk)
        met_row2.addWidget(self.metronome_standalone_btn)
        met_row2.addWidget(self.metronome_vol_slider)
        met_row2.addWidget(self.metronome_vol_lbl)
        self.tap_status_lbl = QtWidgets.QLabel("")
        self.tap_status_lbl.setStyleSheet("color: #9AA4B2; font-size: 11px;")
        met_row2.addWidget(self.tap_status_lbl, 1)

        rhythm_l.addWidget(self.bpm_lbl)
        rhythm_l.addWidget(self.bpm_stab_lbl)
        rhythm_l.addWidget(self.pitch_lbl)
        rhythm_l.addWidget(self.tuning_bar)
        rhythm_l.addLayout(met_row)
        rhythm_l.addLayout(met_row2)
        cards.addWidget(rhythm_box, 2)

        root.addLayout(cards)

        # Recent bounded chord transition strip + Capo/Transposition selector + Reset button
        prog_bar = QtWidgets.QHBoxLayout()
        self.chord_progression_lbl = QtWidgets.QLabel("最近和弦进行 (最多 12 步): -")
        self.chord_progression_lbl.setStyleSheet(
            "padding: 5px 10px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px; color: #E6EAF0;"
        )
        self.chord_progression_lbl.setWordWrap(True)

        self.transpose_combo = QtWidgets.QComboBox()
        self.transpose_combo.setToolTip("仅切换乐谱/变调夹和弦与调性显示偏移（零 PCM 拷贝/重采样开销，不影响实音分析）")
        for lbl, semi in TRANSPOSE_PRESETS:
            self.transpose_combo.addItem(lbl, semi)
        self.transpose_combo.currentIndexChanged.connect(self._on_transpose_changed)

        self.reset_harmony_btn = QtWidgets.QPushButton("换歌重置 (和弦/调性/BPM)")
        self.reset_harmony_btn.setToolTip("切歌后一键清空和弦轨迹、调性滑动窗口与 BPM 累积，不中断当前捕获")
        self.reset_harmony_btn.clicked.connect(self._on_reset_clicked)
        prog_bar.addWidget(self.chord_progression_lbl, 1)
        prog_bar.addWidget(QtWidgets.QLabel("移调/Capo:"))
        prog_bar.addWidget(self.transpose_combo)
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
    def transpose_semitones(self) -> int:
        return self._transpose_semitones

    @property
    def recent_progression(self) -> list[str]:
        return list(self._chord_history)

    def _on_transpose_changed(self) -> None:
        semi = int(self.transpose_combo.currentData() or 0)
        if semi != self._transpose_semitones:
            self._transpose_semitones = semi
            self._refresh_transposed_views()
            self.transpose_semitones_changed.emit(semi)

    def set_transpose_semitones(self, semitones: int) -> None:
        target = int(semitones)
        idx = self.transpose_combo.findData(target)
        if idx < 0:
            self.transpose_combo.addItem(f"自定义移调 ({target:+d} 半音)", target)
            idx = self.transpose_combo.findData(target)
        self.transpose_combo.blockSignals(True)
        self.transpose_combo.setCurrentIndex(max(0, idx))
        self.transpose_combo.blockSignals(False)
        self._transpose_semitones = target
        self._refresh_transposed_views()

    def _refresh_transposed_views(self) -> None:
        if self._last_snapshot is not None:
            self._render_harmonic_labels(self._last_snapshot)
        if self._chord_history:
            semi = self._transpose_semitones
            disp = [transpose_chord_symbol(c, semi) if semi != 0 else c for c in self._chord_history]
            self.chord_progression_lbl.setText(f"最近和弦进行 (最多 12 步): {' -> '.join(disp)}")

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

    def _on_metronome_vol_slider_changed(self, value: int) -> None:
        self.metronome_vol_lbl.setText(f"音量: {int(value)}%")
        self.metronome_volume_changed.emit(float(value) / 100.0)

    def sync_metronome_ui(
        self,
        *,
        bpm: float | None = None,
        beats_per_bar: int | None = None,
        overlay_enabled: bool | None = None,
        standalone_playing: bool | None = None,
        count_in_enabled: bool | None = None,
        volume: float | None = None,
    ) -> None:
        if bpm is not None:
            self.metronome_bpm_spin.blockSignals(True)
            self.metronome_bpm_spin.setValue(round(max(30.0, min(240.0, float(bpm))), 1))
            self.metronome_bpm_spin.blockSignals(False)
        if beats_per_bar is not None:
            idx = self.metronome_sig_combo.findData(int(beats_per_bar))
            if idx >= 0:
                self.metronome_sig_combo.blockSignals(True)
                self.metronome_sig_combo.setCurrentIndex(idx)
                self.metronome_sig_combo.blockSignals(False)
        if overlay_enabled is not None:
            self.metronome_overlay_chk.blockSignals(True)
            self.metronome_overlay_chk.setChecked(bool(overlay_enabled))
            self.metronome_overlay_chk.blockSignals(False)
        if standalone_playing is not None:
            self.metronome_standalone_btn.blockSignals(True)
            self.metronome_standalone_btn.setChecked(bool(standalone_playing))
            self.metronome_standalone_btn.setText("停止独立节拍器" if standalone_playing else "独立节拍器")
            self.metronome_standalone_btn.blockSignals(False)
        if count_in_enabled is not None:
            self.metronome_count_in_chk.blockSignals(True)
            self.metronome_count_in_chk.setChecked(bool(count_in_enabled))
            self.metronome_count_in_chk.blockSignals(False)
        if volume is not None:
            pct = max(0, min(150, int(round(float(volume) * 100.0))))
            self.metronome_vol_slider.blockSignals(True)
            self.metronome_vol_slider.setValue(pct)
            self.metronome_vol_slider.blockSignals(False)
            self.metronome_vol_lbl.setText(f"音量: {pct}%")

    def _on_reset_clicked(self) -> None:
        self.clear_progression()
        self.reset_harmony_requested.emit()

    def clear_progression(self) -> None:
        self._chord_history.clear()
        self._tap_tracker.reset()
        self._latest_detected_bpm = None
        self._last_snapshot = None
        self.adopt_bpm_btn.setEnabled(False)
        self.tap_status_lbl.setText("")
        self.chord_progression_lbl.setText("最近和弦进行 (最多 12 步): -")
        self.chord_primary_lbl.setText("N (静音)")
        self.chord_tones_lbl.setText("构成音: -")
        self.chord_secondary_lbl.setText("第二候选: -")
        self.chord_stability_lbl.setText("稳定度: Silent | 相关度: 0.00")
        self.key_primary_lbl.setText("Unknown")
        self.key_secondary_lbl.setText("第二候选: -")
        self.key_relation_lbl.setText("稳定度: Insufficient | 关系说明: 已重置，等待新音频")
        self.bpm_lbl.setText("BPM: Unknown")
        self.bpm_stab_lbl.setText("节拍稳定度: Unknown")
        self.pitch_lbl.setText("主音高: -")
        self.tuning_bar.set_pitch(None, 0.0)

    def _render_harmonic_labels(self, snap: AnalysisSnapshot) -> None:
        semi = self._transpose_semitones
        ch = snap.chord
        if semi == 0 or ch.is_silent:
            disp_chord = ch.primary
            disp_sec = ch.secondary
            self.chord_primary_lbl.setText(disp_chord)
        else:
            disp_chord = transpose_chord_symbol(ch.primary, semi)
            disp_sec = transpose_chord_symbol(ch.secondary, semi)
            self.chord_primary_lbl.setText(
                f"{disp_chord} (实音 {ch.primary})" if disp_chord != ch.primary else disp_chord
            )
        tones = "-" if ch.is_silent else spell_chord_tones(disp_chord)
        self.chord_tones_lbl.setText(f"构成音: {tones}")
        self.chord_secondary_lbl.setText(f"第二候选: {disp_sec}")
        self.chord_stability_lbl.setText(
            f"稳定度: {ch.stability} | 相关度: {ch.correlation:.2f} | 领先差值: {ch.margin:.2f}"
        )

        ky = snap.key
        if semi == 0:
            self.key_primary_lbl.setText(ky.primary)
            self.key_secondary_lbl.setText(f"第二候选: {ky.secondary}")
        else:
            disp_key = transpose_key_label(ky.primary, semi)
            disp_key_sec = transpose_key_label(ky.secondary, semi)
            self.key_primary_lbl.setText(
                f"{disp_key} (实音 {ky.primary})" if disp_key != ky.primary else disp_key
            )
            self.key_secondary_lbl.setText(f"第二候选: {disp_key_sec}")
        mod_tag = " [可能转调]" if ky.modulation_hint else ""
        self.key_relation_lbl.setText(
            f"稳定度: {ky.stability}{mod_tag} | {ky.relation_note}"
        )
        self.key_sig_note_lbl.setText(ky.key_signature_note)

        pt = snap.pitch
        if pt.frequency_hz is not None:
            disp_note = transpose_note_name(pt.note_name, semi) if semi != 0 else pt.note_name
            self.pitch_lbl.setText(
                f"主音高: {disp_note} ({pt.frequency_hz:.1f} Hz, {pt.cents_offset:+.1f} cents)"
            )
            self.tuning_bar.set_pitch(pt.frequency_hz, pt.cents_offset)
        else:
            self.pitch_lbl.setText(f"主音高: {pt.note_name}")
            self.tuning_bar.set_pitch(None, 0.0)

    def update_analysis(self, snap: AnalysisSnapshot, chroma_history: np.ndarray | None = None) -> None:
        self._last_snapshot = snap
        self._render_harmonic_labels(snap)
        ch = snap.chord
        if not ch.is_silent and ch.primary not in ("Unknown", "N (静音)", "-"):
            if not self._chord_history or self._chord_history[-1] != ch.primary:
                self._chord_history.append(ch.primary)
                semi = self._transpose_semitones
                disp = [transpose_chord_symbol(c, semi) if semi != 0 else c for c in self._chord_history]
                self.chord_progression_lbl.setText(
                    f"最近和弦进行 (最多 12 步): {' -> '.join(disp)}"
                )

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

        if snap.chroma_12:
            self._bar_item.setOpts(height=np.asarray(snap.chroma_12, dtype=np.float32))

        if chroma_history is not None and chroma_history.size > 0:
            self._chroma_img.setImage(chroma_history, autoLevels=False, levels=(0.0, 0.9))

