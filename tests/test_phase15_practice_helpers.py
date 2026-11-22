"""Phase 15 tests: chord-tone spelling, TuningCentsBar needle, 1-bar count-in pre-roll, volume slider, and A/B quick-nudge."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import soundfile as sf
from PySide6 import QtCore, QtWidgets

from audio.metronome import PracticeMetronome
from audio.playback import HistoryABPlayer, StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from core.config import AudioConfig
from core.models import (
    AnalysisSnapshot,
    ChordEstimate,
    ChordTimelineSegment,
    KeyEstimate,
    PitchEstimate,
    StemDeepAnalysisReport,
    TempoEstimate,
)
from main import ListenScopeController
from ui.chroma_widget import ChromaAndHarmonyWidget, TuningCentsBar, spell_chord_tones
from ui.mixer_widget import StemMixerWidget


def _ensure_qapp() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def test_spell_chord_tones_comprehensive() -> None:
    assert spell_chord_tones("C") == "C · E · G"
    assert spell_chord_tones("Cmaj") == "C · E · G"
    assert spell_chord_tones("Am") == "A · C · E"
    assert spell_chord_tones("F#m") == "F# · A · C#"
    assert spell_chord_tones("Cmaj7") == "C · E · G · B"
    assert spell_chord_tones("Am7") == "A · C · E · G"
    assert spell_chord_tones("G7") == "G · B · D · F"
    assert spell_chord_tones("Dsus4") == "D · G · A"
    assert spell_chord_tones("Asus2") == "A · B · E"
    assert spell_chord_tones("Bdim") == "B · D · F"
    assert spell_chord_tones("Caug") == "C · E · G#"

    # Flats & enharmonic normalization (diatonic letter spelling)
    assert spell_chord_tones("Db") == "Db · F · Ab"
    assert spell_chord_tones("Bbm") == "Bb · Db · F"
    assert spell_chord_tones("Eb7") == "Eb · G · Bb · Db"
    assert spell_chord_tones("Cb") == "Cb · Eb · Gb"
    assert spell_chord_tones("E#m") == "E# · G# · B#"

    # Slash chords & empty/unknown tokens
    assert spell_chord_tones("C/G") == "C · E · G"
    assert spell_chord_tones("N (静音)") == "-"
    assert spell_chord_tones("Unknown") == "-"
    assert spell_chord_tones("-") == "-"
    assert spell_chord_tones("") == "-"
    assert spell_chord_tones("结束") == "-"
    assert spell_chord_tones("InvalidChordXYZ") == "-"


def test_tuning_cents_bar_and_chroma_widget_sync() -> None:
    _ensure_qapp()
    bar = TuningCentsBar()
    assert bar.has_signal is False
    assert bar.zone_color == TuningCentsBar.COLOR_IDLE

    # Green zone (<= ±10 cents)
    bar.set_pitch(440.0, 5.0)
    assert bar.has_signal is True
    assert bar.cents_offset == pytest.approx(5.0)
    assert bar.zone_color == TuningCentsBar.COLOR_IN_TUNE

    # Amber zone (10 < |c| <= 25)
    bar.set_pitch(440.0, 18.0)
    assert bar.zone_color == TuningCentsBar.COLOR_SLIGHT

    # Red zone (> 25) and clamping
    bar.set_pitch(440.0, -72.0)
    assert bar.cents_offset == pytest.approx(-50.0)
    assert bar.zone_color == TuningCentsBar.COLOR_OFF

    # Exercise paintEvent offscreen safely
    bar.resize(220, 18)
    px = bar.grab()
    assert not px.isNull()

    # NaN / invalid clears back to idle
    bar.set_pitch(float("nan"), 10.0)
    assert bar.has_signal is False
    assert bar.zone_color == TuningCentsBar.COLOR_IDLE

    widget = ChromaAndHarmonyWidget()
    snap = AnalysisSnapshot(
        timestamp=1.0,
        waveform_min=[-0.2, -0.1],
        waveform_max=[0.2, 0.1],
        fft_freqs_hz=[100.0, 200.0],
        fft_db=[-40.0, -35.0],
        log_freqs_hz=[100.0, 200.0],
        log_spectrum_db=[-40.0, -35.0],
        chroma_12=[0.1] * 12,
        chord=ChordEstimate(primary="Am7", secondary="C", stability="High", correlation=0.91, margin=0.14),
        key=KeyEstimate(primary="C major", secondary="A minor", stability="Moderate", correlation=0.82, margin=0.09),
        tempo=TempoEstimate(bpm=124.0, stability="Moderate", confidence_score=0.68),
        pitch=PitchEstimate(frequency_hz=441.0, note_name="A4", cents_offset=+3.5, confidence=0.92),
        rms_dbfs=-18.0,
        peak_dbfs=-10.0,
        window_seconds=2.0,
    )
    widget.update_analysis(snap)
    assert widget.chord_tones_lbl.text() == "构成音: A · C · E · G"
    assert widget.tuning_bar.has_signal is True
    assert widget.tuning_bar.zone_color == TuningCentsBar.COLOR_IN_TUNE

    widget.clear_progression()
    assert widget.chord_tones_lbl.text() == "构成音: -"
    assert widget.tuning_bar.has_signal is False
    assert widget.tuning_bar.zone_color == TuningCentsBar.COLOR_IDLE
    widget.close()


def test_metronome_count_in_exact_bar_and_fractional_bpm_clicks() -> None:
    # Exact 120 BPM, 4/4 -> 96000 frames @ 48kHz, even when overlay_enabled=False
    met = PracticeMetronome(sample_rate=48000, channels=2)
    met.set_bpm(120.0)
    met.set_beats_per_bar(4)
    met.set_overlay_enabled(False)
    met.set_count_in_enabled(True)
    met.set_volume(1.0)

    total_frames = met.begin_count_in(rate_scale=1.0)
    assert total_frames == 96000
    assert met.is_counting_in is True

    consumed = 0
    while met.is_counting_in:
        blk, n = met.consume_count_in_block(4096, rate_scale=1.0)
        assert n > 0
        assert blk.shape == (n, 2)
        consumed += n
    assert consumed == 96000
    assert met.is_counting_in is False

    # Fractional BPM double-trigger guard: 123.7 BPM in 3/4 must produce strictly 3 click onsets (never 4)
    met_frac = PracticeMetronome(sample_rate=48000, channels=2)
    met_frac.set_bpm(123.7)
    met_frac.set_beats_per_bar(3)
    met_frac.set_volume(1.0)
    met_frac.set_count_in_enabled(True)
    bar_n = met_frac.begin_count_in(rate_scale=1.0)
    assert bar_n > 0

    chunks = []
    while met_frac.is_counting_in:
        blk, n = met_frac.consume_count_in_block(512, rate_scale=1.0)
        chunks.append(blk[:n, 0])
    full = np.concatenate(chunks)
    assert full.shape[0] == bar_n

    # Count distinct rising beat attack transients (peaks above 0.25 separated by > 0.15s)
    onset_indices = []
    i = 0
    min_gap = int(0.15 * 48000)
    abs_sig = np.abs(full)
    while i < len(abs_sig):
        if abs_sig[i] > 0.25:
            onset_indices.append(i)
            i += min_gap
        else:
            i += 1
    assert len(onset_indices) == 3

    # set_count_in_enabled(False) clears active count-in
    met_frac.begin_count_in(rate_scale=1.0)
    assert met_frac.is_counting_in is True
    met_frac.set_count_in_enabled(False)
    assert met_frac.is_counting_in is False
    assert met_frac.count_in_remaining_frames == 0


def test_history_ab_player_count_in_preroll_and_wsola() -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10.0)
    rb = FixedRingBuffer(audio_config=cfg)
    # Use constant DC signal (0.25) so click transients & music entry frame are crystal clear
    music = np.full((48000 * 3, 2), 0.25, dtype=np.float32)
    rb.write(music)

    met = PracticeMetronome(sample_rate=48000, channels=2)
    met.set_bpm(120.0)
    met.set_beats_per_bar(4)
    met.set_overlay_enabled(False)
    met.set_count_in_enabled(True)
    met.set_volume(0.8)

    player = HistoryABPlayer(rb, audio_config=cfg, metronome=met)
    player.select_recent_seconds(2.0)
    player.start_playback(open_audio_device=False)

    # 96000 frames is NOT a multiple of 4096 (96000 = 23*4096 + 1792) -> exercises mid-block handoff
    blocks = [player.render_block(4096) for _ in range(25)]
    rendered = np.concatenate(blocks, axis=0)

    # Beat 3 click occurs at 48000..49344; gap 52000..60000 must be silent between clicks
    assert float(np.max(np.abs(rendered[48000:49500, 0]))) > 0.1
    tail_between_clicks = rendered[52000:60000, 0]
    assert float(np.max(np.abs(tail_between_clicks))) < 1e-4

    # Music starts cleanly right at sample 96000
    assert rendered[95999, 0] == pytest.approx(0.0, abs=1e-4)
    assert rendered[96000, 0] == pytest.approx(0.25, abs=1e-4)

    # Verify speed=0.75x scales count-in bar to 128000 frames before WSOLA music enters
    player.stop()
    assert met.is_counting_in is False
    player.set_speed(0.75)
    player.start_playback(open_audio_device=False)
    expected_ci = met.count_in_bar_frames(rate_scale=0.75)
    assert expected_ci == 128000
    wsola_blocks = [player.render_block(4096) for _ in range(33)]
    wsola_audio = np.concatenate(wsola_blocks, axis=0)
    assert wsola_audio[127999, 0] == pytest.approx(0.0, abs=1e-4)
    assert float(np.mean(np.abs(wsola_audio[128200:130000, 0]))) > 0.10

    # Seek must cancel any remaining count-in immediately
    player.start_playback(open_audio_device=False)
    assert met.is_counting_in is True
    player.seek(player.loop_range[0] + 1000)
    assert met.is_counting_in is False
    player.stop()


def test_stem_mixer_engine_count_in_and_advance_false(tmp_path: Path) -> None:
    sr = 48000
    dur_frames = sr * 2
    bass = np.full((dur_frames, 2), 0.30, dtype=np.float32)
    vocals = np.full((dur_frames, 2), 0.15, dtype=np.float32)
    bass_wav = tmp_path / "bass.wav"
    vocals_wav = tmp_path / "vocals.wav"
    sf.write(str(bass_wav), bass, sr, subtype="PCM_16")
    sf.write(str(vocals_wav), vocals, sr, subtype="PCM_16")

    met = PracticeMetronome(sample_rate=sr, channels=2)
    met.set_bpm(120.0)
    met.set_beats_per_bar(4)
    met.set_overlay_enabled(False)
    met.set_count_in_enabled(True)
    met.set_volume(0.8)

    mixer = StemMixerEngine(sample_rate=sr, channels=2, metronome=met)
    mixer.load_stems({"bass": bass_wav, "vocals": vocals_wav})
    mixer.play(open_audio_device=False)
    assert met.count_in_remaining_frames == 96000

    # advance=False peek MUST NOT consume count-in or move playback position
    peek = mixer.render_block(512, advance=False)
    assert met.count_in_remaining_frames == 96000
    assert mixer.position_frame == 0
    assert peek[0, 0] == pytest.approx(0.45, abs=1e-3)

    # Render across the 96000-frame boundary in 10000-frame blocks (9 full + 1 split block)
    blocks = [mixer.render_block(10000, advance=True) for _ in range(11)]
    audio = np.concatenate(blocks, axis=0)
    assert audio[95999, 0] == pytest.approx(0.0, abs=1e-4)
    assert audio[96000, 0] == pytest.approx(0.45, abs=1e-3)
    assert mixer.position_frame == 14000

    # Test 0.75x WSOLA path with count-in + cancel on pause
    mixer.stop()
    assert met.is_counting_in is False
    mixer.set_speed(0.75)
    mixer.play(open_audio_device=False)
    assert met.count_in_remaining_frames == 128000
    first_blk = mixer.render_block(4096, advance=True)
    assert first_blk.shape == (4096, 2)
    assert mixer.position_frame == 0
    assert met.count_in_remaining_frames == 128000 - 4096
    mixer.pause()
    assert met.is_counting_in is False
    mixer.clear()


def test_ab_quick_nudge_clamping_and_controller_metronome_wiring(tmp_path: Path) -> None:
    _ensure_qapp()
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        ai_python_executable="",
        work_dir=tmp_path / "work",
        settings_path=tmp_path / "work" / "settings.json",
    )
    try:
        # Fill 45s into ring buffer
        tone = np.full((48000 * 45, 2), 0.1, dtype=np.float32)
        ctrl.ring_buffer.write(tone)

        w = ctrl.window
        # Verify mixer chord HUD renders chord tones gracefully
        mw: StemMixerWidget = w.mixer_widget
        mw._chord_segments = [
            ChordTimelineSegment(start_sec=0.0, end_sec=1.0, chord="C", secondary="Am", correlation=0.9, stability="High"),
            ChordTimelineSegment(start_sec=1.0, end_sec=2.0, chord="G", secondary="Em", correlation=0.9, stability="High"),
        ]
        mw.sync_playback_position()
        assert "C · E · G" in mw.live_chord_hud_lbl.text()
        assert "G" in mw.live_chord_hud_lbl.text()

        # Verify metronome volume slider & count-in checkbox wiring
        w.chroma_widget.metronome_vol_slider.setValue(115)
        assert ctrl.metronome.volume == pytest.approx(1.15, abs=1e-4)
        assert w.chroma_widget.metronome_vol_lbl.text() == "音量: 115%"

        w.chroma_widget.metronome_count_in_chk.setChecked(True)
        assert ctrl.metronome.count_in_enabled is True

        # Verify A/B quick nudge controls & bounds clamping
        w.start_ago_spin.setValue(10.0)
        w.end_ago_spin.setValue(2.0)
        w.apply_ab_btn.click()
        assert ctrl.ab_player.loop_range == (
            48000 * (45 - 10),
            48000 * (45 - 2),
        )

        # A-1s widens start to 11.0s ago
        w.ab_a_back_btn.click()
        assert w.start_ago_spin.value() == pytest.approx(11.0, abs=1e-2)
        assert w.end_ago_spin.value() == pytest.approx(2.0, abs=1e-2)

        # A+1s shifts start back to 10.0s ago
        w.ab_a_fwd_btn.click()
        assert w.start_ago_spin.value() == pytest.approx(10.0, abs=1e-2)

        # B+1s moves B closer to 0s (end_ago goes from 2.0 -> 1.0)
        w.ab_b_fwd_btn.click()
        assert w.end_ago_spin.value() == pytest.approx(1.0, abs=1e-2)
        # B+1s twice clamps cleanly at 0.0
        w.ab_b_fwd_btn.click()
        w.ab_b_fwd_btn.click()
        assert w.end_ago_spin.value() == pytest.approx(0.0, abs=1e-2)

        # Clamping prevents A and B crossing (< 0.5s gap)
        w.start_ago_spin.setValue(0.8)
        w.end_ago_spin.setValue(0.0)
        w.ab_a_fwd_btn.click()
        assert w.start_ago_spin.value() == pytest.approx(0.5, abs=1e-2)
        assert w.start_ago_spin.value() - w.end_ago_spin.value() >= 0.5

        w.start_ago_spin.setValue(1.0)
        w.end_ago_spin.setValue(0.2)
        w.ab_b_back_btn.click()
        assert w.end_ago_spin.value() == pytest.approx(0.5, abs=1e-2)

        # Manual invalid spinbox values normalize cleanly on apply
        w.start_ago_spin.setValue(4.0)
        w.end_ago_spin.setValue(8.0)
        w.apply_ab_btn.click()
        assert w.end_ago_spin.value() <= w.start_ago_spin.value() - 0.5
        lo, hi = w.ab_region.getRegion()
        assert -lo == pytest.approx(w.start_ago_spin.value(), abs=1e-2)
        assert -hi == pytest.approx(w.end_ago_spin.value(), abs=1e-2)
    finally:
        ctrl.shutdown()
        w.close()
