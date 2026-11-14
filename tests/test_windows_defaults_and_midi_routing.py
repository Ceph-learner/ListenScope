"""Regression tests for Round 1/2 Windows installer baseline, 6s defaults, RAM guardrails, and standalone MIDI routing."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import mido
import numpy as np
from PySide6 import QtWidgets
import pytest

from ai.models import MODEL_REGISTRY
from audio.playback import StemMixerEngine
from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.models import AIJobRequest
from core.resource_manager import SimulationOverrides
from core.settings_store import PersistedSettings, load_settings, save_settings
from core.system_probe import (
    MIDI_ENV_SETUP_GUIDE,
    apply_external_ai_probe_to_report,
    probe_external_midi_environment,
    probe_system,
)
import main as main_mod
from ui.main_window import ListenScopeMainWindow
from ui.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parent.parent


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _write_bass_wav(path: Path, *, duration_sec: float = 1.5, freq_hz: float = 110.0) -> Path:
    sr = 48000
    n = int(sr * duration_sec)
    t = np.arange(n, dtype=np.float32) / float(sr)
    sig = 0.35 * np.sin(2.0 * np.pi * freq_hz * t)
    stereo = np.stack([sig, sig], axis=1)
    pcm16 = np.clip(stereo * 32767.0, -32768.0, 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    return path


def _wait_until(app: QtWidgets.QApplication, predicate, *, timeout_sec: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.03)
    app.processEvents()
    assert predicate(), f"Condition not satisfied within {timeout_sec}s"


def test_p0_installer_requirements_and_scripts() -> None:
    ai_req = (ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
    ai_lines = [ln.strip() for ln in ai_req.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not any(ln.startswith("basic-pitch") for ln in ai_lines)
    assert any("onnxruntime-gpu" in ln and "<1.27" in ln for ln in ai_lines)
    assert any(ln.startswith("audioread>=3.1.0") for ln in ai_lines)
    assert any(ln.startswith("demucs>=4.1.0") for ln in ai_lines)
    assert any(ln.startswith("audio-separator[gpu]>=0.48.0") for ln in ai_lines)
    assert "torch==2.11.0" in ai_req and "cu128" in ai_req
    assert "torchvision==0.26.0" in ai_req
    assert "constraints-ai-cu128.txt" in ai_req
    assert "sitecustomize.py" in ai_req

    constraints_txt = (ROOT / "constraints-ai-cu128.txt").read_text(encoding="utf-8")
    for pinned in (
        "torch==2.11.0+cu128",
        "torchaudio==2.11.0+cu128",
        "torchvision==0.26.0+cu128",
        "onnxruntime-gpu>=1.21.0,<1.27",
    ):
        assert pinned in constraints_txt

    midi_req = (ROOT / "requirements-midi.txt").read_text(encoding="utf-8")
    midi_lines = [ln.strip() for ln in midi_req.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert any("basic-pitch>=0.4.0,<0.5" in ln for ln in midi_lines)
    assert any("tensorflow>=2.13.0,<2.15.1" in ln for ln in midi_lines)
    assert any("setuptools>=68.0,<81" in ln for ln in midi_lines)
    assert any(ln.startswith("psutil>=") for ln in midi_lines)
    assert any(ln.startswith("mido>=") for ln in midi_lines)
    assert "LongPathsEnabled" in midi_req

    ps1 = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    for token in (
        "[string]$MidiPythonExe",
        "[string]$MidiVenvPath",
        "[string]$CudaWheelDir",
        "[string]$TorchvisionSpec",
        "[switch]$SkipMidi",
        "[switch]$AllowUntestedPython",
        "Resolve-LocalCudaWheel",
        "%2B",
        "--find-links",
        "https://download.pytorch.org/whl/cu128",
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "torchvision==0.26.0",
        "cuda-constraints.txt",
        "PIP_CONSTRAINT",
        "-ExpectedMajor 3 -ExpectedMinor 12",
        "-ExpectedMajor 3 -ExpectedMinor 11",
        "requirements-midi.txt",
        "--check-midi-packages",
        '"pip", "check"',
        "ffmpeg",
    ):
        assert token in ps1

    win_req = (ROOT / "requirements-windows.txt").read_text(encoding="utf-8")
    for dep in (
        "winrt-runtime>=3.0",
        "winrt-Windows.Foundation>=3.0",
        "winrt-Windows.Foundation.Collections>=3.0",
        "winrt-Windows.Media.Control>=3.0",
    ):
        assert dep in win_req

    spec_text = (ROOT / "packaging" / "listenscope_core.spec").read_text(encoding="utf-8")
    assert "requirements-midi.txt" in spec_text
    assert "constraints-ai-cu128.txt" in spec_text
    assert '"basic_pitch"' in spec_text
    assert '"tensorflow"' in spec_text
    assert '"winrt.windows.media.control"' in spec_text

    packaging_doc = (ROOT / "docs" / "PACKAGING.md").read_text(encoding="utf-8")
    assert "constraints-ai-cu128.txt" in packaging_doc
    assert "LongPathsEnabled" in packaging_doc
    assert "-MidiVenvPath" in packaging_doc
    assert "-CudaWheelDir" in packaging_doc


def test_p0_check_env_json_and_gpu_readiness_without_basic_pitch() -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.check_env", "--json", "--check-ai-packages", "--check-midi-packages", "--no-write"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="ascii",
        check=True,
        timeout=20.0,
    )
    payload = json.loads(proc.stdout)
    assert "tools" in payload and "ffmpeg" in payload["tools"]
    assert "installed" in payload["tools"]["ffmpeg"]

    ai_pkgs = payload["ai_packages"]
    assert "audioread" in ai_pkgs
    assert ai_pkgs["basic_pitch"].get("optional") is True
    for k in ("demucs", "audio_separator", "basic_pitch", "onnxruntime", "soundfile", "mido"):
        assert k in ai_pkgs

    midi_pkgs = payload["midi_packages"]
    for k in ("basic_pitch", "tensorflow", "pkg_resources", "psutil", "mido"):
        assert k in midi_pkgs

    base = probe_system()
    merged = apply_external_ai_probe_to_report(
        base,
        {
            "ok": True,
            "python_executable": r"C:\ListenScope\.venv-ai\Scripts\python.exe",
            "gpus": [
                {
                    "index": 0,
                    "name": "NVIDIA GeForce RTX 5060 Ti",
                    "total_vram_mb": 8151.0,
                    "used_vram_mb": 500.0,
                    "free_vram_mb": 7651.0,
                    "driver_version": "616.64",
                    "source": "nvml",
                }
            ],
            "pytorch": {
                "installed": True,
                "version": "2.11.0+cu128",
                "cuda_available": True,
                "cuda_build": "12.8",
                "device_count": 1,
                "device_name": "NVIDIA GeForce RTX 5060 Ti",
                "compute_capability": [12, 0],
                "arch_list": ["sm_90", "sm_120"],
                "supports_sm_120": True,
                "kernel_smoke_test_passed": True,
            },
            "onnxruntime": {
                "installed": True,
                "version": "1.26.0",
                "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "cuda_provider_available": True,
            },
            "ai_packages": {
                "demucs": {"installed": True, "version": "4.1.0"},
                "audio_separator": {"installed": True, "version": "0.48.0"},
                "audioread": {"installed": True, "version": "3.1.0"},
                "basic_pitch": {"installed": False, "version": None, "optional": True},
                "onnxruntime": {"installed": True, "version": "1.26.0"},
                "soundfile": {"installed": True, "version": "0.13.1"},
                "mido": {"installed": True, "version": "1.3.3"},
            },
        },
    )
    assert merged.gpu_ai_ready is True
    assert merged.gpu_ai_block_reason is None
    assert merged.gpus[0].total_vram_mb == pytest.approx(8151.0)


def test_p0_defaults_mdx_segment_preserved_and_legacy_settings_compat(tmp_path: Path) -> None:
    app = _get_app()
    default_cfg = AIConfig()
    assert default_cfg.long_audio_chunk_seconds == pytest.approx(6.0)
    assert default_cfg.demucs_default_segment_sec == 6
    assert default_cfg.mdx_segment_size == 256
    assert MODEL_REGISTRY["htdemucs_4stem"].default_segment_sec == 6
    assert MODEL_REGISTRY["mdx_low_vram_2stem"].default_segment_sec == 256

    req = AIJobRequest(
        task_id="t1",
        input_wav_path="in.wav",
        output_dir=str(tmp_path),
        stem_mode="4stem",
        model_id="htdemucs_4stem",
    )
    assert req.segment_seconds == 6
    assert req.chunk_seconds == pytest.approx(6.0)

    legacy_file = tmp_path / "legacy_v2_settings.json"
    legacy_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "resource_limits": {"pause_ram_before_ai_mb": 3200.0},
                "ai_config": {
                    "long_audio_chunk_seconds": 15.0,
                    "mdx_segment_size": 256,
                },
                "ai_python_executable": r"C:\ListenScope\.venv-ai\Scripts\python.exe",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_settings(legacy_file)
    assert loaded.resource_limits.pause_ram_before_ai_mb == pytest.approx(3200.0)
    assert loaded.ai_config.long_audio_chunk_seconds == pytest.approx(15.0)
    assert loaded.ai_config.demucs_default_segment_sec == 6
    assert loaded.ai_config.mdx_segment_size == 256
    assert loaded.midi_python_executable == ""

    v3_file = tmp_path / "v3_settings.json"
    save_settings(
        PersistedSettings(
            resource_limits=ResourceLimits(),
            ai_config=AIConfig(long_audio_chunk_seconds=9.5, demucs_default_segment_sec=8),
            ai_python_executable=r"C:\ListenScope\.venv-ai\Scripts\python.exe",
            midi_python_executable=r"C:\ListenScope\.venv-midi\Scripts\python.exe",
        ),
        v3_file,
    )
    reloaded = load_settings(v3_file)
    assert reloaded.ai_config.long_audio_chunk_seconds == pytest.approx(9.5)
    assert reloaded.ai_config.demucs_default_segment_sec == 8
    assert reloaded.ai_config.mdx_segment_size == 256
    assert reloaded.midi_python_executable == r"C:\ListenScope\.venv-midi\Scripts\python.exe"

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        assert mw.segment_spin.value() == 6
    finally:
        mw.close()
        app.processEvents()

    dlg = SettingsDialog(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        ai_python_executable="/fake/ai/python",
        midi_python_executable="/fake/midi/python",
    )
    try:
        assert dlg.chunk_sec_spin.value() == pytest.approx(6.0)
        assert dlg.demucs_seg_spin.value() == 6
        assert dlg.midi_python_edit.text() == "/fake/midi/python"

        dlg._on_midi_probe_finished({"ok": False, "error": "missing exe", "setup_guide": MIDI_ENV_SETUP_GUIDE})
        assert MIDI_ENV_SETUP_GUIDE in dlg.midi_probe_result_lbl.text()

        dlg._on_midi_probe_finished(
            {
                "ok": True,
                "python_executable": "/fake/midi/python",
                "python_version": "3.11.9",
                "midi_ready": True,
                "midi_packages": {
                    "basic_pitch": {"installed": True},
                    "tensorflow": {"installed": True},
                    "pkg_resources": {"installed": True},
                    "psutil": {"installed": True},
                    "mido": {"installed": True},
                },
            }
        )
        assert "READY" in dlg.midi_probe_result_lbl.text()

        dlg.chunk_sec_spin.setValue(12.0)
        dlg.demucs_seg_spin.setValue(8)
        dlg.midi_python_edit.setText("/new/midi311/python")
        dlg._on_accept()
        assert dlg.updated_ai_config is not None
        assert dlg.updated_ai_config.long_audio_chunk_seconds == pytest.approx(12.0)
        assert dlg.updated_ai_config.demucs_default_segment_sec == 8
        assert dlg.updated_ai_config.mdx_segment_size == 256
        assert dlg.updated_midi_python == "/new/midi311/python"
    finally:
        dlg.close()
        app.processEvents()


def test_p0_ram_guardrail_refusal_shows_available_ram_and_reason(tmp_path: Path) -> None:
    app = _get_app()
    work_dir = tmp_path / "work"
    ctrl = main_mod.ListenScopeController(
        use_mock_ai_for_demo=True,
        work_dir=work_dir,
        settings_path=tmp_path / "settings.json",
    )
    try:
        ctrl._timer.stop()
        t = np.arange(48000, dtype=np.float32) / 48000.0
        tone = 0.25 * np.sin(2.0 * np.pi * 220.0 * t)
        ctrl.ring_buffer.write(np.stack([tone, tone], axis=1).astype(np.float32))
        ctrl.resource_manager.set_simulation_overrides(
            SimulationOverrides(
                system_ram_total_mb=16384.0,
                system_ram_available_mb=2500.0,
                main_ram_mb=260.0,
            )
        )
        ctrl._on_start_ai_separation("4stem", "htdemucs_4stem", 6, False)
        app.processEvents()

        assert ctrl.ai_job_manager.is_busy is False
        assert ctrl.window.ai_status_badge.text() == "AI: Blocked"
        assert ctrl.window.mixer_widget.job_progress.value() == 0
        banner = ctrl.window.notice_banner.text()
        status = ctrl.window.mixer_widget.job_status_lbl.text()
        for text in (banner, status):
            assert "2500" in text
            assert "3072" in text
            assert "RAM" in text
        jobs_root = work_dir / "ai_jobs"
        leftover = list(jobs_root.glob("job_*")) if jobs_root.exists() else []
        assert leftover == []

        ctrl.resource_manager.set_simulation_overrides(
            SimulationOverrides(
                system_ram_total_mb=16384.0,
                system_ram_available_mb=1900.0,
                main_ram_mb=260.0,
            )
        )
        should_stop, stop_reason = ctrl.resource_manager.should_emergency_stop_ai()
        assert should_stop is True
        assert stop_reason is not None
        assert "1900" in stop_reason
        assert "2048" in stop_reason
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()


def test_p1_midi_probe_discovery_settings_and_standalone_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _get_app()

    missing_probe = probe_external_midi_environment(str(tmp_path / "missing_python"))
    assert missing_probe["ok"] is False
    assert missing_probe["midi_ready"] is False
    assert ".venv-midi" in missing_probe["error"]
    assert MIDI_ENV_SETUP_GUIDE in missing_probe["setup_guide"]

    cur_probe = probe_external_midi_environment(sys.executable)
    assert cur_probe["ok"] is True
    assert cur_probe["midi_ready"] is False
    assert "basic_pitch" in cur_probe["missing_packages"]
    assert MIDI_ENV_SETUP_GUIDE in cur_probe["midi_block_reason"]

    fake_root = tmp_path / "repo_layout"
    fake_midi_exe = fake_root / ".venv-midi" / "bin" / "python"
    fake_midi_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_midi_exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    monkeypatch.setattr(main_mod, "ROOT", fake_root)
    assert main_mod._discover_midi_python_executable() == str(fake_midi_exe)

    bass_wav = _write_bass_wav(tmp_path / "stems" / "bass.wav", duration_sec=1.5, freq_hz=110.0)

    # Case A: Missing MIDI interpreter in live mode -> lightweight fallback + explicit algorithm & setup guide
    ctrl_fallback = main_mod.ListenScopeController(
        use_mock_ai_for_demo=False,
        ai_python_executable=str(tmp_path / "missing_ai_py"),
        midi_python_executable="",
        work_dir=tmp_path / "work_fb",
        settings_path=tmp_path / "settings_fb.json",
    )
    try:
        ctrl_fallback._timer.stop()
        ctrl_fallback.window.mixer_widget.load_stem_paths({"bass": str(bass_wav)})
        ctrl_fallback._on_transcribe_stem_midi("bass", str(bass_wav))
        _wait_until(app, lambda: not ctrl_fallback._ui_midi_result_q.empty() or ctrl_fallback._latest_midi_result is not None)
        ctrl_fallback._on_ui_tick()
        app.processEvents()

        res = ctrl_fallback._latest_midi_result
        assert res is not None
        assert res.backend_used == "cpu_monophonic_fallback_test"
        assert res.output_midi_path is not None and res.output_midi_path.exists()

        info_text = ctrl_fallback.window.mixer_widget.midi_info_lbl.text()
        banner_text = ctrl_fallback.window.notice_banner.text()
        plot_title = ctrl_fallback.window.mixer_widget.piano_roll_plot.getPlotItem().titleLabel.text
        assert "cpu_monophonic_fallback_test" in info_text
        assert "cpu_monophonic_fallback_test" in banner_text
        assert "cpu_monophonic_fallback_test" in plot_title
        assert ".venv-midi" in info_text
        assert ctrl_fallback.window.mixer_widget.save_midi_btn.isEnabled() is True
    finally:
        ctrl_fallback.window.close()
        ctrl_fallback.shutdown()
        app.processEvents()

    # Case B: Configured external MIDI interpreter -> routes strictly via midi_python (never ai_python)
    invoked_log = tmp_path / "midi_invocations.jsonl"
    stub_midi_py = tmp_path / "stub_midi_python"
    stub_midi_py.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import argparse, json, sys",
                "from pathlib import Path",
                "import mido",
                "p = argparse.ArgumentParser()",
                "p.add_argument('-m', dest='module')",
                "p.add_argument('--audio', required=True)",
                "p.add_argument('--output-midi', required=True)",
                "p.add_argument('--stem-name', default='bass')",
                "p.add_argument('--allow-cpu-fallback', action='store_true')",
                "p.add_argument('--json', action='store_true')",
                "args, unknown = p.parse_known_args()",
                f"log_p = Path({str(invoked_log)!r})",
                "log_p.parent.mkdir(parents=True, exist_ok=True)",
                "log_p.open('a', encoding='utf-8').write(json.dumps({'argv': sys.argv, 'module': args.module, 'stem': args.stem_name}) + '\\n')",
                "out = Path(args.output_midi)",
                "out.parent.mkdir(parents=True, exist_ok=True)",
                "mf = mido.MidiFile(ticks_per_beat=480)",
                "tr = mido.MidiTrack()",
                "mf.tracks.append(tr)",
                "tr.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))",
                "tr.append(mido.Message('note_on', note=45, velocity=96, time=0))",
                "tr.append(mido.Message('note_off', note=45, velocity=0, time=480))",
                "tr.append(mido.MetaMessage('end_of_track', time=0))",
                "mf.save(str(out))",
                "payload = {",
                "  'source_stem_name': args.stem_name,",
                "  'output_midi_path': str(out),",
                "  'notes': [{'pitch_midi': 45, 'note_name': 'A2', 'start_sec': 0.0, 'end_sec': 0.5, 'velocity': 96, 'confidence': 0.91}],",
                "  'backend_used': 'basic-pitch',",
                "  'warning': None",
                "}",
                "print('TensorFlow native startup noise', file=sys.stdout)",
                "print(json.dumps(payload), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    real_run = subprocess.run

    def run_midi_stub(args, *rest, **kwargs):
        if isinstance(args, list) and args[0] == str(stub_midi_py):
            args = [sys.executable, str(stub_midi_py), *args[1:]]
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", run_midi_stub)

    ctrl_ext = main_mod.ListenScopeController(
        use_mock_ai_for_demo=False,
        ai_python_executable=str(tmp_path / "nonexistent_ai_python"),
        midi_python_executable=str(stub_midi_py),
        work_dir=tmp_path / "work_ext",
        settings_path=tmp_path / "settings_ext.json",
    )
    try:
        ctrl_ext._timer.stop()
        ctrl_ext.window.mixer_widget.load_stem_paths({"bass": str(bass_wav)})
        ctrl_ext._on_transcribe_stem_midi("bass", str(bass_wav))
        _wait_until(app, lambda: not ctrl_ext._ui_midi_result_q.empty() or ctrl_ext._latest_midi_result is not None)
        ctrl_ext._on_ui_tick()
        app.processEvents()

        assert invoked_log.exists()
        recs = [json.loads(ln) for ln in invoked_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(recs) == 1
        assert recs[0]["module"] == "analysis.midi_transcription"
        assert recs[0]["stem"] == "bass"

        res_ext = ctrl_ext._latest_midi_result
        assert res_ext is not None
        assert res_ext.backend_used == "basic-pitch"
        assert len(res_ext.notes) == 1
        assert res_ext.notes[0].note_name == "A2"
        assert res_ext.output_midi_path is not None and res_ext.output_midi_path.exists()
        mid_parsed = mido.MidiFile(str(res_ext.output_midi_path))
        assert len(mid_parsed.tracks) >= 1

        info_text = ctrl_ext.window.mixer_widget.midi_info_lbl.text()
        plot_title = ctrl_ext.window.mixer_widget.piano_roll_plot.getPlotItem().titleLabel.text
        assert "Spotify Basic Pitch CPU (basic-pitch)" in info_text
        assert "Spotify Basic Pitch CPU (basic-pitch)" in plot_title
        assert ctrl_ext.window.mixer_widget.analysis_tabs.currentIndex() == 2
        assert ctrl_ext.window.mixer_widget.save_midi_btn.isEnabled() is True

        # Save settings through controller and verify persistence
        ctrl_ext._on_settings_applied(
            ctrl_ext.resource_limits,
            AIConfig(long_audio_chunk_seconds=6.0, demucs_default_segment_sec=6),
            ctrl_ext.ai_job_manager.ai_python_executable or "",
            midi_python=str(stub_midi_py),
        )
        persisted = load_settings(tmp_path / "settings_ext.json")
        assert persisted.midi_python_executable == str(stub_midi_py)
    finally:
        ctrl_ext.window.close()
        ctrl_ext.shutdown()
        app.processEvents()


def test_p1_run_external_python_frozen_windows_dll_and_sys_path_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes
    from core.paths import run_external_python

    bundle_dir = (tmp_path / "dist" / "ListenScopeCore" / "_internal").resolve()
    bundle_sub = bundle_dir / "torch" / "lib"
    bundle_sub.mkdir(parents=True, exist_ok=True)

    # Plant a poison '_socket.py' inside the frozen bundle root to simulate bundled
    # Python 3.12 '_socket.pyd' in _internal. External Python 3.11 must import its
    # own stdlib '_socket' first because bundle_dir is appended at the end of sys.path.
    (bundle_dir / "_socket.py").write_text(
        "raise RuntimeError('Frozen bundle _socket shadowed external interpreter stdlib!')\n",
        encoding="utf-8",
    )

    # Plant a ListenScope bundle entrypoint module inside _internal
    pkg_dir = bundle_dir / "analysis"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "frozen_probe_entry.py").write_text(
        "\n".join(
            [
                "import _socket, json, os, sys",
                "payload = {",
                "    'argv': sys.argv,",
                "    'cwd': os.getcwd(),",
                "    'sys_path_tail': sys.path[-1],",
                "    'sys_path_head': sys.path[0],",
                "    'socket_ok': hasattr(_socket, 'socket'),",
                "    'env_path': os.environ.get('PATH', ''),",
                "    'env_pythonpath': os.environ.get('PYTHONPATH', ''),",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )

    ext_dir = (tmp_path / "midi_venv" / "Scripts").resolve()
    ext_dir.mkdir(parents=True, exist_ok=True)
    fake_ext_python = ext_dir / "python.exe"
    fake_ext_python.write_text("", encoding="utf-8")

    external_ffmpeg_dir = (tmp_path / "tools" / "ffmpeg" / "bin").resolve()
    external_ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    dll_calls: list[object] = []

    class _FakeSetDllDirectoryW:
        argtypes = None

        def __call__(self, arg: object) -> int:
            dll_calls.append(arg)
            return 1

    class _FakeKernel32:
        def __init__(self) -> None:
            self.SetDllDirectoryW = _FakeSetDllDirectoryW()

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, use_last_error=False: _FakeKernel32(), raising=False)

    real_popen = subprocess.Popen
    captured_popen: dict[str, object] = {}

    def fake_popen(command, *rest, **kwargs):
        # Verify SetDllDirectoryW(None) is active at the exact moment Popen is called
        captured_popen["dll_calls_at_spawn"] = list(dll_calls)
        captured_popen["command"] = list(command)
        captured_popen["cwd"] = kwargs.get("cwd")
        captured_popen["env"] = dict(kwargs.get("env") or {})
        real_cmd = [sys.executable, *command[1:]]
        return real_popen(real_cmd, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    input_env = os.environ.copy()
    input_env["PATH"] = os.pathsep.join([str(bundle_dir), str(bundle_sub), str(external_ffmpeg_dir)])
    input_env["PYTHONPATH"] = os.pathsep.join([str(bundle_dir), str(bundle_sub)])

    orig_args = [
        str(fake_ext_python),
        "-m",
        "analysis.frozen_probe_entry",
        "--audio",
        "bass.wav",
        "--json",
    ]
    res = run_external_python(
        orig_args,
        timeout=15.0,
        check=True,
        text=True,
        encoding="utf-8",
        env=input_env,
    )

    assert res.returncode == 0
    assert res.args == orig_args
    assert captured_popen["dll_calls_at_spawn"] == [None]
    assert dll_calls == [None, str(bundle_dir)]
    assert captured_popen["cwd"] == str(ext_dir)

    cmd = captured_popen["command"]
    assert isinstance(cmd, list)
    assert cmd[0] == str(fake_ext_python)
    assert cmd[1] == "-c"
    assert "sys.path.append(root)" in cmd[2]
    assert "runpy.run_module" in cmd[2]
    assert cmd[3:] == [str(bundle_dir), "analysis.frozen_probe_entry", "--audio", "bass.wav", "--json"]

    out = json.loads(res.stdout.strip())
    assert out["socket_ok"] is True
    assert out["cwd"] == str(ext_dir)
    assert out["sys_path_tail"] == str(bundle_dir)
    assert out["sys_path_head"] != str(bundle_dir)
    assert out["argv"][1:] == ["--audio", "bass.wav", "--json"]
    assert str(bundle_dir) not in out["env_path"].split(os.pathsep)
    assert str(bundle_sub) not in out["env_path"].split(os.pathsep)
    assert str(external_ffmpeg_dir) in out["env_path"].split(os.pathsep)
    assert out["env_pythonpath"] == ""

