"""Regression tests for topbar capsule truncation, overlap prevention, and 4-stage progressive collapse."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


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


def _inject_heavy_telemetry(win, *, dbfs: float = -120.0, ram_avail_mb: float = 102297.6, vram_free_mb: float = 6553.6, vram_total_mb: float = 8192.0, dev_name: str = "Realtek High Definition Audio USB Speakers (Very Long Device Name)") -> None:
    from core.models import CaptureMode, CaptureStats, ResourceSnapshot, ResourceStatus

    win.populate_audio_sources([], include_synthetic=False)
    for idx in range(win.source_combo.count()):
        data = win.source_combo.itemData(idx)
        if isinstance(data, dict) and data.get("kind") == "system_loopback":
            win.source_combo.setCurrentIndex(idx)
            break

    win.update_capture_stats(
        CaptureStats(
            mode=CaptureMode.SYSTEM_LOOPBACK,
            pid=None,
            process_name=dev_name,
            sample_rate=48000,
            channels=2,
            dtype="float32",
            is_running=True,
            is_silent=False,
            rms_dbfs=dbfs,
            peak_dbfs=min(0.0, dbfs + 6.0),
        ),
        42.5,
    )
    win.update_resource_snapshot(
        ResourceSnapshot(
            timestamp=10.0,
            main_ram_mb=320.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=131072.0,
            system_ram_available_mb=ram_avail_mb,
            gpu_name="NVIDIA GeForce RTX 5060 Ti",
            vram_total_mb=vram_total_mb,
            vram_used_mb=max(0.0, vram_total_mb - vram_free_mb),
            vram_free_mb=vram_free_mb,
            gpu_utilization_pct=22.0,
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            audio_queue_size=4,
            audio_queue_maxsize=64,
            ai_buffer_seconds=1.5,
            status=ResourceStatus.WARNING,
        ),
        [],
        [],
    )


def _rect_in_window(win: QtWidgets.QWidget, wdg: QtWidgets.QWidget) -> QtCore.QRect:
    tl = wdg.mapTo(win, QtCore.QPoint(0, 0))
    return QtCore.QRect(tl.x(), tl.y(), wdg.width(), wdg.height())


def _assert_topbar_geometry_and_labels(win, context: str) -> None:
    win_rect = win.rect()

    # 1. All visible top-level items inside _topbar_cmd_row lie inside window and do not overlap
    top_widgets: list[QtWidgets.QWidget] = []
    for i in range(win._topbar_cmd_row.count()):
        wdg = win._topbar_cmd_row.itemAt(i).widget()
        if wdg is not None and wdg.isVisible() and wdg.width() > 0 and wdg.height() > 0:
            top_widgets.append(wdg)

    top_rects = [(wdg.objectName() or type(wdg).__name__, _rect_in_window(win, wdg), wdg) for wdg in top_widgets]
    for name, r, _wdg in top_rects:
        assert win_rect.contains(r.topLeft()) and win_rect.contains(r.bottomRight()), (
            f"{context}: topbar widget {name!r} rect={r} overflows win_rect={win_rect}"
        )
    for idx_a in range(len(top_rects)):
        name_a, rect_a, _ = top_rects[idx_a]
        for idx_b in range(idx_a + 1, len(top_rects)):
            name_b, rect_b, _ = top_rects[idx_b]
            assert not rect_a.intersects(rect_b), (
                f"{context}: topbar widgets overlap: {name_a!r} {rect_a} vs {name_b!r} {rect_b}"
            )

    # 2. Internal sibling widgets inside composite containers do not overlap and fit parent
    for container in (win.resource_bar, win._skin_switcher, win._win_ctrl_box):
        if not container.isVisible():
            continue
        crect = _rect_in_window(win, container)
        children = [
            ch
            for ch in container.findChildren(QtWidgets.QWidget, options=QtCore.Qt.FindChildOption.FindDirectChildrenOnly)
            if ch.isVisible() and ch.width() > 0 and ch.height() > 0
        ]
        child_rects = [(ch.objectName() or type(ch).__name__, _rect_in_window(win, ch)) for ch in children]
        for name, cr in child_rects:
            assert crect.contains(cr.topLeft()) and crect.contains(cr.bottomRight()), (
                f"{context}: child {name!r} rect={cr} exceeds container={crect}"
            )
        for i_a in range(len(child_rects)):
            na, ra = child_rects[i_a]
            for i_b in range(i_a + 1, len(child_rects)):
                nb, rb = child_rects[i_b]
                assert not ra.intersects(rb), f"{context}: sibling overlap {na!r} {ra} vs {nb!r} {rb}"

    # 3. Every visible QLabel inside _topbar_frame must fit contentsRect OR end with '…' + non-empty tooltip
    for lbl in win._topbar_frame.findChildren(QtWidgets.QLabel):
        if not lbl.isVisible():
            continue
        txt = lbl.text()
        if not txt:
            continue
        adv = lbl.fontMetrics().horizontalAdvance(txt)
        cr_w = lbl.contentsRect().width()
        fits = adv <= cr_w
        elided_ok = txt.endswith("…") and bool(lbl.toolTip().strip())
        assert fits or elided_ok, (
            f"{context}: label {lbl.objectName()!r} clipped without ellipsis/tooltip: "
            f"text={txt!r} adv={adv} cr_w={cr_w} tooltip={lbl.toolTip()!r}"
        )

    # 4. Buttons keep non-clipped labels or non-empty tooltips
    for bname, btn in (
        ("capture_btn", win.capture_btn),
        ("freeze_screen_btn", win.freeze_screen_btn),
        ("settings_btn", win.settings_btn),
        ("refresh_btn", win.refresh_btn),
        ("emergency_stop_btn", win.emergency_stop_btn),
        ("_pill_dark", win._pill_dark),
        ("_pill_light", win._pill_light),
        ("_theme_icon_btn", win._theme_icon_btn),
    ):
        if not btn.isVisible():
            continue
        if btn.text().strip():
            assert btn.width() >= btn.sizeHint().width(), (
                f"{context}: {bname} clipped: text={btn.text()!r} w={btn.width()} < hint={btn.sizeHint().width()}"
            )
        else:
            assert btn.toolTip().strip(), f"{context}: {bname} icon-only missing tooltip"

    assert win.source_combo.width() >= win.source_combo.minimumWidth(), (
        f"{context}: source_combo squeezed {win.source_combo.width()} < {win.source_combo.minimumWidth()}"
    )
    assert win.source_combo.toolTip().strip(), f"{context}: source_combo missing tooltip"


def test_topbar_width_sweep_874_to_1600_4_langs_scale_1_0() -> None:
    from core.appearance import Appearance

    widths = sorted(set(list(range(874, 1601, 32)) + [1190, 1366, 1600]))
    app, win, mixer = _make_window()
    try:
        win.show()
        _inject_heavy_telemetry(win)
        for lang in ("zh", "en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            for w in widths:
                win.resize(w, 720 if w >= 1024 else 528)
                app.processEvents()
                _assert_topbar_geometry_and_labels(win, f"scale=1.0 lang={lang} w={w}")
    finally:
        win.close()
        mixer.close()


def test_topbar_width_sweep_874_to_1600_4_langs_scale_1_25() -> None:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = "1.25"
    code = """
import sys
from pathlib import Path
from PySide6 import QtWidgets
REPO = Path.cwd()
sys.path.insert(0, str(REPO))
from core.appearance import Appearance
from tests.test_topbar_capsule_overflow import (
    _assert_topbar_geometry_and_labels,
    _inject_heavy_telemetry,
    _make_window,
)

widths = sorted(set(list(range(874, 1601, 32)) + [1190, 1366, 1600]))
app, win, mixer = _make_window()
try:
    win.show()
    _inject_heavy_telemetry(win)
    for lang in ("zh", "en", "ja", "ko"):
        win.apply_appearance(Appearance(theme_mode="light", language=lang))
        for w in widths:
            win.resize(w, 700 if w >= 1024 else 528)
            app.processEvents()
            _assert_topbar_geometry_and_labels(win, f"scale=1.25 lang={lang} w={w}")
finally:
    win.close()
    mixer.close()
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"1.25x topbar sweep failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_wide_req_uses_worst_case_sample_and_prevents_oscillation() -> None:
    from core.appearance import Appearance
    from core.models import CaptureMode, CaptureStats, ResourceSnapshot, ResourceStatus

    app, win, mixer = _make_window()
    try:
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.show()
        for w in (1190, 1366):
            win.resize(w, 768)
            app.processEvents()
            stage_idle = win._topbar_collapse_stage

            # Mid-level capture + small numbers
            win.update_capture_stats(
                CaptureStats(
                    mode=CaptureMode.SYSTEM_LOOPBACK,
                    pid=None,
                    process_name="Speakers",
                    sample_rate=48000,
                    channels=2,
                    dtype="float32",
                    is_running=True,
                    is_silent=False,
                    rms_dbfs=-28.2,
                    peak_dbfs=-19.0,
                ),
                12.0,
            )
            win.update_resource_snapshot(
                ResourceSnapshot(
                    timestamp=2.0,
                    main_ram_mb=180.0,
                    ai_worker_ram_mb=0.0,
                    system_ram_total_mb=16384.0,
                    system_ram_available_mb=4915.2,
                    gpu_name="RTX 5060 Ti",
                    vram_total_mb=8192.0,
                    vram_used_mb=1638.4,
                    vram_free_mb=6553.6,
                    gpu_utilization_pct=10.0,
                    active_ai_jobs=0,
                    loaded_models=0,
                    current_model=None,
                    current_task=None,
                    audio_queue_size=1,
                    audio_queue_maxsize=64,
                    ai_buffer_seconds=1.0,
                    status=ResourceStatus.NORMAL,
                ),
                [],
                [],
            )
            win._apply_responsive_layout()
            app.processEvents()
            stage_mid = win._topbar_collapse_stage

            # Worst-case numbers within sample bounds (99.9G, -120.0 dBFS)
            _inject_heavy_telemetry(win, dbfs=-120.0, ram_avail_mb=99.9 * 1024.0, vram_free_mb=99.9 * 1024.0, vram_total_mb=99.9 * 1024.0)
            win._apply_responsive_layout()
            app.processEvents()
            stage_heavy = win._topbar_collapse_stage

            assert stage_idle == stage_mid == stage_heavy, (
                f"Layout stage oscillated at w={w}: idle={stage_idle}, mid={stage_mid}, heavy={stage_heavy}"
            )
            _assert_topbar_geometry_and_labels(win, f"worst-case w={w}")
    finally:
        win.close()
        mixer.close()


def test_debounced_relayout_triggers_on_capsule_widening_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.models import ResourceSnapshot, ResourceStatus

    app, win, mixer = _make_window()
    try:
        win.resize(1320, 768)
        win.show()
        app.processEvents()
        assert win._topbar_relayout_timer.interval() == 200
        assert win._topbar_relayout_timer.isSingleShot() is True

        relayout_calls: list[int] = []
        orig_apply = win._apply_responsive_layout

        def _spy_apply() -> None:
            relayout_calls.append(1)
            orig_apply()

        monkeypatch.setattr(win, "_apply_responsive_layout", _spy_apply)

        # Equal/smaller values within sample budget still increase live resource_bar hint if > previous hint
        # Establish baseline large value first so subsequent smaller value shrinks instead of widening
        huge_snap = ResourceSnapshot(
            timestamp=1.0,
            main_ram_mb=200.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=16384.0,
            system_ram_available_mb=10.5 * 1024.0,
            gpu_name="RTX 5060 Ti",
            vram_total_mb=8192.0,
            vram_used_mb=2048.0,
            vram_free_mb=6144.0,
            gpu_utilization_pct=5.0,
            active_ai_jobs=0,
            loaded_models=0,
            current_model=None,
            current_task=None,
            audio_queue_size=0,
            audio_queue_maxsize=64,
            ai_buffer_seconds=0.0,
            status=ResourceStatus.NORMAL,
        )
        win.update_resource_snapshot(huge_snap, [], [])
        win._apply_responsive_layout()
        relayout_calls.clear()

        # Shrinking width (10.5G -> 4.8G) must NOT schedule debounced relayout
        small_snap = ResourceSnapshot(**{**huge_snap.__dict__, "timestamp": 2.0, "system_ram_available_mb": 4.8 * 1024.0})
        win.update_resource_snapshot(small_snap, [], [])
        assert win._topbar_relayout_timer.isActive() is False
        assert relayout_calls == []

        # Extreme widening (4.8G -> 125000.0G) increases sizeHint and triggers 200ms debounced relayout
        ultra_snap = ResourceSnapshot(
            **{**huge_snap.__dict__, "timestamp": 3.0, "system_ram_available_mb": 125000.0 * 1024.0}
        )
        win.update_resource_snapshot(ultra_snap, [], [])
        assert win._topbar_relayout_timer.isActive() is True

        # Wait past 200ms debounce timer
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(280, loop.quit)
        loop.exec()
        assert len(relayout_calls) >= 1
    finally:
        win.close()
        mixer.close()


def test_four_stage_progressive_collapse_order_and_short_capture_format() -> None:
    from core.appearance import Appearance
    from core.models import CaptureMode, CaptureStats, ResourceSnapshot, ResourceStatus

    app, win, mixer = _make_window()
    try:
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.show()
        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name="Speakers (USB)",
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
                is_silent=False,
                rms_dbfs=-28.2,
                peak_dbfs=-20.0,
            ),
            12.0,
        )
        win.update_resource_snapshot(
            ResourceSnapshot(
                timestamp=1.0,
                main_ram_mb=200.0,
                ai_worker_ram_mb=0.0,
                system_ram_total_mb=16384.0,
                system_ram_available_mb=4915.2,
                gpu_name="RTX 5060 Ti",
                vram_total_mb=8192.0,
                vram_used_mb=1638.4,
                vram_free_mb=6553.6,
                gpu_utilization_pct=10.0,
                active_ai_jobs=0,
                loaded_models=0,
                current_model=None,
                current_task=None,
                audio_queue_size=0,
                audio_queue_maxsize=64,
                ai_buffer_seconds=0.0,
                status=ResourceStatus.NORMAL,
            ),
            [],
            [],
        )

        # Observe monotonic stages from wide 1600 down to minimumWidth 760
        seen_stages: list[int] = []
        stage_states: dict[int, tuple[bool, bool, bool, bool]] = {}
        stage_widths: dict[int, int] = {}
        for w in range(1600, 759, -16):
            win.resize(w, 720)
            app.processEvents()
            st = win._topbar_collapse_stage
            if not seen_stages or st != seen_stages[-1]:
                seen_stages.append(st)
            stage_widths.setdefault(st, w)
            stage_states[st] = (
                win._capture_compact_mode,
                win.resource_bar._compact_mode,
                win._theme_icon_btn.isVisible(),
                not bool(win.freeze_screen_btn.text().strip()),
            )
            _assert_topbar_geometry_and_labels(win, f"order w={w} stage={st}")

        assert seen_stages == sorted(seen_stages), f"Stages did not progress monotonically: {seen_stages}"
        assert {0, 1, 2, 3, 4}.issubset(set(seen_stages)), f"Expected stages 0..4 to trigger cleanly, got {seen_stages}"

        # Stage invariants in strict order:
        assert stage_states[0] == (False, False, False, False)
        assert stage_states[1] == (True, False, False, False)
        assert stage_states[2] == (True, True, False, False)
        assert stage_states[3] == (True, True, True, False)
        assert stage_states[4] == (True, True, True, True)

        # Verify short capture label and full tooltip at observed Stage-1 width (w=1190 is covered by sweep tests)
        win.resize(stage_widths[1], 720)
        app.processEvents()
        assert win.capture_status_lbl.text() == "⚠ -28 dB"
        assert "[混入警告]" in win.capture_status_lbl.toolTip()
        assert "-28.2 dBFS" in win.capture_status_lbl.toolTip()

        # Explicit squeeze of TopbarElideLabel directly validates '…' + tooltip invariant
        win.capture_status_lbl.setFixedWidth(44)
        app.processEvents()
        elided_txt = win.capture_status_lbl.text()
        assert elided_txt.endswith("…")
        assert win.capture_status_lbl.toolTip().strip()
        assert win.capture_status_lbl.fontMetrics().horizontalAdvance(elided_txt) <= win.capture_status_lbl.contentsRect().width()
        win.capture_status_lbl.setMinimumWidth(0)
        win.capture_status_lbl.setMaximumWidth(16777215)
    finally:
        win.close()
        mixer.close()


def test_loopback_source_combo_actual_device_elide_and_i18n() -> None:
    from core.appearance import Appearance
    from core.models import CaptureMode, CaptureStats

    long_dev = "Headphones (Sony WH-1000XM5 Stereo High Definition Audio Device)"
    app, win, mixer = _make_window()
    try:
        win.populate_audio_sources([], include_synthetic=False)
        for idx in range(win.source_combo.count()):
            data = win.source_combo.itemData(idx)
            if isinstance(data, dict) and data.get("kind") == "system_loopback":
                win.source_combo.setCurrentIndex(idx)
                break
        win.show()
        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name=long_dev,
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
                is_silent=False,
                rms_dbfs=-22.5,
                peak_dbfs=-14.0,
            ),
            8.0,
        )
        expected_prefixes = {
            "zh": f"[兜底] {long_dev}",
            "en": f"[Fallback] {long_dev}",
            "ko": f"[폴백] {long_dev}",
            "ja": f"[フォールバック] {long_dev}",
        }
        for lang, expected in expected_prefixes.items():
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.resize(1024, 600)
            app.processEvents()
            assert win.source_combo.currentText() == expected
            if lang in ("en", "ko"):
                assert not _CJK_CHAR_RE.search(win.source_combo.currentText()), (
                    f"{lang} source_combo text leaked CJK: {win.source_combo.currentText()!r}"
                )
            tip = win.source_combo.toolTip()
            lines = tip.splitlines()
            assert len(lines) >= 2 and lines[0] == long_dev
            assert "…" in lines[1], f"{lang} tooltip should mention ellipsis behavior: {tip!r}"
            # Narrow resize triggers _needs_scroll -> MarqueeComboBox paints right-elided text and keeps tooltip
            assert win.source_combo._needs_scroll() is True
            assert win.source_combo.toolTip() == tip
    finally:
        win.close()
        mixer.close()
