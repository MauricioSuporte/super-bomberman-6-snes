#!/usr/bin/env python3
"""World 1's 1-6 arena from the SB6 Unity scene (research tool; the build only reads the PNGs).

    python tools/unity_arena_assets.py UNITY_TILES_DIR

UNITY_TILES_DIR = Assets/Sprites/Tiles/1-6 of the Unity project: TilesCroud.png (stands with the crowd) and
TileWithoutCroud.png (empty stands), 17 x 13 cells of 16 px like SB1's stages. An SB5 arena draws 15 columns:
its column 0 is Unity's column 0 (the crowd on the left), columns 1-13 the field (Unity's 2-14) and column 14
Unity's column 16 (the crowd on the right); the thin borders of Unity's columns 1 and 15 are left out. The
pictures written here are laid out the way tools/sb6/features/sb1_stages.py reads them (SB5 column c = picture
column c + 1; picture column 0 and SB5's column 15 are not shown). Writes assets/stages/sb6_1-6_field.png, sb6_1-6_empty_field.png (+ _empty_soft.png), sb6_1-6_soft.png
(the plain floor: the arena has no soft blocks).
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def arrange(path):
    im = Image.open(path).convert("RGBA")
    if im.size != (272, 208):
        raise SystemExit(f"{path}: {im.size}, expected 272 x 208")
    flat = Image.new("RGBA", im.size, (0, 0, 0, 255))
    flat.alpha_composite(im)
    flat = flat.convert("RGB")
    out = Image.new("RGB", (272, 208))
    order = [1, 0] + list(range(2, 15)) + [16, 16]     # picture column -> Unity column
    for col, src in enumerate(order):
        out.paste(flat.crop((src * 16, 0, src * 16 + 16, 208)), (col * 16, 0))
    return out


def main():
    d = sys.argv[1]
    dst = os.path.join(ROOT, "assets", "stages")
    field = arrange(os.path.join(d, "TilesCroud.png"))
    field.save(os.path.join(dst, "sb6_1-6_field.png"))
    arrange(os.path.join(d, "TileWithoutCroud.png")).save(os.path.join(dst, "sb6_1-6_empty_field.png"))
    for n in ("sb6_1-6_soft.png", "sb6_1-6_empty_soft.png"):
        field.crop((4 * 16, 5 * 16, 5 * 16, 6 * 16)).save(os.path.join(dst, n))


if __name__ == "__main__":
    main()
