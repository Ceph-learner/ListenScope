"""Phase 13 tests: pitch-preserving WSOLA stretch, practice sub-looping, A/B playhead, harmony reset, and Audit Pass 2 fixes."""

from __future__ import annotations

import gc
import os
import queue
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import soundfile as sf
from PySide6 import QtCore, QtWidgets

from ai.resource_guard import stream_chunked_separation
from ai.worker import execute_worker_job
from analysis.worker import AnalysisWorker
from audio.playback import HistoryABPlayer, StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from audio.time_stretch import StreamingTimeStretcher
from core.config import AudioConfig, ResourceLimits
from core.models import (
    AIJobRequest,
    AIJobState,
    AnalysisSnapshot,
    ChordEstimate,
    ChordTimelineSegment,
    KeyEstimate,
    MidiNoteCandidate,
    MidiTranscriptionResult,
    PitchEstimate,
    StemDeepAnalysisReport,
    TempoEstimate,
)
from core.resource_manager import ResourceManager, SimulationOverrides
from main import ListenScopeController
from streaming.live_separator import ExperimentalLiveSeparator


def _dominant_freq_hz(mono: np.ndarray, sr: int = 48000) -> float:
    win = np.hanning(len(mono)).astype(np.float32)
    spec = np.abs(np.fft.rfft(mono * win))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / float(sr))
    return float(freqs[int(np.argmax(spec))])


def _make_sine_stereo(freq_hz: float, duration_sec: float, sr: int = 48000, amp: float = 0.4) -> np.ndarray:
    n = int(round(duration_sec * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    sig = (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)
    return np.column_stack([sig, sig]).astype(np.float32)


def _write_stereo_wav(path: Path, stereo: np.ndarray, sr: int = 48000) -> Path:
    sf.write(str(path), stereo, sr, subtype="PCM_16")
    return path


@pytest.mark.parametrize("speed", [0.5, 0.75, 1.25])
def test_time_stretcher_preserves_pitch_and_unity_rms(speed: float) -> None:
    sr = 48000
    dur = 1.6
    pcm = _make_sine_stereo(440.0, dur, sr=sr, amp=0.45)
    span = pcm.shape[0]
    stretcher = StreamingTimeStretcher(sample_rate=sr, channels=2)

    def _read(rel_start: int, count: int) -> np.ndarray:
        return pcm[rel_start : min(span, rel_start + count)]

    chunks: list[np.ndarray] = []
    eof = False
    for _ in range(400):
        blk, _cursor, eof = stretcher.render_block(
            1024,
            speed=speed,
            span_frames=span,
            rel_cursor=0,
            loop_enabled=False,
            read_rel_fn=_read,
        )
        chunks.append(blk)
        if eof:
            break

    assert eof is True
    rendered = np.concatenate(chunks, axis=0)
    expected_frames = int(round(span / speed))
    # One-shot pads final block to 1024 granularity
    assert expected_frames * 0.94 <= rendered.shape[0] <= expected_frames * 1.08 + 1024

    mid_start = rendered.shape[0] // 4
    mid_end = (rendered.shape[0] * 3) // 4
    mid_mono = rendered[mid_start:mid_end, 0]
    peak_hz = _dominant_freq_hz(mid_mono, sr=sr)
    assert 436.0 <= peak_hz <= 444.0

    in_rms = float(np.sqrt(np.mean(pcm[:, 0] ** 2)))
    out_rms = float(np.sqrt(np.mean(mid_mono ** 2)))
    assert out_rms == pytest.approx(in_rms, rel=0.12)


def test_time_stretcher_loop_wrap_continuity() -> None:
    sr = 48000
    pcm = _make_sine_stereo(329.63, 0.8, sr=sr, amp=0.4)
    span = pcm.shape[0]
    stretcher = StreamingTimeStretcher(sample_rate=sr, channels=2)

    def _read(rel_start: int, count: int) -> np.ndarray:
        return pcm[rel_start : min(span, rel_start + count)]

    blocks: list[np.ndarray] = []
    for _ in range(180):  # ~3.84s of slowed looped audio
        blk, _cur, eof = stretcher.render_block(
            1024,
            speed=0.5,
            span_frames=span,
            rel_cursor=0,
            loop_enabled=True,
            read_rel_fn=_read,
        )
        assert eof is False
        blocks.append(blk)

    rendered = np.concatenate(blocks, axis=0)
    assert float(np.sqrt(np.mean(rendered[2048:, 0] ** 2))) > 0.22
    assert 326.0 <= _dominant_freq_hz(rendered[2048:2048 + 32768, 0], sr=sr) <= 333.0


def test_ab_player_speed_one_shot_and_stream_cleanup() -> None:
    sr = 48000
    cfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(audio_config=cfg)
    pcm = _make_sine_stereo(440.0, 1.5, sr=sr, amp=0.4)
    rb.write(pcm)

    player = HistoryABPlayer(rb, audio_config=cfg)
    player.select_recent_seconds(1.5)
    player.set_loop(False)
    player.set_speed(0.5)

    class _DummyStream:
        def __init__(self) -> None:
            self.stopped = False
            self.closed = False

        def stop(self) -> None:
            self.stopped = True

        def close(self) -> None:
            self.closed = True

    dummy = _DummyStream()
    player._stream = dummy
    player.start_playback(open_audio_device=False)

    rendered = []
    for _ in range(250):
        rendered.append(player.render_block(1024))
        if not player.is_playing:
            break

    assert player.is_playing is False
    out = np.concatenate(rendered, axis=0)
    # 1.5s at 0.5x ~ 3.0s (~144000 frames)
    assert out.shape[0] >= int(2.75 * sr)
    assert 436.0 <= _dominant_freq_hz(out[4096:4096 + 32768, 0], sr=sr) <= 444.0

    # Stream closed from non-callback UI thread cleanly
    player.close_if_finished()
    assert dummy.stopped is True and dummy.closed is True
    assert player._stream is None


def test_stem_mixer_subloop_speed_and_seek_clearing(tmp_path: Path) -> None:
    sr = 48000
    part1 = _make_sine_stereo(220.0, 1.0, sr=sr, amp=0.35)
    part2 = _make_sine_stereo(330.0, 1.0, sr=sr, amp=0.35)
    wav_path = _write_stereo_wav(tmp_path / "stem.wav", np.concatenate([part1, part2], axis=0), sr=sr)

    mixer = StemMixerEngine(sample_rate=sr, channels=2)
    mixer.load_stems({"other": wav_path})

    # Loop only the 330Hz second half [1.05s, 1.85s) at 0.75x pitch-preserved speed
    s_sec, e_sec = mixer.set_loop_region(1.05, 1.85)
    assert s_sec == pytest.approx(1.05, abs=0.01)
    assert e_sec == pytest.approx(1.85, abs=0.01)
    mixer.set_speed(0.75)

    class _DummyStream:
        def __init__(self) -> None:
            self.closed = False

        def stop(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    dummy = _DummyStream()
    mixer._stream = dummy
    mixer.play(open_audio_device=False)

    blocks = [mixer.render_block(1024, advance=True) for _ in range(90)]
    mixed = np.concatenate(blocks, axis=0)
    assert 1.0 <= mixer.position_sec <= 1.86
    # Sub-loop only contains 330Hz (not 220Hz!)
    assert 326.0 <= _dominant_freq_hz(mixed[2048:2048 + 32768, 0], sr=sr) <= 334.0

    # Seek outside sub-loop clears loop_region_sec
    mixer.seek(int(0.2 * sr))
    assert mixer.loop_region_sec is None

    # One-shot end closes stream on close_if_finished()
    mixer.set_loop(False)
    mixer.set_speed(1.0)
    mixer.seek(int(1.9 * sr))
    for _ in range(10):
        mixer.render_block(1024, advance=True)
        if not mixer.is_playing:
            break
    assert mixer.is_playing is False
    mixer.close_if_finished()
    assert dummy.closed is True
    mixer.clear()


def test_audit2_worker_abort_unloads_before_telemetry_and_guard_normalizes_channels(tmp_path: Path, monkeypatch) -> None:
    in_wav = _write_stereo_wav(tmp_path / "in.wav", _make_sine_stereo(261.63, 1.0, amp=0.3), sr=48000)

    # 1. stream_chunked_separation handles 1D mono stem output & non-finite values safely on stereo input
    def _odd_shape_sep(chunk: np.ndarray, _sr: int) -> dict[str, np.ndarray]:
        mono = np.mean(chunk, axis=1).astype(np.float32)
        mono[0] = np.nan
        extra = np.column_stack([mono, mono, mono]).astype(np.float32)
        return {"vocals": mono, "accompaniment": extra}

    stems = stream_chunked_separation(
        in_wav,
        tmp_path / "out_guard",
        ("vocals", "accompaniment"),
        _odd_shape_sep,
        chunk_seconds=0.5,
        overlap_seconds=0.1,
    )
    for stem_file in stems.values():
        data, sr = sf.read(stem_file, dtype="float32", always_2d=True)
        assert sr == 48000 and data.shape == (48000, 2)
        assert np.all(np.isfinite(data))

    # 2. execute_worker_job unloads backend BEFORE sampling final abort RSS/VRAM
    events: list[str] = []

    class _MockUnloadOrderBackend:
        def __init__(self) -> None:
            self.unloaded = False

        def load_model(self) -> None:
            events.append("loaded")

        def separate_chunk(self, chunk: np.ndarray, _sr: int) -> dict[str, np.ndarray]:
            return {"vocals": chunk, "accompaniment": chunk}

        def unload_model(self) -> None:
            self.unloaded = True
            events.append("unloaded")

    dummy_backend = _MockUnloadOrderBackend()
    monkeypatch.setattr("ai.worker.build_separation_backend", lambda *_a, **_kw: dummy_backend)

    def _recording_rss() -> float:
        if dummy_backend.unloaded:
            events.append("rss_after_unload")
        return 123.0

    monkeypatch.setattr("ai.worker._sample_process_rss_mb", _recording_rss)

    # Cancel right after INFERRING starts (cancel_check False initially, True once inferring starts)
    checks = {"n": 0}

    def _cancel_after_load() -> bool:
        checks["n"] += 1
        return checks["n"] >= 3

    req = AIJobRequest(
        task_id="abort_order",
        input_wav_path=str(in_wav),
        output_dir=str(tmp_path / "abort_out"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
    )
    res = execute_worker_job(req, cancel_check=_cancel_after_load)
    assert res.state == AIJobState.CANCELLED
    assert "unloaded" in events
    assert "rss_after_unload" in events
    assert events.index("unloaded") < events.index("rss_after_unload")


def test_audit2_live_separator_detects_unexpected_worker_death(tmp_path: Path) -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(audio_config=cfg)
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    try:
        sep = ExperimentalLiveSeparator(rb, rm, audio_config=cfg)

        class _DeadProc:
            pid = 999999
            stdin = None
            stdout = None
            stderr = None

            def poll(self) -> int:
                return 137

        sep._active = True
        sep._subproc = _DeadProc()
        sep._res_q = queue.Queue()
        sep._subproc_stderr_tail.append("Segmentation fault in mock worker")
        rm.update_runtime_state(active_ai_jobs=1, loaded_models=1, ai_worker_pid=999999)

        sep._run_loop()

        assert sep.is_active is False
        m = sep.latest_metrics()
        assert "异常停止" in m.status_message
        assert "137" in m.status_message
        snap = rm.sample()
        assert snap.active_ai_jobs == 0
        assert snap.loaded_models == 0
    finally:
        rm.close()


def test_analysis_worker_reset_harmony() -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(audio_config=cfg)
    rb.write(_make_sine_stereo(261.63, 1.0, sr=48000, amp=0.5))

    aw = AnalysisWorker(rb, audio_config=cfg)
    snap = aw.analyze_latest_once()
    assert snap is not None
    assert aw.chroma.recent_chroma_matrix().shape[0] >= 1

    aw.reset_harmony()
    assert aw.latest_snapshot() is None
    assert aw.chroma.recent_chroma_matrix().shape[0] == 0


def test_phase13_headless_gui_practice_shortcut_and_hud_integration(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        work_dir=tmp_path / "ws13",
        settings_path=tmp_path / "ws13_settings.json",
    )
    try:
        sr = 48000
        tone = _make_sine_stereo(440.0, 3.0, sr=sr, amp=0.35)
        ctrl.ring_buffer.write(tone)
        ctrl.window.show()

        # 1. Chroma progression strip + Reset button
        cw = ctrl.window.chroma_widget
        for chord_lbl in ("C", "Am", "F", "G"):
            cw.update_analysis(
                AnalysisSnapshot(
                    timestamp=0.0,
                    rms_dbfs=-15.0,
                    peak_dbfs=-10.0,
                    window_seconds=3.0,
                    waveform_min=[],
                    waveform_max=[],
                    fft_freqs_hz=[],
                    fft_db=[],
                    log_freqs_hz=[],
                    log_spectrum_db=[],
                    chroma_12=[0.1] * 12,
                    chord=ChordEstimate(
                        primary=chord_lbl,
                        secondary="-",
                        correlation=0.9,
                        margin=0.2,
                        stability="High",
                        is_silent=False,
                    ),
                    key=KeyEstimate("C major", "A minor", "High", 0.85, 0.1, "", ""),
                    tempo=TempoEstimate(120.0, "High", 0.6),
                    pitch=PitchEstimate(440.0, "A4", 0.0, True),
                )
            )
        assert cw.recent_progression == ["C", "Am", "F", "G"]
        gen_before = ctrl.analysis_worker._harmony_generation
        cw.reset_harmony_btn.click()
        app.processEvents()
        assert cw.recent_progression == []
        assert ctrl.analysis_worker._harmony_generation > gen_before
        assert ctrl.analysis_worker.chroma.recent_chroma_matrix().shape[0] <= 2

        # 2. Bottom A/B loop toggle, pitch-preserving speed combo, yellow playhead cursor & Ctrl+Space
        ctrl.window._pick_recent(2.0)
        ctrl.window.ab_loop_chk.setChecked(False)
        ctrl.window.ab_speed_combo.setCurrentIndex(0)  # 0.5x
        app.processEvents()
        assert ctrl.ab_player.loop_enabled is False
        assert ctrl.ab_player.speed == pytest.approx(0.5)

        ctrl.window.ab_loop_chk.setChecked(True)
        # Toggle playback via Ctrl+Space slot without touching sounddevice output
        orig_play = ctrl.ab_player.start_playback
        ctrl.ab_player.start_playback = lambda open_audio_device=True: orig_play(open_audio_device=False)  # type: ignore[method-assign]
        ctrl._on_toggle_active_playback()
        ctrl._on_ui_tick()
        assert ctrl.ab_player.is_playing is True
        assert ctrl.window._ab_playhead_line.isVisible() is True
        assert -120.0 <= float(ctrl.window._ab_playhead_line.value()) <= 0.0

        # Calling Ctrl+Space again pauses & hides A/B cursor on next tick
        ctrl._on_toggle_active_playback()
        ctrl._on_ui_tick()
        assert ctrl.ab_player.is_playing is False
        assert ctrl.window._ab_playhead_line.isVisible() is False

        # 3. Mixer practice controls: chord sub-loop, live chord HUD, speed combo, clear sub-loop, reload clearing
        mw = ctrl.window.mixer_widget
        stem_wav = _write_stereo_wav(tmp_path / "mix_stem.wav", tone, sr=sr)
        mw.load_stem_paths({"other": str(stem_wav)})
        mw.display_deep_analysis(
            StemDeepAnalysisReport(
                duration_sec=3.0,
                harmonic_source_label="other",
                estimated_key=KeyEstimate("C major", "A minor", "High", 0.85, 0.1, "", ""),
                estimated_bpm=TempoEstimate(120.0, "High", 0.6),
                chord_timeline=[
                    ChordTimelineSegment(start_sec=0.0, end_sec=1.5, chord="C", secondary="Am", correlation=0.95, stability="High"),
                    ChordTimelineSegment(start_sec=1.5, end_sec=3.0, chord="G", secondary="Em", correlation=0.92, stability="High"),
                ],
            )
        )
        mw.display_midi_result(
            MidiTranscriptionResult(
                source_stem_name="other",
                output_midi_path=None,
                notes=[
                    MidiNoteCandidate(pitch_midi=60, note_name="C4", start_sec=0.2, end_sec=0.8, velocity=90, confidence=0.9),
                    MidiNoteCandidate(pitch_midi=67, note_name="G4", start_sec=1.7, end_sec=2.5, velocity=90, confidence=0.9),
                ],
                backend_used="test",
            )
        )
        assert mw.loop_chord_btn.isEnabled() is True
        mw.chord_timeline_table.selectRow(1)
        mw.loop_chord_btn.click()
        app.processEvents()
        assert ctrl.mixer_engine.loop_region_sec == pytest.approx((1.5, 3.0), abs=0.02)
        assert mw.clear_subloop_btn.isEnabled() is True
        assert "G" in mw.subloop_badge_lbl.text()

        mw.speed_combo.setCurrentIndex(2)  # 0.75x
        assert ctrl.mixer_engine.speed == pytest.approx(0.75)

        # Simulate active playback near 0.5s -> live chord HUD shows current C & next G
        mw.clear_subloop_btn.click()
        assert ctrl.mixer_engine.loop_region_sec is None
        ctrl.mixer_engine.play(open_audio_device=False)
        ctrl.mixer_engine.seek(int(0.5 * sr))
        mw.sync_playback_position()
        assert "C" in mw.live_chord_hud_lbl.text()
        assert "G" in mw.live_chord_hud_lbl.text()
        assert mw.chord_timeline_table.currentRow() == 0

        # Active playback near 1.9s highlights both chord row 1 and MIDI row 1
        ctrl.mixer_engine.seek(int(1.9 * sr))
        mw.sync_playback_position()
        assert mw.chord_timeline_table.currentRow() == 1
        assert mw.midi_table.currentRow() == 1

        # Piano Roll click-to-seek maps scene click -> timeline seek
        ctrl.window.tabs.setCurrentWidget(mw)
        mw.analysis_tabs.setCurrentIndex(1)
        app.processEvents()
        vb = mw.piano_roll_plot.getPlotItem().getViewBox()
        target_scene = vb.mapViewToScene(QtCore.QPointF(1.1, 63.0))

        class _FakeMouseClick:
            def button(self):
                return QtCore.Qt.MouseButton.LeftButton

            def scenePos(self):
                return target_scene

        mw._on_piano_roll_clicked(_FakeMouseClick())
        assert ctrl.mixer_engine.position_sec == pytest.approx(1.1, abs=0.15)

        # Ctrl+Space on Mixer tab pauses mixer playback cleanly
        ctrl._on_toggle_active_playback()
        assert ctrl.mixer_engine.is_playing is False

        # Reloading stems clears stale MIDI & chord state cleanly
        mw.load_stem_paths({"other": str(stem_wav)})
        assert mw.midi_table.rowCount() == 0
        assert mw._piano_roll_item is None
        assert mw.loop_chord_btn.isEnabled() is False
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()
