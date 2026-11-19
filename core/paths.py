"""Shared path resolution & Windows subprocess helpers for source and PyInstaller frozen layouts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Lock
from typing import Any, Optional


_external_launch_lock = Lock()


def run_external_python(
    args: list[str], *, timeout: float, check: bool, **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    """Launch external Python without inheriting the frozen Windows DLL directory."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        kwargs.setdefault("capture_output", True)
        return subprocess.run(args, timeout=timeout, check=check, **kwargs)

    import ctypes

    kwargs.pop("capture_output", None)
    raw_env = kwargs.pop("env", None)
    env = (os.environ if raw_env is None else raw_env).copy()
    env.pop("PYTHONHOME", None)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_dll_directory = kernel32.SetDllDirectoryW
    set_dll_directory.argtypes = [ctypes.c_wchar_p]
    bundle = str(get_bundle_root())
    bundle_path = Path(bundle)
    for key in ("PATH", "PYTHONPATH"):
        entries = env.get(key, "").split(os.pathsep)
        kept: list[str] = []
        for entry in entries:
            if not entry:
                continue
            try:
                if Path(entry).resolve().is_relative_to(bundle_path):
                    continue
            except (OSError, ValueError):
                pass
            kept.append(entry)
        env[key] = os.pathsep.join(kept)
    # Bundled source modules must be below the external interpreter's stdlib and
    # site-packages. The bundle also contains Python 3.12 extensions such as _socket.
    if len(args) >= 2 and args[1] == "-m":
        launcher = (
            "import runpy, sys; root, mod = sys.argv[1:3]; sys.argv = sys.argv[2:]; "
            "sys.path.append(root); runpy.run_module(mod, run_name='__main__', alter_sys=True)"
        )
        command = [args[0], "-c", launcher, bundle, *args[2:]]
    elif len(args) >= 2 and args[1] == "-c":
        command = [args[0], "-c", *args[2:]]
    else:
        command = [args[0], *args[1:]]
    kwargs.update(env=env, cwd=str(Path(args[0]).resolve().parent))
    no_win = subprocess_no_window_kwargs()
    if "creationflags" in no_win:
        kwargs.setdefault("creationflags", no_win["creationflags"])
    with _external_launch_lock:
        if not set_dll_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        finally:
            set_dll_directory(bundle)

    with proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            exc.stdout, exc.stderr = proc.communicate()
            raise
        except BaseException:
            proc.kill()
            raise
        result = subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


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


def get_app_root() -> Path:
    """Return the application directory (executable dir when frozen, current working dir in source runs)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


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
    """Return sibling workspace_outputs when app directory is writable; otherwise fall back safely."""
    frozen = bool(getattr(sys, "frozen", False))
    app_dir = Path(sys.executable).resolve().parent if frozen else Path.cwd()
    if _is_writable_dir(app_dir):
        return (app_dir / "workspace_outputs") if frozen else Path("workspace_outputs")
    return Path.home() / ".listenscope" / "workspace_outputs"


def default_export_dir() -> Path:
    """Return sibling exports folder when app directory is writable; otherwise fall back safely."""
    frozen = bool(getattr(sys, "frozen", False))
    app_dir = Path(sys.executable).resolve().parent if frozen else Path.cwd()
    if _is_writable_dir(app_dir):
        return (app_dir / "exports") if frozen else Path("exports")
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
    if sys.platform == "win32" and os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
