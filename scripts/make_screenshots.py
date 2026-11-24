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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from analysis.worker import AnalysisWorker
from audio.playback import StemMixerEngine
from audio.ring_buffer import FixedRingBuffer
from core.config import AIConfig, AnalysisConfig, AudioConfig, ResourceLimits
from core.models import (
    AnalysisSnapshot,
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


def capture_screenshots(
    out_dir: Path,
    *,
    prefix: str = "p2e_before_",
    suffix: str = "",
    max_kb: int = 200,
) -> list[Path]:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    snap, spec_mat = _build_synthetic_snapshot()
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

        chroma_hist = np.full((12, 45), 0.15, dtype=np.float32)
        chroma_hist[4, :] = 0.92  # E
        chroma_hist[1, :] = 0.85  # C#
        chroma_hist[8, :] = 0.80  # G#

        def _feed_and_flush() -> None:
            win.update_analysis_snapshot(snap, spec_mat, chroma_hist)
            win.update_resource_snapshot(res_snap, [], [])
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture offscreen synthetic screenshots for ListenScope.")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs" / "review" / "screens")
    parser.add_argument("--prefix", type=str, default="p2e_before_")
    parser.add_argument("--suffix", type=str, default="")
    parser.add_argument("--max-kb", type=int, default=200)
    parser.add_argument("--design-sheet", action="store_true", help="Generate design token & component state sheet")
    args = parser.parse_args(argv)
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
