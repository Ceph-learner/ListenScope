"""Phase 2D Windows real-machine regression verification tests (Issue #40: W1-W8 + W9).

Every test is a minimal reproduction marked `@pytest.mark.xfail(strict=True, reason="<ID>")`.
Implementers remove each xfail marker as the item is fixed.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_w1_system_loopback_follows_default_device_change_without_stream_error() -> None:
    """W1 (NEEDS_TARGET contract): WasapiSystemLoopbackBackend must switch when default loopback ID changes even if old stream doesn't error."""
    from audio.system_loopback import WasapiSystemLoopbackBackend
    from core.config import AudioConfig

    src = (REPO_ROOT / "audio" / "system_loopback.py").read_text("utf-8")
    settings_src = (REPO_ROOT / "core" / "settings_store.py").read_text("utf-8")
    assert "follow_default_device" in settings_src or "follow_default" in src, (
        "Missing follow_default_device setting/polling in system_loopback.py / settings_store.py"
    )
    assert "OnDefaultDeviceChanged" in src or "get_default_wasapi_loopback" in src, (
        "WasapiSystemLoopbackBackend does not monitor default device changes while stream is healthy"
    )
    # Must also have a default-change check inside _capture_loop (not only inside except Exception)
    m = re.search(r"def _capture_loop\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    body = m.group(0)
    assert "follow_default" in body or "_default_device_changed" in body, (
        "_capture_loop only reconnects on stream exception, not when default device switches silently"
    )


def test_w2_force_quit_from_hidden_tray_quits_app_hides_tray_and_has_exit_watchdog(tmp_path: Path) -> None:
    """W2: force_quit() from hidden tray must hide tray, invoke app.quit(), and main.py must have exit watchdog."""
    from main import ListenScopeController

    app = _get_app()
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    quit_called = {"n": 0}
    orig_quit = app.quit
    try:
        ctrl.window.hide()
        app.processEvents()
        with mock.patch.object(app, "quit", side_effect=lambda: quit_called.__setitem__("n", quit_called["n"] + 1)):
            ctrl.window.force_quit()
            app.processEvents()
        assert quit_called["n"] >= 1, "force_quit() on hidden tray window never called app.quit()"
        tray = getattr(ctrl.window, "_tray_icon", None)
        if tray is not None:
            assert not tray.isVisible(), "Tray icon was not hidden on force_quit()"
    finally:
        ctrl.shutdown()

    main_src = (REPO_ROOT / "main.py").read_text("utf-8")
    assert "os._exit(0)" in main_src, "main() missing 5s exit watchdog calling os._exit(0) on stubborn threads/subprocesses"


def test_w2_guard_all_source_threads_are_daemon() -> None:
    """W2 guard: every threading.Thread(...) in production source must set daemon=True."""
    import ast

    def _check_file(py_path: Path, label: str) -> list[str]:
        tree = ast.parse(py_path.read_text("utf-8"), filename=str(py_path))
        bad: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_thread = (
                    isinstance(func, ast.Attribute)
                    and func.attr == "Thread"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "threading"
                )
                if is_thread:
                    has_daemon_true = any(
                        kw.arg == "daemon"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                        for kw in node.keywords
                    )
                    if not has_daemon_true:
                        bad.append(f"{label}:{node.lineno}")
        return bad

    offenders: list[str] = []
    for folder in ("ai", "analysis", "audio", "core", "separation", "streaming", "ui"):
        for py in (REPO_ROOT / folder).rglob("*.py"):
            offenders.extend(_check_file(py, str(py.relative_to(REPO_ROOT))))
    main_py = REPO_ROOT / "main.py"
    offenders.extend(_check_file(main_py, "main.py"))
    assert offenders == [], f"Non-daemon threads found: {offenders}"
    # Also ensure shutdown cancels bootstrap_manager
    main_text = main_py.read_text("utf-8")
    assert "get_bootstrap_manager().cancel()" in main_text, "shutdown() does not cancel running bootstrap_manager subprocess"


def test_w3_bass_midi_postprocess_removes_simultaneous_octave_ghost_notes() -> None:
    """W3: Bass MIDI transcription must strip simultaneous +12/+24 semitone octave ghost notes (<=40ms) and constrain Basic Pitch freq range."""
    from analysis import midi_transcription as mt

    assert hasattr(mt, "suppress_bass_octave_ghosts") or hasattr(mt, "_suppress_bass_octave_ghosts"), (
        "analysis/midi_transcription.py missing bass monophonic octave-ghost suppression helper"
    )
    src = (REPO_ROOT / "analysis" / "midi_transcription.py").read_text("utf-8")
    assert "minimum_frequency" in src and "maximum_frequency" in src, (
        "Basic Pitch predict() call does not pass bass frequency range (minimum_frequency / maximum_frequency)"
    )


def test_w4_system_animations_disabled_zeroes_tab_underline_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """W4: When system_animations_enabled() is False, AcidTabBar underline animation must jump immediately (duration==0)."""
    from ui import acid_style, help_badge

    _get_app()
    monkeypatch.setattr(help_badge, "system_animations_enabled", lambda: False)
    if hasattr(acid_style, "system_animations_enabled"):
        monkeypatch.setattr(acid_style, "system_animations_enabled", lambda: False)

    bar = acid_style.AcidTabBar()
    bar.addTab("TAB 1")
    bar.addTab("TAB 2")
    bar.resize(300, 36)
    bar.show()
    _get_app().processEvents()
    bar.setCurrentIndex(0)
    bar.setCurrentIndex(1)
    assert bar._anim.duration() == 0 or bar._anim.state() == QtCore.QAbstractAnimation.State.Stopped, (
        f"AcidTabBar underline animation still running with duration={bar._anim.duration()}ms when system animations disabled"
    )
    bar.close()


def test_w5_spectrogram_axis_ticks_adapt_to_available_height() -> None:
    """W5: Spectrogram/FFT Y-axis ticks must thin out dynamically when height is small so adjacent ticks >= 1.6x font height."""
    src = (REPO_ROOT / "ui" / "spectrum_widget.py").read_text("utf-8")
    assert "1.6" in src or "_update_dynamic_ticks" in src or "_refresh_axis_ticks" in src, (
        "ui/spectrum_widget.py uses static spectrogram frequency ticks that overlap at 150% DPI"
    )


def test_w6_startup_broad_scan_test_isolates_home_and_root() -> None:
    """W6 #6: test_startup_help_bootstrap_fixes must isolate ROOT and Path.home() so real .venv-ai on Windows does not leak."""
    src = (REPO_ROOT / "tests" / "test_startup_help_bootstrap_fixes.py").read_text("utf-8")
    m = re.search(r"def test_nonblocking_startup_pytorch_scan_and_ui_tick_drain.*?\n(?=def )", src, re.DOTALL)
    assert m is not None
    body = m.group(0)
    assert "monkeypatch.setattr(main_mod, \"ROOT\"" in body or "monkeypatch.setattr(Path, \"home\"" in body, (
        "Broad-scan test does not isolate main_mod.ROOT / Path.home(), leaking real .venv-ai on Windows"
    )


def test_w7_readme_documents_win11_snap_layouts_known_limitation() -> None:
    """W7: README must explicitly note Win11 Snap Layouts is deferred to Phase 3 (P3-WIN)."""
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    assert "Snap" in readme, "README.md missing known limitation note for Win11 Snap Layouts (DEFER -> #33 P3-WIN)"


def test_w8_windows_retest_checklist_includes_w1_w2_w3_w5_and_safe_audio_spec() -> None:
    """W8: WINDOWS_RETEST.md must include W1, W2, W3, W5 and specify -20 dBFS / 50 ms fade / <=5s non-fatiguing audio."""
    txt = (REPO_ROOT / "docs" / "review" / "WINDOWS_RETEST.md").read_text("utf-8")
    for token in ("W1", "W2", "W3", "W5", "-20 dBFS"):
        assert token in txt, f"docs/review/WINDOWS_RETEST.md missing {token!r}"


def test_w9_dev_build_displays_real_version_with_git_short_sha() -> None:
    """W9: Untagged dev builds must display '<version>-dev+<shortSHA>' in footer/about (reading git or env) without altering pyproject.toml."""
    import tomllib

    pyproj = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    base_ver = pyproj["project"]["version"]
    assert base_ver == "1.0.1"  # pyproject.toml version must NOT be changed

    from core import paths as paths_mod

    ver_fn = getattr(paths_mod, "get_app_version_display", None)
    if ver_fn is None:
        try:
            from core import version as ver_mod

            ver_fn = getattr(ver_mod, "get_app_version_display", None)
        except ImportError:
            ver_fn = None
    assert callable(ver_fn), "Missing get_app_version_display() helper in core/version.py or core/paths.py"
    disp = ver_fn()
    assert re.search(r"-dev\+[0-9a-f]{7,}", disp), f"Dev version string missing '-dev+<shortSHA>': {disp!r}"
    acid_src = (REPO_ROOT / "ui" / "acid_style.py").read_text("utf-8")
    assert "LISTENSCOPE_V1.0.1" not in acid_src, "ui/acid_style.py still hardcodes LISTENSCOPE_V1.0.1 in footer"


def test_w2_process_loopback_stop_then_start_receives_audio_frames() -> None:
    """W2 P1 regression: WasapiProcessLoopbackBackend must clear _closing on start() so stop->start still receives PCM."""
    from audio.process_loopback import WasapiProcessLoopbackBackend
    from core.config import AudioConfig

    callbacks: dict[str, object] = {}

    class _FakeTap:
        def start(self) -> None:
            pass

        def close(self) -> None:
            pass

    def _tap_factory(*, pid: int, on_data, resample_quality: str):
        callbacks["on_data"] = on_data
        return _FakeTap()

    backend = WasapiProcessLoopbackBackend(
        pid=1234,
        process_name="QQMusic.exe",
        audio_config=AudioConfig(sample_rate=48000, channels=2),
        tap_factory=_tap_factory,
        pid_exists_fn=lambda _pid: True,
        allow_non_windows=True,
    )
    backend._cached_fmt = {"sample_rate": 48000, "channels": 2, "dtype": "float32"}

    pcm = np.full((960, 2), 0.25, dtype=np.float32).tobytes()
    backend.start()
    try:
        callbacks["on_data"](pcm, 960)  # type: ignore[operator]
        chunk1 = backend.read_chunk(timeout=0.5)
        assert chunk1 is not None and chunk1.shape == (960, 2)
    finally:
        backend.stop()

    # Restart after stop(): _closing must be cleared so new frames are not dropped
    backend.start()
    try:
        callbacks["on_data"](pcm, 960)  # type: ignore[operator]
        chunk2 = backend.read_chunk(timeout=0.5)
        assert chunk2 is not None and chunk2.shape == (960, 2), (
            "WasapiProcessLoopbackBackend dropped audio frames after stop() -> start() restart"
        )
    finally:
        backend.stop()


# ---------------------------------------------------------------------------
# Phase 2D Addendum (Issue #40 updated: W10-W15 & W2 close-button behavior)
# ---------------------------------------------------------------------------


def test_w10_handle_ai_result_handles_every_ai_job_state_and_notifies_mixer() -> None:
    """W10: handle_ai_result must accept every AIJobState without AttributeError and forward to mixer_widget."""
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.models import AIJobResult, AIJobState
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    seen: list[AIJobState] = []
    orig_handler = win.mixer_widget.handle_ai_result

    def _spy(res: AIJobResult) -> None:
        seen.append(res.state)
        orig_handler(res)

    win.mixer_widget.handle_ai_result = _spy  # type: ignore[method-assign]
    try:
        for st in AIJobState:
            res = AIJobResult(
                task_id=f"job_{st.name.lower()}",
                state=st,
                error="simulated error" if st in (AIJobState.FAILED, AIJobState.OOM_ERROR) else None,
            )
            win.handle_ai_result(res)
        app.processEvents()
        assert len(seen) == len(list(AIJobState)), f"mixer_widget missed states: {set(AIJobState) - set(seen)}"
    finally:
        win.close()
        mixer.close()


def test_w10_ast_guard_all_enum_references_exist() -> None:
    """W10 AST guard: every AIJobState.<X> and OOMRecoveryAction.<X> reference in production code must exist."""
    import ast
    from core.models import AIJobState, OOMRecoveryAction

    enum_map = {
        "AIJobState": AIJobState,
        "OOMRecoveryAction": OOMRecoveryAction,
    }
    bad: list[str] = []
    files: list[Path] = [REPO_ROOT / "main.py"]
    for folder in ("ai", "analysis", "audio", "core", "separation", "streaming", "ui"):
        files.extend((REPO_ROOT / folder).rglob("*.py"))

    for py in files:
        tree = ast.parse(py.read_text("utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in enum_map
            ):
                enum_cls = enum_map[node.value.id]
                if not hasattr(enum_cls, node.attr):
                    bad.append(f"{py.relative_to(REPO_ROOT)}:{node.lineno} {node.value.id}.{node.attr}")
    assert bad == [], f"Invalid Enum member references found: {bad}"


def test_w10_ui_tick_isolates_queue_handler_exceptions(tmp_path: Path) -> None:
    """W10: each queue handler in _on_ui_tick must be isolated with try/except + logger.exception."""
    from core.models import AIJobResult, AIJobState
    from main import ListenScopeController

    _get_app()
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws_w10")
    try:
        # Force handle_ai_result to raise; banner queue must still be drained in the same tick
        def _boom(_res: AIJobResult) -> None:
            raise RuntimeError("boom in ai result handler")

        banners: list[str] = []
        ctrl.window.handle_ai_result = _boom  # type: ignore[method-assign]
        ctrl.window.show_banner_message = lambda msg, **_kw: banners.append(str(msg))  # type: ignore[method-assign]
        ctrl._ui_ai_result_q.put(AIJobResult(task_id="t1", state=AIJobState.FAILED, error="err"))
        ctrl._ui_banner_q.put("still-alive-banner")
        ctrl._on_ui_tick()
        assert "still-alive-banner" in banners, "_on_ui_tick aborted subsequent queue handlers on exception"
    finally:
        ctrl.shutdown()


def test_w11_realistic_mix_bpm_acc1_at_least_80pct_and_pads_return_none() -> None:
    """W11: realistic_mix BPM Acc1 must be >= 80%, while steady sine & pure chord pad must still return None."""
    from tests.bench.realistic_mix import run_realistic_mix_benchmark

    report = run_realistic_mix_benchmark()
    summary = report["summary"]
    assert summary["neg_controls_none_pct"] == 100.0, f"Non-rhythmic negative controls leaked BPM: {report['negative_controls']}"
    assert summary["acc1_pct"] >= 80.0, (
        f"realistic_mix BPM Acc1 {summary['acc1_pct']}% < 80% "
        f"(peakiness p50={summary['peakiness_p50']}, p95={summary['peakiness_p95']})"
    )


def test_w12_polyphonic_mix_falls_back_to_lowpass_bass_pitch_or_poly_notice() -> None:
    """W12: Polyphonic mix with E2 bass must show bass E2 (+-10c); pure chord pad shows poly notice; 440Hz sine shows A4."""
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig
    from ui.spectrum_widget import SpectrumAnalysisWidget

    sr = 48000
    step = int(round(sr * 66.67 / 1000.0))

    def _run_pcm(mono: np.ndarray):
        acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=5)
        rb = FixedRingBuffer(acfg)
        w = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
        stereo = np.stack([mono, mono], axis=1).astype(np.float32)
        snap = None
        for pos in range(0, stereo.shape[0], step):
            chunk = stereo[pos : pos + step]
            if chunk.shape[0] == 0:
                break
            rb.write(chunk)
            snap = w.analyze_latest_once()
        return snap

    n = int(round(0.8 * sr))
    t = np.arange(n, dtype=np.float64) / float(sr)

    # 1. E2 bass (82.41 Hz) + C major chord pad (C4/E4/G4/B4)
    e2_hz = 82.406889
    bass = 0.28 * (0.7 * np.sin(2.0 * np.pi * e2_hz * t) + 0.3 * np.sin(2.0 * np.pi * 2.0 * e2_hz * t))
    pad = sum(0.14 * np.sin(2.0 * np.pi * f * t) for f in (261.63, 329.63, 392.00, 493.88, 523.25))
    snap_bass = _run_pcm((bass + pad).astype(np.float32))
    assert snap_bass is not None and snap_bass.pitch.note_name == "E2" and snap_bass.pitch.frequency_hz is not None, (
        f"Expected polyphonic bass fallback E2, got {snap_bass.pitch if snap_bass else None}"
    )
    cents_err = abs(1200.0 * np.log2(snap_bass.pitch.frequency_hz / e2_hz))
    assert cents_err <= 10.0, f"Polyphonic bass E2 error {cents_err:.1f}c > 10c"

    # 2. Pure chord pad without bass -> polyphonic notice, NOT '等待有效音高'
    snap_pad = _run_pcm(pad.astype(np.float32))
    assert snap_pad is not None and snap_pad.pitch.note_name is None
    _get_app()
    sw = SpectrumAnalysisWidget()
    try:
        sw.update_snapshot(snap_pad)
        detail_txt = sw.pitch_detail.text()
        assert "等待有效音高" not in detail_txt and ("多声部" in detail_txt or "Poly" in detail_txt), (
            f"Pure chord pad still showed waiting text instead of polyphonic notice: {detail_txt!r}"
        )
    finally:
        sw.close()

    # 3. Single 440 Hz sine -> A4
    snap_a4 = _run_pcm((0.35 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32))
    assert snap_a4 is not None and snap_a4.pitch.note_name == "A4"


def test_w13_viewbox_data_height_waveform_autogain_and_chroma_seconds_axis() -> None:
    """W13: ViewBox data area height >= 80px at 1420x900 & 1366x768; waveform auto-gain for -38 dBFS; chroma X-axis in seconds."""
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        sw = win.spectrum_widget
        for w, h in ((1420, 900), (1366, 768)):
            win.resize(w, h)
            win.show()
            app.processEvents()
            for name, plot in (
                ("wave_plot", sw.wave_plot),
                ("spec_plot", sw.spec_plot),
                ("fft_plot", sw.fft_plot),
                ("log_plot", sw.log_plot),
            ):
                vb_h = float(plot.getViewBox().sceneBoundingRect().height())
                assert vb_h >= 80.0, f"{name} ViewBox data height {vb_h:.1f}px < 80px at {w}x{h}"

        # Waveform auto-gain support & Chroma X-axis in seconds
        sw_src = (REPO_ROOT / "ui" / "spectrum_widget.py").read_text("utf-8")
        assert "auto_gain" in sw_src or "wave_auto_gain" in sw_src, "SpectrumAnalysisWidget missing waveform auto-gain"
        chroma_src = (REPO_ROOT / "ui" / "chroma_widget.py").read_text("utf-8")
        assert "秒" in chroma_src or "s)" in chroma_src, "Chroma heatmap X-axis not converted from frame index to seconds"
    finally:
        win.close()
        mixer.close()


def test_w2_close_button_prompts_and_respects_remembered_choice_and_inno_setup(tmp_path: Path) -> None:
    """W2 (updated): close button behavior persisted in schema 2, tray bubble i18n, and Inno Setup CloseApplications/AppMutex."""
    from core.config import AIConfig, ResourceLimits
    from core.settings_store import PersistedSettings, load_settings, save_settings

    # 1. Settings schema 2 optional close_behavior field
    assert hasattr(PersistedSettings, "close_behavior") or hasattr(PersistedSettings, "close_action"), (
        "PersistedSettings missing optional close_behavior/close_action field (schema 2)"
    )
    field_name = "close_behavior" if hasattr(PersistedSettings, "close_behavior") else "close_action"
    s = PersistedSettings(resource_limits=ResourceLimits(), ai_config=AIConfig(), **{field_name: "quit"})
    p = tmp_path / "settings.json"
    save_settings(s, path=p)
    loaded = load_settings(path=p)
    assert loaded.schema_version == 2
    assert getattr(loaded, field_name) == "quit"

    # 2. Inno Setup installer script includes CloseApplications=yes and AppMutex
    iss = (REPO_ROOT / "scripts" / "installer.iss").read_text("utf-8")
    assert "CloseApplications=yes" in iss, "scripts/installer.iss missing CloseApplications=yes"
    assert "AppMutex=" in iss, "scripts/installer.iss missing AppMutex="


def test_w14_idle_low_ram_shows_amber_not_red_critical_and_records_report() -> None:
    """W14: AI idle with ~2.6 GB free RAM shows amber '内存偏低' (not red Critical); docs/WINDOWS_TEST_REPORT.md records measurements."""
    report_path = REPO_ROOT / "docs" / "WINDOWS_TEST_REPORT.md"
    assert report_path.exists(), "docs/WINDOWS_TEST_REPORT.md not created with W14 real-machine measurements"
    report_txt = report_path.read_text("utf-8")
    for token in ("1830", "3893", "0.435"):
        assert token in report_txt, f"docs/WINDOWS_TEST_REPORT.md missing measurement {token!r}"

    mw_src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    assert "内存偏低" in mw_src, "ui/main_window.py missing amber '内存偏低' state when AI is idle"
    assert "pause_ram_before_ai_mb" in mw_src or "pause_ram_before_ai_mb" in (REPO_ROOT / "main.py").read_text("utf-8"), (
        "AI rejection notice missing pause_ram_before_ai_mb setting guidance"
    )


def test_w15_ui_polish_source_combo_stretch_and_smtc_concise_and_footer_spacing() -> None:
    """W15: source_combo stretches in top bar, SMTC status label is concise with tooltip, and mixer badge has tooltip."""
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        smtc_txt = win.chroma_widget.track_status_lbl.text()
        assert len(smtc_txt) <= 32, f"SMTC status label still too long/technical ({len(smtc_txt)} chars): {smtc_txt!r}"
        assert win.chroma_widget.track_status_lbl.toolTip().strip(), "SMTC status label missing detailed toolTip"
        assert win.mixer_widget.deep_rhythm_badge_lbl.toolTip().strip(), "Mixer deep_rhythm_badge_lbl missing toolTip"
        sp = win.source_combo.sizePolicy().horizontalPolicy()
        assert sp in (QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding), (
            f"source_combo horizontal sizePolicy is {sp}, not Expanding"
        )
    finally:
        win.close()
        mixer.close()

