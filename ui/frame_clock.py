"""Unified 60/30 Hz display interpolation clock decoupled from 15 Hz DSP snapshots."""

from __future__ import annotations

import time
from PySide6 import QtCore


class FrameClock(QtCore.QObject):
    """Single-instance display clock driving smooth meter/needle interpolation."""

    tick = QtCore.Signal(float)

    def __init__(self, parent: QtCore.QObject | None = None, *, default_hz: int = 60) -> None:
        super().__init__(parent)
        self._hz = max(1, min(120, int(default_hz)))
        self._last_t: float = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(8, int(round(1000.0 / self._hz))))
        self._timer.timeout.connect(self._on_timeout)

    def is_active(self) -> bool:
        return self._timer.isActive()

    def set_active(self, on: bool, hz: int | None = None) -> None:
        if hz is not None:
            self._hz = max(1, min(120, int(hz)))
            self._timer.setInterval(max(8, int(round(1000.0 / self._hz))))
        if on:
            if not self._timer.isActive():
                self._last_t = time.monotonic()
                self._timer.start()
        else:
            self._timer.stop()

    def stop(self) -> None:
        self._timer.stop()

    def _on_timeout(self) -> None:
        now = time.monotonic()
        dt = (now - self._last_t) if self._last_t > 0.0 else (1.0 / float(self._hz))
        self._last_t = now
        dt = max(0.001, min(0.1, float(dt)))
        self.tick.emit(dt)
