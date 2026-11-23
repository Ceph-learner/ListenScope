"""Regression tests for v1.0.1 UI/UX polish fixes (Issues 1-8)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from audio.drum_preview import DrumPreviewPlayer
from audio.playback import StemMixerEngine
from core.models import (
    ChordTimelineSegment,
    DrumsAnalysisResult,
    KeyEstimate,
    StemDeepAnalysisReport,
    TempoEstimate,
)
import main as main_mod
from ui.chord_practice import ChordPracticeDialog
from ui.help_badge import (
    HelpBadge,
    _get_popover,
    install_focus_animations,
    set_help_mode_enabled,
)
from ui.mixer_widget import StemMixerWidget


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_help_badge_no_focus_popup_and_focus_ring_reset_on_tab_and_deactivate() -> None:
    app = _get_app()
    set_help_mode_enabled(True)

    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    tabs = QtWidgets.QTabWidget()
    page1 = QtWidgets.QWidget()
    p1_l = QtWidgets.QHBoxLayout(page1)
    btn1 = QtWidgets.QPushButton("按钮 A")
    badge = HelpBadge("标题", "说明内容")
    p1_l.addWidget(badge)
    p1_l.addWidget(btn1)
    page2 = QtWidgets.QWidget()
    tabs.addTab(page1, "Tab 1")
    tabs.addTab(page2, "Tab 2")
    layout.addWidget(tabs)

    animator = install_focus_animations(host)
    pop = _get_popover()
    pop.hide()
    host.resize(500, 300)
    host.show()
    app.processEvents()

    try:
        assert badge.focusPolicy() == QtCore.Qt.FocusPolicy.TabFocus
        # focusInEvent must NEVER auto-show _HelpPopover
        QtWidgets.QApplication.sendEvent(
            badge,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason),
        )
        app.processEvents()
        assert pop.isVisible() is False

        # Explicit click opens _HelpPopover when window is active
        badge.click()
        app.processEvents()
        assert pop.isVisible() is True

        # FocusRingAnimator activates on TabFocusReason and resets on QTabWidget switch
        QtWidgets.QApplication.sendEvent(
            btn1,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason),
        )
        app.processEvents()
        assert animator._current_target is btn1

        tabs.setCurrentIndex(1)
        app.processEvents()
        assert animator._current_target is None
        assert animator._overlay.isVisible() is False
        assert pop.isVisible() is False

        # Passive MouseFocusReason must NOT trigger FocusRingAnimator
        QtWidgets.QApplication.sendEvent(
            btn1,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.MouseFocusReason),
        )
        app.processEvents()
        assert animator._current_target is None

        # WindowDeactivate resets FocusRingAnimator
        tabs.setCurrentIndex(0)
        app.processEvents()
        QtWidgets.QApplication.sendEvent(
            btn1,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason),
        )
        app.processEvents()
        assert animator._current_target is btn1
        QtWidgets.QApplication.sendEvent(host, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        app.processEvents()
        assert animator._current_target is None
        assert animator._overlay.isVisible() is False
    finally:
        pop.hide()
        animator.teardown()
        host.close()
        app.processEvents()


@pytest.mark.parametrize(
    ("estimate", "expected_key"),
    [
        (KeyEstimate("D major", "B minor", "Medium", 0.65, 0.05), "D major"),
        (KeyEstimate("E minor", "G major", "Low", 0.45, 0.02), "E minor"),
        (KeyEstimate("A major", "F# minor", "Medium", 0.60, 0.04, modulation_hint=True), "A major"),
        (None, "C major"),
    ],
)
def test_chord_practice_auto_preselects_across_stabilities_and_fallback(
    estimate: KeyEstimate | None,
    expected_key: str,
) -> None:
    _get_app()
    dialog = ChordPracticeDialog(["C", "G"], estimate, 0)
    try:
        assert dialog._key.currentData() == expected_key
        assert dialog._results.rowCount() > 0
        assert dialog._preview_btn.isEnabled() is True
        assert dialog._export_midi_btn.isEnabled() is True
    finally:
        dialog.close()


def test_drum_preview_player_progress_and_mixer_16step_highlight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _get_app()

    class _FakeStream:
        def __init__(self, callback, **_kwargs) -> None:
            self.callback = callback
            self.active = False

        def start(self) -> None:
            self.active = True

        def abort(self) -> None:
            self.active = False

        def close(self) -> None:
            self.active = False

    holder: list[_FakeStream] = []

    def _make_stream(**kwargs):
        s = _FakeStream(**kwargs)
        holder.append(s)
        return s

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=_make_stream, CallbackStop=RuntimeError))

    player = DrumPreviewPlayer(1000, 2)
    pcm = np.ones(2000, dtype=np.float32) * 0.25
    player.play(pcm)
    assert player.is_playing is True
    assert player.duration_sec == pytest.approx(2.0)
    assert player.position_sec == pytest.approx(0.0)

    out = np.zeros((500, 2), dtype=np.float32)
    holder[0].callback(out, 500, None, None)
    assert player.position_sec == pytest.approx(0.5)
    assert player.stop() is True
    assert player.is_playing is False
    assert player.position_sec == pytest.approx(0.0)
    assert player.duration_sec == pytest.approx(0.0)

    mixer = StemMixerWidget(StemMixerEngine(48000, 2))
    try:
        drums = DrumsAnalysisResult(
            tmp_path / "drums.wav",
            4.0,
            120.0,
            "High",
            [0.0, 0.5],
            [0.25],
            [0.125],
            groove_16_step=("K", "-", "H", "-", "S", "-", "H", "-", "K", "-", "H", "-", "S", "-", "H", "-"),
        )
        report = StemDeepAnalysisReport(
            4.0,
            "Other",
            KeyEstimate("G# major", "F minor", "High", 0.9, 0.2),
            TempoEstimate(120.0, "High", 0.9),
            drums=drums,
            chord_timeline=[ChordTimelineSegment(0.0, 2.0, "G#", "Fm", 0.88, "High")],
        )
        mixer.display_deep_analysis(report)
        # Issue 7: enharmonic display in deep summary
        assert "G# / Ab major" in mixer.deep_summary_lbl.text()
        # Issue 8: ready indicator on tab 3
        assert mixer.analysis_tabs.tabText(3).endswith("●")
        # Issue 6: beat duration column & rhythm capsule
        assert mixer.chord_timeline_table.columnCount() == 7
        assert mixer.chord_timeline_table.item(0, 6).text() == "4.0 拍"
        assert "120.0" in mixer.deep_rhythm_badge_lbl.text()

        # Issue 5: 16-step column highlight at 120 BPM (16th note = 0.125s -> 0.5s = step 4)
        mixer.set_drum_preview_playing(True)
        mixer.update_drum_preview_progress(0.5, 4.0)
        assert mixer._rhythm_active_col == 4
        assert "Step 05/16" in mixer.rhythm_status.text()
        bg_item = mixer.rhythm_table.item(0, 4)
        assert bg_item is not None and bg_item.data(QtCore.Qt.ItemDataRole.BackgroundRole) is not None

        mixer.set_drum_preview_playing(False)
        assert mixer._rhythm_active_col == -1
        assert bg_item.data(QtCore.Qt.ItemDataRole.BackgroundRole) is None
    finally:
        mixer.close()


def test_small_window_1280x720_mixer_geometry_and_quick_midi_selectors(tmp_path: Path) -> None:
    app = _get_app()
    ctrl = main_mod.ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        ctrl.analysis_worker.stop()
        ctrl._timer.stop()
        mw = ctrl.window
        mw.resize(1280, 720)
        mw.show()
        mw.tabs.setCurrentWidget(mw.mixer_widget)
        mw.mixer_widget.analysis_tabs.setCurrentIndex(0)
        app.processEvents()

        mx = mw.mixer_widget
        assert mx.chord_timeline_table.height() >= 100
        assert mx._deep_summary_scroll.height() >= 54

        # Quick stem-to-MIDI selector is disabled when no stems loaded
        assert mx.pr_transcribe_btn.isEnabled() is False
        assert mx.midi_transcribe_btn.isEnabled() is False

        # Load stems and verify priority default selection + signal emission
        bass_wav = tmp_path / "bass.wav"
        vocals_wav = tmp_path / "vocals.wav"
        bass_wav.write_bytes(b"")
        vocals_wav.write_bytes(b"")
        mx._sync_midi_stem_selectors({"bass": str(bass_wav), "vocals": str(vocals_wav)})
        assert mx.pr_transcribe_btn.isEnabled() is True
        assert mx.pr_stem_combo.currentData()[0] == "vocals"

        emitted: list[tuple[str, str]] = []
        mx.transcribe_stem_midi.connect(lambda n, p: emitted.append((n, p)))
        mx.pr_transcribe_btn.click()
        assert emitted == [("vocals", str(vocals_wav))]
    finally:
        ctrl.shutdown()
        ctrl.window.close()
        app.processEvents()
