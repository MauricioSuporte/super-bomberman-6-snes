"""World 1 of Super Bomberman 6: "WORLD" instead of "ZONE", the seven-stage chain, SB1-style exit doors.

Text (docs/ROM_MAP.md "Stage intro text"):
* Stage intro (task `$C5:0CD9`) and SB5's pause: set 4 arrangement `$E0` was "ZONE" (BG3 tiles
  `$A6-$AB` / `$B6-$BB` of set 3 archive `$4D`, LZ, VRAM `$5400`) + the dash; SB6 writes STAGE w-s
  instead: the 8 x 16 letters S T A G E of `features/pause.py` (LETTERS, drawn like SB5's big
  digits) in tiles `$A6-$AA` / `$B6-$BA` ($AB / $BB blanked). The new archive goes to `bulk`, the
  old one is freed. The arrangement is 8 wide (STAGE, two gaps, dash: the world digit goes in the
  second gap) and lives in `free_e2` (set 4's arrangements are words in bank `$E2`); the intro task
  places it and the digits through `intro_label` (asm/pause.asm, stage number without its leading
  zero, centred on column 16).
* World map label (BG3, tiles 1-8 / `$11-$18` + the zone digit `$0A+`): set 3 archive `$0D`
  (raw, `$E3:D110`), redrawn in place.
The map label's letters are drawn at build time from SB5's own glyphs (O, R, E, M of the intro
font): W = M upside down, L = E without its upper bars, D = O with round right corners, rendered
with the map font's rules (colour bands by row + 1-px shadow). Preview: build/world_text_preview.png.
"""
import os
import struct
import zlib

import numpy as np
from PIL import Image

from .. import lz
from ..rombuild import BuildError
from ..romlib import off
from . import pause, sb1_enemies

ARC_TABLE = 0xE3BE60          # archive entries (8 bytes), set 3 window starts at $E3:C158
SET3 = 0xE3C158
INTRO_ARC = 0x4D              # set 3: stage intro / HUD font, VRAM $5400 (tile $80), LZ
MAP_ARC = 0x0D                # set 3: world map label font, VRAM $5000, raw
INTRO_ARR = 0xE0              # set 4 arrangement "ZONE  -" -> "STAGE  -"
INTRO_TOP = [0xA6, 0xA7, 0xA8, 0xA9, 0xAA]   # S T A G E (bottoms + $10)
DASH_ARR = 0xC6               # set 4 arrangement: "-" alone (the slot of SB5's freed Password $C6)
PAL_INTRO = 1                 # the letters' BG3 palette (SB5's ZONE / WORLD green)


def _entry(rb, set_base, n):
    return set_base + 8 * (n - 1)


def _tiles2bpp(data, first, tops, bots):
    """16-row picture (ints 0-3) from 2bpp tiles: `tops` above `bots`."""
    rows = []
    for tiles in (tops, bots):
        for y in range(8):
            line = []
            for t in tiles:
                o = (t - first) * 16
                b0, b1 = data[o + 2 * y], data[o + 2 * y + 1]
                line += [((b0 >> (7 - x)) & 1) | (((b1 >> (7 - x)) & 1) << 1) for x in range(8)]
            rows.append(line)
    return np.array(rows)


def _put2bpp(data, first, tops, bots, pic):
    for half, tiles in enumerate((tops, bots)):
        for i, t in enumerate(tiles):
            o = (t - first) * 16
            for y in range(8):
                b0 = b1 = 0
                for x in range(8):
                    c = int(pic[half * 8 + y, i * 8 + x])
                    b0 |= (c & 1) << (7 - x)
                    b1 |= ((c >> 1) & 1) << (7 - x)
                data[o + 2 * y], data[o + 2 * y + 1] = b0, b1


def _shift(m, dy, dx):
    o = np.zeros_like(m)
    h, w = m.shape
    o[dy:, dx:] = m[:h - dy, :w - dx]
    return o


def _crop(m):
    cols = [c for c in range(m.shape[1]) if m[:, c].any()]
    return m[:, cols[0]:cols[-1] + 1]


def _glyphs(font):
    """Fill masks (12 rows high, rows 1-12 of the intro font) of W, O, R, L, D."""
    zone = _tiles2bpp(font, 0x80, range(0xA6, 0xAC), range(0xB6, 0xBC))
    row = _tiles2bpp(font, 0x80, range(0xC0, 0xD0), range(0xD0, 0xE0))      # "RT TIMEHURR"
    o = _crop(zone[1:13, 12:24] == 3)
    e = _crop(zone[1:13, 36:48] == 3)
    r = _crop(row[1:13, 103:115] == 3)
    m = _crop(row[1:13, 55:67] == 3)
    w = m[::-1].copy()
    # L: E's stroke (the columns filled between the bars) down to the bottom bar
    stroke = [c for c in range(e.shape[1]) if e[4, c] and e[7, c]]
    l = e.copy()
    l[:9, :] = False
    l[:, stroke] = e[:, stroke]
    l = _crop(l)
    d = o.copy()
    rc, bot = d.shape[1] - 1, d.shape[0] - 1
    for k in range(4):                       # round right side: 4-px diagonal corners
        for j in range(4 - k):
            d[k, rc - j] = False
            d[bot - k, rc - j] = False
    return [w, o, r, l, d]


def _word(masks, gap, height, scale=(1, 1), top=0):
    """Masks side by side (each scaled by (sy, sx), nearest), `gap` columns apart, in a 64-px field."""
    out = np.zeros((height, 64), bool)
    x = 1
    for m in masks:
        sy, sx = scale
        h, w = m.shape
        nh, nw = int(round(h * sy)), int(round(w * sx))
        ys = (np.arange(nh) * h // nh)
        xs = (np.arange(nw) * w // nw)
        s = m[ys][:, xs]
        if x + nw > 64:
            raise BuildError("WORLD does not fit in 64 pixels")
        out[top:top + nh, x:x + nw] |= s
        x += nw + gap
    return out, x - gap


def _render_map(b):
    band = np.array([3] * 5 + [2] * 7 + [3] * 4)[:, None] * np.ones((1, b.shape[1]), int)
    sh = (_shift(b, 1, 0) | _shift(b, 0, 1) | _shift(b, 1, 1)) & ~b
    out = np.zeros(b.shape, int)
    out[sh] = 1
    out[b] = band[b]
    return out


def text(rb, base_rom, out_dir):
    # ---- intro font (archive $4D)
    ea = _entry(rb, SET3, INTRO_ARC)
    e = rb.d[off(ea):off(ea) + 8]
    vram, size, src = e[0] | e[1] << 8, e[2] | e[3] << 8, e[4] | e[5] << 8 | e[6] << 16
    if (vram, size, src, e[7]) != (0x5400, 0x0770, 0xD5C9DA, 0x03):
        raise BuildError(f"set 3 archive $4D is not the expected one: {bytes(e).hex(' ')}")
    font, used = lz.decompress(bytes(rb.d[off(src):off(src) + 0x1000]), size)
    masks = _glyphs(font)
    font = bytearray(font)
    for c, t in zip("STAGE", INTRO_TOP):
        top, bot = pause.big_letter(pause.LETTERS[c])
        font[(t - 0x80) * 16:(t - 0x7F) * 16] = top
        font[(t + 0x10 - 0x80) * 16:(t + 0x10 - 0x7F) * 16] = bot
    for t in (0xAB, 0xBB):                                       # ZONE's last column
        font[(t - 0x80) * 16:(t - 0x7F) * 16] = bytes(16)
    new_src = rb.alloc("bulk", lz.compress(bytes(font)), "STAGE: stage intro font (set 3 archive $4D)")
    rb.patch(ea, e, bytes([0x00, 0x54, 0x70, 0x07, new_src & 0xFF, (new_src >> 8) & 0xFF, new_src >> 16, 0x03]),
             "STAGE: set 3 archive $4D = the font with STAGE")
    # old font data: nothing else names it (one archive entry; the stock OBJ sheet table copy is freed)
    old = bytes(base_rom[off(src):off(src) + used])
    rb.free_old("free_d5_font", src + 1, used - 1, zlib.crc32(old[1:]),
                "freed SB5 stage intro font with ZONE (set 3 archive $4D, LZ); its first byte stays")

    # ---- the intro arrangement: STAGE (5), gap, gap (the world digit), dash; asm/pause.asm intro_label places it
    letter = 0x2000 | PAL_INTRO << 10
    words = [letter | t for t in INTRO_TOP] + [0x2080] * 2 + [0x208C]
    words += [letter | t + 0x10 for t in INTRO_TOP] + [0x2080] * 2 + [0x209C]
    lo = bytes(w & 0xFF for w in words)
    hi = bytes(w >> 8 for w in words)
    arr = bytes([8, 2, 0, 0, 0]) + lz.compress(lo) + lz.compress(hi) + bytes(1)
    tab = 0xC00000 | (rb.d[off(0xC08000 + 12)] | rb.d[off(0xC08000 + 13)] << 8 | rb.d[off(0xC08000 + 14)] << 16)
    slot = tab + 2 * (INTRO_ARR - 1)
    a = rb.alloc("free_e2", arr, "STAGE: stage intro arrangement (set 4 $E0)")
    if a >> 16 != tab >> 16:
        raise BuildError("WORLD arrangement outside the set 4 bank")
    rb.patch(slot, bytes([0x27, 0xDA]), bytes([a & 0xFF, (a >> 8) & 0xFF]), "STAGE: set 4 arrangement $E0")
    # the dash + a blank (2 wide as the digits; 1 wide hangs the drawer) (set 4 $C6, free since features/options.py freed SB5's Password): SB5's digit arrangements
    # $EA+ are 2 wide (digit, blank), so the world digit's blank covers $E0's dash; intro_label draws this after it
    dash = bytes([2, 2, 0, 0, 0]) + lz.compress(bytes([0x8C, 0x80, 0x9C, 0x80])) + lz.compress(bytes([0x20] * 4)) + bytes(1)
    dslot = tab + 2 * (DASH_ARR - 1)
    old = bytes(rb.d[off(dslot):off(dslot) + 2])
    if old != bytes([0xFB, 0xC3]):
        raise BuildError(f"set 4 slot ${DASH_ARR:02X} is not the freed Password arrangement: {old.hex()}")
    d = rb.alloc("free_e2", dash, "STAGE: stage intro dash (set 4 $C6)")
    if d >> 16 != tab >> 16:
        raise BuildError("dash arrangement outside the set 4 bank")
    rb.patch(dslot, old, bytes([d & 0xFF, (d >> 8) & 0xFF]), "STAGE: set 4 arrangement $C6 = the dash")

    # ---- world map label (archive $0D, raw): tiles 1-8 / $11-$18
    ma = _entry(rb, SET3, MAP_ARC)
    me = rb.d[off(ma):off(ma) + 8]
    msrc = me[4] | me[5] << 8 | me[6] << 16
    if msrc != 0xE3D110 or me[7] != 0x83:
        raise BuildError(f"set 3 archive $0D is not the expected one: {bytes(me).hex(' ')}")
    tops, bots = list(range(1, 9)), list(range(0x11, 0x19))
    o0 = off(msrc)
    old = bytearray(rb.d[o0:o0 + 0x200])
    mb, _ = _word(masks, 2, 16, scale=(15 / 12, 1.25))
    label = _render_map(mb)
    new = bytearray(old)
    _put2bpp(new, 0, tops, bots, label)
    rb.patch(msrc, old, new, "WORLD: world map label (set 3 archive $0D tiles 1-8 / $11-$18)")

    if out_dir:
        pal_m = [(40, 0, 60), (60, 0, 0), (180, 90, 90), (255, 200, 200)]
        img = Image.new("RGB", (64, 16))
        for y in range(16):
            for x in range(64):
                img.putpixel((x, y), pal_m[label[y, x]])
        img.resize((256, 64), Image.NEAREST).save(os.path.join(out_dir, "world_text_preview.png"))


# ---------------------------------------------------------------------------------------------------------
# Stage chain (docs/ROM_MAP.md "Stage records"): mode table $C6:0000 + 3 * (stage - 1) -> record = 3-byte
# pointers to roots (0 ends); root = [type, ptr24]... 00. Types: 04 stage start, 0D all enemies dead,
# 0B a portal's exit (`0F dest` = next mode), 0C its touch test. SB5 stages have up to three portal roots
# (0D `11 label x y`, 0B, 0C `12 x y`); World 1 stages get one door root instead (asm/world1.asm):
#   04 FF 1A F6 03 (a task picks the door once the blocks are out), 0D FF 1A F6 01 (queue it), 0B 0F next, 0C FF 1A F6 02 (touch).
# Intro numbers: word $80:8A8A + 2 * stage, decimal world * 1000 + stage (1001 = "1 - 01").
ASM = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                   "asm", "world1.asm")
MODE_TABLE = 0xC60000
NUMBERS = 0x808A8A
NEXT_WORLD = 0x1C                  # World 2's first stage (SB5's ZONE2-1, for now)
# World 1: (stage id, its number, next stage). 1-6 is two duels (SB5 bosses $67 then $69), 1-7 SB5's $68.
CHAIN = [
    (0x0D, 1, 0x11),               # 1-1: SB5 1-1
    (0x11, 2, 0x18),               # 1-2: SB5 1-5
    (0x18, 3, 0x10),               # 1-3: SB5 1-12
    (0x10, 4, 0x17),               # 1-4: SB5 1-4 (the green tank)
    (0x17, 5, 0x67),               # 1-5: SB5 1-11 (the knights)
]
# 1-6: three duels in the SB6 tournament arena (features/sb1_stages.py "sb6_1-6"), the rival = character 1
# (char1_sb6.png, the mecha bomber) in a column of its palette picture (0 = key colors): white, black, golden
RIVALS = [(0x67, 1), (0x69, 2), (0x6B, 20)]
RIVAL_OWN_ID = 0x5A                # column 1 = palette id $5A (features/bombers.py OWN_ID; char1 shares his)
BG1_MAP = 0x3000                   # arena field: BG1 map at VRAM word $3000
STAGE_OPS = {0x6B: (4, "stands blink"), 0x68: (5, "electric fence"), 0x10: (6, "bumpers animated")}
BOSSES = [                         # (boss stage, its first portal root, next stage)
    (0x67, 0xC71BE3, 0x69),        # 1-6, first duel (white)
    (0x69, 0xC71F6D, 0x6B),        # 1-6, second duel (black)
    (0x6B, 0xC721AD, 0x68),        # 1-6, the Golden Bomber (the stands blink first)
    (0x68, 0xC71DC1, NEXT_WORLD),  # 1-7
]


# World map stage markers (docs/ROM_MAP.md "World map"): $C2:1070 = 3-byte pointers per zone to
# [x, y, stage, n]... + 00 00 00 00. Op $18 draws a flag (object $48, 8x8 at x, y - 9) per entry, op $19
# gives the stage of the entry whose box [x - 8, x + 12) x [y - 8, y + 12) holds the cursor ($103A, $103C),
# op $1A puts the cursor on a stage; the label is set 4 arrangement $1B + n - 1 ("- n"). START plays the
# marker's stage when it is the zone's first one, the last one played ($4DB2) or cleared ($7E:2900 bit
# stage + 3), as in SB5.
MARKER_ZONES = 0xC21070
# 1-1 .. 1-7 where assets/world_map/zone1_stages.png has its red digits (centre cx, cy in the picture): the
# flag is centred on the digit, screen line = picture line + 1 (features/world_map.py) -> x = cx - 4, y = cy + 6
MARKERS = [(64, 166), (113, 160), (167, 150), (175, 80), (119, 124), (63, 83), (119, 94)]
# SB5's boss markers on ZONE2 / ZONE3 whose stages are World 1's now (1-7 $68, 1-6's $69 / $6B): taken out
MARKERS_DROP = {1: (0x68, 0x69), 2: (0x6B,)}


def markers(rb):
    stages = [s for s, _, _ in CHAIN] + [BOSSES[0][0], BOSSES[-1][0]]
    assert len(stages) == len(MARKERS)

    def table(zone):
        a = _p24(rb, MARKER_ZONES + 3 * zone)
        o = off(a)
        n = 0
        while any(rb.d[o + 4 * n:o + 4 * n + 3]):
            n += 1
        return a, [bytes(rb.d[o + 4 * k:o + 4 * k + 4]) for k in range(n)]

    at, old = table(0)
    new = b"".join(bytes([cx - 4, cy + 6, s, n]) for n, ((cx, cy), s) in enumerate(zip(MARKERS, stages), 1))
    size = 4 * len(old) + 4
    rb.patch(at, bytes(rb.d[off(at):off(at) + size]), (new + bytes(4)).ljust(size, b"\x00"),
             "World 1 map: markers 1-1..1-7 (x, y, stage, label n)")
    for zone, drop in MARKERS_DROP.items():
        at, old = table(zone)
        keep = [e for e in old if e[2] not in drop]
        if len(keep) + len(drop) != len(old):
            raise BuildError(f"world map zone {zone + 1}: markers {drop} not found")
        rb.patch(at, b"".join(old), b"".join(keep).ljust(4 * len(old), b"\x00"),
                 f"world map ZONE{zone + 1}: without the markers of stages "
                 + ", ".join(f"${s:02X}" for s in drop) + " (World 1's now)")
    return [f"1-{n} ${s:02X} at ({cx - 4}, {cy + 6})" for n, ((cx, cy), s) in enumerate(zip(MARKERS, stages), 1)]


def _p24(rb, a):
    o = off(a)
    return rb.d[o] | rb.d[o + 1] << 8 | rb.d[o + 2] << 16


def _roots(rb, stage):
    rec = _p24(rb, MODE_TABLE + 3 * (stage - 1))
    roots, a = [], rec
    while _p24(rb, a):
        r = _p24(rb, a)
        entries, b = [], r
        while rb.d[off(b)]:
            entries.append((rb.d[off(b)], _p24(rb, b + 1)))
            b += 4
        roots.append((r, entries))
        a += 3
    return rec, roots


def _blink_table(rb, blink):
    """Rows of the stands' BG1 map words (arena map at VRAM word $3000, 32 wide; cell (c, r) at
    $3000 + 64r + 2c): every row as (address, left word, right word), the empty stands first, then the crowd."""
    rows = {0: [], 1: []}
    for c, r, crowd, empty in blink:
        for dy in range(2):
            a = BG1_MAP + 64 * r + 32 * dy + 2 * c
            rows[0].append(struct.pack("<HHH", a, empty[2 * dy], empty[2 * dy + 1]))
            rows[1].append(struct.pack("<HHH", a, crowd[2 * dy], crowd[2 * dy + 1]))
    data = b"".join(rows[0] + rows[1])
    return rb.alloc("bulk", data, f"World 1: 1-6's stands, BG1 map words (empty / crowd, {len(rows[0])} rows)"), len(rows[0])


def code(rb, arena, anim_start=0, clown=None):
    """arena: features/sb1_stages.py's result for "sb6_1-6" (ext ids, blink cells); anim_start: the animated
    fence's task start (asm/stage_anim.asm, 0 = none)."""
    from .. import asar
    blink, nrows = _blink_table(rb, arena["blink"])
    region = rb.regions["bulk"]
    defs = {"ORG": f"${region.cursor:06X}", "KNIGHT_STAGE": f"${KNIGHT_STAGE:02X}",
            "W1ARC": f"${arena['ext']['arc']:06X}", "BLINK": f"${blink:06X}", "BLINKN": str(nrows),
            "ANIMSTART": f"${anim_start:06X}", "CLOWNSTART": f"${clown['start']:06X}",
            "CLOWNHIT": f"${clown['hit']:06X}", "CLOWN_TYPE": f"${sb1_enemies.KINDS['clownbody']['type']:02X}"}
    for k, (stage, col) in enumerate(RIVALS):
        defs[f"RIVAL{k + 1}"] = f"${stage:02X}"
        defs[f"PAL{k + 1}"] = f"${RIVAL_OWN_ID + col - 1:02X}"
    runs, syms = asar.assemble_into(rb.d, ASM, defs)
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"world1.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "World 1: exit door op FF 1A F6, knights (asm/world1.asm)")
    k = syms["knight_hit"]
    rb.patch(0xC349EC, bytes.fromhex("B9 52 10 29 04"), bytes([0x5C, k & 0xFF, k >> 8 & 0xFF, k >> 16, 0xEA]),
             "enemy flame test: World 1's knights are not hurt from the front (asm/world1.asm knight_hit)")
    rb.patch(0xC3005C + 16 * (8 - 1) + 14, b"", bytes([KNIGHT_HP]),
             "enemy type $08 (knights, 1-5; SB5's stage $15 is out of the chain): hearts 4 -> 2")

    def jsl(name, n):
        a = syms[name]
        return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16]) + bytes([0xEA] * (n - 4))
    rb.patch(0xC01B0E, bytes.fromhex("A9 E3 85 C8 C2 20 BF 96 1C C0 85 C6"), jsl("arc_entry", 12),
             "archive loader: set 4 ids $F0+ = World 1's entries (asm/world1.asm arc_entry)")
    rb.patch(0xC43CD5, bytes.fromhex("AA BD 4E BB 18 69 07"), jsl("rival_pal", 7),
             "rival set-up: 1-6's rivals = character 1 in their palette (asm/world1.asm rival_pal)")
    rb.patch(0xC43D28, bytes.fromhex("B1 BD 9D 7A 16"), jsl("rival_stats", 5),
             "rival set-up: 1-6's rivals' hits, the Golden Bomber's kick (asm/world1.asm rival_stats)")
    return syms


KNIGHT_HP = 2            # 1-5's knights: 2 hits (SB5: 4)
KNIGHT_STAGE = 0x17      # 1-5 (SB1's 6-4): its knights (enemy type $08) take no hit from the front
# enemies kept (stage: types; the other type 04 roots that place an enemy `A2 x y type` go): 1-5 = SB1's 6-4,
# its two knights only
KEEP_ENEMIES = {0x17: {0x08}, 0x10: {0x04}}      # 1-5: SB1 6-4's knights; 1-4: SB5's tanks (SB1 4-4 has them)


# script ops left out (stage: {type: [op prefixes]}): 1-4 is SB1's 4-4 now (features/sb1_stages.py), without
# SB5's clouds (its type 06 script draws them on BG1 with FF 8D DA 04 / FF 8D DB 04, set 4 arrangements)
# 1-4: SB5's clouds on BG1 (FF 8D) and its decoration objects (FF DD, $C5:49A1: one of them, $C5:49D7, rewrites
# tiles $12C-$12F, where SB1's pillars turned into arches)
DROP_OPS = {0x10: {0x06: [bytes.fromhex("FF 8D DA"), bytes.fromhex("FF 8D DB"), bytes.fromhex("FF DD")]},
            # 1-5: SB5's decoration objects of theme 5 (FF DF, $C5:4A94; $C5:4AB6 rewrites tiles $12C-$12F too)
            0x17: {0x06: [bytes.fromhex("FF DF")]},
            # 1-7: SB5's arena scatters 16 soft blocks (type 01 `10 10`, $0E1F -> $C5:0160); the SB1 4-8 arena
            # has none (its soft block picture is the floor: they were invisible)
            0x68: {0x01: [bytes([0x10])]}}


def _drop_ops(rb, a, prefixes):
    """The script at a (to its 00) without the ops starting with one of the prefixes. Operand lengths: op n
    at $C2:0AF5+n-1, FF n at $C2:09D8+n-1, FE n at $C2:094D+n-1 (tools/scriptdis.py)."""
    out = bytearray()
    while True:
        op = rb.d[off(a)]
        if op == 0:
            return bytes(out + b"\x00")
        if op in (0xFE, 0xFF):
            sub = rb.d[off(a) + 1]
            ln = 2 + rb.d[off(0xC2094D if op == 0xFE else 0xC209D8) + sub - 1]
        else:
            ln = 1 + rb.d[off(0xC20AF5) + op - 1]
        b = bytes(rb.d[off(a):off(a) + ln])
        if not any(b.startswith(x) for x in prefixes):
            out += b
        a += ln


def chain(rb):
    def p(a):
        return bytes([a & 0xFF, (a >> 8) & 0xFF, a >> 16])

    pick = rb.alloc("bulk", bytes.fromhex("FF 1A F6 03 00"), "World 1 door: start the task that picks it")
    queue = rb.alloc("bulk", bytes.fromhex("FF 1A F6 01 00"), "World 1 door: queue the portal (clear)")
    touch = rb.alloc("bulk", bytes.fromhex("FF 1A F6 02 00"), "World 1 door: players on it")
    report = []
    for stage, num, nxt in CHAIN:
        rec, roots = _roots(rb, stage)
        kept = []
        for r, entries in roots:
            if any(t == 0x0D for t, _ in entries):
                continue
            if sb1_enemies.stage_enemies(stage) is not None and any(t == 0x04 and rb.d[off(a)] == 0xA2 and rb.d[off(a) + 3]
                                                                   not in KEEP_ENEMIES.get(stage, ())
                                                                   for t, a in entries):
                continue                      # replaced below
            if stage in KEEP_ENEMIES and any(t == 0x04 and rb.d[off(a)] == 0xA2 and rb.d[off(a) + 3]
                                             not in KEEP_ENEMIES[stage] for t, a in entries):
                continue
            repl = DROP_OPS.get(stage, {})
            if any(t in repl for t, _ in entries):
                ents = [(t, rb.alloc("bulk", _drop_ops(rb, a, repl[t]),
                                     f"World 1: stage ${stage:02X} type {t:02X} script without some ops")
                         if t in repl else a) for t, a in entries]
                r = rb.alloc("bulk", b"".join(bytes([t]) + p(a) for t, a in ents) + bytes(1),
                             f"World 1: stage ${stage:02X} root with new scripts")
            kept.append(r)
        if stage in STAGE_OPS:      # 1-4's bumpers (n = 6): a type 04 root with FF 1A F6 n
            n, what = STAGE_OPS[stage]
            op = rb.alloc("bulk", bytes([0xFF, 0x1A, 0xF6, n, 0x00]), f"World 1: stage ${stage:02X} {what} (op)")
            kept.append(rb.alloc("bulk", bytes([0x04]) + p(op) + bytes(1), f"World 1: stage ${stage:02X} {what} (root)"))
        for k, scr in enumerate(sb1_enemies.stage_enemies(stage) or []):
            sa = rb.alloc("bulk", scr, f"World 1: stage ${stage:02X} SB1 enemy {k}")
            kept.append(rb.alloc("bulk", bytes([0x04]) + p(sa) + bytes(1), f"World 1: stage ${stage:02X} enemy root {k}"))
        exit_ = rb.alloc("bulk", bytes([0x0F, nxt, 0x00]), f"World 1 door: stage ${stage:02X} -> ${nxt:02X}")
        door = rb.alloc("bulk", bytes([0x04]) + p(pick) + bytes([0x0D]) + p(queue) + bytes([0x0B]) + p(exit_)
                        + bytes([0x0C]) + p(touch) + b"\x00", f"World 1 door root, stage ${stage:02X}")
        new = rb.alloc("bulk", b"".join(p(r) for r in kept + [door]) + b"\x00\x00\x00",
                       f"World 1: stage ${stage:02X} record (1-{num}, door -> ${nxt:02X})")
        rb.patch(MODE_TABLE + 3 * (stage - 1), p(rec), p(new), f"World 1: stage ${stage:02X} = 1-{num}")
        o = off(NUMBERS + 2 * stage)
        old = bytes(rb.d[o:o + 2])
        word = 1000 + num
        rb.patch(NUMBERS + 2 * stage, old, bytes([word & 0xFF, word >> 8]), f"World 1: stage ${stage:02X} shows 1-{num:02d}")
        report.append(f"1-{num} = ${stage:02X}")
    for stage, root, nxt in BOSSES:
        rec, roots = _roots(rb, stage)
        portal = [e for r, e in roots if r == root]
        if not portal:
            raise BuildError(f"boss ${stage:02X}: root ${root:06X} not in its record")
        kept = [r for r, entries in roots if r == root or not any(t == 0x0D for t, _ in entries)]
        if sb1_enemies.stage_enemies(stage) is not None:     # the boss is an SB1 enemy: no SB5 rival
            kept = [r for r in kept if not any(t == 0x04 and bytes(rb.d[off(a):off(a) + 2]) == bytes([0xFF, 0x7C])
                                               for t, a in dict(roots)[r])]
            for k, scr in enumerate(sb1_enemies.stage_enemies(stage)):
                sa = rb.alloc("bulk", scr, f"World 1: boss ${stage:02X} SB1 enemy {k}")
                kept.append(rb.alloc("bulk", bytes([0x04]) + p(sa) + bytes(1), f"World 1: boss ${stage:02X} enemy root {k}"))
        repl = DROP_OPS.get(stage, {})
        for i, r in enumerate(kept):
            entries = dict(roots).get(r)
            if entries and any(t in repl for t, _ in entries):
                ents = [(t, rb.alloc("bulk", _drop_ops(rb, a, repl[t]),
                                     f"World 1: boss ${stage:02X} type {t:02X} script without some ops")
                         if t in repl else a) for t, a in entries]
                kept[i] = rb.alloc("bulk", b"".join(bytes([t]) + p(a) for t, a in ents) + bytes(1),
                                   f"World 1: boss ${stage:02X} root with new scripts")
        if stage in STAGE_OPS:      # 1-6's stands blink (n = 4), 1-7's fence (5): a type 04 root with FF 1A F6 n
            n, what = STAGE_OPS[stage]
            op = rb.alloc("bulk", bytes([0xFF, 0x1A, 0xF6, n, 0x00]), f"World 1: stage ${stage:02X} {what} (op)")
            kept.append(rb.alloc("bulk", bytes([0x04]) + p(op) + bytes(1), f"World 1: stage ${stage:02X} {what} (root)"))
        if sb1_enemies.stage_enemies(stage) is not None:     # SB5's portal is drawn with its theme's tiles:
            kept = [r for r in kept if r != root]               # the World 1 door instead (a floor cell)
            exit_ = rb.alloc("bulk", bytes([0x0F, nxt, 0x00]), f"World 1 door: boss ${stage:02X} -> ${nxt:02X}")
            kept.append(rb.alloc("bulk", bytes([0x04]) + p(pick) + bytes([0x0D]) + p(queue) + bytes([0x0B])
                                 + p(exit_) + bytes([0x0C]) + p(touch) + bytes(1), f"World 1 door root, boss ${stage:02X}"))
            new = rb.alloc("bulk", b"".join(p(r) for r in kept) + bytes(3),
                           f"World 1: boss ${stage:02X} record (SB1 enemy boss, door -> ${nxt:02X})")
            rb.patch(MODE_TABLE + 3 * (stage - 1), p(rec), p(new), f"World 1: boss ${stage:02X} = SB1 enemy boss")
            report.append(f"boss ${stage:02X} -> ${nxt:02X}")
            continue
        exit_ = dict(portal[0])[0x0B]
        o = off(exit_)
        if rb.d[o] != 0x0F:
            raise BuildError(f"boss ${stage:02X}: exit script at ${exit_:06X} is not 0F dest")
        rb.patch(exit_, bytes(rb.d[o:o + 3]), bytes([0x0F, nxt, 0x00]), f"World 1: boss ${stage:02X} exit -> ${nxt:02X}")
        new = rb.alloc("bulk", b"".join(p(r) for r in kept) + b"\x00\x00\x00",
                       f"World 1: boss ${stage:02X} record (one exit -> ${nxt:02X})")
        rb.patch(MODE_TABLE + 3 * (stage - 1), p(rec), p(new), f"World 1: boss ${stage:02X} has one exit")
        report.append(f"boss ${stage:02X} -> ${nxt:02X}")
    return report
