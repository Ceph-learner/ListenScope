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
from PySide6 import QtCore, QtGui, QtWidgets

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
    assert Appearance().preset == "acid_telemetry"
    assert Appearance().theme_mode == "light"
    assert Appearance(theme_mode="dark").resolve_theme_mode(system_is_dark=False) == "dark"
    assert Appearance(theme_mode="light").resolve_theme_mode(system_is_dark=True) == "light"
    assert Appearance(theme_mode="system").resolve_theme_mode(system_is_dark=False) == "light"
    assert Appearance(theme_mode="system").resolve_theme_mode(system_is_dark=True) == "dark"
    assert Appearance(preset="classic", theme_mode="light").effective_colors()[0] == "#F4F6FA"
    assert Appearance(preset="acid_telemetry", theme_mode="light").effective_colors()[0] == "#EEF2F6"

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
        w.apply_appearance(Appearance(preset="arctic_slate", theme_mode="system", font_size=14))
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

    from ui.help_badge import _get_popover

    lbl = QtWidgets.QLabel("示例")
    holder, badge = wrap_with_help(lbl, "复杂功能说明", "详细操作指导内容")
    assert isinstance(badge, HelpBadge)
    assert badge.focusPolicy() == QtCore.Qt.FocusPolicy.NoFocus
    assert "复杂功能说明" in badge.toolTip()
    holder.show()
    holder.activateWindow()
    app.processEvents()
    badge.click()
    pop = _get_popover()
    assert pop.isVisible()
    assert "详细操作指导内容" in pop._body_lbl.text()
    pop.hide()
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
        appearance=Appearance(preset="classic", theme_mode="system", font_size=14, font_family="Sans Serif"),
    )
    try:
        dlg.open_category("appearance")
        assert "跟随系统" in dlg._theme_summary.text()
        assert "14 px" in dlg._font_summary.text()
        assert hasattr(dlg, "open_repo_btn")
        assert hasattr(dlg, "open_issues_btn")
        assert hasattr(dlg, "copy_repo_url_btn")
        dlg.open_category("midi")
        assert dlg.setup_all_btn.isEnabled()
        assert dlg.setup_midi_only_btn.isEnabled()
        assert dlg.scan_pytorch_btn.isEnabled()
        assert dlg.open_pytorch_url_btn.isEnabled()
        assert len(dlg.findChildren(HelpBadge)) >= 8
        assert dlg.findChildren(QtWidgets.QGraphicsEffect) == []
    finally:
        dlg.close()
        app.processEvents()


def test_acid_telemetry_v2_preset_integration_topbar_sync_persistence_and_packaging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import re
    from core.appearance import PRESETS
    from core.models import AnalysisSnapshot, ChordEstimate, PitchEstimate
    from ui.acid_style import (
        AcidGraphicOverlay,
        DotMatrixWidget,
        acid_stylesheet,
        is_acid_eligible,
        resolve_acid_variant,
    )
    from ui.appearance import appearance_stylesheet

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 1. Core preset registry keeps classic [0] and arctic_slate [1], adds acid_telemetry, and migrates legacy preset name silently
    preset_keys = list(PRESETS.keys())
    assert preset_keys[0] == "classic"
    assert preset_keys[1] == "arctic_slate"
    assert "acid_telemetry" in PRESETS
    assert Appearance.from_mapping({"preset": "marathon"}).preset == "acid_telemetry"
    assert Appearance.from_mapping({"preset": "lenso"}).preset == "arctic_slate"

    m_dark = Appearance(preset="acid_telemetry", theme_mode="dark")
    m_light = Appearance(preset="acid_telemetry", theme_mode="light")
    m_sys = Appearance(preset="acid_telemetry", theme_mode="system")
    assert m_dark.effective_colors() == ("#0B0D0F", "#F1F2EC", "#CEFF18")
    assert m_light.effective_colors() == ("#EEF2F6", "#090D14", "#00A878")
    assert m_sys.effective_colors(system_is_dark=False) == ("#EEF2F6", "#090D14", "#00A878")

    # Acid Telemetry locks font_family, custom colors, and background_image while allowing font_size
    m_locked = Appearance.from_mapping({
        "preset": "acid_telemetry",
        "theme_mode": "light",
        "font_size": 16,
        "font_family": "Comic Sans MS",
        "background": "#123456",
        "text": "#654321",
        "accent": "#FF00FF",
        "background_image": "/tmp/custom_bg.png",
    })
    assert m_locked.font_size == 16
    assert m_locked.font_family == ""
    assert m_locked.background == ""
    assert m_locked.text == ""
    assert m_locked.accent == ""
    assert m_locked.background_image == ""
    assert is_acid_eligible(m_dark) is True
    assert is_acid_eligible(Appearance(preset="classic")) is False
    assert is_acid_eligible(Appearance(preset="acid_telemetry", accent="#123456")) is True
    assert resolve_acid_variant(m_dark) == "dark"
    assert resolve_acid_variant(m_light) == "light"
    assert resolve_acid_variant(m_sys, system_is_dark=False) == "light"
    assert resolve_acid_variant(m_sys, system_is_dark=True) == "dark"
    assert resolve_acid_variant(Appearance(preset="arctic_slate")) is None

    # 2. AppearanceDialog lists Acid Telemetry preset, locks font/color/bg controls in Acid mode, unlocks in Arctic Slate, and cancels cleanly
    previews: list[Appearance] = []
    initial = Appearance(preset="classic", theme_mode="dark")
    dlg = AppearanceDialog(initial, DARK_STYLESHEET, on_preview=previews.append, system_is_dark=True)
    acid_btn = next(b for b in dlg._presets.buttons() if b.property("preset") == "acid_telemetry")
    assert acid_btn.text() == "酸性遥测"
    acid_btn.click()
    assert dlg.values().preset == "acid_telemetry"
    assert dlg._font.isEnabled() is True
    assert dlg._font_family.isEnabled() is False
    assert all(not edit.isEnabled() for edit in dlg._colors.values())
    assert dlg._bg_image_edit.isEnabled() is False
    assert dlg._acid_lock_banner.isHidden() is False
    assert "#0B0D0F" in dlg._sample.styleSheet()
    assert "#CEFF18" in dlg._sample.styleSheet()
    # Switch to Arctic Slate unlocks font family, colors, and background image
    slate_btn = next(b for b in dlg._presets.buttons() if b.property("preset") == "arctic_slate")
    slate_btn.click()
    assert dlg._font_family.isEnabled() is True
    assert all(edit.isEnabled() for edit in dlg._colors.values())
    assert dlg._bg_image_edit.isEnabled() is True
    assert dlg._acid_lock_banner.isHidden() is True
    dlg.done(QtWidgets.QDialog.DialogCode.Rejected)
    assert previews[-1] == initial

    # 3. SettingsDialog honors dark Acid Telemetry variant, shrinks to 560x500 even under wide fallback fonts, and resets cleanly
    orig_app_font = app.font()
    fallback_mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
    fallback_mono.setPixelSize(12)
    app.setFont(fallback_mono)
    s_dlg = SettingsDialog(
        probe_system(),
        ResourceLimits(),
        AIConfig(),
        appearance=Appearance(preset="acid_telemetry", theme_mode="dark"),
    )
    try:
        s_dlg.show()
        app.processEvents()
        assert s_dlg._acid_variant == "dark"
        assert "酸性遥测 · 黑夜" in s_dlg._theme_summary.text()
        assert "#0B0D0F" in s_dlg.styleSheet()
        scroll_pages = s_dlg.findChildren(QtWidgets.QWidget, "settingsScrollPage")
        assert len(scroll_pages) == 3
        assert all(not p.autoFillBackground() for p in scroll_pages)
        s_dlg.open_category("midi")
        s_dlg.resize(560, 500)
        app.processEvents()
        assert s_dlg.width() == 560
        assert s_dlg.midi_python_edit.width() >= 180
        assert s_dlg._header.eyebrow_lbl.height() >= 10
        assert s_dlg._page_eyebrow.height() >= 10

        s_dlg.apply_skin(Appearance(preset="classic", theme_mode="dark"))
        app.processEvents()
        assert s_dlg._acid_variant is None
        assert s_dlg.styleSheet() == ""
        s_dlg.resize(560, 500)
        app.processEvents()
        assert s_dlg.width() == 560
        assert s_dlg.midi_python_edit.width() >= 180
    finally:
        s_dlg.close()
        app.setFont(orig_app_font)
        app.processEvents()

    # 4. Full MainWindow + Controller integration: Default Clinical Light -> Topbar Acid Dark -> Static Lock -> Follow System -> Lenso
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        w = controller.window
        # Default startup theme is now Acid Telemetry Clinical Light!
        assert w.appearance.preset == "acid_telemetry"
        assert w.appearance.theme_mode == "light"
        assert w._acid_variant == "light"
        assert w._skin_switcher.isHidden() is False
        assert w._hazard_bar.isHidden() is False
        assert w._acid_footer.isHidden() is False
        assert w._pill_light.isChecked() is True
        assert w._pill_dark.isChecked() is False
        assert w._skin_badge.text() == "ACID // CLINICAL_LIGHT"
        assert w.history_overview_plot.backgroundBrush().color().name().upper() == "#F8FAFC"

        # Topbar quick switch pill flips to Acid & Void v2 Dark with Clinical Paper Dock and persists theme_mode="dark"
        w._pill_dark.click()
        assert w._acid_variant == "dark"
        assert w._pill_dark.isChecked() is True
        assert w._skin_badge.text() == "ACID // VOID_V2"
        assert w._history_box.objectName() == "historyPaperDock"
        assert w.history_overview_plot.backgroundBrush().color().name().upper() == "#F4F5F2"
        assert "// 01 SPECTRUM" in w.tabs.tabText(0)
        assert "// 02 CHROMA & HARMONY" in w.tabs.tabText(1).replace("&&", "&")
        assert w.chroma_widget.chord_echo_lbl.isHidden() is False
        assert all(dm.isHidden() is False for dm in w.chroma_widget.findChildren(DotMatrixWidget))
        assert all(ov.isHidden() is False for ov in w.chroma_widget.findChildren(AcidGraphicOverlay))
        saved_dark = load_settings(controller._settings_path).appearance
        assert saved_dark.preset == "acid_telemetry"
        assert saved_dark.theme_mode == "dark"

        # Programmatic short aliases ("light"/"dark") match pill behavior
        w.set_acid_skin("light")
        assert w._acid_variant == "light"
        w.set_acid_skin("dark")
        assert w._acid_variant == "dark"

        # [STATIC_LOCK] freezes analysis snapshot updates until unlocked
        snap_am = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[-0.3, -0.2],
            waveform_max=[0.3, 0.2],
            fft_freqs_hz=[100.0, 1000.0],
            fft_db=[-35.0, -24.0],
            log_freqs_hz=[100.0, 1000.0],
            log_spectrum_db=[-35.0, -24.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("Am", "C", "High", 0.9, 0.25, False),
            key=KeyEstimate("A minor", "C major", "High", 0.92, 0.2),
            tempo=TempoEstimate(120.0, "High", 0.8),
            pitch=PitchEstimate(440.0, "A4", 0.0, 0.95),
            rms_dbfs=-18.0,
            peak_dbfs=-6.0,
            window_seconds=2.0,
        )
        snap_c = replace(
            snap_am,
            timestamp=2.0,
            chord=ChordEstimate("C", "G", "High", 0.92, 0.3, False),
            pitch=PitchEstimate(261.63, "C4", 0.0, 0.96),
        )
        w.update_analysis_snapshot(snap_am, None, None)
        assert w.chroma_widget.chord_primary_lbl.text() == "Am"
        assert "Am" in w.chroma_widget.chord_echo_lbl.text()

        w._acid_footer.lock_btn.click()
        assert w._static_lock is True
        assert w._acid_footer.lock_btn.text() == "[STATIC_LOCK: ON]"
        w.update_analysis_snapshot(snap_c, None, None)
        assert w.chroma_widget.chord_primary_lbl.text() == "Am"  # remains frozen while locked

        w._acid_footer.lock_btn.click()
        assert w._static_lock is False
        assert w._acid_footer.lock_btn.text() == "[STATIC_LOCK: OFF]"
        w.update_analysis_snapshot(snap_c, None, None)
        assert w.chroma_widget.chord_primary_lbl.text() == "C"

        # Follow-system in Acid Telemetry mode tracks Windows colorScheme changes
        w.apply_appearance(Appearance(preset="acid_telemetry", theme_mode="system"))
        monkeypatch.setattr("ui.main_window.detect_system_is_dark", lambda *_a, **_k: False)
        w._system_is_dark = True
        w._on_system_color_scheme_changed(QtCore.Qt.ColorScheme.Light)
        assert w._acid_variant == "light"
        assert w._pill_light.isChecked() is True

        # Switch back to Arctic Slate Light cleanly hides topbar switcher/chrome & restores classic tabs & plots
        w.apply_appearance(Appearance(preset="arctic_slate", theme_mode="light"))
        assert w._acid_variant is None
        assert w._skin_switcher.isVisible() is False
        assert w._hazard_bar.isVisible() is False
        assert w._acid_footer.isVisible() is False
        assert w.chroma_widget.chord_echo_lbl.isVisible() is False
        assert all(dm.isVisible() is False for dm in w.chroma_widget.findChildren(DotMatrixWidget))
        assert all(ov.isVisible() is False for ov in w.chroma_widget.findChildren(AcidGraphicOverlay))
        assert w._history_box.objectName() == ""
        assert w.tabs.tabText(0) == "// 01 实时频谱与波形"
        assert w._skin_badge.text() == "THEME // ARCTIC_SLATE"
        assert w.history_overview_plot.backgroundBrush().color().name().upper() == "#EEF4FC"
        assert w.findChildren(QtWidgets.QGraphicsEffect) == []
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()

    # 5. ChordPracticeDialog SNAPSHOT_ONLY & Acid skin isolation
    est = KeyEstimate("C major", "A minor", "High", 0.91, 0.22)
    c_dlg = ChordPracticeDialog(["C", "G", "Am"], est, 0, acid_variant="dark")
    try:
        assert c_dlg._results.rowHeight(0) == c_dlg._results.rowHeight(1)
        assert any(lbl.text() == "SNAPSHOT_ONLY" for lbl in c_dlg.findChildren(QtWidgets.QLabel))
    finally:
        c_dlg.close()
        app.processEvents()

    # 6. Acid flat controls QSS, PyInstaller spec SVG assets, and IP scrub in ui/ + docs/
    qss_light = acid_stylesheet(m_light, "light")
    qss_dark = acid_stylesheet(m_dark, "dark")
    for qss in (qss_light, qss_dark):
        assert "QComboBox::drop-down" in qss
        assert "QComboBox::down-arrow" in qss
        assert "QSpinBox::up-button" in qss
        assert "QSpinBox::down-button" in qss
        assert "QScrollArea" in qss
        assert "QWidget#settingsScrollPage" in qss
        assert "QFrame#acidTopbar QLabel" not in qss
        assert "QGroupBox#historyPaperDock" in qss
    assert "acid_chevron_down_light.svg" in qss_light
    assert "acid_chevron_up_light.svg" in qss_light
    assert "acid_check_light.svg" in qss_light
    assert "acid_chevron_down_dark.svg" in qss_dark
    assert "acid_chevron_up_dark.svg" in qss_dark
    assert "acid_check_dark.svg" in qss_dark

    # Classic stylesheet must stay completely untouched by Acid-only chevron SVGs
    classic_qss = appearance_stylesheet(DARK_STYLESHEET, Appearance(preset="classic", theme_mode="dark"))
    assert "acid_chevron_" not in classic_qss

    root = Path(__file__).resolve().parent.parent
    spec_txt = (root / "packaging" / "listenscope_core.spec").read_text(encoding="utf-8")
    for svg_name in (
        "acid_check_dark.svg",
        "acid_check_light.svg",
        "acid_chevron_down_light.svg",
        "acid_chevron_down_dark.svg",
        "acid_chevron_up_light.svg",
        "acid_chevron_up_dark.svg",
        "listenscope.svg",
        "listenscope.ico",
    ):
        assert (root / "ui" / "assets" / svg_name).is_file()
    for svg_name in (
        "acid_check_dark.svg",
        "acid_check_light.svg",
        "acid_chevron_down_light.svg",
        "acid_chevron_down_dark.svg",
        "acid_chevron_up_light.svg",
        "acid_chevron_up_dark.svg",
    ):
        assert svg_name in spec_txt

    forbidden = re.compile(r"marathon|nucaloric|\bm5\b|马拉松", re.IGNORECASE)
    for py_file in sorted((root / "ui").glob("*.py")):
        assert not forbidden.search(py_file.read_text(encoding="utf-8")), f"Unexpected legacy term in {py_file.name}"
    for doc_file in [root / "README.md", root / "ACKNOWLEDGMENTS.md", root / "CONTRIBUTING.md", *sorted((root / "docs").glob("*.md"))]:
        if doc_file.exists():
            assert not forbidden.search(doc_file.read_text(encoding="utf-8")), f"Unexpected legacy term in {doc_file.name}"


def test_home_feedback_i18n_bass_boost_export_singleline_chords_pytorch_scan_and_frameless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from types import SimpleNamespace
    from core.i18n import LANGUAGES, tr_telemetry, translate_text
    from core.models import AnalysisSnapshot, ChordEstimate, KeyEstimate, PitchEstimate, TempoEstimate
    from core.system_probe import (
        PYTORCH_CU128_INDEX_URL,
        PYTORCH_OFFICIAL_URL,
        scan_local_pytorch_installations,
    )

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 1. 4-language support (zh/en/ko/ja) without duplicate English in en mode
    assert tuple(LANGUAGES.keys()) == ("zh", "en", "ko", "ja")
    assert tr_telemetry("CAPTURE_START", "开始捕获", "캡처 시작", "キャプチャ開始", lang="zh") == "CAPTURE_START // 开始捕获"
    assert tr_telemetry("CAPTURE_START", "开始捕获", "캡처 시작", "キャプチャ開始", lang="en") == "CAPTURE_START"
    assert tr_telemetry("CAPTURE_START", "开始捕获", "캡처 시작", "キャプチャ開始", lang="ko") == "CAPTURE_START // 캡처 시작"
    assert tr_telemetry("CAPTURE_START", "开始捕获", "캡처 시작", "キャプチャ開始", lang="ja") == "CAPTURE_START // キャプチャ開始"
    assert translate_text("外观", "en") == "Theme"
    assert translate_text("外观", "ko") == "테마"
    assert translate_text("外观", "ja") == "外観"

    # 2. Custom Bass Solo Boost dB (0-24 dB, default 12 dB), >12 dB warning, and optional apply on export
    engine = StemMixerEngine()
    assert engine.bass_monitor_boost_db == pytest.approx(12.0)
    assert engine.apply_bass_boost_on_export is False
    engine.set_bass_monitor_boost_db(18.5)
    assert engine.bass_monitor_boost_db == pytest.approx(18.5)
    engine.set_bass_monitor_boost_db(99.0)
    assert engine.bass_monitor_boost_db == pytest.approx(24.0)

    sr = 48000
    t = np.arange(sr // 2, dtype=np.float32) / sr
    bass_sig = (0.12 * np.sin(2.0 * np.pi * 55.0 * t)).astype(np.float32)
    bass_wav = _write_mono_wav(tmp_path / "bass.wav", bass_sig, sr=sr)
    engine.load_stems({"bass": bass_wav})
    engine.set_solo("bass", True)
    engine.set_bass_monitor_boost_db(12.0)

    out_unboosted = tmp_path / "export_raw.wav"
    out_boosted = tmp_path / "export_boosted.wav"
    engine.export_mix_streaming(out_unboosted, apply_bass_boost=False)
    engine.export_mix_streaming(out_boosted, apply_bass_boost=True)

    with wave.open(str(out_unboosted), "rb") as wf_raw, wave.open(str(out_boosted), "rb") as wf_b:
        arr_raw = np.frombuffer(wf_raw.readframes(wf_raw.getnframes()), dtype=np.int16).astype(np.float64)
        arr_b = np.frombuffer(wf_b.readframes(wf_b.getnframes()), dtype=np.int16).astype(np.int64)
    rms_raw = float(np.sqrt(np.mean(arr_raw ** 2)))
    rms_b = float(np.sqrt(np.mean(arr_b.astype(np.float64) ** 2)))
    assert rms_b > rms_raw * 2.5

    mixer_w = StemMixerWidget(engine)
    try:
        assert mixer_w.bass_boost_db_spin.value() == pytest.approx(12.0)
        assert mixer_w.bass_boost_warn_lbl.isHidden() is True
        mixer_w.bass_boost_db_spin.setValue(15.0)
        assert engine.bass_monitor_boost_db == pytest.approx(15.0)
        assert mixer_w.bass_boost_warn_lbl.isHidden() is False
        mixer_w.bass_boost_export_chk.setChecked(True)
        assert engine.apply_bass_boost_on_export is True
    finally:
        mixer_w.close()
        engine.clear()

    # 3. Single-line recent chord progression in "both" mode (Name[Degree])
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        w = controller.window
        cw = w.chroma_widget
        assert cw.chord_progression_lbl.wordWrap() is False
        cw.progression_mode_combo.setCurrentIndex(cw.progression_mode_combo.findData("both"))
        snap_base = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[-0.2],
            waveform_max=[0.2],
            fft_freqs_hz=[100.0],
            fft_db=[-30.0],
            log_freqs_hz=[100.0],
            log_spectrum_db=[-30.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("C", "G", "High", 0.9, 0.25, False),
            key=KeyEstimate("C major", "A minor", "High", 0.92, 0.2),
            tempo=TempoEstimate(120.0, "High", 0.8),
            pitch=PitchEstimate(261.63, "C4", 0.0, 0.95),
            rms_dbfs=-18.0,
            peak_dbfs=-6.0,
            window_seconds=2.0,
        )
        for idx, ch_name in enumerate(["C", "G", "Am", "F", "Dm", "G", "C", "Am", "F", "G"]):
            cw.update_analysis(
                replace(
                    snap_base,
                    timestamp=float(idx + 1),
                    chord=ChordEstimate(ch_name, "C", "High", 0.9, 0.25, False),
                )
            )
        prog_txt = cw.chord_progression_lbl.text()
        assert "\n" not in prog_txt
        assert "[" in prog_txt and "]" in prog_txt
        assert "…" in prog_txt  # 10 steps > 8 inline limit shows ellipsis prefix while full 10 are in toolTip
        assert len(cw.chord_progression_lbl.toolTip().split("→")) == 10

        # 4. Language switching (zh -> en -> ko -> ja -> zh) & window geometry lock when visible
        w.show()
        min_hint = w.minimumSizeHint()
        init_w = 1360 if min_hint.width() <= 1300 else min_hint.width() + 450
        init_h = 860 if min_hint.height() <= 855 else min_hint.height() + 40
        w.resize(init_w, init_h)
        w.move(80, 60)
        app.processEvents()
        geom_before = w.geometry()
        assert geom_before.width() == init_w and geom_before.height() == init_h
        w.apply_appearance(replace(w.appearance, language="en"))
        app.processEvents()
        assert w.geometry() == geom_before
        assert w.capture_btn.text() == "CAPTURE_START"
        assert w.tabs.tabText(0) == "// 01 SPECTRUM"
        w.apply_appearance(replace(w.appearance, language="ko"))
        app.processEvents()
        assert w.geometry() == geom_before
        assert "캡처 시작" in w.capture_btn.text()
        w.apply_appearance(replace(w.appearance, language="ja"))
        app.processEvents()
        assert w.geometry() == geom_before
        assert "キャプチャ開始" in w.capture_btn.text()
        w.apply_appearance(replace(w.appearance, language="zh"))
        app.processEvents()
        assert w.geometry() == geom_before
        assert w.capture_btn.text() == "CAPTURE_START // 开始捕获"
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()

    # 5. Local PyTorch scanner & official URL constants
    assert PYTORCH_OFFICIAL_URL == "https://pytorch.org/get-started/locally/"
    assert "download.pytorch.org/whl/cu128" in PYTORCH_CU128_INDEX_URL
    fake_py = tmp_path / ".venv-ai" / "Scripts" / "python.exe"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "core.system_probe.run_external_python",
        lambda cmd, **_k: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "installed": True,
                "python_executable": cmd[0],
                "torch_version": "2.11.0+cu128",
                "cuda_available": True,
                "cuda_build": "12.8",
                "supports_sm_120": True,
                "device_name": "NVIDIA GeForce RTX 5060 Ti",
            }),
        ),
    )
    found = scan_local_pytorch_installations((tmp_path,), require_disk_torch=False)
    assert found and found[0]["cuda_available"] is True
    assert found[0]["torch_version"] == "2.11.0+cu128"


def test_help_mode_focus_animations_and_hybrid_gpu_persistence(tmp_path) -> None:
    """Help Mode, Focus Animations, and Plan A/B Hybrid iGPU+dGPU settings persist cleanly."""
    from core.config import AIConfig, ResourceLimits
    from core.settings_store import PersistedSettings, load_settings, save_settings

    settings_path = tmp_path / "settings.json"
    ap = Appearance(
        preset="acid_telemetry",
        theme_mode="light",
        help_mode=False,
        focus_animations=False,
    )
    ai = AIConfig(
        igpu_directml_2stem=True,
        igpu_directml_device_id=2,
        offload_gui_to_igpu=True,
    )
    save_settings(
        PersistedSettings(resource_limits=ResourceLimits(), ai_config=ai, appearance=ap),
        path=settings_path,
    )
    loaded = load_settings(path=settings_path)
    assert loaded.appearance.help_mode is False
    assert loaded.appearance.focus_animations is False
    assert loaded.ai_config.igpu_directml_2stem is True
    assert loaded.ai_config.igpu_directml_device_id == 2
    assert loaded.ai_config.offload_gui_to_igpu is True


def test_mixer_ms_alignment_help_mode_toggle_theme_dialog_and_zero_i18n_leaks(tmp_path) -> None:
    """Verify M/S vertical alignment, Help Mode global toggle, themed AppearanceDialog, Hybrid GPU UI, and 0 EN/KO Chinese leaks."""
    import re
    import wave

    import numpy as np
    import pyqtgraph as pg
    from PySide6 import QtWidgets

    from core.config import AIConfig, ResourceLimits
    from core.i18n import set_current_language
    from core.models import AnalysisSnapshot, ChordEstimate, KeyEstimate, PitchEstimate, TempoEstimate
    from core.system_probe import probe_system
    from main import ListenScopeController
    from ui.appearance import AppearanceDialog
    from ui.chord_practice import ChordPracticeDialog
    from ui.help_badge import HelpBadge, set_help_mode_enabled
    from ui.main_window import DARK_STYLESHEET
    from ui.settings_dialog import SettingsDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cjk_re = re.compile(r"[\u4e00-\u9fff]")

    stems: dict[str, str] = {}
    for name in ("vocals", "drums", "bass", "other"):
        p = tmp_path / f"{name}.wav"
        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00\x00\x00" * 11025)
        stems[name] = str(p)

    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        controller.analysis_worker.stop()
        controller._timer.stop()
        mw = controller.window
        mw.resize(1380, 900)
        mw.show()
        mw.mixer_widget.load_stem_paths(stems)
        mw.tabs.setCurrentIndex(2)
        app.processEvents()

        # 1. M and S buttons vertically aligned across all 4 stem tracks
        m_xs = {
            name: row.mute_btn.mapTo(mw.mixer_widget, row.mute_btn.rect().topLeft()).x()
            for name, row in mw.mixer_widget._rows.items()
        }
        s_xs = {
            name: row.solo_btn.mapTo(mw.mixer_widget, row.solo_btn.rect().topLeft()).x()
            for name, row in mw.mixer_widget._rows.items()
        }
        assert len(set(m_xs.values())) == 1, f"M buttons misaligned: {m_xs}"
        assert len(set(s_xs.values())) == 1, f"S buttons misaligned: {s_xs}"

        # 2. Help Mode toggle globally hides and restores all HelpBadges
        badges = mw.findChildren(HelpBadge)
        assert len(badges) >= 15
        mw.apply_appearance(replace(mw.appearance, help_mode=False))
        app.processEvents()
        assert all(b.isHidden() for b in badges)
        mw.apply_appearance(replace(mw.appearance, help_mode=True))
        app.processEvents()
        assert all(not b.isHidden() for b in badges)

        # 3. AppearanceDialog inherits the active theme stylesheet itself (not only preview box)
        ap_en = Appearance(preset="acid_telemetry", theme_mode="light", language="en")
        set_current_language("en")
        mw.apply_appearance(ap_en)
        dlg_app = AppearanceDialog(ap_en, DARK_STYLESHEET, parent=mw)
        assert bool(dlg_app.styleSheet().strip())
        assert "ACID_TELEMETRY" in dlg_app.styleSheet() or "#F3F4F6" in dlg_app.styleSheet() or "QDialog" in dlg_app.styleSheet()

        # 4. SettingsDialog exposes Plan A & Plan B Hybrid GPU toggles
        dlg_set = SettingsDialog(
            probe_system(),
            ResourceLimits(),
            AIConfig(igpu_directml_2stem=True, igpu_directml_device_id=1, offload_gui_to_igpu=True),
            appearance=ap_en,
            parent=mw,
        )
        assert dlg_set.igpu_dml_chk.isChecked() is True
        assert dlg_set.igpu_dml_id_spin.value() == 1
        assert dlg_set.gui_offload_chk.isChecked() is True

        # 5. Zero Chinese character leaks across EN & KO (including live snapshot, HelpBadges, plots, tables)
        freqs = np.linspace(20.0, 12000.0, 64)
        snap = AnalysisSnapshot(
            timestamp=4.0,
            waveform_min=[-0.2] * 64,
            waveform_max=[0.2] * 64,
            fft_freqs_hz=freqs.tolist(),
            fft_db=[-20.0] * 64,
            log_freqs_hz=freqs.tolist(),
            log_spectrum_db=[-20.0] * 64,
            chroma_12=[0.8, 0.1, 0.2, 0.1, 0.7, 0.3, 0.1, 0.8, 0.1, 0.5, 0.1, 0.2],
            chord=ChordEstimate("Am", "C", "High", 0.93, 0.31, False),
            key=KeyEstimate("C major", "A minor", "High", 0.91, 0.24, relation_note="平行大小调 C / Am"),
            tempo=TempoEstimate(124.0, "High", 0.84),
            pitch=PitchEstimate(440.0, "A4", +1.8, 0.95),
            rms_dbfs=-14.2,
            peak_dbfs=-3.6,
            window_seconds=2.0,
        )
        hist = np.zeros((12, 12), dtype=np.float32)

        def _collect_leaks(root: QtWidgets.QWidget) -> list[str]:
            found_leaks: list[str] = []
            if cjk_re.search(root.windowTitle()):
                found_leaks.append(f"title:{root.windowTitle()}")
            for w in root.findChildren(QtWidgets.QWidget):
                if isinstance(w, HelpBadge):
                    for s in (w._title, w._explanation):
                        if cjk_re.search(s):
                            found_leaks.append(f"help:{s[:60]}")
                elif isinstance(w, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
                    if cjk_re.search(w.text()):
                        found_leaks.append(f"lbl:{w.text()[:60]}")
                elif isinstance(w, QtWidgets.QGroupBox):
                    if cjk_re.search(w.title()):
                        found_leaks.append(f"grp:{w.title()[:60]}")
                elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                    for s in (w.prefix(), w.suffix()):
                        if cjk_re.search(s):
                            found_leaks.append(f"spin:{s}")
                elif isinstance(w, QtWidgets.QTabWidget):
                    for i in range(w.count()):
                        if cjk_re.search(w.tabText(i)):
                            found_leaks.append(f"tab:{w.tabText(i)}")
                elif isinstance(w, QtWidgets.QComboBox) and not w.property("lsKeepItems"):
                    for i in range(w.count()):
                        if cjk_re.search(w.itemText(i)):
                            found_leaks.append(f"combo:{w.itemText(i)}")
                elif isinstance(w, QtWidgets.QTableWidget):
                    for c in range(w.columnCount()):
                        hi = w.horizontalHeaderItem(c)
                        if hi and cjk_re.search(hi.text()):
                            found_leaks.append(f"hdr:{hi.text()}")
                elif isinstance(w, pg.PlotWidget):
                    pi = w.getPlotItem()
                    if pi.titleLabel.text and cjk_re.search(pi.titleLabel.text):
                        found_leaks.append(f"plot:{pi.titleLabel.text}")
                    for ax_n in ("bottom", "left"):
                        ax = pi.getAxis(ax_n)
                        if ax and ax.labelText and cjk_re.search(ax.labelText):
                            found_leaks.append(f"axis:{ax.labelText}")
            return found_leaks

        for lang in ("en", "ko"):
            ap_lang = Appearance(preset="acid_telemetry", theme_mode="light", language=lang)
            set_current_language(lang)
            mw.apply_appearance(ap_lang)
            mw.update_analysis_snapshot(snap, hist, None)
            da = AppearanceDialog(ap_lang, DARK_STYLESHEET, parent=mw)
            ds = SettingsDialog(probe_system(), ResourceLimits(), AIConfig(), appearance=ap_lang, parent=mw)
            dc = ChordPracticeDialog(
                ["Am", "F", "C", "G"],
                KeyEstimate("C major", "A minor", "High", 0.91, 0.24),
                0,
                detected_bpm=124.0,
                acid_variant="light",
                parent=mw,
            )
            app.processEvents()
            for name, win in (("MainWindow", mw), ("Appearance", da), ("Settings", ds), ("ChordPractice", dc)):
                leaks = _collect_leaks(win)
                assert leaks == [], f"{lang} leaks in {name}: {leaks}"
            dc.close()
            ds.close()
            da.close()

        dlg_set.close()
        dlg_app.close()
        set_help_mode_enabled(True)
    finally:
        set_current_language("zh")
        controller.shutdown()
        controller.window.close()
        app.processEvents()

