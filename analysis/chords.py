"""CPU chord candidate matcher (12 Major, 12 Minor, N / Unknown) with temporal smoothing."""

from __future__ import annotations

import numpy as np

from core.models import ChordEstimate

from .chroma import PITCH_CLASSES


def _build_chord_templates() -> tuple[list[str], np.ndarray]:
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

    return names, np.stack(templates, axis=0)


class ChordDetector:
    """Template-based chord estimator with EMA smoothing, silence gating, and Unknown fallback."""

    def __init__(
        self,
        *,
        ema_alpha: float = 0.35,
        min_correlation: float = 0.58,
        min_margin_for_high: float = 0.08,
    ) -> None:
        self._names, self._templates = _build_chord_templates()
        self._ema_alpha = ema_alpha
        self._min_correlation = min_correlation
        self._min_margin_for_high = min_margin_for_high
        self._smoothed_chroma: np.ndarray | None = None

    def reset(self) -> None:
        self._smoothed_chroma = None

    def update(self, chroma_12: np.ndarray, *, is_silent: bool) -> ChordEstimate:
        if is_silent or float(np.linalg.norm(chroma_12)) < 1e-6:
            # Decay smoother slightly on silence so stale chords do not linger
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
            self._smoothed_chroma = chroma_12.astype(np.float32, copy=True)
        else:
            self._smoothed_chroma = (
                self._ema_alpha * chroma_12 + (1.0 - self._ema_alpha) * self._smoothed_chroma
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
