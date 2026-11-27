"""In-app online update checker, downloader, and SHA256 verifier (GitHub Releases).

Security & privacy invariants (Issue #37 R2-6):
- Network requests are strictly restricted to api.github.com, github.com,
  objects.githubusercontent.com, and an optional user-configured mirror host.
- All requests are read-only GETs; no user data or telemetry is uploaded.
- Network calls run in background threads with a default 5-second timeout;
  offline / network failures are logged silently without interrupting the user.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Literal, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import urllib.request
import zipfile

from .paths import launch_detached
from .version import get_base_version

logger = logging.getLogger(__name__)

DEFAULT_REPO = "Ceph-learner/ListenScope"
DEFAULT_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT_SEC = 5.0
DEFAULT_CHECK_INTERVAL_SEC = 24.0 * 3600.0
MAX_RELEASE_NOTES_CHARS = 4000

INSTALLER_ASSET_NAME = "ListenScope-Setup-Windows-x64.exe"
PORTABLE_ASSET_NAME = "ListenScope-Core-Windows-x64-Portable.zip"
CHECKSUM_ASSET_NAME = "SHA256SUMS.txt"
APP_MUTEX_NAME = "ListenScopeSingleInstanceMutex"

PORTABLE_PRESERVED_PATHS: tuple[str, ...] = (
    "settings.json",
    "exports",
    "workspace_outputs",
    "runtime/ai",
    "m",
    ".venv-*",
    "tools/ffmpeg",
    "logs",
)

_PRESERVED_TOP_LEVEL_EXACT: frozenset[str] = frozenset(
    {"settings.json", "exports", "workspace_outputs", "m", "logs"}
)
_PRESERVED_NESTED_EXACT: tuple[tuple[str, ...], ...] = (
    ("runtime", "ai"),
    ("tools", "ffmpeg"),
)
_NON_UNWRAP_TOP_DIRS: frozenset[str] = frozenset(
    {"exports", "workspace_outputs", "runtime", "m", "tools", "logs", "_internal"}
)
_ERROR_ALREADY_EXISTS = 183
_APP_MUTEX_LOCK = threading.Lock()
_APP_MUTEX_HANDLE: Optional[int] = None

ALLOWED_GITHUB_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
    }
)

# SHA256SUMS.txt MUST only be fetched directly from GitHub, never via a mirror (U1).
ALLOWED_CHECKSUM_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
    }
)


class UpdateSecurityError(ValueError):
    """Raised when a URL points outside the allowed GitHub / mirror host allowlist."""


class UpdateChecksumFetchError(RuntimeError):
    """Raised when SHA256SUMS.txt cannot be fetched directly from GitHub."""


class UpdateChecksumError(RuntimeError):
    """Raised when a downloaded update fails SHA256SUMS.txt verification."""


class UpdateAssetNotFoundError(FileNotFoundError):
    """Raised when a release does not contain the exact expected Windows asset."""


class UpdateDownloadCancelled(RuntimeError):
    """Raised when an in-progress update download is cancelled by the user."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int = 0


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    version: str
    name: str
    body: str
    published_at: str
    html_url: str
    prerelease: bool
    assets: tuple[ReleaseAsset, ...] = ()


@dataclass(frozen=True)
class UpdateCheckResult:
    status: Literal["update_available", "up_to_date", "skipped", "throttled", "error"]
    current_version: str
    release: Optional[ReleaseInfo] = None
    message: str = ""


_SEMVER_RE = re.compile(
    r"^[vV]?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?"
    r"(?:[-.]?(?P<pre>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)

_PRE_RANK = {
    "dev": 0,
    "a": 1,
    "alpha": 1,
    "b": 2,
    "beta": 2,
    "rc": 3,
}


def _parse_prerelease_key(pre: str) -> tuple[tuple[int, int, str], ...]:
    tokens = re.split(r"[.\-_]+", pre.strip().lower())
    out: list[tuple[int, int, str]] = []
    for tok in tokens:
        if not tok:
            continue
        m = re.match(r"^([a-z]+)(\d+)$", tok)
        if m:
            label, num = m.group(1), int(m.group(2))
            out.append((0, _PRE_RANK.get(label, 50), label))
            out.append((1, num, ""))
        elif tok.isdigit():
            out.append((1, int(tok), ""))
        else:
            out.append((0, _PRE_RANK.get(tok, 50), tok))
    return tuple(out)


def parse_version(raw: str) -> tuple[tuple[int, int, int], int, tuple[tuple[int, int, str], ...]]:
    """Parse a semantic/PEP440-like version string into a comparable tuple.

    Ordering:
    - Build metadata (+sha) is ignored for precedence.
    - Any prerelease (e.g. 1.1.0-dev+abc, 1.1.0-alpha.1, 1.1.0-rc.1) sorts
      strictly before the corresponding final release (1.1.0).
    """
    cleaned = str(raw or "").strip()
    m = _SEMVER_RE.match(cleaned)
    if not m:
        raise ValueError(f"Invalid version string: {raw!r}")
    major = int(m.group("major"))
    minor = int(m.group("minor") or 0)
    patch = int(m.group("patch") or 0)
    pre = m.group("pre")
    if pre:
        return ((major, minor, patch), 0, _parse_prerelease_key(pre))
    return ((major, minor, patch), 1, ())


def normalize_version(raw: str) -> str:
    """Strip leading 'v'/'V' and whitespace from a version/tag string."""
    s = str(raw or "").strip()
    if s.startswith(("v", "V")) and len(s) > 1 and s[1].isdigit():
        return s[1:]
    return s


def is_newer_version(candidate: str, current: str) -> bool:
    """Return True if candidate version is strictly newer than current version."""
    try:
        return parse_version(candidate) > parse_version(current)
    except ValueError:
        return False


def should_auto_check(
    last_check_ts: float,
    *,
    now: Optional[float] = None,
    interval_sec: float = DEFAULT_CHECK_INTERVAL_SEC,
) -> bool:
    """Return True if at least interval_sec (default 24h) elapsed since last_check_ts."""
    cur_ts = time.time() if now is None else float(now)
    last_ts = float(last_check_ts or 0.0)
    if last_ts <= 0.0:
        return True
    return (cur_ts - last_ts) >= max(0.0, float(interval_sec))


def _extract_host(url: str) -> tuple[str, str]:
    parsed = urlparse(str(url or "").strip())
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    return scheme, host


def build_allowed_hosts(
    mirror_prefix: str = "",
    extra_allowed_hosts: frozenset[str] = frozenset(),
    *,
    base_allowed_hosts: frozenset[str] = ALLOWED_GITHUB_HOSTS,
) -> frozenset[str]:
    hosts = set(base_allowed_hosts)
    hosts.update(h.lower() for h in extra_allowed_hosts if h)
    if mirror_prefix.strip():
        scheme, host = _extract_host(mirror_prefix)
        if scheme in ("https", "http") and host:
            hosts.add(host)
    return frozenset(hosts)


def validate_update_url(
    url: str,
    *,
    mirror_prefix: str = "",
    extra_allowed_hosts: frozenset[str] = frozenset(),
    base_allowed_hosts: frozenset[str] = ALLOWED_GITHUB_HOSTS,
) -> str:
    """Validate that url uses https (or http for localhost/test) and an allowed host."""
    cleaned = str(url or "").strip()
    scheme, host = _extract_host(cleaned)
    allowed = build_allowed_hosts(
        mirror_prefix=mirror_prefix,
        extra_allowed_hosts=extra_allowed_hosts,
        base_allowed_hosts=base_allowed_hosts,
    )
    if not host or host not in allowed:
        raise UpdateSecurityError(f"Disallowed update URL host: {host!r} (url={cleaned!r})")
    if scheme == "https":
        return cleaned
    if scheme == "http" and host in ("127.0.0.1", "localhost", "::1"):
        return cleaned
    raise UpdateSecurityError(f"Update URL must use HTTPS (got {scheme!r} for {host!r})")


def apply_mirror_prefix(url: str, mirror_prefix: str) -> str:
    prefix = str(mirror_prefix or "").strip()
    if not prefix:
        return url
    return f"{prefix.rstrip('/')}/{url.lstrip('/')}"


def _build_opener(
    *,
    mirror_prefix: str = "",
    extra_allowed_hosts: frozenset[str] = frozenset(),
    base_allowed_hosts: frozenset[str] = ALLOWED_GITHUB_HOSTS,
) -> urllib.request.OpenerDirector:
    class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            validate_update_url(
                newurl,
                mirror_prefix=mirror_prefix,
                extra_allowed_hosts=extra_allowed_hosts,
                base_allowed_hosts=base_allowed_hosts,
            )
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_AllowlistRedirectHandler())


def _make_headers(current_version: str, *, accept: str = "*/*", extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    hdrs = {
        "User-Agent": f"ListenScope/{normalize_version(current_version) or get_base_version()}",
        "Accept": accept,
    }
    if extra:
        hdrs.update(extra)
    return hdrs


def _parse_release_payload(item: dict[str, Any]) -> Optional[ReleaseInfo]:
    if not isinstance(item, dict) or item.get("draft"):
        return None
    tag = str(item.get("tag_name", "") or "").strip()
    if not tag:
        return None
    ver = normalize_version(tag)
    assets_raw = item.get("assets") or []
    assets: list[ReleaseAsset] = []
    if isinstance(assets_raw, list):
        for a in assets_raw:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name", "") or "").strip()
            dl = str(a.get("browser_download_url", "") or "").strip()
            size = int(a.get("size", 0) or 0)
            if name and dl:
                assets.append(ReleaseAsset(name=name, download_url=dl, size=size))
    body = str(item.get("body", "") or "")
    if len(body) > MAX_RELEASE_NOTES_CHARS:
        body = body[:MAX_RELEASE_NOTES_CHARS].rstrip() + "\n\n..."
    return ReleaseInfo(
        tag_name=tag,
        version=ver,
        name=str(item.get("name", "") or tag).strip(),
        body=body,
        published_at=str(item.get("published_at", "") or "").strip(),
        html_url=str(item.get("html_url", "") or "").strip(),
        prerelease=bool(item.get("prerelease", False)),
        assets=tuple(assets),
    )


def detect_install_kind(app_root: Optional[Path] = None) -> Literal["installer", "portable"]:
    """Detect whether ListenScope is running from an Inno Setup install or a portable folder."""
    from .paths import get_app_root

    root = Path(app_root) if app_root is not None else get_app_root()
    if (root / "unins000.exe").exists() or (root / "unins000.dat").exists():
        return "installer"
    return "portable"


def select_release_asset(
    release: ReleaseInfo,
    install_kind: Literal["installer", "portable"] = "portable",
) -> Optional[ReleaseAsset]:
    """Strictly match the Windows release asset produced by release-windows.yml (no fallback guessing)."""
    expected_name = INSTALLER_ASSET_NAME if install_kind == "installer" else PORTABLE_ASSET_NAME
    for a in release.assets:
        if a.name == expected_name:
            return a
    return None


def find_checksum_asset(release: ReleaseInfo) -> Optional[ReleaseAsset]:
    for a in release.assets:
        if a.name == CHECKSUM_ASSET_NAME:
            return a
    return None


def check_for_updates(
    current_version: str,
    *,
    include_prerelease: bool = False,
    skipped_version: str = "",
    api_base_url: str = DEFAULT_API_BASE,
    repo: str = DEFAULT_REPO,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    mirror_prefix: str = "",
    extra_allowed_hosts: frozenset[str] = frozenset(),
) -> UpdateCheckResult:
    """Query GitHub Releases API for a newer version. Never raises on network/offline errors."""
    cur_norm = normalize_version(current_version)
    base = api_base_url.rstrip("/")
    url = (
        f"{base}/repos/{repo}/releases?per_page=10"
        if include_prerelease
        else f"{base}/repos/{repo}/releases/latest"
    )
    try:
        validate_update_url(url, mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
        opener = _build_opener(mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
        req = urllib.request.Request(
            url,
            headers=_make_headers(cur_norm, accept="application/vnd.github+json"),
            method="GET",
        )
        with opener.open(req, timeout=float(timeout_sec)) as resp:
            raw_bytes = resp.read()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except UpdateSecurityError as exc:
        logger.warning("Update check blocked by host allowlist: %s", exc)
        return UpdateCheckResult(status="error", current_version=cur_norm, message=str(exc))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.info("Update check skipped/failed (offline or network error): %s", exc)
        return UpdateCheckResult(status="error", current_version=cur_norm, message=str(exc))

    candidates: list[ReleaseInfo] = []
    if isinstance(payload, list):
        for item in payload:
            rel = _parse_release_payload(item)
            if rel is not None:
                candidates.append(rel)
    elif isinstance(payload, dict):
        rel = _parse_release_payload(payload)
        if rel is not None:
            candidates.append(rel)

    if not include_prerelease:
        candidates = [c for c in candidates if not c.prerelease]

    if not candidates:
        return UpdateCheckResult(status="up_to_date", current_version=cur_norm)

    best: Optional[ReleaseInfo] = None
    for cand in candidates:
        try:
            parse_version(cand.version)
        except ValueError:
            continue
        if best is None or is_newer_version(cand.version, best.version):
            best = cand

    if best is None or not is_newer_version(best.version, cur_norm):
        return UpdateCheckResult(status="up_to_date", current_version=cur_norm, release=best)

    skip_norm = normalize_version(skipped_version)
    if skip_norm and normalize_version(best.version) == skip_norm:
        return UpdateCheckResult(status="skipped", current_version=cur_norm, release=best)

    return UpdateCheckResult(status="update_available", current_version=cur_norm, release=best)


def check_for_updates_async(
    current_version: str,
    callback: Callable[[UpdateCheckResult], None],
    **kwargs: Any,
) -> threading.Thread:
    """Run check_for_updates() in a daemon background thread and invoke callback(result)."""
    def _worker() -> None:
        res = check_for_updates(current_version, **kwargs)
        try:
            callback(res)
        except Exception as exc:
            logger.warning("Update check callback failed: %s", exc)

    th = threading.Thread(target=_worker, name="ListenScope-UpdateCheck", daemon=True)
    th.start()
    return th


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse standard SHA256SUMS.txt lines into {filename: lowercase_hex_digest}."""
    out: dict[str, str] = {}
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", s)
        if not m:
            continue
        digest = m.group(1).lower()
        fname = Path(m.group(2).strip()).name
        if fname:
            out[fname] = digest
    return out


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def verify_file_sha256(path: Path, expected_hex: str) -> bool:
    exp = str(expected_hex or "").strip().lower()
    if len(exp) != 64:
        return False
    return compute_file_sha256(path) == exp


def _fetch_checksums_direct(
    url: str,
    *,
    current_version: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    extra_allowed_hosts: frozenset[str] = frozenset(),
) -> str:
    """Fetch SHA256SUMS.txt ONLY from github.com / objects.githubusercontent.com — never via mirror (U1)."""
    try:
        validate_update_url(
            url,
            mirror_prefix="",
            extra_allowed_hosts=extra_allowed_hosts,
            base_allowed_hosts=ALLOWED_CHECKSUM_HOSTS,
        )
        opener = _build_opener(
            mirror_prefix="",
            extra_allowed_hosts=extra_allowed_hosts,
            base_allowed_hosts=ALLOWED_CHECKSUM_HOSTS,
        )
        req = urllib.request.Request(
            url,
            headers=_make_headers(current_version),
            method="GET",
        )
        with opener.open(req, timeout=float(timeout_sec)) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (UpdateSecurityError, HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Failed fetching SHA256SUMS.txt directly from %s: %s", url, exc)
        raise UpdateChecksumFetchError(f"Failed to fetch {CHECKSUM_ASSET_NAME} directly from GitHub: {exc}") from exc


def _download_file_resumable(
    url: str,
    part_path: Path,
    *,
    current_version: str,
    mirror_prefix: str = "",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    extra_allowed_hosts: frozenset[str] = frozenset(),
) -> None:
    part_path.parent.mkdir(parents=True, exist_ok=True)
    urls = [url]
    if mirror_prefix.strip():
        urls.append(apply_mirror_prefix(url, mirror_prefix))

    opener = _build_opener(mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
    last_exc: Optional[BaseException] = None

    for candidate_url in urls:
        validate_update_url(candidate_url, mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
        if cancel_event is not None and cancel_event.is_set():
            raise UpdateDownloadCancelled("Download cancelled before request")

        existing = part_path.stat().st_size if part_path.exists() else 0
        extra_hdrs: dict[str, str] = {}
        if existing > 0:
            extra_hdrs["Range"] = f"bytes={existing}-"

        try:
            req = urllib.request.Request(
                candidate_url,
                headers=_make_headers(current_version, extra=extra_hdrs),
                method="GET",
            )
            with opener.open(req, timeout=float(timeout_sec)) as resp:
                status = getattr(resp, "status", 200)
                if status == 206 and existing > 0:
                    mode = "ab"
                    downloaded = existing
                    content_len = int(resp.headers.get("Content-Length") or 0)
                    total = existing + content_len if content_len > 0 else 0
                else:
                    mode = "wb"
                    downloaded = 0
                    total = int(resp.headers.get("Content-Length") or 0)

                if progress_cb is not None:
                    progress_cb(downloaded, total)

                with part_path.open(mode) as fh:
                    while True:
                        if cancel_event is not None and cancel_event.is_set():
                            raise UpdateDownloadCancelled("Download cancelled by user")
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb is not None:
                            progress_cb(downloaded, total)
            return
        except UpdateDownloadCancelled:
            raise
        except HTTPError as exc:
            if exc.code == 416 and existing > 0:
                # Server says range not satisfiable (file may already be complete); verify caller side
                return
            last_exc = exc
            logger.warning("Download from %s failed (HTTP %s); trying fallback if available.", candidate_url, exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            logger.warning("Download from %s failed (%s); trying fallback if available.", candidate_url, exc)

    if last_exc is not None:
        raise last_exc


def download_and_verify_update(
    release: ReleaseInfo,
    *,
    dest_dir: Path,
    install_kind: Literal["installer", "portable"] = "portable",
    current_version: Optional[str] = None,
    mirror_prefix: str = "",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    extra_allowed_hosts: frozenset[str] = frozenset(),
) -> Path:
    """Download the matching release asset into dest_dir with resume & SHA256SUMS.txt verification.

    If SHA256 verification fails, the downloaded file is deleted and UpdateChecksumError is raised.
    """
    ver = current_version or get_base_version()
    asset = select_release_asset(release, install_kind=install_kind)
    if asset is None:
        raise UpdateAssetNotFoundError(f"No matching {install_kind} release asset found in {release.tag_name}")

    sums_asset = find_checksum_asset(release)
    if sums_asset is None:
        raise UpdateChecksumFetchError(f"Release {release.tag_name} is missing {CHECKSUM_ASSET_NAME}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final_path = dest_dir / Path(asset.name).name
    part_path = dest_dir / f"{Path(asset.name).name}.part"

    sums_text = _fetch_checksums_direct(
        sums_asset.download_url,
        current_version=ver,
        timeout_sec=timeout_sec,
        extra_allowed_hosts=extra_allowed_hosts,
    )
    checksums = parse_sha256sums(sums_text)
    expected_sha = checksums.get(Path(asset.name).name)
    if not expected_sha:
        raise UpdateChecksumFetchError(f"{CHECKSUM_ASSET_NAME} does not contain an entry for {asset.name}")

    # If a previously verified/downloaded final file already exists and matches, reuse it
    if final_path.exists() and verify_file_sha256(final_path, expected_sha):
        if progress_cb is not None:
            sz = final_path.stat().st_size
            progress_cb(sz, sz)
        return final_path

    _download_file_resumable(
        asset.download_url,
        part_path,
        current_version=ver,
        mirror_prefix=mirror_prefix,
        timeout_sec=timeout_sec,
        progress_cb=progress_cb,
        cancel_event=cancel_event,
        extra_allowed_hosts=extra_allowed_hosts,
    )

    if not verify_file_sha256(part_path, expected_sha):
        actual = compute_file_sha256(part_path) if part_path.exists() else "<missing>"
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise UpdateChecksumError(
            f"SHA256 mismatch for {asset.name}: expected {expected_sha}, got {actual}"
        )

    part_path.replace(final_path)
    return final_path


# ---------------------------------------------------------------------------
# Issue #37 R2-4 & R2-5: Single-instance AppMutex, Installer & Portable Apply
# ---------------------------------------------------------------------------


def _get_win32_mutex_kernel32():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def acquire_app_mutex(name: str = APP_MUTEX_NAME) -> Optional[int]:
    """Acquire the Windows single-instance named mutex without aborting on ERROR_ALREADY_EXISTS."""
    global _APP_MUTEX_HANDLE
    if sys.platform != "win32":
        return None
    with _APP_MUTEX_LOCK:
        if _APP_MUTEX_HANDLE is not None:
            return _APP_MUTEX_HANDLE
        try:
            import ctypes

            kernel32 = _get_win32_mutex_kernel32()
            set_last_error = getattr(ctypes, "set_last_error", None)
            if callable(set_last_error):
                set_last_error(0)
            handle = kernel32.CreateMutexW(None, False, str(name))
            if not handle:
                get_last_error = getattr(ctypes, "get_last_error", None)
                last_err = get_last_error() if callable(get_last_error) else None
                logger.warning("CreateMutexW(%s) returned NULL (winerror=%s)", name, last_err)
                return None
            get_last_error = getattr(ctypes, "get_last_error", None)
            last_err = int(get_last_error() or 0) if callable(get_last_error) else 0
            if last_err == _ERROR_ALREADY_EXISTS:
                # Overlapping restart_application() launches the child before parent exits.
                logger.debug("App mutex %s already exists (winerror=%s); continuing.", name, last_err)
            _APP_MUTEX_HANDLE = int(handle)
            return _APP_MUTEX_HANDLE
        except Exception as exc:
            logger.warning("Failed to acquire app mutex %s: %s", name, exc)
            return None


def release_app_mutex() -> bool:
    """Release the process-wide Windows single-instance mutex if currently held."""
    global _APP_MUTEX_HANDLE
    with _APP_MUTEX_LOCK:
        handle = _APP_MUTEX_HANDLE
        if handle is None:
            return False
        _APP_MUTEX_HANDLE = None
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            kernel32 = _get_win32_mutex_kernel32()
            ok = bool(kernel32.CloseHandle(handle))
            if not ok:
                get_last_error = getattr(ctypes, "get_last_error", None)
                last_err = get_last_error() if callable(get_last_error) else None
                logger.warning("CloseHandle(app_mutex) failed (winerror=%s)", last_err)
            return ok
        except Exception as exc:
            logger.warning("Failed to release app mutex: %s", exc)
            return False


def launch_installer_update(
    installer_path: Path,
    *,
    launch_fn: Callable[..., Any] = launch_detached,
    release_mutex_fn: Callable[[], Any] = release_app_mutex,
) -> Any:
    """Release the single-instance mutex and launch the Inno Setup silent installer."""
    exe_path = Path(installer_path)
    if not exe_path.is_file():
        raise FileNotFoundError(f"Installer package not found: {exe_path}")
    release_mutex_fn()
    return launch_fn(
        [str(exe_path), "/SILENT", "/NORESTART"],
        cwd=str(exe_path.parent),
        allow_job_relax=True,
    )


def _normalized_rel_parts(rel_path: Path | str) -> tuple[str, ...]:
    raw = str(rel_path or "").replace("\\", "/")
    return tuple(p.lower() for p in PurePosixPath(raw).parts if p not in ("", ".", "/"))


def is_preserved_portable_path(rel_path: Path) -> bool:
    """Return True if rel_path is or resides inside one of the 8 preserved portable paths."""
    parts = _normalized_rel_parts(rel_path)
    if not parts:
        return False
    p0 = parts[0]
    if p0 in _PRESERVED_TOP_LEVEL_EXACT or fnmatch.fnmatchcase(p0, ".venv-*"):
        return True
    return len(parts) >= 2 and parts[:2] in _PRESERVED_NESTED_EXACT


def has_preserved_portable_descendant(rel_path: Path) -> bool:
    """Return True for parent dirs (runtime/, tools/) that must be descended rather than moved wholesale."""
    parts = _normalized_rel_parts(rel_path)
    if not parts:
        return False
    return any(len(pref) > len(parts) and pref[: len(parts)] == parts for pref in _PRESERVED_NESTED_EXACT)


def _validate_zip_entry_parts(raw_name: str, *, is_dir: bool) -> tuple[str, ...]:
    if not raw_name or "\x00" in raw_name:
        raise UpdateSecurityError(f"Invalid archive entry path: {raw_name!r}")
    norm = raw_name.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise UpdateSecurityError(f"Absolute path rejected in archive: {raw_name!r}")
    raw_segments = norm.split("/")
    if ".." in raw_segments:
        raise UpdateSecurityError(f"Path traversal rejected in archive: {raw_name!r}")
    parts = tuple(p for p in PurePosixPath(norm).parts if p not in ("", ".", "/"))
    if not parts:
        if is_dir and norm in (".", "./"):
            return ()
        raise UpdateSecurityError(f"Invalid empty archive entry path: {raw_name!r}")
    if ".." in parts:
        raise UpdateSecurityError(f"Path traversal rejected in archive: {raw_name!r}")
    return parts


def extract_portable_update(zip_path: Path, staging_dir: Path) -> Path:
    """Safely extract a portable update ZIP into staging_dir and unwrap single root directory if present."""
    src_zip = Path(zip_path)
    if not src_zip.is_file():
        raise FileNotFoundError(f"Portable archive not found: {src_zip}")

    dst_root = Path(staging_dir)
    dst_root.mkdir(parents=True, exist_ok=True)
    resolved_root = dst_root.resolve()

    extracted_files = 0
    with zipfile.ZipFile(src_zip, "r") as zf:
        infos = zf.infolist()
        if not infos:
            raise ValueError(f"Portable update archive is empty: {src_zip}")

        for info in infos:
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(unix_mode):
                raise UpdateSecurityError(f"Symlink entry rejected in archive: {info.filename!r}")
            is_dir = info.is_dir() or info.filename.endswith(("/", "\\"))
            parts = _validate_zip_entry_parts(info.filename, is_dir=is_dir)
            if not parts:
                continue

            target = (resolved_root / Path(*parts)).resolve()
            if target != resolved_root and not target.is_relative_to(resolved_root):
                raise UpdateSecurityError(f"Zip-slip target rejected: {info.filename!r}")

            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src_fh, target.open("wb") as dst_fh:
                    shutil.copyfileobj(src_fh, dst_fh)
                extracted_files += 1

    if extracted_files == 0:
        raise ValueError(f"Portable update archive contains no files: {src_zip}")

    top_entries = list(resolved_root.iterdir())
    if len(top_entries) == 1 and top_entries[0].is_dir():
        top_name_lower = top_entries[0].name.lower()
        if top_name_lower not in _NON_UNWRAP_TOP_DIRS and not fnmatch.fnmatchcase(top_name_lower, ".venv-*"):
            return top_entries[0]
    return resolved_root


def wait_for_pid_exit(
    pid: Optional[int],
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 0.1,
) -> bool:
    """Wait until pid exits (treating zombies as exited). Returns True if exited before timeout."""
    if pid is None or int(pid) <= 0:
        return True
    import psutil

    target_pid = int(pid)
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    interval = max(0.01, float(poll_interval_sec))
    while True:
        try:
            proc = psutil.Process(target_pid)
            status = proc.status()
            if status == psutil.STATUS_ZOMBIE or not proc.is_running():
                return True
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return True
        except psutil.AccessDenied:
            if not psutil.pid_exists(target_pid):
                return True

        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return False
        time.sleep(min(interval, remaining))


def _restore_backup_item(src: Path, dst: Path) -> None:
    if src.is_dir() and not src.is_symlink() and dst.exists() and dst.is_dir():
        for child in list(src.iterdir()):
            _restore_backup_item(child, dst / child.name)
        try:
            src.rmdir()
        except OSError:
            pass
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def apply_portable_update(
    app_dir: Path,
    staging_dir: Path,
    *,
    backup_dir: Optional[Path] = None,
    wait_pid: Optional[int] = None,
    wait_timeout_sec: float = 30.0,
    relaunch_cmd: Optional[list[str]] = None,
    launch_fn: Callable[..., Any] = launch_detached,
    copy_fn: Optional[Callable[[Path, Path], None]] = None,
) -> None:
    """Apply an extracted portable update atomically with backup and full rollback on error."""
    resolved_app = Path(app_dir).resolve()
    resolved_staging = Path(staging_dir).resolve()
    if not resolved_app.is_dir():
        raise FileNotFoundError(f"Application directory not found: {resolved_app}")
    if not resolved_staging.is_dir():
        raise FileNotFoundError(f"Staging directory not found: {resolved_staging}")

    if wait_pid is not None and int(wait_pid) > 0:
        if not wait_for_pid_exit(int(wait_pid), timeout_sec=wait_timeout_sec):
            raise TimeoutError(f"Timed out waiting for PID {wait_pid} to exit after {wait_timeout_sec}s")

    if backup_dir is None:
        resolved_backup = Path(tempfile.mkdtemp(prefix="listenscope-update-backup-")).resolve()
    else:
        resolved_backup = Path(backup_dir).resolve()
        resolved_backup.mkdir(parents=True, exist_ok=True)

    copy_impl = copy_fn if copy_fn is not None else shutil.copy2
    backed_up: list[Path] = []
    installed: list[Path] = []
    created_dirs: list[Path] = []

    def _backup_dir_contents(cur_dir: Path) -> None:
        for item in list(cur_dir.iterdir()):
            rel = item.relative_to(resolved_app)
            if is_preserved_portable_path(rel):
                continue
            if item.is_dir() and not item.is_symlink() and has_preserved_portable_descendant(rel):
                _backup_dir_contents(item)
                continue
            dst = resolved_backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dst))
            backed_up.append(rel)

    def _install_dir_contents(cur_src: Path) -> None:
        for src_item in list(cur_src.iterdir()):
            rel = src_item.relative_to(resolved_staging)
            if is_preserved_portable_path(rel):
                continue
            if src_item.is_symlink():
                raise UpdateSecurityError(f"Refusing symlink in portable update staging dir: {rel}")
            dst_item = resolved_app / rel
            if src_item.is_dir():
                if not dst_item.exists():
                    dst_item.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(rel)
                _install_dir_contents(src_item)
            else:
                dst_item.parent.mkdir(parents=True, exist_ok=True)
                installed.append(rel)
                copy_impl(src_item, dst_item)

    try:
        _backup_dir_contents(resolved_app)
        _install_dir_contents(resolved_staging)
    except BaseException:
        for rel in reversed(installed):
            if is_preserved_portable_path(rel) or has_preserved_portable_descendant(rel):
                continue
            target = resolved_app / rel
            try:
                if target.is_symlink() or target.is_file():
                    target.unlink(missing_ok=True)
                elif target.is_dir() and not any(target.iterdir()):
                    target.rmdir()
            except OSError:
                pass
        for rel_dir in reversed(created_dirs):
            if is_preserved_portable_path(rel_dir) or has_preserved_portable_descendant(rel_dir):
                continue
            dir_target = resolved_app / rel_dir
            try:
                if dir_target.is_dir() and not any(dir_target.iterdir()):
                    dir_target.rmdir()
            except OSError:
                pass
        for rel in reversed(backed_up):
            src = resolved_backup / rel
            dst = resolved_app / rel
            if src.exists() or src.is_symlink():
                _restore_backup_item(src, dst)
        raise

    shutil.rmtree(resolved_backup, ignore_errors=True)
    if relaunch_cmd:
        launch_fn(list(relaunch_cmd), cwd=str(resolved_app), allow_job_relax=True)


def _ps_single_quote(val: str) -> str:
    return "'" + str(val).replace("'", "''") + "'"


def build_portable_updater_ps1(
    app_dir: Path,
    staging_dir: Path,
    backup_dir: Path,
    wait_pid: int,
    relaunch_exe: Path,
    *,
    skip_relaunch: bool = False,
) -> str:
    """Generate a PowerShell 5.1 script performing wait -> backup -> replace -> rollback -> relaunch."""
    skip_lit = "$true" if skip_relaunch else "$false"
    pid_val = max(0, int(wait_pid or 0))
    return f"""$ErrorActionPreference = 'Stop'
$AppDir = {_ps_single_quote(str(app_dir))}
$StagingDir = {_ps_single_quote(str(staging_dir))}
$BackupDir = {_ps_single_quote(str(backup_dir))}
$WaitPid = {pid_val}
$RelaunchExe = {_ps_single_quote(str(relaunch_exe))}
$SkipRelaunch = {skip_lit}

function Get-NormalizedRelParts([string]$RelPath) {{
    $norm = $RelPath.Replace('\\', '/').Trim('/')
    if ([string]::IsNullOrWhiteSpace($norm)) {{
        return @()
    }}
    $parts = @($norm -split '/' | Where-Object {{ $_ -and $_ -ne '.' }} | ForEach-Object {{ $_.ToLowerInvariant() }})
    return $parts
}}

function Test-PreservedPortablePath([string]$RelPath) {{
    $parts = @(Get-NormalizedRelParts $RelPath)
    if ($parts.Count -eq 0) {{ return $false }}
    $p0 = $parts[0]
    if ($p0 -in @('settings.json', 'exports', 'workspace_outputs', 'm', 'logs')) {{ return $true }}
    if ($p0 -like '.venv-*') {{ return $true }}
    if ($parts.Count -ge 2) {{
        if (($parts[0] -eq 'runtime' -and $parts[1] -eq 'ai') -or ($parts[0] -eq 'tools' -and $parts[1] -eq 'ffmpeg')) {{
            return $true
        }}
    }}
    return $false
}}

function Test-PreservedDescendant([string]$RelPath) {{
    $parts = @(Get-NormalizedRelParts $RelPath)
    if ($parts.Count -eq 1) {{
        return ($parts[0] -eq 'runtime' -or $parts[0] -eq 'tools')
    }}
    return $false
}}

function Move-ItemSafe([string]$Src, [string]$Dst, [bool]$ThrowOnError = $true) {{
    $ea = if ($ThrowOnError) {{ 'Stop' }} else {{ 'SilentlyContinue' }}
    $srcRoot = [System.IO.Path]::GetPathRoot($Src)
    $dstRoot = [System.IO.Path]::GetPathRoot($Dst)
    if ($srcRoot -and $dstRoot -and ($srcRoot -ieq $dstRoot)) {{
        Move-Item -LiteralPath $Src -Destination $Dst -Force -ErrorAction $ea
    }} else {{
        Copy-Item -LiteralPath $Src -Destination $Dst -Recurse -Force -ErrorAction $ea
        Remove-Item -LiteralPath $Src -Recurse -Force -ErrorAction $ea
    }}
}}

function Restore-FromBackup([string]$Src, [string]$Dst) {{
    if ((Test-Path -LiteralPath $Src -PathType Container) -and (Test-Path -LiteralPath $Dst -PathType Container)) {{
        foreach ($child in @(Get-ChildItem -LiteralPath $Src -Force -ErrorAction SilentlyContinue)) {{
            Restore-FromBackup $child.FullName (Join-Path $Dst $child.Name)
        }}
        Remove-Item -LiteralPath $Src -Force -ErrorAction SilentlyContinue
    }} else {{
        $dstParent = Split-Path -Path $Dst -Parent
        if (-not (Test-Path -LiteralPath $dstParent)) {{
            [System.IO.Directory]::CreateDirectory($dstParent) | Out-Null
        }}
        Move-ItemSafe $Src $Dst $false
    }}
}}

$backedUp = New-Object 'System.Collections.Generic.List[string]'
$installed = New-Object 'System.Collections.Generic.List[string]'
$createdDirs = New-Object 'System.Collections.Generic.List[string]'

function Backup-NonPreserved([string]$CurDir, [string]$RelPrefix) {{
    foreach ($item in @(Get-ChildItem -LiteralPath $CurDir -Force -ErrorAction Stop)) {{
        $rel = if ($RelPrefix) {{ "$RelPrefix/$($item.Name)" }} else {{ $item.Name }}
        if (Test-PreservedPortablePath $rel) {{ continue }}
        if ($item.PSIsContainer -and (Test-PreservedDescendant $rel)) {{
            Backup-NonPreserved $item.FullName $rel
            continue
        }}
        $dst = Join-Path $BackupDir ($rel.Replace('/', '\\'))
        $dstParent = Split-Path -Path $dst -Parent
        if (-not (Test-Path -LiteralPath $dstParent)) {{
            [System.IO.Directory]::CreateDirectory($dstParent) | Out-Null
        }}
        Move-ItemSafe $item.FullName $dst $true
        $backedUp.Add($rel)
    }}
}}

function Install-NonPreserved([string]$CurDir, [string]$RelPrefix) {{
    foreach ($item in @(Get-ChildItem -LiteralPath $CurDir -Force -ErrorAction Stop)) {{
        $rel = if ($RelPrefix) {{ "$RelPrefix/$($item.Name)" }} else {{ $item.Name }}
        if (Test-PreservedPortablePath $rel) {{ continue }}
        $dst = Join-Path $AppDir ($rel.Replace('/', '\\'))
        if ($item.PSIsContainer) {{
            if (-not (Test-Path -LiteralPath $dst)) {{
                [System.IO.Directory]::CreateDirectory($dst) | Out-Null
                $createdDirs.Add($rel)
            }}
            Install-NonPreserved $item.FullName $rel
        }} else {{
            $dstParent = Split-Path -Path $dst -Parent
            if (-not (Test-Path -LiteralPath $dstParent)) {{
                [System.IO.Directory]::CreateDirectory($dstParent) | Out-Null
            }}
            $installed.Add($rel)
            Copy-Item -LiteralPath $item.FullName -Destination $dst -Force -ErrorAction Stop
        }}
    }}
}}

try {{
    if ($WaitPid -gt 0) {{
        $deadline = (Get-Date).AddSeconds(30)
        while ($true) {{
            $proc = $null
            try {{
                $proc = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
            }} catch {{
                $proc = $null
            }}
            if ($null -eq $proc) {{
                break
            }}
            try {{
                if ($proc.HasExited) {{
                    break
                }}
            }} catch {{
            }}
            if ((Get-Date) -ge $deadline) {{
                throw "Timed out waiting for PID $WaitPid to exit"
            }}
            Start-Sleep -Milliseconds 100
        }}
    }}

    if (-not (Test-Path -LiteralPath $AppDir -PathType Container)) {{
        throw "Application directory not found: $AppDir"
    }}
    if (-not (Test-Path -LiteralPath $StagingDir -PathType Container)) {{
        throw "Staging directory not found: $StagingDir"
    }}
    if (-not (Test-Path -LiteralPath $BackupDir)) {{
        [System.IO.Directory]::CreateDirectory($BackupDir) | Out-Null
    }}

    Backup-NonPreserved $AppDir ''
    Install-NonPreserved $StagingDir ''
}} catch {{
    $err = $_
    for ($i = $installed.Count - 1; $i -ge 0; $i--) {{
        $rel = $installed[$i]
        if (Test-PreservedPortablePath $rel) {{ continue }}
        $target = Join-Path $AppDir ($rel.Replace('/', '\\'))
        if (Test-Path -LiteralPath $target) {{
            Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
        }}
    }}
    for ($i = $createdDirs.Count - 1; $i -ge 0; $i--) {{
        $relDir = $createdDirs[$i]
        if ((Test-PreservedPortablePath $relDir) -or (Test-PreservedDescendant $relDir)) {{ continue }}
        $dirPath = Join-Path $AppDir ($relDir.Replace('/', '\\'))
        if ((Test-Path -LiteralPath $dirPath -PathType Container) -and (@(Get-ChildItem -LiteralPath $dirPath -Force -ErrorAction SilentlyContinue).Count -eq 0)) {{
            Remove-Item -LiteralPath $dirPath -Force -ErrorAction SilentlyContinue
        }}
    }}
    for ($i = $backedUp.Count - 1; $i -ge 0; $i--) {{
        $rel = $backedUp[$i]
        $src = Join-Path $BackupDir ($rel.Replace('/', '\\'))
        $dst = Join-Path $AppDir ($rel.Replace('/', '\\'))
        if (Test-Path -LiteralPath $src) {{
            Restore-FromBackup $src $dst
        }}
    }}
    [Console]::Error.WriteLine("ListenScope portable update failed and rolled back: $err")
    exit 1
}}

Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
if (-not $SkipRelaunch -and -not [string]::IsNullOrWhiteSpace($RelaunchExe) -and (Test-Path -LiteralPath $RelaunchExe)) {{
    Start-Process -FilePath $RelaunchExe -WorkingDirectory $AppDir
}}
"""


def launch_portable_update(
    zip_path: Path,
    app_dir: Path,
    *,
    pid: Optional[int] = None,
    relaunch_cmd: Optional[list[str]] = None,
    staging_parent: Optional[Path] = None,
    launch_fn: Callable[..., Any] = launch_detached,
) -> tuple[Path, Any]:
    """Extract portable ZIP into temp staging first, then spawn detached external applier."""
    src_zip = Path(zip_path)
    resolved_app = Path(app_dir).resolve()
    if staging_parent is not None:
        Path(staging_parent).mkdir(parents=True, exist_ok=True)
    temp_root = Path(
        tempfile.mkdtemp(
            prefix="listenscope-update-",
            dir=str(staging_parent) if staging_parent is not None else None,
        )
    ).resolve()
    staging_raw = temp_root / "staging"
    backup_dir = temp_root / "backup"

    try:
        staging_dir = extract_portable_update(src_zip, staging_raw)
        wait_pid = os.getpid() if pid is None else int(pid)

        if sys.platform == "win32" and getattr(sys, "frozen", False):
            skip_relaunch = relaunch_cmd is not None and len(relaunch_cmd) == 0
            if relaunch_cmd:
                relaunch_exe = Path(relaunch_cmd[0])
            else:
                relaunch_exe = resolved_app / "ListenScope.exe"
            ps1_path = temp_root / "listenscope_apply_update.ps1"
            ps1_text = build_portable_updater_ps1(
                resolved_app,
                staging_dir,
                backup_dir,
                wait_pid,
                relaunch_exe,
                skip_relaunch=skip_relaunch,
            )
            ps1_path.write_text(ps1_text, encoding="utf-8-sig")
            proc = launch_fn(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(ps1_path),
                ],
                cwd=str(temp_root),
                allow_job_relax=True,
            )
            return temp_root, proc

        eff_relaunch = (
            list(relaunch_cmd)
            if relaunch_cmd is not None
            else ([sys.executable, *sys.argv])
        )
        cmd = [
            sys.executable,
            "-m",
            "core.updater",
            "--apply-portable",
            "--app-dir",
            str(resolved_app),
            "--staging-dir",
            str(staging_dir),
            "--backup-dir",
            str(backup_dir),
            "--wait-pid",
            str(wait_pid),
        ]
        if eff_relaunch:
            cmd.extend(["--relaunch-cmd-json", json.dumps(eff_relaunch)])

        child_env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parent.parent)
        existing_pp = child_env.get("PYTHONPATH", "")
        pp_parts = [p for p in existing_pp.split(os.pathsep) if p]
        if repo_root not in pp_parts:
            child_env["PYTHONPATH"] = os.pathsep.join([repo_root, *pp_parts]) if pp_parts else repo_root

        proc = launch_fn(
            cmd,
            cwd=str(temp_root),
            env=child_env,
            allow_job_relax=True,
        )
        return temp_root, proc
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def _cli_main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ListenScope standalone update applier")
    parser.add_argument("--apply-portable", action="store_true", help="Apply an extracted portable update")
    parser.add_argument("--app-dir", type=str, default="", help="Target portable application directory")
    parser.add_argument("--staging-dir", type=str, default="", help="Extracted update staging directory")
    parser.add_argument("--backup-dir", type=str, default=None, help="Backup directory outside app_dir")
    parser.add_argument("--wait-pid", type=int, default=None, help="PID to wait for before replacing files")
    parser.add_argument("--relaunch-cmd-json", type=str, default=None, help="JSON argv list for relaunch")
    args = parser.parse_args(argv)

    if not args.apply_portable:
        parser.print_help()
        return 2
    if not args.app_dir or not args.staging_dir:
        parser.error("--app-dir and --staging-dir are required with --apply-portable")

    relaunch_cmd: Optional[list[str]] = None
    if args.relaunch_cmd_json:
        loaded = json.loads(args.relaunch_cmd_json)
        if not isinstance(loaded, list) or not all(isinstance(x, str) for x in loaded):
            raise ValueError("--relaunch-cmd-json must decode to a list of strings")
        relaunch_cmd = loaded

    apply_portable_update(
        Path(args.app_dir),
        Path(args.staging_dir),
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
        wait_pid=args.wait_pid,
        relaunch_cmd=relaunch_cmd,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
