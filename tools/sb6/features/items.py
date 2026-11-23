"""Stage items drawn like Super Bomberman 6 (Unity): its icons and its blinking border.

SB5 draws a visible item ($C5:4557) as a metatile of the field's layer: words $047C + 4 x item .. +3 = BG tiles
$080 + 4 (item - 1) .. +3 (TL TR BL BR) in palette 1, from set 0 archive $5E (LZ, 80 tiles: items 1-$14; the egg,
$15, is a sprite). Palette 1 (set 0's data at $81:9094, 16 colors) is the items' own: BG3 uses CGRAM 0-7 in a
stage and no field draws in it. Its entry 2 is the border: a palette animation (task $C1:0992, script
$85:EDCF = [frames, palette id]..., 0 = loop; ids 1-5 = one color each for CGRAM 18, $81:D756 + 6 (id - 1))
changes it every 6 frames.

SB6 draws a 14 x 14 icon (assets/items/sb6_items_sheet.png, the Unity sheet; cells by name in its .meta) over a
16 x 16 border picture (not Full Fire: its icon fills the cell, NO_BORDER) whose 1-pixel ring cycles ItemBorder1-6 (red, red-orange, orange, yellow, orange,
red-orange; 1/40 s each, the cyan inside shows where an icon is see-through). Here: every icon over the border
picture, the ring in entry 2, the other colors quantized together into palette 1's 14 other entries; the ring's
colors go to ids 1-4 and a new script plays them in SB6's order, 6 frames apiece as SB5's (36 frames a cycle;
SB6's is 0.15 s: see BLINK).
"""
import os
import re
import struct

import numpy as np
from PIL import Image

from .. import lz
from . import explosions
from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHEET = os.path.join(ROOT, "assets", "items", "sb6_items_sheet.png")

# SB5 item id -> SB6 sprite name in the Unity sheet's .meta (names from the item prefabs; the four SB5 items
# SB6 has no prefab for use the sheet's unnamed cells that redraw them: (column, row) from x 512, top 0)
ICONS = {
    0x01: "BlastRadiusIcon", 0x02: "ExtraBombIcon", 0x03: "SpeedUpIcon", 0x04: "ControlBombIcon",
    0x05: "BombPassIcon", 0x06: "DestructiblePassIcon", 0x07: "InvincibleSuitIcon", 0x08: "ClockIcon",
    0x09: "OneUpIcon", 0x0A: (8, 0),                    # geta (speed down)
    0x0B: "BombKickIcon", 0x0C: "PowerGloveIcon", 0x0D: "PierceBombIcon", 0x0E: "FullFireIcon",
    0x0F: (9, 1),                                       # mine
    0x10: "SearchBombIcon",                             # SB5's slow fuse bomb = SB6's search bomb
    0x11: "BombPunchIcon", 0x12: "SkullIcon", 0x13: "SkullIcon", 0x14: "HeartIcon",
}
BORDERS = [f"ItemBorder{i}" for i in range(1, 7)]
NO_BORDER = (0x0E,)                 # SB6 draws these without the ring (its FullFire prefab: no BorderAnimation)
BORDER_ENTRY = 2                    # palette 1 entry of the ring
ICON_ENTRIES = [1] + list(range(3, 16))
ARCHIVE = 0x5D                      # index in $E3:BE60 (set 0 id $5E)
ARC_ENTRY = 0xE3BE60 + 8 * ARCHIVE
TILES = 0x80                        # first BG tile
PALETTE = 0xC19094                  # [dest $10, count $10, 16 colors]
BLINK_COLORS = 0xC1D75A             # color of id 1; id n at + 6 (n - 1)
BLINK_TABLE = 0xC5EDA1              # word per palette animation of the set ($85:EDA1, [0] = the items')
BLINK_SCRIPT = 0xC5EDCF
BLINK_OLD = bytes.fromhex("06 01 06 02 06 03 06 04 06 05 00")
# SB6: 6 border frames of 1/40 s (1.5 SNES frames each). Every step makes SB5's NMI send the whole CGRAM
# ($0351: $2C0 of the frame's DMA budget, the VRAM queue waits): faster steps cost fps (1-3 steps: 1-3 fps in
# 1-1 / 1-3 with 4 players), so SB6's colors in its order keep SB5's 6 frames a step
BLINK = [(6, 1), (6, 2), (6, 3), (6, 4), (6, 3), (6, 2)]


def _sprites():
    meta = open(SHEET + ".meta", encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"name: (\S+)\s+rect:\s+serializedVersion: 2\s+x: (\d+)\s+y: (\d+)\s+width: (\d+)"
                         r"\s+height: (\d+)", meta):
        out[m.group(1)] = tuple(int(v) for v in m.group(2, 3, 4, 5))
    return out


def _cell(img, sprites, key):
    if isinstance(key, tuple):
        x, top = 512 + 16 * key[0], 16 * key[1]
    else:
        x, y, w, h = sprites[key]
        if (w, h) != (16, 16):
            raise BuildError(f"items: {key} is not 16 x 16")
        top = img.shape[0] - y - h
    return img[top:top + 16, x:x + 16]


def _rgb5(c):
    return tuple((int(v) >> 3) << 3 for v in c)


def pictures():
    """({item: 16 x 16 RGBA (border frame 1 under the icon)}, [6 ring colors], cyan inside)."""
    img = np.asarray(Image.open(SHEET).convert("RGBA"))
    sp = _sprites()
    borders = [_cell(img, sp, b) for b in BORDERS]
    ring = np.zeros((16, 16), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    ring_cols = []
    for b in borders:
        cols = {tuple(int(v) for v in px[:3]) for px in b[ring]}
        inside = {tuple(int(v) for v in px[:3]) for px in b[~ring]}
        if len(cols) != 1 or len(inside) != 1 or (b[..., 3] < 255).any():
            raise BuildError("items: a border frame is not a ring of one color around one color")
        ring_cols.append(cols.pop())
    inside = inside.pop()
    out = {}
    for item, key in ICONS.items():
        icon = _cell(img, sp, key).astype(np.int32)
        if item in NO_BORDER:
            if (icon[..., 3] < 255).any():
                raise BuildError(f"items: item ${item:02X} has no border but is see-through")
            out[item] = icon
            continue
        pic = borders[0].astype(np.int32).copy()
        a = icon[..., 3:4] > 0
        pic = np.where(a, icon, pic)
        out[item] = pic
    return out, ring_cols, inside


def _lab(rgb):
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def quantize(pics, ring_cols, k=len(ICON_ENTRIES)):
    """Shared palette of k colors for the icons' pixels (not the ring): weighted k-means in Lab, seeded with
    the most used colors; returns (palette [(r, g, b)], {item: 16 x 16 entry indices}, mean error)."""
    ring = np.zeros((16, 16), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    counts = {}
    for item, p in pics.items():
        for px in p[~ring if item not in NO_BORDER else np.ones((16, 16), bool)]:
            c = _rgb5(px[:3])
            counts[c] = counts.get(c, 0) + 1
    cols = sorted(counts, key=lambda c: -counts[c])
    if len(cols) <= k:
        pal = cols
    else:
        pts = _lab(cols)
        w = np.array([counts[c] for c in cols], np.float64)
        # farthest-point seeds from the most used color (keeps small but distinct colors such as the reds)
        seeds = [0]
        d = np.linalg.norm(pts - pts[0], axis=1)
        while len(seeds) < k:
            j = int(np.argmax(d * np.sqrt(w)))
            seeds.append(j)
            d = np.minimum(d, np.linalg.norm(pts - pts[j], axis=1))
        cent = pts[seeds].copy()
        for _ in range(50):
            lab = np.argmin(((pts[:, None] - cent[None]) ** 2).sum(-1), 1)
            new = cent.copy()
            for j in range(k):
                m = lab == j
                if m.any():
                    new[j] = (pts[m] * w[m, None]).sum(0) / w[m].sum()
            if np.allclose(new, cent):
                break
            cent = new
        # each cluster is drawn with its most used real color (no invented colors)
        lab = np.argmin(((pts[:, None] - cent[None]) ** 2).sum(-1), 1)
        pal = []
        for j in range(k):
            m = [i for i in range(len(cols)) if lab[i] == j]
            if m:
                pal.append(cols[max(m, key=lambda i: counts[cols[i]])])
    pal_lab = _lab(pal)
    out, err, n = {}, 0.0, 0
    for item, p in pics.items():
        t = np.zeros((16, 16), np.int32)
        for y in range(16):
            for x in range(16):
                if ring[y, x] and item not in NO_BORDER:
                    t[y, x] = BORDER_ENTRY
                    continue
                c = _rgb5(p[y, x, :3])
                d = np.linalg.norm(pal_lab - _lab([c])[0], axis=1)
                j = int(np.argmin(d))
                err += float(d[j])
                n += 1
                t[y, x] = ICON_ENTRIES[j]
        out[item] = t
    return pal, out, err / max(n, 1)


def build():
    """(tile bytes of items 1-$14, palette 1 [16 BGR555 words], ring colors [BGR555], mean Lab error)."""
    pics, ring_cols, _ = pictures()
    pal, idx, err = quantize(pics, ring_cols)
    data = bytearray()
    for item in range(1, 0x15):
        t = idx[item]
        for q in range(4):
            data += encode_4bpp(t[8 * (q >> 1):8 * (q >> 1) + 8, 8 * (q & 1):8 * (q & 1) + 8])
    words = [0] * 16
    words[BORDER_ENTRY] = bgr555(ring_cols[0])
    for e, c in zip(ICON_ENTRIES, pal):
        words[e] = bgr555(c)
    return bytes(data), words, [bgr555(c) for c in ring_cols], err, idx


def bgr555(c):
    return (int(c[0]) >> 3) | (int(c[1]) >> 3) << 5 | (int(c[2]) >> 3) << 10


def blink_sequence():
    """The ring's colors over 9 frames (tests): [BGR555 per frame]."""
    _, _, ring, _, _ = build()
    ids = {1: ring[0], 2: ring[1], 3: ring[2], 4: ring[3]}
    out = []
    for frames, i in BLINK:
        out += [ids[i]] * frames
    return out


def apply(rb, preview=None):
    data, words, ring, err, idx = build()
    # SB6's ring: red, red-orange, orange, yellow, orange, red-orange = ids 1 2 3 4 3 2
    if not (ring[1] == ring[5] and ring[2] == ring[4]):
        raise BuildError("items: SB6's border colors are no longer 1 2 3 4 3 2")
    # ---- tiles: archive $5E ----
    packed = lz.compress(data)
    a = rb.alloc(explosions.ALLOC, packed, "items: SB6 item tiles (set 0 archive $5E, LZ)")
    ent = bytes(rb.d[off(ARC_ENTRY):off(ARC_ENTRY) + 8])
    if ent[:4] != bytes.fromhex("00 08 00 0A"):
        raise BuildError("items: unexpected item archive entry")
    rb.patch(ARC_ENTRY + 4, ent[4:7], a.to_bytes(3, "little"), "items: item archive -> SB6 icons")
    # ---- palette 1 ----
    old = bytes(rb.d[off(PALETTE):off(PALETTE) + 4 + 32])
    if old[:4] != bytes.fromhex("10 00 10 00"):
        raise BuildError("items: unexpected item palette")
    rb.patch(PALETTE + 4, old[4:], b"".join(struct.pack("<H", w) for w in words), "items: SB6 item colors (palette 1)")
    # ---- the border's blink ----
    for i in range(4):
        e = BLINK_COLORS + 6 * i
        if bytes(rb.d[off(e) - 4:off(e)]) != bytes.fromhex("12 00 01 00"):
            raise BuildError("items: unexpected border color entry")
        rb.patch(e, bytes(rb.d[off(e):off(e) + 2]), struct.pack("<H", ring[i]), f"items: border color id {i + 1}")
    if bytes(rb.d[off(BLINK_SCRIPT):off(BLINK_SCRIPT) + len(BLINK_OLD)]) != BLINK_OLD:
        raise BuildError("items: unexpected border script")
    script = bytes(b for f, i in BLINK for b in (f, i)) + b"\x00"
    s = rb.alloc("free_c5_sheets", script, "items: SB6 border blink (palette animation script, bank $85)")
    if s & 0xFFFF < 0x8000:
        raise BuildError("items: the blink script must be in the upper half of bank $85")
    rb.patch(BLINK_TABLE, struct.pack("<H", BLINK_SCRIPT & 0xFFFF), struct.pack("<H", s & 0xFFFF),
             "items: border blink script -> SB6's")
    # the old script (11 bytes) stays: SB5's next script starts right after it, so it cannot be told apart
    if preview:
        _preview(idx, words, preview)
    return dict(tiles=len(data), lz=len(packed), error=err, colors=len(ICON_ENTRIES))


def _preview(idx, words, path):
    rgb = [((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3) for w in words]
    im = Image.new("RGB", (20 * 18, 18), (255, 0, 255))
    for n, item in enumerate(range(1, 0x15)):
        for y in range(16):
            for x in range(16):
                im.putpixel((18 * n + x, y), rgb[idx[item][y, x]])
    im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(path)
