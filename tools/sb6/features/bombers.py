"""Player bomber (character 0) from the pose sheet assets/bombers/bomber.png.

The sheet (tools/bomber_sheet.py) is cut into pieces by sb6.bomber.convert:

* tiles: 1 KB strips in the `obj` banks, as new sheets of the relocated OBJ
  sheet table (sb6.objsheets);
* `$80:BB7A`: `[sheet, row]` of each animation (patched in place);
* mappings: a new table for type $10 (region `objmap`, bank $B3), selected by `bomber_map`
  (asm/bombers.asm) for seat bombers of character 0;
* animation scripts: with assets/bombers/bomber_anims.txt, a new script table
  for the same bombers (`bomber_anim`), also in `objmap`; `bomber_loop` lets a
  type $10 script restart in the middle.
"""
import os

from .. import asar, bomber
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "bombers.asm")
STRIPS_PER_SHEET = 32        # 32 KB per sheet; row = 2 * strip (byte, doubled by $C5:6BAD)


PAL_TABLE = 0x818000         # set 0 palette pointers; ids 1-4 = white, black, red, blue
PAL_IDS = 4


def apply(rb, base_rom, sheets, sheet_path, palette_path=None, scripts_path=None):
    """`sheets`: sb6.objsheets.ObjSheets. sheet_path alone: SB5 colors. With palette_path (one pixel per color,
    column 0 = colors painted in the sheet, columns 1-4 = white, black, red,
    blue) the bomber palettes 1-4 are replaced by 15-color ones."""
    if not os.path.exists(sheet_path):
        return None
    palettes, notes = [], {}
    try:
        scripted = bool(scripts_path and os.path.exists(scripts_path))
        br = bomber.BomberRom(base_rom, bomber.load_scripts(scripts_path) if scripted else None)
        if palette_path:
            cells, palettes, notes = bomber.read_sheet_recolor(br, sheet_path, palette_path)
            inexact = notes["snapped"]
        else:
            cells, inexact = bomber.read_sheet(br, sheet_path)
        strips, anim_strip, mappings = bomber.convert(br, cells)
    except ValueError as e:
        raise BuildError(f"{os.path.basename(sheet_path)}: {e}")

    # tiles
    first_sheet = sheets.next_id
    for i in range(0, len(strips), STRIPS_PER_SHEET):
        blob = b"".join(strips[i:i + STRIPS_PER_SHEET])
        sheets.add(blob, f"bomber: tiles, sheet {first_sheet + i // STRIPS_PER_SHEET}")

    # [sheet, row] per animation of character 0
    ct = br.char_table(0)
    old = bytes(base_rom[off(ct):off(ct) + 2 * bomber.ANIMS])
    new = bytearray()
    for a in range(1, bomber.ANIMS + 1):
        s = anim_strip[a]
        new += bytes([first_sheet + s // STRIPS_PER_SHEET, 2 * (s % STRIPS_PER_SHEET)])
    rb.patch(ct, old, bytes(new), "bomber: sheet/row of each animation (character 0)")

    # mappings: word table + data in one bank; ids without a pose keep the stock data
    count = max([br.map_table_len()] + list(br.new_maps.values()))
    blobs = []
    for m in range(1, count + 1):
        if m in mappings:
            a = next(a for a, maps in br.poses() if m in maps)
            blobs.append(bomber.encode_mapping(mappings[m], 2 * (anim_strip[a] % STRIPS_PER_SHEET)))
        elif m > br.map_table_len():
            blobs.append(bomber.encode_mapping([], 0))
        else:
            p = off(br.map_addr(m))
            n = base_rom[p]
            blobs.append(bytes(base_rom[p:p + 1 + 7 * n]) if n < 32 else b"\x01" + bytes(7))
    # The OAM builder ($C0:152E) makes the table's bank the data bank and still
    # addresses WRAM, so the table is referenced through the $80-$BF mirror.
    start = rb.regions["objmap"].cursor
    data, pos = bytearray(), (start & 0xFFFF) + 2 * count
    for b in blobs:
        data += bytes([pos & 0xFF, pos >> 8 & 0xFF])
        pos += len(b)
    maptab = rb.alloc("objmap", bytes(data) + b"".join(blobs), "bomber: sprite mappings (type $10, character 0)")
    if maptab != start:
        raise BuildError("bomber mappings moved")
    maptab = maptab & 0x3FFFFF | 0x800000

    # animation scripts (same bank rule: $C0:11F8 makes the table's bank the
    # data bank). Every stock script of type $10 ends in `00 00`, which
    # bomber_loop reads as "restart at offset 0".
    animtab = maptab
    if br.scripts:
        blobs = [br.script_bytes(a) for a in range(1, bomber.ANIMS + 1)]
        start = rb.regions["objmap"].cursor
        data, pos = bytearray(), (start & 0xFFFF) + 2 * len(blobs)
        for b in blobs:
            data += bytes([pos & 0xFF, pos >> 8 & 0xFF])
            pos += len(b)
        animtab = rb.alloc("objmap", bytes(data) + b"".join(blobs), "bomber: animation scripts (type $10, character 0)")
        if animtab != start:
            raise BuildError("bomber scripts moved")
        animtab = animtab & 0x3FFFFF | 0x800000

    # palettes: [dest, count, 16 colors] like the stock entries (dest/count are
    # overridden by $C4:37B0), pointer words of set 0 repointed
    for i, colors in enumerate(palettes[:PAL_IDS]):
        blob = bytearray([0x80, 0, 0x10, 0, 0, 0])
        for r, g, b in colors:
            v = r >> 3 | (g >> 3) << 5 | (b >> 3) << 10
            blob += bytes([v & 0xFF, v >> 8])
        addr = rb.alloc("bank81", bytes(blob), f"bomber: palette {i + 1} (15 colors)")
        word = PAL_TABLE + 2 * i
        rb.patch(word, bytes(base_rom[off(word):off(word) + 2]), bytes([addr & 0xFF, addr >> 8 & 0xFF]),
                 f"bomber: palette {i + 1} pointer")

    # hook
    reg = rb.regions["bulk"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"E4": f"${reg.cursor:06X}", "MAPTAB": f"${maptab:06X}",
                                                "ANIMTAB": f"${animtab:06X}",
                                                "PALS": str(PAL_IDS)})
    start, end = reg.cursor, syms["end_e4"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"bombers.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "bomber: mapping selector (asm/bombers.asm)")
    hook = syms["bomber_map"]
    rb.patch(0xC012A4, bytes.fromhex("B9 9F 04 3A"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
             "bomber: mapping table of seat bombers")
    if br.scripts:
        hook = syms["bomber_anim"]
        rb.patch(0xC0120E, bytes.fromhex("BF 1F 17 C0"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: animation scripts of seat bombers")
        hook = syms["bomber_loop"]
        rb.patch(0xC0126A, bytes.fromhex("C9 00 D0 06 99 FF 07"),
                 bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16, 0xD0, 0x04, 0xEA]),
                 "bomber: script restart offset")
    if palettes:
        hook = syms["bomber_palcount"]
        rb.patch(0xC437C1, bytes.fromhex("A9 09 85 AB"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: 16-color palettes for ids 1-4")
    pieces = [len(p) for p in mappings.values()]
    return dict(strips=len(strips), poses=len(mappings), max_pieces=max(pieces), inexact=inexact, notes=notes,
                scripts=len(br.scripts))
