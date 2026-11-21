"""CPU chord candidate matcher (12 Major, 12 Minor, N / Unknown) with temporal smoothing."""

from __future__ import annotations

import re
import numpy as np

from core.models import ChordEstimate

from .chroma import PITCH_CLASSES


_FLAT_TO_SHARP = {
    "DB": "C#",
    "EB": "D#",
    "FB": "E",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
    "E#": "F",
    "B#": "C",
    "CB": "B",
}

_CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "maj": (0, 4, 7),
    "m": (0, 3, 7),
    "min": (0, 3, 7),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "min7": (0, 3, 7, 10),
    "7": (0, 4, 7, 10),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
}

_EXTRA_CHORD_SUFFIXES = {"6", "m6", "min6", "9", "m9", "maj9", "add9", "5", "dim7", "m7b5"}
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b♯♭]?)(.*)$")
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b♯♭]?)(-?\d+)?$")
_KEY_RE = re.compile(r"^([A-Ga-g][#b♯♭]?)\s+(major|minor|大调|小调)$", re.IGNORECASE)
_MAJOR_DEGREES = ("I", "♭II", "II", "♭III", "III", "IV", "♯IV", "V", "♭VI", "VI", "♭VII", "VII")
_MINOR_DEGREES = ("I", "♭II", "II", "III", "♯III", "IV", "♯IV", "V", "VI", "♯VI", "VII", "♯VII")
_MINOR_QUALITIES = {"m", "min", "m6", "min6", "m7", "min7", "m9", "dim", "dim7", "m7b5"}
_DEGREE_SUFFIXES = {"maj": "", "m": "", "min": "", "m6": "6", "min6": "6", "m7": "7", "min7": "7",
                    "m9": "9", "dim": "°", "dim7": "°7", "m7b5": "ø7", "aug": "+"}


def _normalize_pitch_token(token: str) -> str | None:
    clean = (token or "").strip().replace("♯", "#").replace("♭", "b")
    if not clean:
        return None
    norm = _FLAT_TO_SHARP.get(clean.upper(), clean[0].upper() + clean[1:])
    return norm if norm in PITCH_CLASSES else None


def chord_scale_degree(chord_name: str, key_label: str) -> str:
    """Label the root relative to the detected major or natural minor scale."""
    key = _KEY_RE.fullmatch(key_label.strip())
    chord = _CHORD_RE.fullmatch(chord_name.split("/", 1)[0].strip())
    if key is None or chord is None:
        return "-"
    tonic = _normalize_pitch_token(key[1])
    root = _normalize_pitch_token(chord[1] + chord[2])
    suffix = chord[3].strip()
    quality = "maj" if suffix == "M" else suffix.lower()
    if tonic is None or root is None or (quality not in _CHORD_INTERVALS and quality not in _EXTRA_CHORD_SUFFIXES):
        return "-"
    degrees = _MINOR_DEGREES if key[2].lower() in ("minor", "小调") else _MAJOR_DEGREES
    degree = degrees[(PITCH_CLASSES.index(root) - PITCH_CLASSES.index(tonic)) % 12]
    if quality in _MINOR_QUALITIES:
        degree = degree.lower()
    return degree + _DEGREE_SUFFIXES.get(quality, quality)


def transpose_note_name(note_name: str, semitones: int) -> str:
    """Shift a pitch class (`C`, `Bb`) or octave-tagged note (`A4`, `C#3`) by `semitones`."""
    raw = (note_name or "").strip()
    semi = int(semitones)
    if semi == 0 or not raw or raw in ("-", "N", "N (静音)", "Unknown", "Insufficient", "结束"):
        return raw
    m = _NOTE_RE.match(raw)
    if not m:
        return raw
    norm_root = _normalize_pitch_token(m.group(1) + m.group(2))
    if norm_root is None:
        return raw
    idx = PITCH_CLASSES.index(norm_root)
    oct_str = m.group(3)
    if oct_str is None:
        return PITCH_CLASSES[(idx + semi) % 12]
    midi = (int(oct_str) + 1) * 12 + idx + semi
    return f"{PITCH_CLASSES[midi % 12]}{(midi // 12) - 1}"


def transpose_chord_symbol(chord_name: str, semitones: int) -> str:
    """Shift a chord symbol (supporting slash bass & triad/7th/sus qualities) by `semitones`."""
    raw = (chord_name or "").strip()
    semi = int(semitones)
    if semi == 0 or not raw or raw in ("-", "N", "N (静音)", "Unknown", "结束"):
        return raw

    if "/" in raw:
        main_part, bass_part = raw.split("/", 1)
        new_main = transpose_chord_symbol(main_part, semi)
        if new_main == main_part.strip() and not _CHORD_RE.match(main_part.strip()):
            return raw
        new_bass = transpose_note_name(bass_part, semi)
        return f"{new_main}/{new_bass}"

    m = _CHORD_RE.match(raw)
    if not m:
        return raw
    norm_root = _normalize_pitch_token(m.group(1) + m.group(2))
    suffix = (m.group(3) or "").strip()
    if norm_root is None:
        return raw
    s_low = suffix.lower()
    if suffix not in _CHORD_INTERVALS and s_low not in _CHORD_INTERVALS and s_low not in _EXTRA_CHORD_SUFFIXES:
        return raw

    new_root = PITCH_CLASSES[(PITCH_CLASSES.index(norm_root) + semi) % 12]
    return f"{new_root}{suffix}"


def transpose_key_label(key_label: str, semitones: int) -> str:
    """Shift key labels like `'C major'` or `'F# minor'` by `semitones`."""
    raw = (key_label or "").strip()
    semi = int(semitones)
    if semi == 0 or not raw or raw in ("-", "Unknown", "Insufficient"):
        return raw
    m = _KEY_RE.match(raw)
    if not m:
        return raw
    new_tonic = transpose_note_name(m.group(1), semi)
    return f"{new_tonic} {m.group(2)}"


_ENHARMONIC_KEY_DISPLAY: dict[str, str] = {
    "C# major": "C# / Db major",
    "D# major": "D# / Eb major",
    "F# major": "F# / Gb major",
    "G# major": "G# / Ab major",
    "A# major": "A# / Bb major",
    "D# minor": "D# / Eb minor",
    "G# minor": "G# / Ab minor",
    "A# minor": "A# / Bb minor",
}


def format_key_display(key_label: str) -> str:
    """Format a key label with enharmonic hint (e.g. `'G# major'` -> `'G# / Ab major'`)."""
    clean = (key_label or "").strip()
    return _ENHARMONIC_KEY_DISPLAY.get(clean, clean)


def spell_chord_tones(chord_name: str) -> str:
    """Return chromatic note spelling (e.g. `'A · C · E'`) for detected chord symbols, or `'-'`."""
    raw = (chord_name or "").strip()
    if not raw or raw in ("-", "N", "N (静音)", "Unknown", "结束"):
        return "-"
    base = raw.split("/", 1)[0].strip()
    m = _CHORD_RE.match(base)
    if not m:
        return "-"
    norm_root = _normalize_pitch_token(m.group(1) + m.group(2))
    suffix = (m.group(3) or "").strip()
    if norm_root is None:
        return "-"

    intervals = _CHORD_INTERVALS.get(suffix)
    if intervals is None:
        intervals = _CHORD_INTERVALS.get(suffix.lower())
    if intervals is None:
        return "-"

    root_idx = PITCH_CLASSES.index(norm_root)
    return " · ".join(PITCH_CLASSES[(root_idx + iv) % 12] for iv in intervals)


def _build_chord_templates(*, include_sevenths: bool = False) -> tuple[list[str], np.ndarray]:
    names: list[str] = []
    templates: list[np.ndarray] = []
    # Root weighted slightly higher than 3rd and 5th
    maj_pattern = np.array([1.0, 0, 0, 0, 0.85, 0, 0, 0.90, 0, 0, 0, 0], dtype=np.float32)
    min_pattern = np.array([1.0, 0, 0, 0.85, 0, 0, 0, 0.90, 0, 0, 0, 0], dtype=np.float32)
    maj_pattern /= np.linalg.norm(maj_pattern)
    min_pattern /= np.linalg.norm(min_pattern)

    for root_idx, root_name in enumerate(PITCH_CLASSES):
        names.append(root_name)
        templates.append(np.roll(maj_pattern, root_idx))
        names.append(f"{root_name}m")
        templates.append(np.roll(min_pattern, root_idx))

    if include_sevenths:
        maj7_p = np.array([1.0, 0, 0, 0, 0.82, 0, 0, 0.85, 0, 0, 0, 0.72], dtype=np.float32)
        min7_p = np.array([1.0, 0, 0, 0.82, 0, 0, 0, 0.85, 0, 0, 0.72, 0], dtype=np.float32)
        dom7_p = np.array([1.0, 0, 0, 0, 0.82, 0, 0, 0.85, 0, 0, 0.72, 0], dtype=np.float32)
        sus4_p = np.array([1.0, 0, 0, 0, 0, 0.82, 0, 0.90, 0, 0, 0, 0], dtype=np.float32)
        for p in (maj7_p, min7_p, dom7_p, sus4_p):
            p /= np.linalg.norm(p)

        for root_idx, root_name in enumerate(PITCH_CLASSES):
            names.append(f"{root_name}maj7")
            templates.append(np.roll(maj7_p, root_idx))
            names.append(f"{root_name}m7")
            templates.append(np.roll(min7_p, root_idx))
            names.append(f"{root_name}7")
            templates.append(np.roll(dom7_p, root_idx))
            names.append(f"{root_name}sus4")
            templates.append(np.roll(sus4_p, root_idx))

    return names, np.stack(templates, axis=0)


class ChordDetector:
    """Template-based chord estimator with EMA smoothing, silence gating, and Unknown fallback."""

    def __init__(
        self,
        *,
        ema_alpha: float = 0.35,
        min_correlation: float = 0.58,
        min_margin_for_high: float = 0.08,
        include_sevenths: bool = False,
    ) -> None:
        self._include_sevenths = bool(include_sevenths)
        self._names, self._templates = _build_chord_templates(include_sevenths=self._include_sevenths)
        self._ema_alpha = ema_alpha
        self._min_correlation = min_correlation
        self._min_margin_for_high = min_margin_for_high
        self._smoothed_chroma: np.ndarray | None = None

    def reset(self) -> None:
        self._smoothed_chroma = None

    def update(self, chroma_12: np.ndarray, *, is_silent: bool) -> ChordEstimate:
        arr = np.asarray(chroma_12, dtype=np.float32)
        if (
            is_silent
            or arr.shape != (12,)
            or not np.all(np.isfinite(arr))
            or float(np.linalg.norm(arr)) < 1e-6
        ):
            # Decay smoother slightly on silence or invalid frames so stale chords do not linger
            if self._smoothed_chroma is not None:
                self._smoothed_chroma *= 0.5
            return ChordEstimate(
                primary="N (静音)",
                secondary="-",
                stability="Silent",
                correlation=0.0,
                margin=0.0,
                is_silent=True,
            )

        if self._smoothed_chroma is None:
            self._smoothed_chroma = arr.copy()
        else:
            self._smoothed_chroma = (
                self._ema_alpha * arr + (1.0 - self._ema_alpha) * self._smoothed_chroma
            ).astype(np.float32)

        norm = float(np.linalg.norm(self._smoothed_chroma))
        vec = self._smoothed_chroma / max(norm, 1e-9)
        scores = self._templates @ vec
        order = np.argsort(scores)[::-1]
        best_idx, second_idx = int(order[0]), int(order[1])
        best_score = float(scores[best_idx])
        second_score = float(scores[second_idx])
        margin = best_score - second_score

        if best_score < self._min_correlation:
            return ChordEstimate(
                primary="Unknown",
                secondary=self._names[best_idx],
                stability="Low",
                correlation=best_score,
                margin=margin,
                is_silent=False,
            )

        if margin >= self._min_margin_for_high and best_score >= 0.72:
            stability = "High"
        elif margin >= 0.03 and best_score >= 0.64:
            stability = "Medium"
        else:
            stability = "Low"

        return ChordEstimate(
            primary=self._names[best_idx],
            secondary=self._names[second_idx],
            stability=stability,
            correlation=best_score,
            margin=margin,
            is_silent=False,
        )
