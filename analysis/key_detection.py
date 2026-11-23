"""Sliding-window key detection with modern pop/jazz profiles, tonality weighting, and relative key disambiguation."""

from __future__ import annotations

from typing import Optional

import numpy as np

from core.models import KeyEstimate

from .chroma import PITCH_CLASSES

_KEY_PROFILES: dict[str, tuple[np.ndarray, np.ndarray]] = {
    # Albrecht & Shanahan (2013) - best overall pop/rock/jazz balance
    "albrecht": (
        np.array([0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081], dtype=np.float32),
        np.array([0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052], dtype=np.float32),
    ),
    # Sha'ath (2011) - EDM/pop weighted profile
    "shaath": (
        np.array([6.6, 2.0, 3.5, 2.3, 4.3, 4.0, 2.5, 5.2, 2.4, 3.7, 2.3, 3.4], dtype=np.float32),
        np.array([6.5, 2.7, 3.5, 5.4, 2.6, 3.5, 2.5, 5.2, 4.0, 2.7, 4.3, 3.2], dtype=np.float32),
    ),
    # Krumhansl-Kessler (1990) - classical baseline
    "krumhansl": (
        np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=np.float32),
        np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=np.float32),
    ),
    # KeyFinder / Temperley harmonic-minor-aware profile
    "keyfinder": (
        np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0], dtype=np.float32),
        np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0], dtype=np.float32),
    ),
}


def _zscore(v: np.ndarray) -> np.ndarray:
    std = float(np.std(v))
    if std < 1e-8:
        return np.zeros_like(v)
    return (v - float(np.mean(v))) / std


def _build_key_templates(profile: str = "shaath") -> tuple[list[str], np.ndarray]:
    key = (profile or "shaath").strip().lower()
    if key not in _KEY_PROFILES:
        raise ValueError(f"Unknown key profile: {profile!r}")
    major_prof, minor_prof = _KEY_PROFILES[key]
    names: list[str] = []
    rows: list[np.ndarray] = []
    for root_idx, root in enumerate(PITCH_CLASSES):
        names.append(f"{root} major")
        rows.append(_zscore(np.roll(major_prof, root_idx)))
        names.append(f"{root} minor")
        rows.append(_zscore(np.roll(minor_prof, root_idx)))
    return names, np.stack(rows, axis=0)


class KeyDetector:
    """Sliding-window key estimator using tonal hierarchy profiles and tonic priors."""

    def __init__(
        self,
        *,
        min_active_frames: int = 30,
        min_correlation: float = 0.45,
        profile: str = "shaath",
    ) -> None:
        self._profile = profile
        self._names, self._templates = _build_key_templates(profile)
        self._min_active_frames = min_active_frames
        self._min_correlation = min_correlation

    @staticmethod
    def _weighted_mean(mat: np.ndarray, weights: Optional[np.ndarray]) -> np.ndarray:
        if weights is not None and weights.shape[0] == mat.shape[0]:
            w_sum = float(np.sum(weights))
            if np.isfinite(w_sum) and w_sum > 1e-9:
                return np.average(mat, axis=0, weights=weights).astype(np.float32)
        return np.mean(mat, axis=0).astype(np.float32)

    @classmethod
    def _compute_tonic_bonus(
        cls,
        active: np.ndarray,
        *,
        active_weights: Optional[np.ndarray] = None,
        active_bass: Optional[np.ndarray] = None,
        bass_root_prior: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        bass_vec: Optional[np.ndarray] = None
        bass_w = 0.0

        if bass_root_prior is not None and bass_root_prior.shape == (12,) and np.all(np.isfinite(bass_root_prior)):
            raw_b = np.maximum(bass_root_prior.astype(np.float32), 0.0)
            b_max = float(np.max(raw_b))
            if b_max > 1e-9:
                bass_vec = raw_b / b_max
                bass_w = 0.70
        elif active_bass is not None and active_bass.shape[0] == active.shape[0] and active_bass.shape[0] > 0:
            raw_b = np.maximum(cls._weighted_mean(active_bass, active_weights), 0.0)
            b_max = float(np.max(raw_b))
            if b_max > 1e-9:
                bass_vec = raw_b / b_max
                bass_w = 0.55

        edge_n = max(1, int(round(active.shape[0] * 0.15)))
        if active_bass is not None and active_bass.shape[0] == active.shape[0] and active_bass.shape[0] > 0:
            bass_edge_frames = np.vstack([active_bass[:edge_n], active_bass[-edge_n:]])
            edge_raw = np.maximum(np.mean(bass_edge_frames, axis=0).astype(np.float32), 0.0)
        else:
            edge_frames = np.vstack([active[:edge_n], active[-edge_n:]])
            edge_raw = np.maximum(np.mean(edge_frames, axis=0).astype(np.float32), 0.0)
        e_max = float(np.max(edge_raw))
        edge_vec = (edge_raw / e_max) if e_max > 1e-9 else None
        edge_w = 0.30 if edge_vec is not None else 0.0

        if bass_vec is None and edge_vec is None:
            return np.zeros(24, dtype=np.float32)

        num = np.zeros(12, dtype=np.float32)
        den = 0.0
        if bass_vec is not None:
            num += bass_w * bass_vec
            den += bass_w
        if edge_vec is not None:
            num += edge_w * edge_vec
            den += edge_w

        tonic_prior = num / max(den, 1e-9)
        p_min = float(np.min(tonic_prior))
        p_max = float(np.max(tonic_prior))
        if p_max - p_min > 1e-9:
            tonic_prior = (tonic_prior - p_min) / (p_max - p_min)

        bonus_12 = np.clip(
            0.04 * (tonic_prior - float(np.mean(tonic_prior))) / (float(np.std(tonic_prior)) + 1e-6),
            -0.08,
            0.08,
        ).astype(np.float32)
        return np.repeat(bonus_12, 2)

    def _score_mean_chroma(
        self,
        chroma_mat: np.ndarray,
        *,
        frame_weights: Optional[np.ndarray] = None,
        bass_mat: Optional[np.ndarray] = None,
        bass_root_prior: Optional[np.ndarray] = None,
    ) -> tuple[int, int, float, float]:
        mean_chroma = self._weighted_mean(chroma_mat, frame_weights)
        z = _zscore(mean_chroma)
        corrs = (self._templates @ z) / 12.0
        bonus = self._compute_tonic_bonus(
            chroma_mat,
            active_weights=frame_weights,
            active_bass=bass_mat,
            bass_root_prior=bass_root_prior,
        )
        final_scores = corrs + bonus
        order = np.argsort(final_scores)[::-1]
        best_idx, second_idx = int(order[0]), int(order[1])
        if best_idx % 2 == 0:
            r = best_idx // 2
            min_idx = 2 * r + 1
            maj_ev = float(mean_chroma[(r + 4) % 12]) + 0.5 * float(mean_chroma[(r + 9) % 12])
            min_ev = float(mean_chroma[(r + 3) % 12]) + 0.5 * float(mean_chroma[(r + 8) % 12])
            if min_ev > maj_ev and float(final_scores[best_idx] - final_scores[min_idx]) < 0.20:
                best_idx, second_idx = min_idx, best_idx
        margin = float(final_scores[best_idx] - final_scores[second_idx])
        return best_idx, second_idx, float(corrs[best_idx]), margin

    def estimate(
        self,
        chroma_window: np.ndarray,
        *,
        frame_weights: Optional[np.ndarray] = None,
        bass_window: Optional[np.ndarray] = None,
        bass_root_prior: Optional[np.ndarray] = None,
    ) -> KeyEstimate:
        if chroma_window.size == 0 or chroma_window.ndim != 2 or chroma_window.shape[1] != 12:
            return KeyEstimate(
                primary="Unknown",
                secondary="-",
                stability="Insufficient",
                correlation=0.0,
                margin=0.0,
                relation_note="等待有效音频输入",
            )

        finite_mask = np.all(np.isfinite(chroma_window), axis=1)
        clean_window = chroma_window[finite_mask]
        if clean_window.shape[0] == 0:
            return KeyEstimate(
                primary="Unknown",
                secondary="-",
                stability="Insufficient",
                correlation=0.0,
                margin=0.0,
                relation_note="等待有效音频输入",
            )

        w_clean: Optional[np.ndarray] = None
        if frame_weights is not None and frame_weights.ndim == 1 and frame_weights.shape[0] == chroma_window.shape[0]:
            w_sub = frame_weights[finite_mask]
            w_clean = np.where(np.isfinite(w_sub) & (w_sub > 0.0), w_sub, 0.0).astype(np.float32)

        b_clean: Optional[np.ndarray] = None
        if bass_window is not None and bass_window.ndim == 2 and bass_window.shape == chroma_window.shape:
            b_sub = bass_window[finite_mask]
            b_clean = np.where(np.isfinite(b_sub), b_sub, 0.0).astype(np.float32)

        norms = np.linalg.norm(clean_window, axis=1)
        active_mask = norms > 1e-4
        active = clean_window[active_mask]
        if active.shape[0] < self._min_active_frames:
            return KeyEstimate(
                primary="Unknown",
                secondary="-",
                stability="Insufficient",
                correlation=0.0,
                margin=0.0,
                relation_note=f"有效音频帧不足 ({active.shape[0]}/{self._min_active_frames})",
            )

        active_w = w_clean[active_mask] if w_clean is not None else None
        active_b = b_clean[active_mask] if b_clean is not None else None

        b_idx, s_idx, b_corr, margin = self._score_mean_chroma(
            active,
            frame_weights=active_w,
            bass_mat=active_b,
            bass_root_prior=bass_root_prior,
        )
        primary = self._names[b_idx]
        secondary = self._names[s_idx]

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
            h1_idx, _, h1_corr, h1_margin = self._score_mean_chroma(
                active[:mid],
                frame_weights=active_w[:mid] if active_w is not None else None,
                bass_mat=active_b[:mid] if active_b is not None else None,
            )
            h2_idx, _, h2_corr, h2_margin = self._score_mean_chroma(
                active[mid:],
                frame_weights=active_w[mid:] if active_w is not None else None,
                bass_mat=active_b[mid:] if active_b is not None else None,
            )
            if (
                h1_idx != h2_idx
                and h1_corr >= 0.70
                and h2_corr >= 0.70
                and h1_margin >= 0.05
                and h2_margin >= 0.05
            ):
                modulation = True
                primary = self._names[h2_idx]
                secondary = self._names[h1_idx]
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
