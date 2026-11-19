"""World 1 of Super Bomberman 6: "WORLD" instead of "ZONE", the seven-stage chain, SB1-style exit doors.

Text (docs/ROM_MAP.md "Stage intro text"):
* Stage intro (task `$C5:0CD9`): set 4 arrangement `$E0` = "ZONE" (BG3 tiles `$A6-$AB` / `$B6-$BB`
  of set 3 archive `$4D`, LZ, VRAM `$5400`) + the dash, centred on column `$10`; the digits are
  drawn by the task at columns `$11`, `$15`, `$16`. "WORLD" is wider than "ZONE": it takes
  tiles `$A6-$AB` + `$E7`/`$E8` (top) and `$B6-$BB` + `$F7`/`$F8` (bottom; past the archive's
  end, so the archive grows by 32 bytes: VRAM `$57B8-$57C7`, unused in stages and on the map). The
  new archive goes to `bulk`, the old one is freed. The arrangement is 14 wide (WORLD, gap,
  digit, gap, dash, gap) and lives in `free_e2` (set 4's arrangements are words in bank `$E2`).
* World map label (BG3, tiles 1-8 / `$11-$18` + the zone digit `$0A+`): set 3 archive `$0D`
  (raw, `$E3:D110`), redrawn in place.
The new letters are drawn at build time from SB5's own glyphs (O, R, E, M of the intro font):
W = M upside down, L = E without its upper bars, D = O with round right corners, rendered with
the fonts' outline/shadow rules (intro: outline all round + drop shadow 2 px down/right; map
label: colour bands by row + 1-px shadow). Preview: build/world_text_preview.png.
"""
import os
import zlib

import numpy as np
from PIL import Image

from .. import lz
from ..rombuild import BuildError
from ..romlib import off
from . import sb1_enemies

ARC_TABLE = 0xE3BE60          # archive entries (8 bytes), set 3 window starts at $E3:C158
SET3 = 0xE3C158
INTRO_ARC = 0x4D              # set 3: stage intro / HUD font, VRAM $5400 (tile $80), LZ
MAP_ARC = 0x0D                # set 3: world map label font, VRAM $5000, raw
INTRO_ARR = 0xE0              # set 4 arrangement "ZONE  -"
INTRO_TOP = [0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB, 0xE7, 0xE8]
INTRO_BOT = [0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB, 0xF7, 0xF8]


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


def _dilate(m):
    o = m.copy()
    h, w = m.shape
    p = np.zeros((h + 2, w + 2), bool)
    p[1:-1, 1:-1] = m
    for dy in range(3):
        for dx in range(3):
            o |= p[dy:dy + h, dx:dx + w]
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


def _render_intro(b):
    l1 = _dilate(b) & ~b
    s = _shift(b, 2, 2) & ~b & ~l1
    l2 = _dilate(s) & ~b & ~s & ~l1
    out = np.zeros(b.shape, int)
    out[l1 | l2] = 1
    out[s] = 2
    out[b] = 3
    return out


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
    font = bytearray(font) + bytearray(32)                       # tiles $F7, $F8
    for t in (0xE7, 0xE8):
        if any(font[(t - 0x80) * 16:(t - 0x7F) * 16]):
            raise BuildError(f"intro font tile ${t:02X} is not blank")
    masks = _glyphs(font)
    b, width = _word(masks, 2, 16, top=1)
    print(f'WORLD intro width {width}')
    b = np.roll(b, max(61 - width, 0), axis=1)                   # right-aligned: the digit follows
    intro = _render_intro(b)
    _put2bpp(font, 0x80, INTRO_TOP, INTRO_BOT, intro)
    new_src = rb.alloc("bulk", lz.compress(bytes(font)), "WORLD: stage intro font (set 3 archive $4D, + tile $F7)")
    rb.patch(ea, e, bytes([0x00, 0x54, 0x90, 0x07, new_src & 0xFF, (new_src >> 8) & 0xFF, new_src >> 16, 0x03]),
             "WORLD: set 3 archive $4D = the font with WORLD (two tiles longer)")
    # old font data: nothing else names it (one archive entry; the stock OBJ sheet table copy is freed)
    old = bytes(base_rom[off(src):off(src) + used])
    rb.free_old("free_d5_font", src + 1, used - 1, zlib.crc32(old[1:]),
                "freed SB5 stage intro font with ZONE (set 3 archive $4D, LZ); its first byte stays")

    # ---- the intro arrangement: WORLD (8), gap, digit (col 17), gap, dash, gap; centred on $10 (14 wide: col 8)
    words = [0x24 << 8 | t for t in INTRO_TOP] + [0x2080] * 3 + [0x208C] + [0x2080] * 2
    words += [0x24 << 8 | t for t in INTRO_BOT] + [0x2080] * 3 + [0x209C] + [0x2080] * 2
    lo = bytes(w & 0xFF for w in words)
    hi = bytes(w >> 8 for w in words)
    arr = bytes([14, 2, 0, 0, 0]) + lz.compress(lo) + lz.compress(hi) + b"\x00"
    tab = 0xC00000 | (rb.d[off(0xC08000 + 12)] | rb.d[off(0xC08000 + 13)] << 8 | rb.d[off(0xC08000 + 14)] << 16)
    slot = tab + 2 * (INTRO_ARR - 1)
    a = rb.alloc("free_e2", arr, "WORLD: stage intro arrangement (set 4 $E0)")
    if a >> 16 != tab >> 16:
        raise BuildError("WORLD arrangement outside the set 4 bank")
    rb.patch(slot, bytes([0x27, 0xDA]), bytes([a & 0xFF, (a >> 8) & 0xFF]), "WORLD: set 4 arrangement $E0")

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
        pal_i = [(255, 0, 255), (0, 24, 16), (64, 96, 0), (88, 216, 0)]
        pal_m = [(40, 0, 60), (60, 0, 0), (180, 90, 90), (255, 200, 200)]
        img = Image.new("RGB", (64, 34))
        for y in range(16):
            for x in range(64):
                img.putpixel((x, y), pal_i[intro[y, x]])
                img.putpixel((x, 18 + y), pal_m[label[y, x]])
        img.resize((256, 136), Image.NEAREST).save(os.path.join(out_dir, "world_text_preview.png"))


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
BOSSES = [                         # (boss stage, its first portal root, next stage)
    (0x67, 0xC71BE3, 0x69),        # 1-6, first duel
    (0x69, 0xC71F6D, 0x68),        # 1-6, second duel
    (0x68, 0xC71DC1, NEXT_WORLD),  # 1-7
]


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


def code(rb):
    from .. import asar
    region = rb.regions["bulk"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"ORG": f"${region.cursor:06X}", "KNIGHT_STAGE": f"${KNIGHT_STAGE:02X}"})
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
    return syms


KNIGHT_STAGE = 0x17      # 1-5 (SB1's 6-4): its knights (enemy type $08) take no hit from the front
# enemies kept (stage: types; the other type 04 roots that place an enemy `A2 x y type` go): 1-5 = SB1's 6-4,
# its two knights only
KEEP_ENEMIES = {0x17: {0x08}}


# script ops left out (stage: {type: [op prefixes]}): 1-4 is SB1's 4-4 now (features/sb1_stages.py), without
# SB5's clouds (its type 06 script draws them on BG1 with FF 8D DA 04 / FF 8D DB 04, set 4 arrangements)
DROP_OPS = {0x10: {0x06: [bytes.fromhex("FF 8D DA"), bytes.fromhex("FF 8D DB")]}}


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
            if sb1_enemies.stage_enemies(stage) is not None and any(t == 0x04 and rb.d[off(a)] == 0xA2
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


# ---------------------------------------------------------------------------------------------------------
# Music: Super Bomberman 1's own driver and songs in World 1 (asm/title_music.asm fd_sound, the map's
# foreign-driver code). SB1 cold-restarts its driver at every stage ($3E) and uploads ~54 KB: sound RAM
# $0800-end with the driver, the world's songs and the game SFX, then sends the world's start jingle and,
# ~3 s later, its song (port 0). assets/sound/sb1_stage_<w>.bin = that upload, taken in Mesen at the first
# command (tools/mesen/sb1_stages.lua FIRSTCMD). Worlds 1, 2, 4, 6 share one set: their images differ only
# in $0800-$22FF (driver variables, instrument table) and from $CD7C (the world's own samples), so the
# middle is stored once; the tail goes in the IPL upload list (above the loader's triples).
# Here SB5's stage set request (group 4: the screen is dark) uploads it instead, SB5's start jingle
# (group 0 $20) sends SB1's jingle and SB5's stage music (group 0 $06, bosses $0F) SB1's song.
SB1_STAGE = {     # name: (image, jingle, song) as port 0 commands without the toggle bit; 0 = none
    "w1": ("sb1_stage_w1.bin", 0x0D, 0x02),
    "w2": ("sb1_stage_w2.bin", 0x1E, 0x04),
    "w3": ("sb1_stage_w3.bin", 0x20, 0x06),
    "w4": ("sb1_stage_w4.bin", 0x22, 0x0B),
    "w6": ("sb1_stage_w6.bin", 0x26, 0x08),
    "w5": ("sb1_stage_w5.bin", 0x24, 0x14),
    "boss": ("sb1_stage_boss.bin", 0x00, 0x0A),
}
STAGE_MUSIC = {   # 1-1 World 1's, 1-2 World 2's (2-1), 1-3 World 3's (3-6), 1-4 World 4's (4-4),
    0x0D: "w1",   # 1-5 World 6's (6-4), 1-6 the tournament's (World 5), 1-7 the 2-8 boss's
    0x11: "w2",
    0x18: "w3",
    0x10: "w4",
    0x17: "w6",
    0x67: "w5",
    0x69: "w5",
    0x68: "boss",
}
FAMILY = ("w1", "w2", "w4", "w6")
SPLIT1, SPLIT2 = 0x2300, 0xCD7C   # own $0800-$22FF, shared $2300-$CD7B, own tail $CD7C-
# SB5 group-2 SFX (stages) -> SB1 SFX (port 1); 0 = silent. SB1: $1E bomb set, $15 explosion, $1F player
# death, $16 enemy death (tools/extract_sb1_sfx.py).
SB1_SFX = {0x06: 0x1E, 0x0C: 0x15}
SB1_DEATH, SB1_ENEMY = 0x1F, 0x16
SB1_ENTRY, SB1_READY = 0x0812, (0x68, 0x09)   # as the map's SB1 driver (features/world_map.py)


def stage_drivers(snd_dir):
    """Driver entries for world_map.sound(stages=): pieces (key, data, regions) uploaded one after the
    other from $0800, IPL extra blocks; and name -> index."""
    def img(name):
        return open(os.path.join(snd_dir, SB1_STAGE[name][0]), "rb").read()

    base = 0x0800
    out, index = [], {}
    shared = img(FAMILY[0])[SPLIT1 - base:SPLIT2 - base]
    for name in FAMILY:
        if img(name)[SPLIT1 - base:SPLIT2 - base] != shared:
            raise BuildError(f"SB1 stage music: {name}'s image differs from w1's in ${SPLIT1:04X}-${SPLIT2 - 1:04X}")
    big = {"w3": ["free_c8_sheets"], "w5": ["stream_ee"], "boss": ["free_c7_sheets", "free_c9_sheets"]}
    for name, (fn, jingle, song) in SB1_STAGE.items():
        data = img(name)
        if name in FAMILY:
            pieces = [(f"sb1 {name} $0800", data[:SPLIT1 - base], ["stream_ec", "free_c9_sheets", "obj_f7"]),
                      ("sb1 w1/w2/w4/w6 $2300", shared, ["stream_ed"])]
            extra = [(SPLIT2, data[SPLIT2 - base:])]
        else:
            data += bytes(-len(data) % 3)
            cut = len(data) if name != "boss" else 0xBFFD + 3     # boss: 48 KB in $C7, the rest elsewhere
            pieces = [(f"sb1 {name} $0800", data[:cut], big[name])]
            if cut < len(data):
                pieces.append((f"sb1 {name} ${base + cut:04X}", data[cut:], ["free_c9_sheets", "obj_f7"]))
            extra = []
        index[name] = len(out)
        out.append(dict(name=f"SB1 stage {name}", pieces=pieces, extra=extra, entry=SB1_ENTRY, ready=SB1_READY,
                        song=0x00, echo=0x00, sfx=(jingle, song)))
    return out, index


def stage_tables(rb, first, index):
    """$1031 -> driver (0 = SB5's music) and SB5 group-2 SFX -> SB1 SFX tables in bulk: asm defines."""
    t = bytearray(256)
    for stage, name in STAGE_MUSIC.items():
        t[stage] = first + index[name]
    s = bytearray(128)
    for k, v in SB1_SFX.items():
        s[k] = v
    ta = rb.alloc("bulk", bytes(t), "SB1 stage music: driver of each stage ($1031)")
    sa = rb.alloc("bulk", bytes(s), "SB1 stage music: SB5 group-2 SFX -> SB1 SFX (port 1)")
    return {"FD_STAGES": f"${ta:06X}", "FD_SB1SFX": f"${sa:06X}", "SB1_DEATH": f"${SB1_DEATH:02X}"}
