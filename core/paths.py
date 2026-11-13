"""Shared path resolution & Windows subprocess helpers for source and PyInstaller frozen layouts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
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


def _is_writable_dir(directory: Path) -> bool:
    """Check directory writability safely without leaving probe files or directories behind."""
    if not directory.exists() or not directory.is_dir():
        return False
    try:
        with tempfile.TemporaryFile(dir=str(directory)):
            return True
    except Exception:
        return False


def default_work_dir() -> Path:
    """Return safe workspace_outputs path for source runs vs frozen read-only Windows installs."""
    if not getattr(sys, "frozen", False) and _is_writable_dir(Path.cwd()):
        return Path("workspace_outputs")
    return Path.home() / ".listenscope" / "workspace_outputs"


def default_export_dir() -> Path:
    """Return safe default export directory for file save dialogs."""
    if not getattr(sys, "frozen", False) and _is_writable_dir(Path.cwd()):
        return Path("exports")
    docs = Path.home() / "Documents"
    if _is_writable_dir(docs):
        return docs / "ListenScope" / "exports"
    return Path.home() / ".listenscope" / "exports"


def subprocess_no_window_kwargs() -> dict[str, Any]:
    """Suppress console window flicker when GUI-only Windows apps spawn helper Python processes."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
