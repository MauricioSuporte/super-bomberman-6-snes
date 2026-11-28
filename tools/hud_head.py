#!/usr/bin/env python3
"""HUD heads of a character that has no Unity portraits (Unity's
`<Name><skin>_Portrait_0.png`): its front stand pose ($47) from its pose sheet,
one picture per color of its palette picture, in the format of
assets/hud/portraits/<Name>/<skin>.png (32x32, the head at the top: the build
takes the 16 rows from the topmost one, 15 columns around it).

    python tools/hud_head.py 8 BigBomber

Only for characters painted with Bomberman's key colors (char<n>_pallete.png
with BombermanPallete.png's column 0). The pictures can be repainted by hand
afterwards; running this again overwrites them.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb6 import bomber  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BDIR = os.path.join(ROOT, "assets", "bombers")
FRONT = 0x47
TOP = 16           # first row of the head in the 32x32 picture (as in Bomberman's)


def heads(char):
    sheet = np.asarray(Image.open(os.path.join(BDIR, f"char{char}_sb6.png")).convert("RGBA"), np.int32)
    pal = np.asarray(Image.open(os.path.join(BDIR, f"char{char}_pallete.png")).convert("RGBA"), np.int32)
    key = {tuple(int(v) for v in pal[r, 0, :3]): r for r in range(pal.shape[0])}
    x, y = bomber.cell_pos(FRONT - 1, 0)
    cell = sheet[y:y + 64, x:x + 64]
    on = cell[..., 3] >= 128
    if (cell[..., :3] == (255, 0, 255)).all(-1).any():
        on &= ~(cell[..., :3] == (255, 0, 255)).all(-1)
    ys, xs = np.nonzero(on)
    x0 = (int(xs.min()) + int(xs.max()) + 1) // 2 - 16
    out = []
    for skin in range(1, pal.shape[1]):
        img = np.zeros((32, 32, 4), np.uint8)
        for yy in range(32):
            for xx in range(32):
                sy, sx = int(ys.min()) + yy - TOP, x0 + xx
                if not (0 <= sy < 64 and 0 <= sx < 64) or not on[sy, sx]:
                    continue
                rgb = tuple(int(v) for v in cell[sy, sx, :3])
                if rgb in key and pal[key[rgb], skin, 3] >= 128:
                    rgb = tuple(int(v) for v in pal[key[rgb], skin, :3])
                img[yy, xx] = (*rgb, 255)
        out.append(img)
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    char, name = int(sys.argv[1]), sys.argv[2]
    d = os.path.join(ROOT, "assets", "hud", "portraits", name)
    os.makedirs(d, exist_ok=True)
    imgs = heads(char)
    for k, img in enumerate(imgs, 1):
        Image.fromarray(img, "RGBA").save(os.path.join(d, f"{k}.png"))
    print(f"wrote {len(imgs)} heads in {d}")


if __name__ == "__main__":
    main()
