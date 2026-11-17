"""Appearance values independent of Qt and of the settings file version."""

from dataclasses import dataclass
import re


PRESETS = {
    "classic": ("经典", "#14161A", "#E6EAF0", "#7EE2B8"),
    "lenso": ("Lenso", "#131B2B", "#EFF5FF", "#A3C6FF"),
    "codex": ("Codex", "#141417", "#ECECF0", "#ACAEFF"),
    "claude": ("Claude Code", "#201B18", "#F1E5D8", "#DF9B7B"),
}
SCOPES = {"off", "floating", "panels"}
LAYOUTS = {
    "workbench": ("A · 工作台", "音轨、分析和历史波形从上到下排列。"),
    "split": ("B · 双栏扒谱（默认）", "左侧切换音轨，右侧查看分析，历史波形在下方。"),
    "practice": ("C · 练习优先", "历史波形置顶并放大，下方并排显示分析和音轨。"),
}


def _choice(raw, choices, default):
    return raw if isinstance(raw, str) and raw in choices else default


def _number(raw, low, high, default):
    return min(high, max(low, raw)) if type(raw) is int else default


def _color(raw):
    return raw.upper() if isinstance(raw, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", raw) else ""


@dataclass(frozen=True)
class Appearance:
    preset: str = "classic"
    font_size: int = 12
    background: str = ""
    text: str = ""
    accent: str = ""
    scope: str = "floating"
    strength: int = 45
    softness: int = 60
    dispersion: int = 20
    layout: str = "split"

    @classmethod
    def from_mapping(cls, raw):
        if not isinstance(raw, dict):
            return cls()
        return cls(
            preset=_choice(raw.get("preset"), PRESETS, "classic"),
            font_size=_number(raw.get("font_size"), 11, 16, 12),
            background=_color(raw.get("background")),
            text=_color(raw.get("text")),
            accent=_color(raw.get("accent")),
            scope=_choice(raw.get("scope"), SCOPES, "floating"),
            strength=_number(raw.get("strength"), 0, 100, 45),
            softness=_number(raw.get("softness"), 0, 100, 60),
            dispersion=_number(raw.get("dispersion"), 0, 100, 20),
            layout=_choice(raw.get("layout"), LAYOUTS, "split"),
        )

    @property
    def colors(self):
        _, background, foreground, accent = PRESETS[self.preset]
        return self.background or background, self.text or foreground, self.accent or accent
