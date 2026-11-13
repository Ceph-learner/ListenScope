"""Phase 10 headless PySide6 + PyQtGraph GUI smoke test."""

from __future__ import annotations

import gc
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from core.models import ResourceStatus
from core.resource_manager import SimulationOverrides
from main import ListenScopeController


def test_desktop_gui_headless_smoke_capture_settings_and_emergency_stop(tmp_path) -> None:
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
