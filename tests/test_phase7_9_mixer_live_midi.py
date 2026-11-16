"""Phase 8 & 9 tests: Experimental Live 2-stem separator (RTF gate, bounded drop, auto-stop) & Basic Pitch MIDI adapter."""

from __future__ import annotations

from queue import Queue
import sys
import time
from types import SimpleNamespace
import wave

import mido
import numpy as np
import pytest

from analysis.midi_transcription import transcribe_stem_to_midi
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.models import ResourceStatus
from core.resource_manager import ResourceManager, SimulationOverrides
from streaming import benchmark as benchmark_module
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


@pytest.mark.parametrize("test_seconds", [1.0, 2.0])
def test_live_benchmark_measures_new_output_frames(monkeypatch, test_seconds: float) -> None:
    chunk_sizes = []
    backend = SimpleNamespace(
        load_model=lambda: None,
        separate_chunk=lambda pcm, sr: chunk_sizes.append(pcm.shape[0]),
        unload_model=lambda: None,
    )
    clock = iter((0.0, 1.8))
    monkeypatch.setattr(benchmark_module, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(benchmark_module, "build_separation_backend", lambda *args, **kwargs: backend)
    monkeypatch.setattr(benchmark_module, "release_torch_and_memory", lambda: None)

    result = benchmark_live_model(
        use_gpu=False, use_mock_backend=True, test_duration_sec=test_seconds,
        audio_config=AudioConfig(sample_rate=8000),
        ai_config=AIConfig(live_chunk_seconds=2.0, live_overlap_seconds=0.25),
    )

    assert chunk_sizes == [16000]
    assert result.test_duration_sec == pytest.approx(1.75)
    assert result.rtf == pytest.approx(1.8 / 1.75)
    assert result.can_run_realtime is False


def test_experimental_live_separator_bounded_drop_and_auto_stop_on_resource_warning() -> None:
    aud_cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=30)
    ai_cfg = AIConfig(live_chunk_seconds=1.0, live_overlap_seconds=0.2, live_max_buffer_seconds=2.5)
    rb = FixedRingBuffer(aud_cfg)
    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))

    live = ExperimentalLiveSeparator(rb, rm, ai_config=ai_cfg, audio_config=aud_cfg)
    assert live.is_active is False  # Strictly disabled by default

    try:
        live._output_overwritten_frames = 12
        live._output_primed = True
        live._pull_playback_block(4, device_underflow=True)
        live._latest_rtf = 0.8
        ok, _ = live.start(
            model_id="mdx_low_vram_2stem",
            use_gpu=False,
            use_mock_backend=True,
            skip_benchmark=True,
        )
        assert ok is True
        assert live.is_active is True
        metrics = live.latest_metrics()
        assert (metrics.playback_rebuffers, metrics.device_underflows, metrics.rtf) == (0, 0, 0.0)
        assert metrics.output_overwritten_frames == 0

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
    metrics = live.latest_metrics()
    assert metrics.buffer_seconds == 0.0
    assert metrics.output_overwritten_frames == 6 + second_length - 8


def test_live_output_oversized_stems_keep_the_same_frame_offsets(live_output_ring) -> None:
    live = live_output_ring
    vocals = np.repeat((np.arange(10, dtype=np.float32) / 32)[:, None], 2, axis=1)
    inst = np.repeat((np.arange(12, dtype=np.float32) / 64)[:, None], 2, axis=1)
    live._append_output(vocals, inst)

    np.testing.assert_array_equal(live.pull_mixed_block(8), vocals[2:10] + inst[2:10])
    assert live.latest_metrics().output_overwritten_frames == 2


def test_live_output_does_not_count_consumed_frames_as_overwritten(live_output_ring) -> None:
    live = live_output_ring
    pcm = np.arange(14, dtype=np.float32)[:, None] / 16
    stereo = np.repeat(pcm, 2, axis=1)
    live._append_output(stereo[:6], np.zeros_like(stereo[:6]))
    np.testing.assert_array_equal(live.pull_mixed_block(4), stereo[:4])
    live._append_output(stereo[6:12], np.zeros_like(stereo[6:12]))
    assert live.latest_metrics().output_overwritten_frames == 0
    live._append_output(stereo[12:], np.zeros_like(stereo[12:]))
    np.testing.assert_array_equal(live.pull_mixed_block(8), stereo[6:14])
    assert live.latest_metrics().output_overwritten_frames == 2


def test_live_playback_primes_again_after_underrun(live_output_ring) -> None:
    live = live_output_ring
    pcm = np.full((3, 2), 0.25, dtype=np.float32)
    silent = np.zeros((4, 2), dtype=np.float32)
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4, device_underflow=True), silent)
    metrics = live.latest_metrics()
    assert (metrics.playback_rebuffers, metrics.device_underflows) == (0, 1)
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), np.full((4, 2), 0.5))
    np.testing.assert_array_equal(live._pull_playback_block(4), np.array([[0.5, 0.5]] * 2 + [[0, 0]] * 2))
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), silent)
    np.testing.assert_array_equal(live._pull_playback_block(4), silent)
    assert live.latest_metrics().playback_rebuffers == 1
    live._append_output(pcm, pcm)
    np.testing.assert_array_equal(live._pull_playback_block(4), np.full((4, 2), 0.5))


def test_live_rejects_stale_capture_before_worker_start(live_output_ring, monkeypatch) -> None:
    live = live_output_ring
    monkeypatch.setattr(live.resource_manager, "can_start_ai_job", lambda **_: pytest.fail("stale request reached worker admission"))
    ok, message = live.start(source_is_current=lambda: False)
    assert not ok and "捕获源已变化" in message
    assert not live.is_active and not live.is_starting


def test_live_output_open_mutes_and_discards_if_capture_changes(live_output_ring, monkeypatch) -> None:
    live = live_output_ring
    live._active = True
    source_current = True
    calls = []
    initial = np.empty((4, 2), dtype=np.float32)
    rendered = np.empty((4, 2), dtype=np.float32)

    class FakeStream:
        def __init__(self, *, callback, **kwargs):
            self.callback = callback

        def start(self):
            nonlocal source_current
            self.callback(initial, len(initial), None, SimpleNamespace(output_underflow=True))
            source_current = False
            self.callback(rendered, len(rendered), None, SimpleNamespace(output_underflow=True))

        def stop(self):
            calls.append("stop")

        def close(self):
            calls.append("close")

    pcm = np.full((8, 2), 0.25, dtype=np.float32)
    live._append_output(pcm, pcm)
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=FakeStream))
    live._ensure_output_stream(lambda: source_current)
    np.testing.assert_array_equal(initial, np.full((4, 2), 0.5))
    np.testing.assert_array_equal(rendered, np.zeros_like(rendered))
    assert calls == ["stop", "close"] and live._stream is None
    assert live._out_available == 4
    assert live.latest_metrics().device_underflows == 1


def test_live_ignores_duplicate_results_and_drops_overlap_across_gap(live_output_ring, monkeypatch) -> None:
    live = live_output_ring
    live.resource_manager.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    responses = Queue()
    for seq, sample in ((0, 0.125), (0, 0.25), (2, 0.375), (1, 0.5)):
        pcm = np.full((live._chunk_frames, 2), sample, dtype=np.float32)
        responses.put({"type": "chunk", "seq": seq, "shape": pcm.shape, "infer_sec": 0.75,
                       "vocals": pcm.tobytes(), "instrumental": bytes(pcm.nbytes)})
    live._res_q = responses
    monkeypatch.setattr(live, "_is_worker_alive", lambda: True)
    monkeypatch.setattr(live._stop_event, "wait", lambda timeout: live._stop_event.set())

    live._run_loop()

    np.testing.assert_array_equal(live.pull_mixed_block(8), np.repeat(
        np.array([0.125] * 3 + [0.375] * 3 + [0.0] * 2)[:, None], 2, axis=1
    ))
    assert live.latest_metrics().rtf == 1.0


def test_live_callback_mixes_wrapped_spans_in_place_and_silences_tail(live_output_ring, monkeypatch) -> None:
    live = live_output_ring
    live._active = True
    live._mix_scratch = live._mix_scratch[:2]
    live.set_gains(0.75, 0.5)
    frames = np.arange(1, 12, dtype=np.float32) / 16
    pcm = np.column_stack((frames, -frames))
    live._append_output(pcm[:6], pcm[:6] / 2)
    live.pull_mixed_block(4)
    live._append_output(pcm[6:], pcm[6:] / 2)

    class FakeStream:
        def __init__(self, *, callback, **kwargs):
            self.callback = callback

        def start(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=FakeStream))
    live._ensure_output_stream()
    out = np.full((5, 2), np.nan, dtype=np.float32)
    tail = np.full((4, 2), np.nan, dtype=np.float32)
    stopped = np.full((4, 2), np.nan, dtype=np.float32)

    def unexpected_allocation(*args, **kwargs):
        pytest.fail("callback allocated a new sample block")

    with monkeypatch.context() as patch:
        for name in ("empty", "zeros", "vstack"):
            patch.setattr(np, name, unexpected_allocation)
        live._stream.callback(out, len(out), None, None)
        live._stream.callback(tail, len(tail), None, None)
        live._stop_event.set()
        live._stream.callback(stopped, len(stopped), None, SimpleNamespace(output_underflow=True))

    np.testing.assert_array_equal(out, pcm[4:9])
    np.testing.assert_array_equal(tail[:2], pcm[9:11])
    np.testing.assert_array_equal(tail[2:], np.zeros((2, 2), dtype=np.float32))
    np.testing.assert_array_equal(stopped, np.zeros((4, 2), dtype=np.float32))
    metrics = live.latest_metrics()
    assert metrics.playback_rebuffers == 1 and metrics.device_underflows == 0


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
