"""Bombs drawn like Super Bomberman 6 (Unity): the bomb sprites of its sheet (BombItems/Itens.png).

SB5's bombs are 16 x 16 OBJ pieces (type 0 animations, one piece per mapping) in OBJ palette 0, from set 0
archive $23 (index $22, LZ, $C00 bytes = 96 tiles from OBJ tile $0E0, stored as column pairs: archive tile
32 r + 2 c + line is VRAM tile $0E0 + 32 r + 16 line + c). Pictures (VRAM tile of the 16 x 16 piece):
  normal  $10C large, $10E medium, $120 small (12 frames each: large medium small medium)
  pierce  $128 / $12A / $12C (the same)
  control $122 / $124 / $126 (remote bombs: 8 frames each, 1 2 3; SB5 played 1 2 3 2)
  search  $EC (30 frames) / $EE (10 frames): ability $40 (SB5's bomb that chases the nearest rival)
  magnet  $12E large / $100 medium / $102 small (ability $20, SB5's mine: animation 4 = medium large medium small,
          12 frames each, Unity's order; features/magnet.py)
SB6's sheet cells (by name in its .meta) or the owner's pictures in assets/bombs (FILES) take their place.

Freed for the magnet bomb's medium and small frames (REMAP): the flash of SB5's enemy death puff ($101, $110:
animation 6 now starts at its third mapping) and its last frame ($102 / $103 / $112 / $113, mapping 23: nothing is
drawn then), the shadow under a bomber mounting a Louie ($0EB / $0FB: animation $0A shows nothing) and $111 (no
picture). The puff's small smoke (8 x 8 $100) moves to $0FB, $0EB is left blank; SB5 mappings no animation of the
Normal Game shows (pieces over these tiles) keep only an 8 x 8 corner or a blank tile. SB5's mine picture ($12E)
is the magnet bomb's large frame. Mappings 16 and 17 (the puff's flash) become its medium and small frames.

Colors: OBJ palette 0 of a stage is set 0 palette id $58 ($81:881A, 16 colors). Its entries 1-4 (a navy ramp)
are used only by these bomb pictures (the OBJ flames use 5-8 and 15, the smoke 10-15, the mine 1-3, 7, 14, 15),
so they become SB6's blues (BLUES); entry 9 (a dark red only SB5's remote / search bombs used) becomes a gray
and the outline 14 a neutral near-black (EXTRA: the control bomb's helmet, the search bomb's black body, which
came out purple / brown). Every SB6 pixel is drawn with the nearest of the palette's colors but the smoke's
(SMOKE). The SB5 pictures kept in the archive must not use the entries changed here (checked).
"""
import os
import re
import struct

import numpy as np
from PIL import Image

from .. import lz
from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp
from . import explosions

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHEET = os.path.join(ROOT, "assets", "items", "sb6_items_sheet.png")

ARCHIVE = 0x22                      # index in $E3:BE60 (set 0 id $23)
ARC_ENTRY = 0xE3BE60 + 8 * ARCHIVE
ENTRY = bytes.fromhex("00 00 00 0C 00 D4 CA 05")
SIZE = 0xC00
FIRST_TILE = 0x0E0
PALETTE = 0xC1881A                  # set 0 palette id $58: [dest $80, count $10, 16 colors]
OLD_BLUES = (0x34C6, 0x496B, 0x5A0F, 0x7AF5)
BLUE_ENTRIES = (1, 2, 3, 4)
SMOKE = (8, 10, 11, 12, 13)         # dark red and tans of the OBJ flames / smoke: SB6's grays would turn brown
OLD_EXTRA = {9: 0x1C50, 14: 0x1866}
EXTRA = {9: (112, 120, 144), 14: (40, 32, 40)}   # 9: the control bomb's helmet gray
FREE_ENTRIES = (4, 9)               # no SB5 picture kept in the archive uses them
# SB6's bomb blues, darkest first (BombLarge's own colors)
BLUES = ((23, 13, 87), (39, 70, 194), (24, 120, 248), (184, 232, 248))
CELLS = {
    0x10C: "BombLarge", 0x10E: "BombMedium", 0x120: "BombSmall",
    0x128: "PierceBombLarge", 0x12A: "PierceBombMedium", 0x12C: "PierceBombSmall",
}
# the owner's pictures (assets/bombs, 16 x 16 frames side by side): VRAM tile -> (file, frame)
BOMBS_DIR = os.path.join(ROOT, "assets", "bombs")
FILES = {
    0x122: ("ControlBomb.png", 0), 0x124: ("ControlBomb.png", 1), 0x126: ("ControlBomb.png", 2),
    0x12E: ("MagnetBomb.png", 0), 0x100: ("MagnetBomb.png", 1), 0x102: ("MagnetBomb.png", 2),
}
# the search bomb in 8 x 8 tiles (SearchBombSliced.png; frames 3-4's lower left corner, the eye turned right, from
# SearchBombMounted.png): VRAM tile -> (file, x, y); its 4 frames are mappings (SEARCH_FRAMES)
TILES8 = {
    0x0EC: ("SearchBombSliced.png", 0, 0), 0x0ED: ("SearchBombSliced.png", 8, 0),
    0x0FC: ("SearchBombSliced.png", 0, 8), 0x0FD: ("SearchBombSliced.png", 8, 8),
    0x0EE: ("SearchBombSliced.png", 16, 8), 0x0EF: ("SearchBombSliced.png", 24, 8),
    0x0FE: ("SearchBombSliced.png", 32, 8), 0x0FF: ("SearchBombMounted.png", 32, 8),
}
# 8 x 8 tiles: new tile <- SB5's tile (None = blank), before the pictures are drawn
MOVES = {0x0FB: 0x100, 0x0EB: None}
FREED = (0x101, 0x110, 0x111, 0x102, 0x103, 0x112, 0x113, 0x0EB, 0x0FB)   # no SB5 picture left there (REMAP)
BLANK = 0x0EB
# SB5's LZ stream of archive $23: named only by the archive entry and the stock OBJ sheet table's copy of it
# (sheet $23; objsheets.ObjSheets copies that table before freeing it): both name SB6's (docs/FREE_SPACE.md)
OLD_DATA = [("free_ca_bombs", 0xCAD400, 2494, 0xB0BBDC68, "was SB5's bomb sprites (set 0 archive $23, LZ)")]
ALLOC = ["free_ca_bombs"] + explosions.ALLOC


def free_old(rb):
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)


def _cells():
    img = np.asarray(Image.open(SHEET).convert("RGBA"))
    meta = open(SHEET + ".meta", encoding="utf-8").read()
    out = {}
    for t, (name, k) in FILES.items():
        own = np.asarray(Image.open(os.path.join(BOMBS_DIR, name)).convert("RGBA"))
        out[name, k] = own[:16, 16 * k:16 * k + 16]
    for m in re.finditer(r"name: (\S+)\s+rect:\s+serializedVersion: 2\s+x: (\d+)\s+y: (\d+)\s+width: (\d+)"
                         r"\s+height: (\d+)", meta):
        x, y, w, h = (int(v) for v in m.group(2, 3, 4, 5))
        top = img.shape[0] - y - h
        out[m.group(1)] = img[top:top + h, x:x + w]
    return out


def _lab(rgb):
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def bgr555(c):
    return (int(c[0]) >> 3) | (int(c[1]) >> 3) << 5 | (int(c[2]) >> 3) << 10


def rgb(w):
    return ((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3)


def palette(rom):
    """OBJ palette 0 of a stage with SB6's blues: 16 BGR555 words."""
    o = off(PALETTE)
    if bytes(rom[o:o + 4]) != bytes.fromhex("80 00 10 00"):
        raise BuildError("bombs: unexpected palette $58")
    words = list(struct.unpack_from("<16H", rom, o + 4))
    for e, c in list(zip(BLUE_ENTRIES, BLUES)) + list(EXTRA.items()):
        words[e] = bgr555(c)
    return words


def pictures(rom):
    """{VRAM tile: 16 x 16 palette 0 entries}, {VRAM tile: 8 x 8 entries} and the mean Lab error."""
    cells = _cells()
    pal = [rgb(w) for w in palette(rom)]
    use = [e for e in range(1, 16) if e not in SMOKE]
    plab = _lab([pal[e] for e in use])
    tot = [0.0, 0]

    def quant(c):
        a = np.zeros(c.shape[:2], np.int32)
        for y in range(c.shape[0]):
            for x in range(c.shape[1]):
                if c[y, x, 3]:
                    d = np.linalg.norm(plab - _lab([c[y, x, :3]])[0], axis=1)
                    j = int(np.argmin(d))
                    tot[0] += float(d[j])
                    tot[1] += 1
                    a[y, x] = use[j]
        return a

    out = {}
    for t, name in list(CELLS.items()) + list(FILES.items()):
        c = cells.get(name)
        if c is None or c.shape != (16, 16, 4):
            raise BuildError(f"bombs: {name} is not a 16 x 16 cell of the sheet")
        out[t] = quant(c)
    small = {}
    for t, (name, x, y) in TILES8.items():
        img = np.asarray(Image.open(os.path.join(BOMBS_DIR, name)).convert("RGBA"))
        small[t] = quant(img[y:y + 8, x:x + 8])
    return out, small, tot[0] / max(tot[1], 1)


def _planar(raw):
    """8 x 8 color indices of a 4bpp tile."""
    t = np.zeros((8, 8), np.int32)
    for y in range(8):
        for b in range(4):
            v = raw[2 * y + (b & 1) + 16 * (b >> 1)]
            for x in range(8):
                t[y, x] |= ((v >> (7 - x)) & 1) << b
    return t


def _k(t):
    """Archive tile of VRAM OBJ tile t."""
    r, rest = divmod(t - FIRST_TILE, 32)
    line, c = divmod(rest, 16)
    return 32 * r + 2 * c + line


def archive(rom, pics, small=None):
    src = int.from_bytes(ENTRY[4:7], "little")
    data, _ = lz.decompress(bytes(rom[off(src):off(src) + SIZE * 2]), SIZE)
    data = bytearray(data[:SIZE])
    old = bytes(data)
    for t, src in MOVES.items():
        k = _k(t)
        data[32 * k:32 * k + 32] = bytes(32) if src is None else old[32 * _k(src):32 * _k(src) + 32]
    for t, a in pics.items():
        for dy in (0, 1):
            for dx in (0, 1):
                k = _k(t + 16 * dy + dx)
                data[32 * k:32 * k + 32] = encode_4bpp(a[8 * dy:8 * dy + 8, 8 * dx:8 * dx + 8])
    for t, a in (small or {}).items():
        k = _k(t)
        data[32 * k:32 * k + 32] = encode_4bpp(a)
    return bytes(data)


def apply(rb, base_rom, sheets, preview=None):
    """After free_old (SB5's stream is read from the base ROM), before sheets.finish()."""
    i = 8 * ARCHIVE
    if bytes(rb.d[off(ARC_ENTRY):off(ARC_ENTRY) + 8]) != ENTRY or bytes(sheets.entries[i:i + 8]) != ENTRY:
        raise BuildError("bombs: unexpected archive entry")
    pics, small, err = pictures(rb.d)
    data = archive(base_rom, pics, small)
    ours = {p + d for p in pics for d in (0, 1, 16, 17)} | set(MOVES) | set(small)
    for t in range(FIRST_TILE, FIRST_TILE + SIZE // 32):
        if t in ours:
            continue
        k = _k(t)
        used = set(_planar(data[32 * k:32 * k + 32]).ravel().tolist())
        if used & set(FREE_ENTRIES):
            raise BuildError(f"bombs: SB5's OBJ tile ${t:03X} uses palette entries {FREE_ENTRIES}")
    packed = lz.compress(data)
    a = rb.alloc(ALLOC, packed, "bombs: SB6 bomb sprites (set 0 archive $23, LZ)")
    rb.patch(ARC_ENTRY + 4, ENTRY[4:7], a.to_bytes(3, "little"), "bombs: bomb sprite archive -> SB6's")
    sheets.entries[i + 4:i + 7] = a.to_bytes(3, "little")     # OBJ sheet $23 (the relocated table's copy)
    words = palette(rb.d)
    o = off(PALETTE) + 4
    old = bytes(rb.d[o + 2:o + 10])
    if struct.unpack("<4H", old) != OLD_BLUES:
        raise BuildError("bombs: unexpected bomb colors in palette $58")
    rb.patch(PALETTE + 6, old, struct.pack("<4H", *words[1:5]), "bombs: SB6's bomb blues (palette $58 entries 1-4)")
    for e, w in OLD_EXTRA.items():
        rb.patch(PALETTE + 4 + 2 * e, struct.pack("<H", w), struct.pack("<H", words[e]),
                 f"bombs: palette $58 entry {e} for SB6's bombs")
    if preview:
        full = dict(pics)
        for f in SEARCH_FRAMES:
            full[0x200 + len(full)] = _frame(small, f)
        _preview(full, words, preview)
    return dict(lz=len(packed), at=a, error=err, pictures=len(pics) + len(SEARCH_FRAMES))


def _frame(small, f):
    a = np.zeros((16, 16), np.int32)
    for t, dx, dy in f:
        a[dy:dy + 8, dx:dx + 8] = small[t]
    return a


def _preview(pics, words, path):
    pal = [rgb(w) for w in words]
    im = Image.new("RGB", (18 * len(pics), 18), (255, 0, 255))
    for n, (t, a) in enumerate(sorted(pics.items())):
        for y in range(16):
            for x in range(16):
                if a[y, x]:
                    im.putpixel((18 * n + x, y), pal[a[y, x]])
    im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(path)


# Type 0 animations ($85:81EE + 2 (n - 1), [mapping, frames]..., a pair with 0 frames restarts; mapping 0 shows
# nothing) and mappings ($85:8000 + 2 (id - 1), [count, (x, y, tile - $E0, attr: bit 0 = 16 x 16)...]).
ANIMS, MAPS = 0xC581EE, 0xC58000
MAGNET_ANIM = 4
MAGNET_FRAMES = 12
MAGNET_SEQ = [16, 10, 16, 17]        # medium ($100), large (mapping 10 = $12E), medium, small ($102)
DEATH_ANIM = 6                       # SB5's enemy death puff: mappings 16 17 (the flash) 18 (small smoke) 19-23
DEATH_LAST = 23                      # its last frame (16 x 16 $102): mapping 0 (nothing) for its 7 frames
SHADOW_ANIM = 0x0A                   # mapping 39: the shadow under a bomber jumping onto a Louie
CONTROL_LOOP = 0xC5833D              # animation 2's 4th pair (mapping 15 = frame 2 mirrored)
SEARCH_ANIM, SEARCH_MAPS, SEARCH_TIME = 5, (11, 12, 13, 14), 10
SEARCH_TOP = (-13, -14, -15, -14)    # SB5's float: its mappings 11-14 drew the bomb 4-6 pixels above a normal one
# the search bomb's frames: (8 x 8 tile, x, y in the 16 x 16 picture)
SEARCH_FRAMES = [
    [(0x0EC, 0, 0), (0x0ED, 8, 0), (0x0FC, 0, 8), (0x0FD, 8, 8)],
    [(0x0EC, 0, 0), (0x0ED, 8, 0), (0x0EE, 0, 8), (0x0EF, 8, 8)],
    [(0x0EC, 0, 0), (0x0ED, 8, 0), (0x0FF, 0, 8), (0x0EF, 8, 8)],
    [(0x0EC, 0, 0), (0x0ED, 8, 0), (0x0FF, 0, 8), (0x0FE, 8, 8)],
]
REUSED = {16: (0x100, 0x21), 17: (0x102, 0x21)}   # the magnet bomb's medium and small frames


def _w(d, a):
    return d[off(a)] | d[off(a) + 1] << 8


def _piece(x, y, tile, attr):
    t = (tile - 0xE0) & 0x1FF
    return struct.pack("<hhH", x, y, t) + bytes([attr])


def remap(rb):
    """After ObjSheets.finish() (the magnet bomb's animation goes into free_c5_sheets, bank $85)."""
    d = rb.d
    ptr = ANIMS + 2 * (DEATH_ANIM - 1)
    a = 0xC50000 | _w(d, ptr)
    if bytes(d[off(a):off(a) + 6]) != bytes.fromhex("10 03 11 04 12 06"):
        raise BuildError("bombs: unexpected death puff animation")
    rb.patch(ptr, struct.pack("<H", a & 0xFFFF), struct.pack("<H", a + 4 & 0xFFFF),
             "bombs: enemy death puff starts at its small smoke (its flash's tiles are the magnet bomb's)")
    last = a + 4 + 2 * 5                 # (the 6th pair from its new start: mapping 23, 7 frames)
    rb.patch(last, bytes([DEATH_LAST, 7]), bytes([0, 7]),
             "bombs: enemy death puff's last frame shows nothing (its tiles are the magnet bomb's)")
    a = 0xC50000 | _w(d, ANIMS + 2 * (SHADOW_ANIM - 1))
    rb.patch(a, bytes([39, 0xFF]), bytes([0, 0xFF]), "bombs: no shadow under a bomber mounting a Louie (magnet bomb)")
    rb.patch(CONTROL_LOOP, bytes.fromhex("0F 08 00 00"), bytes.fromhex("00 00 00 00"),
             "bombs: control bomb frames 1 2 3 (not mirrored)")
    for m, (tile, attr) in REUSED.items():
        a = 0xC50000 | _w(d, MAPS + 2 * (m - 1))
        old = bytes(d[off(a):off(a) + 8])
        if old[0] != 4:
            raise BuildError(f"bombs: unexpected mapping {m}")
        rb.patch(a, old, bytes([1]) + _piece(-8, -9, tile, attr), f"bombs: mapping {m} = a magnet bomb frame")
    script = b"".join(bytes([m, MAGNET_FRAMES]) for m in MAGNET_SEQ) + bytes(2)
    s = rb.alloc("free_c5_sheets", script, "bombs: magnet bomb animation (type 0 animation 4, bank $85)")
    ptr = ANIMS + 2 * (MAGNET_ANIM - 1)
    a = 0xC50000 | _w(d, ptr)
    if bytes(d[off(a):off(a) + 2]) != bytes([10, 0xFF]):
        raise BuildError("bombs: unexpected animation 4")
    rb.patch(ptr, struct.pack("<H", a & 0xFFFF), struct.pack("<H", s & 0xFFFF), "bombs: magnet bomb animation")
    # the search bomb: 4 frames of 8 x 8 pieces (the first one a single 16 x 16 piece), new mapping data
    a = 0xC50000 | _w(d, ANIMS + 2 * (SEARCH_ANIM - 1))
    want = b"".join(bytes([m, SEARCH_TIME]) for m in SEARCH_MAPS) + bytes(2)
    if bytes(d[off(a):off(a) + len(want)]) != want:
        raise BuildError("bombs: unexpected search bomb animation")
    for m, f, top in zip(SEARCH_MAPS, SEARCH_FRAMES, SEARCH_TOP):
        if f == SEARCH_FRAMES[0]:
            data = bytes([1]) + _piece(-8, top, 0x0EC, 0x21)
        else:
            data = bytes([len(f)]) + b"".join(_piece(x - 8, y + top, t, 0x20) for t, x, y in f)
        at = rb.alloc("free_c5_sheets", data, f"bombs: search bomb frame (type 0 mapping {m}, bank $85)")
        ptr = MAPS + 2 * (m - 1)
        rb.patch(ptr, bytes(d[off(ptr):off(ptr) + 2]), struct.pack("<H", at & 0xFFFF),
                 f"bombs: mapping {m} = a search bomb frame")
    # every other mapping drawing the freed tiles
    changed = []
    for m in range(1, 0xF8):
        if m in REUSED or m in SEARCH_MAPS:
            continue
        a = 0xC50000 | _w(d, MAPS + 2 * (m - 1))
        n = d[off(a)]
        for i in range(n):
            p = a + 1 + 7 * i
            x, y, t, attr = struct.unpack("<hhHB", bytes(d[off(p):off(p) + 7]))
            tile = (t + 0xE0) & 0x1FF
            big = attr & 1
            cover = {tile, tile + 1, tile + 16, tile + 17} if big else {tile}
            if not cover & (set(FREED) | {0x100}):
                continue
            if tile == 0x100:
                new = 0x0FB                   # the small smoke's new place
            elif tile in FREED:
                new = BLANK
            else:
                new = tile                    # a 16 x 16 piece over freed tiles: its own corner only
            if not big and new == tile:
                continue
            rb.patch(p, bytes(d[off(p):off(p) + 7]), _piece(x, y, new, attr & ~1),
                     f"bombs: mapping {m} off the magnet bomb's tiles")
            changed.append(m)
    return dict(anim=s, mappings=sorted(set(changed)))
