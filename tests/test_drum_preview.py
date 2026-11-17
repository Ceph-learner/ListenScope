"""Deterministic coverage for local drum audition without an audio device."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6 import QtWidgets

from audio.drum_preview import DrumPreviewPlayer, render_drum_preview
from core.models import DrumsAnalysisResult, KeyEstimate, StemDeepAnalysisReport, TempoEstimate
from main import ListenScopeController


class CallbackStop(Exception):
    pass


class FakeStream:
    def __init__(self, callback, **_):
        self.callback = callback
        self.active = False
        self.closed = False

    def start(self):
        self.active = True

    def abort(self):
        self.active = False

    def close(self):
        self.closed = True


def test_preview_retains_hit_spacing_with_bounded_pcm(tmp_path):
    sr = 8000
    drums = DrumsAnalysisResult(tmp_path / "drums.wav", 30, None, "Unknown")
    assert render_drum_preview(drums, sr).size == 0
    drums.kick_times_sec = [13.0, 21.5]
    drums.snare_times_sec = [13.4]
    drums.hihat_times_sec = [20.98, float("nan")]
    pcm = render_drum_preview(drums, sr)
    assert pcm.shape == (8 * sr,)
    assert pcm.dtype == np.float32
    assert pcm[0] == pcm[-1] == 0
    assert np.max(np.abs(pcm)) <= 0.65
    assert np.any(pcm[:sr // 5])
    assert not np.any(pcm[sr // 5:int(0.4 * sr)])
    assert np.any(pcm[int(0.4 * sr):sr])
    np.testing.assert_array_equal(render_drum_preview(drums, sr), pcm)


def test_preview_stream_writes_silent_tail_and_closes_after_device_finishes(monkeypatch):
    streams = []
    def make_stream(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=make_stream, CallbackStop=CallbackStop))
    player = DrumPreviewPlayer(48000, 2)
    player.play(np.array([0.25, -0.20], dtype=np.float32))
    stream = streams[-1]
    out = np.full((3, 2), 1, dtype=np.float32)
    with pytest.raises(CallbackStop):
        stream.callback(out, out.shape[0], None, None)
    np.testing.assert_allclose(out, [[0.25, 0.25], [-0.20, -0.20], [0.0, 0.0]])
    assert not player.close_if_finished()
    stream.active = False
    assert player.close_if_finished()
    assert stream.closed
    assert not player.stop()

    def fail_start(self):
        raise OSError("device unavailable")
    monkeypatch.setattr(FakeStream, "start", fail_start)
    with pytest.raises(OSError, match="device unavailable"):
        player.play(np.array([0.5], dtype=np.float32))
    assert streams[-1].closed
    assert not player.stop()


def test_preview_button_stops_for_mixer_clear_and_natural_end(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    streams = []
    def make_stream(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=make_stream, CallbackStop=CallbackStop))
    try:
        widget = controller.window.mixer_widget
        drums = DrumsAnalysisResult(tmp_path / "drums.wav", 2.0, None, "Unknown", [0.10])
        report = StemDeepAnalysisReport(
            2.0, "Drums", KeyEstimate("Unknown", "Unknown", "Insufficient", 0.0, 0.0),
            TempoEstimate(None, "Unknown", 0.0), drums=drums,
        )
        controller._latest_deep_report = report
        widget.display_deep_analysis(report)
        assert widget.preview_drums_btn.isEnabled()
        widget.preview_drums_btn.click()
        assert widget.preview_drums_btn.text() == "停止试听"
        assert streams[-1].active
        controller._on_mixer_before_play()
        assert streams[-1].closed
        assert widget.preview_drums_btn.text() == "试听鼓点"

        widget.preview_drums_btn.click()
        streams[-1].active = False
        controller._on_ui_tick()
        assert streams[-1].closed
        assert widget.preview_drums_btn.text() == "试听鼓点"

        widget.preview_drums_btn.click()
        controller._on_clear_stem_results()
        assert streams[-1].closed
        assert not widget.preview_drums_btn.isEnabled()
    finally:
        controller.shutdown()
        app.processEvents()
