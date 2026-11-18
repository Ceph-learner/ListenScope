"""Multi-stem synchronized mixer, OOM recovery prompt, stem analysis bridge, and Basic Pitch MIDI UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from analysis.chroma import PITCH_CLASSES
from analysis.drum_midi import export_drum_midi
from audio.playback import BASS_MONITOR_BOOST_DB, StemMixerEngine
from core.appearance import Appearance
from core.models import (
    AIJobProgress,
    AIJobResult,
    AIJobState,
    ChordTimelineSegment,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    OOMRecoveryAction,
    StemDeepAnalysisReport,
)
from ui.appearance import apply_plot_appearance, set_widget_tone
from ui.chroma_widget import (
    spell_chord_tones,
    transpose_chord_symbol,
    transpose_key_label,
    transpose_note_name,
)
from ui.help_badge import HelpBadge
from ui.marathon_style import TelemetryHeader, apply_marathon_plot_theme, get_marathon_palette


def _fmt_sec(sec: float) -> str:
    sec = max(0.0, float(sec))
    mins = int(sec // 60)
    rem = sec - mins * 60
    return f"{mins:02d}:{rem:04.1f}"


class _StemTrackRow(QtWidgets.QFrame):
    """Per-stem waveform, Mute/Solo, Volume, and Analyze/MIDI actions."""

    mute_changed = QtCore.Signal(str, bool)
    solo_changed = QtCore.Signal(str, bool)
    volume_changed = QtCore.Signal(str, float)
    send_to_analysis_requested = QtCore.Signal(str, str)
    transcribe_midi_requested = QtCore.Signal(str, str)

    def __init__(self, stem_name: str, stem_path: str, duration_sec: float, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.stem_name = stem_name
        self.stem_path = stem_path
        self._wave_x: Optional[np.ndarray] = None
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setProperty("trackCard", True)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        # Left column: stem label & duration
        info = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel(stem_name.upper())
        title.setObjectName("stemTrackTitle")
        dur_lbl = QtWidgets.QLabel(f"{duration_sec:.1f}s")
        dur_lbl.setObjectName("stemMetaDuration")
        info.addWidget(title)
        info.addWidget(dur_lbl)
        row.addLayout(info)

        # Mute / Solo / Volume
        self.mute_btn = QtWidgets.QPushButton("M")
        self.mute_btn.setObjectName("stemMuteBtn")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(32)
        self.mute_btn.toggled.connect(lambda checked: self.mute_changed.emit(self.stem_name, checked))

        self.solo_btn = QtWidgets.QPushButton("S")
        self.solo_btn.setObjectName("stemSoloBtn")
        self.solo_btn.setCheckable(True)
        self.solo_btn.setFixedWidth(32)
        self.solo_btn.toggled.connect(lambda checked: self.solo_changed.emit(self.stem_name, checked))

        self.vol_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(110)
        self.vol_slider.valueChanged.connect(lambda val: self.volume_changed.emit(self.stem_name, val / 100.0))

        row.addWidget(self.mute_btn)
        row.addWidget(self.solo_btn)
        row.addWidget(self.vol_slider)

        # Waveform preview plot
        self.wave_plot = pg.PlotWidget()
        self.wave_plot.setMaximumHeight(54)
        self.wave_plot.setMinimumHeight(44)
        self.wave_plot.setBackground("#F8FAFC")
        self.wave_plot.setYRange(-1.0, 1.0)
        self.wave_plot.hideAxis("bottom")
        self.wave_plot.hideAxis("left")
        self.wave_plot.setMouseEnabled(x=False, y=False)
        self._max_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.1))
        self._min_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.1))
        row.addWidget(self.wave_plot, 1)

        # Bridge actions
        analyze_btn = QtWidgets.QPushButton("载入实时视图")
        analyze_btn.setToolTip("将此分轨前 <=30s 载入实时频谱/和弦视图（会清空当前实时缓冲）")
        analyze_btn.clicked.connect(lambda: self.send_to_analysis_requested.emit(self.stem_name, self.stem_path))
        midi_btn = QtWidgets.QPushButton("转 MIDI")
        midi_btn.setObjectName("marathonPrimaryBtn")
        midi_btn.clicked.connect(lambda: self.transcribe_midi_requested.emit(self.stem_name, self.stem_path))
        row.addWidget(analyze_btn)
        row.addWidget(midi_btn)

    def apply_theme(
        self,
        appearance: Appearance,
        *,
        system_is_dark: Optional[bool] = None,
        marathon_variant: Optional[str] = None,
    ) -> None:
        if marathon_variant in ("light", "dark"):
            p = get_marathon_palette(marathon_variant)
            apply_marathon_plot_theme(self.wave_plot, appearance, marathon_variant)
            pen = pg.mkPen(p.plot_wave, width=1.1)
        else:
            apply_plot_appearance(self.wave_plot, appearance, system_is_dark=system_is_dark)
            _, _, accent = appearance.effective_colors(system_is_dark=system_is_dark)
            pen = pg.mkPen(accent, width=1.1)
        self._max_curve.setPen(pen)
        self._min_curve.setPen(pen)

    def set_waveform(self, mins: np.ndarray, maxs: np.ndarray) -> None:
        n = int(mins.shape[0])
        if self._wave_x is None or len(self._wave_x) != n:
            self._wave_x = np.arange(n, dtype=np.float32)
        self._min_curve.setData(self._wave_x, mins)
        self._max_curve.setData(self._wave_x, maxs)

    def sync_flags(self, muted: bool, solo: bool, volume: float) -> None:
        self.mute_btn.blockSignals(True)
        self.solo_btn.blockSignals(True)
        self.vol_slider.blockSignals(True)
        self.mute_btn.setChecked(muted)
        self.solo_btn.setChecked(solo)
        self.vol_slider.setValue(int(round(volume * 100)))
        self.mute_btn.blockSignals(False)
        self.solo_btn.blockSignals(False)
        self.vol_slider.blockSignals(False)


class StemMixerWidget(QtWidgets.QWidget):
    """Controls isolated AI separation progress, OOM 3-choice recovery, multi-stem playback, deep transcription, and MIDI output."""

    cancel_ai_requested = QtCore.Signal()
    oom_action_requested = QtCore.Signal(str)  # OOMRecoveryAction value
    export_mix_requested = QtCore.Signal(str)
    send_stem_to_analysis = QtCore.Signal(str, str)
    transcribe_stem_midi = QtCore.Signal(str, str)
    open_single_stem_midi_requested = QtCore.Signal(str)  # local single-stem WAV path
    before_play_requested = QtCore.Signal()
    drum_preview_requested = QtCore.Signal()
    deep_analyze_requested = QtCore.Signal(object)  # dict[stem_name, stem_path]
    export_sheet_requested = QtCore.Signal(str)     # output .md/.csv path
    save_midi_requested = QtCore.Signal(str)        # output .mid path
    metronome_overlay_toggled = QtCore.Signal(bool)
    midi_settings_requested = QtCore.Signal()
    clear_results_requested = QtCore.Signal()

    def __init__(self, mixer_engine: StemMixerEngine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.mixer_engine = mixer_engine
        self.plot_appearance = Appearance()
        self._system_is_dark: Optional[bool] = None
        self._marathon_variant: Optional[str] = None
        self._rows: dict[str, _StemTrackRow] = {}
        self._stem_paths: dict[str, str] = {}
        self._piano_roll_item: Optional[pg.BarGraphItem] = None
        self._chord_segments: list[ChordTimelineSegment] = []
        self._midi_notes: list[MidiNoteCandidate] = []
        self._piano_roll_max_sec: float = 0.0
        self._transpose_semitones: int = 0
        self._last_deep_report: Optional[StemDeepAnalysisReport] = None
        self._last_single_stem_dir: str = ""
        self._last_midi_stem_name: str = ""
        self._cached_time_txt: str = ""
        self._cached_hud_txt: str = ""

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(7)

        root.addWidget(TelemetryHeader("STEM WORKSTATION // MIX & MIDI", "分轨混音 · 深度扒谱 · MIDI 转录"))

        # AI Job status & progress bar
        job_box = QtWidgets.QGroupBox("AI SEPARATION // 分轨任务队列")
        job_l = QtWidgets.QHBoxLayout(job_box)
        self.job_status_lbl = QtWidgets.QLabel("空闲：请在下方 120s 历史时间轴选择片段并启动 2-Stem 或 4-Stem 分轨")
        self.job_status_lbl.setWordWrap(True)
        self.job_progress = QtWidgets.QProgressBar()
        self.job_progress.setRange(0, 100)
        self.job_progress.setValue(0)
        self.job_progress.setFixedWidth(200)
        self.cancel_btn = QtWidgets.QPushButton("取消任务")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_ai_requested.emit)
        job_l.addWidget(self.job_status_lbl, 1)
        job_l.addWidget(self.job_progress)
        job_l.addWidget(self.cancel_btn)
        root.addWidget(job_box)

        # OOM Recovery Choice Banner (hidden unless OOM occurs)
        self.oom_banner = QtWidgets.QGroupBox("[GUARDRAIL] 显存 / 内存不足 (GPU OOM) 恢复选项")
        self.oom_banner.setObjectName("oomBanner")
        oom_l = QtWidgets.QHBoxLayout(self.oom_banner)
        self.oom_msg_lbl = QtWidgets.QLabel("分离触发 OOM，已安全清理残留内存与临时文件，请选择处理方式：")
        self.oom_msg_lbl.setWordWrap(True)
        oom_l.addWidget(self.oom_msg_lbl, 1)

        btn_seg = QtWidgets.QPushButton("1. 降低 segment 重试")
        btn_seg.clicked.connect(lambda: self.oom_action_requested.emit(OOMRecoveryAction.REDUCE_SEGMENT.value))
        btn_light = QtWidgets.QPushButton("2. 切换轻量 2-Stem 模型")
        btn_light.clicked.connect(lambda: self.oom_action_requested.emit(OOMRecoveryAction.LIGHTER_MODEL.value))
        btn_cpu = QtWidgets.QPushButton("3. 改用 CPU fallback")
        btn_cpu.clicked.connect(lambda: self.oom_action_requested.emit(OOMRecoveryAction.CPU_FALLBACK.value))
        for b in (btn_seg, btn_light, btn_cpu):
            oom_l.addWidget(b)
        self.oom_banner.setVisible(False)
        root.addWidget(self.oom_banner)

        # Transport, Presets & Deep Analysis bar
        ctrl_bar = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("播放分轨")
        self.pause_btn = QtWidgets.QPushButton("暂停")
        self.stop_btn = QtWidgets.QPushButton("停止")
        self.loop_chk = QtWidgets.QCheckBox("循环")
        self.loop_chk.setChecked(True)
        self.loop_chk.toggled.connect(self.mixer_engine.set_loop)

        self.export_btn = QtWidgets.QPushButton("导出混合 WAV")
        self.export_btn.setToolTip("流式导出当前分轨混音 WAV；若已设定局部循环、不变调倍速或随播节拍器将同步应用到导出结果")
        self.deep_analyze_btn = QtWidgets.QPushButton("分析和弦与节奏")
        self.deep_analyze_btn.setObjectName("analysisAction")
        self.deep_analyze_btn.setEnabled(False)
        self.sevenths_chk = QtWidgets.QCheckBox("扩展和弦 (maj7/m7/7/sus4)")
        self.sevenths_chk.setToolTip("离线深度分轨和声识别是否启用 7 和弦与 sus4 模板（实时视图仍保持 12 大/小三和弦标准）")
        self.export_sheet_btn = QtWidgets.QPushButton("导出扒谱报告")
        self.export_sheet_btn.setEnabled(False)
        self.open_stem_midi_btn = QtWidgets.QPushButton("打开单轨 WAV…")
        self.open_stem_midi_btn.setToolTip(
            "从任意目录选择已有单轨 WAV (如上一轮导出的 bass.wav) 直接载入混音器，并通过独立 Python 3.11 Basic Pitch 转录与导出 MIDI；不中断当前实时捕获"
        )

        self.play_btn.clicked.connect(self._on_play_clicked)
        self.pause_btn.clicked.connect(self.mixer_engine.pause)
        self.stop_btn.clicked.connect(self.mixer_engine.stop)
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.deep_analyze_btn.clicked.connect(self._on_deep_analyze_clicked)
        self.export_sheet_btn.clicked.connect(self._on_export_sheet_clicked)
        self.open_stem_midi_btn.clicked.connect(self._on_open_single_stem_clicked)

        ctrl_bar.addWidget(self.play_btn)
        ctrl_bar.addWidget(self.pause_btn)
        ctrl_bar.addWidget(self.stop_btn)
        ctrl_bar.addWidget(self.loop_chk)
        ctrl_bar.addWidget(self.export_btn)
        ctrl_bar.addStretch(1)
        self.clear_results_btn = QtWidgets.QPushButton("清除分轨结果")
        self.clear_results_btn.setToolTip("清空当前音轨、分析和 MIDI 预览，保留原音频和已导出的文件。")
        self.clear_results_btn.setEnabled(False)
        self.clear_results_btn.clicked.connect(self.clear_results_requested.emit)
        ctrl_bar.addWidget(self.clear_results_btn)
        root.addLayout(ctrl_bar)

        monitor_bar = QtWidgets.QHBoxLayout()
        monitor_bar.addWidget(QtWidgets.QLabel("监听"))

        presets = [
            ("全部", "all"),
            ("纯伴奏", "instrumental_mix"),
            ("仅人声", "vocals_only"),
            ("仅贝斯", "bass_only"),
            ("仅鼓组", "drums_only"),
            ("仅其他", "other_only"),
        ]
        self._preset_buttons = {}
        for label, key in presets:
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            monitor_bar.addWidget(b)
            self._preset_buttons[key] = b
        self.bass_monitor_boost_chk = QtWidgets.QCheckBox(f"贝斯独听 +{BASS_MONITOR_BOOST_DB} dB")
        self.bass_monitor_boost_chk.setChecked(True)
        self.bass_monitor_boost_chk.setToolTip("仅在播放且贝斯是唯一出声的轨道时生效。可关闭以回到原电平，导出不受影响。")
        self.bass_monitor_boost_chk.toggled.connect(self.mixer_engine.set_bass_monitor_boost)
        monitor_bar.addWidget(self.bass_monitor_boost_chk)
        self._sync_preset_availability(())
        monitor_bar.addStretch(1)
        root.addLayout(monitor_bar)

        # Practice toolbar: pitch-preserving speed, sub-region chord loop & live chord HUD
        practice_bar = QtWidgets.QHBoxLayout()
        practice_bar.addWidget(QtWidgets.QLabel("不变调倍速:"))
        self.speed_combo = QtWidgets.QComboBox()
        for label, val in [("0.5x (半速扒谱)", 0.5), ("0.65x", 0.65), ("0.75x", 0.75), ("0.85x", 0.85), ("1.0x (原速)", 1.0), ("1.25x", 1.25)]:
            self.speed_combo.addItem(label, val)
        self.speed_combo.setCurrentIndex(4)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self.loop_chord_btn = QtWidgets.QPushButton("循环选中和弦段")
        self.loop_chord_btn.setEnabled(False)
        self.loop_chord_btn.clicked.connect(self._on_loop_selected_chord)

        self.clear_subloop_btn = QtWidgets.QPushButton("取消局部循环")
        self.clear_subloop_btn.setEnabled(False)
        self.clear_subloop_btn.clicked.connect(self._on_clear_subloop)

        self.metronome_chk = QtWidgets.QCheckBox("随播节拍器")
        self.metronome_chk.setToolTip("与混音回放（含 0.5x–1.25x 变速练习）同步叠加纯 CPU 节拍器")
        self.metronome_chk.toggled.connect(self.metronome_overlay_toggled.emit)

        self.subloop_badge_lbl = QtWidgets.QLabel("循环范围: 全曲")
        self.subloop_badge_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.subloop_badge_lbl, "info")

        self.live_chord_hud_lbl = QtWidgets.QLabel("实时和弦追踪: -")
        self.live_chord_hud_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.live_chord_hud_lbl, "info")

        practice_bar.addWidget(self.speed_combo)
        practice_bar.addWidget(
            HelpBadge(
                "不变调倍速 (WSOLA)",
                "使用纯 CPU 时域波形相似重叠 (WSOLA) 算法放慢或加快分轨速度，同时保持歌曲音高完全不变，便于听清快句或贝斯走音。",
            )
        )
        practice_bar.addWidget(self.loop_chord_btn)
        practice_bar.addWidget(self.clear_subloop_btn)
        practice_bar.addWidget(self.metronome_chk)
        practice_bar.addWidget(self.subloop_badge_lbl)
        practice_bar.addWidget(self.live_chord_hud_lbl, 1)
        root.addLayout(practice_bar)

        # Timeline Scrubber bar
        scrub_bar = QtWidgets.QHBoxLayout()
        scrub_bar.addWidget(QtWidgets.QLabel("进度:"))
        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.valueChanged.connect(self._on_seek_value_changed)
        self.time_lbl = QtWidgets.QLabel("00:00.0 / 00:00.0")
        self.time_lbl.setObjectName("monoTelemetry")
        self.time_lbl.setMinimumWidth(115)
        scrub_bar.addWidget(self.seek_slider, 1)
        scrub_bar.addWidget(self.time_lbl)
        root.addLayout(scrub_bar)

        # Splitter between Stem tracks and Deep Analysis + Piano Roll + MIDI Table tabs
        self._workspace_splitter = splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self._track_scroll = scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(115)
        self._tracks_container = QtWidgets.QWidget()
        self._tracks_layout = QtWidgets.QVBoxLayout(self._tracks_container)
        self._tracks_layout.setSpacing(6)
        self._tracks_layout.addStretch(1)
        scroll.setWidget(self._tracks_container)
        splitter.addWidget(scroll)

        self.analysis_tabs = QtWidgets.QTabWidget()
        self.analysis_tabs.setMinimumHeight(212)

        # Sub-tab 1: Deep Stem Arrangement & Chord Progression Timeline (non-destructive CPU analysis)
        deep_tab = QtWidgets.QWidget()
        deep_l = QtWidgets.QVBoxLayout(deep_tab)
        deep_l.setContentsMargins(6, 3, 6, 2)
        deep_l.setSpacing(3)
        analysis_actions = QtWidgets.QHBoxLayout()
        for control in (self.deep_analyze_btn, self.sevenths_chk):
            analysis_actions.addWidget(control)
        analysis_actions.addWidget(
            HelpBadge(
                "离线深度和弦、贝斯与鼓点分析",
                "结合分轨和声、YIN 贝斯低音基频探测（输出最低音名、精确 MIDI 编号与转调警告）及鼓点瞬态检测。\n勾选「扩展和弦」可额外匹配 maj7/m7/7/sus4。",
            )
        )
        analysis_actions.addWidget(self.export_sheet_btn)
        analysis_actions.addStretch(1)
        deep_l.addLayout(analysis_actions)
        self.deep_summary_lbl = QtWidgets.QLabel(
            "分轨完成后，可在这里分析和弦、调性、贝斯音符和鼓点。"
        )
        self.deep_summary_lbl.setWordWrap(True)
        self.deep_summary_lbl.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        self.deep_summary_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.deep_summary_lbl, "info")
        self.chord_timeline_table = QtWidgets.QTableWidget(0, 6)
        self.chord_timeline_table.setMinimumHeight(48)
        self.chord_timeline_table.setHorizontalHeaderLabels(
            ["开始 (s)", "结束 (s)", "和弦候选", "第二候选", "相关度", "稳定度"]
        )
        self.chord_timeline_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.chord_timeline_table.horizontalHeader().setStretchLastSection(True)
        self.chord_timeline_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chord_timeline_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.chord_timeline_table.cellClicked.connect(self._on_chord_row_clicked)
        deep_l.addWidget(self.deep_summary_lbl)
        deep_l.addWidget(self.chord_timeline_table, 1)
        self.analysis_tabs.addTab(deep_tab, "// 01 和弦与节奏")

        # Sub-tab 2: Piano Roll (PyQtGraph horizontal bar visualizer + synchronized playhead cursor + click-to-seek)
        pr_tab = QtWidgets.QWidget()
        pr_l = QtWidgets.QVBoxLayout(pr_tab)
        self.piano_roll_plot = pg.PlotWidget(title="PIANO ROLL // MIDI 钢琴卷帘预览 (单击可跳转播放)")
        self.piano_roll_plot.setBackground("#F8FAFC")
        self.piano_roll_plot.showGrid(x=True, y=True, alpha=0.22)
        self.piano_roll_plot.setLabel("bottom", "Time", units="s")
        self.piano_roll_plot.setLabel("left", "Pitch")
        self._piano_roll_cursor = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#EF4444", width=1.6),
        )
        self._piano_roll_cursor.setVisible(False)
        self._piano_roll_cursor.setZValue(20)
        self.piano_roll_plot.addItem(self._piano_roll_cursor)
        self.piano_roll_plot.scene().sigMouseClicked.connect(self._on_piano_roll_clicked)
        pr_l.addWidget(self.piano_roll_plot)
        self.analysis_tabs.addTab(pr_tab, "// 02 MIDI 卷帘")

        # Sub-tab 3: MIDI Table + Save As
        midi_tab = QtWidgets.QWidget()
        midi_l = QtWidgets.QVBoxLayout(midi_tab)
        midi_actions = QtWidgets.QHBoxLayout()
        self.midi_info_lbl = QtWidgets.QLabel(
            "尚未转录。点轨道右侧「转 MIDI」，或打开已有单轨 WAV。"
        )
        self.midi_info_lbl.setWordWrap(True)
        self.midi_info_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.midi_info_lbl, "info")
        self.midi_open_stem_btn = self.open_stem_midi_btn
        self.midi_settings_btn = QtWidgets.QPushButton("MIDI 环境设置")
        self.midi_settings_btn.clicked.connect(self.midi_settings_requested.emit)
        self.save_midi_btn = QtWidgets.QPushButton("另存 MIDI (.mid)")
        self.save_midi_btn.setObjectName("marathonPrimaryBtn")
        self.save_midi_btn.setEnabled(False)
        self.save_midi_btn.clicked.connect(self._on_save_midi_clicked)
        midi_actions.addWidget(self.midi_open_stem_btn)
        midi_actions.addWidget(
            HelpBadge(
                "Cubase 兼容单轨 MIDI",
                "所有导出的 MIDI 均符合标准格式 0 (480 TPB、Tick 0 插入拍号/调号/轨道名与 Controller Reset)，并自动修剪重叠音符，可直接拖入 Cubase / Nuendo。",
            )
        )
        midi_actions.addWidget(self.midi_settings_btn)
        midi_actions.addStretch(1)
        midi_actions.addWidget(self.save_midi_btn)
        midi_l.addLayout(midi_actions)
        midi_l.addWidget(self.midi_info_lbl)

        self.midi_table = QtWidgets.QTableWidget(0, 5)
        self.midi_table.setHorizontalHeaderLabels(["音符", "MIDI 编号", "开始 (s)", "结束 (s)", "力度"])
        self.midi_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.midi_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.midi_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.midi_table.cellClicked.connect(self._on_midi_row_clicked)
        midi_l.addWidget(self.midi_table)
        self.analysis_tabs.addTab(midi_tab, "// 03 MIDI 音符")

        rhythm_tab = QtWidgets.QWidget()
        rhythm_layout = QtWidgets.QVBoxLayout(rhythm_tab)
        self.rhythm_status = QtWidgets.QLabel("分析含独立鼓轨的分轨结果后，这里会显示 16 步鼓点。")
        self.rhythm_status.setWordWrap(True)
        rhythm_header = QtWidgets.QHBoxLayout()
        rhythm_header.addWidget(self.rhythm_status, 1)
        self.preview_drums_btn = QtWidgets.QPushButton("试听鼓点")
        self.preview_drums_btn.setToolTip("从第一个检测到的鼓点开始，试听最多 8 秒合成鼓音。")
        self.preview_drums_btn.setEnabled(False)
        self.preview_drums_btn.clicked.connect(self.drum_preview_requested.emit)
        rhythm_header.addWidget(self.preview_drums_btn)
        self.export_drums_btn = QtWidgets.QPushButton("导出鼓点 MIDI")
        self.export_drums_btn.setObjectName("marathonPrimaryBtn")
        self.export_drums_btn.setEnabled(False)
        self.export_drums_btn.setToolTip("导出检测到的底鼓、军鼓和踩镲，保留原片段中的击打时间，可直接拖入 Cubase。")
        self.export_drums_btn.clicked.connect(self._on_export_drums_clicked)
        rhythm_header.addWidget(self.export_drums_btn)
        rhythm_layout.addLayout(rhythm_header)
        self.rhythm_table = QtWidgets.QTableWidget(3, 16)
        self.rhythm_table.setAccessibleName("16 步鼓点网格")
        self.rhythm_table.setVerticalHeaderLabels(["底鼓", "军鼓", "踩镲"])
        self.rhythm_table.setHorizontalHeaderLabels([str(step) for step in range(1, 17)])
        self.rhythm_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.rhythm_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        rhythm_layout.addWidget(self.rhythm_table)
        self.analysis_tabs.addTab(rhythm_tab, "// 04 16 步鼓点")

        splitter.addWidget(self.analysis_tabs)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 220])
        root.addWidget(splitter, 1)

    def apply_workspace_layout(self, layout: str) -> None:
        splitter = self._workspace_splitter
        orientation = QtCore.Qt.Orientation
        splitter.setOrientation(orientation.Vertical if layout == "workbench" else orientation.Horizontal)
        first = self.analysis_tabs if layout == "practice" else self._track_scroll
        if splitter.widget(0) is not first:
            splitter.insertWidget(0, first)
        splitter.setSizes({
            "workbench": [220, 240],
            "split": [640, 490],
            "practice": [630, 500],
        }[layout])

    def apply_theme(
        self,
        appearance: Appearance,
        *,
        system_is_dark: Optional[bool] = None,
        marathon_variant: Optional[str] = None,
    ) -> None:
        self.plot_appearance = appearance
        self._system_is_dark = system_is_dark
        self._marathon_variant = marathon_variant
        for row in self._rows.values():
            row.apply_theme(appearance, system_is_dark=system_is_dark, marathon_variant=marathon_variant)
        if marathon_variant in ("light", "dark"):
            p = get_marathon_palette(marathon_variant)
            apply_marathon_plot_theme(self.piano_roll_plot, appearance, marathon_variant)
            self._piano_roll_cursor.setPen(pg.mkPen(p.plot_pr_cursor, width=1.6))
            if self._piano_roll_item is not None:
                self._piano_roll_item.setOpts(brush=p.accent, pen=pg.mkPen(p.accent_strong, width=0.8))
            dot_color = QtGui.QColor(p.accent)
        else:
            apply_plot_appearance(self.piano_roll_plot, appearance, system_is_dark=system_is_dark)
            mode = appearance.resolve_theme_mode(system_is_dark=system_is_dark)
            _, _, accent = appearance.effective_colors(system_is_dark=system_is_dark)
            self._piano_roll_cursor.setPen(pg.mkPen("#DC2626" if mode == "light" else "#FF6B6B", width=1.6))
            if self._piano_roll_item is not None:
                self._piano_roll_item.setOpts(brush=accent, pen=pg.mkPen(accent, width=0.8))
            dot_color = QtGui.QColor(accent)
        for r in range(self.rhythm_table.rowCount()):
            for c in range(self.rhythm_table.columnCount()):
                item = self.rhythm_table.item(r, c)
                if item is not None:
                    item.setForeground(dot_color)

    @property
    def include_sevenths(self) -> bool:
        return bool(self.sevenths_chk.isChecked())

    def set_transpose_semitones(self, semitones: int) -> None:
        self._transpose_semitones = int(semitones)
        if self._last_deep_report is not None:
            self.display_deep_analysis(self._last_deep_report)
        else:
            self.sync_playback_position()

    def _tr_chord(self, chord: str) -> str:
        return transpose_chord_symbol(chord, self._transpose_semitones) if self._transpose_semitones != 0 else chord

    def _tr_key(self, key: str) -> str:
        return transpose_key_label(key, self._transpose_semitones) if self._transpose_semitones != 0 else key

    def _tr_note(self, note: str) -> str:
        return transpose_note_name(note, self._transpose_semitones) if self._transpose_semitones != 0 else note

    def _on_play_clicked(self) -> None:
        self.before_play_requested.emit()
        self.mixer_engine.play(open_audio_device=True)

    def _on_speed_changed(self) -> None:
        speed = float(self.speed_combo.currentData() or 1.0)
        self.mixer_engine.set_speed(speed)

    def _on_loop_selected_chord(self) -> None:
        if not self._chord_segments or self.mixer_engine.max_frames <= 0:
            return
        row = self.chord_timeline_table.currentRow()
        if row < 0 or row >= len(self._chord_segments):
            row = 0
        seg = self._chord_segments[row]
        s_sec, e_sec = self.mixer_engine.set_loop_region(seg.start_sec, seg.end_sec)
        self.loop_chk.blockSignals(True)
        self.loop_chk.setChecked(True)
        self.loop_chk.blockSignals(False)
        self.subloop_badge_lbl.setText(f"局部循环 [{self._tr_chord(seg.chord)}]: {s_sec:.2f}s ~ {e_sec:.2f}s")
        set_widget_tone(self.subloop_badge_lbl, "ok")
        self.clear_subloop_btn.setEnabled(True)
        self.sync_playback_position()

    def _on_clear_subloop(self) -> None:
        self.mixer_engine.clear_loop_region()
        self.subloop_badge_lbl.setText("循环范围: 全曲")
        set_widget_tone(self.subloop_badge_lbl, "info")
        self.clear_subloop_btn.setEnabled(False)

    def sync_metronome_ui(self, enabled: bool) -> None:
        self.metronome_chk.blockSignals(True)
        self.metronome_chk.setChecked(bool(enabled))
        self.metronome_chk.blockSignals(False)

    def _on_seek_released(self) -> None:
        max_f = self.mixer_engine.max_frames
        if max_f > 0:
            target = int(round((self.seek_slider.value() / 1000.0) * max_f))
            self.mixer_engine.seek(target)
            self.sync_playback_position()

    def _on_seek_value_changed(self, value: int) -> None:
        if self.seek_slider.isSliderDown():
            max_f = self.mixer_engine.max_frames
            if max_f > 0:
                target = int(round((value / 1000.0) * max_f))
                self.mixer_engine.seek(target)
                self.sync_playback_position()

    def _seek_to_sec(self, start_sec: float) -> None:
        sr = max(1, self.mixer_engine.sample_rate)
        target = int(round(max(0.0, float(start_sec)) * sr))
        self.mixer_engine.seek(target)
        self.sync_playback_position()

    def _on_piano_roll_clicked(self, event) -> None:
        if event is None or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        vb = self.piano_roll_plot.getPlotItem().getViewBox()
        if vb is None:
            return
        scene_pos = event.scenePos()
        if not vb.sceneBoundingRect().contains(scene_pos):
            return
        view_pt = vb.mapSceneToView(scene_pos)
        dur = max(self.mixer_engine.total_duration_sec, self._piano_roll_max_sec)
        if dur <= 0.0:
            return
        target_sec = max(0.0, min(dur, float(view_pt.x())))
        self._seek_to_sec(target_sec)

    @QtCore.Slot(int, int)
    def _on_chord_row_clicked(self, row: int, _col: int) -> None:
        item = self.chord_timeline_table.item(row, 0)
        if item is None:
            return
        try:
            self._seek_to_sec(float(item.text()))
        except ValueError:
            pass

    @QtCore.Slot(int, int)
    def _on_midi_row_clicked(self, row: int, _col: int) -> None:
        item = self.midi_table.item(row, 2)
        if item is None:
            return
        try:
            self._seek_to_sec(float(item.text()))
        except ValueError:
            pass

    def sync_playback_position(self) -> None:
        dur = self.mixer_engine.total_duration_sec
        pos = self.mixer_engine.position_sec
        t_txt = f"{_fmt_sec(pos)} / {_fmt_sec(dur)}"
        if t_txt != self._cached_time_txt:
            self._cached_time_txt = t_txt
            self.time_lbl.setText(t_txt)
        if self._piano_roll_item is not None:
            self._piano_roll_cursor.setValue(pos)
            if not self._piano_roll_cursor.isVisible():
                self._piano_roll_cursor.setVisible(True)
        if not self.seek_slider.isSliderDown():
            val = int(round((pos / dur) * 1000.0)) if dur > 1e-6 else 0
            clamped_val = max(0, min(1000, val))
            if self.seek_slider.value() != clamped_val:
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(clamped_val)
                self.seek_slider.blockSignals(False)

        subloop = self.mixer_engine.loop_region_sec
        if subloop is None and self.clear_subloop_btn.isEnabled():
            self.subloop_badge_lbl.setText("循环范围: 全曲")
            set_widget_tone(self.subloop_badge_lbl, "info")
            self.clear_subloop_btn.setEnabled(False)

        # Live active/next chord HUD & table row sync
        if self._chord_segments:
            active_idx = -1
            for idx, seg in enumerate(self._chord_segments):
                if seg.start_sec - 1e-4 <= pos < seg.end_sec:
                    active_idx = idx
                    break
            if active_idx == -1 and pos >= self._chord_segments[-1].start_sec - 1e-4:
                active_idx = len(self._chord_segments) - 1
            if 0 <= active_idx < len(self._chord_segments):
                cur = self._chord_segments[active_idx]
                cur_chord = self._tr_chord(cur.chord)
                tones = spell_chord_tones(cur_chord)
                cur_disp = f"{cur_chord} ({tones})" if tones != "-" else cur_chord
                nxt = (
                    self._tr_chord(self._chord_segments[active_idx + 1].chord)
                    if active_idx + 1 < len(self._chord_segments)
                    else "结束"
                )
                hud_txt = f"当前和弦: {cur_disp}  |  下一和弦: {nxt}"
                if hud_txt != self._cached_hud_txt:
                    self._cached_hud_txt = hud_txt
                    self.live_chord_hud_lbl.setText(hud_txt)
                    set_widget_tone(self.live_chord_hud_lbl, "ok")
                if self.mixer_engine.is_playing and self.chord_timeline_table.currentRow() != active_idx:
                    self.chord_timeline_table.blockSignals(True)
                    self.chord_timeline_table.selectRow(active_idx)
                    self.chord_timeline_table.blockSignals(False)

        # Highlight sounding MIDI note during active playback
        if self._midi_notes and self.mixer_engine.is_playing:
            note_idx = -1
            for idx, n in enumerate(self._midi_notes):
                if n.start_sec - 1e-4 <= pos <= n.end_sec:
                    note_idx = idx
                    break
            if 0 <= note_idx < self.midi_table.rowCount() and self.midi_table.currentRow() != note_idx:
                self.midi_table.blockSignals(True)
                self.midi_table.selectRow(note_idx)
                self.midi_table.blockSignals(False)

    def _on_export_clicked(self) -> None:
        from core.paths import default_export_dir

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出混合音轨 WAV",
            str(default_export_dir() / "listenscope_mix.wav"),
            "WAV Audio (*.wav)",
        )
        if file_path:
            self.export_mix_requested.emit(file_path)

    def _on_deep_analyze_clicked(self) -> None:
        if self._stem_paths:
            self.deep_analyze_requested.emit(dict(self._stem_paths))

    def _on_export_sheet_clicked(self) -> None:
        from core.paths import default_export_dir

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出扒谱与分析报告",
            str(default_export_dir() / "listenscope_transcription.md"),
            "Markdown 报告 (*.md);;CSV 明细表 (*.csv)",
        )
        if file_path:
            self.export_sheet_requested.emit(file_path)

    def _on_open_single_stem_clicked(self) -> None:
        from core.paths import default_export_dir

        start_dir = self._last_single_stem_dir or str(default_export_dir())
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "打开已有单轨 WAV 进行 MIDI 转录 (如 bass.wav)",
            start_dir,
            "WAV Audio (*.wav);;All Files (*)",
        )
        if file_path:
            self._last_single_stem_dir = str(Path(file_path).parent)
            self.open_single_stem_midi_requested.emit(file_path)

    def set_drum_preview_playing(self, playing: bool) -> None:
        self.preview_drums_btn.setText("停止试听" if playing else "试听鼓点")

    def _on_export_drums_clicked(self) -> None:
        from core.paths import default_export_dir

        report = self._last_deep_report
        if report is None or report.drums is None:
            return
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出鼓点 MIDI", str(default_export_dir() / "listenscope_drums.mid"),
            "MIDI 文件 (*.mid *.midi)",
        )
        if not selected or self._last_deep_report is not report:
            return
        destination = Path(selected)
        if not destination.suffix:
            destination = destination.with_suffix(".mid")
        try:
            count = export_drum_midi(report.drums, destination)
        except (OSError, ValueError) as exc:
            self.rhythm_status.setText(f"导出鼓点 MIDI 失败：{exc}")
            return
        self.rhythm_status.setText(f"已导出 {count} 个鼓点至 {destination.name}。")

    def _on_save_midi_clicked(self) -> None:
        from core.paths import default_export_dir

        stem_base = (self._last_midi_stem_name or "listenscope_stem").strip() or "listenscope_stem"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "另存转录 MIDI 文件",
            str(default_export_dir() / f"{stem_base}.mid"),
            "MIDI File (*.mid)",
        )
        if file_path:
            self.save_midi_requested.emit(file_path)

    def set_midi_transcribing(self, stem_name: str, midi_python: str = "") -> None:
        self.analysis_tabs.setCurrentIndex(2)
        self._last_midi_stem_name = stem_name or "listenscope_stem"
        self.save_midi_btn.setEnabled(False)
        set_widget_tone(self.midi_info_lbl, "info")
        if midi_python and Path(midi_python).exists():
            self.midi_info_lbl.setText(
                f"[BUSY] 正在通过独立 MIDI 解释器 ({midi_python}) 对 `{self._last_midi_stem_name}` 执行 Spotify Basic Pitch CPU 转录..."
            )
        else:
            self.midi_info_lbl.setText(
                f"正在对 {self._last_midi_stem_name} 使用轻量转录。配置独立环境后可用 Basic Pitch。"
            )

    def set_midi_error(self, message: str) -> None:
        self.save_midi_btn.setEnabled(False)
        set_widget_tone(self.midi_info_lbl, "error")
        self.midi_info_lbl.setText(f"[ERR] {message}")

    def _sync_preset_availability(self, track_names) -> None:
        names = {name.lower() for name in track_names}
        self.bass_monitor_boost_chk.setEnabled("bass" in names)
        for key, button in self._preset_buttons.items():
            if key.endswith("_only"):
                available = key.removesuffix("_only") in names
            elif key == "instrumental_mix":
                available = "instrumental" in names or ("vocals" in names and len(names) > 1)
            else:
                available = bool(names)
            button.setEnabled(available)
            button.setToolTip("" if available else "当前分轨结果没有此预设需要的音轨")

    def _apply_preset(self, preset: str) -> None:
        self.mixer_engine.apply_preset(preset)
        for name, track in self.mixer_engine.tracks.items():
            row = self._rows.get(name)
            if row is not None:
                row.sync_flags(track.muted, track.solo, track.volume)

    def update_ai_progress(self, prog: AIJobProgress) -> None:
        running = prog.state in (
            AIJobState.PREPARING,
            AIJobState.LOADING_MODEL,
            AIJobState.INFERRING,
            AIJobState.WRITING,
        )
        self.cancel_btn.setEnabled(running)
        self.clear_results_btn.setEnabled(bool(self._rows) and not running)
        self.job_progress.setValue(int(round(prog.progress * 100)))
        self.job_status_lbl.setText(f"[{prog.state.value}] {prog.message}")
        if running:
            self.oom_banner.setVisible(False)

    def handle_ai_result(self, res: AIJobResult) -> None:
        self.cancel_btn.setEnabled(False)
        self.clear_results_btn.setEnabled(bool(self._rows))
        if res.state == AIJobState.COMPLETED:
            self.job_progress.setValue(100)
            self.job_status_lbl.setText(
                f"[OK] 分轨完成 ({res.model_id} | {res.device_used} | 用时 {res.elapsed_sec:.2f}s | 峰值 Worker RAM={res.peak_ram_mb:.1f} MB)"
            )
            self.oom_banner.setVisible(False)
            self.load_stem_paths(res.stem_paths)
        elif res.state == AIJobState.OOM_ERROR:
            self.job_progress.setValue(0)
            self.job_status_lbl.setText(f"[WARN] GPU OOM: {res.error}")
            self.oom_msg_lbl.setText(res.error or "显存/内存不足，请选择安全恢复策略：")
            self.oom_banner.setVisible(True)
        else:
            self.job_progress.setValue(0)
            self.job_status_lbl.setText(f"[{res.state.value}] {res.error or '已停止'}")

    def clear_results(self) -> None:
        self.load_stem_paths({})
        self.job_progress.setValue(0)
        self.job_status_lbl.setText("分轨结果已清除。可在历史时间轴重新选择片段。")

    def load_stem_paths(self, stem_paths: dict[str, str]) -> None:
        for row in self._rows.values():
            self._tracks_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._stem_paths = dict(stem_paths)
        self._chord_segments.clear()
        self._midi_notes.clear()
        self._last_deep_report = None
        self._last_midi_stem_name = ""
        self._piano_roll_max_sec = 0.0
        self._cached_time_txt = ""
        self._cached_hud_txt = ""

        if self._piano_roll_item is not None:
            self.piano_roll_plot.removeItem(self._piano_roll_item)
            self._piano_roll_item = None
        self.piano_roll_plot.setTitle("PIANO ROLL // MIDI 钢琴卷帘预览 (单击可跳转播放)")
        self.midi_table.setRowCount(0)
        self.rhythm_table.clearContents()
        self.export_drums_btn.setEnabled(False)
        self.preview_drums_btn.setEnabled(False)
        self.set_drum_preview_playing(False)
        self.rhythm_status.setText("分析含独立鼓轨的分轨结果后，这里会显示 16 步鼓点。")
        set_widget_tone(self.midi_info_lbl, "info")
        self.midi_info_lbl.setText(
            "尚未转录。点轨道右侧「转 MIDI」，或打开已有单轨 WAV。"
        )
        self.save_midi_btn.setEnabled(False)
        self.loop_chord_btn.setEnabled(False)
        self.clear_subloop_btn.setEnabled(False)
        self.subloop_badge_lbl.setText("循环范围: 全曲")
        set_widget_tone(self.subloop_badge_lbl, "info")
        self.live_chord_hud_lbl.setText("实时和弦追踪: -")
        set_widget_tone(self.live_chord_hud_lbl, "info")

        tracks = self.mixer_engine.load_stems(stem_paths)
        self._sync_preset_availability(tracks)
        self.deep_analyze_btn.setEnabled(bool(tracks))
        self.clear_results_btn.setEnabled(bool(tracks))
        self.export_sheet_btn.setEnabled(False)
        self.chord_timeline_table.setRowCount(0)
        self.analysis_tabs.setCurrentIndex(0)
        set_widget_tone(self.deep_summary_lbl, "info")
        self.deep_summary_lbl.setText(
            "点「分析和弦与节奏」生成和弦时间轴、贝斯音符和鼓点。"
            if tracks else "分轨完成后，可在这里分析和弦、调性、贝斯音符和鼓点。"
        )
        self._piano_roll_cursor.setVisible(False)
        self.sync_playback_position()

        for name, state in tracks.items():
            row = _StemTrackRow(name, str(state.path), state.duration_sec)
            row.apply_theme(
                self.plot_appearance,
                system_is_dark=self._system_is_dark,
                marathon_variant=self._marathon_variant,
            )
            mins, maxs = self.mixer_engine.get_stem_waveform_envelope(name)
            row.set_waveform(mins, maxs)
            row.mute_changed.connect(self.mixer_engine.set_mute)
            row.solo_changed.connect(self.mixer_engine.set_solo)
            row.volume_changed.connect(self.mixer_engine.set_volume)
            row.send_to_analysis_requested.connect(self.send_stem_to_analysis.emit)
            row.transcribe_midi_requested.connect(self.transcribe_stem_midi.emit)
            self._tracks_layout.insertWidget(self._tracks_layout.count() - 1, row)
            self._rows[name] = row

    def display_deep_analysis(self, report: StemDeepAnalysisReport) -> None:
        same_report = self._last_deep_report is report
        prev_row = self.chord_timeline_table.currentRow()
        self._last_deep_report = report
        bpm_txt = f"{report.estimated_bpm.bpm:.1f} ({report.estimated_bpm.stability})" if report.estimated_bpm.bpm else "Unknown"
        key_p = self._tr_key(report.estimated_key.primary)
        key_s = self._tr_key(report.estimated_key.secondary)
        tr_tag = f" | 移调={self._transpose_semitones:+d}" if self._transpose_semitones != 0 else ""
        parts = [
            f"调性: {key_p} (候选: {key_s}, {report.estimated_key.stability}{tr_tag}) | BPM: {bpm_txt} | 和声源: {report.harmonic_source_label}"
        ]
        mod_flags: list[str] = []
        if report.estimated_key.modulation_hint:
            mod_flags.append("全局调性波动/可能转调")
        if report.bass is None:
            parts.append("贝斯 · 缺少独立贝斯轨")
        elif not report.bass.notes:
            state = "低于静音门限" if report.bass.signal_detected is False else "没有足够稳定的音符"
            parts.append(f"贝斯 · {state}")
        else:
            low_raw = report.bass.lowest_note or "-"
            high_raw = report.bass.highest_note or "-"
            low_b = self._tr_note(low_raw) or "-"
            high_b = self._tr_note(high_raw) or "-"
            low_midi = report.bass.lowest_midi
            high_midi = report.bass.highest_midi
            if low_midi is not None and self._transpose_semitones != 0:
                trans_low_midi = max(0, min(127, low_midi + self._transpose_semitones))
                midi_low_txt = f"MIDI {trans_low_midi} · 实音 {low_raw} MIDI {low_midi}"
            elif low_midi is not None:
                midi_low_txt = f"MIDI {low_midi}"
            else:
                midi_low_txt = ""
            freq_txt = f"{report.bass.lowest_freq_hz:.1f}Hz" if report.bass.lowest_freq_hz is not None else ""
            time_txt = f"@{report.bass.lowest_note_time_sec:.2f}s" if report.bass.lowest_note_time_sec is not None else ""
            low_meta = " · ".join(p for p in (midi_low_txt, freq_txt, time_txt) if p)
            low_disp = f"{low_b} ({low_meta})" if low_meta else low_b
            high_midi_txt = f"MIDI {max(0, min(127, high_midi + self._transpose_semitones))}" if high_midi is not None else ""
            high_disp = f"{high_b} ({high_midi_txt})" if high_midi_txt else high_b
            roots_b = ", ".join(self._tr_note(r) for r in report.bass.root_pitch_classes) or "-"
            if report.bass.modulation_detected:
                mod_flags.append(report.bass.modulation_note or "贝斯段内调性/最低音区发生转移")
            mod_suffix = f" | [INFO] 疑似转调: {'；'.join(mod_flags)}" if mod_flags else ""
            parts.append(
                f"贝斯: 最低 {low_disp} ~ 最高 {high_disp} | "
                f"核心根音 [{roots_b}] | 音符数={len(report.bass.notes)}{mod_suffix}"
            )
        if report.bass is None or not report.bass.notes:
            if mod_flags:
                parts.append(f"[INFO] 疑似转调: {'；'.join(mod_flags)}")

        if self._marathon_variant in ("light", "dark"):
            accent = get_marathon_palette(self._marathon_variant).accent
        else:
            _, _, accent = self.plot_appearance.effective_colors(system_is_dark=self._system_is_dark)
        if report.drums is not None:
            self.rhythm_table.clearContents()
            has_hits = bool(report.drums.kick_times_sec or report.drums.snare_times_sec or report.drums.hihat_times_sec)
            self.export_drums_btn.setEnabled(has_hits)
            self.preview_drums_btn.setEnabled(has_hits)
            self.rhythm_status.setText("16 步鼓点概览 · MIDI 保留原始击打时间。" if has_hits else "当前鼓轨未检测到鼓点。")
            for column, step in enumerate(report.drums.groove_16_step[:16]):
                for row, hit in enumerate(("K", "S", "H")):
                    if hit in step.split("+"):
                        item = QtWidgets.QTableWidgetItem("●")
                        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                        item.setForeground(QtGui.QColor(accent))
                        self.rhythm_table.setItem(row, column, item)
            parts.append(
                f"Drums: Kick={len(report.drums.kick_times_sec)} / Snare={len(report.drums.snare_times_sec)} / "
                f"HiHat={len(report.drums.hihat_times_sec)} | 16步律动: {' '.join(report.drums.groove_16_step)}"
            )
        else:
            self.rhythm_table.clearContents()
            self.export_drums_btn.setEnabled(False)
            self.preview_drums_btn.setEnabled(False)
            self.rhythm_status.setText("当前结果没有独立鼓轨。")
        if report.melody is not None:
            low_m = self._tr_note(report.melody.lowest_note) or "-"
            high_m = self._tr_note(report.melody.highest_note) or "-"
            med_m = self._tr_note(report.melody.median_note) or "-"
            parts.append(
                f"Melody ({report.melody.stem_name}): 音域 {low_m}~{high_m} "
                f"(中位 {med_m}) | 有声率={report.melody.voiced_ratio * 100:.1f}%"
            )
        set_widget_tone(self.deep_summary_lbl, "warn" if mod_flags else "info")
        self.deep_summary_lbl.setText("\n".join(parts))

        rows = list(report.chord_timeline[:400])
        self._chord_segments = rows
        self.chord_timeline_table.setRowCount(len(rows))
        for idx, seg in enumerate(rows):
            vals = [
                f"{seg.start_sec:.2f}",
                f"{seg.end_sec:.2f}",
                self._tr_chord(seg.chord),
                self._tr_chord(seg.secondary),
                f"{seg.correlation:.3f}",
                seg.stability,
            ]
            for col, text in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.chord_timeline_table.setItem(idx, col, item)

        self.loop_chord_btn.setEnabled(bool(rows))
        if rows:
            target_row = prev_row if (same_report and 0 <= prev_row < len(rows)) else 0
            self.chord_timeline_table.blockSignals(True)
            self.chord_timeline_table.selectRow(target_row)
            self.chord_timeline_table.blockSignals(False)
        self.export_sheet_btn.setEnabled(True)
        if not same_report:
            self.analysis_tabs.setCurrentIndex(0)
        self.sync_playback_position()

    def display_midi_result(self, result: MidiTranscriptionResult) -> None:
        self._last_midi_stem_name = str(result.source_stem_name or self._last_midi_stem_name or "listenscope_stem")
        backend = str(result.backend_used or "unknown")
        if backend == "basic-pitch":
            algo_desc = "Spotify Basic Pitch CPU (basic-pitch)"
            set_widget_tone(self.midi_info_lbl, "ok")
        else:
            algo_desc = f"[FALLBACK] 轻量回退算法 ({backend}，非 Spotify Basic Pitch)"
            set_widget_tone(self.midi_info_lbl, "warn")
        self.piano_roll_plot.setTitle(
            f"PIANO ROLL // {result.source_stem_name} · {algo_desc} (单击可跳转播放)"
        )
        warn = f"\n说明: {result.warning}" if result.warning else ""
        self.midi_info_lbl.setText(
            f"源音轨: {result.source_stem_name} | 实际算法: {algo_desc} | "
            f"音符数: {len(result.notes)} | 文件: {result.output_midi_path}{warn}"
        )
        if self.analysis_tabs.currentIndex() == 0:
            self.analysis_tabs.setCurrentIndex(2)
        show = list(result.notes[:250])
        self._midi_notes = show
        self.midi_table.setRowCount(len(show))
        for idx, n in enumerate(show):
            vals = [n.note_name, str(n.pitch_midi), f"{n.start_sec:.2f}", f"{n.end_sec:.2f}", str(n.velocity)]
            for col, text in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.midi_table.setItem(idx, col, item)

        # Render batched Piano Roll bars (bounded to <= 600 notes)
        if self._piano_roll_item is not None:
            self.piano_roll_plot.removeItem(self._piano_roll_item)
            self._piano_roll_item = None

        pr_notes = result.notes[:600]
        if pr_notes:
            if self._marathon_variant in ("light", "dark"):
                mp = get_marathon_palette(self._marathon_variant)
                bar_brush = mp.accent
                bar_pen = pg.mkPen(mp.accent_strong, width=0.8)
            else:
                _, _, accent = self.plot_appearance.effective_colors(system_is_dark=self._system_is_dark)
                bar_brush = accent
                bar_pen = pg.mkPen(accent, width=0.8)
            starts = np.array([float(n.start_sec) for n in pr_notes], dtype=np.float32)
            widths = np.array([max(0.04, float(n.end_sec - n.start_sec)) for n in pr_notes], dtype=np.float32)
            pitches = np.array([float(n.pitch_midi) for n in pr_notes], dtype=np.float32)
            self._piano_roll_item = pg.BarGraphItem(
                x0=starts,
                width=widths,
                y=pitches,
                height=0.72,
                brush=bar_brush,
                pen=bar_pen,
            )
            self.piano_roll_plot.addItem(self._piano_roll_item)

            lo = max(0, int(np.min(pitches)) - 2)
            hi = min(127, int(np.max(pitches)) + 2)
            self.piano_roll_plot.setYRange(lo, hi)
            ticks = [
                (m, f"{PITCH_CLASSES[m % 12]}{(m // 12) - 1}")
                for m in range(lo, hi + 1)
                if m % 2 == 0 or (hi - lo) <= 16
            ]
            self.piano_roll_plot.getAxis("left").setTicks([ticks])
            max_end = max(1.0, max(float(n.end_sec) for n in pr_notes) + 0.5)
            self._piano_roll_max_sec = max_end
            self.piano_roll_plot.setXRange(0.0, max_end)
            self._piano_roll_cursor.setValue(self.mixer_engine.position_sec)
            self._piano_roll_cursor.setVisible(True)
        else:
            self._piano_roll_max_sec = 0.0
            self._piano_roll_cursor.setVisible(False)

        self.save_midi_btn.setEnabled(result.output_midi_path is not None and Path(result.output_midi_path).exists())

