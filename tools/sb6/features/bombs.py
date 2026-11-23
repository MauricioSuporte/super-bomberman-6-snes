"""Bombs drawn like Super Bomberman 6 (Unity): the bomb sprites of its sheet (BombItems/Itens.png).

SB5's bombs are 16 x 16 OBJ pieces (type 0 animations, one piece per mapping) in OBJ palette 0, from set 0
archive $23 (index $22, LZ, $C00 bytes = 96 tiles from OBJ tile $0E0, stored as column pairs: archive tile
32 r + 2 c + line is VRAM tile $0E0 + 32 r + 16 line + c). Pictures (VRAM tile of the 16 x 16 piece):
  normal  $10C large, $10E medium, $120 small (12 frames each: large medium small medium)
  pierce  $128 / $12A / $12C (the same)
  remote  $122 / $124 / $126 (8 frames each: 1 2 3 2)
  slow fuse (ability $40, SB6's search bomb)  $EC (30 frames) / $EE (10 frames)
  mine    $12E (no SB6 picture: SB5's, in SB6's blues)
SB6's sheet cells (by name in its .meta) take their place. Their animations are SB6's shapes too: normal and pierce
medium large medium small (SB6) = SB5's order from another frame; the control bomb's frames 1-3 for SB5's 3.

Colors: OBJ palette 0 of a stage is set 0 palette id $58 ($81:881A, 16 colors). Its entries 1-4 (a navy ramp)
are used only by these bomb pictures (the OBJ flames use 5-8 and 15, the smoke 10-15, the mine 1-3, 7, 14, 15),
so they become SB6's blues (BLUES); entry 9 (a dark red only SB5's remote / slow fuse bombs used) becomes a gray
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
EXTRA = {9: (96, 96, 104), 14: (40, 32, 40)}
FREE_ENTRIES = (4, 9)               # no SB5 picture kept in the archive uses them
# SB6's bomb blues, darkest first (BombLarge's own colors)
BLUES = ((23, 13, 87), (39, 70, 194), (24, 120, 248), (184, 232, 248))
CELLS = {
    0x10C: "BombLarge", 0x10E: "BombMedium", 0x120: "BombSmall",
    0x128: "PierceBombLarge", 0x12A: "PierceBombMedium", 0x12C: "PierceBombSmall",
    0x122: "ControlBombFrame1", 0x124: "ControlBombFrame2", 0x126: "ControlBombFrame3",
    0x0EC: "SearchBombFrame1", 0x0EE: "SearchBombFrame2",
}
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
    """{VRAM tile: 16 x 16 palette 0 entries} and the mean Lab error."""
    cells = _cells()
    pal = [rgb(w) for w in palette(rom)]
    use = [e for e in range(1, 16) if e not in SMOKE]
    plab = _lab([pal[e] for e in use])
    out, err, n = {}, 0.0, 0
    for t, name in CELLS.items():
        c = cells.get(name)
        if c is None or c.shape != (16, 16, 4):
            raise BuildError(f"bombs: {name} is not a 16 x 16 cell of the sheet")
        a = np.zeros((16, 16), np.int32)
        for y in range(16):
            for x in range(16):
                if c[y, x, 3]:
                    d = np.linalg.norm(plab - _lab([c[y, x, :3]])[0], axis=1)
                    j = int(np.argmin(d))
                    err += float(d[j])
                    n += 1
                    a[y, x] = use[j]
        out[t] = a
    return out, err / max(n, 1)


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


def archive(rom, pics):
    src = int.from_bytes(ENTRY[4:7], "little")
    data, _ = lz.decompress(bytes(rom[off(src):off(src) + SIZE * 2]), SIZE)
    data = bytearray(data[:SIZE])
    for t, a in pics.items():
        for dy in (0, 1):
            for dx in (0, 1):
                k = _k(t + 16 * dy + dx)
                data[32 * k:32 * k + 32] = encode_4bpp(a[8 * dy:8 * dy + 8, 8 * dx:8 * dx + 8])
    return bytes(data)


def apply(rb, base_rom, sheets, preview=None):
    """After free_old (SB5's stream is read from the base ROM), before sheets.finish()."""
    i = 8 * ARCHIVE
    if bytes(rb.d[off(ARC_ENTRY):off(ARC_ENTRY) + 8]) != ENTRY or bytes(sheets.entries[i:i + 8]) != ENTRY:
        raise BuildError("bombs: unexpected archive entry")
    pics, err = pictures(rb.d)
    data = archive(base_rom, pics)
    for t in range(FIRST_TILE, FIRST_TILE + SIZE // 32, 2):
        if (t - FIRST_TILE) // 16 % 2 or t in pics:
            continue
        for dy in (0, 1):
            for dx in (0, 1):
                k = _k(t + 16 * dy + dx)
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
        _preview(pics, words, preview)
    return dict(lz=len(packed), at=a, error=err, pictures=len(pics))


def _preview(pics, words, path):
    pal = [rgb(w) for w in words]
    im = Image.new("RGB", (18 * len(pics), 18), (255, 0, 255))
    for n, (t, a) in enumerate(sorted(pics.items())):
        for y in range(16):
            for x in range(16):
                if a[y, x]:
                    im.putpixel((18 * n + x, y), pal[a[y, x]])
    im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(path)
