"""PyQtGraph real-time waveform, FFT spectrum, log-frequency spectrum, and bounded spectrogram UI."""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from core.models import AnalysisSnapshot

ANALYSIS_VIEWS = {
    "monitor": ("实时监听", ((0, 0, 1, 2), (2, 0, 1, 1), (2, 1, 1, 1), (1, 0, 1, 2)), (4, 3, 3), (1, 1, 0)),
    "frequency": ("频率诊断", ((0, 1, 1, 1), (0, 0, 2, 1), (1, 1, 1, 1), (2, 0, 1, 2)), (2, 3, 2), (3, 2, 0)),
    "history": ("时频追踪", ((1, 0, 1, 1), (1, 1, 1, 1), (1, 2, 1, 1), (0, 0, 1, 3)), (5, 3, 0), (1, 1, 1)),
}

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
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)
        toolbar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("实时分析")
        title.setObjectName("analysisHeading")
        toolbar.addWidget(title, 1)
        self.view_combo = QtWidgets.QComboBox()
        self.view_combo.setAccessibleName("实时分析布局")
        for key, (name, *_geometry) in ANALYSIS_VIEWS.items():
            self.view_combo.addItem(name, key)
        toolbar.addWidget(self.view_combo)
        root.addLayout(toolbar)

        metrics = QtWidgets.QHBoxLayout()
        metrics.setSpacing(9)
        self.pitch_label = QtWidgets.QLabel("—")
        self.pitch_label.setObjectName("analysisPitch")
        self.pitch_detail = QtWidgets.QLabel("等待有效音高")
        self.rms_label = QtWidgets.QLabel("−120.0 dBFS")
        self.peak_label = QtWidgets.QLabel("−120.0 dBFS")
        self.window_label = QtWidgets.QLabel("0.0 / 120 s")
        self.level_meter = QtWidgets.QProgressBar()
        self.level_meter.setObjectName("analysisLevel")
        self.level_meter.setAccessibleName("RMS 信号电平，−60 到 0 dBFS")
        self.level_meter.setRange(0, 60)
        self.level_meter.setValue(0)
        self.level_meter.setTextVisible(False)
        self.level_meter.setFixedHeight(4)
        for caption, value, detail, stretch in (
            ("主音高", self.pitch_label, self.pitch_detail, 5),
            ("平均电平 · RMS", self.rms_label, self.level_meter, 4),
            ("峰值电平", self.peak_label, None, 3),
            ("历史缓冲", self.window_label, None, 3),
        ):
            metrics.addWidget(self._metric_card(caption, value, detail), stretch)
        root.addLayout(metrics)
        self._plot_grid = QtWidgets.QGridLayout()
        self._plot_grid.setSpacing(8)
        root.addLayout(self._plot_grid, 1)

        # Row 1: Waveform
        self.wave_plot = pg.PlotWidget()
        self.wave_plot.setLabel("bottom", "包络点", **{"font-size": "9pt"})
        self.wave_plot.setBackground("#14161A")
        self.wave_plot.setYRange(-1.05, 1.05)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.2)
        self._wave_max_curve = self.wave_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.2))
        self._wave_min_curve = self.wave_plot.plot(pen=pg.mkPen("#4EA8DE", width=1.2))
        frequency_axis = _FftFrequencyAxis(orientation="bottom")
        self.fft_plot = pg.PlotWidget(axisItems={"bottom": frequency_axis})
        self.fft_plot.setBackground("#14161A")
        self.fft_plot.setLabel("bottom", "频率 (Hz)", **{"font-size": "9pt"})
        self.fft_plot.setYRange(-105, 5)
        self.fft_plot.setLogMode(x=True, y=False)
        self.fft_plot.showGrid(x=True, y=True, alpha=0.2)
        self._fft_curve = self.fft_plot.plot(pen=pg.mkPen("#2EC27E", width=1.5))
        log_axis = _FftFrequencyAxis(orientation="bottom")
        self.log_plot = pg.PlotWidget(axisItems={"bottom": log_axis})
        self.log_plot.setBackground("#14161A")
        self.log_plot.setLabel("bottom", "频率 (Hz)", **{"font-size": "9pt"})
        self.log_plot.setLogMode(x=True, y=False)
        self.log_plot.setYRange(-105, 5)
        self.log_plot.showGrid(x=True, y=True, alpha=0.2)
        self._log_curve = self.log_plot.plot(
            pen=pg.mkPen("#F5A623", width=1.8),
            fillLevel=-105,
            brush=(245, 166, 35, 45),
        )
        self.spec_plot = pg.PlotWidget()
        self.spec_plot.setBackground("#14161A")
        self.spec_plot.setLabel("bottom", "更新帧（右侧为最新）", **{"font-size": "9pt"})
        self.spec_plot.setLabel("left", "频带序号", **{"font-size": "9pt"})
        self._spec_img = pg.ImageItem()
        try:
            cmap = pg.colormap.get("inferno") if hasattr(pg, "colormap") else None
        except Exception:
            cmap = None
        if cmap is not None:
            self._spec_img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
        self.spec_plot.addItem(self._spec_img)
        self._plots = (self.wave_plot, self.fft_plot, self.log_plot, self.spec_plot)
        self._chart_cards = tuple(self._chart_card(name, unit, plot) for name, unit, plot in zip(
            ("实时波形", "FFT 频谱", "频带能量", "最近时频图"),
            ("幅值", "dBFS", "dBFS", "有界历史"),
            self._plots,
        ))
        self.view_combo.currentIndexChanged.connect(self._arrange_plots)
        self._arrange_plots()

    @staticmethod
    def _metric_card(caption, value, detail):
        card = QtWidgets.QFrame()
        card.setObjectName("analysisMetric")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(3)
        title = QtWidgets.QLabel(caption)
        title.setObjectName("analysisCaption")
        layout.addWidget(title)
        if not value.objectName():
            value.setObjectName("analysisValue")
        layout.addWidget(value)
        if detail is not None:
            if isinstance(detail, QtWidgets.QLabel):
                detail.setObjectName("analysisCaption")
            layout.addWidget(detail)
        layout.addStretch(1)
        return card

    def _arrange_plots(self) -> None:
        _, positions, rows, columns = ANALYSIS_VIEWS[self.view_combo.currentData()]
        for card, position in zip(self._chart_cards, positions):
            self._plot_grid.removeWidget(card)
            self._plot_grid.addWidget(card, *position)
        for index, weight in enumerate(rows):
            self._plot_grid.setRowStretch(index, weight)
        for index, weight in enumerate(columns):
            self._plot_grid.setColumnStretch(index, weight)

    @staticmethod
    def _chart_card(name: str, unit: str, plot: pg.PlotWidget) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("analysisChart")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(1, 4, 1, 1)
        layout.setSpacing(1)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(10, 0, 10, 0)
        title = QtWidgets.QLabel(name)
        title.setObjectName("analysisChartHeading")
        caption = QtWidgets.QLabel(unit)
        caption.setObjectName("analysisCaption")
        header.addWidget(title, 1)
        header.addWidget(caption)
        layout.addLayout(header)
        plot.setMinimumHeight(54)
        layout.addWidget(plot, 1)
        return card

    def update_analysis(self, snap: AnalysisSnapshot, spectrogram: np.ndarray | None = None) -> None:
        self.rms_label.setText(f"{snap.rms_dbfs:.1f} dBFS")
        self.peak_label.setText(f"{snap.peak_dbfs:.1f} dBFS")
        self.level_meter.setValue(round(max(0.0, min(60.0, snap.rms_dbfs + 60))))
        if snap.pitch.frequency_hz is not None:
            self.pitch_label.setText(snap.pitch.note_name)
            self.pitch_detail.setText(f"{snap.pitch.frequency_hz:.1f} Hz  ·  {snap.pitch.cents_offset:+.1f} cents")
        else:
            self.pitch_label.setText("—")
            self.pitch_detail.setText("等待有效音高")
        self.window_label.setText(f"{snap.window_seconds:.1f} / 120 s")

        if snap.waveform_min and snap.waveform_max:
            x_w = np.arange(len(snap.waveform_min), dtype=np.float32)
            self._wave_max_curve.setData(x_w, np.asarray(snap.waveform_max, dtype=np.float32))
            self._wave_min_curve.setData(x_w, np.asarray(snap.waveform_min, dtype=np.float32))

        if snap.fft_freqs_hz and snap.fft_db:
            freqs = np.asarray(snap.fft_freqs_hz, dtype=np.float32)
            mask = freqs > 0
            self._fft_curve.setData(freqs[mask], np.asarray(snap.fft_db, dtype=np.float32)[mask])

        if snap.log_freqs_hz and len(snap.log_freqs_hz) == len(snap.log_spectrum_db):
            self._log_curve.setData(snap.log_freqs_hz, snap.log_spectrum_db)

        if spectrogram is not None and spectrogram.size > 0:
            self._spec_img.setImage(spectrogram, autoLevels=False, levels=(-90.0, -5.0))
