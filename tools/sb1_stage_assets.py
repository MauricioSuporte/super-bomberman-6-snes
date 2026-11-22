#!/usr/bin/env python3
"""Turns a Mesen capture of a Super Bomberman (USA) stage into the pictures tools/sb6/features/sb1_stages.py
builds World 1 stages from (research tool; the build only reads the PNGs).

    python tools/sb1_stage_assets.py PREFIX NAME [--raw]

PREFIX = files written by tools/mesen/sb1_stages.lua VIDEO=<frame> (PREFIX_vram.bin, _cgram.bin, _ppu.bin):
SB1 draws a stage on BG1 in 16x16-tile mode, 17 x 13 entries (2-cell walls left and right). Writes
assets/stages/NAME_field.png (272 x 208: the stage without its soft blocks, every inner floor cell drawn as SB1
draws it with no soft block around: under a hard block / the top wall its shadow, else the plain floor) and
NAME_soft.png (16 x 16, the soft block; the floor for an arena without any). Colors are SB1's BGR15 values << 3.
--raw: the map's 17 x 13 entries as they are (World 5's tournament arena, whose stands, stars and corridor the
soft block guess takes for soft blocks), the soft block = the floor of row 3.
"""
import collections
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 17, 13


def load(prefix):
    v = open(prefix + "_vram.bin", "rb").read()
    c = open(prefix + "_cgram.bin", "rb").read()
    p = open(prefix + "_ppu.bin", "rb").read()
    return v, c, p


def cell(v, c, ch, e):
    t0 = e & 0x3FF
    px = np.zeros((16, 16), np.uint8)
    for dy in range(2):
        for dx in range(2):
            a = ch + ((t0 + dx + 16 * dy) & 0x3FF) * 32
            for y in range(8):
                for pl in range(4):
                    b = v[(a + (pl // 2) * 16 + y * 2 + (pl & 1)) & 0xFFFF]
                    for x in range(8):
                        px[dy * 8 + y, dx * 8 + x] |= ((b >> (7 - x)) & 1) << pl
    if e & 0x4000:
        px = px[:, ::-1]
    if e & 0x8000:
        px = px[::-1]
    pal = (e >> 10) & 7
    rgb = np.zeros((16, 16, 3), np.uint8)
    for y in range(16):
        for x in range(16):
            k = px[y, x]
            i = pal * 16 + k if k else 0          # transparent: the backdrop (color 0)
            w = c[2 * i] | c[2 * i + 1] << 8
            rgb[y, x] = ((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3)
    return rgb


def main():
    prefix, name = sys.argv[1], sys.argv[2]
    v, c, p = load(prefix)
    base = (p[0x07] & 0xFC) << 9
    ch = (p[0x0B] & 15) << 13
    g = [[v[base + 2 * (r * 32 + col)] | v[base + 2 * (r * 32 + col) + 1] << 8 for col in range(W)] for r in range(H)]
    if "--raw" in sys.argv[3:]:
        out = np.zeros((H * 16, W * 16, 3), np.uint8)
        for r in range(H):
            for col in range(W):
                out[r * 16:r * 16 + 16, col * 16:col * 16 + 16] = cell(v, c, ch, g[r][col])
        d = os.path.join(ROOT, "assets", "stages")
        Image.fromarray(out).save(os.path.join(d, name + "_field.png"))
        Image.fromarray(cell(v, c, ch, g[3][2])).save(os.path.join(d, name + "_soft.png"))
        print(f"{name}: raw map, floor {g[3][2]:04X}")
        return
    inner = [(col, r) for r in range(1, H - 1) for col in range(2, W - 2)]
    hard = {(col, r) for col, r in inner if col % 2 == 1 and r % 2 == 0}
    hard_e = collections.Counter(g[r][col] for col, r in hard).most_common(1)[0][0]
    # soft blocks: the palette of the most common non-hard entry that is not a floor... found as the entries
    # that never sit under a hard block nor in row 1 and are drawn with another palette than the floor
    under = collections.Counter(g[r][col] for col, r in inner if (col, r - 1) in hard)
    top = collections.Counter(g[1][col] for col in range(2, W - 2))
    rest = collections.Counter(g[r][col] for col, r in inner if (col, r) not in hard and r > 1
                               and (col, r - 1) not in hard)
    floor_pal = (rest.most_common(1)[0][0] >> 10) & 7
    soft = {e for e in set(under) | set(top) | set(rest) if (e >> 10) & 7 != floor_pal and e != hard_e}
    plain = next(e for e, _ in rest.most_common() if e not in soft)
    shadow = next(e for e, _ in under.most_common() if e not in soft)
    topf = next(e for e, _ in top.most_common() if e not in soft)
    row1 = {k: collections.Counter(g[1][col] for col in range(2, W - 2) if col % 2 == k and g[1][col] not in soft)
            .most_common(1)[0][0] for k in (0, 1)}
    on_field = collections.Counter(g[r][col] for col, r in inner if g[r][col] in soft)
    # an arena (no soft block on the field): the floor stands for the soft block (never placed there)
    soft_e = on_field.most_common(1)[0][0] if on_field else plain
    print(f"{name}: hard {hard_e:04X}, soft {sorted('%04X' % e for e in soft)} (picture {soft_e:04X}), "
          f"floor {plain:04X}, under a hard block {shadow:04X}, row 1 {row1[0]:04X}/{row1[1]:04X}")
    out = np.zeros((H * 16, W * 16, 3), np.uint8)
    for r in range(H):
        for col in range(W):
            e = g[r][col]
            if (col, r) in hard:
                e = hard_e
            elif 2 <= col < W - 2 and 1 <= r < H - 1 and on_field:      # an arena is taken as it is
                e = (row1[col % 2] if g[1][col] in soft else g[1][col]) if r == 1                     else shadow if (col, r - 1) in hard else plain
            out[r * 16:r * 16 + 16, col * 16:col * 16 + 16] = cell(v, c, ch, e)
    d = os.path.join(ROOT, "assets", "stages")
    os.makedirs(d, exist_ok=True)
    Image.fromarray(out).save(os.path.join(d, name + "_field.png"))
    Image.fromarray(cell(v, c, ch, soft_e)).save(os.path.join(d, name + "_soft.png"))


if __name__ == "__main__":
    main()
