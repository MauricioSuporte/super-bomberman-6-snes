#!/usr/bin/env python3
"""Draws Super Bomberman (USA) 2-8's clown mask (World 1's 1-7 boss) straight from SB1's own frame tables into
the pictures tools/sb6/features/sb1_enemies.py builds the boss from (research tool; the build reads the PNGs).

    python tools/sb1_clown_frames.py SB1_ROM DIR

DIR = a Mesen dump of SB1 in 2-8 (tools/mesen/sb1_stages.lua STAGE=0F VIDEO=1950: 0F_vram.bin, 0F_cgram.bin,
0F_ppu.bin). The boss object ($1000 in SB1, routine $C7:3CDA) draws its frames with obj $0E = $30, $0F = 4,
$1E = 8 (OBJ palettes 4-6; the white silhouettes use 7). docs/ROM_MAP.md "SB1 2-8's clown".

Writes assets/enemies/sb1_2-8_clown_frames.png: row 0 = the FRAMES pictures (W x H each, the boss's
obj x, y at picture pixel (OX, OY), its center (x, y - 32) at (OX, OY - 32)), row 1 = the same in SB1's red
flash palette (the one the boss loads into OBJ palettes 4-6 every other 2 frames after a hit), and
assets/enemies/sb1_2-8_fx.png: 16 x 16 cells, its shot's 4 pictures ($C7:3A3B-$3A4D, OBJ palette 0) and the
top left quarter of the 5 pictures of the explosions its death scatters ($C6:31D7 -> animation $C6:2F23: 32 x 32,
one 16 x 16 tile mirrored into the 4 quarters, OBJ palette 6, obj $0F = $0E).
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb1_enemy_assets import SIZES, _tile  # noqa: E402
from sb1_enemy_frames import pieces  # noqa: E402

# picture order = the asm's picture ids (asm/sb1_enemies.asm clown): N, O (mouth open), I (intro glint),
# D / E / F (mouth opening, crying), G (dead), the white silhouettes of N, D, E, G, then the 12 sinking frames
FRAMES = [0x2B58, 0x3452, 0x2C0D, 0x2D7D, 0x2E32, 0x2EFB, 0x2FC4, 0x308D, 0x3142, 0x31F7, 0x3389,
          0x3507, 0x35BC, 0x3685, 0x3726, 0x37E5, 0x385E, 0x38F5, 0x3946, 0x39A1, 0x39CA, 0x3A07, 0x3A1C]
SHOTS = [0x3A3B, 0x3A41, 0x3A47, 0x3A4D]
BOOMS = [0xC62EBA, 0xC62ECF, 0xC62EE4, 0xC62EF9, 0xC62F0E]
W, H, OX, OY = 128, 120, 72, 104
# SB1's red flash (CGRAM OBJ palettes 4-6 in the frames after a hit, measured in Mesen)
RED = [0x7C1F, 0x007F, 0x0018, 0x001F, 0x000C, 0x0013, 0x001A, 0x0119, 0x0011, 0x0017, 0x0011, 0x0012, 0x000C,
       0x053F, 0x0011, 0x01DF]


def draw(rom, ptr, v, c, obsel, w, h, ox, oy, red, f1e=0x08, f0f=0x04):
    base, gap = (obsel & 7) << 14, ((obsel >> 3) & 3) << 13
    small, large = SIZES[obsel >> 5]
    img = np.zeros((h, w, 4), np.uint8)
    for dx, dy, name, attr, big in reversed(pieces(rom, ptr if ptr > 0xFFFF else 0xC70000 | ptr, f0f, f1e)):
        pw, ph = large if big else small
        pal = (attr >> 1) & 7
        t = np.zeros((ph, pw, 4), np.uint8)
        for ty in range(ph // 8):
            for tx in range(pw // 8):
                n = ((name & 0xF0) + ty * 16) & 0xF0 | ((name + tx) & 0x0F)
                px = _tile(v, base + n * 32 + ((gap + 0x2000) if name & 0x100 else 0))
                for yy in range(8):
                    for xx in range(8):
                        k = int(px[yy, xx])
                        if k:
                            col = RED[k] if red and pal in (4, 5, 6) else c[2 * (128 + pal * 16 + k)] | c[2 * (128 + pal * 16 + k) + 1] << 8
                            t[ty * 8 + yy, tx * 8 + xx] = ((col & 31) << 3, (col >> 5 & 31) << 3, (col >> 10 & 31) << 3, 255)
        if attr & 0x40:
            t = t[:, ::-1]
        if attr & 0x80:
            t = t[::-1]
        x, y = ox + dx - 8, oy + dy
        if x < 0 or y < 0 or x + pw > w or y + ph > h:
            raise SystemExit(f"${ptr:04X}: piece ({dx}, {dy}) outside the {w} x {h} picture")
        m = t[..., 3] > 0
        img[y:y + ph, x:x + pw][m] = t[m]
    return img


def main():
    rom = open(sys.argv[1], "rb").read()
    d = sys.argv[2]
    v = open(os.path.join(d, "0F_vram.bin"), "rb").read()
    c = open(os.path.join(d, "0F_cgram.bin"), "rb").read()
    obsel = open(os.path.join(d, "0F_ppu.bin"), "rb").read()[1]
    rows = [np.concatenate([draw(rom, p, v, c, obsel, W, H, OX, OY, red) for p in FRAMES], 1) for red in (False, True)]
    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(ROOT, "assets", "enemies", "sb1_2-8_clown_frames.png"))
    # a shot is one 16x16 piece at (dx, dy) = (-8, -8): obj (16, 8) puts it at (0, 0) (drawn 8 px left of its obj x)
    # (the shots' objects have $1E = 0: OBJ palette 0, Bomberman's white and blue; they do not flash)
    cells = [draw(rom, p, v, c, obsel, 16, 16, 16, 8, False, 0) for p in SHOTS]
    for p in BOOMS:
        b = draw(rom, p, v, c, obsel, 32, 32, 24, 16, False, 0x06, 0x0E)
        q = b[:16, :16]
        if not (np.array_equal(b[:16, 16:], q[:, ::-1]) and np.array_equal(b[16:, :16], q[::-1])
                and np.array_equal(b[16:, 16:], q[::-1, ::-1])):
            raise SystemExit(f"explosion ${p:06X}: its quarters are not mirrors of the top left one")
        cells.append(q)
    Image.fromarray(np.concatenate(cells, 1)).save(os.path.join(ROOT, "assets", "enemies", "sb1_2-8_fx.png"))
    print(f"{len(FRAMES)} pictures, {len(SHOTS)} shot and {len(BOOMS)} explosion pictures")


if __name__ == "__main__":
    main()
