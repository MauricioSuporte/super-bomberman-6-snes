"""Character + color selection in the Normal Game (asm/picker.asm).

The Normal Game calls Battle's CHARACTER SELECT screen ($C6:89CF) for its
background (checker, frame and title) and the fades, but once its setup is
done the hack takes the screen over and runs a picker laid out like the SB6
fan game's (Unity scene SkinSelect, BomberSkinSelectMenu.cs):

* a grid of 32x32 portraits (assets/picker/CharacterSelectPortrait.png: one
  column per character, row 1 at rest, row 2 under the cursor) drawn on BG1,
  with the frame of the cursor sheet; the portrait under the cursor shows
  the color the player picked with L / R (SkinSelectPallete_26.png, or
  SkinSelectPallete_44.png for the characters with 44 color columns: column 0
  holds the key colors painted in the portraits, column n + 1 their colors
  in color n);
* one player at a time (the lowest seat not confirmed yet); B gives the
  previous player his choice back (on player 1: back to the file list);
* the cursor of the Unity scene (corners that breathe, "L / R" above and the
  player number below), in the color of the character's color
  (row 0 of the 26-column picture, row 8 of the 44-column one);
* the row of players at the top (the Unity per-player cursors): the active
  player's character walks down (animation 2), dimmed; a confirmed one plays
  its animation $20 once and stays on its last pose;
* a sound (Unity Sounds/Skin/change.wav, title_music.PALETTE_SFX) when the
  color changes.
"""
import os
import re
import struct

import numpy as np
from PIL import Image

from .. import asar
from . import bombers, title_music
from ..rombuild import BuildError
from ..romlib import off

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
ASM = os.path.join(ROOT, "asm", "picker.asm")
ART = os.path.join(ROOT, "assets", "picker")
OFF_SEAT = 0                 # $6269+seat of the seats that do not play (1 = human)

# ---- screen layout (SNES pixels / tiles) ------------------------------------
GRID_COLS = 5
CELL_TX = (4, 9, 14, 19, 24)          # tile column of each grid column (32 px portraits, 8 px apart)
CELL_TY = (13, 19)                    # tile row of each grid row
MAP_ROWS = range(5, 25)               # BG1 rows inside the frame (the title and frame stay SB5's)
MAP_COLS = range(2, 30)
EMPTY = 0x211C                        # SB5's empty BG1 tile, priority set
PORTRAIT_TILE = 0x160                 # BG tiles $160+ (VRAM $1600-$1F1F: the menu's archive $93, sent again on the way back)
STATIC_PALS = (3, 4, 7)               # BG palettes of the portraits at rest
HOVER_PALS = (5, 6)                   # BG palettes of the portrait under the cursor
ENTRY_W, ENTRY_GAP, ENTRY_Y = 32, 12, 42   # player row: Unity per-player cursors (32x43)
FEET_DY = 35                          # feet of the character below the cursor's top
# OBJ: tiles 0-11 cursor glyphs, 16+ the player cursors (3 brightness steps
# each), $100+ the characters of the row (two 32-tile halves per seat)
GLYPHS = ("TL", "TR", "BL", "BR", "L", "SL", "R", "1", "2", "3", "4", "P")
BRACKET_TILE = 16
CURSOR_PAL = 4                        # OBJ palette of the cursor and the player cursors
POSE_BLOCKS = 8                       # 16x16 sprites per pose of the player row
# brightness of the player cursors (Unity alpha: confirmed 1, active 0.45, waiting 0.25)
LEVELS = (1.0, 0.45, 0.25)
SHADE = (0, 24, 32)                   # what shows through them (the darkened checker), 8-bit RGB
WALK, WIN = 0x02, 0x20
# The player row counts video frames. In a stage a walking bomber's timer
# drops 2 per frame (8 -> 4 frames per pose, measured in 1-1); standing (the
# victory at the portal) it drops 1 per frame.
ROW_DIV = {WALK: 2, WIN: 1}
# characters whose column of CharacterSelectPortrait.png is not drawn yet:
# the grid shows their front stand pose (bombers.FRONT) in their own colors
POSE_PORTRAITS = {7}


def _bgr(rgb):
    r, g, b = (int(v) for v in rgb[:3])
    return r >> 3 | (g >> 3) << 5 | (b >> 3) << 10


def _mix(rgb, alpha):
    return tuple(round(alpha * c + (1 - alpha) * s) for c, s in zip(rgb[:3], SHADE))


def _tile4(px):
    """8x8 color indices -> 32 bytes of 4bpp."""
    t = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = int(px[y][x])
            for plane in range(4):
                if v >> plane & 1:
                    t[(16 if plane >= 2 else 0) + 2 * y + (plane & 1)] |= 0x80 >> x
    return bytes(t)


def _rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.int32)


# ---- portraits ----------------------------------------------------------------
def _key_tables():
    """{columns: (key colors, [(skin colors), ...])} of the two palette pictures."""
    out = {}
    for name in ("SkinSelectPallete_26.png", "SkinSelectPallete_44.png"):
        a = _rgba(os.path.join(ART, name))
        keys = [tuple(a[y, 0, :3]) for y in range(a.shape[0])]
        out[a.shape[1]] = (keys, a)
    return out


def _portraits(n_chars):
    a = _rgba(os.path.join(ART, "CharacterSelectPortrait.png"))
    if a.shape[0] != 64 or a.shape[1] % 32:
        raise BuildError("CharacterSelectPortrait.png: 32x32 portraits, row 1 at rest, row 2 under the cursor")
    count = min(a.shape[1] // 32, n_chars)
    frame = _rgba(os.path.join(ART, "SkinSelectCursor.png"))[24:56, 0:32]
    out = []
    for c in range(count):
        pair = []
        for row in range(2):
            img = a[32 * row:32 * row + 32, 32 * c:32 * c + 32].copy()
            on = frame[..., 3] >= 128
            img[on] = frame[on]
            pair.append(img)
        out.append(pair)
    return out


def _pose_portrait(ch, pal_path):
    """Stand-in portrait of a character without a column in
    CharacterSelectPortrait.png: its front stand pose (animation $47) at 1x
    in the middle of the 32x32 cell, in its in-game colors. Returns the two
    RGBA pictures (at rest, under the cursor: the same one) and the color
    table in the palette pictures' format: rows 1-15 = palette entries
    (column 0 a key color nobody paints, column s + 1 = color s), row 0 =
    the cursor tint (row 7 of char<n>_pallete.png: the suit, as Unity's
    BomberPortraitSelectionCursor does for CossackBomber)."""
    cell, pals = ch["front"], ch["palettes"]
    ys, xs = np.nonzero(cell)
    if not len(xs) or xs.max() - xs.min() >= 32 or ys.max() - ys.min() >= 32:
        raise BuildError(f"picker: char{ch['char']}'s pose $47 does not fit a 32x32 portrait")
    x0 = (int(xs.min()) + int(xs.max()) + 1) // 2 - 16
    y0 = (int(ys.min()) + int(ys.max()) + 1) // 2 - 16
    tab = np.zeros((16, len(pals) + 1, 4), dtype=np.int32)
    tab[..., 3] = 255
    for i in range(16):
        tab[i, 0, :3] = (1, 2, 3 + i)
    for s_, pal in enumerate(pals):
        for i, rgb in enumerate(pal[:15]):
            tab[i + 1, s_ + 1, :3] = rgb
    tint = _rgba(pal_path)
    for s_ in range(len(pals)):
        tab[0, s_ + 1, :3] = tint[7, min(s_ + 1, tint.shape[1] - 1), :3]
    img = np.zeros((32, 32, 4), dtype=np.int32)
    for y in range(32):
        for x in range(32):
            sy, sx = y0 + y, x0 + x
            v = int(cell[sy, sx]) if 0 <= sy < 64 and 0 <= sx < 64 else 0
            if v:
                img[y, x] = tab[v, 0]
    frame = _rgba(os.path.join(ART, "SkinSelectCursor.png"))[24:56, 0:32]
    on = frame[..., 3] >= 128
    img[on] = frame[on]
    keys = [tuple(int(v) for v in tab[r, 0, :3]) for r in range(16)]
    return [img, img.copy()], (keys, tab)


def _fit_rest(rest, loose):
    """The portraits at rest share STATIC_PALS: while they do not fit, the
    least used color of a stand-in portrait (`loose`) that no painted
    portrait has takes its closest color. Returns (grids, [(char, text)])."""
    rest = [[row[:] for row in g] for g in rest]
    merged = []
    while True:
        sets = [s for grid in rest for s in _tile_sets(grid)]
        try:
            _partition(sets, len(STATIC_PALS), "the portraits at rest")
            return rest, merged
        except BuildError:
            pass
        fixed = {v for c, g in enumerate(rest) if c not in loose for row in g for v in row} - {None}
        best = None
        for c in loose:
            count = {}
            for row in rest[c]:
                for v in row:
                    if v is not None and v not in fixed:
                        count[v] = count.get(v, 0) + 1
            for v, n in count.items():
                others = ({w for row in rest[c] for w in row} | fixed) - {None, v}
                near = min(others, key=lambda w: sum((a - b) ** 2 for a, b in zip(v, w)))
                cost = n * sum((a - b) ** 2 for a, b in zip(v, near))
                if best is None or cost < best[0]:
                    best = (cost, c, v, near)
        if best is None:
            raise BuildError("picker: the portraits at rest need more than "
                             f"{len(STATIC_PALS)} palettes of 15 colors")
        _, c, v, near = best
        rest[c] = [[near if w == v else w for w in row] for row in rest[c]]
        merged.append((c, "%02X%02X%02X -> %02X%02X%02X" % (v + near)))


def _logical(img, keys):
    """32x32 RGBA -> grid of logical colors: None (transparent), ('k', key row) or ('f', rgb)."""
    out = []
    for y in range(32):
        row = []
        for x in range(32):
            p = img[y, x]
            if p[3] < 128:
                row.append(None)
                continue
            rgb = tuple(int(v) for v in p[:3])
            row.append(("k", keys.index(rgb)) if rgb in keys else ("f", rgb))
        out.append(row)
    return out


def _tile_sets(grid):
    """16 sets of logical colors, tiles in row-major order."""
    return [{grid[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)} - {None}
            for ty in range(4) for tx in range(4)]


def _partition(sets, slots, what):
    """Assigns every set to one of `slots` palettes of 15 colors. Returns
    (palette of each set, [colors of each palette]). Greedy (fewest new
    colors), largest sets first, then shuffled orders until one fits."""
    import random
    rnd = random.Random(1)
    order = sorted(range(len(sets)), key=lambda i: -len(sets[i]))
    for attempt in range(400):
        pals, pick = [set() for _ in range(slots)], [0] * len(sets)
        for i in order:
            best = None
            for k, p in enumerate(pals):
                new = len(sets[i] - p)
                if len(p) + new <= 15 and (best is None or new < best[0]):
                    best = (new, k)
            if best is None:
                break
            pick[i] = best[1]
            pals[best[1]] |= sets[i]
        else:
            return pick, [sorted(p, key=repr) for p in pals]
        order = order[:]
        rnd.shuffle(order)
    raise BuildError(f"picker: {what} need more than {slots} palettes of 15 colors")


def _encode(grid, sets, pick, pals):
    """Tiles (512 bytes) of a portrait with its tiles' palettes."""
    out = bytearray()
    for t in range(16):
        ty, tx = divmod(t, 4)
        pal = pals[pick[t]]
        px = [[0 if grid[ty * 8 + y][tx * 8 + x] is None else pal.index(grid[ty * 8 + y][tx * 8 + x]) + 1
               for x in range(8)] for y in range(8)]
        out += _tile4(px)
    return bytes(out)


def _resolve(color, skin_column, table):
    """Logical color -> RGB in a skin (column of the palette picture; an empty entry is the key)."""
    if color[0] == "f":
        return color[1]
    keys, a = table
    p = a[color[1], skin_column]
    return tuple(int(v) for v in (p[:3] if p[3] >= 128 else a[color[1], 0, :3]))


def _cell_words(c):
    """VRAM word address of the top-left map entry of cell c."""
    return 0x3000 + 32 * CELL_TY[c // GRID_COLS] + CELL_TX[c % GRID_COLS]


def _cell_center(c):
    return 8 * CELL_TX[c % GRID_COLS] + 16, 8 * CELL_TY[c // GRID_COLS] + 16


# ---- OBJ art ------------------------------------------------------------------
def _glyph_tiles():
    """The cursor pieces of SkinSelectCursor.png (yellow = the cursor color
    index 2, black = 1), "/" drawn in place of the "+"."""
    a = _rgba(os.path.join(ART, "SkinSelectCursor.png"))
    at = dict(TL=(24, 0), TR=(32, 0), BL=(24, 8), BR=(32, 8), L=(8, 16), R=(16, 16), P=(0, 16),
              **{str(n): ((n - 1) % 3 * 8, (n - 1) // 3 * 8) for n in range(1, 5)})
    out = bytearray()
    for g in GLYPHS:
        if g == "SL":
            px = [[0] * 8 for _ in range(8)]
            ink = [(5, 3), (4, 4), (3, 5), (2, 6)]
            for x, y in ink:
                for sx, sy in ((x - 1, y), (x, y + 1)):
                    if (sx, sy) not in ink:
                        px[sy][sx] = 1
            for x, y in ink:
                px[y][x] = 2
        else:
            x0, y0 = at[g]
            cell = a[y0:y0 + 8, x0:x0 + 8]
            px = [[0 if p[3] < 128 else (1 if p[:3].sum() < 96 else 2) for p in row] for row in cell]
        out += _tile4(px)
    return bytes(out)


def _brackets():
    """Player cursors P1-P4 (Unity Sprites/Cursor): their colors, sprite
    layout [(dx, dy)] and tiles for each player and brightness step (index
    3 + p + 4 * step for the color, 1 / 15 for the outline)."""
    imgs = [_rgba(os.path.join(ART, f"P{p} Cursor.png")) for p in range(1, 5)]
    h = max(a.shape[0] for a in imgs)
    cells = sorted({(tx, ty) for a in imgs for ty in range(-(-h // 8)) for tx in range(4)
                    if (a[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8, 3] >= 128).any()}, key=lambda t: (t[1], t[0]))
    colors, tiles = [], bytearray()
    for p, a in enumerate(imgs):
        opaque = a[..., 3] >= 128
        rgb = a[..., :3]
        bright = rgb.sum(-1) > 96
        main = tuple(int(v) for v in np.median(rgb[opaque & bright], axis=0))
        colors.append(main)
        for step in range(len(LEVELS)):
            for tx, ty in cells:
                px = [[0] * 8 for _ in range(8)]
                for y in range(8):
                    for x in range(8):
                        yy, xx = ty * 8 + y, tx * 8 + x
                        if yy < a.shape[0] and opaque[yy, xx]:
                            px[y][x] = 3 + p + 4 * step if bright[yy, xx] else (1 if step == 0 else 15)
                tiles += _tile4(px)
    return colors, [(8 * tx, 8 * ty) for tx, ty in cells], bytes(tiles)


def _pose(cell, name):
    """A pose (64x64 indices, feet at (32, 38)) as up to POSE_BLOCKS 16x16
    sprites: (n, [(dx, dy)], top tile row, bottom tile row)."""
    ys, xs = np.nonzero(cell)
    if not len(xs):
        return 0, [], b"", b""
    best = None
    for oy in range(16):
        for ox in range(16):
            x0, y0 = xs.min() - ox, ys.min() - oy
            blocks = sorted({((x - x0) // 16, (y - y0) // 16) for x, y in zip(xs, ys)}, key=lambda b: (b[1], b[0]))
            if best is None or len(blocks) < len(best[0]):
                best = (blocks, x0, y0)
    blocks, x0, y0 = best
    if len(blocks) > POSE_BLOCKS:
        raise BuildError(f"picker: {name} needs {len(blocks)} sprites of 16x16, the row holds {POSE_BLOCKS}")
    top, bottom, offs = bytearray(), bytearray(), []
    pad = np.zeros((96, 96), dtype=np.int32)
    pad[16:80, 16:80] = cell
    for bx, by in blocks:
        x, y = x0 + 16 * bx, y0 + 16 * by
        offs.append((x - 32, y - 38))
        blk = pad[y + 16:y + 32, x + 16:x + 32]
        for row, half in ((top, 0), (bottom, 8)):
            for tx in range(2):
                row += _tile4(blk[half:half + 8, 8 * tx:8 * tx + 8])
    return len(blocks), offs, bytes(top), bytes(bottom)


def _preview_poses(poses, seqs, path):
    """Debug: the poses as the SNES shows them (env SB6_PICKER_POSES=file.png)."""
    from PIL import Image
    def untile(data, i):
        t = data[32 * i:32 * i + 32]
        px = np.zeros((8, 8), dtype=np.int32)
        for y in range(8):
            for x in range(8):
                s_ = 7 - x
                px[y, x] = (t[2 * y] >> s_ & 1) | (t[2 * y + 1] >> s_ & 1) << 1 | (t[16 + 2 * y] >> s_ & 1) << 2 | (t[17 + 2 * y] >> s_ & 1) << 3
        return px
    im = Image.new("L", (64 * 16, 64 * (len(poses) // 16 + 1)))
    for i, (nb, offs, top, bottom) in enumerate(poses):
        canvas = np.zeros((64, 64), dtype=np.int32)
        for k, (dx, dy) in enumerate(offs):
            for r, row in enumerate((top, bottom)):
                for tx in range(2):
                    y, x = 38 + dy + 8 * r, 32 + dx + 8 * tx
                    canvas[y:y + 8, x:x + 8] = np.maximum(canvas[y:y + 8, x:x + 8], untile(row, 2 * k + tx) * 16)
        im.paste(Image.fromarray(canvas.astype(np.uint8)), (64 * (i % 16), 64 * (i // 16)))
    im.save(path)
    for k, v in seqs.items():
        print("picker poses", k, v)


# ---- build --------------------------------------------------------------------
class Blob:
    """Data assembled in Python: labelled parts of one allocation."""

    def __init__(self):
        self.data, self.labels = bytearray(), {}

    def add(self, label, data):
        self.labels[label] = len(self.data)
        self.data += data
        return self.labels[label]


# ---- the Normal Game menu (mode 3) opens with the character selection ----------
# Task 8 ($C7:0BB9) runs the menu's states from the table at $C7:0BCC ($1037: 0 back to the title, 1 NORMAL
# MODE menu $C7:0C1D, 2 Continue files, 3 Erase, 4 start, 5 New Game files; each state leaves $1037 = next - 1,
# then $C7:0C01 adds 1). States 0 and 1 are ours, in free_c7_options: SB5's state 0 / 1 scripts ($C7:0BD8 /
# $0BE0) jump to them (FF A6 takes a target below the table as the next bank's, `44` reaches +-32 KB):
#  1: [PICKREQ] != 0 -> the picker first (s_pick); left with B -> state 0; else B on the menu comes back to it
#  0: after the picker ([PICKED] = 1) -> the picker again with the last choices; else the title at once
#     (SB5 slept 30 frames first)
PICKREQ, PICKED, PICKB = 0x0197, 0x0198, 0x0199     # WRAM (docs/FREE_SPACE.md)
STATE0, STATE1, STATE_NEXT = 0xC70BD8, 0xC70BE0, 0xC70C01
NORMAL_MENU = 0xC70C1D


def _st(v, a):
    return bytes([0x5B, v, 0x5F, a & 0xFF, a >> 8])


def _test(a, v, n):
    """`5D a 86 v 49 n`: the next n bytes run when [a] == v."""
    return bytes([0x5D, a & 0xFF, a >> 8, 0x86, v, 0x49, n])


def _jump(at, to):
    """`44 rel16` at `at` (bank $C7) to `to`: relative to the end of the op."""
    r = (to - (at + 3)) & 0xFFFF
    return bytes([0x44, r & 0xFF, r >> 8])


def _flow_scripts(base, s_pick, menu_gfx):
    """(state 1 script, state 0 script), state 1 first at `base` (bank $C7)."""
    nxt = STATE_NEXT & 0xFFFF
    b16 = base & 0xFFFF
    s1 = bytearray(_test(PICKREQ, 0, 3))
    hole = len(s1)
    s1 += bytes(3)                                   # no picker: jump to the menu (below)
    s1 += _st(0, PICKED) + bytes([0x24]) + s_pick.to_bytes(3, "little") + _st(0, PICKREQ)
    left = _st(0xFF, 0x1037)                         # left with B: state 0, the title
    s1 += _test(PICKB, 1, len(left) + 3) + left
    s1 += _jump(b16 + len(s1), nxt)
    s1 += bytes([0x24]) + menu_gfx.to_bytes(3, "little")   # the menu's graphics (the picker's are in VRAM)
    s1 += _st(1, PICKED)                             # B on the menu comes back to the picker
    menu = len(s1)
    s1 += bytes([0x24]) + NORMAL_MENU.to_bytes(3, "little")
    s1 += _jump(b16 + len(s1), nxt)
    s1[hole:hole + 3] = _jump(b16 + hole, b16 + menu)
    at0 = b16 + len(s1)
    again = _st(0, PICKED) + _st(2, PICKREQ) + _st(0, 0x1037) + _st(0x80, 0x0300)   # dark at once
    s0 = bytearray(_test(PICKED, 1, len(again) + 3) + again)
    s0 += _jump(at0 + len(s0), nxt)
    s0 += bytes.fromhex("0F 02 00")                  # mode 2: the title
    return bytes(s1), bytes(s0)


def flow(rb, s_pick, menu_gfx):
    # (the mode's own graphics stay: the picker draws its checker and heads with the menu's tiles)
    # Task 7's fade-out before the states ($C7:0BB1 `FD 08`, then $104A = 0): the screen is black while the
    # picker comes first (the mode's own fade-in shows nothing yet), so it goes dark at once instead.
    dark = _st(0x80, 0x0300)
    tail = (_test(PICKREQ, 0, 2) + bytes.fromhex("FD 08") + _test(PICKREQ, 0, 0)[:-2]
            + bytes([0x47, len(dark)]) + dark + _st(0, 0x104A) + b"\x00")
    a7 = rb.alloc("free_c7_options", tail, "Normal Game menu: task 7's fade-out, dark at once before the picker")
    rb.patch(0xC70BB1, bytes.fromhex("FD 08 5B 00 5F 4A 10 00"), bytes([0x24]) + a7.to_bytes(3, "little") + bytes(4),
             "Normal Game menu: task 7's fade-out -> skipped when the picker comes first")
    base = rb.regions["free_c7_options"].cursor
    s1, s0 = _flow_scripts(base, s_pick, menu_gfx)
    a1 = rb.alloc("free_c7_options", s1, "Normal Game menu state 1: character selection first, then NORMAL MODE")
    a0 = rb.alloc("free_c7_options", s0, "Normal Game menu state 0: back to the character selection or the title")
    if a1 != base or a0 != base + len(s1):
        raise BuildError("picker flow scripts moved")
    rb.patch(STATE0, bytes.fromhex("FD 0E 1E 00 00 0F 02 00"), _jump(STATE0 & 0xFFFF, a0 & 0xFFFF) + bytes(5),
             "Normal Game menu state 0 -> back to the character selection or the title at once")
    rb.patch(STATE1, bytes.fromhex("24 1D 0C C7 45 1B"), _jump(STATE1 & 0xFFFF, a1 & 0xFFFF) + bytes(3),
             "Normal Game menu state 1 -> character selection first")
    menu_speed(rb)


# The NORMAL MODE menu's answers (New Game / Continue / Erase File, a file): SB5's accept ($C7:124C, called after
# SFX 4 by every choice of the menu and its file lists) slept 64 frames; now 1: A -> the next list taking input in
# ~47 frames (was ~111). The rest is SB5's: leaving the menu, drawing the list and the hand cursor sliding in
# ($C7:123D: `4F 46` pushes the hand's sprite (animation $46, not a length: another value draws a wrong tile),
# `4A 3A` creates it and slides it in, 19 frames; `4A 3C` only moves an existing one).
ACCEPT_SLEEP = 0xC71257      # `FD 0E 40 00 00` in $C7:124C
ACCEPT_FRAMES = 1


def menu_speed(rb):
    rb.patch(ACCEPT_SLEEP, bytes.fromhex("FD 0E 40 00 00"), bytes([0xFD, 0x0E, ACCEPT_FRAMES, 0, 0]),
             "Normal menu: accept wait 64 -> 1 frame (New Game / Continue / Erase File, file choices)")


def apply(rb, base_rom, bomber, title=None, wmap_nmi=0, wmap_op=0, w1_op=0, pause_nmi=0, music_track=0):
    """`bomber`: result of features/bombers.py. Returns the asm symbols + `bomber_colors`."""
    own = bool(bomber and bomber.get("paltab"))
    if not own or not bomber.get("pick_anims"):
        raise BuildError("picker: needs bomber_sb6.png + BombermanPallete.png (SB6 art and palettes)")
    bomber_colors = bomber["palcount"]
    chars = {0: bomber, **{ch["char"]: ch for ch in bomber.get("chars", [])}}
    own_id = bomber["own_id"]
    chpal, chcol = [own_id] + [0] * 8, [bomber_colors] + [6] * 8
    for c, ch in chars.items():
        if 1 <= c <= 8:
            chpal[c], chcol[c] = own_id + ch["pal0"], ch["colors"]
            if chpal[c] > 0xFF:
                raise BuildError(f"picker: char{c}'s first palette id ${chpal[c]:X} is past $FF")

    # characters of the grid: the portrait picture's columns, each must be inserted
    portraits = _portraits(10)
    # characters after the painted portraits: their front pose until the artist draws one
    own_tab = {}
    while len(portraits) < 10 and len(portraits) in chars and len(portraits) in POSE_PORTRAITS:
        c = len(portraits)
        pair, own_tab[c] = _pose_portrait(chars[c], os.path.join(ROOT, "assets", "bombers", f"char{c}_pallete.png"))
        portraits.append(pair)
    n = len(portraits)
    missing = [c for c in range(n) if c not in chars]
    if missing:
        raise BuildError(f"picker: characters {missing} have a portrait but no sheet")
    if n > GRID_COLS * len(CELL_TY) or PORTRAIT_TILE + 16 * n > 0x1F2:
        raise BuildError(f"picker: {n} portraits do not fit the grid / VRAM")
    keytabs = _key_tables()

    def table_of(c):
        """The palette picture of character c's portraits (26 or 44 columns, as its color picture)."""
        if c in own_tab:
            return own_tab[c], own_tab[c][1].shape[1]
        cols = 44 if chcol[c] > 25 else 26
        return keytabs[cols], cols

    blob = Blob()

    # portraits at rest: default color (column 1), shared palettes
    rest = []
    for c in range(n):
        tab, _ = table_of(c)
        g = _logical(portraits[c][0], tab[0])
        rgbgrid = [[None if v is None else _resolve(v, 1, tab) for v in row] for row in g]
        rest.append(rgbgrid)
    rest, merged = _fit_rest(rest, sorted(own_tab))
    for c, text in merged:
        print(f"picker: char{c}'s stand-in portrait at rest: {text}")
    rest_sets = [s for grid in rest for s in _tile_sets(grid)]
    pick, pals = _partition(rest_sets, len(STATIC_PALS), "the portraits at rest")
    rest_tiles = bytearray()
    rest_map = []
    for c in range(n):
        p = pick[16 * c:16 * c + 16]
        rest_tiles += _encode(rest[c], _tile_sets(rest[c]), p, pals)
        rest_map.append([PORTRAIT_TILE + 16 * c + t | STATIC_PALS[p[t]] << 10 | 0x2000 for t in range(16)])
    static_cg = [(16 * STATIC_PALS[k], [_bgr(rgb) for rgb in pal]) for k, pal in enumerate(pals) if pal]

    # portraits under the cursor: two palettes per character, colors per skin
    hov_tiles, hov_map, hov_cols = bytearray(), [], []
    for c in range(n):
        tab, cols = table_of(c)
        g = _logical(portraits[c][1], tab[0])
        sets = _tile_sets(g)
        p, hp = _partition(sets, len(HOVER_PALS), f"portrait {c} under the cursor")
        hov_tiles += _encode(g, sets, p, hp)
        hov_map.append([PORTRAIT_TILE + 16 * c + t | HOVER_PALS[p[t]] << 10 | 0x2000 for t in range(16)])
        colors = bytearray()
        for skin in range(chcol[c]):
            col = skin + 1 if skin + 1 < cols else 0
            for pal in hp:
                words = [_bgr(_resolve(v, col, tab)) for v in pal] + [0] * (15 - len(pal))
                colors += struct.pack("<15H", *words)
        hov_cols.append(bytes(colors))

    # the BG1 rows inside the frame: empty, the portraits at rest
    rows = [[EMPTY] * 32 for _ in range(32)]
    for c in range(n):
        tx, ty = CELL_TX[c % GRID_COLS], CELL_TY[c // GRID_COLS]
        for t in range(16):
            rows[ty + t // 4][tx + t % 4] = rest_map[c][t]
    bgmap = b"".join(struct.pack("<H", rows[r][x]) for r in MAP_ROWS for x in MAP_COLS)

    # cursor color of each character and skin (row 0 / row 8 of the palette picture)
    tints = []
    for c in range(n):
        (keys, a), cols = table_of(c)
        row = 8 if cols == 44 else 0
        words = []
        for skin in range(chcol[c]):
            col = skin + 1 if skin + 1 < cols else 0
            p = a[row, col] if a[row, col, 3] >= 128 else a[row, 0]
            words.append(_bgr(p))
        tints.append(struct.pack(f"<{len(words)}H", *words))

    # OBJ palette of the cursor and the player cursors
    bcolors, blayout, btiles = _brackets()
    if BRACKET_TILE + len(btiles) // 32 > 0x100:
        raise BuildError("picker: the player cursors take too many OBJ tiles")
    pal4 = [(0, 0, 0)] * 16
    pal4[1], pal4[2] = (0, 0, 0), (248, 248, 248)
    for step, alpha in enumerate(LEVELS):
        for p in range(4):
            pal4[3 + p + 4 * step] = _mix(bcolors[p], alpha)
    pal4[15] = _mix((0, 0, 0), 0.35)
    pal4_words = [_bgr(c) for c in pal4[1:]]
    shade = _bgr(SHADE)

    # poses of the player row: walk down and victory of each character
    poses, pose_index, seqs = [], {}, {}
    for c in range(n):
        for a in (WALK, WIN):
            seq = []
            for k, (cell, frames) in enumerate(chars[c]["pick_anims"][a]):
                if cell is None:
                    key = b""
                else:
                    key = cell.tobytes()
                if key not in pose_index:
                    pose_index[key] = len(poses)
                    poses.append(_pose(cell, f"char{c} animation {a:02X} pose {k + 1}") if cell is not None
                                 else (0, [], b"", b""))
                seq.append((pose_index[key], max(1, -(-frames // ROW_DIV[a]))))
            seqs[(c, a)] = seq
    if os.environ.get("SB6_PICKER_POSES"):
        _preview_poses(poses, seqs, os.environ["SB6_PICKER_POSES"])
    pose_addr = []
    for i, (nb, offs, top, bottom) in enumerate(poses):
        rec = bytes([nb]) + b"".join(struct.pack("<bb", dx, dy) for dx, dy in offs) + top + bottom
        pose_addr.append(rb.alloc(["obj_f8", "obj_f9", "stream_ef"], rec, f"picker: pose {i} of the player row"))

    # tables (one blob, one bank)
    blob.add("pk_bgmap", bgmap)
    blob.add("pk_rtiles", bytes(rest_tiles))
    blob.add("pk_htiles", bytes(hov_tiles))
    blob.add("pk_rmap", b"".join(struct.pack("<16H", *m) for m in rest_map))
    blob.add("pk_hmap", b"".join(struct.pack("<16H", *m) for m in hov_map))
    blob.add("pk_glyphs", _glyph_tiles())
    blob.add("pk_btiles", btiles)
    for c in range(n):
        blob.add(f"pk_hcol{c}", hov_cols[c])
        blob.add(f"pk_tint{c}", tints[c])
    blob.add("pk_hcolp", b"".join(struct.pack("<H", 0) for _ in range(n)))   # patched below
    blob.add("pk_tintp", b"".join(struct.pack("<H", 0) for _ in range(n)))
    blob.add("pk_static", b"".join(struct.pack("<H", 2 * idx) + struct.pack("<15H", *(w + [0] * (15 - len(w))))
                                   for idx, w in static_cg))
    blob.add("pk_pal4", struct.pack("<15H", *pal4_words))
    blob.add("pk_cellv", b"".join(struct.pack("<H", _cell_words(c)) for c in range(n)))
    blob.add("pk_cellx", bytes(_cell_center(c)[0] for c in range(n)))
    blob.add("pk_celly", bytes(_cell_center(c)[1] for c in range(n)))
    blob.add("pk_bxy", bytes(v for xy in blayout for v in xy))
    blob.add("pk_posep", b"".join(struct.pack("<I", a)[:3] for a in pose_addr))
    for (c, a), seq in seqs.items():
        blob.add(f"pk_seq{c}_{a:02X}", b"".join(struct.pack("<HB", i, f) for i, f in seq) + bytes(3))
    blob.add("pk_walkp", bytes(2 * n))
    blob.add("pk_winp", bytes(2 * n))
    # x of each player cursor for 1-4 players (centered, Unity spacing)
    blob.add("pk_entx", bytes(128 - ((ENTRY_W + ENTRY_GAP) * cnt - ENTRY_GAP) // 2 + (ENTRY_W + ENTRY_GAP) * e
                              for cnt in range(1, 5) for e in range(4)))
    # VRAM loads while the screen is hidden, one group per NMI:
    # [vram16, source offset16 in the blob, size16, last of the group]
    jobs = [(0x3000 + 32 * r + MAP_COLS[0], "pk_bgmap", 2 * len(MAP_COLS) * k, 2 * len(MAP_COLS), k == len(MAP_ROWS) - 1)
            for k, r in enumerate(MAP_ROWS)]
    for label, vram in (("pk_rtiles", 16 * PORTRAIT_TILE), ("pk_glyphs", 0x6000), ("pk_btiles", 0x6000 + 16 * BRACKET_TILE)):
        jobs.append((vram, label, 0, None, True))
    blob.add("pk_jobs", bytes(8 * 64))
    data = blob.data
    sizes = dict(pk_rtiles=len(rest_tiles), pk_glyphs=len(GLYPHS) * 32, pk_btiles=len(btiles))
    addr = rb.alloc(["obj_f9", "obj_f8", "stream_ef", "obj_f7", "obj_f6", "obj_f2", "obj_f1", "obj_f0", "title_fc"], bytes(data), "picker: portraits, palettes, cursor art, tables")
    lab = {k: addr + v for k, v in blob.labels.items()}
    recs = bytearray()
    for vram, label, start, size, last in jobs:
        size = sizes[label] if size is None else size
        while size > 0:
            part = min(size, 0x800)
            recs += struct.pack("<HHHBB", vram, (lab[label] + start) & 0xFFFF, part, 0, 1 if (last and part == size) or part == 0x800 else 0)
            vram, start, size = vram + part // 2, start + part, size - part
    recs += bytes([0xFF]) * 8
    if len(recs) > 8 * 64:
        raise BuildError("picker: too many VRAM jobs")
    data[blob.labels["pk_jobs"]:blob.labels["pk_jobs"] + len(recs)] = recs
    if len({a >> 16 for a in lab.values()}) != 1:
        raise BuildError("picker: tables across a bank")
    for c in range(n):
        struct.pack_into("<H", data, blob.labels["pk_hcolp"] + 2 * c, lab[f"pk_hcol{c}"] & 0xFFFF)
        struct.pack_into("<H", data, blob.labels["pk_tintp"] + 2 * c, lab[f"pk_tint{c}"] & 0xFFFF)
        struct.pack_into("<H", data, blob.labels["pk_walkp"] + 2 * c, lab[f"pk_seq{c}_{WALK:02X}"] & 0xFFFF)
        struct.pack_into("<H", data, blob.labels["pk_winp"] + 2 * c, lab[f"pk_seq{c}_{WIN:02X}"] & 0xFFFF)
    rb.d[off(addr):off(addr) + len(data)] = data

    defines = {k.upper(): f"${v:06X}" for k, v in lab.items() if not re.match(r"pk_(hcol|tint)\d+$|pk_seq", k)}
    reg = rb.regions["bulk"]
    defines.update({
        "E4": f"${reg.cursor:06X}", "OFFSEAT": f"${OFF_SEAT:02X}", "OWNID": f"${own_id:02X}",
        "SEATID": f"${bombers.SEAT_ID:02X}",
        "PALS": str(bombers.PAL_IDS), "PALTAB": f"${bomber['paltab']:06X}", "PALN": str(bomber["pal_total"]),
        "N": str(n), "GCOLS": str(GRID_COLS), "LASTROW": str((n - 1) // GRID_COLS * GRID_COLS), "PALSFX": f"${title_music.PALETTE_SFX:02X}",
        "NSTATIC": str(len(static_cg)), "BN": str(len(blayout)), "BTILE": str(BRACKET_TILE),
        "SHADE": f"${shade:04X}", "ENTW": str(ENTRY_W + ENTRY_GAP), "ENTY": str(ENTRY_Y), "FEET": str(FEET_DY),
        "PTILE": f"${PORTRAIT_TILE:03X}",
        "SCLR": f"${bomber.get('stream_clear', 0):06X}",
        "TITLE_OP": f"${(title or {}).get('title_op', 0):06X}",
        "TITLE_NMI": f"${(title or {}).get('title_nmi', 0):06X}",
        "WMAP_NMI": f"${wmap_nmi:06X}",
        "PAUSE_NMI": f"${pause_nmi:06X}",
        "WMAP_OP": f"${wmap_op:06X}",
        "W1_OP": f"${w1_op:06X}",
        "MUSIC_TRACK": f"${music_track:06X}",
        "CHPAL": ",".join(f"${v:02X}" for v in chpal), "CHCOL": ",".join(str(v) for v in chcol)})
    for c in range(n):
        if chcol[c] > 64:
            raise BuildError(f"picker: char{c} has {chcol[c]} colors")
    runs, syms = asar.assemble_into(rb.d, ASM, defines)
    start, end = reg.cursor, syms["end_e4"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"picker.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "picker: Normal Game character/color selection (asm/picker.asm)")

    def ptr(name):
        a = syms[name]
        return bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16])

    flow(rb, syms["s_pick"], syms["menu_gfx"])
    rb.patch(0xC2069B, bytes.fromhex("7C 46 C1"), ptr("pick_op"), "picker: script op FF 1A nn >= $F0 runs native code")
    rb.patch(0xC0F421, bytes.fromhex("22 E0 04 C0"), bytes([0x22]) + ptr("pick_nmi"), "picker: its VRAM transfers in the NMI")
    syms["bomber_colors"] = bomber_colors
    syms["grid"] = n
    syms["poses"] = len(poses)
    syms["data_bytes"] = len(data)
    return syms
