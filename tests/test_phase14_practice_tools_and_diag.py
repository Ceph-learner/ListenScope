"""Phase 14 tests: Tap Tempo & CPU practice metronome sync, 120s A/B bookmarks, and sanitized diagnostic bundle export."""

from __future__ import annotations

import gc
import json
import os
import time
import wave
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtWidgets

from audio.bookmarks import ABBookmarkManager
from audio.metronome import PracticeMetronome, TapTempoTracker
from audio.playback import HistoryABPlayer, StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AudioConfig, ResourceLimits
from core.diagnostics import export_diagnostic_bundle
from core.logging import BoundedMemoryLogHandler, PerformanceLogger
from core.models import AnalysisSnapshot, ChordEstimate, KeyEstimate, PitchEstimate, SystemHardwareReport, TempoEstimate
from core.resource_manager import ResourceManager
from core.settings_store import PersistedSettings, save_settings
from main import ListenScopeController


def _write_silent_or_tone_wav(path: Path, seconds: float = 2.0, sr: int = 48000, amp: float = 0.0) -> Path:
    n = int(round(seconds * sr))
    if amp <= 0.0:
        stereo = np.zeros((n, 2), dtype=np.float32)
    else:
        t = np.arange(n, dtype=np.float32) / float(sr)
        sig = (amp * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
        stereo = np.column_stack([sig, sig])
    i16 = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(i16.tobytes())
    return path


def _make_dummy_hw_report() -> SystemHardwareReport:
    return SystemHardwareReport(
        timestamp_utc="2026-11-13 00:00:00 UTC",
        os_system="Windows",
        os_release="11",
        os_version="10.0.22631",
        architecture="AMD64",
        is_windows=True,
        windows_build=22631,
        wasapi_process_loopback_supported=True,
        python_version="3.11.9",
        git_version="git version 2.45.0",
        cpu_model="Test CPU",
        cpu_cores_logical=16,
        ram_total_mb=16384.0,
        ram_available_mb=12288.0,
        gpu_ai_ready=False,
        gpu_ai_block_reason="test",
    )


def test_tap_tempo_tracker_accuracy_gap_reset_and_bounds() -> None:
    tracker = TapTempoTracker(max_taps=8, reset_gap_sec=2.5)
    assert tracker.tap(float("nan")) is None
    assert tracker.tap(float("inf")) is None
    assert tracker.tap_count == 0

    assert tracker.tap(10.0) is None
    assert tracker.tap(10.5) == pytest.approx(120.0, abs=0.1)
    for k in range(2, 12):
        res = tracker.tap(10.0 + k * 0.5)
    assert res == pytest.approx(120.0, abs=0.1)
    assert tracker.tap_count == 8  # Strictly bounded deque(maxlen=8)

    # Gap > 2.5s resets previous phrase cleanly
    assert tracker.tap(20.0) is None
    assert tracker.tap_count == 1
    assert tracker.tap(20.75) == pytest.approx(80.0, abs=0.1)


def test_practice_metronome_beats_accent_speed_sync_and_guards() -> None:
    met = PracticeMetronome(sample_rate=48000, channels=2)
    assert met.set_bpm(120.0) == 120.0
    assert met.set_bpm(float("nan")) == 120.0
    assert met.set_volume(1.0) == 1.0
    assert met.set_volume(float("inf")) == 1.0
    met.set_beats_per_bar(3)
    met.reset_phase()

    # Render 2.0 seconds (4 beats at 120 BPM = 0s, 0.5s, 1.0s, 1.5s) in chunks
    chunks = [met.render_click_block(4800, rate_scale=1.0) for _ in range(20)]
    full = np.concatenate(chunks, axis=0)
    assert full.shape == (96000, 2)

    accent_p0 = float(np.max(np.abs(full[0:1000, 0])))
    beat_p1 = float(np.max(np.abs(full[24000:25000, 0])))
    beat_p2 = float(np.max(np.abs(full[48000:49000, 0])))
    accent_p3 = float(np.max(np.abs(full[72000:73000, 0])))
    quiet_mid = float(np.max(np.abs(full[10000:18000, 0])))

    assert accent_p0 > 0.60
    assert 0.35 < beat_p1 < 0.52
    assert 0.35 < beat_p2 < 0.52
    assert accent_p3 > 0.60  # Beat 4 is bar 2 beat 1 in 3/4!
    assert accent_p0 > beat_p1 * 1.25
    assert accent_p3 > beat_p2 * 1.25
    assert quiet_mid < 1e-4

    # At 0.5x playback speed, beat spacing stretches from 24000 to 48000 samples
    met.reset_phase()
    half = met.render_click_block(60000, rate_scale=0.5)
    assert float(np.max(np.abs(half[23500:26000, 0]))) < 1e-4
    assert float(np.max(np.abs(half[48000:49000, 0]))) > 0.40

    # overlay_into stays silent when disabled and handles NaN rate_scale cleanly
    buf = np.zeros((2048, 2), dtype=np.float32)
    met.set_overlay_enabled(False)
    met.overlay_into(buf, rate_scale=float("nan"))
    assert float(np.max(np.abs(buf))) == 0.0
    met.set_overlay_enabled(True)
    met.overlay_into(buf, rate_scale=float("nan"))
    assert float(np.max(np.abs(buf))) > 0.40


def test_metronome_overlay_with_ab_player_and_stem_mixer(tmp_path: Path) -> None:
    cfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(audio_config=cfg)
    rb.write(np.zeros((48000 * 2, 2), dtype=np.float32))

    met = PracticeMetronome(sample_rate=48000, channels=2)
    met.set_bpm(120.0)
    met.set_volume(1.0)
    met.set_overlay_enabled(True)

    # 1. HistoryABPlayer at 0.5x & one-shot EOF silence tail protection
    player = HistoryABPlayer(rb, audio_config=cfg, metronome=met)
    player.set_ab_range(0, 4800)  # 0.1s excerpt -> beat at sample 0 only
    player.set_loop(False)
    player.start_playback(open_audio_device=False)
    block = player.render_block(30000)  # larger than excerpt + 0.5s beat
    assert float(np.max(np.abs(block[:1000]))) > 0.50
    # Trailing silence beyond frame 4800 must NOT receive spurious clicks at frame 24000
    assert float(np.max(np.abs(block[24000:26000]))) < 1e-4

    # 2. StemMixerEngine: advance=False must stay silent, advance=True overlays click at stretched speed
    wav_path = _write_silent_or_tone_wav(tmp_path / "silent_stem.wav", seconds=2.0, amp=0.0)
    mixer = StemMixerEngine(sample_rate=48000, channels=2, metronome=met)
    try:
        mixer.load_stems({"vocals": wav_path})
        preview = mixer.render_block(2048, advance=False)
        assert float(np.max(np.abs(preview))) == 0.0

        mixer.set_speed(0.5)
        mixer.set_loop(True)
        mixer.play(open_audio_device=False)
        m1 = mixer.render_block(48500, advance=True)
        assert float(np.max(np.abs(m1[:1000]))) > 0.50
        assert float(np.max(np.abs(m1[23500:26000]))) < 1e-4
        assert float(np.max(np.abs(m1[48000:48500]))) > 0.35
    finally:
        mixer.clear()


def test_ab_bookmark_manager_bounds_and_rollover_pruning() -> None:
    mgr = ABBookmarkManager(max_bookmarks=12)
    with pytest.raises(ValueError):
        mgr.add_bookmark(5000, 5000)

    for i in range(15):
        start = i * 48000
        mgr.add_bookmark(start, start + 48000, label=f"段 {i + 1}", oldest_abs_frame=0)

    items = mgr.list_bookmarks(oldest_abs_frame=0, newest_abs_frame=15 * 48000, sample_rate=48000)
    assert len(items) == 12
    # FIFO retained newest 12 (segments 4..15)
    assert items[0]["label"] == "段 4"
    assert items[-1]["label"] == "段 15"

    # Roll buffer past segment 8 (frame 8 * 48000 = 384000)
    pruned = mgr.prune_expired(oldest_abs_frame=8 * 48000)
    assert pruned >= 4
    rem = mgr.list_bookmarks(oldest_abs_frame=8 * 48000, newest_abs_frame=15 * 48000, sample_rate=48000)
    assert all(it["end_abs_frame"] > 8 * 48000 for it in rem)
    assert mgr.remove_bookmark(rem[0]["bookmark_id"]) is True
    assert len(mgr.list_bookmarks(oldest_abs_frame=8 * 48000, newest_abs_frame=15 * 48000, sample_rate=48000)) == len(rem) - 1


def test_diagnostic_bundle_export_sanitized_and_bounded(tmp_path: Path) -> None:
    home_str = str(Path.home())
    settings_path = tmp_path / "settings.json"
    save_settings(
        PersistedSettings(
            resource_limits=ResourceLimits(),
            ai_config=AIConfig(),
            ai_python_executable=str(Path.home() / "secret_user_env" / "python.exe"),
        ),
        settings_path,
    )

    perf = PerformanceLogger(log_dir=tmp_path / "perf")
    log_handler = BoundedMemoryLogHandler(maxlen=500)
    import logging

    test_logger = logging.getLogger("ListenScope.TestDiag")
    test_logger.addHandler(log_handler)
    try:
        test_logger.warning("Sample log containing home path %s/foo/bar", home_str)
        perf.log_dir.mkdir(parents=True, exist_ok=True)
        # Create an oversized (>300KB) perf jsonl file to verify bounded tail truncation
        big_jsonl = perf.log_dir / "ai_perf_20261113.jsonl"
        big_line = json.dumps({"path": f"{home_str}/model.onnx", "note": "x" * 500}) + "\n"
        big_jsonl.write_text(big_line * 700, encoding="utf-8")

        rm = ResourceManager()
        try:
            snap = rm.sample()
        finally:
            rm.close()

        out_no_ext = tmp_path / "diag_out" / "support_bundle"
        saved = export_diagnostic_bundle(
            out_no_ext,
            hardware_report=_make_dummy_hw_report(),
            resource_limits=ResourceLimits(),
            ai_config=AIConfig(),
            ai_python_executable=str(Path.home() / "ListenScope" / ".venv-ai" / "Scripts" / "python.exe"),
            resource_snapshot=snap,
            perf_logger=perf,
            log_handler=log_handler,
            settings_path=settings_path,
            max_jsonl_bytes=65536,
        )
        assert saved.suffix == ".zip" and saved.exists()

        with zipfile.ZipFile(saved, "r") as zf:
            names = set(zf.namelist())
            assert {
                "SYSTEM_REPORT.md",
                "diagnostic_summary.json",
                "recent_logs.txt",
                "performance_recent.json",
                "settings_sanitized.json",
                "perf_jsonl/ai_perf_20261113.jsonl",
            }.issubset(names)

            summary = json.loads(zf.read("diagnostic_summary.json").decode("utf-8"))
            assert summary["target_hardware"]["gpu_name"] == "NVIDIA GeForce RTX 5060 Ti"
            assert summary["target_hardware"]["vram_gb"] == 8
            assert summary["target_hardware"]["ram_gb"] == 16
            assert "live_separation" not in summary
            if len(home_str) >= 3:
                json_home = json.dumps(home_str)[1:-1]
                diag_summary_txt = zf.read("diagnostic_summary.json").decode("utf-8")
                settings_san_txt = zf.read("settings_sanitized.json").decode("utf-8")
                assert home_str not in diag_summary_txt
                assert json_home not in diag_summary_txt
                assert home_str not in zf.read("recent_logs.txt").decode("utf-8")
                assert home_str not in settings_san_txt
                assert json_home not in settings_san_txt

            tail_raw = zf.read("perf_jsonl/ai_perf_20261113.jsonl")
            assert len(tail_raw) <= 65536 + 128
            assert tail_raw.startswith(b"# [truncated older entries; kept newest tail]")
    finally:
        test_logger.removeHandler(log_handler)


def test_controller_phase14_integration_bookmarks_metronome_and_diag(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        work_dir=tmp_path / "ws",
        settings_path=tmp_path / "settings.json",
    )
    try:
        # 1. Feed 4s signal -> set A/B -> save bookmark -> change range -> jump back
        ctrl.ring_buffer.write(np.zeros((48000 * 4, 2), dtype=np.float32))
        ctrl._on_ab_set_range(3.0, 1.0)
        saved_range = ctrl.ab_player.loop_range
        ctrl._on_ab_bookmark_save("副歌练习")
        assert ctrl.window.bookmark_combo.count() == 1
        assert ctrl.window.bookmark_jump_btn.isEnabled() is True
        assert ctrl.window.bookmark_del_btn.isEnabled() is True
        bid = int(ctrl.window.bookmark_combo.currentData())

        ctrl._on_ab_set_range(1.5, 0.5)
        assert ctrl.ab_player.loop_range != saved_range
        ctrl._on_ui_tick()
        assert int(ctrl.window.bookmark_combo.currentData()) == bid
        ctrl._on_ab_bookmark_select(bid)
        assert ctrl.ab_player.loop_range == saved_range

        ctrl.window.chroma_widget.tap_tempo_btn.click()
        assert "Tap x1" in ctrl.window.chroma_widget.tap_status_lbl.text()

        ctrl._on_ab_bookmark_delete(bid)
        assert ctrl.window.bookmark_combo.count() == 0
        assert ctrl.window.bookmark_jump_btn.isEnabled() is False

        # Save one more bookmark, then test _on_import_audio_file resets old bookmarks cleanly
        ctrl._on_ab_bookmark_save("待清空片段")
        assert ctrl.window.bookmark_combo.count() == 1
        wav_path = _write_silent_or_tone_wav(tmp_path / "song.wav", seconds=1.5, amp=0.25)
        ctrl._on_import_audio_file(str(wav_path))
        assert ctrl.window.bookmark_combo.count() == 0

        # 2. Metronome UI two-way overlay sync + Tap/Adopt BPM + mutual exclusion vs A/B play
        ctrl.window.chroma_widget.metronome_overlay_chk.setChecked(True)
        assert ctrl.metronome.overlay_enabled is True
        assert ctrl.window.mixer_widget.metronome_chk.isChecked() is True
        ctrl.window.mixer_widget.metronome_chk.setChecked(False)
        assert ctrl.metronome.overlay_enabled is False
        assert ctrl.window.chroma_widget.metronome_overlay_chk.isChecked() is False

        snap = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[0.0, 0.0],
            waveform_max=[0.1, 0.1],
            fft_freqs_hz=[100.0, 440.0],
            fft_db=[-40.0, -10.0],
            log_freqs_hz=[100.0, 440.0],
            log_spectrum_db=[-40.0, -10.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("C major", "A minor", "Stable", 0.9, 0.1, False),
            key=KeyEstimate("C major", "A minor", "Stable", 0.85, 0.15, "相对大小调"),
            tempo=TempoEstimate(96.0, "Stable", 0.8),
            pitch=PitchEstimate(440.0, "A4", 0.0, 0.9),
            rms_dbfs=-18.0,
            peak_dbfs=-6.0,
            window_seconds=2.0,
        )
        ctrl.window.chroma_widget.update_analysis(snap)
        assert ctrl.window.chroma_widget.adopt_bpm_btn.isEnabled() is True
        ctrl.window.chroma_widget.adopt_bpm_btn.click()
        assert ctrl.metronome.bpm == pytest.approx(96.0, abs=0.1)

        # Standalone metronome auto-stops when A/B playback starts
        ctrl.window.chroma_widget.metronome_standalone_btn.click()
        assert ctrl.metronome.standalone_playing is True
        ctrl._on_ab_play()
        assert ctrl.metronome.standalone_playing is False
        assert ctrl.window.chroma_widget.metronome_standalone_btn.isChecked() is False
        ctrl.ab_player.stop()

        # 3. Diagnostic ZIP bundle export from controller
        live = ctrl.live_separator
        live._dropped_chunks = 2
        live._output_overwritten_frames = 32
        live._output_primed = True
        live._pull_playback_block(4, device_underflow=True)
        live._status_message = "private test track and path"
        ctrl.window.update_live_metrics(live.latest_metrics())
        assert "输出重缓冲 1" in ctrl.window.live_widget.lbl_playback_health.text()
        assert "输出溢出丢弃 32 帧" in ctrl.window.live_widget.lbl_playback_health.text()
        diag_zip = tmp_path / "diag" / "test_bundle.zip"
        ctrl._on_export_diagnostic_bundle(str(diag_zip))
        deadline = time.monotonic() + 5.0
        while not diag_zip.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
            app.processEvents()
        assert diag_zip.exists()
        with zipfile.ZipFile(diag_zip) as bundle:
            summary = bundle.read("diagnostic_summary.json").decode("utf-8")
            telemetry = json.loads(summary)["live_separation"]
            assert telemetry["input_drop_events"] == 2
            assert telemetry["output_overwritten_frames"] == 32
            assert telemetry["playback_rebuffers"] == 1
            assert telemetry["device_underflows"] == 1
            assert "private test track and path" not in summary
        ctrl._on_ui_tick()
        assert "离线排障诊断包" in ctrl.window.notice_banner.text()
    finally:
        ctrl.shutdown()
        del ctrl
        app.processEvents()
        gc.collect()
