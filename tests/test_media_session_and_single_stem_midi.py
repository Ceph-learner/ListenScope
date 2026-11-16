"""Regression tests for single-stem WAV -> MIDI GUI entry, SMTC track-change auto-reset, and probe CLI."""

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

from core.config import AIConfig, ResourceLimits
from core.media_session import (
    MediaSessionSnapshot,
    TrackChangeTracker,
    match_session_to_process,
)
from core.models import (
    AnalysisSnapshot,
    ChordEstimate,
    KeyEstimate,
    PitchEstimate,
    TempoEstimate,
)
from core.settings_store import PersistedSettings, load_settings, save_settings
import main as main_mod

ROOT = Path(__file__).resolve().parent.parent


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wait_until(app: QtWidgets.QApplication, predicate, *, timeout_sec: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.03)
    app.processEvents()
    assert predicate(), f"Condition not satisfied within {timeout_sec}s"


def _write_bass_wav(path: Path, *, duration_sec: float = 1.6, freq_hz: float = 110.0) -> Path:
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


def _make_chord_snapshot(chord: str) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        timestamp=time.monotonic(),
        waveform_min=[-0.2, -0.1],
        waveform_max=[0.2, 0.1],
        fft_freqs_hz=[100.0, 200.0, 400.0],
        fft_db=[-40.0, -30.0, -35.0],
        log_freqs_hz=[100.0, 200.0, 400.0],
        log_spectrum_db=[-40.0, -30.0, -35.0],
        chroma_12=[0.8 if i in (0, 4, 7) else 0.1 for i in range(12)],
        chord=ChordEstimate(
            primary=chord,
            secondary="Am",
            stability="High",
            correlation=0.88,
            margin=0.20,
            is_silent=False,
        ),
        key=KeyEstimate(
            primary="C Major",
            secondary="A Minor",
            stability="High",
            correlation=0.84,
            margin=0.18,
            relation_note="关系大小调: C Major / A Minor",
        ),
        tempo=TempoEstimate(bpm=92.0, stability="High", confidence_score=0.85),
        pitch=PitchEstimate(frequency_hz=440.0, note_name="A4", cents_offset=0.0, confidence=0.9),
        rms_dbfs=-22.0,
        peak_dbfs=-14.0,
        window_seconds=2.0,
    )


@pytest.mark.parametrize("historical_job", [False, True], ids=["external", "historical-job"])
def test_single_stem_wav_direct_midi_export_and_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_job: bool,
) -> None:
    app = _get_app()

    # Stem name inference rules
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("bass.wav")) == "bass"
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("ListenScope-51f4554-bass.wav")) == "bass"
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("job_001_vocals.wav")) == "vocals"
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("lead_guitar_take2.wav")) == "guitar"
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("full_mix.wav")) == "mix"
    assert main_mod.ListenScopeController._infer_single_stem_name(Path("mix.wav")) == "mix"

    work_dir = tmp_path / "work"
    src_dir = work_dir / "stems" / "old_job" if historical_job else tmp_path / "previous_round_outputs"
    src_bass = _write_bass_wav(src_dir / "ListenScope-873db544-bass.wav", duration_sec=1.5, freq_hz=110.0)
    src_mix = _write_bass_wav(src_dir / "full_mix.wav", duration_sec=1.0, freq_hz=220.0)
    previous_midi = src_bass.with_suffix(".mid")
    original = mido.MidiFile()
    original.add_track().append(mido.Message("note_on", note=64))
    original.save(str(previous_midi))
    previous_bytes = previous_midi.read_bytes()

    invoked_log = tmp_path / "single_stem_midi_calls.jsonl"
    stub_midi_py = tmp_path / "stub_midi311.py"
    stub_midi_py.write_text(
        "\n".join(
            [
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
                "args, _ = p.parse_known_args()",
                f"Path({str(invoked_log)!r}).open('a', encoding='utf-8').write(json.dumps({{'audio': args.audio, 'out': args.output_midi, 'stem': args.stem_name}}) + '\\n')",
                "out = Path(args.output_midi)",
                "out.parent.mkdir(parents=True, exist_ok=True)",
                "mf = mido.MidiFile(ticks_per_beat=480)",
                "tr = mido.MidiTrack()",
                "mf.tracks.append(tr)",
                "tr.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))",
                "tr.append(mido.Message('note_on', note=40, velocity=92, time=0))",
                "tr.append(mido.Message('note_off', note=40, velocity=0, time=480))",
                "tr.append(mido.Message('note_on', note=45, velocity=88, time=0))",
                "tr.append(mido.Message('note_off', note=45, velocity=0, time=480))",
                "tr.append(mido.MetaMessage('end_of_track', time=0))",
                "mf.save(str(out))",
                "payload = {",
                "  'source_stem_name': args.stem_name,",
                "  'output_midi_path': str(out),",
                "  'notes': [",
                "    {'pitch_midi': 40, 'note_name': 'E2', 'start_sec': 0.0, 'end_sec': 0.5, 'velocity': 92, 'confidence': 0.90},",
                "    {'pitch_midi': 45, 'note_name': 'A2', 'start_sec': 0.5, 'end_sec': 1.0, 'velocity': 88, 'confidence': 0.92}",
                "  ],",
                "  'backend_used': 'basic-pitch',",
                "  'warning': None",
                "}",
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

    monkeypatch.chdir(tmp_path)
    ctrl = main_mod.ListenScopeController(
        use_mock_ai_for_demo=False,
        ai_python_executable="",
        midi_python_executable=str(stub_midi_py),
        work_dir=work_dir.relative_to(tmp_path),
        settings_path=tmp_path / "settings.json",
    )
    try:
        ctrl._timer.stop()
        # Start synthetic live capture and fill the ring before opening the WAV.
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})
        pre_t = np.arange(24000, dtype=np.float32) / 48000.0
        tone = 0.2 * np.sin(2.0 * np.pi * 220.0 * pre_t)
        ctrl.ring_buffer.write(np.stack([tone, tone], axis=1).astype(np.float32))
        pre_written = ctrl.ring_buffer.total_written_frames
        assert pre_written >= 24000
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running

        # Buttons must be exposed on mixer widget & MIDI tab
        assert ctrl.window.mixer_widget.open_stem_midi_btn.isEnabled() is True
        assert ctrl.window.mixer_widget.midi_open_stem_btn.isEnabled() is True

        ctrl._on_open_single_stem_midi(str(src_bass))
        _wait_until(app, lambda: not ctrl._ui_midi_result_q.empty() or ctrl._latest_midi_result is not None)
        ctrl._on_ui_tick()
        app.processEvents()

        # Live capture & 120s ring buffer must NOT be interrupted or cleared
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running
        assert ctrl.ring_buffer.total_written_frames >= pre_written

        assert previous_midi.read_bytes() == previous_bytes
        assert set(src_dir.iterdir()) == {src_bass, src_mix, previous_midi}

        # Intermediate MIDI placed inside work_dir/midi/
        res = ctrl._latest_midi_result
        assert res is not None
        assert res.source_stem_name == "bass"
        assert res.backend_used == "basic-pitch"
        assert len(res.notes) == 2
        assert res.output_midi_path is not None
        assert res.output_midi_path.exists()
        assert res.output_midi_path.resolve().is_relative_to((work_dir / "midi").resolve())

        # Routed through configured external midi_python with canonical stem_name='bass'
        recs = [json.loads(ln) for ln in invoked_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(recs) == 1
        assert Path(recs[0]["audio"]) == src_bass
        assert Path(recs[0]["out"]) == res.output_midi_path
        assert recs[0]["stem"] == "bass"

        # UI updated: Tab 3 -> MIDI sub-tab, explicit Basic Pitch badge, Piano Roll & Save MIDI enabled
        assert ctrl.window.tabs.currentWidget() is ctrl.window.mixer_widget
        assert ctrl.window.mixer_widget.analysis_tabs.currentIndex() == 2
        assert "bass" in ctrl.window.mixer_widget._rows
        assert "Spotify Basic Pitch CPU (basic-pitch)" in ctrl.window.mixer_widget.midi_info_lbl.text()
        assert ctrl.window.mixer_widget._last_midi_stem_name == "bass"
        assert ctrl.window.mixer_widget.save_midi_btn.isEnabled() is True

        # Export final .mid and verify parseable by mido
        final_mid = tmp_path / "exported" / "bass_exported.mid"
        ctrl._on_save_midi_as(str(final_mid))
        assert final_mid.exists()
        mf_read = mido.MidiFile(str(final_mid))
        note_ons = [msg for tr in mf_read.tracks for msg in tr if msg.type == "note_on" and msg.velocity > 0]
        assert len(note_ons) == 2

        # A second conversion through the loaded-stem action gets its own file.
        first_output_bytes = res.output_midi_path.read_bytes()
        ctrl._on_transcribe_stem_midi("bass", str(src_bass.relative_to(tmp_path)))
        _wait_until(app, lambda: not ctrl._ui_midi_result_q.empty())
        ctrl._on_ui_tick()
        second = ctrl._latest_midi_result
        assert second is not None and second.output_midi_path is not None
        assert second.output_midi_path.parent == res.output_midi_path.parent
        assert second.output_midi_path != res.output_midi_path
        assert second.output_midi_path.exists()
        assert res.output_midi_path.read_bytes() == first_output_bytes
        assert previous_midi.read_bytes() == previous_bytes

        # Reject explicit full-mix filenames gracefully without crashing or clearing ring buffer
        ctrl._on_open_single_stem_midi(str(src_mix))
        app.processEvents()
        assert "拒绝直接对完整混音" in ctrl.window.mixer_widget.midi_info_lbl.text()
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running
        assert ctrl.ring_buffer.total_written_frames >= pre_written

        # Missing WAV path shows error without crashing
        ctrl._on_open_single_stem_midi(str(tmp_path / "missing_stem.wav"))
        app.processEvents()
        assert "文件不存在" in ctrl.window.mixer_widget.midi_info_lbl.text()
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()


def test_smtc_tracker_guards_and_controller_auto_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _get_app()

    # Process matching against desktop & AUMID styles
    assert match_session_to_process("QQMusic.exe", "QQMusic.exe") is True
    assert match_session_to_process("Tencent.QQMusic.Desktop!App", "QQMusic.exe") is True
    assert match_session_to_process(r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe", "QQMusic.exe") is True
    assert match_session_to_process("msedge.exe", "QQMusic.exe") is False
    assert match_session_to_process("", "QQMusic.exe") is False

    # Pure unit test of TrackChangeTracker state transitions
    tracker = TrackChangeTracker(confirm_polls=2, target_process_name="QQMusic.exe")
    d0 = tracker.update(
        [
            MediaSessionSnapshot("msedge.exe", "Other Video", "Browser", playback_status="playing"),
            MediaSessionSnapshot("QQMusic.exe", "Song A", "Artist 1", playback_status="playing", position_sec=10.0),
        ]
    )
    assert d0.triggered_reset is False
    assert d0.reason == "initial_baseline"

    for snap, exp_reason in [
        (MediaSessionSnapshot("QQMusic.exe", "Song A", "Artist 1", playback_status="paused", position_sec=28.0), "same_track_paused"),
        (MediaSessionSnapshot("QQMusic.exe", "Song A", "Artist 1", playback_status="playing", position_sec=28.2), "same_track_resumed"),
        (MediaSessionSnapshot("QQMusic.exe", "Song A", "Artist 1", playback_status="playing", position_sec=6.0), "same_track_seek"),
        (MediaSessionSnapshot("QQMusic.exe", "Song A", "Artist 1", playback_status="playing", position_sec=95.0), "same_track_seek"),
        (MediaSessionSnapshot("QQMusic.exe", "", "", playback_status="changing"), "transient_empty_or_changing"),
        (MediaSessionSnapshot("msedge.exe", "Completely Different", "X", playback_status="playing"), "no_matching_session"),
    ]:
        dec = tracker.update([snap])
        assert dec.triggered_reset is False
        assert dec.reason == exp_reason

    # Song A -> Song B requires 2 consecutive polls
    d_pending = tracker.update([MediaSessionSnapshot("QQMusic.exe", "Song B", "Artist 2", playback_status="playing", position_sec=0.3)])
    assert d_pending.triggered_reset is False
    assert d_pending.reason == "pending_confirmation"
    d_switch = tracker.update([MediaSessionSnapshot("QQMusic.exe", "Song B", "Artist 2", playback_status="playing", position_sec=0.9)])
    assert d_switch.triggered_reset is True
    assert d_switch.reason == "track_changed"
    assert d_switch.previous_track is not None and d_switch.previous_track.title == "Song A"
    assert d_switch.active_track is not None and d_switch.active_track.title == "Song B"

    # Full controller integration with GUI Chroma progression + capture + persistence
    settings_path = tmp_path / "settings.json"
    ctrl = main_mod.ListenScopeController(
        use_mock_ai_for_demo=True,
        work_dir=tmp_path / "work_smtc",
        settings_path=settings_path,
    )
    try:
        ctrl._timer.stop()
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})
        ctrl._track_tracker.reset(target_process_name="QQMusic.exe")

        reset_calls: list[float] = []
        orig_reset = ctrl.analysis_worker.reset_harmony

        def spy_reset() -> None:
            reset_calls.append(time.monotonic())
            orig_reset()

        monkeypatch.setattr(ctrl.analysis_worker, "reset_harmony", spy_reset)

        for sym in ("C", "G", "Am", "F"):
            ctrl.window.chroma_widget.update_analysis(_make_chord_snapshot(sym))
        assert ctrl.window.chroma_widget.recent_progression == ["C", "G", "Am", "F"]

        # Baseline + Pause + Resume + Seek + Flicker + Unrelated App -> ZERO resets
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "晴天", "周杰伦", playback_status="playing", position_sec=12.0)]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "晴天", "周杰伦", playback_status="paused", position_sec=35.4)]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "晴天", "周杰伦", playback_status="playing", position_sec=35.8)]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "晴天", "周杰伦", playback_status="playing", position_sec=10.2)]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "", "", playback_status="changing")]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("chrome.exe", "Other", "Y", playback_status="playing")]
        )
        assert reset_calls == []
        assert ctrl.window.chroma_widget.recent_progression == ["C", "G", "Am", "F"]

        # Song switch A -> B (poll 1 pending, poll 2 queued -> drained by _on_ui_tick)
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "七里香", "周杰伦", playback_status="playing", position_sec=0.3)]
        )
        assert reset_calls == []
        assert ctrl.window.chroma_widget.recent_progression == ["C", "G", "Am", "F"]

        dec_final = ctrl._track_tracker.update(
            [MediaSessionSnapshot("QQMusic.exe", "七里香", "周杰伦", playback_status="playing", position_sec=0.9)]
        )
        ctrl._enqueue_track_decision(dec_final)
        ctrl._on_ui_tick()
        app.processEvents()

        assert len(reset_calls) == 1
        assert ctrl.window.chroma_widget.recent_progression == []
        assert ctrl._capture_backend is not None and ctrl._capture_backend.is_running
        assert "七里香" in ctrl.window.chroma_widget.track_status_lbl.text()

        # Disable auto-reset via UI checkbox -> saved and suppresses future automatic clears while keeping manual button
        ctrl.window.chroma_widget.auto_reset_chk.setChecked(False)
        app.processEvents()
        assert ctrl._auto_reset_on_track_change is False
        save_settings(ctrl._build_persisted_settings(), settings_path)
        assert load_settings(settings_path).auto_reset_on_track_change is False

        for sym in ("Dm", "G", "C"):
            ctrl.window.chroma_widget.update_analysis(_make_chord_snapshot(sym))

        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "夜曲", "周杰伦", playback_status="playing", position_sec=0.4)]
        )
        ctrl.process_media_session_snapshots(
            [MediaSessionSnapshot("QQMusic.exe", "夜曲", "周杰伦", playback_status="playing", position_sec=1.0)]
        )
        assert len(reset_calls) == 1
        assert ctrl.window.chroma_widget.recent_progression == ["Dm", "G", "C"]
        assert "自动重置已关闭" in ctrl.window.chroma_widget.track_status_lbl.text()

        # Manual reset button continues to work even when auto-reset is OFF
        ctrl.window.chroma_widget.reset_harmony_btn.click()
        app.processEvents()
        assert len(reset_calls) == 2
        assert ctrl.window.chroma_widget.recent_progression == []
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()

    # Legacy settings compatibility: omitted auto_reset_on_track_change defaults to True
    legacy = tmp_path / "legacy_v2_no_auto.json"
    legacy.write_text(json.dumps({"schema_version": 2, "ai_config": {}}), encoding="utf-8")
    assert load_settings(legacy).auto_reset_on_track_change is True

    # Explicit False roundtrip & invalid boolean coercion in settings
    explicit_false = tmp_path / "explicit_false.json"
    save_settings(
        PersistedSettings(
            resource_limits=ResourceLimits(),
            ai_config=AIConfig(),
            auto_reset_on_track_change=False,
        ),
        explicit_false,
    )
    assert load_settings(explicit_false).auto_reset_on_track_change is False

    bad_bool = tmp_path / "bad_bool.json"
    bad_bool.write_text(
        json.dumps({"schema_version": 2, "ai_config": {}, "auto_reset_on_track_change": "invalid"}),
        encoding="utf-8",
    )
    assert load_settings(bad_bool).auto_reset_on_track_change is True


def test_probe_media_session_cli_self_test_gbk_ascii_safe() -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "gbk"
    proc = subprocess.run(
        [sys.executable, "scripts/probe_media_session.py", "--self-test-mock", "--json"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="ascii",
        check=True,
        timeout=20.0,
    )
    payload = json.loads(proc.stdout)
    assert payload["target_process"] == "QQMusic.exe"
    assert payload["total_polls"] == 8
    assert payload["reset_count"] == 1
    assert payload["reset_events"][0]["poll_index"] == 7
    assert payload["final_active_track"] == "七里香 — 周杰伦"
    reasons = [ev["decision"]["reason"] for ev in payload["events"]]
    assert reasons == [
        "initial_baseline",
        "same_track_paused",
        "same_track_resumed",
        "same_track_seek",
        "transient_empty_or_changing",
        "no_matching_session",
        "pending_confirmation",
        "track_changed",
    ]
