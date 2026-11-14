"""Player bomber sprites: SB5 format <-> an editable "pose sheet".

How SB5 draws a bomber (object type $10, see docs/ROM_MAP.md):

* animation `a` (1-$4D) -> script of `[mapping, frames]` pairs
  (`$C0:171D + 3*type` -> word table, bank of the table);
* mapping `m` -> `[count]` + count x `[x16, y16, tile16, attr]`
  (`$C0:16CC + 3*type`); attr bit 0 = 16x16, `$40`/`$80` flips, `$20` kept;
* character table `$80:BB66 + 2*char` -> per animation `[sheet, row]`:
  1 KB (32 tiles, 16 columns x 2 rows) of raw 4bpp at
  `sheet source + row * $200` is DMA'd to the bomber's VRAM page whenever the
  animation changes, so **all poses of one animation share 32 tiles**.

The pose sheet shows every pose (mapping) of every animation assembled in a
64x64 cell. `convert()` cuts edited cells back into 16x16/8x8 pieces, reuses
equal (or mirrored) pieces, and packs animations into 1 KB strips.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw

TYPE = 0x10              # Bomberman; character n is object type $10 + n ($80:BB44)
TYPE_TABLE = 0x80BB44
ANIMS = 0x4D             # animations 1..$4D are real; the table has 81 slots
CHAR_SLOTS = 81
# The sheet is a plain grid of 64x64 cells, like the Unity project's
# Bomberman.png, and a bomber sits at the same place inside a cell (feet
# centre at x = 32, soles on row 43), so frames can be copied cell to cell.
CELL_W, CELL_H = 64, 64
ORG_X, ORG_Y = 32, 38    # object position inside a cell
COLS = 7                 # pose columns of the Bomberman sheet; wider for characters with longer animations
GROUP_ROWS = 39          # animations per column group
HEADER_H = CELL_H        # first grid row: title and colors
STRIP_TILES = 32
KEY = (255, 0, 255)      # also read as transparent

# OBJ colors 1-8 of the white bomber (CGRAM 145-152 in a stage). Colors 9-15
# of the slot belong to the Louie being ridden, so bomber art cannot use them.
PALETTE = [(0x9C, 0xBD, 0xAC), (0xFF, 0xF6, 0xE6), (0xE6, 0x31, 0x39), (0xFF, 0x6A, 0x7B),
           (0xFF, 0xCD, 0x52), (0x5A, 0x31, 0xB4), (0x8B, 0x6A, 0xEE), (0x31, 0x18, 0x29)]

# Labels printed on the sheet. Groups of four animations are always in the
# order right, down, left, up; only the actions identified so far are named.
NAMES = {0x15: "festa? baixo", 0x16: "morte"}
for _first, _what in ((0x01, "andar"), (0x05, ""), (0x09, ""), (0x0D, ""), (0x11, ""), (0x17, ""), (0x1B, ""),
                      (0x23, ""), (0x27, ""), (0x2B, ""), (0x2F, "andar2"), (0x33, ""), (0x37, ""),
                      (0x3B, "veic."), (0x42, "veic.par"), (0x46, "parado"), (0x4A, "parado2")):
    for _i, _dir in enumerate(("direita", "baixo", "esquerda", "cima")):
        NAMES[_first + _i] = f"{_what} {_dir}".strip()


def _off(a):
    return a & 0x3FFFFF


def load_scripts(path, cols=COLS):
    """Animation scripts file -> {animation: (steps [(pose, frames)], loop index, hide at the end)}.

    One line per animation: `<animation hex> : <frames per pose> : <sequence>`.
    Sequence tokens: pose number (1 = first cell of the row), `N*F` = pose N
    for F frames, `-` = nothing drawn, `[` = the loop restarts here (default:
    from the beginning), `fim` = disappear and stop (must be the last token).
    """
    out = {}
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.split("#")[0].strip()
            if not line:
                continue
            try:
                a, frames, seq = (t.strip() for t in line.split(":"))
                a, frames = int(a, 16), int(frames)
                steps, loop, hide = [], 0, False
                for tok in seq.split():
                    if hide:
                        raise ValueError
                    if tok == "[":
                        loop = len(steps)
                    elif tok.lower() == "fim":
                        hide = True
                    else:
                        pose, _, f = tok.partition("*")
                        pose, f = 0 if pose == "-" else int(pose), int(f) if f else frames
                        if not (0 <= pose <= cols and 1 <= f <= 254) or (pose == 0 and tok[0] != "-"):
                            raise ValueError
                        steps.append((pose, f))
                if not (1 <= a <= ANIMS) or a in out or not any(p for p, _ in steps) or len(steps) > 100                         or loop >= len(steps):
                    raise ValueError
            except ValueError:
                raise ValueError(f"{path}, linha {ln}: nao entendi '{line}' "
                                 f"(formato: animacao : quadros : poses 1-{cols})")
            out[a] = (steps, loop, hide)
    return out


class BomberRom:
    def __init__(self, rom, scripts=None, char=0):
        """scripts (load_scripts): animations that play other poses/orders than the cartridge's.
        char: character 0-9; its object type is TYPE + char, with its own tables."""
        self.rom = rom
        self.char = char
        self.type = rom[_off(TYPE_TABLE) + char]
        self.anim_tab = self.rl(0xC0171D + 3 * self.type)
        self.map_tab = self.rl(0xC016CC + 3 * self.type)
        self.scripts = scripts or {}
        self.cols = max([COLS] + [len(self.stock_poses(a)) for a in range(1, ANIMS + 1)])
        # poses a script uses beyond the cartridge's get new mapping ids
        self.new_maps, nxt = {}, self.map_table_len() + 1
        for a in sorted(self.scripts):
            for k in range(len(self.stock_poses(a)) + 1, max(p for p, _ in self.scripts[a][0]) + 1):
                self.new_maps[(a, k)] = nxt
                nxt += 1
        if nxt > 256:
            raise ValueError("poses novas demais (os ids de pose do SB5 vao ate 255)")
        for a, (steps, _, _) in self.scripts.items():
            if max(q for q, _ in steps) > self.cols:
                raise ValueError(f"animacao {a:02X}: a folha tem {self.cols} poses por linha")

    def rb(self, a): return self.rom[_off(a)]
    def rw(self, a): return self.rom[_off(a)] | self.rom[_off(a) + 1] << 8
    def rl(self, a): return self.rw(a) | self.rb(a + 2) << 16

    def anim(self, a):
        """[(mapping, frames)] of animation a (with the scripts applied)."""
        if a in self.scripts:
            maps = dict(self.poses())[a]
            return [(maps[p - 1] if p else 0, f) for p, f in self.scripts[a][0]]
        return self.stock_anim(a)

    def script_bytes(self, a):
        """Script of animation a as the engine reads it. The terminator is
        `[restart offset, 0]` (asm/bombers.asm, bomber_loop)."""
        if a not in self.scripts:
            p = _off(self.anim_tab & 0xFF0000 | self.rw(self.anim_tab + 2 * (a - 1)))
            n = 0
            while self.rom[p + 2 * n + 1] and n < 80:
                n += 1
            return bytes(self.rom[p:p + 2 * n]) + bytes(2)
        _, loop, hide = self.scripts[a]
        out = b"".join(bytes(s) for s in self.anim(a))
        return out + (bytes([0, 255]) if hide else b"") + bytes([2 * loop, 0])

    def stock_poses(self, a):
        seen = []
        for m, _ in self.stock_anim(a):
            if m and m not in seen:
                seen.append(m)
        return seen

    def stock_anim(self, a):
        p = self.anim_tab & 0xFF0000 | self.rw(self.anim_tab + 2 * (a - 1))
        out = []
        while len(out) < 64:
            m, d = self.rb(p), self.rb(p + 1)
            if d == 0:
                break
            out.append((m, d))
            p += 2
        return out

    def poses(self):
        """[(animation, [mappings in order of first use])]."""
        if getattr(self, "_poses", None):
            return self._poses
        out = []
        for a in range(1, ANIMS + 1):
            seen = self.stock_poses(a)
            if a in self.scripts:   # cells 1..highest pose used; the others are not read
                n = max(p for p, _ in self.scripts[a][0])
                seen = seen[:n] + [self.new_maps[(a, k)] for k in range(len(seen) + 1, n + 1)]
            out.append((a, seen))
        self._poses = out
        return out

    def org_y(self, a):
        """Origin row of animation a: lower (multiples of 8) when its poses reach above the cell."""
        cache = self.__dict__.setdefault("_org", {})
        if a not in cache:
            top = min((y for m in dict(self.poses())[a] for _, y, _, _ in self.mapping(m)), default=0)
            cache[a] = ORG_Y + max(0, -(-(-top - ORG_Y) // 8)) * 8
        return cache[a]

    def map_addr(self, m):
        return self.map_tab & 0xFF0000 | self.rw(self.map_tab + 2 * (m - 1))

    def mapping(self, m):
        if m > self.map_table_len():    # new pose: nothing in the cartridge
            return []
        p = self.map_addr(m)
        out = []
        for k in range(self.rb(p)):
            q = _off(p + 1 + 7 * k)
            x, y, t = struct.unpack("<hhH", self.rom[q:q + 6])
            out.append((x, y, t, self.rom[q + 6]))
        return out

    def map_table_len(self):
        """Entries in the mapping word table: the animation word table follows it."""
        n = (self.anim_tab - self.map_tab) // 2
        if not 0 < n < 256:
            raise ValueError(f"type ${self.type:02X}: unexpected mapping table")
        return n

    def char_table(self, char):
        return 0x800000 | self.rw(0x80BB66 + 2 * char)

    def sheet_src(self, sheet):
        return self.rl(0x85E22D + 8 * (sheet - 1) + 4)

    def tile(self, addr):
        d = self.rom[_off(addr):_off(addr) + 32]
        px = np.zeros((8, 8), np.uint8)
        for y in range(8):
            for b, plane in enumerate((d[2 * y], d[2 * y + 1], d[16 + 2 * y], d[17 + 2 * y])):
                for x in range(8):
                    px[y, x] |= (plane >> (7 - x) & 1) << b
        return px

    def render(self, char, a, m):
        """Pose (animation a, mapping m) as a CELL_H x CELL_W array of color indexes."""
        cache = self.__dict__.setdefault("_render", {})
        if (char, a, m) not in cache:
            cache[(char, a, m)] = self._render_pose(char, a, m)
        return cache[(char, a, m)]

    def piece(self, char, a, tile, attr):
        """One mapping piece of animation a as it is drawn (flips applied)."""
        base = self.sheet_src(self.rb(self.char_table(char) + 2 * (a - 1)))
        n = 2 if attr & 1 else 1
        img = np.zeros((8 * n, 8 * n), np.uint8)
        for ty in range(n):
            for tx in range(n):
                img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = self.tile(base + ((tile & 0x1FF) + tx + 16 * ty) * 32)
        if attr & 0x40:
            img = img[:, ::-1]
        if attr & 0x80:
            img = img[::-1]
        return img

    def _render_pose(self, char, a, m):
        cell = np.zeros((CELL_H, CELL_W), np.uint8)
        for x, y, tile, attr in reversed(self.mapping(m)):   # the first piece is drawn on top
            img = self.piece(char, a, tile, attr)
            n = len(img) // 8
            x0, y0 = ORG_X + x, self.org_y(a) + y
            if x0 < 0 or y0 < 0 or x0 + 8 * n > CELL_W or y0 + 8 * n > CELL_H:
                raise ValueError(f"mapping ${m:02X} leaves the {CELL_W}x{CELL_H} cell")
            dst = cell[y0:y0 + 8 * n, x0:x0 + 8 * n]
            dst[img != 0] = img[img != 0]
        return cell


# ---- sheet layout -----------------------------------------------------------
def cell_pos(index, col, cols=COLS):
    """Top-left pixel of the cell of the index-th animation, pose column col."""
    g, r = divmod(index, GROUP_ROWS)
    return g * (1 + cols) * CELL_W + (1 + col) * CELL_W, HEADER_H + r * CELL_H


def sheet_size(cols=COLS):
    groups = (ANIMS + GROUP_ROWS - 1) // GROUP_ROWS
    return groups * (1 + cols) * CELL_W, HEADER_H + GROUP_ROWS * CELL_H


def rom_palette(rom, pid):
    """Colors 1-8 of palette id `pid` of set 0 (`$81:8000`), as RGB."""
    w = _off(0x818000) + 2 * (pid - 1)
    p = _off(0x810000 | rom[w] | rom[w + 1] << 8)
    out = []
    for i in range(1, 9):
        v = rom[p + 4 + 2 * i] | rom[p + 5 + 2 * i] << 8
        out.append(((v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3))
    return out


def char_palettes(rom, char, count=6):
    """The character's `count` color variants (palette ids `$80:BB4E[char] + n`), 8 colors each."""
    base = rom[_off(0x80BB4E) + char]
    return [rom_palette(rom, base + n) for n in range(count)]


def key_colors(colors):
    """Colors to paint a sheet with: the given ones, equal entries made
    different (one SNES step away) so every palette row has its own."""
    out = []
    for c in colors:
        k = tuple(c)
        if k in out:
            for ch, d in ((2, 8), (2, -8), (1, 8), (1, -8), (0, 8), (0, -8), (2, 16), (1, 16), (0, 16)):
                t = list(c)
                t[ch] += d
                if 0 <= t[ch] <= 248 and tuple(t) not in out:
                    k = tuple(t)
                    break
        out.append(k)
    return out


def export_sheet(br, char, title, palette=None):
    """RGBA picture with every pose of the character, ready to be edited."""
    palette = palette or PALETTE
    w, h = sheet_size(br.cols)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dark = (24, 28, 40, 255)
    dr.rectangle((0, 0, w - 1, HEADER_H - 1), fill=dark)
    dr.text((6, 4), title, fill=(255, 255, 255, 255))
    dr.text((6, 18), "grade 64x64 - 1a coluna de cada bloco = rotulo - fundo transparente - cores:",
            fill=(170, 180, 200, 255))
    for i, c in enumerate(palette):
        dr.rectangle((6 + i * 14, 36, 17 + i * 14, 47), fill=c + (255,), outline=(0, 0, 0, 255))
    draw_labels(im, br)
    for i, (a, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col, br.cols)
            cell = br.render(char, a, m)
            rgba = np.zeros((CELL_H, CELL_W, 4), np.uint8)
            for k, c in enumerate(palette):
                rgba[cell == k + 1] = c + (255,)
            im.paste(Image.fromarray(rgba, "RGBA"), (x, y))
    return im


def draw_labels(im, br):
    """Label cell (first column) of every animation: number, name, sequence."""
    dr = ImageDraw.Draw(im)
    for i, (a, maps) in enumerate(br.poses()):
        x0, y0 = cell_pos(i, -1, br.cols)
        dr.rectangle((x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1), fill=(24, 28, 40, 255), outline=(70, 80, 110, 255))
        words = NAMES.get(a, "").rsplit(" ", 1) if NAMES.get(a) else []
        lines = [f"{a:02X} {words[0] if len(words) > 1 else ''}".strip(), words[-1] if words else "",
                 "".join(str(maps.index(m) + 1) if m else "-" for m, _ in br.anim(a))[:10]]
        if br.org_y(a) != ORG_Y:
            lines.append(f"+{br.org_y(a) - ORG_Y}px abaixo")
        for k, text in enumerate(lines):
            dr.text((x0 + 3, y0 + 4 + 13 * k), text[:10],
                    fill=(255, 255, 255, 255) if k < 2 else (140, 150, 175, 255))


def read_sheet(br, path):
    """Edited sheet -> ({(animation, mapping): index array}, off-palette pixel count)."""
    im = Image.open(path).convert("RGBA")
    if im.size != sheet_size(br.cols):
        raise ValueError(f"{path}: size {im.size}, expected {sheet_size(br.cols)} (do not resize or crop the sheet)")
    a = np.asarray(im, dtype=np.int32)
    pal = np.array(PALETTE, dtype=np.int32)
    cells, inexact = {}, 0
    for i, (an, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col, br.cols)
            px = a[y:y + CELL_H, x:x + CELL_W]
            rgb = px[..., :3]
            solid = (px[..., 3] >= 128) & ~(rgb == np.array(KEY)).all(-1)
            d = ((rgb[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1)
            # equal colors in the palette (white x3): the first one wins
            idx = (d.argmin(-1) + 1).astype(np.uint8)
            inexact += int((solid & (d.min(-1) != 0)).sum())
            idx[~solid] = 0
            cells[(an, m)] = idx
    return cells, inexact


def read_sheet_recolor(br, path, palette_path):
    """Sheet painted with the key colors of a palette picture.

    The picture has one pixel per color: column 0 = colors used in the sheet,
    columns 1.. = the same entries for each bomber color (white, black, ...).
    Colors that are not in column 0 are kept as they are in every palette.
    Cells still equal to the SB5 art are repainted with the nearest entries
    of the first palette. Returns (cells, palettes [[15 rgb]], notes).
    """
    im = Image.open(path).convert("RGBA")
    if im.size != sheet_size(br.cols):
        raise ValueError(f"{path}: size {im.size}, expected {sheet_size(br.cols)} (do not resize or crop the sheet)")
    a = np.asarray(im, dtype=np.int32)
    pal = np.asarray(Image.open(palette_path).convert("RGB"), dtype=np.int32)
    key = [tuple(int(v) for v in pal[r, 0]) for r in range(pal.shape[0])]
    sb5 = np.array([(0, 0, 0)] + PALETTE, dtype=np.int32)

    raw, legacy, counts = {}, {}, {}
    for i, (an, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col, br.cols)
            px = a[y:y + CELL_H, x:x + CELL_W]
            solid = (px[..., 3] >= 128) & ~(px[..., :3] == np.array(KEY)).all(-1)
            ref = br.render(0, an, m)
            if ((ref != 0) == solid).all() and (sb5[ref][solid] == px[..., :3][solid]).all():
                legacy[(an, m)] = ref
                continue
            raw[(an, m)] = (px[..., :3], solid)
            cols, n = np.unique(px[..., :3][solid], axis=0, return_counts=True)
            for c, k in zip(cols, n):
                counts[tuple(int(v) for v in c)] = counts.get(tuple(int(v) for v in c), 0) + int(k)
    if not raw:
        raise ValueError(f"{path}: no edited cell found")

    # sheet color -> entry ("row", r) or ("fixed", rgb); strays snap to a close key color
    entry, snapped = {}, 0
    for c, n in counts.items():
        if c in key:
            entry[c] = ("row", key.index(c))
            continue
        d = [sum((u - v) ** 2 for u, v in zip(c, k)) for k in key]
        if min(d) <= 200:
            entry[c] = ("row", d.index(min(d)))
            snapped += n
        else:
            entry[c] = ("fixed", c)
    # entries that are the same SNES color (5 bits) in every palette share one index
    def signature(e):
        cols = [pal[e[1], c] for c in range(1, pal.shape[1])] if e[0] == "row" else [e[1]] * (pal.shape[1] - 1)
        return tuple(tuple(int(v) >> 3 for v in c) for c in cols)

    first = {}
    for e in sorted(set(entry.values()), key=lambda e: (e[0] != "row", e[1])):
        first.setdefault(signature(e), e)
    entry = {c: first[signature(e)] for c, e in entry.items()}
    used = sorted({e for e in entry.values() if e[0] == "row"}) + sorted({e for e in entry.values() if e[0] == "fixed"})
    if len(used) > 15:
        lines = [f"{'linha %d da paleta' % e[1] if e[0] == 'row' else 'cor fixa %02X%02X%02X' % e[1]}: "
                 f"{sum(n for c, n in counts.items() if entry[c] == e)} px" for e in used]
        raise ValueError(f"a folha usa {len(used)} cores; um sprite de SNES tem 15:\n  " + "\n  ".join(lines))
    index = {e: i + 1 for i, e in enumerate(used)}

    def colors(column):
        return [tuple(int(v) for v in pal[e[1], column]) if e[0] == "row" else e[1] for e in used]

    palettes = [colors(c) for c in range(1, pal.shape[1])]
    shown = np.array(palettes[0], dtype=np.int32)
    near = [0] + [int(((shown - np.array(c)) ** 2).sum(-1).argmin()) + 1 for c in PALETTE]
    cells = {}
    for k, ref in legacy.items():
        cells[k] = np.array(near, np.uint8)[ref]
    for k, (rgb, solid) in raw.items():
        idx = np.zeros((CELL_H, CELL_W), np.uint8)
        for c in {tuple(int(v) for v in p) for p in rgb[solid]}:
            idx[solid & (rgb == np.array(c)).all(-1)] = index[entry[c]]
        cells[k] = idx
    # every color a sheet painted like this one may use -> its index (the other
    # characters' sheets, read_sheet_like): sheet colors, key rows that end up
    # equal to a used entry, and the SB5 colors of the cells still in SB5 art
    cmap = {c: index[e] for c, e in entry.items()}
    by_sig = {signature(e): index[e] for e in used}
    for r, k in enumerate(key):
        if k not in cmap and signature(("row", r)) in by_sig:
            cmap[k] = by_sig[signature(("row", r))]
    notes = dict(edited=len(raw), legacy=len(legacy), colors=len(used), snapped=snapped,
                 fixed=[e[1] for e in used if e[0] == "fixed"], used=used, cmap=cmap,
                 sb5=dict(zip(PALETTE, near[1:])))
    return cells, palettes, notes


def read_sheet_like(br, path, ref, ref_br, ref_cells, cmap, sb5=None):
    """Sheet of a character 1-9 laid out like Bomberman's (br: Bomberman's
    poses, with the character's scripts). Cells equal to the same cell of
    `ref` (bomber_sb6.png, read as ref_cells by ref_br) are Bomberman's pose;
    the others are painted with Bomberman's colors (cmap: color -> index of
    his palette, read_sheet_recolor). Returns (cells, animations with an
    edited or new pose, notes)."""
    im = Image.open(path).convert("RGBA")
    if im.size != sheet_size(br.cols):
        raise ValueError(f"{path}: size {im.size}, expected {sheet_size(br.cols)} (do not resize or crop the sheet)")
    a = np.asarray(im, dtype=np.int32)
    r = np.asarray(Image.open(ref).convert("RGBA"), dtype=np.int32)
    colors = dict(cmap)
    for c, i in (sb5 or {}).items():
        colors.setdefault(tuple(c), i)
    keys = np.array(list(colors), dtype=np.int32)
    vals = np.array(list(colors.values()), dtype=np.uint8)
    ref_maps = dict(ref_br.poses())
    cells, edited, snapped, unknown = {}, set(), 0, {}
    for i, (an, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col, br.cols)
            px, rp = a[y:y + CELL_H, x:x + CELL_W], r[y:y + CELL_H, x:x + CELL_W]
            solid = (px[..., 3] >= 128) & ~(px[..., :3] == np.array(KEY)).all(-1)
            rsolid = (rp[..., 3] >= 128) & ~(rp[..., :3] == np.array(KEY)).all(-1)
            rm = ref_maps.get(an, [])
            if col < len(rm) and (solid == rsolid).all() and (px[..., :3][solid] == rp[..., :3][solid]).all():
                cells[(an, m)] = ref_cells[(an, rm[col])]
                continue
            edited.add(an)
            rgb = px[..., :3]
            d = ((rgb[:, :, None, :] - keys[None, None, :, :]) ** 2).sum(-1)
            idx = vals[d.argmin(-1)]
            far = solid & (d.min(-1) > 200)
            snapped += int((solid & (d.min(-1) != 0) & ~far).sum())
            for c in {tuple(int(v) for v in q) for q in rgb[far]}:
                unknown[c] = unknown.get(c, 0) + int((far & (rgb == np.array(c)).all(-1)).sum())
            idx[~solid] = 0
            cells[(an, m)] = idx
    if unknown:
        raise ValueError("cores que nao estao na paleta do Bomberman (BombermanPallete.png / bomber_sb6.png): "
                         + ", ".join("%02X%02X%02X (%d px)" % (c + (n,)) for c, n in sorted(unknown.items())[:12]))
    return cells, edited, dict(edited=len(edited), snapped=snapped)


# ---- conversion ---------------------------------------------------------------
def _canon(px):
    """(key bytes, flip attr) so that flipping the stored key gives px."""
    best = None
    for attr, v in ((0, px), (0x40, px[:, ::-1]), (0x80, px[::-1]), (0xC0, px[::-1, ::-1])):
        k = v.tobytes()
        if best is None or k < best[0]:
            best = (k, attr)
    return best


def _decompose(cell, gx, gy, threshold):
    """Pieces [(x, y, size, key, flip)] of a cell on a 16-px grid at (gx, gy)."""
    ys, xs = np.nonzero(cell)
    if not len(xs):
        return []
    pad = np.zeros((CELL_H + 32, CELL_W + 32), np.uint8)
    pad[16:16 + CELL_H, 16:16 + CELL_W] = cell
    pieces = []
    for by in range(gy, CELL_H + 16, 16):
        for bx in range(gx, CELL_W + 16, 16):
            blk = pad[by:by + 16, bx:bx + 16]
            quads = [(qx, qy) for qy in (0, 8) for qx in (0, 8) if blk[qy:qy + 8, qx:qx + 8].any()]
            if not quads:
                continue
            if len(quads) >= threshold:
                k, f = _canon(blk)
                pieces.append((bx - 16, by - 16, 16, k, f))
            else:
                for qx, qy in quads:
                    k, f = _canon(blk[qy:qy + 8, qx:qx + 8])
                    pieces.append((bx - 16 + qx, by - 16 + qy, 8, k, f))
    return pieces


def _stock_anim(br, a, maps, cells, split=False):
    """The cartridge's own pieces of animation a with the edits painted on
    its tiles: a tile stays one tile wherever the cartridge uses it (other
    poses, under other pieces), which the grid cut cannot do for the poses
    packed with overlapping pieces. Returns the pieces of each pose, or None
    when there is a new pose or the edits ask two things of the same tile.
    split: 16x16 pieces as four 8x8 ones (the cartridge also overlaps the
    tiles of its 16x16 pieces; more sprites, never more tiles)."""
    oy = br.org_y(a)
    base = br.sheet_src(br.rb(br.char_table(br.char) + 2 * (a - 1)))
    tiles, want = {}, {}

    def tile(t):
        if t not in tiles:
            tiles[t] = br.tile(base + t * 32).copy()
        return tiles[t]

    def parts(m):
        """8x8 parts of pose m, top first: (x, y, tile, flips)."""
        out = []
        for x, y, t, attr in br.mapping(m):
            n = 2 if attr & 1 else 1
            for ty in range(n):
                for tx in range(n):
                    sx, sy = (n - 1 - tx if attr & 0x40 else tx), (n - 1 - ty if attr & 0x80 else ty)
                    out.append((ORG_X + x + 8 * sx, oy + y + 8 * sy, (t & 0x1FF) + tx + 16 * ty, attr & 0xC0))
        return out

    def shown(t, f):
        img = tile(t)
        if f & 0x40:
            img = img[:, ::-1]
        if f & 0x80:
            img = img[::-1]
        return img

    def draw(m):
        out = np.zeros((CELL_H, CELL_W), np.uint8)
        for x, y, t, f in reversed(parts(m)):
            img = shown(t, f)
            dst = out[y:y + 8, x:x + 8]
            dst[img != 0] = img[img != 0]
        return out

    loose = {}
    for m in maps:
        if not br.mapping(m):
            return None
        cell, ps = cells[(a, m)], parts(m)
        loose[m] = np.zeros((CELL_H, CELL_W), bool)
        for y, x in zip(*np.nonzero(cell != br.render(br.char, a, m))):
            v = int(cell[y, x])
            cover = [(t, (7 - (y - py) if f & 0x80 else y - py), (7 - (x - px) if f & 0x40 else x - px))
                     for px, py, t, f in ps if px <= x < px + 8 and py <= y < py + 8]
            if not cover:
                loose[m][y, x] = True
                continue
            if v:       # the tile that shows there now, or the one on top
                cover = [next((c for c in cover if tile(c[0])[c[1], c[2]]), cover[0])]
            for c in cover:
                if want.setdefault(c, v) != v:
                    return None
    for (t, y, x), v in want.items():
        tiles[t][y, x] = v

    result = []
    for m in maps:
        cell, pieces = cells[(a, m)], []
        for by in range(0, CELL_H, 8):          # painted outside every piece: 8x8 pieces on top
            for bx in range(0, CELL_W, 8):
                if loose[m][by:by + 8, bx:bx + 8].any():
                    k, f = _canon(cell[by:by + 8, bx:bx + 8])
                    pieces.append((bx, by, 8, k, f))
        img = draw(m)
        for bx, by, _, _, _ in pieces:
            img[by:by + 8, bx:bx + 8][cell[by:by + 8, bx:bx + 8] != 0] = cell[by:by + 8, bx:bx + 8][
                cell[by:by + 8, bx:bx + 8] != 0]
        if not (img == cell).all():
            return None
        for x, y, t, attr in br.mapping(m):
            n = 2 if attr & 1 else 1
            full = np.zeros((8 * n, 8 * n), np.uint8)
            for ty in range(n):
                for tx in range(n):
                    sx, sy = (n - 1 - tx if attr & 0x40 else tx), (n - 1 - ty if attr & 0x80 else ty)
                    full[8 * sy:8 * sy + 8, 8 * sx:8 * sx + 8] = shown((t & 0x1FF) + tx + 16 * ty, attr & 0xC0)
            step = 8 if split else 8 * n
            for qy in range(0, 8 * n, step):
                for qx in range(0, 8 * n, step):
                    part = full[qy:qy + step, qx:qx + step]
                    if part.any():
                        key, f = _canon(part)
                        pieces.append((ORG_X + x + qx, oy + y + qy, step, key, f))
        result.append(pieces)
    return result


def _cost(keys):
    return sum(4 if len(k) == 256 else 1 for k in keys)


def _candidates(cell, exhaustive):
    ys, xs = np.nonzero(cell)
    if not len(xs):
        return [[]]
    if exhaustive:
        return [_decompose(cell, gx, gy, t) for t in (2, 3, 5)
                for gx in range(0, 16 if t < 5 else 8) for gy in range(0, 16 if t < 5 else 8)]
    x0, y0 = int(xs.min()) + 16, int(ys.min()) + 16
    return [_decompose(cell, gx, gy, t) for t in (2, 3)
            for gx in {x0 % 16, (x0 + 8) % 16} for gy in {y0 % 16, (y0 + 8) % 16}]


def _fit_anim(cells, exhaustive, extra=None):
    """Grid choice per pose (greedy + refinement). Returns (pieces per pose, set of keys).
    extra: one more candidate per pose (or None), e.g. the cartridge's pieces."""
    cands = [_candidates(c, exhaustive) for c in cells]
    for cl, e in zip(cands, extra or []):
        if e is not None:
            cl.append(e)
    sets = [[{k for _, _, _, k, _ in p} for p in cl] for cl in cands]
    pick = [None] * len(cells)
    pop = {}   # in how many poses a piece could be used
    for cl in sets:
        for k in set().union(*cl):
            pop[k] = pop.get(k, 0) + 1
    for _ in range(3 if exhaustive else 1):
        for i in range(len(cells)):
            others = set()
            for j, pj in enumerate(pick):
                if j != i and pj is not None:
                    others |= sets[j][pj]
            # few new tiles first, then pieces other poses can reuse, then fewer sprites
            pick[i] = min(range(len(cands[i])),
                          key=lambda n: (_cost(sets[i][n] - others),
                                         -_cost(k for k in sets[i][n] - others if pop[k] > 1),
                                         len(cands[i][n])))
    keys = set()
    for i, n in enumerate(pick):
        keys |= sets[i][n]
    return [cands[i][n] for i, n in enumerate(pick)], keys


def convert(br, cells, only=None, stream=False):
    """Cells -> (strips [bytes of 1 KB], {animation: strip}, {mapping: pieces}, streamed).

    Mapping pieces are returned as [(x, y, tile index in strip, attr)] per
    mapping, with the strip of their animation in the second dict.
    `only`: set of animations to convert (the others keep the cartridge's tiles).
    stream: an animation whose poses do not fit one strip together is
    streamed pose by pose (asm/bombers.asm, bomber_stream): each pose gets a
    block of at most POSE_TILES tiles (`streamed[a][m] = (block, columns)`,
    block = row 0 then row 1 of `columns` tiles; its pieces count tiles from
    the block) and its strip only holds the first pose, at columns 0-7.
    """
    strips = []      # each: dict(keys=set, anims=[...])
    fitted = {}
    problems = []
    streamed, mappings_s = {}, {}
    for a, maps in br.poses():
        if only is not None and a not in only:
            continue
        played = {m for m, _ in br.anim(a) if m}   # cells the sequence never shows get no tiles
        maps = [m for m in maps if m in played]
        chosen = None
        for how in ("grid", "stock", "stock8", "search"):
            if how.startswith("stock"):
                pieces = _stock_anim(br, a, maps, cells, how == "stock8")
                if pieces is None:
                    continue
                keys = {k for q in pieces for _, _, _, k, _ in q}
            else:
                extra = _stock_anim(br, a, maps, cells) if how == "search" else None
                pieces, keys = _fit_anim([cells[(a, m)] for m in maps], how == "search", extra)
            if _cost(keys) <= STRIP_TILES:
                chosen = (pieces, keys)
                break
        if chosen is None and stream:
            try:
                streamed[a] = _stream_anim(br, a, maps, cells, mappings_s)
            except ValueError as e:
                problems.append(str(e))
            continue
        if chosen is None:
            problems.append(f"animacao {a:02X} ({NAMES.get(a, '')}): as {len(maps)} poses precisam de "
                            f"{_cost(keys)} tiles 8x8 diferentes; o limite e {STRIP_TILES}")
            continue
        fitted[a] = (maps, chosen[0])
        for s in strips:
            if _cost(s["keys"] | chosen[1]) <= STRIP_TILES:
                s["keys"] |= chosen[1]
                s["anims"].append(a)
                break
        else:
            strips.append(dict(keys=set(chosen[1]), anims=[a]))
    if problems:
        raise ValueError("sprites grandes/variados demais para o motor do SB5:\n  " + "\n  ".join(problems))

    data, anim_strip, mappings = [], {}, {}
    for si, s in enumerate(strips):
        px = np.zeros((16, 128), np.uint8)
        slot = {}
        blocks = sorted(k for k in s["keys"] if len(k) == 256)
        singles = sorted(k for k in s["keys"] if len(k) == 64)
        for i, k in enumerate(blocks):
            px[:, 16 * i:16 * i + 16] = np.frombuffer(k, np.uint8).reshape(16, 16)
            slot[k] = 2 * i
        for j, k in enumerate(singles):
            n = len(blocks) * 4 + j
            col, row = 2 * (n // 4) + (n % 4) % 2, (n % 4) // 2
            px[row * 8:row * 8 + 8, col * 8:col * 8 + 8] = np.frombuffer(k, np.uint8).reshape(8, 8)
            slot[k] = row * 16 + col
        data.append(encode_strip(px))
        for a in s["anims"]:
            anim_strip[a] = si
            maps, pieces = fitted[a]
            for m, plist in zip(maps, pieces):
                mappings[m] = [(x - ORG_X, y - br.org_y(a), slot[k], 0x20 | f | (1 if size == 16 else 0))
                               for x, y, size, k, f in plist]
    verify(cells, br, data, anim_strip, mappings)
    for a, poses in streamed.items():     # the first pose shown, for the start of the animation
        first = next(m for m, _ in br.anim(a) if m)
        anim_strip[a] = len(data)
        data.append(poses[first][2])
        streamed[a] = {m: (block, w) for m, (block, w, _) in poses.items()}
    mappings.update(mappings_s)
    return data, anim_strip, mappings, streamed


POSE_TILES = 16          # a streamed pose: half of the bomber's 32-tile page (double buffer)


def _stream_anim(br, a, maps, cells, mappings):
    """Blocks of the poses of animation a (convert, stream). Returns
    {mapping: (block, columns, 1 KB strip with the pose at columns 0-7)}."""
    out = {}
    for m in maps:
        pieces, keys = _fit_anim([cells[(a, m)]], True)
        if _cost(keys) > POSE_TILES:
            raise ValueError(f"animacao {a:02X} ({NAMES.get(a, '')}): uma pose precisa de {_cost(keys)} tiles 8x8; "
                             f"o limite por pose e {POSE_TILES} (32x32 px)")
        px = np.zeros((16, 128), np.uint8)
        slot = {}
        blocks = sorted(k for k in keys if len(k) == 256)
        singles = sorted(k for k in keys if len(k) == 64)
        for i, k in enumerate(blocks):
            px[:, 16 * i:16 * i + 16] = np.frombuffer(k, np.uint8).reshape(16, 16)
            slot[k] = 2 * i
        for j, k in enumerate(singles):
            n = len(blocks) * 4 + j
            col, row = 2 * (n // 4) + (n % 4) % 2, (n % 4) // 2
            px[row * 8:row * 8 + 8, col * 8:col * 8 + 8] = np.frombuffer(k, np.uint8).reshape(8, 8)
            slot[k] = row * 16 + col
        w = 2 * -(-(4 * len(blocks) + len(singles)) // 4)
        strip = encode_strip(px)
        block = strip[:32 * w] + strip[512:512 + 32 * w]
        mappings[m] = [(x - ORG_X, y - br.org_y(a), slot[k], 0x20 | f | (1 if size == 16 else 0))
                       for x, y, size, k, f in pieces[0]]
        verify({(a, m): cells[(a, m)]}, _OnePose(br, a, m), [strip], {a: 0}, mappings)
        out[m] = (block, w, strip)
    return out


class _OnePose:
    """Just enough of BomberRom for verify() on one pose."""
    def __init__(self, br, a, m):
        self.a, self.m, self.oy = a, m, br.org_y(a)

    def poses(self):
        return [(self.a, [self.m])]

    def org_y(self, a):
        return self.oy


def encode_strip(px):
    """16x128 color indexes -> 32 SNES 4bpp tiles (1 KB)."""
    out = bytearray()
    for ty in range(2):
        for tx in range(16):
            t = px[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            lo, hi = bytearray(), bytearray()
            for y in range(8):
                planes = [0, 0, 0, 0]
                for x in range(8):
                    v = int(t[y, x])
                    for b in range(4):
                        planes[b] |= (v >> b & 1) << (7 - x)
                lo += bytes(planes[:2])
                hi += bytes(planes[2:])
            out += lo + hi
    return bytes(out)


def encode_mapping(pieces, row):
    if not pieces:
        # $C0:158A loops 256 times on a zero count: an empty pose is one piece
        # far to the right, which the drawer clips.
        return bytes([1]) + struct.pack("<hhHB", 0x4000, 0, 0, 0x20)
    out = bytearray([len(pieces)])
    for x, y, tile, attr in pieces:
        out += struct.pack("<hhHB", x, y, (row * 16 + tile) & 0xFFFF, attr)
    return bytes(out)


def verify(cells, br, strips, anim_strip, mappings):
    """Redraws every pose from the converted strips/mappings; raises on a mismatch."""
    for a, maps in br.poses():
        if a not in anim_strip:
            continue
        px = decode_strip(strips[anim_strip[a]])
        oy = br.org_y(a)
        for m in maps:
            if m not in mappings:       # not played (convert)
                continue
            out = np.zeros((CELL_H, CELL_W), np.uint8)
            for x, y, tile, attr in reversed(mappings[m]):
                n = 16 if attr & 1 else 8
                tx, ty = tile % 16 * 8, tile // 16 * 8
                img = px[ty:ty + n, tx:tx + n]
                if attr & 0x40:
                    img = img[:, ::-1]
                if attr & 0x80:
                    img = img[::-1]
                x0, y0 = max(0, -(ORG_X + x)), max(0, -(oy + y))
                x1, y1 = min(n, CELL_W - ORG_X - x), min(n, CELL_H - oy - y)
                dst = out[oy + y + y0:oy + y + y1, ORG_X + x + x0:ORG_X + x + x1]
                src = img[y0:y1, x0:x1]
                dst[src != 0] = src[src != 0]
            if not (out == cells[(a, m)]).all():
                raise ValueError(f"internal error: pose {a:02X}/{m:02X} does not survive the conversion")


def decode_strip(data):
    px = np.zeros((16, 128), np.uint8)
    for i in range(32):
        d = data[32 * i:32 * i + 32]
        for y in range(8):
            for x in range(8):
                s = 7 - x
                px[i // 16 * 8 + y, i % 16 * 8 + x] = ((d[2 * y] >> s & 1) | (d[2 * y + 1] >> s & 1) << 1 |
                                                       (d[16 + 2 * y] >> s & 1) << 2 | (d[17 + 2 * y] >> s & 1) << 3)
    return px
