"""Blue background in the Normal Game's menu (file lists), green in its picker.

SB5 draws that background (checkerboard + Bomberman / rabbit heads) with
palette 0 of the screen's palette, set 3:

  * id 14 (`$81:9796`, 80 colors from CGRAM 0): the Normal menu, orange;
  * id 70 (`$81:A9F6`, 48 colors): Battle's picker, green checker and grey
    heads; the Normal Game reuses it, so its picker opened green and turned
    orange once the menu's checker animation wrote entries 3-4 again.

The checker scrolls by swapping entries 3-4 from a cycle table (`$81:E216`,
records `[3, 2, color, color]`, orange; Battle's green one follows it).

The hack recolors palette 0 (entries 1-15) of a copy of id 14 to the SB6
fan game's blue (BackgroundNormalGame1.png): same brightness, hue ~200
degrees; the orange cycle table is only the Normal menu's, so it is patched
in place. The Normal Game's character selection is green like the fan
game's SkinSelect (Character Select Edited1/2.png): a copy of id 70 (the
picker keeps entry 6, the red X of its grid) with the fan game's checker
pair and heads, and green copies of the menu's checker cycle steps (set
`$0D` ids 196-213, `[3, 2, c, c]`, loaded by the palette task). `pal_lookup`
(asm/bombers.asm) returns them: id 14 in mode 3, id 70 and the cycle steps
while the Normal Game's picker runs (`$7F:FF00` = 1); Battle keeps its
palettes.
"""
import colorsys
import struct

from ..romlib import off

SET3_TABLE = 0xC190EA       # set 3's word table (bank $81 = $C1), entry per id - 1
MENU_ID, PICK_ID = 14, 70
CYCLE = 0xC1E216            # orange checker cycle: 18 records of [03 00 02 00 c c]
CYCLE_RECORDS = 18
CYCLE_SET, CYCLE_ID = 0x0D, 196   # set $0D ids 196-213 = the records of the orange cycle (palette task)
HUE = 200 / 360
VALUE = 0.92                # a bit darker than SB5's orange
SAT = 1.1
# The fan game's picker (Character Select Edited1/2.png, 8-bit RGB) as it shows inside the frame, where
# the picker darkens the background (color math, PICK_DARKEN subtracted from each 5-bit channel): checker
# pair, heads from their darkest shade (grey entry 7) to their lightest (entry 15).
GREEN_CHECKER = ((29, 40, 29), (26, 34, 27))
GREEN_HEADS = ((17, 24, 15), (82, 113, 83))
PICK_DARKEN = 10


def _rgb(v):
    return (v & 31) / 31, (v >> 5 & 31) / 31, (v >> 10 & 31) / 31


def _bgr(r, g, b):
    return round(r * 31) | round(g * 31) << 5 | round(b * 31) << 10


def blue(v):
    """An SB5 background color in the SB6 blue, keeping its brightness."""
    if v == 0:
        return 0
    h, s, val = colorsys.rgb_to_hsv(*_rgb(v))
    return _bgr(*colorsys.hsv_to_rgb(HUE, min(1.0, s * SAT), val * VALUE))


def _lit(rgb):
    """The 5-bit color that shows as the 8-bit `rgb` once the picker darkens it."""
    r, g, b = (min(31, round(c * 31 / 255) + PICK_DARKEN) for c in rgb)
    return r | g << 5 | b << 10


def green(v, lo=0x42, hi=0xDE):
    """A grey head color of Battle's picker (8-bit grey lo..hi) in the fan game's green."""
    if v == 0:
        return 0
    t = min(1.0, max(0.0, ((v & 31) * 255 / 31 - lo) / (hi - lo)))
    a, b = GREEN_HEADS
    return _lit(tuple(x + t * (y - x) for x, y in zip(a, b)))


def _palette(rom, pid):
    addr = 0xC10000 | struct.unpack_from("<H", rom, off(SET3_TABLE + 2 * (pid - 1)))[0]
    dest, count = struct.unpack_from("<HH", rom, off(addr))
    colors = list(struct.unpack_from(f"<{count}H", rom, off(addr) + 4))
    return addr, dest, colors


def apply(rb):
    """Allocates the blue copies; returns their addresses for pal_lookup."""
    cyc = bytearray(rb.d[off(CYCLE):off(CYCLE) + 8 * CYCLE_RECORDS])
    pair = set()
    for k in range(CYCLE_RECORDS):
        start, n, a, b = struct.unpack_from("<HHHH", cyc, 8 * k)
        if (start, n) != (3, 2):
            raise RuntimeError(f"checker cycle record {k} is not [3, 2, c, c]")
        pair |= {a, b}
    if pair != {0x3634, 0x2DD1}:
        raise RuntimeError(f"checker cycle colors {sorted(map(hex, pair))}, expected the orange pair")
    new = bytearray(cyc)
    for k in range(CYCLE_RECORDS):
        _, _, a, b = struct.unpack_from("<HHHH", cyc, 8 * k)
        struct.pack_into("<HH", new, 8 * k + 4, blue(a), blue(b))
    rb.patch(CYCLE, bytes(cyc), bytes(new), "Normal menu: checker cycle colors in blue")

    g1, g2 = (_lit(c) for c in GREEN_CHECKER)
    blobs = []
    for pid in (MENU_ID, PICK_ID):
        _, dest, colors = _palette(rb.d, pid)
        if dest != 0 or len(colors) < 16:
            raise RuntimeError(f"set 3 palette {pid}: not a screen palette from CGRAM 0")
        keep = colors[6]
        if pid == PICK_ID:                          # the fan game's green, its checker pair
            colors[1:16] = [green(c) for c in colors[1:16]]
            colors[3], colors[4] = g1, g2
            colors[6] = keep                        # the red X of the grid
        else:
            colors[1:16] = [blue(c) for c in colors[1:16]]
        blobs.append(struct.pack("<HH", dest, len(colors)) + struct.pack(f"<{len(colors)}H", *colors))
    # the menu's checker cycle steps in the picker's green (orange pair -> the fan game's pair)
    to_green = {0x3634: g1, 0x2DD1: g2}
    for k in range(CYCLE_RECORDS):
        _, _, a, b = struct.unpack_from("<HHHH", cyc, 8 * k)
        blobs.append(struct.pack("<HHHH", 3, 2, to_green[a], to_green[b]))
    # the lookup reads [table + 2 * index]: entry 0 = menu, 1 = picker, 2 + k = cycle step k (one bank)
    size = sum(map(len, blobs)) + 2 * len(blobs)
    table = rb.alloc("bulk", bytes(size), "Normal menu / picker: background palettes, green cycle steps, table")
    at, words = table + 2 * len(blobs), []
    for blob in blobs:
        rb.d[off(at):off(at) + len(blob)] = blob
        words.append(at & 0xFFFF)
        at += len(blob)
    rb.d[off(table):off(table) + 2 * len(blobs)] = struct.pack(f"<{len(words)}H", *words)
    return dict(table=table, checker=(blue(0x3634), blue(0x2DD1)), cycle_set=CYCLE_SET, cycle_id=CYCLE_ID,
                cycle_n=CYCLE_RECORDS)
