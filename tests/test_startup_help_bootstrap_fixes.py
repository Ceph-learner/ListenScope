"""Regression tests for v0.2.3 fixes: strict HelpBadge-only tooltips, flicker-free startup/Settings, async PyTorch discovery, frozen subprocess fix, and clean PS1 bootstrap."""

from __future__ import annotations

from pathlib import Path
import queue
import re
import subprocess
import sys

from PySide6 import QtCore, QtGui, QtWidgets
import pytest

from core.appearance import Appearance
from core.config import AIConfig, ResourceLimits
from core.paths import run_external_python
from core.system_probe import (
    PYTHON_WINDOWS_DOWNLOAD_URL,
    _candidate_local_python_executables,
    probe_system,
)
import main as main_mod
from ui.help_badge import (
    HelpBadge,
    _FocusOverlay,
    _get_popover,
    install_focus_animations,
    install_tooltip_guard,
    set_help_mode_enabled,
)
from ui.settings_dialog import (
    SettingsDialog,
    _clean_bootstrap_line,
    _decode_bootstrap_bytes,
)

ROOT = Path(__file__).resolve().parent.parent


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_help_badge_parentless_hidden_and_zero_stray_toplevel_flashes(tmp_path: Path) -> None:
    """HelpBadge without a parent stays hidden; constructing MainWindow/SettingsDialog shows zero stray tiny top-level windows."""
    app = _get_app()
    set_help_mode_enabled(True)

    orphan_badge = HelpBadge("无父级测试", "未放入布局前不应作为独立顶级窗口显示")
    assert orphan_badge.isHidden() is True

    holder = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(holder)
    layout.addWidget(orphan_badge)
    assert orphan_badge.parentWidget() is holder
    assert orphan_badge.isHidden() is False

    set_help_mode_enabled(False)
    assert orphan_badge.isHidden() is True
    set_help_mode_enabled(True)
    assert orphan_badge.isHidden() is False
    holder.close()

    shown_toplevels: list[tuple[str, int, int]] = []

    class _ShowSpy(QtCore.QObject):
        def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
            if event.type() == QtCore.QEvent.Type.Show and isinstance(obj, QtWidgets.QWidget):
                if obj.isWindow() or isinstance(obj, (HelpBadge, _FocusOverlay)):
                    shown_toplevels.append((type(obj).__name__, obj.width(), obj.height()))
            return False

    spy = _ShowSpy(app)
    app.installEventFilter(spy)
    controller = None
    dlg = None
    try:
        controller = main_mod.ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
        controller.analysis_worker.stop()
        controller._timer.stop()
        app.processEvents()
        assert shown_toplevels == [], f"Unexpected Show events during ListenScopeController init: {shown_toplevels}"

        dlg = SettingsDialog(
            probe_system(),
            ResourceLimits(),
            AIConfig(),
            appearance=Appearance(preset="acid_telemetry", theme_mode="light"),
            parent=controller.window,
        )
        app.processEvents()
        assert shown_toplevels == [], f"Unexpected Show events during SettingsDialog init: {shown_toplevels}"
    finally:
        app.removeEventFilter(spy)
        if dlg is not None:
            dlg.close()
        if controller is not None:
            controller.shutdown()
            controller.window.close()
        app.processEvents()


def test_focus_ring_animator_never_shows_overlay_preshow() -> None:
    app = _get_app()
    host = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(host)
    btn = QtWidgets.QPushButton("测试按钮")
    layout.addWidget(btn)
    animator = install_focus_animations(host)
    try:
        # Host is NOT shown yet: FocusIn/Enter/LayoutRequest must not activate overlay
        QtWidgets.QApplication.sendEvent(
            btn,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason),
        )
        QtWidgets.QApplication.sendEvent(btn, QtCore.QEvent(QtCore.QEvent.Type.LayoutRequest))
        app.processEvents()
        assert animator._overlay.isVisible() is False
    finally:
        host.close()


def test_tooltip_guard_strictly_allows_help_badges_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Native Qt ToolTip events never pop up on non-HelpBadge widgets (even chord_progression_lbl), only on `[?]` HelpBadges."""
    app = _get_app()
    set_help_mode_enabled(True)
    native_tips: list[str] = []
    monkeypatch.setattr(QtWidgets.QToolTip, "showText", lambda _pos, text, *_a: native_tips.append(str(text)))

    controller = main_mod.ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        controller.analysis_worker.stop()
        controller._timer.stop()
        mw = controller.window
        mw.resize(1280, 820)
        mw.show()
        app.processEvents()

        # Even if a non-HelpBadge widget retains toolTip text internally (contract), ToolTip events must be swallowed cleanly.
        cw = mw.chroma_widget
        cw._chord_history.extend(["C", "G", "Am", "F"])
        cw._render_recent_progression()
        assert bool(cw.chord_progression_lbl.toolTip().strip())

        pop = _get_popover()
        pop.hide()

        # Dispatch ToolTip events to regular button, progression label, and PlotWidget viewport
        targets: list[QtWidgets.QWidget] = [
            mw.ab_play_btn,
            cw.chord_progression_lbl,
            mw.history_overview_plot.viewport(),
        ]
        # Force an arbitrary tooltip on ab_play_btn to prove global guard also protects against accidental tips
        mw.ab_play_btn.setToolTip("legacy-should-be-blocked")
        for target in targets:
            pos = target.rect().center()
            gpos = target.mapToGlobal(pos)
            ev = QtGui.QHelpEvent(QtCore.QEvent.Type.ToolTip, pos, gpos)
            QtWidgets.QApplication.sendEvent(target, ev)
            app.processEvents()
            assert native_tips == [], f"Native QToolTip leaked on {target}: {native_tips}"
            assert pop.isVisible() is False

        # HelpBadge ToolTip event opens custom HelpPopover
        badges = [b for b in mw.findChildren(HelpBadge) if b.isVisible()]
        if not badges:
            badges = mw.findChildren(HelpBadge)
        assert badges
        badge = badges[0]
        bpos = badge.rect().center()
        bgpos = badge.mapToGlobal(bpos)
        badge_ev = QtGui.QHelpEvent(QtCore.QEvent.Type.ToolTip, bpos, bgpos)
        QtWidgets.QApplication.sendEvent(badge, badge_ev)
        app.processEvents()
        assert pop.isVisible() is True
        assert native_tips == []
        pop.hide()

        # Tab focus onto HelpBadge shows popover; FocusOut triggers hide without error
        QtWidgets.QApplication.sendEvent(
            badge,
            QtGui.QFocusEvent(QtCore.QEvent.Type.FocusIn, QtCore.Qt.FocusReason.TabFocusReason),
        )
        app.processEvents()
        assert pop.isVisible() is True
        pop.hide()
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()


def test_no_unexpected_settooltip_calls_in_ui_source() -> None:
    """Only ui/help_badge.py, chroma chord_progression_lbl summary property, and QSystemTrayIcon tray label retain .setToolTip in ui/."""
    allowed_files = {"help_badge.py", "chroma_widget.py"}
    unexpected: list[str] = []
    for py_file in sorted((ROOT / "ui").glob("*.py")):
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if ".setToolTip(" in line and "tray.setToolTip(" not in line and py_file.name not in allowed_files:
                unexpected.append(f"{py_file.name}:{lineno}: {line.strip()}")
    assert unexpected == [], f"Found unexpected .setToolTip calls in ui/: {unexpected}"


def test_nonblocking_startup_pytorch_scan_and_ui_tick_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup discovery avoids blocking scan in __init__ and drains async discovery result cleanly on _on_ui_tick."""
    app = _get_app()
    fake_py = tmp_path / "custom_env" / "python.exe"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("", encoding="utf-8")

    monkeypatch.delenv("LISTENSCOPE_AI_PYTHON", raising=False)
    monkeypatch.delenv("LISTENSCOPE_MIDI_PYTHON", raising=False)

    scan_calls: list[bool] = []

    def _fake_scan(_roots=(), **_kwargs):
        scan_calls.append(True)
        return [{"installed": True, "python_executable": str(fake_py), "cuda_available": True}]

    monkeypatch.setattr(main_mod, "scan_local_pytorch_installations", _fake_scan)
    monkeypatch.setattr(
        main_mod,
        "_discover_midi_python_executable",
        lambda: None,
    )

    # Fast mode skips scan_local_pytorch_installations
    assert main_mod._discover_ai_python_executable(allow_broad_scan=False) is None
    assert scan_calls == []

    # Broad mode picks up scanned PyTorch Python
    assert main_mod._discover_ai_python_executable(allow_broad_scan=True) == str(fake_py)
    assert len(scan_calls) == 1

    # Mock controller startup with explicit empty ai_python + queued async discovery item
    probed: list[str] = []
    ctrl = main_mod.ListenScopeController(
        use_mock_ai_for_demo=False,
        ai_python_executable="",
        midi_python_executable="",
        work_dir=tmp_path,
    )
    try:
        ctrl.analysis_worker.stop()
        ctrl._timer.stop()
        monkeypatch.setattr(ctrl, "_schedule_external_ai_probe", lambda p: probed.append(p))
        ctrl._ui_ai_discover_q.put_nowait(str(fake_py))
        ctrl._on_ui_tick()
        assert ctrl.ai_job_manager.ai_python_executable == str(fake_py)
        assert ctrl.live_separator.ai_python_executable == str(fake_py)
        assert ctrl.window._ai_python_executable == str(fake_py)
        assert probed == [str(fake_py)]
    finally:
        ctrl.shutdown()
        ctrl.window.close()
        app.processEvents()


def test_run_external_python_capture_output_and_frozen_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_external_python works cleanly when caller passes capture_output=True and in frozen mode."""
    proc = run_external_python(
        [sys.executable, "-c", "print('hello_ext')"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=True,
    )
    assert proc.stdout.strip() == "hello_ext"

    fake_bundle_exe = tmp_path / "ListenScopeCore.exe"
    fake_bundle_exe.write_text("", encoding="utf-8")
    ext_python = tmp_path / "other" / "python.exe"
    ext_python.parent.mkdir(parents=True)
    ext_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_bundle_exe))
    monkeypatch.setenv("LISTENSCOPE_AI_PYTHON", str(fake_bundle_exe))
    cands = _candidate_local_python_executables((tmp_path,))
    assert all(p.resolve() != fake_bundle_exe.resolve() for p in cands)

    # 1) Non-frozen path: capture_output=True is forwarded cleanly to subprocess.run
    recorded_calls: list[tuple[list[str], dict]] = []

    def _fake_run(cmd, **kwargs):
        recorded_calls.append((list(cmd), dict(kwargs)))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"installed": true}\n', stderr="")

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr("core.paths.subprocess.run", _fake_run)
    res = run_external_python(
        [str(ext_python), "-c", "print(1)"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res.returncode == 0
    assert len(recorded_calls) == 1
    cmd_out, kw_out = recorded_calls[0]
    assert cmd_out[0] == str(ext_python)
    assert kw_out["capture_output"] is True

    # 2) Frozen Windows path: capture_output is popped before Popen and PYTHONHOME is stripped
    import ctypes

    popen_calls: list[tuple[list[str], dict]] = []

    class _FakeKernel32:
        class _SetDllDir:
            argtypes = None

            def __call__(self, _arg: object) -> int:
                return 1

        def __init__(self) -> None:
            self.SetDllDirectoryW = self._SetDllDir()

    class _FakePopen:
        def __init__(self, cmd, **kwargs) -> None:
            popen_calls.append((list(cmd), dict(kwargs)))
            self.returncode = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

        def communicate(self, timeout: float | None = None):
            del timeout
            return ('{"installed": true}\n', "")

        def kill(self) -> None:
            pass

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_kw: _FakeKernel32(), raising=False)
    monkeypatch.setattr("core.paths.subprocess.Popen", _FakePopen)
    monkeypatch.setenv("PYTHONHOME", "/bad/pyinstaller/home")

    res_frozen = run_external_python(
        [str(ext_python), "-c", "print(1)"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res_frozen.returncode == 0
    assert len(popen_calls) == 1
    fcmd, fkw = popen_calls[0]
    assert fcmd[0] == str(ext_python)
    assert "capture_output" not in fkw
    assert "PYTHONHOME" not in fkw["env"]


def test_bootstrap_ansi_cp936_cleaning_and_settings_winget_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANSI/PowerShell tilde lines & CP936 mojibake decode cleanly; SettingsDialog invokes clean PS1 bootstrap & Python URL."""
    app = _get_app()

    ansi_tilde = "\x1b[36;1m     |  \x1b[31;1m             ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ \x1b[0m"
    assert _clean_bootstrap_line(ansi_tilde) == ""

    ansi_msg = (
        "\x1b[36;1m     |  \x1b[31;1m检测到 Core/AI Python 为 3.15.2 (64bit)；"
        "实测基线为 Python 3.12 x64 (cu128 + onnxruntime-gpu 1.26.0)。\x1b[0m"
    )
    cleaned = _clean_bootstrap_line(ansi_msg)
    assert "\x1b" not in cleaned
    assert "[36;1m" not in cleaned
    assert cleaned.startswith("检测到 Core/AI Python 为 3.15.2")

    raw_gbk = "检测到 Core/AI Python 为 3.15.2".encode("cp936")
    assert _decode_bootstrap_bytes(raw_gbk) == "检测到 Core/AI Python 为 3.15.2"
    raw_utf8 = "检测到 Core/AI Python 为 3.15.2 ✓".encode("utf-8")
    assert _decode_bootstrap_bytes(raw_utf8) == "检测到 Core/AI Python 为 3.15.2 ✓"

    opened_urls: list[str] = []
    monkeypatch.setattr("ui.settings_dialog._open_web_url", lambda url: opened_urls.append(url))

    dlg = SettingsDialog(
        probe_system(),
        ResourceLimits(),
        AIConfig(),
        appearance=Appearance(preset="acid_telemetry", theme_mode="light"),
    )
    try:
        assert hasattr(dlg, "open_python_url_btn")
        assert hasattr(dlg, "auto_install_py_chk")
        assert dlg.auto_install_py_chk.isChecked() is True
        dlg.open_python_url_btn.click()
        assert opened_urls == [PYTHON_WINDOWS_DOWNLOAD_URL]

        # Mock Windows turnkey bootstrap execution and verify flags, env, and CP936+ANSI log cleaning
        import io
        import time

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "setup_windows.ps1").write_text("# mock\n", encoding="utf-8")
        monkeypatch.setattr("ui.settings_dialog.get_bundle_root", lambda: tmp_path)
        monkeypatch.setattr("ui.settings_dialog.get_app_root", lambda: tmp_path)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr("ui.settings_dialog.shutil.which", lambda name: "C:\\Windows\\System32\\pwsh.exe" if name == "pwsh" else None)

        popen_capture: dict[str, object] = {}

        class _FakeProc:
            def __init__(self, cmd, **kwargs) -> None:
                popen_capture["cmd"] = list(cmd)
                popen_capture["env"] = dict(kwargs.get("env") or {})
                self.stdout = io.BytesIO(
                    b"\x1b[36;1m     |  \x1b[31;1m             ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ \x1b[0m\n"
                    + b"\x1b[31;1m     |  "
                    + "检测到 Python 3.15.2 无法匹配".encode("cp936")
                    + b"\x1b[0m\n"
                )

            def wait(self) -> int:
                return 1

        monkeypatch.setattr("ui.settings_dialog.subprocess.Popen", _FakeProc)
        dlg._run_turnkey_bootstrap(skip_ai=False)

        deadline = time.monotonic() + 3.0
        while dlg._bootstrap_running and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        assert dlg._bootstrap_running is False
        cmd_used = popen_capture["cmd"]
        env_used = popen_capture["env"]
        assert "-NoProfile" in cmd_used
        assert "-NonInteractive" in cmd_used
        assert "-SkipCore" in cmd_used
        assert "-AutoInstallPython" in cmd_used
        assert env_used["PYTHONUTF8"] == "1"
        assert env_used["NO_COLOR"] == "1"
        assert env_used["TERM"] == "dumb"

        final_msg = dlg.bootstrap_status_lbl.text()
        assert "[ERR] 初始化失败 (exit=1)" in final_msg
        assert "检测到 Python 3.15.2 无法匹配" in final_msg
        assert "\x1b" not in final_msg
        assert "[31;1m" not in final_msg
        assert "~~~" not in final_msg
    finally:
        dlg.close()
        app.processEvents()


def test_setup_windows_ps1_winget_discovery_and_ps51_compatibility() -> None:
    """setup_windows.ps1 includes winget fallback, PlainText/UTF-8 handling, and remains PS 5.1 compatible."""
    ps1_text = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    for token in (
        "[switch]$AutoInstallPython",
        '$ErrorView = "NormalView"',
        '$PSStyle.OutputRendering = "PlainText"',
        "Install-PythonViaWinget",
        "Python.Python.3.12",
        "Python.Python.3.11",
        "Test-PythonCandidateMatch",
        "Resolve-LauncherPython",
        "pythoncore-",
    ):
        assert token in ps1_text
    assert "ConciseView" not in ps1_text

    # Rough structural brace balance check outside comments/strings
    opens = ps1_text.count("{")
    closes = ps1_text.count("}")
    assert opens == closes, f"Unbalanced braces in setup_windows.ps1: {{={opens}, }}={closes}"
