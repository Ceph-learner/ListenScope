from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _make_window():
    from PySide6 import QtWidgets
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    return app, win, mixer


def _contains_chinese_for_lang(text: str, lang: str) -> bool:
    if not text:
        return False
    # In en/ko, any CJK ideograph is a Chinese leak; in ja, Simplified-Chinese-only chars or zero-kana CJK phrases indicate leak.
    if lang in ("en", "ko"):
        return bool(re.search(r"[\u4e00-\u9fff]", text))
    if lang == "ja":
        # Check for obvious untranslated Simplified Chinese phrases or markers
        cn_markers = (
            "当前使用", "其他应用", "低音 ", "多声部", "曲目监测", "未检测到",
            "已缓冲", "请先", "点击", "展开", "收起", "换歌重置", "分轨",
        )
        return any(m in text for m in cn_markers)
    return False


def test_g1_runtime_states_no_chinese_leak_en_ja_ko() -> None:
    from core.appearance import Appearance
    from core.models import AnalysisSnapshot, ChordEstimate, KeyEstimate, PitchEstimate, TempoEstimate

    app, win, mixer = _make_window()
    try:
        for lang in ("en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            app.processEvents()

            # 1. System loopback fallback banner
            win.show_banner_message("当前使用系统 WASAPI Loopback 模式：其他应用声音可能被混入。", tone="warn")
            # 2. Polyphonic bass pitch snapshot
            snap = AnalysisSnapshot(
                timestamp=1.0,
                waveform_min=[],
                waveform_max=[],
                fft_freqs_hz=[],
                fft_db=[],
                log_freqs_hz=[],
                log_spectrum_db=[],
                chroma_12=[0.0] * 12,
                chord=ChordEstimate(primary="N", secondary="-", stability="Silent", correlation=0.0, margin=0.0, is_silent=True),
                key=KeyEstimate(primary="Unknown", secondary="-", stability="Insufficient", correlation=0.0, margin=0.0),
                tempo=TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0),
                window_seconds=4.0,
                rms_dbfs=-18.0,
                peak_dbfs=-6.0,
                pitch=PitchEstimate(frequency_hz=82.4, note_name="E2", cents_offset=-5.0, confidence=0.8, is_polyphonic=True, source_band="bass"),
            )
            win.spectrum_widget.update_snapshot(snap)
            from core.models import CaptureMode, CaptureStats

            # 3. SMTC no-session status + 0s coverage
            win.update_capture_stats(
                CaptureStats(
                    mode=CaptureMode.PROCESS_LOOPBACK,
                    pid=1234,
                    process_name="Spotify.exe",
                    sample_rate=48000,
                    channels=2,
                    dtype="float32",
                    is_running=True,
                ),
                0.0,
            )
            win.chroma_widget.sync_auto_reset_ui(
                track_status_text="曲目监测 (SMTC): 未检测到匹配会话，可继续使用右侧「换歌重置」"
            )
            app.processEvents()

            texts = [
                ("notice_banner", win.notice_banner.text()),
                ("pitch_label", win.spectrum_widget.pitch_label.text()),
                ("pitch_detail", win.spectrum_widget.pitch_detail.text()),
                ("track_status", win.chroma_widget.track_status_lbl.text()),
                ("track_tip", win.chroma_widget.track_status_lbl.toolTip()),
                ("coverage", win.history_coverage_lbl.text()),
            ]
            leaks = [(k, v) for k, v in texts if _contains_chinese_for_lang(v, lang)]
            assert not leaks, f"[{lang}] Chinese leak in runtime states: {leaks}"
    finally:
        win.close()
        mixer.close()


def test_g1_ast_static_chinese_strings_covered_by_i18n() -> None:
    from core.i18n import translate_text
    from core.i18n_catalog import HELP_TRANSLATIONS

    zh_re = re.compile(r"[\u4e00-\u9fff]")
    targets: list[Path] = [REPO_ROOT / "main.py"]
    for folder in ("ui", "core"):
        for p in sorted((REPO_ROOT / folder).rglob("*.py")):
            if p.name in ("i18n.py", "i18n_catalog.py", "i18n_catalog_p2g.py", "system_probe.py"):
                continue
            targets.append(p)

    missing: list[str] = []
    for path in targets:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        help_bodies: set[str] = set()
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == "HelpBadge") or (
                    isinstance(fn, ast.Attribute) and fn.attr == "HelpBadge"
                ):
                    if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in HELP_TRANSLATIONS:
                        for a in node.args:
                            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                help_bodies.add(a.value.strip())

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            val = node.value.strip()
            if not val or not zh_re.search(val) or val in help_bodies:
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Expr):
                gp = parents.get(parent)
                if isinstance(gp, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if gp.body and gp.body[0] is parent:
                        continue
            if val in ("简体中文", "中文", "繁體中文", "日本語", "国Ag"):
                continue
            skip = False
            cur: ast.AST | None = node
            while cur is not None:
                if isinstance(cur, ast.Call):
                    fn = cur.func
                    fn_name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                    if fn_name in ("debug", "info", "warning", "error", "exception", "critical", "tr", "tr_telemetry", "add_argument"):
                        skip = True
                        break
                cur = parents.get(cur)
            if skip or isinstance(parent, ast.JoinedStr):
                continue
            from core.i18n import UI_PHRASE_MAP
            entry = UI_PHRASE_MAP.get(val)
            for lang in ("en", "ja", "ko"):
                if entry is not None and lang in entry:
                    continue
                if translate_text(val, lang) == val:
                    missing.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} [{lang}] {val!r}")
                    break

    assert not missing, f"Untranslated Chinese literals ({len(missing)}): {missing[:10]}"


def test_g2_chroma_narrow_window_heatmap_visible_and_headers_not_elided() -> None:
    from PySide6 import QtCore, QtWidgets
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentWidget(win.chroma_widget)
        for lang in ("zh", "en"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.resize(874, 453)
            win.show()
            app.processEvents()

            scroll = win.chroma_widget.findChild(QtWidgets.QScrollArea)
            assert scroll is not None
            vp = scroll.viewport()
            bar = win.chroma_widget.chroma_bar_plot
            hist = win.chroma_widget.chroma_hist_plot
            assert hist.height() >= 96, f"[{lang}] heatmap height {hist.height()} < 96"
            hist_br = hist.mapTo(vp, QtCore.QPoint(hist.width(), hist.height()))
            assert hist_br.y() <= vp.height() + 2, f"[{lang}] heatmap bottom {hist_br.y()} > viewport {vp.height()}"
            bar_tl = bar.mapTo(vp, QtCore.QPoint(0, 0))
            assert bar_tl.y() >= -1
            for hdr in (win.chroma_widget._chord_hdr, win.chroma_widget._key_hdr, win.chroma_widget._rhythm_hdr):
                assert "…" not in hdr.eyebrow_lbl.text() and "..." not in hdr.eyebrow_lbl.text()
                assert "…" not in hdr.title_lbl.text() and "..." not in hdr.title_lbl.text()
    finally:
        win.close()
        mixer.close()


def test_g3_ab_more_expanded_all_buttons_inside_window() -> None:
    from PySide6 import QtCore, QtWidgets
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        for lang in ("zh", "en"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            for ww, hh in ((874, 453), (1093, 566)):
                win.resize(ww, hh)
                win.show()
                if not win.ab_more_btn.isChecked():
                    win.ab_more_btn.click()
                app.processEvents()

                for w in win._bottom_dock.findChildren(QtWidgets.QPushButton):
                    if not w.isVisible() or w.width() <= 0 or w.height() <= 0:
                        continue
                    tl = w.mapTo(win, QtCore.QPoint(0, 0))
                    br = w.mapTo(win, QtCore.QPoint(w.width(), w.height()))
                    assert tl.x() >= -1 and tl.y() >= -1, f"[{lang}] {ww}x{hh} {w.text()!r} tl={tl}"
                    assert br.x() <= win.width() + 1 and br.y() <= win.height() + 1, (
                        f"[{lang}] {ww}x{hh} {w.text()!r} br={br} > win=({win.width()},{win.height()})"
                    )
    finally:
        win.close()
        mixer.close()


def test_g4_ai_launch_always_gives_feedback_or_starts_and_logs_rejection(caplog, tmp_path) -> None:
    import main as main_mod

    banners: list[tuple[str, str | None]] = []

    class _FakeWindow:
        def show_banner_message(self, text: str, tone: str | None = None) -> None:
            banners.append((text, tone))

    class _FakeLive:
        is_active = True
        is_starting = False

    class _FakeCtrl:
        live_separator = _FakeLive()
        window = _FakeWindow()

    with caplog.at_level(logging.WARNING):
        main_mod.ListenScopeController._on_start_ai_separation(_FakeCtrl(), "4stem", "htdemucs_4stem", 6, True)

    assert banners and banners[0][1] == "warn"
    assert any("ai launch rejected reason=live_separator_active" in r.message for r in caplog.records)


def test_g5_english_narrow_details_source_combo_mixer_empty_and_loopback_tooltip() -> None:
    from PySide6 import QtCore, QtWidgets
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        win.resize(874, 453)
        win.show()
        win.tabs.setCurrentWidget(win.mixer_widget)
        app.processEvents()

        empty_card = win.mixer_widget._empty_tracks_card
        for lbl in empty_card.findChildren(QtWidgets.QLabel):
            if lbl.isVisible() and lbl is win.mixer_widget._empty_tracks_hint_lbl:
                assert lbl.wordWrap(), f"Mixer empty label {lbl.text()!r} must have wordWrap=True"
                br = lbl.mapTo(win, QtCore.QPoint(lbl.width(), lbl.height()))
                assert br.x() <= win.width() + 2, f"Mixer empty label clipped at {br.x()} > {win.width()}"

        long_name = "[Fallback] System WASAPI Loopback (Speakers - Very Long Audio Device Name For Testing)"
        win.source_combo.clear()
        win.source_combo.addItem(long_name, {"kind": "system_loopback"})
        win.source_combo.setCurrentIndex(0)
        app.processEvents()
        assert long_name in win.source_combo.toolTip()
    finally:
        win.close()
        mixer.close()


def test_g6_debug_restart_hook_env_and_strips_from_child(monkeypatch) -> None:
    import main as main_mod

    assert main_mod._DEBUG_RESTART_ENV == "LISTENSCOPE_DEBUG_RESTART_AFTER_S"
    monkeypatch.setenv("LISTENSCOPE_DEBUG_RESTART_AFTER_S", "2")
    captured_env: list[dict[str, str] | None] = []

    def _fake_launch(cmd, **kwargs):
        captured_env.append(kwargs.get("env"))
        return None

    monkeypatch.setattr(main_mod, "launch_detached", _fake_launch)

    class _FakeWin:
        def force_quit(self):
            pass

    class _FakeCtrl:
        work_dir = REPO_ROOT
        _settings_path = REPO_ROOT / "settings.json"
        window = _FakeWin()

        def _build_persisted_settings(self):
            return {}

        def shutdown(self):
            pass

    monkeypatch.setattr(main_mod, "save_settings", lambda *a, **kw: None)
    main_mod.ListenScopeController.restart_application(_FakeCtrl())
    assert captured_env and captured_env[0] is not None
    assert "LISTENSCOPE_DEBUG_RESTART_AFTER_S" not in captured_env[0]


def test_g2_g3_scaled_125_1093x566() -> None:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = "1.25"
    code = (
        "from PySide6 import QtCore, QtWidgets\n"
        "from audio.playback import StemMixerEngine\n"
        "from core.appearance import Appearance\n"
        "from core.config import AIConfig, ResourceLimits\n"
        "from core.system_probe import probe_system\n"
        "from ui.main_window import ListenScopeMainWindow\n"
        "app = QtWidgets.QApplication([])\n"
        "m = StemMixerEngine(sample_rate=48000, channels=2)\n"
        "w = ListenScopeMainWindow(hardware_report=probe_system(), resource_limits=ResourceLimits(), ai_config=AIConfig(), mixer_engine=m)\n"
        "for lang in ('zh', 'en'):\n"
        "    w.apply_appearance(Appearance(theme_mode='light', language=lang))\n"
        "    for ww, hh in ((874, 453), (1093, 566)):\n"
        "        if w.ab_more_btn.isChecked(): w.ab_more_btn.click()\n"
        "        w.resize(ww, hh); w.show(); w.tabs.setCurrentWidget(w.chroma_widget); app.processEvents()\n"
        "        vp = w.chroma_widget.findChild(QtWidgets.QScrollArea).viewport()\n"
        "        hist = w.chroma_widget.chroma_hist_plot\n"
        "        assert hist.height() >= 96 and hist.mapTo(vp, QtCore.QPoint(hist.width(), hist.height())).y() <= vp.height() + 2\n"
        "        w.ab_more_btn.click()\n"
        "        app.processEvents()\n"
        "        for b in w._bottom_dock.findChildren(QtWidgets.QPushButton):\n"
        "            if b.isVisible() and b.width() > 0 and b.height() > 0:\n"
        "                br = b.mapTo(w, QtCore.QPoint(b.width(), b.height()))\n"
        "                assert br.x() <= w.width() + 1 and br.y() <= w.height() + 1, f'[{lang}] {ww}x{hh} {b.text()!r} br={br}'\n"
        "w.close(); m.close()\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=45)
    assert proc.returncode == 0, f"1.25x G2/G3 check failed: {proc.stderr}"

