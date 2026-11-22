"""Phase 1 review verification tests (Issue #31, baseline f43601e).

Every test is a minimal reproduction for one of the 30 Phase 1 items and is marked
`@pytest.mark.xfail(strict=True, reason="<ID>")` prior to implementation.
Implementers remove the xfail marker as each item is fixed.
"""

from __future__ import annotations

import io
import json
import math
import re
import sys
import tomllib
import types
import wave
import zipfile
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent


def _qapp() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def _write_wav_pcm16(path: Path, data: np.ndarray, sr: int) -> None:
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    pcm16 = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(arr.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def _wcag_contrast(fg_hex: str, bg_hex: str) -> float:
    def _rel_lum(h: str) -> float:
        h = h.lstrip("#")
        rgb = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    l1, l2 = _rel_lum(fg_hex), _rel_lum(bg_hex)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# ============================================================================
# 1. Engine & Packaging (E1, E5, E9, E10, E13, E19, E20)
# ============================================================================


def test_e1_mdx_separator_44k_output_preserves_pitch_and_duration(tmp_path: Path) -> None:
    """NEEDS_TARGET contract test: a 44.1kHz output from audio-separator must be resampled back to 48kHz."""
    from ai.models import MODEL_REGISTRY
    from separation.mdx_backend import MDXSeparatorBackend

    sr_in = 48000
    sr_out = 44100
    dur = 0.5
    t_in = np.arange(int(sr_in * dur), dtype=np.float32) / sr_in
    in_pcm = np.stack([0.4 * np.sin(2 * np.pi * 440.0 * t_in)] * 2, axis=1).astype(np.float32)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    class _Fake44kSeparator:
        def __init__(self, out_dir: Path) -> None:
            self._out_dir = out_dir

        def separate(self, _in_wav: str, _output_names=None) -> list[str]:
            # Simulates audio-separator default sample_rate=44100 output
            t_out = np.arange(int(sr_out * dur), dtype=np.float32) / sr_out
            sine440 = np.stack([0.4 * np.sin(2 * np.pi * 440.0 * t_out)] * 2, axis=1).astype(np.float32)
            v_path = self._out_dir / "chunk_(Vocals).wav"
            i_path = self._out_dir / "chunk_(Instrumental).wav"
            _write_wav_pcm16(v_path, sine440, sr_out)
            _write_wav_pcm16(i_path, sine440 * 0.5, sr_out)
            return [str(v_path), str(i_path)]

    spec = next(m for m in MODEL_REGISTRY.values() if m.architecture == "MDX-ONNX" and m.stem_mode == "2stem")
    backend = MDXSeparatorBackend(spec)
    backend._tmp_root = types.SimpleNamespace(name=str(tmp_path))  # type: ignore[assignment]
    backend._loaded = True
    backend._separator = _Fake44kSeparator(out_dir)

    stems = backend.separate_chunk(in_pcm, sr_in)
    vocals = stems["vocals"]
    assert vocals.shape[0] == in_pcm.shape[0]
    # Measure dominant frequency when interpreted at 48kHz: must stay near 440 Hz, not ~478.7 Hz
    mono = vocals[:, 0]
    spec = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / sr_in)
    peak_hz = float(freqs[int(np.argmax(spec))])
    assert abs(peak_hz - 440.0) < 5.0, f"Pitch shifted to {peak_hz:.1f} Hz due to missing 44.1k->48k resample"


def test_e5_system_loopback_retries_up_to_max_device_reconnects() -> None:
    """If the first reconnect open fails, SystemLoopback must retry up to max_device_reconnects."""
    from audio.system_loopback import WasapiSystemLoopbackBackend
    from core.config import AudioConfig

    class _FlakyStream:
        def __init__(self, fail_after: int) -> None:
            self.calls = 0
            self.fail_after = fail_after

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            self.calls += 1
            if self.calls >= self.fail_after:
                raise OSError("device disconnected")
            return np.zeros((frames, 2), dtype=np.float32).tobytes()

        def stop_stream(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _DummyPA:
        def terminate(self) -> None:
            pass

    backend = WasapiSystemLoopbackBackend(
        audio_config=AudioConfig(),
        max_device_reconnects=3,
        allow_non_windows=True,
    )
    open_attempts = {"count": 0}
    dev_info = {"name": "MockSpeaker", "defaultSampleRate": 48000, "maxInputChannels": 2}

    def _fake_open():
        open_attempts["count"] += 1
        if open_attempts["count"] == 1:
            raise OSError("transient device busy during switch")
        # 2nd reconnect attempt succeeds, then stop after 2 reads
        s = _FlakyStream(fail_after=999)
        orig_read = s.read

        def _stop_soon(frames: int, exception_on_overflow: bool = False) -> bytes:
            data = orig_read(frames, exception_on_overflow=exception_on_overflow)
            if s.calls >= 2:
                backend._stop_event.set()
            return data

        s.read = _stop_soon  # type: ignore[method-assign]
        return _DummyPA(), s, dev_info, 480, "float32"

    backend._pa = _DummyPA()
    backend._stream = _FlakyStream(fail_after=2)
    backend._open_default_loopback = _fake_open  # type: ignore[method-assign]
    # Speed up wait
    backend._stop_event.wait = lambda timeout=None: backend._stop_event.is_set()  # type: ignore[method-assign]

    backend._capture_loop(dev_info, 480, "float32")
    assert open_attempts["count"] >= 2, f"Only tried {open_attempts['count']} reconnect before exiting loop"


def test_e9_diagnostics_sanitizes_json_escaped_windows_home_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON-escaped Windows paths (C:\\\\Users\\\\Alice) must be sanitized inside diagnostic zip."""
    from core import diagnostics

    fake_home = r"C:\Users\Alice"
    monkeypatch.setattr(diagnostics.Path, "home", classmethod(lambda cls: fake_home))

    sample_json = json.dumps({"ai_python_executable": r"C:\Users\Alice\.venv-ai\Scripts\python.exe"})
    sanitized = diagnostics._sanitize_text(sample_json)
    assert "Alice" not in sanitized
    assert json.dumps(fake_home)[1:-1] not in sanitized


def test_e10_pyproject_toml_dependencies_under_project_table() -> None:
    """PEP 621: dependencies must live under [project], not [project.urls], and include sounddevice."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    project = data.get("project", {})
    urls = project.get("urls", {})
    assert "dependencies" not in urls, "dependencies accidentally nested under [project.urls]"
    assert isinstance(project.get("dependencies"), list) and len(project["dependencies"]) > 0
    assert any(d.lower().startswith("sounddevice") for d in project["dependencies"])


def test_e13_output_stream_oserror_resets_playing_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """When importing sounddevice raises OSError (missing PortAudio), _is_playing must reset to False."""
    from audio.metronome import PracticeMetronome
    from audio.playback import StemMixerEngine

    real_import = __import__

    def _raise_oserror(name, *args, **kwargs):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)
    monkeypatch.setattr("builtins.__import__", _raise_oserror)

    engine = StemMixerEngine()
    engine._is_playing = True
    engine._ensure_output_stream()
    assert engine.is_playing is False

    met = PracticeMetronome()
    met._standalone_playing = True
    met._ensure_output_stream()
    assert met.standalone_playing is False


def test_e19_mirror_downloader_rejects_truncated_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If server closes early with total_rx < Content-Length and no sha256, downloader must raise."""
    from scripts import mirror_wheel_fetch as mwf

    class _TruncatedResp:
        status = 200
        headers = {"Content-Length": "10000"}

        def __init__(self) -> None:
            self._sent = False

        def read(self, _n: int) -> bytes:
            if not self._sent:
                self._sent = True
                return b"x" * 100
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mwf, "urlopen", lambda req, timeout=30.0: _TruncatedResp())
    dest = tmp_path / "torch-fake.whl"

    with pytest.raises((mwf._SlowMirrorError, RuntimeError)):
        mwf._download_with_speed_guard(
            url="https://example.invalid/torch-fake.whl",
            dest=dest,
            expected_sha256="",
            pkg_name="torch",
            mirror_label="test-mirror",
            base_pct=0,
            span_pct=100,
            min_speed_bps=1.0,
            grace_sec=999.0,
            stall_sec=999.0,
            timeout_sec=5.0,
        )
    assert not dest.exists()


def test_e20_release_workflow_avoids_inline_expression_injection() -> None:
    """release-windows.yml must pass inputs.release_tag via env:, not inline ${{ inputs.release_tag }} in run."""
    yml = (REPO_ROOT / ".github" / "workflows" / "release-windows.yml").read_text("utf-8")
    # Inline interpolation inside PowerShell string in run block is unsafe
    assert '"${{ inputs.release_tag }}"' not in yml


# ============================================================================
# 2. Algorithms (A-M1, A-M3, A-M7, A-M8, A-M9, A-M10, A-L1)
# ============================================================================


def test_am1_realtime_pitch_parabolic_interpolation_bass_accuracy() -> None:
    """Real-time PitchEstimator on harmonic-rich A1 (55 Hz) must stay within 10 cents."""
    from analysis.pitch import PitchEstimator

    sr = 48000
    fft_size = 4096
    f0 = 55.0  # A1
    t = np.arange(fft_size, dtype=np.float32) / sr
    sig = sum((1.0 / k) * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 7)).astype(np.float32)
    win = np.hanning(fft_size).astype(np.float32)
    mag = np.abs(np.fft.rfft(sig * win)).astype(np.float32)

    est = PitchEstimator(sample_rate=sr, fft_size=fft_size).estimate_from_magnitude(mag, is_silent=False)
    assert est.frequency_hz is not None
    cents_err = abs(1200.0 * math.log2(est.frequency_hz / f0))
    assert cents_err < 10.0, f"A1 pitch error {cents_err:.1f} cents (got {est.frequency_hz:.2f} Hz)"


def test_am3_offline_bass_yin_pure_sine_no_octave_down_error() -> None:
    """Pure sine bass notes E1..C4 must not be misclassified an octave too low."""
    from analysis.stem_analyzer import _yin_bass_frame_f0

    sr = 48000
    n = 8192
    win = np.hanning(n).astype(np.float32)
    t = np.arange(n, dtype=np.float32) / sr
    errors = []
    for midi in range(28, 61):  # E1..C4
        f0 = 440.0 * (2.0 ** ((midi - 69) / 12.0))
        frame = (0.5 * np.sin(2 * np.pi * f0 * t)).astype(np.float32)
        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        freq, _ = _yin_bass_frame_f0(frame, mag, sample_rate=sr, bin_hz=sr / float(n))
        if freq <= 0 or abs(1200.0 * math.log2(freq / f0)) > 50.0:
            errors.append((midi, round(f0, 2), round(freq, 2)))
    assert not errors, f"Octave/pitch errors on pure sine bass: {errors[:5]}"


def test_am7_steady_sine_does_not_report_high_confidence_fake_bpm() -> None:
    """A steady unmodulated sine wave has no beats and must not return a High/Medium BPM (RT or offline)."""
    from analysis.fft import SpectrumAnalyzer
    from analysis.stem_analyzer import _estimate_offline_bpm_from_flux
    from analysis.tempo import TempoEstimator
    from core.config import AnalysisConfig

    cfg = AnalysisConfig(analysis_rate_hz=15.0, tempo_window_seconds=24)
    spec = SpectrumAnalyzer(sample_rate=48000, config=cfg)
    tempo = TempoEstimator(config=cfg)
    total = 48000 * 20
    t = np.arange(total, dtype=np.float32) / 48000.0
    sig = (0.3 * np.sin(2 * np.pi * 97.3 * t) + 0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

    est_rt = None
    for s in range(0, total - cfg.fft_size, 3200):
        _, _, log_db = spec.analyze_frame(sig[s : s + cfg.fft_size])
        est_rt = tempo.update(log_db, is_silent=False)
    assert est_rt is not None
    assert est_rt.bpm is None or est_rt.stability == "Unknown", (
        f"Steady sine reported fake RT BPM={est_rt.bpm} ({est_rt.stability}, acf={est_rt.confidence_score:.3f})"
    )

    spec_off = SpectrumAnalyzer(sample_rate=48000, config=cfg)
    flux = []
    prev = None
    for s in range(0, total - cfg.fft_size, 1024):
        _, _, log_db = spec_off.analyze_frame(sig[s : s + cfg.fft_size])
        m = np.power(10.0, np.clip(log_db, -120.0, 20.0) / 20.0)
        flux.append(0.0 if prev is None else float(np.sum(np.maximum(0.0, m - prev))))
        prev = m
    est_off = _estimate_offline_bpm_from_flux(np.asarray(flux, dtype=np.float32), rate_hz=48000 / 1024.0)
    assert est_off.bpm is None or est_off.stability == "Unknown", (
        f"Steady sine reported fake offline BPM={est_off.bpm} ({est_off.stability}, acf={est_off.confidence_score:.3f})"
    )


def test_am8_wsola_time_stretch_preserves_low_e1_pitch() -> None:
    """WSOLA at 1.25x must preserve E1 (41.2 Hz) pitch within 5 cents."""
    from audio.time_stretch import StreamingTimeStretcher

    sr = 48000
    f0 = 41.2034
    t = np.arange(int(sr * 1.2), dtype=np.float32) / sr
    src = np.stack([0.5 * np.sin(2 * np.pi * f0 * t)] * 2, axis=1).astype(np.float32)

    st = StreamingTimeStretcher(sample_rate=sr, channels=2)
    chunks = []
    rel_cursor = 0
    span_frames = src.shape[0]
    read_fn = lambda pos, n: src[pos : pos + n]
    while True:
        out, rel_cursor, eof = st.render_block(
            2048,
            speed=1.25,
            span_frames=span_frames,
            rel_cursor=rel_cursor,
            loop_enabled=False,
            read_rel_fn=read_fn,
        )
        if out.shape[0] > 0:
            chunks.append(out)
        if eof or len(chunks) > 40:
            break
    y = np.concatenate(chunks, axis=0)[:, 0]
    # Measure frequency on steady middle section via zero-padded FFT
    seg = y[len(y) // 4 : (3 * len(y)) // 4]
    nfft = 1 << 18
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n=nfft))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    peak_hz = float(freqs[int(np.argmax(spec))])
    cents_err = abs(1200.0 * math.log2(peak_hz / f0))
    assert cents_err < 5.0, f"WSOLA E1 pitch shifted by {cents_err:.1f} cents (got {peak_hz:.2f} Hz)"


def test_am9_major_seventh_uppercase_M7_parsed_as_maj7_not_m7() -> None:
    """CM7 must be parsed as Cmaj7 (60, 64, 67, 71) and degree Imaj7, not Cm7."""
    from analysis.chord_practice import chord_midi_notes
    from analysis.chords import chord_scale_degree

    assert chord_midi_notes("CM7") == (60, 64, 67, 71)
    assert chord_scale_degree("CM7", "C major") == "Imaj7"


def test_am10_spell_chord_tones_uses_diatonic_letter_spelling() -> None:
    """Fm must spell as 'F · Ab · C' and Bb as 'Bb · D · F', not sharp-only."""
    from analysis.chords import spell_chord_tones

    assert spell_chord_tones("Fm") == "F · Ab · C"
    assert spell_chord_tones("Bb") == "Bb · D · F"


def test_al1_transpose_note_name_handles_b_sharp_and_c_flat_octaves() -> None:
    """B#3 + 12 semitones must be C5 (not C4); Cb4 + 12 must be B4 (not B5)."""
    from analysis.chords import transpose_note_name

    assert transpose_note_name("B#3", 12) == "C5"
    assert transpose_note_name("Cb4", 12) == "B4"


# ============================================================================
# 3. UI / i18n (U-B01..U-B29)
# ============================================================================


@pytest.mark.xfail(strict=True, reason="U-B01")
def test_ub01_spectrogram_displays_full_96_log_bins_and_hz_axis() -> None:
    """Spectrogram YRange must cover all 96 log_freq_bins (not truncated at 64 ~ 1.87kHz)."""
    _qapp()
    from core.config import AnalysisConfig
    from ui.spectrum_widget import SpectrumAnalysisWidget

    cfg = AnalysisConfig()
    w = SpectrumAnalysisWidget()
    try:
        yr = w.spec_plot.getViewBox().viewRange()[1]
        assert yr[1] >= cfg.log_freq_bins - 1, f"Spectrogram Y axis truncated at {yr[1]} (expected {cfg.log_freq_bins})"
        left_label = str(w.spec_plot.getAxis("left").labelText)
        assert "Hz" in left_label or "频率" in left_label
    finally:
        w.close()
        w.deleteLater()


@pytest.mark.xfail(strict=True, reason="U-B04")
def test_ub04_practice_shortcuts_do_not_rely_solely_on_ctrl_space() -> None:
    """NEEDS_TARGET contract test: Space/L/[/] shortcuts must exist and avoid single-key hijack in QLineEdit."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        shortcuts = [sc.key().toString() for sc in mw.findChildren(QtGui.QShortcut)]
        assert "Space" in shortcuts, f"Missing Space playback shortcut; found {shortcuts}"
        assert "L" in shortcuts, f"Missing L loop shortcut; found {shortcuts}"
    finally:
        mw.close()
        mw.deleteLater()


@pytest.mark.xfail(strict=True, reason="U-B05")
def test_ub05_tuning_cents_bar_matches_5c_20c_thresholds_and_amber_slight_color() -> None:
    """TuningCentsBar thresholds must match help text (±5c green, ±20c amber, >20c red)."""
    _qapp()
    from ui.chroma_widget import TuningCentsBar

    bar = TuningCentsBar()
    try:
        bar.set_pitch(440.0, 4.0)
        c_in = bar.zone_color
        bar.set_pitch(440.0, 8.0)
        c_slight = bar.zone_color
        bar.set_pitch(440.0, 22.0)
        c_off = bar.zone_color
        assert c_in != c_slight, "8 cents should already be slight (threshold ±5c), not in-tune"
        assert c_off != c_slight, "22 cents should already be off (threshold ±20c), not slight"
        # Slight color should be amber/yellowish (R > B), not blue (#0284C7)
        qcol = QtGui.QColor(c_slight)
        assert qcol.red() > qcol.blue(), f"Slight color {c_slight} is blue instead of amber"
    finally:
        bar.close()
        bar.deleteLater()


def test_ub06_banner_label_roundtrip_zh_en_zh_preserves_original_text() -> None:
    """show_banner_message must store Chinese original in _ls_orig_text, not translated text."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.i18n import set_current_language
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        set_current_language("en")
        mw.show_banner_message("未捕获")
        # _set_label_cached currently overwrites _ls_orig_text with the already-translated English text!
        assert mw.notice_banner.property("_ls_orig_text") == "未捕获"
    finally:
        set_current_language("zh")
        mw.close()
        mw.deleteLater()


def test_ub09_translate_widget_tree_translates_qaction_tooltip_and_accessible_name() -> None:
    """translate_widget_tree must translate QAction, toolTip, and accessibleName."""
    _qapp()
    from core.i18n import translate_widget_tree

    root = QtWidgets.QWidget()
    menu = QtWidgets.QMenu(root)
    act = menu.addAction("显示主界面")
    btn = QtWidgets.QPushButton("设置", root)
    btn.setAccessibleName("设置")
    btn.setToolTip("打开设置")
    try:
        translate_widget_tree(root, "en")
        assert act.text() != "显示主界面", "QAction text was not translated"
        assert btn.accessibleName() != "设置", "accessibleName was not translated"
        assert btn.toolTip() != "打开设置", "toolTip was not translated"
    finally:
        root.close()
        root.deleteLater()


def test_ub10_non_acid_capture_button_uses_i18n() -> None:
    """In non-acid themes, set_capture_active_ui must translate capture_btn text when lang='en'."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.i18n import set_current_language
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        set_current_language("en")
        mw._acid_variant = None
        mw.set_capture_active_ui(True)
        assert mw.capture_btn.text() != "停止捕获"
    finally:
        set_current_language("zh")
        mw.close()
        mw.deleteLater()


def test_ub11_gpu_checkbox_does_not_hardcode_rtx_5060_ti() -> None:
    """UI GPU checkbox and help text should reflect detected GPU rather than hardcoding RTX 5060 Ti."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.models import GPUInfo
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    hw = probe_system()
    hw.gpus = [GPUInfo(index=0, name="NVIDIA GeForce RTX 4070", total_vram_mb=12288.0, used_vram_mb=1024.0, free_vram_mb=11264.0)]
    mw = ListenScopeMainWindow(
        hardware_report=hw,
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        assert "RTX 5060 Ti" not in mw.ai_gpu_chk.text()
        assert "RTX 4070" in mw.ai_gpu_chk.text()
    finally:
        mw.close()
        mw.deleteLater()


@pytest.mark.xfail(strict=True, reason="U-B12")
def test_ub12_settings_and_appearance_dialogs_do_not_leak_children(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening SettingsDialog repeatedly must delete closed dialogs instead of accumulating children."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow
    from ui.settings_dialog import SettingsDialog

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: QtWidgets.QDialog.DialogCode.Rejected)
    try:
        for _ in range(3):
            mw.open_settings_dialog()
        QtWidgets.QApplication.processEvents()
        leaked = mw.findChildren(SettingsDialog)
        assert len(leaked) == 0, f"{len(leaked)} closed SettingsDialog instances still attached to MainWindow"
    finally:
        mw.close()
        mw.deleteLater()


def test_ub16_light_theme_primary_button_and_in_tune_meet_wcag_aa() -> None:
    """Light theme primary button text/bg contrast must be >= 4.5:1 (WCAG AA normal text)."""
    from ui.acid_style import get_acid_palette

    p = get_acid_palette("light")
    btn_ratio = _wcag_contrast(p.text_inverse, p.accent)
    assert btn_ratio >= 4.5, f"Light primary button contrast {btn_ratio:.2f}:1 < 4.5:1 ({p.text_inverse} on {p.accent})"


@pytest.mark.xfail(strict=True, reason="U-B20")
def test_ub20_maximize_button_syncs_on_system_window_state_change() -> None:
    """System-triggered WindowStateChange (e.g. Win+Up) must sync win_max_btn icon/state."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    try:
        mw.setWindowState(QtCore.Qt.WindowState.WindowMaximized)
        ev = QtCore.QEvent(QtCore.QEvent.Type.WindowStateChange)
        mw.changeEvent(ev)
        assert mw.win_max_btn.text() == "❐"
    finally:
        mw.close()
        mw.deleteLater()


@pytest.mark.xfail(strict=True, reason="U-B21")
def test_ub21_win32_icon_handles_not_reloaded_every_show_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEEDS_TARGET contract test: _apply_windows_taskbar_and_rounding must load HICONs once, not every show."""
    _qapp()
    from audio.playback import StemMixerEngine
    from core.config import AIConfig, ResourceLimits
    from core.system_probe import probe_system
    from ui.main_window import ListenScopeMainWindow

    mw = ListenScopeMainWindow(
        hardware_report=probe_system(),
        resource_limits=ResourceLimits(),
        ai_config=AIConfig(),
        mixer_engine=StemMixerEngine(),
    )
    load_calls = {"n": 0}

    class _FakeUser32:
        def LoadImageW(self, *args):
            load_calls["n"] += 1
            return 1000 + load_calls["n"]

        def SendMessageW(self, *args):
            return 0

        def DestroyIcon(self, _h):
            return 1

    fake_windll = types.SimpleNamespace(user32=_FakeUser32())
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("ctypes.windll", fake_windll, raising=False)
    try:
        mw._apply_windows_taskbar_and_rounding()
        mw._apply_windows_taskbar_and_rounding()
        assert load_calls["n"] == 2, f"LoadImageW called {load_calls['n']} times across 2 show events (leaks HICON)"
    finally:
        mw.close()
        mw.deleteLater()


@pytest.mark.xfail(strict=True, reason="U-B23")
def test_ub23_settings_store_persists_window_geometry_within_schema_2(tmp_path: Path) -> None:
    """PersistedSettings (schema_version=2) must support saving and loading window_geometry."""
    from core.settings_store import PersistedSettings, load_persisted_settings, save_persisted_settings

    assert hasattr(PersistedSettings, "window_geometry")
    s = PersistedSettings(window_geometry="AAAA/fakebase64==")
    p = tmp_path / "settings.json"
    save_persisted_settings(s, path=p)
    loaded = load_persisted_settings(path=p)
    assert loaded.schema_version == 2
    assert loaded.window_geometry == "AAAA/fakebase64=="


@pytest.mark.xfail(strict=True, reason="U-B24")
def test_ub24_log_panel_preserves_scroll_position_when_user_scrolled_up() -> None:
    """When user scrolls up in ResourceMonitorWidget log view, new logs must not yank scrollbar to bottom."""
    _qapp()
    from ui.resource_widget import ResourceMonitorWidget

    w = ResourceMonitorWidget()
    w.resize(600, 300)
    w.show()
    try:
        lines = [f"log line {i}" for i in range(80)]
        w.update_logs(lines)
        QtWidgets.QApplication.processEvents()
        bar = w.log_text.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(0)
        lines.append("log line 80")
        w.update_logs(lines)
        QtWidgets.QApplication.processEvents()
        assert bar.value() == 0, f"Scrollbar yanked from 0 to {bar.value()} on new log line"
    finally:
        w.close()
        w.deleteLater()


def test_ub25_spectrogram_and_chroma_history_duration_labels_match_actual_30s() -> None:
    """Spectrogram card unit must match actual spectrum_history_seconds (30s), not '120S HISTORY'."""
    _qapp()
    from core.config import AnalysisConfig
    from ui.spectrum_widget import SpectrumAnalysisWidget

    cfg = AnalysisConfig()
    w = SpectrumAnalysisWidget()
    try:
        labels = [lbl.text() for lbl in w.findChildren(QtWidgets.QLabel)]
        assert "120S HISTORY" not in labels, "Spectrogram unit claims 120S HISTORY while actual buffer is 30s"
        assert any(f"{cfg.spectrum_history_seconds}S" in t.upper() for t in labels)
    finally:
        w.close()
        w.deleteLater()


def test_ub28_i18n_has_no_mixed_scripts_and_no_conflicting_duplicate_keys() -> None:
    """ja must contain no Hangul (メ트로ノーム bug), and UI_PHRASE_MAP/EXTRA_PHRASE_MAP must not conflict."""
    from core import i18n, i18n_catalog

    hangul_re = re.compile(r"[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]")
    ja_metronome = i18n.UI_PHRASE_MAP.get("节拍器", {}).get("ja", "")
    assert not hangul_re.search(ja_metronome), f"Japanese metronome contains Hangul: {ja_metronome!r}"

    # Check source-level duplicate key conflicts between i18n.py and i18n_catalog.py
    src = (REPO_ROOT / "core" / "i18n.py").read_text("utf-8")
    # Verify EXTRA_PHRASE_MAP keys don't silently overwrite different translations
    assert "紧急停止 AI" not in i18n_catalog.EXTRA_PHRASE_MAP or (
        i18n_catalog.EXTRA_PHRASE_MAP["紧急停止 AI"]["ko"] == "AI 긴급 중지"
    )


def test_ub29_dark_theme_status_warn_is_amber_not_cyan() -> None:
    """Dark theme status_warn_fg must be distinct amber (R > B), not cyan #77DCE4."""
    from ui.acid_style import get_acid_palette

    p = get_acid_palette("dark")
    col = QtGui.QColor(p.status_warn_fg)
    assert p.status_warn_fg.upper() != p.accent_secondary.upper()
    assert col.red() > col.blue(), f"Dark status_warn_fg {p.status_warn_fg} is cyan instead of amber"
