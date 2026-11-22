"""PyQtGraph real-time waveform, FFT spectrum, log-frequency spectrum, and bounded spectrogram UI."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import ANALYSIS_LAYOUTS, Appearance
from core.i18n import get_current_language, translate_text
from core.models import AnalysisSnapshot
from ui.appearance import apply_plot_appearance
from ui.help_badge import HelpBadge
from ui.acid_style import (
    AcidGraphicOverlay,
    TelemetryHeader,
    TelemetryPulseStrip,
    acid_colormap_lut,
    apply_acid_plot_theme,
    get_acid_palette,
)

ANALYSIS_VIEWS = {
    "monitor": (((0, 0, 1, 2), (2, 0, 1, 1), (2, 1, 1, 1), (1, 0, 1, 2)), (4, 3, 3), (1, 1, 0)),
    "frequency": (((0, 1, 1, 1), (0, 0, 2, 1), (1, 1, 1, 1), (2, 0, 1, 2)), (2, 3, 2), (3, 2, 0)),
    "history": (((1, 0, 1, 1), (1, 1, 1, 1), (1, 2, 1, 1), (0, 0, 1, 3)), (5, 3, 0), (1, 1, 1)),
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
        self._cached_wave_x: Optional[np.ndarray] = None
        self._cached_texts: dict[str, str] = {}
        self._last_level_val: int = -1
        self._default_spec_lut: Optional[np.ndarray] = None
        self._metric_overlays: list[AcidGraphicOverlay] = []

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(6)
        self._header = TelemetryHeader("AUDIO SPECTRUM // REALTIME", "实时频谱与波形分析")
        self._pulse_strip = TelemetryPulseStrip(bar_count=10)
        self._header.add_right_widget(self._pulse_strip)
        self.view_combo = QtWidgets.QComboBox()
        self.view_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.view_combo.setAccessibleName("实时分析布局")
        for key, name in ANALYSIS_LAYOUTS.items():
            self.view_combo.addItem(name, key)
        self._header.add_right_widget(self.view_combo)
        self._header.add_right_widget(
            HelpBadge(
                "实时分析布局与四大图表说明",
                "• <b>布局切换</b>：可随时在「实时监听 / 频率诊断 / 时频追踪」三种画布排布间切换；切换时保留全部波形曲线与已缩放的坐标范围。<br/>"
                "• <b>CH-01 实时波形</b>：展示最新音频块的最大/最小包络振幅，用于观察动态与过载。<br/>"
                "• <b>CH-02 FFT 频谱</b>：高分辨率对数频率轴频谱，便于定位基频与高次谐波峰值。<br/>"
                "• <b>CH-03 频带能量</b>：按人耳听感划分的对数频带能量分布（低频贝斯底鼓在左侧，高频齿音擦片在右侧）。<br/>"
                "• <b>CH-04 最近时频图</b>：滚动声谱瀑布图，直观追踪随时间变化的旋律线与共振峰轨迹。",
            )
        )
        root.addWidget(self._header)

        metrics = QtWidgets.QHBoxLayout()
        metrics.setSpacing(8)
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
        for eyebrow, caption, value, detail, stretch, rail, help_tip in (
            (
                "PITCH // F0",
                "主音高",
                self.pitch_label,
                self.pitch_detail,
                5,
                "primary",
                "采用 YIN / 自相关基频算法实时追踪当前最显著音高（显示音名、Hz 频率与音分偏差 cents）。",
            ),
            (
                "LEVEL // RMS",
                "平均电平 · RMS",
                self.rms_label,
                self.level_meter,
                4,
                "secondary",
                "RMS (均方根) 反映人耳主观感知的平均响度（单位 dBFS，0 dBFS 为满刻度）。",
            ),
            (
                "PEAK // dBFS",
                "峰值电平",
                self.peak_label,
                None,
                3,
                "secondary",
                "当前分析帧的瞬时最大采样振幅；若接近 0.0 dBFS 说明信号逼近数字削波。",
            ),
            (
                "RING // BUFFER",
                "历史缓冲",
                self.window_label,
                None,
                3,
                "primary",
                "固定 120 秒内存环形缓冲区已写入的有效音频时长（上限约 43.95 MiB 原始 PCM，绝不无限增长）。",
            ),
        ):
            card = self._metric_card(eyebrow, caption, value, detail, accent_rail=rail, help_tip=help_tip)
            ov = AcidGraphicOverlay(card, stencil="")
            ov.setVisible(False)
            self._metric_overlays.append(ov)
            metrics.addWidget(card, stretch)
        root.addLayout(metrics)
        self._plot_grid = QtWidgets.QGridLayout()
        self._plot_grid.setSpacing(8)
        root.addLayout(self._plot_grid, 1)

        # Row 1: Waveform
        self.wave_plot = pg.PlotWidget()
        self.wave_plot.setLabel("bottom", "包络点", **{"font-size": "9pt"})
        self.wave_plot.setBackground("#F8FAFC")
        self.wave_plot.setYRange(-1.05, 1.05)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.22)
        self._wave_max_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.2))
        self._wave_min_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.2))
        frequency_axis = _FftFrequencyAxis(orientation="bottom")
        self.fft_plot = pg.PlotWidget(axisItems={"bottom": frequency_axis})
        self.fft_plot.setBackground("#F8FAFC")
        self.fft_plot.setLabel("bottom", "频率 (Hz)", **{"font-size": "9pt"})
        self.fft_plot.setYRange(-105, 5)
        self.fft_plot.setLogMode(x=True, y=False)
        self.fft_plot.showGrid(x=True, y=True, alpha=0.22)
        self._fft_curve = self.fft_plot.plot(pen=pg.mkPen("#00A878", width=1.5))
        log_axis = _FftFrequencyAxis(orientation="bottom")
        self.log_plot = pg.PlotWidget(axisItems={"bottom": log_axis})
        self.log_plot.setBackground("#F8FAFC")
        self.log_plot.setLabel("bottom", "频率 (Hz)", **{"font-size": "9pt"})
        self.log_plot.setLogMode(x=True, y=False)
        self.log_plot.setYRange(-105, 5)
        self.log_plot.showGrid(x=True, y=True, alpha=0.22)
        self._log_curve = self.log_plot.plot(
            pen=pg.mkPen("#0284C7", width=1.8),
            fillLevel=-105,
            brush=(2, 132, 199, 34),
        )
        from core.config import AnalysisConfig

        n_bins = int(AnalysisConfig().log_freq_bins)
        self.spec_plot = pg.PlotWidget()
        self.spec_plot.setBackground("#F8FAFC")
        self.spec_plot.setLabel("bottom", "时间 (s)", **{"font-size": "9pt"})
        self.spec_plot.setLabel("left", "频率 (Hz)", **{"font-size": "9pt"})
        self.spec_plot.setYRange(0, n_bins, padding=0)
        bin_freqs = np.geomspace(27.5, 16000.0, n_bins)
        tick_freqs = (31.5, 63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)
        ticks = [
            (
                float(np.interp(np.log(f), np.log(bin_freqs), np.arange(n_bins))),
                f"{int(f // 1000)}k" if f >= 1000.0 else (f"{f:g}"),
            )
            for f in tick_freqs
        ]
        self.spec_plot.getAxis("left").setTicks([ticks])
        self._spec_img = pg.ImageItem()
        try:
            cmap = pg.colormap.get("inferno") if hasattr(pg, "colormap") else None
        except Exception:
            cmap = None
        if cmap is not None:
            self._default_spec_lut = cmap.getLookupTable(0.0, 1.0, 256)
        self._spec_img.setLookupTable(acid_colormap_lut("spectrogram", "light"))
        self.spec_plot.addItem(self._spec_img)
        self._plots = (self.wave_plot, self.fft_plot, self.log_plot, self.spec_plot)
        for p in self._plots:
            try:
                p.hideButtons()
            except Exception:
                pass
        from core.config import AnalysisConfig

        spec_hist_sec = int(AnalysisConfig().spectrum_history_seconds)
        self._chart_cards = tuple(
            self._chart_card(tag, name, unit, plot)
            for tag, name, unit, plot in zip(
                ("CH-01", "CH-02", "CH-03", "CH-04"),
                ("实时波形", "FFT 频谱", "频带能量", "最近时频图"),
                ("AMP", "dBFS", "LOG BANDS", f"{spec_hist_sec}S HISTORY"),
                self._plots,
            )
        )
        self.view_combo.currentIndexChanged.connect(self._arrange_plots)
        self._arrange_plots()

    def update_telemetry(
        self,
        *,
        energy: float = 0.0,
        climax: float = 0.0,
        strength: float = 0.70,
        reactive: bool = True,
        locked: bool = False,
        phase: float = 0.0,
    ) -> None:
        s_val = float(strength) / 100.0 if float(strength) > 1.0 else float(strength)
        self._pulse_strip.set_telemetry(
            energy=energy,
            climax=climax,
            strength=s_val,
            reactive=reactive,
            locked=locked,
            phase=phase,
        )

    def apply_theme(
        self,
        appearance: Appearance,
        *,
        system_is_dark: Optional[bool] = None,
        acid_variant: Optional[str] = None,
    ) -> None:
        if acid_variant in ("light", "dark"):
            p = get_acid_palette(acid_variant)
            self._pulse_strip.set_theme_color(p.accent)
            cross = QtGui.QColor(241, 242, 236, 55) if acid_variant == "dark" else QtGui.QColor(9, 13, 20, 45)
            stencil = QtGui.QColor(241, 242, 236, 14) if acid_variant == "dark" else QtGui.QColor(9, 13, 20, 11)
            checker = QtGui.QColor(206, 255, 24, 175) if acid_variant == "dark" else QtGui.QColor(0, 168, 120, 165)
            for ov in self._metric_overlays:
                ov.set_colors(cross, stencil, checker)
                ov.setVisible(True)
                ov.raise_()
            for plot in self._plots:
                apply_acid_plot_theme(plot, appearance, acid_variant)
            wave_pen = pg.mkPen(p.plot_wave, width=1.2)
            self._wave_max_curve.setPen(wave_pen)
            self._wave_min_curve.setPen(wave_pen)
            self._fft_curve.setPen(pg.mkPen(p.plot_fft, width=1.5))
            qc = QtGui.QColor(p.plot_log)
            self._log_curve.setPen(pg.mkPen(p.plot_log, width=1.8))
            self._log_curve.setBrush((qc.red(), qc.green(), qc.blue(), 34 if acid_variant == "light" else 42))
            self._spec_img.setLookupTable(acid_colormap_lut("spectrogram", acid_variant))
            return

        for ov in self._metric_overlays:
            ov.setVisible(False)

        mode = appearance.resolve_theme_mode(system_is_dark=system_is_dark)
        _bg, _fg, accent = appearance.effective_colors(system_is_dark=system_is_dark)
        self._pulse_strip.set_theme_color(accent)
        for plot in self._plots:
            apply_plot_appearance(plot, appearance, system_is_dark=system_is_dark)
        wave_pen = pg.mkPen(accent, width=1.2)
        self._wave_max_curve.setPen(wave_pen)
        self._wave_min_curve.setPen(wave_pen)
        fft_color = "#0D9488" if mode == "light" else "#2EC27E"
        self._fft_curve.setPen(pg.mkPen(fft_color, width=1.5))
        log_color = "#C2410C" if mode == "light" else "#F5A623"
        qc = QtGui.QColor(log_color)
        self._log_curve.setPen(pg.mkPen(log_color, width=1.8))
        self._log_curve.setBrush((qc.red(), qc.green(), qc.blue(), 38 if mode == "light" else 45))
        if self._default_spec_lut is not None:
            self._spec_img.setLookupTable(self._default_spec_lut)

    @staticmethod
    def _metric_card(
        eyebrow: str,
        caption: str,
        value,
        detail,
        *,
        accent_rail: str = "primary",
        help_tip: str = "",
    ):
        card = QtWidgets.QFrame()
        card.setObjectName("analysisMetric")
        card.setProperty("accentRail", accent_rail)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(11, 7, 11, 7)
        layout.setSpacing(2)
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        eb = QtWidgets.QLabel(eyebrow)
        eb.setObjectName("telemetryEyebrow")
        title = QtWidgets.QLabel(caption)
        title.setObjectName("analysisCaption")
        top_row.addWidget(eb)
        top_row.addWidget(title, 1)
        if help_tip:
            top_row.addWidget(HelpBadge(f"{eyebrow} · {caption}", help_tip))
        layout.addLayout(top_row)
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
        positions, rows, columns = ANALYSIS_VIEWS[self.view_combo.currentData()]
        for card, position in zip(self._chart_cards, positions):
            self._plot_grid.removeWidget(card)
            self._plot_grid.addWidget(card, *position)
        for index, weight in enumerate(rows):
            self._plot_grid.setRowStretch(index, weight)
        for index, weight in enumerate(columns):
            self._plot_grid.setColumnStretch(index, weight)

    @staticmethod
    def _chart_card(tag: str, name: str, unit: str, plot: pg.PlotWidget) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("analysisChart")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(2, 5, 2, 2)
        layout.setSpacing(3)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(8, 0, 8, 0)
        header.setSpacing(6)
        tag_lbl = QtWidgets.QLabel(tag)
        tag_lbl.setObjectName("telemetryEyebrow")
        title = QtWidgets.QLabel(name)
        title.setObjectName("analysisChartHeading")
        caption = QtWidgets.QLabel(unit)
        caption.setObjectName("telemetryPill")
        header.addWidget(tag_lbl)
        header.addWidget(title, 1)
        header.addWidget(caption)
        layout.addLayout(header)
        plot.setMinimumHeight(54)
        layout.addWidget(plot, 1)
        return card

    def _set_text_cached(self, key: str, lbl: QtWidgets.QLabel, text: str) -> None:
        lang = get_current_language()
        rendered = translate_text(text, lang) if text else text
        cache_val = f"{lang}:{rendered}"
        if self._cached_texts.get(key) != cache_val:
            self._cached_texts[key] = cache_val
            lbl.setProperty("_ls_orig_text", text)
            lbl.setText(rendered)

    def update_analysis(self, snap: AnalysisSnapshot, spectrogram: np.ndarray | None = None) -> None:
        self._set_text_cached("rms", self.rms_label, f"{snap.rms_dbfs:.1f} dBFS")
        self._set_text_cached("peak", self.peak_label, f"{snap.peak_dbfs:.1f} dBFS")
        lvl = round(max(0.0, min(60.0, snap.rms_dbfs + 60)))
        if lvl != self._last_level_val:
            self._last_level_val = lvl
            self.level_meter.setValue(lvl)
        if snap.pitch.frequency_hz is not None:
            self._set_text_cached("pitch", self.pitch_label, snap.pitch.note_name)
            self._set_text_cached(
                "pitch_det",
                self.pitch_detail,
                f"{snap.pitch.frequency_hz:.1f} Hz  ·  {snap.pitch.cents_offset:+.1f} cents",
            )
        else:
            self._set_text_cached("pitch", self.pitch_label, "—")
            self._set_text_cached("pitch_det", self.pitch_detail, "等待有效音高")
        self._set_text_cached("window", self.window_label, f"{snap.window_seconds:.1f} / 120 s")

        if snap.waveform_min and snap.waveform_max:
            n_w = len(snap.waveform_min)
            if self._cached_wave_x is None or len(self._cached_wave_x) != n_w:
                self._cached_wave_x = np.arange(n_w, dtype=np.float32)
            self._wave_max_curve.setData(self._cached_wave_x, np.asarray(snap.waveform_max, dtype=np.float32))
            self._wave_min_curve.setData(self._cached_wave_x, np.asarray(snap.waveform_min, dtype=np.float32))

        if snap.fft_freqs_hz and snap.fft_db:
            freqs = np.asarray(snap.fft_freqs_hz, dtype=np.float32)
            mask = freqs > 0
            self._fft_curve.setData(freqs[mask], np.asarray(snap.fft_db, dtype=np.float32)[mask])

        if snap.log_freqs_hz and len(snap.log_freqs_hz) == len(snap.log_spectrum_db):
            self._log_curve.setData(snap.log_freqs_hz, snap.log_spectrum_db)

        if spectrogram is not None and spectrogram.size > 0:
            self._spec_img.setImage(spectrogram, autoLevels=False, levels=(-90.0, -5.0))
            frames = int(spectrogram.shape[0])
            bins = int(spectrogram.shape[1]) if spectrogram.ndim > 1 else 96
            dur_s = max(1.0 / 15.0, frames / 15.0)
            self._spec_img.setRect(QtCore.QRectF(-dur_s, 0.0, dur_s, float(bins)))
