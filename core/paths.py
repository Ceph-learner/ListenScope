"""Shared path resolution & Windows subprocess helpers for source and PyInstaller frozen layouts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any


def get_bundle_root() -> Path:
    """Return the root directory containing source modules / bundled datas.

    Works identically in editable source trees (`Path(__file__).resolve().parent.parent`)
    and Windows PyInstaller 6 frozen builds (`sys._MEIPASS` / `_internal/`).
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def subprocess_no_window_kwargs() -> dict[str, Any]:
    """Suppress console window flicker when GUI-only Windows apps spawn helper Python processes."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
