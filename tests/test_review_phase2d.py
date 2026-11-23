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
