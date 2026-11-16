"""Phase 8 & 9 tests: Experimental Live 2-stem separator (RTF gate, bounded drop, auto-stop) & Basic Pitch MIDI adapter."""

from __future__ import annotations

from queue import Queue
import time
import wave

import mido
import numpy as np
import pytest

from analysis.midi_transcription import transcribe_stem_to_midi
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.models import ResourceStatus
from core.resource_manager import ResourceManager, SimulationOverrides
from streaming.benchmark import benchmark_live_model
from streaming.live_separator import ExperimentalLiveSeparator


def _write_a4_stem(path, freq_hz: float = 440.0, duration_sec: float = 1.5, sr: int = 48000) -> None:
    t = np.arange(int(duration_sec * sr), dtype=np.float32) / float(sr)
    sig = (0.3 * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)
    pcm = np.column_stack([sig, sig])
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((pcm * 32767.0).astype(np.int16).tobytes())


def test_live_benchmark_gates_rtf_above_one() -> None:
    fast = benchmark_live_model(
        "mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
        simulate_delay_sec=0.0,
        test_duration_sec=2.0,
    )
    assert fast.can_run_realtime is True
    assert fast.rtf < 1.0

    # Inject 1.1s delay per 2.0s chunk => RTF >= 0.55..1.1; 1.2s per 1.0s chunk triggers RTF >= 1.0 cleanly
    slow_cfg = AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.1, live_max_buffer_seconds=3.0)
    slow = benchmark_live_model(
        "mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
        simulate_delay_sec=1.2,
        test_duration_sec=1.0,
        ai_config=slow_cfg,
    )
    assert slow.can_run_realtime is False
    assert slow.rtf >= 1.0
    assert "无法实时运行" in slow.message


def test_experimental_live_separator_bounded_drop_and_auto_stop_on_resource_warning() -> None:
    aud_cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=30)
    ai_cfg = AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.2, live_max_buffer_seconds=2.5)
    rb = FixedRingBuffer(aud_cfg)
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))

    live = ExperimentalLiveSeparator(rb, rm, ai_config=ai_cfg, audio_config=aud_cfg)
    assert live.is_active is False  # Strictly disabled by default

    try:
        ok, _ = live.start(
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
            skip_benchmark=True,
        )
        assert ok is True
        assert live.is_active is True

        # Push > max_buffer_seconds immediately to force bounded drop protection
        t = np.arange(48000 * 5, dtype=np.float32) / 48000.0
        tone = (0.25 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
        rb.write(np.column_stack([tone, tone]))
        time.sleep(0.5)

        metrics = live.latest_metrics()
        assert metrics.buffer_seconds <= ai_cfg.live_max_buffer_seconds + 0.05
        assert metrics.dropped_chunks >= 1

        # Simulate tight RAM (WARNING status) -> live separator must auto-stop cleanly
        rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=4000.0))
        assert rm.sample().status == ResourceStatus.WARNING
        deadline = time.monotonic() + 5.0
        while live.is_active and time.monotonic() < deadline:
            time.sleep(0.05)

        assert live.is_active is False
        assert "自动停止" in live.latest_metrics().status_message
    finally:
        live.stop()
        rm.close()


@pytest.fixture
def live_output_ring():
    audio = AudioConfig(sample_rate=4, channels=2, ring_buffer_seconds=2)
    ai = AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.2, live_max_buffer_seconds=2.0)
    resources = ResourceManager()
    try:
        yield ExperimentalLiveSeparator(FixedRingBuffer(audio), resources, ai_config=ai)
    finally:
        resources.close()


def test_live_output_consumes_fifo_across_callbacks(live_output_ring) -> None:
    frames = np.arange(1, 14, dtype=np.float32) / 16
    stereo = np.column_stack((frames, -frames))
    live = live_output_ring
    live._append_output(stereo[:6], stereo[:6] / 2)
    np.testing.assert_array_equal(live.pull_mixed_block(4), stereo[:4] * 1.5)
    assert live.latest_metrics().buffer_seconds == 0.5

    # With an eight-frame ring, this makes both the next write and read wrap.
    live._append_output(stereo[6:11], stereo[6:11] / 2)
    np.testing.assert_array_equal(live.pull_mixed_block(5), stereo[4:9] * 1.5)
    tail_audio = np.clip(stereo[9:11] * 1.5, -1.0, 1.0)
    expected_tail = np.vstack((tail_audio, np.zeros((2, 2), dtype=np.float32)))
    np.testing.assert_array_equal(live.pull_mixed_block(4), expected_tail)
    np.testing.assert_array_equal(live.pull_mixed_block(4), np.zeros((4, 2), dtype=np.float32))
    assert live.latest_metrics().buffer_seconds == 0.0

    live._append_output(stereo[11:], stereo[11:])
    mixed = live.pull_mixed_block(2, vocals_gain=0.5, inst_gain=1.0)
    np.testing.assert_array_equal(mixed, np.clip(stereo[11:] * 1.5, -1.0, 1.0))


@pytest.mark.parametrize("second_length", [4, 8, 10])
def test_live_output_overflow_retains_newest_unread_frames(live_output_ring, second_length) -> None:
    frames = np.arange(1, 7 + second_length, dtype=np.float32) / 32
    stereo = np.column_stack((frames, -frames))
    live = live_output_ring
    live._append_output(stereo[:6], np.zeros_like(stereo[:6]))
    live._append_output(stereo[6:], np.zeros_like(stereo[6:]))
    np.testing.assert_array_equal(live.pull_mixed_block(3), stereo[-8:-5])
    np.testing.assert_array_equal(live.pull_mixed_block(5), stereo[-5:])
    assert live.latest_metrics().buffer_seconds == 0.0


def test_live_playback_primes_again_after_underrun(live_output_ring) -> None:
    live = live_output_ring
    pcm = np.full((3, 2), 0.25, dtype=np.float32)
    silent = np.zeros((4, 2), dtype=np.float32)
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), silent)
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), np.full((4, 2), 0.5))
    np.testing.assert_array_equal(live._pull_playback_block(4), np.array([[0.5, 0.5]] * 2 + [[0, 0]] * 2))
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), silent)
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), np.full((4, 2), 0.5))


def test_live_ignores_duplicate_results_and_drops_overlap_across_gap(live_output_ring, monkeypatch) -> None:
    live = live_output_ring
    live.resource_manager.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    responses = Queue()
    for seq, sample in ((0, 0.125), (0, 0.25), (2, 0.375), (1, 0.5)):
        pcm = np.full((live._chunk_frames, 2), sample, dtype=np.float32)
        responses.put({"type": "chunk", "seq": seq, "shape": pcm.shape,
                       "vocals": pcm.tobytes(), "instrumental": bytes(pcm.nbytes)})
    live._res_q = responses
    monkeypatch.setattr(live, "_is_worker_alive", lambda: True)
    monkeypatch.setattr(live._stop_event, "wait", lambda timeout: live._stop_event.set())

    live._run_loop()

    np.testing.assert_array_equal(live.pull_mixed_block(8), np.repeat(
        np.array([0.125] * 3 + [0.375] * 3 + [0.0] * 2)[:, None], 2, axis=1
    ))


def test_midi_transcription_refuses_full_mix_and_writes_valid_midi_for_stem(tmp_path) -> None:
    mix_wav = tmp_path / "full_mix.wav"
    bass_wav = tmp_path / "song_bass.wav"
    _write_a4_stem(mix_wav, freq_hz=440.0, duration_sec=1.0)
    _write_a4_stem(bass_wav, freq_hz=110.0, duration_sec=1.2)  # A2 = MIDI 45

    with pytest.raises(ValueError, match="Basic Pitch"):
        transcribe_stem_to_midi(mix_wav, tmp_path / "mix.mid", stem_name="mix", allow_cpu_pitch_fallback=True)

    mid_out = tmp_path / "bass.mid"
    res = transcribe_stem_to_midi(
        bass_wav,
        mid_out,
        stem_name="bass",
        allow_full_mix=False,
        allow_cpu_pitch_fallback=True,
    )
    assert res.output_midi_path == mid_out
    assert mid_out.exists()
    assert len(res.notes) >= 1
    assert any(abs(n.pitch_midi - 45) <= 1 for n in res.notes)

    mid_file = mido.MidiFile(str(mid_out))
    msgs = [msg for tr in mid_file.tracks for msg in tr if msg.type == "note_on"]
    assert len(msgs) >= 1
