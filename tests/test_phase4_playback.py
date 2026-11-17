"""Phase 4 tests: HistoryABPlayer A/B looping + QQ Music hint, and StemMixerEngine streaming mix/export."""

from __future__ import annotations

import sys
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from audio.playback import AB_PAUSE_PLAYER_HINT, HistoryABPlayer, StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from core.config import AudioConfig


def test_ab_playback_reports_unavailable_output_device(monkeypatch):
    ring = FixedRingBuffer(AudioConfig(ring_buffer_seconds=1))
    ring.write(np.full((1000, 2), 0.1, dtype=np.float32))
    player = HistoryABPlayer(ring)
    player.set_ab_range(0, 1000)

    def unavailable(**_kwargs):
        raise OSError("device disconnected")

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=unavailable))
    with pytest.raises(RuntimeError, match="无法打开播放设备"):
        player.start_playback(require_device=True)
    assert not player.is_playing


def _write_const_wav(path, val: float, frames: int = 4800, sr: int = 48000) -> None:
    pcm = np.full((frames, 2), val, dtype=np.float32)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((pcm * 32767.0).astype(np.int16).tobytes())


def test_history_ab_player_loops_seamlessly_and_returns_qq_hint() -> None:
    cfg = AudioConfig(sample_rate=100, channels=2, dtype="float32", ring_buffer_seconds=10)
    rb = FixedRingBuffer(cfg)
    vals = np.arange(100, dtype=np.float32) / 100.0
    rb.write(np.column_stack([vals, vals]))

    player = HistoryABPlayer(rb, audio_config=cfg)
    a, b = player.set_ab_range(20, 40)
    assert (a, b) == (20, 40)

    hint = player.start_playback(open_audio_device=False)
    assert hint == AB_PAUSE_PLAYER_HINT

    # Pull 45 frames -> expects [20..39] + [20..39] + [20..24] cleanly
    block = player.render_block(45)
    expected = np.concatenate([vals[20:40], vals[20:40], vals[20:25]])
    assert np.allclose(block[:, 0], expected, atol=1e-6)
    player.stop()
    assert player.is_playing is False


def test_stem_mixer_engine_mute_solo_presets_and_streaming_export(tmp_path) -> None:
    stems = {}
    for name, amp in (("vocals", 0.2), ("drums", 0.1), ("bass", 0.3), ("other", 0.05)):
        p = tmp_path / f"{name}.wav"
        _write_const_wav(p, amp, frames=2000, sr=48000)
        stems[name] = p

    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    loaded = mixer.load_stems(stems)
    assert set(loaded.keys()) == {"vocals", "drums", "bass", "other"}

    mixer.play(open_audio_device=False)
    all_mix = mixer.render_block(256, advance=False)
    assert np.allclose(all_mix, 0.2 + 0.1 + 0.3 + 0.05, atol=1e-3)

    mixer.apply_preset("bass_only")
    bass_mix = mixer.render_block(256, advance=False)
    assert np.allclose(bass_mix, 0.3, atol=1e-3)

    mixer.apply_preset("instrumental_mix")
    inst_mix = mixer.render_block(256, advance=False)
    assert np.allclose(inst_mix, 0.1 + 0.3 + 0.05, atol=1e-3)

    mixer.apply_preset("all")
    mixer.set_solo("vocals", True)
    mixer.set_volume("vocals", 0.5)
    voc_mix = mixer.render_block(256, advance=False)
    assert np.allclose(voc_mix, 0.1, atol=1e-3)

    out_mix_wav = tmp_path / "mixed.wav"
    mixer.export_mix_streaming(out_mix_wav, chunk_frames=500)
    assert out_mix_wav.exists()
    with wave.open(str(out_mix_wav), "rb") as wf:
        assert wf.getnframes() == 2000

    mins, maxs = mixer.get_stem_waveform_envelope("bass", num_points=40)
    assert mins.shape == (40,) and maxs.shape == (40,)
    mixer.clear()


def test_missing_bass_preset_preserves_two_stem_mix(tmp_path) -> None:
    from PySide6 import QtWidgets
    from ui.mixer_widget import StemMixerWidget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    paths = {name: tmp_path / f"{name}.wav" for name in ("vocals", "instrumental", "bass")}
    for name, volume in (("vocals", 0.15), ("instrumental", 0.30), ("bass", 0.10)):
        _write_const_wav(paths[name], volume)

    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    widget = StemMixerWidget(mixer)
    try:
        widget.load_stem_paths({name: paths[name] for name in ("vocals", "instrumental")})
        bass_button = next(b for b in widget.findChildren(QtWidgets.QPushButton) if b.text() == "仅贝斯")
        assert not bass_button.isEnabled()
        mixer.play(open_audio_device=False)
        mixer.apply_preset("instrumental_mix")
        mixer.apply_preset("bass_only")
        assert np.allclose(mixer.render_block(256, advance=False), 0.30, atol=1e-3)

        widget.load_stem_paths({"vocals": paths["vocals"], "bass": paths["bass"]})
        assert bass_button.isEnabled()
        bass_button.click()
        mixer.play(open_audio_device=False)
        assert np.allclose(mixer.render_block(256, advance=False), 0.10, atol=1e-3)
        assert np.allclose(mixer.render_block(256), 0.10 * 10 ** (12 / 20), atol=1e-3)
        out = tmp_path / "bass-only-export.wav"
        mixer.export_mix_streaming(out)
        with wave.open(str(out), "rb") as wav:
            exported = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        assert np.allclose(exported / 32768.0, 0.10, atol=1e-3)
        widget.bass_monitor_boost_chk.click()
        assert np.allclose(mixer.render_block(256), 0.10, atol=1e-3)
    finally:
        mixer.clear()
        widget.close()
