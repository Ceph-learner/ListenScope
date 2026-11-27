"""Offscreen synthetic screenshot generator for ListenScope UI verification (Phase 2E / Release Prep).

Uses purely synthetic deterministic audio/analysis data (no personal paths, no real song titles):
- Single tone A4 (440 Hz), E2 bass + chord pad, 120 BPM drums, C#m/E chord, E major key.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from analysis.worker import AnalysisWorker
from audio.playback import StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AnalysisConfig, AudioConfig, ResourceLimits
from core.models import (
    AnalysisSnapshot,
    CaptureMode,
    CaptureStats,
    ChordEstimate,
    KeyEstimate,
    PitchEstimate,
    ResourceSnapshot,
    ResourceStatus,
    TempoEstimate,
)
from core.system_probe import probe_system
from ui.appearance import Appearance
from ui.main_window import ListenScopeMainWindow


def _build_synthetic_snapshot() -> tuple[AnalysisSnapshot, np.ndarray]:
    """Generate a realistic deterministic AnalysisSnapshot via AnalysisWorker + synthetic C#m/E & E major."""
    sr = 48000
    acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=20)
    rb = FixedRingBuffer(acfg)
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())

    # 3.0 s of 440 Hz A4 + subtle E2 bass + 120 BPM rhythmic envelope
    dur_sec = 3.0
    n = int(sr * dur_sec)
    t = np.arange(n, dtype=np.float32) / float(sr)
    beat_env = 0.65 + 0.35 * np.power(np.maximum(0.0, np.cos(2.0 * np.pi * 1.0 * t)), 8.0)
    mono = (
        0.26 * beat_env * np.sin(2.0 * np.pi * 440.0 * t)
        + 0.14 * np.sin(2.0 * np.pi * 82.41 * t)
        + 0.08 * np.sin(2.0 * np.pi * 277.18 * t)
        + 0.08 * np.sin(2.0 * np.pi * 329.63 * t)
        + 0.08 * np.sin(2.0 * np.pi * 415.30 * t)
    ).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    step = int(round(sr * 66.67 / 1000.0))
    snap = None
    for pos in range(0, stereo.shape[0], step):
        chunk = stereo[pos : pos + step]
        if chunk.shape[0] == 0:
            break
        rb.write(chunk)
        snap = worker.analyze_latest_once()

    assert snap is not None
    # Override chord/key/tempo/pitch labels to exact Issue #42 canonical synthetic values
    snap.pitch = PitchEstimate(
        frequency_hz=440.0,
        note_name="A4",
        cents_offset=0.2,
        confidence=0.96,
        is_polyphonic=False,
        source_band="full",
    )
    snap.chord = ChordEstimate(
        primary="C#m/E",
        secondary="E",
        stability="Medium",
        correlation=0.84,
        margin=0.12,
        is_silent=False,
    )
    snap.key = KeyEstimate(
        primary="E major",
        secondary="C# minor",
        stability="High",
        correlation=0.86,
        margin=0.08,
    )
    snap.tempo = TempoEstimate(
        bpm=120.0,
        stability="High",
        confidence_score=0.82,
        alt_bpm=60.0,
    )
    spec_mat = (
        worker.spectrum.recent_spectrogram()
        if hasattr(worker, "spectrum") and hasattr(worker.spectrum, "recent_spectrogram")
        else None
    )
    return snap, spec_mat


def _ensure_ui_fonts(app: QtWidgets.QApplication) -> dict[str, str]:
    """Load platform UI fonts cleanly and return preferred sans/cjk/mono font family names."""
    if sys.platform == "win32":
        for font_file in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
            fp = Path(r"C:\Windows\Fonts") / font_file
            if fp.exists():
                QtGui.QFontDatabase.addApplicationFont(str(fp))
    families = set(QtGui.QFontDatabase.families())
    if sys.platform == "win32":
        assert any(f in families for f in ("Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI")), (
            f"Missing Windows UI fonts in QFontDatabase: {sorted(families)[:20]}"
        )

    def _pick(candidates: tuple[str, ...], fallback: str) -> str:
        for name in candidates:
            if name in families:
                return name
        return fallback

    sans = _pick(("Segoe UI", "Noto Sans", "Cantarell", "DejaVu Sans"), app.font().family())
    cjk = _pick(
        ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans", "DejaVu Sans"),
        sans,
    )
    mono = _pick(
        ("Cascadia Mono", "Cascadia Code", "Consolas", "Source Code Pro", "DejaVu Sans Mono"),
        "Monospace",
    )
    app.setFont(QtGui.QFont(cjk, 10))
    return {"sans": sans, "cjk": cjk, "mono": mono}


def _save_png_under_limit(pixmap: QtGui.QPixmap, out_path: Path, max_kb: int = 200) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use maximum PNG compression (quality=0..100 in Qt PNG means 0=max compression or -1 default)
    pixmap.save(str(out_path), "PNG", 9)
    if out_path.stat().st_size > max_kb * 1024:
        # Downscale slightly only if PNG exceeds size budget
        scaled = pixmap.scaledToWidth(
            int(pixmap.width() * 0.85),
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        scaled.save(str(out_path), "PNG", 9)


def _prepare_synthetic_main_window(
    app: QtWidgets.QApplication,
    *,
    theme_mode: str = "light",
    language: str = "zh",
    width: int = 1366,
    height: int = 768,
) -> tuple[ListenScopeMainWindow, StemMixerEngine]:
    """Create a populated ListenScopeMainWindow using deterministic synthetic audio/telemetry."""
    snap, spec_mat = _build_synthetic_snapshot()
    if spec_mat is None or spec_mat.size == 0:
        n_frames, n_bins = 450, 96
        t_idx = np.linspace(0.0, 1.0, n_frames, dtype=np.float32)[:, None]
        spec_mat = np.full((n_frames, n_bins), -78.0, dtype=np.float32)
        spec_mat[:, 20:24] = -18.0 + 6.0 * np.sin(2.0 * np.pi * 2.0 * t_idx)
        spec_mat[:, 44:47] = -12.0 + 4.0 * np.cos(2.0 * np.pi * 1.5 * t_idx)
        spec_mat[:, 56:58] = -26.0
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    res_snap = ResourceSnapshot(
        timestamp=1.0,
        main_ram_mb=320.0,
        ai_worker_ram_mb=0.0,
        system_ram_total_mb=16384.0,
        system_ram_available_mb=6200.0,
        gpu_name="Synthetic RTX GPU",
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
    cap_stats = CaptureStats(
        mode=CaptureMode.SYNTHETIC_SIMULATION,
        pid=None,
        process_name="Simulated",
        is_running=True,
        sample_rate=48000,
        channels=2,
        dtype="float32",
        rms_dbfs=-18.0,
        peak_dbfs=-6.2,
        is_silent=False,
    )
    chroma_hist = np.full((450, 12), 0.12, dtype=np.float32)
    chroma_hist[:, 4] = 0.92  # E
    chroma_hist[:, 1] = 0.85  # C#
    chroma_hist[:, 8] = 0.80  # G#

    win.apply_appearance(Appearance(theme_mode=theme_mode, language=language))
    win.tabs.setCurrentIndex(0)
    win.resize(width, height)
    win.show()
    win.update_analysis_snapshot(snap, spec_mat, chroma_hist)
    win.update_capture_stats(cap_stats, ring_available_sec=3.0)
    win.update_resource_snapshot(res_snap, [], [])
    win._acid_footer.set_telemetry(cpu_pct=4.2)
    for _ in range(4):
        app.processEvents()
    return win, mixer


def capture_screenshots(
    out_dir: Path,
    *,
    prefix: str = "p2e_before_",
    suffix: str = "",
    max_kb: int = 200,
) -> list[Path]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ensure_ui_fonts(app)
    snap, spec_mat = _build_synthetic_snapshot()
    if spec_mat is None or spec_mat.size == 0:
        n_frames, n_bins = 450, 96
        t_idx = np.linspace(0.0, 1.0, n_frames, dtype=np.float32)[:, None]
        spec_mat = np.full((n_frames, n_bins), -78.0, dtype=np.float32)
        spec_mat[:, 20:24] = -18.0 + 6.0 * np.sin(2.0 * np.pi * 2.0 * t_idx)
        spec_mat[:, 44:47] = -12.0 + 4.0 * np.cos(2.0 * np.pi * 1.5 * t_idx)
        spec_mat[:, 56:58] = -26.0
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    saved: list[Path] = []
    try:
        res_snap = ResourceSnapshot(
            timestamp=1.0,
            main_ram_mb=320.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=16384.0,
            system_ram_available_mb=6200.0,
            gpu_name="Synthetic RTX GPU",
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
        cap_stats = CaptureStats(
            mode=CaptureMode.SYNTHETIC_SIMULATION,
            pid=None,
            process_name="Simulated",
            is_running=True,
            sample_rate=48000,
            channels=2,
            dtype="float32",
            rms_dbfs=-18.0,
            peak_dbfs=-6.2,
            is_silent=False,
        )

        chroma_hist = np.full((450, 12), 0.12, dtype=np.float32)
        chroma_hist[:, 4] = 0.92  # E
        chroma_hist[:, 1] = 0.85  # C#
        chroma_hist[:, 8] = 0.80  # G#

        def _feed_and_flush() -> None:
            win.update_analysis_snapshot(snap, spec_mat, chroma_hist)
            win.update_capture_stats(cap_stats, ring_available_sec=3.0)
            win.update_resource_snapshot(res_snap, [], [])
            win._acid_footer.set_telemetry(cpu_pct=4.2)
            for _ in range(4):
                app.processEvents()

        # 1. Light 1366x768 Spectrum tab
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.tabs.setCurrentIndex(0)
        win.resize(1366, 768)
        win.show()
        _feed_and_flush()
        p1 = out_dir / f"{prefix}light_spectrum_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p1, max_kb=max_kb)
        saved.append(p1)

        # 2. Dark 1366x768 Spectrum tab (EN)
        win.apply_appearance(Appearance(theme_mode="dark", language="en"))
        win.tabs.setCurrentIndex(0)
        win.resize(1366, 768)
        _feed_and_flush()
        p2 = out_dir / f"{prefix}dark_en_spectrum_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p2, max_kb=max_kb)
        saved.append(p2)

        # 3. Light 1366x768 Chord & Tempo tab
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.tabs.setCurrentIndex(1)
        win.resize(1366, 768)
        _feed_and_flush()
        p3 = out_dir / f"{prefix}light_chord_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p3, max_kb=max_kb)
        saved.append(p3)

        # 4. Light 1366x768 Mixer empty state tab
        win.tabs.setCurrentIndex(2)
        win.resize(1366, 768)
        _feed_and_flush()
        p4 = out_dir / f"{prefix}light_mixer_empty_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p4, max_kb=max_kb)
        saved.append(p4)

        # 5. Small 1093x566 Light Spectrum tab
        win.tabs.setCurrentIndex(0)
        win.resize(1093, 566)
        _feed_and_flush()
        p5 = out_dir / f"{prefix}small_1093x566{suffix}.png"
        _save_png_under_limit(win.grab(), p5, max_kb=max_kb)
        saved.append(p5)
    finally:
        win.close()
        mixer.close()
    return saved


def capture_p2f_screenshots(
    out_dir: Path,
    *,
    prefix: str = "p2f_after_",
    suffix: str = "",
    max_kb: int = 200,
) -> list[Path]:
    """Capture Phase 2F verification screenshots (125% narrow spectrum/mixer + EN light chord)."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    snap, spec_mat = _build_synthetic_snapshot()
    if spec_mat is None or spec_mat.size == 0:
        n_frames, n_bins = 450, 96
        t_idx = np.linspace(0.0, 1.0, n_frames, dtype=np.float32)[:, None]
        spec_mat = np.full((n_frames, n_bins), -78.0, dtype=np.float32)
        spec_mat[:, 20:24] = -18.0 + 6.0 * np.sin(2.0 * np.pi * 2.0 * t_idx)
        spec_mat[:, 44:47] = -12.0 + 4.0 * np.cos(2.0 * np.pi * 1.5 * t_idx)
    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    saved: list[Path] = []
    try:
        res_snap = ResourceSnapshot(
            timestamp=1.0,
            main_ram_mb=320.0,
            ai_worker_ram_mb=0.0,
            system_ram_total_mb=16384.0,
            system_ram_available_mb=2875.0,
            gpu_name="Synthetic RTX GPU",
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
            status=ResourceStatus.CRITICAL,
        )
        cap_stats = CaptureStats(
            mode=CaptureMode.SYNTHETIC_SIMULATION,
            pid=None,
            process_name="Simulated",
            is_running=True,
            sample_rate=48000,
            channels=2,
            dtype="float32",
            rms_dbfs=-18.0,
            peak_dbfs=-6.2,
            is_silent=False,
        )
        chroma_hist = np.full((450, 12), 0.12, dtype=np.float32)
        chroma_hist[:, 4] = 0.92
        chroma_hist[:, 1] = 0.85
        chroma_hist[:, 8] = 0.80

        def _feed() -> None:
            win.update_analysis_snapshot(snap, spec_mat, chroma_hist)
            win.update_capture_stats(cap_stats, ring_available_sec=3.0)
            win.update_resource_snapshot(res_snap, [], [])
            win._acid_footer.set_telemetry(cpu_pct=4.2)
            for _ in range(4):
                app.processEvents()

        dpr = max(1.0, float(app.primaryScreen().devicePixelRatio() if app.primaryScreen() else 1.0))
        narrow_w = int(round(1093 / dpr)) if dpr > 1.05 else 874
        narrow_h = int(round(566 / dpr)) if dpr > 1.05 else 453

        # 1. Narrow 125% (874x453 logical -> 1093x566 physical) Spectrum tab
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.tabs.setCurrentIndex(0)
        win.resize(narrow_w, narrow_h)
        win.show()
        _feed()
        p1 = out_dir / f"{prefix}narrow_125_spectrum_1093x566{suffix}.png"
        _save_png_under_limit(win.grab(), p1, max_kb=max_kb)
        saved.append(p1)

        # 2. Narrow 125% (874x453 logical -> 1093x566 physical) Mixer empty state tab
        win.tabs.setCurrentIndex(2)
        win.resize(narrow_w, narrow_h)
        _feed()
        p2 = out_dir / f"{prefix}narrow_125_mixer_1093x566{suffix}.png"
        _save_png_under_limit(win.grab(), p2, max_kb=max_kb)
        saved.append(p2)

        # 3. English Light Chord tab (1366x768 logical)
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        win.tabs.setCurrentIndex(1)
        win.resize(1366, 768)
        _feed()
        p3 = out_dir / f"{prefix}light_en_chord_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p3, max_kb=max_kb)
        saved.append(p3)

        # 4. 1.25x scaled 1366x768 physical (1093x614 logical) English Light Spectrum tab
        win.apply_appearance(Appearance(theme_mode="light", language="en"))
        win.tabs.setCurrentIndex(0)
        en_1366_w = int(round(1366 / dpr)) if dpr > 1.05 else 1093
        en_1366_h = int(round(768 / dpr)) if dpr > 1.05 else 614
        win.resize(en_1366_w, en_1366_h)
        _feed()
        p4 = out_dir / f"{prefix}125_en_spectrum_1366x768{suffix}.png"
        _save_png_under_limit(win.grab(), p4, max_kb=max_kb)
        saved.append(p4)
    finally:
        win.close()
        mixer.close()
    return saved


def render_design_sheet(out_dir: Path, *, max_kb: int = 200) -> Path:
    """Render a compact visual design token & component state sheet PNG."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w, h = 960, 540
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor("#14161A"))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    p.setPen(QtGui.QColor("#CEFF18"))
    p.setFont(QtGui.QFont("Cascadia Mono", 14, QtGui.QFont.Weight.Bold))
    p.drawText(24, 38, "LISTENSCOPE DESIGN SYSTEM // TOKENS & STATES")

    swatches = [
        ("bg_canvas", "#14161A"),
        ("bg_surface", "#1C2026"),
        ("border_rim", "#2C323C"),
        ("fg_primary", "#E6EAF0"),
        ("accent_dark", "#CEFF18"),
        ("accent_light", "#00A878"),
        ("danger", "#C42B1C"),
    ]
    for i, (name, col) in enumerate(swatches):
        x = 24 + i * 130
        p.fillRect(x, 64, 112, 56, QtGui.QColor(col))
        p.setPen(QtGui.QColor("#2C323C"))
        p.drawRect(x, 64, 112, 56)
        p.setPen(QtGui.QColor("#E6EAF0"))
        p.setFont(QtGui.QFont("Cascadia Mono", 9))
        p.drawText(x, 136, f"{name} {col}")

    p.setPen(QtGui.QColor("#B4BECB"))
    p.setFont(QtGui.QFont("Microsoft YaHei UI", 11))
    p.drawText(24, 180, "Spacing: 4/8/12/16/24/32 px   |   Radius: 0/2/4 px   |   Type: 11/12/13/16/20/28 px")
    p.drawText(24, 210, "Fonts: Segoe UI / Microsoft YaHei UI + Cascadia Mono / Consolas (OS fonts, unbundled)")
    p.end()

    out_path = out_dir / "design_sheet.png"
    _save_png_under_limit(pm, out_path, max_kb=max_kb)
    app.processEvents()
    return out_path


def capture_settings_ai(out_path: Path, *, max_kb: int = 250) -> Path:
    """Capture 2E-R light-theme SettingsDialog on the 'AI 与 MIDI 环境' category."""
    from ui.settings_dialog import SettingsDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    report = probe_system()
    report.gpu_name = "NVIDIA GeForce RTX 5060 Ti"
    report.vram_total_mb = 8192.0
    report.vram_free_mb = 7168.0
    report.gpu_ai_ready = True

    mixer = StemMixerEngine(sample_rate=48000, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=report,
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )
    try:
        app_cfg = Appearance(theme_mode="light", language="zh")
        win.apply_appearance(app_cfg)
        dlg = SettingsDialog(
            hardware_report=report,
            resource_limits=ResourceLimits(),
            ai_config=AIConfig(),
            ai_python_executable=r"C:\ListenScope\.venv-ai\Scripts\python.exe",
            midi_python_executable=r"C:\ListenScope\.venv-midi\Scripts\python.exe",
            appearance=app_cfg,
            close_behavior="ask",
            acid_variant=win._acid_variant or "",
            parent=win,
        )
        try:
            dlg.open_category("midi")
            dlg.resize(980, 680)
            dlg.show()
            for _ in range(4):
                app.processEvents()
            _save_png_under_limit(dlg.grab(), out_path, max_kb=max_kb)
        finally:
            dlg.close()
    finally:
        win.close()
        mixer.close()
    return out_path


def capture_demo_gif(out_path: Path, *, width: int = 860, max_kb: int = 2900) -> Path:
    """Capture a ~10s light-theme synthetic demo GIF (width=860, <3 MB) across 2E-R tabs."""
    from PIL import Image

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    sr = 48000
    acfg = AudioConfig(sample_rate=sr, channels=2, ring_buffer_seconds=20)
    rb = FixedRingBuffer(acfg)
    worker = AnalysisWorker(rb, audio_config=acfg, analysis_config=AnalysisConfig())

    mixer = StemMixerEngine(sample_rate=sr, channels=2)
    win = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=mixer,
    )

    res_snap = ResourceSnapshot(
        timestamp=1.0,
        main_ram_mb=310.0,
        ai_worker_ram_mb=0.0,
        system_ram_total_mb=16384.0,
        system_ram_available_mb=6240.0,
        gpu_name="Synthetic RTX GPU",
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
    cap_stats = CaptureStats(
        mode=CaptureMode.SYNTHETIC_SIMULATION,
        pid=None,
        process_name="Simulated",
        is_running=True,
        sample_rate=sr,
        channels=2,
        dtype="float32",
        rms_dbfs=-18.0,
        peak_dbfs=-6.2,
        is_silent=False,
    )

    chords_seq = [
        ("C#m/E", "E", 440.0, "A4", [82.41, 277.18, 329.63, 415.30], (4, 1, 8)),
        ("A", "F#m", 440.0, "A4", [110.0, 220.0, 277.18, 329.63], (9, 1, 4)),
        ("E", "C#m", 329.63, "E4", [82.41, 164.81, 246.94, 329.63], (4, 8, 11)),
        ("B", "G#m", 493.88, "B4", [123.47, 246.94, 311.13, 369.99], (11, 3, 6)),
    ]

    frames_pil: list[Image.Image] = []
    chroma_hist = np.full((45, 12), 0.10, dtype=np.float32)

    def _grab_pil() -> Image.Image:
        pm = win.grab()
        img = pm.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        w0, h0 = img.width(), img.height()
        ptr = img.constBits()
        pil_im = Image.frombuffer("RGBA", (w0, h0), bytes(ptr), "raw", "RGBA", 0, 1).convert("RGB")
        new_h = int(round(h0 * (width / float(w0))))
        return pil_im.resize((width, new_h), Image.Resampling.LANCZOS)

    try:
        win.apply_appearance(Appearance(theme_mode="light", language="zh"))
        win.resize(1280, 720)
        win.show()
        win.update_resource_snapshot(res_snap, [], [])
        win.update_capture_stats(cap_stats, 1.5)

        # Warm up 1.5s of audio first so buffer/waveform is already populated
        step_n = int(round(sr * 0.25))
        t_cursor = 0.0
        for _ in range(6):
            t = t_cursor + np.arange(step_n, dtype=np.float32) / float(sr)
            t_cursor += 0.25
            mono = (0.24 * np.sin(2.0 * np.pi * 440.0 * t) + 0.14 * np.sin(2.0 * np.pi * 82.41 * t)).astype(np.float32)
            rb.write(np.stack([mono, mono], axis=1))
            worker.analyze_latest_once()

        # 40 frames x 250ms = 10.0 seconds total
        # Frames 0..17: Tab 0 (Spectrum & Waveform), 18..31: Tab 1 (Chords & Key), 32..39: Tab 2 (Mixer empty + A/B)
        for idx in range(40):
            if idx == 0:
                win.tabs.setCurrentIndex(0)
            elif idx == 18:
                win.tabs.setCurrentIndex(1)
            elif idx == 32:
                win.tabs.setCurrentIndex(2)

            c_prim, c_sec, f0, note_n, freqs, pcs = chords_seq[(idx // 5) % len(chords_seq)]
            t = t_cursor + np.arange(step_n, dtype=np.float32) / float(sr)
            t_cursor += 0.25
            beat_env = 0.55 + 0.45 * np.power(np.maximum(0.0, np.cos(2.0 * np.pi * 1.0 * t)), 6.0)
            mono = np.zeros(step_n, dtype=np.float32)
            for k, f in enumerate(freqs):
                mono += (0.18 if k == 0 else 0.10) * beat_env * np.sin(2.0 * np.pi * f * t)
            rb.write(np.stack([mono, mono], axis=1))
            snap = worker.analyze_latest_once()

            snap.pitch = PitchEstimate(
                frequency_hz=f0,
                note_name=note_n,
                cents_offset=round(float(np.sin(idx * 0.4) * 1.8), 1),
                confidence=0.95,
                is_polyphonic=False,
                source_band="full",
            )
            snap.chord = ChordEstimate(
                primary=c_prim,
                secondary=c_sec,
                stability="High" if idx % 5 >= 1 else "Medium",
                correlation=0.86,
                margin=0.14,
                is_silent=False,
            )
            snap.key = KeyEstimate(
                primary="E major",
                secondary="C# minor",
                stability="High",
                correlation=0.87,
                margin=0.09,
            )
            snap.tempo = TempoEstimate(bpm=120.0, stability="High", confidence_score=0.84, alt_bpm=60.0)
            snap.window_seconds = round(min(120.0, 1.5 + (idx + 1) * 0.25), 1)
            snap.latency_ms = 3.8

            chroma_hist = np.roll(chroma_hist, -1, axis=0)
            chroma_hist[-1, :] = 0.08
            for pc in pcs:
                chroma_hist[-1, pc] = 0.90

            spec_mat = np.full((90, 96), -82.0, dtype=np.float32)
            for b_idx in (16, 40, 56):
                spec_mat[:, max(0, b_idx - 1) : min(96, b_idx + 2)] = -18.0

            win.update_analysis_snapshot(snap, spec_mat, chroma_hist)
            win.update_capture_stats(cap_stats, snap.window_seconds)
            for _ in range(3):
                app.processEvents()
            frames_pil.append(_grab_pil())
    finally:
        win.close()
        mixer.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Quantize with a shared adaptive palette for clean, compact GIF (<3 MB)
    quantized = [f.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames_pil]
    quantized[0].save(
        str(out_path),
        save_all=True,
        append_images=quantized[1:],
        duration=250,
        loop=0,
        optimize=True,
    )
    if out_path.stat().st_size > max_kb * 1024:
        quantized = [f.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames_pil]
        quantized[0].save(
            str(out_path),
            save_all=True,
            append_images=quantized[1:],
            duration=250,
            loop=0,
            optimize=True,
        )
    return out_path


def capture_social_preview(out_path: Path, *, max_kb: int = 1024) -> Path:
    """Render an exact 1280x640 light-theme social preview combining official branding and live UI."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fonts = _ensure_ui_fonts(app)

    win, mixer = _prepare_synthetic_main_window(
        app,
        theme_mode="light",
        language="zh",
        width=1366,
        height=768,
    )
    try:
        ui_pm = win.grab()
    finally:
        win.close()
        mixer.close()

    canvas_w, canvas_h = 1280, 640
    canvas = QtGui.QImage(canvas_w, canvas_h, QtGui.QImage.Format.Format_ARGB32)
    canvas.fill(QtGui.QColor("#EEF2F6"))

    p = QtGui.QPainter(canvas)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)

    # Subtle engineering grid background matching light Acid Telemetry canvas
    p.setPen(QtGui.QPen(QtGui.QColor("#DCE3EC"), 1))
    for gx in range(32, canvas_w, 32):
        p.drawLine(gx, 0, gx, canvas_h)
    for gy in range(32, canvas_h, 32):
        p.drawLine(0, gy, canvas_w, gy)

    # Top & bottom hairline accent bars
    p.fillRect(0, 0, 760, 6, QtGui.QColor("#007A57"))
    p.fillRect(760, 0, 280, 6, QtGui.QColor("#0284C7"))
    p.fillRect(1040, 0, 240, 6, QtGui.QColor("#090D14"))
    p.fillRect(0, canvas_h - 4, canvas_w, 4, QtGui.QColor("#007A57"))

    # Right-side framed light-theme UI screenshot (852x479 -> 16:9 from 1366x768)
    shot_w = 852
    shot_h = round(shot_w * ui_pm.height() / max(1, ui_pm.width()))
    shot_x = canvas_w - 38 - shot_w
    shot_y = (canvas_h - shot_h) // 2

    # Crisp multi-step elevation shadow behind the UI window
    for offset, alpha in ((10, 16), (6, 24), (2, 36)):
        p.fillRect(
            shot_x + offset,
            shot_y + offset,
            shot_w,
            shot_h,
            QtGui.QColor(9, 13, 20, alpha),
        )

    scaled_ui = ui_pm.scaled(
        shot_w,
        shot_h,
        QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    p.drawPixmap(shot_x, shot_y, scaled_ui)
    p.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
    p.drawRect(shot_x, shot_y, shot_w, shot_h)

    # Left brand column (x=40..356)
    brand_x = 42
    brand_w = shot_x - brand_x - 28

    # Official light app icon rendered from SVG
    svg_path = REPO_ROOT / "ui" / "assets" / "listenscope_master_light.svg"
    renderer = QtSvg.QSvgRenderer(str(svg_path))
    icon_size = 92
    icon_y = 84
    renderer.render(p, QtCore.QRectF(brand_x, icon_y, icon_size, icon_size))

    # Bold application title
    title_y = icon_y + icon_size + 24
    title_font = QtGui.QFont(fonts["sans"], 34, QtGui.QFont.Weight.Bold)
    title_font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, -0.5)
    p.setFont(title_font)
    p.setPen(QtGui.QColor("#090D14"))
    p.drawText(QtCore.QRectF(brand_x, title_y, brand_w, 48), QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, "ListenScope")

    # Dual-tone accent divider
    div_y = title_y + 56
    p.fillRect(brand_x, div_y, 56, 4, QtGui.QColor("#007A57"))
    p.fillRect(brand_x + 62, div_y, 22, 4, QtGui.QColor("#0284C7"))

    # Clean subtitle (ZH + EN) using verified installed CJK/sans fonts
    sub_y = div_y + 18
    sub_zh_font = QtGui.QFont(fonts["cjk"], 15, QtGui.QFont.Weight.DemiBold)
    p.setFont(sub_zh_font)
    p.setPen(QtGui.QColor("#0F172A"))
    p.drawText(
        QtCore.QRectF(brand_x, sub_y, brand_w, 52),
        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.TextFlag.TextWordWrap,
        "实时听歌分析 · A/B 慢放\n本地 AI 分轨与扒谱工作台",
    )

    sub_en_font = QtGui.QFont(fonts["sans"], 11, QtGui.QFont.Weight.Normal)
    p.setFont(sub_en_font)
    p.setPen(QtGui.QColor("#475569"))
    p.drawText(
        QtCore.QRectF(brand_x, sub_y + 56, brand_w, 40),
        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.TextFlag.TextWordWrap,
        "Offline Windows Audio Analysis, A/B Loop & Stem Practice",
    )

    # Compact telemetry highlight chips
    chips = [
        ("SPECTRUM & F0", "实时频谱 · 音准刻度"),
        ("CHORD · KEY · BPM", "24 调和弦 · 移调联动"),
        ("120s A/B · STEMS", "AI 分轨 · Cubase MIDI"),
    ]
    chip_y = 414
    chip_h = 44
    chip_gap = 10
    tag_font = QtGui.QFont(fonts["mono"], 9, QtGui.QFont.Weight.Bold)
    desc_font = QtGui.QFont(fonts["cjk"], 11, QtGui.QFont.Weight.Normal)
    for tag, desc in chips:
        p.fillRect(brand_x, chip_y, brand_w, chip_h, QtGui.QColor("#FFFFFF"))
        p.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 1))
        p.drawRect(brand_x, chip_y, brand_w, chip_h)
        p.fillRect(brand_x, chip_y, 4, chip_h, QtGui.QColor("#007A57"))

        p.setFont(tag_font)
        p.setPen(QtGui.QColor("#007A57"))
        p.drawText(QtCore.QRectF(brand_x + 12, chip_y + 4, brand_w - 18, 16), QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, tag)

        p.setFont(desc_font)
        p.setPen(QtGui.QColor("#1E293B"))
        p.drawText(QtCore.QRectF(brand_x + 12, chip_y + 21, brand_w - 18, 20), QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, desc)

        chip_y += chip_h + chip_gap

    p.end()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_path), "PNG", 9)
    max_bytes = int(max_kb) * 1024
    if out_path.stat().st_size > max_bytes:
        from PIL import Image

        with Image.open(out_path) as im:
            quant = im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
            quant.save(out_path, format="PNG", optimize=True)
    assert out_path.stat().st_size <= max_bytes, (
        f"Social preview exceeds size budget: {out_path.stat().st_size} > {max_bytes}"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture offscreen synthetic screenshots for ListenScope.")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs" / "review" / "screens")
    parser.add_argument("--prefix", type=str, default="p2e_before_")
    parser.add_argument("--suffix", type=str, default="")
    parser.add_argument("--max-kb", type=int, default=200)
    parser.add_argument("--design-sheet", action="store_true", help="Generate design token & component state sheet")
    parser.add_argument("--p2f", action="store_true", help="Generate Phase 2F verification screenshots")
    parser.add_argument("--settings-ai", type=Path, default=None, help="Output path for Settings AI & MIDI PNG")
    parser.add_argument("--demo-gif", type=Path, default=None, help="Output path for ~10s 860px light demo GIF")
    parser.add_argument("--social-preview", type=Path, default=None, help="Output path for 1280x640 light social preview PNG")
    args = parser.parse_args(argv)
    if args.p2f:
        pfx = "p2f_after_" if args.prefix == "p2e_before_" else args.prefix
        paths = capture_p2f_screenshots(args.out_dir, prefix=pfx, suffix=args.suffix, max_kb=args.max_kb)
        for p in paths:
            print(f"{p} ({p.stat().st_size / 1024.0:.1f} KB)")
        return 0
    if args.settings_ai is not None:
        out = capture_settings_ai(args.settings_ai)
        print(f"{out} ({out.stat().st_size / 1024.0:.1f} KB)")
        return 0
    if args.demo_gif is not None:
        out = capture_demo_gif(args.demo_gif)
        print(f"{out} ({out.stat().st_size / 1024.0:.1f} KB)")
        return 0
    if args.social_preview is not None:
        out = capture_social_preview(args.social_preview)
        print(f"{out} ({out.stat().st_size / 1024.0:.1f} KB)")
        return 0
    if args.design_sheet:
        sheet = render_design_sheet(args.out_dir, max_kb=args.max_kb)
        print(f"{sheet} ({sheet.stat().st_size / 1024.0:.1f} KB)")
        return 0
    paths = capture_screenshots(args.out_dir, prefix=args.prefix, suffix=args.suffix, max_kb=args.max_kb)
    for p in paths:
        print(f"{p} ({p.stat().st_size / 1024.0:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
