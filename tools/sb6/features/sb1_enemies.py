"""Super Bomberman 1 enemies in World 1 (1-2 = SB1 2-1's spring heads, pots and clown faces).

SB5 enemies (docs/ROM_MAP.md "Enemies"): the stage record places them (`A2 x y type`, type 04 script); a type's
16-byte record at $C3:005C + 16*(type-1) (copied to $1D41+ by $C3:0000) holds its set 8 archive (OBJ tiles, LZ,
stored as column pairs: archive tile 2i is VRAM tile i of a 16-tile row, 2i+1 the one under it, 32 per page),
set 8 palette (16 colors), palette slot mask, object type T (7: every enemy) and first animation; a walking
enemy shows animation first + facing - 1 (facing $1632: 1 right, 2 down, 3 left, 4 up). Sprites go through T's
animation scripts and mappings ($C0:171D / $C0:16CC + 3*T).

Here the records of types 02, 03 and 06 (only in SB5 stages no longer played: $0F, $12-$14, $16) become copies
of type 01's (an enemy that just walks) with the pictures of assets/enemies/<sheet>.png (tools/sb1_enemy_assets.py:
32 x 48 cells, anchor = the lowest 16x16 piece at (8, 28)): their archives and palettes replace those types' own
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
RECORDS = 0xC3005C
HIT = 0xC34D41                   # enemy hit (JSL gs_enemy, features/game_sfx.py)
BASE_TYPE = 0x01                 # records copied from type 01's
ANIM_FIRST, MAP_FIRST = 0x60, 0xE0
CW, CH, AX, AY = 32, 48, 8, 28   # sheet cell, anchor (top left of the lowest 16x16 piece)
PIECE_X, PIECE_Y = -8, -9        # where SB5 draws a 16x16 enemy (type 05) relative to the object
# kind: SB5 type slot, sheet, animations right / down / left / up as [(cell, frames), ...]
SPRING = [(0, 16), (1, 4), (2, 28), (1, 4)]
KINDS = {
    "spring": dict(type=0x02, sheet="sb1_2-1_spring", anims=[[(c + 3 * d, n) for c, n in SPRING] for d in range(4)]),
    "pot": dict(type=0x03, sheet="sb1_2-1_pot", anims=[[(c, 8) for c in range(8)]] * 4),
    "clown": dict(type=0x06, sheet="sb1_2-1_clown", anims=[[(2, 8), (3, 8)], [(0, 8), (1, 8)]] * 2),
    # SB1 3-6's chameleon: a frog that becomes a copy of a live player's bomber (asm/sb1_enemies.asm)
    "frog": dict(type=0x05, sheet="sb1_3-6_frog", routine="chameleon",
                 anims=[[(0, 12), (1, 12), (2, 12), (1, 12), (3, 6), (4, 6), (5, 12), (4, 6), (3, 6)]] * 4),
    # SB1 2-8's clown mask (1-7's boss): an enemy with an empty picture whose routine moves the clown, drawn
    # on BG2 from assets/enemies/sb1_2-8_clown.png (asm/sb1_enemies.asm `clown`); type 07 was only in SB5
    # stages $18-$1B (1-3's enemies are SB1's now)
    "clownbody": dict(type=0x07, sheet="sb1_2-8_body", routine="clown", anims=[[(0, 60)]] * 4),
}
CLOWN = ("sb1_2-8_clown", "sb1_2-8_clown_closed")   # BG2 pictures, mouth open / closed (112 x 92, same box)
CLOWN_CENTER = (56, 44)          # the body's cell center in the picture
CLOWN_PALS = (3, 6)              # BG palettes of the 1-7 arena it takes (features/sb1_stages.py "sb1_4-8")
# 1-2 (stage $11): SB1 2-1 has 4 spring heads, 2 pots, 2 clown faces (`A2 x y type` roots, world1.chain)
STAGE_ENEMIES = {0x11: [(7, 3, "spring"), (5, 5, "spring"), (9, 5, "pot"), (5, 7, "clown"), (9, 7, "spring"),
                        (7, 9, "pot"), (11, 9, "clown"), (13, 5, "spring")],
                 # 1-3 (stage $18): SB1 3-6's 7 chameleons
                 0x18: [(13, 8, "frog"), (9, 5, "frog"), (9, 9, "frog"), (5, 7, "frog"), (1, 8, "frog"),
                        (7, 3, "frog"), (11, 11, "frog")],
                 # 1-7 (stage $68, boss): the clown instead of SB5's rival
                 0x68: [(7, 4, "clownbody")]}


def _w(rb, a):
    return rb.d[off(a)] | rb.d[off(a) + 1] << 8


def _bgr(p):
    return (int(p[0]) >> 3) | (int(p[1]) >> 3) << 5 | (int(p[2]) >> 3) << 10


def _kind(rb, name, k, map_id):
    sheet = np.asarray(Image.open(os.path.join(ASSETS, k["sheet"] + ".png")).convert("RGBA"))
    cells = [sheet[:, i * CW:(i + 1) * CW] for i in range(sheet.shape[1] // CW)]
    colors = sorted({_bgr(p) for c in cells for p in c.reshape(-1, 4) if p[3]})
    if len(colors) > 15:
        raise BuildError(f"SB1 enemy {name}: {len(colors)} colors (15 at most)")
    if not colors:
        colors = [0]
    lut = {c: i + 1 for i, c in enumerate(colors)}
    tiles, known, maps = [], {}, []
    for cell in cells:
        pieces = []
        for ty in range(CH // 8):
            for tx in range(CW // 8):
                blk = cell[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                if not blk[..., 3].any():
                    continue
                idx = np.zeros((8, 8), np.uint8)
                for y in range(8):
                    for x in range(8):
                        if blk[y, x, 3]:
                            idx[y, x] = lut[_bgr(blk[y, x])]
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
                pieces.append(struct.pack("<hhHB", tx * 8 - AX + PIECE_X, ty * 8 - AY + PIECE_Y, vt,
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
    hit = bytes(rb.d[off(HIT):off(HIT) + 6])          # JSL gs_enemy (features/game_sfx.py) : NOP NOP
    if hit[0] != 0x22 or hit[4:] != bytes.fromhex("EA EA"):
        raise BuildError(f"SB1 enemies: ${HIT:06X} is not game_sfx's JSL ({hit.hex()})")
    gs = int.from_bytes(hit[1:4], "little")
    runs, syms = asar.assemble_into(rb.d, ASM, {"ORG": f"${region.cursor:06X}", "GS_ENEMY": f"${gs:06X}",
                                                "CHAM_TYPE": f"${KINDS['frog']['type']:02X}",
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
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "SB1 enemies: chameleon routine (asm/sb1_enemies.asm)")
    c = syms["cham_hit"]
    rb.patch(HIT, hit, bytes([0x22, c & 0xFF, c >> 8 & 0xFF, c >> 16]) + hit[4:],
             "enemy hit: a chameleon's own palette slot back first (asm/sb1_enemies.asm cham_hit)")
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
    all_maps, all_scripts, info = [], [], {}
    for name, k in KINDS.items():
        built = _kind(rb, name, k, MAP_FIRST + len(all_maps))
        rec = RECORDS + 16 * (k["type"] - 1)
        old = bytes(rb.d[off(rec):off(rec) + 15])
        arc_id, pal_id = old[0], old[1]
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
        rb.patch(stock, bytes(rb.d[off(stock):off(stock) + len(data)]), data,
                 f"SB1 enemy {name}: OBJ palette (set 8 palette {pal_id}, in place)")
        # record: type 01's, with this kind's archive, palette, animations
        anim = ANIM_FIRST + len(all_scripts)
        new = bytes([arc_id, pal_id]) + base_rec[2:4] + bytes([anim]) + base_rec[5:]
        if "routine" in k:                                   # own actor routine (it runs $C3:4B5A itself)
            r = syms[k["routine"]]
            new = new[:9] + bytes([r & 0xFF, r >> 8 & 0xFF, r >> 16]) + new[12:]
        rb.patch(rec, old, new, f"SB1 enemy {name}: type ${k['type']:02X} record (type 01's walk, own pictures)")
        all_maps += built["maps"]
        all_scripts += built["scripts"]
        info[name] = dict(type=k["type"], tiles=built["tiles"], frames=len(built["maps"]), colors=len(built["colors"]))
    if MAP_FIRST + len(all_maps) > 0x100 or ANIM_FIRST + len(all_scripts) > MAP_FIRST:
        raise BuildError("SB1 enemies: too many mappings / animations")
    mt = _table(rb, all_maps, "SB1 enemies: T 7 mappings from $E0")
    at = _table(rb, all_scripts, "SB1 enemies: T 7 animations from $60")
    defs = {"ENMAP": f"${mt >> 16:02X}", "ENMAPBASE": f"${(mt - 2 * (MAP_FIRST - 1)) & 0xFFFF:04X}",
            "ENMAPFIRST": f"${MAP_FIRST:02X}", "ENANIM": f"${at >> 16:02X}",
            "ENANIMBASE": f"${(at - 2 * (ANIM_FIRST - 1)) & 0xFFFF:04X}", "ENANIMFIRST": f"${ANIM_FIRST:02X}"}
    info["_clown"] = dict(pals=bg["pals"], start=syms["clown_start"], hit=syms["clown_hit"], tiles=bg["ntiles"])
    return defs, info


def stage_enemies(stage):
    """`A2 x y type` scripts of a stage whose enemies are replaced (world1.chain), else None."""
    if stage not in STAGE_ENEMIES:
        return None
    return [bytes([0xA2, x, y, KINDS[k]["type"], 0x00]) for x, y, k in STAGE_ENEMIES[stage]]
