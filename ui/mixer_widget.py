"""Multi-stem synchronized mixer, OOM recovery prompt, stem analysis bridge, and Basic Pitch MIDI UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from analysis.chroma import PITCH_CLASSES
from audio.playback import StemMixerEngine
from core.models import (
    AIJobProgress,
    AIJobResult,
    AIJobState,
    MidiTranscriptionResult,
    OOMRecoveryAction,
    StemDeepAnalysisReport,
)


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
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background: #1C2026; border: 1px solid #2C323C; border-radius: 6px; }")

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        # Left column: stem label & duration
        info = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel(stem_name.upper())
        title.setStyleSheet("font-weight: 700; font-size: 13px; border: none;")
        dur_lbl = QtWidgets.QLabel(f"{duration_sec:.1f}s")
        dur_lbl.setStyleSheet("color: #9AA4B2; border: none;")
        info.addWidget(title)
        info.addWidget(dur_lbl)
        row.addLayout(info)

        # Mute / Solo / Volume
        self.mute_btn = QtWidgets.QPushButton("M")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(32)
        self.mute_btn.toggled.connect(lambda checked: self.mute_changed.emit(self.stem_name, checked))

        self.solo_btn = QtWidgets.QPushButton("S")
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
        self.wave_plot.setMaximumHeight(56)
        self.wave_plot.setMinimumHeight(46)
        self.wave_plot.setBackground("#14161A")
        self.wave_plot.setYRange(-1.0, 1.0)
        self.wave_plot.hideAxis("bottom")
        self.wave_plot.hideAxis("left")
        self.wave_plot.setMouseEnabled(x=False, y=False)
        self._max_curve = self.wave_plot.plot(pen=pg.mkPen("#7EE2B8", width=1.1))
        self._min_curve = self.wave_plot.plot(pen=pg.mkPen("#7EE2B8", width=1.1))
        row.addWidget(self.wave_plot, 1)

        # Bridge actions
        analyze_btn = QtWidgets.QPushButton("载入实时视图")
        analyze_btn.setToolTip("将此分轨前 <=30s 载入实时频谱/和弦视图（会清空当前实时缓冲）")
        analyze_btn.clicked.connect(lambda: self.send_to_analysis_requested.emit(self.stem_name, self.stem_path))
        midi_btn = QtWidgets.QPushButton("转 MIDI")
        midi_btn.clicked.connect(lambda: self.transcribe_midi_requested.emit(self.stem_name, self.stem_path))
        row.addWidget(analyze_btn)
        row.addWidget(midi_btn)

    def set_waveform(self, mins: np.ndarray, maxs: np.ndarray) -> None:
        x = np.arange(mins.shape[0], dtype=np.float32)
        self._min_curve.setData(x, mins)
        self._max_curve.setData(x, maxs)

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
    before_play_requested = QtCore.Signal()
    deep_analyze_requested = QtCore.Signal(object)  # dict[stem_name, stem_path]
    export_sheet_requested = QtCore.Signal(str)     # output .md/.csv path
    save_midi_requested = QtCore.Signal(str)        # output .mid path

    def __init__(self, mixer_engine: StemMixerEngine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.mixer_engine = mixer_engine
        self._rows: dict[str, _StemTrackRow] = {}
        self._stem_paths: dict[str, str] = {}
        self._piano_roll_item: Optional[pg.BarGraphItem] = None

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(8)

        # AI Job status & progress bar
        job_box = QtWidgets.QGroupBox("AI 音轨分离任务状态 (独立子进程串行)")
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
        self.oom_banner = QtWidgets.QGroupBox("⚠️ 显存 / 内存不足 (GPU OOM) 恢复选项")
        self.oom_banner.setStyleSheet(
            "QGroupBox { border: 1px solid #F5A623; background: #332400; border-radius: 6px; padding-top: 14px; }"
        )
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
        self.deep_analyze_btn = QtWidgets.QPushButton("深度分析分轨 (和弦/Bass/鼓/旋律)")
        self.deep_analyze_btn.setEnabled(False)
        self.sevenths_chk = QtWidgets.QCheckBox("扩展和弦 (maj7/m7/7/sus4)")
        self.sevenths_chk.setToolTip("离线深度分轨和声识别是否启用 7 和弦与 sus4 模板（实时视图仍保持 12 大/小三和弦标准）")
        self.export_sheet_btn = QtWidgets.QPushButton("导出扒谱报告")
        self.export_sheet_btn.setEnabled(False)

        self.play_btn.clicked.connect(self._on_play_clicked)
        self.pause_btn.clicked.connect(self.mixer_engine.pause)
        self.stop_btn.clicked.connect(self.mixer_engine.stop)
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.deep_analyze_btn.clicked.connect(self._on_deep_analyze_clicked)
        self.export_sheet_btn.clicked.connect(self._on_export_sheet_clicked)

        ctrl_bar.addWidget(self.play_btn)
        ctrl_bar.addWidget(self.pause_btn)
        ctrl_bar.addWidget(self.stop_btn)
        ctrl_bar.addWidget(self.loop_chk)
        ctrl_bar.addWidget(self.export_btn)
        ctrl_bar.addWidget(self.deep_analyze_btn)
        ctrl_bar.addWidget(self.sevenths_chk)
        ctrl_bar.addWidget(self.export_sheet_btn)
        ctrl_bar.addSpacing(8)

        presets = [
            ("全部", "all"),
            ("纯伴奏", "instrumental_mix"),
            ("仅人声", "vocals_only"),
            ("仅贝斯", "bass_only"),
            ("仅鼓组", "drums_only"),
            ("仅其他", "other_only"),
        ]
        for label, key in presets:
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            ctrl_bar.addWidget(b)
        ctrl_bar.addStretch(1)
        root.addLayout(ctrl_bar)

        # Timeline Scrubber bar
        scrub_bar = QtWidgets.QHBoxLayout()
        scrub_bar.addWidget(QtWidgets.QLabel("进度:"))
        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.valueChanged.connect(self._on_seek_value_changed)
        self.time_lbl = QtWidgets.QLabel("00:00.0 / 00:00.0")
        self.time_lbl.setMinimumWidth(115)
        scrub_bar.addWidget(self.seek_slider, 1)
        scrub_bar.addWidget(self.time_lbl)
        root.addLayout(scrub_bar)

        # Splitter between Stem tracks and Deep Analysis + Piano Roll + MIDI Table tabs
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self._tracks_container = QtWidgets.QWidget()
        self._tracks_layout = QtWidgets.QVBoxLayout(self._tracks_container)
        self._tracks_layout.setSpacing(6)
        self._tracks_layout.addStretch(1)
        scroll.setWidget(self._tracks_container)
        splitter.addWidget(scroll)

        self.analysis_tabs = QtWidgets.QTabWidget()

        # Sub-tab 1: Deep Stem Arrangement & Chord Progression Timeline (non-destructive CPU analysis)
        deep_tab = QtWidgets.QWidget()
        deep_l = QtWidgets.QVBoxLayout(deep_tab)
        self.deep_summary_lbl = QtWidgets.QLabel(
            "分轨完成后点击上方「深度分析分轨」：离线流式解析时间轴和弦进行、Bass 根音、鼓组 Kick/Snare/Hi-Hat 16 步律动及主旋律音域（支持点击表格行跳转混音试听位置）。"
        )
        self.deep_summary_lbl.setWordWrap(True)
        self.deep_summary_lbl.setStyleSheet(
            "padding: 8px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px;"
        )
        self.chord_timeline_table = QtWidgets.QTableWidget(0, 6)
        self.chord_timeline_table.setHorizontalHeaderLabels(
            ["开始 (s)", "结束 (s)", "和弦候选", "第二候选", "相关度", "稳定度"]
        )
        self.chord_timeline_table.horizontalHeader().setStretchLastSection(True)
        self.chord_timeline_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.chord_timeline_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.chord_timeline_table.cellClicked.connect(self._on_chord_row_clicked)
        deep_l.addWidget(self.deep_summary_lbl)
        deep_l.addWidget(self.chord_timeline_table, 1)
        self.analysis_tabs.addTab(deep_tab, "和弦进行 & Bass/鼓/旋律深度分析")

        # Sub-tab 2: Piano Roll (PyQtGraph horizontal bar visualizer + synchronized playhead cursor)
        pr_tab = QtWidgets.QWidget()
        pr_l = QtWidgets.QVBoxLayout(pr_tab)
        self.piano_roll_plot = pg.PlotWidget(title="MIDI 钢琴卷帘预览 (Pitch vs Time)")
        self.piano_roll_plot.setBackground("#14161A")
        self.piano_roll_plot.showGrid(x=True, y=True, alpha=0.25)
        self.piano_roll_plot.setLabel("bottom", "Time", units="s")
        self.piano_roll_plot.setLabel("left", "Pitch")
        self._piano_roll_cursor = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#FF6B6B", width=1.6),
        )
        self._piano_roll_cursor.setVisible(False)
        self._piano_roll_cursor.setZValue(20)
        self.piano_roll_plot.addItem(self._piano_roll_cursor)
        pr_l.addWidget(self.piano_roll_plot)
        self.analysis_tabs.addTab(pr_tab, "MIDI 钢琴卷帘 (Piano Roll)")

        # Sub-tab 3: MIDI Table + Save As
        midi_tab = QtWidgets.QWidget()
        midi_l = QtWidgets.QVBoxLayout(midi_tab)
        midi_hdr = QtWidgets.QHBoxLayout()
        self.midi_info_lbl = QtWidgets.QLabel("尚未执行分轨 MIDI 转录（Basic Pitch 仅作用于单一分轨；点击音符行可跳转至对应时间位置）。")
        self.midi_info_lbl.setWordWrap(True)
        self.save_midi_btn = QtWidgets.QPushButton("另存 MIDI (.mid)")
        self.save_midi_btn.setEnabled(False)
        self.save_midi_btn.clicked.connect(self._on_save_midi_clicked)
        midi_hdr.addWidget(self.midi_info_lbl, 1)
        midi_hdr.addWidget(self.save_midi_btn)
        midi_l.addLayout(midi_hdr)

        self.midi_table = QtWidgets.QTableWidget(0, 5)
        self.midi_table.setHorizontalHeaderLabels(["音符", "MIDI 编号", "开始 (s)", "结束 (s)", "力度"])
        self.midi_table.horizontalHeader().setStretchLastSection(True)
        self.midi_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.midi_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.midi_table.cellClicked.connect(self._on_midi_row_clicked)
        midi_l.addWidget(self.midi_table)
        self.analysis_tabs.addTab(midi_tab, "MIDI 音符明细表")

        splitter.addWidget(self.analysis_tabs)
        splitter.setSizes([240, 220])
        root.addWidget(splitter, 1)

    @property
    def include_sevenths(self) -> bool:
        return bool(self.sevenths_chk.isChecked())

    def _on_play_clicked(self) -> None:
        self.before_play_requested.emit()
        self.mixer_engine.play(open_audio_device=True)

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
                self._piano_roll_cursor.setValue(self.mixer_engine.position_sec)

    def _seek_to_sec(self, start_sec: float) -> None:
        sr = max(1, self.mixer_engine.sample_rate)
        target = int(round(max(0.0, float(start_sec)) * sr))
        self.mixer_engine.seek(target)
        self.sync_playback_position()

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
        self.time_lbl.setText(f"{_fmt_sec(pos)} / {_fmt_sec(dur)}")
        if self._piano_roll_item is not None:
            self._piano_roll_cursor.setValue(pos)
            self._piano_roll_cursor.setVisible(True)
        if not self.seek_slider.isSliderDown():
            val = int(round((pos / dur) * 1000.0)) if dur > 1e-6 else 0
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(max(0, min(1000, val)))
            self.seek_slider.blockSignals(False)

    def _on_export_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出混合音轨 WAV",
            str(Path("exports") / "listenscope_mix.wav"),
            "WAV Audio (*.wav)",
        )
        if file_path:
            self.export_mix_requested.emit(file_path)

    def _on_deep_analyze_clicked(self) -> None:
        if self._stem_paths:
            self.deep_analyze_requested.emit(dict(self._stem_paths))

    def _on_export_sheet_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出扒谱与分析报告",
            str(Path("exports") / "listenscope_transcription.md"),
            "Markdown 报告 (*.md);;CSV 明细表 (*.csv)",
        )
        if file_path:
            self.export_sheet_requested.emit(file_path)

    def _on_save_midi_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "另存转录 MIDI 文件",
            str(Path("exports") / "listenscope_stem.mid"),
            "MIDI File (*.mid)",
        )
        if file_path:
            self.save_midi_requested.emit(file_path)

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
        self.job_progress.setValue(int(round(prog.progress * 100)))
        self.job_status_lbl.setText(f"[{prog.state.value}] {prog.message}")
        if running:
            self.oom_banner.setVisible(False)

    def handle_ai_result(self, res: AIJobResult) -> None:
        self.cancel_btn.setEnabled(False)
        if res.state == AIJobState.COMPLETED:
            self.job_progress.setValue(100)
            self.job_status_lbl.setText(
                f"✅ 分轨完成 ({res.model_id} | {res.device_used} | 用时 {res.elapsed_sec:.2f}s | 峰值 Worker RAM={res.peak_ram_mb:.1f} MB)"
            )
            self.oom_banner.setVisible(False)
            self.load_stem_paths(res.stem_paths)
        elif res.state == AIJobState.OOM_ERROR:
            self.job_progress.setValue(0)
            self.job_status_lbl.setText(f"⚠️ GPU OOM: {res.error}")
            self.oom_msg_lbl.setText(res.error or "显存/内存不足，请选择安全恢复策略：")
            self.oom_banner.setVisible(True)
        else:
            self.job_progress.setValue(0)
            self.job_status_lbl.setText(f"[{res.state.value}] {res.error or '已停止'}")

    def load_stem_paths(self, stem_paths: dict[str, str]) -> None:
        for row in self._rows.values():
            self._tracks_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._stem_paths = dict(stem_paths)

        tracks = self.mixer_engine.load_stems(stem_paths)
        self.deep_analyze_btn.setEnabled(bool(tracks))
        self.export_sheet_btn.setEnabled(False)
        self.chord_timeline_table.setRowCount(0)
        self.deep_summary_lbl.setText(
            "分轨完成后点击上方「深度分析分轨」：离线流式解析时间轴和弦进行、Bass 根音、鼓组 Kick/Snare/Hi-Hat 16 步律动及主旋律音域（支持点击表格行跳转混音试听位置）。"
        )
        self._piano_roll_cursor.setVisible(self._piano_roll_item is not None)
        self.sync_playback_position()

        for name, state in tracks.items():
            row = _StemTrackRow(name, str(state.path), state.duration_sec)
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
        bpm_txt = f"{report.estimated_bpm.bpm:.1f} ({report.estimated_bpm.stability})" if report.estimated_bpm.bpm else "Unknown"
        parts = [
            f"调性: {report.estimated_key.primary} (候选: {report.estimated_key.secondary}, {report.estimated_key.stability}) | BPM: {bpm_txt} | 和声源: {report.harmonic_source_label}"
        ]
        if report.bass is not None:
            parts.append(
                f"Bass: 音域 {report.bass.lowest_note or '-'}~{report.bass.highest_note or '-'} | "
                f"核心根音 [{', '.join(report.bass.root_pitch_classes) or '-'}] | 音符数={len(report.bass.notes)}"
            )
        if report.drums is not None:
            parts.append(
                f"Drums: Kick={len(report.drums.kick_times_sec)} / Snare={len(report.drums.snare_times_sec)} / "
                f"HiHat={len(report.drums.hihat_times_sec)} | 16步律动: {' '.join(report.drums.groove_16_step)}"
            )
        if report.melody is not None:
            parts.append(
                f"Melody ({report.melody.stem_name}): 音域 {report.melody.lowest_note or '-'}~{report.melody.highest_note or '-'} "
                f"(中位 {report.melody.median_note or '-'}) | 有声率={report.melody.voiced_ratio * 100:.1f}%"
            )
        self.deep_summary_lbl.setText("\n".join(parts))

        rows = report.chord_timeline[:400]
        self.chord_timeline_table.setRowCount(len(rows))
        for idx, seg in enumerate(rows):
            vals = [
                f"{seg.start_sec:.2f}",
                f"{seg.end_sec:.2f}",
                seg.chord,
                seg.secondary,
                f"{seg.correlation:.3f}",
                seg.stability,
            ]
            for col, text in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.chord_timeline_table.setItem(idx, col, item)

        self.export_sheet_btn.setEnabled(True)
        self.analysis_tabs.setCurrentIndex(0)

    def display_midi_result(self, result: MidiTranscriptionResult) -> None:
        warn = f" | {result.warning}" if result.warning else ""
        self.midi_info_lbl.setText(
            f"源音轨: {result.source_stem_name} | 后端: {result.backend_used} | "
            f"音符数: {len(result.notes)} | 文件: {result.output_midi_path}{warn}"
        )
        show = result.notes[:250]
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
            starts = np.array([float(n.start_sec) for n in pr_notes], dtype=np.float32)
            widths = np.array([max(0.04, float(n.end_sec - n.start_sec)) for n in pr_notes], dtype=np.float32)
            pitches = np.array([float(n.pitch_midi) for n in pr_notes], dtype=np.float32)
            self._piano_roll_item = pg.BarGraphItem(
                x0=starts,
                width=widths,
                y=pitches,
                height=0.72,
                brush="#4EA8DE",
                pen=pg.mkPen("#7EE2B8", width=0.8),
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
            self.piano_roll_plot.setXRange(0.0, max_end)
            self._piano_roll_cursor.setValue(self.mixer_engine.position_sec)
            self._piano_roll_cursor.setVisible(True)
        else:
            self._piano_roll_cursor.setVisible(False)

        self.save_midi_btn.setEnabled(result.output_midi_path is not None and Path(result.output_midi_path).exists())

