"""Phase 2 tests: Fixed 120s PCM Ring Buffer and bounded PerformanceLogger."""

from __future__ import annotations

import json
import wave

import numpy as np

from audio.ring_buffer import FixedRingBuffer
from core.config import AudioConfig
from core.logging import PerformanceLogger
from core.models import AIJobRequest, AIJobResult, AIJobState


def test_ring_buffer_preallocates_46mb_and_wraps_cleanly(tmp_path) -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, dtype="float32", ring_buffer_seconds=120)
    rb = FixedRingBuffer(cfg)

    # 120s * 48000 * 2ch * 4 bytes = 46,080,000 bytes
    assert rb.buffer_nbytes == 46_080_000
    base_ptr = rb._buffer.ctypes.data

    # Test wrap-around cleanly with a smaller ring (2s) to validate exact sample ordering fast
    small_cfg = AudioConfig(sample_rate=100, channels=2, dtype="float32", ring_buffer_seconds=2)
    srb = FixedRingBuffer(small_cfg)
    assert srb.capacity_frames == 200
    s_ptr = srb._buffer.ctypes.data

    # Write 350 sequential numbered frames -> buffer keeps last 200 frames [150..349]
    for start in range(0, 350, 50):
        idx = np.arange(start, start + 50, dtype=np.float32)
        chunk = np.column_stack([idx, -idx])
        srb.write(chunk)

    assert srb._buffer.ctypes.data == s_ptr  # Never reallocated
    assert srb.total_written_frames == 350
    assert srb.available_frames == 200
    assert srb.oldest_abs_frame == 150

    tail, s_abs, e_abs = srb.read_recent(1.5)
    assert (s_abs, e_abs) == (200, 350)
    assert np.allclose(tail[:, 0], np.arange(200, 350, dtype=np.float32))
    assert np.allclose(tail[:, 1], -np.arange(200, 350, dtype=np.float32))

    # Stream WAV export of wrapped normalized audio
    srb.clear()
    tone = (0.5 * np.sin(np.linspace(0, 8 * np.pi, 250, dtype=np.float32))).astype(np.float32)
    srb.write(np.column_stack([tone, tone]))
    out_wav = tmp_path / "ab_excerpt.wav"
    path, dur = srb.export_wav_streaming(out_wav, 100, 250, chunk_frames=40)
    assert path.exists()
    assert abs(dur - 1.5) < 0.05
    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == 100
        assert wf.getnchannels() == 2
        assert wf.getnframes() == 150


def test_performance_logger_writes_bounded_jsonl(tmp_path) -> None:
    perf = PerformanceLogger(log_dir=tmp_path / "perf", history_maxlen=3)
    req = AIJobRequest(
        task_id="t1",
        input_wav_path="in.wav",
        output_dir=str(tmp_path),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        chunk_seconds=20.0,
        segment_seconds=256,
        overlap=0.25,
    )
    for i in range(5):
        res = AIJobResult(
            task_id=f"t{i}",
            state=AIJobState.COMPLETED,
            elapsed_sec=1.2 + i,
            input_duration_sec=10.0,
            rtf=0.12,
            device_used="MockCPU",
            model_id="mdx_low_vram_2stem",
            architecture="MDX-ONNX",
            start_ram_mb=100.0,
            peak_ram_mb=150.0,
            end_ram_mb=105.0,
        )
        out_file = perf.log_job(req, res)

    assert len(perf.recent_records()) == 3
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5
    parsed = json.loads(lines[-1])
    assert parsed["model_name"] == "mdx_low_vram_2stem"
    assert parsed["peak_ram_mb"] == 150.0
