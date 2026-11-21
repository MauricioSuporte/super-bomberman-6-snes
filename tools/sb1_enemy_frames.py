#!/usr/bin/env python3
"""Draws Super Bomberman (USA) enemies straight from SB1's own animation and sprite tables into the frame
sheets that tools/sb6/features/sb1_enemies.py builds SB5 enemies from (research tool; the build only reads
the PNGs). Every frame of every animation is drawn, not only the ones a capture happened to show.

    python tools/sb1_enemy_frames.py SB1_ROM DIR

DIR = Mesen dumps of SB1 in each stage (tools/mesen/sb1_stages.lua STAGE=<ss> VIDEO=2000: <ss>_vram.bin,
<ss>_cgram.bin, <ss>_ppu.bin; 08 = 2-1, 19 = 4-2, 1B = 4-4) for the tiles and colors those tables point at; a
sheet whose stage has no dump is skipped.

SB1's tables (docs/ROM_MAP.md "SB1's 2-1 enemies"): an animation = [count] + count x [frame24, frames]; a
frame = [count] + count x [dx, dy, slot, tile, attr] (`$C6:25EA`): OBJ name = $C3:082F[(obj $0F + slot) & 15]
| tile (+ $100 when that sum has bit 3), attr = ((attr & $CF) | obj $0E | name bit 8) + obj $1E, 16x16 when
attr & $20; it is drawn at (obj x - 8 + dx, obj y + dy) (+ the screen's $18).

Sheets: 32 x 64 cells (64 x 64 for SB1 4-2's horned robot, OX = 40) side by side, transparent background; a piece (dx, dy) has its top left at cell pixel
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
# sheet: stage dump, cell width, OX, [(obj $0F (tile slot base), $1E (palette add), animations)] (several kinds
# on one sheet: their pictures one after the other). Animations in SB1's direction order where SB1 has 4 (a
# direction table at obj $16: 0 up, 1 right, 2 down, 3 left).
SHEETS = {
    "sb1_2-1_spring": ("08", 32, 24, [(0x07, 0x0C, [0xC643A7, 0xC643C8, 0xC643E9, 0xC64386])]),  # SB1 dirs 1, 2, 3, 0
    "sb1_2-1_pot": ("08", 32, 24, [(0x04, 0x08, [0xC6448A])]),
    "sb1_2-1_clown": ("08", 32, 24, [(0x06, 0x0A, [0xC64AFC])]),
    # SB1 4-4's UFO ($C6:74C5, table $C6:7DA3) and bomb robot ($C6:5FDE, table $C6:7D13)
    "sb1_4-4_ufobot": ("1B", 32, 24, [(0x07, 0x0A, [0xC65842]),
                                      (0x08, 0x0C, [0xC641BE, 0xC641CF, 0xC641E0, 0xC641F1])]),
    # SB1 4-2's horned robot ($C6:5A34, table $C6:7D03; 40 px wide lying on its side)
    "sb1_4-2_horn": ("19", 64, 40, [(0x04, 0x08, [0xC63E7E, 0xC63E8F, 0xC63EB8, 0xC63EE5])]),
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


def draw(ps, v, c, obsel, cw=CW, ox=OX):
    base, gap = (obsel & 7) << 14, ((obsel >> 3) & 3) << 13
    small, large = SIZES[obsel >> 5]
    img = np.zeros((CH, cw, 4), np.uint8)
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
                            col = c[2 * i2] | c[2 * i2 + 1] << 8
                            t[ty * 8 + yy, tx * 8 + xx] = ((col & 31) << 3, (col >> 5 & 31) << 3, (col >> 10 & 31) << 3, 255)
        if attr & 0x40:
            t = t[:, ::-1]
        if attr & 0x80:
            t = t[::-1]
        X, Y = ox + dx - 8, OY + dy
        if X < 0 or Y < 0 or X + w > cw or Y + h > CH:
            raise SystemExit(f"piece ({dx}, {dy}) {w}x{h} outside the {cw}x{CH} cell")
        m = t[..., 3] > 0
        img[Y:Y + h, X:X + w][m] = t[m]
    return img


def main():
    rom = open(sys.argv[1], "rb").read()
    d = sys.argv[2]
    for sheet, (stage, cw, ox, kinds) in SHEETS.items():
        if not os.path.exists(os.path.join(d, f"{stage}_vram.bin")):
            print(f"{sheet}: no {stage}_vram.bin, skipped")
            continue
        v = open(os.path.join(d, f"{stage}_vram.bin"), "rb").read()
        c = open(os.path.join(d, f"{stage}_cgram.bin"), "rb").read()
        obsel = open(os.path.join(d, f"{stage}_ppu.bin"), "rb").read()[1]
        cells = []
        for f0f, f1e, anims in kinds:
            order, scripts = {}, []
            for a in anims:
                seq = []
                for ptr, frames in anim(rom, a):
                    if ptr not in order:
                        order[ptr] = len(cells)
                        cells.append(draw(pieces(rom, ptr, f0f, f1e), v, c, obsel, cw, ox))
                    seq.append((order[ptr], frames))
                scripts.append(seq)
            print(f"{sheet}: animations (cell, frames): {scripts}")
        Image.fromarray(np.concatenate(cells, 1)).save(os.path.join(ROOT, "assets", "enemies", sheet + ".png"))
        print(f"{sheet}: {len(cells)} pictures")


if __name__ == "__main__":
    main()
