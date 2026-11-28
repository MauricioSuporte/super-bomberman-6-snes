"""Stage HUD of the Normal Game drawn like Super Bomberman 6 (Unity)'s NormalGameHud: no clock, no score, each
seat's status instead.

SB6 (Assets/Resources/HUD/NormalGameHud.prefab, Sprites/HUD/NormalGame, copied to assets/hud): per player its
portrait, a 2 x 2 grid (fire range, speed / bombs, bomb type; the first three with their number over the icon),
2 x 3 power-ups (extra life, soft block pass, full fire / kick or bomb pass, punch, power glove) and a divider
(HudGrid's right line) on HudBase's 23-line panel; a seat without a player blinks PUSH START (HudPushStartInGrid);
the shared lives in a tab hanging below the panel's middle (HudLifePreviewLayout: a Lifes heart with the number).
Here:

* layout (HUD line y = screen line y + 1, lines 0-22 = HudBase rows 0-22): seat blocks of 56 pixels at x 8, 68,
  132, 192 = head (16 x 16, the bottom of SB6's HUD portrait of the character and skin chosen in the character
  select, assets/hud/portraits), grid, power-ups; dividers (2 pixels, HudGrid's) at x 65, 127, 189. Grid rows
  at lines 2 / 10 / 18 (+ 19, with a shadow at its bottom right), icons at lines 3-9 and 11-17. A seat out of the
  stage (not in the game, dead) blinks SB6's PUSH START (Unity's HUD/Push_start.png) every 64 frames, centered between its dividers. Heads
  fill columns 0-14 of their cells (column 15 blue: 1 pixel between the head and the grid in every seat).
* BG2 (4bpp) draws seats 1 and 4, BG1 (same characters, scrolled 4 pixels right in the HUD lines) seats 2 and 3:
  56-pixel blocks 60 / 64 pixels apart do not fit 8-pixel cells of one layer. Heads and icons in BG palettes 0
  (SB5's HUD colors) or 1 (the items' colors, entry 2 = their blinking border left out), opaque: the HUD's blue
  is palette 0 entry 4 / palette 1 entry 12 (the stage pause blacks the backdrop); tiles $D0-$F9 (SB5's HUD
  tiles, set 3 archive $4A, not loaded in the Normal Game). Maps: BG2 rows 28-31 of its lower screen ($3F80),
  BG1 rows 24-27 of the same screen ($3F00, BG1SC $3C in the HUD lines). The panel's top lines are a BG2 tile
  (BG3 keeps those cells for the text). Heads are drawn at the stage load (asm/hud.asm build_heads) from a
  template per character (a color class per pixel) and a map per skin (class -> entry in palettes 0 / 1, the
  palette of each tile).
* BG3 (2bpp, priority): palette 1 (SB5's HUD greens) the panel's border, the grid lines and the dividers,
  palette 0 (greys, white) the text; tiles up to $7F (from $59: free in every stage; below, SB5's HUD tiles,
  only shown by its hidden HUD rows), map rows 56-59 ($4700; HUD line y = row 56 line y + 4).
* Below the HUD lines SB5's stage IRQ shows the field (BG3 scroll 0: screen line s = BG3 line s + 1): BG3 rows
  2-4 of the field map hold the panel's last lines (HUD lines 20-22) and the lives tab (lines 21-30, x 116-139):
  its frame in BG3 palette 1, the heart in palette 6 (CGRAM 25-27 = items palette entries 9-11, kept for it:
  dark red, red, white) over the backdrop (the HUD's blue): window 2 hides BG1 / BG2 / OBJ in x 120-135 on screen
  lines 22-30 (asm/hud.asm hud_l21, a stage IRQ at line 31 puts the windows back).
* Sprites pass under the HUD (SB6): the line-0 IRQ leaves OBJ out of TM until SB5's line-21 IRQ puts `$030F` back,
  window 2 hides them behind the lives heart, the tab's frame and the panel's last lines are BG3 with priority.
* SB5's stage IRQ ($C0:F08D line 0) shows the HUD rows (BG2 VOFS 484, BG3 446, BG1 196 / HOFS -4, TM + BG1)
  while `!on` = $A5; SB5's own HUD rows (BG2 rows 0-2, BG3 rows 63, 0-1) are still written by SB5, unseen.
  Battle (IRQ $C0:F12A) keeps SB5's HUD.
* asm/hud.asm: hud_load (stage HUD task, Normal Game) queues the tiles and the heads; hud_tick (the HUD task's
  score redraw) every 4th frame (a check every frame cost 1-7 5 fps in tools/coop4_check.py): the rows (after
  the load; after a pause, whose menu rewrites BG3 rows), the lives and one seat, queuing a seat's cells / rows
  when they changed; the clock stops (no time up in the Normal Game: SB6 has none).
"""
import os
import struct

import numpy as np
from PIL import Image

from .. import asar
from ..rombuild import BuildError
from ..romlib import Rom, off

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASSETS = os.path.join(ROOT, "assets", "hud")
ASM = os.path.join(ROOT, "asm", "hud.asm")

# CGRAM 0-15 in every stage (set 3 palette 1, SB5's HUD; measured in all World 1 stages): BG palette 0 and
# BG3 palettes 0-3. Palette 1 = the items' (features/items.py), read from the build.
P0 = [0x48E4, 0x18C6, 0x35AD, 0x7FFF, 0x48E4, 0x0860, 0x0188, 0x036B,
      0x0000, 0x1000, 0x5900, 0x7F0F, 0x2B3F, 0x000A, 0x0018, 0x3DBF]
# CGRAM 15 (SB5's pink $3DBF: BG3 palette 3, unused by the Normal Game's BG3, 3 icon pixels) holds a purple in the
# Normal Game (hud_load / hud_tick write it to the CGRAM copy $7E:2910): SB6's purple skins had no color near them;
# of CGRAM 8-15 (BG3 palettes 2-3) it is the one whose loss costs the icons least and gives the heads most
PURPLE_ENTRY, PURPLE_RGB = 15, (152, 0, 208)
PURPLE = (PURPLE_RGB[2] * 31 + 127) // 255 << 10 | (PURPLE_RGB[1] * 31 + 127) // 255 << 5 | (PURPLE_RGB[0] * 31 + 127) // 255
HUD_P0 = P0[:PURPLE_ENTRY] + [PURPLE] + P0[PURPLE_ENTRY + 1:]   # CGRAM 0-15 as the Normal Game's HUD lines show it
P0_USE = list(range(1, 16))
P1_USE = [1] + list(range(3, 16))       # entry 2 = the items' blinking border
BLUE = {0: 4, 1: 12}                    # the HUD's blue in BG palettes 0 / 1 (items.FIXED[12])
BG3_PAL = 1                             # CGRAM 4-7: 1 = $0860 (dark), 2 = $0188 (dark green), 3 = $036B (green)
TEXT_PAL = 0                            # CGRAM 0-3: 1 = $18C6 (shadow), 3 = $7FFF (white)
TAB_PAL = 6                             # CGRAM 24-27: 1 dark red, 2 red, 3 white (items entries 9-11)

# VRAM / layout
BG2_TILE0 = 0xD0                        # BG2 tiles $D0-$F9 (BG1/BG2 characters at word 0)
BG2_TILES = 42
BG3_CHR = 0x5000
BG3_LOW = 0x01                          # BG3 tiles may go down to here (SB5's HUD tiles below $59)
HUD_MAP = 0x3C00                        # lower screen of BG2's HUD map ($0369 = $3A: $3800, 32 x 64)
BG2_ROW0 = 28                           # BG2 rows 28-31: HUD line y = row 28 line 6 + y
BG1_ROW0 = 24                           # BG1 rows 24-27 of map $3C00 (BG1SC $3C in the HUD lines)
BG3_MAP = 0x4000
BG3_ROW0 = 56                           # rows 56-59 of BG3's 32 x 64 map: HUD line y = row 56 line y + 4
BG3_DY = 4                              # (PUSH START's last lines and the panel's bottom lines in different cells)
BG3_ROWS = 4
FIELD_ROW0 = 2                          # field BG3 rows 2-4: HUD line y = field BG3 line y - 14
# screen line s shows BG line VOFS + 1 + s; HUD line y is screen line y + 1
VOFS2 = 256 + 8 * BG2_ROW0 + 6 - 2      # 484
VOFS1 = 8 * BG1_ROW0 + 6 - 2            # 196
HOFS1 = 0x3FC                           # -4: BG1's cells 4 pixels right of BG2's
BG1_SHIFT = 4
VOFS3 = 8 * BG3_ROW0 + BG3_DY - 2       # 450
HUD_LINES = 23
FIELD_FROM = 20                         # HUD lines drawn on the field's BG3 too (whichever layer the IRQ shows)
SEAT_X = (8, 68, 132, 192)              # first pixel of each seat's block (head 16, grid 16, power-ups 24)
SEAT_BG1 = (False, True, True, False)
SEAT_W = 56
DIVIDERS = (65, 127, 189)               # HudGrid's divider: bright green, dark (x, x + 1), lines 2-19
BG3_COLS = ((1, 7), (8, 8), (16, 8), (24, 7))   # each seat's BG3 columns (its block, the dividers it holds)
TEXT_Y = 1                              # Unity's Push_start (23 x 19, rows 1-17 drawn), its row 1 on line 2,
TEXT_X = (23, 85, 147, 210)             # centered between the seat's dividers / borders (blue x 4-64, 67-126,
                                        # 129-188, 191-252: text_x())
PUSH_OF = {(49, 48, 49): 1, (107, 105, 107): 2, (255, 255, 255): 3}   # -> BG3 palette 0 ($18C6, $35AD, white)
BLINK = 64                              # frames per blink phase ($0069 bit 6)
STATES = 4                              # BG3 block per seat: in the game, PUSH START, blank, GAME OVER
TAB_X, TAB_W, TAB_Y = 116, 24, 21       # lives tab: x 116-139, HUD lines 21 (top) - 30 (bottom line)
TAB_BOTTOM = 30
HEART_X = 123                           # Unity's 9 x 9 Lifes heart without row 2: lines 22-29
HEART_ROWS = (0, 1, 3, 4, 5, 6, 7, 8)
WIN = (120, 135)                        # window 2 (backdrop behind the heart) on HUD lines 22-29
HEART_COLS = (15, 16)                   # field BG3 row 3: the heart's 2 tiles (dynamic)

# BG2 tile numbers
T_BLANK = 0xD0
T_TOP = 0xD1                            # the panel's top lines (HUD lines 0-1)
T_HEAD = 0xD2                           # + 4 seat + (TL, TR, BL, BR)
T_DYN = 0xE2                            # + 3 seat + (fire, speed, bombs)
T_ICON = 0xEE                           # + icon - 1
ICONS = ["DefaultBomb", "RemoteBomb", "SpikyBomb", "MagnetBomb", "SearchBomb", "Kick", "BombPass", "BoxingGlove",
         "PowerGlove", "ExtraLife", "SoftBlockPass", "GoldFire"]
I_NORMAL, I_REMOTE, I_PIERCE, I_MAGNET, I_SEARCH, I_KICK, I_BPASS, I_PUNCH, I_GLOVE, I_HEART, I_WPASS, I_FULL = \
    range(1, 13)
DYN = ["MaxExplosionRange", "MaxSpeed", "MaxBombs"]

# SB5's HUD (set 3 archive $4A, LZ, VRAM $0D00 = tile $D0): heads of P1 / P2, tiles (TL, TR / ML, MR / BL, BR)
# of a 16 x 24 strip whose rows 4-19 are the head: the heads without the character select (attract demo)
HEAD_TILES = ((0xEE, 0xEF, 0xF0, 0xF1, 0xF2, 0xF3), (0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9))
HEAD_BG = 4
HEAD_RECOLOR = {2: {3: 15, 11: 14, 2: 13}, 3: {3: 11, 11: 10, 2: 9}}
# characters of the character select (asm/picker.asm choice 1-9) -> SB6's portrait folders
PORTRAITS = ["Bomberman", "LadyBomber", "TinyBomber", "Bookworm", "KamikazeBomber", "MechaBomber", "MinerBomber",
             "CossackBomber", "BigBomber"]
HEAD_SHIFTS = 1                         # templates per character (every seat draws the same window)
HEAD_GAP = 1                            # see-through columns at a head's right (blue up to the grid's line)
HEAD_MAP = 20                           # entries of a skin's class map (class 0 = see-through)
HEAD_REC = 1 + HEAD_MAP                 # tile palettes (bit per tile), map: (palette 1 entry << 4) | palette 0 entry

# HudBase colors -> BG3 palette 1 entries (the blue inside = 0: BG2's blue)
BG3_OF = {(8, 8, 16): 1, (48, 48, 48): 1, (66, 97, 0): 2, (90, 223, 0): 3}

# seat records (asm/hud.asm build_rec): act, fire (out: blink phase), speed, bombs, bomb type icon, power-ups x 6
REC = 11


def rgb5(c):
    return (c & 31, c >> 5 & 31, c >> 10 & 31)


def _load(name):
    return np.asarray(Image.open(os.path.join(ASSETS, name + ".png")).convert("RGBA"), np.int32)


def _err(rgb, c):
    r, g, b = ((int(v) * 31 + 127) // 255 for v in rgb[:3])
    pr, pg, pb = rgb5(c)
    return 3 * (pr - r) ** 2 + 4 * (pg - g) ** 2 + 2 * (pb - b) ** 2


def _nearest(rgb, pal, use):
    e, i = min((_err(rgb, pal[i]), i) for i in use)
    return i, e


def quantize_pic(pic, pals):
    """RGBA picture -> (palette, entries), the palette (0 / 1) with the smaller error; see-through = the blue."""
    out = []
    for n, (pal, use) in enumerate(pals):
        idx = np.full(pic.shape[:2], BLUE[n], np.int32)
        err = 0
        for y in range(pic.shape[0]):
            for x in range(pic.shape[1]):
                if pic[y, x, 3] >= 128:
                    idx[y, x], e = _nearest(pic[y, x], pal, use)
                    err += e
        out.append((err, n, idx))
    out.sort(key=lambda t: t[0])
    return out[0][1], out[0][2]


def _white(pal, use):
    return max(use, key=lambda i: sum(rgb5(pal[i])))


def digit_mask(d):
    """7 x 7 bool: Unity's HudNumbers digit d."""
    return _load("HudNumbers")[:, 7 * d:7 * d + 7, 3] >= 128


def cell_tile(idx7, blue):
    """8 x 8 entries: a 7 x 7 picture at x / y 1-7 (row / column 0 = under the grid line: the blue)."""
    t = np.full((8, 8), blue, np.int32)
    t[1:, 1:] = idx7
    return t


def encode_4bpp(t):
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = int(t[y][x])
            for p in range(4):
                if v >> p & 1:
                    out[(p // 2) * 16 + y * 2 + (p & 1)] |= 0x80 >> x
    return bytes(out)


def encode_2bpp(t):
    out = bytearray(16)
    for y in range(8):
        for x in range(8):
            v = int(t[y][x])
            for p in range(2):
                if v >> p & 1:
                    out[y * 2 + p] |= 0x80 >> x
    return bytes(out)


def decode_4bpp(raw):
    t = np.zeros((8, 8), np.int32)
    for y in range(8):
        for p in range(4):
            v = raw[(p // 2) * 16 + y * 2 + (p & 1)]
            for x in range(8):
                t[y, x] |= ((v >> (7 - x)) & 1) << p
    return t


def decode_2bpp(raw):
    t = np.zeros((8, 8), np.int32)
    for y in range(8):
        for p in range(2):
            v = raw[y * 2 + p]
            for x in range(8):
                t[y, x] |= ((v >> (7 - x)) & 1) << p
    return t


def default_heads(base_rom):
    """{seat: 16 x 16 palette-0 entries} from SB5's HUD tiles (blue = 4)."""
    rom = Rom(base_rom)
    arc = rom.archive(3, 0x4A)
    if arc["vram"] != 0x0D00 or arc["flags"] & 0x80:
        raise BuildError("hud: set 3 archive $4A is not SB5's HUD tiles (LZ at VRAM $0D00)")
    data, _ = rom.archive_data(3, 0x4A)
    out = {}
    for seat, tiles in enumerate(HEAD_TILES):
        strip = np.zeros((24, 16), np.int32)
        for i, t in enumerate(tiles):
            o = (t - 0xD0) * 32
            strip[8 * (i // 2):8 * (i // 2) + 8, 8 * (i % 2):8 * (i % 2) + 8] = decode_4bpp(data[o:o + 32])
        out[seat] = strip[4:20].copy()
    for seat, m in HEAD_RECOLOR.items():
        h = out[0].copy()
        for a, b in m.items():
            h[out[0] == a] = b
        out[seat] = h
    pink = tuple(v * 255 // 31 for v in rgb5(P0[PURPLE_ENTRY]))
    alt = min((i for i in P0_USE if i != PURPLE_ENTRY), key=lambda i: _lab_err(pink, P0[i]))
    for h in out.values():
        h[h == 0] = HEAD_BG
        h[h == PURPLE_ENTRY] = alt                      # CGRAM 15 is the purple in the Normal Game
    return out


def portrait_heads():
    """[((template,), [per skin: [class -> (r, g, b)]])] per character of the character
    select: 16 x 16 classes of SB6's HUD portrait (from the head's top), the head in columns 0-14 (centered there,
    a wider one cut evenly on both sides) and column 15 see-through: at least 1 pixel of blue between the head
    and the grid's left line (HEAD_GAP) in every seat; classes = pixels with the same color in every skin (0 =
    see-through). One template for every seat (seats 2-4 used to have their own, one pixel left of P1's)."""
    out = []
    for name in PORTRAITS:
        d = os.path.join(ASSETS, "portraits", name)
        skins = sorted(int(f[:-4]) for f in os.listdir(d) if f.endswith(".png"))
        if skins != list(range(1, len(skins) + 1)):
            raise BuildError(f"hud: portraits of {name} are not skins 1-{len(skins)}")
        ims = [np.asarray(Image.open(os.path.join(d, f"{k}.png")).convert("RGBA")) for k in skins]
        ys, _ = np.nonzero(ims[0][..., 3] >= 128)
        y0 = min(int(ys.min()), 16)
        band = np.nonzero((ims[0][y0:y0 + 16, :, 3] >= 128).any(0))[0]
        a, w = int(band.min()), int(band.max()) - int(band.min()) + 1
        n = 16 - HEAD_GAP
        x0 = a - (n - w) // 2 if w <= n else a + (w - n) // 2
        x0 = min(max(x0, 0), ims[0].shape[1] - n)
        classes = {}
        tpls = []
        for _ in range(HEAD_SHIFTS):
            sel = [im[y0:y0 + 16, x0:x0 + n] for im in ims]
            tpl = np.zeros((16, 16), np.int32)
            for y in range(16):
                for x in range(n):
                    if sel[0][y, x, 3] >= 128:
                        k = tuple(tuple(int(v) for v in s[y, x, :3]) for s in sel)
                        tpl[y, x] = classes.setdefault(k, len(classes) + 1)
            tpls.append(tpl)
        if len(classes) >= HEAD_MAP:
            raise BuildError(f"hud: {name}'s head has {len(classes)} color classes (at most {HEAD_MAP - 1})")
        cols = [[None] * (len(classes) + 1) for _ in skins]
        for k, c in classes.items():
            for s in range(len(skins)):
                cols[s][c] = k[s]
        out.append((tuple(tpls), cols))
    return out


_LAB = {}


def _lab_err(rgb, c):
    """Squared Lab distance (heads: an RGB distance turned SB6's greys into the items' greens)."""
    from .items import _lab
    k = tuple(int(v) for v in rgb[:3])
    if k not in _LAB:
        _LAB[k] = _lab(k)
    if c not in _LAB:
        _LAB[c] = _lab(tuple(v * 255 // 31 for v in rgb5(c)))
    return float(((_LAB[k] - _LAB[c]) ** 2).sum())


def head_record(tpls, cols, p1, shift=0):
    """A skin's record (HEAD_REC bytes: tile palettes of the template in bits 0-3, the class map) and the 4 tiles [(palette, 8 x 8 entries)] of template `shift` as asm/hud.asm draws them."""
    pals = ((HUD_P0, P0_USE), (p1, P1_USE))

    def near(c, pal, use):
        return min(use, key=lambda i: _lab_err(c, pal[i]))
    m = [[BLUE[0], BLUE[1]]] + [[near(c, HUD_P0, P0_USE), near(c, p1, P1_USE)] for c in cols[1:]]
    bits, out = 0, []
    for n, tpl in enumerate(tpls):
        tiles = []
        for t in range(4):
            part = tpl[8 * (t >> 1):8 * (t >> 1) + 8, 8 * (t & 1):8 * (t & 1) + 8]
            err = [sum(_lab_err(cols[c], pals[p][0][m[c][p]]) for c in part.ravel() if c) for p in (0, 1)]
            p = 1 if err[1] < err[0] else 0
            bits |= p << (t + 4 * n)
            tiles.append((p, np.vectorize(lambda c: m[c][p])(part)))
        out.append(tiles)
    rec = bytes([bits]) + bytes(a | b << 4 for a, b in m) + bytes(HEAD_MAP - len(m))
    return rec, out[shift]


def text_pixels(name="PushStart"):
    """(entries 19 x 23): SB6's PUSH START (assets/hud/PushStart.png = Unity's HUD/Push_start.png) or GAME OVER
    (GameOver.png, the same letters' style: a seat out of the stage when no life is left) in BG3 palette 0
    (dark, grey, white), 0 = see-through."""
    img = _load(name)
    pic = np.zeros(img.shape[:2], np.int32)
    for y in range(img.shape[0]):
        for x in range(img.shape[1]):
            if img[y, x, 3] >= 128:
                k = tuple(int(v) for v in img[y, x, :3])
                if k not in PUSH_OF:
                    raise BuildError(f"hud: {name}.png color {k}")
                pic[y, x] = PUSH_OF[k]
    return pic


def blue_span(seat, line=10):
    """(first, last) x of the panel's blue around a seat's block (between its dividers / the borders)."""
    base = _load("HudBase")
    x = SEAT_X[seat] + 8
    a, b = x, x
    bg = lambda x: x not in DIVIDERS and x - 1 not in DIVIDERS and tuple(int(v) for v in base[line, x, :3]) == (40, 48, 112)
    while bg(a - 1):
        a -= 1
    while bg(b + 1):
        b += 1
    return a, b


def text_x(seat):
    """PUSH START's first x: its 23 pixels centered in blue_span (TEXT_X)."""
    a, b = blue_span(seat)
    return (a + b) // 2 - text_pixels().shape[1] // 2


def bg3_picture(states):
    """(palettes, entries) 23 x 256 of BG3's HUD lines; states per seat: 0 in the game (grid), 1 PUSH START,
    2 out, blank (blink), 3 GAME OVER (out, no life left)."""
    base = _load("HudBase")
    ent = np.zeros((HUD_LINES, 256), np.int32)
    pal = np.full((HUD_LINES, 256), BG3_PAL, np.int32)
    for y in range(HUD_LINES):
        for x in range(256):
            ent[y, x] = BG3_OF.get(tuple(int(v) for v in base[y, x, :3]), 0)
    ent[0:2, 8:248] = 0                                 # the top lines: BG2's T_TOP
    for x in DIVIDERS:
        ent[2:20, x] = 3
        ent[2:20, x + 1] = 1
    texts = {1: text_pixels(), 3: text_pixels("GameOver")}
    for seat, st in enumerate(states):
        sx = SEAT_X[seat]
        if st == 0:
            x0, w = sx + 16, 16
            ent[2, x0:x0 + w + 1] = 2
            ent[2, x0] = ent[2, x0 + w] = 1
            for x in (x0, x0 + 8, x0 + w):
                ent[3:19, x] = 3
            for y in (10, 18):
                ent[y, x0:x0 + w + 1] = 3
            ent[19, x0 - 1:x0 + w + 2] = 3              # a second bottom line and a shadow at the bottom right
            ent[18, x0 + w + 1] = 1
            ent[19, x0 + w + 2] = 1
        elif st in texts:
            text = texts[st]
            y0, x0 = TEXT_Y, TEXT_X[seat]
            m = text != 0
            ent[y0:y0 + len(text), x0:x0 + text.shape[1]][m] = text[m]
            pal[y0:y0 + len(text), x0:x0 + text.shape[1]][m] = TEXT_PAL
    return pal, ent


def life_heart(v):
    """8 x 9 of Unity's Lifes heart v without its row 2 (one line shorter: the heart fits the tab, lines 22-29;
    the number, rows 4-8, unchanged), in TAB_PAL entries (nearest of dark red, red, white); 0 = see-through."""
    from . import items
    img = _load("Lifes")[:, 9 * v:9 * v + 9]
    cols = [items.FIXED[9], items.FIXED[10], items.FIXED[11]]
    h = np.zeros((len(HEART_ROWS), 9), np.int32)
    for y, sy in enumerate(HEART_ROWS):
        for x in range(9):
            p = img[sy, x]
            if p[3] < 128:
                continue
            rgb = tuple(int(c) for c in p[:3])
            h[y, x] = 1 + min(range(3), key=lambda i: _lab_err(rgb, items.bgr555(cols[i])))
    return h


def field_picture(lives=None):
    """(palettes, entries, backdrop) of HUD lines FIELD_FROM .. TAB_BOTTOM on the field's BG3: the panel's last
    lines, the tab, the heart of `lives` (or none); backdrop = pixels where window 2 shows the backdrop."""
    n = TAB_BOTTOM + 1 - FIELD_FROM
    pal = np.full((n, 256), BG3_PAL, np.int32)
    ent = np.zeros((n, 256), np.int32)
    back = np.zeros((n, 256), bool)
    _, base = bg3_picture([2] * 4)
    ent[:HUD_LINES - FIELD_FROM] = base[FIELD_FROM:]

    def put(y, x, v, p=BG3_PAL):
        ent[y - FIELD_FROM, x], pal[y - FIELD_FROM, x] = v, p
    x0 = TAB_X
    for y in range(TAB_Y + 1, TAB_BOTTOM):              # sides: bright green, dark
        for x in (x0, x0 + 1, x0 + TAB_W - 2, x0 + TAB_W - 1):
            if y > HUD_LINES - 1:
                put(y, x, 0)
        for x, v in ((x0 + 2, 3), (x0 + 3, 1), (x0 + TAB_W - 4, 1), (x0 + TAB_W - 3, 3)):
            put(y, x, v)
        for x in range(WIN[0], WIN[1] + 1):
            put(y, x, 0, TAB_PAL)
            back[y - FIELD_FROM, x] = True
    put(TAB_BOTTOM, x0 + 2, 2)
    for x in range(x0 + 3, x0 + TAB_W - 3):
        put(TAB_BOTTOM, x, 3)
    put(TAB_BOTTOM, x0 + TAB_W - 3, 2)
    if lives is not None:
        h = life_heart(lives)
        for y in range(len(h)):
            for x in range(9):
                if h[y, x]:
                    put(TAB_Y + 1 + y, HEART_X + x, h[y, x], TAB_PAL)
    return pal, ent, back


class Bg3Tiles:
    """BG3 tiles (2bpp) shared by flips; words get their numbers once every tile is known."""

    def __init__(self):
        self.tiles, self.look = [], {}

    def add(self, ent):
        if not ent.any():
            return None
        for f in range(4):
            tt = ent[:, ::-1] if f & 1 else ent
            tt = tt[::-1] if f & 2 else tt
            k = encode_2bpp(tt)
            if k in self.look:
                return self.look[k], f
        self.look[encode_2bpp(ent)] = len(self.tiles)
        self.tiles.append(encode_2bpp(ent))
        return len(self.tiles) - 1, 0

    def cell(self, pal, ent, where):
        ps = set(int(v) for v in pal[ent != 0].ravel())
        if len(ps) > 1:
            raise BuildError(f"hud: BG3 cell {where} needs palettes {sorted(ps)}")
        t = self.add(ent)
        return None if t is None else (t[0], t[1], ps.pop())


def bg3_word(t0, c):
    if c is None:
        return 0
    n, f, p = c
    return (t0 + n) | p << 10 | 0x2000 | (f & 1) << 14 | (f >> 1) << 15


def build(base_rom, p1):
    """Every table of the HUD: {name: bytes / list}."""
    if len(p1) != 16:
        raise BuildError("hud: items palette")
    pals = ((HUD_P0, P0_USE), (p1, P1_USE))
    if tuple(text_x(s) for s in range(4)) != TEXT_X:
        raise BuildError(f"hud: TEXT_X is not centered between the dividers ({[text_x(s) for s in range(4)]})")
    t = {"p1": p1}
    tiles, pal = {}, {}
    tiles[T_BLANK], pal[T_BLANK] = np.full((8, 8), BLUE[0], np.int32), 0
    top = np.full((8, 8), BLUE[0], np.int32)
    top[6], top[7] = 6, 5                               # HudBase rows 0-1: CGRAM 6 / 5 (= BG3 palette 1's)
    tiles[T_TOP], pal[T_TOP] = top, 0
    for seat, h in default_heads(base_rom).items():
        for i in range(4):
            n = T_HEAD + 4 * seat + i
            tiles[n] = h[8 * (i // 2):8 * (i // 2) + 8, 8 * (i % 2):8 * (i % 2) + 8]
            pal[n] = 0
    for k, name in enumerate(ICONS):
        p, idx = quantize_pic(_load(name), pals)
        n = T_ICON + k
        tiles[n], pal[n] = cell_tile(idx, BLUE[p]), p
    dyn_src, dyn_pal = [], []
    for name in DYN:
        p, idx = quantize_pic(_load(name), pals)
        w = _white(*pals[p])
        for d in range(10):
            c = idx.copy()
            c[digit_mask(d)] = w
            dyn_src.append(encode_4bpp(cell_tile(c, BLUE[p])))
        dyn_pal.append(p)
    t["dyn_src"] = b"".join(dyn_src)                    # 3 kinds x 10 tiles (fire, speed, bombs)
    for seat in range(4):
        for k in range(3):
            n = T_DYN + 3 * seat + k
            tiles[n], pal[n] = decode_4bpp(dyn_src[10 * k]), dyn_pal[k]
    if sorted(tiles) != list(range(BG2_TILE0, BG2_TILE0 + len(tiles))) or len(tiles) > BG2_TILES:
        raise BuildError("hud: BG2 tiles are not within $D0-$F9")
    t["bg2_tiles"] = b"".join(encode_4bpp(tiles[n]) for n in sorted(tiles))
    t["bg2_pics"], t["bg2_pal"] = tiles, pal

    def word(n):
        return n | pal[n] << 10
    t["icon_words"] = [word(T_BLANK)] + [word(T_ICON + k) for k in range(len(ICONS))]
    t["head_words"] = [[word(T_HEAD + 4 * s + i) for i in range(4)] for s in range(4)]
    t["dyn_words"] = [[word(T_DYN + 3 * s + k) for k in range(3)] for s in range(4)]
    t["bg2_rows"] = [[word(T_BLANK)] + [word(T_TOP)] * 30 + [word(T_BLANK)]] + [[word(T_BLANK)] * 32 for _ in range(3)]
    t["bg1_rows"] = [[0] * 32 for _ in range(4)]
    t["bg2_map"] = b"".join(struct.pack("<32H", *r) for r in t["bg2_rows"])
    t["bg1_map"] = b"".join(struct.pack("<32H", *r) for r in t["bg1_rows"])
    t["seat_col"] = [(x - (BG1_SHIFT if b else 0)) // 8 for x, b in zip(SEAT_X, SEAT_BG1)]
    t["seat_rowa"] = [HUD_MAP + 32 * ((BG1_ROW0 if b else BG2_ROW0) + 1) + c for b, c in zip(SEAT_BG1, t["seat_col"])]
    # heads of the character select's characters and skins
    heads = portrait_heads()
    for name, (tpls, _) in zip(PORTRAITS, heads):
        if any(tpl[:, 16 - HEAD_GAP:].any() for tpl in tpls):
            raise BuildError(f"hud: {name}'s head reaches the grid (no {HEAD_GAP}-pixel gap)")
    t["heads"] = heads
    tpl_blob, recs, counts = bytearray(), [], []
    for tpls, cols in heads:
        tpl_blob += b"".join(bytes(int(v) for v in tpl.ravel()) for tpl in tpls)
        counts.append(len(cols))
        recs.append(b"".join(head_record(tpls, c, p1)[0] for c in cols))
    t["head_tpl"], t["head_recs"], t["head_counts"] = bytes(tpl_blob), recs, counts
    # BG3: the HUD rows (each seat in 3 states), the field rows, the tab's hearts
    b3 = Bg3Tiles()

    def rows_of(pal3, ent3, nrows, cols, tag):
        return [[b3.cell(pal3[8 * ty:8 * ty + 8, 8 * tx:8 * tx + 8], ent3[8 * ty:8 * ty + 8, 8 * tx:8 * tx + 8],
                         f"{tag} ({tx}, {ty})") for tx in cols] for ty in range(nrows)]

    def hud_pic(states):
        pp, ee = bg3_picture(states)
        P = np.full((8 * BG3_ROWS, 256), BG3_PAL, np.int32)
        E = np.zeros((8 * BG3_ROWS, 256), np.int32)
        P[BG3_DY:BG3_DY + HUD_LINES], E[BG3_DY:BG3_DY + HUD_LINES] = pp, ee
        return P, E
    hud_rows = rows_of(*hud_pic([2] * 4), BG3_ROWS, range(32), "HUD")
    blocks = []
    for s, (c0, n) in enumerate(BG3_COLS):
        var = []
        for st in range(STATES):
            states = [2] * 4
            states[s] = st
            var.append(rows_of(*hud_pic(states), BG3_ROWS, range(c0, c0 + n), f"seat {s + 1}"))
        blocks.append(var)
    # field rows 2-4 = HUD lines 14-37
    fp, fe, fb = field_picture()
    P = np.full((24, 256), BG3_PAL, np.int32)
    E = np.zeros((24, 256), np.int32)
    o = FIELD_FROM - (8 * FIELD_ROW0 - 2)
    P[o:o + len(fp)], E[o:o + len(fe)] = fp, fe
    field_rows = rows_of(P, E, 3, range(32), "field")
    heart = []
    for v in range(10):
        fp, fe, _ = field_picture(v)
        E[o:o + len(fe)], P[o:o + len(fp)] = fe, fp
        heart.append([E[8:16, 8 * c:8 * c + 8].copy() for c in HEART_COLS])
    n3 = len(b3.tiles) + len(HEART_COLS)
    t0 = 0x80 - n3                                      # BG3 tiles end at $7F (the font starts at $80)
    if t0 < BG3_LOW:
        raise BuildError(f"hud: {n3} BG3 tiles do not fit below $80")
    t3_lives = t0 + len(b3.tiles)
    t["bg3_t0"], t["t3_lives"] = t0, t3_lives
    t["bg3_tiles"] = b"".join(b3.tiles)
    t["lives_src"] = b"".join(encode_2bpp(c) for cells in heart for c in cells)

    def words(rows):
        return [[bg3_word(t0, c) for c in r] for r in rows]
    t["bg3_rows"] = words(hud_rows)
    t["bg3_map"] = b"".join(struct.pack("<32H", *r) for r in t["bg3_rows"])
    t["bg3_block"] = [[words(v) for v in var] for var in blocks]     # [seat][state][row][column]
    fr = words(field_rows)
    for i, c in enumerate(HEART_COLS):
        fr[1][c] = (t3_lives + i) | TAB_PAL << 10 | 0x2000
    t["field_rows"] = fr
    t["field_map"] = b"".join(struct.pack("<32H", *r) for r in fr)
    return t


def seat_words(t, seat, rec, head_bits=0):
    """BG2 / BG1 words of a seat's block: (row A, row B), 7 each (asm/hud.asm row_words)."""
    act, fire, speed, bombs, bt, p0, p1, p2, p3, p4, p5 = rec
    blank = t["icon_words"][0]
    if not act:
        return [blank] * 7, [blank] * 7
    h = [w & ~0x1C00 | (head_bits >> i & 1) << 10 for i, w in enumerate(t["head_words"][seat])]
    d, iw = t["dyn_words"][seat], t["icon_words"]
    return [h[0], h[1], d[0], d[1], iw[p0], iw[p1], iw[p2]], [h[2], h[3], d[2], iw[bt], iw[p3], iw[p4], iw[p5]]


def record(act, fire, speed_word, bombs, ab, f167a, hearts, frame=0, lives=1):
    """A seat's record from SB5's RAM, as build_rec computes it (frame = $0069: an out seat's blink phase;
    lives = $1D23: none left = GAME OVER, 2, blinking as PUSH START)."""
    if not act:
        on = frame >> 6 & 1
        return (0, 2 if on and lives == 0 else on) + (0,) * (REC - 2)
    clamp = lambda v: min(v, 9)
    speed = 1 if speed_word < 0xE0 else clamp((speed_word - 0xC0) >> 5)
    bt = I_REMOTE if ab & 0x01 else I_PIERCE if ab & 0x10 else I_SEARCH if ab & 0x40 else I_MAGNET if ab & 0x20 \
        else I_NORMAL
    kick = I_KICK if ab & 0x02 else I_BPASS if not f167a & 0x40 else 0
    return (1, clamp(fire), speed, clamp(bombs), bt, I_HEART if hearts else 0, 0 if f167a & 0x20 else I_WPASS,
            I_FULL if fire >= 8 else 0, kick, I_PUNCH if ab & 0x08 else 0, I_GLOVE if ab & 0x04 else 0)


def seat_state(rec):
    return 0 if rec[0] else 3 if rec[1] == 2 else 1 if rec[1] else 2


def seat_head(t, seat, picks=None):
    """(tile bits, [4 x 8 x 8 entries]) of a seat's head: the character select's choice (picks = bytes of
    $7F:FF00-$7F:FF0F) or SB5's head."""
    if picks and picks[1] == 1:
        c, s = picks[2 + seat] - 1, picks[8 + seat]
        if 0 <= c < len(t["heads"]) and s < t["head_counts"][c]:
            tpls, cols = t["heads"][c]
            _, tiles = head_record(tpls, cols[s], t["p1"])
            return sum(p << i for i, (p, _) in enumerate(tiles)), [e for _, e in tiles]
    return 0, [t["bg2_pics"][T_HEAD + 4 * seat + i] for i in range(4)]


def render(t, p1, recs, lives, p0=HUD_P0, picks=None, backdrop=None):
    """(31 x 256 x 3 5-bit picture, 31 x 256 bool: pixels the HUD owns) of HUD lines 0-30 (screen lines 1-31) for
    seat records, lives (0-9) and the character select's choices; p0 / p1 = CGRAM 0-15 / 16-31; backdrop = the
    color behind the heart (default CGRAM 0; the stage pause blacks CGRAM 0 below the HUD lines only)."""
    cols = {0: p0, 1: p1}
    cg = list(p0) + list(p1)
    n = TAB_BOTTOM + 1
    out = np.zeros((n, 256, 3), np.int32)
    own = np.zeros((n, 256), bool)
    rows = {False: [list(r) for r in t["bg2_rows"]], True: [list(r) for r in t["bg1_rows"]]}
    pics = dict(t["bg2_pics"])
    for s, rec in enumerate(recs):
        bits, heads = seat_head(t, s, picks)
        for i in range(4):
            pics[T_HEAD + 4 * s + i] = heads[i]
        a, b = seat_words(t, s, rec, bits)
        c, r = t["seat_col"][s], rows[SEAT_BG1[s]]
        r[1][c:c + 7], r[2][c:c + 7] = a, b
        if rec[0]:
            for k, v in enumerate((rec[1], rec[2], rec[3])):
                pics[T_DYN + 3 * s + k] = decode_4bpp(t["dyn_src"][32 * (10 * k + v):32 * (10 * k + v) + 32])

    def layer(rs, shift):
        img = np.full((HUD_LINES, 256), -1, np.int32)
        for y in range(HUD_LINES):
            r, py = (y + 6) // 8, (y + 6) % 8
            for tx in range(32):
                w = rs[r][tx]
                if not w & 0x3FF:
                    continue
                line = pics[w & 0x3FF][py]
                for px in range(8):
                    if line[px]:
                        img[y, (8 * tx + px + shift) % 256] = (w >> 10 & 7) << 4 | line[px]
        return img
    bg2, bg1 = layer(rows[False], 0), layer(rows[True], BG1_SHIFT)
    for y in range(HUD_LINES):
        for x in range(256):
            v = bg1[y, x] if bg1[y, x] >= 0 else bg2[y, x]
            out[y, x] = rgb5(cols[v >> 4][v & 15]) if v >= 0 else rgb5(p0[0])
            own[y, x] = True
    bp, be = bg3_picture([seat_state(r) for r in recs])
    for y in range(HUD_LINES):
        for x in range(256):
            if be[y, x]:
                out[y, x] = rgb5(cg[4 * bp[y, x] + be[y, x]])
    fp, fe, fb = field_picture(lives)
    for y in range(len(fe)):
        for x in range(256):
            if fe[y, x]:
                out[FIELD_FROM + y, x] = rgb5(cg[4 * fp[y, x] + fe[y, x]])
                own[FIELD_FROM + y, x] = True
            elif fb[y, x]:
                out[FIELD_FROM + y, x] = rgb5(p0[0] if backdrop is None else backdrop)
                own[FIELD_FROM + y, x] = True
    return out, own


def apply(rb, base_rom, preview=None):
    from . import items
    p1 = list(struct.unpack("<16H", bytes(rb.d[off(items.PALETTE) + 4:off(items.PALETTE) + 36])))
    want = {e: items.bgr555(c) for e, c in items.FIXED.items()}
    if any(p1[e] != w for e, w in want.items()) or p1[BLUE[1]] != P0[BLUE[0]]:
        raise BuildError("hud: the items palette does not hold the HUD's fixed colors (items.FIXED)")
    t = build(base_rom, p1)
    region = "free_c8_sheets"
    dyn = rb.alloc(region, t["dyn_src"] + t["lives_src"], "SB6 HUD: numbered cells, lives hearts")
    parts = ["bg2_tiles", "bg3_tiles", "bg2_map", "bg1_map", "bg3_map", "field_map"]
    o = {}
    blob = b""
    for k in parts:
        o[k] = len(blob)
        blob += t[k]
    data = rb.alloc(region, blob, "SB6 HUD: BG2 / BG3 tiles and rows")
    hrec_off, hrec = [], bytearray()
    for r in t["head_recs"]:
        hrec_off.append(len(hrec))
        hrec += r
    heads = rb.alloc(region, t["head_tpl"] + bytes(hrec), "SB6 HUD: heads (templates, skin maps)")
    reg = rb.regions[region]
    if len({dyn >> 16, data >> 16, heads >> 16, reg.cursor >> 16}) != 1:
        raise BuildError("hud: code and tables in two banks")
    words = []
    for s in range(4):
        words += t["head_words"][s] + t["dyn_words"][s]
    block = [w for s in range(4) for st in range(STATES) for r in t["bg3_block"][s][st] for w in r]
    blkoff, a = [], 0
    for s in range(4):
        for st in range(STATES):
            blkoff.append(a)
            a += BG3_ROWS * BG3_COLS[s][1]
    hrec_at = heads + len(t["head_tpl"])

    def at(k):
        return f"${data + o[k]:06X}"
    defs = {"ORG": f"${reg.cursor:06X}", "DYNSRC": f"${dyn:06X}", "LIVSRC": f"${dyn + len(t['dyn_src']):06X}",
            "DATABANK": f"${data & 0xFF0000:06X}",
            "BG2T": at("bg2_tiles"), "BG2TN": str(len(t["bg2_tiles"])), "BG2TV": f"${16 * BG2_TILE0:04X}",
            "BG3T": at("bg3_tiles"), "BG3TN": str(len(t["bg3_tiles"])),
            "BG3TV": f"${BG3_CHR + 8 * t['bg3_t0']:04X}",
            "BG2M": at("bg2_map"), "BG2MV": f"${HUD_MAP + 32 * BG2_ROW0:04X}",
            "BG1M": at("bg1_map"), "BG1MV": f"${HUD_MAP + 32 * BG1_ROW0:04X}",
            "BG3M": at("bg3_map"), "BG3MV": f"${BG3_MAP + 32 * BG3_ROW0:04X}",
            "FLDM": at("field_map"), "FLDMV": f"${BG3_MAP + 32 * FIELD_ROW0:04X}",
            "LIVESV": f"${BG3_CHR + 8 * t['t3_lives']:04X}",
            "HTPL": f"${heads:06X}", "NCH": str(len(PORTRAITS)), "HREC": str(HEAD_REC),
            "HCHR": ",".join(f"${(hrec_at + a) & 0xFFFF:04X},{n}" for a, n in zip(hrec_off, t["head_counts"])),
            "HEADV": f"${16 * T_HEAD:04X}",
            "ICONW": ",".join(f"${w:04X}" for w in t["icon_words"]),
            "SEATW": ",".join(f"${w:04X}" for w in words),
            "ROWA": ",".join(f"${a:04X}" for a in t["seat_rowa"]),
            "BLOCKW": ",".join(f"${w:04X}" for w in block),
            "BLKOFF": ",".join(f"blockw+{2 * a}" for a in blkoff),
            "BLKV": ",".join(f"${BG3_MAP + 32 * BG3_ROW0 + c:04X}" for c, _ in BG3_COLS),
            "BLKN": ",".join(f"{2 * n}" for _, n in BG3_COLS),
            "DYNV": f"${16 * T_DYN:04X}",
            "BG3MN": str(64 * BG3_ROWS), "BG3ROWS": str(BG3_ROWS), "VOFS2": f"${VOFS2:04X}", "VOFS3": f"${VOFS3:04X}", "VOFS1": f"${VOFS1:04X}",
            "HOFS1": f"${HOFS1:04X}", "WINL": str(WIN[0]), "WINR": str(WIN[1]),
            "PURPLE": f"${PURPLE:04X}", "PURPLEA": f"${0x7E2910 + 2 * PURPLE_ENTRY:06X}",
            "I_NORMAL": str(I_NORMAL), "I_REMOTE": str(I_REMOTE), "I_PIERCE": str(I_PIERCE), "I_MAGNET": str(I_MAGNET),
            "I_SEARCH": str(I_SEARCH), "I_KICK": str(I_KICK), "I_BPASS": str(I_BPASS), "I_PUNCH": str(I_PUNCH),
            "I_GLOVE": str(I_GLOVE), "I_HEART": str(I_HEART), "I_WPASS": str(I_WPASS), "I_FULL": str(I_FULL)}
    runs, syms = asar.assemble_into(rb.d, ASM, defs)
    start, end = reg.cursor, syms["end"]
    out = bytearray(rb.d)
    for a, d in runs:
        if not (off(start) <= a and a + len(d) <= off(end)):
            raise BuildError(f"hud.asm wrote outside its section at file offset {a:06X}")
        out[a:a + len(d)] = d
    rb.alloc(region, bytes(out[off(start):off(end)]), "SB6 HUD (asm/hud.asm)")

    def jsl(a):
        return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16])
    # HUD task ($C5:054A): every stage starts with the SB6 HUD off (Battle, the attract demo keep SB5's)
    rb.patch(0xC5054A, bytes.fromhex("AD 1A 1D 29 08 F0 01 6B"), jsl(syms["hud_begin"]) + bytes.fromhex("29 08 D0 F7"),
             "HUD: task start turns the SB6 HUD off (JSL hud_begin; AND #8; BNE $0549 RTL)")
    rb.patch(0xC505C6, bytes.fromhex("AD 1A 1D 89 01 F0 08 A9 49 22 0F 18 C0 80 06 A9 4A 22 0F 18 C0"),
             jsl(syms["hud_load"]) + bytes([0x80, 0x0F]) + b"\xEA" * 15,
             "HUD: Normal Game draws the SB6 HUD instead of loading SB5's HUD tiles (JSL hud_load)")
    rb.patch(0xC506CD, bytes.fromhex("AD 69 00 49 10 89 1F D0 63"), jsl(syms["hud_tick"]) + bytes([0xD0, 0x66]) +
             b"\xEA" * 3, "HUD: SB6 HUD update instead of the score redraw (JSL hud_tick; BNE $0739)")
    rb.patch(0xC0F0A7, bytes.fromhex("A9 FC A2 FF A0 01 85 12 86 12 64 10 84 10"),
             jsl(syms["hud_irq"]) + bytes([0x80, 0x08]) + b"\xEA" * 8, "HUD: stage IRQ line 0 scrolls (JSL hud_irq)")
    rb.patch(0xC0F140, bytes.fromhex("A9 FC A2 FF A0 01 85 12 86 12 64 10 84 10 85 0E 64 0E"),
             jsl(syms["hud_irq_b"]) + bytes([0x80, 0x0C]) + b"\xEA" * 12,
             "HUD: stage IRQ (Battle) line 0 scrolls (JSL hud_irq_b)")
    rb.patch(0xC5042E, bytes.fromhex("AF AD 34 7E"), jsl(syms["time_gate"]),
             "HUD: the Normal Game's clock stops (JSL time_gate)")
    # line 21 (Normal Game IRQ): BG1 back to the field, window 2 for the lives tab's backdrop
    rb.patch(0xC0F0F1, bytes.fromhex("A9 17 8D 09 42"), jsl(syms["hud_l21"]) + bytes([0xEA]),
             "HUD: stage IRQ line 21, after SB5's writes: BG1 back, the lives tab's window (JSL hud_l21; VTIME 23)")
    # line 23's handler chains a line-30 IRQ (JMP ($006D) from the IRQ entry in bank $80: ROM above $8000) that closes the window
    stub = rb.regions["c0_hi"].cursor
    irq30 = stub + 16
    code = bytes.fromhex("C2 20 A9") + bytes([irq30 & 0xFF, irq30 >> 8 & 0xFF]) + bytes.fromhex(
        "8D 6D 00 E2 20 A9 1F 8D 09 42 60")
    # line 31: window settings (W12SEL, TMW, TSW, WBGLOG, WOBJSEL, WOBJLOG) back from their shadows, next IRQ = line 0 ($C0:F08D);
    # no H-blank wait (HUD line 30's x 118-137 is the tab's bottom line, opaque BG3 over the whole window: a
    # change mid-line shows nothing, and the wait cost 1-3 a frame now and then)
    code += bytes.fromhex("20 AC F1 AD 06 03 85 23 AD 11 03 85 2E AD 12 03 85 2F AD 0D 03 85 2A AD 08 03 85 25 AD 0E 03 85 2B 9C 09 42 C2 20 A9 8D F0 8D 6D 00 E2 20 60")
    if rb.alloc("c0_hi", code, "HUD: stage IRQ line 23 -> line 31 (window 2 closed), then line 0") != stub:
        raise BuildError("hud: c0 stub moved")
    rb.patch(0xC0F07F, bytes.fromhex("C2 20 A9 8D F0 8D 6D 00 E2 20 9C 09 42 60"),
             bytes([0x4C, stub & 0xFF, stub >> 8 & 0xFF]) + b"\xEA" * 11,
             "HUD: stage IRQ line 23 chains a line-30 IRQ (window 2 back)")
    if preview:
        recs = [record(1, 2, 0xE0, 1, 0, 0xE0, 0), record(1, 8, 0x140, 5, 0x0B, 0x80, 1),
                record(1, 4, 0x100, 3, 0x24, 0x40, 0), record(0, 0, 0, 0, 0, 0, 0, 0x40)]
        picks = bytes([0, 1, 2, 4, 6, 1, 0, 0, 0, 3, 10, 0, 0, 0, 0, 0])
        pic, own = render(t, p1, recs, 6, picks=picks)
        img = np.zeros(pic.shape, np.uint8)
        img[:] = (pic * 255 // 31).astype(np.uint8)
        img[~own] = (60, 60, 60)
        Image.fromarray(img).resize((256 * 4, pic.shape[0] * 4), Image.NEAREST).save(preview)
    return {"syms": syms, "bg3_tiles": len(t["bg3_tiles"]) // 16, "heads": sum(t["head_counts"])}
