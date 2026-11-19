"""Appearance values independent of Qt and of the settings file version."""

from dataclasses import dataclass
import re


PRESETS = {
    "classic": ("经典", "#14161A", "#E6EAF0", "#7EE2B8"),
    "lenso": ("Lenso", "#131B2B", "#EFF5FF", "#A3C6FF"),
    "codex": ("Codex", "#141417", "#ECECF0", "#ACAEFF"),
    "claude": ("Claude Code", "#201B18", "#F1E5D8", "#DF9B7B"),
    "acid_telemetry": ("酸性遥测", "#0B0D0F", "#F1F2EC", "#CEFF18"),
}
LIGHT_PRESETS = {
    "classic": ("经典 · 白天", "#F4F6FA", "#181D25", "#0E8A6D"),
    "lenso": ("Lenso · 白天", "#EEF4FC", "#152238", "#2563EB"),
    "codex": ("Codex · 白天", "#F5F5F8", "#18181F", "#4F46E5"),
    "claude": ("Claude Code · 白天", "#FAF5F0", "#2A211B", "#B45309"),
    "acid_telemetry": ("酸性遥测 · 白天", "#EEF2F6", "#090D14", "#00A878"),
}
_PRESET_ALIASES = {
    "marathon": "acid_telemetry",
}
THEME_MODES = {
    "dark": "黑夜",
    "light": "白天",
    "system": "跟随系统",
}
DEFAULT_ANALYSIS_LAYOUT = "monitor"
ANALYSIS_LAYOUTS = {
    "monitor": "实时监听",
    "frequency": "频率诊断",
    "history": "时频追踪",
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


def _font_family(raw):
    if not isinstance(raw, str):
        return ""
    cleaned = raw.replace('"', "").replace("'", "").replace(";", "").strip()
    return cleaned[:80]


def _bg_image(raw):
    if not isinstance(raw, str):
        return ""
    cleaned = raw.replace('"', "").replace("'", "").strip()
    return cleaned[:512]


@dataclass(frozen=True)
class Appearance:
    preset: str = "acid_telemetry"
    font_size: int = 12
    background: str = ""
    text: str = ""
    accent: str = ""
    scope: str = "floating"
    strength: int = 45
    softness: int = 60
    dispersion: int = 20
    layout: str = "split"
    analysis_layout: str = DEFAULT_ANALYSIS_LAYOUT
    theme_mode: str = "light"
    font_family: str = ""
    background_image: str = ""
    language: str = "zh"
    frameless: bool = True
    help_mode: bool = True
    focus_animations: bool = True

    @classmethod
    def from_mapping(cls, raw):
        if not isinstance(raw, dict):
            return cls()
        raw_preset = raw.get("preset")
        if isinstance(raw_preset, str):
            raw_preset = _PRESET_ALIASES.get(raw_preset, raw_preset)
        preset = _choice(raw_preset, PRESETS, "acid_telemetry")
        is_acid = preset == "acid_telemetry"
        raw_frameless = raw.get("frameless")
        frameless = raw_frameless if isinstance(raw_frameless, bool) else True
        raw_help_mode = raw.get("help_mode")
        help_mode = raw_help_mode if isinstance(raw_help_mode, bool) else True
        raw_focus_anim = raw.get("focus_animations")
        focus_animations = raw_focus_anim if isinstance(raw_focus_anim, bool) else True
        return cls(
            preset=preset,
            font_size=_number(raw.get("font_size"), 11, 20, 12),
            background="" if is_acid else _color(raw.get("background")),
            text="" if is_acid else _color(raw.get("text")),
            accent="" if is_acid else _color(raw.get("accent")),
            scope=_choice(raw.get("scope"), SCOPES, "floating"),
            strength=_number(raw.get("strength"), 0, 100, 45),
            softness=_number(raw.get("softness"), 0, 100, 60),
            dispersion=_number(raw.get("dispersion"), 0, 100, 20),
            layout=_choice(raw.get("layout"), LAYOUTS, "split"),
            analysis_layout=_choice(raw.get("analysis_layout"), ANALYSIS_LAYOUTS, DEFAULT_ANALYSIS_LAYOUT),
            theme_mode=_choice(raw.get("theme_mode"), THEME_MODES, "light"),
            font_family="" if is_acid else _font_family(raw.get("font_family")),
            background_image="" if is_acid else _bg_image(raw.get("background_image")),
            language=_choice(raw.get("language"), {"zh", "en", "ko", "ja"}, "zh"),
            frameless=frameless,
            help_mode=help_mode,
            focus_animations=focus_animations,
        )

    def resolve_theme_mode(self, *, system_is_dark: bool | None = None) -> str:
        if self.theme_mode == "light":
            return "light"
        if self.theme_mode == "dark":
            return "dark"
        return "light" if system_is_dark is False else "dark"

    def effective_colors(self, *, system_is_dark: bool | None = None):
        mode = self.resolve_theme_mode(system_is_dark=system_is_dark)
        table = LIGHT_PRESETS if mode == "light" else PRESETS
        _, background, foreground, accent = table[self.preset]
        if self.preset == "acid_telemetry":
            return background, foreground, accent
        return self.background or background, self.text or foreground, self.accent or accent

    def is_acid_locked(self) -> bool:
        return self.preset == "acid_telemetry"

    def effective_font_family(self) -> str:
        return "" if self.preset == "acid_telemetry" else self.font_family

    def effective_background_image(self) -> str:
        return "" if self.preset == "acid_telemetry" else self.background_image

    @property
    def colors(self):
        return self.effective_colors()

