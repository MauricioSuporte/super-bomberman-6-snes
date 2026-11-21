"""Super Bomberman 1 enemies in World 1 (1-2 = SB1 2-1's spring heads, pots and clown faces).

SB5 enemies (docs/ROM_MAP.md "Enemies"): the stage record places them (`A2 x y type`, type 04 script); a type's
16-byte record at $C3:005C + 16*(type-1) (copied to $1D41+ by $C3:0000) holds its set 8 archive (OBJ tiles, LZ,
stored as column pairs: archive tile 2i is VRAM tile i of a 16-tile row, 2i+1 the one under it, 32 per page),
set 8 palette (16 colors), palette slot mask, object type T (7: every enemy) and first animation; a walking
enemy shows animation first + facing - 1 (facing $1632: 1 right, 2 down, 3 left, 4 up). Sprites go through T's
animation scripts and mappings ($C0:171D / $C0:16CC + 3*T).

Here the records of types 02, 03 and 06 (only in SB5 stages no longer played: $0F, $12-$14, $16) become copies
of type 01's (an enemy that just walks) with SB1 2-1's routines (asm/sb1_enemies.asm) and the pictures of
assets/enemies/<sheet>.png (tools/sb1_enemy_assets.py: 32 x 48 cells, anchor = the lowest 16x16 piece at (8, 28);
tools/sb1_enemy_frames.py: 32 x 64, drawn from SB1's tables): their archives and palettes replace those types' own
(set 8 archives / palettes named only by their records), their animations are T 7 ids from $60 and their
mappings T 7 ids from $E0, in new tables (`objmap`) that asm/bombers.asm (`bomber_anim` / `bomber_map`) gives T 7
objects at or above those ids.
"""
import os
import struct

import numpy as np
from PIL import Image

from .. import lz
from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp
from .bombers import _table

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASSETS = os.path.join(ROOT, "assets", "enemies")
ASM = os.path.join(ROOT, "asm", "sb1_enemies.asm")
CHAM_ASM = os.path.join(ROOT, "asm", "chameleon.asm")
RECORDS = 0xC3005C
HIT = 0xC34D41                   # enemy hit (JSL gs_enemy, features/game_sfx.py)
BASE_TYPE = 0x01                 # records copied from type 01's
ANIM_FIRST, MAP_FIRST = 0x60, 0xD6   # (stock T 7: animations 1-$27, mappings 1-$D5)
CW, CH, AX, AY = 32, 48, 8, 28   # sheet cell, anchor (top left of the lowest 16x16 piece)
PIECE_X, PIECE_Y = -8, -9        # where SB5 draws a 16x16 enemy (type 05) relative to the object
# kind: SB5 type slot, sheet, animations right / down / left / up as [(cell, frames), ...]
# SB1 2-1's three enemies (1-2): sheets drawn from SB1's own tables by tools/sb1_enemy_frames.py (32 x 64 cells,
# every frame of every animation), animations = SB1's ($C6:7D1B / $C6:448A / $C6:4AFC: pictures and frames,
# restarted on every turn as SB1's), routines = SB1's ($C6:3947 / $C6:37B0 / $C6:3774, asm/sb1_enemies.asm)
SPRING = [(0, 16), (1, 3), (2, 4), (3, 6), (4, 8), (3, 6), (2, 4), (1, 3)]
CLOWN_FACE = [(0, 21), (1, 7), (2, 7), (3, 7), (2, 7), (1, 7), (0, 21), (4, 10), (5, 12), (4, 10), (0, 21), (6, 13),
              (7, 12)]
SB1_CELL = (32, 64, 8, 28)       # tools/sb1_enemy_frames.py: SB1 piece (dx, dy) -> SB5 piece (dx, dy - 1)
# page 1: a second mapping table, ids from MAP_FIRST again, for the kinds whose animations come after every
# page 0 kind's (asm/bombers.asm enemy_map tells them apart by the object's animation, !ENANIM2)
KINDS = {
    # (start: the record's animation, shown from the enemy's creation: the spring faces down, as SB1's)
    "spring": dict(type=0x02, sheet="sb1_2-1_spring", routine="sb1_spring", cell=SB1_CELL, fit=True, page=1,
                   start=1, anims=[[(c + 5 * d, n) for c, n in SPRING] for d in range(4)]),
    # (pal: kinds that share one OBJ palette, colors merged to 15 (_group_colors): 1-2 with 4 players has stage,
    # 4 bombers, the Louie palette (asm/louies.asm: an egg appears only if a slot is free) and 2 enemy slots)
    "pot": dict(type=0x03, sheet="sb1_2-1_pot", routine="sb1_pot", cell=SB1_CELL, fit=True, page=1, pal="potclown",
                anims=[[(c, 9) for c in range(8)]] * 4),
    "clown": dict(type=0x06, sheet="sb1_2-1_clown", routine="sb1_face", cell=SB1_CELL, fit=True, page=1,
                  pal="potclown", anims=[CLOWN_FACE] * 4),
    # SB1 3-6's chameleon: a frog that becomes a copy of a live player's character (asm/chameleon.asm; its
    # routine goes into the record once the characters' tables are built: chameleon())
    "frog": dict(type=0x05, sheet="sb1_3-6_frog", routine="chameleon",
                 anims=[[(0, 12), (1, 12), (2, 12), (1, 12), (3, 6), (4, 6), (5, 12), (4, 6), (3, 6)]] * 4),
    # SB1 2-8's clown mask (1-7's boss): an enemy with an empty picture whose routine moves the clown, drawn
    # on BG2 from assets/enemies/sb1_2-8_clown.png (asm/sb1_enemies.asm `clown`); type 07 was only in SB5
    # stages $18-$1B (1-3's enemies are SB1's now)
    "clownbody": dict(type=0x07, sheet="sb1_2-8_body", routine="clown", anims=[[(0, 60)]] * 4),
    # SB1 4-4's UFO and bomb robot (1-4, next to SB5's tanks): types $35 / $36, placed by no SB5 stage, which
    # share set 8 archive and palette $31 (so do the two kinds: one sheet, its colors merged to 15)
    "ufo": dict(type=0x35, sheet="sb1_4-4_ufobot", anims=[[(0, 8), (1, 8), (2, 8), (3, 8)]] * 4),
    "robot": dict(type=0x36, sheet="sb1_4-4_ufobot", anims=[[(4, 10), (5, 10)], [(6, 10), (7, 10)],
                                                              [(4, 10), (5, 10)], [(4, 10), (5, 10)]]),
}
ORDER = sorted(KINDS, key=lambda n: KINDS[n].get("page", 0))   # page 0 kinds first (stable)
CLOWN = ("sb1_2-8_clown", "sb1_2-8_clown_closed")   # BG2 pictures, mouth open / closed (112 x 92, same box)
CLOWN_CENTER = (56, 44)          # the body's cell center in the picture
CLOWN_PALS = (3, 6)              # BG palettes of the 1-7 arena it takes (features/sb1_stages.py "sb1_4-8")
# Starts closer than 6 cells to a seat (4 players: lower corners too) are moved to the nearest cell that is not,
# tools/coop4_check.py spawn safety.
# 1-2 (stage $11): 2 of each of SB1 2-1's kinds (SB1 has 4 spring heads; the 2 at (7, 6) and (3, 9) are left out
# so that 4 players keep 50+ fps, tools/coop4_check.py), where SB1 puts them (`A2 x y type` roots,
# world1.chain; SB1 column - 1)
STAGE_ENEMIES = {0x11: [(5, 6, "pot"), (5, 3, "pot"), (1, 8, "clown"), (4, 5, "clown"), (7, 7, "spring"),
                        (11, 7, "spring")],                 # SB1 (13, 9): 2 cells from P4
                 # 1-3 (stage $18): SB1 3-6's 7 chameleons
                 0x18: [(11, 7, "frog"), (9, 5, "frog"), (9, 9, "frog"), (5, 7, "frog"), (3, 7, "frog"),
                        (7, 3, "frog"), (7, 11, "frog")],   # SB1 (13, 8), (1, 8), (11, 11): next to P3/P4
                 # 1-4 (stage $10): SB1 4-4's 4 UFOs and its robot, with SB5's 2 tanks (world1.KEEP_ENEMIES)
                 0x10: [(3, 5, "ufo"), (11, 5, "ufo"), (5, 7, "ufo"), (7, 11, "ufo"), (7, 6, "robot")],
                 # (SB1 (3, 9), (11, 11): next to P3/P4)
                 # 1-7 (stage $68, boss): the clown instead of SB5's rival
                 0x68: [(7, 4, "clownbody")]}


def _w(rb, a):
    return rb.d[off(a)] | rb.d[off(a) + 1] << 8


def _bgr(p):
    return (int(p[0]) >> 3) | (int(p[1]) >> 3) << 5 | (int(p[2]) >> 3) << 10


def _blocks(cell, ox, oy, lut):
    """The cell cut into 8x8 blocks on a grid shifted by (ox, oy): [(x, y, color indices)] of the non-empty ones."""
    h, w = cell.shape[:2]
    pad = np.zeros((h + 16, w + 16, 4), np.uint8)
    pad[8:8 + h, 8:8 + w] = cell
    out = []
    for y in range(oy - 8 if oy else 0, h, 8):
        for x in range(ox - 8 if ox else 0, w, 8):
            blk = pad[y + 8:y + 16, x + 8:x + 16]
            if not blk[..., 3].any():
                continue
            idx = np.zeros((8, 8), np.uint8)
            for yy in range(8):
                for xx in range(8):
                    if blk[yy, xx, 3]:
                        idx[yy, xx] = lut[_bgr(blk[yy, xx])]
            out.append((x, y, idx))
    return out


def _group_colors(group):
    """Colors of every sheet of palette group `group`, merged to 15: the cheapest pair (pixels of the rarer one x
    distance) becomes the more used one until 15 are left. Returns (colors, lut: each sheet color -> 1-15)."""
    count = {}
    for k in KINDS.values():
        if k.get("pal") == group:
            sheet = np.asarray(Image.open(os.path.join(ASSETS, k["sheet"] + ".png")).convert("RGBA"))
            for px in sheet.reshape(-1, 4):
                if px[3]:
                    c = _bgr(px)
                    count[c] = count.get(c, 0) + 1
    rgb = {c: (c & 31, c >> 5 & 31, c >> 10 & 31) for c in count}
    left, into = dict(count), {c: c for c in count}
    while len(left) > 15:
        a, b = min(((a, b) for a in left for b in left if a < b),
                   key=lambda p: min(left[p[0]], left[p[1]]) * sum((x - y) ** 2 for x, y in zip(rgb[p[0]], rgb[p[1]])))
        if left[a] < left[b]:
            a, b = b, a
        left[a] += left.pop(b)
        for c in into:
            if into[c] == b:
                into[c] = a
    colors = sorted(left)
    idx = {c: i + 1 for i, c in enumerate(colors)}
    merged = sorted((c, into[c]) for c in into if into[c] != c)
    if merged:
        print(f"SB1 enemies palette {group}: {len(count)} colors merged to 15 "
              f"({', '.join(f'${a:04X}->${b:04X}' for a, b in merged)})")
    return colors, {c: idx[into[c]] for c in count}


def _cover(cell, lut, known):
    """`fit` kinds: the 8x8 grid offset that needs the fewest new tiles (`known`: tile flips seen so far, updated),
    then on it the 16x16 phase with the fewest pieces, [(x, y, 16x16 or 8x8 indices)]: a 16x16 piece wherever at
    least 2 of its four blocks are drawn (each piece costs SB5's OAM builder $C0:152E the same, and one of 128
    sprites; _kind_big turns the ones that do not fit back into 8x8 pieces)."""
    def flips(idx):
        return [encode_4bpp(idx[::-1 if vf else 1, ::-1 if hf else 1]) for hf in (False, True) for vf in (False, True)]
    best = None
    for oy in range(8):
        for ox in range(8):
            g = _blocks(cell, ox, oy, lut)
            new = {min(flips(i)) for *_, i in g if not any(f in known for f in flips(i))}
            if best is None or (len(new), len(g)) < best[0]:
                best = ((len(new), len(g)), g, ox, oy)
    _, g, ox, oy = best
    for *_, i in g:
        known.update(flips(i))
    blocks = {(x, y): i for x, y, i in g}
    best = None
    for py in (0, 8):
        for px in (0, 8):
            out, used = [], set()
            for (x, y) in sorted(blocks, key=lambda b: (b[1], b[0])):
                if (x, y) in used:
                    continue
                gx = x - ((x - (ox - 8 if ox else 0) - px) % 16)
                gy = y - ((y - (oy - 8 if oy else 0) - py) % 16)
                quad = [(gx, gy), (gx + 8, gy), (gx, gy + 8), (gx + 8, gy + 8)]
                have = [q for q in quad if q in blocks and q not in used]
                if len(have) >= 2:
                    img = np.zeros((16, 16), np.uint8)
                    for qx, qy in have:
                        img[qy - gy:qy - gy + 8, qx - gx:qx - gx + 8] = blocks[(qx, qy)]
                    out.append((gx, gy, img))
                    used.update(have)
                else:
                    out.append((x, y, blocks[(x, y)]))
                    used.add((x, y))
            if best is None or len(out) < len(best):
                best = out
    return best


def _kind_big(name, k, cells, lut, map_id, budget=64):
    """`fit` kinds cut with 16x16 pieces where the 2 OBJ pages allow: every cell is covered (_cover), then the
    16x16 pictures that save the most sprites (pieces saved x frames shown) are kept while all tiles fit in
    `budget` and in the OBJ pages the 8x8 cut takes; the others go back to 8x8 pieces. A 16x16 picture takes 4 archive tiles from a multiple of 4 (top
    left, bottom left, top right, bottom right: the page grid puts them side by side), shared by its flips; 8x8
    pieces share any tile."""
    cw, ch, ax, ay = k["cell"]
    known = set()
    covers = [_cover(cell, lut, known) for cell in cells]
    shown = [0] * len(cells)
    for an in k["anims"]:
        for c, n in an:
            shown[c] += n

    def var(img):
        return [(img[::-1 if vf else 1, ::-1 if hf else 1], hf, vf) for hf in (False, True) for vf in (False, True)]

    def canon(img):
        return min(v.tobytes() for v, *_ in var(img))
    gain = {}
    for i, cv in enumerate(covers):
        for x, y, img in cv:
            if img.shape[0] == 16:
                drawn = sum(bool(img[yy:yy + 8, xx:xx + 8].any()) for yy in (0, 8) for xx in (0, 8))
                gain[canon(img)] = gain.get(canon(img), 0) + (drawn - 1) * shown[i]

    def build(keep):
        tiles, known, known16 = [], {}, {}
        split = []
        for cv in covers:
            out = []
            for x, y, img in cv:
                if img.shape[0] == 16 and canon(img) not in keep:
                    out += [(x + xx, y + yy, img[yy:yy + 8, xx:xx + 8]) for yy in (0, 8) for xx in (0, 8)
                            if img[yy:yy + 8, xx:xx + 8].any()]
                else:
                    out.append((x, y, img))
            split.append(out)
        for cv in split:                              # 16x16 pictures first: each at a multiple of 4
            for x, y, img in cv:
                if img.shape[0] != 16 or any(v.tobytes() in known16 for v, *_ in var(img)):
                    continue
                known16[img.tobytes()] = len(tiles)
                for q in (img[:8, :8], img[8:, :8], img[:8, 8:], img[8:, 8:]):
                    kb = encode_4bpp(q)
                    known.setdefault(kb, len(tiles))
                    tiles.append(kb)
        maps = []
        for cv in split:
            pieces = []
            for x, y, img in cv:
                if img.shape[0] == 16:
                    n, hf, vf = next((known16[v.tobytes()], hf, vf) for v, hf, vf in var(img)
                                     if v.tobytes() in known16)
                    size = 1
                else:
                    hit = next(((known[encode_4bpp(v)], hf, vf) for v, hf, vf in var(img) if encode_4bpp(v) in known),
                               None)
                    if hit is None:
                        kb = encode_4bpp(img)
                        known[kb] = len(tiles)
                        tiles.append(kb)
                        hit = (known[kb], False, False)
                    n, hf, vf = hit
                    size = 0
                vt = n // 32 * 32 + n % 2 * 16 + n % 32 // 2      # archive tile n -> VRAM tile of the page grid
                pieces.append(struct.pack("<hhHB", x - ax + PIECE_X, y - ay + PIECE_Y, vt,
                                          0x20 | size | (0x40 if hf else 0) | (0x80 if vf else 0)))
            if not pieces:
                pieces.append(struct.pack("<hhHB", 0x4000, 0, 0, 0x20))
            maps.append(bytes([len(pieces)]) + b"".join(pieces))
        return tiles, maps
    keep = set()
    tiles, maps = build(keep)
    budget = min(budget, -(-len(tiles) // 32) * 32)   # no more OBJ pages than the 8x8 cut needs
    for c in sorted(gain, key=lambda c: -gain[c]):
        if gain[c] <= 0:
            break
        t2, m2 = build(keep | {c})
        if len(t2) <= budget:
            keep.add(c)
            tiles, maps = t2, m2
    return tiles, maps


def _kind(rb, name, k, map_id):
    cw, ch, ax, ay = k.get("cell", (CW, CH, AX, AY))
    sheet = np.asarray(Image.open(os.path.join(ASSETS, k["sheet"] + ".png")).convert("RGBA"))
    cells = [sheet[:, i * cw:(i + 1) * cw] for i in range(sheet.shape[1] // cw)]
    colors = sorted({_bgr(p) for c in cells for p in c.reshape(-1, 4) if p[3]})
    if len(colors) > 15 and not k.get("pal"):
        raise BuildError(f"SB1 enemy {name}: {len(colors)} colors (15 at most)")
    if not colors:
        colors = [0]
    lut = {c: i + 1 for i, c in enumerate(colors)}
    if k.get("pal"):
        colors, lut = _group_colors(k["pal"])
    if k.get("fit"):
        tiles, maps = _kind_big(name, k, cells, lut, map_id)
        if len(tiles) > 64:
            raise BuildError(f"SB1 enemy {name}: {len(tiles)} tiles (64 at most, 2 OBJ pages)")
        arc = b"".join(tiles) + bytes(32 * (len(tiles) % 2))
        scripts = [b"".join(bytes([map_id + c, n]) for c, n in a) + b"\x00\x00" for a in k["anims"]]
        print(f"SB1 enemy {name}: {len(tiles)} tiles, {sum(m[0] for m in maps)} pieces in {len(maps)} pictures "
              f"({sum(m[1 + 7 * i + 6] & 1 for m in maps for i in range(m[0]))} of them 16x16)")
        return dict(arc=arc, colors=colors, maps=maps, scripts=scripts, tiles=len(tiles))
    tiles, known, maps = [], {}, []

    def flips(idx):
        return [encode_4bpp(idx[::-1 if vf else 1, ::-1 if hf else 1]) for hf in (False, True) for vf in (False, True)]
    for cell in cells:
        pieces = []
        grid = _blocks(cell, 0, 0, lut)
        if k.get("fit"):        # the grid that needs the fewest new tiles (SB1's pieces sit at any height)
            best = None
            for oy in range(8):
                for ox in range(8):
                    g = _blocks(cell, ox, oy, lut)
                    new = {min(flips(i)) for *_, i in g if not any(f in known for f in flips(i))}
                    if best is None or (len(new), len(g)) < best[0]:
                        best = ((len(new), len(g)), g)
            grid = best[1]
        for bx, by, idx in grid:
            hit = None
            for hf in (False, True):
                for vf in (False, True):
                    t = idx[:, ::-1] if hf else idx
                    t = t[::-1] if vf else t
                    kb = encode_4bpp(t)
                    if kb in known and hit is None:
                        hit = (known[kb], hf, vf)
            if hit is None:
                kb = encode_4bpp(idx)
                known[kb] = len(tiles)
                tiles.append(kb)
                hit = (known[kb], False, False)
            n, hf, vf = hit
            vt = n // 32 * 32 + n % 2 * 16 + n % 32 // 2      # archive tile n -> VRAM tile of the page grid
            pieces.append(struct.pack("<hhHB", bx - ax + PIECE_X, by - ay + PIECE_Y, vt,
                                      0x20 | (0x40 if hf else 0) | (0x80 if vf else 0)))
        if not pieces:                  # ($C0:158A loops 256 times on a zero count: one piece far right)
            pieces.append(struct.pack("<hhHB", 0x4000, 0, 0, 0x20))
        maps.append(bytes([len(pieces)]) + b"".join(pieces))
    if not tiles:
        tiles.append(bytes(32))
    if len(tiles) > 64:
        raise BuildError(f"SB1 enemy {name}: {len(tiles)} tiles (64 at most, 2 OBJ pages)")
    arc = b"".join(tiles) + bytes(32 * (len(tiles) % 2))
    scripts = [b"".join(bytes([map_id + c, n]) for c, n in a) + b"\x00\x00" for a in k["anims"]]
    return dict(arc=arc, colors=colors, maps=maps, scripts=scripts, tiles=len(tiles))


# the replaced types' own OBJ tiles (set 8 archives 4, 5 and 8, LZ; each named only by its set 8 entry): the
# first byte of each run stays, SB5's LZ reader reads one byte past the archive before it (3: type 01, 1-1's)
OLD_DATA = [
    ("free_cb_enemies1", 0xCB0462, 2340, 0xA8AC4EF6, "freed SB5 enemy tiles (set 8 archives 4, 5: types 02, 03)"),
    ("free_cb_enemies2", 0xCB12E6, 2017, 0x73FD56C8, "freed SB5 enemy tiles (set 8 archives 7, 8: types 05, 06)"),
]


def clown_bg(rb):
    """The clown's BG2 pictures (mouth open, closed): tiles both use (VRAM tiles $340-$35F), each one's own
    (32 at most, $360-$37F, rewritten when the mouth changes; over 32 the least visible are drawn with
    the closest tile) and its 32 x 32 map (background = tile 0, blank). One bank: shared tiles, closed
    tiles, open tiles, open map, closed map; the two palettes (BG palettes CLOWN_PALS)."""
    from .world_map import _fit, _dist
    pics = []
    for name in CLOWN:
        im = np.asarray(Image.open(os.path.join(ASSETS, name + ".png")).convert("RGBA"))
        h, w = (im.shape[0] + 7) // 8 * 8, (im.shape[1] + 7) // 8 * 8
        pic = np.zeros((h, w, 4), np.uint8)
        pic[:im.shape[0], :im.shape[1]] = im
        pics.append([(tx, ty, pic[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]) for ty in range(h // 8) for tx in range(w // 8)
                     if pic[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8, 3].any()])
    blocks = [blk for pic in pics for blk in pic]
    sets = [{_bgr(p) for p in b.reshape(-1, 4) if p[3]} for _, _, b in blocks]
    pals, where = _fit(sets, cap=15, most=2)
    if len(pals) > 2:
        raise BuildError(f"clown: {len(pals)} palettes")
    pals = [sorted(p) for p in pals]
    # each block -> (palette, 8x8 indices); a tile = its canonical flip
    cells, k = [], 0
    for pic in pics:
        out = []
        for tx, ty, b in pic:
            p = where[k]
            k += 1
            lut = {c: i + 1 for i, c in enumerate(pals[p])}
            idx = np.zeros((8, 8), np.uint8)
            for y in range(8):
                for x in range(8):
                    if b[y, x, 3]:
                        c = _bgr(b[y, x])
                        idx[y, x] = lut.get(c) or lut[min(pals[p], key=lambda d: _dist(c, d))]
            out.append((tx, ty, p, idx))
        cells.append(out)

    def flips(idx):
        return [(idx[::-1 if vf else 1, ::-1 if hf else 1], hf, vf) for hf in (False, True) for vf in (False, True)]

    def canon(idx):
        return min(encode_4bpp(t) for t, _, _ in flips(idx))
    own = [{canon(i) for *_, i in pic} for pic in cells]
    shared = sorted(own[0] & own[1])
    if len(shared) > 32:
        raise BuildError(f"clown: {len(shared)} shared tiles (32 at most)")
    groups, mapping = [], [{}, {}]                      # per picture: canonical tile -> slot
    for n, pic in enumerate(cells):
        mine = sorted(own[n] - set(shared))
        while len(mine) > 32:                           # the tile with the fewest opaque pixels goes to the closest
            dec = {e: np.array([[(e[(y & 7) * 2 + (pl & 1) + (pl >> 1) * 16] >> (7 - x)) & 1 for x in range(8)]
                                for y in range(8) for pl in range(4)]) for e in mine + shared}

            def px(e):
                d = dec[e].reshape(8, 4, 8)
                return sum(d[:, pl] << pl for pl in range(4))
            worst = min(mine, key=lambda e: (px(e) > 0).sum())
            near = min((e for e in mine + shared if e != worst), key=lambda e: (px(e) != px(worst)).sum())
            mapping[n][worst] = near
            mine.remove(worst)
        groups.append(mine)
    slot = {}
    for i, e in enumerate(shared):
        slot[e] = 0x340 + i
    tiledata = [b"".join(shared) + bytes(32 * (32 - len(shared)))]
    maps = []
    for n, pic in enumerate(cells):
        mine = groups[n]
        local = dict(slot)
        for i, e in enumerate(mine):
            local[e] = 0x360 + i
        for e, near in mapping[n].items():
            local[e] = local[near]
        tiledata.append(b"".join(mine) + bytes(32 * (32 - len(mine))))
        words = [0x0000] * 1024
        for tx, ty, p, idx in pic:
            e = canon(idx)
            src = mapping[n].get(e, e)
            # the flip that turns the stored (canonical) tile into this block
            hf, vf = next((hf, vf) for t, hf, vf in flips(idx) if encode_4bpp(t) == src) if src == e else (False, False)
            words[ty * 32 + tx] = local[e] | CLOWN_PALS[p] << 10 | 0x2000 | (0x4000 if hf else 0) | (0x8000 if vf else 0)
        maps.append(b"".join(struct.pack("<H", x) for x in words))
    # one bank: shared, closed's own, open's own, open map, closed map
    data = tiledata[0] + tiledata[2] + tiledata[1] + maps[0] + maps[1]
    regs = [r for r in ("free_cb_enemies1", "free_cb_enemies2", "obj_f9", "obj_f8", "bulk") if r in rb.regions]
    a = rb.alloc(regs, data, f"SB1 clown (1-7's boss): BG2 tiles ({len(shared)} + {len(groups[0])} / "
                             f"{len(groups[1])}) and 2 maps")
    if a >> 16 != (a + len(data) - 1) >> 16:
        raise BuildError("clown: BG2 data crosses a bank")
    return dict(tiles=a, closed=a + 0x400, open=a + 0x800, map=a + 0xC00, pals=pals,
                ntiles=len(shared) + max(len(g) for g in groups), merged=sum(len(m) for m in mapping))


def code(rb, bg):
    from .. import asar
    region = rb.regions["bulk"]
    anims, aid = {}, ANIM_FIRST                          # each kind's first animation (apply() hands them out in order)
    for name in ORDER:
        k = KINDS[name]
        anims[name] = aid
        aid += len(k["anims"])
    runs, syms = asar.assemble_into(rb.d, ASM, {"ORG": f"${region.cursor:06X}",
                                                "ASPRING": f"${anims['spring']:02X}", "APOT": f"${anims['pot']:02X}",
                                                "AFACE": f"${anims['clown']:02X}",
                                                "CLOWN_TYPE": f"${KINDS['clownbody']['type']:02X}",
                                                "CTILES": f"${bg['tiles']:06X}", "COPEN": f"${bg['open']:06X}",
                                                "CCLOSED": f"${bg['closed']:06X}",
                                                "CMAP": f"${bg['map']:06X}", "CBANK": f"${bg['tiles'] >> 16:02X}",
                                                "COX": str(CLOWN_CENTER[0]), "COY": str(CLOWN_CENTER[1]),
                                                "CSTAGE": "$68"})
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"sb1_enemies.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "SB1 enemies: clown routines (asm/sb1_enemies.asm)")
    return syms


def apply(rb):
    """Archives, palettes, records, tables; returns the asm defines for asm/bombers.asm."""
    for name, start, size, crc, purpose in OLD_DATA:      # (the new archives go there first)
        rb.free_old(name, start, size, crc, purpose)
    bg = clown_bg(rb)
    syms = code(rb, bg)
    arc_tab = 0xE30000 + _w(rb, 0xC01C96 + 2 * 8)
    pal_tab = 0x810000 + _w(rb, 0xC00379 + 2 * 8)
    base_rec = bytes(rb.d[off(RECORDS + 16 * (BASE_TYPE - 1)):off(RECORDS + 16 * (BASE_TYPE - 1)) + 15])
    pages, all_scripts, info = ([], []), [], {}
    sheets = {}                                          # sheet -> (its first mapping, archive, palette)
    groups = {}                                          # palette group -> set 8 palette of its first kind
    anim2 = None
    for name in ORDER:
        k = KINDS[name]
        all_maps = pages[k.get("page", 0)]
        if k.get("page", 0) and anim2 is None:
            anim2 = ANIM_FIRST + len(all_scripts)
        rec = RECORDS + 16 * (k["type"] - 1)
        old = bytes(rb.d[off(rec):off(rec) + 15])
        arc_id, pal_id = old[0], old[1]
        if k["sheet"] in sheets:                         # a second kind on the same sheet: its maps, archive, palette
            first, a0, p0 = sheets[k["sheet"]]
            if (a0, p0) != (arc_id, pal_id):
                raise BuildError(f"SB1 enemy {name}: shares {k['sheet']} but not its archive / palette")
            built = _kind(rb, name, k, first)
            anim = ANIM_FIRST + len(all_scripts)
            new = bytes([arc_id, pal_id]) + base_rec[2:4] + bytes([anim]) + base_rec[5:]
            rb.patch(rec, old, new, f"SB1 enemy {name}: type ${k['type']:02X} record (type 01's walk, {k['sheet']})")
            all_scripts += built["scripts"]
            info[name] = dict(type=k["type"], tiles=built["tiles"], frames=0, colors=len(built["colors"]))
            continue
        sheets[k["sheet"]] = (MAP_FIRST + len(all_maps), arc_id, pal_id)
        built = _kind(rb, name, k, MAP_FIRST + len(all_maps))
        own_pal = k.get("pal") not in groups
        if k.get("pal"):
            pal_id = groups.setdefault(k["pal"], pal_id)
        # archive (set 8): same VRAM / flags, new size and source
        e = arc_tab + 8 * (arc_id - 1)
        a = rb.alloc([n for n, *_ in OLD_DATA] + ["bulk"], lz.compress(built["arc"]),
                     f"SB1 enemy {name}: OBJ tiles (set 8 archive {arc_id}, LZ)")
        rb.patch(e + 2, bytes(rb.d[off(e + 2):off(e + 7)]), struct.pack("<H", len(built["arc"])) + a.to_bytes(3, "little"),
                 f"SB1 enemy {name}: set 8 archive {arc_id}")
        # palette (set 8, bank $81): [dest, 16, colors]
        pt = pal_tab + 2 * (pal_id - 1)
        stock = 0x810000 + _w(rb, pt)
        cols = [_w(rb, stock + 4)] + built["colors"] + [0] * (15 - len(built["colors"]))
        data = struct.pack("<HH", _w(rb, stock), 16) + b"".join(struct.pack("<H", c) for c in cols)
        if _w(rb, stock + 2) != 16:
            raise BuildError(f"SB1 enemy {name}: set 8 palette {pal_id} is not a 16-color entry")
        if own_pal:
            rb.patch(stock, bytes(rb.d[off(stock):off(stock) + len(data)]), data,
                     f"SB1 enemy {name}: OBJ palette (set 8 palette {pal_id}, in place)")
        # record: type 01's, with this kind's archive, palette, animations (shown from its creation: `start`)
        anim = ANIM_FIRST + len(all_scripts)
        new = bytes([arc_id, pal_id]) + base_rec[2:4] + bytes([anim + k.get("start", 0)]) + base_rec[5:]
        if k.get("routine") in syms:                         # own actor routine (it runs $C3:4B5A itself)
            r = syms[k["routine"]]
            new = new[:9] + bytes([r & 0xFF, r >> 8 & 0xFF, r >> 16]) + new[12:]
        rb.patch(rec, old, new, f"SB1 enemy {name}: type ${k['type']:02X} record (type 01's walk, own pictures)")
        all_maps += built["maps"]
        all_scripts += built["scripts"]
        info[name] = dict(type=k["type"], tiles=built["tiles"], frames=len(built["maps"]), colors=len(built["colors"]),
                          rec=rec)
    if max(MAP_FIRST + len(m) for m in pages) > 0x100 or ANIM_FIRST + len(all_scripts) > MAP_FIRST:
        raise BuildError("SB1 enemies: too many mappings / animations")
    mt = _table(rb, pages[0], f"SB1 enemies: T 7 mappings from ${MAP_FIRST:02X}")
    mt2 = _table(rb, pages[1], f"SB1 enemies: T 7 mappings from ${MAP_FIRST:02X}, page 1 (animations from ${anim2:02X})")
    at = _table(rb, all_scripts, f"SB1 enemies: T 7 animations from ${ANIM_FIRST:02X}")
    defs = {"ENMAP": f"${mt >> 16:02X}", "ENMAPBASE": f"${(mt - 2 * (MAP_FIRST - 1)) & 0xFFFF:04X}",
            "ENMAPFIRST": f"${MAP_FIRST:02X}", "ENANIM": f"${at >> 16:02X}",
            "ENANIMBASE": f"${(at - 2 * (ANIM_FIRST - 1)) & 0xFFFF:04X}", "ENANIMFIRST": f"${ANIM_FIRST:02X}",
            "ENMAP2": f"${mt2 >> 16:02X}", "ENMAPBASE2": f"${(mt2 - 2 * (MAP_FIRST - 1)) & 0xFFFF:04X}",
            "ENANIM2": f"${anim2:02X}"}
    info["_clown"] = dict(pals=bg["pals"], start=syms["clown_start"], hit=syms["clown_hit"], tiles=bg["ntiles"])
    return defs, info


def stage_enemies(stage):
    """`A2 x y type` scripts of a stage whose enemies are replaced (world1.chain), else None."""
    if stage not in STAGE_ENEMIES:
        return None
    return [bytes([0xA2, x, y, KINDS[k]["type"], 0x00]) for x, y, k in STAGE_ENEMIES[stage]]


# ---------------------------------------------------------------------------
# SB1 3-6's chameleons (1-3): asm/chameleon.asm, built once the characters' tables exist.
CHAM_STAGE = 0x18                # 1-3
NMI_HOOK = 0xC0F41D              # JSL in the NMI after the OAM DMA (bombers' stream_nmi)
HALF_COLS = 8                    # a VRAM half: 8 columns x 2 rows of 8x8 tiles
WALK = range(1, 5)               # walk right, down, left, up = facing 1-4
CHAM_DATA = ["free_c9_sheets", "free_c7_sheets", "free_c8_sheets"]
PIECE = struct.Struct("<hhHB")


def _pose_pixels(tiles, pieces):
    """{(x, y): color index} drawn by pieces [(x, y, tile, attr)]; tiles(tile number) -> 8x8 indices."""
    out = {}
    for x, y, t, a in reversed(pieces):          # (the first piece is on top)
        n = 2 if a & 1 else 1
        for ty in range(n):
            for tx in range(n):
                px = tiles(t + ty * 16 + tx)
                for yy in range(8):
                    for xx in range(8):
                        sx = tx * 8 + xx if not a & 0x40 else (n - 1 - tx) * 8 + 7 - xx
                        sy = ty * 8 + yy if not a & 0x80 else (n - 1 - ty) * 8 + 7 - yy
                        if px[yy][xx]:
                            out[(x + sx, y + sy)] = px[yy][xx]
    return out


def _decode(tile32):
    return [[sum(((tile32[y * 2 + (p & 1) + (p >> 1) * 16] >> (7 - x)) & 1) << p for p in range(4))
             for x in range(8)] for y in range(8)]


def chameleon(rb, binfo, sheets, en_info):
    """CTAB (each character's walk in blocks of <= 8 columns), the routine and its hooks (asm/chameleon.asm).
    Poses streamed for the players already are such blocks; the others are cut out of the animation's 1 KB
    strip (the columns its pieces use, in order) with their pieces renumbered, and checked pixel by pixel."""
    from .. import asar
    t = binfo["tables"]

    def rb8(a):
        return rb.d[off(a)]

    def rw(a):
        return rb.d[off(a)] | rb.d[off(a) + 1] << 8

    def rl(a):
        return rw(a) | rb8(a + 2) << 16

    def sheet_src(s):
        return int.from_bytes(sheets.entries[8 * (s - 1) + 4:8 * (s - 1) + 7], "little")

    blocks, maps, stats = {}, {}, dict(streamed=0, cut=0, widest=0)

    def block_addr(data):
        if data not in blocks:
            blocks[data] = rb.alloc(CHAM_DATA, data, f"chameleons: pose tiles ({len(data) // 64} columns)")
        return blocks[data]

    def map_addr(blob):
        if blob not in maps:
            a = rb.alloc(["objmap3", "objmap2", "objmap"], blob, "chameleons: pose pieces (cut from a strip)")
            maps[blob] = a & 0x3FFFFF | 0x800000
        return maps[blob]

    empty = map_addr(bytes([1]) + PIECE.pack(0x4000, 0, 0, 0x20))
    scripts = {}                                         # (char, facing) -> [(frames, map24, src24, cols)], loop
    for c in range(10):
        mt, at = rl(t["charmap"] + 3 * c), rl(t["charanim"] + 3 * c)
        if not mt or not at:
            raise BuildError(f"chameleons: character {c} has no tables of its own")
        so, sn = rw(t["charstream"] + 3 * c), rb8(t["charstream"] + 3 * c + 2)
        ct = 0x800000 | rw(0x80BB66 + 2 * c)
        for a in WALK:
            p = at & 0xFF0000 | rw(at + 2 * (a - 1))
            seq = []
            while rb8(p + 1):
                seq.append((rb8(p), rb8(p + 1)))
                p += 2
            loop = rb8(p) // 2
            if not seq or loop >= len(seq):
                raise BuildError(f"chameleons: character {c}, animation {a:02X}: empty or bad loop")
            out = []
            for m, fr in seq:
                if not m:
                    out.append((fr, empty, 0, 0))
                    continue
                mp = mt & 0xFF0000 | rw(mt + 2 * (m - 1))
                e = 0xE40000 | (so + 4 * (m - 1)) if sn and m <= sn else 0
                if e and rb8(e + 3) & 15:
                    w = rb8(e + 3) & 15
                    out.append((fr, mp, rw(e) | (0xEC + (rb8(e + 3) >> 4)) << 16, w))
                    stats["streamed"] += 1
                    continue
                sheet, row = rb8(ct + 2 * (a - 1)), rb8(ct + 2 * (a - 1) + 1)
                s0 = off(sheet_src(sheet) + row * 0x200)
                strip = bytes(rb.d[s0:s0 + 0x400])
                pieces = [PIECE.unpack_from(rb.d, off(mp) + 1 + 7 * i) for i in range(rb8(mp))]
                if all(x >= 0x1000 for x, *_ in pieces):     # an empty pose (encode_mapping: one piece far right)
                    out.append((fr, empty, 0, 0))
                    continue
                used = set()
                for x, y, tile, attr in pieces:
                    rel = tile - row * 16
                    r, col, n = rel >> 4, rel & 15, 2 if attr & 1 else 1
                    if not (0 <= r and r + n <= 2 and col + n <= 16):
                        raise BuildError(f"chameleons: character {c}, pose {m:02X}: a piece outside its strip")
                    used |= set(range(col, col + n))
                cols = sorted(used)
                w = len(cols)
                if w > HALF_COLS:
                    raise BuildError(f"chameleons: character {c}, pose {m:02X} uses {w} columns "
                                     f"(a VRAM half holds {HALF_COLS})")
                new = {col: i for i, col in enumerate(cols)}
                data = b"".join(strip[r * 0x200 + col * 32:r * 0x200 + col * 32 + 32] for r in (0, 1) for col in cols)
                npieces = [(x, y, ((tile - row * 16) >> 4) * 16 + new[(tile - row * 16) & 15], attr)
                           for x, y, tile, attr in pieces]
                # the cut pose draws the same pixels as the player's
                old_px = _pose_pixels(lambda n: _decode(strip[((n - row * 16) >> 4) * 0x200 + ((n - row * 16) & 15) * 32:]
                                                        [:32]), pieces)
                new_px = _pose_pixels(lambda n: _decode(data[((n >> 4) * w + (n & 15)) * 32:][:32]), npieces)
                if old_px != new_px:
                    raise BuildError(f"chameleons: character {c}, pose {m:02X} drawn differently once cut")
                blob = bytes([len(npieces)]) + b"".join(PIECE.pack(*q) for q in npieces)
                out.append((fr, map_addr(blob), block_addr(data), w))
                stats["cut"] += 1
                stats["widest"] = max(stats["widest"], w)
            scripts[(c, a)] = (out, loop)

    # one bank: 40 words (character * 4 + facing - 1) -> entries [frames, map24, src24, cols], [0, loop16]
    region = next(r for r in CHAM_DATA if r in rb.regions and rb.regions[r].free() >= 4096)
    base = rb.regions[region].cursor
    head, body, where = bytearray(), bytearray(), {}
    pos = (base & 0xFFFF) + 80
    for c in range(10):
        for a in WALK:
            out, loop = scripts[(c, a)]
            key = (tuple(out), loop)
            if key not in where:
                start = pos + len(body)
                for fr, mp, src, w in out:
                    body += bytes([fr]) + mp.to_bytes(3, "little") + src.to_bytes(3, "little") + bytes([w])
                body += bytes([0]) + (start + 8 * loop).to_bytes(2, "little")
                where[key] = start
            head += where[key].to_bytes(2, "little")
    ctab = rb.alloc(region, bytes(head + body), "chameleons: walk poses of each character and facing (CTAB)")
    if ctab != base or (ctab + len(head) + len(body) - 1) >> 16 != ctab >> 16:
        raise BuildError("chameleons: CTAB moved or crosses a bank")

    hit = bytes(rb.d[off(HIT):off(HIT) + 6])             # JSL gs_enemy (features/game_sfx.py) : NOP NOP
    nmi = bytes(rb.d[off(NMI_HOOK):off(NMI_HOOK) + 4])
    if hit[0] != 0x22 or hit[4:] != bytes.fromhex("EA EA") or nmi[0] != 0x22:
        raise BuildError(f"chameleons: unexpected hooks ({hit.hex()}, {nmi.hex()})")
    region = rb.regions["bulk"]
    runs, syms = asar.assemble_into(rb.d, CHAM_ASM, {
        "ORG": f"${region.cursor:06X}", "GS_ENEMY": f"${int.from_bytes(hit[1:4], 'little'):06X}",
        "NMINEXT": f"${int.from_bytes(nmi[1:4], 'little'):06X}", "CHAM_TYPE": f"${KINDS['frog']['type']:02X}",
        "STAGE": f"${CHAM_STAGE:02X}", "CTAB": f"${ctab:06X}", "CTB": f"${ctab & 0xFF0000:06X}",
        "EMPTY": f"${empty:06X}"})
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"chameleon.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "chameleons: routine, NMI DMA, hit hook (asm/chameleon.asm)")

    def jsl(a):
        return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16])
    rec, r = en_info["frog"]["rec"], syms["chameleon"]
    rb.patch(rec + 9, bytes(rb.d[off(rec + 9):off(rec + 12)]), bytes([r & 0xFF, r >> 8 & 0xFF, r >> 16]),
             "SB1 enemy frog: chameleon actor routine (asm/chameleon.asm)")
    rb.patch(HIT, hit, jsl(syms["cham_hit"]) + hit[4:],
             "enemy hit: a chameleon's own palette slot back first (asm/chameleon.asm cham_hit)")
    rb.patch(NMI_HOOK, nmi, jsl(syms["cham_nmi"]), "NMI: chameleon poses DMA'd with the OAM (asm/chameleon.asm)")
    return dict(stats, blocks=len(blocks), maps=len(maps), scripts=len(where))
