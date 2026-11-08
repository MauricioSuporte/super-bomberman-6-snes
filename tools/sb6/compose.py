"""Builds the reference 256x224 title picture from the fan-game assets.

The geometry mirrors TitleScreenDropIntro / TitleScreenVerticalPanIntro of the
Unity project (see assets/title/layout.json). Returns RGBA layers so the
background (BG2) and the logo (BG1) can be converted separately.
"""
import json
import os
from PIL import Image


def _alpha_paste(dst, src, x, y):
    layer = Image.new("RGBA", dst.size, (0, 0, 0, 0))
    layer.paste(src, (x, y))
    return Image.alpha_composite(dst, layer)


def _binary_alpha(im):
    """SNES layers have 1-bit transparency: threshold the alpha channel."""
    im = im.convert("RGBA")
    px = [(r, g, b, 255 if a >= 128 else 0) for (r, g, b, a) in im.getdata()]
    out = Image.new("RGBA", im.size)
    out.putdata(px)
    return out


def load_layout(asset_dir):
    with open(os.path.join(asset_dir, "layout.json"), encoding="utf-8") as fh:
        return json.load(fh)


def character_positions(layout):
    """Top-left pixel of every character, keyed by name."""
    sw, sh = layout["screen"]
    chars = layout["characters"]
    n = len(chars)
    left_half = chars[0]["size"][0] / 2
    right_half = chars[-1]["size"][0] / 2
    min_x = -sw / 2 + left_half
    max_x = sw / 2 - right_half
    pos = {}
    for i, c in enumerate(chars):
        t = i / (n - 1)
        cx = min_x + (max_x - min_x) * t + c["offset"][0]
        bottom = layout["characters_bottom_margin"] + c["offset"][1]
        w, h = c["size"]
        left = round(sw / 2 + cx - w / 2)
        top = round(sh - (bottom + h))
        pos[c["name"]] = (left, top)
    return pos


def compose_background(asset_dir, layout):
    sw, sh = layout["screen"]
    bg = Image.open(os.path.join(asset_dir, layout["background"]["file"])).convert("RGBA")
    top = layout["background"]["crop_top"]
    canvas = bg.crop((0, top, sw, top + sh))
    canvas = _binary_alpha(canvas)
    by_name = {c["name"]: c for c in layout["characters"]}
    pos = character_positions(layout)
    for name in layout["draw_order"]:
        c = by_name[name]
        sprite = Image.open(os.path.join(asset_dir, c["file"])).convert("RGBA")
        if sprite.size != tuple(c["size"]):
            sprite = sprite.resize(tuple(c["size"]), Image.NEAREST)
        canvas = _alpha_paste(canvas, _binary_alpha(sprite), *pos[name])
    # The background is opaque: fill any hole with the top-left sky color.
    opaque = Image.new("RGBA", canvas.size, canvas.getpixel((0, 0))[:3] + (255,))
    return Image.alpha_composite(opaque, canvas)


def compose_logo(asset_dir, layout, frame_file=None, native=False):
    """Logo on a transparent 256xN canvas, already positioned (x, y) on screen."""
    sw, _ = layout["screen"]
    lg = layout["logo"]
    logo = Image.open(os.path.join(asset_dir, frame_file or lg["file"])).convert("RGBA")
    if not native:
        bw, bh = lg["box"]
        scale = min(bw / logo.width, bh / logo.height)
        size = (max(1, round(logo.width * scale)), max(1, round(logo.height * scale)))
        logo = logo.resize(size, Image.LANCZOS)
    logo = _binary_alpha(logo)
    x = (sw - logo.width) // 2
    return logo, (x, lg["top"])
