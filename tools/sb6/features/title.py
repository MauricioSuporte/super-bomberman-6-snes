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
with its own archives, palette and arrangements, and redirects the title
scripts to sub-scripts in free space. BG1/BG2 (sky, characters, logo) are not
arrangements any more: features/title_anim.py + asm/title_anim.asm send them
frame by frame (intro and idle animation of the Unity title).
"""
import os

from .. import lz
from ..romlib import off
from .. import asar
from ..rombuild import BuildError
from . import title_anim
from . import options
from .title_text import text_tiles

ASM = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asm", "title_anim.asm")
ANIM_REGIONS = ["title_fa", "title_fb", "free_c8_sheets"]  # tiles, maps, tables and code of the animated title

SET = 5                   # new graphics set used by the SB6 title
VRAM_TILE_LIMIT = 0x3000  # words: BG1/BG2 maps start at VRAM $3000
TEXT_ENTRIES = (1, 2, 3)  # CGRAM 1-3: BG3 text colors (palette 8 of set 3)

# BG3 text (SB5's menu art) moves up so the menu sits between the logo (ends
# at y~70) and the characters (start at y~130), as in the SB6 title. Scrolling
# BG3 does not work: the FF 8D/FF 91 drawers add the layer scroll back.
TEXT_SHIFT_ROWS = 7       # PUSH START BUTTON rows 16-17 -> 9-10 (y 72-87)
TEXT_SHIFT = TEXT_SHIFT_ROWS * 8
VERSION_ROW = 26          # rows 26-27 (y 208-223), where (c) 1997 HUDSON SOFT was (25-26)
VERSION_TILE = 0x140      # first free BG3 tile after SB5's text ($102-$13A)
BG3_CHR = 0x5000          # BG3 character base (VRAM word)
VERSION_ATTR = 0x2000     # priority, palette 0 (like the old copyright line)
MENU_ATTR = 0x2100        # tile words of SB5's menu text (tiles $1xx)
PLAYERS_ARR = 4           # set 5 arrangement: 1-4 PLAYER GAME (see coop.py)

# SB5's title arrangements that apply() stops drawing: set 4 #2 (scene, BG2) and #3 (logo, BG1), one
# block, and #6 (the (c) HUDSON line, BG3). Arrangements name their set in the op (FF 8D-90 id set), and
# the only ones naming these are the title lines patched or skipped below ($C6:FCA1/$C6:FCA8 inside the
# intro path's skip, $C7:17E6/$C7:17ED inside handler 6's skip, $C6:FE50/$C7:1802 now the version); no
# native caller of the drawer ($C0:0000/0009/001B) passes them. #4, #5, #7 (PUSH START, menus) stay.
OLD_DATA = [
    ("free_e2_title", 0xE20264, 1104, 0x65BD5A4D, "freed SB5 title scene and logo arrangements (set 4 #2, #3)"),
    ("free_e2_copy", 0xE207A2, 82, 0xEF9D0BB9, "freed SB5 title (c) HUDSON arrangement (set 4 #6)"),
    # SB5's two title characters (set 3 OBJ archives $61, $62, LZ, one block): loaded only by `28 61 28 62`
    # at $C6:FC9D (intro path, skipped) and $C7:17DE (handler 4, patched); every other "28 61" / "28 62"
    # in the ROM is an operand or data. The first byte stays: the decompressor reads one byte past
    # archive $60 (the menu cursor, still loaded), which ends right there. It stops where archive $63
    # (the exit portal's beam, loaded when a stage is cleared) starts.
    ("free_d6", 0xD6A3ED, 9914, 0xD86C3097, "freed SB5 title characters (set 3 archives $61, $62)"),
]


def free_old(rb):
    """Fills SB5's unused title arrangements with $FF and declares them as free regions."""
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)

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


def players_menu(rb, dig_top, dig_bottom):
    """SB5's "1 PLAYER GAME / 2 PLAYER GAME" (set 4 arrangement 7, 14x4) plus
    "3 PLAYER GAME" and "4 PLAYER GAME": the "2" rows with the digit cell
    (column 0) replaced."""
    tab = 0xC00000 | rb.rl(0xC08000 + 3 * 4)
    hdr = off((tab & 0xFF0000) | rb.rw(tab + 2 * (7 - 1)))
    w, h = rb.d[hdr], rb.d[hdr + 1]
    lo, n = lz.decompress(bytes(rb.d[hdr + 5:hdr + 5 + 512]), w * h)
    hi, _ = lz.decompress(bytes(rb.d[hdr + 5 + n:hdr + 5 + n + 512]), w * h)
    rows = [[hi[r * w + c] << 8 | lo[r * w + c] for c in range(w)] for r in range(h)]
    for k in range(2):
        top, bottom = list(rows[2]), list(rows[3])
        top[0], bottom[0] = dig_top[k], dig_bottom[k]
        rows += [top, bottom]
    return arrangement(w, len(rows), 0x0B, 0x12 - TEXT_SHIFT_ROWS, [x for r in rows for x in r])


# Menu cursor of the fan game (assets/title/Cursor.png, 16x16 cells): row 0 =
# 9 heads (rest, left 1-2, right 1-2, down 1-2, up 1-2), rows 1-2 = 7 + 7 face
# plates with different eyes. The game draws a head with a face over it, the
# face moved with the head (TitleScreenCursorEyeIdle.GetEyeOffsetPixels, y up).
CURSOR_HEADS, CURSOR_EYES = 9, 7
CURSOR_EYE_SHIFT = {0: (0, 0), 1: (-1, 0), 2: (-2, 0), 3: (1, 0), 4: (2, 0),
                    5: (0, 1), 6: (0, 2), 7: (0, -1), 8: (0, -2)}   # (x, y down) per head
# Unity sequences (11 heads in 0.5 s): the look around after 3 s without
# input (left-right / down-up, each also reversed, random first-row face) and
# the confirmation (face 2, which stays until the next input).
CURSOR_SEQS = [[0, 1, 2, 2, 1, 0, 3, 4, 4, 3, 0], [0, 3, 4, 4, 3, 0, 1, 2, 2, 1, 0],
               [0, 7, 8, 8, 7, 0, 5, 6, 6, 5, 0], [0, 5, 6, 6, 5, 0, 7, 8, 8, 7, 0],
               [0, 7, 8, 8, 7, 0, 6, 5, 5, 6, 0]]
CURSOR_ANIM_FRAMES, CURSOR_IDLE_FRAMES, CURSOR_CONFIRM_EYE = 30, 180, 2
# SB5's wait after an accepted title item ($C7:1AFD, 64): the press reaches the next menu 10 frames
# after the wait, so 20 = CURSOR_ANIM_FRAMES from the press (measured in Mesen).
ACCEPT_WAIT = CURSOR_ANIM_FRAMES - 10


def cursor_tables(asset_dir):
    """(poses, colors, steps, sequences): pose `face * 9 + head` = 4 OBJ tiles
    (top left, top right, bottom left, bottom right; 128 bytes) of the head
    with the face over it; colors 1-15 of the cursor's OBJ palette; the
    sequence step shown in each frame of an animation; the sequences."""
    from PIL import Image
    import numpy as np
    from ..snesgfx import bgr555, encode_4bpp
    sheet = Image.open(os.path.join(asset_dir, "Cursor.png")).convert("RGBA")
    colors = sorted({p[:3] for p in sheet.getdata() if p[3] >= 128})
    if len(colors) > 15:
        raise BuildError("Cursor.png: more than 15 colors")
    index = {c: k + 1 for k, c in enumerate(colors)}
    poses = bytearray()
    for eye in range(CURSOR_EYES):                       # the first row of faces
        face = sheet.crop((16 * eye, 16, 16 * eye + 16, 32))
        for head in range(CURSOR_HEADS):
            img = sheet.crop((16 * head, 0, 16 * head + 16, 16))
            dx, dy = CURSOR_EYE_SHIFT[head]
            img.alpha_composite(face.crop((max(0, -dx), max(0, -dy), 16 - max(0, dx), 16 - max(0, dy))),
                                (max(0, dx), max(0, dy)))
            px = np.array([[index[tuple(p[:3])] if p[3] >= 128 else 0 for p in row]
                           for row in np.array(img).tolist()], dtype=np.uint8)
            for ty in (0, 8):
                for tx in (0, 8):
                    poses += encode_4bpp(px[ty:ty + 8, tx:tx + 8])
    pal = b"".join(bgr555([(v * 31 + 127) // 255 for v in c]).to_bytes(2, "little")
                   for c in colors).ljust(30, b"\x00")
    n = len(CURSOR_SEQS[0])
    steps = bytes(max(i for i in range(n) if i * CURSOR_ANIM_FRAMES // n <= t) for t in range(CURSOR_ANIM_FRAMES))
    return bytes(poses), pal, steps, bytes(sum(CURSOR_SEQS, []))


def drop_frames(asset_dir):
    """Intro frames (from the pan's first) where each wave of characters starts to fall."""
    L = title_anim.load_layout(asset_dir)
    A = L["animation"]
    pan = round(A["pan_seconds"] * title_anim.FPS)
    drop = round(A["characters_drop_seconds"] * title_anim.FPS)
    waves = len(L["characters"]) // 2 + 1
    return [pan + k * (drop + title_anim.SWAP_FRAMES) for k in range(waves)]


def apply(rb, asset_dir, out_dir, starts, version_text, boot=None, cache_dir=None, pan_sound=0):
    """boot = boot_logo.convert() result: set 5 archive 3, palette 2, arrangement 5.

    pan_sound = title_music's `pre_start` (0 = silent intro).
    Returns the build's numbers and `syms` (title_op, title_nmi: asm/picker.asm
    calls them from its script op and NMI hooks)."""
    # Original BG3 text colors (palette 8 of set 3) keep CGRAM 0-3.
    pal_tab3 = 0x810000 | rb.rw(0xC00379 + 2 * 3)
    text_pal = 0x810000 | rb.rw(pal_tab3 + 2 * (8 - 1))
    reserved = {k: rb.rw(text_pal + 4 + 2 * k) for k in range(4)}

    # ---- animated scene (BG1/BG2): tiles, maps and tables of asm/title_anim.asm
    def put(data, label):
        return rb.alloc(ANIM_REGIONS, data, label)

    anim = title_anim.build(asset_dir, starts, reserved, put, cache_dir)
    os.makedirs(out_dir, exist_ok=True)
    title_anim.simulate(anim, os.path.join(out_dir, "title_preview.png"))
    colors = anim["cgram"]
    tab = {k: rb.alloc(ANIM_REGIONS, v, f"title: table {k}") for k, v in anim["tables"].items()}
    ptrs = b"".join(rb.le16((tab["logocg"] + k * anim["consts"]["CGLEN"]) & 0xFFFF)
                    for k in range(anim["consts"]["NLOGO"]))
    tab["logoptr"] = rb.alloc(ANIM_REGIONS, ptrs, "title: table logoptr")
    poses, cur_pal, cur_steps, cur_seqs = cursor_tables(asset_dir)
    tab["curposes"] = rb.alloc(ANIM_REGIONS, poses, "title cursor: 63 poses (7 faces x 9 heads), 4 OBJ tiles each")
    tab["curpal"] = rb.alloc(ANIM_REGIONS, cur_pal, "title cursor: OBJ palette 0, colors 1-15")
    tab["cursteps"] = rb.alloc(ANIM_REGIONS, cur_steps, "title cursor: sequence step per animation frame")
    tab["curseqs"] = rb.alloc(ANIM_REGIONS, cur_seqs, "title cursor: head sequences (4 looks around, confirmation)")
    if (tab["curposes"] & 0xFFFF) + len(poses) > 0x10000:
        raise BuildError("title cursor poses cross a bank")
    region = next(r for r in (rb.regions[n] for n in ANIM_REGIONS) if r.free() >= 0x800)
    defines = {"ORG": f"${region.cursor:06X}", "SET": str(SET), "CURY": f"${0xA0 - TEXT_SHIFT:02X}",
               "JOBS": f"${tab['jobs']:06X}", "INITA": f"${tab['init_a']:06X}", "INITB": f"${tab['init_b']:06X}",
               "PLAY": f"${tab['play']:06X}", "DROP": f"${tab['drop']:06X}", "LOGOCG": f"${tab['logocg']:06X}",
               "LOGOPTR": f"${tab['logoptr']:06X}", "ALT": f"${tab['alt']:06X}", "PANSND": f"${pan_sound:06X}",
               "CURPOSES": f"${tab['curposes']:06X}", "CURPAL": f"${tab['curpal']:06X}",
               "CURSTEPS": f"${tab['cursteps']:06X}", "CURSEQS": f"${tab['curseqs']:06X}",
               "CURHEADS": str(CURSOR_HEADS), "CURSEQLEN": str(len(CURSOR_SEQS[0])),
               "CURANIM": str(CURSOR_ANIM_FRAMES), "CURIDLE": str(CURSOR_IDLE_FRAMES),
               "CUREYE": str(CURSOR_CONFIRM_EYE), "CURCONFIRM": str(len(CURSOR_SEQS))}
    defines.update({k: str(v) for k, v in anim["consts"].items()})
    if title_anim.SCRATCH != 2 or title_anim.ALTREC != 8 or anim["consts"]["NCHAR"] > 8:
        raise BuildError("title: asm/title_anim.asm expects 2 scratch areas, 8-byte !ALT records and at most 8 characters")
    runs, syms = asar.assemble_into(rb.d, ASM, defines)
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"title_anim.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc(region.name, bytes(out[off(start):off(end)]), "title: intro and idle animation (asm/title_anim.asm)")

    # Version string glyphs (BG3, 2bpp) replacing SB5's copyright line.
    text = version_text if len(version_text) % 2 == 0 else version_text + " "
    ver_tiles, ver_top, ver_bottom = text_tiles(text, VERSION_TILE, VERSION_ATTR)
    # Digits 3 and 4 of the player-count menu (1-4 PLAYER GAME), after them.
    dig_tiles, dig_top, dig_bottom = text_tiles("34", VERSION_TILE + len(ver_tiles) // 16,
                                                MENU_ATTR, art=True)
    ver_tiles += dig_tiles
    # OPTIONS submenu: DISCORD and the QR code's 16 tiles (features/options.py), after them.
    opt_tiles, discord, qr = options.glyphs(os.path.join(asset_dir, "..", "options"),
                                            VERSION_TILE + len(ver_tiles) // 16)
    ver_tiles += opt_tiles
    if VERSION_TILE + len(ver_tiles) // 16 > 0x180:
        raise BuildError("title: BG3 glyphs pass tile $17F (VRAM $5C00)")
    ver_addr = rb.alloc("bulk", ver_tiles, f"title: BG3 glyphs for '{version_text}' and 3/4 (2bpp)")

    # Archive table for set 5 (bank $E3): [vram, size, src24, flags]; flag $80 = raw,
    # type 2 = 4bpp BG tiles, type 3 = 2bpp BG tiles (as SB5's BG3 text, archive $96 of set 3).
    # Entry 1 was the static title's tiles: the scene's tiles are sent by title_anim's jobs now.
    glyphs = rb.le16(BG3_CHR + VERSION_TILE * 8) + rb.le16(len(ver_tiles)) + rb.le24(ver_addr) + bytes([0x83])
    arc_entry = glyphs + glyphs
    if boot:
        boot_addr = rb.alloc("bulk", boot["tiles"], "boot logo: BG1 4bpp tiles (raw)")
        arc_entry += rb.le16(0x0000) + rb.le16(len(boot["tiles"])) + rb.le24(boot_addr) + bytes([0x82])
    arc_table = rb.alloc("e3_tables", arc_entry,
                         "set 5 archive table (1, 2 = version glyphs, 3 = boot logo)")

    # Palette table for set 5 (bank $81): word pointer -> [dest, count, colors].
    pal_entries = [rb.le16(0) + rb.le16(128) + b"".join(rb.le16(c) for c in colors)]
    if boot:
        pal_entries.append(rb.le16(0) + rb.le16(128) + b"".join(rb.le16(c) for c in boot["colors"]))
    pblob = bytearray(2 * len(pal_entries)) + b"".join(pal_entries)
    pal_table = rb.alloc("bank81", bytes(pblob), "set 5 palette table + palettes 1 (title), 2 (boot logo)")
    pos = pal_table + 2 * len(pal_entries)
    for i, e in enumerate(pal_entries):
        pblob[2 * i:2 * i + 2] = rb.le16(pos & 0xFFFF)
        pos += len(e)
    rb.d[pal_table & 0x3FFFFF:(pal_table & 0x3FFFFF) + len(pblob)] = pblob

    # Arrangement table for set 5 (any bank; entries are in the table's bank).
    # 1 and 2 were the static logo and scene (kept as copies of 3: scripts use
    # the numbers of 3-5).
    arr3 = arrangement(len(text), 2, (32 - len(text)) // 2, VERSION_ROW, ver_top + ver_bottom)
    arrs = [arr3, arr3, arr3, players_menu(rb, dig_top, dig_bottom),
            arrangement(32, 28, 0, 0, boot["words"]) if boot else arr3]
    arrs += options.arrangements(arrangement, discord, qr)       # 6 DISCORD, 7 QR code
    blob = bytearray(2 * len(arrs)) + b"".join(arrs)
    arr_table = rb.alloc("bulk", bytes(blob),
                         "set 5 arrangement table: 3 (version, BG3), 4 (1-4 PLAYER GAME, BG3), 5 (boot logo), "
                         "6 (DISCORD), 7 (QR code)")
    pos = arr_table + 2 * len(arrs)
    for i, a in enumerate(arrs):
        blob[2 * i:2 * i + 2] = rb.le16(pos & 0xFFFF)
        pos += len(a)
    o = arr_table & 0x3FFFFF
    rb.d[o:o + len(blob)] = blob

    s_load, s_wait = syms["s_load"], syms["s_wait"]
    s_null = rb.alloc("bulk", b"\x00", "script: empty (returns)")

    # ---- hook the set tables (set 5 is null in all of them) ----------------
    rb.patch(0xC01C96 + 2 * SET, b"\x00\x00", rb.le16(arc_table & 0xFFFF), "archive set 5 -> $E3 table")
    rb.patch(0xC00379 + 2 * SET, b"\x00\x00", rb.le16(pal_table & 0xFFFF), "palette set 5 -> $81 table")
    rb.patch(0xC08000 + 3 * SET, b"\x00\x00\x00", rb.le24(arr_table), "arrangement set 5 -> table")

    # ---- boot logo (mode 1, script $C7:0AC4; see boot_logo.py) -------------
    if boot:
        rb.patch(0xC70ACE, bytes.fromhex("26 03 27 46 2A 2B"), bytes([0x26, SET, 0x27, 0x03, 0x2A, 0x02]),
                 "boot logo: set 5 archive 3 + palette 2")
        rb.patch(0xC70AD9, bytes.fromhex("FF 8D D3 04 01 00 00"), bytes([0xFF, 0x8D, 0x05, SET, 0x01, 0x00, 0x00]),
                 "boot logo: set 5 arrangement 5 on BG1")

    # The boot logo script ends with 0F A9 (intro); go to mode 2 (title
    # without intro, where Start during the intro leads) until SB6 has its own.
    rb.patch(0xC70AF5, bytes.fromhex("0F A9"), bytes.fromhex("0F 02"), "boot: skip the intro, straight to the title")

    # ---- intro path (mode $A9) --------------------------------------------
    rb.patch(0xC6FC93,
             bytes.fromhex("26 03 27 07 27 96 2A 09 2A 08 28 61 28 62 FF 8D 03 04 01 00 00 FF 8D 02 04 02 00 00"),
             call(s_load) + skip(22), "intro title: load SB6 title (drawn by title_anim)")
    rb.patch(0xC6FCBB, bytes.fromhex("2C 12 02 2C 13 02 2C 14 02"), skip(7),
             "intro title: no SB5 logo palette cycling")
    rb.patch(0xC6FD7C, bytes.fromhex("24 AC FE C6"), call(s_null), "intro title: no SB5 character (left)")
    rb.patch(0xC6FDC9, bytes.fromhex("24 BC FE C6"), call(s_null), "intro title: no SB5 character (right)")

    # ---- title without intro (mode 2, handler list $C7:1783) ---------------
    rb.patch(0xC717D1, bytes.fromhex("26 03 27 07 27 96 2A 09 2A 08 26 03 00"), call(s_load) + b"\x00",
             "mode 2 handler 2: load SB6 title")
    rb.patch(0xC717DE, bytes.fromhex("28 61 28 62 00"), b"\x00", "mode 2 handler 4: no SB5 character sprites")
    rb.patch(0xC717E6, bytes.fromhex("FF 8D 03 04 01 00 00 FF 8D 02 04 02 00 00"),
             skip(12), "mode 2 handler 6: SB6 title drawn by title_anim")
    # The task that starts the music and the PUSH START loop first waits for the intro.
    rb.patch(0xC71847, bytes.fromhex("06 04 42 02 00 5B A0 60 34 10 5B 00 5F 36 10 24 D3 1A C7"),
             call(s_wait) + skip(13), "mode 2: cursor, PUSH START and music after the intro")
    rb.patch(0xC71821, bytes.fromhex("3A 44 D0 00 C0 00 40 01 40 02 3A 43 20 00 C0 00"), skip(14),
             "mode 2: no SB5 characters")
    rb.patch(0xC71832, bytes.fromhex("2C 12 02 2C 13 02 2C 14 02"), skip(7),
             "mode 2: no SB5 logo palette cycling")

    # ---- menu text between logo and characters, version instead of (c) ----
    # Set 4 arrangements 4 (PUSH START BUTTON), 5 (title menu) and 7 (other
    # title menu) carry their BG3 row in header byte 3; FF 91 x y w h layer
    # clears the menu block before a redraw; FF 0C ... is the window (HDMA on
    # WH2/WH3) that blinks PUSH START BUTTON (x $30-$D0, y $80-$90); the
    # cursor object's Y is item * 16 + $A0 (script $C7:1AB5, op 61 = add).
    arr_tab4 = 0xC00000 | rb.rl(0xC08000 + 3 * 4)
    for n, row in ((4, 0x10), (5, 0x12), (7, 0x12)):
        hdr = (arr_tab4 & 0xFF0000) | rb.rw(arr_tab4 + 2 * (n - 1))
        rb.patch(hdr + 3, bytes([row]), bytes([row - TEXT_SHIFT_ROWS]), f"title text: set 4 arrangement {n} row")
    for a in (0xC718B6, 0xC719B7):
        rb.patch(a, bytes.fromhex("FF 91 09 12 10 06 03"),
                 bytes([0xFF, 0x91, 0x09, 0x12 - TEXT_SHIFT_ROWS, 0x10, 0x06, 0x03]), "title menu: clear block row")
    window = bytes([0xFF, 0x0C, 0x30, 0x80 - TEXT_SHIFT, 0xD0, 0x90 - TEXT_SHIFT, 0x02])
    version = bytes([0xFF, 0x8D, 0x03, SET, 0x03, 0x00, 0x00])
    for where, win, cpy in (("intro", 0xC6FE63, 0xC6FE50), ("mode 2", 0xC7181A, 0xC71802)):
        rb.patch(win, bytes.fromhex("FF 0C 30 80 D0 90 02"), window, f"{where} title: PUSH START blink window moved")
        rb.patch(cpy, bytes.fromhex("FF 8D 06 04 03 00 00"), version, f"{where} title: version instead of (c) line")
    rb.patch(0xC71ABF, bytes.fromhex("61 A0"), bytes([0x61, 0xA0 - TEXT_SHIFT]), "title menu cursor Y moved")
    # An accepted item (A/Start, $C7:189C: SFX 4, then $C7:1AEA sleeps 64 frames with the cursor
    # hopping, then FD 0E 04) took 74 frames to the next menu / the fade; it takes the cursor's
    # confirmation (CURSOR_ANIM_FRAMES, 0.5 s) now. s_accept also starts that confirmation, so a
    # press the game does not take (while it waits, fades or shows the QR) does not.
    rb.patch(0xC7189C, bytes.fromhex("42 04 02 24 EA 1A C7"), call(syms["s_accept"]) + skip(1) + b"\xFF",
             "title menu: accept through s_accept (cursor confirmation)")
    rb.patch(0xC71AFD, bytes.fromhex("5B 40"), bytes([0x5B, ACCEPT_WAIT]), "title menu: shorter wait after accept")
    # initial cursor Y ($1034) when the title appears (intro path; mode 2: s_wait)
    rb.patch(0xC6FE6F, bytes.fromhex("5B A0 60 34 10"), bytes([0x5B, 0xA0 - TEXT_SHIFT, 0x60, 0x34, 0x10]),
             "title menu cursor initial Y moved")

    return dict(stats=anim["stats"], error=anim["error"], logo_error=anim["logo_error"], start=anim["start"],
                syms=syms)
