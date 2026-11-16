"""Character + color selection in the Normal Game (asm/picker.asm).

Port of the "choose a character in Normal Game" and "choose character colors
with L and R" mods of SuperBomberman5SNESRecomp. The recomp suspends the
whole machine while Battle's picker runs; the cartridge calls the picker as a
script subroutine from the file confirmation instead and saves the script
variables around it.
"""
import os

import numpy as np
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
XCELL_CHARS = range(1, 9)    # characters of the grid (cell = character, Bomberman is 0, cell 9 = random)


def xcell_tile(c):
    """First tile of character c's cell sprite: 4 tiles + 4 one row below, in
    $40-$6F (empty in the picker's OBJ VRAM)."""
    return 0x40 + 4 * ((c - 1) % 4) + 0x20 * ((c - 1) // 4)


def xcell_xy(c):
    """Top sprite of cell c: 40 px per cell, rows of five cells 40 px apart."""
    return 0x28 + 40 * (c % 5), 0x77 + 40 * (c // 5)


def xcell_blank(c):
    """BG1 map words ($3000) of cell c's figure: 4 x 4 tiles."""
    col, row = 4 + 5 * (c % 5), 15 + 5 * (c // 5)
    return [0x3000 + 32 * (row + r) + col for r in range(4)]
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
    stand = stand.copy()
    for _ in range(48):         # a pose wider than the cell (a tool in the hand) loses its thinnest edge columns
        ys, xs = stand.nonzero()
        if xs.max() - xs.min() + 1 <= 16:
            break
        left, right = int((xs == xs.min()).sum()), int((xs == xs.max()).sum())
        stand[:, xs.min() if left <= right else xs.max()] = 0
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


def _recolor(stand, own, shown):
    """The pose (indices of palette `own`) with the nearest colors of palette `shown`."""
    a, b = np.array(own, dtype=np.int32), np.array(shown, dtype=np.int32)
    near = np.array([0] + [int(((b - c) ** 2).sum(-1).argmin()) + 1 for c in a], dtype=np.uint8)
    return near[stand]


def apply(rb, base_rom, bomber, title=None):
    """`bomber`: result of features/bombers.py (its palettes and the pose for
    the grid), or None. Returns the asm symbols + `bomber_colors`."""
    own = bool(bomber and bomber.get("paltab"))
    bomber_colors = bomber["palcount"] if own else 6
    # every redrawn character of the grid (1-8) also gets a sprite cell
    chars = (bomber or {}).get("chars", []) if own else []
    xchs = [ch for ch in chars if ch["char"] in XCELL_CHARS]
    # palette id of color 0 (0 = the cartridge's ids) and color count of characters 0-8
    own_id = bomber["own_id"] if own else 0x80
    chpal, chcol = [own_id if own else 0] + [0] * 8, [bomber_colors] + [6] * 8
    for ch in chars:
        if ch["char"] <= 8:
            chpal[ch["char"]], chcol[ch["char"]] = own_id + ch["pal0"], ch["colors"]
    # the cells share OBJ palette 7 = Bomberman's first color. A character
    # painted with his color layout uses its own indices there; one with its
    # own layout is drawn with the nearest colors (cell_7), and the cell a seat
    # recolors (palette 4, the character's own colors) gets its real indices
    # (cell_4), swapped in by the NMI (xswap)
    for ch in xchs:
        ch["cell_4"] = _cell(ch["stand"])
        ch["cell_7"] = (_cell(_recolor(ch["stand"], ch["first"], bomber["first"]))
                        if ch["notes"].get("own") else ch["cell_4"])
    reg = rb.regions["bulk"]
    with tempfile.TemporaryDirectory() as tmp:
        gpath, cpath = os.path.join(tmp, "glyphs.bin"), os.path.join(tmp, "cell.bin")
        nmi, data = [], []
        for ch in xchs:
            c, t = ch["char"], xcell_tile(ch["char"])
            path = os.path.join(tmp, f"xcell{c}.bin").replace("\\", "/")
            with open(path, "wb") as fh:
                fh.write(ch["cell_7"])
            data += [f"xcell_{c}:", f'    incbin "{path}"']
            if ch["cell_4"] != ch["cell_7"]:
                with open(path + "4", "wb") as fh:
                    fh.write(ch["cell_4"])
                data += [f"xcell4_{c}:", f'    incbin "{path}4"']
            vram = 0x6000 + 16 * t
            nmi += ["    rep #$20", f"    lda.w #xcell_{c}"]
            nmi += ["    sta $4302", "    lda #$0080", "    sta $4305",
                    f"    lda.w #${vram:04X}", "    sta $2116", "    sep #$20", "    lda #$01", "    sta $420B",
                    "    rep #$20", f"    lda.w #${vram + 0x100:04X}", "    sta $2116", "    lda #$0080", "    sta $4305",
                    "    sep #$20", "    lda #$01", "    sta $420B",
                    f"    lda.l $7E62C9+{c}", f"    cmp.b #{c + 1}", "    bne +", "    rep #$20"]
            for a in xcell_blank(c):
                nmi += [f"    lda.w #${a:04X}", "    sta $2116", "    lda #$211C"] + ["    sta $2118"] * 4
            nmi += ["    sep #$20", "+"]
        # every frame (M 8-bit): the cell that took OBJ palette 4 gets its own
        # indices, the one that gave it back the palette 7 ones
        swap = [ch for ch in xchs if ch["cell_4"] != ch["cell_7"]]
        # (one cell per NMI, and only while the game's VRAM queue is empty: the
        # portrait and the label it sends when the cursor moves fill the vblank)
        sw = ["    lda.l !p4char", "    cmp.l !p4tile", "    bne +", "    brl .xsw_done",
              "+   rep #$20", "    lda.l $7E0355", "    cmp.l $7E0357", "    sep #$20", "    beq +",
              "    brl .xsw_done", "+   lda.l !p4tile"]
        for ch in swap:
            c = ch["char"]
            sw += [f"    cmp.b #{c}", "    bne +", "    rep #$20", f"    lda.w #xcell_{c}", "    sta $4302",
                   f"    lda.w #${0x6000 + 16 * xcell_tile(c):04X}", "    jsr xs_dma", "    sep #$20",
                   "    lda #$FE", "    sta.l !p4tile", "    brl .xsw_done", "+"]
        sw += ["    lda.l !p4char", "    sta.l !p4tile"]
        for ch in swap:
            c = ch["char"]
            sw += [f"    cmp.b #{c}", "    bne +", "    rep #$20", f"    lda.w #xcell4_{c}", "    sta $4302",
                   f"    lda.w #${0x6000 + 16 * xcell_tile(c):04X}", "    jsr xs_dma", "    sep #$20", "+"]
        sw += [".xsw_done:"]
        data += ["; $4302 = source, A (16-bit) = VRAM: a cell's 4 + 4 tiles", "xs_dma:",
                 "    sta $2116", "    pha", "    sep #$20", "    lda #$80", "    sta $2115", "    rep #$20", "    lda #$1801", "    sta $4300", "    lda #$0080", "    sta $4305",
                 "    sep #$20", "    lda.b #xs_dma>>16", "    sta $4304", "    lda #$01", "    sta $420B",
                 "    rep #$20", "    pla", "    clc", "    adc #$0100", "    sta $2116", "    lda #$0080",
                 "    sta $4305", "    sep #$20", "    lda #$01", "    sta $420B", "    rep #$20", "    rts"]
        xnmi, xdata = os.path.join(tmp, "xnmi.asm"), os.path.join(tmp, "xdata.asm")
        xswap = os.path.join(tmp, "xswap.asm")
        with open(xswap, "w") as fh:
            fh.write("\n".join(sw) + "\n")
        with open(xnmi, "w") as fh:
            fh.write("\n".join(nmi) + "\n")
        with open(xdata, "w") as fh:
            fh.write("\n".join(data) + "\n")
        on = [0] * 9
        for ch in xchs:
            on[ch["char"]] = 1
        with open(gpath, "wb") as fh:
            fh.write(_glyphs())
        with open(cpath, "wb") as fh:
            fh.write(_cell(bomber["stand"]) if own else b"")
        runs, syms = asar.assemble_into(rb.d, ASM, {
            "E4": f"${reg.cursor:06X}", "OFFSEAT": f"${OFF_SEAT:02X}", "BCOLS": str(bomber_colors),
            "PALS": str(bombers.PAL_IDS if own else 0), "OWN": "1" if own else "0",
            "PALTAB": f"${bomber['paltab'] if own else 0:06X}",
            "GTILE": f"${GLYPH_TILE:02X}", "GVRAM": f"${GLYPH_VRAM:04X}",
            "CTILE": f"${CELL_TILE:02X}", "CVRAM": f"${0x6000 + 16 * CELL_TILE:04X}",
            "GLYPHS": gpath.replace("\\", "/"), "CELL": cpath.replace("\\", "/"),
            "XN": str(len(xchs)), "XPAL": f"${own_id:02X}", "OWNID": f"${own_id:02X}",
            "PALN": str(bomber["pal_total"] if own else 0),
            "XON": ",".join(map(str, on)),
            "XX": ",".join(f"${xcell_xy(c)[0]:02X}" for c in range(9)),
            "XY": ",".join(f"${xcell_xy(c)[1]:02X}" for c in range(9)),
            "XT": ",".join(f"${xcell_tile(c) if c else 0:02X}" for c in range(9)),
            "XNMI": xnmi.replace("\\", "/"), "XDATA": xdata.replace("\\", "/"),
            "XSWAP": xswap.replace("\\", "/"),
            "SCLR": f"${(bomber or {}).get('stream_clear', 0):06X}",
            "TITLE_OP": f"${(title or {}).get('title_op', 0):06X}",
            "TITLE_NMI": f"${(title or {}).get('title_nmi', 0):06X}",
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
    syms["xcell"] = [ch["char"] for ch in xchs]
    return syms
