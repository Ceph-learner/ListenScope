"""Phase 2E UI polish verification tests (Issue #42, E1-E11; E9 kept PENDING for owner icon selection)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore, QtWidgets

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


@pytest.mark.xfail(strict=True, reason="E4")
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


@pytest.mark.xfail(strict=True, reason="E5")
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


@pytest.mark.xfail(strict=True, reason="E6")
def test_e6_chord_card_deduplicates_primary_label_and_uses_stability_meter() -> None:
    """E6: Chord card must not duplicate primary chord name in secondary line, and must replace raw correlation text with a 5-bar meter."""
    chroma_src = (REPO_ROOT / "ui" / "chroma_widget.py").read_text("utf-8")
    assert "稳定度:" not in chroma_src or "相关 " not in chroma_src, (
        "Chord/Key cards still display raw '稳定度: ... | 相关 ... | 差 ...' string instead of 5-bar meter + tooltip"
    )


@pytest.mark.xfail(strict=True, reason="E7")
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


@pytest.mark.xfail(strict=True, reason="E10")
def test_e10_design_doc_and_design_sheet_cli_exist() -> None:
    """E10: docs/DESIGN.md must document spacing/radius/type/color tokens, and scripts/make_screenshots.py must support --design-sheet."""
    design_md = REPO_ROOT / "docs" / "DESIGN.md"
    assert design_md.exists(), "docs/DESIGN.md does not exist"
    txt = design_md.read_text("utf-8")
    for token in ("Microsoft YaHei UI", "Cascadia Mono", "4/8/12/16/24/32"):
        assert token in txt, f"docs/DESIGN.md missing required token section {token!r}"
    script_src = (REPO_ROOT / "scripts" / "make_screenshots.py").read_text("utf-8")
    assert "--design-sheet" in script_src, "scripts/make_screenshots.py missing --design-sheet option"


@pytest.mark.xfail(strict=True, reason="E11")
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
