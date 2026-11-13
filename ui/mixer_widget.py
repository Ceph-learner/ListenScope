"""Multi-stem synchronized mixer, OOM recovery prompt, stem analysis bridge, and Basic Pitch MIDI UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from audio.playback import StemMixerEngine
from core.models import (
    AIJobProgress,
    AIJobResult,
    AIJobState,
    MidiTranscriptionResult,
    OOMRecoveryAction,
)


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
        analyze_btn = QtWidgets.QPushButton("送入分析")
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
    """Controls isolated AI separation progress, OOM 3-choice recovery, multi-stem playback, and MIDI output."""

    cancel_ai_requested = QtCore.Signal()
    oom_action_requested = QtCore.Signal(str)  # OOMRecoveryAction value
    export_mix_requested = QtCore.Signal(str)
    send_stem_to_analysis = QtCore.Signal(str, str)
    transcribe_stem_midi = QtCore.Signal(str, str)

    def __init__(self, mixer_engine: StemMixerEngine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.mixer_engine = mixer_engine
        self._rows: dict[str, _StemTrackRow] = {}

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

        # Transport & Presets bar
        ctrl_bar = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("播放分轨")
        self.pause_btn = QtWidgets.QPushButton("暂停")
        self.stop_btn = QtWidgets.QPushButton("停止")
        self.export_btn = QtWidgets.QPushButton("导出混合 WAV")
        self.play_btn.clicked.connect(lambda: self.mixer_engine.play(open_audio_device=True))
        self.pause_btn.clicked.connect(self.mixer_engine.pause)
        self.stop_btn.clicked.connect(self.mixer_engine.stop)
        self.export_btn.clicked.connect(self._on_export_clicked)

        ctrl_bar.addWidget(self.play_btn)
        ctrl_bar.addWidget(self.pause_btn)
        ctrl_bar.addWidget(self.stop_btn)
        ctrl_bar.addWidget(self.export_btn)
        ctrl_bar.addSpacing(14)

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

        # Splitter between Stem tracks and MIDI note preview
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self._tracks_container = QtWidgets.QWidget()
        self._tracks_layout = QtWidgets.QVBoxLayout(self._tracks_container)
        self._tracks_layout.setSpacing(6)
        self._tracks_layout.addStretch(1)
        scroll.setWidget(self._tracks_container)
        splitter.addWidget(scroll)

        midi_box = QtWidgets.QGroupBox("MIDI 扒谱输出预览 (Basic Pitch — 仅作用于分轨后单乐器音轨)")
        midi_l = QtWidgets.QVBoxLayout(midi_box)
        self.midi_info_lbl = QtWidgets.QLabel("尚未执行分轨 MIDI 转录。")
        self.midi_table = QtWidgets.QTableWidget(0, 5)
        self.midi_table.setHorizontalHeaderLabels(["音符", "MIDI 编号", "开始 (s)", "结束 (s)", "力度"])
        self.midi_table.horizontalHeader().setStretchLastSection(True)
        self.midi_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        midi_l.addWidget(self.midi_info_lbl)
        midi_l.addWidget(self.midi_table)
        splitter.addWidget(midi_box)

        splitter.setSizes([280, 160])
        root.addWidget(splitter, 1)

    def _on_export_clicked(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出混合音轨 WAV",
            str(Path("exports") / "listenscope_mix.wav"),
            "WAV Audio (*.wav)",
        )
        if file_path:
            self.export_mix_requested.emit(file_path)

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

        tracks = self.mixer_engine.load_stems(stem_paths)
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

    def display_midi_result(self, result: MidiTranscriptionResult) -> None:
        warn = f" | {result.warning}" if result.warning else ""
        self.midi_info_lbl.setText(
            f"源音轨: {result.source_stem_name} | 后端: {result.backend_used} | "
            f"音符数: {len(result.notes)} | 文件: {result.output_midi_path}{warn}"
        )
        show = result.notes[:200]
        self.midi_table.setRowCount(len(show))
        for idx, n in enumerate(show):
            vals = [n.note_name, str(n.pitch_midi), f"{n.start_sec:.2f}", f"{n.end_sec:.2f}", str(n.velocity)]
            for col, text in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.midi_table.setItem(idx, col, item)
