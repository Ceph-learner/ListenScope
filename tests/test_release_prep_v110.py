"""Release v1.1.0 preparation verification tests (R4-1, R4-2, T5)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import tomllib

from PySide6 import QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_qapp() -> QtWidgets.QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def _extract_run_blocks(workflow_text: str) -> list[str]:
    """Extract all `run:` script block bodies from a GitHub Actions workflow YAML."""
    lines = workflow_text.splitlines()
    blocks: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        m = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if not m:
            idx += 1
            continue
        base_indent = len(m.group(1))
        rest = m.group(2).strip()
        if rest and rest not in ("|", "|-", "|+", ">", ">-", ">+"):
            blocks.append(rest)
            idx += 1
            continue
        idx += 1
        body_lines: list[str] = []
        while idx < len(lines):
            nxt = lines[idx]
            if not nxt.strip():
                body_lines.append("")
                idx += 1
                continue
            indent = len(nxt) - len(nxt.lstrip(" "))
            if indent <= base_indent:
                break
            body_lines.append(nxt)
            idx += 1
        blocks.append("\n".join(body_lines))
    return blocks


def test_r4_1_version_unified_to_1_1_0_rc1() -> None:
    """All version sources, HUD footer, issue template, and READMEs are aligned to 1.1.0-rc.2."""
    pyproj = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    assert pyproj["project"]["version"] == "1.1.0-rc.2"

    iss_txt = (REPO_ROOT / "scripts" / "installer.iss").read_text("utf-8")
    assert '#define MyAppVersion "1.1.0-rc.2"' in iss_txt
    assert '#define MyAppNumericVersion "1.1.0.2"' in iss_txt
    assert "VersionInfoVersion={#MyAppNumericVersion}" in iss_txt
    assert "AppId={{D92B6E14-9F1A-4D7E-A78A-3F6F49B8C201}" in iss_txt
    assert not re.search(r"(?<!\d\.)1\.0\.1\b", iss_txt)

    from core import version as ver_mod

    assert ver_mod._FALLBACK_BASE_VERSION == "1.1.0-rc.2"
    ver_mod.get_base_version.cache_clear()
    ver_mod.get_app_version_display.cache_clear()
    assert ver_mod.get_base_version() == "1.1.0-rc.2"
    assert ver_mod.get_app_version_display().startswith("1.1.0-rc.2")

    bug_yml = (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text("utf-8")
    assert "v1.1.0" in bug_yml
    assert "1.0.1" not in bug_yml

    _get_qapp()
    from ui.acid_style import AcidBarcodeFooter

    footer = AcidBarcodeFooter()
    try:
        assert "v1.1.0-rc.2" in footer.status_lbl.text()
    finally:
        footer.close()

    for readme_name in ("README.md", "README.en.md", "README.ko.md", "README.ja.md"):
        txt = (REPO_ROOT / readme_name).read_text("utf-8")
        assert "1.0.1" not in txt, f"{readme_name} still contains stale 1.0.1"


def test_frozen_build_info_displays_exact_rc1_without_dev_or_sha(monkeypatch) -> None:
    """Packaged _build_info must surface exact '1.1.0-rc.2' with zero '-dev' or '+sha'."""
    import sys
    from types import ModuleType
    from core import version as ver_mod

    fake_bi = ModuleType("core._build_info")
    fake_bi.BASE_VERSION = "1.1.0-rc.2"
    fake_bi.BUILD_VERSION = "1.1.0-rc.2"
    fake_bi.GIT_SHA = "deadbee"

    monkeypatch.delenv("LISTENSCOPE_BUILD_VERSION", raising=False)
    monkeypatch.delenv("LISTENSCOPE_BASE_VERSION", raising=False)
    monkeypatch.delenv("LISTENSCOPE_GIT_SHA", raising=False)
    monkeypatch.setitem(sys.modules, "core._build_info", fake_bi)
    ver_mod.get_base_version.cache_clear()
    ver_mod.get_app_version_display.cache_clear()
    try:
        disp = ver_mod.get_app_version_display()
        assert disp == "1.1.0-rc.2"
        assert "-dev" not in disp and "+" not in disp
    finally:
        ver_mod.get_base_version.cache_clear()
        ver_mod.get_app_version_display.cache_clear()


def test_rc_semver_comparison_and_prerelease_opt_out(monkeypatch) -> None:
    """Verify RC version ordering and exclusion of prereleases when include_prerelease=False."""
    import json
    from unittest.mock import MagicMock
    from core.updater import check_for_updates, is_newer_version

    assert is_newer_version("v1.1.0-rc.2", "1.1.0-rc.1") is True
    assert is_newer_version("v1.1.0", "1.1.0-rc.2") is True
    assert is_newer_version("v1.1.0-rc.10", "1.1.0-rc.2") is True
    assert is_newer_version("v1.1.0-rc.1", "1.1.0") is False

    rc_entry = {
        "tag_name": "v1.1.0-rc.1",
        "name": "ListenScope v1.1.0-rc.1",
        "body": "测试版，仅用于验证升级流程",
        "published_at": "2026-11-28T00:00:00Z",
        "html_url": "https://github.com/Ceph-learner/ListenScope/releases/tag/v1.1.0-rc.1",
        "prerelease": True,
        "draft": False,
        "assets": [],
    }
    stable_entry = {
        "tag_name": "v1.0.1",
        "name": "ListenScope v1.0.1",
        "body": "Stable release",
        "published_at": "2026-10-01T00:00:00Z",
        "html_url": "https://github.com/Ceph-learner/ListenScope/releases/tag/v1.0.1",
        "prerelease": False,
        "draft": False,
        "assets": [],
    }
    rc_payload = json.dumps(rc_entry).encode("utf-8")

    fake_resp = MagicMock()
    fake_resp.read.return_value = rc_payload
    fake_resp.__enter__.return_value = fake_resp
    fake_resp.__exit__.return_value = False
    fake_opener = MagicMock()
    fake_opener.open.return_value = fake_resp

    monkeypatch.setattr("core.updater._build_opener", lambda **_kw: fake_opener)
    res = check_for_updates("1.0.1", include_prerelease=False)
    assert res.status == "up_to_date"
    assert res.release is None

    seen_urls: list[str] = []

    class _ListOpener:
        def open(self, req, timeout=5.0):
            seen_urls.append(req.full_url)
            resp = MagicMock()
            resp.read.return_value = json.dumps([rc_entry, stable_entry]).encode("utf-8")
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

    monkeypatch.setattr("core.updater._build_opener", lambda **_kw: _ListOpener())
    res_no_pre = check_for_updates("1.0.1", include_prerelease=False)
    assert res_no_pre.status == "up_to_date"
    assert res_no_pre.release is not None and res_no_pre.release.tag_name == "v1.0.1"
    assert seen_urls[-1].endswith("/releases/latest")

    res_with_pre = check_for_updates("1.0.1", include_prerelease=True)
    assert res_with_pre.status == "update_available"
    assert res_with_pre.release is not None
    assert res_with_pre.release.tag_name == "v1.1.0-rc.1"
    assert seen_urls[-1].endswith("/releases?per_page=10")


def test_r4_2_release_workflow_hardened_and_supports_dry_run() -> None:
    """release-windows.yml pins SHA+v7, avoids ${{}} in run:, supports dry_run, prereleases, and numeric iss version."""
    yml_path = REPO_ROOT / ".github" / "workflows" / "release-windows.yml"
    yml = yml_path.read_text("utf-8")

    uses_matches = re.findall(r"^\s*-?\s*uses:\s*(.+)$", yml, re.MULTILINE)
    assert len(uses_matches) >= 3
    for spec in uses_matches:
        assert re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}\s+#\s*v\d+", spec.strip()), (
            f"Action not pinned to 40-char commit SHA with '# vN' comment: {spec!r}"
        )

    run_blocks = _extract_run_blocks(yml)
    assert len(run_blocks) >= 8
    for block in run_blocks:
        assert "${{" not in block, f"Unsafe GitHub expression inside run block:\n{block}"

    assert "dry_run:" in yml
    assert "default: true" in yml
    assert "v1.1.0" in yml
    assert "inputs.dry_run != true" in yml
    assert "Write dry-run artifact summary" in yml
    assert "GITHUB_STEP_SUMMARY" in yml
    assert r"QT_QPA_FONTDIR: C:\Windows\Fonts" in yml
    assert "-o faulthandler_timeout=180" in yml

    # Prerelease tag handling: '-' in tag enables --prerelease and prerelease notice
    assert '$isPrerelease = $tag.Contains("-")' in yml
    assert '"--prerelease"' in yml
    assert "测试版，仅用于验证升级流程" in yml
    assert 'BUILD_VERSION = "$env:APP_VERSION"' in yml
    assert "ListenScope startup version=" in yml
    assert "/DMyAppNumericVersion=" in yml

    spec_txt = (REPO_ROOT / "packaging" / "listenscope_core.spec").read_text("utf-8")
    assert "core._build_info" in spec_txt

    for required_token in (
        "ListenScope-Setup-Windows-x64.exe",
        "ListenScope-Core-Windows-x64-Portable.zip",
        "SHA256SUMS.txt",
        "Get-FileHash",
        "-Algorithm SHA256",
        '"$hash  $name"',
        r"dist\release\SHA256SUMS.txt",
    ):
        assert required_token in yml, f"Missing expected release token {required_token!r}"

    dep_yml = (REPO_ROOT / ".github" / "dependabot.yml").read_text("utf-8")
    assert 'package-ecosystem: "github-actions"' in dep_yml


def test_t5_social_preview_exists_dimensions_and_size() -> None:
    """docs/design/social_preview.png must exist, be exact 1280x640 PNG, and <= 1 MB."""
    png_path = REPO_ROOT / "docs" / "design" / "social_preview.png"
    assert png_path.exists(), "docs/design/social_preview.png does not exist"
    raw = png_path.read_bytes()
    assert len(raw) <= 1048576, f"social_preview.png exceeds 1 MB: {len(raw)} bytes"
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (1280, 640), f"Expected 1280x640, got {width}x{height}"

    script_src = (REPO_ROOT / "scripts" / "make_screenshots.py").read_text("utf-8")
    assert "def capture_social_preview" in script_src
    assert "--social-preview" in script_src


def test_r4_user_docs_and_changelog_content_and_formal_tone() -> None:
    """CHANGELOG and USER_GUIDE/FAQ docs cover required v1.1.0 topics with zero AI-dev or draft wording."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [1.1.0] - Pending Release" in changelog
    assert changelog.index("## [Unreleased]") < changelog.index("## [1.1.0] - Pending Release")
    assert "随 #" not in changelog
    assert "随 #66" not in changelog
    assert "随 #67" not in changelog
    for section in ("### 新功能", "### 改进", "### 修复", "### 已知限制"):
        assert section in changelog
    for item in ("#91", "应用内在线更新", "系统环回默认播放设备自动跟随", "四级渐进折叠", "[兜底]", "temperley1999", "SMF Type-0", "SHA256SUMS.txt", "Snap Layouts"):
        assert item in changelog

    ug_zh = (REPO_ROOT / "docs" / "USER_GUIDE.md").read_text("utf-8")
    faq_zh = (REPO_ROOT / "docs" / "FAQ.md").read_text("utf-8")
    for doc in (ug_zh, faq_zh):
        assert "系统环回" in doc
        assert "120 秒" in doc
        assert "GitHub Releases" in doc
        assert "SHA256SUMS.txt" in doc

    ug_en = (REPO_ROOT / "docs" / "USER_GUIDE.en.md").read_text("utf-8")
    faq_en = (REPO_ROOT / "docs" / "FAQ.en.md").read_text("utf-8")
    for doc in (ug_en, faq_en):
        assert "System Loopback" in doc
        assert "120-second" in doc
        assert "GitHub Releases" in doc
        assert "SHA256SUMS.txt" in doc

    forbidden_terms = ("AI 辅助", "AI 助手", "Neon", "Hydrogen", "Codex", "Claude", "Antigravity", "subagent")
    for rel in ("CHANGELOG.md", "docs/USER_GUIDE.md", "docs/USER_GUIDE.en.md", "docs/FAQ.md", "docs/FAQ.en.md"):
        content = (REPO_ROOT / rel).read_text("utf-8")
        low = content.lower()
        for term in forbidden_terms:
            assert term.lower() not in low, f"Forbidden term {term!r} found in {rel}"
