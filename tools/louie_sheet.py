"""Louie pose sheets, laid out like the players' (tools/bomber_sheet.py): one 64x64 cell per pose, one row per
animation, the first cell of a row = its label, transparent background, a 64-pixel header with the colors.

    python tools/louie_sheet.py [character ...]      (default 6, the Black Louie) -> assets/louies/louie<n>_sb5.png

Mount character n (0-9, `$16C2`): object type `$80:C401[n]`, animations `$C0:171D + 3T` (scripts of
`[mapping, frames]`), mappings `$C0:16CC + 3T`, `[sheet, row]` per animation at `$80:C415[n]` (word), colors =
palette id `$80:C40B[n]` of set 0 in entries 8-15 (docs/ROM_MAP.md "Mounts (Louies) and eggs").
Read from the untouched base ROM. Export only: the build does not read these pictures back (yet).
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb6.bomber import rom_palette  # noqa: E402
from sb6.objsheets import SHEET_TABLE  # noqa: E402
from sb6.romlib import off  # noqa: E402
import walk_check  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "Super Bomberman 5 (USA).sfc")
OUT = os.path.join(ROOT, "assets", "louies")
CELL = 64
ORG_X, ORG_Y = 32, 44          # the Louie's object point inside a cell (its pieces reach y -27..+9)
ANIMS = 34
DIRS = ("direita", "baixo", "esquerda", "cima")     # $1632 1-4 = animation base + 0..3
# animations with a known use; the others are labeled by number (walk 01-04, shoulder charge 1F-22 by facing)
NAMES = {1: "anda", 6: "some", 0x1F: "ombrada"}
CHARS = {0: "Louie vermelho", 1: "Louie verde", 2: "Louie rosa", 3: "Louie amarelo", 4: "Louie (tipo 4)",
         5: "Louie (tipo 5)", 6: "Black Louie (Warooi)"}


class LouieRom:
    def __init__(self, rom, char):
        self.rom, self.char = rom, char
        self.type = self.b(0x80C401 + char)
        self.anim_tab = self.l(0xC0171D + 3 * self.type)
        self.map_tab = self.l(0xC016CC + 3 * self.type)
        self.strips = 0x800000 | self.w(0x80C415 + 2 * char)
        self.pal_id = self.b(0x80C40B + char)

    def b(self, a): return self.rom[off(a)]
    def w(self, a): return self.rom[off(a)] | self.rom[off(a) + 1] << 8
    def l(self, a): return self.w(a) | self.b(a + 2) << 16

    def script(self, a):
        p = self.anim_tab & 0xFF0000 | self.w(self.anim_tab + 2 * (a - 1))
        out = []
        while len(out) < 64 and self.b(p + 1):
            out.append((self.b(p), self.b(p + 1)))
            p += 2
        return out

    def poses(self, a):
        seen = []
        for m, _ in self.script(a):
            if m and m not in seen:
                seen.append(m)
        return seen

    def strip(self, a):
        sheet, row = self.b(self.strips + 2 * (a - 1)), self.b(self.strips + 2 * (a - 1) + 1)
        e = off(SHEET_TABLE + 8 * (sheet - 1))
        src = self.rom[e + 4] | self.rom[e + 5] << 8 | self.rom[e + 6] << 16
        return sheet, row, self.rom[off(src):off(src) + 0x2000]

    def mapping(self, m):
        p = self.map_tab & 0xFF0000 | self.w(self.map_tab + 2 * (m - 1))
        out = []
        for k in range(self.b(p)):
            q = off(p + 1 + 7 * k)
            x, y, t = struct.unpack("<hhH", self.rom[q:q + 6])
            out.append((x, y, t, self.rom[q + 6]))
        return out

    def render(self, a, m):
        """64x64 color indices (0, 8-15) of pose m with animation a's tiles (mapping tile = tile of the sheet)."""
        data = self.strip(a)[2]
        c = np.zeros((CELL, CELL), np.uint8)
        for x, y, t, at in reversed(self.mapping(m)):
            w = 16 if at & 1 else 8
            im = np.zeros((w, w), np.uint8)
            for ty in range(w // 8):
                for tx in range(w // 8):
                    im[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = walk_check.tile(data, (t + tx + 16 * ty) & 0x1FF)
            if at & 0x40:
                im = im[:, ::-1]
            if at & 0x80:
                im = im[::-1]
            X, Y = ORG_X + x, ORG_Y + y
            reg = c[Y:Y + w, X:X + w]
            reg[im != 0] = im[im != 0]
        return c


def label(a):
    for base, name in NAMES.items():
        if base == 6 and a == 6:
            return name, ""
        if base != 6 and base <= a < base + 4:
            return name, DIRS[a - base]
    return "", ""


def export(rom, char):
    lr = LouieRom(rom, char)
    pal = rom_palette(rom, lr.pal_id)                # entries 8-15
    cols = max(len(lr.poses(a)) for a in range(1, ANIMS + 1))
    w, h = (1 + cols) * CELL, CELL + ANIMS * CELL
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dark = (24, 28, 40, 255)
    dr.rectangle((0, 0, w - 1, CELL - 1), fill=dark)
    dr.text((6, 4), f"{CHARS.get(char, f'Louie {char}')} - SB5 (tipo de objeto ${lr.type:02X}, paleta ${lr.pal_id:02X})",
            fill=(255, 255, 255, 255))
    dr.text((6, 18), "grade 64x64 - 1a coluna = rotulo (animacao, sequencia de poses) - fundo transparente - cores:",
            fill=(170, 180, 200, 255))
    for i, c in enumerate(pal):
        dr.rectangle((6 + i * 14, 36, 17 + i * 14, 47), fill=tuple(c) + (255,), outline=(0, 0, 0, 255))
    for a in range(1, ANIMS + 1):
        y0 = CELL * a
        poses = lr.poses(a)
        dr.rectangle((0, y0, CELL - 1, y0 + CELL - 1), fill=dark, outline=(70, 80, 110, 255))
        name, d = label(a)
        sheet, row, _ = lr.strip(a)
        seq = "".join(str(poses.index(m) + 1) if m else "-" for m, _ in lr.script(a))
        for k, text in enumerate((f"{a:02X} {name}", d, seq[:10], f"${sheet:02X}/{row}")):
            dr.text((3, y0 + 4 + 13 * k), text[:10], fill=(255, 255, 255, 255) if k < 2 else (140, 150, 175, 255))
        for col, m in enumerate(poses):
            cell = lr.render(a, m)
            rgba = np.zeros((CELL, CELL, 4), np.uint8)
            for k, c in enumerate(pal):
                rgba[cell == 8 + k] = tuple(c) + (255,)
            im.paste(Image.fromarray(rgba, "RGBA"), ((col + 1) * CELL, y0))
    return im


def main():
    chars = [int(a) for a in sys.argv[1:]] or [6]
    rom = open(BASE, "rb").read()
    os.makedirs(OUT, exist_ok=True)
    for c in chars:
        path = os.path.join(OUT, f"louie{c}_sb5.png")
        export(rom, c).save(path)
        print(path)


if __name__ == "__main__":
    main()
