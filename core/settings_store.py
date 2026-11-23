"""Persistent settings loader/saver for ResourceLimits, AIConfig, AI worker path, and practice tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import logging
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Optional

from .config import AIConfig, ResourceLimits
from .appearance import Appearance
from .paths import _is_writable_dir, get_app_root

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
    auto_reset_on_track_change: bool = True
    schema_version: int = 2
    appearance: Appearance = Appearance()
    progression_mode: str = "chords"
    window_geometry: str = ""
    bottom_panel_collapsed: bool = False
    follow_default_device: bool = True
    close_behavior: str = "ask"


def default_settings_path() -> Path:
    app_root = get_app_root()
    if _is_writable_dir(app_root):
        return app_root / "settings.json"
    return Path.home() / ".listenscope" / "settings.json"


def _clamp_practice_values(
    *,
    metronome_bpm: Any = 120.0,
    metronome_beats_per_bar: Any = 4,
    metronome_volume: Any = 0.70,
    metronome_count_in: Any = False,
    transpose_semitones: Any = 0,
    auto_reset_on_track_change: Any = True,
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

    auto_reset = bool(auto_reset_on_track_change) if isinstance(auto_reset_on_track_change, bool) else True

    return {
        "metronome_bpm": bpm,
        "metronome_beats_per_bar": beats,
        "metronome_volume": vol,
        "metronome_count_in": count_in,
        "transpose_semitones": semi,
        "auto_reset_on_track_change": auto_reset,
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
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse settings file %s (%s); using safe defaults.", target, exc)
        if target.exists():
            backup = target.with_name(f"{target.stem}.corrupt-{int(time.time())}.json")
            try:
                target.replace(backup)
                logger.warning("Backed up corrupt settings file to %s", backup)
            except Exception as backup_exc:
                logger.warning("Failed to back up corrupt settings file %s: %s", target, backup_exc)
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
        auto_reset_on_track_change=payload.get("auto_reset_on_track_change", True),
    )
    raw_geom = payload.get("window_geometry", "")
    window_geometry = str(raw_geom).strip() if isinstance(raw_geom, str) else ""
    bottom_collapsed = bool(payload.get("bottom_panel_collapsed", False))
    raw_follow = payload.get("follow_default_device", True)
    follow_default_device = bool(raw_follow) if isinstance(raw_follow, bool) else True
    raw_cb = str(payload.get("close_behavior", "ask") or "ask").strip().lower()
    close_behavior = raw_cb if raw_cb in ("ask", "tray", "quit") else "ask"
    return PersistedSettings(
        resource_limits=limits,
        ai_config=ai_cfg,
        ai_python_executable=ai_python,
        midi_python_executable=midi_python,
        appearance=Appearance.from_mapping(payload.get("appearance")),
        progression_mode=_progression_mode(payload.get("progression_mode")),
        window_geometry=window_geometry,
        bottom_panel_collapsed=bottom_collapsed,
        follow_default_device=follow_default_device,
        close_behavior=close_behavior,
        **practice,
    )


def _progression_mode(value: object) -> str:
    return value if isinstance(value, str) and value in ("chords", "degrees", "both") else "chords"


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
        auto_reset_on_track_change=settings.auto_reset_on_track_change,
    )
    raw_cb = str(getattr(settings, "close_behavior", "ask") or "ask").strip().lower()
    close_behavior = raw_cb if raw_cb in ("ask", "tray", "quit") else "ask"
    payload = {
        "schema_version": int(settings.schema_version),
        "resource_limits": asdict(settings.resource_limits),
        "ai_config": asdict(settings.ai_config),
        "ai_python_executable": str(settings.ai_python_executable or "").strip(),
        "midi_python_executable": str(settings.midi_python_executable or "").strip(),
        "appearance": asdict(settings.appearance),
        "progression_mode": _progression_mode(settings.progression_mode),
        "window_geometry": str(getattr(settings, "window_geometry", "") or "").strip(),
        "bottom_panel_collapsed": bool(getattr(settings, "bottom_panel_collapsed", False)),
        "follow_default_device": bool(getattr(settings, "follow_default_device", True)),
        "close_behavior": close_behavior,
        **practice,
    }
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as f:
            tmp_path = Path(f.name)
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
    return target


load_persisted_settings = load_settings
save_persisted_settings = save_settings

