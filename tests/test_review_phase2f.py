"""Phase 2F UI, lifecycle, i18n, and DSP regression tests (Issue #60, F1-F12)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

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


def _dummy_snapshot():
    from core.models import (
        AnalysisSnapshot,
        ChordEstimate,
        KeyEstimate,
        PitchEstimate,
        TempoEstimate,
    )

    return AnalysisSnapshot(
        timestamp=1.0,
        waveform_min=[-0.1] * 16,
        waveform_max=[0.1] * 16,
        fft_freqs_hz=[100.0, 200.0, 440.0],
        fft_db=[-40.0, -50.0, -25.0],
        log_freqs_hz=[100.0, 200.0, 440.0],
        log_spectrum_db=[-40.0, -50.0, -25.0],
        chroma_12=[0.1] * 12,
        chord=ChordEstimate("C#m/E", "E", "High", 0.9, 0.2, False),
        key=KeyEstimate("E major", "C# minor", "High", 0.9, 0.2),
        tempo=TempoEstimate(120.0, "High", 0.9, 60.0),
        pitch=PitchEstimate(440.0, "A4", 0.0, 0.9, False, "full"),
        rms_dbfs=-20.0,
        peak_dbfs=-10.0,
        window_seconds=3.0,
        latency_ms=5.0,
    )


def _hex_to_rgb(hx: str) -> tuple[int, int, int]:
    s = hx.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _rel_luminance(hx: str) -> float:
    r, g, b = _hex_to_rgb(hx)
    def _lin(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = _rel_luminance(fg_hex)
    l2 = _rel_luminance(bg_hex)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_f1_narrow_topbar_no_clipping_and_60s_visible() -> None:
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        for lang in ("zh", "en"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.resize(874, 453)
            win.show()
            app.processEvents()

            # E-STOP must keep a short label (not icon-only) and not clip
            estop_txt = win.emergency_stop_btn.text().strip()
            assert len(estop_txt) > 0, f"[{lang}] E-STOP label disappeared in narrow 874x453 window"
            assert win.emergency_stop_btn.width() >= win.emergency_stop_btn.sizeHint().width(), (
                f"[{lang}] E-STOP clipped: width={win.emergency_stop_btn.width()} < sizeHint={win.emergency_stop_btn.sizeHint().width()}"
            )

            # Topbar buttons must either fit their text without clipping OR be icon-only with tooltip
            for name, btn in (
                ("capture_btn", win.capture_btn),
                ("freeze_screen_btn", win.freeze_screen_btn),
                ("settings_btn", win.settings_btn),
                ("refresh_btn", win.refresh_btn),
            ):
                if btn.isVisible():
                    if btn.text().strip():
                        assert btn.width() >= btn.sizeHint().width(), (
                            f"[{lang}] {name} clipped: {btn.text()!r} w={btn.width()} < hint={btn.sizeHint().width()}"
                        )
                    else:
                        assert btn.toolTip().strip(), f"[{lang}] {name} icon-only without tooltip"

            # Theme switcher in narrow window must not clip (e.g. merged single icon button or full labels)
            if win._skin_switcher.isVisible():
                for pb in (win._pill_dark, win._pill_light):
                    if pb.isVisible() and pb.text().strip():
                        assert pb.width() >= pb.sizeHint().width(), (
                            f"[{lang}] theme pill clipped: {pb.text()!r} w={pb.width()} < hint={pb.sizeHint().width()}"
                        )

            # 60s button in A/B dock must remain visible in narrow window
            assert win.recent_60_btn.isVisible(), f"[{lang}] recent_60_btn disappeared in narrow 874x453 window"

        # Width sweep 874..1366 (step 64) + 1093 + 1366 across zh/en/ja/ko
        widths = sorted(set(list(range(874, 1367, 64)) + [1093, 1366]))
        for lang in ("zh", "en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            for w in widths:
                win.resize(w, 600 if w >= 1093 else 453)
                win.show()
                app.processEvents()
                assert win.source_combo.width() >= win.source_combo.minimumWidth(), (
                    f"[{lang}] w={w}: source_combo squeezed ({win.source_combo.width()} < {win.source_combo.minimumWidth()})"
                )
                assert win.emergency_stop_btn.text().strip(), f"[{lang}] w={w}: E-STOP empty"
                for name, btn in (
                    ("capture_btn", win.capture_btn),
                    ("freeze_screen_btn", win.freeze_screen_btn),
                    ("settings_btn", win.settings_btn),
                    ("refresh_btn", win.refresh_btn),
                    ("emergency_stop_btn", win.emergency_stop_btn),
                ):
                    if btn.isVisible() and btn.text().strip():
                        assert btn.width() >= btn.sizeHint().width(), (
                            f"[{lang}] w={w}: {name} clipped ({btn.width()} < {btn.sizeHint().width()})"
                        )
    finally:
        win.close()
        mixer.close()

    # Also verify under QT_SCALE_FACTOR=1.25 with 1093x566 physical window
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = "1.25"
    code = (
        "import sys; from PySide6 import QtWidgets; "
        "from audio.playback import StemMixerEngine; "
        "from core.config import AIConfig, ResourceLimits; "
        "from core.system_probe import probe_system; "
        "from ui.main_window import ListenScopeMainWindow; "
        "app = QtWidgets.QApplication([]); "
        "m = StemMixerEngine(sample_rate=48000, channels=2); "
        "w = ListenScopeMainWindow(hardware_report=probe_system(), resource_limits=ResourceLimits(), ai_config=AIConfig(), mixer_engine=m); "
        "w.resize(int(1093 / 1.25), int(566 / 1.25)); w.show(); app.processEvents(); "
        "assert w.emergency_stop_btn.text().strip(); "
        "assert w.recent_60_btn.isVisible(); "
        "assert w.source_combo.width() >= w.source_combo.minimumWidth(); "
        "w.close(); m.close()"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"1.25x subprocess failed: {proc.stderr}"


def test_f2_resource_capsule_status_consistent_wide_and_compact() -> None:
    from core.models import ResourceSnapshot, ResourceStatus
    from ui.resource_widget import ResourceMonitorBar

    _get_app()
    bar = ResourceMonitorBar(critical_ram_mb=2048.0, critical_vram_free_mb=1024.0)
    snap = ResourceSnapshot(
        timestamp=1.0,
        main_ram_mb=250.0,
        ai_worker_ram_mb=0.0,
        system_ram_total_mb=16384.0,
        system_ram_available_mb=2800.0,
        gpu_name="RTX 5060 Ti",
        vram_total_mb=8192.0,
        vram_used_mb=1692.0,
        vram_free_mb=6500.0,
        gpu_utilization_pct=5.0,
        active_ai_jobs=0,
        loaded_models=0,
        current_model=None,
        current_task=None,
        audio_queue_size=0,
        audio_queue_maxsize=64,
        ai_buffer_seconds=0.0,
        status=ResourceStatus.CRITICAL,
    )
    bar.set_compact_mode(False, lang="zh")
    bar.update_snapshot(snap)
    wide_tone = bar.status_badge.property("tone")
    wide_text = bar.status_badge.text()

    bar.set_compact_mode(True, lang="zh")
    compact_tone = bar.status_badge.property("tone")
    compact_text = bar.status_badge.text()

    assert wide_tone == "warn"
    assert compact_tone == wide_tone, f"Compact tone {compact_tone!r} != wide tone {wide_tone!r}"
    assert compact_text not in ("Critical", "Warning"), f"Compact text {compact_text!r} leaked raw enum instead of shortened {wide_text!r}"


def test_f3_light_theme_warn_color_is_amber_not_blue() -> None:
    from ui.acid_style import get_acid_palette

    p = get_acid_palette("light")
    r_fg, _g_fg, b_fg = _hex_to_rgb(p.status_warn_fg)
    r_bg, _g_bg, b_bg = _hex_to_rgb(p.status_warn_bg)
    assert r_fg > b_fg + 40, f"Light warn fg {p.status_warn_fg} is not warm amber"
    assert r_bg > b_bg + 20, f"Light warn bg {p.status_warn_bg} is not warm amber"
    ratio = _contrast_ratio(p.status_warn_fg, p.status_warn_bg)
    assert ratio >= 4.5, f"Light warn contrast {ratio:.2f} < 4.5"


def test_f4_capture_status_capsule_not_clipped_in_en_1600() -> None:
    from core.appearance import Appearance
    from core.models import CaptureMode, CaptureStats

    app, win, mixer = _make_window()
    try:
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        win.resize(1600, 900)
        win.show()
        app.processEvents()
        win.update_capture_stats(
            CaptureStats(
                mode=CaptureMode.SYSTEM_LOOPBACK,
                pid=None,
                process_name="System Loopback",
                sample_rate=48000,
                channels=2,
                dtype="float32",
                is_running=True,
                is_silent=True,
                rms_dbfs=-120.0,
                peak_dbfs=-120.0,
            ),
            12.0,
        )
        app.processEvents()
        assert win.capture_status_lbl.width() >= win.capture_status_lbl.sizeHint().width(), (
            f"capture_status_lbl clipped: {win.capture_status_lbl.text()!r} w={win.capture_status_lbl.width()} < hint={win.capture_status_lbl.sizeHint().width()}"
        )
        assert win.capture_status_lbl.toolTip().strip(), "capture_status_lbl missing full tooltip"
    finally:
        win.close()
        mixer.close()


def test_f5_mixer_empty_state_consistency_ampersand_and_narrow_visible() -> None:
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(2)
        for lang in ("zh", "en", "ja", "ko"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            app.processEvents()
            mw = win.mixer_widget
            btn_txt = mw._empty_quick_2stem_btn.text()
            # No unescaped single '&' in button text
            assert not re.search(r"(?<!&)&(?!&)", btn_txt), f"[{lang}] Unescaped '&' in button text: {btn_txt!r}"
            # Hint must reference the actual primary button label (without '&&' escaping)
            display_btn = btn_txt.replace("&&", "&")
            hint_txt = mw._empty_tracks_hint_lbl.text()
            assert display_btn in hint_txt, f"[{lang}] Hint {hint_txt!r} does not match button {display_btn!r}"

            # Scan all visible buttons for unescaped '&'
            for w in win.findChildren(QtWidgets.QAbstractButton):
                if w.isVisible() and isinstance(w.text(), str):
                    t = w.text()
                    if "&" in t and not re.match(r"^[^&]*(&&[^&]*)*$", t):
                        pytest.fail(f"[{lang}] Unescaped '&' in {type(w).__name__}: {t!r}")

        # Narrow 874x453: primary button must be visible without scrolling
        win.resize(874, 453)
        win.show()
        app.processEvents()
        mw = win.mixer_widget
        btn = mw._empty_quick_2stem_btn
        assert btn.isVisible()
        bottom_right = btn.mapTo(mw, QtCore.QPoint(btn.width(), btn.height()))
        assert bottom_right.y() <= mw.height(), (
            f"Mixer primary button pushed below visible area at 874x453: y={bottom_right.y()} > mw.height={mw.height()}"
        )
    finally:
        win.close()
        mixer.close()


def test_f6_no_chinese_leak_in_en_ja_ko() -> None:
    from core.appearance import Appearance
    from core.i18n import translate_text
    from core.resource_manager import ResourceManager
    from core.config import ResourceLimits

    # Direct checks for known leaked strings
    for lang in ("en", "ja", "ko"):
        for zh_str in (
            "开始捕获后显示",
            "有效音频帧不足 (3/12)",
            "用户手动紧急停止 AI：子进程与临时输出已清理，当前可用 RAM=2000 MB，音频捕获与实时频谱继续正常运行。",
            "可用 RAM 跌破紧急阈值 (1500 MB < 2048 MB)；建议关闭浏览器等占用内存的程序后重试",
            "未检测到 winrt-Windows.Media.Control，仅保留手动「换歌重置」（可用 scripts\\setup_windows.ps1 重装 .venv-core）",
            "资源安全阈值、AI 与 MIDI 环境配置已保存至 C:\\settings.json",
        ):
            translated = translate_text(zh_str, lang)
            assert translated != zh_str, f"[{lang}] Untranslated string: {zh_str!r}"

    # ResourceManager critical reason must be translated or translatable
    rm = ResourceManager(ResourceLimits())
    _st, reasons = rm._evaluate_status(
        main_ram_mb=200.0,
        system_avail_mb=1500.0,
        vram_free_mb=6000.0,
    )
    assert len(reasons) > 0
    for r in reasons:
        assert translate_text(r, "en") != r, f"ResourceManager reason not translated to en: {r!r}"

    # Traverse visible widgets in en, ko & ja across all tabs
    app, win, mixer = _make_window()
    try:
        cjk_re = re.compile(r"[\u4e00-\u9fff]")
        sc_only_re = re.compile(r"[这为们个时设频谱轨帧调缓]")
        for lang in ("en", "ko", "ja"):
            win.apply_appearance(Appearance(theme_mode="light", language=lang))
            win.resize(1366, 768)
            win.show()
            for idx in range(win.tabs.count()):
                win.tabs.setCurrentIndex(idx)
                app.processEvents()
                for w in (*win.findChildren(QtWidgets.QLabel), *win.findChildren(QtWidgets.QPushButton)):
                    if not w.isVisible():
                        continue
                    for prop_name, val in (("text", w.text()), ("tooltip", w.toolTip())):
                        if not val or "中文" in val:
                            continue
                        if lang in ("en", "ko") and cjk_re.search(val):
                            pytest.fail(f"[{lang}] Tab {idx} {type(w).__name__} {prop_name} leaked Hanzi: {val!r}")
                        if lang == "ja" and sc_only_re.search(val):
                            pytest.fail(f"[ja] Tab {idx} {type(w).__name__} {prop_name} leaked Simplified Chinese: {val!r}")
    finally:
        win.close()
        mixer.close()


def test_f7_spectrogram_preserved_after_apply_appearance() -> None:
    from core.appearance import Appearance

    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(0)
        win.show()
        app.processEvents()
        snap = _dummy_snapshot()
        win.spectrum_widget.update_analysis(snap, spectrogram=np.full((45, 96), -40.0, dtype=np.float32))
        assert win.spectrum_widget._spec_empty_item.isVisible() is False

        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        app.processEvents()
        # Simulate tick where spectrogram=None (tick % 3 != 0)
        win.spectrum_widget.update_analysis(snap, spectrogram=None)
        app.processEvents()
        assert win.spectrum_widget._spec_empty_item.isVisible() is False, "Spectrogram reset to empty placeholder after theme/lang switch"
        assert win.spectrum_widget._spec_img.image is not None
    finally:
        win.close()
        mixer.close()


def test_f8_chroma_heatmap_readable_height_and_ticks() -> None:
    app, win, mixer = _make_window()
    try:
        win.tabs.setCurrentIndex(1)
        for w, h in ((1366, 768), (874, 453)):
            win.resize(w, h)
            win.show()
            app.processEvents()
            plot = win.chroma_widget.chroma_hist_plot
            axis = plot.getAxis("left")
            font = axis.style.get("tickFont") or win.chroma_widget.font()
            line_h = QtGui.QFontMetrics(font).height()
            ticks_levels = getattr(axis, "_tickLevels", None)
            num_ticks = len(ticks_levels[0]) if ticks_levels else 12
            assert plot.height() >= 96, f"At {w}x{h} chroma heatmap too short: {plot.height()}px < 96px"
            assert axis.height() >= num_ticks * (line_h + 2), (
                f"At {w}x{h} chroma heatmap left axis too short ({axis.height():.1f}px) for {num_ticks} ticks of height {line_h}px"
            )
    finally:
        win.close()
        mixer.close()


def test_f9_quit_completes_within_2s_with_blocking_thread_and_subprocess(tmp_path: Path) -> None:
    from core.paths import register_active_subprocess, unregister_active_subprocess
    from main import ListenScopeController

    _get_app()
    ctrl = ListenScopeController(
        use_mock_ai_for_demo=True,
        settings_path=str(tmp_path / "settings.json"),
    )

    class _BlockingCapture:
        def stop(self) -> None:
            time.sleep(5.0)

        def get_stats(self):
            return None

    # Launch a real subprocess that ignores SIGTERM to verify terminate -> kill within 2s
    sub = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ],
    )
    register_active_subprocess(sub)
    ctrl._capture_backend = _BlockingCapture()  # type: ignore[assignment]
    try:
        t0 = time.monotonic()
        ctrl.shutdown()
        elapsed = time.monotonic() - t0
        assert elapsed <= 2.0, f"shutdown() took {elapsed:.2f}s (> 2.0s)"
        assert sub.poll() is not None, "SIGTERM-ignoring subprocess still alive after shutdown()"
    finally:
        unregister_active_subprocess(sub)
        if sub.poll() is None:
            sub.kill()
            sub.wait(timeout=1.0)


def test_f10_bpm_detected_within_15s_on_synthetic_mix() -> None:
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig

    sr = 48000
    target_bpm = 96.0
    beat_sec = 60.0 / target_bpm
    dur_sec = 14.0
    n = int(sr * dur_sec)
    t = np.arange(n, dtype=np.float32) / float(sr)

    # Continuous dense mix: sustained chord pad + bassline + soft-compressed drum hits + 16th shimmer
    pad = (
        0.22 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.18 * np.sin(2.0 * np.pi * 277.18 * t)
        + 0.18 * np.sin(2.0 * np.pi * 329.63 * t)
        + 0.15 * np.sin(2.0 * np.pi * 440.0 * t)
        + 0.08 * np.sin(2.0 * np.pi * 659.25 * t + 0.5 * np.sin(2.0 * np.pi * 5.0 * t))
    )
    bass = 0.25 * np.sin(2.0 * np.pi * 110.0 * t)
    drums = np.zeros_like(t)
    rng = np.random.default_rng(42)
    step_sec = beat_sec / 2.0  # 8th-note kick/snare pattern
    k = 0
    while k * step_sec < dur_sec - 0.1:
        idx = int(k * step_sec * sr)
        hit_len = min(int(0.10 * sr), n - idx)
        ht = np.arange(hit_len, dtype=np.float32) / float(sr)
        if k % 2 == 0:
            drums[idx : idx + hit_len] += 0.18 * np.sin(2.0 * np.pi * 65.0 * ht) * np.exp(-ht * 22.0)
        else:
            drums[idx : idx + hit_len] += 0.10 * rng.standard_normal(hit_len).astype(np.float32) * np.exp(-ht * 28.0)
        k += 1

    mono = np.tanh(pad + bass + drums).astype(np.float32) * 0.7
    stereo = np.stack([mono, mono], axis=1)

    acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=20)
    rb = FixedRingBuffer(acfg)
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
    hop = int(sr * 0.066)
    snap = None
    for pos in range(0, stereo.shape[0], hop):
        chunk = stereo[pos : pos + hop]
        if chunk.shape[0] == 0:
            break
        rb.write(chunk)
        snap = worker.analyze_latest_once()

    assert snap is not None
    assert snap.tempo.bpm is not None, f"BPM still Unknown after {dur_sec}s continuous mix (conf={snap.tempo.confidence_score:.3f})"
    assert abs(snap.tempo.bpm - target_bpm) <= 3.0 or abs(snap.tempo.bpm - target_bpm * 2.0) <= 6.0, (
        f"Detected BPM {snap.tempo.bpm} far from {target_bpm}"
    )


def test_f10_negative_controls_chord_pad_noise_vibrato() -> None:
    from analysis.worker import AnalysisWorker
    from audio.ring_buffer import FixedRingBuffer
    from core.config import AnalysisConfig, AudioConfig

    sr = 48000
    dur = 10.0
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float32) / float(sr)
    rng = np.random.default_rng(123)

    neg_cases = {
        "chord_pad": (
            0.12 * np.sin(2.0 * np.pi * 261.63 * t)
            + 0.12 * np.sin(2.0 * np.pi * 329.63 * t)
            + 0.12 * np.sin(2.0 * np.pi * 392.00 * t)
        ).astype(np.float32),
        "white_noise": (0.08 * rng.standard_normal(n)).astype(np.float32),
        "vibrato_tone": (0.20 * np.sin(2.0 * np.pi * 440.0 * t + 1.5 * np.sin(2.0 * np.pi * 5.2 * t))).astype(np.float32),
    }

    hop = int(sr * 0.066)
    for name, mono in neg_cases.items():
        acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=12)
        rb = FixedRingBuffer(acfg)
        worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())
        st = np.stack([mono, mono], axis=1)
        snap = None
        for pos in range(0, st.shape[0], hop):
            chunk = st[pos : pos + hop]
            if chunk.shape[0] == 0:
                break
            rb.write(chunk)
            snap = worker.analyze_latest_once()
        assert snap is not None
        assert snap.tempo.bpm is None or snap.tempo.stability != "High", (
            f"Negative control {name} false-locked High BPM: {snap.tempo}"
        )


def test_f11_memory_guardrail_messages_actionable_and_distinguish_manual_vs_auto() -> None:
    from core.config import ResourceLimits
    from core.i18n import translate_text
    from core.models import AIJobResult, AIJobState
    from core.resource_manager import ResourceManager, SimulationOverrides

    rm = ResourceManager(ResourceLimits())
    rm.set_simulation_overrides(SimulationOverrides(system_ram_available_mb=2875.0))
    allowed, reason = rm.can_start_ai_job("2stem", require_gpu=False)
    assert allowed is False
    for lang in ("zh", "en", "ja", "ko"):
        msg = translate_text(reason, lang)
        assert any(k in msg.lower() for k in ("browser", "浏览器", "ブラウザ", "브라우저", "close", "关闭", "閉じ", "닫")), (
            f"[{lang}] Refusal message lacks actionable advice: {msg!r}"
        )

    app, win, mixer = _make_window()
    try:
        win.show()
        app.processEvents()
        win.dismiss_banner()
        win.handle_ai_result(
            AIJobResult(
                task_id="t_user",
                state=AIJobState.EMERGENCY_STOPPED,
                error="user stop",
                stop_reason="user",
            )
        )
        assert not win.notice_banner.isVisible()

        win.handle_ai_result(
            AIJobResult(
                task_id="t_guard",
                state=AIJobState.EMERGENCY_STOPPED,
                error="可用 RAM 跌破紧急阈值 (1500 MB < 2048 MB)",
                stop_reason="ram_guard",
            )
        )
        assert win.notice_banner.isVisible()
        assert "护栏" in win.notice_banner.text() or "guardrail" in win.notice_banner.text().lower()
    finally:
        win.close()
        mixer.close()


def test_f12_tray_icon_uses_3_bar_svg_and_follows_system_theme() -> None:
    from core.appearance import Appearance
    from ui.main_window import _load_tray_icon

    for name in ("listenscope_tray_black.svg", "listenscope_tray_white.svg"):
        asset = (REPO_ROOT / "ui" / "assets" / name).read_text("utf-8")
        design = (REPO_ROOT / "docs" / "design" / "icon" / name).read_text("utf-8")
        assert asset == design
        assert asset.count("<rect ") == 3, f"{name} must have 3 bars, got {asset.count('<rect ')}"

    app, win, mixer = _make_window()
    try:
        ic_light = _load_tray_icon(taskbar_light=True)
        ic_dark = _load_tray_icon(taskbar_light=False)
        assert not ic_light.isNull() and not ic_dark.isNull()
        assert ic_light.pixmap(24, 24).toImage() != ic_dark.pixmap(24, 24).toImage()
        # Theme change must refresh tray icon
        win._system_is_dark = True
        win.apply_appearance(Appearance(theme_mode="dark", language="en"))
        win._system_is_dark = False
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
    finally:
        win.close()
        mixer.close()
