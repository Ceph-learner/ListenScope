"""Phase 11 tests: non-destructive CPU stem deep analysis, settings persistence, AI env probe, bounded import, Piano Roll, and scrubber."""

from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pyqtgraph as pg
import pytest
import soundfile as sf
from PySide6 import QtWidgets

from analysis.stem_analyzer import (
    analyze_bass_stem,
    analyze_drums_stem,
    analyze_melody_stem,
    analyze_stems_offline,
    export_transcription_sheet,
)
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.models import MidiNoteCandidate, MidiTranscriptionResult
from core.resource_manager import SimulationOverrides
from core.settings_store import PersistedSettings, load_settings, save_settings
from core.system_probe import probe_external_ai_environment, probe_system
from main import ListenScopeController
from ui.settings_dialog import SettingsDialog


def _write_sine_wav(path: Path, freqs: list[tuple[float, float]], *, sr: int = 48000, ch: int = 2, amp: float = 0.35) -> Path:
    parts: list[np.ndarray] = []
    for f, dur in freqs:
        n = int(round(sr * dur))
        t = np.arange(n, dtype=np.float32) / float(sr)
        if f <= 0:
            sig = np.zeros(n, dtype=np.float32)
        else:
            sig = (
                amp * np.sin(2.0 * np.pi * f * t)
                + 0.35 * amp * np.sin(2.0 * np.pi * (2.0 * f) * t)
                + 0.15 * amp * np.sin(2.0 * np.pi * (3.0 * f) * t)
            ).astype(np.float32)
        parts.append(sig)
    mono = np.concatenate(parts)
    if ch == 1:
        data = mono[:, None]
    else:
        data = np.column_stack([mono] * ch)
    sf.write(str(path), data, sr, subtype="PCM_16")
    return path


def _write_chord_progression_wav(path: Path, chords: list[tuple[list[float], float]], *, sr: int = 48000) -> Path:
    parts: list[np.ndarray] = []
    for freqs, dur in chords:
        n = int(round(sr * dur))
        t = np.arange(n, dtype=np.float32) / float(sr)
        sig = np.zeros(n, dtype=np.float32)
        for f in freqs:
            sig += (0.22 * np.sin(2.0 * np.pi * f * t)).astype(np.float32)
        parts.append(sig)
    mono = np.concatenate(parts)
    stereo = np.column_stack([mono, mono])
    sf.write(str(path), stereo, sr, subtype="PCM_16")
    return path


def _write_drums_wav(path: Path, *, bpm: float = 120.0, duration_sec: float = 4.0, sr: int = 48000) -> Path:
    n_total = int(round(duration_sec * sr))
    sig = np.zeros(n_total, dtype=np.float32)
    beat_sec = 60.0 / bpm
    eighth_sec = beat_sec * 0.5
    rng = np.random.default_rng(42)

    # Kick on beats 1 and 3
    kick_len = int(0.11 * sr)
    tk = np.arange(kick_len, dtype=np.float32) / float(sr)
    kick_wave = (0.75 * np.sin(2.0 * np.pi * 62.0 * tk) * np.exp(-tk / 0.032)).astype(np.float32)

    # Snare on beats 2 and 4 (mid-band resonant thump + filtered noise)
    snare_len = int(0.10 * sr)
    ts = np.arange(snare_len, dtype=np.float32) / float(sr)
    snare_noise = rng.normal(0.0, 1.0, snare_len).astype(np.float32)
    snare_wave = (
        (0.45 * np.sin(2.0 * np.pi * 240.0 * ts) + 0.35 * np.sin(2.0 * np.pi * 920.0 * ts) * snare_noise)
        * np.exp(-ts / 0.03)
    ).astype(np.float32)

    # Hi-hat on eighth notes (high-frequency modulated bursts > 6kHz)
    hat_len = int(0.04 * sr)
    th = np.arange(hat_len, dtype=np.float32) / float(sr)
    hat_wave = (
        0.45 * np.sin(2.0 * np.pi * 8200.0 * th) * np.cos(2.0 * np.pi * 1900.0 * th) * np.exp(-th / 0.012)
    ).astype(np.float32)

    beat_idx = 0
    while beat_idx * beat_sec + 0.15 < duration_sec:
        pos = int(round(beat_idx * beat_sec * sr))
        if beat_idx % 2 == 0:
            sig[pos : pos + kick_len] += kick_wave
        else:
            sig[pos : pos + snare_len] += snare_wave
        beat_idx += 1

    eigth_idx = 0
    while eigth_idx * eighth_sec + 0.06 < duration_sec:
        pos = int(round(eigth_idx * eighth_sec * sr))
        sig[pos : pos + hat_len] += hat_wave
        eigth_idx += 1

    sig = np.clip(sig, -0.95, 0.95).astype(np.float32)
    sf.write(str(path), np.column_stack([sig, sig]), sr, subtype="PCM_16")
    return path


def test_weak_stems_are_analyzed_without_turning_silence_into_notes(tmp_path: Path) -> None:
    bass = _write_sine_wav(tmp_path / "bass.wav", [(55.0, 2.0)], amp=0.0075)
    other = _write_chord_progression_wav(tmp_path / "other.wav", [([220.0, 277.18, 329.63], 2.0)])
    audio, rate = sf.read(other, dtype="float32")
    sf.write(other, audio * 0.025, rate, subtype="PCM_16")
    silent = _write_sine_wav(tmp_path / "silent.wav", [(0, 2.0)])
    weak = analyze_stems_offline({"other": other, "bass": bass})
    assert weak.bass is not None and weak.bass.signal_detected
    assert any(note.pitch_midi == 33 for note in weak.bass.notes)
    assert any(segment.chord.startswith("A") for segment in weak.chord_timeline)
    silence = analyze_stems_offline({"other": silent, "bass": silent})
    assert silence.bass is not None and silence.bass.signal_detected is False
    assert not silence.bass.notes
    assert silence.chord_timeline and all(segment.stability == "Silent" for segment in silence.chord_timeline)
    noise_path = tmp_path / "noise.wav"
    sf.write(noise_path, np.random.default_rng(42).normal(0, 0.0056, 96000), 48000, subtype="PCM_16")
    noise = analyze_bass_stem(noise_path)
    assert noise.signal_detected is True and not noise.notes


def test_clear_stem_results_invalidates_pending_analysis(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "workspace")
    try:
        path = _write_sine_wav(tmp_path / "bass.wav", [(55.0, 1.0)])
        mixer = ctrl.window.mixer_widget
        mixer.load_stem_paths({"bass": str(path)})
        ctrl.ring_buffer.write(np.ones((100, 2), dtype=np.float32))
        mixer.set_midi_transcribing("bass")
        assert mixer.analysis_tabs.currentIndex() == 2
        assert mixer.midi_settings_btn.isEnabled()
        generation = ctrl._stem_generation
        report = analyze_stems_offline({"bass": path})
        ctrl._ui_deep_analysis_q.put_nowait((generation, report, "old result"))
        mixer.clear_results_btn.click()
        ctrl._on_ui_tick()
        assert not mixer.clear_results_btn.isEnabled()
        assert not ctrl.mixer_engine.tracks
        assert ctrl._latest_deep_report is None and ctrl._stem_generation == generation + 1
        assert ctrl.ring_buffer.total_written_frames == 100 and path.exists()
    finally:
        ctrl.shutdown()
        ctrl.window.close()
        app.processEvents()


def test_settings_navigation_keeps_draft_edits_and_midi_focus() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dlg = SettingsDialog(probe_system(), ResourceLimits(), AIConfig())
    dlg.show()
    app.processEvents()
    try:
        assert dlg._active_category == "appearance"
        assert dlg._category_buttons["appearance"].isChecked()
        dlg._category_buttons["resources"].click()
        dlg.min_ram_spin.setValue(6000)
        assert dlg._category_buttons["resources"].isChecked()
        dlg.focus_midi()
        assert dlg._active_category == "midi"
        assert dlg.focusWidget() is dlg.midi_python_edit
        dlg.midi_python_edit.setText("draft.exe")
        dlg.open_category("resources")
        assert dlg.min_ram_spin.value() == 6000
        dlg.open_category("midi")
        assert dlg.midi_python_edit.text() == "draft.exe"
        dlg.open_category("midi")
        dlg.resize(560, 500)
        app.processEvents()
        assert dlg.width() == 560 and all(button.isVisible() for button in dlg._category_buttons.values())
        assert dlg.midi_python_edit.width() >= 180
        dlg.reject()
        assert dlg.updated_limits is None
        assert dlg.updated_midi_python == ""
    finally:
        dlg.close()


def test_settings_store_persistence_and_safety_invariants(tmp_path: Path) -> None:
    s_path = tmp_path / "cfg" / "settings.json"
    # Missing file falls back safely
    initial = load_settings(s_path)
    assert initial.resource_limits.max_concurrent_ai_jobs == 1
    assert initial.resource_limits.max_loaded_models == 1

    custom = PersistedSettings(
        resource_limits=ResourceLimits(min_ram_before_ai_mb=5600.0, min_vram_2stem_mb=2400.0),
        ai_config=AIConfig(long_audio_chunk_seconds=18.0, allow_experimental_roformer=True),
        ai_python_executable=sys.executable,
    )
    save_settings(custom, s_path)
    loaded = load_settings(s_path)
    assert loaded.resource_limits.min_ram_before_ai_mb == 5600.0
    assert loaded.resource_limits.min_vram_2stem_mb == 2400.0
    assert loaded.ai_config.long_audio_chunk_seconds == 18.0
    assert loaded.ai_config.allow_experimental_roformer is True
    assert loaded.ai_python_executable == sys.executable

    # Tampered parallel counts are forcibly clamped back to strict serial invariants
    tampered = json.loads(s_path.read_text(encoding="utf-8"))
    tampered["resource_limits"]["max_concurrent_ai_jobs"] = 4
    tampered["resource_limits"]["max_loaded_models"] = 3
    tampered["ai_config"]["demucs_jobs"] = 8
    tampered["ai_config"]["demucs_shifts"] = 5
    s_path.write_text(json.dumps(tampered), encoding="utf-8")

    clamped = load_settings(s_path)
    assert clamped.resource_limits.max_concurrent_ai_jobs == 1
    assert clamped.resource_limits.max_loaded_models == 1
    assert clamped.ai_config.demucs_jobs == 1
    assert clamped.ai_config.demucs_shifts == 1

    # Corrupt JSON falls back cleanly without throwing
    s_path.write_text("{corrupt json", encoding="utf-8")
    recovered = load_settings(s_path)
    assert recovered.resource_limits.max_concurrent_ai_jobs == 1


def test_probe_external_ai_environment_success_and_missing() -> None:
    res_ok = probe_external_ai_environment(sys.executable, timeout_sec=20.0)
    assert res_ok["ok"] is True
    assert res_ok["python_executable"] == sys.executable
    pkgs = res_ok["ai_packages"]
    for key in ("demucs", "audio_separator", "basic_pitch", "onnxruntime", "soundfile", "mido"):
        assert key in pkgs
    assert pkgs["soundfile"]["installed"] is True
    assert pkgs["mido"]["installed"] is True

    res_bad = probe_external_ai_environment("/nonexistent/listenscope/python_missing")
    assert res_bad["ok"] is False
    assert "找不到 Python" in res_bad["error"]


def test_ring_buffer_streaming_audio_import_resampling_and_truncation(tmp_path: Path) -> None:
    rb = FixedRingBuffer(audio_config=AudioConfig())
    assert rb.sample_rate == 48000

    # 3.0s 44.1kHz stereo WAV imported with 1.5s cap -> truncates strictly and resamples cleanly
    wav_long = _write_sine_wav(tmp_path / "long_44k.wav", [(440.0, 3.0)], sr=44100, ch=2)
    imported_sec, truncated = rb.import_audio_file_streaming(wav_long, max_seconds=1.5, chunk_seconds=0.5)
    assert truncated is True
    assert imported_sec == pytest.approx(1.5, abs=0.05)
    assert rb.available_seconds == pytest.approx(1.5, abs=0.05)

    # Short 1.0s mono 44.1kHz file -> not truncated and upmixed to stereo 48kHz
    wav_short = _write_sine_wav(tmp_path / "short_44k_mono.wav", [(440.0, 1.0)], sr=44100, ch=1)
    imported_short, truncated_short = rb.import_audio_file_streaming(wav_short, max_seconds=10.0, chunk_seconds=0.5)
    assert truncated_short is False
    assert imported_short == pytest.approx(1.0, abs=0.05)
    newest = rb.total_written_frames
    pcm = rb.read_range(max(0, newest - 48000), newest)
    assert pcm.shape[1] == 2
    assert float(np.max(np.abs(pcm))) > 0.1


def test_deep_stem_analyzer_bass_drums_melody_chords_and_export(tmp_path: Path) -> None:
    # Bass: 1.0s E1 (41.20 Hz, MIDI 28) -> 1.0s A2 (110.0 Hz, MIDI 45)
    bass_wav = _write_sine_wav(tmp_path / "bass.wav", [(41.20, 1.0), (110.0, 1.0)])
    bass_res = analyze_bass_stem(bass_wav)
    assert bass_res.lowest_note == "E1"
    assert bass_res.highest_note == "A2"
    assert "E" in bass_res.root_pitch_classes and "A" in bass_res.root_pitch_classes

    # Drums: 120 BPM Kick / Snare / Hi-Hat pattern
    drums_wav = _write_drums_wav(tmp_path / "drums.wav", bpm=120.0, duration_sec=4.0)
    drums_res = analyze_drums_stem(drums_wav)
    assert len(drums_res.kick_times_sec) >= 3
    assert len(drums_res.snare_times_sec) >= 3
    assert len(drums_res.hihat_times_sec) >= 10
    assert drums_res.estimated_bpm is not None
    assert 115.0 <= drums_res.estimated_bpm <= 125.0
    assert len(drums_res.groove_16_step) == 16

    # Melody: C4 (261.63 Hz) -> G4 (392.00 Hz)
    vocals_wav = _write_sine_wav(tmp_path / "vocals.wav", [(261.63, 1.0), (392.00, 1.0)])
    mel_res = analyze_melody_stem(vocals_wav, stem_name="vocals")
    assert mel_res.lowest_note == "C4"
    assert mel_res.highest_note == "G4"
    assert mel_res.voiced_ratio > 0.5

    # Harmony (`other`): C -> Am -> F -> G progression (each 1.0s)
    other_wav = _write_chord_progression_wav(
        tmp_path / "other.wav",
        [
            ([261.63, 329.63, 392.00], 1.0),  # C
            ([220.00, 261.63, 329.63], 1.0),  # Am
            ([174.61, 220.00, 261.63], 1.0),  # F
            ([196.00, 246.94, 293.66], 1.0),  # G
        ],
    )
    # Match duration on bass/vocals over 4.0s for unified 4-stem run
    bass_4s = _write_sine_wav(tmp_path / "bass4.wav", [(130.81, 1.0), (110.0, 1.0), (87.31, 1.0), (98.00, 1.0)])

    report = analyze_stems_offline(
        {
            "other": other_wav,
            "bass": bass_4s,
            "drums": drums_wav,
            "vocals": vocals_wav,
        }
    )
    detected_chords = {seg.chord for seg in report.chord_timeline}
    assert "C" in detected_chords
    assert "Am" in detected_chords
    assert report.estimated_key.primary in ("C major", "A minor")
    assert report.estimated_bpm.bpm is not None

    midi_dummy = MidiTranscriptionResult(
        source_stem_name="bass",
        output_midi_path=tmp_path / "bass.mid",
        notes=[MidiNoteCandidate(pitch_midi=45, note_name="A2", start_sec=0.0, end_sec=0.8, velocity=96, confidence=0.9)],
        backend_used="cpu-pitch-fallback",
    )
    md_out = export_transcription_sheet(report, tmp_path / "sheet.md", midi_result=midi_dummy)
    md_text = md_out.read_text(encoding="utf-8")
    assert "# ListenScope" in md_text
    assert "| 开始 (s) |" in md_text
    assert "`C`" in md_text

    csv_out = export_transcription_sheet(report, tmp_path / "sheet.csv", midi_result=midi_dummy)
    with csv_out.open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][0] == "section"
    sections = {r[0] for r in rows[1:]}
    assert {"chord", "bass", "drum_kick", "midi"}.issubset(sections)


def test_phase11_headless_gui_workstation_integration(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_file = tmp_path / "persist" / "settings.json"
    ws1 = tmp_path / "ws1"

    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=ws1, settings_path=settings_file)
    ctrl.resource_manager.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))

    try:
        ctrl.window.show()
        # 1. Settings persistence round-trip via _on_settings_applied
        new_limits = ResourceLimits(min_ram_before_ai_mb=5400.0)
        new_ai_cfg = AIConfig(long_audio_chunk_seconds=20.0)
        ctrl._on_settings_applied(new_limits, new_ai_cfg, sys.executable)
        assert settings_file.exists()

        # 2. SettingsDialog inline AI environment verifier test
        hw_rep = probe_system()
        dlg = SettingsDialog(hw_rep, new_limits, new_ai_cfg, ai_python_executable=sys.executable, parent=ctrl.window)
        dlg._verify_ai_environment()
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not dlg.verify_ai_env_btn.isEnabled():
            app.processEvents()
            time.sleep(0.03)
        assert dlg.verify_ai_env_btn.isEnabled()
        assert "AI 包:" in dlg.ai_probe_result_lbl.text()
        dlg.close()

        # 3. Start synthetic capture and confirm non-destructive deep stem analysis
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})
        deadline = time.monotonic() + 0.35
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        frames_before_deep = ctrl.ring_buffer.total_written_frames
        assert frames_before_deep > 0

        # Prepare separated stem WAVs in tmp_path
        stems = {
            "other": str(
                _write_chord_progression_wav(
                    tmp_path / "sep_other.wav",
                    [([261.63, 329.63, 392.00], 1.2), ([220.00, 261.63, 329.63], 1.2)],
                )
            ),
            "bass": str(_write_sine_wav(tmp_path / "sep_bass.wav", [(65.41, 1.2), (110.0, 1.2)])),
            "drums": str(_write_drums_wav(tmp_path / "sep_drums.wav", bpm=120.0, duration_sec=2.4)),
            "vocals": str(_write_sine_wav(tmp_path / "sep_vocals.wav", [(261.63, 1.2), (329.63, 1.2)])),
        }
        mw = ctrl.window.mixer_widget
        mw.load_stem_paths(stems)
        assert mw.deep_analyze_btn.isEnabled() is True
        assert mw.export_sheet_btn.isEnabled() is False

        # Trigger non-destructive deep analysis
        ctrl._on_deep_analyze_stems(stems)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and ctrl._latest_deep_report is None:
            app.processEvents()
            time.sleep(0.03)
        app.processEvents()
        assert ctrl._latest_deep_report is not None
        assert mw.chord_timeline_table.rowCount() >= 1
        assert mw.export_sheet_btn.isEnabled() is True
        # Non-destructive guarantee: live capture continues advancing ring buffer!
        assert ctrl.ring_buffer.total_written_frames >= frames_before_deep
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running

        # 4. Trigger MIDI transcription -> verifies horizontal Piano Roll BarGraphItem & Save As
        ctrl._on_transcribe_stem_midi("bass", stems["bass"])
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and ctrl._latest_midi_result is None:
            app.processEvents()
            time.sleep(0.03)
        app.processEvents()
        assert ctrl._latest_midi_result is not None
        assert isinstance(mw._piano_roll_item, pg.BarGraphItem)
        assert mw.save_midi_btn.isEnabled() is True

        # Export sheet & save MIDI as
        sheet_out = tmp_path / "exports" / "sheet.md"
        ctrl._on_export_transcription_sheet(str(sheet_out))
        assert sheet_out.exists()
        midi_copy = tmp_path / "exports" / "copied_bass.mid"
        ctrl._on_save_midi_as(str(midi_copy))
        assert midi_copy.exists() and midi_copy.stat().st_size > 0

        # 5. Mixer seek scrubber sync check
        assert ctrl.mixer_engine.max_frames > 0
        mid_frame = ctrl.mixer_engine.max_frames // 2
        ctrl.mixer_engine.seek(mid_frame)
        ctrl.window.sync_mixer_position()
        assert 400 <= mw.seek_slider.value() <= 600

        # 6. Bounded local audio import via controller
        local_wav = _write_sine_wav(tmp_path / "local_import.wav", [(440.0, 2.0)], sr=44100, ch=2)
        ctrl._on_import_audio_file(str(local_wav))
        app.processEvents()
        assert 1.8 <= ctrl.ring_buffer.available_seconds <= 2.2
        assert ctrl.ab_player.loop_range[1] > ctrl.ab_player.loop_range[0]
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()

    # Verify a fresh controller reloads persisted settings cleanly
    ctrl2 = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws2", settings_path=settings_file)
    try:
        assert ctrl2.resource_limits.min_ram_before_ai_mb == 5400.0
        assert ctrl2.ai_config.long_audio_chunk_seconds == 20.0
        assert ctrl2.ai_job_manager.ai_python_executable == sys.executable
    finally:
        ctrl2.window.close()
        ctrl2.shutdown()
        ctrl2 = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()
