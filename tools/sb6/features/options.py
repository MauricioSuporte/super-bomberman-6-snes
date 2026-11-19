"""Title OPTIONS: an SB6 submenu on the title instead of SB5's Options screen.

SB5's title menu (menu `$1036` = 0: NORMAL GAME / BATTLE GAME / OPTIONS) sent
OPTIONS to mode `$0B` (Options screen: Password, Sound, Sound Test). The hack
keeps the title up instead: OPTIONS is accepted like the other items (SFX 4,
the cursor's confirmation, SB5's 64-frame wait in `$C7:1AEA`), then the menu
block shows the submenu (menu 3, one item: DISCORD). DISCORD shows a QR code
(invite to the Super Bomberman 6 Discord server, `assets/options/discord_qr.png`)
over the title on BG3; any button closes it and the submenu is back. B in the
submenu goes back to the main menu with the cursor on OPTIONS.

Script VM (docs/ROM_MAP.md): the title's task runs `$C7:1872` every frame; an
accepted item reaches the menu checks at `$C7:18A3` after SB5's wait. The
OPTIONS check (`$C7:18D5`) becomes a call to `s_confirm`, which handles menu
0 item 2 (open the submenu) and menu 3 (QR), then the stock checks go on (no
other menu matches 3). B: the menu-2 test at `$C7:19AD` becomes a call to
`s_back` (menu 2 as before, menu 3 back to the main menu).
While the QR is up the menu is 4: SB5's cursor hop stops and the SB6 cursor
(`asm/title_anim.asm` `cursor`) leaves its confirmation face; the closing
press is seen under menu 4 (one frame before menu 3), so it does not start a
new confirmation.

SB5's Options screen (mode `$0B`, with its Sound / Sound Test pages) and the
Password screen (mode 7, only reached from Options) are gone: their scripts,
graphics and music are freed (`OLD_DATA`) and both modes now lead to the
title's record, so a stray mode switch shows the title.
"""
import os

from PIL import Image

from ..rombuild import BuildError
from .title_text import text_tiles

SUBMENU, QRMENU = 3, 4            # $1036 values (SB5 uses 0-2)
ARR_DISCORD, ARR_QR = 6, 7        # set 5 arrangements (features/title.py builds the table)
QR_SCALE = 4                      # pixels per module: one BG3 tile = 2 x 2 modules
QR_TILES = (20, 20)               # arrangement size in tiles (even width, quiet zone >= 4 modules)
QR_POS = (6, 4)                   # tile column / row on BG3 (x 48-207, y 32-191)
QR_LIGHT, QR_DARK = 2, 1          # BG3 palette 0: CGRAM 2 near white, 1 near black (SB5's text colors)
ATTR = 0x2000                     # priority, palette 0

# SB5's menu letters (set 4 arrangement 5, tiles $1xx of BG3 archive $96): top / bottom word.
SB5_LETTERS = {"I": (0x2128, 0x2127), "S": (0x2129, 0x212B), "O": (0x2116, 0x211E), "R": (0x2117, 0x211F)}

# SB5's menu block (title.py moves it up 7 rows, coop.py makes it 8 rows high): FF 91 x y w h layer.
MENU_CLEAR = bytes.fromhex("FF 91 09 0B 10 08 03")
MENU_X, MENU_Y = 0x0B, 0x0B       # first menu row (set 4 arrangement 5 row $12 - 7)

# Freed (owner's call, 2026-11-18): everything only the Options (mode $0B) and Password (mode 7)
# screens read. Proofs (docs/FREE_SPACE.md):
#  * scripts $C7:00DE-$C7:0AB1: the mode $0B record ($C7:00DE), its handlers, the Options / Sound /
#    Sound Test scripts and tables, the mode 7 record ($C7:08BD) and the Password scripts, up to the boot
#    logo's record ($C7:0AB2). Only the mode table names them ($C6:0012 = mode 7, $C6:001E = mode $0B,
#    entry n - 1 at $C6:0000 + 3 * (n - 1)): no other script pointer (C6/C7) and no native LDA #$C7 pair
#    points inside; the scripts left in bank C7 do not skip into it. Both entries now point at mode 2's.
#  * set 3 archive $92 (Options tiles, raw, `29 92` at $C7:012A; also set 0 $F1, set 6 $95, set 8 $CD)
#    and archive $25 (Options / Password background, LZ, `29 25` at $C7:0108 and $C7:0905; set 0 $84,
#    set 6 $28, set 8 $60: every other `27/28/29` hit with those ids decodes as data or another set; no
#    native load). $25's first byte stays (the decompressor of archive $24 reads one byte past it).
#  * set 6 arrangements $C3 (frame), $DA (menu), $DB/$DC (Stereo / Mono), $DD (Sound Test page) and
#    set 4 $C6/$C7 (Password), drawn only by `FF 8D` inside the freed scripts; no native caller
#    passes those set 4 / set 6 ids.
#  * Password music, music id $1B: its sequence (sound set $41 = $26 + id, upload list) and song $1A's
#    upload list (directory / tuning, `$DA:CEFE`, no other song record names it); requested only by
#    `42 1B 00` at $C7:093C. The song record and its samples (shared with songs 1, 9, $0C, $0E, $14,
#    $19) stay.
# Kept: set 3 archives $1D, $22, $26, $66 and palettes $1B, $1C, $41 (Battle, the Normal Game menu and
# other scenes load the same ids), set 13 palettes $BB-$C3 (the Password fade; that fade's ids are
# computed, as the $C4-$D5 ones of other screens), menu SFX (shared).
OLD_DATA = [
    ("free_c7_options", 0xC700DE, 2516, 0x9490F331,
     "freed SB5 Options / Sound Test / Password scripts (modes $0B and 7)"),
    ("free_e3_options", 0xE30000, 0x1280, 0x8015F6A4, "freed SB5 Options screen tiles (set 3 archive $92)"),
    ("free_d4_options", 0xD49DFE, 4523, 0x3804E1F1, "freed SB5 Options / Password background (set 3 archive $25)"),
    ("free_e1_options", 0xE19DD9, 633, 0xFFDCD856, "freed SB5 Options frame arrangement (set 6 $C3)"),
    ("free_e1_options2", 0xE1C03F, 3160, 0x481AB2B0,
     "freed SB5 Options / Sound Test arrangements (set 6 $DA-$DD)"),
    ("free_e2_password", 0xE2C3FB, 936, 0x182873DC, "freed SB5 Password arrangements (set 4 $C6/$C7)"),
    ("free_d9_password", 0xD9D641, 341, 0xBA1C584C, "freed SB5 Password music sequence (sound set $41)"),
    ("free_da_password", 0xDACEFE, 44, 0xBCBFF762, "freed SB5 Password song upload list (song $1A)"),
]
MODE_TABLE, TITLE_RECORD = 0xC60000, 0xC7177A


def free_old(rb):
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)
    for mode, rec in ((7, 0xC708BD), (0x0B, 0xC700DE)):
        rb.patch(MODE_TABLE + 3 * (mode - 1), rb.le24(rec), rb.le24(TITLE_RECORD),
                 f"mode ${mode:02X} (freed screen) -> the title's record")


def _qr_modules(asset_dir):
    img = Image.open(os.path.join(asset_dir, "discord_qr.png")).convert("L")
    w, h = img.size
    if w != h:
        raise BuildError("discord_qr.png: not square")
    px = img.load()
    return [[px[x, y] < 128 for x in range(w)] for y in range(h)]


def glyphs(asset_dir, first_tile):
    """-> (2bpp tiles from `first_tile`, DISCORD arrangement words (8x2), QR arrangement words).

    D and C are drawn (title_text.ART, SB5's letter style); I, S, O, R are SB5's own tiles. The QR
    uses one tile per 2 x 2 modules (16 tiles)."""
    art, top, bottom = text_tiles("DC", first_tile, ATTR, art=True)
    d, c = (0x2117, bottom[0]), (0x211B, bottom[1])     # tops: SB5's B/R/P and G tiles
    letters = dict(SB5_LETTERS, D=d, C=c)
    blank = 0x2105                                       # SB5's blank cell in the menu text
    word = "DISCORD"
    rows = [[letters[ch][k] for ch in word] + [blank] for k in (0, 1)]
    discord = rows[0] + rows[1]

    qr_first = first_tile + len(art) // 16
    tiles = bytearray(art)
    for combo in range(16):                              # bit 0 top left, 1 top right, 2 bottom left, 3 bottom right
        rows8 = []
        for y in range(8):
            r = []
            for x in range(8):
                bit = (x >= 4) | (y >= 4) << 1
                r.append(QR_DARK if combo >> bit & 1 else QR_LIGHT)
            rows8.append(r)
        for row in rows8:
            p0 = sum((v & 1) << (7 - x) for x, v in enumerate(row))
            p1 = sum((v >> 1 & 1) << (7 - x) for x, v in enumerate(row))
            tiles += bytes([p0, p1])
    mods = _qr_modules(asset_dir)
    n = len(mods)
    tw, th = QR_TILES
    ox, oy = (2 * tw - n) // 2, (2 * th - n) // 2
    if min(ox, oy, 2 * tw - n - ox, 2 * th - n - oy) < 4:
        raise BuildError(f"QR code of {n} modules does not fit {tw}x{th} tiles with a 4-module quiet zone")

    def dark(mx, my):
        mx, my = mx - ox, my - oy
        return 0 <= mx < n and 0 <= my < n and mods[my][mx]

    qr = []
    for ty in range(th):
        for tx in range(tw):
            combo = sum(1 << b for b, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1)))
                        if dark(2 * tx + dx, 2 * ty + dy))
            qr.append(ATTR | (qr_first + combo))
    return bytes(tiles), discord, qr


def arrangements(arrangement, discord, qr):
    """Set 5 arrangements ARR_DISCORD and ARR_QR (title.arrangement builds the data)."""
    return [arrangement(8, 2, MENU_X, MENU_Y, discord),
            arrangement(QR_TILES[0], QR_TILES[1], QR_POS[0], QR_POS[1], qr)]


def _skip_if_not(addr, value, body):
    """`5D addr 86 value 49 n` + body: body runs when [addr] == value."""
    if len(body) > 255:
        raise BuildError("options script block too long")
    return bytes([0x5D, addr & 0xFF, addr >> 8, 0x86, value, 0x49, len(body)]) + body


def _set(addr, value):
    return bytes([0x5B, value, 0x5F, addr & 0xFF, addr >> 8])


def apply(rb, title_set):
    """Patches the title menu script (after title.py and coop.py)."""
    cursor_y = bytes.fromhex("24 B5 1A C7")          # $C7:1AB5: cursor Y = item * 16 + base
    draw = lambda arr, s=title_set: bytes([0xFF, 0x8D, arr, s, 0x03, 0x00, 0x00])
    wait1 = bytes.fromhex("FD 0E 01 00 00")           # sleep one frame (as SB5's $C7:1B36)
    if bytes(rb.d[0x0718B6:0x0718BD]) != MENU_CLEAR:
        raise BuildError("options: the title's menu clear block is not the expected one")

    open_sub = (MENU_CLEAR + draw(ARR_DISCORD) + _set(0x1036, SUBMENU) + _set(0x1032, 0)
                + _set(0x1037, 0) + cursor_y)
    qx, qy = QR_POS
    # W34SEL shadow $0307: $08 (BG3 window 2, the PUSH START blink, set at $C1:46D6) would cut a band out of the QR
    show = _set(0x1036, QRMENU) + _set(0x0307, 0x00) + draw(ARR_QR)
    loop = wait1 + bytes.fromhex("30 FF 31 FF")       # any pad, any new button
    back = -(len(loop) + 3)
    loop += bytes([0x48, back & 0xFF, back >> 8 & 0xFF])   # none: wait again
    close = (bytes([0xFF, 0x91, qx, qy, QR_TILES[0], QR_TILES[1], 0x03])
             + bytes.fromhex("FF 8D 04 04 03 00 00")      # PUSH START BUTTON (under the QR)
             + draw(ARR_DISCORD) + _set(0x0307, 0x08) + wait1 + _set(0x1036, SUBMENU) + _set(0x1032, 0) + cursor_y)
    confirm = (_skip_if_not(0x1036, 0, _skip_if_not(0x1032, 2, open_sub + b"\x00"))
               + _skip_if_not(0x1036, SUBMENU, show + loop + close) + b"\x00")
    s_confirm = rb.alloc("bulk", confirm, "script: title OPTIONS submenu / DISCORD QR (features/options.py)")

    # $C7:18D5: 5D 36 10 86 00 49 11 5D 32 10 86 02 49 0A 06 06 0F 0B 44 B9 01 (OPTIONS -> mode $0B)
    old = bytes.fromhex("5D 36 10 86 00 49 11 5D 32 10 86 02 49 0A 06 06 0F 0B 44 B9 01")
    # then on to $C7:18ED (the other menus' checks), as the stock 49 skips did ($C7:18EA jumps to the loop)
    new = bytes([0x24]) + rb.le24(s_confirm) + bytes([0x45, 0x18ED - (0x18D5 + 6)])
    rb.patch(0xC718D5, old, new + b"\xFF" * (len(old) - len(new)), "title: OPTIONS opens the SB6 submenu")

    # B: $C7:19AD 5D 36 10 86 02 49 1F (menu 2 -> back block $C7:19B4, else $C7:19D3)
    stock_back = bytes(rb.d[0x0719B4:0x0719D3])
    if stock_back[:3] != bytes.fromhex("42 03 02") or stock_back[-4:] != cursor_y:
        raise BuildError("options: unexpected back block at $C7:19B4")
    to_main = (bytes.fromhex("42 03 02") + MENU_CLEAR + bytes.fromhex("FF 8D 05 04 03 00 00")
               + _set(0x1036, 0) + _set(0x1032, 2) + cursor_y)
    back_s = (_skip_if_not(0x1036, 2, stock_back + b"\x00") + _skip_if_not(0x1036, SUBMENU, to_main) + b"\x00")
    s_back = rb.alloc("bulk", back_s, "script: title B in the OPTIONS submenu (features/options.py)")
    # Attract demo: SB5's title timer ($C5:6ECA, 30 x 64 frames without new input, then $C5:6EF3
    # switches to a demo mode) would cut a QR scan short. Its "new action?" test (JSR $6F2C) answers
    # yes while the title (mode 2) shows the submenu or the QR. M 8-bit, DBR in WRAM range.
    stub = bytes.fromhex("AD 31 10 C9 02 D0 0A AD 36 10 C9 03 90 03 A9 01 60 4C 2C 6F")
    at = rb.alloc("c5", stub, "title: no attract demo in the OPTIONS submenu / QR (features/options.py)")
    rb.patch(0xC56ECA, bytes.fromhex("20 2C 6F"), bytes([0x20, at & 0xFF, at >> 8 & 0xFF]),
             "title: attract demo timer waits in the OPTIONS submenu")
    rel = 0xC719D3 - 0xC719B4
    rb.patch(0xC719AD, bytes.fromhex("5D 36 10 86 02 49 1F"),
             bytes([0x24]) + rb.le24(s_back) + bytes([0x44, rel, 0x00]), "title: B in the OPTIONS submenu")
    return dict(s_confirm=s_confirm, s_back=s_back)
