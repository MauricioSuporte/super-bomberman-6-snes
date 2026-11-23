"""The stage egg drawn and animated like Super Bomberman 6's (Unity EggClassic, the Louie eggs' idle loop).

SB5's egg (mount character 9: type 0 object, animation $15, [sheet $1A, row 2]) bobs one 16 x 16 body over a
shadow of two 8 x 8 pieces (type 0 mappings $40-$42, script $85:8825). Its page is lines 2-3 of sheet $1A
(raw, $CA:0800; mapping tile = 16 line + column from the sheet's top): columns 0-5 are a Louie's (character 2's
animations), 6-9 the egg's, 10-15 empty, so the egg owns columns 6-15 (20 tiles).

SB6's ground egg (Resources/Items/*LouieEgg.prefab) plays EggClassic frames 0 1 2 3 0 1 2 3 7 4 5 6 7 1, 0.133 s
each (8 SNES frames), then waits 0.5 s on the last one. Those 8 frames are 3 egg bodies (0 = 7, 1 = 3 = 4 = 5,
2 = 6) at several heights and 4 shadows (the rest frames' union, 4, 5, 6): 3 16 x 16 bodies + 4 16 x 8 shadows =
the 20 tiles. The 18-column pictures lose the two columns most like their neighbours (the same ones in every
frame). Each frame is a mapping (body in front, shadow under it) in new tables (`objmap`); asm/bombers.asm gives
them to type 0 objects in animation EGG_ANIM (bomber_map / bomber_anim, as the SB1 enemies' tables).

Colors: SB6's egg is white / pale blue with green spots: palette id $51 (the green Louie's: white, pale blues,
greens) holds those colors, so the egg takes $51 instead of the pink Louie's $52 ($80:C40B + 9 and the two
`LDA #$52 / JSR $53EB`) and shares a half with a green Louie. Pixels use entries 8-15 only (asm/louies.asm makes
the half copy with pixels 9-15 -> 1-7 from these tiles).
"""
import os
import re
import struct

import numpy as np
from PIL import Image

from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHEET = os.path.join(ROOT, "assets", "eggs", "EggClassic.png")
EGG_SHEET = 0xCA0800                # sheet $1A (Louie sheets, uncompressed): 16 tiles a line
LINES = (2, 3)                      # [sheet $1A, row 2] = lines 2 and 3
COLUMNS = range(6, 16)              # the egg's columns of those lines
PAL_TABLE = 0x80C40B                # palette id per mount character
EGG_CHAR = 9
OLD_PAL, PAL = 0x52, 0x51
LDA_PAL = (0xC45078, 0xC45140)      # LDA #$52 / JSR $53EB (palette half): an egg out of a block, a dropped one
EGG_ANIM = 0x15                     # type 0 animation of the egg (`$079F` + object)
OLD_SCRIPT = bytes.fromhex("40 08 41 07 42 08 41 07 00 00")     # $85:8825 (kept: type 0's ids are all taken)
BG = (248, 16, 64)                  # the Unity sheet's background
SHADOW = (0, 0, 0)
# SB6's colors -> entries of id $51 (8 outline, 9-15: mint, green, dark green, brown, pale blue, blue, white)
COLORS = {(255, 251, 255): 15, (248, 248, 248): 15, (214, 238, 245): 13, (148, 176, 199): 14, (70, 104, 134): 8,
          (0, 194, 0): 10, (34, 139, 34): 11, SHADOW: 8}
SEQUENCE = (0, 1, 2, 3, 0, 1, 2, 3, 7, 4, 5, 6, 7, 1)   # RandomLouieEgg.prefab's idle animationSprite
STEP = 8                            # 0.1333 s
WAIT = 30                           # loopRestartDelay 0.5 s, on the last frame
X0, Y0 = -8, -19                    # object position of the (16-column) frame's top left
BODY_TILES = (0x26, 0x28, 0x2A)     # 16 x 16 pieces (tile, +1, +16, +17)
SHADOW_TILES = ((0x2C, 0x2D), (0x2E, 0x2F), (0x3C, 0x3D), (0x3E, 0x3F))
SHADOW_LINE = 16                    # frame line of the shadow pieces' top (shadows are in lines 18-23)
REST = (0, 1, 2, 3, 7)              # frames sharing the rest shadow


def _palette(rom):
    p = 0x810000 | struct.unpack_from("<H", rom, off(0x818000 + 2 * (PAL - 1)))[0]
    cnt = struct.unpack_from("<H", rom, off(p + 2))[0]
    words = [struct.unpack_from("<H", rom, off(p + 4 + 2 * i))[0] for i in range(cnt)]
    return [((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3) for w in words]


def _frames():
    img = np.asarray(Image.open(SHEET).convert("RGBA")).astype(np.int32)
    meta = open(SHEET + ".meta", encoding="utf-8").read()
    out = []
    for i in range(8):
        m = re.search(rf"name: EggClassic_{i}\s+rect:\s+serializedVersion: 2\s+x: (\d+)\s+y: (\d+)\s+width: (\d+)"
                      r"\s+height: (\d+)", meta)
        x, y, w, h = (int(v) for v in m.groups())
        top = img.shape[0] - y - h
        out.append(img[top:top + h, x:x + w])
    return out


def _lab(rgb):
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def frames(rom):
    """[(body 16 x 16 entries, body top line, shadow 8 x 16 entries)] of the 8 frames (the shadow's top is
    SHADOW_LINE), the frame -> body index and frame -> shadow index lists."""
    raw = _frames()
    on = [(f[..., 3] > 0) & ~((f[..., 0] == BG[0]) & (f[..., 1] == BG[1]) & (f[..., 2] == BG[2])) for f in raw]
    blk = [o & (f[..., 0] == 0) & (f[..., 1] == 0) & (f[..., 2] == 0) for f, o in zip(raw, on)]
    # 16 columns: drop the two most like their right neighbour in frame 0 (the same columns in every frame)
    cols, o0 = raw[0][..., :3], on[0]
    keep = list(range(raw[0].shape[1]))
    while len(keep) > 16:
        diff = [(np.sum(o0[:, keep[i]] != o0[:, keep[i + 1]]) * 1000
                 + np.abs(cols[:, keep[i]] - cols[:, keep[i + 1]]).sum(), i) for i in range(1, len(keep) - 2)]
        keep.pop(min(diff)[1])
    pal = _palette(rom)
    plab = _lab(pal[1:])

    def entry(c):
        c = tuple(int(v) for v in c)
        if c in COLORS:
            return COLORS[c]
        return 9 + int(np.argmin(np.linalg.norm(plab - _lab([c])[0], axis=1)))

    out = []
    for f, o, b in zip(raw, on, blk):
        f, o, b = f[:, keep], o[:, keep], b[:, keep]
        body_px = o & ~b
        rows = np.nonzero(body_px.any(1))[0]
        top = int(rows[0])
        if rows[-1] - top >= 16:
            raise BuildError("eggs: an egg body is taller than 16 lines")
        body = np.zeros((16, 16), np.int32)
        for y, x in zip(*np.nonzero(body_px)):
            body[y - top, x] = entry(f[y, x, :3])
        shadow = np.zeros((8, 16), np.int32)
        for y, x in zip(*np.nonzero(b)):
            if body_px[y, x]:
                continue
            if not SHADOW_LINE <= y < SHADOW_LINE + 8:
                raise BuildError("eggs: a shadow pixel out of the shadow pieces")
            shadow[y - SHADOW_LINE, x] = 8
        out.append((body, top, shadow))
    bodies, body_of = [], []
    for body, _, _ in out:
        for i, b in enumerate(bodies):
            if np.array_equal(b, body):
                body_of.append(i)
                break
        else:
            bodies.append(body)
            body_of.append(len(bodies) - 1)
    if len(bodies) != len(BODY_TILES):
        raise BuildError(f"eggs: {len(bodies)} egg bodies, room for {len(BODY_TILES)}")
    rest = np.zeros((8, 16), np.int32)
    for i in REST:
        rest = np.maximum(rest, out[i][2])
    shadows = [rest] + [out[i][2] for i in range(8) if i not in REST]
    shadow_of = [0 if i in REST else 1 + [j for j in range(8) if j not in REST].index(i) for i in range(8)]
    if len(shadows) != len(SHADOW_TILES):
        raise BuildError("eggs: shadow count")
    return out, bodies, body_of, shadows, shadow_of


def tiles(rom):
    """{sheet offset: 32 bytes} of the egg's 20 tiles."""
    _, bodies, _, shadows, _ = frames(rom)
    at = lambda t: (t >> 4) * 0x200 + (t & 15) * 32
    out = {}
    for b, t in zip(bodies, BODY_TILES):
        for dy in (0, 1):
            for dx in (0, 1):
                out[at(t + 16 * dy + dx)] = encode_4bpp(b[8 * dy:8 * dy + 8, 8 * dx:8 * dx + 8])
    for s, (l, r) in zip(shadows, SHADOW_TILES):
        out[at(l)] = encode_4bpp(s[:, :8])
        out[at(r)] = encode_4bpp(s[:, 8:])
    if sorted(out) != sorted(at(16 * line + c) for line in LINES for c in COLUMNS):
        raise BuildError("eggs: the tiles do not fill the egg's columns")
    return out


def mappings(rom):
    """[mapping bytes] of frames 0-7 (ids 1-8 in the egg's table)."""
    out, _, body_of, _, shadow_of = frames(rom)
    maps = []
    for i, (_, top, _) in enumerate(out):
        bt = BODY_TILES[body_of[i]]
        l, r = SHADOW_TILES[shadow_of[i]]
        pieces = [(X0, Y0 + top, bt, 0x21), (X0, Y0 + SHADOW_LINE, l, 0x20), (X0 + 8, Y0 + SHADOW_LINE, r, 0x20)]
        maps.append(bytes([len(pieces)]) + b"".join(struct.pack("<hhHB", *p) for p in pieces))
    return maps


def script():
    """[mapping id, frames] pairs of SB6's idle loop (id = frame + 1); a 0-frame pair restarts it (its id is a
    valid one: the resolver may run once on it, docs/ROM_MAP.md)."""
    pairs = [(f + 1, STEP) for f in SEQUENCE]
    pairs[-1] = (pairs[-1][0], STEP + WAIT)
    return bytes(b for p in pairs for b in p) + bytes([1, 0])


def timeline():
    """Frame shown at each of the loop's SNES frames (tests)."""
    out = []
    for n, f in enumerate(SEQUENCE):
        out += [f] * (STEP + (WAIT if n == len(SEQUENCE) - 1 else 0))
    return out


def apply(rb):
    """Before louies.apply (its pixel 9-15 -> 1-7 copy of the sheet is made from these tiles). Returns the
    defines of asm/bombers.asm (EGGANIM, the tables)."""
    from .bombers import _table
    if rb.d[off(PAL_TABLE + EGG_CHAR)] != OLD_PAL:
        raise BuildError("eggs: unexpected egg palette id")
    if bytes(rb.d[off(0xC58825):off(0xC58825) + len(OLD_SCRIPT)]) != OLD_SCRIPT:
        raise BuildError("eggs: unexpected egg animation")
    rb.patch(PAL_TABLE + EGG_CHAR, bytes([OLD_PAL]), bytes([PAL]), "eggs: SB6's egg colors (palette id $51)")
    for a in LDA_PAL:
        rb.patch(a, bytes([0xA9, OLD_PAL, 0x20, 0xEB, 0x53]), bytes([0xA9, PAL, 0x20, 0xEB, 0x53]),
                 "eggs: an egg's colors (LDA #id / JSR $53EB)")
    for o, data in sorted(tiles(rb.d).items()):
        a = EGG_SHEET + o
        old = bytes(rb.d[off(a):off(a) + 32])
        c = (o % 0x200) // 32
        if c >= 10 and old != bytes(32):
            raise BuildError(f"eggs: sheet $1A + ${o:03X} is not empty")
        rb.patch(a, old, data, f"eggs: SB6 egg tile (sheet $1A + ${o:03X})")
    mt = _table(rb, mappings(rb.d), "eggs: SB6 egg frames (type 0 mappings of animation $15)")
    at = _table(rb, [script()], "eggs: SB6 egg idle loop (type 0 animation $15)")
    return {"EGGANIM": f"${EGG_ANIM:02X}", "EGGMAP": f"${mt >> 16:02X}", "EGGMAPBASE": f"${mt & 0xFFFF:04X}",
            "EGGANIMB": f"${at >> 16:02X}", "EGGANIMBASE": f"${(at - 2 * (EGG_ANIM - 1)) & 0xFFFF:04X}"}
