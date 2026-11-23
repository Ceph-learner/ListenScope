"""Non-destructive CPU streaming deep stem analyzer (Harmony/Chords, Bass, Drums groove, Melody, & Sheet Export).

Reads separated stem WAV files cleanly in fixed chunks via `soundfile` (with stdlib
`wave` 16/24/32-bit fallback) so live capture and the 120s FixedRingBuffer are never
clobbered and memory stays bounded (<20 MB transient overhead).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import csv
from pathlib import Path
from typing import Iterable, Optional
import wave

import numpy as np

from audio.pcm_utils import StreamingResampler, decode_wave_bytes, normalize_to_canonical_pcm
from core.config import AnalysisConfig
from core.models import (
    BassAnalysisResult,
    ChordTimelineSegment,
    DrumsAnalysisResult,
    KeyEstimate,
    MelodyAnalysisResult,
    MidiTranscriptionResult,
    StemDeepAnalysisReport,
    StemNoteEvent,
    TempoEstimate,
)

from .chords import ChordDetector, transpose_chord_symbol, transpose_key_label, transpose_note_name
from .chroma import ChromaExtractor, PITCH_CLASSES
from .fft import SpectrumAnalyzer
from .key_detection import KeyDetector
from .pitch import PitchEstimator, freq_to_note_and_cents
from .tempo import TempoEstimator
from .yin import yin_frame_f0 as _yin_bass_frame_f0

CANONICAL_SR = 48000
MAX_EVENTS_CAP = 2000


def _midi_to_name(midi_num: int) -> str:
    clamped = max(0, min(127, int(midi_num)))
    return f"{PITCH_CLASSES[clamped % 12]}{(clamped // 12) - 1}"


def _open_audio_reader(path: Path) -> tuple[str, object, int, int, int]:
    """Open audio file cleanly, returning `(kind, handle, sr, ch, total_frames)`."""
    try:
        import soundfile as sf  # type: ignore[import-untyped]

        sf_file = sf.SoundFile(str(path), "r")
        return "sf", sf_file, int(sf_file.samplerate), max(1, int(sf_file.channels)), int(sf_file.frames)
    except Exception:
        wf = wave.open(str(path), "rb")
        return "wave", wf, int(wf.getframerate()), max(1, int(wf.getnchannels())), int(wf.getnframes())


def _read_reader_chunk_f32(kind: str, handle: object, take: int, src_ch: int) -> np.ndarray:
    if take <= 0:
        return np.empty((0, src_ch), dtype=np.float32)
    if kind == "sf":
        arr = np.asarray(handle.read(take, dtype="float32", always_2d=True), dtype=np.float32)  # type: ignore[attr-defined]
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.size > 0 and not np.all(np.isfinite(arr)):
            arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)
        return arr

    wf = handle
    raw = wf.readframes(take)  # type: ignore[attr-defined]
    if not raw:
        return np.empty((0, src_ch), dtype=np.float32)
    sw = int(wf.getsampwidth())  # type: ignore[attr-defined]
    try:
        return decode_wave_bytes(raw, sw, src_ch)
    except ValueError:
        return np.empty((0, src_ch), dtype=np.float32)


def _iter_aligned_mono_48k_frames(
    sources: list[tuple[Path, float]],
    *,
    fft_size: int,
    hop_size: int,
    max_seconds: float = 120.0,
) -> tuple[float, Iterable[tuple[float, np.ndarray]]]:
    """Yield sliding `(center_time_sec, mono_frame_48k)` from one or weighted WAV paths."""
    readers: list[tuple[str, object, int, int, int, float]] = []
    min_duration = float("inf")
    try:
        for p, weight in sources:
            kind, handle, sr, ch, total_frames = _open_audio_reader(p)
            readers.append((kind, handle, sr, ch, total_frames, float(weight)))
            min_duration = min(min_duration, total_frames / float(max(1, sr)))
    except Exception:
        for _k, h, *_ in readers:
            try:
                h.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        raise

    if min_duration == float("inf"):
        min_duration = 0.0
    eff_duration = min(float(max_seconds), min_duration)

    def _generator() -> Iterable[tuple[float, np.ndarray]]:
        block_sec = 0.5
        buf = np.empty(0, dtype=np.float32)
        global_sample_offset = 0
        max_samples = int(round(eff_duration * CANONICAL_SR))
        written_samples = 0

        resamplers: list[Optional[StreamingResampler]] = [
            StreamingResampler(sr, CANONICAL_SR, 1) if sr != CANONICAL_SR else None
            for (_k, _h, sr, *_rest) in readers
        ]
        flushed = [False] * len(readers)

        try:
            while written_samples < max_samples:
                chunks_48k: list[np.ndarray] = []
                min_len = None
                for r_idx, (kind, handle, sr, ch, _total_frames, weight) in enumerate(readers):
                    src_take = max(256, int(round(block_sec * sr)))
                    raw_arr = _read_reader_chunk_f32(kind, handle, src_take, ch)
                    rs = resamplers[r_idx]
                    if raw_arr.shape[0] == 0:
                        if rs is not None and not flushed[r_idx]:
                            flushed[r_idx] = True
                            mono_48k = rs.flush()[:, 0]
                            if mono_48k.shape[0] > 0:
                                chunks_48k.append(mono_48k * weight)
                                min_len = mono_48k.shape[0] if min_len is None else min(min_len, mono_48k.shape[0])
                                continue
                        min_len = 0
                        break
                    if rs is not None:
                        mono_src = normalize_to_canonical_pcm(
                            raw_arr,
                            src_rate=sr,
                            src_channels=ch,
                            dst_rate=sr,
                            dst_channels=1,
                        )
                        mono_48k = rs.process(mono_src)[:, 0]
                    else:
                        mono_48k = normalize_to_canonical_pcm(
                            raw_arr,
                            src_rate=sr,
                            src_channels=ch,
                            dst_rate=CANONICAL_SR,
                            dst_channels=1,
                        )[:, 0]
                    chunks_48k.append(mono_48k * weight)
                    min_len = mono_48k.shape[0] if min_len is None else min(min_len, mono_48k.shape[0])

                if not chunks_48k or min_len is None or min_len <= 0:
                    break

                summed = np.zeros(min_len, dtype=np.float32)
                for c in chunks_48k:
                    summed += c[:min_len]
                remain = max_samples - written_samples
                if summed.shape[0] > remain:
                    summed = summed[:remain]
                written_samples += int(summed.shape[0])
                buf = np.concatenate([buf, summed]) if buf.size > 0 else summed

                while buf.shape[0] >= fft_size:
                    frame = buf[:fft_size]
                    center_sec = (global_sample_offset + fft_size * 0.5) / float(CANONICAL_SR)
                    yield center_sec, frame
                    buf = buf[hop_size:]
                    global_sample_offset += hop_size
                if buf.size > 0 and buf.base is not None:
                    buf = np.array(buf, dtype=np.float32, copy=True)
        finally:
            for _k, h, *_ in readers:
                try:
                    h.close()  # type: ignore[attr-defined]
                except Exception:
                    pass

    return eff_duration, _generator()


def _coalesce_note_frames(
    frame_notes: list[tuple[float, int, float, float]],
    *,
    hop_sec: float,
    min_note_duration_sec: float = 0.08,
    max_notes: int = MAX_EVENTS_CAP,
) -> list[StemNoteEvent]:
    """Group quantized MIDI frame observations into clean note events."""
    events: list[StemNoteEvent] = []
    cur_midi: Optional[int] = None
    cur_start: float = 0.0
    cur_last_t: float = 0.0
    cur_freqs: list[float] = []
    cur_confs: list[float] = []

    def _flush() -> None:
        if cur_midi is None or not cur_freqs:
            return
        dur = (cur_last_t + hop_sec) - cur_start
        if dur < min_note_duration_sec:
            return
        events.append(
            StemNoteEvent(
                start_sec=round(max(0.0, cur_start), 3),
                end_sec=round(cur_last_t + hop_sec, 3),
                pitch_midi=int(cur_midi),
                note_name=_midi_to_name(int(cur_midi)),
                frequency_hz=round(float(np.median(cur_freqs)), 2),
                confidence=round(float(np.mean(cur_confs)), 3),
            )
        )

    for t_sec, midi_num, freq_hz, conf in frame_notes:
        if midi_num < 0:
            _flush()
            cur_midi = None
            cur_freqs.clear()
            cur_confs.clear()
            continue

        if cur_midi is None:
            cur_midi = midi_num
            cur_start = t_sec
            cur_last_t = t_sec
            cur_freqs = [freq_hz]
            cur_confs = [conf]
        elif midi_num == cur_midi and (t_sec - cur_last_t) <= hop_sec * 2.5:
            cur_last_t = t_sec
            cur_freqs.append(freq_hz)
            cur_confs.append(conf)
        else:
            _flush()
            if len(events) >= max_notes:
                return events
            cur_midi = midi_num
            cur_start = t_sec
            cur_last_t = t_sec
            cur_freqs = [freq_hz]
            cur_confs = [conf]

    _flush()
    return events[:max_notes]



def _detect_bass_modulation(events: list[StemNoteEvent]) -> tuple[bool, str]:
    """Compare first-half vs second-half bass pitch-class weightings to surface key shift / modulation hints."""
    if len(events) < 4:
        return False, ""
    span = events[-1].end_sec - events[0].start_sec
    if span < 1.6:
        return False, ""
    mid = len(events) // 2
    first_half = events[:mid]
    second_half = events[mid:]

    vec_a = np.zeros(12, dtype=np.float64)
    vec_b = np.zeros(12, dtype=np.float64)
    for ev in first_half:
        vec_a[ev.pitch_midi % 12] += max(0.05, ev.end_sec - ev.start_sec)
    for ev in second_half:
        vec_b[ev.pitch_midi % 12] += max(0.05, ev.end_sec - ev.start_sec)

    na = float(np.linalg.norm(vec_a))
    nb = float(np.linalg.norm(vec_b))
    if na <= 1e-6 or nb <= 1e-6:
        return False, ""
    cos_sim = float(np.dot(vec_a, vec_b) / (na * nb))
    pc_a = PITCH_CLASSES[int(np.argmax(vec_a))]
    pc_b = PITCH_CLASSES[int(np.argmax(vec_b))]
    if cos_sim < 0.45 and pc_a != pc_b:
        return True, f"前半段根音重心 {pc_a} → 后半段 {pc_b} (可能发生转调，最低音按实音 MIDI 标定)"
    return False, ""


def analyze_bass_stem(bass_wav_path: Path | str, *, max_seconds: float = 120.0) -> BassAnalysisResult:
    """Analyze separated bass stem in [28 Hz, 350 Hz] using FFT-accelerated YIN/CMNDF + subharmonic verification."""
    path = Path(bass_wav_path)
    fft_size = 8192
    hop_size = 2048
    hop_sec = hop_size / float(CANONICAL_SR)
    bin_hz = CANONICAL_SR / float(fft_size)
    win = np.hanning(fft_size).astype(np.float32)

    duration_sec, frames_iter = _iter_aligned_mono_48k_frames(
        [(path, 1.0)], fft_size=fft_size, hop_size=hop_size, max_seconds=max_seconds
    )

    frame_data: list[tuple[float, float, float]] = []
    signal_detected = False
    silence_rms = 10.0 ** (AnalysisConfig().silence_threshold_dbfs / 20.0)

    for center_sec, frame in frames_iter:
        t_start = max(0.0, center_sec - hop_sec * 0.5)
        if not np.all(np.isfinite(frame)):
            frame = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
        rms = float(np.sqrt(np.mean(np.square(frame))))
        if rms < silence_rms:
            frame_data.append((t_start, 0.0, 0.0))
            continue
        signal_detected = True

        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        freq, conf = _yin_bass_frame_f0(frame, mag, sample_rate=CANONICAL_SR, bin_hz=bin_hz)
        if freq <= 0.0:
            frame_data.append((t_start, 0.0, 0.0))
            continue
        frame_data.append((t_start, freq, conf))

    # 3-frame median filter across adjacent voiced frames eliminates single-frame octave glitches
    raw_obs: list[tuple[float, int, float, float]] = []
    for idx, (t_start, freq, conf) in enumerate(frame_data):
        if freq <= 0.0:
            raw_obs.append((t_start, -1, 0.0, 0.0))
            continue
        nbrs = [freq]
        if idx > 0 and frame_data[idx - 1][1] > 0.0:
            nbrs.append(frame_data[idx - 1][1])
        if idx + 1 < len(frame_data) and frame_data[idx + 1][1] > 0.0:
            nbrs.append(frame_data[idx + 1][1])
        med_freq = float(np.median(nbrs)) if len(nbrs) == 3 else freq
        midi = max(0, min(127, int(round(69.0 + 12.0 * np.log2(med_freq / 440.0)))))
        raw_obs.append((t_start, midi, med_freq, conf))

    events = _coalesce_note_frames(raw_obs, hop_sec=hop_sec, min_note_duration_sec=0.08)
    if events:
        lowest_ev = min(events, key=lambda ev: (ev.pitch_midi, ev.start_sec))
        highest_ev = max(events, key=lambda ev: (ev.pitch_midi, -ev.start_sec))
        lowest_midi = int(lowest_ev.pitch_midi)
        highest_midi = int(highest_ev.pitch_midi)
        lowest = _midi_to_name(lowest_midi)
        highest = _midi_to_name(highest_midi)
        lowest_freq_hz = round(float(lowest_ev.frequency_hz), 2)
        lowest_time_sec = round(float(lowest_ev.start_sec), 3)
        counts = Counter(PITCH_CLASSES[ev.pitch_midi % 12] for ev in events)
        roots = [pc for pc, _ in counts.most_common(6)]
        mod_detected, mod_note = _detect_bass_modulation(events)
    else:
        lowest = None
        highest = None
        lowest_midi = None
        highest_midi = None
        lowest_freq_hz = None
        lowest_time_sec = None
        roots = []
        mod_detected = False
        mod_note = ""

    return BassAnalysisResult(
        stem_path=path,
        duration_sec=round(duration_sec, 3),
        lowest_note=lowest,
        highest_note=highest,
        root_pitch_classes=roots,
        notes=events,
        signal_detected=signal_detected,
        lowest_midi=lowest_midi,
        highest_midi=highest_midi,
        lowest_freq_hz=lowest_freq_hz,
        lowest_note_time_sec=lowest_time_sec,
        modulation_detected=mod_detected,
        modulation_note=mod_note,
    )


def _pick_band_onsets(
    flux: np.ndarray,
    frame_times: np.ndarray,
    *,
    hop_sec: float,
    min_gap_sec: float,
    k_std: float = 1.65,
    floor_val: float = 0.03,
) -> list[float]:
    if flux.size < 5:
        return []
    win_half = max(3, int(round(0.22 / max(1e-4, hop_sec))))
    times: list[float] = []
    last_t = -10.0

    global_peak = float(np.max(flux))
    if global_peak < floor_val:
        return []
    rel_floor = max(floor_val, 0.12 * global_peak)

    for i in range(1, flux.shape[0] - 1):
        val = float(flux[i])
        if val < rel_floor:
            continue
        if not (val >= float(flux[i - 1]) and val > float(flux[i + 1])):
            continue
        s = max(0, i - win_half)
        e = min(flux.shape[0], i + win_half + 1)
        seg = flux[s:e]
        thresh = float(np.median(seg)) + k_std * float(np.std(seg)) + rel_floor * 0.35
        if val >= thresh:
            t_sec = float(frame_times[i])
            if (t_sec - last_t) >= min_gap_sec:
                times.append(round(t_sec, 3))
                last_t = t_sec
                if len(times) >= MAX_EVENTS_CAP:
                    break
    return times


def _estimate_offline_bpm_from_flux(flux: np.ndarray, rate_hz: float) -> TempoEstimate:
    if flux.size > 0 and not np.all(np.isfinite(flux)):
        flux = np.nan_to_num(flux, nan=0.0, posinf=0.0, neginf=0.0)
    if flux.size < max(16, int(round(1.8 * rate_hz))) or float(np.max(flux)) < 1e-4:
        return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)
    peakiness = float(np.percentile(flux, 95)) / (float(np.median(flux)) + 1e-9)
    if peakiness < 4.0:
        return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)
    smoothed = np.convolve(flux, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")
    centered = smoothed - float(np.mean(smoothed))
    energy = float(np.dot(centered, centered))
    if energy < 1e-6:
        return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)
    acf = np.correlate(centered, centered, mode="full")[centered.size - 1 :] / max(energy, 1e-9)

    min_lag = max(2, int(round((60.0 / 190.0) * rate_hz)))
    max_lag = min(acf.shape[0] - 1, int(round((60.0 / 55.0) * rate_hz)))
    if max_lag <= min_lag:
        return TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)

    lags = np.arange(min_lag, max_lag + 1, dtype=np.float32)
    bpms = 60.0 * rate_hz / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 118.0) / 0.55) ** 2).astype(np.float32)
    weighted = acf[min_lag : max_lag + 1] * prior
    best_rel = int(np.argmax(weighted))
    best_lag = min_lag + best_rel
    raw_acf = float(acf[best_lag])
    if not np.isfinite(raw_acf) or raw_acf < 0.14:
        return TempoEstimate(bpm=None, stability="Unknown", confidence_score=raw_acf if np.isfinite(raw_acf) else 0.0)

    refined = float(best_lag)
    if 0 < best_rel < weighted.shape[0] - 1:
        y0, y1, y2 = float(weighted[best_rel - 1]), float(weighted[best_rel]), float(weighted[best_rel + 1])
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-9:
            refined += max(-0.5, min(0.5, 0.5 * (y0 - y2) / denom))
    bpm = round(60.0 * rate_hz / max(1.0, refined), 1)
    stability = "High" if raw_acf >= 0.35 else ("Medium" if raw_acf >= 0.2 else "Low")
    return TempoEstimate(bpm=bpm, stability=stability, confidence_score=round(raw_acf, 3))


def analyze_drums_stem(drums_wav_path: Path | str, *, max_seconds: float = 120.0) -> DrumsAnalysisResult:
    """Analyze separated drums stem into Kick / Snare / Hi-Hat hits, BPM, and a 16-step groove map."""
    path = Path(drums_wav_path)
    fft_size = 2048
    hop_size = 512
    hop_sec = hop_size / float(CANONICAL_SR)
    rate_hz = CANONICAL_SR / float(hop_size)
    win = np.hanning(fft_size).astype(np.float32)
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / CANONICAL_SR)

    kick_mask = (freqs >= 35.0) & (freqs <= 130.0)
    snare_mask = (freqs >= 160.0) & (freqs <= 2500.0)
    hat_mask = (freqs >= 4500.0) & (freqs <= 15000.0)

    duration_sec, frames_iter = _iter_aligned_mono_48k_frames(
        [(path, 1.0)], fft_size=fft_size, hop_size=hop_size, max_seconds=max_seconds
    )

    prev_k: Optional[np.ndarray] = None
    prev_s: Optional[np.ndarray] = None
    prev_h: Optional[np.ndarray] = None
    k_flux: list[float] = []
    s_flux: list[float] = []
    h_flux: list[float] = []
    times: list[float] = []

    for center_sec, frame in frames_iter:
        if not np.all(np.isfinite(frame)):
            frame = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        log_mag = np.log1p(mag)
        mk = log_mag[kick_mask]
        ms = log_mag[snare_mask]
        mh = log_mag[hat_mask]

        if prev_k is None:
            k_flux.append(0.0)
            s_flux.append(0.0)
            h_flux.append(0.0)
        else:
            k_flux.append(float(np.mean(np.maximum(0.0, mk - prev_k))))
            s_flux.append(float(np.mean(np.maximum(0.0, ms - prev_s))))
            h_flux.append(float(np.mean(np.maximum(0.0, mh - prev_h))))
        prev_k, prev_s, prev_h = mk, ms, mh
        times.append(max(0.0, center_sec - hop_sec * 0.5))

    t_arr = np.asarray(times, dtype=np.float32)
    kf = np.asarray(k_flux, dtype=np.float32)
    sf_arr = np.asarray(s_flux, dtype=np.float32)
    hf = np.asarray(h_flux, dtype=np.float32)

    kicks = _pick_band_onsets(kf, t_arr, hop_sec=hop_sec, min_gap_sec=0.085, k_std=1.55)
    snares = _pick_band_onsets(sf_arr, t_arr, hop_sec=hop_sec, min_gap_sec=0.085, k_std=1.7)
    hihats = _pick_band_onsets(hf, t_arr, hop_sec=hop_sec, min_gap_sec=0.055, k_std=1.5)

    combined = kf * 1.4 + sf_arr * 1.1 + hf * 0.4
    tempo_est = _estimate_offline_bpm_from_flux(combined, rate_hz=rate_hz)

    # Quantize to 1-bar 16-step groove summary using estimated BPM (default 120 BPM reference if unknown)
    ref_bpm = tempo_est.bpm if tempo_est.bpm is not None else 120.0
    sixteenth_sec = (60.0 / ref_bpm) / 4.0
    t0 = min([t for t in (kicks[:1] + snares[:1] + hihats[:1])] or [0.0])
    step_counts = [{"K": 0, "S": 0, "H": 0} for _ in range(16)]
    for tag, hit_list in (("K", kicks), ("S", snares), ("H", hihats)):
        for t_hit in hit_list:
            idx = int(round((t_hit - t0) / max(1e-4, sixteenth_sec))) % 16
            step_counts[idx][tag] += 1

    bar_est = max(1, int(round(duration_sec / max(0.5, sixteenth_sec * 16.0))))
    min_support = max(1, bar_est // 3)
    groove: list[str] = []
    for bucket in step_counts:
        tags = [tag for tag in ("K", "S", "H") if bucket[tag] >= min_support]
        groove.append("+".join(tags) if tags else ".")

    return DrumsAnalysisResult(
        stem_path=path,
        duration_sec=round(duration_sec, 3),
        estimated_bpm=tempo_est.bpm,
        bpm_stability=tempo_est.stability,
        kick_times_sec=kicks,
        snare_times_sec=snares,
        hihat_times_sec=hihats,
        groove_16_step=groove,
    )


def analyze_melody_stem(
    melody_wav_path: Path | str,
    *,
    stem_name: str = "vocals",
    max_seconds: float = 120.0,
) -> MelodyAnalysisResult:
    """Analyze separated vocals or lead melody stem into note sequence and vocal/instrument range."""
    path = Path(melody_wav_path)
    fft_size = 4096
    hop_size = 1024
    hop_sec = hop_size / float(CANONICAL_SR)
    win = np.hanning(fft_size).astype(np.float32)
    est = PitchEstimator(sample_rate=CANONICAL_SR, fft_size=fft_size)

    duration_sec, frames_iter = _iter_aligned_mono_48k_frames(
        [(path, 1.0)], fft_size=fft_size, hop_size=hop_size, max_seconds=max_seconds
    )

    raw_obs: list[tuple[float, int, float, float]] = []
    total_frames = 0
    voiced_frames = 0

    for center_sec, frame in frames_iter:
        total_frames += 1
        if not np.all(np.isfinite(frame)):
            frame = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
        rms = float(np.sqrt(np.mean(np.square(frame))))
        t_start = max(0.0, center_sec - hop_sec * 0.5)
        if not np.isfinite(rms) or rms < 0.01:
            raw_obs.append((t_start, -1, 0.0, 0.0))
            continue
        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        p = est.estimate_from_magnitude(mag, is_silent=False)
        if (
            p.frequency_hz is None
            or not np.isfinite(p.frequency_hz)
            or p.confidence < 0.22
            or p.frequency_hz < 75.0
            or p.frequency_hz > 1450.0
        ):
            raw_obs.append((t_start, -1, 0.0, 0.0))
            continue
        voiced_frames += 1
        midi = max(0, min(127, int(round(69.0 + 12.0 * np.log2(p.frequency_hz / 440.0)))))
        raw_obs.append((t_start, midi, p.frequency_hz, p.confidence))

    events = _coalesce_note_frames(raw_obs, hop_sec=hop_sec, min_note_duration_sec=0.08)
    if events:
        midis = [e.pitch_midi for e in events]
        lowest = _midi_to_name(min(midis))
        highest = _midi_to_name(max(midis))
        median = _midi_to_name(int(round(float(np.median(midis)))))
    else:
        lowest = highest = median = None

    voiced_ratio = round(voiced_frames / float(max(1, total_frames)), 3)
    return MelodyAnalysisResult(
        stem_path=path,
        stem_name=stem_name,
        duration_sec=round(duration_sec, 3),
        lowest_note=lowest,
        highest_note=highest,
        median_note=median,
        voiced_ratio=voiced_ratio,
        notes=events,
    )


def analyze_harmony_and_chords(
    sources: list[tuple[Path, float]],
    *,
    source_label: str,
    max_seconds: float = 120.0,
    segment_sec: float = 0.5,
    include_sevenths: bool = False,
    bass_root_prior: Optional[np.ndarray] = None,
) -> tuple[str, float, KeyEstimate, TempoEstimate, list[ChordTimelineSegment]]:
    """Stream harmonic source(s) to extract Key, BPM, and merged ChordTimelineSegments."""
    cfg = AnalysisConfig(analysis_rate_hz=CANONICAL_SR / 1024.0)
    spec = SpectrumAnalyzer(sample_rate=CANONICAL_SR, config=cfg)
    hr_stride = 3  # ~15.6 Hz effective HR chroma rate (matches real-time 15 Hz worker & cuts offline CPU ~3x)
    chroma_cfg = AnalysisConfig(analysis_rate_hz=(CANONICAL_SR / float(cfg.hop_size)) / float(hr_stride))
    chroma_ext = ChromaExtractor(sample_rate=CANONICAL_SR, config=chroma_cfg)
    chord_det = ChordDetector(ema_alpha=0.55, include_sevenths=include_sevenths)
    key_det = KeyDetector(min_active_frames=12)

    fft_size = cfg.fft_size
    hop_size = cfg.hop_size
    hr_window = 16384
    hop_sec = hop_size / float(CANONICAL_SR)
    win_frames = max(4, int(round(segment_sec / hop_sec)))
    silence_rms = 10.0 ** (cfg.silence_threshold_dbfs / 20.0)

    duration_sec, frames_iter = _iter_aligned_mono_48k_frames(
        sources, fft_size=fft_size, hop_size=hop_size, max_seconds=max_seconds
    )

    flux_vals: list[float] = []
    prev_mag_like: Optional[np.ndarray] = None
    bucket_chromas: list[np.ndarray] = []
    bucket_silent = 0
    bucket_count = 0
    bucket_start = 0.0
    raw_segments: list[ChordTimelineSegment] = []
    hr_buf = np.zeros(hr_window, dtype=np.float32)
    hr_filled = 0
    last_c12 = np.zeros(12, dtype=np.float32)

    for idx, (center_sec, frame) in enumerate(frames_iter):
        if not np.all(np.isfinite(frame)):
            frame = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
        if hr_filled == 0:
            take = min(hr_window, frame.shape[0])
            hr_buf[hr_window - take :] = frame[-take:]
            hr_filled = take
        else:
            step = min(hop_size, frame.shape[0])
            hr_buf[:-step] = hr_buf[step:]
            hr_buf[-step:] = frame[-step:]
            hr_filled = min(hr_window, hr_filled + step)

        rms = float(np.sqrt(np.mean(np.square(frame))))
        is_silent = (not np.isfinite(rms)) or rms < silence_rms
        _fft_mag, _fft_db, log_db = spec.analyze_frame(frame, record=False)
        if idx % hr_stride == 0:
            hr_view = hr_buf[hr_window - hr_filled :] if hr_filled < hr_window else hr_buf
            last_c12 = chroma_ext.extract_from_pcm(hr_view, record_history=True, is_silent=is_silent)
        c12 = np.zeros(12, dtype=np.float32) if is_silent else last_c12

        log_safe = np.clip(np.nan_to_num(log_db, nan=-120.0, posinf=20.0, neginf=-120.0), -120.0, 20.0)
        mag_like = np.power(10.0, log_safe / 20.0)
        if prev_mag_like is None or is_silent or prev_mag_like.shape != mag_like.shape:
            flux_vals.append(0.0)
            prev_mag_like = None if is_silent else mag_like.astype(np.float32, copy=True)
        else:
            flux_vals.append(float(np.sum(np.maximum(0.0, mag_like - prev_mag_like))))
            prev_mag_like = mag_like.astype(np.float32, copy=True)

        if bucket_count == 0:
            bucket_start = max(0.0, center_sec - hop_sec * 0.5)
        bucket_chromas.append(c12)
        if is_silent:
            bucket_silent += 1
        bucket_count += 1

        if bucket_count >= win_frames:
            mean_c = np.mean(np.stack(bucket_chromas, axis=0), axis=0)
            win_silent = bucket_silent > (bucket_count * 0.75)
            est = chord_det.update(mean_c, is_silent=win_silent)
            end_t = min(duration_sec, bucket_start + bucket_count * hop_sec)
            raw_segments.append(
                ChordTimelineSegment(
                    start_sec=round(bucket_start, 2),
                    end_sec=round(end_t, 2),
                    chord=est.primary,
                    secondary=est.secondary,
                    correlation=round(est.correlation, 3),
                    stability=est.stability,
                )
            )
            bucket_chromas.clear()
            bucket_silent = 0
            bucket_count = 0

    if bucket_count > 0:
        mean_c = np.mean(np.stack(bucket_chromas, axis=0), axis=0)
        win_silent = bucket_silent > (bucket_count * 0.75)
        est = chord_det.update(mean_c, is_silent=win_silent)
        end_t = min(duration_sec, bucket_start + bucket_count * hop_sec)
        if end_t - bucket_start >= 0.15:
            raw_segments.append(
                ChordTimelineSegment(
                    start_sec=round(bucket_start, 2),
                    end_sec=round(end_t, 2),
                    chord=est.primary,
                    secondary=est.secondary,
                    correlation=round(est.correlation, 3),
                    stability=est.stability,
                )
            )

    # Coalesce consecutive identical chords to form readable progression sheet
    merged: list[ChordTimelineSegment] = []
    for seg in raw_segments:
        if merged and merged[-1].chord == seg.chord:
            prev = merged[-1]
            d1 = max(0.01, prev.end_sec - prev.start_sec)
            d2 = max(0.01, seg.end_sec - seg.start_sec)
            weighted_corr = round((prev.correlation * d1 + seg.correlation * d2) / (d1 + d2), 3)
            merged[-1] = ChordTimelineSegment(
                start_sec=prev.start_sec,
                end_sec=seg.end_sec,
                chord=prev.chord,
                secondary=prev.secondary,
                correlation=weighted_corr,
                stability=prev.stability if d1 >= d2 else seg.stability,
            )
        else:
            merged.append(seg)

    chroma_mat, weight_vec, bass_mat = chroma_ext.recent_chroma_bundle(seconds=max_seconds)
    key_est = key_det.estimate(
        chroma_mat,
        frame_weights=weight_vec,
        bass_window=bass_mat,
        bass_root_prior=bass_root_prior,
    )
    tempo_est = _estimate_offline_bpm_from_flux(np.asarray(flux_vals, dtype=np.float32), rate_hz=1.0 / hop_sec)
    return source_label, duration_sec, key_est, tempo_est, merged[:400]


def analyze_stems_offline(
    stem_paths: dict[str, str | Path],
    *,
    max_seconds: float = 120.0,
    include_sevenths: bool = False,
) -> StemDeepAnalysisReport:
    """Run non-destructive streaming CPU analysis over separated stem WAVs."""
    by_key = {k.strip().lower(): Path(v) for k, v in stem_paths.items() if Path(v).exists()}
    if not by_key:
        raise ValueError("未找到可供深度分析的音轨 WAV 文件。")

    bass_res = analyze_bass_stem(by_key["bass"], max_seconds=max_seconds) if "bass" in by_key else None
    bass_root_prior: Optional[np.ndarray] = None
    if bass_res is not None and bass_res.notes:
        prior = np.zeros(12, dtype=np.float32)
        for ev in bass_res.notes:
            dur = max(0.05, float(ev.end_sec) - float(ev.start_sec))
            prior[int(ev.pitch_midi) % 12] += dur * float(ev.confidence)
        if float(np.sum(prior)) > 1e-9:
            bass_root_prior = prior

    # Select best harmonic combination without including drums when harmonic stems exist
    if "instrumental" in by_key:
        if "vocals" in by_key:
            harm_sources = [(by_key["instrumental"], 0.85), (by_key["vocals"], 0.15)]
        else:
            harm_sources = [(by_key["instrumental"], 1.0)]
        harm_label = "instrumental"
    elif "other" in by_key and "bass" in by_key and "vocals" in by_key:
        harm_sources = [(by_key["other"], 0.55), (by_key["bass"], 0.30), (by_key["vocals"], 0.15)]
        harm_label = "other + bass + vocals (drumless harmonic mix)"
    elif "other" in by_key and "bass" in by_key:
        harm_sources = [(by_key["other"], 0.65), (by_key["bass"], 0.35)]
        harm_label = "other + bass (harmonic mix)"
    elif "other" in by_key:
        harm_sources = [(by_key["other"], 1.0)]
        harm_label = "other"
    elif "bass" in by_key:
        harm_sources = [(by_key["bass"], 1.0)]
        harm_label = "bass"
    else:
        first_k, first_p = next(iter(by_key.items()))
        harm_sources = [(first_p, 1.0)]
        harm_label = first_k

    source_label, duration_sec, key_est, harm_tempo, chord_timeline = analyze_harmony_and_chords(
        harm_sources,
        source_label=harm_label,
        max_seconds=max_seconds,
        include_sevenths=include_sevenths,
        bass_root_prior=bass_root_prior,
    )

    drums_res = analyze_drums_stem(by_key["drums"], max_seconds=max_seconds) if "drums" in by_key else None

    melody_res: Optional[MelodyAnalysisResult] = None
    if "vocals" in by_key:
        melody_res = analyze_melody_stem(by_key["vocals"], stem_name="vocals", max_seconds=max_seconds)
    elif "other" in by_key:
        melody_res = analyze_melody_stem(by_key["other"], stem_name="other", max_seconds=max_seconds)

    # Prefer drum stem BPM when available and valid
    final_bpm = harm_tempo
    if drums_res is not None and drums_res.estimated_bpm is not None:
        final_bpm = TempoEstimate(
            bpm=drums_res.estimated_bpm,
            stability=drums_res.bpm_stability,
            confidence_score=harm_tempo.confidence_score if harm_tempo.bpm is not None else 0.35,
        )

    notes: list[str] = []
    if max(duration_sec, bass_res.duration_sec if bass_res else 0.0) >= max_seconds - 0.1:
        notes.append(f"分析严格限制在前 {max_seconds:.0f}s，避免长音频内存飙升。")

    return StemDeepAnalysisReport(
        duration_sec=round(duration_sec, 3),
        harmonic_source_label=source_label,
        estimated_key=key_est,
        estimated_bpm=final_bpm,
        chord_timeline=chord_timeline,
        bass=bass_res,
        drums=drums_res,
        melody=melody_res,
        notes=notes,
    )


def export_transcription_sheet(
    report: StemDeepAnalysisReport,
    output_path: Path | str,
    *,
    midi_result: Optional[MidiTranscriptionResult] = None,
    transpose_semitones: int = 0,
) -> Path:
    """Export chord progression, bass, drums groove, melody, and optional MIDI notes to Markdown or CSV."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out.with_name(out.name + ".tmp")
    semi = int(transpose_semitones)

    def _tr_chord(c: str) -> str:
        return transpose_chord_symbol(c, semi) if semi != 0 else c

    def _tr_key(k: str) -> str:
        return transpose_key_label(k, semi) if semi != 0 else k

    def _tr_note(n: str) -> str:
        return transpose_note_name(n, semi) if semi != 0 else n

    if out.suffix.lower() == ".csv":
        try:
            with tmp_path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["section", "start_sec", "end_sec", "label", "detail_1", "detail_2", "confidence_or_corr"])
                for seg in report.chord_timeline:
                    writer.writerow(
                        ["chord", seg.start_sec, seg.end_sec, _tr_chord(seg.chord), _tr_chord(seg.secondary), seg.stability, seg.correlation]
                    )
                if report.bass is not None:
                    for n in report.bass.notes:
                        writer.writerow(["bass", n.start_sec, n.end_sec, _tr_note(n.note_name), n.pitch_midi, f"{n.frequency_hz}Hz", n.confidence])
                if report.drums is not None:
                    for t in report.drums.kick_times_sec:
                        writer.writerow(["drum_kick", t, t, "Kick", "", "", ""])
                    for t in report.drums.snare_times_sec:
                        writer.writerow(["drum_snare", t, t, "Snare", "", "", ""])
                    for t in report.drums.hihat_times_sec:
                        writer.writerow(["drum_hihat", t, t, "HiHat", "", "", ""])
                if report.melody is not None:
                    for n in report.melody.notes:
                        writer.writerow(["melody", n.start_sec, n.end_sec, _tr_note(n.note_name), n.pitch_midi, f"{n.frequency_hz}Hz", n.confidence])
                if midi_result is not None:
                    for n in midi_result.notes:
                        writer.writerow(["midi", n.start_sec, n.end_sec, _tr_note(n.note_name), n.pitch_midi, f"vel={n.velocity}", n.confidence])
            tmp_path.replace(out)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return out

    bpm_str = f"{report.estimated_bpm.bpm:.1f} ({report.estimated_bpm.stability})" if report.estimated_bpm.bpm else "Unknown"
    key_primary = _tr_key(report.estimated_key.primary)
    key_secondary = _tr_key(report.estimated_key.secondary)
    transpose_line = (
        f"- **记谱 / 变调夹移调 (Transpose)**: `{semi:+d} 半音`（实音调性: `{report.estimated_key.primary}`）"
        if semi != 0
        else "- **记谱移调 (Transpose)**: `0 半音 (原调实音)`"
    )
    mod_flags: list[str] = []
    if report.estimated_key.modulation_hint:
        mod_flags.append("全局调性滑动窗口检测到可能转调")
    if report.bass is not None and report.bass.modulation_detected and report.bass.modulation_note:
        mod_flags.append(report.bass.modulation_note)
    lines: list[str] = [
        "# ListenScope 离线分轨与扒谱分析报告",
        "",
        "## 1. 全局调性与节拍概览",
        "",
        f"- **分析时长**: `{report.duration_sec:.2f} s`",
        f"- **和声分析源**: `{report.harmonic_source_label}`",
        transpose_line,
        f"- **推测调性 (Key)**: `{key_primary}`（第二候选: `{key_secondary}`，稳定度: `{report.estimated_key.stability}`）",
        f"- **调性说明**: {report.estimated_key.relation_note}；{report.estimated_key.key_signature_note}",
        f"- **推测速度 (BPM)**: `{bpm_str}`",
    ]
    if mod_flags:
        lines.append(f"- **转调提示 (Modulation)**: {'；'.join(mod_flags)}")
    lines.extend(
        [
            "",
            "## 2. 时间轴和弦进行表 (Chord Timeline)",
            "",
            "| 开始 (s) | 结束 (s) | 和弦候选 | 第二候选 | 相关度 | 稳定度 |",
            "| ---: | ---: | :--- | :--- | ---: | :--- |",
        ]
    )
    for seg in report.chord_timeline:
        lines.append(
            f"| {seg.start_sec:.2f} | {seg.end_sec:.2f} | `{_tr_chord(seg.chord)}` | `{_tr_chord(seg.secondary)}` | {seg.correlation:.3f} | {seg.stability} |"
        )

    if report.bass is not None:
        low_tr = _tr_note(report.bass.lowest_note) or "-"
        high_tr = _tr_note(report.bass.highest_note) or "-"
        low_midi_val = (report.bass.lowest_midi + semi) if report.bass.lowest_midi is not None else None
        high_midi_val = (report.bass.highest_midi + semi) if report.bass.highest_midi is not None else None
        if low_midi_val is not None:
            extra_parts = [f"MIDI {low_midi_val}"]
            if report.bass.lowest_freq_hz is not None:
                extra_parts.append(f"{report.bass.lowest_freq_hz:.1f} Hz")
            if report.bass.lowest_note_time_sec is not None:
                extra_parts.append(f"@ {report.bass.lowest_note_time_sec:.2f}s")
            low_desc = f"`{low_tr}` ({' · '.join(extra_parts)})"
        else:
            low_desc = f"`{low_tr}`"
        high_desc = f"`{high_tr}` (MIDI {high_midi_val})" if high_midi_val is not None else f"`{high_tr}`"
        concert_note = ""
        if semi != 0 and report.bass.lowest_note:
            concert_midi_txt = f" MIDI {report.bass.lowest_midi}" if report.bass.lowest_midi is not None else ""
            concert_note = f"（实音最低 `{report.bass.lowest_note}`{concert_midi_txt}）"
        lines.extend(
            [
                "",
                "## 3. Bass 音轨分析",
                "",
                f"- **最低音**: {low_desc}{concert_note} | **最高音**: {high_desc}",
                f"- **音域**: `{low_tr} ~ {high_tr}`",
                f"- **高频根音级**: `{', '.join(_tr_note(r) for r in report.bass.root_pitch_classes) or '-'}`",
                f"- **提取音符数**: `{len(report.bass.notes)}`",
            ]
        )
        if report.bass.modulation_detected and report.bass.modulation_note:
            lines.append(f"- **贝斯转调提示**: {report.bass.modulation_note}")
        lines.extend(
            [
                "",
                "| 开始 (s) | 结束 (s) | 音名 | MIDI | 基频 (Hz) | 置信度 |",
                "| ---: | ---: | :--- | ---: | ---: | ---: |",
            ]
        )
        for n in report.bass.notes[:120]:
            tr_midi = max(0, min(127, int(n.pitch_midi) + semi))
            midi_cell = f"{tr_midi} (实{n.pitch_midi})" if semi != 0 else f"{n.pitch_midi}"
            lines.append(
                f"| {n.start_sec:.2f} | {n.end_sec:.2f} | `{_tr_note(n.note_name)}` | {midi_cell} | {n.frequency_hz:.1f} | {n.confidence:.2f} |"
            )

    if report.drums is not None:
        lines.extend(
            [
                "",
                "## 4. 鼓组 (Drums) 三频段瞬态与 16 步律动表",
                "",
                f"- **鼓组估计 BPM**: `{report.drums.estimated_bpm or 'Unknown'}` ({report.drums.bpm_stability})",
                f"- **底鼓 Kick (35-130Hz) 触发数**: `{len(report.drums.kick_times_sec)}`",
                f"- **军鼓 Snare (160-2500Hz) 触发数**: `{len(report.drums.snare_times_sec)}`",
                f"- **踩镲 Hi-Hat (4.5-15kHz) 触发数**: `{len(report.drums.hihat_times_sec)}`",
                f"- **16 步参考律动型**: `{' | '.join(report.drums.groove_16_step)}`",
            ]
        )

    if report.melody is not None:
        lines.extend(
            [
                "",
                f"## 5. 主旋律 / 人声分析 (`{report.melody.stem_name}`)",
                "",
                f"- **音域**: `{_tr_note(report.melody.lowest_note) or '-'} ~ {_tr_note(report.melody.highest_note) or '-'}` "
                f"(中位音高: `{_tr_note(report.melody.median_note) or '-'}`)",
                f"- **有声帧占比**: `{report.melody.voiced_ratio * 100:.1f}%`",
                f"- **提取音符数**: `{len(report.melody.notes)}`",
            ]
        )

    if midi_result is not None:
        lines.extend(
            [
                "",
                f"## 6. MIDI 扒谱明细 (`{midi_result.source_stem_name}` · {midi_result.backend_used})",
                "",
                f"- **输出文件**: `{midi_result.output_midi_path}` | **音符数**: `{len(midi_result.notes)}`",
                "",
                "| 音名 | MIDI | 开始 (s) | 结束 (s) | 力度 |",
                "| :--- | ---: | ---: | ---: | ---: |",
            ]
        )
        for n in midi_result.notes[:200]:
            lines.append(f"| `{_tr_note(n.note_name)}` | {n.pitch_midi} | {n.start_sec:.2f} | {n.end_sec:.2f} | {n.velocity} |")

    try:
        tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp_path.replace(out)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return out

