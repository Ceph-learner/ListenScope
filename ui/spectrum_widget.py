"""PyQtGraph real-time waveform, FFT spectrum, log-frequency spectrum, and bounded spectrogram UI."""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core.appearance import ANALYSIS_LAYOUTS, Appearance
from core.i18n import get_current_language, translate_text
from core.models import AnalysisSnapshot
from ui.appearance import apply_plot_appearance
from ui.frame_clock import Ballistics
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
    "monitor": (((0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)), (1, 1, 0), (1, 1, 0)),
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

    def tickValues(self, minVal, maxVal, size):
        if not self.logMode:
            return self.logTickValues(minVal, maxVal, size, [])
        return super().tickValues(minVal, maxVal, size)

    def tickStrings(self, values, scale, spacing):
        if not self.logMode:
            return self.logTickStrings(values, scale, spacing)
        return super().tickStrings(values, scale, spacing)

    def logTickStrings(self, values, scale, spacing):
        labels = []
        for tick in values:
            hz = 10**tick * scale
            labels.append(f"{hz / 1000:.4g}k" if hz >= 1000 else f"{hz:.4g}")
        return labels


class SpectrumAnalysisWidget(QtWidgets.QWidget):
    """Lightweight GPU/CPU-friendly PyQtGraph display consuming precomputed AnalysisSnapshot only."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        analysis_config: Optional["AnalysisConfig"] = None,
    ) -> None:
        super().__init__(parent)
        from core.config import AnalysisConfig

        cfg = analysis_config or AnalysisConfig()
        self._waveform_window_seconds: float = float(cfg.waveform_window_seconds)
        self._waveform_display_points: int = max(1, int(cfg.waveform_display_points))
        self._cached_wave_x: np.ndarray = np.linspace(
            -self._waveform_window_seconds, 0.0, self._waveform_display_points, dtype=np.float32
        )
        self._cached_fft_freqs: Optional[list[float]] = None
        self._fft_x: Optional[np.ndarray] = None
        self._fft_slope_offset: Optional[np.ndarray] = None
        self._fft_ballistics: Optional[Ballistics] = None
        self._last_text_t: float = 0.0
        self._clip_latched: bool = False
        self._cached_texts: dict[str, str] = {}
        self._last_level_val: int = -1
        self._default_spec_lut: Optional[np.ndarray] = None
        self._metric_overlays: list[AcidGraphicOverlay] = []
        self._compact_mode: bool = False
        self._eyebrow_labels: list[QtWidgets.QLabel] = []
        self._metric_cards: list[QtWidgets.QFrame] = []

        root = QtWidgets.QVBoxLayout(self)
        self._root_layout = root
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(6)
        self._header = TelemetryHeader("AUDIO SPECTRUM // REALTIME", "实时频谱与波形分析")
        self._pulse_strip = TelemetryPulseStrip(bar_count=10)
        self._header.add_right_widget(self._pulse_strip)
        self._slope_combo = QtWidgets.QComboBox()
        self._slope_combo.setToolTip("FFT 频谱倾斜补偿 (dB/oct)")
        for lbl, slp in (("0 dB/oct", 0.0), ("3 dB/oct", 3.0), ("4.5 dB/oct", 4.5)):
            self._slope_combo.addItem(lbl, slp)
        self._slope_combo.currentIndexChanged.connect(self._on_slope_changed)
        self._header.add_right_widget(self._slope_combo)
        self._clip_latch_btn = QtWidgets.QPushButton("CLIP")
        self._clip_latch_btn.setCheckable(True)
        self._clip_latch_btn.setEnabled(False)
        self._clip_latch_btn.setToolTip("峰值 > -0.3 dBFS 削波锁存灯（点击清除）")
        self._clip_latch_btn.clicked.connect(self._clear_clip_latch)
        self._header.add_right_widget(self._clip_latch_btn)
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
            self._metric_cards.append(card)
            ov = AcidGraphicOverlay(card, stencil="")
            ov.setVisible(False)
            self._metric_overlays.append(ov)
            metrics.addWidget(card, stretch)
        root.addLayout(metrics)
        self._plot_stack = QtWidgets.QStackedWidget()
        self._grid_page = QtWidgets.QWidget()
        self._plot_grid = QtWidgets.QGridLayout(self._grid_page)
        self._plot_grid.setContentsMargins(0, 0, 0, 0)
        self._plot_grid.setSpacing(8)
        self._plot_stack.addWidget(self._grid_page)

        self._compact_tabs = QtWidgets.QTabWidget()
        self._compact_tab1 = QtWidgets.QWidget()
        self._compact_tab1_l = QtWidgets.QHBoxLayout(self._compact_tab1)
        self._compact_tab1_l.setContentsMargins(0, 2, 0, 0)
        self._compact_tab1_l.setSpacing(6)
        self._compact_tab2 = QtWidgets.QWidget()
        self._compact_tab2_l = QtWidgets.QHBoxLayout(self._compact_tab2)
        self._compact_tab2_l.setContentsMargins(0, 2, 0, 0)
        self._compact_tab2_l.setSpacing(6)
        self._compact_tabs.addTab(self._compact_tab1, "波形与 FFT 频谱")
        self._compact_tabs.addTab(self._compact_tab2, "频带能量与声谱图")
        self._plot_stack.addWidget(self._compact_tabs)
        root.addWidget(self._plot_stack, 1)

        # Row 1: Waveform
        self._wave_auto_gain: bool = True
        self._wave_gain_scale: float = 1.0
        self.wave_plot = pg.PlotWidget()
        self.wave_plot.setLabel("bottom", "时间 (秒)", **{"font-size": "9pt"})
        self.wave_plot.setBackground("#F8FAFC")
        self.wave_plot.setYRange(-1.05, 1.05)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.22)
        self._wave_max_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.2))
        self._wave_min_curve = self.wave_plot.plot(pen=pg.mkPen("#0F766E", width=1.2))
        self._wave_fill = pg.FillBetweenItem(
            self._wave_min_curve,
            self._wave_max_curve,
            brush=pg.mkBrush(15, 118, 110, 72),
        )
        self.wave_plot.addItem(self._wave_fill)
        for wc in (self._wave_max_curve, self._wave_min_curve):
            wc.setClipToView(True)
            wc.setDownsampling(auto=True, method="peak")
        frequency_axis = _FftFrequencyAxis(orientation="bottom")
        self.fft_plot = pg.PlotWidget(axisItems={"bottom": frequency_axis})
        self.fft_plot.setBackground("#F8FAFC")
        self.fft_plot.setLabel("bottom", "频率 (Hz)", **{"font-size": "9pt"})
        self.fft_plot.setYRange(-105, 5)
        self.fft_plot.setLogMode(x=False, y=False)
        self.fft_plot.showGrid(x=True, y=True, alpha=0.22)
        self._fft_curve = self.fft_plot.plot(pen=pg.mkPen("#00A878", width=1.5))
        self._fft_peak_curve = self.fft_plot.plot(
            pen=pg.mkPen("#F59E0B", width=1.0, style=QtCore.Qt.PenStyle.DashLine)
        )
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
        self._spec_n_bins = n_bins
        self._spec_bin_freqs = np.geomspace(27.5, 16000.0, n_bins)
        self._refresh_axis_ticks()
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
        self._wave_gain_btn = QtWidgets.QPushButton("自动增益")
        self._wave_gain_btn.setObjectName("miniToolbarBtn")
        self._wave_gain_btn.setCheckable(True)
        self._wave_gain_btn.setChecked(True)
        self._wave_gain_btn.setAutoDefault(False)
        self._wave_gain_btn.setMaximumHeight(18)
        self._wave_gain_btn.setStyleSheet("QPushButton { padding: 0px 6px; min-height: 16px; max-height: 18px; font-size: 9px; }")
        self._wave_gain_btn.setToolTip("切换波形自动增益与固定 ±1 振幅范围")
        self._wave_gain_btn.toggled.connect(self.set_wave_auto_gain)

        self._chart_cards = tuple(
            self._chart_card(
                tag,
                name,
                unit,
                plot,
                extra_widget=(self._wave_gain_btn if tag == "CH-01" else None),
            )
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
            wqc = QtGui.QColor(p.plot_wave)
            self._wave_fill.setBrush(pg.mkBrush(wqc.red(), wqc.green(), wqc.blue(), 64 if acid_variant == "light" else 76))
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
        wqc = QtGui.QColor(accent)
        self._wave_fill.setBrush(pg.mkBrush(wqc.red(), wqc.green(), wqc.blue(), 64 if mode == "light" else 76))
        fft_color = "#0D9488" if mode == "light" else "#2EC27E"
        self._fft_curve.setPen(pg.mkPen(fft_color, width=1.5))
        log_color = "#C2410C" if mode == "light" else "#F5A623"
        qc = QtGui.QColor(log_color)
        self._log_curve.setPen(pg.mkPen(log_color, width=1.8))
        self._log_curve.setBrush((qc.red(), qc.green(), qc.blue(), 38 if mode == "light" else 45))
        if self._default_spec_lut is not None:
            self._spec_img.setLookupTable(self._default_spec_lut)

    def _metric_card(
        self,
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
        self._eyebrow_labels.append(eb)
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

    def set_compact_mode(self, compact: bool, *, compact_cards: Optional[bool] = None) -> None:
        compact = bool(compact)
        cards_compact = compact if compact_cards is None else bool(compact_cards)
        if self._compact_mode == compact and getattr(self, "_cards_compact", None) == cards_compact:
            return
        self._compact_mode = compact
        self._cards_compact = cards_compact
        if cards_compact:
            self._root_layout.setContentsMargins(6, 0, 6, 0)
            self._root_layout.setSpacing(2)
            self._plot_grid.setSpacing(4)
            self._header.setMaximumHeight(16777215)
        else:
            self._root_layout.setContentsMargins(10, 6, 10, 8)
            self._root_layout.setSpacing(6)
            self._plot_grid.setSpacing(8)
            self._header.setMaximumHeight(16777215)
        for eb in self._eyebrow_labels:
            eb.setVisible(not cards_compact)
        self.pitch_detail.setVisible(not cards_compact)
        self.level_meter.setVisible(not cards_compact)
        for card in self._metric_cards:
            card.setMaximumHeight(36 if cards_compact else 16777215)
            lay = card.layout()
            if lay is not None:
                lay.setContentsMargins(8 if cards_compact else 11, 1 if cards_compact else 7, 8 if cards_compact else 11, 1 if cards_compact else 7)
                lay.setSpacing(0 if cards_compact else 2)
        self._arrange_plots()
        self._refresh_axis_ticks()

    def _refresh_axis_ticks(self) -> None:
        """Adapt spectrogram and FFT Y-axis ticks to available pixel height (>= 1.6x font height)."""
        font_h = max(10.0, float(self.fontMetrics().height()))
        min_px_gap = 1.6 * font_h

        # 1. Spectrogram left axis (frequency bins)
        spec_h = float(max(40, self.spec_plot.height() - 28))
        n_bins = max(2, int(getattr(self, "_spec_n_bins", 96)))
        bin_freqs = getattr(self, "_spec_bin_freqs", np.geomspace(27.5, 16000.0, n_bins))
        tick_freqs = (31.5, 63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0)
        kept_spec: list[tuple[float, str]] = []
        last_px: Optional[float] = None
        for f in tick_freqs:
            y_val = float(np.interp(np.log(f), np.log(bin_freqs), np.arange(n_bins)))
            px_y = (y_val / float(n_bins - 1)) * spec_h
            if last_px is None or (px_y - last_px) >= min_px_gap:
                lbl = f"{int(f // 1000)}k" if f >= 1000.0 else f"{f:g}"
                kept_spec.append((y_val, lbl))
                last_px = px_y
        self.spec_plot.getAxis("left").setTicks([kept_spec])
        self.spec_plot.setLabel("left", "" if spec_h < 90.0 else "频率 (Hz)", **{"font-size": "9pt"})

        # 2. FFT & Log-band Y-axis (-105..5 dBFS) and redundant bottom titles on tight height
        db_candidates = (-100.0, -80.0, -60.0, -40.0, -20.0, 0.0)
        for plot in (self.fft_plot, self.log_plot):
            ph = float(max(40, plot.height() - 28))
            kept_db: list[tuple[float, str]] = []
            prev_db_px: Optional[float] = None
            for db in db_candidates:
                px_y = ((db - (-105.0)) / 110.0) * ph
                if prev_db_px is None or (px_y - prev_db_px) >= min_px_gap:
                    kept_db.append((db, f"{int(db)}"))
                    prev_db_px = px_y
            plot.getAxis("left").setTicks([kept_db])
        for plot, orig_bottom in (
            (self.wave_plot, "时间 (秒)"),
            (self.fft_plot, "频率 (Hz)"),
            (self.log_plot, "频率 (Hz)"),
            (self.spec_plot, "时间 (s)"),
        ):
            plot.setLabel("bottom", "" if plot.height() < 150 else orig_bottom, **{"font-size": "9pt"})

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        win = self.window()
        if win is not None and win is not self:
            compact = win.height() < 760 or (win.isVisible() and self.height() < 360)
        else:
            compact = self.height() < 360
        cards_compact = compact or (self.height() < 460)
        self.set_compact_mode(compact, compact_cards=cards_compact)
        self._header.setVisible(self.height() >= 255)
        self._refresh_axis_ticks()

    def _arrange_plots(self) -> None:
        for card in self._chart_cards:
            self._plot_grid.removeWidget(card)
            self._compact_tab1_l.removeWidget(card)
            self._compact_tab2_l.removeWidget(card)

        if self._compact_mode:
            self._compact_tab1_l.addWidget(self._chart_cards[0], 1)
            self._compact_tab1_l.addWidget(self._chart_cards[1], 1)
            self._compact_tab2_l.addWidget(self._chart_cards[2], 1)
            self._compact_tab2_l.addWidget(self._chart_cards[3], 1)
            self._plot_stack.setCurrentWidget(self._compact_tabs)
            return

        self._plot_stack.setCurrentWidget(self._grid_page)
        view_key = self.view_combo.currentData()
        positions, rows, columns = ANALYSIS_VIEWS[view_key]
        for card, position in zip(self._chart_cards, positions):
            self._plot_grid.addWidget(card, *position)
        for index, weight in enumerate(rows):
            self._plot_grid.setRowStretch(index, weight)
        for index, weight in enumerate(columns):
            self._plot_grid.setColumnStretch(index, weight)

    @staticmethod
    def _chart_card(
        tag: str,
        name: str,
        unit: str,
        plot: pg.PlotWidget,
        *,
        extra_widget: Optional[QtWidgets.QWidget] = None,
    ) -> QtWidgets.QFrame:
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
        if extra_widget is not None:
            header.addWidget(extra_widget)
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

    def _on_slope_changed(self) -> None:
        self._fft_slope_offset = None

    def _clear_clip_latch(self) -> None:
        self._clip_latched = False
        self._clip_latch_btn.setChecked(False)
        self._clip_latch_btn.setEnabled(False)

    def advance_frame(self, dt: float) -> None:
        if self._fft_ballistics is not None and self._fft_x is not None:
            cur, pk = self._fft_ballistics.step(dt)
            self._fft_curve.setData(self._fft_x, cur, skipFiniteCheck=True)
            self._fft_peak_curve.setData(self._fft_x, pk, skipFiniteCheck=True)

    def set_wave_auto_gain(self, enabled: bool) -> None:
        self._wave_auto_gain = bool(enabled)
        if hasattr(self, "_wave_gain_btn"):
            self._wave_gain_btn.blockSignals(True)
            self._wave_gain_btn.setChecked(self._wave_auto_gain)
            set_i18n_text(self._wave_gain_btn, "自动增益" if self._wave_auto_gain else "固定 ±1")
            self._wave_gain_btn.blockSignals(False)
        if not self._wave_auto_gain:
            self._wave_gain_scale = 1.05
            self.wave_plot.setYRange(-1.05, 1.05, padding=0)

    def _apply_waveform_auto_gain(self, w_min: np.ndarray, w_max: np.ndarray) -> None:
        if not self._wave_auto_gain:
            return
        if w_min.size == 0 or w_max.size == 0:
            return
        peak = max(float(np.max(np.abs(w_min))), float(np.max(np.abs(w_max))))
        target = max(0.1, min(1.05, 1.2 * peak))
        alpha = 0.5 if target > self._wave_gain_scale else 0.2
        self._wave_gain_scale = (1.0 - alpha) * self._wave_gain_scale + alpha * target
        self.wave_plot.setYRange(-self._wave_gain_scale, self._wave_gain_scale, padding=0)

    def update_snapshot(self, snap: AnalysisSnapshot, spectrogram: np.ndarray | None = None) -> None:
        self.update_analysis(snap, spectrogram)

    def update_analysis(self, snap: AnalysisSnapshot, spectrogram: np.ndarray | None = None) -> None:
        if snap.peak_dbfs > -0.3 and not self._clip_latched:
            self._clip_latched = True
            self._clip_latch_btn.setEnabled(True)
            self._clip_latch_btn.setChecked(True)

        now = time.monotonic()
        if now - self._last_text_t >= 0.18:
            self._last_text_t = now
            self._set_text_cached("rms", self.rms_label, f"{snap.rms_dbfs:.1f} dBFS")
            self._set_text_cached("peak", self.peak_label, f"{snap.peak_dbfs:.1f} dBFS")

        lvl = round(max(0.0, min(60.0, snap.rms_dbfs + 60)))
        if lvl != self._last_level_val:
            self._last_level_val = lvl
            self.level_meter.setValue(lvl)
        if snap.pitch.frequency_hz is not None:
            if getattr(snap.pitch, "source_band", "full") == "bass":
                self._set_text_cached(
                    "pitch",
                    self.pitch_label,
                    f"低音 {snap.pitch.note_name} {snap.pitch.cents_offset:+.0f}c",
                )
                self._set_text_cached(
                    "pitch_det",
                    self.pitch_detail,
                    f"多声部 · 显示低音 ({snap.pitch.frequency_hz:.1f} Hz)",
                )
            else:
                self._set_text_cached("pitch", self.pitch_label, snap.pitch.note_name or "—")
                self._set_text_cached(
                    "pitch_det",
                    self.pitch_detail,
                    f"{snap.pitch.frequency_hz:.1f} Hz  ·  {snap.pitch.cents_offset:+.1f} cents",
                )
        elif getattr(snap.pitch, "is_polyphonic", False):
            self._set_text_cached("pitch", self.pitch_label, "多声部")
            self._set_text_cached("pitch_det", self.pitch_detail, "多声部音频，无单一主音")
        else:
            self._set_text_cached("pitch", self.pitch_label, "—")
            self._set_text_cached("pitch_det", self.pitch_detail, "等待有效音高")
        self._set_text_cached("window", self.window_label, f"{snap.window_seconds:.1f} / 120 s")

        if snap.waveform_min and snap.waveform_max:
            n_w = len(snap.waveform_min)
            if self._cached_wave_x.shape[0] != n_w:
                self._cached_wave_x = np.linspace(-self._waveform_window_seconds, 0.0, n_w, dtype=np.float32)
            w_max = np.asarray(snap.waveform_max, dtype=np.float32)
            w_min = np.asarray(snap.waveform_min, dtype=np.float32)
            self._apply_waveform_auto_gain(w_min, w_max)
            self._wave_max_curve.setData(self._cached_wave_x, w_max, skipFiniteCheck=True)
            self._wave_min_curve.setData(self._cached_wave_x, w_min, skipFiniteCheck=True)

        if snap.fft_freqs_hz and snap.fft_db:
            if self._cached_fft_freqs is not snap.fft_freqs_hz and self._cached_fft_freqs != snap.fft_freqs_hz:
                freqs = np.asarray(snap.fft_freqs_hz, dtype=np.float32)
                valid = freqs > 0
                self._cached_fft_freqs = snap.fft_freqs_hz
                self._fft_valid_mask = valid
                self._fft_x = np.log10(freqs[valid]).astype(np.float32)
                self._fft_slope_offset = None
                self._fft_ballistics = Ballistics(
                    int(self._fft_x.shape[0]),
                    floor_val=-120.0,
                    release_rate=20.0,
                    hold_sec=1.5,
                    peak_fall_rate=12.0,
                    mode="db",
                )
            fft_y = np.asarray(snap.fft_db, dtype=np.float32)
            if self._fft_x is not None and fft_y.shape[0] == self._fft_valid_mask.shape[0]:
                y_sel = fft_y[self._fft_valid_mask] if not np.all(self._fft_valid_mask) else fft_y
                slope = float(self._slope_combo.currentData() or 0.0)
                if slope > 0.0:
                    if self._fft_slope_offset is None:
                        octaves = (self._fft_x - float(np.log10(1000.0))) / math.log10(2.0)
                        self._fft_slope_offset = (octaves * slope).astype(np.float32)
                    y_sel = y_sel + self._fft_slope_offset
                if self._fft_ballistics is not None:
                    self._fft_ballistics.set_target(y_sel)
                self._fft_curve.setData(self._fft_x, y_sel, skipFiniteCheck=True)

        if snap.log_freqs_hz and len(snap.log_freqs_hz) == len(snap.log_spectrum_db):
            self._log_curve.setData(snap.log_freqs_hz, snap.log_spectrum_db, skipFiniteCheck=True)

        if spectrogram is not None and spectrogram.size > 0:
            self._spec_img.setImage(spectrogram, autoLevels=False, levels=(-90.0, -5.0))
            frames = int(spectrogram.shape[0])
            bins = int(spectrogram.shape[1]) if spectrogram.ndim > 1 else 96
            dur_s = max(1.0 / 15.0, frames / 15.0)
            self._spec_img.setRect(QtCore.QRectF(-dur_s, 0.0, dur_s, float(bins)))
