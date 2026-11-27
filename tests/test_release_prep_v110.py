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


def test_r4_1_version_unified_to_1_1_0() -> None:
    """All version sources, HUD footer, issue template, and READMEs are aligned to 1.1.0."""
    pyproj = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    assert pyproj["project"]["version"] == "1.1.0"

    iss_txt = (REPO_ROOT / "scripts" / "installer.iss").read_text("utf-8")
    assert '#define MyAppVersion "1.1.0"' in iss_txt
    assert "1.0.1" not in iss_txt

    from core import version as ver_mod

    assert ver_mod._FALLBACK_BASE_VERSION == "1.1.0"
    ver_mod.get_base_version.cache_clear()
    ver_mod.get_app_version_display.cache_clear()
    assert ver_mod.get_base_version() == "1.1.0"
    assert ver_mod.get_app_version_display().startswith("1.1.0")

    bug_yml = (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text("utf-8")
    assert "v1.1.0-dev+" in bug_yml
    assert "1.0.1" not in bug_yml

    _get_qapp()
    from ui.acid_style import AcidBarcodeFooter

    footer = AcidBarcodeFooter()
    try:
        assert "v1.1.0" in footer.status_lbl.text()
    finally:
        footer.close()

    for readme_name in ("README.md", "README.en.md", "README.ko.md", "README.ja.md"):
        txt = (REPO_ROOT / readme_name).read_text("utf-8")
        assert "1.0.1" not in txt, f"{readme_name} still contains stale 1.0.1"


def test_r4_2_release_workflow_hardened_and_supports_dry_run() -> None:
    """release-windows.yml pins SHA+v7, avoids ${{}} in run:, supports dry_run, and keeps SHA256 notes."""
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
    """CHANGELOG and USER_GUIDE/FAQ docs cover required v1.1.0 topics with zero AI-dev wording."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [1.1.0] - Pending Release" in changelog
    assert changelog.index("## [Unreleased]") < changelog.index("## [1.1.0] - Pending Release")
    for section in ("### 新功能", "### 改进", "### 修复", "### 已知限制"):
        assert section in changelog
    for item in ("#66", "#67", "temperley1999", "SMF Type-0", "SHA256SUMS.txt", "Snap Layouts"):
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
