"""Player bombers from the pose sheets of assets/bombers: Bomberman (character
0, bomber.png or bomber_sb6.png) and the other nine characters
(char<n>_sb6.png + char<n>_pallete.png, inserted once they differ from the
cartridge's art or colors; only the edited animations get new tiles).

A sheet (tools/bomber_sheet.py) is cut into pieces by sb6.bomber.convert:

* tiles: 1 KB strips in the `obj` banks, as new sheets of the relocated OBJ
  sheet table (sb6.objsheets);
* `$80:BB66 + 2*character` -> `[sheet, row]` of each animation (patched in place);
* mappings: a new table for the character's type (regions `objmap*`, banks
  $B3-$B5), selected by `bomber_map` (asm/bombers.asm) for seat bombers of
  that character;
* animation scripts: with assets/bombers/<name>_anims.txt, a new script table
  for the same bombers (`bomber_anim`), also in `objmap*`; `bomber_loop` lets
  a bomber script restart in the middle;
* palettes of characters 1-9: 16-color entries after Bomberman's in the
  `pal_lookup` table, which replace the stock ids through a byte table.
"""
import os

import numpy as np
from PIL import Image

from .. import asar, bomber
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "bombers.asm")
STRIPS_PER_SHEET = 32        # 32 KB per sheet; row = 2 * strip (byte, doubled by $C5:6BAD)


PAL_TABLE = 0x818000         # set 0 palette pointers; ids 1-6 = the cartridge's six bomber colors
PAL_IDS = 6                  # replaced in place by the first columns of the palette picture
OWN_ID = 0x5A                # every column is also palette id OWN_ID + n of set 0 (pal_lookup;
                             # the cartridge's set 0 ends at id $59)
STAND = 0x02                 # animation whose first pose faces the screen (walk down)
OBJMAP = ["objmap", "objmap2", "objmap3"]
STREAM = [f"stream_{b:02x}" for b in range(0xEC, 0xF0)]   # pose blocks (tools/build.py)
CHARS = range(1, 10)         # characters with a char<n>_sb6.png sheet
VARIANTS = 6                 # color variants of each of them (palette ids $80:BB4E[char] + n)
XLAT_IDS = 0x50
LIFT_TABLE = 0xC5242C        # height of the bomb lifted with the Power Glove, per character ($C5:2403)
CARRY_ANIMS = range(0x2F, 0x3B)   # walking / standing with the bomb lifted
SEAT_ID = 0xFC               # ids $FC-$FF: the palette entry chosen by seat 0-3 (picker, past the direct ids)
SEAT_IDX = 0x7FFC48          # 4 bytes: those entries (docs/FREE_SPACE.md, picker block)
WALKS, STANDS = 0x01, 0x46   # walk / stand animations, d = 0 right, 1 down, 2 left, 3 up
FRONT = 0x47                 # standing, facing the screen (portrait of a character without one)
# Characters that keep walking in place when they stop (SB6 Unity's
# MovementController.AnimateFootstepsAtRest, set for CossackBomber): their
# stand animations play the walk's poses; SB5's idle $15 still comes later.
WALK_AT_REST = {7}


def _carry_top(br, cells):
    """Highest drawn row of the poses carrying a bomb (cell coordinates)."""
    tops = []
    for a, maps in br.poses():
        if a in CARRY_ANIMS:
            for m in maps:
                ys = np.nonzero(cells[(a, m)])[0]
                if len(ys):
                    tops.append(int(ys.min()))
    return min(tops) if tops else None


def _table(rb, blobs, label):
    """Word table + its data in one bank, addressed through the $80-$BF mirror
    (the engine makes the table's bank the data bank and still reads WRAM)."""
    size = 2 * len(blobs) + sum(len(b) for b in blobs)
    for name in OBJMAP:
        reg = rb.regions[name]
        if reg.free() < size:
            continue
        start = reg.cursor
        data, pos = bytearray(), (start & 0xFFFF) + 2 * len(blobs)
        for b in blobs:
            data += bytes([pos & 0xFF, pos >> 8 & 0xFF])
            pos += len(b)
        if rb.alloc(name, bytes(data) + b"".join(blobs), label) != start:
            raise BuildError(f"{label} moved")
        return start & 0x3FFFFF | 0x800000
    raise BuildError(f"no room for {label} ({size} bytes) in {OBJMAP}")


def _insert(rb, base_rom, sheets, br, cells, name, only=None):
    """Tiles, `[sheet, row]` table, mappings and scripts of one character.
    `only`: animations to convert; the others keep the cartridge's tiles and pieces."""
    strips, anim_strip, mappings, streamed = bomber.convert(br, cells, only, stream=True)
    stream = _stream_blocks(rb, streamed, name)

    first_sheet = sheets.next_id
    for i in range(0, len(strips), STRIPS_PER_SHEET):
        blob = b"".join(strips[i:i + STRIPS_PER_SHEET])
        sheets.add(blob, f"{name}: tiles, sheet {first_sheet + i // STRIPS_PER_SHEET}")

    ct = br.char_table(br.char)
    old = bytes(base_rom[off(ct):off(ct) + 2 * bomber.ANIMS])
    new = bytearray(old)
    for a, s in anim_strip.items():
        new[2 * (a - 1):2 * a] = bytes([first_sheet + s // STRIPS_PER_SHEET, 2 * (s % STRIPS_PER_SHEET)])
    if new != old:
        rb.patch(ct, old, bytes(new), f"{name}: sheet/row of each animation (character {br.char})")

    # mappings: ids without a new pose keep the stock data
    count = max([br.map_table_len()] + list(br.new_maps.values()))
    owner = {m: a for a, maps in br.poses() for m in maps}
    blobs = []
    for m in range(1, count + 1):
        if m in mappings:   # (a streamed pose counts its tiles from its block: row 0)
            row = 0 if owner[m] in streamed else 2 * (anim_strip[owner[m]] % STRIPS_PER_SHEET)
            blobs.append(bomber.encode_mapping(mappings[m], row))
        elif m > br.map_table_len():
            blobs.append(bomber.encode_mapping([], 0))
        else:
            p = off(br.map_addr(m))
            n = base_rom[p]
            blobs.append(bytes(base_rom[p:p + 1 + 7 * n]) if n < 32 else b"\x01" + bytes(7))
    maptab = _table(rb, blobs, f"{name}: sprite mappings (type ${br.type:02X})")

    # animation scripts. Every stock script of the bomber types ends in
    # `00 00`, which bomber_loop reads as "restart at offset 0".
    animtab = 0
    if br.scripts:
        animtab = _table(rb, [br.script_bytes(a) for a in range(1, bomber.ANIMS + 1)],
                         f"{name}: animation scripts (type ${br.type:02X})")
    return dict(maptab=maptab, animtab=animtab, strips=len(strips), mappings=mappings, ct=bytes(new), blobs=blobs,
                stream=stream, streamed=sorted(streamed), count=count)


def _stream_blocks(rb, streamed, name):
    """Pose blocks of the streamed animations -> {mapping: (address, columns, animation)}."""
    out = {}
    for a, poses in sorted(streamed.items()):
        for m, (block, w) in sorted(poses.items()):
            if m in out:    # bomber_stream tells a pose of the current animation by its entry
                raise BuildError(f"{name}: pose {m:02X} is streamed in animations {out[m][2]:02X} and {a:02X}")
            region = next((r for r in STREAM if rb.regions[r].free() >= len(block)), None)
            if region is None:
                raise BuildError(f"{name}: no room for the streamed poses ({STREAM})")
            out[m] = (rb.alloc(region, block, f"{name}: animation {a:02X}, pose {m:02X} ({w} columns, streamed)"), w, a)
    return out


def _stream_table(rb, stream, count, name):
    """[source16, animation, columns | (source bank - $EC) << 4] per mapping id 1..count
    (columns 0 = not streamed), in bank $E4. The animation lets bomber_stream skip the
    ids the script interpreter resolves for one call at a loop point (`[`).
    Returns the 3-byte CHARSTREAM entry: offset16 in the bank, count."""
    if not stream:
        return bytes(3)
    data = bytearray()
    for m in range(1, count + 1):
        src, w, a = stream.get(m, (0, 0, 0))
        if w and not (0xEC <= src >> 16 <= 0xEF and 1 <= w <= 8):
            raise BuildError(f"{name}: streamed pose {m:02X} must be in banks $EC-$EF with 1-8 columns")
        data += bytes([src & 0xFF, src >> 8 & 0xFF, a, w | ((src >> 16) - 0xEC) << 4 if w else 0])
    addr = rb.alloc("bulk", bytes(data), f"{name}: streamed poses (source, columns) per mapping")
    if addr >> 16 != 0xE4 or count > 255:
        raise BuildError(f"{name}: stream table must be in bank $E4 with at most 255 mappings")
    return bytes([addr & 0xFF, addr >> 8 & 0xFF, count])


def _pal_blob(colors):
    """[dest, count, 16 colors] like the stock entries (dest/count are overridden by $C4:37B0)."""
    blob = bytearray([0x80, 0, 0x10, 0, 0, 0])
    for r, g, b in colors:
        v = r >> 3 | (g >> 3) << 5 | (b >> 3) << 10
        blob += bytes([v & 0xFF, v >> 8])
    return bytes(blob)


def _char_palettes(bomber_pal, char_pal, used):
    """Palettes of a character from its picture in BombermanPallete.png's format
    (column 0 = Bomberman's key colors, columns 1.. = its colors), in the
    order of Bomberman's palette entries (`used`). Rows missing from the
    picture keep Bomberman's colors."""
    bp = np.asarray(Image.open(bomber_pal).convert("RGB"), dtype=np.int32)
    cp = np.asarray(Image.open(char_pal).convert("RGB"), dtype=np.int32)
    cols = cp.shape[1] - 1
    if cols < 1:
        raise ValueError(f"{char_pal}: precisa da coluna de cores-chave e pelo menos uma cor")
    rows = {tuple(int(v) for v in cp[r, 0]): r for r in range(cp.shape[0])}

    def color(e, n):
        k = tuple(int(v) for v in bp[e[1], 0]) if e[0] == "row" else e[1]
        if k in rows:
            return tuple(int(v) for v in cp[rows[k], 1 + n])
        if e[0] == "fixed":
            return e[1]
        return tuple(int(v) for v in bp[e[1], 1 + min(n, bp.shape[1] - 2)])

    pals = [[color(e, n) for e in used] for n in range(cols)]
    return [q + [(0, 0, 0)] * (15 - len(q)) for q in pals]


def _key_column(path):
    """Key colors (column 0) of a palette picture."""
    im = Image.open(path).convert("RGB")
    return [im.getpixel((0, y)) for y in range(im.height)]


PICK_ANIMS = (0x02, 0x20)       # walk down, victory: the picker's row of chosen characters


def _pick_anims(br, cells):
    """{animation: [(pose indices 64x64 or None, frames)]} of the picker's animations."""
    return {a: [(cells.get((a, m)) if m else None, f) for m, f in br.anim(a)] for a in PICK_ANIMS}


def _characters(rb, base_rom, sheets, bdir, charmap, charanim, all_pals, xlat, ref):
    """Characters 1-9, laid out like Bomberman (char<n>_sb6.png +
    char<n>_pallete.png, optional char<n>_anims.txt over bomber_anims.txt).
    `ref`: Bomberman's sheet, cells, layout, palettes and final tables. Every
    character with a sheet is inserted (one still equal to Bomberman's costs
    only its tables). Animations equal to Bomberman's use his tiles and
    pieces; only the edited ones get new tiles."""
    done = []
    bkeys = _key_column(ref["palette"])
    fixed = [tuple(c) for c in ref["notes"]["fixed"]]

    # characters painted with the key colors of their own palette picture:
    # those with the same picture share one color layout (and its palettes)
    # when their colors fit in 15 entries together
    pre, groups = {}, {}
    for c in CHARS:
        sheet, pal = os.path.join(bdir, f"char{c}_sb6.png"), os.path.join(bdir, f"char{c}_pallete.png")
        scripts = os.path.join(bdir, f"char{c}_anims.txt")
        if not (os.path.exists(sheet) and os.path.exists(pal)) or _key_column(pal) == bkeys:
            continue
        try:
            own = bomber.load_scripts(scripts, ref["br"].cols) if os.path.exists(scripts) else {}
            brc = bomber.BomberRom(base_rom, {**ref["br"].scripts, **own}, 0)
            raw, counts, loose = bomber.sheet_pixels(brc, sheet, ref["sheet"])
            blank = not counts
            if blank:       # nothing painted yet: Bomberman's art and sequences, the character's colors
                own, brc = {}, bomber.BomberRom(base_rom, dict(ref["br"].scripts), 0)
                raw, counts, loose = bomber.sheet_pixels(brc, ref["sheet"], ref["sheet"])
        except ValueError as e:
            raise BuildError(f"char{c}: {e}")
        pre[c] = dict(own=own, brc=brc, raw=raw, counts=counts, blank=blank, loose=loose)
        with open(pal, "rb") as fh:
            groups.setdefault(fh.read(), []).append(c)
    for members in groups.values():
        pal = os.path.join(bdir, f"char{members[0]}_pallete.png")
        total, loose = {}, set()
        for c in members:
            loose |= pre[c]["loose"]
            for k, n in pre[c]["counts"].items():
                total[k] = total.get(k, 0) + n
        try:
            layout = bomber.own_layout(total, pal, fixed, loose)
            for c in members:
                pre[c]["layout"] = layout
        except ValueError:
            for c in members:
                try:
                    pre[c]["layout"] = bomber.own_layout(pre[c]["counts"], pal, fixed, pre[c]["loose"], merge=True)
                except ValueError as e:
                    raise BuildError(f"char{c}: {e}")

    for c in CHARS:
        sheet, pal = os.path.join(bdir, f"char{c}_sb6.png"), os.path.join(bdir, f"char{c}_pallete.png")
        scripts = os.path.join(bdir, f"char{c}_anims.txt")
        if not (os.path.exists(sheet) and os.path.exists(pal)):
            continue
        try:
            if c in pre:
                p = pre[c]
                own, brc = p["own"], p["brc"]
                cmap, palettes, snapped, merged = p["layout"]
                cells = bomber.own_cells(p["raw"], cmap)
                edited = {a for a, maps in brc.poses() if maps}
                notes = dict(edited=len(edited), snapped=snapped, blank=p["blank"], own=True, merged=merged)
            else:
                own = bomber.load_scripts(scripts, ref["br"].cols) if os.path.exists(scripts) else {}
                brc = bomber.BomberRom(base_rom, {**ref["br"].scripts, **own}, 0)
                cells, edited, notes = bomber.read_sheet_like(brc, sheet, ref["sheet"], ref["br"], ref["cells"],
                                                              ref["notes"]["cmap"], ref["notes"]["sb5"])
                same_poses = dict(ref["br"].poses())
                edited |= {a for a, maps in brc.poses() if len(maps) != len(same_poses[a])}
                palettes = _char_palettes(ref["palette"], pal, ref["notes"]["used"])
            shared = palettes == ref["palettes"]
            info = dict(char=c, notes=notes, scripts=len(own), colors=len(palettes), shared=shared,
                        first=palettes[0],
                        **_insert_char(rb, base_rom, sheets, brc, cells, edited, c, ref))
        except ValueError as e:
            raise BuildError(f"char{c}: {e}")
        info["stand"] = cells[(STAND, dict(brc.poses())[STAND][0])]
        info["front"] = cells[(FRONT, dict(brc.poses())[FRONT][0])]
        info["pick_anims"] = _pick_anims(brc, cells)
        info["palettes"] = palettes
        # the lifted bomb sits as far above the head as on Bomberman's
        top, top0 = _carry_top(brc, cells), _carry_top(ref["br"], ref["cells"])
        if top is not None and top0 is not None:
            stock = base_rom[off(LIFT_TABLE) + c]
            info["lift"] = max(0, min(0x30, base_rom[off(LIFT_TABLE)] + top0 - top))
            if info["lift"] != stock:
                rb.patch(LIFT_TABLE + c, bytes([stock]), bytes([info["lift"]]),
                         f"char{c}: lifted bomb height (head {top0 - top:+d} px from Bomberman's)")
        charmap[c], charanim[c] = info["maptab"], info["animtab"]
        # index in the palette table of its color 0 (palettes already there are not repeated)
        info["pal0"] = next((i for i in range(len(all_pals) - len(palettes) + 1)
                             if all_pals[i:i + len(palettes)] == palettes), len(all_pals))
        if info["pal0"] == len(all_pals):
            all_pals.extend(palettes)
        base = base_rom[off(0x80BB4E) + c]                # the stock ids (Battle, co-op defaults)
        for n in range(min(VARIANTS, len(palettes))):
            xlat[base + n - 1] = info["pal0"] + n + 1
        done.append(info)
    return done


def _rest_walk(script):
    """A walk script played standing: a walking bomber runs 2 script steps
    per frame (`$0800,obj`), a standing one 1, so every pose lasts half as
    long (rounded alternately, the cycle keeps its length)."""
    out, carry = bytearray(), 0
    for i in range(0, len(script) - 2, 2):
        m, f = script[i], script[i + 1]
        if m == 0 and f == 255:          # (hide at the end: kept)
            out += script[i:i + 2]
            continue
        half = (f + carry) // 2
        carry = (f + carry) % 2
        out += bytes([m, max(1, half)])
    return bytes(out) + script[-2:]


def _insert_char(rb, base_rom, sheets, brc, cells, edited, c, ref):
    """Tables of character c laid out like Bomberman: his `[sheet, row]` and
    pieces for the animations not in `edited`, new tiles for the others."""
    name = f"char{c}"
    strips, anim_strip, mappings, streamed = bomber.convert(brc, cells, edited, stream=True)
    own_stream = _stream_blocks(rb, streamed, name)
    first_sheet = sheets.next_id
    for i in range(0, len(strips), STRIPS_PER_SHEET):
        sheets.add(b"".join(strips[i:i + STRIPS_PER_SHEET]), f"{name}: tiles, sheet {first_sheet + i // STRIPS_PER_SHEET}")

    ct = brc.char_table(c)
    old = bytes(base_rom[off(ct):off(ct) + 2 * bomber.ANIMS])
    new = bytearray(ref["info"]["ct"])
    for a, s in anim_strip.items():
        new[2 * (a - 1):2 * a] = bytes([first_sheet + s // STRIPS_PER_SHEET, 2 * (s % STRIPS_PER_SHEET)])
    at_rest = c in WALK_AT_REST
    if at_rest:
        # standing = the walk of the same facing: its strip (`$C4:4318` sends it when the bomber stops)
        if set(streamed) & {WALKS + d for d in range(4)}:
            raise BuildError(f"{name}: walks in place when standing, but its walk is streamed pose by pose")
        for d in range(4):
            w, st = WALKS + d, STANDS + d
            new[2 * (st - 1):2 * st] = new[2 * (w - 1):2 * w]
    rb.patch(ct, old, bytes(new), f"{name}: sheet/row of each animation (Bomberman's layout)")

    ids0 = {(a, k): m for a, maps in ref["br"].poses() for k, m in enumerate(maps)}
    blobs0 = ref["info"]["blobs"]
    count = max([brc.map_table_len(), len(blobs0)] + list(brc.new_maps.values()))
    blob_of, stream = {}, {}
    for a, maps in brc.poses():
        for k, m in enumerate(maps):
            if a in edited:     # (a pose its sequence never shows: empty; a streamed one: row 0)
                row = 0 if a in streamed else 2 * (anim_strip.get(a, 0) % STRIPS_PER_SHEET)
                blob_of[m] = bomber.encode_mapping(mappings.get(m, []), row)
                if m in own_stream:
                    stream[m] = own_stream[m]
            else:
                blob_of[m] = blobs0[ids0[(a, k)] - 1]
                if ids0[(a, k)] in ref["info"]["stream"]:
                    stream[m] = ref["info"]["stream"][ids0[(a, k)]]
    blobs = [blob_of.get(m, blobs0[m - 1] if m <= len(blobs0) else bomber.encode_mapping([], 0))
             for m in range(1, count + 1)]
    maptab = _table(rb, blobs, f"{name}: sprite mappings (Bomberman's layout)")
    scripts = [brc.script_bytes(a) for a in range(1, bomber.ANIMS + 1)]
    if at_rest:
        for d in range(4):
            scripts[STANDS + d - 1] = _rest_walk(scripts[WALKS + d - 1])
    animtab = _table(rb, scripts, f"{name}: animation scripts (Bomberman's sequences)")
    return dict(maptab=maptab, animtab=animtab, strips=len(strips), mappings=mappings, stream=stream,
                streamed=sorted(streamed), count=count)


def apply(rb, base_rom, sheets, sheet_path, palette_path=None, scripts_path=None, chars_dir=None, menu_bg=None,
          enemies=None):
    """`sheets`: sb6.objsheets.ObjSheets. sheet_path alone: SB5 colors. With palette_path (one pixel per color,
    column 0 = colors painted in the sheet, columns 1.. = one bomber color
    each) the bomber palettes 1-6 are replaced by 15-color ones (columns 1-6)
    and every column becomes palette id OWN_ID + n. The result then has
    `paltab`, `palcount` and `stand` (the pose facing the screen, indices).
    chars_dir: folder with the sheets of characters 1-9 (`chars` in the result)."""
    charmap, charanim = [0] * 10, [0] * 10
    palettes, notes, info0, cells, inexact, br = [], {}, None, None, 0, None
    if os.path.exists(sheet_path):
        try:
            scripted = bool(scripts_path and os.path.exists(scripts_path))
            br = bomber.BomberRom(base_rom, bomber.load_scripts(scripts_path) if scripted else None)
            if palette_path:
                cells, palettes, notes = bomber.read_sheet_recolor(br, sheet_path, palette_path)
                inexact = notes["snapped"]
            else:
                cells, inexact = bomber.read_sheet(br, sheet_path)
            info0 = _insert(rb, base_rom, sheets, br, cells, "bomber")
        except ValueError as e:
            raise BuildError(f"{os.path.basename(sheet_path)}: {e}")
        charmap[0], charanim[0] = info0["maptab"], info0["animtab"]

    # Bomberman's palettes 1-6: pointer words of set 0 repointed
    for i, colors in enumerate(palettes[:PAL_IDS]):
        addr = rb.alloc("bank81", _pal_blob(colors), f"bomber: palette {i + 1} (15 colors)")
        word = PAL_TABLE + 2 * i
        rb.patch(word, bytes(base_rom[off(word):off(word) + 2]), bytes([addr & 0xFF, addr >> 8 & 0xFF]),
                 f"bomber: palette {i + 1} pointer")

    all_pals, xlat = list(palettes), bytearray(XLAT_IDS)
    chars = []
    if chars_dir and info0 and palettes:
        ref = dict(sheet=sheet_path, palette=palette_path, br=br, cells=cells, notes=notes, palettes=palettes,
                   info=info0)
        chars = _characters(rb, base_rom, sheets, chars_dir, charmap, charanim, all_pals, xlat, ref)
    if not (info0 or chars):
        return None

    # every palette: word table + data in one bank (ids OWN_ID + n; the characters' through xlat)
    paltab = 0
    # ids OWN_ID..SEAT_ID-1 name the table's entries; the entries past them
    # are only reached through the per-seat ids SEAT_ID + seat (the picker
    # keeps the seat's entry at SEAT_IDX, asm/bombers.asm pal_lookup)
    if len(all_pals) > 0x100:
        raise BuildError(f"{len(all_pals)} bomber palettes; the table holds 256 "
                         f"(characters with the same palette picture share them when their colors fit together)")
    far = [c["char"] for c in chars if OWN_ID + c["pal0"] + min(c["colors"], VARIANTS) > SEAT_ID]
    if far:
        raise BuildError(f"bomber palettes: the stock colors of characters {far} (Battle) need ids past ${SEAT_ID - 1:02X}")
    if all_pals:
        start = rb.regions["bulk"].cursor
        data, pos = bytearray(), (start & 0xFFFF) + 2 * len(all_pals)
        blobs = [_pal_blob(colors) for colors in all_pals]
        for blob in blobs:
            data += bytes([pos & 0xFF, pos >> 8 & 0xFF])
            pos += len(blob)
        paltab = rb.alloc("bulk", bytes(data) + b"".join(blobs),
                          f"bomber: {len(palettes)} palettes (ids ${OWN_ID:02X}+) and {len(all_pals) - len(palettes)} "
                          f"of other characters")
        if paltab != start:
            raise BuildError("bomber palettes moved")

    def longs(values):
        return b"".join(bytes([v & 0xFF, v >> 8 & 0xFF, v >> 16]) for v in values)

    cmap = rb.alloc("bulk", longs(charmap), "bomber: mapping table of each character (0 = stock)")
    canim = rb.alloc("bulk", longs(charanim), "bomber: script table of each character (0 = stock)")
    xtab = rb.alloc("bulk", bytes(xlat), "bomber: replaced palette ids (entry + 1 of the palette table)")
    # streamed poses: [offset16 in $E4, mapping count] per character (count 0 = none)
    cstream = bytearray(30)
    for c, info in [(0, info0)] + [(ch["char"], ch) for ch in chars]:
        if info:
            cstream[3 * c:3 * c + 3] = _stream_table(rb, info["stream"], info["count"], "bomber" if c == 0 else f"char{c}")
    streaming = any(cstream[2::3])
    cstab = rb.alloc("bulk", bytes(cstream), "bomber: streamed pose table of each character")

    # hook
    reg = rb.regions["bulk"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"E4": f"${reg.cursor:06X}", "CHARMAP": f"${cmap:06X}",
                                                "CHARANIM": f"${canim:06X}", "PALTAB": f"${paltab:06X}",
                                                "XLAT": f"${xtab:06X}", "CHARSTREAM": f"${cstab:06X}",
                                                "PALS": str(PAL_IDS if palettes else 0),
                                                "OWNID": f"${OWN_ID:02X}",
                                                "SEATID": f"${SEAT_ID:02X}", "SEATIDX": f"${SEAT_IDX:06X}",
                                                "BGTAB": f"${menu_bg['table']:06X}" if menu_bg else "0",
                                                "CYCSET": str(menu_bg["cycle_set"] if menu_bg else 0),
                                                "CYCID": str(menu_bg["cycle_id"] if menu_bg else 0),
                                                "CYCN": str(menu_bg["cycle_n"] if menu_bg else 0),
                                                **{"ENMAP": "0", "W1PAL": "0", "EGGANIM": "0", "PORTALANIM": "0", **(enemies or {})}})
    start, end = reg.cursor, syms["end_e4"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"bombers.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "bomber: mapping selector (asm/bombers.asm)")
    if any(charmap):
        hook = syms["bomber_map"]
        rb.patch(0xC012A4, bytes.fromhex("B9 9F 04 3A"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: mapping table of seat bombers")
    if streaming:
        hook = syms["stream_nmi"]
        rb.patch(0xC0F41D, bytes.fromhex("22 AF 6A C5"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: streamed poses DMA'd in the NMI (before the animation strip queue)")
    if any(charanim):
        hook = syms["bomber_anim"]
        rb.patch(0xC0120E, bytes.fromhex("BF 1F 17 C0"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: animation scripts of seat bombers")
        hook = syms["bomber_loop"]
        rb.patch(0xC0126A, bytes.fromhex("C9 00 D0 06 99 FF 07"),
                 bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16, 0xD0, 0x04, 0xEA]),
                 "bomber: script restart offset")
    if all_pals:
        hook = syms["bomber_palcount"]
        rb.patch(0xC437C1, bytes.fromhex("A9 09 85 AB"), bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16]),
                 "bomber: 16-color palettes for ids 1-6, $80+ and the replaced ones")
        hook = syms["pal_lookup"]
        rb.patch(0xC001FA, bytes.fromhex("A9 81 85 AA C2 30"),
                 bytes([0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16, 0xEA, 0xEA]),
                 "bomber: palette ids $80+ of set 0, replaced ids")
    result = dict(chars=chars, strips=0, poses=0, max_pieces=0, inexact=inexact, notes=notes, scripts=0,
                  paltab=paltab if palettes else 0, palcount=len(palettes), stand=None, sheet=bool(info0),
                  pal_total=len(all_pals), own_id=OWN_ID, first=palettes[0] if palettes else None, stream_clear=syms["stream_clear"] if streaming else 0,
                  tables=dict(charmap=cmap, charanim=canim, charstream=cstab))
    if info0:
        pieces = [len(p) for p in info0["mappings"].values()]
        result.update(strips=info0["strips"], poses=len(pieces), max_pieces=max(pieces), scripts=len(br.scripts))
        if palettes:
            result["stand"] = cells[(STAND, dict(br.poses())[STAND][0])]
            result["pick_anims"] = _pick_anims(br, cells)
            result["palettes"] = palettes
    return result


# SB5's playable characters' OBJ sheets 1-20 ($C7:4000-$C9:7FFF: character n = sheets 2n+1 / 2n+2, raw
# 4bpp, with zero padding between some of them; also set 0 archives 1-$14). Once every character's
# [sheet, row] table ($80:BB66 + 2 * char) names only the SB6 sheets (ids from 97), nothing draws them:
# Battle, the attract demo and the boss rivals (same per-character tables) use the new sheets too. Louie
# sheets $15-$22 follow at $C9:8000 and stay. One region per bank.
STOCK_SHEETS = [
    ("free_c7_sheets", 0xC74000, 0xC000, 0x27457CEC),
    ("free_c8_sheets", 0xC80000, 0x10000, 0xDD694454),
    ("free_c9_sheets", 0xC90000, 0x8000, 0xC66F31B8),
]
STOCK_SHEET_IDS = range(1, 21)


def free_stock_sheets(rb, base_rom):
    """After apply(): fills SB5's character sheets with $FF and declares them as free regions."""
    for c in range(10):
        t = 0x800000 | rb.rw(0x80BB66 + 2 * c)
        used = sorted({rb.rb(t + 2 * a) for a in range(bomber.ANIMS)} & set(STOCK_SHEET_IDS))
        if used:
            raise BuildError(f"character {c} still uses SB5's sheets {used}: give it a char<n>_sb6.png")
    for name, start, size, crc in STOCK_SHEETS:
        o = off(start)
        if rb.d[o:o + size] != base_rom[o:o + size]:
            raise BuildError(f"{name}: SB5's sheets were edited (assets/bomberman/sheet.png?), but they are no "
                             "longer drawn: edit assets/bombers instead")
        rb.free_old(name, start, size, crc, f"freed SB5 character OBJ sheets (${start >> 16:02X})")
