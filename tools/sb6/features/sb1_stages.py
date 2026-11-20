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

# stage name: SB5 stage, theme, map, set 4 archive / palette (gfx; or arc / pal written from the stage's own
# src_arc / src_pal); new_theme: the theme's tables are new ones in bank $D0 (a freed theme id); script: the
# stage's type 02 script bytes rewritten to name them
STAGES = {
    # soft_anim: the soft block's pictures (16 x 16 each, the first = _soft.png) shown anim_hold frames each,
    # in a loop (SB1 4-4's bumpers: 5 pictures, 3 frames; from SB1's VRAM, tiles 2/3/$12/$13)
    "sb1_4-4": dict(stage=0x10, theme=2, map=4, gfx=2, soft_anim="sb1_4-4_soft_anim", anim_hold=3),
    "sb1_6-4": dict(stage=0x17, theme=5, map=0x0B, gfx=5),
    # 1-7 (SB5 boss arena $68: theme $27, archive $1F and palette $1B shared with the other arenas, map $8F its
    # own) gets SB1's 4-8 arena in theme 4 (free: its room serves theme 5 above), set 4 archive / palette 4
    # 1-6 = the SB6 Unity scene's tournament arena (tools/unity_arena_assets.py): stands with the crowd, and
    # the empty stands as the alternate picture (asm/world1.asm blinks them); ids past SB5's (theme $28 is
    # named by no script; archive / palette $F0 through arc_entry / pal_lookup); stages $67/$69/$6B
    # (white, black, golden bomber) all draw map $8E
    "sb6_1-6": dict(stage=0x67, theme=0x28, map=0x8E, arc=0xF0, pal=0xF0, src_arc=0x1F, src_pal=0x1B,
                    new_theme=True, ext=True, rows=(3, 11), alt="sb6_1-6_empty",
                    scripts=[(0xC71BB1, "2A 1B 27 1F 0B 27 0C 8E", "2A F0 27 F0 0B 28 0C 8E"),
                             (0xC71F3B, "2A 1C 27 1F 0B 27 0C 90", "2A F0 27 F0 0B 28 0C 8E"),
                             (0xC72178, "2A 1B 27 1F 0B 27 0C 92", "2A F0 27 F0 0B 28 0C 8E")]),
    "sb1_4-8": dict(anim="sb1_4-8_shock", anim_hold=2, stage=0x68, theme=4, map=0x8F, arc=4, pal=4, src_arc=0x1F, src_pal=0x1B, new_theme=True,
                    script=(0xC71D8F, "2A 1B 27 1F 0B 27 0C 8F", "2A 04 27 04 0B 04 0C 8F")),
}
SPARE_THEMES = (4,)            # theme 4 (SB5 stages $13 / $14, not played): its tables can hold a bigger theme
SOFT_ID = 2
PALS = (4, 5, 6)                # SB1 colors
BURN_PAL = 3
FLAME_FLOOR = range(5, 11)      # palette 2 entries of the floor around SB5's flames (tiles $050-$07B)
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


def _rgb555(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    return (a[..., 0].astype(np.int32) >> 3) | (a[..., 1].astype(np.int32) >> 3) << 5 | \
        (a[..., 2].astype(np.int32) >> 3) << 10


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
    th, mp = spec["theme"], spec["map"]
    gfx = spec.get("arc", spec.get("gfx"))
    pal_id = spec.get("pal", gfx)
    src_arc, src_pal = spec.get("src_arc", gfx), spec.get("src_pal", pal_id)
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

    top, bottom = spec.get("rows", (1, 11))
    alt = _cells(spec["alt"])[0] if "alt" in spec else None
    blink = []                      # (column, row, metatile id, id in the alternate picture)

    anim = _cells(spec["anim"])[0] if "anim" in spec else None
    second = {}                     # metatile id -> its cells in the animation's other frames

    def meta(cell, col, cell1=None):
        key = (cell.tobytes(), col, None if cell1 is None else cell1.tobytes())
        if key not in ids:
            ids[key] = new_id()
            cells.append((ids[key], cell, col))
            if cell1 is not None:
                second[ids[key]] = [cell1]
        return ids[key]

    floors = {}
    for r in range(13):
        for c in range(16):
            cell = field[r * 16:r * 16 + 16, (c + 1) * 16:(c + 1) * 16 + 16]
            inner = 1 <= c <= 13 and top <= r <= bottom
            hard = inner and c % 2 == 0 and r % 2 == 0
            col = 0x00 if inner and not hard else 0x80
            if col == 0:
                for v in cell.reshape(-1).tolist():
                    floors[v] = floors.get(v, 0) + 1
            cell1 = None
            if anim is not None:
                cell1 = anim[r * 16:r * 16 + 16, (c + 1) * 16:(c + 1) * 16 + 16]
                if (cell1 == cell).all():
                    cell1 = None
            grid[r, c] = meta(cell, col, cell1)
            if alt is not None:
                other = alt[r * 16:r * 16 + 16, (c + 1) * 16:(c + 1) * 16 + 16]
                if (other != cell).any():
                    blink.append((c, r, int(grid[r, c]), meta(other, col)))
    cells.append((SOFT_ID, soft, 0x30))
    if "soft_anim" in spec:
        if anim is not None:
            raise BuildError(f"{name}: one animation per stage")
        strip = _rgb555(os.path.join(ASSETS, spec["soft_anim"] + ".png"))
        if strip.shape[0] != 16 or strip.shape[1] % 16 or not (strip[:, :16] == soft).all():
            raise BuildError(f"{name}: {spec['soft_anim']}.png must be 16 x 16 pictures, the first = the soft block")
        second[SOFT_ID] = [strip[:, x:x + 16] for x in range(16, strip.shape[1], 16)]
    floor = max(floors, key=floors.get)
    count = max(i for i, _, _ in cells) + 1
    # ---- palettes and tiles ----
    tiles8 = [np.concatenate([t] + [_split(c)[q] for c in second[i]]) if i in second else t for i, cell, _ in cells
              for q, t in enumerate(_split(cell))]
    pals, where = _palettes(tiles8)
    if len(pals) > len(PALS):
        raise BuildError(f"{name}: {len(pals)} palettes needed")
    entry = 0xE30000 + _w(rb, 0xC01C96 + 2 * 4) + 8 * (gfx - 1)
    sentry = 0xE30000 + _w(rb, 0xC01C96 + 2 * 4) + 8 * (src_arc - 1)
    src, size = _p24(rb, sentry + 4), _w(rb, sentry + 2)
    base, _ = lz.decompress(bytes(rb.d[off(src):off(src) + 0x4000]), size)
    n_tiles = N_TILES if "src_arc" not in spec else size // 32      # an arena keeps its archive's size
    base = bytearray(base[:32 * n_tiles]) + bytes(max(0, 32 * n_tiles - len(base)))
    free = [n for n in range(1, n_tiles) if n not in BURN_TILES]
    tiles = _Tiles(base, free)
    table = bytearray(8 * count)
    approx = 0
    pairs, frame1 = {}, {}          # animated tiles: (frame 0, other frames...) -> slot; slot -> the others' tiles

    def flip(t, hf, vf):
        t = t[:, ::-1] if hf else t
        return t[::-1, :] if vf else t

    def add_pair(idx, others):
        for hf in (False, True):
            for vf in (False, True):
                k = tuple(encode_4bpp(flip(x, hf, vf)) for x in [idx] + others)
                if k in pairs:
                    return pairs[k], hf, vf
        if not tiles.free:
            raise BuildError(f"{name}: no free tile slot left for the animation")
        n = tiles.free.pop()        # from the archive's end: one block of slots
        tiles.data[32 * n:32 * n + 32] = encode_4bpp(idx)
        frame1[n] = [encode_4bpp(x) for x in others]
        pairs[tuple(encode_4bpp(x) for x in [idx] + others)] = n
        return n, False, False

    for animated in (False, True):
        for k, (i, cell, _) in enumerate(cells):
            if (i in second) != animated:
                continue
            for q, t in enumerate(_split(cell)):
                p = where[4 * k + q]
                idx, a = _index(t, pals[p])
                approx += a
                if animated:
                    others = []
                    for c in second[i]:
                        x, a = _index(_split(c)[q], pals[p])
                        approx += a
                        others.append(x)
                    n, hf, vf = add_pair(idx, others)
                else:
                    n, hf, vf = tiles.add(idx)
                word = (0x100 + n) | PALS[p] << 10 | (0x4000 if hf else 0) | (0x8000 if vf else 0)
                table[8 * i + 2 * q:8 * i + 2 * q + 2] = struct.pack("<H", word)
    # burning frames (palette 3)
    burn = os.path.join(ASSETS, name + "_burn.png")       # SB1's own pictures (5 of its 6, from its VRAM)
    if os.path.exists(burn):
        strip = _rgb555(burn)
        if strip.shape != (16, 80):
            raise BuildError(f"{name}_burn.png must be 5 pictures of 16 x 16")
        frames = [strip[:, 16 * k:16 * k + 16] for k in range(5)]
    else:
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
    used = n_tiles - 1 - len(BURN_TILES) - len(tiles.free)
    shock = None
    if frame1:                      # every frame of the animated block (VRAM: BG tiles $100+ at word $1000)
        lo, hi = min(frame1), max(frame1)
        if hi - lo + 1 != len(frame1):
            raise BuildError(f"{name}: the animated tiles are not one block")
        f0 = bytes(tiles.data[32 * lo:32 * hi + 32])
        frames_ = [f0]
        for k in range(len(next(iter(frame1.values())))):
            fk = bytearray(f0)
            for n, encs in frame1.items():
                fk[32 * (n - lo):32 * (n - lo) + 32] = encs[k]
            frames_.append(bytes(fk))
        shock = dict(vram=0x1000 + 16 * lo, frames=frames_, tiles=len(frame1))
    # ---- archive ----
    packed = lz.compress(bytes(tiles.data))
    a = rb.alloc([r for r in ("free_cd_stage2", "free_cd_stage45", "free_c9_sheets", "free_c8_sheets", "obj_f9",
                              "obj_f8", "bulk") if r in rb.regions], packed,
                 f"{name}: BG tiles (set 4 archive {gfx:02X}, LZ)")
    ent = bytes(rb.d[off(sentry):off(sentry) + 2]) + struct.pack("<H", len(tiles.data)) + a.to_bytes(3, "little") +         bytes([rb.d[off(sentry) + 7]])
    ext = {}
    if spec.get("ext"):             # an id past SB5's tables: its own entry (asm/world1.asm `arc_entry`)
        ext["arc"] = rb.alloc("e3_tables", ent, f"{name}: set 4 archive {gfx:02X} entry (World 1 ids)")
    else:
        rb.patch(entry, bytes(rb.d[off(entry):off(entry + 8)]), ent, f"{name}: set 4 archive {gfx} -> SB1 tiles")
    # ---- palette (bank $81) ----
    pt = 0x810000 + _w(rb, 0xC00379 + 2 * 4) + 2 * (pal_id - 1)
    old = 0x810000 + _w(rb, 0x810000 + _w(rb, 0xC00379 + 2 * 4) + 2 * (src_pal - 1))
    dest, cnt = _w(rb, old), _w(rb, old + 2)
    colors = [_w(rb, old + 4 + 2 * i) for i in range(cnt)]
    first_row = dest // 16
    def put(row, pal):
        o = (row - first_row) * 16
        colors[o:o + 16] = [colors[o]] + list(pal) + [0] * (15 - len(pal))
    put(BURN_PAL, bpal)
    # the flames (palette 2, SB5's) are drawn over their own floor pixels, colors FLAME_FLOOR: SB5's grass
    # there showed through the explosions; they take the SB1 floor's most common color
    o = (2 - first_row) * 16
    for i in FLAME_FLOOR:
        colors[o + i] = floor
    for p, pal in zip(PALS, pals):
        put(p, pal)
    for row, pal in spec.get("extra_pals", {}).items():    # rows the field leaves free (1-7: the clown's)
        if row in PALS[:len(pals)]:
            raise BuildError(f"{name}: palette {row} is the field's")
        put(row, pal)
    data = struct.pack("<HH", dest, cnt) + b"".join(struct.pack("<H", c) for c in colors)
    regs81 = [r for r in ("free_81_stage45", "free_81_stage2", "bank81") if r in rb.regions]
    if spec.get("ext"):             # pointer word + colors in one bank (pal_lookup in asm/bombers.asm sets it)
        start = rb.regions["bulk"].cursor
        ext["pal"] = rb.alloc("bulk", struct.pack("<H", (start + 2) & 0xFFFF) + data,
                              f"{name}: set 4 palette {pal_id:02X} (pointer word + colors)")
        if ext["pal"] != start:
            raise BuildError(f"{name}: palette moved")
    else:
        pa = rb.alloc(regs81, data, f"{name}: BG palettes (set 4 palette {pal_id:02X})")
        rb.patch(pt, bytes(rb.d[off(pt):off(pt) + 2]), struct.pack("<H", pa & 0xFFFF), f"{name}: set 4 palette {pal_id}")
    # ---- theme tables (bank $D0) ----
    def theme_slot(t):
        a1, a2 = _w(rb, 0xD00000 + 2 * (t - 1)), _w(rb, 0xD00000 + 2 * t)
        c1, c2 = _w(rb, 0xD08000 + 2 * (t - 1)), _w(rb, 0xD08000 + 2 * t)
        return a1, (a2 - a1) // 8, c1, c2 - c1

    a1, cap, c1, ccap = theme_slot(th)
    if spec.get("new_theme"):
        cb = bytearray(count)
        for i, _, cl in cells:
            cb[i] = cl
        cb[0] = 0x80
        ma = rb.alloc(D0_ROOM, bytes(table), f"{name}: theme {th} metatiles ({count})")
        ca = rb.alloc(D0_ROOM, bytes(cb), f"{name}: theme {th} collisions")
        for base_t, val in ((0xD00000, ma), (0xD08000, ca)):
            at = base_t + 2 * (th - 1)
            rb.patch(at, bytes(rb.d[off(at):off(at) + 2]), struct.pack("<H", val & 0xFFFF), f"{name}: theme {th} tables")
        a1, cap, c1, ccap = None, count, None, count
    elif count > min(cap, ccap):
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
    if a1 is not None:
        rb.patch(0xD00000 + a1, bytes(rb.d[off(0xD00000 + a1):off(0xD00000 + a1) + len(table)]), bytes(table),
                 f"{name}: theme {th} metatiles ({count})")
        cbytes = bytearray(count)
        for i, _, cl in cells:
            cbytes[i] = cl
        cbytes[0] = 0x80
        rb.patch(0xD00000 + c1, bytes(rb.d[off(0xD00000 + c1):off(0xD00000 + c1) + count]), bytes(cbytes),
                 f"{name}: theme {th} collisions")
    for at, old_s, new_s in spec.get("scripts", [spec["script"]] if "script" in spec else []):
        rb.patch(at, bytes.fromhex(old_s), bytes.fromhex(new_s), f"{name}: stage field ids ({at:06X})")
    # ---- map ----
    lst = _p24(rb, 0xD0A000 + 3 * (mp - 1))
    m = rb.alloc("bulk", lz.compress(bytes(grid.flatten())), f"{name}: map {mp} (16 x 13 metatiles, LZ)")
    rb.patch(lst, bytes(rb.d[off(lst):off(lst) + 3]), m.to_bytes(3, "little"), f"{name}: map {mp} -> SB1 layout")
    words = {i: [struct.unpack("<H", table[8 * i + 2 * q:8 * i + 2 * q + 2])[0] for q in range(4)]
             for i, _, _ in cells}
    return dict(metatiles=count, tiles=used, palettes=len(pals), approx=approx, bytes=len(packed), ext=ext, anim=shock,
                blink=[(c, r, words[a], words[b]) for c, r, a, b in blink])


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


D0_ROOM = ["free_d0_maps2", "free_d0_maps1", "d0"]    # bank $D0 room for new theme tables


def apply(rb):
    # stages built from SB5's own archive / palette first (those are freed next), then the ones in new tables
    out = {name: build(rb, name, spec) for name, spec in STAGES.items() if not spec.get("new_theme")}
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)
    out.update({name: build(rb, name, spec) for name, spec in STAGES.items() if spec.get("new_theme")})
    out["anim"] = _anim_code(rb, [(spec, out[name]["anim"]) for name, spec in STAGES.items() if out[name]["anim"]])
    return out


ANIM_ASM = os.path.join(ROOT, "asm", "stage_anim.asm")


def _anim_code(rb, anims):
    """asm/stage_anim.asm: per animated stage [stage, frames held, frames, VRAM word, block size, first
    block (long)] in a table; every stage's blocks in one bank (the task copies them with MVN)."""
    if not anims:
        return 0
    from .. import asar
    blob, rows = bytearray(), []
    for spec, a in anims:
        rows.append((spec, a, len(blob)))
        blob += b"".join(a["frames"])
    regs = [r for r in ("free_cd_stage2", "free_cd_stage45", "obj_f9", "obj_f8", "bulk") if r in rb.regions]
    src = rb.alloc(regs, bytes(blob), "World 1: animated BG tiles, every frame of " +
                   ", ".join(f"stage ${spec['stage']:02X} ({len(a['frames'])} x {a['tiles']} tiles)"
                             for spec, a, _ in rows))
    if src >> 16 != (src + len(blob) - 1) >> 16:
        raise BuildError("animated tiles cross a bank")
    table = bytearray()
    for spec, a, o in rows:
        table += bytes([spec["stage"], spec["anim_hold"], len(a["frames"])]) + struct.pack(
            "<HH", a["vram"], len(a["frames"][0])) + (src + o).to_bytes(3, "little")
    table.append(0xFF)
    t = rb.alloc("bulk", bytes(table), "World 1: animated stages (stage, hold, frames, VRAM, size, tiles)")
    region = rb.regions["bulk"]
    defs = {"ORG": f"${region.cursor:06X}", "TABLE": f"${t:06X}", "BANK": f"${src >> 16:02X}"}
    runs, syms = asar.assemble_into(rb.d, ANIM_ASM, defs)
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"stage_anim.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "World 1: animated stage tiles, task (asm/stage_anim.asm)")
    return syms["anim_start"]
