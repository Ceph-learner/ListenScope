"""Tests for Issue #37 R2 in-app online updater (check, prompt, resumable download, SHA256, security).

All network tests use a local ThreadingHTTPServer on 127.0.0.1 — zero external network access.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any

import pytest
from PySide6 import QtWidgets

from core.i18n import set_current_language, translate_text, translate_widget_tree
from core.settings_store import load_settings, save_settings
from core.updater import (
    ReleaseAsset,
    ReleaseInfo,
    UpdateChecksumError,
    UpdateDownloadCancelled,
    UpdateSecurityError,
    check_for_updates,
    check_for_updates_async,
    compute_file_sha256,
    detect_install_kind,
    download_and_verify_update,
    is_newer_version,
    normalize_version,
    parse_sha256sums,
    parse_version,
    select_release_asset,
    should_auto_check,
    validate_update_url,
)
from ui.update_dialog import UpdateAvailableDialog

_LOCAL_HOST = frozenset({"127.0.0.1"})


def _ensure_qapp() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


class _LocalReleaseServer:
    """In-process HTTP server on 127.0.0.1 supporting GitHub Releases API, Range 206, slow chunks, and redirects."""

    def __init__(self) -> None:
        self.routes: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.chunk_delay_sec: float = 0.0
        self.chunk_size: int = 8192
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:
                headers_lower = {k.lower(): v for k, v in self.headers.items()}
                outer.requests.append((self.path, headers_lower))
                route = outer.routes.get(self.path)
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return

                if "redirect" in route:
                    self.send_response(302)
                    self.send_header("Location", route["redirect"])
                    self.end_headers()
                    return

                status = int(route.get("status", 200))
                body: bytes = route.get("body", b"")
                content_type = route.get("content_type", "application/octet-stream")
                if status != 200:
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if body:
                        self.wfile.write(body)
                    return

                range_hdr = headers_lower.get("range", "")
                start = 0
                if range_hdr.startswith("bytes=") and range_hdr.endswith("-"):
                    try:
                        start = int(range_hdr[len("bytes=") : -1])
                    except ValueError:
                        start = 0
                    if 0 < start < len(body):
                        slice_bytes = body[start:]
                        self.send_response(206)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                        self.send_header("Content-Length", str(len(slice_bytes)))
                        self.end_headers()
                        self._write_chunked(slice_bytes)
                        return

                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._write_chunked(body)

            def _write_chunked(self, data: bytes) -> None:
                step = max(1, int(outer.chunk_size))
                for off in range(0, len(data), step):
                    try:
                        self.wfile.write(data[off : off + step])
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    if outer.chunk_delay_sec > 0.0:
                        time.sleep(outer.chunk_delay_sec)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LocalReleaseServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# 1. Version comparison (including prereleases) & 24h throttle
# ---------------------------------------------------------------------------

def test_version_comparison_including_prereleases() -> None:
    assert normalize_version("v1.2.3") == "1.2.3"
    assert normalize_version("v1.0.0-dev+abc123") == "1.0.0-dev+abc123"

    # Stable vs stable
    assert is_newer_version("1.0.1", "1.0.0")
    assert is_newer_version("1.1.0", "1.0.9")
    assert is_newer_version("2.0.0", "1.9.9")
    assert not is_newer_version("1.0.0", "1.0.0")
    assert not is_newer_version("0.9.9", "1.0.0")

    # Prerelease ordering per SemVer 2.0.0
    assert is_newer_version("1.0.0", "1.0.0-rc.1")
    assert is_newer_version("1.0.0", "1.0.0-dev+deadbeef")
    assert is_newer_version("1.0.0-beta.1", "1.0.0-alpha.2")
    assert is_newer_version("1.0.0-alpha.10", "1.0.0-alpha.2")
    assert is_newer_version("1.0.0-rc.1", "1.0.0-beta.9")
    assert not is_newer_version("1.0.0-rc.1", "1.0.0")
    assert not is_newer_version("1.0.0-alpha.1", "1.0.0-alpha.1")

    with pytest.raises(ValueError):
        parse_version("not-a-version")


def test_should_auto_check_24h_throttle() -> None:
    now = 1_700_000_000.0
    assert should_auto_check(0.0, now=now)
    assert not should_auto_check(now - 3600.0, now=now)
    assert not should_auto_check(now - 86399.0, now=now)
    assert should_auto_check(now - 86401.0, now=now)


# ---------------------------------------------------------------------------
# 2. Host allowlist & redirect security (R2-6)
# ---------------------------------------------------------------------------

def test_host_allowlist_and_scheme_enforcement() -> None:
    validate_update_url("https://api.github.com/repos/Ceph-learner/ListenScope/releases/latest")
    validate_update_url("https://github.com/Ceph-learner/ListenScope/releases/download/v1.0.0/ListenScope.zip")
    validate_update_url("https://objects.githubusercontent.com/github-production-release-asset/foo")

    # Localhost rejected by default, allowed only when explicitly opted in for testing
    with pytest.raises(UpdateSecurityError):
        validate_update_url("http://127.0.0.1:8080/test")
    validate_update_url("http://127.0.0.1:8080/test", extra_allowed_hosts=_LOCAL_HOST)

    # User-configured mirror host is allowed
    validate_update_url(
        "https://mirror.example.com/https://github.com/Ceph-learner/ListenScope/releases/download/v1.0.0/a.zip",
        mirror_prefix="https://mirror.example.com/",
    )

    # Disallowed host rejected
    with pytest.raises(UpdateSecurityError):
        validate_update_url("https://evil.example.org/payload.exe")

    # Non-HTTPS rejected for remote hosts
    with pytest.raises(UpdateSecurityError):
        validate_update_url("http://api.github.com/repos/Ceph-learner/ListenScope/releases/latest")


def test_redirect_to_disallowed_host_is_blocked() -> None:
    with _LocalReleaseServer() as srv:
        srv.routes["/repos/Ceph-learner/ListenScope/releases/latest"] = {
            "redirect": "https://evil.example.org/fake.json"
        }
        res = check_for_updates(
            "0.1.0",
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert res.status == "error"
        assert "disallowed" in res.message.lower()
        assert "evil.example.org" in res.message.lower()


# ---------------------------------------------------------------------------
# 3. Check for updates: stable, prerelease, skip version, offline/error, async
# ---------------------------------------------------------------------------

def test_check_for_updates_stable_skip_prerelease_and_offline() -> None:
    with _LocalReleaseServer() as srv:
        latest_payload = {
            "tag_name": "v1.2.0",
            "name": "ListenScope v1.2.0",
            "body": "## Changes\n- Added online updater",
            "published_at": "2026-11-26T00:00:00Z",
            "html_url": "https://github.com/Ceph-learner/ListenScope/releases/tag/v1.2.0",
            "prerelease": False,
            "draft": False,
            "assets": [
                {
                    "name": "ListenScope-1.2.0-Setup.exe",
                    "browser_download_url": f"{srv.base_url}/files/ListenScope-1.2.0-Setup.exe",
                    "size": 1024,
                },
                {
                    "name": "ListenScope-1.2.0-Portable.zip",
                    "browser_download_url": f"{srv.base_url}/files/ListenScope-1.2.0-Portable.zip",
                    "size": 2048,
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": f"{srv.base_url}/files/SHA256SUMS.txt",
                    "size": 128,
                },
            ],
        }
        prerelease_payload = [
            {
                "tag_name": "v1.3.0-rc.1",
                "name": "ListenScope v1.3.0-rc.1",
                "body": "RC build",
                "published_at": "2026-11-27T00:00:00Z",
                "html_url": "https://github.com/Ceph-learner/ListenScope/releases/tag/v1.3.0-rc.1",
                "prerelease": True,
                "draft": False,
                "assets": [],
            },
            latest_payload,
        ]
        srv.routes["/repos/Ceph-learner/ListenScope/releases/latest"] = {
            "body": json.dumps(latest_payload).encode("utf-8"),
            "content_type": "application/json",
        }
        srv.routes["/repos/Ceph-learner/ListenScope/releases?per_page=10"] = {
            "body": json.dumps(prerelease_payload).encode("utf-8"),
            "content_type": "application/json",
        }

        # Stable update available
        res = check_for_updates(
            "1.0.0",
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert res.status == "update_available"
        assert res.release is not None
        assert res.release.version == "1.2.0"
        assert select_release_asset(res.release, install_kind="installer").name.endswith(".exe")  # type: ignore[union-attr]
        assert select_release_asset(res.release, install_kind="portable").name.endswith(".zip")  # type: ignore[union-attr]

        # Skip this version
        res_skip = check_for_updates(
            "1.0.0",
            skipped_version="v1.2.0",
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert res_skip.status == "skipped"

        # Already up to date
        res_same = check_for_updates(
            "1.2.0",
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert res_same.status == "up_to_date"

        # Prerelease opt-in picks v1.3.0-rc.1
        res_pre = check_for_updates(
            "1.2.0",
            include_prerelease=True,
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert res_pre.status == "update_available"
        assert res_pre.release is not None
        assert res_pre.release.version == "1.3.0-rc.1"
        assert res_pre.release.prerelease is True

        # Async check runs in background thread
        done = threading.Event()
        got: list[Any] = []
        th = check_for_updates_async(
            "1.0.0",
            lambda r: (got.append(r), done.set()),
            api_base_url=srv.base_url,
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert th.daemon is True
        assert done.wait(timeout=3.0)
        assert len(got) == 1 and got[0].status == "update_available"

    # Offline / closed port never raises, returns status="error"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()
    res_err = check_for_updates(
        "1.0.0",
        api_base_url=f"http://127.0.0.1:{closed_port}",
        timeout_sec=1.0,
        extra_allowed_hosts=_LOCAL_HOST,
    )
    assert res_err.status == "error"


# ---------------------------------------------------------------------------
# 4. Download, SHA256 mismatch deletion, Range resume, cancel, mirror fallback
# ---------------------------------------------------------------------------

def _make_release(
    base_url: str,
    *,
    asset_name: str = "ListenScope-1.2.0-Portable.zip",
    asset_path: str = "/dl/pkg.zip",
    sums_path: str = "/dl/SHA256SUMS.txt",
) -> ReleaseInfo:
    return ReleaseInfo(
        tag_name="v1.2.0",
        version="1.2.0",
        name="v1.2.0",
        body="Release notes",
        published_at="2026-11-26T00:00:00Z",
        html_url="https://github.com/Ceph-learner/ListenScope/releases/tag/v1.2.0",
        prerelease=False,
        assets=(
            ReleaseAsset(name=asset_name, download_url=f"{base_url}{asset_path}", size=0),
            ReleaseAsset(name="SHA256SUMS.txt", download_url=f"{base_url}{sums_path}", size=0),
        ),
    )


def test_download_sha256_mismatch_deletes_file(tmp_path: Path) -> None:
    payload = b"ListenScope portable payload bytes " * 1024
    wrong_sha = "0" * 64
    sums_text = f"{wrong_sha}  ListenScope-1.2.0-Portable.zip\n".encode("utf-8")

    with _LocalReleaseServer() as srv:
        srv.routes["/dl/pkg.zip"] = {"body": payload}
        srv.routes["/dl/SHA256SUMS.txt"] = {"body": sums_text, "content_type": "text/plain"}
        rel = _make_release(srv.base_url)

        with pytest.raises(UpdateChecksumError):
            download_and_verify_update(
                rel,
                dest_dir=tmp_path,
                install_kind="portable",
                timeout_sec=2.0,
                extra_allowed_hosts=_LOCAL_HOST,
            )

        assert not (tmp_path / "ListenScope-1.2.0-Portable.zip").exists()
        assert not (tmp_path / "ListenScope-1.2.0-Portable.zip.part").exists()


def test_download_resumes_from_partial_file_via_range(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 512  # 131072 bytes
    good_sha = hashlib.sha256(payload).hexdigest()
    sums_text = f"{good_sha}  ListenScope-1.2.0-Portable.zip\n".encode("utf-8")

    # Pre-seed first 40000 bytes as an interrupted .part file
    part_path = tmp_path / "ListenScope-1.2.0-Portable.zip.part"
    part_path.write_bytes(payload[:40000])

    with _LocalReleaseServer() as srv:
        srv.routes["/dl/pkg.zip"] = {"body": payload}
        srv.routes["/dl/SHA256SUMS.txt"] = {"body": sums_text, "content_type": "text/plain"}
        rel = _make_release(srv.base_url)

        progress_events: list[tuple[int, int]] = []
        final_path = download_and_verify_update(
            rel,
            dest_dir=tmp_path,
            install_kind="portable",
            timeout_sec=2.0,
            progress_cb=lambda c, t: progress_events.append((c, t)),
            extra_allowed_hosts=_LOCAL_HOST,
        )

        assert final_path == tmp_path / "ListenScope-1.2.0-Portable.zip"
        assert final_path.read_bytes() == payload
        assert not part_path.exists()
        assert compute_file_sha256(final_path) == good_sha
        assert progress_events and progress_events[-1] == (len(payload), len(payload))

        pkg_reqs = [hdrs for path, hdrs in srv.requests if path == "/dl/pkg.zip"]
        assert pkg_reqs and pkg_reqs[0].get("range") == "bytes=40000-"


def test_download_cancel_preserves_part_and_allows_resume(tmp_path: Path) -> None:
    payload = b"ABCD1234" * 32768  # 262144 bytes (4 x 64 KiB read chunks)
    good_sha = hashlib.sha256(payload).hexdigest()
    sums_text = f"{good_sha}  ListenScope-1.2.0-Portable.zip\n".encode("utf-8")

    with _LocalReleaseServer() as srv:
        srv.chunk_size = 16384
        srv.chunk_delay_sec = 0.005
        srv.routes["/dl/pkg.zip"] = {"body": payload}
        srv.routes["/dl/SHA256SUMS.txt"] = {"body": sums_text, "content_type": "text/plain"}
        rel = _make_release(srv.base_url)

        cancel_ev = threading.Event()

        def _on_progress(cur: int, _tot: int) -> None:
            if cur >= 4096:
                cancel_ev.set()

        with pytest.raises(UpdateDownloadCancelled):
            download_and_verify_update(
                rel,
                dest_dir=tmp_path,
                install_kind="portable",
                timeout_sec=3.0,
                progress_cb=_on_progress,
                cancel_event=cancel_ev,
                extra_allowed_hosts=_LOCAL_HOST,
            )

        part_path = tmp_path / "ListenScope-1.2.0-Portable.zip.part"
        assert part_path.exists()
        partial_size = part_path.stat().st_size
        assert 0 < partial_size < len(payload)

        # Resume without cancel -> completes cleanly
        srv.chunk_delay_sec = 0.0
        final_path = download_and_verify_update(
            rel,
            dest_dir=tmp_path,
            install_kind="portable",
            timeout_sec=3.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert final_path.read_bytes() == payload
        assert not part_path.exists()


def test_download_mirror_fallback(tmp_path: Path) -> None:
    payload = b"Mirror fallback works!" * 512
    good_sha = hashlib.sha256(payload).hexdigest()
    sums_text = f"{good_sha}  ListenScope-1.2.0-Portable.zip\n".encode("utf-8")

    with _LocalReleaseServer() as primary, _LocalReleaseServer() as mirror:
        primary.routes["/dl/pkg.zip"] = {"status": 502, "body": b"Bad Gateway"}
        primary.routes["/dl/SHA256SUMS.txt"] = {"status": 502, "body": b"Bad Gateway"}

        # Mirror prefix prepends mirror.base_url + "/" before primary URL
        mirror.routes[f"/{primary.base_url}/dl/pkg.zip"] = {"body": payload}
        mirror.routes[f"/{primary.base_url}/dl/SHA256SUMS.txt"] = {
            "body": sums_text,
            "content_type": "text/plain",
        }
        rel = _make_release(primary.base_url)

        final_path = download_and_verify_update(
            rel,
            dest_dir=tmp_path,
            install_kind="portable",
            mirror_prefix=f"{mirror.base_url}/",
            timeout_sec=2.0,
            extra_allowed_hosts=_LOCAL_HOST,
        )
        assert final_path.read_bytes() == payload


def test_parse_sha256sums_and_detect_install_kind(tmp_path: Path) -> None:
    parsed = parse_sha256sums(
        "ABCDEF0123456789abcdef0123456789abcdef0123456789abcdef0123456789  *ListenScope-1.0.0.zip\n"
    )
    assert parsed["ListenScope-1.0.0.zip"] == "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

    assert detect_install_kind(tmp_path) == "portable"
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert detect_install_kind(tmp_path) == "installer"


# ---------------------------------------------------------------------------
# 5. Settings persistence (schema_version remains 2)
# ---------------------------------------------------------------------------

def test_updater_settings_persist_with_schema_2(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    base = load_settings(settings_file)
    cfg = replace(
        base,
        auto_check_updates=False,
        include_prerelease_updates=True,
        update_mirror_prefix="https://mirror.example.com/",
        skipped_update_version="1.2.3",
        last_update_check_ts=1700000123.5,
    )
    save_settings(cfg, settings_file)

    raw = json.loads(settings_file.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2

    loaded = load_settings(settings_file)
    assert loaded.schema_version == 2
    assert loaded.auto_check_updates is False
    assert loaded.include_prerelease_updates is True
    assert loaded.update_mirror_prefix == "https://mirror.example.com/"
    assert loaded.skipped_update_version == "1.2.3"
    assert loaded.last_update_check_ts == pytest.approx(1700000123.5)


# ---------------------------------------------------------------------------
# 6. UpdateAvailableDialog UI & 4-language i18n check
# ---------------------------------------------------------------------------

def test_update_dialog_ui_and_i18n(tmp_path: Path) -> None:
    _ensure_qapp()
    rel = ReleaseInfo(
        tag_name="v2.0.0",
        version="2.0.0",
        name="ListenScope v2.0.0",
        body="### What's New\n- In-app updater\n",
        published_at="2026-11-26T12:00:00Z",
        html_url="https://github.com/Ceph-learner/ListenScope/releases/tag/v2.0.0",
        prerelease=False,
        assets=(),
    )

    cjk_re = re.compile(r"[\u4e00-\u9fff]")
    try:
        for lang in ("zh", "en", "ja", "ko"):
            set_current_language(lang)
            dlg = UpdateAvailableDialog(
                rel,
                current_version="1.0.0",
                dest_dir=tmp_path,
                install_kind="portable",
            )
            translate_widget_tree(dlg, lang)
            if lang in ("en", "ko"):
                assert not cjk_re.search(dlg.windowTitle()), f"{lang} title leaked CJK: {dlg.windowTitle()}"
                assert not cjk_re.search(dlg.header_lbl.text()), f"{lang} header leaked CJK: {dlg.header_lbl.text()}"
                assert not cjk_re.search(dlg.meta_lbl.text()), f"{lang} meta leaked CJK: {dlg.meta_lbl.text()}"
                assert not cjk_re.search(dlg.update_btn.text())
                assert not cjk_re.search(dlg.later_btn.text())
                assert not cjk_re.search(dlg.skip_btn.text())

            # Test dynamic progress / status translation
            prog = translate_text("正在下载更新包: 12.3 / 45.6 MB (27%)", lang)
            if lang in ("en", "ko"):
                assert not cjk_re.search(prog), f"{lang} progress leaked CJK: {prog}"
            dlg.close()

        set_current_language("zh")
        dlg = UpdateAvailableDialog(rel, current_version="1.0.0", dest_dir=tmp_path)
        dlg.skip_btn.click()
        assert dlg.user_action == "skip"
    finally:
        set_current_language("zh")
