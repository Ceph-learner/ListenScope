"""Audit Pass 5 & Phase 16 tests: PCM decode hardening, reconnect/race fixes, transposition, practice exports, settings v2, and stale generation guard."""

from __future__ import annotations

import csv
import gc
import json
import os
import sys
import types
import wave
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtWidgets

from analysis.chords import (
    transpose_chord_symbol,
    transpose_key_label,
    transpose_note_name,
)
from analysis.stem_analyzer import export_transcription_sheet
from audio.pcm_utils import decode_wave_bytes
from audio.playback import HistoryABPlayer, StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from audio.system_loopback import WasapiSystemLoopbackBackend
from core.config import AudioConfig
from core.models import (
    AIJobResult,
    AIJobState,
    AnalysisSnapshot,
    BassAnalysisResult,
    ChordEstimate,
    ChordTimelineSegment,
    KeyEstimate,
    MelodyAnalysisResult,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    PitchEstimate,
    StemDeepAnalysisReport,
    StemNoteEvent,
    TempoEstimate,
)
from core.settings_store import load_settings
from main import ListenScopeController
from separation.demucs_backend import DemucsSeparatorBackend


def _make_sine(seconds: float = 1.5, freq_hz: float = 440.0, sr: int = 48000, amp: float = 0.25) -> np.ndarray:
    n = int(round(seconds * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    mono = (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)
    return np.column_stack([mono, mono])


def _write_wav(path: Path, stereo: np.ndarray, *, sr: int = 48000, sw: int = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sw == 2:
        data = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    else:
        raise ValueError("helper supports 16-bit")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(stereo.shape[1])
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(data)
    return path


def test_decode_wave_bytes_widths_alignment_and_invalid_width() -> None:
    assert decode_wave_bytes(b"", 2, 2).shape == (0, 2)
    assert decode_wave_bytes(b"\x00\x01", 0, 2).shape == (0, 2)

    # 8-bit unsigned (0x80 -> 0.0, 0xFF -> ~1.0) plus trailing odd byte for 2ch
    u8 = decode_wave_bytes(bytes([128, 255, 64, 128, 99]), 1, 2)
    assert u8.shape == (2, 2)
    assert u8[0, 0] == pytest.approx(0.0, abs=1e-4)
    assert u8[0, 1] > 0.95

    # 16-bit with partial frame trailing bytes
    pcm16 = np.array([16384, -16384, 8192, -8192], dtype=np.int16).tobytes() + b"\xab\xcd\xef"
    s16 = decode_wave_bytes(pcm16, 2, 2)
    assert s16.shape == (2, 2)
    assert s16[0, 0] == pytest.approx(0.5, abs=1e-3)
    assert s16[0, 1] == pytest.approx(-0.5, abs=1e-3)

    # 24-bit signed (4194304 = +0.5, -4194304 = -0.5) + partial tail
    pos24 = (4194304).to_bytes(3, "little", signed=True)
    neg24 = (-4194304).to_bytes(3, "little", signed=True)
    s24 = decode_wave_bytes(pos24 + neg24 + b"\x11\x22", 3, 2)
    assert s24.shape == (1, 2)
    assert s24[0, 0] == pytest.approx(0.5, abs=1e-4)
    assert s24[0, 1] == pytest.approx(-0.5, abs=1e-4)

    # 32-bit signed
    pcm32 = np.array([1073741824, -1073741824], dtype=np.int32).tobytes() + b"\x01"
    s32 = decode_wave_bytes(pcm32, 4, 2)
    assert s32.shape == (1, 2)
    assert s32[0, 0] == pytest.approx(0.5, abs=1e-5)

    with pytest.raises(ValueError):
        decode_wave_bytes(b"\x00" * 10, 5, 2)


def test_ring_buffer_corrupt_import_preserves_existing_audio(tmp_path: Path) -> None:
    rb = FixedRingBuffer(audio_config=AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=8))
    orig = np.full((48000, 2), 0.25, dtype=np.float32)
    rb.write(orig)
    before_frames = rb.total_written_frames

    bad_flac = tmp_path / "broken.flac"
    bad_flac.write_bytes(b"not a real flac file")
    with pytest.raises(Exception):
        rb.import_audio_file_streaming(bad_flac)

    assert rb.total_written_frames == before_frames
    assert rb.available_seconds == pytest.approx(1.0, abs=1e-3)
    retained = rb.read_range(0, 48000)
    assert float(np.mean(retained)) == pytest.approx(0.25, abs=1e-5)

    bad_wav = tmp_path / "broken.wav"
    bad_wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    with pytest.raises(Exception):
        rb.import_audio_file_streaming(bad_wav)
    assert rb.total_written_frames == before_frames


def test_system_loopback_reconnect_updates_name_and_clears_transient_notice() -> None:
    state = {"dev_idx": 0, "reads": 0}

    class _FakeStream:
        def __init__(self, idx: int) -> None:
            self._idx = idx

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            state["reads"] += 1
            if self._idx == 0 and state["reads"] >= 3:
                state["dev_idx"] = 1
                raise OSError("device disconnected")
            arr = np.full((frames, 2), 0.05, dtype=np.float32)
            return arr.tobytes()

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _FakePA:
        paFloat32 = 1
        paInt16 = 8

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            idx = state["dev_idx"]
            return {
                "index": idx,
                "name": "USB Headphones" if idx == 0 else "Desk Speakers",
                "defaultSampleRate": 48000,
                "maxInputChannels": 2,
                "maxOutputChannels": 2,
            }

        def open(self, **_kwargs: Any) -> _FakeStream:
            return _FakeStream(state["dev_idx"])

        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        audio_config=AudioConfig(sample_rate=48000, channels=2),
        pyaudio_factory=_FakePA,
        max_device_reconnects=3,
        allow_non_windows=True,
    )
    error_transitions: list[str | None] = []
    orig_set_error = backend._stats.set_error

    def _recording_set_error(msg: str | None) -> None:
        error_transitions.append(msg)
        orig_set_error(msg)

    backend._stats.set_error = _recording_set_error  # type: ignore[method-assign]
    backend.start()
    try:
        cleared_after_healthy = False
        for _ in range(80):
            _ = backend.read_chunk(timeout=0.05)
            st = backend.get_stats()
            if st.process_name == "Desk Speakers" and st.last_error is None:
                cleared_after_healthy = True
                break
        final_st = backend.get_stats()
        assert final_st.process_name == "Desk Speakers"
        reconnect_indices = [
            i for i, msg in enumerate(error_transitions) if msg and "Desk Speakers" in msg
        ]
        assert reconnect_indices, f"Expected transient reconnect notice for Desk Speakers, got {error_transitions!r}"
        assert any(msg is None for msg in error_transitions[reconnect_indices[0] + 1 :]), (
            f"Transient reconnect notice was not cleared after healthy chunks: {error_transitions!r}"
        )
        assert cleared_after_healthy is True
    finally:
        backend.stop()


def test_playback_stream_open_stop_race_discards_leaked_handle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=4)
    rb = FixedRingBuffer(audio_config=cfg)
    rb.write(_make_sine(1.0))

    ab = HistoryABPlayer(rb, audio_config=cfg)
    ab.select_recent_seconds(1.0)
    wav_path = _write_wav(tmp_path / "stem.wav", _make_sine(1.0))
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    mixer.load_stems({"vocals": wav_path})

    pause_target: dict[str, Any] = {"fn": None}

    class _FakeOutputStream:
        def __init__(self, **_kwargs: Any) -> None:
            events.append("init")

        def start(self) -> None:
            events.append("start")
            if pause_target["fn"] is not None:
                pause_target["fn"]()

        def stop(self) -> None:
            events.append("stop")

        def close(self) -> None:
            events.append("close")

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.OutputStream = _FakeOutputStream  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    try:
        pause_target["fn"] = ab.pause
        ab.start_playback(open_audio_device=True)
        assert ab.is_playing is False
        assert ab._stream is None
        assert events[-2:] == ["stop", "close"]

        events.clear()
        pause_target["fn"] = mixer.pause
        mixer.play(open_audio_device=True)
        assert mixer.is_playing is False
        assert mixer._stream is None
        assert events[-2:] == ["stop", "close"]
    finally:
        ab.stop()
        mixer.clear()


def test_demucs_separate_chunk_normalizes_channels_and_nans() -> None:
    from ai.models import MODEL_REGISTRY

    class _FakeTensor:
        def __init__(self, arr: np.ndarray) -> None:
            self.arr = np.asarray(arr, dtype=np.float32)

        def unsqueeze(self, axis: int) -> "_FakeTensor":
            return _FakeTensor(np.expand_dims(self.arr, axis=axis))

        def to(self, *_args: Any, **_kwargs: Any) -> "_FakeTensor":
            return self

        def __getitem__(self, idx: int) -> "_FakeTensor":
            return _FakeTensor(self.arr[idx])

        def detach(self) -> "_FakeTensor":
            return self

        def cpu(self) -> "_FakeTensor":
            return self

        def numpy(self) -> np.ndarray:
            return self.arr

    class _NullCtx:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_a: Any) -> None:
            return None

    class _FakeTorch:
        float32 = np.float32

        @staticmethod
        def from_numpy(arr: np.ndarray) -> _FakeTensor:
            return _FakeTensor(arr)

        @staticmethod
        def inference_mode() -> _NullCtx:
            return _NullCtx()

    class _FakeDemucsModel:
        samplerate = 48000
        sources = ["drums", "bass", "other", "vocals"]

    class _FakeApplyModel:
        @staticmethod
        def apply_model(model: Any, tensor: _FakeTensor, **_kw: Any) -> _FakeTensor:
            n = tensor.arr.shape[-1]
            stems = np.zeros((1, 4, 2, n), dtype=np.float32)
            stems[0, :, :, :] = 0.1
            stems[0, 1, 0, 0] = float("nan")
            return _FakeTensor(stems)

    backend = DemucsSeparatorBackend(MODEL_REGISTRY["htdemucs_4stem"], use_gpu=False)
    backend._torch = _FakeTorch()
    backend._model = _FakeDemucsModel()
    backend._apply_model_fn = _FakeApplyModel.apply_model

    bad_1d = np.array([0.2, float("nan"), 0.4, -0.3], dtype=np.float32)
    out_1d = backend._separate_with_demucs(bad_1d, 48000, segment_sec=4.0)
    assert set(out_1d.keys()) == {"drums", "bass", "other", "vocals"}
    for arr in out_1d.values():
        assert arr.shape == (4, 2)
        assert np.all(np.isfinite(arr))

    four_ch = np.full((16, 4), 0.15, dtype=np.float32)
    four_ch[2, 1] = float("inf")
    out_4ch = backend._separate_with_demucs(four_ch, 48000, segment_sec=4.0)
    for arr in out_4ch.values():
        assert arr.shape == (16, 2)
        assert np.all(np.isfinite(arr))


def test_transposition_helpers_and_transcription_sheet_export(tmp_path: Path) -> None:
    assert transpose_note_name("A4", -2) == "G4"
    assert transpose_note_name("C4", -1) == "B3"
    assert transpose_note_name("Bb", 2) == "C"
    assert transpose_note_name("N (静音)", -2) == "N (静音)"

    assert transpose_chord_symbol("D", -2) == "C"
    assert transpose_chord_symbol("C/G", -2) == "A#/F"
    assert transpose_chord_symbol("Bbm7", 2) == "Cm7"
    assert transpose_chord_symbol("Unknown", -2) == "Unknown"

    assert transpose_key_label("D major", -2) == "C major"
    assert transpose_key_label("F# minor", 2) == "G# minor"

    report = StemDeepAnalysisReport(
        duration_sec=2.0,
        harmonic_source_label="other+bass",
        estimated_key=KeyEstimate("D major", "B minor", "High", 0.9, 0.2),
        estimated_bpm=TempoEstimate(110.0, "High", 0.7),
        chord_timeline=[
            ChordTimelineSegment(0.0, 1.0, "D", "Bm", 0.9, "High"),
            ChordTimelineSegment(1.0, 2.0, "A/C#", "F#m", 0.85, "High"),
        ],
        bass=BassAnalysisResult(
            stem_path=tmp_path / "bass.wav",
            duration_sec=2.0,
            lowest_note="D2",
            highest_note="A2",
            root_pitch_classes=["D", "A"],
            notes=[StemNoteEvent(0.0, 1.0, 38, "D2", 73.4, 0.9)],
        ),
        melody=MelodyAnalysisResult(
            stem_path=tmp_path / "vocals.wav",
            stem_name="vocals",
            duration_sec=2.0,
            lowest_note="F#4",
            highest_note="A4",
            median_note="F#4",
            voiced_ratio=0.8,
            notes=[StemNoteEvent(0.0, 1.0, 66, "F#4", 370.0, 0.9)],
        ),
    )
    midi = MidiTranscriptionResult(
        source_stem_name="vocals",
        output_midi_path=tmp_path / "vocals.mid",
        notes=[MidiNoteCandidate(66, "F#4", 0.0, 0.9, 95, 0.9)],
        backend_used="cpu-pitch-fallback",
    )

    md_path = export_transcription_sheet(report, tmp_path / "sheet.md", midi_result=midi, transpose_semitones=-2)
    md_text = md_path.read_text(encoding="utf-8")
    assert "-2 半音" in md_text
    assert "`C major`" in md_text
    assert "`C`" in md_text
    assert "`G/B`" in md_text
    assert "`C2`" in md_text
    assert "`E4`" in md_text

    csv_path = export_transcription_sheet(report, tmp_path / "sheet.csv", midi_result=midi, transpose_semitones=-2)
    with csv_path.open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    labels = {(r[0], r[3]) for r in rows[1:]}
    assert ("chord", "C") in labels
    assert ("chord", "G/B") in labels
    assert ("bass", "C2") in labels
    assert ("melody", "E4") in labels
    assert ("midi", "E4") in labels


def test_ab_and_mixer_stretched_metronome_exports(tmp_path: Path) -> None:
    sr = 48000
    cfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(audio_config=cfg)
    rb.write(_make_sine(1.5, freq_hz=440.0, sr=sr, amp=0.25))

    # 1. HistoryABPlayer 0.75x + Metronome export (~2.0s output without altering loop_range or position)
    ab = HistoryABPlayer(rb, audio_config=cfg)
    a_f, b_f = ab.select_recent_seconds(1.5)
    assert ab.position_frame == a_f
    ab_out, ab_dur = ab.export_ab_practice_wav_streaming(
        tmp_path / "ab_slow_click.wav",
        a_f,
        b_f,
        speed=0.75,
        include_metronome=True,
        bpm=120.0,
        beats_per_bar=4,
        metronome_volume=0.8,
        chunk_frames=4096,
    )
    assert ab_out.exists()
    assert not ab_out.with_name(ab_out.name + ".tmp").exists()
    assert ab_dur == pytest.approx(2.0, abs=0.03)
    assert ab.position_frame == a_f
    with wave.open(str(ab_out), "rb") as wf:
        assert wf.getframerate() == sr
        assert wf.getnchannels() == 2
        assert wf.getnframes() == int(round((b_f - a_f) / 0.75))

    # 2. StemMixerEngine sub-loop (0.2s..1.0s = 0.8s) at 0.75x (~1.067s output) + click
    bass_wav = _write_wav(tmp_path / "bass.wav", _make_sine(1.5, freq_hz=110.0, sr=sr, amp=0.2))
    vocals_wav = _write_wav(tmp_path / "vocals.wav", _make_sine(1.5, freq_hz=440.0, sr=sr, amp=0.2))
    mixer = StemMixerEngine(sample_rate=sr, channels=2)
    try:
        mixer.load_stems({"bass": bass_wav, "vocals": vocals_wav})
        mixer.set_loop_region(0.2, 1.0)
        mixer.set_speed(0.75)
        pre_pos = mixer.position_frame
        mix_out = mixer.export_mix_streaming(
            tmp_path / "mix_subloop_slow.wav",
            chunk_frames=4096,
            use_loop_region=True,
            speed=0.75,
            include_metronome=True,
            bpm=120.0,
            beats_per_bar=4,
            metronome_volume=0.75,
        )
        assert mix_out.exists()
        assert not mix_out.with_name(mix_out.name + ".tmp").exists()
        assert mixer.position_frame == pre_pos
        with wave.open(str(mix_out), "rb") as wf:
            expected_frames = int(round((0.8 * sr) / 0.75))
            assert wf.getnframes() == pytest.approx(expected_frames, abs=4)
    finally:
        mixer.clear()


def test_settings_v2_backward_compat_ui_transposition_and_stale_generation_guard(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_path = tmp_path / "cfg" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Verify v1 settings JSON (without practice fields) loads safely
    settings_path.write_text(
        json.dumps({"schema_version": 1, "resource_limits": {"min_ram_before_ai_mb": 5200.0}, "ai_config": {}}),
        encoding="utf-8",
    )
    v1_loaded = load_settings(settings_path)
    assert v1_loaded.schema_version == 2
    assert v1_loaded.metronome_bpm == 120.0
    assert v1_loaded.metronome_beats_per_bar == 4
    assert v1_loaded.metronome_volume == 0.70
    assert v1_loaded.metronome_count_in is False
    assert v1_loaded.transpose_semitones == 0

    # Clamps invalid v2 bounds cleanly
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "metronome_bpm": 999.0,
                "metronome_beats_per_bar": 3,
                "metronome_volume": 8.0,
                "metronome_count_in": "invalid",
                "transpose_semitones": -99,
            }
        ),
        encoding="utf-8",
    )
    clamped = load_settings(settings_path)
    assert clamped.metronome_bpm == 240.0
    assert clamped.metronome_beats_per_bar == 3
    assert clamped.metronome_volume == 1.5
    assert clamped.metronome_count_in is False
    assert clamped.transpose_semitones == -11

    # 2. Controller UI tuning paint, Capo synchronization, practice export wiring, and v2 persistence round-trip
    settings_path.unlink()
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        ai_python_executable="",
        work_dir=tmp_path / "work1",
        settings_path=settings_path,
    )
    try:
        cw = ctrl.window.chroma_widget
        mw = ctrl.window.mixer_widget

        # Exercise TuningCentsBar.paintEvent with live pitch (regression guard for QtCore.Qt.PenStyle.NoPen)
        cw.tuning_bar.set_pitch(442.0, 14.0)
        pixmap = cw.tuning_bar.grab()
        assert pixmap.width() > 0 and pixmap.height() > 0

        # Freeze periodic background timer ticks so synthetic AnalysisSnapshot stays deterministic
        ctrl._timer.stop()

        # Feed D chord / D major snapshot + load deep report
        snap = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[-0.1, -0.1],
            waveform_max=[0.1, 0.1],
            fft_freqs_hz=[293.66],
            fft_db=[-10.0],
            log_freqs_hz=[293.66],
            log_spectrum_db=[-10.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("D", "Bm", "High", 0.92, 0.12, False),
            key=KeyEstimate("D major", "B minor", "High", 0.90, 0.15, "关系大小调"),
            tempo=TempoEstimate(104.0, "High", 0.8),
            pitch=PitchEstimate(440.0, "A4", 8.0, 0.95),
            rms_dbfs=-16.0,
            peak_dbfs=-4.0,
            window_seconds=2.0,
        )
        cw.update_analysis(snap)

        rep = StemDeepAnalysisReport(
            duration_sec=1.0,
            harmonic_source_label="other",
            estimated_key=KeyEstimate("D major", "B minor", "High", 0.9, 0.2),
            estimated_bpm=TempoEstimate(104.0, "High", 0.7),
            chord_timeline=[
                ChordTimelineSegment(0.0, 0.5, "D", "Bm", 0.9, "High"),
                ChordTimelineSegment(0.5, 1.0, "A", "F#m", 0.85, "High"),
            ],
        )
        mw.display_deep_analysis(rep)
        mw.chord_timeline_table.selectRow(1)
        mw.analysis_tabs.setCurrentIndex(1)  # User viewing Piano Roll tab

        # Select Capo 2 (-2)
        capo_idx = cw.transpose_combo.findData(-2)
        assert capo_idx >= 0
        cw.transpose_combo.setCurrentIndex(capo_idx)
        app.processEvents()

        assert cw.transpose_semitones == -2
        assert "C (实音 D)" in cw.chord_primary_lbl.text()
        assert "C · E · G" in cw.chord_tones_lbl.text()
        assert "C major (实音 D major)" in cw.key_primary_lbl.text()
        assert "G4" in cw.pitch_lbl.text()
        # Mixer stays in sync and does NOT forcibly jump off Piano Roll tab or row 1
        assert mw.chord_timeline_table.item(0, 2).text() == "C"
        assert mw.chord_timeline_table.item(1, 2).text() == "G"
        assert mw.chord_timeline_table.currentRow() == 1
        assert mw.analysis_tabs.currentIndex() == 1

        # Inverted A/B spinbox values normalize cleanly to (8.0, 4.0)
        ctrl.ring_buffer.write(_make_sine(10.0))
        ctrl.window.start_ago_spin.setValue(4.0)
        ctrl.window.end_ago_spin.setValue(8.0)
        ctrl.window.apply_ab_btn.click()
        assert ctrl.window.start_ago_spin.value() == pytest.approx(8.0, abs=1e-2)
        assert ctrl.window.end_ago_spin.value() == pytest.approx(4.0, abs=1e-2)

        # Practice A/B WAV export honors controller speed & overlay click
        ctrl.ab_player.set_speed(0.75)
        cw.metronome_bpm_spin.setValue(96.0)
        cw.metronome_overlay_chk.setChecked(True)
        ab_wav_path = tmp_path / "ctrl_ab_practice.wav"
        ctrl._on_export_ab_wav(str(ab_wav_path))
        ctrl.wait_pending_io()
        assert ab_wav_path.exists()
        assert "0.75x" in ctrl.window.notice_banner.text()

        # Modify remaining practice preferences before shutdown persistence check
        idx_3_4 = cw.metronome_sig_combo.findData(3)
        cw.metronome_sig_combo.setCurrentIndex(idx_3_4)
        cw.metronome_vol_slider.setValue(115)
        cw.metronome_count_in_chk.setChecked(True)

        # Stale generation guard: simulate old deep analysis returning after a newer separation completed
        stale_rep = StemDeepAnalysisReport(
            duration_sec=1.0,
            harmonic_source_label="old",
            estimated_key=KeyEstimate("F major", "D minor", "High", 0.9, 0.2),
            estimated_bpm=TempoEstimate(80.0, "High", 0.6),
            chord_timeline=[ChordTimelineSegment(0.0, 1.0, "F", "Dm", 0.9, "High")],
        )
        ctrl._ui_deep_analysis_q.put_nowait((0, stale_rep, "STALE REPORT"))
        ctrl._ui_ai_result_q.put_nowait(
            AIJobResult(
                task_id="job_new",
                state=AIJobState.COMPLETED,
                model_id="mdx_low_vram_2stem",
                device_used="cpu",
                stem_paths={},
            )
        )
        ctrl._on_ui_tick()
        assert ctrl._stem_generation == 1
        assert ctrl._latest_deep_report is None
        assert ctrl.window.notice_banner.text() != "STALE REPORT"
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()

    # Reopen controller and confirm v2 practice prefs persisted cleanly
    ctrl2 = ListenScopeController(
        use_mock_ai_for_demo=True,
        ai_python_executable="",
        work_dir=tmp_path / "work2",
        settings_path=settings_path,
    )
    try:
        assert ctrl2.metronome.bpm == pytest.approx(96.0, abs=0.1)
        assert ctrl2.metronome.beats_per_bar == 3
        assert ctrl2.metronome.volume == pytest.approx(1.15, abs=1e-2)
        assert ctrl2.metronome.count_in_enabled is True
        assert ctrl2.window.chroma_widget.transpose_semitones == -2
        assert ctrl2.window.mixer_widget._transpose_semitones == -2
        assert ctrl2.window.chroma_widget.metronome_bpm_spin.value() == pytest.approx(96.0, abs=0.1)
    finally:
        ctrl2.window.close()
        ctrl2.shutdown()
        ctrl2 = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()


def test_live_separator_ignores_malformed_ipc_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import queue as py_queue
    from types import SimpleNamespace

    from core.config import AIConfig
    from core.resource_manager import ResourceManager
    from streaming.live_separator import ExperimentalLiveSeparator

    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=4)
    rb = FixedRingBuffer(audio_config=cfg)
    rb.write(_make_sine(1.0))

    rm = ResourceManager()
    rm.sample = lambda **_kw: SimpleNamespace(  # type: ignore[method-assign]
        status=SimpleNamespace(value="NORMAL"),
        status_reasons=[],
        main_ram_mb=200.0,
        ai_worker_ram_mb=100.0,
        vram_free_mb=None,
        gpu_utilization_pct=None,
    )
    sep = ExperimentalLiveSeparator(
        rb,
        rm,
        ai_config=AIConfig(live_chunk_seconds=0.5, live_overlap_seconds=0.1, live_max_buffer_seconds=2.0),
        audio_config=cfg,
    )
    res_q: py_queue.Queue[Any] = py_queue.Queue()
    req_q: py_queue.Queue[Any] = py_queue.Queue(maxsize=4)
    sep._res_q = res_q
    sep._req_q = req_q
    sep._is_worker_alive = lambda: True  # type: ignore[method-assign]
    sep._cleanup_worker_only = lambda: None  # type: ignore[method-assign]

    chunk_frames = sep._chunk_frames
    bad_pcm = np.full((chunk_frames, 2), 0.15, dtype=np.float32)
    bad_pcm[0, 0] = float("nan")
    good_pcm = np.full((chunk_frames, 2), 0.2, dtype=np.float32)

    # Queue several corrupt messages followed by NaN-bearing and valid chunks, then stop event
    res_q.put("not-a-dict")
    res_q.put({"type": "chunk", "seq": 0, "shape": ("bad", 2), "vocals": b"1234", "instrumental": b"1234"})
    res_q.put({"type": "chunk", "seq": 0, "shape": (4, 1), "vocals": b"\x00" * 16, "instrumental": b"\x00" * 16})
    res_q.put({"type": "chunk", "seq": 0, "shape": (chunk_frames, 2), "vocals": b"\x00" * 8, "instrumental": good_pcm.tobytes()})
    res_q.put(
        {
            "type": "chunk",
            "seq": 0,
            "shape": (chunk_frames, 2),
            "vocals": bad_pcm.tobytes(),
            "instrumental": good_pcm.tobytes(),
            "infer_sec": float("nan"),
        }
    )

    orig_wait = sep._stop_event.wait

    def _stop_after_one_tick(timeout: float | None = None) -> bool:
        sep._stop_event.set()
        return True

    monkeypatch.setattr(sep._stop_event, "wait", _stop_after_one_tick)
    sep._run_loop()
    monkeypatch.setattr(sep._stop_event, "wait", orig_wait)

    mixed = sep.pull_mixed_block(2048)
    assert mixed.shape == (2048, 2)
    assert np.all(np.isfinite(mixed))
    assert float(np.max(np.abs(mixed))) > 0.05
    assert sep.latest_metrics().rtf == 0.0

