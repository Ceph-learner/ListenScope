"""PyQtGraph 12-bin chroma, chord candidate, Krumhansl-Schmuckler key, BPM, and pitch display."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from analysis.chords import (
    chord_scale_degree,
    spell_chord_tones,
    transpose_chord_symbol,
    transpose_key_label,
    transpose_note_name,
)
from analysis.chroma import PITCH_CLASSES
from audio.drum_preview import DrumPreviewPlayer
from audio.metronome import TapTempoTracker
from core.models import AnalysisSnapshot
from ui.appearance import apply_plot_appearance, set_widget_tone
from ui.chord_practice import ChordPracticeDialog
from ui.help_badge import HelpBadge
from ui.marathon_style import (
    TelemetryHeader,
    apply_marathon_plot_theme,
    get_marathon_palette,
    marathon_colormap_lut,
)


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
    """Lightweight horizontal -50c..+50c pitch-accuracy needle indicator with smooth glide animation."""

    COLOR_IN_TUNE = "#00A878"
    COLOR_SLIGHT = "#0284C7"
    COLOR_OFF = "#EF4444"
    COLOR_IDLE = "#64748B"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_signal: bool = False
        self._cents: float = 0.0
        self._display_cents: float = 0.0
        self._track_bg: str = "#E2E8F0"
        self._track_border: str = "#CBD5E1"
        self._center_tick: str = "#334155"
        self._color_in_tune: str = self.COLOR_IN_TUNE
        self._color_slight: str = self.COLOR_SLIGHT
        self._color_off: str = self.COLOR_OFF
        self._color_idle: str = self.COLOR_IDLE

        self._needle_anim = QtCore.QVariantAnimation(self)
        self._needle_anim.setDuration(90)
        self._needle_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._needle_anim.valueChanged.connect(self._on_anim_value)

        self.setFixedHeight(18)
        self.setMinimumWidth(140)
        self.setToolTip("实时主音高音准偏离条 (-50 ~ +50 cents；青绿色 ±10c 为准音区间，科技蓝 ±25c 微偏)")

    def _on_anim_value(self, value: object) -> None:
        try:
            self._display_cents = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        self.update()

    def set_theme_colors(
        self,
        *,
        track_bg: str,
        track_border: str,
        center_tick: str,
        in_tune: str = "#00A878",
        slight: str = "#0284C7",
        off: str = "#EF4444",
        idle: str = "#64748B",
    ) -> None:
        self._track_bg = track_bg
        self._track_border = track_border
        self._center_tick = center_tick
        self._color_in_tune = in_tune
        self._color_slight = slight
        self._color_off = off
        self._color_idle = idle
        self.update()

    @property
    def has_signal(self) -> bool:
        return self._has_signal

    @property
    def cents_offset(self) -> float:
        return self._cents

    @property
    def zone_color(self) -> str:
        if not self._has_signal:
            return self._color_idle
        ac = abs(self._cents)
        if ac <= 10.0:
            return self._color_in_tune
        if ac <= 25.0:
            return self._color_slight
        return self._color_off

    def set_pitch(self, frequency_hz: float | None, cents_offset: float = 0.0) -> None:
        if frequency_hz is None:
            if not self._has_signal and self._cents == 0.0:
                return
            self._needle_anim.stop()
            self._has_signal = False
            self._cents = 0.0
            self._display_cents = 0.0
            self.update()
            return
        freq = float(frequency_hz)
        if not math.isfinite(freq) or freq <= 0.0:
            if not self._has_signal and self._cents == 0.0:
                return
            self._needle_anim.stop()
            self._has_signal = False
            self._cents = 0.0
            self._display_cents = 0.0
            self.update()
            return
        cents = float(cents_offset)
        if not math.isfinite(cents):
            cents = 0.0
        clamped = max(-50.0, min(50.0, cents))
        was_signal = self._has_signal
        self._has_signal = True
        self._cents = clamped
        if not was_signal or not self.isVisible() or abs(clamped - self._display_cents) < 0.4:
            self._needle_anim.stop()
            self._display_cents = clamped
            self.update()
        else:
            self._needle_anim.stop()
            self._needle_anim.setStartValue(self._display_cents)
            self._needle_anim.setEndValue(clamped)
            self._needle_anim.start()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        rect = self.rect()
        if rect.width() <= 6 or rect.height() <= 4:
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        pad = 6
        track = QtCore.QRectF(pad, 3.0, max(1.0, rect.width() - 2 * pad), max(4.0, rect.height() - 6.0))
        p.setPen(QtGui.QPen(QtGui.QColor(self._track_border), 1.0))
        p.setBrush(QtGui.QColor(self._track_bg))
        p.drawRoundedRect(track, 3.0, 3.0)

        # Signal cyan-green center ±10 cents zone
        band_w = track.width() * 0.20
        center_x = track.center().x()
        band_rect = QtCore.QRectF(center_x - band_w * 0.5, track.top() + 1.0, band_w, max(2.0, track.height() - 2.0))
        in_tune_col = QtGui.QColor(self._color_in_tune)
        in_tune_col.setAlpha(44)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(in_tune_col)
        p.drawRect(band_rect)

        # Center 0c tick
        p.setPen(QtGui.QPen(QtGui.QColor(self._center_tick), 1.0))
        p.drawLine(QtCore.QPointF(center_x, track.top() + 1.0), QtCore.QPointF(center_x, track.bottom() - 1.0))

        if self._has_signal:
            ratio = (self._display_cents + 50.0) / 100.0
            nx = track.left() + ratio * track.width()
            col = QtGui.QColor(self.zone_color)
            p.setPen(QtGui.QPen(col, 1.0))
            p.setBrush(col)
            needle = QtCore.QRectF(nx - 2.0, track.top() + 1.0, 4.0, max(2.0, track.height() - 2.0))
            p.drawRoundedRect(needle, 1.0, 1.0)

        p.end()


class ChromaAndHarmonyWidget(QtWidgets.QWidget):
    """Displays 12-bin chroma, chord candidates, bounded transition strip, key candidates, BPM, and pitch readout."""

    reset_harmony_requested = QtCore.Signal()
    auto_reset_toggled = QtCore.Signal(bool)
    progression_mode_changed = QtCore.Signal(str)
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
        self._practice_preview_player: DrumPreviewPlayer | None = None
        self._practice_before_play: Callable[[], str | None] | None = None
        self._active_practice_dialog: ChordPracticeDialog | None = None
        self._default_chroma_lut: np.ndarray | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        # Harmonic summary cards (top)
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(8)

        # Chord card
        chord_box = QtWidgets.QFrame()
        chord_box.setProperty("marathonCard", True)
        chord_box.setProperty("accentRail", "primary")
        chord_box.setToolTip("12 Major / 12 Minor / N / Unknown")
        chord_box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        chord_l = QtWidgets.QVBoxLayout(chord_box)
        chord_l.setContentsMargins(10, 8, 10, 8)
        chord_l.setSpacing(4)
        chord_l.addWidget(TelemetryHeader("CHORD // 01", "和弦推测", badge_text="MAJ / MIN"))
        self.chord_primary_lbl = QtWidgets.QLabel("N (静音)")
        self.chord_primary_lbl.setObjectName("chromaPrimary")
        self.chord_tones_lbl = QtWidgets.QLabel("构成音: -")
        self.chord_tones_lbl.setObjectName("chromaSubtle")
        self.chord_degree_lbl = QtWidgets.QLabel("相对级数: -")
        self.chord_degree_lbl.setObjectName("chromaSubtle")
        self.chord_degree_lbl.setToolTip("相对当前检测调性的和弦级数。小调以自然小调音阶为基准。")
        self.chord_secondary_lbl = QtWidgets.QLabel("第二候选: -")
        self.chord_secondary_lbl.setObjectName("chromaCaption")
        self.chord_stability_lbl = QtWidgets.QLabel("稳定度: Silent | 相关 0.00")
        self.chord_stability_lbl.setObjectName("chromaCaption")
        self.chord_stability_lbl.setWordWrap(True)
        self.chord_stability_lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        chord_l.addWidget(self.chord_primary_lbl)
        chord_l.addWidget(self.chord_tones_lbl)
        chord_l.addWidget(self.chord_degree_lbl)
        chord_l.addWidget(self.chord_secondary_lbl)
        chord_l.addWidget(self.chord_stability_lbl)
        chord_l.addStretch(1)
        cards.addWidget(chord_box, 3)

        # Key card
        key_box = QtWidgets.QFrame()
        key_box.setProperty("marathonCard", True)
        key_box.setProperty("accentRail", "secondary")
        key_box.setToolTip("Krumhansl-Schmuckler 滑动窗口")
        key_box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        key_l = QtWidgets.QVBoxLayout(key_box)
        key_l.setContentsMargins(10, 8, 10, 8)
        key_l.setSpacing(4)
        key_l.addWidget(TelemetryHeader("TONALITY // 02", "调性推测", badge_text="K-S WINDOW"))
        self.key_primary_lbl = QtWidgets.QLabel("Unknown")
        self.key_primary_lbl.setObjectName("chromaSecondaryHero")
        self.key_secondary_lbl = QtWidgets.QLabel("第二候选: -")
        self.key_secondary_lbl.setObjectName("chromaSubtle")
        self.key_relation_lbl = QtWidgets.QLabel("稳定度: Insufficient | 关系说明: 等待音频")
        self.key_relation_lbl.setObjectName("chromaCaption")
        self.key_relation_lbl.setWordWrap(True)
        self.key_relation_lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        self.key_sig_note_lbl = QtWidgets.QLabel(
            "说明: 调性中心(Key)与调号(Key Signature)并不完全等同，关系大小调/调式混合可能共用调号。"
        )
        self.key_sig_note_lbl.setWordWrap(True)
        self.key_sig_note_lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        self.key_sig_note_lbl.setObjectName("chromaCaption")
        key_l.addWidget(self.key_primary_lbl)
        key_l.addWidget(self.key_secondary_lbl)
        key_l.addWidget(self.key_relation_lbl)
        key_l.addWidget(self.key_sig_note_lbl)
        key_l.addStretch(1)
        cards.addWidget(key_box, 3)

        # BPM + Pitch + CPU Practice Metronome card
        rhythm_box = QtWidgets.QFrame()
        rhythm_box.setProperty("marathonCard", True)
        rhythm_box.setProperty("accentRail", "obsidian")
        rhythm_box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        rhythm_l = QtWidgets.QVBoxLayout(rhythm_box)
        rhythm_l.setContentsMargins(10, 8, 10, 8)
        rhythm_l.setSpacing(4)
        rhythm_l.addWidget(TelemetryHeader("TEMPO & PITCH // 03", "节拍 · 音高 · CPU 节拍器", badge_text="SYNTH CLICK"))

        self.bpm_lbl = QtWidgets.QLabel("BPM: Unknown")
        self.bpm_lbl.setObjectName("chromaWarnHero")
        self.bpm_stab_lbl = QtWidgets.QLabel("节拍稳定度: Unknown")
        self.bpm_stab_lbl.setObjectName("chromaCaption")
        self.bpm_stab_lbl.setWordWrap(True)

        pitch_row = QtWidgets.QHBoxLayout()
        pitch_row.setSpacing(8)
        self.pitch_lbl = QtWidgets.QLabel("主音高: -")
        self.pitch_lbl.setObjectName("chromaSubtle")
        self.tuning_bar = TuningCentsBar()
        pitch_row.addWidget(self.pitch_lbl)
        pitch_row.addWidget(self.tuning_bar, 1)

        met_row = QtWidgets.QHBoxLayout()
        met_row.setSpacing(6)
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
        met_row.addWidget(
            HelpBadge(
                "Tap 定速与纯 CPU 节拍器",
                "连续点击「Tap 定速」两次以上即可估算速度；「随播节拍器」与「预备拍」均纯 CPU 混音合成，支持 0.5×–1.25× 变速同速跟随。",
            )
        )

        met_row2 = QtWidgets.QHBoxLayout()
        met_row2.setSpacing(6)
        met_row2.addWidget(self.metronome_overlay_chk)
        met_row2.addWidget(self.metronome_count_in_chk)
        met_row2.addWidget(self.metronome_standalone_btn)
        met_row2.addWidget(self.metronome_vol_slider)
        met_row2.addWidget(self.metronome_vol_lbl)
        self.tap_status_lbl = QtWidgets.QLabel("")
        self.tap_status_lbl.setObjectName("chromaCaption")
        met_row2.addWidget(self.tap_status_lbl, 1)

        rhythm_l.addWidget(self.bpm_lbl)
        rhythm_l.addWidget(self.bpm_stab_lbl)
        rhythm_l.addLayout(pitch_row)
        rhythm_l.addLayout(met_row)
        rhythm_l.addLayout(met_row2)
        rhythm_l.addStretch(1)
        cards.addWidget(rhythm_box, 4)

        root.addLayout(cards)

        # Recent bounded chord transition strip + Practice action + Capo/Reset toolbar
        prog_bar = QtWidgets.QHBoxLayout()
        prog_bar.setSpacing(8)
        self.chord_progression_lbl = QtWidgets.QLabel("最近和弦进行 (最多 12 步): -")
        self.chord_progression_lbl.setObjectName("chromaProgression")
        self.chord_progression_lbl.setWordWrap(True)
        self.progression_mode_combo = QtWidgets.QComboBox()
        for label, value in (("和弦名", "chords"), ("罗马数字", "degrees"), ("和弦名与级数", "both")):
            self.progression_mode_combo.addItem(label, value)
        self.progression_mode_combo.setAccessibleName("最近和弦进行显示方式")
        self.progression_mode_combo.currentIndexChanged.connect(self._on_progression_mode_changed)

        self.transpose_combo = QtWidgets.QComboBox()
        self.transpose_combo.setToolTip("仅切换乐谱/变调夹和弦与调性显示偏移（零 PCM 拷贝/重采样开销，不影响实音分析）")
        for lbl, semi in TRANSPOSE_PRESETS:
            self.transpose_combo.addItem(lbl, semi)
        self.transpose_combo.currentIndexChanged.connect(self._on_transpose_changed)

        self.auto_reset_chk = QtWidgets.QCheckBox("自动切歌重置")
        self.auto_reset_chk.setChecked(True)
        self.auto_reset_chk.setToolTip(
            "监测到当前播放软件通过 Windows 媒体会话 (SMTC) 真实切歌时自动清空和弦/调性/BPM；"
            "同一首歌暂停、恢复或拖动进度条不会触发误重置"
        )
        self.auto_reset_chk.toggled.connect(self.auto_reset_toggled.emit)

        self.reset_harmony_btn = QtWidgets.QPushButton("换歌重置 (和弦/调性/BPM)")
        self.reset_harmony_btn.setToolTip("切歌后一键清空和弦轨迹、调性滑动窗口与 BPM 累积，不中断当前捕获")
        self.reset_harmony_btn.clicked.connect(self._on_reset_clicked)
        prog_bar.addWidget(self.chord_progression_lbl, 1)
        prog_bar.addWidget(self.progression_mode_combo)
        self.practice_chords_btn = QtWidgets.QPushButton("练习和弦")
        self.practice_chords_btn.setObjectName("analysisAction")
        self.practice_chords_btn.setToolTip("查看基于最近和弦推荐的练习模板，支持本地试听与导出 MIDI")
        self.practice_chords_btn.clicked.connect(self._open_chord_practice)
        prog_bar.addWidget(self.practice_chords_btn)
        root.addLayout(prog_bar)

        tools_bar = QtWidgets.QHBoxLayout()
        tools_bar.setSpacing(8)
        tools_bar.addWidget(QtWidgets.QLabel("移调/Capo:"))
        tools_bar.addWidget(self.transpose_combo)
        tools_bar.addWidget(
            HelpBadge(
                "移调 / Capo 与转调保护",
                "Capo/移调仅改变和弦、调性与记谱提示的指型展示，底层检测始终锚定实音与实际 MIDI 音高，避免转调后错位；遇到转调歌曲时「调性推测」卡片会亮出 [可能转调] 警告。",
            )
        )
        tools_bar.addWidget(self.auto_reset_chk)
        tools_bar.addWidget(
            HelpBadge(
                "SMTC 自动切歌重置",
                "仅当 Windows 媒体会话 (SMTC) 连续两次确认目标播放器切换了新曲目时，才自动清空和弦轨迹、调性窗口与 BPM，暂停/拖动进度条不会误重置。",
            )
        )
        tools_bar.addWidget(self.reset_harmony_btn)
        tools_bar.addStretch(1)
        root.addLayout(tools_bar)

        self.track_status_lbl = QtWidgets.QLabel("曲目会话监测 (SMTC): 待启动按进程捕获（也可随时手动点击「换歌重置」）")
        self.track_status_lbl.setWordWrap(True)
        self.track_status_lbl.setObjectName("chromaTrackStatus")
        root.addWidget(self.track_status_lbl)

        # Plots splitter: 12-bin Chroma Bar + Bounded Chroma History Heatmap
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        self._chroma_bar_heights = np.zeros(12, dtype=np.float32)
        self._label_cache: dict[int, str] = {}

        self.chroma_bar_plot = pg.PlotWidget(title="12-BIN CHROMA // 实时色度分布")
        self.chroma_bar_plot.setBackground("#F8FAFC")
        self.chroma_bar_plot.setYRange(0.0, 1.05)
        self.chroma_bar_plot.showGrid(x=False, y=True, alpha=0.22)
        ax = self.chroma_bar_plot.getAxis("bottom")
        ax.setTicks([[(i, name) for i, name in enumerate(PITCH_CLASSES)]])
        self._bar_item = pg.BarGraphItem(
            x=np.arange(12, dtype=np.float32),
            height=self._chroma_bar_heights,
            width=0.65,
            brush="#00A878",
            pen=pg.mkPen("#008F66", width=0.8),
        )
        self.chroma_bar_plot.addItem(self._bar_item)
        splitter.addWidget(self.chroma_bar_plot)

        self.chroma_hist_plot = pg.PlotWidget(title="CHROMA HEATMAP // 有界时序热图 (120s)")
        self.chroma_hist_plot.setBackground("#F8FAFC")
        ay = self.chroma_hist_plot.getAxis("left")
        note_font = QtGui.QFont(self.font())
        note_font.setPixelSize(10)
        ay.setStyle(tickFont=note_font, tickTextOffset=3)
        ay.geometryChanged.connect(self.refresh_chroma_note_ticks)
        self.chroma_hist_plot.setYRange(0, len(PITCH_CLASSES), padding=0)
        self.chroma_hist_plot.setMouseEnabled(x=True, y=False)
        self.refresh_chroma_note_ticks()
        self._chroma_img = pg.ImageItem()
        try:
            cmap = pg.colormap.get("viridis") if hasattr(pg, "colormap") else None
        except Exception:
            cmap = None
        if cmap is not None:
            self._default_chroma_lut = cmap.getLookupTable(0.0, 1.0, 256)
        self._chroma_img.setLookupTable(marathon_colormap_lut("chroma", "light"))
        self.chroma_hist_plot.addItem(self._chroma_img)
        splitter.addWidget(self.chroma_hist_plot)

        splitter.setSizes([210, 240])
        root.addWidget(splitter, 1)

    def refresh_chroma_note_ticks(self) -> None:
        axis = self.chroma_hist_plot.getAxis("left")
        font = axis.style["tickFont"] or self.font()
        label_height = QtGui.QFontMetrics(font).height() + 3
        available = max(1.0, axis.height())
        stride = max(1, min(len(PITCH_CLASSES), int(np.ceil(len(PITCH_CLASSES) * label_height / available))))
        if stride != getattr(self, "_chroma_tick_stride", None):
            self._chroma_tick_stride = stride
            axis.setTicks([[(i + 0.5, PITCH_CLASSES[i]) for i in range(0, len(PITCH_CLASSES), stride)]])

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
        self._render_recent_progression()

    @property
    def progression_mode(self) -> str:
        return self.progression_mode_combo.currentData()

    def set_progression_mode(self, mode: str) -> None:
        index = self.progression_mode_combo.findData(mode)
        self.progression_mode_combo.setCurrentIndex(max(0, index))

    def _on_progression_mode_changed(self) -> None:
        self._render_recent_progression()
        self.progression_mode_changed.emit(self.progression_mode)

    def _render_recent_progression(self) -> None:
        key = self._last_snapshot.key.primary if self._last_snapshot is not None else ""
        mode = self.progression_mode
        labels = []
        for chord in self._chord_history:
            name = transpose_chord_symbol(chord, self._transpose_semitones)
            degree = chord_scale_degree(chord, key) if mode != "chords" else "-"
            if degree == "-":
                labels.append(name)
            elif mode == "degrees":
                labels.append(degree)
            else:
                labels.append(f"{name} ({degree})")
        text = " → ".join(labels) or "-"
        self.chord_progression_lbl.setText(f"最近和弦进行 (最多 12 步): {text}")

    def configure_chord_practice(
        self,
        *,
        preview_player: DrumPreviewPlayer | None = None,
        before_play: Callable[[], str | None] | None = None,
    ) -> None:
        self._practice_preview_player = preview_player
        self._practice_before_play = before_play

    def sync_chord_preview_stopped(self, *, natural: bool = False) -> None:
        dialog = self._active_practice_dialog
        if dialog is None:
            return
        try:
            dialog.sync_preview_stopped(natural=natural)
        except RuntimeError:
            self._active_practice_dialog = None

    def open_chord_practice(self, *, modal: bool = True) -> ChordPracticeDialog:
        if self._active_practice_dialog is not None:
            prev = self._active_practice_dialog
            self._active_practice_dialog = None
            try:
                prev.stop_preview()
                prev.close()
                prev.deleteLater()
            except RuntimeError:
                pass

        estimate = self._last_snapshot.key if self._last_snapshot is not None else None
        dialog = ChordPracticeDialog(
            self.recent_progression,
            estimate,
            self._transpose_semitones,
            self,
            bpm=float(self.metronome_bpm_spin.value()),
            detected_bpm=self._latest_detected_bpm,
            preview_player=self._practice_preview_player,
            before_play=self._practice_before_play,
        )
        self._active_practice_dialog = dialog
        if modal:
            try:
                dialog.exec()
            finally:
                dialog.stop_preview()
                if self._active_practice_dialog is dialog:
                    self._active_practice_dialog = None
                dialog.deleteLater()
        else:
            def _on_finished(_result: int = 0) -> None:
                dialog.stop_preview()
                if self._active_practice_dialog is dialog:
                    self._active_practice_dialog = None

            dialog.finished.connect(_on_finished)
            dialog.show()
        return dialog

    def _open_chord_practice(self) -> None:
        self.open_chord_practice(modal=True)

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

    def sync_auto_reset_ui(
        self,
        *,
        enabled: bool | None = None,
        track_status_text: str | None = None,
    ) -> None:
        if enabled is not None:
            self.auto_reset_chk.blockSignals(True)
            self.auto_reset_chk.setChecked(bool(enabled))
            self.auto_reset_chk.blockSignals(False)
        if track_status_text is not None:
            self.track_status_lbl.setText(track_status_text)

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

    def _set_cached_text(self, label: QtWidgets.QLabel, text: str) -> None:
        key = id(label)
        if self._label_cache.get(key) != text:
            self._label_cache[key] = text
            label.setText(text)

    def apply_theme(
        self,
        appearance,
        *,
        system_is_dark: bool | None = None,
        marathon_variant: str | None = None,
    ) -> None:
        if marathon_variant in ("light", "dark"):
            p = get_marathon_palette(marathon_variant)
            for plot in (self.chroma_bar_plot, self.chroma_hist_plot):
                apply_marathon_plot_theme(plot, appearance, marathon_variant)
            self.tuning_bar.set_theme_colors(
                track_bg=p.cents_track_bg,
                track_border=p.cents_track_bd,
                center_tick=p.cents_center_tick,
                in_tune=p.cents_in_tune,
                slight=p.cents_slight,
                off=p.cents_off,
                idle=p.cents_idle,
            )
            self._bar_item.setOpts(brush=p.accent, pen=pg.mkPen(p.accent_strong, width=0.8))
            self._chroma_img.setLookupTable(marathon_colormap_lut("chroma", marathon_variant))
            return

        for plot in (self.chroma_bar_plot, self.chroma_hist_plot):
            apply_plot_appearance(plot, appearance, system_is_dark=system_is_dark)
        mode = appearance.resolve_theme_mode(system_is_dark=system_is_dark)
        bg, fg, accent = appearance.effective_colors(system_is_dark=system_is_dark)
        bg_c, fg_c = QtGui.QColor(bg), QtGui.QColor(fg)
        track_bg = QtGui.QColor(
            round(bg_c.red() + (fg_c.red() - bg_c.red()) * 0.04),
            round(bg_c.green() + (fg_c.green() - bg_c.green()) * 0.04),
            round(bg_c.blue() + (fg_c.blue() - bg_c.blue()) * 0.04),
        ).name()
        border_c = QtGui.QColor(
            round(bg_c.red() + (fg_c.red() - bg_c.red()) * 0.20),
            round(bg_c.green() + (fg_c.green() - bg_c.green()) * 0.20),
            round(bg_c.blue() + (fg_c.blue() - bg_c.blue()) * 0.20),
        ).name()
        center_c = QtGui.QColor(
            round(bg_c.red() + (fg_c.red() - bg_c.red()) * 0.55),
            round(bg_c.green() + (fg_c.green() - bg_c.green()) * 0.55),
            round(bg_c.blue() + (fg_c.blue() - bg_c.blue()) * 0.55),
        ).name()
        if mode == "light":
            self.tuning_bar.set_theme_colors(
                track_bg=track_bg,
                track_border=border_c,
                center_tick=center_c,
                in_tune="#15803D",
                slight="#B45309",
                off="#DC2626",
                idle="#6B7280",
            )
        else:
            self.tuning_bar.set_theme_colors(
                track_bg=track_bg,
                track_border=border_c,
                center_tick=center_c,
                in_tune="#2EC27E",
                slight="#F5A623",
                off="#E03E3E",
                idle="#6B7480",
            )
        self._bar_item.setOpts(brush=accent, pen=pg.mkPen(accent, width=0.8))
        if self._default_chroma_lut is not None:
            self._chroma_img.setLookupTable(self._default_chroma_lut)

    def _on_reset_clicked(self) -> None:
        self.clear_progression()
        self.reset_harmony_requested.emit()

    def clear_progression(self) -> None:
        self._chord_history.clear()
        self._tap_tracker.reset()
        self._latest_detected_bpm = None
        self._last_snapshot = None
        self.adopt_bpm_btn.setEnabled(False)
        self._set_cached_text(self.tap_status_lbl, "")
        self._set_cached_text(self.chord_progression_lbl, "最近和弦进行 (最多 12 步): -")
        self._set_cached_text(self.chord_primary_lbl, "N (静音)")
        self._set_cached_text(self.chord_tones_lbl, "构成音: -")
        self._set_cached_text(self.chord_degree_lbl, "相对级数: -")
        self._set_cached_text(self.chord_secondary_lbl, "第二候选: -")
        self._set_cached_text(self.chord_stability_lbl, "稳定度: Silent | 相关度: 0.00")
        self._set_cached_text(self.key_primary_lbl, "Unknown")
        self._set_cached_text(self.key_secondary_lbl, "第二候选: -")
        self._set_cached_text(self.key_relation_lbl, "稳定度: Insufficient | 关系说明: 已重置，等待新音频")
        set_widget_tone(self.key_relation_lbl, "info")
        self._set_cached_text(self.bpm_lbl, "BPM: Unknown")
        self._set_cached_text(self.bpm_stab_lbl, "节拍稳定度: Unknown")
        self._set_cached_text(self.pitch_lbl, "主音高: -")
        self.tuning_bar.set_pitch(None, 0.0)
        try:
            self._chroma_img.clear()
        except Exception:
            pass

    def _render_harmonic_labels(self, snap: AnalysisSnapshot) -> None:
        semi = self._transpose_semitones
        ch = snap.chord
        if semi == 0 or ch.is_silent:
            disp_chord = ch.primary
            disp_sec = ch.secondary
            self._set_cached_text(self.chord_primary_lbl, disp_chord)
        else:
            disp_chord = transpose_chord_symbol(ch.primary, semi)
            disp_sec = transpose_chord_symbol(ch.secondary, semi)
            self._set_cached_text(
                self.chord_primary_lbl,
                f"{disp_chord} (实音 {ch.primary})" if disp_chord != ch.primary else disp_chord,
            )
        tones = "-" if ch.is_silent else spell_chord_tones(disp_chord)
        self._set_cached_text(self.chord_tones_lbl, f"构成音: {tones}")
        self._set_cached_text(self.chord_secondary_lbl, f"第二候选: {disp_sec}")
        self._set_cached_text(
            self.chord_stability_lbl,
            f"稳定度: {ch.stability} | 相关 {ch.correlation:.2f} | 差 {ch.margin:.2f}",
        )

        ky = snap.key
        degree = "-" if ch.is_silent else chord_scale_degree(ch.primary, ky.primary)
        self._set_cached_text(self.chord_degree_lbl, f"相对级数: {degree}")
        if semi == 0:
            self._set_cached_text(self.key_primary_lbl, ky.primary)
            self._set_cached_text(self.key_secondary_lbl, f"第二候选: {ky.secondary}")
        else:
            disp_key = transpose_key_label(ky.primary, semi)
            disp_key_sec = transpose_key_label(ky.secondary, semi)
            self._set_cached_text(
                self.key_primary_lbl,
                f"{disp_key} (实音 {ky.primary})" if disp_key != ky.primary else disp_key,
            )
            self._set_cached_text(self.key_secondary_lbl, f"第二候选: {disp_key_sec}")
        mod_tag = " [可能转调]" if ky.modulation_hint else ""
        set_widget_tone(self.key_relation_lbl, "warn" if ky.modulation_hint else "info")
        self._set_cached_text(
            self.key_relation_lbl,
            f"稳定度: {ky.stability}{mod_tag} | {ky.relation_note}",
        )
        self._set_cached_text(self.key_sig_note_lbl, ky.key_signature_note)

        pt = snap.pitch
        if pt.frequency_hz is not None and math.isfinite(float(pt.frequency_hz)) and float(pt.frequency_hz) > 0:
            concert_midi = max(0, min(127, int(round(69.0 + 12.0 * math.log2(float(pt.frequency_hz) / 440.0)))))
            disp_note = transpose_note_name(pt.note_name, semi) if semi != 0 else pt.note_name
            disp_midi = max(0, min(127, concert_midi + semi))
            bass_tag = " [低音区]" if float(pt.frequency_hz) < 185.0 else ""
            if semi != 0:
                pitch_txt = (
                    f"主音高: {disp_note} (MIDI {disp_midi} | 实音 {pt.note_name} MIDI {concert_midi} · "
                    f"{pt.frequency_hz:.1f} Hz, {pt.cents_offset:+.1f} cents){bass_tag}"
                )
            else:
                pitch_txt = (
                    f"主音高: {disp_note} (MIDI {concert_midi} · "
                    f"{pt.frequency_hz:.1f} Hz, {pt.cents_offset:+.1f} cents){bass_tag}"
                )
            self._set_cached_text(self.pitch_lbl, pitch_txt)
            self.tuning_bar.set_pitch(pt.frequency_hz, pt.cents_offset)
        else:
            self._set_cached_text(self.pitch_lbl, f"主音高: {pt.note_name}")
            self.tuning_bar.set_pitch(None, 0.0)

    def update_analysis(self, snap: AnalysisSnapshot, chroma_history: np.ndarray | None = None) -> None:
        previous_key = self._last_snapshot.key.primary if self._last_snapshot is not None else None
        self._last_snapshot = snap
        self._render_harmonic_labels(snap)
        ch = snap.chord
        new_chord = (
            not ch.is_silent and ch.primary not in ("Unknown", "N (静音)", "-")
            and (not self._chord_history or self._chord_history[-1] != ch.primary)
        )
        if new_chord:
            self._chord_history.append(ch.primary)
        if new_chord or previous_key != snap.key.primary:
            self._render_recent_progression()

        tp = snap.tempo
        if tp.bpm is not None:
            self._latest_detected_bpm = float(tp.bpm)
            if not self.adopt_bpm_btn.isEnabled():
                self.adopt_bpm_btn.setEnabled(True)
            self._set_cached_text(self.bpm_lbl, f"BPM: {tp.bpm:.1f}")
        else:
            self._latest_detected_bpm = None
            if self.adopt_bpm_btn.isEnabled():
                self.adopt_bpm_btn.setEnabled(False)
            self._set_cached_text(self.bpm_lbl, "BPM: Unknown")
        self._set_cached_text(self.bpm_stab_lbl, f"节拍稳定度: {tp.stability} (自相关峰: {tp.confidence_score:.2f})")

        if snap.chroma_12 and len(snap.chroma_12) == 12:
            self._chroma_bar_heights[:] = snap.chroma_12
            self._bar_item.setOpts(height=self._chroma_bar_heights)

        if chroma_history is not None and chroma_history.size > 0:
            self._chroma_img.setImage(chroma_history, autoLevels=False, levels=(0.0, 0.9))

