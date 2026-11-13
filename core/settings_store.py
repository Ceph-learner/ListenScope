"""Persistent settings loader/saver for ResourceLimits, AIConfig, AI worker path, and practice tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import logging
import math
from pathlib import Path
from typing import Any, Optional

from .config import AIConfig, ResourceLimits

logger = logging.getLogger(__name__)


@dataclass
class PersistedSettings:
    resource_limits: ResourceLimits
    ai_config: AIConfig
    ai_python_executable: str = ""
    midi_python_executable: str = ""
    metronome_bpm: float = 120.0
    metronome_beats_per_bar: int = 4
    metronome_volume: float = 0.70
    metronome_count_in: bool = False
    transpose_semitones: int = 0
    schema_version: int = 2


def default_settings_path() -> Path:
    return Path.home() / ".listenscope" / "settings.json"


def _clamp_practice_values(
    *,
    metronome_bpm: Any = 120.0,
    metronome_beats_per_bar: Any = 4,
    metronome_volume: Any = 0.70,
    metronome_count_in: Any = False,
    transpose_semitones: Any = 0,
) -> dict[str, Any]:
    try:
        bpm = float(metronome_bpm)
        if not math.isfinite(bpm):
            bpm = 120.0
    except Exception:
        bpm = 120.0
    bpm = round(max(30.0, min(240.0, bpm)), 1)

    try:
        beats = int(metronome_beats_per_bar)
    except Exception:
        beats = 4
    if beats not in (2, 3, 4, 6):
        beats = max(1, min(12, beats))

    try:
        vol = float(metronome_volume)
        if not math.isfinite(vol):
            vol = 0.70
    except Exception:
        vol = 0.70
    vol = round(max(0.0, min(1.5, vol)), 2)

    count_in = bool(metronome_count_in) if isinstance(metronome_count_in, bool) else False

    try:
        semi = int(transpose_semitones)
    except Exception:
        semi = 0
    semi = max(-11, min(11, semi))

    return {
        "metronome_bpm": bpm,
        "metronome_beats_per_bar": beats,
        "metronome_volume": vol,
        "metronome_count_in": count_in,
        "transpose_semitones": semi,
    }


def _filter_dataclass_kwargs(cls: type[Any], raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    valid_names = {f.name for f in fields(cls)}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in valid_names:
            continue
        if k == "demucs_segment_ladder" and isinstance(v, list):
            try:
                v = tuple(int(x) for x in v)
            except Exception:
                continue
        out[k] = v
    return out


def load_settings(path: Optional[Path | str] = None) -> PersistedSettings:
    """Load settings JSON with strict validation and safe fallback on malformed/unsafe values."""
    target = Path(path) if path is not None else default_settings_path()
    default_limits = ResourceLimits()
    default_ai = AIConfig()
    if not target.exists():
        return PersistedSettings(
            resource_limits=default_limits,
            ai_config=default_ai,
            ai_python_executable="",
            midi_python_executable="",
        )

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("settings root JSON must be an object")
    except Exception as exc:
        logger.warning("Failed to parse settings file %s (%s); using safe defaults.", target, exc)
        return PersistedSettings(
            resource_limits=default_limits,
            ai_config=default_ai,
            ai_python_executable="",
            midi_python_executable="",
        )

    try:
        lim_kwargs = _filter_dataclass_kwargs(ResourceLimits, payload.get("resource_limits"))
        # Hard safety invariants enforced on load
        lim_kwargs["max_concurrent_ai_jobs"] = 1
        lim_kwargs["max_loaded_models"] = 1
        limits = ResourceLimits(**lim_kwargs)
    except Exception as exc:
        logger.warning("Invalid saved ResourceLimits in %s (%s); using safe defaults.", target, exc)
        limits = default_limits

    try:
        ai_kwargs = _filter_dataclass_kwargs(AIConfig, payload.get("ai_config"))
        ai_kwargs["demucs_jobs"] = 1
        ai_kwargs["demucs_shifts"] = 1
        ai_cfg = AIConfig(**ai_kwargs)
    except Exception as exc:
        logger.warning("Invalid saved AIConfig in %s (%s); using safe defaults.", target, exc)
        ai_cfg = default_ai

    raw_py = payload.get("ai_python_executable", "")
    ai_python = str(raw_py).strip() if isinstance(raw_py, str) else ""
    raw_midi_py = payload.get("midi_python_executable", "")
    midi_python = str(raw_midi_py).strip() if isinstance(raw_midi_py, str) else ""
    practice = _clamp_practice_values(
        metronome_bpm=payload.get("metronome_bpm", 120.0),
        metronome_beats_per_bar=payload.get("metronome_beats_per_bar", 4),
        metronome_volume=payload.get("metronome_volume", 0.70),
        metronome_count_in=payload.get("metronome_count_in", False),
        transpose_semitones=payload.get("transpose_semitones", 0),
    )
    return PersistedSettings(
        resource_limits=limits,
        ai_config=ai_cfg,
        ai_python_executable=ai_python,
        midi_python_executable=midi_python,
        **practice,
    )


def save_settings(settings: PersistedSettings, path: Optional[Path | str] = None) -> Path:
    """Atomically write user settings JSON to disk."""
    target = Path(path) if path is not None else default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    practice = _clamp_practice_values(
        metronome_bpm=settings.metronome_bpm,
        metronome_beats_per_bar=settings.metronome_beats_per_bar,
        metronome_volume=settings.metronome_volume,
        metronome_count_in=settings.metronome_count_in,
        transpose_semitones=settings.transpose_semitones,
    )
    payload = {
        "schema_version": int(settings.schema_version),
        "resource_limits": asdict(settings.resource_limits),
        "ai_config": asdict(settings.ai_config),
        "ai_python_executable": str(settings.ai_python_executable or "").strip(),
        "midi_python_executable": str(settings.midi_python_executable or "").strip(),
        **practice,
    }
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target

