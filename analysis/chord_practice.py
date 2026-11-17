"""Deterministic, local practice progressions in major and natural minor."""

from dataclasses import dataclass
from collections.abc import Sequence

from .chords import chord_scale_degree, transpose_key_label
from .chroma import PITCH_CLASSES


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
