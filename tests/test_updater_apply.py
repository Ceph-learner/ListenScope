"""Tests for Issue #37 R2-4 & R2-5 (AppMutex, Installer apply, Portable apply, Rollback, PS1, UI/Controller)."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import zipfile

import pytest
from PySide6 import QtWidgets

import core.updater as updater_mod
from core.i18n import set_current_language, translate_text, translate_widget_tree
from core.updater import (
    APP_MUTEX_NAME,
    PORTABLE_PRESERVED_PATHS,
    ReleaseAsset,
    ReleaseInfo,
    UpdateSecurityError,
    acquire_app_mutex,
    apply_portable_update,
    build_portable_updater_ps1,
    extract_portable_update,
    has_preserved_portable_descendant,
    is_preserved_portable_path,
    launch_installer_update,
    launch_portable_update,
    release_app_mutex,
    wait_for_pid_exit,
)
from ui.update_dialog import UpdateAvailableDialog

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_qapp() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def _seed_portable_app_dir(app_dir: Path) -> dict[Path, bytes]:
    """Create a realistic portable directory with all 8 preserved paths plus replaceable app files."""
    preserved: dict[Path, bytes] = {
        Path("settings.json"): b'{"schema_version": 2, "custom": true}\n',
        Path("exports/track.mid"): b"ORIGINAL_MIDI_BYTES",
        Path("workspace_outputs/job/out.wav"): b"ORIGINAL_WAV_BYTES",
        Path("runtime/ai/python.exe"): b"ORIGINAL_AI_PY",
        Path("m/python.exe"): b"ORIGINAL_MIDI_PY",
        Path(".venv-core/pyvenv.cfg"): b"home = C:\\Python312\n",
        Path(".venv-ai/pyvenv.cfg"): b"home = C:\\Python312-ai\n",
        Path("tools/ffmpeg/bin/ffmpeg.exe"): b"ORIGINAL_FFMPEG",
        Path("logs/app.log"): b"existing log line\n",
    }
    replaceable: dict[Path, bytes] = {
        Path("ListenScope.exe"): b"OLD_EXE_V1",
        Path("_internal/lib.dll"): b"OLD_DLL_V1",
        Path("runtime/old_helper.txt"): b"OLD_RUNTIME_HELPER",
        Path("tools/old_tool.txt"): b"OLD_TOOL",
    }
    for rel, content in {**preserved, **replaceable}.items():
        p = app_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return preserved


def _create_portable_zip(
    zip_path: Path,
    entries: dict[str, bytes],
    *,
    prefix: str = "",
) -> Path:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, data in entries.items():
            arcname = f"{prefix}{rel}" if prefix else rel
            zf.writestr(arcname, data)
    return zip_path


# ---------------------------------------------------------------------------
# 1. Preserved path classification
# ---------------------------------------------------------------------------


def test_preserved_path_rules_and_parent_descendants() -> None:
    assert len(PORTABLE_PRESERVED_PATHS) == 8

    for p in (
        "settings.json",
        "SETTINGS.JSON",
        "exports",
        "Exports/song.mid",
        "workspace_outputs/job1/stem.wav",
        "runtime/ai",
        "Runtime/AI/python.exe",
        "m",
        "M/Scripts/python.exe",
        ".venv-core",
        ".venv-core/pyvenv.cfg",
        ".VENV-AI/Scripts/python.exe",
        ".venv-midi/pyvenv.cfg",
        "tools/ffmpeg/bin/ffmpeg.exe",
        "TOOLS/FFMPEG/license.txt",
        "logs/listenscope.log",
    ):
        assert is_preserved_portable_path(Path(p)), f"Expected preserved: {p}"

    for p in (
        "ListenScope.exe",
        "_internal/lib.dll",
        "runtime",
        "runtime/old_helper.txt",
        "tools",
        "tools/old_tool.txt",
        "core/updater.py",
    ):
        assert not is_preserved_portable_path(Path(p)), f"Expected non-preserved: {p}"

    assert has_preserved_portable_descendant(Path("runtime"))
    assert has_preserved_portable_descendant(Path("RUNTIME"))
    assert has_preserved_portable_descendant(Path("tools"))
    assert has_preserved_portable_descendant(Path("Tools"))
    assert not has_preserved_portable_descendant(Path("runtime/ai"))
    assert not has_preserved_portable_descendant(Path("tools/ffmpeg"))
    assert not has_preserved_portable_descendant(Path("_internal"))
    assert not has_preserved_portable_descendant(Path("."))


# ---------------------------------------------------------------------------
# 2. Portable ZIP extraction & zip-slip / symlink / empty rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wrap_prefix", ["", "ListenScopeCore/"])
def test_portable_upgrade_preserves_all_8_paths_and_replaces_app(tmp_path: Path, wrap_prefix: str) -> None:
    app_dir = tmp_path / "app"
    preserved = _seed_portable_app_dir(app_dir)

    zip_entries: dict[str, bytes] = {
        "ListenScope.exe": b"NEW_EXE_V2",
        "_internal/lib.dll": b"NEW_DLL_V2",
        "_internal/new_mod.pyd": b"NEW_MOD_V2",
        "runtime/new_helper.txt": b"NEW_RUNTIME_HELPER",
        "tools/new_tool.txt": b"NEW_TOOL",
        # Conflicting payloads inside ALL preserved locations must be ignored
        "settings.json": b"CLOBBER_SETTINGS",
        "exports/track.mid": b"CLOBBER_MIDI",
        "exports/injected.mid": b"SHOULD_NOT_EXIST",
        "workspace_outputs/job/out.wav": b"CLOBBER_WAV",
        "runtime/ai/python.exe": b"CLOBBER_AI_PY",
        "m/python.exe": b"CLOBBER_MIDI_PY",
        ".venv-core/pyvenv.cfg": b"CLOBBER_VENV_CORE",
        ".venv-ai/pyvenv.cfg": b"CLOBBER_VENV_AI",
        "tools/ffmpeg/bin/ffmpeg.exe": b"CLOBBER_FFMPEG",
        "logs/app.log": b"CLOBBER_LOG",
    }
    zip_path = _create_portable_zip(tmp_path / "update.zip", zip_entries, prefix=wrap_prefix)
    staging = extract_portable_update(zip_path, tmp_path / "staging")
    if wrap_prefix:
        assert staging.name == "ListenScopeCore"

    backup_dir = tmp_path / "backup"
    launched: list[tuple[Any, dict[str, Any]]] = []

    def _fake_launch(cmd: Any, **kwargs: Any) -> str:
        launched.append((cmd, kwargs))
        return "proc-ok"

    apply_portable_update(
        app_dir,
        staging,
        backup_dir=backup_dir,
        wait_pid=None,
        relaunch_cmd=[str(app_dir / "ListenScope.exe")],
        launch_fn=_fake_launch,
    )

    assert (app_dir / "ListenScope.exe").read_bytes() == b"NEW_EXE_V2"
    assert (app_dir / "_internal/lib.dll").read_bytes() == b"NEW_DLL_V2"
    assert (app_dir / "_internal/new_mod.pyd").read_bytes() == b"NEW_MOD_V2"
    assert (app_dir / "runtime/new_helper.txt").read_bytes() == b"NEW_RUNTIME_HELPER"
    assert (app_dir / "tools/new_tool.txt").read_bytes() == b"NEW_TOOL"

    assert not (app_dir / "runtime/old_helper.txt").exists()
    assert not (app_dir / "tools/old_tool.txt").exists()
    assert not (app_dir / "exports/injected.mid").exists()
    assert not backup_dir.exists()

    for rel, orig_bytes in preserved.items():
        assert (app_dir / rel).read_bytes() == orig_bytes

    assert len(launched) == 1
    assert launched[0][0] == [str(app_dir / "ListenScope.exe")]
    assert launched[0][1]["cwd"] == str(app_dir.resolve())
    assert launched[0][1]["allow_job_relax"] is True


def test_portable_update_rolls_back_on_copy_failure(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    preserved = _seed_portable_app_dir(app_dir)

    staging = tmp_path / "staging"
    for rel, data in {
        "ListenScope.exe": b"NEW_EXE_V2",
        "_internal/lib.dll": b"NEW_DLL_V2",
        "_internal/added.dll": b"PARTIAL_OR_NEW",
        "runtime/new_helper.txt": b"NEW_RUNTIME_HELPER",
        "tools/new_tool.txt": b"NEW_TOOL",
    }.items():
        p = staging / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    launched: list[Any] = []
    copy_calls = 0

    def _failing_copy(src: Path, dst: Path) -> None:
        nonlocal copy_calls
        copy_calls += 1
        if copy_calls >= 3:
            # Write partial corrupted bytes before failing to verify partial file cleanup too.
            dst.write_bytes(b"CORRUPTED_PARTIAL")
            raise OSError("Simulated disk full during Phase 2")
        dst.write_bytes(src.read_bytes())

    with pytest.raises(OSError, match="Simulated disk full"):
        apply_portable_update(
            app_dir,
            staging,
            backup_dir=tmp_path / "backup",
            relaunch_cmd=[str(app_dir / "ListenScope.exe")],
            launch_fn=lambda *a, **kw: launched.append((a, kw)),
            copy_fn=_failing_copy,
        )

    assert not launched
    assert (app_dir / "ListenScope.exe").read_bytes() == b"OLD_EXE_V1"
    assert (app_dir / "_internal/lib.dll").read_bytes() == b"OLD_DLL_V1"
    assert (app_dir / "runtime/old_helper.txt").read_bytes() == b"OLD_RUNTIME_HELPER"
    assert (app_dir / "tools/old_tool.txt").read_bytes() == b"OLD_TOOL"

    assert not (app_dir / "_internal/added.dll").exists()
    assert not (app_dir / "runtime/new_helper.txt").exists()
    assert not (app_dir / "tools/new_tool.txt").exists()

    for rel, orig_bytes in preserved.items():
        assert (app_dir / rel).read_bytes() == orig_bytes


def test_extract_portable_update_rejects_zip_slip_symlink_and_empty(tmp_path: Path) -> None:
    bad_rel_zip = tmp_path / "slip_rel.zip"
    _create_portable_zip(bad_rel_zip, {"../escaped.txt": b"evil"})
    with pytest.raises(UpdateSecurityError):
        extract_portable_update(bad_rel_zip, tmp_path / "s1")
    assert not (tmp_path / "escaped.txt").exists()

    bad_bs_zip = tmp_path / "slip_backslash.zip"
    _create_portable_zip(bad_bs_zip, {"sub\\..\\..\\escaped2.txt": b"evil"})
    with pytest.raises(UpdateSecurityError):
        extract_portable_update(bad_bs_zip, tmp_path / "s2")
    assert not (tmp_path / "escaped2.txt").exists()

    bad_abs_zip = tmp_path / "slip_abs.zip"
    _create_portable_zip(bad_abs_zip, {"C:\\Windows\\evil.dll": b"evil"})
    with pytest.raises(UpdateSecurityError):
        extract_portable_update(bad_abs_zip, tmp_path / "s3")

    symlink_zip = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink_zip, "w") as zf:
        zi = zipfile.ZipInfo("link_file")
        zi.create_system = 3
        zi.external_attr = (0o120777 << 16)
        zf.writestr(zi, "/etc/passwd")
    with pytest.raises(UpdateSecurityError):
        extract_portable_update(symlink_zip, tmp_path / "s4")

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w"):
        pass
    with pytest.raises(ValueError):
        extract_portable_update(empty_zip, tmp_path / "s5")


def test_launch_portable_update_extracts_first_and_selects_launcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app_dir = tmp_path / "portable_app"
    _seed_portable_app_dir(app_dir)

    # Bad zip fails before launch_fn is ever called and leaves no staging temp dir
    bad_zip = _create_portable_zip(tmp_path / "bad.zip", {"../evil.exe": b"x"})
    staging_parent = tmp_path / "staging_root"
    called: list[Any] = []
    with pytest.raises(UpdateSecurityError):
        launch_portable_update(
            bad_zip,
            app_dir,
            staging_parent=staging_parent,
            launch_fn=lambda *a, **kw: called.append((a, kw)),
        )
    assert called == []
    assert list(staging_parent.iterdir()) == []

    # Source / non-frozen mode launches python -m core.updater --apply-portable
    good_zip = _create_portable_zip(tmp_path / "good.zip", {"ListenScope.exe": b"V2"})
    monkeypatch.setattr(updater_mod.sys, "frozen", False, raising=False)
    src_calls: list[tuple[Any, dict[str, Any]]] = []
    temp_root, proc = launch_portable_update(
        good_zip,
        app_dir,
        pid=12345,
        relaunch_cmd=[sys.executable, "main.py"],
        staging_parent=staging_parent,
        launch_fn=lambda cmd, **kw: (src_calls.append((cmd, kw)), "src-proc")[1],
    )
    assert proc == "src-proc"
    assert temp_root.parent == staging_parent.resolve()
    cmd, kw = src_calls[0]
    assert cmd[:4] == [sys.executable, "-m", "core.updater", "--apply-portable"]
    assert "--app-dir" in cmd and str(app_dir.resolve()) in cmd
    assert "--wait-pid" in cmd and "12345" in cmd
    assert kw["cwd"] == str(temp_root)
    assert kw["allow_job_relax"] is True

    # Frozen Windows mode writes listenscope_apply_update.ps1 and launches powershell.exe
    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(updater_mod.sys, "frozen", True, raising=False)
    win_calls: list[tuple[Any, dict[str, Any]]] = []
    win_root, win_proc = launch_portable_update(
        good_zip,
        app_dir,
        pid=4321,
        relaunch_cmd=[],
        staging_parent=staging_parent,
        launch_fn=lambda cmd, **kw: (win_calls.append((cmd, kw)), "win-proc")[1],
    )
    assert win_proc == "win-proc"
    ps1_file = win_root / "listenscope_apply_update.ps1"
    assert ps1_file.is_file()
    ps1_text = ps1_file.read_text(encoding="utf-8-sig")
    assert "$SkipRelaunch = $true" in ps1_text
    assert "$WaitPid = 4321" in ps1_text
    wcmd, wkw = win_calls[0]
    assert wcmd == [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(ps1_file),
    ]
    assert wkw == {"cwd": str(win_root), "allow_job_relax": True}


# ---------------------------------------------------------------------------
# 3. wait_for_pid_exit & CLI --apply-portable
# ---------------------------------------------------------------------------


def test_wait_for_pid_exit_handles_exited_running_and_zombie(monkeypatch: pytest.MonkeyPatch) -> None:
    assert wait_for_pid_exit(None) is True
    assert wait_for_pid_exit(0) is True

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    assert wait_for_pid_exit(proc.pid, timeout_sec=2.0) is True

    blocker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert wait_for_pid_exit(blocker.pid, timeout_sec=0.12, poll_interval_sec=0.03) is False
    finally:
        blocker.kill()
        blocker.wait(timeout=5)

    import psutil

    class _ZombieProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def status(self) -> str:
            return psutil.STATUS_ZOMBIE

        def is_running(self) -> bool:
            return True

    monkeypatch.setattr(psutil, "Process", _ZombieProc)
    assert wait_for_pid_exit(99999, timeout_sec=0.5) is True


def test_cli_apply_portable_end_to_end(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    preserved = _seed_portable_app_dir(app_dir)
    zip_path = _create_portable_zip(
        tmp_path / "pkg.zip",
        {
            "ListenScope.exe": b"CLI_NEW_EXE",
            "settings.json": b"NO_CLOBBER",
        },
        prefix="ListenScopeCore/",
    )
    staging = extract_portable_update(zip_path, tmp_path / "staging")
    marker = tmp_path / "relaunched.txt"
    relaunch_cmd = [
        sys.executable,
        "-c",
        f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ok', encoding='utf-8')",
    ]

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "core.updater",
            "--apply-portable",
            "--app-dir",
            str(app_dir),
            "--staging-dir",
            str(staging),
            "--backup-dir",
            str(tmp_path / "backup"),
            "--relaunch-cmd-json",
            json.dumps(relaunch_cmd),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, res.stderr
    assert (app_dir / "ListenScope.exe").read_bytes() == b"CLI_NEW_EXE"
    for rel, orig in preserved.items():
        assert (app_dir / rel).read_bytes() == orig
    # Wait briefly for relaunched child to write marker
    for _ in range(50):
        if marker.exists():
            break
        import time
        time.sleep(0.05)
    assert marker.read_text(encoding="utf-8") == "ok"


# ---------------------------------------------------------------------------
# 4. Installer launch, installer.iss contract, and AppMutex
# ---------------------------------------------------------------------------


def test_launch_installer_update_releases_mutex_first_and_passes_silent_flags(tmp_path: Path) -> None:
    missing = tmp_path / "missing-setup.exe"
    events: list[tuple[str, Any]] = []

    with pytest.raises(FileNotFoundError):
        launch_installer_update(
            missing,
            launch_fn=lambda *a, **kw: events.append(("launch", a)),
            release_mutex_fn=lambda: events.append(("release", None)),
        )
    assert events == []

    installer = tmp_path / "ListenScope-Setup-Windows-x64.exe"
    installer.write_bytes(b"MZ")

    def _release() -> bool:
        events.append(("release", None))
        return True

    def _launch(cmd: Any, **kwargs: Any) -> str:
        events.append(("launch", (cmd, kwargs)))
        return "setup-proc"

    ret = launch_installer_update(installer, launch_fn=_launch, release_mutex_fn=_release)
    assert ret == "setup-proc"
    assert events[0] == ("release", None)
    assert events[1] == (
        "launch",
        (
            [str(installer), "/SILENT", "/NORESTART"],
            {"cwd": str(tmp_path), "allow_job_relax": True},
        ),
    )


def test_installer_iss_contract() -> None:
    iss_path = REPO_ROOT / "scripts" / "installer.iss"
    text = iss_path.read_text(encoding="utf-8")
    assert "CloseApplications=yes" in text
    assert f"AppMutex={APP_MUTEX_NAME}" in text
    assert 'Name: "{app}\\exports"; Flags: uninsneveruninstall' in text


def test_app_mutex_acquire_already_exists_and_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater_mod, "_APP_MUTEX_HANDLE", None)
    monkeypatch.setattr(updater_mod.sys, "platform", "linux")
    assert acquire_app_mutex() is None
    assert release_app_mutex() is False

    state: dict[str, Any] = {
        "last_error": 0,
        "next_handle": 1001,
        "created": [],
        "closed": [],
        "close_ret": 1,
    }

    def _create_mutex(sec: Any, initial_owner: Any, name: str) -> int:
        state["created"].append((sec, bool(initial_owner), name))
        return state["next_handle"]

    def _close_handle(handle: int) -> int:
        state["closed"].append(handle)
        return state["close_ret"]

    fake_k32 = SimpleNamespace(CreateMutexW=_create_mutex, CloseHandle=_close_handle)

    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: fake_k32, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda v: state.__setitem__("last_error", v), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: state["last_error"], raising=False)

    # Normal acquisition
    h1 = acquire_app_mutex()
    assert h1 == 1001
    assert state["created"][-1] == (None, False, APP_MUTEX_NAME)
    assert hasattr(fake_k32.CreateMutexW, "argtypes")
    assert hasattr(fake_k32.CreateMutexW, "restype")
    assert hasattr(fake_k32.CloseHandle, "argtypes")
    assert hasattr(fake_k32.CloseHandle, "restype")

    # Release closes handle
    assert release_app_mutex() is True
    assert state["closed"] == [1001]
    assert release_app_mutex() is False

    # ERROR_ALREADY_EXISTS (183) must STILL return handle (restart overlap safety)
    state["next_handle"] = 2002
    monkeypatch.setattr(
        ctypes,
        "set_last_error",
        lambda _v: state.__setitem__("last_error", 183),
        raising=False,
    )
    h2 = acquire_app_mutex()
    assert h2 == 2002
    assert release_app_mutex() is True
    assert state["closed"] == [1001, 2002]

    # NULL handle returns None
    state["next_handle"] = 0
    assert acquire_app_mutex() is None


# ---------------------------------------------------------------------------
# 5. Controller apply_downloaded_update & UI / i18n
# ---------------------------------------------------------------------------


def test_controller_apply_downloaded_update_success_and_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import main as main_mod

    _ensure_qapp()
    saved_calls: list[Any] = []
    monkeypatch.setattr(main_mod, "save_settings", lambda cfg, path: saved_calls.append((cfg, path)))

    def _make_fake_ctrl():
        events: list[tuple[str, Any]] = []

        class _FakeWindow:
            def show_banner_message(self, text: str, *, tone: str = "info") -> None:
                events.append(("banner", (text, tone)))

            def force_quit(self) -> None:
                events.append(("force_quit", None))

        class _FakeCtrl:
            work_dir = tmp_path / "workspace_outputs"
            _settings_path = tmp_path / "settings.json"
            window = _FakeWindow()
            _shutdown_done = False

            def _build_persisted_settings(self) -> dict[str, Any]:
                return {"schema_version": 2}

            def shutdown(self) -> None:
                self._shutdown_done = True
                events.append(("shutdown", None))

        return _FakeCtrl(), events

    # 1) Installer success -> shutdown + force_quit
    ctrl1, ev1 = _make_fake_ctrl()
    inst_calls: list[Path] = []
    monkeypatch.setattr(updater_mod, "launch_installer_update", lambda p: inst_calls.append(p))
    pkg1 = tmp_path / "ListenScope-Setup-Windows-x64.exe"
    pkg1.write_bytes(b"MZ")
    assert main_mod.ListenScopeController.apply_downloaded_update(ctrl1, pkg1, install_kind="installer") is True
    assert inst_calls == [pkg1]
    assert ("shutdown", None) in ev1 and ("force_quit", None) in ev1

    # 2) Installer failure -> re-acquire mutex, show warning banner, do NOT shutdown/quit
    ctrl2, ev2 = _make_fake_ctrl()
    reacquired: list[str] = []
    monkeypatch.setattr(updater_mod, "launch_installer_update", lambda p: (_ for _ in ()).throw(OSError("denied")))
    monkeypatch.setattr(updater_mod, "acquire_app_mutex", lambda: reacquired.append("reacquired") or 1)
    assert main_mod.ListenScopeController.apply_downloaded_update(ctrl2, pkg1, install_kind="installer") is False
    assert reacquired == ["reacquired"]
    assert ("shutdown", None) not in ev2 and ("force_quit", None) not in ev2
    assert any(kind == "banner" and data[1] == "warn" for kind, data in ev2)

    # 3) Portable success -> shutdown + force_quit
    ctrl3, ev3 = _make_fake_ctrl()
    port_calls: list[tuple[Path, Path, Any]] = []
    monkeypatch.setattr(
        updater_mod,
        "launch_portable_update",
        lambda p, app_dir, **kw: (port_calls.append((p, app_dir, kw)), (tmp_path, None))[1],
    )
    pkg2 = tmp_path / "ListenScope-Core-Windows-x64-Portable.zip"
    pkg2.write_bytes(b"PK")
    assert main_mod.ListenScopeController.apply_downloaded_update(ctrl3, pkg2, install_kind="portable") is True
    assert len(port_calls) == 1 and port_calls[0][0] == pkg2
    assert ("shutdown", None) in ev3 and ("force_quit", None) in ev3


def test_controller_drain_update_results_wires_apply_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import queue
    import main as main_mod
    import ui.update_dialog as update_dlg_mod

    _ensure_qapp()
    pkg = tmp_path / "ListenScope-Setup-Windows-x64.exe"
    pkg.write_bytes(b"MZ")

    class _FakeDlg:
        def __init__(self, release, **kwargs: Any) -> None:
            self.release = release
            self.install_kind = "installer"
            self.downloaded_path = pkg
            self.user_action = "apply"

        def exec(self) -> int:
            return int(QtWidgets.QDialog.DialogCode.Accepted)

    monkeypatch.setattr(update_dlg_mod, "UpdateAvailableDialog", _FakeDlg)
    monkeypatch.setattr(main_mod, "save_settings", lambda *a, **kw: None)

    rel = ReleaseInfo(
        tag_name="v2.1.0",
        version="2.1.0",
        name="v2.1.0",
        body="notes",
        published_at="2026-11-27T00:00:00Z",
        html_url="https://github.com/Ceph-learner/ListenScope/releases/tag/v2.1.0",
        prerelease=False,
        assets=(),
    )
    res_obj = updater_mod.UpdateCheckResult(status="update_available", current_version="1.0.0", release=rel)
    q: queue.Queue[Any] = queue.Queue()
    q.put((True, res_obj))
    q.put((True, res_obj))

    applied: list[tuple[Path, str]] = []

    class _FakeWin:
        last_update_check_ts = 0.0
        update_mirror_prefix = ""
        skipped_update_version = ""

        def show_banner_message(self, *a: Any, **kw: Any) -> None:
            pass

    class _FakeCtrl:
        _update_result_q = q
        work_dir = tmp_path
        _settings_path = tmp_path / "settings.json"
        window = _FakeWin()
        _shutdown_done = False

        def _build_persisted_settings(self) -> dict[str, Any]:
            return {}

        def apply_downloaded_update(self, downloaded_path: Path, *, install_kind: str) -> bool:
            applied.append((downloaded_path, install_kind))
            self._shutdown_done = True
            return True

    main_mod.ListenScopeController._drain_update_results(_FakeCtrl())
    assert applied == [(pkg, "installer")]


def test_main_acquires_and_releases_app_mutex_in_finally(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import main as main_mod

    lifecycle: list[str] = []
    watchdog_exits: list[int] = []

    class _DummyIcon:
        def isNull(self) -> bool:
            return True

    class _DummyApp:
        def setWindowIcon(self, icon: Any) -> None:
            pass

        def exec(self) -> int:
            lifecycle.append("exec")
            return 0

        def processEvents(self) -> None:
            pass

    dummy_app = _DummyApp()

    class _DummyQApplication:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        @classmethod
        def instance(cls) -> _DummyApp:
            return dummy_app

    class _DummyWindow:
        def show(self) -> None:
            pass

        def force_quit(self) -> None:
            pass

    class _DummyController:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            lifecycle.append("init")
            self.window = _DummyWindow()

        def start_capture(self, *args: Any, **kwargs: Any) -> None:
            pass

        def shutdown(self) -> None:
            lifecycle.append("shutdown")

    monkeypatch.setattr(updater_mod, "acquire_app_mutex", lambda *a, **kw: (lifecycle.append("acquire"), 123)[1])
    monkeypatch.setattr(updater_mod, "release_app_mutex", lambda *a, **kw: (lifecycle.append("release"), True)[1])
    monkeypatch.setattr(main_mod.os, "_exit", lambda code=0: watchdog_exits.append(int(code)))
    monkeypatch.setattr(main_mod.gc, "collect", lambda *a, **kw: 0)
    monkeypatch.setattr(main_mod.QtCore.QTimer, "singleShot", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "_load_app_icon", lambda: _DummyIcon())
    monkeypatch.setattr(main_mod.QtWidgets, "QApplication", _DummyQApplication)
    monkeypatch.setattr(main_mod, "ListenScopeController", _DummyController)

    settings_file = tmp_path / "settings.json"
    rc = main_mod.main(["--settings", str(settings_file)])
    assert rc == 0
    assert lifecycle == ["acquire", "init", "exec", "shutdown", "release"]
    assert watchdog_exits == []

    lifecycle.clear()

    class _BoomController:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "ListenScopeController", _BoomController)
    with pytest.raises(RuntimeError, match="boom"):
        main_mod.main(["--settings", str(settings_file)])
    assert lifecycle == ["acquire", "release"]
    assert watchdog_exits == []


def test_portable_update_rolls_back_on_phase1_backup_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app_dir = tmp_path / "app"
    preserved = _seed_portable_app_dir(app_dir)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "ListenScope.exe").write_bytes(b"NEW")

    real_move = updater_mod.shutil.move
    move_count = 0

    def _flaky_move(src: str, dst: str) -> Any:
        nonlocal move_count
        move_count += 1
        if move_count == 2 and str(tmp_path / "backup") in dst:
            raise PermissionError("Simulated locked file in Phase 1")
        return real_move(src, dst)

    monkeypatch.setattr(updater_mod.shutil, "move", _flaky_move)

    with pytest.raises(PermissionError, match="Simulated locked file"):
        apply_portable_update(app_dir, staging, backup_dir=tmp_path / "backup")

    assert (app_dir / "ListenScope.exe").read_bytes() == b"OLD_EXE_V1"
    assert (app_dir / "_internal/lib.dll").read_bytes() == b"OLD_DLL_V1"
    assert (app_dir / "runtime/old_helper.txt").read_bytes() == b"OLD_RUNTIME_HELPER"
    assert (app_dir / "tools/old_tool.txt").read_bytes() == b"OLD_TOOL"
    for rel, orig in preserved.items():
        assert (app_dir / rel).read_bytes() == orig


def test_update_dialog_apply_button_and_4lang_i18n(tmp_path: Path) -> None:
    _ensure_qapp()
    rel = ReleaseInfo(
        tag_name="v2.1.0",
        version="2.1.0",
        name="ListenScope v2.1.0",
        body="### Changes\n- Self update apply",
        published_at="2026-11-27T00:00:00Z",
        html_url="https://github.com/Ceph-learner/ListenScope/releases/tag/v2.1.0",
        prerelease=False,
        assets=(ReleaseAsset(name="ListenScope-Core-Windows-x64-Portable.zip", download_url="https://github.com/x"),),
    )
    cjk_re = re.compile(r"[\u4e00-\u9fff]")

    try:
        for install_kind in ("installer", "portable"):
            for lang in ("zh", "en", "ja", "ko"):
                set_current_language(lang)
                dlg = UpdateAvailableDialog(
                    rel,
                    current_version="1.0.0",
                    dest_dir=tmp_path,
                    install_kind=install_kind,
                )
                assert not dlg.apply_btn.isVisible()
                pkg = tmp_path / f"pkg-{install_kind}.bin"
                pkg.write_bytes(b"ok")
                dlg._on_download_finished(str(pkg))
                assert dlg.user_action == "downloaded"
                assert dlg.apply_btn.isVisibleTo(dlg)
                assert not dlg.update_btn.isVisibleTo(dlg)
                assert not dlg.skip_btn.isVisibleTo(dlg)
                translate_widget_tree(dlg, lang)
                if lang in ("en", "ko"):
                    assert not cjk_re.search(dlg.apply_btn.text()), f"{lang} apply_btn leaked CJK: {dlg.apply_btn.text()}"
                elif lang == "ja":
                    assert any(ord(ch) > 0x3040 for ch in dlg.apply_btn.text())
                if lang == "zh" and install_kind == "installer":
                    assert dlg.apply_btn.text() == "立即安装更新并退出"
                if lang == "zh" and install_kind == "portable":
                    assert dlg.apply_btn.text() == "立即应用更新并重启"
                dlg.apply_btn.click()
                assert dlg.user_action == "apply"
                dlg.close()

        for lang in ("en", "ja", "ko"):
            msg = translate_text("应用更新失败，请手动安装或重启后重试: permission denied", lang)
            assert "permission denied" in msg
            if lang in ("en", "ko"):
                assert not cjk_re.search(msg)
    finally:
        set_current_language("zh")


# ---------------------------------------------------------------------------
# 6. PowerShell 5.1 script structure + Windows-only real powershell.exe tests
# ---------------------------------------------------------------------------


def test_build_portable_updater_ps1_structure(tmp_path: Path) -> None:
    ps1 = build_portable_updater_ps1(
        tmp_path / "ListenScope [v1]",
        tmp_path / "O'BrienStaging",
        tmp_path / "backup",
        9876,
        tmp_path / "ListenScope [v1]" / "ListenScope.exe",
        skip_relaunch=True,
    )
    assert "O''BrienStaging'" in ps1
    assert f"'{tmp_path / 'ListenScope [v1]'}'" in ps1
    assert "-LiteralPath" in ps1
    for kept in ("settings.json", "exports", "workspace_outputs", "m", "logs", ".venv-*", "runtime", "tools"):
        assert kept in ps1
    assert "function Move-ItemSafe" in ps1
    assert "GetPathRoot" in ps1
    assert "Remove-Item -LiteralPath $StagingDir" in ps1
    assert "$SkipRelaunch = $true" in ps1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell updater test")
def test_windows_powershell_portable_updater_success_and_rollback(tmp_path: Path) -> None:
    # 1) Real powershell.exe success run preserving all 8 paths
    app_ok = tmp_path / "app_ok"
    preserved_ok = _seed_portable_app_dir(app_ok)
    staging_ok = tmp_path / "staging_ok"
    for rel, data in {
        "ListenScope.exe": b"PS_NEW_EXE",
        "_internal/lib.dll": b"PS_NEW_DLL",
        "runtime/new_helper.txt": b"PS_NEW_RUNTIME",
        "tools/new_tool.txt": b"PS_NEW_TOOL",
        "settings.json": b"CLOBBER",
        "exports/track.mid": b"CLOBBER",
        "workspace_outputs/job/out.wav": b"CLOBBER",
        "runtime/ai/python.exe": b"CLOBBER",
        "m/python.exe": b"CLOBBER",
        ".venv-core/pyvenv.cfg": b"CLOBBER",
        ".venv-ai/pyvenv.cfg": b"CLOBBER",
        "tools/ffmpeg/bin/ffmpeg.exe": b"CLOBBER",
        "logs/app.log": b"CLOBBER",
    }.items():
        p = staging_ok / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    ps1_ok = tmp_path / "apply_ok.ps1"
    ps1_ok.write_text(
        build_portable_updater_ps1(
            app_ok,
            staging_ok,
            tmp_path / "backup_ok",
            0,
            app_ok / "ListenScope.exe",
            skip_relaunch=True,
        ),
        encoding="utf-8-sig",
    )
    res_ok = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_ok)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res_ok.returncode == 0, res_ok.stderr
    assert (app_ok / "ListenScope.exe").read_bytes() == b"PS_NEW_EXE"
    assert (app_ok / "_internal/lib.dll").read_bytes() == b"PS_NEW_DLL"
    assert not (app_ok / "runtime/old_helper.txt").exists()
    assert not (app_ok / "tools/old_tool.txt").exists()
    for rel, orig in preserved_ok.items():
        assert (app_ok / rel).read_bytes() == orig

    # 2) Real powershell.exe failure rollback when staging file is exclusively locked
    app_fail = tmp_path / "app_fail"
    preserved_fail = _seed_portable_app_dir(app_fail)
    staging_fail = tmp_path / "staging_fail"
    for rel, data in {
        "ListenScope.exe": b"NEW_EXE",
        "_internal/lib.dll": b"NEW_DLL",
        "_internal/zz_locked.dll": b"LOCKED_BYTES",
    }.items():
        p = staging_fail / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    ps1_fail = tmp_path / "apply_fail.ps1"
    ps1_fail.write_text(
        build_portable_updater_ps1(
            app_fail,
            staging_fail,
            tmp_path / "backup_fail",
            0,
            app_fail / "ListenScope.exe",
            skip_relaunch=True,
        ),
        encoding="utf-8-sig",
    )

    import msvcrt

    locked_path = staging_fail / "_internal/zz_locked.dll"
    with locked_path.open("r+b") as lock_fh:
        msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, len(b"LOCKED_BYTES"))
        try:
            res_fail = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_fail)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            lock_fh.seek(0)
            msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, len(b"LOCKED_BYTES"))

    assert res_fail.returncode != 0
    assert (app_fail / "ListenScope.exe").read_bytes() == b"OLD_EXE_V1"
    assert (app_fail / "_internal/lib.dll").read_bytes() == b"OLD_DLL_V1"
    assert not (app_fail / "_internal/zz_locked.dll").exists()
    for rel, orig in preserved_fail.items():
        assert (app_fail / rel).read_bytes() == orig
