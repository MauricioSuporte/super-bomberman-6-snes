#!/usr/bin/env python3
"""Cuts Super Bomberman (USA) enemies out of Mesen captures into the frame sheets that
tools/sb6/features/sb1_enemies.py builds SB5 enemies from (research tool; the build only reads the PNGs).

    python tools/sb1_enemy_assets.py DIR STAGE NAME=PAL:PIECES[:FRAMES] ...

DIR = files written by tools/mesen/sb1_stages.lua STAGE=<stage> VIDEO=<frames> VIDEOSFX=1 (<STAGE>_vram_<f>.bin,
_cgram_, _oam_, _ppu_). An enemy is PIECES consecutive OAM entries of OBJ palette PAL (SB1 draws each object's
sprites one after the other) with 16x16 pieces; its lowest 16x16 piece is the anchor. Every distinct picture of
the kind, in order of first appearance (or FRAMES = comma-separated indices of that order), goes into
assets/enemies/NAME.png: 32 x 48 cells side by side, anchor at (8, 28), transparent background; the colors are
SB1's BGR15 values << 3.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = [((8, 8), (16, 16)), ((8, 8), (32, 32)), ((8, 8), (64, 64)), ((16, 16), (32, 32)),
         ((16, 16), (64, 64)), ((32, 32), (64, 64)), ((16, 32), (32, 64)), ((16, 32), (32, 32))]
CW, CH, AX, AY = 32, 48, 8, 28


def _tile(v, addr):
    px = np.zeros((8, 8), np.uint8)
    for y in range(8):
        b = [v[(addr + o + 2 * y) & 0xFFFF] for o in (0, 1, 16, 17)]
        for x in range(8):
            s = 7 - x
            px[y, x] = sum(((b[p] >> s) & 1) << p for p in range(4))
    return px


def sprites(oam, v, c, obsel):
    base, gap = (obsel & 7) << 14, ((obsel >> 3) & 3) << 13
    small, large = SIZES[obsel >> 5]
    out = []
    for i in range(128):
        x, y, t, a = oam[4 * i:4 * i + 4]
        hi = oam[512 + i // 4] >> (2 * (i % 4))
        x |= (hi & 1) << 8
        x = x - 512 if x >= 256 else x
        w, h = large if hi & 2 else small
        y = y - 256 if y >= 240 else y
        name, pal = t | (a & 1) << 8, (a >> 1) & 7
        img = np.zeros((h, w, 4), np.uint8)
        for ty in range(h // 8):
            for tx in range(w // 8):
                n = ((name & 0xF0) + ty * 16) & 0xF0 | ((name + tx) & 0x0F)
                px = _tile(v, base + n * 32 + ((gap + 0x2000) if name & 0x100 else 0))
                for yy in range(8):
                    for xx in range(8):
                        k = px[yy, xx]
                        if k:
                            i2 = 128 + pal * 16 + int(k)
                            cw = c[2 * i2] | c[2 * i2 + 1] << 8
                            img[ty * 8 + yy, tx * 8 + xx] = ((cw & 31) << 3, (cw >> 5 & 31) << 3, (cw >> 10 & 31) << 3, 255)
        if a & 0x40:
            img = img[:, ::-1]
        if a & 0x80:
            img = img[::-1]
        out.append((x, y, w, h, img, i, pal))
    return out


def main():
    d, stage = sys.argv[1], int(sys.argv[2], 16)
    kinds = {}
    for spec in sys.argv[3:]:
        name, rest = spec.split("=")
        f = rest.split(":")
        kinds[name] = dict(pal=int(f[0]), n=int(f[1]), pick=[int(x) for x in f[2].split(",")] if len(f) > 2 else None,
                           seen={}, order=[])
    frames = sorted(int(fn.split("_")[-1][:-4]) for fn in os.listdir(d) if fn.startswith(f"{stage:02X}_oam_"))
    for fr in frames:
        rd = lambda k: open(os.path.join(d, f"{stage:02X}_{k}_{fr}.bin"), "rb").read()
        v, c, oam, ppu = rd("vram"), rd("cgram"), rd("oam"), rd("ppu")
        sp = sorted(sprites(oam, v, c, ppu[1]), key=lambda s: s[5])
        for name, k in kinds.items():
            mine = [s for s in sp if s[6] == k["pal"]]
            i = 0
            while i + k["n"] <= len(mine):
                g = mine[i:i + k["n"]]
                bigs = [s for s in g if s[2] == 16 and s[3] == 16]
                if any(s[5] != g[0][5] + j for j, s in enumerate(g)) or not bigs:
                    i += 1
                    continue
                anc = max(bigs, key=lambda s: s[1])
                img = np.zeros((CH, CW, 4), np.uint8)
                for s in sorted(g, key=lambda s: -s[5]):
                    x, y, w, h, im = s[:5]
                    X, Y = x - anc[0] + AX, y - anc[1] + AY
                    for yy in range(h):
                        for xx in range(w):
                            if im[yy, xx, 3] and 0 <= Y + yy < CH and 0 <= X + xx < CW:
                                img[Y + yy, X + xx] = im[yy, xx]
                key = img.tobytes()
                if key not in k["seen"]:
                    k["seen"][key] = img
                    k["order"].append(key)
                i += k["n"]
    os.makedirs(os.path.join(ROOT, "assets", "enemies"), exist_ok=True)
    for name, k in kinds.items():
        pick = k["pick"] if k["pick"] is not None else range(len(k["order"]))
        imgs = [k["seen"][k["order"][i]] for i in pick]
        Image.fromarray(np.concatenate(imgs, 1)).save(os.path.join(ROOT, "assets", "enemies", name + ".png"))
        print(f"{name}: {len(k['order'])} pictures, {len(imgs)} kept")


if __name__ == "__main__":
    main()
