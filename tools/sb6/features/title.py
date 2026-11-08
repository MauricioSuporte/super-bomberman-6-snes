"""Title screen: Super Bomberman 6 background, characters and logo.

How the original title is built (SB5, verified with Mesen traces):
  * Intro path (mode $A9) setup script $C6:FC93 and title-without-intro path
    (mode 2, handler list $C7:1783: 2 = $C7:17D1 load, 4 = $C7:17DE sprites,
    6 = $C7:17E3 draw) load, in graphics set 3:
      27 07  BG1/BG2 tiles (archive 7, $5CC0 bytes at VRAM $0000)
      27 96  BG3 font             2A 09  128 BG colors     2A 08  BG3 text colors
      FF 8D 03 04 01 00 00        logo arrangement 3 of set 4 on BG1
      FF 8D 02 04 02 00 00        scene arrangement 2 of set 4 on BG2
  * 2C 12/13/14 02 start palette-cycling tasks (palettes 6-7) for the SB5 logo.
  * $C6:FEAC / $C6:FEBC (intro) and $C7:1821 (mode 2) create the two SB5
    characters (objects 43/44).
Archive 7 and palette 9 are shared with another scene ($C6:EB1A), so the hack
does not touch them: it adds graphics set 5 (empty in all three set tables)
with its own archive, palette and arrangements, and redirects the title
scripts to sub-scripts in free space.
"""
import os

from PIL import Image

from .. import lz
from ..compose import compose_background, compose_logo, load_layout
from ..snesgfx import (Layer, PaletteSlot, TileSet, best_palettes, build_layer_map,
                       cgram_block)

SET = 5                   # new graphics set used by the SB6 title
VRAM_TILE_LIMIT = 0x3000  # words: BG1/BG2 maps start at VRAM $3000
TEXT_ENTRIES = (1, 2, 3)  # CGRAM 1-3: BG3 text colors (palette 8 of set 3)

# Script VM helpers (see docs/ROM_MAP.md).
def call(addr):
    return bytes([0x24, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16])


def skip(n):
    return bytes([0x45, n])


def arrangement(width, height, x, y, words):
    """FF 8D arrangement: w, h, x, y, mode 0, low-byte stream, high-byte stream.

    The width must be even: $C0:0135 reads two entries per loop step."""
    if width % 2 or not 0 < width <= 64 or len(words) != width * height:
        raise ValueError(f"bad arrangement size {width}x{height}")
    lo = bytes(w & 0xFF for w in words)
    hi = bytes(w >> 8 for w in words)
    # One part; $C0:0064 keeps drawing parts until a zero width byte.
    return bytes([width, height, x, y, 0]) + lz.compress(lo) + lz.compress(hi) + b"\x00"


def _trim(words, tw, th):
    rows = [r for r in range(th) if any(words[r * tw + c] for c in range(tw))]
    cols = [c for c in range(tw) if any(words[r * tw + c] for r in range(th))]
    r0, r1, c0, c1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    if (c1 - c0) % 2:  # the FF 8D row writer consumes two entries per step
        c1 = c1 + 1 if c1 < tw else c1
        c0 = c0 - 1 if (c1 - c0) % 2 else c0
    sub = [words[r * tw + c] for r in range(r0, r1) for c in range(c0, c1)]
    return sub, c1 - c0, r1 - r0, c0, r0


def convert(asset_dir, starts):
    layout = load_layout(asset_dir)
    background = compose_background(asset_dir, layout)
    logo, (lx, ly) = compose_logo(asset_dir, layout)
    logo_canvas = Image.new("RGBA", (256, (ly + logo.height + 7) // 8 * 8), (0, 0, 0, 0))
    logo_canvas.paste(logo, (lx, ly))

    bg2 = Layer("bg2", background, opaque_required=True)
    bg1 = Layer("bg1", logo_canvas, opaque_required=False)

    def make_slots():
        free0 = [e for e in range(1, 16) if e not in TEXT_ENTRIES]
        return [PaletteSlot(0, free0)] + [PaletteSlot(i, range(1, 16)) for i in range(1, 8)]

    assignment, slots, err, start = best_palettes([bg1, bg2], make_slots, starts)
    by_index = {s.index: s for s in slots}
    tiles = TileSet()
    bg1_words, bg1_prev = build_layer_map(bg1, assignment, by_index, tiles)
    bg2_words, bg2_prev = build_layer_map(bg2, assignment, by_index, tiles)
    preview = bg2_prev.copy()
    preview.alpha_composite(bg1_prev, (0, 0))
    target = background.copy()
    target.alpha_composite(logo_canvas, (0, 0))
    return dict(layout=layout, slots=slots, tiles=tiles, error=err, start=start,
                bg1=(bg1_words, bg1.tw, bg1.th), bg2=(bg2_words, bg2.tw, bg2.th),
                preview=preview, target=target)


def apply(rb, asset_dir, out_dir, starts):
    conv = convert(asset_dir, starts)
    tiles = conv["tiles"].data()
    if len(tiles) // 2 > VRAM_TILE_LIMIT:
        raise ValueError(f"title uses {len(tiles) // 32} tiles; VRAM limit is {VRAM_TILE_LIMIT // 16}")

    # Original BG3 text colors (palette 8 of set 3) keep CGRAM 0-3.
    pal_tab3 = 0x810000 | rb.rw(0xC00379 + 2 * 3)
    text_pal = 0x810000 | rb.rw(pal_tab3 + 2 * (8 - 1))
    reserved = {k: rb.rw(text_pal + 4 + 2 * k) for k in range(4)}
    colors = cgram_block(conv["slots"], reserved)

    # ---- data in free space ----------------------------------------------
    tiles_addr = rb.alloc("bulk", tiles, "title: BG1/BG2 4bpp tiles (raw)")

    # Archive table for set 5 (bank $E3): [vram, size, src24, flags]; flag $80 = raw, 2 = BG tiles.
    arc_entry = rb.le16(0x0000) + rb.le16(len(tiles)) + rb.le24(tiles_addr) + bytes([0x82])
    arc_table = rb.alloc("e3_tables", arc_entry, "set 5 archive table (entry 1 = title tiles)")

    # Palette table for set 5 (bank $81): word pointer -> [dest, count, colors].
    pal_entry = rb.le16(0) + rb.le16(128) + b"".join(rb.le16(c) for c in colors)
    pal_table = rb.alloc("bank81", bytes(2) + pal_entry, "set 5 palette table + title palette 1")
    rb.d[pal_table & 0x3FFFFF:(pal_table & 0x3FFFFF) + 2] = rb.le16((pal_table + 2) & 0xFFFF)

    # Arrangement table for set 5 (any bank; entries are in the table's bank).
    w1, tw1, th1 = conv["bg1"]
    sub1, aw1, ah1, ax1, ay1 = _trim(w1, tw1, th1)
    w2, tw2, th2 = conv["bg2"]
    arr1 = arrangement(aw1, ah1, ax1, ay1, sub1)
    arr2 = arrangement(tw2, th2, 0, 0, w2)
    blob = bytearray(4) + arr1 + arr2
    arr_table = rb.alloc("bulk", bytes(blob), "set 5 arrangement table + title arrangements 1 (logo), 2 (scene)")
    blob[0:2] = rb.le16((arr_table + 4) & 0xFFFF)
    blob[2:4] = rb.le16((arr_table + 4 + len(arr1)) & 0xFFFF)
    o = arr_table & 0x3FFFFF
    rb.d[o:o + len(blob)] = blob

    # Sub-scripts.
    loadgfx = bytes([0x26, SET, 0x27, 0x01, 0x2A, 0x01,     # SB6 tiles + colors
                     0x26, 0x03, 0x27, 0x96, 0x2A, 0x08,     # SB5 BG3 font + text colors
                     0x00])
    draw = bytes([0xFF, 0x8D, 0x01, SET, 0x01, 0x00, 0x00,  # logo on BG1
                  0xFF, 0x8D, 0x02, SET, 0x02, 0x00, 0x00,  # scene on BG2
                  0x00])
    s_load = rb.alloc("bulk", loadgfx, "script: title graphics load (set 5)")
    s_draw = rb.alloc("bulk", draw, "script: title arrangements draw (set 5)")
    s_null = rb.alloc("bulk", b"\x00", "script: empty (returns)")

    # ---- hook the set tables (set 5 is null in all of them) ----------------
    rb.patch(0xC01C96 + 2 * SET, b"\x00\x00", rb.le16(arc_table & 0xFFFF), "archive set 5 -> $E3 table")
    rb.patch(0xC00379 + 2 * SET, b"\x00\x00", rb.le16(pal_table & 0xFFFF), "palette set 5 -> $81 table")
    rb.patch(0xC08000 + 3 * SET, b"\x00\x00\x00", rb.le24(arr_table), "arrangement set 5 -> table")

    # ---- intro path (mode $A9) --------------------------------------------
    rb.patch(0xC6FC93,
             bytes.fromhex("26 03 27 07 27 96 2A 09 2A 08 28 61 28 62 FF 8D 03 04 01 00 00 FF 8D 02 04 02 00 00"),
             call(s_load) + call(s_draw) + skip(18), "intro title: load/draw SB6 title")
    rb.patch(0xC6FCBB, bytes.fromhex("2C 12 02 2C 13 02 2C 14 02"), skip(7),
             "intro title: no SB5 logo palette cycling")
    rb.patch(0xC6FD7C, bytes.fromhex("24 AC FE C6"), call(s_null), "intro title: no SB5 character (left)")
    rb.patch(0xC6FDC9, bytes.fromhex("24 BC FE C6"), call(s_null), "intro title: no SB5 character (right)")

    # ---- title without intro (mode 2, handler list $C7:1783) ---------------
    rb.patch(0xC717D1, bytes.fromhex("26 03 27 07 27 96 2A 09 2A 08 26 03 00"), call(s_load) + b"\x00",
             "mode 2 handler 2: load SB6 title")
    rb.patch(0xC717DE, bytes.fromhex("28 61 28 62 00"), b"\x00", "mode 2 handler 4: no SB5 character sprites")
    rb.patch(0xC717E6, bytes.fromhex("FF 8D 03 04 01 00 00 FF 8D 02 04 02 00 00"),
             call(s_draw) + skip(8), "mode 2 handler 6: draw SB6 title")
    rb.patch(0xC71821, bytes.fromhex("3A 44 D0 00 C0 00 40 01 40 02 3A 43 20 00 C0 00"), skip(14),
             "mode 2: no SB5 characters")
    rb.patch(0xC71832, bytes.fromhex("2C 12 02 2C 13 02 2C 14 02"), skip(7),
             "mode 2: no SB5 logo palette cycling")

    os.makedirs(out_dir, exist_ok=True)
    side = Image.new("RGB", (512, 224))
    side.paste(conv["target"].convert("RGB"), (0, 0))
    side.paste(conv["preview"].convert("RGB"), (256, 0))
    side.resize((1024, 448), Image.NEAREST).save(os.path.join(out_dir, "title_preview.png"))
    return dict(tiles=len(tiles) // 32, error=conv["error"], start=conv["start"],
                arr_bytes=len(arr1) + len(arr2))
