"""Persistent settings loader/saver for ResourceLimits, AIConfig, and AI worker interpreter path."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import logging
from pathlib import Path
from typing import Any, Optional

from .config import AIConfig, ResourceLimits

logger = logging.getLogger(__name__)


@dataclass
class PersistedSettings:
    resource_limits: ResourceLimits
    ai_config: AIConfig
    ai_python_executable: str = ""
    schema_version: int = 1


def default_settings_path() -> Path:
    return Path.home() / ".listenscope" / "settings.json"


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
    return PersistedSettings(
        resource_limits=limits,
        ai_config=ai_cfg,
        ai_python_executable=ai_python,
    )


def save_settings(settings: PersistedSettings, path: Optional[Path | str] = None) -> Path:
    """Atomically write user settings JSON to disk."""
    target = Path(path) if path is not None else default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": int(settings.schema_version),
        "resource_limits": asdict(settings.resource_limits),
        "ai_config": asdict(settings.ai_config),
        "ai_python_executable": str(settings.ai_python_executable or "").strip(),
    }
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target
