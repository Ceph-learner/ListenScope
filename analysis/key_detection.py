"""Krumhansl-Schmuckler sliding-window key detection with relative/modal/modulation awareness."""

from __future__ import annotations

import numpy as np

from core.models import KeyEstimate

from .chroma import PITCH_CLASSES

# Krumhansl-Kessler (1990) tonal hierarchy profiles
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=np.float32)
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=np.float32)


def _zscore(v: np.ndarray) -> np.ndarray:
    std = float(np.std(v))
    if std < 1e-8:
        return np.zeros_like(v)
    return (v - float(np.mean(v))) / std


def _build_key_templates() -> tuple[list[str], np.ndarray]:
    names: list[str] = []
    rows: list[np.ndarray] = []
    for root_idx, root in enumerate(PITCH_CLASSES):
        names.append(f"{root} major")
        rows.append(_zscore(np.roll(_MAJOR_PROFILE, root_idx)))
        names.append(f"{root} minor")
        rows.append(_zscore(np.roll(_MINOR_PROFILE, root_idx)))
    return names, np.stack(rows, axis=0)


class KeyDetector:
    """Sliding-window key estimator using Krumhansl-Schmuckler profiles."""

    def __init__(self, *, min_active_frames: int = 30, min_correlation: float = 0.45) -> None:
        self._names, self._templates = _build_key_templates()
        self._min_active_frames = min_active_frames
        self._min_correlation = min_correlation

    def _score_mean_chroma(self, chroma_mat: np.ndarray) -> tuple[int, int, float, float]:
        mean_chroma = np.mean(chroma_mat, axis=0)
        z = _zscore(mean_chroma)
        corrs = (self._templates @ z) / 12.0
        order = np.argsort(corrs)[::-1]
        best_idx, second_idx = int(order[0]), int(order[1])
        return best_idx, second_idx, float(corrs[best_idx]), float(corrs[second_idx])

    def estimate(self, chroma_window: np.ndarray) -> KeyEstimate:
        if chroma_window.size == 0:
            return KeyEstimate(
                primary="Unknown",
                secondary="-",
                stability="Insufficient",
                correlation=0.0,
                margin=0.0,
                relation_note="等待有效音频输入",
            )

        norms = np.linalg.norm(chroma_window, axis=1)
        active = chroma_window[norms > 1e-4]
        if active.shape[0] < self._min_active_frames:
            return KeyEstimate(
                primary="Unknown",
                secondary="-",
                stability="Insufficient",
                correlation=0.0,
                margin=0.0,
                relation_note=f"有效音频帧不足 ({active.shape[0]}/{self._min_active_frames})",
            )

        b_idx, s_idx, b_corr, s_corr = self._score_mean_chroma(active)
        primary = self._names[b_idx]
        secondary = self._names[s_idx]
        margin = b_corr - s_corr

        if b_corr < self._min_correlation:
            return KeyEstimate(
                primary="Unknown",
                secondary=primary,
                stability="Low",
                correlation=b_corr,
                margin=margin,
                relation_note="调性证据不足或为无调性/打击乐段落",
            )

        # Check relative major/minor (major root index i == minor root index (i+9)%12 -> b_idx//2 vs s_idx//2)
        relation_notes: list[str] = []
        p_root, p_mode = primary.split()
        s_root, s_mode = secondary.split()
        p_pc = PITCH_CLASSES.index(p_root)
        s_pc = PITCH_CLASSES.index(s_root)
        if p_mode != s_mode and ((p_mode == "major" and (p_pc + 9) % 12 == s_pc) or (p_mode == "minor" and (p_pc + 3) % 12 == s_pc)):
            if margin < 0.08:
                relation_notes.append(f"关系大小调接近 ({primary} / {secondary})")
        elif p_pc == s_pc and p_mode != s_mode and margin < 0.08:
            relation_notes.append(f"同主音调式混合倾向 ({primary} / {secondary})")

        # Check modulation across first vs second half of window
        modulation = False
        if active.shape[0] >= self._min_active_frames * 2:
            mid = active.shape[0] // 2
            h1_idx, _, h1_corr, _ = self._score_mean_chroma(active[:mid])
            h2_idx, _, h2_corr, _ = self._score_mean_chroma(active[mid:])
            if h1_idx != h2_idx and h1_corr >= 0.55 and h2_corr >= 0.55:
                modulation = True
                relation_notes.append(f"疑似转调: {self._names[h1_idx]} -> {self._names[h2_idx]}")

        if margin >= 0.08 and b_corr >= 0.65 and not modulation:
            stability = "High"
        elif margin >= 0.03 and b_corr >= 0.52:
            stability = "Medium"
        else:
            stability = "Low"

        return KeyEstimate(
            primary=primary,
            secondary=secondary,
            stability=stability,
            correlation=b_corr,
            margin=margin,
            relation_note="；".join(relation_notes) if relation_notes else "调性中心稳定",
            modulation_hint=modulation,
        )
