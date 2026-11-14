"""Character + color selection in the Normal Game (asm/picker.asm).

Port of the "choose a character in Normal Game" and "choose character colors
with L and R" mods of SuperBomberman5SNESRecomp. The recomp suspends the
whole machine while Battle's picker runs; the cartridge calls the picker as a
script subroutine from the file confirmation instead and saves the script
variables around it.
"""
import os
import tempfile

from .. import asar
from . import bombers
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "picker.asm")
OFF_SEAT = 0                 # $6269+seat of the seats that do not play (1 = human)
GLYPH_TILE = 0xF0            # first of the 12 "L + R" tiles: unused by the picker's OBJ sheet
GLYPH_VRAM = 0x6000 + 16 * GLYPH_TILE   # VRAM word address (OBJ tiles at $6000)
CELL_TILE = 0xC0             # Bomberman's cell: 4 tiles here and 4 one row below
XCELL_TILE = 0xC4            # cell of one other redrawn character (first row of the grid): same layout
XCELL_CHARS = range(1, 5)    # characters in the first row of the grid (cell = character, Bomberman is 0)
# The cursor's "1P".."4P" tiles (6+2n, 7+2n): ink color of each seat, dark outline.
INKS = (0xF, 0x3, 0x9, 0xB)
OUTLINE = 1
# Strokes as (row, column). "R" is the cartridge's "P" plus a leg, as in the recomp mod.
P_STROKE = [(1, 2), (1, 3), (1, 4), (2, 2), (2, 4), (3, 2), (3, 4), (4, 2), (4, 3), (4, 4), (5, 2), (6, 2)]
STROKES = (
    [(y, 2) for y in range(1, 7)] + [(6, 3), (6, 4)],          # L
    [(3, 2), (3, 3), (3, 4), (2, 3), (4, 3)],                  # +
    P_STROKE + [(5, 3), (6, 4)],                               # R
)


def _glyphs():
    """12 tiles (4bpp): L, +, R for each seat, ink + one-pixel outline."""
    out = bytearray()
    for ink in INKS:
        for stroke in STROKES:
            px = [[0] * 8 for _ in range(8)]
            for y, x in stroke:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if 0 <= y + dy < 8 and 0 <= x + dx < 8:
                            px[y + dy][x + dx] = OUTLINE
            for y, x in stroke:
                px[y][x] = ink
            tile = bytearray(32)
            for y in range(8):
                for x in range(8):
                    for plane in range(4):
                        if px[y][x] >> plane & 1:
                            tile[(16 if plane >= 2 else 0) + 2 * y + (plane & 1)] |= 0x80 >> x
            out += tile
    return bytes(out)


def _cell(stand):
    """The pose (indices, one 64x64 cell) as two 16x16 sprites, one above the
    other, feet on the last row: tile rows CELL_TILE.. and CELL_TILE + $10.."""
    ys, xs = stand.nonzero()
    w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    if w > 16 or h > 32:
        raise BuildError(f"picker: the standing pose is {w}x{h}, the cell sprite holds 16x32")
    img = [[0] * 16 for _ in range(32)]
    x0, y0 = (16 - w) // 2, 32 - h
    for y, x in zip(ys, xs):
        img[y0 + y - ys.min()][x0 + x - xs.min()] = int(stand[y, x])

    def tile(tx, ty):
        t = bytearray(32)
        for y in range(8):
            for x in range(8):
                v = img[ty * 8 + y][tx * 8 + x]
                for plane in range(4):
                    if v >> plane & 1:
                        t[(16 if plane >= 2 else 0) + 2 * y + (plane & 1)] |= 0x80 >> x
        return bytes(t)

    # sprite 1 = tiles T, T+1 / T+16, T+17; sprite 2 = T+2, T+3 / T+18, T+19
    return (tile(0, 0) + tile(1, 0) + tile(0, 2) + tile(1, 2) +
            tile(0, 1) + tile(1, 1) + tile(0, 3) + tile(1, 3))


def apply(rb, base_rom, bomber):
    """`bomber`: result of features/bombers.py (its palettes and the pose for
    the grid), or None. Returns the asm symbols + `bomber_colors`."""
    own = bool(bomber and bomber.get("paltab"))
    bomber_colors = bomber["palcount"] if own else 6
    # the first redrawn character of the grid's first row (with its own palettes) also gets a sprite cell
    chars = (bomber or {}).get("chars", []) if own else []
    xch = next((ch for ch in chars if ch["char"] in XCELL_CHARS), None)
    # palette id of color 0 (0 = the cartridge's ids) and color count of characters 0-8
    chpal, chcol = [0x80 if own else 0] + [0] * 8, [bomber_colors] + [6] * 8
    for ch in chars:
        if ch["char"] <= 8:
            chpal[ch["char"]], chcol[ch["char"]] = 0x80 + ch["pal0"], ch["colors"]
    reg = rb.regions["bulk"]
    with tempfile.TemporaryDirectory() as tmp:
        gpath, cpath = os.path.join(tmp, "glyphs.bin"), os.path.join(tmp, "cell.bin")
        xpath = os.path.join(tmp, "xcell.bin")
        with open(gpath, "wb") as fh:
            fh.write(_glyphs())
        with open(cpath, "wb") as fh:
            fh.write(_cell(bomber["stand"]) if own else b"")
        with open(xpath, "wb") as fh:
            fh.write(_cell(xch["stand"]) if xch else b"")
        runs, syms = asar.assemble_into(rb.d, ASM, {
            "E4": f"${reg.cursor:06X}", "OFFSEAT": f"${OFF_SEAT:02X}", "BCOLS": str(bomber_colors),
            "PALS": str(bombers.PAL_IDS if own else 0), "OWN": "1" if own else "0",
            "PALTAB": f"${bomber['paltab'] if own else 0:06X}",
            "GTILE": f"${GLYPH_TILE:02X}", "GVRAM": f"${GLYPH_VRAM:04X}",
            "CTILE": f"${CELL_TILE:02X}", "CVRAM": f"${0x6000 + 16 * CELL_TILE:04X}",
            "GLYPHS": gpath.replace("\\", "/"), "CELL": cpath.replace("\\", "/"),
            "XCH": str(xch["char"] if xch else 0), "XPAL": f"${0x80 + xch['pal0'] if xch else 0:02X}",
            "PALN": str(bomber["pal_total"] if own else 0),
            "XTILE": f"${XCELL_TILE:02X}", "XVRAM": f"${0x6000 + 16 * XCELL_TILE:04X}",
            "XCELL": xpath.replace("\\", "/"),
            "SCLR": f"${(bomber or {}).get('stream_clear', 0):06X}",
            "CHPAL": ",".join(f"${v:02X}" for v in chpal), "CHCOL": ",".join(str(v) for v in chcol)})
    start, end = reg.cursor, syms["end_e4"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"picker.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "picker: Normal Game character/color selection (asm/picker.asm)")

    def ptr(name):
        a = syms[name]
        return bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16])

    rb.patch(0xC710E2, bytes.fromhex("24 4C 12 C7"), b"\x24" + ptr("script_new"),
             "picker: New Game file confirm -> character selection")
    rb.patch(0xC70E27, bytes.fromhex("24 4C 12 C7"), b"\x24" + ptr("script_cont"),
             "picker: Continue file confirm -> character selection")
    rb.patch(0xC2069B, bytes.fromhex("7C 46 C1"), ptr("pick_op"), "picker: script op FF 1A nn >= $F0 runs native code")
    rb.patch(0xC0F421, bytes.fromhex("22 E0 04 C0"), bytes([0x22]) + ptr("pick_nmi"), "picker: cursor glyph tiles sent in the NMI")
    syms["bomber_colors"] = bomber_colors
    syms["xcell"] = xch["char"] if xch else 0
    return syms
