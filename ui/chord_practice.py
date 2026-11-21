"""On-demand practice reference built from a frozen live-analysis snapshot."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from pathlib import Path
import re
from typing import Optional

from PySide6 import QtCore, QtWidgets

from analysis.chord_practice import (
    DEFAULT_BEATS_PER_CHORD,
    DEFAULT_PRACTICE_BPM,
    PRACTICE_KEYS,
    PracticeProgression,
    export_chord_progression_midi,
    practice_key,
    recommend_progressions,
    render_chord_progression_preview,
    sounding_chord_progression,
)
from analysis.chords import transpose_chord_symbol, transpose_key_label
from audio.drum_preview import DrumPreviewPlayer
from core.appearance import Appearance
from core.i18n import get_current_language, translate_widget_tree
from core.models import KeyEstimate
from core.paths import default_export_dir
from ui.acid_style import FramelessDialogChrome, TelemetryHeader, acid_stylesheet, get_acid_palette
from ui.appearance import detect_system_is_dark, set_widget_tone
from ui.help_badge import HelpBadge, install_focus_animations


class _PracticeTableDelegate(QtWidgets.QStyledItemDelegate):
    """Strip cell focus rect indentation on Row 0 and unify column alignment with headers."""

    def initStyleOption(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:  # type: ignore[override]
        super().initStyleOption(option, index)
        option.state &= ~QtWidgets.QStyle.StateFlag.State_HasFocus
        if index.column() == 2:
            option.displayAlignment = QtCore.Qt.AlignmentFlag.AlignCenter
        else:
            option.displayAlignment = (
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
            )


class ChordPracticeDialog(QtWidgets.QDialog):
    def __init__(
        self,
        recent: list[str],
        estimate: KeyEstimate | None,
        transpose: int,
        parent=None,
        *,
        bpm: float = DEFAULT_PRACTICE_BPM,
        detected_bpm: float | None = None,
        preview_player: DrumPreviewPlayer | None = None,
        before_play: Callable[[], str | None] | None = None,
        acid_variant: Optional[str] = None,
        frameless: Optional[bool] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("练习和弦 // CHORD PRACTICE")
        self.resize(760, 530)
        self.setMinimumSize(640, 440)
        parent_app: Optional[Appearance] = None
        if parent is not None:
            win = parent.window()
            if hasattr(win, "appearance") and isinstance(getattr(win, "appearance"), Appearance):
                parent_app = getattr(win, "appearance")
        want_frameless = (
            bool(frameless)
            if frameless is not None
            else (bool(parent_app.frameless) if parent_app is not None else True)
        )
        if parent is None and acid_variant in ("light", "dark"):
            self.setStyleSheet(acid_stylesheet(Appearance(frameless=want_frameless), acid_variant))

        self._raw_recent = tuple(recent)
        self._transpose = int(transpose)
        self._recent = tuple(transpose_chord_symbol(chord, self._transpose) for chord in recent)
        suggested = None
        if (
            estimate is not None
            and estimate.primary not in ("", "Unknown", "Insufficient")
            and estimate.stability in ("High", "Medium", "Low")
        ):
            suggested = practice_key(transpose_key_label(estimate.primary, self._transpose))

        self._estimated_key_selected = suggested is not None
        self._estimate_low_or_mod = bool(
            estimate is not None and (estimate.stability == "Low" or estimate.modulation_hint)
        )
        if suggested is None:
            suggested = "C major"
            self._default_fallback_selected = True
        else:
            self._default_fallback_selected = False
        self._insufficient_history = len(set(recent)) < 3
        self._items: list[PracticeProgression] = []
        self._player = preview_player if preview_player is not None else DrumPreviewPlayer(48000, 2)
        self._before_play = before_play
        self._preview_playing = False

        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setInterval(50)
        self._preview_timer.timeout.connect(self._on_preview_tick)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._shell_frame = QtWidgets.QFrame(self)
        outer.addWidget(self._shell_frame)

        root = QtWidgets.QVBoxLayout(self._shell_frame)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Zone 1: Frozen live-analysis snapshot reference (kept distinct from local practice templates)
        self._snapshot_card = QtWidgets.QFrame()
        self._snapshot_card.setObjectName("practiceCard")
        snap_layout = QtWidgets.QVBoxLayout(self._snapshot_card)
        snap_layout.setContentsMargins(12, 9, 12, 9)
        snap_layout.setSpacing(5)

        capo_badge = f"CAPO // {self._transpose:+d} ST" if self._transpose else "CONCERT // PITCH"
        self._snap_header = TelemetryHeader(
            "CHORD PRACTICE // SNAPSHOT",
            "原曲快照参考",
            badge_text=capo_badge,
        )
        self._chrome = FramelessDialogChrome(self, self._shell_frame, self._snap_header, resizable=True)
        if acid_variant in ("light", "dark"):
            pal = get_acid_palette(acid_variant)
            self._chrome.sync_colors(pal.text_secondary, "#FFFFFF")
        elif parent_app is not None:
            _, fg, _ = parent_app.effective_colors(system_is_dark=detect_system_is_dark())
            self._chrome.sync_colors(fg, "#FFFFFF")
        else:
            self._chrome.sync_colors("#334155", "#FFFFFF")
        self._chrome.apply_frameless(want_frameless)

        snap_note = QtWidgets.QLabel("SNAPSHOT_ONLY")
        snap_note.setObjectName("chromaCaption")
        self._snap_header.add_right_widget(snap_note)
        self._snap_header.add_right_widget(
            HelpBadge(
                "原曲快照参考 (SNAPSHOT_ONLY) 与和弦练习怎么用？",
                "• <b>什么是原曲快照 (SNAPSHOT_ONLY)</b>：打开本窗口时，系统会将刚才实时识别到的「原曲调性」、「检测 BPM」与「最近和弦走向」冻结在此卡片中，防止后台播放切歌或杂音打乱你的练习界面。<br/>"
                "• <b>4 步跟练用法</b>：<br/>"
                "  1. <b>确认练习调</b>：若原曲调性稳定会自动预选；若开启了 Capo 变调夹，会智能换算为你的乐器指型调。<br/>"
                "  2. <b>看懂「最近和弦匹配 (N 步)」</b>：下表第三列显示该经典套路与原曲最近和弦连续吻合的步数（例如 <code>3 步</code> 代表该套路前 3 个和弦与原曲刚才弹奏的完全一致；<code>通用练习</code> 代表该调下的经典常用走向）。<br/>"
                "  3. <b>本地试听进行</b>：点选任意一行，设置舒适的练习 BPM，点击「试听进行」即可在本地合成钢琴/电钢柱式和弦跟弹。<br/>"
                "  4. <b>导出 Cubase 标准 MIDI</b>：点击「导出进行 MIDI」可将真实发声和弦导出为 <code>.mid</code> 文件拖入宿主编曲。",
            )
        )
        self._snap_header.add_right_widget(self._chrome.close_btn)
        snap_layout.addWidget(self._snap_header)

        key_text = (
            f"{estimate.primary}（稳定度: {estimate.stability}）"
            if estimate is not None and estimate.primary not in ("", "Unknown", "Insufficient")
            else "未检测到稳定调性"
        )
        mod_text = " · [WARN] 检测到可能转调，建议对比原曲确认调性" if (estimate is not None and estimate.modulation_hint) else ""
        det_bpm_text = (
            f" · 检测速度: {float(detected_bpm):.1f} BPM"
            if detected_bpm is not None and isfinite(float(detected_bpm)) and float(detected_bpm) > 0
            else ""
        )
        self._snapshot_key_lbl = QtWidgets.QLabel(f"原曲检测调性: {key_text}{det_bpm_text}{mod_text}")
        self._snapshot_key_lbl.setObjectName("practiceMeta")
        self._snapshot_key_lbl.setWordWrap(True)
        snap_layout.addWidget(self._snapshot_key_lbl)

        recent_text = " → ".join(self._raw_recent[-8:]) if self._raw_recent else "-"
        capo_text = f" · 移调/Capo: {self._transpose:+d} 半音" if self._transpose else ""
        self._snapshot_chords_lbl = QtWidgets.QLabel(f"最近识别实音: {recent_text}{capo_text}")
        self._snapshot_chords_lbl.setObjectName("chromaCaption")
        self._snapshot_chords_lbl.setWordWrap(True)
        snap_layout.addWidget(self._snapshot_chords_lbl)
        root.addWidget(self._snapshot_card)

        # Zone 2: Practice key, tempo, status & progressions table
        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(8)
        key_lbl = QtWidgets.QLabel("练习调")
        self._key = QtWidgets.QComboBox()
        self._key.setMinimumWidth(155)
        self._key.addItem("请选择大调或小调", None)
        for key in PRACTICE_KEYS:
            self._key.addItem(key.replace(" major", " 大调").replace(" minor", " 小调"), key)
        self._key.setAccessibleName("练习调")
        key_lbl.setBuddy(self._key)
        key_help = HelpBadge(
            "练习调与指型口径",
            "若启用了移调/Capo，这里选择吉他手眼中的指型调；下表自动展示对应指型和弦，试听与 MIDI 导出会自动换算回真实发声音高。",
        )

        bpm_lbl = QtWidgets.QLabel("速度")
        self._bpm = QtWidgets.QDoubleSpinBox()
        self._bpm.setRange(30.0, 240.0)
        self._bpm.setDecimals(1)
        self._bpm.setSingleStep(1.0)
        self._bpm.setSuffix(" BPM")
        init_bpm = float(bpm) if isfinite(float(bpm)) else DEFAULT_PRACTICE_BPM
        self._bpm.setValue(max(30.0, min(240.0, init_bpm)))
        self._bpm.setMinimumWidth(112)
        self._bpm.setAccessibleName("练习速度 BPM")
        bpm_lbl.setBuddy(self._bpm)
        bpm_help = HelpBadge(
            "练习速度与匹配步数说明",
            "• <b>练习速度 (BPM)</b>：默认每个和弦占 4 拍（1 小节），调节 BPM 会实时改变本地试听与导出 MIDI 的快慢。<br/>"
            "• <b>最近和弦匹配（N 步 / 通用练习）</b>：将原曲最近识别到的和弦序列与当前调的常用套路做前缀连续比对。匹配步数越高（如 <code>3 步</code>、<code>4 步</code>），说明原曲当前段落越可能采用了该和弦套路，系统会自动将其排在表格最上方！",
        )

        self._status = QtWidgets.QLabel()
        self._status.setObjectName("practicePill")
        self._status.setWordWrap(True)

        controls.addWidget(key_lbl)
        controls.addWidget(self._key)
        controls.addWidget(key_help)
        controls.addWidget(bpm_lbl)
        controls.addWidget(self._bpm)
        controls.addWidget(bpm_help)
        controls.addWidget(self._status, 1)
        root.addLayout(controls)

        self._results = QtWidgets.QTableWidget(0, 3)
        self._results.setObjectName("practiceTable")
        self._results.setAccessibleName("和弦练习模板")
        self._results.setItemDelegate(_PracticeTableDelegate(self._results))
        self._results.setWordWrap(False)
        chords_col_title = "和弦（指型）" if self._transpose else "和弦"
        self._results.setHorizontalHeaderLabels(["罗马级数", chords_col_title, "最近和弦匹配"])
        for col, align in (
            (0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            (1, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            (2, QtCore.Qt.AlignmentFlag.AlignCenter),
        ):
            hdr_item = self._results.horizontalHeaderItem(col)
            if hdr_item is not None:
                hdr_item.setTextAlignment(align)
        header = self._results.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._results.verticalHeader().hide()
        self._results.verticalHeader().setDefaultSectionSize(32)
        self._results.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._results.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._results.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._results.setAlternatingRowColors(True)
        self._results.setShowGrid(True)
        self._results.setMinimumHeight(204)
        root.addWidget(self._results, 1)

        # Zone 3: Pitch/Tempo convention Strip + Feedback + Footer Actions
        self._convention_lbl = QtWidgets.QLabel()
        self._convention_lbl.setObjectName("practiceConvention")
        self._convention_lbl.setWordWrap(True)
        root.addWidget(self._convention_lbl)

        self._feedback_lbl = QtWidgets.QLabel("选中上方任意进行后，可试听或导出为标准 .mid 文件。")
        self._feedback_lbl.setObjectName("practiceFeedback")
        self._feedback_lbl.setProperty("tone", "info")
        self._feedback_lbl.setWordWrap(True)
        root.addWidget(self._feedback_lbl)

        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(8)
        self._preview_btn = QtWidgets.QPushButton("试听进行")
        self._preview_btn.setAutoDefault(False)
        self._preview_btn.clicked.connect(self._on_preview_clicked)

        self._export_midi_btn = QtWidgets.QPushButton("导出进行 MIDI")
        self._export_midi_btn.setObjectName("acidPrimaryBtn")
        self._export_midi_btn.setAutoDefault(False)
        self._export_midi_btn.clicked.connect(self._on_export_midi_clicked)
        midi_help = HelpBadge(
            "Cubase 兼容标准 MIDI",
            "导出 SMF Type-0 (480 PPQ) 标准 MIDI：第 0 tick 写入英文轨名、拍号、BPM、调号、Reset All CC(121=0) 与音色号，避免休止错位与音符挂起；默认保存在程序同级 exports 目录。",
        )

        self._close_btn = QtWidgets.QPushButton("关闭")
        self._close_btn.setAutoDefault(False)
        self._close_btn.clicked.connect(self.close)

        footer.addWidget(self._preview_btn)
        footer.addWidget(self._export_midi_btn)
        footer.addWidget(midi_help)
        footer.addStretch(1)
        footer.addWidget(self._close_btn)
        root.addLayout(footer)

        if suggested:
            self._key.setCurrentIndex(self._key.findData(suggested))
        self._key.activated.connect(self._on_key_selected)
        self._key.currentIndexChanged.connect(self._refresh)
        self._bpm.valueChanged.connect(self._on_tempo_changed)
        self._results.currentCellChanged.connect(self._on_selection_changed)
        self.finished.connect(self._on_dialog_finished)
        self._refresh()
        install_focus_animations(self)
        translate_widget_tree(self, get_current_language())

    def _set_feedback(self, text: str, tone: str = "info") -> None:
        self._feedback_lbl.setText(text)
        set_widget_tone(self._feedback_lbl, tone)

    def tempo_bpm(self) -> float:
        return float(self._bpm.value())

    def selected_progression(self) -> PracticeProgression | None:
        if not self._items:
            return None
        row = self._results.currentRow()
        if row < 0 or row >= len(self._items):
            row = 0
        return self._items[row]

    def sounding_chords(self, progression: PracticeProgression | None = None) -> tuple[str, ...]:
        item = progression if progression is not None else self.selected_progression()
        if item is None:
            return ()
        return sounding_chord_progression(item.chords, self._transpose)

    def _on_key_selected(self) -> None:
        self._estimated_key_selected = False
        self._default_fallback_selected = False
        self._refresh()

    def _on_tempo_changed(self) -> None:
        self._update_convention_label()

    def _on_selection_changed(self, _row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if _row != _prev_row:
            self.stop_preview()
        self._update_convention_label()

    def _refresh(self) -> None:
        self.stop_preview()
        key = self._key.currentData()
        if key is None:
            reason = "近期和弦不足" if self._insufficient_history else "检测调性尚不稳定"
            self._status.setText(f"{reason}，请手动选择练习调。")
            self._items = []
            self._results.setRowCount(0)
            self._update_convention_label()
            return

        items = recommend_progressions(key, self._recent)
        self._items = items
        if self._default_fallback_selected:
            basis = "尚未检测到稳定调性，已默认载入 C 大调练习模板，可随时切换"
        elif self._estimated_key_selected:
            if self._estimate_low_or_mod:
                basis = "按当前检测调预选（波动较大，可手动切换）"
            else:
                basis = "按当前检测调预选，可切换"
        else:
            basis = "手动选调"
        if self._transpose:
            basis += f" · 当前指型偏移 {self._transpose:+d} 半音"
        self._status.setText(basis)

        self._results.blockSignals(True)
        self._results.setRowCount(len(items))
        for row, item in enumerate(items):
            match = f"{item.matched_steps} 步" if item.matched_steps else "通用练习"
            for column, text in enumerate((" → ".join(item.degrees), " → ".join(item.chords), match)):
                cell = QtWidgets.QTableWidgetItem(text)
                if column == 2:
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                else:
                    cell.setTextAlignment(
                        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
                    )
                self._results.setItem(row, column, cell)
        if items:
            self._results.selectRow(0)
        self._results.blockSignals(False)
        self._update_convention_label()

    def _update_convention_label(self) -> None:
        item = self.selected_progression()
        has_selection = item is not None
        self._preview_btn.setEnabled(has_selection)
        self._export_midi_btn.setEnabled(has_selection)
        if item is None:
            self._convention_lbl.setText("请先在上方选择大调或小调练习模板，再试听进行或导出 MIDI。")
            return

        bpm = self.tempo_bpm()
        displayed = " → ".join(item.chords)
        sounding = " → ".join(self.sounding_chords(item))
        if self._transpose:
            self._convention_lbl.setText(
                f"口径：表中为指型 ({displayed})；试听与 MIDI 按实际发声音高输出 (实音 {sounding}) · "
                f"{bpm:.1f} BPM · 每和弦 {DEFAULT_BEATS_PER_CHORD} 拍"
            )
        else:
            self._convention_lbl.setText(
                f"试听与 MIDI 口径：{sounding}（实音，未移调） · {bpm:.1f} BPM · 每和弦 {DEFAULT_BEATS_PER_CHORD} 拍"
            )

    def _suggest_midi_filename(self, item: PracticeProgression) -> str:
        key_val = str(self._key.currentData() or "practice").replace(" ", "_")
        chords_slug = "-".join(self.sounding_chords(item))
        raw = f"listenscope_{key_val}_{chords_slug}".replace("#", "sharp")
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_") or "listenscope_chord_practice"
        return f"{cleaned}.mid"

    def _on_export_midi_clicked(self) -> None:
        item = self.selected_progression()
        if item is None:
            return
        sounding = self.sounding_chords(item)
        bpm = self.tempo_bpm()
        selected_key = str(self._key.currentData() or "")
        sounding_key = (
            transpose_key_label(selected_key, -self._transpose)
            if (selected_key and self._transpose != 0)
            else selected_key
        ) or None
        default_path = default_export_dir() / self._suggest_midi_filename(item)
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出练习和弦 MIDI",
            str(default_path),
            "MIDI 文件 (*.mid *.midi)",
        )
        if not selected:
            self._set_feedback("已取消导出 MIDI。", "info")
            return
        destination = Path(selected)
        if not destination.suffix:
            destination = destination.with_suffix(".mid")
        try:
            count = export_chord_progression_midi(
                sounding,
                destination,
                bpm=bpm,
                beats_per_chord=DEFAULT_BEATS_PER_CHORD,
                key_signature=sounding_key,
            )
        except (OSError, ValueError) as exc:
            self._set_feedback(f"导出进行 MIDI 失败：{exc}", "error")
            return
        self._set_feedback(
            f"已导出 {count} 个和弦（实音 {' → '.join(sounding)}，{bpm:.1f} BPM）至 {destination.name}。",
            "ok",
        )

    def _on_preview_clicked(self) -> None:
        if self._preview_playing:
            if self.stop_preview():
                self._set_feedback("已停止试听进行。", "info")
            return
        item = self.selected_progression()
        if item is None:
            return
        if self._before_play is not None:
            blocked_reason = self._before_play()
            if blocked_reason:
                self._set_feedback(blocked_reason, "error")
                return
        sounding = self.sounding_chords(item)
        bpm = self.tempo_bpm()
        try:
            pcm = render_chord_progression_preview(
                sounding,
                self._player.sample_rate,
                bpm=bpm,
                beats_per_chord=DEFAULT_BEATS_PER_CHORD,
            )
        except ValueError as exc:
            self._set_feedback(f"生成试听音频失败：{exc}", "error")
            return
        if not pcm.size:
            return
        try:
            self._player.play(pcm)
        except Exception as exc:
            self.stop_preview()
            self._set_feedback(f"无法打开试听设备：{exc}", "error")
            return
        self._preview_playing = True
        self._preview_btn.setText("停止试听")
        self._preview_timer.start()
        self._set_feedback(f"正在试听：{' → '.join(sounding)}（{bpm:.1f} BPM，实音）", "ok")

    def _on_preview_tick(self) -> None:
        if not self._preview_playing:
            self._preview_timer.stop()
            return
        if self._player.close_if_finished() or self._player._stream is None:
            self.sync_preview_stopped(natural=True)

    def sync_preview_stopped(self, *, natural: bool = False) -> None:
        self._preview_timer.stop()
        was_playing = self._preview_playing
        self._preview_playing = False
        self._preview_btn.setText("试听进行")
        if was_playing:
            self._set_feedback("试听结束。" if natural else "已停止试听进行。", "info")

    def stop_preview(self) -> bool:
        self._preview_timer.stop()
        stopped = self._player.stop()
        was_playing = self._preview_playing
        self._preview_playing = False
        self._preview_btn.setText("试听进行")
        return bool(stopped or was_playing)

    def _on_dialog_finished(self, _result: int) -> None:
        self.stop_preview()

    def done(self, result: int) -> None:  # type: ignore[override]
        self.stop_preview()
        if hasattr(self, "_chrome"):
            self._chrome.teardown()
        super().done(result)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop_preview()
        if hasattr(self, "_chrome"):
            self._chrome.teardown()
        super().closeEvent(event)
