"""World 1's exit portal: SB1's (Unity's Portal.png), in the middle of the field once every enemy is dead.

assets/portal/sb1_portal.png = SB6 Unity's Sprites/Itens/Portal.png (16 x 32): the upper half is the portal
on (Portal_0), the lower half off (Portal_1, Unity's idle sprite). Unity alternates them every 0.01 s, which
at 60 fps shows each one ~3 frames: the open portal here shows on 3 / off 3.

The portal is an SB5 portal object (type 6, the object script of SB5's kind $41 with our animations) made
by asm/world1.asm (portal_task) from its own kind definition (KIND below, bank $80: `$C2:265C` reads kinds
with DBR = $80; `w1_kind` points it there while world1 creates the portal). Its pictures and colors are
OBJ archive / palette 1 of set 7 (null in SB5, tables here); its animations / mappings are type 6 ids
PORTAL_APPEAR / PORTAL_OPEN (SB5's type 6 has $58 animations) read from own tables through
asm/bombers.asm's enemy_map / enemy_anim. Appearance (candidate 1 of tools/portal_designs.py): off 3
frames / blank 3, five times, off 30 frames, then held: SB5's object script then sets the open animation
and marks the cell a portal ($1152 bit 6, $80:D525). Draw group $48 (byte 0 of the kind: SB5's floor
objects, drawn under the bombers; SB5's portal is $38, sorted with them). Checked by `qa_check.py portal`.
"""
import os
import struct

from PIL import Image

from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHEET = os.path.join(ROOT, "assets", "portal", "sb1_portal.png")
SET = 7                               # archive / palette set (null in SB5)
PAL_SET_TABLE, ARC_SET_TABLE = 0xC00379, 0xC01C96
PORTAL_APPEAR, PORTAL_OPEN = 0x70, 0x71
ON_FRAMES = OFF_FRAMES = 3
X0, Y0 = 0, -17                       # 16 x 16 piece relative to the object (as SB5 portal's 16 x 16 piece)
STOCK_SCRIPT = 0xD51A                 # SB5 portal's object script ($80:D51A): wait for the animation's end,
                                      # animation 2, then $D525 marks the cell; ours sets PORTAL_OPEN instead


def frames():
    """[off, on] 16 x 16 color index arrays and the 15 colors."""
    im = Image.open(SHEET).convert("RGBA")
    if im.size != (16, 32):
        raise BuildError("portal: sb1_portal.png must be 16 x 32")
    colors, out = [], []
    for top in (16, 0):
        f = [[0] * 16 for _ in range(16)]
        for y in range(16):
            for x in range(16):
                p = im.getpixel((x, top + y))
                if p[3] == 0:
                    continue
                c = (p[0] >> 3, p[1] >> 3, p[2] >> 3)
                if c not in colors:
                    colors.append(c)
                f[y][x] = colors.index(c) + 1
        out.append(f)
    if len(colors) > 15:
        raise BuildError(f"portal: {len(colors)} colors")
    return out, colors


def tiles(frames_):
    """Column pairs (archive tile 2i = VRAM tile i of the 16-tile row, 2i + 1 the one under it): frame f is
    columns 2f, 2f + 1, i.e. mapping tile 2f (16 x 16 piece)."""
    out = b""
    for f in frames_:
        for cx in (0, 8):
            for cy in (0, 8):
                out += encode_4bpp([row[cx:cx + 8] for row in f[cy:cy + 8]])
    return out


def appear_script():
    pairs = [(1, 3), (3, 3)] * 5 + [(1, 30), (1, 0xFF)]
    return bytes(b for p in pairs for b in p)


def open_script():
    return bytes([2, ON_FRAMES, 1, OFF_FRAMES, 1, 0])


def mappings():
    piece = lambda t: bytes([1]) + struct.pack("<hhHB", X0, Y0, t, 0x21)
    # hidden = a blank 16 x 16 (a piece left out of the OAM makes SB5's builder show the change late)
    return [piece(0), piece(2), piece(4)]


def apply(rb):
    """Returns the defines of asm/bombers.asm and asm/world1.asm."""
    from .bombers import _table
    for t, name in ((PAL_SET_TABLE, "palette"), (ARC_SET_TABLE, "archive")):
        if struct.unpack_from("<H", rb.d, off(t + 2 * SET))[0] != 0:
            raise BuildError(f"portal: {name} set {SET} is not null")
    fr, colors = frames()
    data = tiles(fr + [[[0] * 16 for _ in range(16)]])
    src = rb.alloc("bulk", data, "World 1 portal: SB1's exit, off / on / blank (6 OBJ columns, raw)")
    arc = rb.alloc("e3_tables", rb.le16(0) + rb.le16(len(data)) + rb.le24(src) + bytes([0x85]),
                   "World 1 portal: set 7 archive table (1 = its tiles)")
    words = [0] + [r | g << 5 | b << 10 for r, g, b in colors] + [0] * (15 - len(colors))
    pal = bytearray(2) + rb.le16(0) + rb.le16(16) + b"".join(rb.le16(w) for w in words)
    pa = rb.alloc("bank81", bytes(pal), "World 1 portal: set 7 palette table (1 = its 16 colors)")
    pal[0:2] = rb.le16((pa + 2) & 0xFFFF)
    rb.d[pa & 0x3FFFFF:(pa & 0x3FFFFF) + len(pal)] = pal
    rb.patch(ARC_SET_TABLE + 2 * SET, b"\x00\x00", rb.le16(arc & 0xFFFF), "archive set 7 -> World 1 portal")
    rb.patch(PAL_SET_TABLE + 2 * SET, b"\x00\x00", rb.le16(pa & 0xFFFF), "palette set 7 -> World 1 portal")

    mt = _table(rb, mappings(), "World 1 portal: type 6 mappings (off, on, hidden)")
    at = _table(rb, [appear_script(), open_script()], "World 1 portal: type 6 animations (appear, open)")

    # object script (bank $80): SB5's with the open animation id; then the kind (bank $80, read by $C2:265C)
    stock = bytes(rb.d[STOCK_SCRIPT:STOCK_SCRIPT + 11])
    if stock != bytes.fromhex("15 01 3B 2F FC 06 02 35 25 D5 1F"):
        raise BuildError("portal: unexpected SB5 portal object script")
    script = stock[:6] + bytes([PORTAL_OPEN]) + stock[7:]
    sa = rb.alloc("c0_hi", script, "World 1 portal: object script (SB5's $80:D51A, open animation)")
    kind = bytes([0x48, SET, 0xF8, 1, 1, 0x26, PORTAL_APPEAR, 0, sa & 0xFF, sa >> 8 & 0xFF])
    ka = rb.alloc("c0_hi", kind, "World 1 portal: object kind (set 7, palette / archive 1, slots 3-7, type 6)")
    return ({"PORTALANIM": f"${PORTAL_APPEAR:02X}", "PORTALMAP": f"${mt >> 16:02X}",
             "PORTALMAPBASE": f"${mt & 0xFFFF:04X}", "PORTALANIMB": f"${at >> 16:02X}",
             "PORTALANIMBASE": f"${(at - 2 * (PORTAL_APPEAR - 1)) & 0xFFFF:04X}"},
            {"PORTALKIND": f"${ka & 0xFFFF:04X}"},
            {"colors": len(colors), "bytes": len(data)})
