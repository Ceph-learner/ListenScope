"""Shared path resolution & Windows subprocess helpers for source and PyInstaller frozen layouts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional


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


def find_ffmpeg_executable() -> Optional[str]:
    """Locate ffmpeg binary across PATH, current working dir, app dir, and bundle root."""
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).resolve())

    exe_names = ("ffmpeg.exe", "ffmpeg") if sys.platform == "win32" else ("ffmpeg", "ffmpeg.exe")
    search_bases: list[Path] = []
    for base in (
        Path.cwd(),
        Path(sys.executable).resolve().parent,
        get_bundle_root(),
    ):
        for rel in (
            base,
            base / "ffmpeg",
            base / "ffmpeg" / "bin",
            base / "tools" / "ffmpeg" / "bin",
            base.parent,
            base.parent / "tools" / "ffmpeg" / "bin",
        ):
            if rel not in search_bases:
                search_bases.append(rel)

    for directory in search_bases:
        for exe_name in exe_names:
            cand = directory / exe_name
            if cand.is_file():
                return str(cand.resolve())
    return None


def prepend_ffmpeg_path_env(env: dict[str, str]) -> dict[str, str]:
    """Ensure discovered local FFmpeg parent folder is visible on subprocess PATH."""
    ff = find_ffmpeg_executable()
    if ff:
        ff_dir = str(Path(ff).resolve().parent)
        existing = env.get("PATH", "")
        parts = existing.split(os.pathsep) if existing else []
        if ff_dir not in parts:
            env["PATH"] = f"{ff_dir}{os.pathsep}{existing}" if existing else ff_dir
    return env


def subprocess_no_window_kwargs() -> dict[str, Any]:
    """Suppress console window flicker when GUI-only Windows apps spawn helper Python processes."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
