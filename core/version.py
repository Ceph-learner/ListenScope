"""Application version formatting for source runs and frozen/release builds."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib


_FALLBACK_BASE_VERSION = "1.1.0-rc.1"


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_base_version() -> str:
    """Return base semantic version from pyproject.toml without modifying it."""
    env_base = os.environ.get("LISTENSCOPE_BASE_VERSION", "").strip()
    if env_base:
        return env_base
    try:
        from core import _build_info  # type: ignore[attr-defined]

        bv = str(getattr(_build_info, "BASE_VERSION", "") or "").strip()
        if bv:
            return bv
    except Exception:
        pass
    pyproject = _repo_root() / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            ver = str(data.get("project", {}).get("version", "") or "").strip()
            if ver:
                return ver
        except Exception:
            pass
    return _FALLBACK_BASE_VERSION


def _sanitize_short_sha(raw: str) -> str:
    cleaned = re.sub(r"[^0-9a-fA-F]", "", raw.strip()).lower()
    return cleaned[:12] if len(cleaned) >= 7 else ""


def _git_output(args: list[str], cwd: Path) -> str:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


@lru_cache(maxsize=1)
def get_app_version_display() -> str:
    """Return display version: '<base>' on exact tag builds, else '<base>-dev+<shortSHA>'."""
    env_full = os.environ.get("LISTENSCOPE_BUILD_VERSION", "").strip()
    if env_full:
        return env_full

    base = get_base_version()

    try:
        from core import _build_info  # type: ignore[attr-defined]

        bi_ver = str(getattr(_build_info, "BUILD_VERSION", "") or "").strip()
        if bi_ver:
            return bi_ver
        bi_sha = _sanitize_short_sha(str(getattr(_build_info, "GIT_SHA", "") or ""))
        if bi_sha:
            return f"{base}-dev+{bi_sha}"
    except Exception:
        pass

    env_sha = _sanitize_short_sha(os.environ.get("LISTENSCOPE_GIT_SHA", ""))
    if env_sha:
        return f"{base}-dev+{env_sha}"

    if not getattr(sys, "frozen", False):
        root = _repo_root()
        if (root / ".git").exists():
            exact_tag = _git_output(["describe", "--tags", "--exact-match"], root)
            if exact_tag in (base, f"v{base}"):
                return base
            short_sha = _sanitize_short_sha(_git_output(["rev-parse", "--short=7", "HEAD"], root))
            if short_sha:
                return f"{base}-dev+{short_sha}"

    return f"{base}-dev"
