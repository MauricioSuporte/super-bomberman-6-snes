"""Pose check of the pose dumps written by tools/mesen/qa.lua (scenario.pose): every frame each dumped bomber is
rebuilt from OAM + OBJ VRAM exactly as the SNES draws it (its OBJ palette slot only) and must be one of the poses
of its character's sheet (tools/walk_check.py poses(): bomber_sb6.png / char<n>_sb6.png with the build's colors and
scripts). A frame with pieces that match no pose = a broken animation (wrong tiles, a stale page, a lost DMA).
"""
import functools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import walk_check  # noqa: E402

OAM, VRAM = 544, 16 * 1024


@functools.lru_cache(None)
def ref_poses(char):
    ref, _ = walk_check.poses(char)
    by_shape = {}
    for key, img in ref.items():
        by_shape.setdefault(img.shape, []).append((key, img))
    return by_shape


def frames(path):
    """-> [(actors {actor: (obj, page, mapping, anim, slot)}, oam bytes, vram bytes)]"""
    data = open(path, "rb").read()
    out, o = [], 0
    while o < len(data):
        n = data[o]
        o += 1
        actors = {}
        for i in range(n):
            a, obj, page, mp, anim, slot = data[o + 6 * i:o + 6 * i + 6]
            actors[a] = (obj, page, mp, anim, slot)
        o += 6 * n
        out.append((actors, data[o:o + OAM], data[o + OAM:o + OAM + VRAM]))
        o += OAM + VRAM
    return out


def shown(oam, vr, pal, top=None):
    """-> (cropped image of the pieces in palette slot pal, pieces placed); top = [] gets the screen y of each piece."""
    canvas = np.zeros((512, 512), np.uint8)
    placed = 0
    for s in reversed(range(128)):
        x, y, t, at = oam[4 * s:4 * s + 4]
        hb = oam[512 + s // 4] >> (2 * (s % 4)) & 3
        tn = t | (at & 1) << 8
        if (at >> 1 & 7) != pal or y >= 0xE0:
            continue
        x = x - 256 if hb & 1 else x
        sz = 16 if hb >> 1 else 8
        img = np.zeros((sz, sz), np.uint8)
        for ty in range(sz // 8):
            for tx in range(sz // 8):
                img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = walk_check.tile(vr, (tn + tx + 16 * ty) & 0x1FF)
        if at & 0x40:
            img = img[:, ::-1]
        if at & 0x80:
            img = img[::-1]
        X, Y = x + 128, (y + 1) % 256 + 128
        if top is not None:
            top.append((y + 1) % 256)
        reg = canvas[Y:Y + sz, X:X + sz]
        reg[img != 0] = img[img != 0]
        placed += 1
    return walk_check.crop(canvas), placed


def clipped_top(img, char):
    """A bomber at the top of the screen: SB5 hides the pieces above line 0 (as with one player). What is left
    must be part of one pose: its lowest pixel row on the pose's, 90% of the pixels shown equal to the pose's."""
    h, w = img.shape
    on = img != 0
    for shape, refs in ref_poses(char).items():
        if shape[0] < h or shape[1] < w:
            continue
        for _, v in refs:
            reg = v[shape[0] - h:]
            for dx in range(shape[1] - w + 1):
                if (reg[:, dx:dx + w][on] == img[on]).mean() >= 0.9:    # (a hidden piece may have covered some)
                    return True
    return False


def check(path, chars, skip=2, until=1 << 30):
    """chars = {actor: character}. -> {actor: (frames drawn, frames matching no pose, [(frame, anim)] of the bad)}"""
    res = {a: [0, 0, []] for a in chars}
    for f, (actors, oam, vr) in enumerate(frames(path)):
        if f < skip or f >= until:
            continue
        for a, char in chars.items():
            if a not in actors or actors[a][0] == 0xFF:
                continue
            ys = []
            img, placed = shown(oam, vr, actors[a][4], ys)
            if not placed:
                continue
            res[a][0] += 1
            ok = any((v == img).all() for _, v in ref_poses(char).get(img.shape, []))
            if not ok and min(ys) < 24:              # (a piece above, up to 16 px tall, is off the screen)
                ok = clipped_top(img, char)
            if not ok:
                res[a][1] += 1
                res[a][2].append((f, actors[a][3]))
    return {a: tuple(v) for a, v in res.items()}
