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
_active_subprocs_lock = Lock()
_ACTIVE_SUBPROCS: set[subprocess.Popen[Any]] = set()
_win_job_handle: Optional[int] = None


def _ensure_windows_kill_job() -> Optional[int]:
    """Create a Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE so child processes never outlive parent."""
    global _win_job_handle
    if sys.platform != "win32":
        return None
    if _win_job_handle is not None:
        return _win_job_handle
    try:
        import ctypes
        from ctypes import wintypes

        class _IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            job,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return None
        _win_job_handle = int(job)
        return _win_job_handle
    except Exception:
        return None


def register_active_subprocess(proc: subprocess.Popen[Any]) -> subprocess.Popen[Any]:
    with _active_subprocs_lock:
        exited = [p for p in _ACTIVE_SUBPROCS if p.poll() is not None]
        for p in exited:
            _ACTIVE_SUBPROCS.discard(p)
        _ACTIVE_SUBPROCS.add(proc)
    if sys.platform == "win32":
        job = _ensure_windows_kill_job()
        handle = getattr(proc, "_handle", None)
        if job and handle:
            try:
                import ctypes

                ctypes.windll.kernel32.AssignProcessToJobObject(job, int(handle))
            except Exception:
                pass
    return proc


def unregister_active_subprocess(proc: subprocess.Popen[Any]) -> None:
    with _active_subprocs_lock:
        _ACTIVE_SUBPROCS.discard(proc)


def kill_all_active_subprocesses() -> None:
    """Immediately kill all tracked external subprocesses (watchdog last-resort cleanup)."""
    with _active_subprocs_lock:
        procs = list(_ACTIVE_SUBPROCS)
        _ACTIVE_SUBPROCS.clear()
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass


def terminate_all_active_subprocesses(timeout: float = 1.0) -> None:
    """Terminate and reap all tracked external subprocesses during shutdown."""
    with _active_subprocs_lock:
        procs = list(_ACTIVE_SUBPROCS)
        _ACTIVE_SUBPROCS.clear()
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.wait(timeout=max(0.05, float(timeout)))
        except Exception:
            try:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=0.1)
            except Exception:
                pass


def _strip_bundle_from_path_var(raw_val: str, bundle_paths: tuple[Path, ...]) -> str:
    kept: list[str] = []
    for entry in raw_val.split(os.pathsep):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
            if any(resolved.is_relative_to(bp) for bp in bundle_paths):
                continue
        except (OSError, ValueError):
            pass
        kept.append(entry)
    return os.pathsep.join(kept)


def _prepare_external_launch(
    args: list[str], env: Optional[dict[str, str]] = None
) -> tuple[list[str], dict[str, str], str]:
    """Prepare command, cleaned env, and interpreter-local cwd for external Python in frozen builds."""
    prepared_env = dict(os.environ if env is None else env)
    for var in (
        "PYTHONHOME",
        "_MEIPASS",
        "_MEIPASS2",
        "TCL_LIBRARY",
        "TK_LIBRARY",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
    ):
        prepared_env.pop(var, None)
    prepared_env.setdefault("PYTHONUTF8", "1")
    prepared_env.setdefault("PYTHONIOENCODING", "utf-8")
    prepared_env["PYTHONNOUSERSITE"] = "1"

    bundle = str(get_bundle_root())
    bundle_paths_list = [Path(bundle)]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            mp = Path(meipass).resolve()
            if mp not in bundle_paths_list:
                bundle_paths_list.append(mp)
        except OSError:
            pass
    bundle_paths = tuple(bundle_paths_list)

    for key in ("PATH", "PYTHONPATH"):
        if key in prepared_env:
            cleaned = _strip_bundle_from_path_var(prepared_env[key], bundle_paths)
            if cleaned:
                prepared_env[key] = cleaned
            elif key == "PYTHONPATH":
                prepared_env.pop(key, None)
            else:
                prepared_env[key] = ""

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

    cwd = str(Path(args[0]).resolve().parent)
    return command, prepared_env, cwd


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
    command, env, cwd = _prepare_external_launch(args, raw_env)
    bundle = str(get_bundle_root())

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_dll_directory = kernel32.SetDllDirectoryW
    set_dll_directory.argtypes = [ctypes.c_wchar_p]

    kwargs.update(env=env, cwd=cwd)
    no_win = subprocess_no_window_kwargs()
    if "creationflags" in no_win:
        kwargs.setdefault("creationflags", no_win["creationflags"])
    with _external_launch_lock:
        if not set_dll_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            proc = register_active_subprocess(
                subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
            )
        finally:
            set_dll_directory(bundle)

    try:
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
    finally:
        unregister_active_subprocess(proc)


def popen_external_python(cmd: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """Launch an external Python subprocess without inheriting PyInstaller/frozen env pollution."""
    frozen = bool(getattr(sys, "frozen", False))
    if sys.platform == "win32" and frozen:
        import ctypes

        raw_env = kwargs.pop("env", None)
        kwargs.pop("cwd", None)
        command, env, cwd = _prepare_external_launch(cmd, raw_env)
        bundle = str(get_bundle_root())

        caller_flags = int(kwargs.pop("creationflags", 0) or 0)
        no_win_flags = int(subprocess_no_window_kwargs().get("creationflags", 0) or 0)
        merged_flags = caller_flags | no_win_flags
        if merged_flags:
            kwargs["creationflags"] = merged_flags

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        set_dll_directory = kernel32.SetDllDirectoryW
        set_dll_directory.argtypes = [ctypes.c_wchar_p]
        with _external_launch_lock:
            if not set_dll_directory(None):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                return register_active_subprocess(subprocess.Popen(command, env=env, cwd=cwd, **kwargs))
            finally:
                set_dll_directory(bundle)

    raw_env = kwargs.pop("env", None)
    env = dict(raw_env if raw_env is not None else os.environ)
    for var in (
        "PYTHONHOME",
        "PYTHONPATH",
        "_MEIPASS",
        "_MEIPASS2",
        "TCL_LIBRARY",
        "TK_LIBRARY",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
    ):
        env.pop(var, None)

    if frozen:
        meipass = getattr(sys, "_MEIPASS", None)
        bundle_path = Path(meipass).resolve() if meipass else get_bundle_root()
        if "PATH" in env:
            env["PATH"] = _strip_bundle_from_path_var(env["PATH"], (bundle_path,))
        if sys.platform != "win32" and "LD_LIBRARY_PATH" in env:
            cleaned_ld = _strip_bundle_from_path_var(env["LD_LIBRARY_PATH"], (bundle_path,))
            if cleaned_ld:
                env["LD_LIBRARY_PATH"] = cleaned_ld
            else:
                env.pop("LD_LIBRARY_PATH", None)
    elif sys.platform != "win32" and "LD_LIBRARY_PATH" in env:
        parts = [p for p in env["LD_LIBRARY_PATH"].split(os.pathsep) if p and "_MEI" not in p]
        if parts:
            env["LD_LIBRARY_PATH"] = os.pathsep.join(parts)
        else:
            env.pop("LD_LIBRARY_PATH", None)

    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUTF8"] = "1"
    kwargs.setdefault("cwd", str(get_bundle_root()))

    caller_flags = int(kwargs.pop("creationflags", 0) or 0)
    no_win_flags = int(subprocess_no_window_kwargs().get("creationflags", 0) or 0)
    merged_flags = caller_flags | no_win_flags
    if merged_flags:
        kwargs["creationflags"] = merged_flags

    return register_active_subprocess(subprocess.Popen(cmd, env=env, **kwargs))


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
