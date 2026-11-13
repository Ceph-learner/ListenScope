"""PyQtGraph real-time waveform, FFT spectrum, log-frequency spectrum, and bounded spectrogram UI."""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from core.models import AnalysisSnapshot


class _FftFrequencyAxis(pg.AxisItem):
    """Display readable frequency labels on the FFT's log-scaled axis."""

    def logTickValues(self, minVal, maxVal, size, stdTicks):
        span = maxVal - minVal
        if span <= 0 or size <= 0:
            return []
        offsets = (1, 2, 5) if span >= 1.0 else range(1, 10)
        decades = range(math.floor(minVal), math.ceil(maxVal) + 1)
        min_spacing = 64 * span / size
        ticks = []
        # Give decade labels priority over the intervening labels.
        for multiplier in offsets:
            offset = math.log10(multiplier)
            for decade in decades:
                tick = decade + offset
                if minVal <= tick <= maxVal and all(abs(tick - old) >= min_spacing for old in ticks):
                    ticks.append(tick)
        if not ticks:
            # A deep zoom can put the entire view between two standard frequency ticks.
            ticks = [(minVal + maxVal) / 2]
        return [(min_spacing, sorted(ticks))]

    def logTickStrings(self, values, scale, spacing):
        labels = []
        for tick in values:
            hz = 10**tick * scale
            labels.append(f"{hz / 1000:.4g}k" if hz >= 1000 else f"{hz:.4g}")
        return labels


class SpectrumAnalysisWidget(QtWidgets.QWidget):
    """Lightweight GPU/CPU-friendly PyQtGraph display consuming precomputed AnalysisSnapshot only."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(8)

        # Level & status header strip
        hdr = QtWidgets.QHBoxLayout()
        self.rms_label = QtWidgets.QLabel("RMS: -120.0 dBFS")
        self.peak_label = QtWidgets.QLabel("Peak: -120.0 dBFS")
        self.pitch_label = QtWidgets.QLabel("主音高 / 频谱峰: -")
        self.window_label = QtWidgets.QLabel("环形缓冲已保留: 0.0 s")
        for lbl in (self.rms_label, self.peak_label, self.pitch_label, self.window_label):
            lbl.setStyleSheet("padding: 4px 8px; background: #1C2026; border-radius: 4px;")
            hdr.addWidget(lbl)
        hdr.addStretch(1)
        root.addLayout(hdr)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # Row 1: Waveform
        self.wave_plot = pg.PlotWidget(title="实时波形包络 (Waveform Min/Max)")
        self.wave_plot.setBackground("#14161A")
        self.wave_plot.setYRange(-1.05, 1.05)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.2)
        self._wave_max_curve = self.wave_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.2))
        self._wave_min_curve = self.wave_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.2))
        splitter.addWidget(self.wave_plot)

        # Row 2: FFT Spectrum + Log Frequency Spectrum side by side
        mid_row = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        frequency_axis = _FftFrequencyAxis(orientation="bottom")
        self.fft_plot = pg.PlotWidget(title="FFT 频谱 (dBFS)", axisItems={"bottom": frequency_axis})
        self.fft_plot.setBackground("#14161A")
        self.fft_plot.setLabel("bottom", "频率 (Hz)")
        self.fft_plot.setYRange(-105, 5)
        self.fft_plot.setLogMode(x=True, y=False)
        self.fft_plot.showGrid(x=True, y=True, alpha=0.2)
        self._fft_curve = self.fft_plot.plot(pen=pg.mkPen("#2EC27E", width=1.5))
        mid_row.addWidget(self.fft_plot)

        self.log_plot = pg.PlotWidget(title="对数频率能量谱 (27.5 Hz - 16 kHz, 96-bin)")
        self.log_plot.setBackground("#14161A")
        self.log_plot.setYRange(-105, 5)
        self.log_plot.showGrid(x=True, y=True, alpha=0.2)
        self._log_curve = self.log_plot.plot(
            pen=pg.mkPen("#F5A623", width=1.8),
            fillLevel=-105,
            brush=(245, 166, 35, 45),
        )
        mid_row.addWidget(self.log_plot)
        splitter.addWidget(mid_row)

        # Row 3: Bounded 30s Spectrogram Image
        self.spec_plot = pg.PlotWidget(title="最近时频图 (Spectrogram, 有界历史 <= 30s)")
        self.spec_plot.setBackground("#14161A")
        self._spec_img = pg.ImageItem()
        try:
            cmap = pg.colormap.get("inferno") if hasattr(pg, "colormap") else None
        except Exception:
            cmap = None
        if cmap is not None:
            self._spec_img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
        self.spec_plot.addItem(self._spec_img)
        splitter.addWidget(self.spec_plot)

        splitter.setSizes([140, 220, 180])
        root.addWidget(splitter, 1)

    def update_analysis(self, snap: AnalysisSnapshot, spectrogram: np.ndarray | None = None) -> None:
        self.rms_label.setText(f"RMS: {snap.rms_dbfs:.1f} dBFS")
        self.peak_label.setText(f"Peak: {snap.peak_dbfs:.1f} dBFS")
        if snap.pitch.frequency_hz is not None:
            self.pitch_label.setText(
                f"主音高 / Peak: {snap.pitch.note_name} ({snap.pitch.frequency_hz:.1f} Hz, {snap.pitch.cents_offset:+.1f} cents)"
            )
        else:
            self.pitch_label.setText(f"主音高 / Peak: {snap.pitch.note_name}")
        self.window_label.setText(f"环形缓冲: {snap.window_seconds:.1f} / 120.0 s")

        if snap.waveform_min and snap.waveform_max:
            x_w = np.arange(len(snap.waveform_min), dtype=np.float32)
            self._wave_max_curve.setData(x_w, np.asarray(snap.waveform_max, dtype=np.float32))
            self._wave_min_curve.setData(x_w, np.asarray(snap.waveform_min, dtype=np.float32))

        if snap.fft_freqs_hz and snap.fft_db:
            freqs = np.asarray(snap.fft_freqs_hz, dtype=np.float32)
            mask = freqs > 0
            self._fft_curve.setData(freqs[mask], np.asarray(snap.fft_db, dtype=np.float32)[mask])

        if snap.log_spectrum_db:
            x_log = np.arange(len(snap.log_spectrum_db), dtype=np.float32)
            self._log_curve.setData(x_log, np.asarray(snap.log_spectrum_db, dtype=np.float32))

        if spectrogram is not None and spectrogram.size > 0:
            self._spec_img.setImage(spectrogram, autoLevels=False, levels=(-90.0, -5.0))
