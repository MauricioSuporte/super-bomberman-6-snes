"""In-stage pause menu (Normal Game), like the SB6 fan game's and the SB5 recomp's.

SB5's pause (native task `$C5:0000`, `$1D1D` = 1 freezes the stage, PAUSE! and
WORLD n - nn on BG3) only waits for Start. In the Normal Game the hack adds,
under PAUSE!, the Unity pause menu:

    RESUME / RETURN TO WORLD MAP / RETURN TO TITLE

Up/down move (SFX 1), Start or A accepts (SFX 4), B goes back (SFX 3) or, on
the main list, resumes. The two returns ask first (RETURN TO WORLD MAP? /
RETURN TO TITLE SCREEN?, NO / YES, NO selected). Yes ends the stage the
native way: `$1D1E` bit 2 (what portals and op `0F` do), the next mode in
`$1031` (3 = the Normal Game menu with `$631A` = 1, which starts on the
world map as after a zone; 2 = the title), and bit 6 of `$1D1A` cleared so
the stage is not counted as cleared (`$C5:3D19`). Battle keeps SB5's pause.

Screen (asm/pause.asm): an 8x8 font of our own (one BG3 tile per glyph,
color 3 top / 2 bottom, color 1 shadow) in BG3 tiles `$100+` (VRAM `$5800`):
the NMI saves those tiles first and puts them back on resume. Text rows
17-21 come from per-state tables (DMA). Unselected text uses BG3 palette 0
(white / gray), the selected line palette 6 (yellow / orange, red shadow),
as SB5's HUD palettes have them. A frame (palette 6: red / orange / yellow
lines, like the Unity window's gold border) surrounds rows 9-23 x columns
3-28, and inside it the scene is shown at half brightness (color window 1,
its left/right per line from an HDMA table; the scene on the subscreen, added
at half to a black backdrop), like the Unity window's 50% black fill; the
stage's own color math, windows and HDMA are put back on resume. SB5's
WORLD n - nn becomes STAGE n-m.
"""
import os
import struct

from .. import asar
from ..rombuild import BuildError
from ..romlib import off

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASM = os.path.join(ROOT, "asm", "pause.asm")

FIRST_TILE = 0x100          # BG3 tile of the first glyph (VRAM $5000 + 8 * tile)
BG3_CHR, BG3_MAP = 0x5000, 0x4000
ROW0, NROWS = 17, 7         # text rows 17-21 + the frame's bottom (PAUSE! is at rows 14-15)
TOP, BOTTOM = 9, 23         # panel rows (frame), WORLD n - nn is at rows 11-12
LEFT, RIGHT = 3, 28         # panel columns (frame)
BAND = [1, 2, 3, 2, 1]      # frame lines from the outside in (palette 6: red, orange, yellow)
INSET = 2                   # pixels between the cell edge and the frame
PAL_FRAME = 6
LABEL_ROW = 11              # STAGE w-s over SB5's WORLD w - ss (rows 11-12, columns 4-27 rewritten)
PAL_LABEL = 1               # WORLD's green; the digits and "-" are SB5's own (tiles $82-$8C / $92-$9C)
LABEL_TILE = 0xA6           # S T A G E in SB5's stage font (features/world1.py puts them there; bottoms + $10)
# 8 x 16 letters in the style of SB5's big digits: 2-pixel strokes inside a 1-pixel dark outline (4-neighbour: rounded corners)
LETTERS = {
    "S": ["######", "######", "##..##", "##....", "##....", "##....", "######", "######", "....##", "....##",
          "....##", "##..##", "######", "######"],
    "T": ["######", "######"] + ["..##.."] * 12,
    "A": ["######", "######", "##..##", "##..##", "##..##", "##..##", "######", "######"] + ["##..##"] * 6,
    "G": ["######", "######", "##..##", "##....", "##....", "##....", "##.###", "##.###", "##..##", "##..##",
          "##..##", "##..##", "######", "######"],
    "E": ["######", "######", "##....", "##....", "##....", "##....", "#####.", "#####.", "##....", "##....",
          "##....", "##....", "######", "######"],
}


def big_letter(rows):
    """-> (top tile, bottom tile): fill 3, outline 1, outer corners of the fill 2 (as SB5's '0')."""
    fill = [[False] * 8 for _ in range(16)]
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            fill[1 + y][1 + x] = c == "#"
    f = lambda x, y: 0 <= x < 8 and 0 <= y < 16 and fill[y][x]
    px = [[0] * 8 for _ in range(16)]
    for y in range(16):
        for x in range(8):
            if fill[y][x]:
                px[y][x] = 2 if (x, y) in ((1, 1), (6, 1), (1, 14), (6, 14)) else 3
            elif any(f(x + dx, y + dy) for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                px[y][x] = 1
    return encode(px[:8]), encode(px[8:])

PAL_TEXT, PAL_SEL = 0, 6    # BG3 palettes: 0 white/gray (HUD), 6 yellow/orange/red
BLANK = 0x2000              # SB5's blank BG3 cell below the HUD (tile 0, priority)
OPT_COL = 8                 # option column (cursor 2 to the left)

# 6- or 7-pixel-wide glyphs, 7 rows ('X' = stroke). Drawn at x 0, y 0 with a shadow at +1, +1.
FONT = {
    "A": [".XXXX.", "XX..XX", "XX..XX", "XXXXXX", "XX..XX", "XX..XX", "XX..XX"],
    "C": [".XXXX.", "XX..XX", "XX....", "XX....", "XX....", "XX..XX", ".XXXX."],
    "D": ["XXXXX.", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XXXXX."],
    "E": ["XXXXXX", "XX....", "XX....", "XXXXX.", "XX....", "XX....", "XXXXXX"],
    "I": ["XXXXXX", "..XX..", "..XX..", "..XX..", "..XX..", "..XX..", "XXXXXX"],
    "L": ["XX....", "XX....", "XX....", "XX....", "XX....", "XX....", "XXXXXX"],
    "M": ["XX...XX", "XXX.XXX", "XXXXXXX", "XX.X.XX", "XX...XX", "XX...XX", "XX...XX"],
    "N": ["XX..XX", "XXX.XX", "XXXXXX", "XX.XXX", "XX..XX", "XX..XX", "XX..XX"],
    "O": [".XXXX.", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX", ".XXXX."],
    "P": ["XXXXX.", "XX..XX", "XX..XX", "XXXXX.", "XX....", "XX....", "XX...."],
    "R": ["XXXXX.", "XX..XX", "XX..XX", "XXXXX.", "XXXX..", "XX.XX.", "XX..XX"],
    "S": [".XXXX.", "XX..XX", "XX....", ".XXXX.", "....XX", "XX..XX", ".XXXX."],
    "T": ["XXXXXX", "..XX..", "..XX..", "..XX..", "..XX..", "..XX..", "..XX.."],
    "U": ["XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX", ".XXXX."],
    "W": ["XX...XX", "XX...XX", "XX...XX", "XX.X.XX", "XXXXXXX", "XXX.XXX", "XX...XX"],
    "Y": ["XX..XX", "XX..XX", "XX..XX", ".XXXX.", "..XX..", "..XX..", "..XX.."],
    "?": [".XXXX.", "XX..XX", "....XX", "...XX.", "..XX..", "......", "..XX.."],
    ">": ["XX....", "XXXX..", "XXXXXX", "XXXXXXX", "XXXXXX", "XXXX..", "XX...."],
}
TOP_ROWS = 4                # stroke rows 0-3 in color 3, 4-6 in color 2

MAIN = ["RESUME", "RETURN TO WORLD MAP", "RETURN TO TITLE"]
QUESTIONS = ["RETURN TO WORLD MAP?", "RETURN TO TITLE SCREEN?"]
ANSWERS = ["NO", "YES"]


def glyph_tile(rows):
    px = [[0] * 8 for _ in range(8)]
    for y, line in enumerate(rows):
        for x, c in enumerate(line):
            if c == "X" and y + 1 < 8 and x + 1 < 8:
                px[y + 1][x + 1] = 1
    for y, line in enumerate(rows):
        for x, c in enumerate(line):
            if c == "X":
                px[y][x] = 3 if y < TOP_ROWS else 2
    out = bytearray()
    for row in px:
        p0 = p1 = 0
        for x, v in enumerate(row):
            p0 |= (v & 1) << (7 - x)
            p1 |= (v >> 1 & 1) << (7 - x)
        out += bytes([p0, p1])
    return bytes(out)


def encode(px):
    out = bytearray()
    for row in px:
        p0 = p1 = 0
        for x, v in enumerate(row):
            p0 |= (v & 1) << (7 - x)
            p1 |= (v >> 1 & 1) << (7 - x)
        out += bytes([p0, p1])
    return bytes(out)


def frame_tiles():
    """-> {name: 2bpp tile} for the frame's corners and edges (tl, t, tr, l, r, bl, b, br).

    The frame is a rectangle INSET pixels inside the panel's outer cells, BAND lines thick, without its four
    outermost corner pixels."""
    w, h = 3 * 8, 3 * 8                      # a 3 x 3 cell panel holds every kind of cell
    img = [[0] * w for _ in range(h)]
    n = len(BAND)
    for y in range(h):
        for x in range(w):
            d = min(x - INSET, y - INSET, w - 1 - INSET - x, h - 1 - INSET - y)
            if 0 <= d < n:
                corner = (x - INSET in (0, w - 1 - 2 * INSET) or x == w - 1 - INSET) and                          (y - INSET in (0, h - 1 - 2 * INSET) or y == h - 1 - INSET)
                if not (d == 0 and corner):
                    img[y][x] = BAND[d]
    names = {"tl": (0, 0), "t": (1, 0), "tr": (2, 0), "l": (0, 1), "r": (2, 1), "bl": (0, 2), "b": (1, 2),
             "br": (2, 2)}
    return {k: encode([row[cx * 8:cx * 8 + 8] for row in img[cy * 8:cy * 8 + 8]]) for k, (cx, cy) in names.items()}


def build_tables():
    """-> (2bpp tiles, screens: 8 x NROWS rows of 32 BG3 words, little-endian, frame words, window box).

    Screens: 0 blank, 1-3 main list (item 0-2 selected), 4-5 world map question (NO / YES), 6-7 title
    question (NO / YES)."""
    chars = sorted(FONT)
    frame = frame_tiles()
    tiles = b"".join(glyph_tile(FONT[c]) for c in chars) + b"".join(frame.values())
    tile_of = {c: FIRST_TILE + i for i, c in enumerate(chars)}
    fw = {k: 0x2000 | PAL_FRAME << 10 | (FIRST_TILE + len(chars) + i) for i, k in enumerate(frame)}

    def put(rows, row, col, text, pal):
        for i, ch in enumerate(text):
            if ch != " ":
                if ch not in tile_of:
                    raise BuildError(f"pause: no glyph for {ch!r}")
                rows[row][col + i] = 0x2000 | pal << 10 | tile_of[ch]

    def screen(lines, framed=True):
        rows = [[BLANK] * 32 for _ in range(NROWS)]
        if not framed:
            return b"".join(struct.pack("<32H", *r) for r in rows)
        for r in range(BOTTOM - ROW0):
            rows[r][LEFT], rows[r][RIGHT] = fw["l"], fw["r"]
        bottom = rows[BOTTOM - ROW0]
        bottom[LEFT:RIGHT + 1] = [fw["bl"]] + [fw["b"]] * (RIGHT - LEFT - 1) + [fw["br"]]
        for row, col, text, pal in lines:
            if col < 0 or col + len(text) > 32:
                raise BuildError(f"pause: {text!r} does not fit")
            put(rows, row, col, text, pal)
        return b"".join(struct.pack("<32H", *r) for r in rows)

    screens = [screen([], framed=False)]
    for sel in range(len(MAIN)):
        lines = [(2 * i, OPT_COL, t, PAL_SEL if i == sel else PAL_TEXT) for i, t in enumerate(MAIN)]
        lines.append((2 * sel, OPT_COL - 2, ">", PAL_SEL))
        screens.append(screen(lines))
    for q in QUESTIONS:
        for sel in range(2):
            col = 16 - (len(q) + 1) // 2
            ans = 15
            lines = [(0, col, q, PAL_TEXT)]
            lines += [(2 + 2 * i, ans, a, PAL_SEL if i == sel else PAL_TEXT) for i, a in enumerate(ANSWERS)]
            lines.append((2 + 2 * sel, ans - 2, ">", PAL_SEL))
            screens.append(screen(lines))
    top = [BLANK] * 32
    top[LEFT:RIGHT + 1] = [fw["tl"]] + [fw["t"]] * (RIGHT - LEFT - 1) + [fw["tr"]]
    box = (8 * LEFT + INSET, 8 * RIGHT + 7 - INSET, 8 * TOP + INSET, 8 * BOTTOM + 7 - INSET)
    return tiles, b"".join(screens), struct.pack("<32H", *top), fw, box


def hdma_table(box):
    """HDMA to $2126/$2127 (window 1 left / right): empty above and below the panel."""
    x0, x1, y0, y1 = box
    out = bytearray()
    for count, l, r in ((y0, 0xFF, 0x00), (y1 - y0 + 1, x0, x1), (1, 0xFF, 0x00)):
        while count > 0:
            n = min(count, 0x7F)
            out += bytes([n, l, r])
            count -= n
    return bytes(out) + bytes(1)  # end



def boss_numbers():
    """Stages $67-$70 (SB5's bosses, whose number SB5 does not write): world << 4 | stage of World 1's."""
    from . import world1
    out = [0] * 10
    for stage, num in [(s, 6) for s, _ in world1.RIVALS] + [(0x68, 7)]:
        out[stage - 0x67] = 1 << 4 | num
    return out

QUEUE_LAST_LINE = 250      # SB5's VRAM queue (NMI $C0:04E0) starts an entry only before this scanline


def apply(rb):
    # SB5's VRAM queue started entries up to line 259 (CMP #$0104): a 256-byte entry there and the rest of the NMI
    # ended at lines 2-3 of the next frame, after the HDMA init of line 0 (the NMI writes HDMAEN $420C = 0 first and
    # $0AEA at its end): channel 7 ran uninitialised that frame (1-7's darkness / light window, the pause panel:
    # stray lines, the light gone). Keeping HDMA on during the NMI's DMA is no fix (5A22 v1: HDMA starting during a
    # DMA can hang the console). Measured: the NMI's end comes <= 5 lines after the last entry's start.
    rb.patch(0xC004F2, bytes.fromhex("C9 04 01"), bytes([0xC9, QUEUE_LAST_LINE & 0xFF, QUEUE_LAST_LINE >> 8]),
             "NMI: the VRAM queue's last entry starts by line 250 (the NMI ends inside the vblank: HDMA init at line 0)")
    tiles, screens, top, fw, box = build_tables()
    ntiles = len(tiles) // 16
    if FIRST_TILE + ntiles > 0x200 or len(tiles) > 0x500:
        raise BuildError("pause: glyphs past BG3 tile $1FF")
    blank = struct.pack("<32H", *[BLANK] * 32)
    hdma = hdma_table(box)
    blob = tiles + screens + top + blank + hdma
    data = rb.alloc(["free_c7_sheets", "stream_ee"], blob, "pause menu: BG3 glyphs, frame, text rows, window HDMA")
    if data >> 16 != (data + len(blob) - 1) >> 16:
        raise BuildError("pause: tables across a bank (one DMA source bank)")
    region = rb.regions["bulk"]
    defs = {"ORG": f"${region.cursor:06X}", "GLYPHS": f"${data:06X}", "GLYPHBYTES": str(len(tiles)),
            "SCREENS": f"${data + len(tiles):06X}", "SCRBYTES": str(32 * 2 * NROWS),
            "GLYPHVRAM": f"${BG3_CHR + 8 * FIRST_TILE:04X}", "ROWVRAM": f"${BG3_MAP + 32 * ROW0:04X}",
            "TOPROW": f"${data + len(tiles) + len(screens):06X}",
            "BLANKROW": f"${data + len(tiles) + len(screens) + 64:06X}",
            "HDMA": f"${data + len(tiles) + len(screens) + 128:06X}",
            "TOPVRAM": f"${BG3_MAP + 32 * TOP:04X}", "SIDEROWS": str(ROW0 - TOP - 1), "SIDEGAP": str(RIGHT - LEFT), "PLEFT": str(LEFT),
            "LEFT": f"${fw['l']:04X}",
            "RIGHT": f"${fw['r']:04X}", "BLANK": f"${BLANK:04X}",
            "LS0": f"${0x2000 | PAL_LABEL << 10 | LABEL_TILE:04X}",
            "BOSSNUM": ",".join(f"${b:02X}" for b in boss_numbers()),
            "LVRAM": f"${BG3_MAP + 32 * LABEL_ROW:04X}", "LC0": str(LEFT + 1), "LC1": str(RIGHT - 1)}
    runs, syms = asar.assemble_into(rb.d, ASM, defs)
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"pause.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "pause menu (asm/pause.asm)")

    def le24(a):
        return bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16])
    rb.patch(0xC50058, bytes.fromhex("A9 01 8D 1D 1D"), b"\x22" + le24(syms["pm_open"]) + b"\xEA",
             "pause: entry ($1D1D = 1) also opens the SB6 pause menu (asm/pause.asm pm_open)")
    # stage intro ($C5:0CD9): after set 4 is chosen, STAGE w-s through intro_label, then its PLX
    rb.patch(0xC50CEB, bytes([0xA9, 0x10, 0x8D, 0x28, 0x1D, 0xA9]),
             bytes([0x22, syms["intro_label"] & 0xFF, syms["intro_label"] >> 8 & 0xFF, syms["intro_label"] >> 16,
                    0x80, 0xC50D48 - 0xC50CF1 & 0xFF]), "STAGE: stage intro text (JSL intro_label, BRA $0D48)")
    rb.patch(0xC5009E, bytes.fromhex("20 B7 00 F0"), b"\x5C" + le24(syms["pm_tick"]),
             "pause: each paused frame runs the menu instead of the Start test (asm/pause.asm pm_tick)")
    # the music keeps playing through the pause (as in SB6): skip SB5's driver commands group $10 id 6 (pause the
    # music, $C5:0088) and id 7 (resume it, $C5:0029); the pause / resume SFX (group 2 id 5) stay. Battle too.
    for a, cmd in ((0xC50088, 0x06), (0xC50029, 0x07)):
        rb.patch(a, bytes([0xA9, 0x10, 0xEB, 0xA9, cmd]), bytes([0x80, 0x07, 0xEB, 0xA9, cmd]),
                 f"pause: no music {'pause' if cmd == 6 else 'resume'} command ($10/{cmd}: BRA over its JSL $C00CED)")
    syms["tiles"] = ntiles
    return syms
