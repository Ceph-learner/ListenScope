"""Deterministic, local practice progressions in major and natural minor."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

import mido
import numpy as np

from .chords import (
    _CHORD_INTERVALS,
    _CHORD_RE,
    _normalize_pitch_token,
    chord_scale_degree,
    transpose_chord_symbol,
    transpose_key_label,
)
from .chroma import PITCH_CLASSES

DEFAULT_PRACTICE_BPM = 120.0
DEFAULT_BEATS_PER_CHORD = 4

_PRACTICE_EXTRA_INTERVALS: dict[str, tuple[int, ...]] = {
    **_CHORD_INTERVALS,
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "min6": (0, 3, 7, 9),
    "5": (0, 7),
    "dim7": (0, 3, 6, 9),
    "m7b5": (0, 3, 6, 10),
    "add9": (0, 4, 7, 14),
    "9": (0, 4, 7, 10, 14),
    "m9": (0, 3, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
}

# One conventional key spelling per pitch class.
_KEY_ROOTS = {
    "major": ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"),
    "minor": ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"),
}
PRACTICE_KEYS = tuple(f"{root} {mode}" for mode, roots in _KEY_ROOTS.items() for root in roots)
_SCALES = {
    "major": ((0, 2, 4, 5, 7, 9, 11), ("I", "ii", "iii", "IV", "V", "vi", "vii°")),
    "minor": ((0, 2, 3, 5, 7, 8, 10), ("i", "ii°", "III", "iv", "v", "VI", "VII")),
}
_TEMPLATES = {
    "major": ((1, 5, 6, 4), (6, 4, 1, 5), (1, 6, 4, 5), (2, 5, 1), (1, 4, 5, 1)),
    "minor": ((1, 6, 3, 7), (1, 7, 6, 7), (1, 4, 5, 1), (1, 3, 7, 6)),
}


@dataclass(frozen=True)
class PracticeProgression:
    degrees: tuple[str, ...]
    chords: tuple[str, ...]
    matched_steps: int


def practice_key(label: str) -> str | None:
    root, _, mode = transpose_key_label(label, 12).partition(" ")
    if root not in PITCH_CLASSES or mode not in _KEY_ROOTS:
        return None
    return f"{_KEY_ROOTS[mode][PITCH_CLASSES.index(root)]} {mode}"


def recommend_progressions(key: str, recent_chords: Sequence[str]) -> list[PracticeProgression]:
    key = practice_key(key)
    if key is None:
        return []
    root, mode = key.split()
    tonic = PITCH_CLASSES.index(transpose_key_label(key, 12).split()[0])
    offsets, degree_names = _SCALES[mode]
    letters = "CDEFGAB"
    first_letter = letters.index(root[0])
    symbols = []
    for index, (offset, degree) in enumerate(zip(offsets, degree_names)):
        letter = letters[(first_letter + index) % 7]
        shift = (tonic + offset - PITCH_CLASSES.index(letter) + 6) % 12 - 6
        accidental = "#" * shift if shift >= 0 else "b" * -shift
        quality = "dim" if degree.endswith("°") else ("m" if degree.islower() else "")
        symbols.append(letter + accidental + quality)

    recent = []
    for chord in recent_chords[-12:]:
        degree = chord_scale_degree(chord, key).removesuffix("maj7").removesuffix("7")
        if not recent or recent[-1] != degree:
            recent.append(degree)
    results = []
    for template in _TEMPLATES[mode]:
        degrees = tuple(degree_names[index - 1] for index in template)
        matched = next((
            count for count in range(min(len(recent), len(degrees)), 0, -1)
            if tuple(recent[-count:]) == degrees[:count]
        ), 0)
        results.append(PracticeProgression(degrees, tuple(symbols[index - 1] for index in template), matched))
    # Stable sort leaves the curated order in place when histories tie.
    return sorted(results, key=lambda item: -item.matched_steps)


def sounding_chord_progression(chords: Sequence[str], transpose: int) -> tuple[str, ...]:
    """Convert displayed practice chords back to concert sounding pitch under Capo/instrument transpose."""
    semi = int(transpose)
    if semi == 0:
        return tuple(chords)
    return tuple(transpose_chord_symbol(chord, -semi) for chord in chords)


def chord_midi_notes(chord_name: str, *, root_octave: int = 4) -> tuple[int, ...]:
    """Return closed-position MIDI pitches (ascending) for a chord symbol."""
    raw = (chord_name or "").strip()
    if not raw or raw in ("-", "N", "N (静音)", "Unknown", "Insufficient", "结束"):
        raise ValueError(f"不支持的和弦符号: {chord_name!r}")

    bass_pc: int | None = None
    main_part = raw
    if "/" in raw:
        main_part, bass_part = raw.split("/", 1)
        main_part = main_part.strip()
        bass_norm = _normalize_pitch_token(bass_part.strip())
        if bass_norm is None:
            raise ValueError(f"不支持的低音和弦符号: {chord_name!r}")
        bass_pc = PITCH_CLASSES.index(bass_norm)

    match = _CHORD_RE.fullmatch(main_part)
    if match is None:
        raise ValueError(f"不支持的和弦符号: {chord_name!r}")
    norm_root = _normalize_pitch_token(match[1] + match[2])
    from .chords import _normalize_chord_quality

    suffix = match[3].strip()
    quality = _normalize_chord_quality(suffix)
    if suffix in _PRACTICE_EXTRA_INTERVALS:
        intervals = _PRACTICE_EXTRA_INTERVALS[suffix]
    elif quality in _PRACTICE_EXTRA_INTERVALS:
        intervals = _PRACTICE_EXTRA_INTERVALS[quality]
    else:
        raise ValueError(f"不支持的和弦性质: {chord_name!r}")
    if norm_root is None:
        raise ValueError(f"不支持的和弦根音: {chord_name!r}")

    root_pc = PITCH_CLASSES.index(norm_root)
    root_midi = (int(root_octave) + 1) * 12 + root_pc
    notes = tuple(root_midi + interval for interval in intervals)
    if bass_pc is not None:
        bass_midi = bass_pc + 12 * ((root_midi - 1 - bass_pc) // 12)
        notes = (bass_midi, *notes)
    if any(note < 0 or note > 127 for note in notes):
        raise ValueError(f"和弦 MIDI 音高超出范围 (0–127): {chord_name!r}")
    return notes


def _validate_practice_tempo(bpm: float) -> float:
    if isinstance(bpm, bool) or not isfinite(float(bpm)) or float(bpm) <= 0:
        raise ValueError("速度 (BPM) 必须为正数。")
    return float(bpm)


from .midi_common import write_cubase_note_spans


def export_chord_progression_midi(
    chords: Sequence[str],
    destination: Path | str,
    *,
    bpm: float = DEFAULT_PRACTICE_BPM,
    beats_per_chord: int = DEFAULT_BEATS_PER_CHORD,
    channel: int = 0,
    velocity: int = 80,
    key_signature: str | None = None,
    time_signature: tuple[int, int] = (4, 4),
) -> int:
    """Save a chord progression on a melodic MIDI channel atomically (Cubase SMF-compliant) and return chord count."""
    chord_list = list(chords)
    if not chord_list:
        raise ValueError("当前没有可导出的和弦进行。")
    if isinstance(beats_per_chord, bool) or int(beats_per_chord) < 1:
        raise ValueError("每个和弦至少需要 1 拍。")
    if isinstance(channel, bool) or not 0 <= int(channel) <= 15:
        raise ValueError("MIDI 通道必须在 0–15 之间。")

    valid_bpm = _validate_practice_tempo(bpm)
    beats = int(beats_per_chord)
    melodic_channel = int(channel)
    note_velocity = max(1, min(127, int(velocity)))
    chord_note_groups = [chord_midi_notes(chord) for chord in chord_list]

    ticks_per_beat = 480
    chord_ticks = beats * ticks_per_beat
    spans: list[tuple[int, int, int, int, int]] = []
    for idx, notes in enumerate(chord_note_groups):
        st = idx * chord_ticks
        et = (idx + 1) * chord_ticks
        for note in notes:
            spans.append((st, et, melodic_channel, note, note_velocity))

    write_cubase_note_spans(
        spans,
        destination,
        track_name="ListenScope Chord Practice",
        tempo_bpm=valid_bpm,
        channel=melodic_channel,
        program=0 if melodic_channel != 9 else None,
        time_signature=time_signature,
        key_signature=key_signature,
        ticks_per_beat=ticks_per_beat,
    )
    return len(chord_note_groups)


def render_chord_progression_preview(
    chords: Sequence[str],
    sample_rate: int,
    *,
    bpm: float = DEFAULT_PRACTICE_BPM,
    beats_per_chord: int = DEFAULT_BEATS_PER_CHORD,
) -> np.ndarray:
    """Synthesize a click-free local chord audition buffer matching MIDI tempo and chord duration."""
    if int(sample_rate) <= 0:
        raise ValueError("采样率必须为正数。")
    if isinstance(beats_per_chord, bool) or int(beats_per_chord) < 1:
        raise ValueError("每个和弦至少需要 1 拍。")
    valid_bpm = _validate_practice_tempo(bpm)

    chord_list = list(chords)
    if not chord_list:
        return np.empty(0, dtype=np.float32)

    chord_note_groups = [chord_midi_notes(chord) for chord in chord_list]
    sr = int(sample_rate)
    chord_sec = float(int(beats_per_chord)) * 60.0 / valid_bpm
    boundaries = [round(index * chord_sec * sr) for index in range(len(chord_note_groups) + 1)]
    total_samples = boundaries[-1]
    if total_samples <= 0:
        return np.empty(0, dtype=np.float32)

    preview = np.zeros(total_samples, dtype=np.float32)
    decay_tau = max(0.35, 0.72 * chord_sec)

    for index, notes in enumerate(chord_note_groups):
        start = boundaries[index]
        stop = boundaries[index + 1]
        count = stop - start
        if count <= 0:
            continue
        t = np.arange(count, dtype=np.float64) / float(sr)
        chord_wave = np.zeros(count, dtype=np.float64)
        for midi_note in notes:
            freq = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
            if freq >= 0.45 * sr:
                continue
            tone = 0.68 * np.sin(2.0 * np.pi * freq * t)
            if 2.0 * freq < 0.45 * sr:
                tone += 0.22 * np.sin(2.0 * np.pi * 2.0 * freq * t) * np.exp(-t / 0.45)
            if 3.0 * freq < 0.45 * sr:
                tone += 0.10 * np.sin(2.0 * np.pi * 3.0 * freq * t) * np.exp(-t / 0.25)
            chord_wave += tone
        chord_wave *= (0.45 / max(1, len(notes))) * np.exp(-t / decay_tau)

        attack = min(count // 3, max(1, round(0.008 * sr)))
        release = min(count // 2, max(1, round(0.015 * sr)))
        if attack > 0:
            chord_wave[:attack] *= np.linspace(0.0, 1.0, attack)
        if release > 0:
            chord_wave[-release:] *= np.linspace(1.0, 0.0, release)
        preview[start:stop] = chord_wave.astype(np.float32)

    if total_samples >= 2:
        preview[0] = 0.0
        preview[-1] = 0.0
    peak = float(np.max(np.abs(preview), initial=0.0))
    if peak > 0.65:
        preview *= np.float32(0.65 / peak)
    return preview
