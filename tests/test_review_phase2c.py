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


@pytest.mark.xfail(strict=True, reason="U-B02")
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


@pytest.mark.xfail(strict=True, reason="U-B03")
def test_ub03_main_window_fits_small_screens_1093x566_and_1024x528() -> None:
    """NEEDS_TARGET contract: minimumSize must allow <=780x540 and all visible bottom buttons must stay inside 1093x566."""
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
        win.resize(1024, 528)
        win.show()
        app.processEvents()
        assert win.width() <= 1024 and win.height() <= 528
    finally:
        win.close()
        mixer.close()


@pytest.mark.xfail(strict=True, reason="U-B07")
def test_ub07_ui_tick_deduplicates_snapshots_throttles_hidden_and_uses_precise_timer() -> None:
    """main.py must deduplicate snapshots by timestamp, throttle when hidden/minimized, use PreciseTimer, and sample resources off GUI thread."""
    src = (REPO_ROOT / "main.py").read_text("utf-8")
    assert "_last_snap_ts" in src or "_last_rendered_snap_ts" in src, "Missing snapshot timestamp deduplication in main.py"
    assert "PreciseTimer" in src, "UI tick timer is not set to Qt.TimerType.PreciseTimer"
    # _on_ui_tick must not call resource_manager.sample() synchronously on GUI thread
    m = re.search(r"def _on_ui_tick\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "resource_manager.sample()" not in m.group(0), "_on_ui_tick still calls resource_manager.sample() on GUI thread"


@pytest.mark.xfail(strict=True, reason="U-FX1")
def test_ufx1_frame_clock_exists_and_decouples_display_interpolation() -> None:
    """UI must provide a unified FrameClock (PreciseTimer, set_active(on, hz)) for 60/30 Hz display interpolation."""
    found = False
    for p in (REPO_ROOT / "ui").glob("*.py"):
        if "class FrameClock" in p.read_text("utf-8"):
            found = True
            break
    assert found, "Missing unified FrameClock class under ui/"


@pytest.mark.xfail(strict=True, reason="U-FX2")
def test_ufx2_ballistics_and_spectrogram_ring_buffer_exist() -> None:
    """Spectrum/chroma meters must use Ballistics peak-hold & SpectrumAnalyzer must avoid per-tick np.stack over deque."""
    ui_texts = "\n".join(p.read_text("utf-8") for p in (REPO_ROOT / "ui").glob("*.py"))
    assert "class Ballistics" in ui_texts, "Missing Ballistics meter/FFT peak-hold class under ui/"
    assert "skipFiniteCheck=True" in ui_texts, "pyqtgraph curves missing skipFiniteCheck=True"


@pytest.mark.xfail(strict=True, reason="U-B08")
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


@pytest.mark.xfail(strict=True, reason="U-B13")
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


@pytest.mark.xfail(strict=True, reason="U-B14")
def test_ub14_help_badge_is_keyboard_focusable_and_at_least_24px() -> None:
    """HelpBadge must support Qt.TabFocus (without auto-popup on focus) and have size >= 24x24 px (WCAG 2.5.8)."""
    from ui.help_badge import HelpBadge

    _get_app()
    badge = HelpBadge("示例帮助说明")
    assert badge.width() >= 24 and badge.height() >= 24, f"HelpBadge too small: {badge.width()}x{badge.height()}"
    assert badge.focusPolicy() in (QtCore.Qt.FocusPolicy.TabFocus, QtCore.Qt.FocusPolicy.StrongFocus), (
        f"HelpBadge is not keyboard focusable: {badge.focusPolicy()}"
    )


@pytest.mark.xfail(strict=True, reason="U-B15")
def test_ub15_focus_ring_uses_2px_accent_secondary_even_when_animation_disabled() -> None:
    """QSS focus outline must be >=2px using accent_secondary distinct from hover, and remain visible without animation."""
    src = (REPO_ROOT / "ui" / "acid_style.py").read_text("utf-8")
    m = re.search(r"QPushButton:focus.*?\{\{(.*?)\}\}", src, re.DOTALL)
    assert m is not None
    block = m.group(1)
    assert "2px solid" in block and "accent_secondary" in block, (
        f"ui/acid_style.py :focus rule still lacks 2px accent_secondary border: {block.strip()!r}"
    )


@pytest.mark.xfail(strict=True, reason="U-B17")
def test_ub17_static_lock_split_from_freeze_screen() -> None:
    """Static decoration lock must not freeze real-time spectrum/chord/key/pitch data updates; separate freeze_screen toggle required."""
    src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    m = re.search(r"def update_analysis_snapshot\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "if self._static_lock:\n            return" not in m.group(0), (
        "update_analysis_snapshot still returns early on self._static_lock, freezing data"
    )


@pytest.mark.xfail(strict=True, reason="U-B18")
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


@pytest.mark.xfail(strict=True, reason="U-B19")
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


@pytest.mark.xfail(strict=True, reason="U-FX3")
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


@pytest.mark.xfail(strict=True, reason="U-B22")
def test_ub22_win10_rounded_mask_avoids_jagged_qregion_polygon() -> None:
    """NEEDS_TARGET contract: _update_rounded_mask must not apply jagged QRegion(path.toFillPolygon().toPolygon()) mask on Win10."""
    src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    m = re.search(r"def _update_rounded_mask\(self.*?\n(?=    def )", src, re.DOTALL)
    assert m is not None
    assert "toFillPolygon().toPolygon()" not in m.group(0), (
        "_update_rounded_mask still applies jagged QRegion polygon mask"
    )


@pytest.mark.xfail(strict=True, reason="U-B26")
def test_ub26_mixer_widget_uses_bisect_for_chord_and_midi_lookup() -> None:
    """ui/mixer_widget.py must use bisect.bisect_right instead of O(N) linear scan every tick."""
    src = (REPO_ROOT / "ui" / "mixer_widget.py").read_text("utf-8")
    assert "bisect_right(" in src, "ui/mixer_widget.py still performs O(N) linear scan over chords/MIDI every tick"


@pytest.mark.xfail(strict=True, reason="U-B27")
def test_ub27_appearance_dialog_debounces_font_spinbox_changes() -> None:
    """ui/appearance.py must debounce SpinBox changes (>=100ms QTimer) instead of re-applying full QSS on every step."""
    src = (REPO_ROOT / "ui" / "appearance.py").read_text("utf-8")
    assert "QTimer" in src and ("120" in src or "debounce" in src.lower()), (
        "ui/appearance.py lacks 120ms debounce timer on font SpinBox"
    )


@pytest.mark.xfail(strict=True, reason="U-B30")
def test_ub30_telemetry_pulse_strip_accepts_real_level_or_is_static_by_default() -> None:
    """TelemetryPulseStrip must accept real audio level/bands (e.g. set_level / set_bands) instead of fake sine animation."""
    from ui.acid_style import TelemetryPulseStrip

    _get_app()
    strip = TelemetryPulseStrip()
    assert hasattr(strip, "set_level") or hasattr(strip, "set_bands") or hasattr(strip, "update_levels"), (
        "TelemetryPulseStrip has no real-audio level input API (pure decorative sine wave)"
    )


@pytest.mark.xfail(strict=True, reason="A-M6-UI")
def test_am6_ui_tempo_half_double_buttons_present_in_chroma_widget() -> None:
    """Merged from Phase 2B A-M6: Chroma/Tempo UI must provide ×2 and ÷2 quick tempo multiplier buttons."""
    from ui.chroma_widget import ChromaChordWidget

    _get_app()
    w = ChromaChordWidget()
    btn_texts = [b.text() for b in w.findChildren(QtWidgets.QAbstractButton)]
    has_double = any("×2" in t or "x2" in t.lower() or "2x" in t.lower() for t in btn_texts)
    has_half = any("÷2" in t or "/2" in t or "0.5x" in t.lower() for t in btn_texts)
    assert has_double and has_half, f"Missing tempo ×2/÷2 buttons in ChromaChordWidget (found: {btn_texts})"
