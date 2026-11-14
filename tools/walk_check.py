#!/usr/bin/env python3
"""Checks a walk capture (tools/mesen/walk_capture.lua) against the pose sheet.

    python tools/walk_check.py build/walk_c2.bin 2 [build/walk_c2.png]
    python tools/walk_check.py build/trap_c2.bin 2 --anim 21

char 0 = Bomberman (bomber_sb6.png), 1-9 = char<n>_sb6.png. Every frame's
bomber is rebuilt from the OAM + VRAM dump exactly as the SNES draws it and
compared with the sheet's poses: prints the pose sequence (e.g. `01-1x41
01-2x8 ...`) and how many frames match no pose (must be 0). With a third
argument, writes a strip of the poses shown in each direction.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb6 import bomber  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "assets", "bombers")
REC = 6 + 544 + 16384    # object bytes, OAM, OBJ VRAM $6000-$7FFF
PLAYER_PAL = 1           # OBJ palette of player 1's bomber (enemies and bombs use others)


def crop(a):
    ys, xs = np.nonzero(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else a[:0, :0]


def tile(d, i):
    t = np.zeros((8, 8), np.uint8)
    b = d[32 * i:32 * i + 32]
    for y in range(8):
        for x in range(8):
            s = 7 - x
            t[y, x] = (b[2*y] >> s & 1) | (b[2*y+1] >> s & 1) << 1 | (b[16+2*y] >> s & 1) << 2 | (b[17+2*y] >> s & 1) << 3
    return t


def poses(char):
    rom = open(os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"), "rb").read()
    sc = bomber.load_scripts(os.path.join(DIR, "bomber_anims.txt"))
    br0 = bomber.BomberRom(rom, sc, 0)
    c0, pals, n0 = bomber.read_sheet_recolor(br0, os.path.join(DIR, "bomber_sb6.png"),
                                             os.path.join(DIR, "BombermanPallete.png"))
    br, cells = br0, c0
    if char:
        own_f = os.path.join(DIR, f"char{char}_anims.txt")
        own = bomber.load_scripts(own_f, br0.cols) if os.path.exists(own_f) else {}
        br = bomber.BomberRom(rom, {**sc, **own}, 0)
        cells, _, _ = bomber.read_sheet_like(br, os.path.join(DIR, f"char{char}_sb6.png"),
                                             os.path.join(DIR, "bomber_sb6.png"), br0, c0, n0["cmap"], n0["sb5"])
    ref = {}
    for a, maps in br.poses():
        for k, m in enumerate(maps):
            ref[(a, k + 1)] = crop(cells[(a, m)])
    return ref, pals


def shown(rec):
    oam, vr = rec[6:550], rec[550:]
    canvas = np.zeros((512, 512), np.uint8)
    placed = 0
    for s in reversed(range(128)):
        x, y, t, at = oam[4*s:4*s+4]
        hb = oam[512 + s // 4] >> (2 * (s % 4)) & 3
        tn = t | (at & 1) << 8
        if (at >> 1 & 7) != PLAYER_PAL or y >= 0xE0:
            continue
        x = x - 256 if hb & 1 else x
        sz = 16 if hb >> 1 else 8
        img = np.zeros((sz, sz), np.uint8)
        for ty in range(sz // 8):
            for tx in range(sz // 8):
                img[ty*8:ty*8+8, tx*8:tx*8+8] = tile(vr, tn + tx + 16 * ty)
        if at & 0x40:
            img = img[:, ::-1]
        if at & 0x80:
            img = img[::-1]
        X, Y = x + 128, (y + 1) % 256 + 128
        reg = canvas[Y:Y+sz, X:X+sz]
        reg[img != 0] = img[img != 0]
        placed += 1
    return crop(canvas), placed


def main():
    args = sys.argv[1:]
    prefer = (1, 2, 3, 4)
    if "--anim" in args:
        i = args.index("--anim")
        prefer = (int(args[i + 1], 16),)
        del args[i:i + 2]
    sys.argv[1:] = args
    data = open(sys.argv[1], "rb").read()
    char = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ref, pals = poses(char)
    seq, imgs, bad = [], [], 0
    for f in range(len(data) // REC):
        img, placed = shown(data[f*REC:(f+1)*REC])
        hit = [k for k, v in ref.items() if v.shape == img.shape and (v == img).all()]
        walk = [k for k in hit if k[0] in prefer] or hit
        lab = ("%02X-%d" % walk[0]) if walk else ("NONE" if placed else "-")
        bad += bool(placed and not walk)
        seq.append(lab)
        imgs.append(img)
    runs, cur, run = [], None, 0
    for lab in seq:
        if lab != cur:
            if cur is not None:
                runs.append(f"{cur}x{run}")
            cur, run = lab, 0
        run += 1
    runs.append(f"{cur}x{run}")
    print(" ".join(runs))
    print("frames:", len(seq), "no matching pose:", bad)
    if len(sys.argv) > 3:
        from PIL import Image
        pal = [(0, 0, 0, 0)] + [tuple(int(c) for c in col) + (255,) for col in pals[0][:15]]
        W = 160
        im = Image.new("RGBA", (8 * W, 4 * W), (40, 44, 56, 255))
        for r, d in enumerate((1, 2, 3, 4)):
            frames, last = [], None
            for lab, img in zip(seq, imgs):
                if lab.startswith("%02X-" % d) and lab != last:
                    frames.append(img)
                last = lab
            for c, img in enumerate(frames[2:10]):
                a = np.zeros(img.shape + (4,), np.uint8)
                for i, col in enumerate(pal):
                    a[img == i] = col
                t = Image.fromarray(a, "RGBA").resize((img.shape[1] * 4, img.shape[0] * 4), Image.NEAREST)
                im.alpha_composite(t, (c * W + (W - t.width) // 2, r * W + (W - t.height) // 2))
        im.save(sys.argv[3])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
