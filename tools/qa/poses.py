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
    """-> [(actors {actor: (obj, page, mapping, anim, slot, screen x, screen y)}, oam bytes, vram bytes)]"""
    data = open(path, "rb").read()
    out, o = [], 0
    while o < len(data):
        n = data[o]
        o += 1
        actors = {}
        for i in range(n):
            a, obj, page, mp, anim, slot, xl, xh, yl, yh = data[o + 10 * i:o + 10 * i + 10]
            sx, sy = xl | xh << 8, yl | yh << 8
            actors[a] = (obj, page, mp, anim, slot, sx - 0x10000 if sx & 0x8000 else sx, sy - 0x10000 if sy & 0x8000 else sy)
        o += 10 * n
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


def pieces(oam):
    """-> [(entry, x, y, w, tile, attr)] of the visible OAM entries (x -256..255, y screen line of the top)."""
    out = []
    for s in range(128):
        x, y, t, at = oam[4 * s:4 * s + 4]
        hb = oam[512 + s // 4] >> (2 * (s % 4)) & 3
        if y >= 0xE0 and y + (16 if hb >> 1 else 8) <= 256:
            continue
        out.append((s, x - 256 if hb & 1 else x, (y + 1) % 256 if y < 0xF0 else y - 255, 16 if hb >> 1 else 8, t, at))
    return out


def line_overflow(oam, lines=224):
    """SNES OBJ limits per screen line: <= 32 sprites in range, <= 34 8-pixel slivers. -> [(line, sprites, slivers)]
    of the lines over (the PPU then drops pieces: the 33rd sprite on, or the first sprites' slivers)."""
    ps = pieces(oam)
    bad = []
    for ln in range(lines):
        on = [(x, w) for s, x, y, w, t, at in ps if y <= ln < y + w and -w < x < 256]
        sl = sum(sum(1 for i in range(w // 8) if -8 < x + 8 * i < 256) for x, w in on)
        if len(on) > 32 or sl > 34:
            bad.append((ln, len(on), sl))
    return bad


def louie_image(oam, vr, slot, sx, sy, box=(-24, -40, 40, 24)):
    """The pieces of OBJ palette slot `slot` around screen point (sx, sy) (a Louie's object), drawn: a hashable key."""
    x0, y0, x1, y1 = sx + box[0], sy + box[1], sx + box[2], sy + box[3]
    canvas = np.zeros((y1 - y0 + 32, x1 - x0 + 32), np.uint8)
    n = 0
    for s, x, y, w, t, at in reversed(pieces(oam)):
        if (at >> 1 & 7) != slot or not (x0 <= x < x1 and y0 <= y < y1):
            continue
        tn = t | (at & 1) << 8
        img = np.zeros((w, w), np.uint8)
        for ty in range(w // 8):
            for tx in range(w // 8):
                img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = walk_check.tile(vr, (tn + tx + 16 * ty) & 0x1FF)
        if at & 0x40:
            img = img[:, ::-1]
        if at & 0x80:
            img = img[::-1]
        reg = canvas[y - y0:y - y0 + w, x - x0:x - x0 + w]
        reg[img != 0] = img[img != 0]
        n += 1
    return walk_check.crop(canvas).tobytes() + bytes(walk_check.crop(canvas).shape), n


def mount_shape(oam, vr, slot, sx, sy):
    """The pieces of OBJ palette slot `slot` centred within a Louie's box around its object point (sx, sy) (the
    rider has its own slot): (96 x 96 mask, object point at (40, 56), pieces). Shape only (non-zero pixels): a Louie may wear another Louie's
    colors (at most two Louie colors at once, asm/louies.asm). The other Louies must be >= 3 cells away."""
    c = np.zeros((96, 96), np.uint8)
    n = 0
    for s, x, y, w, t, at in reversed(pieces(oam)):
        if (at >> 1 & 7) != slot:
            continue
        cx, cy = x + w // 2 - sx, y + w // 2 - sy
        if not (-20 <= cx <= 20 and -36 <= cy <= 8):
            continue
        tn = t | (at & 1) << 8
        img = np.zeros((w, w), np.uint8)
        for ty in range(w // 8):
            for tx in range(w // 8):
                img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = walk_check.tile(vr, (tn + tx + 16 * ty) & 0x1FF)
        if at & 0x40:
            img = img[:, ::-1]
        if at & 0x80:
            img = img[::-1]
        X, Y = x - sx + 40, y - sy + 56
        reg = c[Y:Y + w, X:X + w]
        reg[img != 0] = img[img != 0]
        n += 1
    return c != 0, n


def _shape_diff(a, b):
    """Pixels of two mount masks that differ, the best of +-2 pixels of shift (the object point and the OAM may
    be a frame apart)."""
    best = None
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            d = int((np.roll(np.roll(a, dy, 0), dx, 1) ^ b).sum())
            best = d if best is None else min(best, d)
    return best


def mount_glitches(path, actors, k0, k1, base=0):
    """Frames (k = frame - base in [k0, k1)) where a mount shows a picture far (> 1/4 of its pixels) from both the
    frame before and the frame after (a pose lasts >= 2 frames; a torn one, a pose's pieces over another pose's
    tiles, one) and never again in the scenario (a turn's in-between pose shows one frame, at every turn).
    -> (mount frames seen, [(k, actor, mapping, animation)])"""
    by = {}
    prev = {}
    for f, (act, oam, vr) in enumerate(frames(path)):
        k = f - base
        act, prev = prev, act                  # (a dump's OAM was built by the frame before: its objects' state)
        if not k0 - 1 <= k <= k1:
            continue
        for a in actors:
            if a not in act or act[a][0] == 0xFF:
                continue
            obj, page, mp, anim, slot, sx, sy = act[a]
            key, n = mount_shape(oam, vr, slot, sx, sy)
            if n:
                by[(k, a)] = (key, mp, anim)
    def crop_key(m):
        c = walk_check.crop(m.astype(np.uint8))
        return c.tobytes() + bytes(c.shape)
    times = {}
    for (k, a), (key, mp, anim) in by.items():
        times[(a, crop_key(key))] = times.get((a, crop_key(key)), 0) + 1
    bad = []
    seen = 0
    for (k, a), (key, mp, anim) in by.items():
        if not k0 <= k < k1:
            continue
        seen += 1
        lim = max(int(key.sum()) // 4, 24)        # (a pose's own frames differ by a few pixels)
        p, nx = by.get((k - 1, a)), by.get((k + 1, a))
        if p is not None and nx is not None and _shape_diff(p[0], key) > lim and _shape_diff(nx[0], key) > lim \
                and times[(a, crop_key(key))] == 1:         # (a turn's pose shows 1 frame, at every turn)
            bad.append((k, a, mp, anim))
    return seen, sorted(bad)


def mount_mismatch(path, actor, k0, k1, base=0, tol=8):
    """Frames (k = frame - base in [k0, k1)) where a mount's picture differs (> tol pixels, best of +-2 shift) from
    the picture its (mapping, animation) shows most often: a pose must always look the same (a mapping drawing other
    tiles than its own: SB5's Red / Green Louie mappings are type 0's, as the bombs'; features/bombs.py). A pose's
    first 2 frames and the 3 frames after an animation change (its strip may still be on its way) are left out.
    -> (frames seen, [(k, mapping, animation, pixels)])"""
    seen, by = 0, {}
    prev, last, anim_at, map_at = {}, None, -99, -99
    for f, (act, oam, vr) in enumerate(frames(path)):
        k = f - base
        act, prev = prev, act
        if actor not in act or act[actor][0] == 0xFF:
            continue
        obj, page, mp, anim, slot, sx, sy = act[actor]
        if last is not None and anim != last[1]:
            anim_at = k
        if (mp, anim) != last:
            map_at = k
        last = (mp, anim)
        if not k0 <= k < k1 or k - map_at <= 1 or k - anim_at <= 2:     # (the OAM may show the pose before 2 frames)
            continue
        m, n = mount_shape(oam, vr, slot, sx, sy)
        if not n:
            continue
        seen += 1
        by.setdefault((mp, anim), []).append((k, m))
    bad = []
    for (mp, anim), fs in by.items():
        best = max(fs, key=lambda a: sum(_shape_diff(a[1], b[1]) <= tol for b in fs))[1]
        bad += [(k, mp, anim, d) for k, m in fs for d in [_shape_diff(best, m)] if d > tol]
    return seen, sorted(bad)
