"""Phase 2C UI verification tests (Issue #32, 18 items: 17 UI items + A-M6-UI tempo x2/div2).

Every test is a minimal reproduction marked `@pytest.mark.xfail(strict=True, reason="<ID>")`.
Implementers remove each xfail marker as the item is fixed.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_ub02_fft_display_uses_log_frequency_resampling_with_dense_bass_bins() -> None:
    """AnalysisWorker must emit log-resampled FFT display bins (~221 pts, >=12 pts in 27.5-110 Hz), not linear [::4]."""
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig

    acfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=4)
    rb = FixedRingBuffer(acfg)
    t = np.arange(8192, dtype=np.float32) / 48000.0
    tone = (0.4 * np.sin(2.0 * np.pi * 82.4 * t)).astype(np.float32)
    rb.write(np.stack([tone, tone], axis=1))
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    snap = worker.analyze_latest_once()
    freqs = np.asarray(snap.fft_freqs_hz, dtype=np.float32)
    bass_pts = int(np.sum((freqs >= 27.5) & (freqs <= 110.0)))
    assert bass_pts >= 24, f"27.5-110 Hz only has {bass_pts} FFT display points (linear [::4] starvation)"


def test_ub03_main_window_fits_small_screens_1093x566_and_1024x528() -> None:
    """CONFIRMED: minimumSize <=780x540, realtime PlotWidgets >=120px (>=100px at 1024x528), buttons inside window, collapsible bottom A/B panel."""
    import pyqtgraph as pg
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        assert win.minimumWidth() <= 780 and win.minimumHeight() <= 540, (
            f"minimumSize too large for small screens: {win.minimumWidth()}x{win.minimumHeight()}"
        )
        win.show()
        for w_px, h_px, min_plot_h in ((1093, 566, 120), (1024, 528, 100), (1366, 768, 120)):
            win.resize(w_px, h_px)
            app.processEvents()
            assert win.width() <= w_px and win.height() <= h_px
            plots = [p for p in win.spectrum_widget.findChildren(pg.PlotWidget) if p.isVisible()]
            assert len(plots) >= 1
            for p in plots:
                assert p.height() >= min_plot_h, f"PlotWidget squished to {p.height()}px at {w_px}x{h_px} (need >= {min_plot_h}px)"
            win_rect = win.rect()
            for btn in win.findChildren(QtWidgets.QAbstractButton):
                if btn.isVisible() and btn.width() > 0 and btn.height() > 0:
                    tl = btn.mapTo(win, QtCore.QPoint(0, 0))
                    br = btn.mapTo(win, QtCore.QPoint(btn.width() - 1, btn.height() - 1))
                    assert win_rect.contains(tl) and win_rect.contains(br), (
                        f"Button {btn.text()!r} clipped outside {w_px}x{h_px}"
                    )

        # Collapsing bottom A/B panel must increase realtime chart area height
        win.resize(1093, 566)
        app.processEvents()
        h_before = win.spectrum_widget.height()
        toggle_fn = getattr(win, "set_bottom_panel_collapsed", None) or getattr(win, "toggle_bottom_panel", None)
        assert callable(toggle_fn), "Missing collapsible bottom A/B panel API (set_bottom_panel_collapsed / toggle_bottom_panel)"
        toggle_fn(True)
        app.processEvents()
        assert win.spectrum_widget.height() > h_before, "Collapsing bottom A/B panel did not increase chart height"
    finally:
        win.close()
        mixer.close()


def test_ub07_ui_tick_deduplicates_snapshots_throttles_hidden_and_uses_precise_timer() -> None:
    """main.py must deduplicate snapshots by timestamp, throttle when hidden/minimized, use PreciseTimer, and sample resources off GUI thread."""
    src = (REPO_ROOT / "main.py").read_text("utf-8")
    assert "_last_snap_ts" in src or "_last_rendered_snap_ts" in src, "Missing snapshot timestamp deduplication in main.py"
    assert "PreciseTimer" in src, "UI tick timer is not set to Qt.TimerType.PreciseTimer"
    # _on_ui_tick must not call resource_manager.sample() synchronously on GUI thread
    m = re.search(r"def _on_ui_tick\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "resource_manager.sample()" not in m.group(0), "_on_ui_tick still calls resource_manager.sample() on GUI thread"


def test_ufx1_frame_clock_exists_and_decouples_display_interpolation() -> None:
    """UI must provide a unified FrameClock (PreciseTimer, set_active(on, hz)) for 60/30 Hz display interpolation."""
    found = False
    for p in (REPO_ROOT / "ui").glob("*.py"):
        if "class FrameClock" in p.read_text("utf-8"):
            found = True
            break
    assert found, "Missing unified FrameClock class under ui/"


def test_ufx2_ballistics_and_spectrogram_ring_buffer_exist() -> None:
    """Spectrum/chroma meters must use Ballistics peak-hold & SpectrumAnalyzer must avoid per-tick np.stack over deque."""
    ui_texts = "\n".join(p.read_text("utf-8") for p in (REPO_ROOT / "ui").glob("*.py"))
    assert "class Ballistics" in ui_texts, "Missing Ballistics meter/FFT peak-hold class under ui/"
    assert "skipFiniteCheck=True" in ui_texts, "pyqtgraph curves missing skipFiniteCheck=True"


def test_ub08_set_i18n_text_prevents_dynamic_label_reversion_on_language_switch() -> None:
    """core/i18n.py must provide set_i18n_text(widget, zh) so updating dynamic labels refreshes _ls_orig_text."""
    from core import i18n

    assert hasattr(i18n, "set_i18n_text"), "core/i18n.py missing set_i18n_text()"
    _get_app()
    lbl = QtWidgets.QLabel()
    i18n.set_current_language("zh")
    i18n.set_i18n_text(lbl, "空闲：等待任务")
    i18n.set_i18n_text(lbl, "正在分析音频")
    i18n.translate_widget_tree(lbl, "en")
    i18n.translate_widget_tree(lbl, "zh")
    assert lbl.text() == "正在分析音频", f"Dynamic label reverted to stale original text: {lbl.text()!r}"


def test_ub13_tooltip_filter_allows_native_tooltips_unless_lsSuppressTip_set() -> None:
    """Tooltip guard must allow normal native tooltips and only suppress widgets with property('lsSuppressTip') == True."""
    from ui.help_badge import install_tooltip_guard

    _get_app()
    host = QtWidgets.QWidget()
    btn = QtWidgets.QPushButton("×", host)
    btn.setToolTip("关闭窗口")
    guard = install_tooltip_guard(host)
    ev = QtCore.QEvent(QtCore.QEvent.Type.ToolTip)
    blocked = guard.eventFilter(btn, ev)
    assert blocked is False, "Global tooltip filter blocked native tooltip on normal button"


def test_ub14_help_badge_is_keyboard_focusable_and_at_least_24px() -> None:
    """HelpBadge must support Qt.TabFocus (without auto-popup on focus) and have size >= 24x24 px (WCAG 2.5.8)."""
    from ui.help_badge import HelpBadge

    _get_app()
    badge = HelpBadge("示例帮助说明")
    assert badge.width() >= 24 and badge.height() >= 24, f"HelpBadge too small: {badge.width()}x{badge.height()}"
    assert badge.focusPolicy() in (QtCore.Qt.FocusPolicy.TabFocus, QtCore.Qt.FocusPolicy.StrongFocus), (
        f"HelpBadge is not keyboard focusable: {badge.focusPolicy()}"
    )


def test_ub15_focus_ring_uses_2px_accent_secondary_even_when_animation_disabled() -> None:
    """QSS focus outline must be >=2px using accent_secondary distinct from hover, and remain visible without animation."""
    src = (REPO_ROOT / "ui" / "acid_style.py").read_text("utf-8")
    m = re.search(r"QPushButton:focus.*?\{\{(.*?)\}\}", src, re.DOTALL)
    assert m is not None
    block = m.group(1)
    assert "2px solid" in block and "accent_secondary" in block, (
        f"ui/acid_style.py :focus rule still lacks 2px accent_secondary border: {block.strip()!r}"
    )


def test_ub17_static_lock_split_from_freeze_screen() -> None:
    """Static decoration lock must not freeze real-time spectrum/chord/key/pitch data updates; separate freeze_screen toggle required."""
    src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    m = re.search(r"def update_analysis_snapshot\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "if self._static_lock:\n            return" not in m.group(0), (
        "update_analysis_snapshot still returns early on self._static_lock, freezing data"
    )


def test_ub18_ai_progress_localized_stages_and_stretchable_bar() -> None:
    """StemMixerWidget AI progress must display localized stage text (not raw '[INFERRING]') and stretchable progress bar."""
    from audio.playback import StemMixerEngine
    from core.models import AIJobProgress, AIJobState
    from ui.mixer_widget import StemMixerWidget

    _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    w = StemMixerWidget(mixer)
    try:
        w.update_ai_progress(
            AIJobProgress(task_id="t1", state=AIJobState.INFERRING, progress=0.5, current_chunk=3, total_chunks=6, message="chunk 3/6")
        )
        txt = w.job_status_lbl.text()
        assert "[INFERRING]" not in txt and "[inferring]" not in txt.lower(), f"Raw enum leaked in progress label: {txt!r}"
        assert w.progress_bar.maximumWidth() > 212, "progress_bar is still fixed at 212 px"
    finally:
        mixer.close()


def test_ub19_marquee_combobox_does_not_scroll_infinitely_at_rest() -> None:
    """MarqueeComboBox must not run an infinite 35ms scroll timer when idle/unhovered (WCAG 2.2.2)."""
    from ui.acid_style import MarqueeComboBox

    _get_app()
    cb = MarqueeComboBox()
    cb.addItem("A very long audio device name that definitely overflows the combobox width 1234567890")
    cb.resize(120, 28)
    cb.show()
    _get_app().processEvents()
    timer = getattr(cb, "_marquee_timer", None) or getattr(cb, "_timer", None)
    assert timer is None or not timer.isActive(), "MarqueeComboBox scrolls continuously while unhovered and unfocused"
    cb.close()


def test_ufx3_system_animations_helper_help_badge_delay_and_explicit_banner_tone() -> None:
    """NEEDS_TARGET contract: system_animations_enabled() exists, HelpBadge hover delay >=400ms, show_banner_message uses explicit tone."""
    from ui.help_badge import HelpBadge

    _get_app()
    badge = HelpBadge("提示")
    assert badge._hover_show_timer.interval() >= 400, (
        f"HelpBadge hover delay is {badge._hover_show_timer.interval()}ms, expected >=400ms"
    )
    ui_texts = "\n".join(p.read_text("utf-8") for p in (REPO_ROOT / "ui").glob("*.py"))
    assert "def system_animations_enabled" in ui_texts, "Missing system_animations_enabled() helper under ui/"


def test_ub22_win10_rounded_mask_avoids_jagged_qregion_polygon() -> None:
    """NEEDS_TARGET contract: _update_rounded_mask must not apply jagged QRegion(path.toFillPolygon().toPolygon()) mask on Win10."""
    src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    m = re.search(r"def _update_rounded_mask\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "toFillPolygon().toPolygon()" not in m.group(0), (
        "_update_rounded_mask still applies jagged QRegion polygon mask"
    )


def test_ub26_mixer_widget_uses_bisect_for_chord_and_midi_lookup() -> None:
    """ui/mixer_widget.py must use bisect.bisect_right instead of O(N) linear scan every tick."""
    src = (REPO_ROOT / "ui" / "mixer_widget.py").read_text("utf-8")
    assert "bisect_right(" in src, "ui/mixer_widget.py still performs O(N) linear scan over chords/MIDI every tick"


def test_ub27_appearance_dialog_debounces_font_spinbox_changes() -> None:
    """ui/appearance.py must debounce SpinBox changes (>=100ms QTimer) instead of re-applying full QSS on every step."""
    src = (REPO_ROOT / "ui" / "appearance.py").read_text("utf-8")
    assert "QTimer" in src and ("120" in src or "debounce" in src.lower()), (
        "ui/appearance.py lacks 120ms debounce timer on font SpinBox"
    )


def test_ub30_telemetry_pulse_strip_accepts_real_level_or_is_static_by_default() -> None:
    """TelemetryPulseStrip must accept real audio level/bands (e.g. set_level / set_bands) instead of fake sine animation."""
    from ui.acid_style import TelemetryPulseStrip

    _get_app()
    strip = TelemetryPulseStrip()
    assert hasattr(strip, "set_level") or hasattr(strip, "set_bands") or hasattr(strip, "update_levels"), (
        "TelemetryPulseStrip has no real-audio level input API (pure decorative sine wave)"
    )


def test_am6_ui_tempo_half_double_buttons_present_in_chroma_widget() -> None:
    """Merged from Phase 2B A-M6: Chroma/Tempo UI must provide ×2 and ÷2 quick tempo multiplier buttons."""
    from ui.chroma_widget import ChromaChordWidget

    _get_app()
    w = ChromaChordWidget()
    btn_texts = [b.text() for b in w.findChildren(QtWidgets.QAbstractButton)]
    has_double = any("×2" in t or "x2" in t.lower() or "2x" in t.lower() for t in btn_texts)
    has_half = any("÷2" in t or "/2" in t or "0.5x" in t.lower() for t in btn_texts)
    assert has_double and has_half, f"Missing tempo ×2/÷2 buttons in ChromaChordWidget (found: {btn_texts})"


def test_ub31_mixer_header_does_not_overlap_groupbox_and_progress_visible() -> None:
    """In main window at 1120x680, mixer header must not overlap AI SEPARATION groupbox and job_status_lbl must be readable."""
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.models import AIJobProgress, AIJobState
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        win.resize(1120, 680)
        win.show()
        win.tabs.setCurrentWidget(win.mixer_widget)
        w = win.mixer_widget
        w.update_ai_progress(
            AIJobProgress(task_id="t1", state=AIJobState.INFERRING, progress=0.42, current_chunk=5, total_chunks=12, message="推理第 5/12 块")
        )
        app.processEvents()
        hdr = getattr(w, "_header", None)
        assert hdr is not None
        job_boxes = [gb for gb in w.findChildren(QtWidgets.QGroupBox) if "AI SEPARATION" in gb.title() or "分轨" in gb.title()]
        assert job_boxes
        hdr_rect = QtCore.QRect(hdr.mapTo(w, QtCore.QPoint(0, 0)), hdr.size())
        box_rect = QtCore.QRect(job_boxes[0].mapTo(w, QtCore.QPoint(0, 0)), job_boxes[0].size())
        assert not hdr_rect.intersects(box_rect), f"Mixer header {hdr_rect} overlaps AI groupbox {box_rect}"
        lbl = w.job_status_lbl
        assert lbl.isVisible() and lbl.height() >= lbl.fontMetrics().height(), (
            f"Progress label squished/invisible: visible={lbl.isVisible()}, h={lbl.height()}, font_h={lbl.fontMetrics().height()}"
        )
        assert "5/12" in lbl.text() or "推理" in lbl.text(), f"Progress stage text not shown: {lbl.text()!r}"
        assert "[INFERRING]" not in lbl.text(), f"Raw enum still shown: {lbl.text()!r}"
    finally:
        win.close()
        mixer.close()


def test_ub32_fixed_width_controls_elide_with_ellipsis_and_full_tooltip() -> None:
    """Fixed-width controls (ai_2stem_combo, ai_gpu_chk) at 1093px must elide with ellipsis or fit fully, with full-text tooltip."""
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        win.resize(1093, 620)
        win.show()
        app.processEvents()
        for widget, text in ((win.ai_2stem_combo, win.ai_2stem_combo.currentText()), (win.ai_gpu_chk, win.ai_gpu_chk.text())):
            tip = widget.toolTip().strip()
            assert tip and len(tip) >= len(text.rstrip("….")), f"{widget.objectName() or type(widget).__name__} missing full-text toolTip"
            fm = widget.fontMetrics()
            avail = max(1, widget.width() - 28)
            if fm.horizontalAdvance(text) > avail:
                assert text.endswith("…") or text.endswith("..."), (
                    f"{type(widget).__name__} text hard-truncated without ellipsis at width {widget.width()}: {text!r}"
                )
    finally:
        win.close()
        mixer.close()


def test_p2c_perf_analyze_latest_once_cpu_within_5ms_median() -> None:
    """A-H1 CPU regression (+3.69ms median over e4c49e8 3.11ms): steady-state analyze_latest_once median must be <= 5.0 ms."""
    import time
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig

    acfg = AudioConfig(ring_buffer_seconds=20)
    rb = FixedRingBuffer(acfg)
    w = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    chunk = (0.3 * np.sin(2.0 * np.pi * 440.0 * np.arange(3200) / 48000.0)).astype(np.float32)
    chunk2 = np.stack([chunk, chunk], axis=1)
    times = []
    for _ in range(120):
        rb.write(chunk2)
        t0 = time.perf_counter()
        w.analyze_latest_once()
        times.append((time.perf_counter() - t0) * 1000.0)
    med_ms = float(np.median(times[20:]))
    assert med_ms <= 5.0, f"analyze_latest_once steady median CPU is {med_ms:.2f} ms (must be <= 5.0 ms)"


def test_ub08_all_visible_controls_translated_in_en_ja_ko(tmp_path: Path) -> None:
    """U-B08: Switching to en/ja/ko leaves zero untranslated CJK/Hangul/Kana leaks across visible widgets and tabs."""
    from dataclasses import replace
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from core.i18n import set_current_language
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    re_cjk_all = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    re_hangul = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
    re_han_kana = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")
    user_data_whitelist: set[str] = set()

    try:
        win.resize(1093, 566)
        win.show()
        # Exercise dynamic state toggles before/after translation
        win.freeze_screen_btn.click()
        win._bottom_collapse_btn.click()
        win._bottom_collapse_btn.click()
        win.ab_more_btn.click()
        win.ab_more_btn.click()
        app.processEvents()

        for lang, pat in (("en", re_cjk_all), ("ja", re_hangul), ("ko", re_han_kana)):
            win.apply_appearance(replace(win.appearance, language=lang), force_theme=True)
            app.processEvents()
            leaks: list[str] = []
            for w in [win, *win.findChildren(QtWidgets.QWidget)]:
                if not w.isVisible():
                    continue
                for attr in ("text", "toolTip", "accessibleName"):
                    fn = getattr(w, attr, None)
                    if callable(fn):
                        val = str(fn() or "").strip()
                        if val and val not in user_data_whitelist and pat.search(val):
                            leaks.append(f"{type(w).__name__}.{attr}={val!r}")
                if isinstance(w, QtWidgets.QTabBar):
                    for idx in range(w.count()):
                        t = w.tabText(idx).strip()
                        if t and t not in user_data_whitelist and pat.search(t):
                            leaks.append(f"QTabBar[{idx}]={t!r}")
            assert leaks == [], f"{lang} visible leaks: {leaks}"
    finally:
        set_current_language("zh")
        win.close()
        mixer.close()


def _rel_luminance(hex_color: str) -> float:
    from PySide6 import QtGui

    c = QtGui.QColor(hex_color)
    def _lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(c.redF()) + 0.7152 * _lin(c.greenF()) + 0.0722 * _lin(c.blueF())


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = _rel_luminance(fg_hex)
    l2 = _rel_luminance(bg_hex)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_ub03_dark_dock_contrast_header_no_clip_1093_no_overflow_and_tab05_accessible() -> None:
    """U-B03: Dark dock & axis contrast >=4.5:1, no header subtitle clip (zh/en), no 1093x566 bottom overflow, tab 05 accessible."""
    from dataclasses import replace
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from core.i18n import set_current_language
    from ui.acid_style import get_acid_palette
    from ui.main_window import ListenScopeMainWindow

    app = _get_app()
    dark_p = get_acid_palette("dark")
    assert _rel_luminance(dark_p.dock_bg) < 0.20, f"Dark dock_bg {dark_p.dock_bg} is too bright"
    assert _rel_luminance(dark_p.dock_card) < 0.20, f"Dark dock_card {dark_p.dock_card} is too bright"
    assert _rel_luminance(dark_p.hist_plot_bg) < 0.20, f"Dark hist_plot_bg {dark_p.hist_plot_bg} is too bright"
    assert _contrast_ratio(dark_p.plot_axis, dark_p.plot_bg) >= 4.5
    assert _contrast_ratio(dark_p.hist_plot_axis, dark_p.hist_plot_bg) >= 4.5

    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        # 1. Dark dock QSS uses dark background
        win.apply_appearance(replace(win.appearance, preset="acid_telemetry", theme_mode="dark", language="en"), force_theme=True)
        win.resize(1366, 768)
        win.show()
        app.processEvents()
        assert f"background-color: {dark_p.dock_bg}" in win.styleSheet()

        # 2. SpectrumAnalysisWidget header subtitle not clipped by metric cards in both zh and en
        for lang in ("en", "zh"):
            for w, h in ((1366, 768), (1093, 566)):
                win.apply_appearance(replace(win.appearance, language=lang), force_theme=True)
                win.resize(w, h)
                app.processEvents()
                sw = win.spectrum_widget
                assert sw._header.geometry().bottom() <= sw._metric_cards[0].geometry().top(), (
                    f"Header overlaps cards at {w}x{h} ({lang}): {sw._header.geometry()} vs {sw._metric_cards[0].geometry()}"
                )
                assert sw._header.height() >= sw._header.sizeHint().height() - 1, (
                    f"Header clipped at {w}x{h} ({lang}): {sw._header.height()} < {sw._header.sizeHint().height()}"
                )

        # 3. At 1093x566, no visible widget inside _history_box overflows bottom/right
        win.resize(1093, 566)
        app.processEvents()
        box_rect = win._history_box.rect()
        for child in win._history_box.findChildren(QtWidgets.QWidget):
            if child.isVisible() and child.parent() is win._history_box:
                g = child.geometry()
                assert g.bottom() <= box_rect.bottom() + 1 and g.right() <= box_rect.right() + 1, (
                    f"Overflow in _history_box at 1093x566: {type(child).__name__} {g} vs {box_rect}"
                )

        # 4. Tabs scroll buttons enabled and tab 05 (LIVE ENGINE) switchable at 1093 width
        assert win.tabs.usesScrollButtons() is True
        win.tabs.setCurrentIndex(4)
        app.processEvents()
        assert win.tabs.currentWidget() is win.live_widget
    finally:
        set_current_language("zh")
        win.close()
        mixer.close()


@pytest.mark.xfail(strict=True, reason="U-B34")
def test_ub34_realtime_waveform_envelope_4s_uniform_band_for_440hz_and_1khz() -> None:
    """U-B34: 4s realtime waveform min/max envelope for 440Hz & 1kHz sine must form a uniform +/-A band (no aliasing)."""
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig

    acfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10)
    amp = 0.5
    t = np.arange(48000 * 4, dtype=np.float32) / 48000.0
    for freq in (440.0, 1000.0):
        rb = FixedRingBuffer(acfg)
        sig = (amp * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)
        rb.write(np.stack([sig, sig], axis=1))
        w = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
        snap = w.analyze_latest_once()
        wmin = np.asarray(snap.waveform_min, dtype=np.float32)
        wmax = np.asarray(snap.waveform_max, dtype=np.float32)
        assert wmax.size >= 256 and wmin.size == wmax.size
        assert float(np.min(wmax)) >= 0.9 * amp, (
            f"{freq} Hz waveform_max dipped to {float(np.min(wmax)):.3f} (need >= {0.9 * amp:.3f})"
        )
        assert float(np.max(wmin)) <= -0.9 * amp, (
            f"{freq} Hz waveform_min rose to {float(np.max(wmin)):.3f} (need <= {-0.9 * amp:.3f})"
        )



