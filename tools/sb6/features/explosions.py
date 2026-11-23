"""Explosions drawn like Super Bomberman 6 (Unity): the fire of its sprite sheet (BombItems/Itens.png).

SB5's flames are BG tiles $010-$07F in palette 2 (set 0 archive $5D, LZ, at VRAM word $0100: 28 pictures of
16 x 16, tile n always in quadrant n & 3 of its cell): 7 kinds x 4 frames, kind k at tiles $10 + 16 k (right
end, down end, left end, up end, horizontal middle, vertical middle, center), frame f = 4 more. An explosion
cell shows frames 0 1 2 3 2 1 0, 4 stage frames each (word table $80:8BE6, `$C5:1EFA`). SB6 plays the same
shape: Weak, Medium, Strong, Maximum and back (its BombExplosion prefab, ItemSheetPrefabAuthoring.cs), with the
named cells of assets/items/sb6_items_sheet.png (= Itens.png): Explosion{Start,Middle,End}{Weak..Maximum} =
SB5's frames 0-3. Middle turned 90 degrees is the vertical middle, End (tip to the right) turned / mirrored the ends.

Colors: SB6's 6 fire colors go to palette 2 entries FIRE (8-13): set 6 palette 2, which every stage's set-up
loads after the stage's palettes (SB5's held its 5 fire colors for entries 11-15; World 1's own palettes get them
too, features/sb1_stages.py); the floor around an arena's flames (1-6, 1-7: flames on the field's own layer)
takes FLOOR (entries 1-7). A pierce bomb's flames are the normal ones: SB6's pink would need a BG palette of its
own, and every one is taken in a stage (0 and its BG3 halves: the HUD and the pause menu, 1 items, 2 flames,
3-7 the field).
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHEET = os.path.join(ROOT, "assets", "items", "sb6_items_sheet.png")

LEVELS = ("Weak", "Medium", "Strong", "Maximum")    # SB5's frames 0-3
FIRE = range(8, 14)                 # palette 2 entries of the 6 fire colors
FLOOR = range(1, 8)                 # palette 2 entries of the floor around an arena's flames
KINDS = ("right", "down", "left", "up", "hmid", "vmid", "center")   # tiles $10 + 16 * kind
FLAME_VRAM = 0x0100                 # word address of tile $010
ARCHIVE = 0x5C                      # index in the archive array $E3:BE60 (set 0 id $5D): flames
ARC_ENTRY = 0xE3BE60 + 8 * ARCHIVE
FIRE_PAL_WORD = 0xC19090            # set 6 palette table word of id 2 ($81:908E + 2): the fire colors
FIRE_PAL_OLD = 0xC190B8             # SB5's: [$2B, 5, 5 colors] (only set 6 id 2 names it)

# SB5 data replaced (docs/FREE_SPACE.md): the flame archive's LZ stream but its first byte (the archive before
# it reads one byte past its own stream), and the items' stream right after it (features/items.py replaces it;
# only the flames' archive read past it). Both are named by no other archive entry (the stock OBJ sheet table
# copy names them as sheets $5D / $5E, which no object asks for).
OLD_DATA = [("free_c0_flames", 0xC06001, 2953, 0x678B330B, "was SB5's flame tiles (set 0 archive $5D, LZ)"),
            ("free_c0_items", 0xC06B8A, 2470, 0x9003C426, "was SB5's item tiles (set 0 archive $5E, LZ)"),
            ("free_81_fire", 0xC190B8, 14, 0x541101DA, "was SB5's fire colors (set 6 palette 2), bank $81")]
FREED = ["free_c0_flames", "free_c0_items"]
ALLOC = FREED + ["free_d3", "free_db_b", "bulk"]    # where the new archives go (freed SB5 data first: bank $E4 is nearly full)


def free_old(rb):
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)


def _sheet():
    img = np.asarray(Image.open(SHEET).convert("RGBA"))
    meta = open(SHEET + ".meta", encoding="utf-8").read()
    cells = {}
    for m in re.finditer(r"name: (\S+)\s+rect:\s+serializedVersion: 2\s+x: (\d+)\s+y: (\d+)\s+width: (\d+)"
                         r"\s+height: (\d+)", meta):
        x, y, w, h = (int(v) for v in m.group(2, 3, 4, 5))
        top = img.shape[0] - y - h
        cells[m.group(1)] = img[top:top + h, x:x + w]
    return cells


def _parts():
    """{(part, frame): 16 x 16 RGBA} of the normal explosion."""
    cells = _sheet()
    out = {}
    for part in ("Start", "Middle", "End"):
        for f, lv in enumerate(LEVELS):
            c = cells.get(f"Explosion{part}{lv}")
            if c is None or c.shape != (16, 16, 4):
                raise BuildError(f"explosions: Explosion{part}{lv} is not a 16 x 16 cell of the sheet")
            out[part, f] = c
    return out


def _colors():
    """SB6's fire colors, darkest first."""
    seen = {}
    for a in _parts().values():
        for px in a.reshape(-1, 4):
            if px[3]:
                seen[tuple(int(v) for v in px[:3])] = 1
    cols = sorted(seen, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    if len(cols) != len(FIRE):
        raise BuildError(f"explosions: {len(cols)} fire colors, expected {len(FIRE)}")
    return cols


def bgr555(c):
    return (c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10


def fire_words():
    return [bgr555(c) for c in _colors()]


def pictures():
    """{(kind, frame): 16 x 16 color indices (0 = no fire, FIRE = the fire colors)}."""
    lut = {c: FIRE.start + i for i, c in enumerate(_colors())}
    parts = _parts()
    out = {}

    def idx(a):
        t = np.zeros((16, 16), np.int32)
        for y in range(16):
            for x in range(16):
                if a[y, x, 3]:
                    t[y, x] = lut[tuple(int(v) for v in a[y, x, :3])]
        return t

    for f in range(4):
        start, mid, end = idx(parts["Start", f]), idx(parts["Middle", f]), idx(parts["End", f])   # end: tip right
        out["right", f] = end
        out["left", f] = end[:, ::-1]
        out["down", f] = np.rot90(end, -1)                     # tip down
        out["up", f] = np.rot90(end, 1)
        out["hmid", f] = mid
        out["vmid", f] = np.rot90(mid, 1)
        out["center", f] = start
    return out


def tiles(floor=None):
    """Tiles $010-$07F (3584 bytes). floor: optional 16 x 16 palette 2 indices shown around the fire (an
    arena's floor cell; see-through without it)."""
    pics = pictures()
    data = bytearray()
    for k, kind in enumerate(KINDS):
        for f in range(4):
            p = pics[kind, f].copy()
            if floor is not None:
                p[p == 0] = floor[p == 0]
            for q in range(4):
                data += encode_4bpp(p[8 * (q >> 1):8 * (q >> 1) + 8, 8 * (q & 1):8 * (q & 1) + 8])
    return bytes(data)


def fire_mask(tile_no):
    """8 x 8 color indices of BG tile tile_no ($010-$07F) in the see-through set (tests)."""
    t = tile_no - 0x10
    k, f, q = t // 16, (t // 4) & 3, t & 3
    p = pictures()[KINDS[k], f]
    return p[8 * (q >> 1):8 * (q >> 1) + 8, 8 * (q & 1):8 * (q & 1) + 8]


def fire_palette(rb):
    """Set 6 palette 2 (loaded by every stage's set-up, `$C5:13DC`, after the stage's palettes): SB5's 5 fire colors
    for palette 2 entries 11-15 -> SB6's in entries FIRE (a new entry in bank $81; the old one is freed)."""
    blob = struct.pack("<HH", 0x20 + FIRE.start, len(FIRE)) + b"".join(struct.pack("<H", w) for w in fire_words())
    a = rb.alloc("bank81", blob, f"explosions: SB6 fire colors (set 6 palette 2: palette 2 entries "
                                 f"{FIRE.start}-{FIRE.stop - 1})")
    rb.patch(FIRE_PAL_WORD, struct.pack("<H", FIRE_PAL_OLD & 0xFFFF), struct.pack("<H", a & 0xFFFF),
             "explosions: set 6 palette 2 -> SB6's fire colors")
    return a


# $C5:1F28 (flame cell X, M/X 8-bit, DB $80): SB5 leaves a cell's flame out only when the flames are on the field's
# own layer and `$1152` bit 7; a soft block burning in the cell (`$1052` bit $20, a pierce bomb's flames go through
# it) got a flame on BG1 over its burning picture on BG2 (World 1). Now that cell never gets one, as in SB5.
SKIP_AT = 0xC51F28
SKIP_OLD = bytes.fromhex("AD 61 0F CD 7C 1B D0 07 BD 52 11 89 80 D0 45")
SKIP_CODE = bytes.fromhex("BD 52 10 89 20 D0 11 AD 61 0F CD 7C 1B D0 07 BD 52 11 89 80 D0 02 18 60 38 60")


def apply(rb):
    """Flame tiles (archive; after free_old) and no flame over a burning soft block."""
    at = rb.alloc("c5", SKIP_CODE, "explosions: no flame on a cell whose soft block burns (bank $C5)")
    jsr = bytes([0x20, at & 0xFF, at >> 8 & 0xFF])
    # JSR check / BCS $1F7C (skip the cell) / BRA $1F37 (draw it) / NOPs
    rb.patch(SKIP_AT, SKIP_OLD, jsr + bytes.fromhex("B0 4F 80 08") + bytes([0xEA] * 8),
             "explosions: a burning soft block's cell gets no flame")
    packed = lz.compress(tiles())
    a = rb.alloc(ALLOC, packed, "explosions: SB6 flame tiles (set 0 archive $5D, LZ)")
    ent = bytes(rb.d[off(ARC_ENTRY):off(ARC_ENTRY) + 8])
    if ent[2:4] != b"\x00\x0E":
        raise BuildError("explosions: unexpected flame archive entry")
    rb.patch(ARC_ENTRY + 4, ent[4:7], a.to_bytes(3, "little"), "explosions: flame archive -> SB6 tiles")
    return dict(lz=len(packed), at=a)
