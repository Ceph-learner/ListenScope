"""Offline harmony recommendation invariants, MIDI export, synthesis, and native dialog audition lifecycle."""

import sys
from pathlib import Path
from types import SimpleNamespace

import mido
import numpy as np
import pytest
from PySide6 import QtWidgets

from analysis.chord_practice import (
    PRACTICE_KEYS,
    chord_midi_notes,
    export_chord_progression_midi,
    practice_key,
    recommend_progressions,
    render_chord_progression_preview,
    sounding_chord_progression,
)
from analysis.chords import chord_scale_degree
from core.models import CaptureMode, CaptureStats, DrumsAnalysisResult, KeyEstimate, StemDeepAnalysisReport, TempoEstimate
from main import ListenScopeController
from ui.chord_practice import ChordPracticeDialog


class CallbackStop(Exception):
    pass


class FakeStream:
    def __init__(self, callback, **_):
        self.callback = callback
        self.active = False
        self.closed = False
        self.aborted = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def abort(self):
        self.active = False
        self.aborted = True

    def close(self):
        self.closed = True


def _extract_midi_note_spans(midi_path: Path):
    midi = mido.MidiFile(midi_path)
    abs_tick = 0
    active_starts = {}
    spans = []
    set_tempo = None
    channels = set()
    event_order = []
    for msg in midi.tracks[0]:
        abs_tick += msg.time
        if msg.type == "set_tempo":
            set_tempo = msg.tempo
        elif msg.type == "program_change":
            channels.add(msg.channel)
        elif msg.type == "note_on" and msg.velocity > 0:
            channels.add(msg.channel)
            event_order.append((abs_tick, "on", msg.note))
            active_starts[(msg.channel, msg.note)] = abs_tick
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            channels.add(msg.channel)
            event_order.append((abs_tick, "off", msg.note))
            start_tick = active_starts.pop((msg.channel, msg.note))
            spans.append((start_tick, abs_tick, msg.note, msg.channel))
    assert not active_starts
    return midi, set_tempo, channels, spans, event_order


def test_practice_matches_recent_prefix_and_keeps_diatonic_spelling():
    result = recommend_progressions("F major", ["F", "C7", "Dm"])[0]
    assert result.chords == ("F", "C", "Dm", "Bb")
    assert result.degrees == ("I", "V", "vi", "IV")
    assert result.matched_steps == 3
    result = recommend_progressions("A minor", ["Am", "F", "C", "G"])[0]
    assert result.degrees == ("i", "VI", "III", "VII")
    assert result.matched_steps == 4
    assert practice_key("C# major") == "Db major"


def test_practice_templates_are_valid_in_all_keys_and_ignore_broken_prefixes():
    assert len(PRACTICE_KEYS) == 24
    for key in PRACTICE_KEYS:
        for template in recommend_progressions(key, []):
            assert tuple(chord_scale_degree(chord, key) for chord in template.chords) == template.degrees
    assert not recommend_progressions("Unknown", ["C"])
    interrupted = recommend_progressions("C major", ["C", "F#", "G"])
    assert all(result.matched_steps < 2 for result in interrupted)


def test_sounding_chord_progression_and_midi_export_invariants(tmp_path: Path, monkeypatch):
    # Capo -2: displaying C-G-Am-F corresponds to concert sounding D-A-Bm-G (not transposed twice to Bb).
    assert sounding_chord_progression(("C", "G", "Am", "F"), -2) == ("D", "A", "Bm", "G")
    assert sounding_chord_progression(("C", "G", "Am", "F"), 0) == ("C", "G", "Am", "F")
    assert chord_midi_notes("C/E") == (52, 60, 64, 67)
    with pytest.raises(ValueError):
        chord_midi_notes("N")

    out_mid = tmp_path / "prog.mid"
    count = export_chord_progression_midi(("G", "Em", "C", "D"), out_mid, bpm=96.0, beats_per_chord=4)
    assert count == 4

    midi, tempo, channels, spans, order = _extract_midi_note_spans(out_mid)
    assert midi.type == 0
    assert midi.ticks_per_beat == 480
    assert channels == {0}  # melodic channel, never GM drum channel 9
    assert round(mido.tempo2bpm(tempo), 2) == pytest.approx(96.0, abs=0.05)

    expected_chords = [chord_midi_notes(ch) for ch in ("G", "Em", "C", "D")]
    chord_ticks = 4 * midi.ticks_per_beat
    for idx, chord_notes in enumerate(expected_chords):
        seg = sorted(n for s, e, n, ch in spans if s == idx * chord_ticks and e == (idx + 1) * chord_ticks and ch == 0)
        assert tuple(seg) == chord_notes

    # Shared tone G4 (67) and B4 (71) between G -> Em must turn off before re-striking at tick=chord_ticks
    at_boundary = [(kind, note) for tick, kind, note in order if tick == chord_ticks]
    assert at_boundary.index(("off", 67)) < at_boundary.index(("on", 67))
    assert at_boundary.index(("off", 71)) < at_boundary.index(("on", 71))

    # Atomic replace failure preserves existing destination file and cleans .mid.tmp
    original_bytes = out_mid.read_bytes()
    def fail_replace(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="disk full"):
        export_chord_progression_midi(("C", "F"), out_mid, bpm=120.0)
    assert out_mid.read_bytes() == original_bytes
    assert not list(tmp_path.glob("*.mid.tmp"))


def test_practice_preview_synthesis_matches_timing_bounds_and_pitches():
    sr = 8000
    pcm = render_chord_progression_preview(("D", "A"), sr, bpm=120.0, beats_per_chord=4)
    # 2 chords * 4 beats @ 120 BPM = 4.0 seconds
    assert pcm.shape == (4 * sr,)
    assert pcm.dtype == np.float32
    assert pcm[0] == 0.0 and pcm[-1] == 0.0
    assert np.max(np.abs(pcm)) <= 0.65
    np.testing.assert_array_equal(render_chord_progression_preview(("D", "A"), sr, bpm=120.0), pcm)
    assert render_chord_progression_preview((), sr).size == 0

    # Verify spectral peaks match concert sounding pitches D4 (293.66 Hz) vs A4 (440.0 Hz)
    seg_a = pcm[: 2 * sr]
    seg_b = pcm[2 * sr :]
    freqs = np.fft.rfftfreq(seg_a.size, d=1.0 / sr)
    mag_a = np.abs(np.fft.rfft(seg_a))
    mag_b = np.abs(np.fft.rfft(seg_b))
    peak_hz_a = float(freqs[int(np.argmax(mag_a))])
    peak_hz_b = float(freqs[int(np.argmax(mag_b))])
    assert any(abs(peak_hz_a - target) < 6.0 for target in (293.66, 369.99, 440.0))
    assert any(abs(peak_hz_b - target) < 6.0 for target in (440.0, 554.37, 659.25))


def test_practice_dialog_applies_capo_once_exports_sounding_midi_and_handles_cancel(tmp_path: Path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    high = KeyEstimate("D major", "B minor", "High", 0.9, 0.15)
    dialog = ChordPracticeDialog(["D", "A", "Bm"], high, -2, bpm=108.0, detected_bpm=108.0)
    assert dialog._key.currentData() == "C major"
    assert dialog._results.item(0, 1).text() == "C → G → Am → F"
    assert "3 步" in dialog._results.item(0, 2).text()
    assert dialog.sounding_chords() == ("D", "A", "Bm", "G")
    assert "D → A → Bm → G" in dialog._convention_lbl.text()

    # Cancel save dialog leaves disk untouched
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *_args, **_kw: ("", ""))
    dialog._export_midi_btn.click()
    assert dialog._feedback_lbl.property("tone") == "info"

    # Accept save dialog without extension -> auto .mid and exports concert D -> A -> Bm -> G at 108 BPM
    target_no_ext = tmp_path / "practice_capo2"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *_args, **_kw: (str(target_no_ext), ""))
    dialog._export_midi_btn.click()
    saved_mid = target_no_ext.with_suffix(".mid")
    assert saved_mid.exists()
    assert dialog._feedback_lbl.property("tone") == "ok"

    _midi, tempo, channels, spans, _order = _extract_midi_note_spans(saved_mid)
    assert channels == {0}
    assert round(mido.tempo2bpm(tempo), 2) == pytest.approx(108.0, abs=0.05)
    first_chord_notes = tuple(sorted(n for s, _e, n, _ch in spans if s == 0))
    assert first_chord_notes == chord_midi_notes("D")

    key = dialog._key.findData("A minor")
    dialog._key.setCurrentIndex(key)
    dialog._key.activated.emit(key)
    assert "手动" in dialog._status.text()
    dialog.close()

    uncertain = KeyEstimate("D major", "B minor", "Medium", 0.6, 0.04)
    dialog = ChordPracticeDialog(["D", "A", "Bm"], uncertain, 0)
    assert dialog._key.currentData() is None
    assert dialog._results.rowCount() == 0
    assert not dialog._preview_btn.isEnabled()
    assert not dialog._export_midi_btn.isEnabled()
    key = dialog._key.findData("D major")
    dialog._key.setCurrentIndex(key)
    dialog._key.activated.emit(key)
    assert dialog._results.rowCount() > 0
    assert dialog._preview_btn.isEnabled()
    assert dialog._export_midi_btn.isEnabled()
    dialog.close()
    app.processEvents()


def test_practice_preview_lifecycle_and_controller_mutual_exclusion(tmp_path: Path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    streams: list[FakeStream] = []

    def make_stream(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=make_stream, CallbackStop=CallbackStop))
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        # Prepare buffered audio & separated drum report so A/B, metronome, drum preview can interact
        controller.ring_buffer.write(np.zeros((48000, 2), dtype=np.float32))
        drums = DrumsAnalysisResult(tmp_path / "drums.wav", 2.0, None, "Unknown", [0.10])
        report = StemDeepAnalysisReport(
            2.0, "Drums", KeyEstimate("Unknown", "Unknown", "Insufficient", 0.0, 0.0),
            TempoEstimate(None, "Unknown", 0.0), drums=drums,
        )
        controller._latest_deep_report = report
        controller.window.mixer_widget.display_deep_analysis(report)

        cw = controller.window.chroma_widget
        cw._chord_history.extend(["C", "G", "Am"])
        dialog = cw.open_chord_practice(modal=False)
        key_idx = dialog._key.findData("C major")
        dialog._key.setCurrentIndex(key_idx)
        dialog._key.activated.emit(key_idx)
        assert dialog._preview_btn.isEnabled()

        # 1. Start preview & manual stop
        dialog._preview_btn.click()
        assert dialog._preview_playing is True
        assert dialog._preview_btn.text() == "停止试听"
        assert len(streams) == 1 and streams[-1].active
        dialog._preview_btn.click()
        assert dialog._preview_playing is False
        assert dialog._preview_btn.text() == "试听进行"
        assert streams[-1].closed

        # 2. Natural completion via controller UI tick
        dialog._preview_btn.click()
        assert streams[-1].active
        streams[-1].active = False
        controller._on_ui_tick()
        assert dialog._preview_playing is False
        assert dialog._preview_btn.text() == "试听进行"
        assert streams[-1].closed
        assert "结束" in dialog._feedback_lbl.text()

        # 3. Switching progression row stops active preview cleanly
        dialog._preview_btn.click()
        assert dialog._preview_playing is True
        dialog._results.selectRow(1)
        assert dialog._preview_playing is False
        assert streams[-1].closed

        # 4. Starting A/B play stops chord preview; drum preview pauses A/B and chord preview stops drum preview
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        assert dialog._preview_playing is True
        controller._on_ab_play()
        ab_stream = streams[-1]
        assert chord_stream.closed
        assert dialog._preview_playing is False
        assert dialog._preview_btn.text() == "试听进行"
        assert ab_stream.active

        # 5. Drum preview pauses A/B -> Chord preview stops drum preview -> Spacebar stops chord preview
        controller._on_drum_preview()
        drum_stream = streams[-1]
        assert ab_stream.closed
        assert controller.window.mixer_widget.preview_drums_btn.text() == "停止试听"
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        assert drum_stream.closed
        assert controller.window.mixer_widget.preview_drums_btn.text() == "试听鼓点"
        assert dialog._preview_playing is True
        controller._on_toggle_active_playback()
        assert chord_stream.closed
        assert dialog._preview_playing is False
        assert dialog._preview_btn.text() == "试听进行"

        # 6. Starting chord preview stops standalone metronome; mixer play stops chord preview
        controller._on_metronome_standalone_toggled(True)
        met_stream = streams[-1]
        assert cw.metronome_standalone_btn.isChecked()
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        assert met_stream.closed
        assert not cw.metronome_standalone_btn.isChecked()
        assert dialog._preview_playing is True
        controller._on_mixer_before_play()
        assert chord_stream.closed
        assert dialog._preview_playing is False

        # 7. Switching key resets preview cleanly
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        alt_idx = dialog._key.findData("A minor")
        dialog._key.setCurrentIndex(alt_idx)
        dialog._key.activated.emit(alt_idx)
        assert chord_stream.closed
        assert dialog._preview_playing is False

        # 8. System loopback & live separation both block chord preview without opening streams
        fake_loopback = SimpleNamespace(
            is_running=True,
            get_stats=lambda: CaptureStats(CaptureMode.SYSTEM_LOOPBACK, None, "loopback", 48000, 2, "float32"),
        )
        controller._capture_backend = fake_loopback
        count_before = len(streams)
        dialog._preview_btn.click()
        assert len(streams) == count_before
        assert dialog._preview_playing is False
        assert dialog._feedback_lbl.property("tone") == "error"
        controller._capture_backend = None

        with monkeypatch.context() as patch:
            patch.setattr(controller.window.live_widget, "_pending_start", True)
            dialog._preview_btn.click()
            assert len(streams) == count_before
            assert dialog._preview_playing is False
            assert dialog._feedback_lbl.property("tone") == "error"

        # 9. Starting system loopback capture or live separation stops active chord preview
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        assert dialog._preview_playing is True
        class _DummyLoopbackBackend:
            is_running = False
            def start(self):
                raise RuntimeError("no loopback device")
            def stop(self):
                pass
        with monkeypatch.context() as patch:
            patch.setattr("main.WasapiSystemLoopbackBackend", lambda **_kw: _DummyLoopbackBackend())
            controller.start_capture({"kind": "system_loopback"})
        assert chord_stream.closed
        assert dialog._preview_playing is False

        dialog._preview_btn.click()
        chord_stream = streams[-1]
        fake_proc_cap = SimpleNamespace(
            is_running=True,
            get_stats=lambda: CaptureStats(CaptureMode.PROCESS_LOOPBACK, 123, "QQMusic.exe", 48000, 2, "float32"),
        )
        controller._capture_backend = fake_proc_cap
        with monkeypatch.context() as patch:
            patch.setattr(controller.live_separator, "start", lambda **_kw: (False, "mock stop"))
            controller._on_live_start("mdx_low_vram_2stem")
        assert chord_stream.closed
        assert dialog._preview_playing is False
        controller._capture_backend = None

        # 10. Device open failure cleans up stream and does not leave stuck button
        def fail_start(self):
            raise OSError("no output device")

        with monkeypatch.context() as patch:
            patch.setattr(FakeStream, "start", fail_start)
            dialog._preview_btn.click()
        assert streams[-1].closed
        assert dialog._preview_playing is False
        assert dialog._preview_btn.text() == "试听进行"
        assert dialog._feedback_lbl.property("tone") == "error"

        # 11. Closing dialog while playing releases active stream
        dialog._preview_btn.click()
        chord_stream = streams[-1]
        assert dialog._preview_playing is True
        dialog.close()
        assert chord_stream.closed
        assert dialog._preview_playing is False
    finally:
        controller.shutdown()
        app.processEvents()
