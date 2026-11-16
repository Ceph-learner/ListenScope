"""Phase 5 & 6 tests: Model registry, Demucs safety ladder, AIWorkerProcess, cancellation (Test E), and external venv mode."""

from __future__ import annotations

import sys
import threading
import time
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from ai.backend import build_separation_backend
from ai.job_manager import AIJobManager
from ai.models import list_models
from ai.resource_guard import stream_chunked_separation
from core.config import AIConfig, ResourceLimits
from core.logging import PerformanceLogger
from core.models import AIJobProgress, AIJobRequest, AIJobState, OOMRecoveryAction
from core.resource_manager import ResourceManager, SimulationOverrides
from separation.demucs_backend import DemucsSeparatorBackend
from separation.mdx_backend import SeparationOOMError


def _create_stereo_wav(path, duration_sec: float = 4.0, sr: int = 48000) -> None:
    total = int(duration_sec * sr)
    t = np.arange(total, dtype=np.float32) / float(sr)
    l = (0.3 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    r = (0.2 * np.sin(2.0 * np.pi * 329.63 * t)).astype(np.float32)
    pcm = np.column_stack([l, r])
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((pcm * 32767.0).astype(np.int16).tobytes())


@pytest.mark.parametrize("overlap_seconds", [0.0, 0.25])
def test_chunked_stems_crossfade_the_same_source_frames(tmp_path: Path, overlap_seconds: float) -> None:
    src = tmp_path / "ramp.wav"
    ramp = np.arange(26, dtype=np.int16) * 256
    with wave.open(str(src), "wb") as wf:
        wf.setparams((1, 2, 12, 0, "NONE", "not compressed"))
        wf.writeframes(ramp.astype("<i2").tobytes())
    chunk_offsets = iter((0.0, 0.5, -0.25))

    def separate(pcm: np.ndarray, sample_rate: int) -> dict[str, np.ndarray]:
        # Simulate the same stem at different inference levels in each window.
        return {"vocals": pcm + next(chunk_offsets)}

    result = stream_chunked_separation(
        src, tmp_path / "stems", ("vocals",), separate,
        chunk_seconds=1.0, overlap_seconds=overlap_seconds,
    )
    with wave.open(result["vocals"], "rb") as wf:
        assert (wf.getnchannels(), wf.getframerate(), wf.getnframes()) == (1, 12, len(ramp))
        got = np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2")

    offsets = np.repeat([0.0, 0.5, -0.25], [12, 12, 2]).astype(np.float32)
    if overlap_seconds:
        offsets[12:15] = [0.0, 0.25, 0.5]
        offsets[24:] = [0.5, -0.25]
    expected = ((ramp.astype(np.float32) / 32768 + offsets) * 32767).astype(np.int16)
    np.testing.assert_array_equal(got, expected)


def test_model_registry_priority_and_roformer_default_disabled() -> None:
    default_models = list_models()
    ids = [m.model_id for m in default_models]
    assert ids[0] == "mdx_low_vram_2stem"
    assert default_models[0].architecture == "MDX-ONNX"
    assert "htdemucs_4stem" in ids
    assert "bs_roformer_experimental" not in ids

    with pytest.raises(PermissionError):
        build_separation_backend("bs_roformer_experimental", use_mock_backend=False)

    all_models = list_models(include_experimental=True)
    assert any(m.model_id == "bs_roformer_experimental" for m in all_models)


def test_demucs_backend_enforces_jobs1_shifts1_and_bounded_oom_ladder(monkeypatch) -> None:
    """Inject lightweight fake torch + demucs modules to verify Demucs parameter safety & bounded OOM retry."""
    calls: list[dict] = []

    class FakeTensor:
        def __init__(self, arr: np.ndarray) -> None:
            self._arr = arr

        def unsqueeze(self, dim: int) -> "FakeTensor":
            return FakeTensor(np.expand_dims(self._arr, axis=dim))

        def to(self, *_args, **_kwargs) -> "FakeTensor":
            return self

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def numpy(self) -> np.ndarray:
            return self._arr

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    fake_torch = types.ModuleType("torch")
    fake_torch.float32 = "float32"
    fake_torch.from_numpy = lambda arr: FakeTensor(arr)
    fake_torch.inference_mode = _NoGrad
    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: True,
        empty_cache=lambda: None,
        ipc_collect=lambda: None,
        OutOfMemoryError=MemoryError,
    )

    class FakeDemucsModel:
        samplerate = 48000
        sources = ("drums", "bass", "other", "vocals")

        def to(self, _dev):
            return self

        def eval(self):
            return self

    def fake_apply_model(model, tensor, **kwargs):
        calls.append(kwargs)
        seg = kwargs["segment"]
        if seg >= 10:
            raise RuntimeError("CUDA out of memory during segment=10")
        n = tensor._arr.shape[-1]
        # Return fake batch of 4 stems
        return [[FakeTensor(np.zeros((2, n), dtype=np.float32)) for _ in range(4)]]

    fake_demucs = types.ModuleType("demucs")
    fake_apply_mod = types.ModuleType("demucs.apply")
    fake_apply_mod.apply_model = fake_apply_model
    fake_pre_mod = types.ModuleType("demucs.pretrained")
    fake_pre_mod.get_model = lambda _name: FakeDemucsModel()

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "demucs", fake_demucs)
    monkeypatch.setitem(sys.modules, "demucs.apply", fake_apply_mod)
    monkeypatch.setitem(sys.modules, "demucs.pretrained", fake_pre_mod)

    spec = [m for m in list_models() if m.model_id == "htdemucs_4stem"][0]
    cfg = AIConfig(max_oom_retries=1)
    backend = DemucsSeparatorBackend(spec, use_gpu=True, segment_seconds=10, ai_config=cfg)
    backend.load_model()

    # Segment=10 fails OOM -> steps down once to segment=8 and succeeds!
    out = backend.separate_chunk(np.zeros((48000, 2), dtype=np.float32), 48000)
    assert set(out.keys()) == {"drums", "bass", "other", "vocals"}
    assert len(calls) == 2
    assert "jobs" not in calls[0] and calls[0]["num_workers"] == 0 and calls[0]["shifts"] == 1 and calls[0]["segment"] == 10.0
    assert "jobs" not in calls[1] and calls[1]["num_workers"] == 0 and calls[1]["shifts"] == 1 and calls[1]["segment"] == 8.0

    # HTDemucs model.max_allowed_segment (e.g. 7.8s) must clamp & deduplicate the ladder safely
    backend._model.max_allowed_segment = 7.8
    assert backend._segment_ladder() == [7.8, 6.0, 4.0]

    # If even smaller segments still OOM after max_oom_retries=1, raises SeparationOOMError cleanly without looping forever
    def always_oom(*_a, **kwargs):
        raise RuntimeError("CUDA out of memory")

    backend._apply_model_fn = always_oom
    with pytest.raises(SeparationOOMError) as exc_info:
        backend.separate_chunk(np.zeros((48000, 2), dtype=np.float32), 48000)
    assert exc_info.value.recovery_options == [
        OOMRecoveryAction.REDUCE_SEGMENT,
        OOMRecoveryAction.LIGHTER_MODEL,
        OOMRecoveryAction.CPU_FALLBACK,
    ]
    backend.unload_model()


def test_ai_job_manager_serial_execution_and_gpu_gate(tmp_path) -> None:
    wav_path = tmp_path / "input.wav"
    _create_stereo_wav(wav_path, duration_sec=4.0)

    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0, vram_free_mb=6500.0, vram_total_mb=8192.0))
    perf = PerformanceLogger(log_dir=tmp_path / "perf")
    mgr = AIJobManager(rm, performance_logger=perf)

    # 1. Must block real GPU job when gpu_ai_ready=False
    bad_gpu_req = AIJobRequest(
        task_id="blocked_gpu",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "out_bad"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=True,
        use_mock_backend=False,
    )
    ok_gpu, msg_gpu = mgr.submit_job(bad_gpu_req, gpu_ai_ready=False, gpu_block_reason="PyTorch lacks sm_120")
    assert ok_gpu is False
    assert "sm_120" in msg_gpu

    # 2. Normal 2-stem mock worker job + reject parallel 2nd job
    out_dir = tmp_path / "out_2stem"
    req1 = AIJobRequest(
        task_id="job_a",
        input_wav_path=str(wav_path),
        output_dir=str(out_dir),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        chunk_seconds=2.0,
        simulate_delay_sec=0.15,
        use_mock_backend=True,
    )
    ok, _ = mgr.submit_job(req1)
    assert ok is True

    req2 = AIJobRequest(
        task_id="job_b",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "out_b"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
    )
    ok2, reason2 = mgr.submit_job(req2)
    assert ok2 is False
    assert "并行" in reason2 or "1" in reason2

    res = mgr.wait_for_completion(timeout=20.0)
    assert res is not None and res.state == AIJobState.COMPLETED
    assert set(res.stem_paths.keys()) == {"vocals", "instrumental"}
    for p in res.stem_paths.values():
        assert (out_dir / p.split("/")[-1]).exists()
    assert not (out_dir / ".tmp_job_a").exists()
    assert len(perf.recent_records()) == 1
    assert mgr.is_busy is False
    rm.close()


@pytest.mark.parametrize("target_stage", [AIJobState.LOADING_MODEL, AIJobState.INFERRING, AIJobState.WRITING])
def test_cancel_ai_job_at_every_stage_cleans_temps(tmp_path, target_stage: AIJobState) -> None:
    """Test E: Cancel during LoadingModel, Inferring, and Writing cleanly stops worker and removes temp files."""
    wav_path = tmp_path / "cancel_in.wav"
    _create_stereo_wav(wav_path, duration_sec=6.0)
    out_dir = tmp_path / f"out_{target_stage.value}"

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(rm, performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"))

    stage_hit = threading.Event()

    def _on_prog(p: AIJobProgress) -> None:
        if p.state == target_stage:
            stage_hit.set()

    mgr.add_progress_callback(_on_prog)
    req = AIJobRequest(
        task_id=f"cancel_{target_stage.value}",
        input_wav_path=str(wav_path),
        output_dir=str(out_dir),
        stem_mode="4stem",
        model_id="htdemucs_4stem",
        use_gpu=False,
        chunk_seconds=2.0,
        simulate_delay_sec=0.35,
        use_mock_backend=True,
    )
    ok, _ = mgr.submit_job(req)
    assert ok is True
    assert stage_hit.wait(timeout=10.0), f"Never reached stage {target_stage.value}"

    res = mgr.cancel_job(timeout=5.0)
    assert res is not None and res.state == AIJobState.CANCELLED
    assert not (out_dir / f".tmp_{req.task_id}").exists()
    assert list(out_dir.glob("*.wav")) == []
    assert mgr.is_busy is False
    rm.close()


def test_external_ai_venv_subprocess_mode(tmp_path, external_python) -> None:
    """Verify Core -> external AI Worker CLI subprocess protocol (`-m ai.worker`) works cleanly."""
    wav_path = tmp_path / "ext_in.wav"
    _create_stereo_wav(wav_path, duration_sec=2.0)

    rm = ResourceManager()
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=12000.0))
    mgr = AIJobManager(
        rm,
        performance_logger=PerformanceLogger(log_dir=tmp_path / "perf"),
        ai_python_executable=external_python,
    )
    assert mgr._uses_external_python()
    req = AIJobRequest(
        task_id="ext_job",
        input_wav_path=str(wav_path),
        output_dir=str(tmp_path / "ext_out"),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        chunk_seconds=2.0,
        use_mock_backend=True,
    )
    ok, _ = mgr.submit_job(req)
    assert ok is True
    res = mgr.wait_for_completion(timeout=15.0)
    assert res is not None and res.state == AIJobState.COMPLETED

    # Also invoke python -m ai.worker CLI directly end-to-end
    import json
    import subprocess
    from dataclasses import asdict

    cli_out = tmp_path / "cli_out"
    req2 = AIJobRequest(
        task_id="cli_job",
        input_wav_path=str(wav_path),
        output_dir=str(cli_out),
        stem_mode="2stem",
        model_id="mdx_low_vram_2stem",
        use_gpu=False,
        use_mock_backend=True,
    )
    req_json = tmp_path / "req.json"
    cfg_json = tmp_path / "cfg.json"
    cancel_flag = tmp_path / "cancel.flag"
    req_json.write_text(json.dumps(asdict(req2)), encoding="utf-8")
    cfg_json.write_text(json.dumps(asdict(AIConfig())), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "ai.worker", "--request-json", str(req_json), "--config-json", str(cfg_json), "--cancel-flag", str(cancel_flag)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20.0,
        check=True,
    )
    lines = [json.loads(line) for line in proc.stdout.strip().splitlines() if line.strip()]
    assert lines[-1]["type"] == "result"
    assert lines[-1]["payload"]["state"] == "Completed"
    rm.close()
