"""Build multi-resolution listenscope.ico and 1280x640 social_preview.png from docs/design/icon/ SVGs.

Dev/asset-generation script only (uses Pillow; NOT a Core runtime dependency).
Renders SVGs via PySide6.QtSvg.QSvgRenderer (or cairosvg if installed) and packs ICO via Pillow.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

REPO_ROOT = Path(__file__).resolve().parent.parent
ICON_SRC_DIR = REPO_ROOT / "docs" / "design" / "icon"
ASSETS_DIR = REPO_ROOT / "ui" / "assets"
DESIGN_DIR = REPO_ROOT / "docs" / "design"


def _render_svg_to_pil(svg_path: Path, size: int) -> Image.Image:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    del app
    renderer = QtSvg.QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {svg_path}")
    img = QtGui.QImage(size, size, QtGui.QImage.Format.Format_RGBA8888)
    img.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(img)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QtCore.QRectF(0, 0, size, size))
    painter.end()
    ptr = img.constBits()
    return Image.frombytes("RGBA", (size, size), bytes(ptr))


def build_ico() -> Path:
    import io
    import struct

    small_svg = ICON_SRC_DIR / "listenscope_small_dark.svg"
    master_svg = ICON_SRC_DIR / "listenscope_master_dark.svg"
    small_sizes = (16, 20, 24, 32)
    master_sizes = (40, 48, 64, 96, 128, 256)

    frames: list[tuple[int, bytes]] = []
    for sz in small_sizes:
        buf = io.BytesIO()
        _render_svg_to_pil(small_svg, sz).save(buf, format="PNG")
        frames.append((sz, buf.getvalue()))
    for sz in master_sizes:
        buf = io.BytesIO()
        _render_svg_to_pil(master_svg, sz).save(buf, format="PNG")
        frames.append((sz, buf.getvalue()))

    out_ico = ASSETS_DIR / "listenscope.ico"
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = bytearray()
    payload = bytearray()
    for sz, png_bytes in frames:
        dim = 0 if sz >= 256 else sz
        entries.extend(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png_bytes), offset))
        payload.extend(png_bytes)
        offset += len(png_bytes)
    out_ico.write_bytes(header + bytes(entries) + bytes(payload))
    return out_ico


def _find_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def build_social_preview() -> Path:
    w, h = 1280, 640
    canvas = Image.new("RGBA", (w, h), (11, 13, 15, 255))
    draw = ImageDraw.Draw(canvas)

    # Subtle technical grid
    for gx in range(0, w, 64):
        draw.line([(gx, 0), (gx, h)], fill=(24, 29, 34, 255), width=1)
    for gy in range(0, h, 64):
        draw.line([(0, gy), (w, gy)], fill=(24, 29, 34, 255), width=1)
    # Accent top/bottom trim
    draw.rectangle([(0, 0), (w, 6)], fill=(206, 255, 24, 255))
    draw.rectangle([(0, h - 6), (w, h)], fill=(119, 220, 228, 255))

    icon_img = _render_svg_to_pil(ICON_SRC_DIR / "listenscope_master_dark.svg", 320)
    canvas.paste(icon_img, (120, (h - 320) // 2), icon_img)

    title_font = _find_font(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ],
        84,
    )
    zh_font = _find_font(
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
        ],
        38,
    )
    en_font = _find_font(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ],
        30,
    )

    tx = 500
    draw.text((tx, 195), "ListenScope", font=title_font, fill=(241, 242, 236, 255))
    draw.text((tx, 305), "实时音频分析 · 分轨 · 吉他扒谱工作台", font=zh_font, fill=(206, 255, 24, 255))
    draw.text((tx, 370), "Offline Audio Analysis & Stem Practice", font=en_font, fill=(119, 220, 228, 255))

    out_png = DESIGN_DIR / "social_preview.png"
    canvas.convert("RGB").save(out_png, format="PNG", optimize=True)
    return out_png


def main() -> int:
    ico = build_ico()
    png = build_social_preview()
    print(f"Generated {ico} and {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
