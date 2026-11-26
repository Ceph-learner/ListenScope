"""In-app online update checker, downloader, and SHA256 verifier (GitHub Releases).

Security & privacy invariants (Issue #37 R2-6):
- Network requests are strictly restricted to api.github.com, github.com,
  objects.githubusercontent.com, and an optional user-configured mirror host.
- All requests are read-only GETs; no user data or telemetry is uploaded.
- Network calls run in background threads with a default 5-second timeout;
  offline / network failures are logged silently without interrupting the user.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Literal, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import urllib.request

from .version import get_base_version

logger = logging.getLogger(__name__)

DEFAULT_REPO = "Ceph-learner/ListenScope"
DEFAULT_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT_SEC = 5.0
DEFAULT_CHECK_INTERVAL_SEC = 24.0 * 3600.0
MAX_RELEASE_NOTES_CHARS = 4000

ALLOWED_GITHUB_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
    }
)


class UpdateSecurityError(ValueError):
    """Raised when a URL points outside the allowed GitHub / mirror host allowlist."""


class UpdateChecksumError(RuntimeError):
    """Raised when a downloaded update fails SHA256SUMS.txt verification."""


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
) -> frozenset[str]:
    hosts = set(ALLOWED_GITHUB_HOSTS)
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
) -> str:
    """Validate that url uses https (or http for localhost/test) and an allowed host."""
    cleaned = str(url or "").strip()
    scheme, host = _extract_host(cleaned)
    allowed = build_allowed_hosts(mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
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
) -> urllib.request.OpenerDirector:
    class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            validate_update_url(
                newurl,
                mirror_prefix=mirror_prefix,
                extra_allowed_hosts=extra_allowed_hosts,
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
    """Select the matching Windows release asset for installer or portable builds."""
    if install_kind == "installer":
        for a in release.assets:
            low = a.name.lower()
            if low.endswith(".exe") and ("setup" in low or "installer" in low):
                return a
        for a in release.assets:
            if a.name.lower().endswith(".exe"):
                return a
        return None

    for a in release.assets:
        low = a.name.lower()
        if low.endswith(".zip") and "portable" in low:
            return a
    for a in release.assets:
        if a.name.lower().endswith(".zip"):
            return a
    return None


def find_checksum_asset(release: ReleaseInfo) -> Optional[ReleaseAsset]:
    for a in release.assets:
        if a.name.lower() == "sha256sums.txt":
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


def _fetch_text_with_mirror(
    url: str,
    *,
    current_version: str,
    mirror_prefix: str = "",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    extra_allowed_hosts: frozenset[str] = frozenset(),
) -> str:
    urls = [url]
    if mirror_prefix.strip():
        urls.append(apply_mirror_prefix(url, mirror_prefix))

    last_exc: Optional[BaseException] = None
    opener = _build_opener(mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
    for candidate_url in urls:
        validate_update_url(candidate_url, mirror_prefix=mirror_prefix, extra_allowed_hosts=extra_allowed_hosts)
        try:
            req = urllib.request.Request(
                candidate_url,
                headers=_make_headers(current_version),
                method="GET",
            )
            with opener.open(req, timeout=float(timeout_sec)) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            logger.warning("Failed fetching %s (%s); trying fallback if available.", candidate_url, exc)
    assert last_exc is not None
    raise last_exc


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
        raise FileNotFoundError(f"No {install_kind} release asset found in {release.tag_name}")

    sums_asset = find_checksum_asset(release)
    if sums_asset is None:
        raise UpdateChecksumError(f"Release {release.tag_name} is missing SHA256SUMS.txt")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final_path = dest_dir / Path(asset.name).name
    part_path = dest_dir / f"{Path(asset.name).name}.part"

    sums_text = _fetch_text_with_mirror(
        sums_asset.download_url,
        current_version=ver,
        mirror_prefix=mirror_prefix,
        timeout_sec=timeout_sec,
        extra_allowed_hosts=extra_allowed_hosts,
    )
    checksums = parse_sha256sums(sums_text)
    expected_sha = checksums.get(Path(asset.name).name)
    if not expected_sha:
        raise UpdateChecksumError(f"SHA256SUMS.txt does not contain an entry for {asset.name}")

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
