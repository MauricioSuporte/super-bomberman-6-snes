"""Bluish background in the Normal Game's menu (file lists) and picker.

SB5 draws that background (checkerboard + Bomberman / rabbit heads) with
palette 0 of the screen's palette, set 3:

  * id 14 (`$81:9796`, 80 colors from CGRAM 0): the Normal menu, orange;
  * id 70 (`$81:A9F6`, 48 colors): Battle's picker, green checker and grey
    heads; the Normal Game reuses it, so its picker opened green and turned
    orange once the menu's checker animation wrote entries 3-4 again.

The checker scrolls by swapping entries 3-4 from a cycle table (`$81:E216`,
records `[3, 2, color, color]`, orange; Battle's green one follows it).

The hack recolors palette 0 (entries 1-15) of copies of ids 14 and 70 to the
SB6 fan game's blue (BackgroundNormalGame1.png): same brightness, hue ~200
degrees (the picker keeps entry 6, the red X of its grid). `pal_lookup` (asm/bombers.asm) returns them for set 3 id 14 in mode
3 and id 70 while the Normal Game's picker runs (`$7F:FF00` = 1); Battle
keeps its palettes. The orange cycle table is only the Normal menu's, so it
is patched in place.
"""
import colorsys
import struct

from ..romlib import off

SET3_TABLE = 0xC190EA       # set 3's word table (bank $81 = $C1), entry per id - 1
MENU_ID, PICK_ID = 14, 70
CYCLE = 0xC1E216            # orange checker cycle: 18 records of [03 00 02 00 c c]
CYCLE_RECORDS = 18
HUE = 200 / 360
VALUE = 0.92                # a bit darker than SB5's orange
SAT = 1.1


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

    out = {}
    for pid in (MENU_ID, PICK_ID):
        _, dest, colors = _palette(rb.d, pid)
        if dest != 0 or len(colors) < 16:
            raise RuntimeError(f"set 3 palette {pid}: not a screen palette from CGRAM 0")
        keep = colors[6]
        colors[1:16] = [blue(c) for c in colors[1:16]]
        if pid == PICK_ID:                          # the checker as on the menu (no green frames)
            colors[3], colors[4] = blue(0x3634), blue(0x2DD1)
            colors[6] = keep                        # the red X of the grid

        blob = struct.pack("<HH", dest, len(colors)) + struct.pack(f"<{len(colors)}H", *colors)
        out[pid] = rb.alloc("bulk", blob, f"Normal menu: set 3 palette {pid} with a blue background")
    # the lookup reads [table + 2 * index]: entry 0 = menu, 1 = picker (same bank)
    if out[MENU_ID] >> 16 != out[PICK_ID] >> 16:
        raise RuntimeError("blue menu palettes in different banks")
    table = rb.alloc("bulk", struct.pack("<HH", out[MENU_ID] & 0xFFFF, out[PICK_ID] & 0xFFFF),
                     "Normal menu: table of the blue background palettes (pal_lookup)")
    if table >> 16 != out[MENU_ID] >> 16:
        raise RuntimeError("blue menu palette table not in the palettes' bank")
    return dict(table=table, checker=(blue(0x3634), blue(0x2DD1)))
