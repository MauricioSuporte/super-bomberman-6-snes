#!/usr/bin/env python3
"""Draws Super Bomberman (USA) enemies straight from SB1's own animation and sprite tables into the frame
sheets that tools/sb6/features/sb1_enemies.py builds SB5 enemies from (research tool; the build only reads
the PNGs). Every frame of every animation is drawn, not only the ones a capture happened to show.

    python tools/sb1_enemy_frames.py SB1_ROM DIR

DIR = a Mesen dump of SB1 in the stage (tools/mesen/sb1_stages.lua STAGE=08 VIDEO=2000: 08_vram.bin,
08_cgram.bin, 08_ppu.bin) for the tiles and colors those tables point at.

SB1's tables (docs/ROM_MAP.md "SB1's 2-1 enemies"): an animation = [count] + count x [frame24, frames]; a
frame = [count] + count x [dx, dy, slot, tile, attr] (`$C6:25EA`): OBJ name = $C3:082F[(obj $0F + slot) & 15]
| tile (+ $100 when that sum has bit 3), attr = ((attr & $CF) | obj $0E | name bit 8) + obj $1E, 16x16 when
attr & $20; it is drawn at (obj x - 8 + dx, obj y + dy) (+ the screen's $18).

Sheets: 32 x 64 cells side by side, transparent background; a piece (dx, dy) has its top left at cell pixel
(dx + 16, dy + 36), so that with sb1_enemies.py's anchor (8, 28) and SB5's (-8, -9) it becomes the SB5 piece
(dx, dy - 1): SB1's 16x16 body (-8, -8) lands where SB5 draws its own 16x16 enemies, and one rule for every
kind keeps their heights relative to each other SB1's. Colors are SB1's BGR15 values << 3.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb1_enemy_assets import SIZES, _tile  # noqa: E402

CW, CH = 32, 64
OX, OY = 24, 36                  # cell pixel of SB1's obj x, y (a piece's left = obj x - 8 + dx, top = obj y + dy)
NAME_LUT = 0xC3082F
# kind: obj $0F (tile slot base), $1E (palette add), animations (SB5 facing order right, down, left, up)
KINDS = {
    "spring": (0x07, 0x0C, [0xC643A7, 0xC643C8, 0xC643E9, 0xC64386]),   # SB1 dirs 1, 2, 3, 0 ($C6:7D1B)
    "pot": (0x04, 0x08, [0xC6448A]),
    "clown": (0x06, 0x0A, [0xC64AFC]),
}


def rom_at(rom, a):
    return a & 0x3FFFFF


def anim(rom, a):
    o = rom_at(rom, a)
    return [(int.from_bytes(rom[o + 1 + 4 * k:o + 4 + 4 * k], "little"), rom[o + 4 + 4 * k]) for k in range(rom[o])]


def pieces(rom, ptr, f0f, f1e, f0e=0x30):
    o = rom_at(rom, ptr)
    lut = rom[rom_at(rom, NAME_LUT):rom_at(rom, NAME_LUT) + 16]
    out = []
    for k in range(rom[o]):
        dx, dy, slot, tile, attr = rom[o + 1 + 5 * k:o + 6 + 5 * k]
        s = (f0f + slot) & 15
        hi = 1 if s & 8 else 0
        name = (lut[s] | tile) | hi << 8
        a = (((attr & 0xCF) | f0e | hi) + f1e) & 0xFF
        out.append((dx - 256 if dx > 127 else dx, dy - 256 if dy > 127 else dy, name, a, bool(attr & 0x20)))
    return out


def draw(ps, v, c, obsel):
    base, gap = (obsel & 7) << 14, ((obsel >> 3) & 3) << 13
    small, large = SIZES[obsel >> 5]
    img = np.zeros((CH, CW, 4), np.uint8)
    for dx, dy, name, attr, big in reversed(ps):          # (the first piece is on top)
        w, h = large if big else small
        pal = (attr >> 1) & 7
        t = np.zeros((h, w, 4), np.uint8)
        for ty in range(h // 8):
            for tx in range(w // 8):
                n = ((name & 0xF0) + ty * 16) & 0xF0 | ((name + tx) & 0x0F)
                px = _tile(v, base + n * 32 + ((gap + 0x2000) if name & 0x100 else 0))
                for yy in range(8):
                    for xx in range(8):
                        k = int(px[yy, xx])
                        if k:
                            i2 = 128 + pal * 16 + k
                            cw = c[2 * i2] | c[2 * i2 + 1] << 8
                            t[ty * 8 + yy, tx * 8 + xx] = ((cw & 31) << 3, (cw >> 5 & 31) << 3, (cw >> 10 & 31) << 3, 255)
        if attr & 0x40:
            t = t[:, ::-1]
        if attr & 0x80:
            t = t[::-1]
        X, Y = OX + dx - 8, OY + dy
        if X < 0 or Y < 0 or X + w > CW or Y + h > CH:
            raise SystemExit(f"piece ({dx}, {dy}) {w}x{h} outside the {CW}x{CH} cell")
        m = t[..., 3] > 0
        img[Y:Y + h, X:X + w][m] = t[m]
    return img


def main():
    rom = open(sys.argv[1], "rb").read()
    d = sys.argv[2]
    v = open(os.path.join(d, "08_vram.bin"), "rb").read()
    c = open(os.path.join(d, "08_cgram.bin"), "rb").read()
    obsel = open(os.path.join(d, "08_ppu.bin"), "rb").read()[1]
    for name, (f0f, f1e, anims) in KINDS.items():
        cells, order, scripts = [], {}, []
        for a in anims:
            seq = []
            for ptr, frames in anim(rom, a):
                if ptr not in order:
                    order[ptr] = len(cells)
                    cells.append(draw(pieces(rom, ptr, f0f, f1e), v, c, obsel))
                seq.append((order[ptr], frames))
            scripts.append(seq)
        Image.fromarray(np.concatenate(cells, 1)).save(os.path.join(ROOT, "assets", "enemies", f"sb1_2-1_{name}.png"))
        print(f"{name}: {len(cells)} pictures; animations (cell, frames): {scripts}")


if __name__ == "__main__":
    main()
