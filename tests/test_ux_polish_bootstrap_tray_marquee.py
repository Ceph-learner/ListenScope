"""Comprehensive regression tests for ListenScope UX polish, bootstrap failover/persistence, tray, marquee, logging, resize & 4-lang i18n."""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import logging
from pathlib import Path
import re
import socketserver
import sys
import threading
import time
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
import pytest

from audio.playback import StemMixerEngine
from core.appearance import Appearance
from core.bootstrap_manager import get_bootstrap_manager, parse_progress_marker
from core.config import AIConfig, ResourceLimits
from core.i18n import translate_widget_tree
from core.logging import resolve_log_dir, setup_application_file_logging, teardown_application_file_logging
from core.settings_store import PersistedSettings, load_settings, save_settings
from core.system_probe import PYTORCH_DOWNLOAD_GUIDE, probe_system
from ui.acid_style import (
    _FONT_UI_CJK,
    MarqueeComboBox,
    MarqueeLabel,
    SegmentedBatteryProgressBar,
    TelemetryPulseStrip,
    _acid_controls_qss,
    get_acid_palette,
)
from ui.appearance import AppearanceDialog
from ui.main_window import ListenScopeMainWindow, _load_app_icon
from ui.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parent.parent
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _load_mirror_module():
    path = ROOT / "scripts" / "mirror_wheel_fetch.py"
    spec = importlib.util.spec_from_file_location("mirror_wheel_fetch", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mirror_wheel_fetch"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mirror_wheel_fetch_slow_mirror_failover_and_pypi_picker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slow/stalling wheel mirror triggers failover to fast mirror; rank_pypi_mirrors picks fastest host."""
    mod = _load_mirror_module()
    payload = b"LS_WHEEL_BYTES_" * 4096  # ~60 KB
    expected_sha = hashlib.sha256(payload).hexdigest()
    wheel_name = "torch-2.8.0+cu128-cp312-cp312-win_amd64.whl"

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            mode = getattr(self.server, "mode", "fast")
            if self.path.startswith("/simple/"):
                if mode == "slow":
                    time.sleep(0.35)
                body = b"<html><body>OK</body></html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/torch/" or self.path == "/torch":
                html = f'<html><body><a href="{wheel_name}#sha256={expected_sha}">{wheel_name}</a></body></html>'.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if mode == "slow":
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    # Trickle very slowly so rolling speed check drops & switches mirror
                    for i in range(0, min(len(payload), 2048), 256):
                        self.wfile.write(payload[i : i + 256])
                        self.wfile.flush()
                        time.sleep(0.18)
                except OSError:
                    pass
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    class _Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    slow_srv = _Srv(("127.0.0.1", 0), _Handler)
    slow_srv.mode = "slow"  # type: ignore[attr-defined]
    fast_srv = _Srv(("127.0.0.1", 0), _Handler)
    fast_srv.mode = "fast"  # type: ignore[attr-defined]

    t1 = threading.Thread(target=slow_srv.serve_forever, daemon=True)
    t2 = threading.Thread(target=fast_srv.serve_forever, daemon=True)
    t1.start()
    t2.start()
    try:
        slow_port = slow_srv.server_address[1]
        fast_port = fast_srv.server_address[1]

        monkeypatch.setattr(
            mod,
            "PYTORCH_CU128_MIRRORS",
            (
                ("slow-mirror", f"http://127.0.0.1:{slow_port}"),
                ("fast-mirror", f"http://127.0.0.1:{fast_port}"),
            ),
        )
        rc = mod.fetch_cuda_wheels(
            wheel_dir=tmp_path,
            specs=["torch==2.8.0+cu128"],
            cuda_tag="cu128",
            py_tag="cp312",
            plat_tag="win_amd64",
            min_speed_kbps=500.0,
            stall_sec=1.5,
            grace_sec=0.3,
        )
        assert rc == 0
        out_file = tmp_path / wheel_name
        assert out_file.exists()
        assert out_file.read_bytes() == payload

        ranked = mod.rank_pypi_mirrors(
            [
                ("slow-pypi", f"http://127.0.0.1:{slow_port}/simple"),
                ("fast-pypi", f"http://127.0.0.1:{fast_port}/simple"),
            ]
        )
        assert ranked[0][0] == "fast-pypi"
        assert ranked[0][1] == f"http://127.0.0.1:{fast_port}/simple"
    finally:
        slow_srv.shutdown()
        fast_srv.shutdown()
        slow_srv.server_close()
        fast_srv.server_close()


def test_bootstrap_coordinator_persists_across_settings_close_reopen_and_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing SettingsDialog keeps download alive; reopening restores progress & cancel stops cleanly."""
    app = _get_app()

    marker = parse_progress_marker(
        "@@LS_PROGRESS|pct=42|stage=下载 torch cu128|speed=18.4 MB/s|mirror=mirrors.nju.edu.cn@@"
    )
    assert marker is not None
    assert marker["pct"] == 42
    assert marker["speed"] == "18.4 MB/s"
    assert marker["mirror"] == "mirrors.nju.edu.cn"

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "setup_windows.ps1").write_text("# mock\n", encoding="utf-8")
    monkeypatch.setattr("ui.settings_dialog.get_bundle_root", lambda: tmp_path)
    monkeypatch.setattr("ui.settings_dialog.get_app_root", lambda: tmp_path)
    monkeypatch.setattr("core.bootstrap_manager.get_app_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("ui.settings_dialog.shutil.which", lambda name: "C:\\pwsh.exe" if name == "pwsh" else None)

    release_evt = threading.Event()
    killed_flag = threading.Event()

    class _FakeStdout:
        def __init__(self) -> None:
            self._lines = [
                "@@LS_PROGRESS|pct=42|stage=下载 torch cu128|speed=18.4 MB/s|mirror=mirrors.nju.edu.cn@@\n".encode("utf-8"),
                "镜像下载稳定推进中\n".encode("utf-8"),
            ]
            self._idx = 0

        def readline(self) -> bytes:
            if self._idx < len(self._lines):
                chunk = self._lines[self._idx]
                self._idx += 1
                return chunk
            release_evt.wait(timeout=4.0)
            return b""

    class _FakeProc:
        def __init__(self, cmd, **kwargs) -> None:
            self.pid = 424242
            self.stdout = _FakeStdout()

        def wait(self) -> int:
            return 1 if killed_flag.is_set() else 0

        def kill(self) -> None:
            killed_flag.set()
            release_evt.set()

    monkeypatch.setattr("ui.settings_dialog.subprocess.Popen", lambda *a, **kw: _FakeProc(*a, **kw))
    monkeypatch.setattr("core.bootstrap_manager.subprocess.run", lambda *a, **kw: None)

    dlg1 = SettingsDialog(probe_system(), ResourceLimits(), AIConfig())
    dlg1._run_turnkey_bootstrap(skip_ai=False)
    for _ in range(30):
        app.processEvents()
        if dlg1.bootstrap_progress.value() >= 42:
            break
        time.sleep(0.02)

    assert dlg1._bootstrap_running is True
    assert dlg1.bootstrap_progress.value() >= 42
    assert "18.4 MB/s" in dlg1.bootstrap_meta_lbl.text()
    assert "mirrors.nju.edu.cn" in dlg1.bootstrap_meta_lbl.text()
    assert dlg1.cancel_bootstrap_btn.isEnabled() is True

    # Close SettingsDialog #1 mid-download; manager must continue running
    dlg1.reject()
    dlg1.deleteLater()
    app.processEvents()
    assert bool(get_bootstrap_manager().snapshot().get("running")) is True

    # Open SettingsDialog #2 and verify live progress/meta/buttons survive intact
    dlg2 = SettingsDialog(probe_system(), ResourceLimits(), AIConfig())
    try:
        assert dlg2._bootstrap_running is True
        assert dlg2.setup_all_btn.isEnabled() is False
        assert dlg2.cancel_bootstrap_btn.isEnabled() is True
        assert dlg2.bootstrap_progress.value() >= 42
        assert "18.4 MB/s" in dlg2.bootstrap_meta_lbl.text()

        # Explicit cancel cleans up and unlocks buttons cleanly
        dlg2.cancel_bootstrap_btn.click()
        for _ in range(40):
            app.processEvents()
            if not dlg2._bootstrap_running:
                break
            time.sleep(0.02)
        assert killed_flag.is_set()
        assert dlg2._bootstrap_running is False
        assert dlg2.setup_all_btn.isEnabled() is True
    finally:
        release_evt.set()
        dlg2.close()
        dlg2.deleteLater()
        app.processEvents()


def test_disk_logging_creates_and_tears_down_rotating_log(tmp_path: Path) -> None:
    """core/logging writes structured log files cleanly and detaches on shutdown."""
    log_dir = resolve_log_dir(tmp_path)
    log_file = setup_application_file_logging(log_dir)
    try:
        logging.getLogger("test.ux").info("ListenScope disk logging smoke check")
        for h in logging.getLogger().handlers:
            h.flush()
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "ListenScope disk logging smoke check" in content
    finally:
        teardown_application_file_logging()


def test_settings_diagnostics_deduplicated_and_appearance_persistence(tmp_path: Path) -> None:
    """System Diagnostics does not repeat manual PYTORCH_DOWNLOAD_GUIDE; 5 new Appearance fields round-trip at schema 2."""
    _get_app()
    report = probe_system()
    dlg = SettingsDialog(report, ResourceLimits(), AIConfig())
    try:
        assert "PYTORCH_DOWNLOAD_GUIDE" not in dlg.status_alert_lbl.text()
        assert PYTORCH_DOWNLOAD_GUIDE not in dlg.status_alert_lbl.text()
        assert hasattr(dlg, "status_goto_env_btn")
        assert hasattr(dlg, "status_open_logs_btn")
        dlg.status_goto_env_btn.click()
        assert dlg._active_category == "midi"
    finally:
        dlg.close()
        dlg.deleteLater()

    app_cfg = Appearance(
        preset="acid_telemetry",
        theme_mode="light",
        telemetry_animation_strength=85,
        music_reactive_animations=False,
        focus_style="brackets",
        ui_surface_style="beveled",
        close_to_tray=False,
    )
    settings_path = tmp_path / "settings.json"
    save_settings(
        PersistedSettings(resource_limits=ResourceLimits(), ai_config=AIConfig(), appearance=app_cfg),
        settings_path,
    )
    loaded = load_settings(settings_path)
    assert loaded.schema_version == 2
    assert loaded.appearance.telemetry_animation_strength == 85
    assert loaded.appearance.music_reactive_animations is False
    assert loaded.appearance.focus_style == "brackets"
    assert loaded.appearance.ui_surface_style == "beveled"
    assert loaded.appearance.close_to_tray is False


def test_mainwindow_ux_polish_marquee_dismiss_hide_a_resize_tray_and_4lang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify marquee scrolling, battery gauge, music pulse & STATIC_LOCK, header layout, dismissible banner, hidden [A], resize, tray & 0 EN/KO leaks."""
    app = _get_app()
    assert not _load_app_icon().isNull()

    # Balanced CJK font order avoids mismatched SimSun narrow/wide glyphs on buttons/combos
    assert _FONT_UI_CJK.find("Microsoft YaHei UI") < _FONT_UI_CJK.find("Cascadia Code")
    p = get_acid_palette("light")
    tactile_qss = _acid_controls_qss(p, variant="light", base_px=12, mono_family="Consolas", surface_style="tactile")
    flat_qss = _acid_controls_qss(p, variant="light", base_px=12, mono_family="Consolas", surface_style="flat")
    assert "border-top: 1px solid #FFFFFF;" in tactile_qss
    assert "border-top: 1px solid #FFFFFF;" not in flat_qss

    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(sample_rate=44100, channels=2),
        appearance=Appearance(preset="acid_telemetry", theme_mode="light", frameless=True),
    )
    try:
        win.show()
        app.processEvents()

        # 1. Topbar no-overlap & header subtitle moved cleanly into eyebrow
        assert win._acid_hero_sub_lbl.isVisible() is False
        assert "实时频谱" in win._brand_eye.text()

        # 2. STATIC_LOCK badge + footer tooltip + music-reactive micro-animations freeze cleanly
        assert win._acid_footer.lock_help is not None
        assert win._acid_footer.lock_help.parentWidget() is win._acid_footer
        win.update_music_telemetry(0.85, 0.90)
        assert win._telemetry_phase > 0.0
        frozen_phase = win._telemetry_phase
        win._acid_footer.lock_btn.setChecked(True)
        win.update_music_telemetry(0.95, 0.95)
        assert win._telemetry_phase == frozen_phase
        win._acid_footer.lock_btn.setChecked(False)

        # 3. Battery segmented progress bar + Pulse strip
        assert isinstance(win.mixer_widget.job_progress, SegmentedBatteryProgressBar)
        assert isinstance(win.spectrum_widget._pulse_strip, TelemetryPulseStrip)

        # 4. Marquee combos & labels scroll overflowing names without truncating short names
        assert isinstance(win.source_combo, MarqueeComboBox)
        assert isinstance(win.ai_2stem_combo, MarqueeComboBox)
        assert isinstance(win.bookmark_combo, MarqueeComboBox)
        assert isinstance(win.chroma_widget.chord_progression_lbl, MarqueeLabel)
        win.chroma_widget.track_status_lbl.setFixedWidth(180)
        win.chroma_widget.track_status_lbl.setText(
            "VeryLongArtistName - VeryLongTrackTitleThatExceedsAvailableWidth (Remastered Deluxe Edition)"
        )
        assert win.chroma_widget.track_status_lbl._needs_scroll() is True

        # 5. Dismissible banner & OOM banner × buttons
        win.show_banner_message("🛑 测试禁止停止提示横幅", tone="warn")
        assert win._notice_bar.isVisible() is True
        assert win.notice_banner.isVisible() is True
        win.notice_dismiss_btn.click()
        assert win._notice_bar.isVisible() is False
        assert win.notice_banner.isVisible() is False

        win.mixer_widget.oom_banner.setVisible(True)
        win.mixer_widget.oom_dismiss_btn.click()
        assert win.mixer_widget.oom_banner.isVisible() is False

        # 6. All PyQtGraph [A] auto-range buttons hidden
        plots = win.findChildren(pg.PlotWidget)
        assert len(plots) >= 7
        for pw in plots:
            assert pw.getPlotItem().autoBtn.isVisible() is False

        # 7. Frameless 8-edge resize geometry + minimum size
        assert win.minimumWidth() >= 940 and win.minimumHeight() >= 620
        edges = win._hit_test_resize_edges(QtCore.QPoint(win.width() - 2, win.height() - 2))
        assert bool(edges & QtCore.Qt.Edge.RightEdge)
        assert bool(edges & QtCore.Qt.Edge.BottomEdge)
        orig_w, orig_h = win.width(), win.height()
        win._resize_edges = QtCore.Qt.Edge.RightEdge | QtCore.Qt.Edge.BottomEdge
        win._resize_start_geom = QtCore.QRect(win.geometry())
        win._resize_start_global = QtCore.QPoint(100, 100)
        win._apply_software_resize(QtCore.QPoint(180, 140))
        assert win.width() == orig_w + 80
        assert win.height() == orig_h + 40
        win._resize_edges = QtCore.Qt.Edge(0)

        # 8. Close-to-tray + force_quit
        class _FakeTray:
            def __init__(self) -> None:
                self.visible = True
                self.msgs: list[tuple[str, str]] = []

            def isVisible(self) -> bool:
                return self.visible

            def hide(self) -> None:
                self.visible = False

            def showMessage(self, title: str, msg: str, *_a) -> None:
                self.msgs.append((title, msg))

        fake_tray = _FakeTray()
        win._tray_icon = fake_tray  # type: ignore[assignment]
        monkeypatch.setattr(QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
        ev = QtGui.QCloseEvent()
        win.closeEvent(ev)
        assert ev.isAccepted() is False
        assert win.isVisible() is False
        assert len(fake_tray.msgs) == 1

        # Now test true quit via force_quit()
        win.show()
        win._force_quit = True
        ev2 = QtGui.QCloseEvent()
        win.closeEvent(ev2)
        assert ev2.isAccepted() is True
        assert fake_tray.visible is False

        # 9. Zero Chinese characters leaked in EN / KO across AppearanceDialog + SettingsDialog
        app_dlg = AppearanceDialog(Appearance(preset="acid_telemetry", theme_mode="light", language="zh"), "")
        set_dlg = SettingsDialog(probe_system(), ResourceLimits(), AIConfig())
        try:
            for lang in ("en", "ko"):
                for root_w in (app_dlg, set_dlg):
                    translate_widget_tree(root_w, lang)
                    for w in (*root_w.findChildren(QtWidgets.QLabel), *root_w.findChildren(QtWidgets.QAbstractButton)):
                        txt = w.text().strip()
                        if txt:
                            assert not _CJK_CHAR_RE.search(txt), f"CJK leak in {type(root_w).__name__} ({lang}): {txt!r}"
                    for cb in root_w.findChildren(QtWidgets.QComboBox):
                        if bool(cb.property("lsKeepItems")):
                            continue
                        for idx in range(cb.count()):
                            itxt = cb.itemText(idx)
                            assert not _CJK_CHAR_RE.search(itxt), f"Combo CJK leak ({lang}): {itxt!r}"
        finally:
            app_dlg.close()
            app_dlg.deleteLater()
            set_dlg.close()
            set_dlg.deleteLater()
    finally:
        win.force_quit()
        win.deleteLater()
        app.processEvents()


def test_ui_rails_tabbar_elided_standby_bay_and_preset_brand_hygiene(tmp_path: Path) -> None:
    from dataclasses import replace
    from core.appearance import LIGHT_PRESETS, PRESETS
    from core.i18n import translate_text
    from core.models import CaptureMode, CaptureStats
    from core.system_probe import probe_system
    from ui.acid_style import (
        AcidSplitter,
        AcidTabBar,
        ElidedLabel,
        SignalLockDot,
        WindowGlyphButton,
        WorkspaceRailHandle,
    )
    from ui.main_window import ListenScopeMainWindow

    # 1. Preset brand hygiene: zero Codex / Claude in PRESETS, LIGHT_PRESETS, or ui/*.py; silent legacy migration works
    forbidden_brand = re.compile(r"\bcodex\b|\bclaude\b", re.IGNORECASE)
    for table in (PRESETS, LIGHT_PRESETS):
        assert tuple(table.keys()) == ("classic", "lenso", "graphite", "terracotta", "acid_telemetry")
        for key, entry in table.items():
            assert not forbidden_brand.search(key)
            assert not forbidden_brand.search(entry[0])
    assert Appearance.from_mapping({"preset": "codex"}).preset == "graphite"
    assert Appearance.from_mapping({"preset": "claude"}).preset == "terracotta"

    repo_root = Path(__file__).resolve().parent.parent
    for py_file in sorted((repo_root / "ui").glob("*.py")):
        assert not forbidden_brand.search(py_file.read_text(encoding="utf-8")), f"Forbidden brand in {py_file.name}"

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(sample_rate=44100, channels=2),
        appearance=Appearance(preset="acid_telemetry", theme_mode="dark", frameless=True),
    )
    try:
        win.resize(1280, 820)
        win.show()
        app.processEvents()

        # 2. Signature widgets wired & rendered cleanly
        assert isinstance(win._brand_eye, ElidedLabel)
        assert win._brand_eye.minimumSizeHint().width() <= 24
        assert win._brand_eye.minimumSizeHint().height() >= win._brand_eye.fontMetrics().height()
        assert isinstance(win.tabs.tabBar(), AcidTabBar)
        assert isinstance(win.mixer_widget.analysis_tabs.tabBar(), AcidTabBar)
        assert isinstance(win.chroma_widget._chroma_splitter, AcidSplitter)
        assert isinstance(win.mixer_widget._workspace_splitter, AcidSplitter)
        assert isinstance(win._workspace_rail, WorkspaceRailHandle)
        assert isinstance(win.win_min_btn, WindowGlyphButton)
        assert isinstance(win.win_max_btn, WindowGlyphButton)
        assert isinstance(win.win_close_btn, WindowGlyphButton)
        assert isinstance(win._capture_dot, SignalLockDot)

        # 3. SignalLockDot tracks capture active state & pulse
        assert win._capture_dot.is_active() is False
        win.set_capture_active_ui(True)
        assert win._capture_dot.is_active() is True
        win.set_capture_active_ui(False)
        assert win._capture_dot.is_active() is False

        # 4. Interactive upper/lower WorkspaceRailHandle adjusts history_overview_plot height & resets
        base_h = win.history_overview_plot.minimumHeight()
        win._on_workspace_rail_dragged(-36)
        assert win.history_overview_plot.minimumHeight() > base_h
        win._on_workspace_rail_reset()
        assert win.history_overview_plot.minimumHeight() == base_h

        # 5. StemMixerWidget empty-bay standby card is visible when no stems are loaded
        assert win.mixer_widget._empty_tracks_card.isHidden() is False

        # 6. Dynamic capture status & key relation strings translate cleanly in EN/KO with zero CJK leak
        for lang in ("en", "ko"):
            win.apply_appearance(replace(win.appearance, language=lang), force_theme=True)
            win.update_capture_stats(
                CaptureStats(
                    mode=CaptureMode.PROCESS_LOOPBACK,
                    pid=42,
                    process_name="synthetic.exe",
                    sample_rate=48000,
                    channels=2,
                    dtype="float32",
                    is_running=True,
                    is_silent=False,
                    rms_dbfs=-14.2,
                ),
                ring_available_sec=18.5,
            )
            assert not _CJK_CHAR_RE.search(win.capture_status_lbl.text())
            assert not _CJK_CHAR_RE.search(win.history_coverage_lbl.text())
            assert not _CJK_CHAR_RE.search(win.mixer_widget._empty_tracks_hint_lbl.text())
            assert not _CJK_CHAR_RE.search(translate_text("同主音调式混合倾向 (A major / A minor)", lang))
            assert not _CJK_CHAR_RE.search(translate_text("关系大小调接近 (C major / A minor)", lang))
    finally:
        win.prepare_for_shutdown()
        win.force_quit()
        win.deleteLater()
        app.processEvents()


def test_frameless_dialogs_topbar_no_clip_and_checkbox_spacing():
    """Verify Round-2 UI polish: frameless Settings/Appearance/Practice dialogs, topbar fit at 1280px with VRAM, and checkbox spacing."""
    from core.config import AIConfig, ResourceLimits
    from core.models import ResourceSnapshot, ResourceStatus
    from core.system_probe import probe_system
    from ui.acid_style import WindowGlyphButton, acid_stylesheet
    from ui.appearance import AppearanceDialog, appearance_stylesheet
    from ui.chord_practice import ChordPracticeDialog
    from ui.main_window import DARK_STYLESHEET, ListenScopeMainWindow
    from ui.settings_dialog import SettingsDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 1. Checkbox QSS breathing room in both Acid and non-Acid stylesheets
    for qss in (
        acid_stylesheet(Appearance(preset="acid_telemetry", theme_mode="light"), "light"),
        acid_stylesheet(Appearance(preset="acid_telemetry", theme_mode="dark"), "dark"),
        appearance_stylesheet(DARK_STYLESHEET, Appearance(preset="classic", theme_mode="dark"), system_is_dark=True),
    ):
        assert "spacing: 8px;" in qss
        assert "padding: 2px 8px 2px 2px;" in qss
        assert "QFrame#dialogShellFrame[frameless=\"true\"]" in qss

    # 2. Topbar brand eyebrow fits without clipping at 1280x820 even with realistic 8GB VRAM numbers
    report = probe_system()
    win = ListenScopeMainWindow(
        hardware_report=report,
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(sample_rate=44100, channels=2),
        appearance=Appearance(preset="acid_telemetry", theme_mode="light", frameless=True),
    )
    try:
        win.resize(1280, 820)
        win.show()
        snap = ResourceSnapshot(
            timestamp=1700000000.0,
            main_ram_mb=210.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=16384.0,
            system_ram_available_mb=10420.0,
            gpu_name="RTX 5060 Ti",
            vram_total_mb=8151.0,
            vram_used_mb=2261.0,
            vram_free_mb=5890.0,
            gpu_utilization_pct=12.0,
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            audio_queue_size=0,
            audio_queue_maxsize=64,
            ai_buffer_seconds=0.0,
            status=ResourceStatus.NORMAL,
        )
        win.resource_bar.update_snapshot(snap)
        app.processEvents()

        eye_text = win._brand_eye.text()
        assert "实时频谱" in eye_text
        needed_w = win._brand_eye.fontMetrics().horizontalAdvance(eye_text)
        avail_w = win._brand_eye.contentsRect().width()
        assert avail_w >= needed_w, f"Topbar brand eyebrow clipped at 1280px: avail={avail_w}px < needed={needed_w}px ({eye_text!r})"
        assert win.resource_bar.objectName() == "resourceCapsule"

        # 3. SettingsDialog, AppearanceDialog, and ChordPracticeDialog adopt frameless shell + vector close button
        settings_dlg = SettingsDialog(
            report,
            ResourceLimits(),
            AIConfig(),
            appearance=Appearance(preset="acid_telemetry", theme_mode="light", frameless=True),
            acid_variant="light",
            parent=win,
        )
        try:
            assert bool(settings_dlg.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint)
            assert settings_dlg._shell_frame.objectName() == "dialogShellFrame"
            assert settings_dlg._shell_frame.property("frameless") is True
            assert isinstance(settings_dlg._chrome.close_btn, WindowGlyphButton)
            assert settings_dlg._chrome.close_btn.isHidden() is False
            settings_dlg.frameless_chk.setChecked(False)
            app.processEvents()
            assert not bool(settings_dlg.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint)
            assert settings_dlg._chrome.close_btn.isHidden() is True
        finally:
            settings_dlg.close()
            settings_dlg.deleteLater()

        app_dlg = AppearanceDialog(
            Appearance(preset="acid_telemetry", theme_mode="dark", frameless=True),
            DARK_STYLESHEET,
            parent=win,
            system_is_dark=True,
        )
        try:
            assert bool(app_dlg.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint)
            assert app_dlg._shell_frame.objectName() == "dialogShellFrame"
            assert isinstance(app_dlg._chrome.close_btn, WindowGlyphButton)
            app_dlg._frameless_chk.setChecked(False)
            app.processEvents()
            assert not bool(app_dlg.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint)
        finally:
            app_dlg.close()
            app_dlg.deleteLater()

        prac_dlg = ChordPracticeDialog(["C", "G", "Am", "F"], None, 0, parent=win, acid_variant="light")
        try:
            assert bool(prac_dlg.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint)
            assert prac_dlg._shell_frame.objectName() == "dialogShellFrame"
            assert isinstance(prac_dlg._chrome.close_btn, WindowGlyphButton)
        finally:
            prac_dlg.close()
            prac_dlg.deleteLater()
    finally:
        win.prepare_for_shutdown()
        win.force_quit()
        win.deleteLater()
        app.processEvents()


