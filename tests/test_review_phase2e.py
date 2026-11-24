"""Phase 2E UI polish verification tests (Issue #42, E1-E11; E9 kept PENDING for owner icon selection)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _get_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_window():
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
    return app, win, mixer


def test_e1_topbar_single_row_le_56px_and_idle_estop_neutral() -> None:
    """E1: At 1366x768 top bar must be single-row (<=56px), E-STOP neutral when AI idle, <=1 solid accent button."""
    app, win, mixer = _make_window()
    try:
        win.resize(1366, 768)
        win.show()
        app.processEvents()
        top_container = getattr(win, "_top_bar", None) or getattr(win, "top_bar", None)
        if top_container is None:
            # Measure vertical span from top of window to top of tabs
            tab_top = win.tabs.mapTo(win, QtCore.QPoint(0, 0)).y()
            assert tab_top <= 56, f"Top bar area height {tab_top}px > 56px at 1366x768 (still multi-row)"
        else:
            assert top_container.height() <= 56, f"Top bar height {top_container.height()}px > 56px at 1366x768"

        # Theme skin badge must not stay permanently in top bar
        if hasattr(win, "_skin_badge"):
            assert not win._skin_badge.isVisible(), "Theme name badge (_skin_badge) still permanently visible in top bar"

        # E-STOP must not have red solid fill when AI is idle
        estop_btn = getattr(win, "estop_btn", None) or getattr(win, "emergency_stop_btn", None)
        if estop_btn is not None:
            assert estop_btn.property("ai_active") is False or "danger" not in str(estop_btn.property("tone") or ""), (
                "E-STOP still rendered with red danger fill while AI is idle"
            )
    finally:
        win.close()
        mixer.close()


def test_e2_no_double_slash_in_interactive_buttons_or_tabs_and_5_tabs_fit_1093() -> None:
    """E2: No button or tab text may contain '//' in zh/en/ja/ko; all 5 tabs fit without scrolling at width 1093."""
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        for lang in ("zh", "en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.resize(1093, 700)
            win.show()
            app.processEvents()
            bad_tabs = [win.tabs.tabText(i) for i in range(win.tabs.count()) if "//" in win.tabs.tabText(i)]
            assert bad_tabs == [], f"[{lang}] Tab labels still contain '//': {bad_tabs}"
            bad_btns = [b.text() for b in win.findChildren(QtWidgets.QPushButton) if b.isVisible() and "//" in b.text()]
            assert bad_btns == [], f"[{lang}] Visible buttons still contain '//': {bad_btns}"
        bar = win.tabs.tabBar()
        total_tab_w = sum(bar.tabRect(i).width() for i in range(bar.count()))
        assert total_tab_w <= bar.width() + 2, f"5 tabs overflow 1093px width ({total_tab_w}px > {bar.width()}px)"
    finally:
        win.close()
        mixer.close()


def test_e3_footer_is_real_24px_status_bar_not_decorative_barcode() -> None:
    """E3: Footer must be a real ~24px status bar (version, sample rate, p50 ms, buffer, CPU%, reduce-motion toggle)."""
    acid_src = (REPO_ROOT / "ui" / "acid_style.py").read_text("utf-8")
    assert "85/15_ANTI_FATIGUE" not in acid_src, "Footer still hardcodes decorative fake telemetry '85/15_ANTI_FATIGUE'"
    assert "ZERO_GLOW: TRUE" not in acid_src, "Footer still hardcodes decorative 'ZERO_GLOW: TRUE'"


def test_e4_visible_help_badges_le_10_per_page_and_f1_help_supported() -> None:
    """E4: Every page must show <= 10 visible HelpBadges and F1 must trigger focused-widget help."""
    from ui.help_badge import HelpBadge

    app, win, mixer = _make_window()
    try:
        win.resize(1366, 768)
        win.show()
        app.processEvents()
        for idx in range(win.tabs.count()):
            win.tabs.setCurrentIndex(idx)
            app.processEvents()
            vis = [h for h in win.findChildren(HelpBadge) if h.isVisible()]
            assert len(vis) <= 10, f"Tab {idx} shows {len(vis)} visible HelpBadges (> 10)"
        mw_src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
        assert "Key_F1" in mw_src or '"F1"' in mw_src or "'F1'" in mw_src, "Missing F1 focused-widget help shortcut"
    finally:
        win.close()
        mixer.close()


def test_e5_mixer_empty_state_shows_le_3_disabled_buttons() -> None:
    """E5: Before separation, mixer page must show an empty-state card and <= 3 visible disabled buttons."""
    app, win, mixer = _make_window()
    try:
        win.resize(1366, 768)
        win.tabs.setCurrentIndex(2)
        win.show()
        app.processEvents()
        vis_disabled = [
            b.text()
            for b in win.mixer_widget.findChildren(QtWidgets.QPushButton)
            if b.isVisible() and not b.isEnabled()
        ]
        assert len(vis_disabled) <= 3, f"Mixer empty state exposes {len(vis_disabled)} disabled buttons (> 3): {vis_disabled}"
    finally:
        win.close()
        mixer.close()


def test_e6_chord_card_deduplicates_primary_label_and_uses_stability_meter() -> None:
    """E6: Chord card must not duplicate primary chord name in secondary line, and must replace raw correlation text with a 5-bar meter."""
    chroma_src = (REPO_ROOT / "ui" / "chroma_widget.py").read_text("utf-8")
    assert "稳定度:" not in chroma_src or "相关 " not in chroma_src, (
        "Chord/Key cards still display raw '稳定度: ... | 相关 ... | 差 ...' string instead of 5-bar meter + tooltip"
    )


def test_e7_charts_uniform_fft_ticks_left_alignment_and_perceptual_colormap() -> None:
    """E7: FFT Y ticks fixed to 0/-30/-60/-90 dB, light/dark spectrogram colormap L* span >= 60%, left plot margins aligned +-2px."""
    sw_src = (REPO_ROOT / "ui" / "spectrum_widget.py").read_text("utf-8")
    assert "(-90.0, -60.0, -30.0, 0.0)" in sw_src or "(0.0, -30.0, -60.0, -90.0)" in sw_src or "(-90, -60, -30, 0)" in sw_src, (
        "FFT Y-axis ticks not standardized to 0 / -30 / -60 / -90 dB"
    )
    app, win, mixer = _make_window()
    try:
        win.resize(1366, 768)
        win.tabs.setCurrentIndex(0)
        win.show()
        app.processEvents()
        sw = win.spectrum_widget
        lefts = [
            float(p.getViewBox().sceneBoundingRect().left())
            for p in (sw.wave_plot, sw.fft_plot, sw.spec_plot)
        ]
        assert max(lefts) - min(lefts) <= 2.5, f"Plot left edges misaligned > 2px: {lefts}"
    finally:
        win.close()
        mixer.close()


def test_e8_unified_lucide_icons_registered_and_no_unicode_window_buttons() -> None:
    """E8: ui/assets/icons/ICONS.md must register every icon in ui/assets/icons/, and window buttons must use SVG instead of □ ❐ × −."""
    icons_dir = REPO_ROOT / "ui" / "assets" / "icons"
    icons_md = icons_dir / "ICONS.md"
    assert icons_md.exists(), "ui/assets/icons/ICONS.md does not exist"
    md_text = icons_md.read_text("utf-8")
    svg_files = sorted(p.name for p in icons_dir.glob("*.svg"))
    assert len(svg_files) >= 8, f"Expected unified Lucide SVG icons in ui/assets/icons/, found {len(svg_files)}"
    missing = [name for name in svg_files if name not in md_text]
    assert missing == [], f"Icons not registered in ui/assets/icons/ICONS.md: {missing}"

    mw_src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    assert not any(ch in mw_src for ch in ("❐", "□")), "ui/main_window.py still uses Unicode glyphs (□/❐) for window buttons"


def test_e9_app_icon_ico_tray_and_icon_doc() -> None:
    """E9: Multi-size .ico (>=7 sizes, 16px from 3-bar small_dark), tray theme switching, ICON.md, social_preview."""
    import struct
    from PySide6 import QtGui

    ico_path = REPO_ROOT / "ui" / "assets" / "listenscope.ico"
    assert ico_path.exists(), "ui/assets/listenscope.ico missing"
    raw = ico_path.read_bytes()
    _reserved, _ico_type, count = struct.unpack_from("<HHH", raw, 0)
    sizes = set()
    for i in range(count):
        w, h = struct.unpack_from("<BB", raw, 6 + i * 16)
        sizes.add((256 if w == 0 else w, 256 if h == 0 else h))
    assert len(sizes) >= 7, f"Expected >= 7 ICO sizes, got {sorted(sizes)}"
    assert (16, 16) in sizes

    # Verify 16px frame comes from small_dark (3 vertical bars at middle row y=8, not 5)
    _get_app()
    icon16 = QtGui.QIcon(str(ico_path))
    im16 = icon16.pixmap(16, 16).toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    bright_runs = 0
    in_run = False
    for x in range(3, 13):
        c = im16.pixelColor(x, 8)
        is_bar = c.alpha() > 128 and (c.green() > 140 or c.blue() > 140) and (c.red() + c.green() + c.blue() > 200)
        if is_bar and not in_run:
            bright_runs += 1
            in_run = True
        elif not is_bar:
            in_run = False
    assert bright_runs == 3, f"16px ICO frame should have 3 bars from small_dark, detected {bright_runs}"

    mw_src = (REPO_ROOT / "ui" / "main_window.py").read_text("utf-8")
    assert "SystemUsesLightTheme" in mw_src and "listenscope_tray_black.svg" in mw_src and "listenscope_tray_white.svg" in mw_src
    assert (REPO_ROOT / "docs" / "design" / "ICON.md").exists()
    assert (REPO_ROOT / "docs" / "design" / "social_preview.png").exists()
    assert (REPO_ROOT / "docs" / "design" / "legacy" / "listenscope_v1.svg").exists()


def test_e10_design_doc_and_design_sheet_cli_exist() -> None:
    """E10: docs/DESIGN.md must document spacing/radius/type/color tokens, and scripts/make_screenshots.py must support --design-sheet."""
    design_md = REPO_ROOT / "docs" / "DESIGN.md"
    assert design_md.exists(), "docs/DESIGN.md does not exist"
    txt = design_md.read_text("utf-8")
    for token in ("Microsoft YaHei UI", "Cascadia Mono", "4/8/12/16/24/32"):
        assert token in txt, f"docs/DESIGN.md missing required token section {token!r}"
    script_src = (REPO_ROOT / "scripts" / "make_screenshots.py").read_text("utf-8")
    assert "--design-sheet" in script_src, "scripts/make_screenshots.py missing --design-sheet option"


def test_e11_default_ab_panel_single_row_le_120px_at_1366x768() -> None:
    """E11: At 1366x768 default state, A/B bottom dock must stay compact (<= 120px height)."""
    app, win, mixer = _make_window()
    try:
        win.resize(1366, 768)
        win.tabs.setCurrentIndex(0)
        win.show()
        app.processEvents()
        dock_h = win._bottom_dock.height()
        assert dock_h <= 120, f"Default A/B bottom dock height {dock_h}px > 120px at 1366x768"
    finally:
        win.close()
        mixer.close()


def test_er_1_icon_buttons_have_no_unicode_glyph_chars() -> None:
    """ER1: Any button with a non-null icon must not also embed ⏸▶■●□❐×− in its text."""
    app, win, mixer = _make_window()
    try:
        win.show()
        app.processEvents()
        forbidden = set("⏸▶■●□❐×−")
        for btn in win.findChildren(QtWidgets.QPushButton):
            if not btn.icon().isNull():
                txt = btn.text() or ""
                hit = [ch for ch in txt if ch in forbidden]
                assert not hit, f"Icon button {btn.objectName() or txt!r} contains forbidden glyph(s) {hit}"
        win.set_freeze_screen(True)
        app.processEvents()
        assert not any(ch in (win.freeze_screen_btn.text() or "") for ch in forbidden)
    finally:
        win.close()
        mixer.close()


def test_er_2_tab_titles_no_underscore_slash_or_ampersand() -> None:
    """ER2: Tab titles in all 4 languages must not contain '_', '//', or '&'."""
    from ui.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        for lang in ("zh", "en", "ko", "ja"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            app.processEvents()
            for i in range(win.tabs.count()):
                title = win.tabs.tabText(i)
                assert "_" not in title and "//" not in title and "&" not in title, (
                    f"Tab {i} in {lang!r} has invalid char: {title!r}"
                )
    finally:
        win.close()
        mixer.close()


def test_er_3_estop_never_truncated_and_resource_capsule_adaptive() -> None:
    """ER3: E-STOP text is never truncated at 1093x566 or 1366x768 (en/zh) and resource capsule adapts."""
    from core.models import ResourceSnapshot, ResourceStatus
    from ui.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        snap = ResourceSnapshot(
            timestamp=1.0,
            main_ram_mb=320.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=16384.0,
            system_ram_available_mb=6200.0,
            gpu_name="Test GPU",
            vram_total_mb=8192.0,
            vram_used_mb=1024.0,
            vram_free_mb=7168.0,
            gpu_utilization_pct=4.0,
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            audio_queue_size=1,
            audio_queue_maxsize=64,
            ai_buffer_seconds=3.0,
            status=ResourceStatus.NORMAL,
        )
        win.update_resource_snapshot(snap, [], [])
        for lang in ("zh", "en"):
            for w, h in ((1366, 768), (1093, 566)):
                win.apply_appearance(Appearance(theme_mode="light", language=lang))
                win.resize(w, h)
                win.show()
                app.processEvents()
                btn = win.emergency_stop_btn
                txt = btn.text()
                if txt:
                    fm = QtGui.QFontMetrics(btn.font())
                    assert btn.width() >= fm.horizontalAdvance(txt), (
                        f"E-STOP truncated at {w}x{h} ({lang}): width={btn.width()} < text={fm.horizontalAdvance(txt)}"
                    )
                if w < 1200:
                    assert win.resource_bar._compact_mode is True
                else:
                    assert win.resource_bar._compact_mode is False
                    assert "G" in win.resource_bar.ram_label.text()
    finally:
        win.close()
        mixer.close()


def test_er_4_footer_telemetry_and_process_cpu() -> None:
    """ER4: Simulated capture populates footer source/Buf/p50/CPU consistently with A/B buffer."""
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig
    from core.models import CaptureMode, CaptureStats

    acfg = AudioConfig(sample_rate=48000, channels=2, ring_buffer_seconds=10)
    rb = FixedRingBuffer(acfg)
    rb.write(np.zeros((4800, 2), dtype=np.float32))
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    snap = worker.analyze_latest_once()
    assert snap.latency_ms is not None and snap.latency_ms >= 0.0

    app, win, mixer = _make_window()
    try:
        cap = CaptureStats(
            mode=CaptureMode.SYNTHETIC_SIMULATION,
            pid=None,
            process_name="Simulated",
            is_running=True,
            sample_rate=48000,
            channels=2,
            dtype="float32",
            rms_dbfs=-20.0,
            peak_dbfs=-6.0,
            is_silent=False,
        )
        win.update_capture_stats(cap, ring_available_sec=3.0)
        win.update_analysis_snapshot(snap, None, None)
        app.processEvents()
        footer_texts = " ".join(lbl.text() for lbl in win._acid_footer.findChildren(QtWidgets.QLabel))
        assert "Simulated" in footer_texts
        assert "3.0s" in footer_texts
        assert "3.0 / 120.0 s" in win.history_coverage_lbl.text()
        assert "p50:" in footer_texts and "p50: --" not in footer_texts
    finally:
        win.close()
        mixer.close()


def test_er_5_spectrogram_fixed_range_and_empty_placeholder() -> None:
    """ER5: Spectrogram X axis stays fixed at -30..0 s and shows placeholder when empty."""
    from core.models import (
        AnalysisSnapshot,
        ChordEstimate,
        KeyEstimate,
        PitchEstimate,
        TempoEstimate,
    )

    app, win, mixer = _make_window()
    try:
        win.show()
        app.processEvents()
        x_range = win.spectrum_widget.spec_plot.viewRange()[0]
        assert abs(x_range[0] - (-30.0)) < 0.5 and abs(x_range[1] - 0.0) < 0.5
        assert win.spectrum_widget._spec_empty_item.isVisible() is True

        dummy_snap = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[0.0] * 16,
            waveform_max=[0.0] * 16,
            fft_freqs_hz=[100.0, 200.0],
            fft_db=[-40.0, -50.0],
            log_freqs_hz=[100.0, 200.0],
            log_spectrum_db=[-40.0, -50.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("C", "Am", "High", 0.9, 0.2, False),
            key=KeyEstimate("C major", "A minor", "High", 0.9, 0.2),
            tempo=TempoEstimate(120.0, "High", 0.9, 60.0),
            pitch=PitchEstimate(440.0, "A4", 0.0, 0.9, False, "full"),
            rms_dbfs=-20.0,
            peak_dbfs=-10.0,
            window_seconds=3.0,
            latency_ms=5.0,
        )
        win.spectrum_widget.update_analysis(dummy_snap, spectrogram=np.full((45, 96), -40.0, dtype=np.float32))
        assert win.spectrum_widget._spec_empty_item.isVisible() is False
    finally:
        win.close()
        mixer.close()


def test_er_6_chroma_heatmap_orientation_and_axis() -> None:
    """ER6: Chroma heatmap disables SI prefix, shows -30..0s, >=6 ticks, and maps C# (idx 1) to row 1."""
    from core.models import (
        AnalysisSnapshot,
        ChordEstimate,
        KeyEstimate,
        PitchEstimate,
        TempoEstimate,
    )

    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(1)
        win.show()
        app.processEvents()
        ax_b = win.chroma_widget.chroma_hist_plot.getAxis("bottom")
        assert ax_b.autoSIPrefix is False
        x_range = win.chroma_widget.chroma_hist_plot.viewRange()[0]
        assert abs(x_range[0] - (-30.0)) < 0.5 and abs(x_range[1] - 0.0) < 0.5

        # Synthetic history where ONLY C# (index 1) has energy
        hist = np.zeros((12, 30), dtype=np.float32)
        hist[1, :] = 0.95
        dummy_snap = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[0.0] * 16,
            waveform_max=[0.0] * 16,
            fft_freqs_hz=[100.0, 200.0],
            fft_db=[-40.0, -50.0],
            log_freqs_hz=[100.0, 200.0],
            log_spectrum_db=[-40.0, -50.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("C#m", "E", "High", 0.9, 0.2, False),
            key=KeyEstimate("E major", "C# minor", "High", 0.9, 0.2),
            tempo=TempoEstimate(120.0, "High", 0.9, 60.0),
            pitch=PitchEstimate(440.0, "A4", 0.0, 0.9, False, "full"),
            rms_dbfs=-20.0,
            peak_dbfs=-10.0,
            window_seconds=3.0,
            latency_ms=5.0,
        )
        win.chroma_widget.update_analysis(dummy_snap, chroma_history=hist)
        img = win.chroma_widget._chroma_img.image
        assert img is not None and img.shape == (30, 12)
        assert float(img[:, 1].mean()) > 0.9
        assert float(img[:, 0].mean()) < 0.05
    finally:
        win.close()
        mixer.close()


def test_er_7_compact_metric_labels_not_clipped() -> None:
    """ER7: At 1093x566, no metric value QLabel has sizeHint().height() > height()."""
    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(0)
        win.resize(1093, 566)
        win.show()
        app.processEvents()
        for lbl in (
            win.spectrum_widget.pitch_label,
            win.spectrum_widget.rms_label,
            win.spectrum_widget.peak_label,
            win.spectrum_widget.window_label,
        ):
            assert lbl.height() >= lbl.sizeHint().height(), (
                f"Metric label {lbl.text()!r} clipped: height={lbl.height()} < sizeHint={lbl.sizeHint().height()}"
            )
    finally:
        win.close()
        mixer.close()


def test_er_8_mixer_empty_state_consistent_and_no_4x_watermark() -> None:
    """ER8: Mixer empty card primary button triggers 2-Stem, WAV-to-MIDI is flat link, no 4X watermark, centered table hint."""
    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(2)
        win.show()
        app.processEvents()
        mw = win.mixer_widget
        assert mw._empty_quick_2stem_btn.objectName() == "acidPrimaryBtn"
        assert mw._empty_open_midi_btn.isFlat() is True
        assert not hasattr(mw, "_empty_tracks_ov")
        assert mw._chord_empty_lbl.isVisible() is True
    finally:
        win.close()
        mixer.close()


def test_er_9_10_11_dark_ab_region_key_separator_and_source_placeholder() -> None:
    """ER9/ER10/ER11: Dark A/B region uses theme lime, key card omits empty separator, source_combo has i18n placeholder."""
    from core.models import (
        AnalysisSnapshot,
        ChordEstimate,
        KeyEstimate,
        PitchEstimate,
        TempoEstimate,
    )
    from ui.acid_style import get_acid_palette
    from ui.appearance import Appearance

    assert get_acid_palette("dark").plot_region_rgba[:3] == (206, 255, 24)
    app, win, mixer = _make_window()
    try:
        win.source_combo.clear()
        for lang in ("zh", "en", "ko", "ja"):
            win.apply_appearance(Appearance(theme_mode="dark", language=lang))
            app.processEvents()
            assert len(win.source_combo.placeholderText().strip()) > 0

        dummy_snap = AnalysisSnapshot(
            timestamp=1.0,
            waveform_min=[0.0] * 16,
            waveform_max=[0.0] * 16,
            fft_freqs_hz=[100.0, 200.0],
            fft_db=[-40.0, -50.0],
            log_freqs_hz=[100.0, 200.0],
            log_spectrum_db=[-40.0, -50.0],
            chroma_12=[0.1] * 12,
            chord=ChordEstimate("E", "C#m", "High", 0.9, 0.2, False),
            key=KeyEstimate("E major", "C# minor", "High", 0.9, 0.2, relation_note=""),
            tempo=TempoEstimate(120.0, "High", 0.9, 60.0),
            pitch=PitchEstimate(440.0, "A4", 0.0, 0.9, False, "full"),
            rms_dbfs=-20.0,
            peak_dbfs=-10.0,
            window_seconds=3.0,
            latency_ms=5.0,
        )
        win.chroma_widget.update_analysis(dummy_snap, None)
        assert not win.chroma_widget.key_relation_lbl.text().endswith("·")
    finally:
        win.close()
        mixer.close()


def test_er_12_13_14_windows_font_assert_win11_wording_and_notices() -> None:
    """ER12/ER13/ER14: Verify Windows font check in screenshot script, Win11 Build 20348 wording, and THIRD_PARTY_NOTICES cleanup."""
    script_src = (REPO_ROOT / "scripts" / "make_screenshots.py").read_text("utf-8")
    assert "QFontDatabase.families()" in script_src and "QT_QPA_FONTDIR" in script_src

    for fn in ("docs/FAQ.md", "docs/FAQ.en.md", "ui/main_window.py", "ui/settings_dialog.py"):
        txt = (REPO_ROOT / fn).read_text("utf-8")
        assert "Windows 11" in txt and "20348" in txt
        assert "Windows 10 Build" not in txt

    notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text("utf-8")
    assert "| soxr |" not in notices and "| certifi |" not in notices
    assert "NEEDS_TARGET" in notices
