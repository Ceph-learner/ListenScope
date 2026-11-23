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


_LETTERS = ("C", "D", "E", "F", "G", "A", "B")
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_IV_LETTER = {0: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}


def _normalize_chord_quality(suffix: str) -> str:
    s = (suffix or "").strip()
    if s.startswith(("M", "Δ")) and not s.startswith(("Ma", "Mi")):
        s = "maj" + s[1:]
    return s.lower()


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
    quality = _normalize_chord_quality(chord[3])
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
    letter = m.group(1).upper()
    acc_str = m.group(2).replace("♯", "#").replace("♭", "b")
    acc = 1 if acc_str == "#" else (-1 if acc_str == "b" else 0)
    raw_pc = _LETTER_PC[letter] + acc
    oct_str = m.group(3)
    if oct_str is None:
        return PITCH_CLASSES[(raw_pc + semi) % 12]
    midi = (int(oct_str) + 1) * 12 + raw_pc + semi
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
    s_low = _normalize_chord_quality(suffix)
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
    """Return diatonic note spelling (e.g. `'A · C · E'`, `'F · Ab · C'`) for detected chord symbols, or `'-'`."""
    raw = (chord_name or "").strip()
    if not raw or raw in ("-", "N", "N (静音)", "Unknown", "结束"):
        return "-"
    base = raw.split("/", 1)[0].strip()
    m = _CHORD_RE.match(base)
    if not m:
        return "-"
    root_letter = m.group(1).upper()
    acc_str = m.group(2).replace("♯", "#").replace("♭", "b")
    norm_root = _normalize_pitch_token(root_letter + acc_str)
    suffix = (m.group(3) or "").strip()
    if norm_root is None:
        return "-"

    quality = _normalize_chord_quality(suffix)
    intervals = _CHORD_INTERVALS.get(suffix)
    if intervals is None:
        intervals = _CHORD_INTERVALS.get(quality)
    if intervals is None:
        return "-"

    root_acc = 1 if acc_str == "#" else (-1 if acc_str == "b" else 0)
    root_pc = (_LETTER_PC[root_letter] + root_acc) % 12
    root_letter_idx = _LETTERS.index(root_letter)
    spelled: list[str] = []
    for iv in intervals:
        target_pc = (root_pc + iv) % 12
        letter_off = 4 if (quality == "aug" and iv == 8) else _IV_LETTER.get(iv)
        if letter_off is None:
            spelled.append(PITCH_CLASSES[target_pc])
            continue
        note_letter = _LETTERS[(root_letter_idx + letter_off) % 7]
        diff = (target_pc - _LETTER_PC[note_letter]) % 12
        if diff == 0:
            spelled.append(note_letter)
        elif diff == 1:
            spelled.append(f"{note_letter}#")
        elif diff == 11:
            spelled.append(f"{note_letter}b")
        else:
            spelled.append(PITCH_CLASSES[target_pc])
    return " · ".join(spelled)


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


_QUALITY_INTERVALS: dict[str, set[int]] = {
    "": {0, 4, 7},
    "m": {0, 3, 7},
    "dim": {0, 3, 6},
    "aug": {0, 4, 8},
    "maj7": {0, 4, 7, 11},
    "m7": {0, 3, 7, 10},
    "7": {0, 4, 7, 10},
    "sus4": {0, 5, 7},
}


def _split_chord_root_quality(symbol: str) -> tuple[int | None, str]:
    for idx, name in sorted(enumerate(PITCH_CLASSES), key=lambda kv: len(kv[1]), reverse=True):
        if symbol.startswith(name):
            return idx, symbol[len(name):]
    return None, ""


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
        self._name_to_idx: dict[str, int] = {name: i for i, name in enumerate(self._names)}
        self._ema_alpha = ema_alpha
        self._min_correlation = min_correlation
        self._min_margin_for_high = min_margin_for_high
        self._smoothed_chroma: np.ndarray | None = None
        self._smoothed_bass: np.ndarray | None = None

    def reset(self) -> None:
        self._smoothed_chroma = None
        self._smoothed_bass = None

    def update(
        self,
        chroma_12: np.ndarray,
        *,
        is_silent: bool,
        bass_chroma: np.ndarray | None = None,
    ) -> ChordEstimate:
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
            if self._smoothed_bass is not None:
                self._smoothed_bass *= 0.5
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

        if bass_chroma is not None:
            bass_arr = np.asarray(bass_chroma, dtype=np.float32)
            if bass_arr.shape == (12,) and np.all(np.isfinite(bass_arr)) and float(np.linalg.norm(bass_arr)) >= 1e-6:
                if self._smoothed_bass is None:
                    self._smoothed_bass = bass_arr.copy()
                else:
                    self._smoothed_bass = (
                        self._ema_alpha * bass_arr + (1.0 - self._ema_alpha) * self._smoothed_bass
                    ).astype(np.float32)

        norm = float(np.linalg.norm(self._smoothed_chroma))
        vec = self._smoothed_chroma / max(norm, 1e-9)
        scores = self._templates @ vec
        order = np.argsort(scores)[::-1]
        best_idx, second_idx = int(order[0]), int(order[1])
        best_score = float(scores[best_idx])
        second_score = float(scores[second_idx])

        # Disambiguate first-inversion major triad (e.g. C/E) vs relative minor (Em)
        # when the bass's 2nd/3rd harmonics inflate the 3rd/7th pitch classes.
        best_root, best_quality = _split_chord_root_quality(self._names[best_idx])
        if best_root is not None and best_quality == "m":
            maj_root = (best_root - 4) % 12
            maj_idx = self._name_to_idx.get(PITCH_CLASSES[maj_root])
            if (
                maj_idx is not None
                and float(vec[maj_root]) > float(vec[(best_root + 7) % 12])
                and float(scores[maj_idx]) >= best_score - 0.08
            ):
                second_idx = best_idx
                second_score = best_score
                best_idx = maj_idx
                best_score = float(scores[maj_idx])

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

        primary = self._names[best_idx]
        if bass_chroma is not None and self._smoothed_bass is not None:
            if float(np.max(self._smoothed_bass)) > 0.25:
                bass_pc = int(np.argmax(self._smoothed_bass))
                root_pc, quality = _split_chord_root_quality(primary)
                intervals = _QUALITY_INTERVALS.get(quality, {0})
                if root_pc is not None and bass_pc != root_pc and (bass_pc - root_pc) % 12 in intervals:
                    primary = f"{primary}/{PITCH_CLASSES[bass_pc]}"

        return ChordEstimate(
            primary=primary,
            secondary=self._names[second_idx],
            stability=stability,
            correlation=best_score,
            margin=margin,
            is_silent=False,
        )
