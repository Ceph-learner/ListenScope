"""Regressions for chord-table alignment, FFT-YIN bass detection, Cubase MIDI, theme/fonts, HelpBadge, and turnkey packaging."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import numpy as np
import pyqtgraph as pg
import pytest
from PySide6 import QtCore, QtWidgets

from analysis.chord_practice import export_chord_progression_midi
from analysis.drum_midi import export_drum_midi
from analysis.midi_common import normalize_midi_file_for_cubase
from analysis.midi_transcription import _write_notes_to_midi
from analysis.stem_analyzer import analyze_bass_stem, export_transcription_sheet
from audio.playback import StemMixerEngine
from core.appearance import Appearance
from core.config import AIConfig, ResourceLimits
from core.models import (
    BassAnalysisResult,
    DrumsAnalysisResult,
    KeyEstimate,
    MidiNoteCandidate,
    StemDeepAnalysisReport,
    TempoEstimate,
)
from core.settings_store import load_settings
from core.system_probe import probe_system
from main import (
    ListenScopeController,
    _discover_ai_python_executable,
    _discover_midi_python_executable,
)
from ui.appearance import AppearanceDialog, detect_system_is_dark, list_installed_font_families
from ui.chord_practice import ChordPracticeDialog, _PracticeTableDelegate
from ui.chroma_widget import TuningCentsBar
from ui.help_badge import HelpBadge, wrap_with_help
from ui.main_window import DARK_STYLESHEET
from ui.mixer_widget import StemMixerWidget
from ui.settings_dialog import SettingsDialog, _discover_installed_runtime_pythons


def _write_mono_wav(path: Path, samples: np.ndarray, sr: int = 48000) -> Path:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    i16 = (clipped * 32767.0).astype(np.int16)
    stereo = np.column_stack([i16, i16])
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())
    return path


def _inspect_midi_ticks(midi_path: Path) -> tuple[mido.MidiFile, list[tuple[int, str, int, int]]]:
    mid = mido.MidiFile(str(midi_path))
    abs_tick = 0
    events: list[tuple[int, str, int, int]] = []
    for msg in mid.tracks[0]:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            events.append((abs_tick, "on", msg.channel, msg.note))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            events.append((abs_tick, "off", msg.channel, msg.note))
    return mid, events


def test_chord_practice_table_row0_alignment_and_help_badges():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    est = KeyEstimate("C major", "A minor", "High", 0.91, 0.22)
    dialog = ChordPracticeDialog(["C", "G", "Am"], est, 0)
    try:
        table = dialog._results
        assert isinstance(table.itemDelegate(), _PracticeTableDelegate)
        assert table.rowCount() >= 2
        assert table.rowHeight(0) == table.rowHeight(1)

        # Verify Row 0 strips State_HasFocus and aligns Roman/Chords left and Match center (matching headers)
        table.setCurrentCell(0, 0)
        for col, expected_align in (
            (0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            (1, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            (2, QtCore.Qt.AlignmentFlag.AlignCenter),
        ):
            opt = QtWidgets.QStyleOptionViewItem()
            opt.state |= QtWidgets.QStyle.StateFlag.State_HasFocus
            idx = table.model().index(0, col)
            table.itemDelegate().initStyleOption(opt, idx)
            assert not (opt.state & QtWidgets.QStyle.StateFlag.State_HasFocus)
            assert opt.displayAlignment == expected_align
            hdr = table.horizontalHeaderItem(col)
            assert hdr is not None
            assert QtCore.Qt.AlignmentFlag(hdr.textAlignment()) == expected_align

        assert len(dialog.findChildren(HelpBadge)) >= 2
        assert dialog.findChildren(QtWidgets.QGraphicsEffect) == []
    finally:
        dialog.close()
        app.processEvents()


def test_bass_yin_accuracy_octave_guard_modulation_and_mixer_display(tmp_path: Path):
    sr = 48000
    # 1. Strong 2nd-harmonic E1 (41.20 Hz, MIDI 28): must not jump an octave to E2 (82.41 Hz)
    t_e1 = np.arange(int(1.8 * sr), dtype=np.float64) / sr
    wave_e1 = 0.50 * np.sin(2.0 * np.pi * 41.2034 * t_e1) + 0.62 * np.sin(2.0 * np.pi * 82.4069 * t_e1)
    wav_e1 = _write_mono_wav(tmp_path / "bass_e1.wav", wave_e1, sr=sr)
    res_e1 = analyze_bass_stem(wav_e1)
    assert res_e1.signal_detected is True
    assert res_e1.lowest_midi == 28
    assert res_e1.lowest_note == "E1"
    assert res_e1.lowest_freq_hz == pytest.approx(41.2, abs=1.8)
    assert res_e1.lowest_note_time_sec is not None and res_e1.lowest_note_time_sec >= 0.0
    assert res_e1.modulation_detected is False

    # 2. 5-string B0 (30.87 Hz, MIDI 23)
    t_b0 = np.arange(int(1.8 * sr), dtype=np.float64) / sr
    wave_b0 = 0.60 * np.sin(2.0 * np.pi * 30.8677 * t_b0) + 0.35 * np.sin(2.0 * np.pi * 61.7354 * t_b0)
    res_b0 = analyze_bass_stem(_write_mono_wav(tmp_path / "bass_b0.wav", wave_b0, sr=sr))
    assert res_b0.lowest_midi == 23
    assert res_b0.lowest_note == "B0"

    # 3. Clear key shift halfway (C2 + G2 -> F#2 + C#3) triggers modulation alert
    seg = np.arange(int(0.9 * sr), dtype=np.float64) / sr
    mod_wave = np.concatenate([
        0.55 * np.sin(2.0 * np.pi * 65.406 * seg),   # C2
        0.55 * np.sin(2.0 * np.pi * 97.999 * seg),   # G2
        0.55 * np.sin(2.0 * np.pi * 92.499 * seg),   # F#2
        0.55 * np.sin(2.0 * np.pi * 138.591 * seg),  # C#3
    ])
    res_mod = analyze_bass_stem(_write_mono_wav(tmp_path / "bass_mod.wav", mod_wave, sr=sr))
    assert res_mod.modulation_detected is True
    assert "可能发生转调" in res_mod.modulation_note

    # 4. Mixer widget renders Bass MIDI / Hz / timestamp + transposition + modulation warning
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mixer = StemMixerWidget(StemMixerEngine())
    try:
        report = StemDeepAnalysisReport(
            duration_sec=3.6,
            harmonic_source_label="other+bass",
            estimated_key=KeyEstimate("E minor", "G major", "High", 0.88, 0.14, modulation_hint=True),
            estimated_bpm=TempoEstimate(112.0, "High", 0.8),
            bass=replace(res_e1, modulation_detected=True, modulation_note="前半段根音 E → 后半段 G"),
        )
        mixer.display_deep_analysis(report)
        txt0 = mixer.deep_summary_lbl.text()
        assert "E1" in txt0
        assert "MIDI 28" in txt0
        assert "Hz" in txt0
        assert "@" in txt0
        assert "疑似转调" in txt0
        assert mixer.deep_summary_lbl.property("tone") == "warn"

        # Capo -2 shifts displayed pitch to D1 / MIDI 26 while preserving concert E1 MIDI 28
        mixer.set_transpose_semitones(-2)
        txt_capo = mixer.deep_summary_lbl.text()
        assert "D1" in txt_capo
        assert "MIDI 26 · 实音 E1 MIDI 28" in txt_capo

        sheet = export_transcription_sheet(report, tmp_path / "sheet.md")
        sheet_txt = sheet.read_text(encoding="utf-8")
        assert "E1" in sheet_txt and "MIDI 28" in sheet_txt
    finally:
        mixer.mixer_engine.clear()
        mixer.close()
        app.processEvents()


def test_cubase_smf_normalization_across_all_midi_exporters(tmp_path: Path):
    # 1. Chord progression MIDI (with enharmonic G# major -> Ab canonical key_signature)
    chord_mid = tmp_path / "chords_cubase.mid"
    export_chord_progression_midi(("G#", "C#", "D#7", "G#"), chord_mid, bpm=110.0, key_signature="G# major")
    mid_c, _ = _inspect_midi_ticks(chord_mid)
    assert mid_c.type == 0
    assert mid_c.ticks_per_beat == 480
    meta_c = [m for m in mid_c.tracks[0] if m.is_meta and m.time == 0]
    assert any(m.type == "track_name" for m in meta_c)
    assert any(m.type == "time_signature" and m.numerator == 4 and m.denominator == 4 for m in meta_c)
    assert any(m.type == "set_tempo" for m in meta_c)
    assert any(m.type == "key_signature" and m.key == "Ab" for m in meta_c)
    cc_c = [(m.control, m.value) for m in mid_c.tracks[0] if m.type == "control_change" and m.time == 0]
    assert (121, 0) in cc_c and (64, 0) in cc_c

    # 2. Drum MIDI (SMF Type 0, channel 9, no program_change)
    drums_mid = tmp_path / "drums_cubase.mid"
    drums = DrumsAnalysisResult(tmp_path / "d.wav", 2.0, 120.0, "High", [0.0, 0.5], [0.25, 0.75], [0.125])
    assert export_drum_midi(drums, drums_mid) == 5
    mid_d, events_d = _inspect_midi_ticks(drums_mid)
    assert mid_d.type == 0
    assert mid_d.ticks_per_beat == 480
    assert {ch for _t, _k, ch, _n in events_d} == {9}
    assert not any(m.type == "program_change" for m in mid_d.tracks[0])

    # 3. Stem note MIDI (overlapping E1 notes trimmed, bass GM program 33, F# minor key sig)
    stem_mid = tmp_path / "bass_cubase.mid"
    notes = [
        MidiNoteCandidate(28, "E1", 0.0, 1.0, 95, 0.9),
        MidiNoteCandidate(28, "E1", 0.5, 1.5, 90, 0.9),  # overlaps previous E1 at 0.5s
    ]
    _write_notes_to_midi(notes, stem_mid, bpm=120.0, stem_name="bass", key_signature="F# minor")
    mid_s, events_s = _inspect_midi_ticks(stem_mid)
    assert mid_s.type == 0
    assert mid_s.ticks_per_beat == 480
    assert any(m.type == "program_change" and m.program == 33 for m in mid_s.tracks[0])
    assert any(m.type == "key_signature" and m.key == "F#m" for m in mid_s.tracks[0])
    # First E1 must turn off cleanly at tick=480 before the second E1 turns on at tick=480
    at_480 = [(k, n) for t, k, _c, n in events_s if t == 480]
    assert at_480.index(("off", 28)) < at_480.index(("on", 28))

    # 4. Raw Type-1 non-480-PPQ MIDI with dangling note normalized for Cubase
    dirty_mid = tmp_path / "dirty_raw.mid"
    raw = mido.MidiFile(type=1, ticks_per_beat=220)
    tr0 = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(95.0), time=0)])
    tr1 = mido.MidiTrack([
        mido.Message("note_on", channel=2, note=60, velocity=88, time=110),
        # Deliberately omit note_off to test dangling cleanup
    ])
    raw.tracks.extend([tr0, tr1])
    raw.save(str(dirty_mid))

    normalize_midi_file_for_cubase(dirty_mid, track_name="Normalized", stem_name="guitar", key_signature="C major")
    clean, clean_ev = _inspect_midi_ticks(dirty_mid)
    assert clean.type == 0
    assert clean.ticks_per_beat == 480
    assert len([e for e in clean_ev if e[1] == "on"]) == len([e for e in clean_ev if e[1] == "off"]) == 1


def test_theme_modes_font_scanning_live_preview_and_system_follow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    families = list_installed_font_families()
    assert isinstance(families, tuple)

    # Core appearance theme_mode resolution
    assert Appearance(theme_mode="dark").resolve_theme_mode(system_is_dark=False) == "dark"
    assert Appearance(theme_mode="light").resolve_theme_mode(system_is_dark=True) == "light"
    assert Appearance(theme_mode="system").resolve_theme_mode(system_is_dark=False) == "light"
    assert Appearance(theme_mode="system").resolve_theme_mode(system_is_dark=True) == "dark"
    assert Appearance(theme_mode="light").effective_colors()[0] == "#F4F6FA"

    # Dialog live preview, Restore Defaults, and safe Cancel revert
    initial = Appearance(preset="classic", theme_mode="dark", font_size=12, layout="split")
    seen_previews: list[Appearance] = []
    dialog = AppearanceDialog(initial, DARK_STYLESHEET, on_preview=seen_previews.append, system_is_dark=True)
    dialog._theme_mode_buttons["light"].click()
    dialog._font.setValue(15)
    assert seen_previews and seen_previews[-1].theme_mode == "light"
    assert seen_previews[-1].font_size == 15
    dialog._reset_btn.click()
    assert dialog.values() == Appearance()
    dialog.done(QtWidgets.QDialog.DialogCode.Rejected)
    assert seen_previews[-1] == initial

    # Full controller integration: system theme follow + Light PlotWidget contrast + persisted save
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        w = controller.window
        assert w.findChildren(QtWidgets.QGraphicsEffect) == []

        # Enable Follow-System theme mode
        w.apply_appearance(Appearance(preset="lenso", theme_mode="system", font_size=14))
        controller._on_appearance_applied()

        # Simulate Windows switching to Daylight mode
        monkeypatch.setattr("ui.main_window.detect_system_is_dark", lambda *_a, **_k: False)
        w._system_is_dark = True  # ensure change triggers refresh
        w._on_system_color_scheme_changed(QtCore.Qt.ColorScheme.Light)
        assert w._system_is_dark is False
        assert w.history_overview_plot.backgroundBrush().color().name().upper() == "#EEF4FC"
        assert w.spectrum_widget.fft_plot.backgroundBrush().color().name().upper() == "#EEF4FC"

        # Save changed font/theme through AppearanceDialog
        class FakeAcceptedDialog(AppearanceDialog):
            def exec(self) -> int:  # type: ignore[override]
                self._theme_mode_buttons["light"].click()
                self._font.setValue(16)
                return QtWidgets.QDialog.DialogCode.Accepted

        monkeypatch.setattr("ui.main_window.AppearanceDialog", FakeAcceptedDialog)
        w.open_appearance_dialog()
        saved = load_settings(controller._settings_path).appearance
        assert saved.theme_mode == "light"
        assert saved.font_size == 16
        assert w.findChildren(pg.PlotWidget)
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()


def test_help_badge_tuning_bar_and_turnkey_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    shown_tips: list[str] = []
    monkeypatch.setattr(QtWidgets.QToolTip, "showText", lambda _pos, text, *_a: shown_tips.append(text))

    lbl = QtWidgets.QLabel("示例")
    holder, badge = wrap_with_help(lbl, "复杂功能说明", "详细操作指导内容")
    assert isinstance(badge, HelpBadge)
    assert badge.focusPolicy() == QtCore.Qt.FocusPolicy.TabFocus
    assert "复杂功能说明" in badge.toolTip()
    badge.click()
    assert shown_tips and "详细操作指导内容" in shown_tips[-1]
    holder.close()

    bar = TuningCentsBar()
    bar.show()
    bar.set_pitch(440.0, 2.0)
    assert bar.has_signal is True
    assert bar.zone_color == TuningCentsBar.COLOR_IN_TUNE
    bar.set_pitch(440.0, 34.0)
    assert bar.zone_color == TuningCentsBar.COLOR_OFF
    bar.set_pitch(None)
    assert bar.has_signal is False
    bar.close()

    # Runtime auto-discovery: bundled relocatable `runtime/ai` + short `m` MIDI dir
    app_dir = tmp_path / "ListenScopeApp"
    ai_py = app_dir / "runtime" / "ai" / "python.exe"
    midi_py = app_dir / "m" / "python.exe"
    ai_py.parent.mkdir(parents=True)
    midi_py.parent.mkdir(parents=True)
    ai_py.write_text("", encoding="utf-8")
    midi_py.write_text("", encoding="utf-8")

    found_ai, found_midi = _discover_installed_runtime_pythons(app_dir)
    assert Path(found_ai) == ai_py
    assert Path(found_midi) == midi_py

    monkeypatch.setenv("LISTENSCOPE_AI_PYTHON", str(ai_py))
    monkeypatch.setenv("LISTENSCOPE_MIDI_PYTHON", str(midi_py))
    assert Path(_discover_ai_python_executable()) == ai_py
    assert Path(_discover_midi_python_executable()) == midi_py
    app.processEvents()


def test_windows_turnkey_installer_and_scripts_present_and_sane():
    root = Path(__file__).resolve().parent.parent
    iss = (root / "scripts" / "installer.iss").read_text(encoding="utf-8")
    setup_ps1 = (root / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    build_ps1 = (root / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")

    # Inno Setup: per-user non-admin possible, smart non-C default drive, bundles staged runtimes & preserves exports
    assert "PrivilegesRequired=lowest" in iss
    assert "GetDefaultInstallDir" in iss
    assert "D:\\ListenScope" in iss
    assert "{#MySourceDir}\\*" in iss
    assert "{app}\\exports" in iss
    assert "uninsneveruninstall" in iss

    # Setup & build scripts support turnkey offline/sibling & relocatable runtimes
    assert "SkipCore" in setup_ps1
    assert "AiVenvPath" in setup_ps1
    assert "--no-write" in setup_ps1
    assert "BundleRuntimes" in build_ps1
    assert "BuildInstaller" in build_ps1
    assert "Assert-PortableRuntime" in build_ps1


def test_settings_dialog_turnkey_storage_and_help_badges():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dlg = SettingsDialog(
        probe_system(),
        ResourceLimits(),
        AIConfig(),
        appearance=Appearance(theme_mode="system", font_size=14, font_family="Sans Serif"),
    )
    try:
        dlg.open_category("appearance")
        assert "跟随系统" in dlg._theme_summary.text()
        assert "14 px" in dlg._font_summary.text()
        dlg.open_category("midi")
        assert dlg.setup_all_btn.isEnabled()
        assert dlg.setup_midi_only_btn.isEnabled()
        assert len(dlg.findChildren(HelpBadge)) >= 3
        assert dlg.findChildren(QtWidgets.QGraphicsEffect) == []
    finally:
        dlg.close()
        app.processEvents()
