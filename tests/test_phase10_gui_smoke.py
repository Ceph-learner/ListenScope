"""Phase 10 headless PySide6 + PyQtGraph GUI smoke test."""

from __future__ import annotations

import gc
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from core.models import CaptureMode, ResourceStatus
from core.resource_manager import SimulationOverrides
from main import ListenScopeController


def test_desktop_gui_headless_smoke_capture_settings_and_emergency_stop(tmp_path, monkeypatch) -> None:
    import psutil

    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16 * 1024**3, available=12 * 1024**3, percent=25.0, used=4 * 1024**3),
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws")
    ctrl.resource_manager.set_simulation_overrides(
        SimulationOverrides(system_ram_available_mb=12000.0)
    )

    try:
        ctrl.window.show()
        ctrl.start_capture({"kind": "synthetic", "pattern": "switching"})

        # Pump event loop for ~0.45s so capture -> ring buffer -> CPU AnalysisWorker -> UI timer fire cleanly
        deadline = time.monotonic() + 0.45
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)

        assert ctrl.ring_buffer.available_seconds > 0.1
        snap = ctrl.analysis_worker.latest_snapshot()
        assert snap is not None
        assert ctrl.window.resource_bar.status_badge.text() == ResourceStatus.NORMAL.value

        # Trigger A/B range selection (returns prompt, does not open device crash in headless VM)
        ctrl.window.recent_10_btn.click()
        app.processEvents()
        assert ctrl.window.notice_banner.isVisible()

        # Click Emergency Stop AI button directly from top bar
        ctrl.window.emergency_stop_btn.click()
        for _ in range(15):
            app.processEvents()
            time.sleep(0.02)

        assert ctrl.ai_job_manager.is_busy is False
        assert ctrl.analysis_worker.is_running is True
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        ctrl = None  # type: ignore[assignment]
        app.processEvents()
        gc.collect()
        app.processEvents()


def test_gui_refuses_live_monitor_when_process_capture_falls_back(tmp_path, monkeypatch) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws")
    try:
        ctrl._timer.stop()
        ctrl._capture_backend = SimpleNamespace(
            is_running=True,
            get_stats=lambda: SimpleNamespace(mode=CaptureMode.SYSTEM_LOOPBACK),
            stop=Mock(),
        )
        launch = Mock(return_value=(True, "test"))
        monkeypatch.setattr(ctrl.live_separator, "start", launch)

        ctrl.window.live_widget.toggle_btn.click()

        launch.assert_not_called()
        button = ctrl.window.live_widget.toggle_btn
        assert button.isEnabled() and not button.isChecked()
        assert "系统环回" in ctrl.window.notice_banner.text()
        assert ctrl._capture_backend.is_running
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()


def test_stopping_capture_invalidates_and_stops_live_before_backend(tmp_path, monkeypatch) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctrl = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path / "ws")
    calls = []
    try:
        ctrl._timer.stop()
        ctrl._capture_backend = SimpleNamespace(stop=lambda: calls.append("capture"))
        ctrl.live_separator._starting = True

        def stop_live(*, status_message):
            assert ctrl._capture_backend is None
            calls.append("live")
            ctrl.live_separator._starting = False

        monkeypatch.setattr(ctrl.live_separator, "stop", stop_live)
        ctrl.stop_capture()
        assert calls == ["live", "capture"]
    finally:
        ctrl.window.close()
        ctrl.shutdown()
        app.processEvents()
