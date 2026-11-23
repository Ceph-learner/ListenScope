"""Unified 60/30 Hz display interpolation clock decoupled from 15 Hz DSP snapshots."""

from __future__ import annotations

import math
import time
import numpy as np
from PySide6 import QtCore


class Ballistics:
    """In-place meter/curve ballistics (instant attack, controlled release, peak-hold + fall)."""

    def __init__(
        self,
        size: int,
        *,
        floor_val: float = -120.0,
        release_rate: float = 20.0,
        hold_sec: float = 1.5,
        peak_fall_rate: float = 12.0,
        mode: str = "db",
        release_tau: float = 0.20,
    ) -> None:
        self.size = max(1, int(size))
        self.floor_val = float(floor_val)
        self.release_rate = float(release_rate)
        self.hold_sec = float(hold_sec)
        self.peak_fall_rate = float(peak_fall_rate)
        self.mode = mode
        self.release_tau = float(release_tau)

        self.target = np.full(self.size, self.floor_val, dtype=np.float32)
        self.current = np.full(self.size, self.floor_val, dtype=np.float32)
        self.peak = np.full(self.size, self.floor_val, dtype=np.float32)
        self._hold = np.zeros(self.size, dtype=np.float32)
        self._dirty = False

    def set_target(self, values) -> None:
        arr = np.asarray(values, dtype=np.float32)
        if arr.shape == (self.size,):
            np.copyto(self.target, arr)
            self._dirty = True

    def step(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        dt_f = max(0.001, min(0.1, float(dt)))
        # Instant attack
        rise = self.target > self.current
        self.current[rise] = self.target[rise]
        fall = ~rise
        if np.any(fall):
            if self.mode == "linear":
                alpha = 1.0 - math.exp(-dt_f / max(0.01, self.release_tau))
                self.current[fall] += (self.target[fall] - self.current[fall]) * alpha
            else:
                self.current[fall] = np.maximum(
                    self.target[fall],
                    self.current[fall] - self.release_rate * dt_f,
                )

        # Peak hold + fall
        pk_rise = self.current >= self.peak
        self.peak[pk_rise] = self.current[pk_rise]
        self._hold[pk_rise] = self.hold_sec
        pk_hold = ~pk_rise
        if np.any(pk_hold):
            self._hold[pk_hold] -= dt_f
            falling = pk_hold & (self._hold <= 0.0)
            if np.any(falling):
                self.peak[falling] = np.maximum(
                    self.current[falling],
                    self.peak[falling] - self.peak_fall_rate * dt_f,
                )
        self._dirty = False
        return self.current, self.peak


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
