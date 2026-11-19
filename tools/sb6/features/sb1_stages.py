"""World 1 stages drawn like Super Bomberman 1's (1-4 = SB1 4-4, 1-5 = SB1 6-4).

SB5 draws a stage's field on BG2 from (op `0A map theme` of the stage record's type 02 script, $C2:0BED):

  * map: 16 x 13 metatile ids (row 13 = 0), LZ; map m = the first 24-bit pointer of the list that the
    3 bytes at $D0:A000 + 3*(m-1) point to;
  * theme: metatile table (word at $D0:0000 + 2*(t-1), bank $D0: 4 BG2 tilemap words TL TR BL BR per id)
    and collision table (word at $D0:8000 + 2*(t-1): $80 wall, $30 soft block, $00 floor per id). Id 2 is
    the soft block the stage scatters at random; a burnt soft block shows the map's own id again;
  * tiles: set 4 archive n (`27 n`, LZ, BG tiles $100+); burning soft block = tiles $116-$129 in palette 3
    (5 frames of 4 tiles, $126 first), flames are common tiles $050-$07B in palette 2;
  * palette: set 4 palette n (`2A n`, bank $81: CGRAM $20 + 80 colors = BG palettes 2-6; 2 holds the
    flames' colors).

The SB1 pictures (assets/stages/<name>_field.png 17 x 13 cells, _soft.png; tools/sb1_stage_assets.py) become a
new map, metatile/collision table, archive and palette for the theme of the stage (theme 2: SB5 stages $0F /
$10, theme 5: $15-$17; only $10 and $17 are still played): SB5 column c = SB1 column c + 1 (SB1's walls are 2
cells wide, SB5's 1 + an outer column 15). Palettes 4-6 take SB1's colors, palette 3 the burning frames (made
from SB1's soft block), palette 2 stays SB5's (flames).
"""
import os
import struct

import numpy as np
from PIL import Image

from .. import lz
from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp
from .world_map import _fit, _dist

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASSETS = os.path.join(ROOT, "assets", "stages")

# stage name: (SB5 stage, theme, map, set 4 archive / palette)
STAGES = {
    "sb1_4-4": dict(stage=0x10, theme=2, map=4, gfx=2),
    "sb1_6-4": dict(stage=0x17, theme=5, map=0x0B, gfx=5),
}
SPARE_THEMES = (4,)            # theme 4 (SB5 stages $13 / $14, not played): its tables can hold a bigger theme
SOFT_ID = 2
PALS = (4, 5, 6)                # SB1 colors
BURN_PAL = 3
BURN_TILES = range(0x16, 0x2A)  # archive tile indices of the 5 burning frames ($116-$129)
BURN_FIRST = 0x26               # first frame shown; then $22, $1E, $1A, $16
N_TILES = 0xB0                  # archive tiles $100-$1AF (theme 2's size; VRAM up to $3600 is the stage's)


def _w(rb, a):
    return rb.d[off(a)] | rb.d[off(a) + 1] << 8


def _p24(rb, a):
    return _w(rb, a) | rb.d[off(a) + 2] << 16


def _bgr(rgb):
    r, g, b = (int(x) >> 3 for x in rgb)
    return r | g << 5 | b << 10


def _cells(name):
    field = np.asarray(Image.open(os.path.join(ASSETS, name + "_field.png")).convert("RGB"))
    soft = np.asarray(Image.open(os.path.join(ASSETS, name + "_soft.png")).convert("RGB"))
    if field.shape[:2] != (13 * 16, 17 * 16) or soft.shape[:2] != (16, 16):
        raise BuildError(f"{name}: the field must be 17 x 13 cells, the soft block 16 x 16")
    f = (field[..., 0].astype(np.int32) >> 3) | (field[..., 1].astype(np.int32) >> 3) << 5 | \
        (field[..., 2].astype(np.int32) >> 3) << 10
    s = (soft[..., 0].astype(np.int32) >> 3) | (soft[..., 1].astype(np.int32) >> 3) << 5 | \
        (soft[..., 2].astype(np.int32) >> 3) << 10
    return f, s


def _burn_frames(soft):
    """5 frames (first shown first) of the soft block burning: fire colors eat it from the edges."""
    rng = np.random.RandomState(7)
    noise = rng.rand(16, 16)
    yy, xx = np.mgrid[0:16, 0:16]
    edge = np.minimum(np.minimum(xx, 15 - xx), np.minimum(yy, 15 - yy)) / 7.5   # 0 at the edge, 1 inside
    fire = [0x001F, 0x00BF, 0x017F, 0x027F, 0x03FF, 0x0010]       # red .. yellow, dark red (BGR15)
    frames = []
    for k in range(5):
        t = (k + 1) / 6.0
        fr = soft.copy()
        burnt = (noise * 0.5 + (1 - edge) * 0.5) < t * 1.1
        gone = (noise * 0.5 + (1 - edge) * 0.5) < t * 0.75
        fr[burnt] = np.array(fire)[((noise[burnt] * 6).astype(int) + k) % 5]
        fr[gone] = -1
        frames.append(fr)
    return frames


def _palettes(tiles8, cap=15, most=3):
    sets = [set(t[t >= 0].tolist()) for t in tiles8]
    pals, where = _fit(sets, cap=cap, most=most)
    return [sorted(p) for p in pals], where


def _index(t, pal):
    lut = {c: i + 1 for i, c in enumerate(pal)}
    out = np.zeros((8, 8), np.uint8)
    approx = 0
    for y in range(8):
        for x in range(8):
            c = int(t[y, x])
            if c < 0:
                continue
            if c not in lut:
                approx += 1
                c = min(pal, key=lambda d: _dist(c, d))
            out[y, x] = lut[c]
    return out, approx


def _split(cell):
    return [cell[0:8, 0:8], cell[0:8, 8:16], cell[8:16, 0:8], cell[8:16, 8:16]]


class _Tiles:
    """Archive tiles with flip-aware dedup into the free slots."""

    def __init__(self, base, free):
        self.data = bytearray(base)
        self.free = list(free)
        self.known = {}

    def add(self, idx):
        for hf in (False, True):
            for vf in (False, True):
                t = idx[:, ::-1] if hf else idx
                t = t[::-1, :] if vf else t
                k = encode_4bpp(t)
                if k in self.known:
                    return self.known[k], hf, vf
        if not self.free:
            raise BuildError("SB1 stage: no free tile slot left in the archive")
        n = self.free.pop(0)
        enc = encode_4bpp(idx)
        self.data[32 * n:32 * n + 32] = enc
        self.known[enc] = n
        return n, False, False


def build(rb, name, spec):
    field, soft = _cells(name)
    th, mp, gfx = spec["theme"], spec["map"], spec["gfx"]
    # ---- metatiles: SB5 columns 0-15 = SB1 columns 1-16 ----
    ids, cells, coll = {}, [], []
    grid = np.zeros((14, 16), np.uint8)
    next_id = [1]

    def new_id():
        while next_id[0] == SOFT_ID:
            next_id[0] += 1
        i = next_id[0]
        next_id[0] += 1
        return i

    for r in range(13):
        for c in range(16):
            cell = field[r * 16:r * 16 + 16, (c + 1) * 16:(c + 1) * 16 + 16]
            inner = 1 <= c <= 13 and 1 <= r <= 11
            hard = inner and c % 2 == 0 and r % 2 == 0
            col = 0x00 if inner and not hard else 0x80
            key = (cell.tobytes(), col)
            if key not in ids:
                ids[key] = new_id()
                cells.append((ids[key], cell, col))
            grid[r, c] = ids[key]
    cells.append((SOFT_ID, soft, 0x30))
    count = max(i for i, _, _ in cells) + 1
    # ---- palettes and tiles ----
    tiles8 = [t for _, cell, _ in cells for t in _split(cell)]
    pals, where = _palettes(tiles8)
    if len(pals) > len(PALS):
        raise BuildError(f"{name}: {len(pals)} palettes needed")
    entry = 0xE30000 + _w(rb, 0xC01C96 + 2 * 4) + 8 * (gfx - 1)
    src, size = _p24(rb, entry + 4), _w(rb, entry + 2)
    base, _ = lz.decompress(bytes(rb.d[off(src):off(src) + 0x4000]), size)
    base = bytearray(base) + bytes(32 * N_TILES - len(base))
    free = [n for n in range(1, N_TILES) if n not in BURN_TILES]
    tiles = _Tiles(base, free)
    table = bytearray(8 * count)
    approx = 0
    for k, (i, cell, _) in enumerate(cells):
        for q, t in enumerate(_split(cell)):
            p = where[4 * k + q]
            idx, a = _index(t, pals[p])
            approx += a
            n, hf, vf = tiles.add(idx)
            word = (0x100 + n) | PALS[p] << 10 | (0x4000 if hf else 0) | (0x8000 if vf else 0)
            table[8 * i + 2 * q:8 * i + 2 * q + 2] = struct.pack("<H", word)
    # burning frames (palette 3)
    frames = _burn_frames(soft)
    bset = set()
    for fr in frames:
        bset |= set(fr[fr >= 0].tolist())
    bpal = sorted(bset)
    if len(bpal) > 15:
        bpal = _palettes([fr for fr in frames], cap=15, most=1)[0][0]
    for k, fr in enumerate(frames):
        first = BURN_FIRST - 4 * k
        for q, t in enumerate(_split(fr)):
            idx, a = _index(t, bpal)
            tiles.data[32 * (first + q):32 * (first + q) + 32] = encode_4bpp(idx)
    used = N_TILES - 1 - len(BURN_TILES) - len(tiles.free)
    # ---- archive ----
    packed = lz.compress(bytes(tiles.data))
    a = rb.alloc(["bulk", "free_c9_sheets", "free_c8_sheets", "obj_f8", "obj_f9"], packed,
                 f"{name}: BG tiles (set 4 archive {gfx}, LZ)")
    rb.patch(entry + 2, bytes(rb.d[off(entry + 2):off(entry + 7)]),
             struct.pack("<H", len(tiles.data)) + a.to_bytes(3, "little"), f"{name}: set 4 archive {gfx} -> SB1 tiles")
    # ---- palette (bank $81) ----
    pt = 0x810000 + _w(rb, 0xC00379 + 2 * 4) + 2 * (gfx - 1)
    old = 0x810000 + _w(rb, pt)
    dest, cnt = _w(rb, old), _w(rb, old + 2)
    colors = [_w(rb, old + 4 + 2 * i) for i in range(cnt)]
    first_row = dest // 16
    def put(row, pal):
        o = (row - first_row) * 16
        colors[o:o + 16] = [colors[o]] + list(pal) + [0] * (15 - len(pal))
    put(BURN_PAL, bpal)
    for p, pal in zip(PALS, pals):
        put(p, pal)
    data = struct.pack("<HH", dest, cnt) + b"".join(struct.pack("<H", c) for c in colors)
    pa = rb.alloc("bank81", data, f"{name}: BG palettes 2-6 (set 4 palette {gfx})")
    rb.patch(pt, bytes(rb.d[off(pt):off(pt) + 2]), struct.pack("<H", pa & 0xFFFF), f"{name}: set 4 palette {gfx}")
    # ---- theme tables (bank $D0) ----
    def theme_slot(t):
        a1, a2 = _w(rb, 0xD00000 + 2 * (t - 1)), _w(rb, 0xD00000 + 2 * t)
        c1, c2 = _w(rb, 0xD08000 + 2 * (t - 1)), _w(rb, 0xD08000 + 2 * t)
        return a1, (a2 - a1) // 8, c1, c2 - c1

    a1, cap, c1, ccap = theme_slot(th)
    if count > min(cap, ccap):
        s = SPARE_THEMES[0]
        sa, scap, sc, sccap = theme_slot(s)
        if sa + 8 * scap == a1 and sc + sccap == c1:     # the spare's tables just before ours: both
            scap, sccap = scap + cap, sccap + ccap
        a1, cap, c1, ccap = sa, scap, sc, sccap
        if count > min(cap, ccap):
            raise BuildError(f"{name}: {count} metatiles, theme {th} holds {cap}, spare theme {s} {cap}")
        for base_t, val in ((0xD00000, a1), (0xD08000, c1)):
            at = base_t + 2 * (th - 1)
            rb.patch(at, bytes(rb.d[off(at):off(at) + 2]), struct.pack("<H", val),
                     f"{name}: theme {th} tables -> theme {s}'s room")
    rb.patch(0xD00000 + a1, bytes(rb.d[off(0xD00000 + a1):off(0xD00000 + a1) + len(table)]), bytes(table),
             f"{name}: theme {th} metatiles ({count})")
    cbytes = bytearray(count)
    for i, _, cl in cells:
        cbytes[i] = cl
    cbytes[0] = 0x80
    rb.patch(0xD00000 + c1, bytes(rb.d[off(0xD00000 + c1):off(0xD00000 + c1) + count]), bytes(cbytes),
             f"{name}: theme {th} collisions")
    # ---- map ----
    lst = _p24(rb, 0xD0A000 + 3 * (mp - 1))
    m = rb.alloc("bulk", lz.compress(bytes(grid.flatten())), f"{name}: map {mp} (16 x 13 metatiles, LZ)")
    rb.patch(lst, bytes(rb.d[off(lst):off(lst) + 3]), m.to_bytes(3, "little"), f"{name}: map {mp} -> SB1 layout")
    return dict(metatiles=count, tiles=used, palettes=len(pals), approx=approx, bytes=len(packed))


# SB5's ZONE1 stage data nothing reads any more: set 4 archives 2 (themes 2: stages $0F/$10, rebuilt above), 4
# (theme 4: $13/$14, not played) and 5 (theme 5: $15-$17, rebuilt) and their palettes 2, 4, 5 (also named set
# 0 archives $F7/$F9/$FA, set 3 $98/$9A/$9B, set 6 $9B/$9D/$9E, set 8 $D3/$D5/$D6: no script or native load
# names them), maps 2-4 and 6-11 (stages $0E/$0F/$10/$12-$17; map 5 is 1-2's, 1 is 1-1's; each map is named
# only by its list entry at $D0:A29A+). The first byte of the archive and map ranges stays: SB5's LZ
# reader ($C0:1D46) reads one command byte past the stream before it (1-1's / 1-2's data).
OLD_DATA = [
    ("free_cd_stage2", 0xCD0885, 3400, 0x89DCE6C4, "freed SB5 stage tiles (set 4 archive 2, LZ)"),
    ("free_cd_stage45", 0xCD1F39, 4802, 0x00A7340C, "freed SB5 stage tiles (set 4 archives 4, 5, LZ)"),
    ("free_81_stage2", 0xC1ACE8, 164, 0x6070E93D, "freed SB5 stage palette (set 4 palette 2), bank $81"),
    ("free_81_stage45", 0xC1AE10, 264, 0xDDD55F25, "freed SB5 stage palettes (set 4 palettes 4, 5), bank $81"),
    ("free_d0_maps1", 0xD0A550, 167, 0x753E61CC, "freed SB5 stage maps 2-4 (LZ)"),
    ("free_d0_maps2", 0xD0A627, 261, 0x0A052514, "freed SB5 stage maps 6-11 (LZ)"),
]


def apply(rb):
    out = {name: build(rb, name, spec) for name, spec in STAGES.items()}
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)
    return out
