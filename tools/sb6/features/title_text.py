"""BG3 text glyphs in the style of SB5's title text (8x16, 2bpp).

SB5's title text is a picture, not a font: every letter is two BG3 tiles
(rows 0-7 and 8-15) whose glyph uses color 2 for the 2-pixel strokes and
color 1 for a 1-pixel outline around them (4-neighbourhood), on rows 3-14.
New strings (the version on the title) are drawn from the stroke masks
below; the outline is computed, so the look matches the original letters.
"""

# Stroke masks: rows 4..13 of the 16-row cell, 8 columns ('X' = color 2).
GLYPHS = {
    "0": ["..XXXX..", ".XX..XX.", ".XX..XX.", ".XX..XX.", ".XX..XX.",
          ".XX..XX.", ".XX..XX.", ".XX..XX.", ".XX..XX.", "..XXXX.."],
    "1": ["...XX...", ".XXXX...", "...XX...", "...XX...", "...XX...",
          "...XX...", "...XX...", "...XX...", "...XX...", "...XX..."],
    "2": ["..XXXX..", ".XX..XX.", ".....XX.", ".....XX.", "....XX..",
          "...XX...", "..XX....", ".XX.....", ".XX.....", ".XXXXXX."],
    "3": ["..XXXX..", ".XX..XX.", ".....XX.", ".....XX.", "...XXX..",
          ".....XX.", ".....XX.", ".....XX.", ".XX..XX.", "..XXXX.."],
    "4": ["....XX..", "...XXX..", "..XXXX..", ".XX.XX..", ".XX.XX..",
          ".XXXXXX.", "....XX..", "....XX..", "....XX..", "....XX.."],
    "5": [".XXXXXX.", ".XX.....", ".XX.....", ".XXXXX..", ".....XX.",
          ".....XX.", ".....XX.", ".....XX.", ".XX..XX.", "..XXXX.."],
    "6": ["..XXXX..", ".XX.....", ".XX.....", ".XXXXX..", ".XX..XX.",
          ".XX..XX.", ".XX..XX.", ".XX..XX.", ".XX..XX.", "..XXXX.."],
    "7": [".XXXXXX.", ".....XX.", ".....XX.", "....XX..", "....XX..",
          "...XX...", "...XX...", "..XX....", "..XX....", "..XX...."],
    "8": ["..XXXX..", ".XX..XX.", ".XX..XX.", ".XX..XX.", "..XXXX..",
          ".XX..XX.", ".XX..XX.", ".XX..XX.", ".XX..XX.", "..XXXX.."],
    "9": ["..XXXX..", ".XX..XX.", ".XX..XX.", ".XX..XX.", ".XX..XX.",
          "..XXXXX.", ".....XX.", ".....XX.", ".....XX.", "..XXXX.."],
    "v": ["........", "........", "........", ".XX..XX.", ".XX..XX.",
          ".XX..XX.", ".XX..XX.", "..XXXX..", "..XXXX..", "...XX..."],
    ".": ["........", "........", "........", "........", "........",
          "........", "........", "........", "...XX...", "...XX..."],
    " ": ["........"] * 10,
}


def glyph_pixels(ch):
    """16x8 grid of color indices (0 transparent, 1 outline, 2 stroke)."""
    mask = GLYPHS[ch]
    px = [[0] * 8 for _ in range(16)]
    for r, line in enumerate(mask):
        for c, v in enumerate(line):
            if v == "X":
                px[4 + r][c] = 2
    for y in range(16):
        for x in range(8):
            if px[y][x] == 0 and any(
                    0 <= y + dy < 16 and 0 <= x + dx < 8 and px[y + dy][x + dx] == 2
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                px[y][x] = 1
    return px


def encode_2bpp(rows8):
    out = bytearray()
    for row in rows8:
        p0 = p1 = 0
        for x, v in enumerate(row):
            p0 |= (v & 1) << (7 - x)
            p1 |= (v >> 1 & 1) << (7 - x)
        out += bytes([p0, p1])
    return bytes(out)


def text_tiles(text, first_tile, attr):
    """-> (2bpp tile data, top-row words, bottom-row words). Identical tiles are shared."""
    tiles, index, top, bottom = [], {}, [], []
    for ch in text:
        px = glyph_pixels(ch)
        for half, row_words in ((px[:8], top), (px[8:], bottom)):
            data = encode_2bpp(half)
            if data not in index:
                index[data] = first_tile + len(tiles)
                tiles.append(data)
            row_words.append(attr | index[data])
    return b"".join(tiles), top, bottom
