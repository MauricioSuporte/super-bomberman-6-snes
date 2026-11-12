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

TYPE = 0x10
ANIMS = 0x4D             # animations 1..$4D are real; the table has 81 slots
CHAR_SLOTS = 81
# The sheet is a plain grid of 64x64 cells, like the Unity project's
# Bomberman.png, and a bomber sits at the same place inside a cell (feet
# centre at x = 32, soles on row 43), so frames can be copied cell to cell.
CELL_W, CELL_H = 64, 64
ORG_X, ORG_Y = 32, 38    # object position inside a cell
COLS = 7                 # most poses in one animation
GROUP_ROWS = 39          # animations per column group
GROUP_W = (1 + COLS) * CELL_W   # label cell + poses
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


def load_scripts(path):
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
                        if not (0 <= pose <= COLS and 1 <= f <= 254) or (pose == 0 and tok[0] != "-"):
                            raise ValueError
                        steps.append((pose, f))
                if not (1 <= a <= ANIMS) or a in out or not any(p for p, _ in steps) or len(steps) > 100                         or loop >= len(steps):
                    raise ValueError
            except ValueError:
                raise ValueError(f"{path}, linha {ln}: nao entendi '{line}' "
                                 f"(formato: animacao : quadros : poses 1-{COLS})")
            out[a] = (steps, loop, hide)
    return out


class BomberRom:
    def __init__(self, rom, scripts=None):
        """scripts (load_scripts): animations that play other poses/orders than the cartridge's."""
        self.rom = rom
        self.anim_tab = self.rl(0xC0171D + 3 * TYPE)
        self.map_tab = self.rl(0xC016CC + 3 * TYPE)
        self.scripts = scripts or {}
        # poses a script uses beyond the cartridge's get new mapping ids
        self.new_maps, nxt = {}, self.map_table_len() + 1
        for a in sorted(self.scripts):
            for k in range(len(self.stock_poses(a)) + 1, max(p for p, _ in self.scripts[a][0]) + 1):
                self.new_maps[(a, k)] = nxt
                nxt += 1
        if nxt > 256:
            raise ValueError("poses novas demais (os ids de pose do SB5 vao ate 255)")

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
        """Entries in the mapping word table (it ends where the data starts)."""
        return (self.rw(self.map_tab) - (self.map_tab & 0xFFFF)) // 2

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
        t = self.char_table(char) + 2 * (a - 1)
        base = self.sheet_src(self.rb(t))
        cell = np.zeros((CELL_H, CELL_W), np.uint8)
        for x, y, tile, attr in reversed(self.mapping(m)):
            n = 2 if attr & 1 else 1
            img = np.zeros((8 * n, 8 * n), np.uint8)
            for ty in range(n):
                for tx in range(n):
                    img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = self.tile(base + ((tile & 0x1FF) + tx + 16 * ty) * 32)
            if attr & 0x40:
                img = img[:, ::-1]
            if attr & 0x80:
                img = img[::-1]
            x0, y0 = ORG_X + x, self.org_y(a) + y
            if x0 < 0 or y0 < 0 or x0 + 8 * n > CELL_W or y0 + 8 * n > CELL_H:
                raise ValueError(f"mapping ${m:02X} leaves the {CELL_W}x{CELL_H} cell")
            dst = cell[y0:y0 + 8 * n, x0:x0 + 8 * n]
            dst[img != 0] = img[img != 0]
        return cell


# ---- sheet layout -----------------------------------------------------------
def cell_pos(index, col):
    """Top-left pixel of the cell of the index-th animation, pose column col."""
    g, r = divmod(index, GROUP_ROWS)
    return g * GROUP_W + (1 + col) * CELL_W, HEADER_H + r * CELL_H


def sheet_size():
    groups = (ANIMS + GROUP_ROWS - 1) // GROUP_ROWS
    return groups * GROUP_W, HEADER_H + GROUP_ROWS * CELL_H


def export_sheet(br, char, title):
    """RGBA picture with every pose of the character, ready to be edited."""
    w, h = sheet_size()
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dark = (24, 28, 40, 255)
    dr.rectangle((0, 0, w - 1, HEADER_H - 1), fill=dark)
    dr.text((6, 4), title, fill=(255, 255, 255, 255))
    dr.text((6, 18), "grade 64x64 - 1a coluna de cada bloco = rotulo - fundo transparente - cores:",
            fill=(170, 180, 200, 255))
    for i, c in enumerate(PALETTE):
        dr.rectangle((6 + i * 14, 36, 17 + i * 14, 47), fill=c + (255,), outline=(0, 0, 0, 255))
    for i, (a, maps) in enumerate(br.poses()):
        x0, y0 = cell_pos(i, -1)
        dr.rectangle((x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1), fill=dark, outline=(70, 80, 110, 255))
        words = NAMES.get(a, "").rsplit(" ", 1) if NAMES.get(a) else []
        lines = [f"{a:02X} {words[0] if len(words) > 1 else ''}".strip(), words[-1] if words else "",
                 "".join(str(maps.index(m) + 1) if m else "-" for m, _ in br.anim(a))[:10]]
        if br.org_y(a) != ORG_Y:
            lines.append(f"+{br.org_y(a) - ORG_Y}px abaixo")
        for k, text in enumerate(lines):
            dr.text((x0 + 3, y0 + 4 + 13 * k), text[:10],
                    fill=(255, 255, 255, 255) if k < 2 else (140, 150, 175, 255))
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col)
            cell = br.render(char, a, m)
            rgba = np.zeros((CELL_H, CELL_W, 4), np.uint8)
            for k, c in enumerate(PALETTE):
                rgba[cell == k + 1] = c + (255,)
            im.paste(Image.fromarray(rgba, "RGBA"), (x, y))
    return im


def read_sheet(br, path):
    """Edited sheet -> ({(animation, mapping): index array}, off-palette pixel count)."""
    im = Image.open(path).convert("RGBA")
    if im.size != sheet_size():
        raise ValueError(f"{path}: size {im.size}, expected {sheet_size()} (do not resize or crop the sheet)")
    a = np.asarray(im, dtype=np.int32)
    pal = np.array(PALETTE, dtype=np.int32)
    cells, inexact = {}, 0
    for i, (an, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col)
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
    if im.size != sheet_size():
        raise ValueError(f"{path}: size {im.size}, expected {sheet_size()} (do not resize or crop the sheet)")
    a = np.asarray(im, dtype=np.int32)
    pal = np.asarray(Image.open(palette_path).convert("RGB"), dtype=np.int32)
    key = [tuple(int(v) for v in pal[r, 0]) for r in range(pal.shape[0])]
    sb5 = np.array([(0, 0, 0)] + PALETTE, dtype=np.int32)

    raw, legacy, counts = {}, {}, {}
    for i, (an, maps) in enumerate(br.poses()):
        for col, m in enumerate(maps):
            x, y = cell_pos(i, col)
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
    notes = dict(edited=len(raw), legacy=len(legacy), colors=len(used), snapped=snapped,
                 fixed=[e[1] for e in used if e[0] == "fixed"])
    return cells, palettes, notes


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


def _fit_anim(cells, exhaustive):
    """Grid choice per pose (greedy + refinement). Returns (pieces per pose, set of keys)."""
    cands = [_candidates(c, exhaustive) for c in cells]
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


def convert(br, cells):
    """Cells -> (strips [bytes of 1 KB], {animation: strip}, {mapping: bytes without tile base}).

    Mapping pieces are returned as [(x, y, tile index in strip, attr)] per
    mapping, with the strip of their animation in the second dict.
    """
    strips = []      # each: dict(keys=set, anims=[...])
    fitted = {}
    problems = []
    for a, maps in br.poses():
        chosen = None
        for exhaustive in (False, True):
            pieces, keys = _fit_anim([cells[(a, m)] for m in maps], exhaustive)
            if _cost(keys) <= STRIP_TILES:
                chosen = (pieces, keys)
                break
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
    return data, anim_strip, mappings


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
        px = decode_strip(strips[anim_strip[a]])
        oy = br.org_y(a)
        for m in maps:
            out = np.zeros((CELL_H, CELL_W), np.uint8)
            for x, y, tile, attr in mappings[m]:
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
