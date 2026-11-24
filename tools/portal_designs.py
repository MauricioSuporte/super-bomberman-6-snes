#!/usr/bin/env python3
"""Candidate SB1-style exit portals (16 x 16, <= 15 colors each) for World 1.

    python tools/portal_designs.py OUTDIR      writes <name>.png (frames side by side) + designs.json (timings)
Frame 0 of each is the still picture; `anim` = [(frame, frames shown)] looped once the portal is open.
"""
import json
import math
import os
import sys

from PIL import Image

K = (16, 16, 24)          # outline
G1, G2, G3, G4 = (72, 72, 80), (112, 112, 120), (160, 160, 168), (216, 216, 224)
W = (248, 248, 248)
B1, B2, B3, B4, B5, B6 = (24, 40, 64), (40, 72, 112), (0, 112, 168), (48, 160, 208), (104, 192, 248), (184, 232, 248)
Y1, Y2 = (248, 200, 0), (248, 136, 0)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITY = os.path.join(ROOT, "assets", "portal", "sb1_portal.png")


class F:
    def __init__(self):
        self.p = [[None] * 16 for _ in range(16)]

    def px(self, x, y, c):
        if 0 <= x < 16 and 0 <= y < 16:
            self.p[y][x] = c

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.px(x, y, c)

    def frame(self, x0, y0, x1, y1, c):
        for x in range(x0, x1 + 1):
            self.px(x, y0, c)
            self.px(x, y1, c)
        for y in range(y0, y1 + 1):
            self.px(x0, y, c)
            self.px(x1, y, c)

    def img(self):
        im = Image.new("RGBA", (16, 16))
        for y in range(16):
            for x in range(16):
                if self.p[y][x]:
                    im.putpixel((x, y), self.p[y][x] + (255,))
        return im


def hatch_base():
    """SB1's metal hatch: outlined square plate, bevel, rivets, dark hole."""
    f = F()
    f.rect(0, 0, 15, 15, K)
    f.rect(1, 1, 14, 14, G2)
    f.rect(1, 1, 14, 1, G4)
    f.rect(1, 1, 1, 14, G3)
    f.rect(1, 14, 14, 14, G1)
    f.rect(14, 1, 14, 14, G1)
    for x, y in ((2, 2), (13, 2), (2, 13), (13, 13)):
        f.px(x, y, W if (x, y) == (2, 2) else G4)
    f.frame(3, 3, 12, 12, K)
    return f


def v_sb1():
    """SB1's own exit (Unity's Portal.png): off / on every 3 frames."""
    im = Image.open(UNITY).convert("RGBA")
    out = []
    for top in (16, 0):       # off (Portal_1, lower half), on (Portal_0)
        f = F()
        for y in range(16):
            for x in range(16):
                p = im.getpixel((x, top + y))
                if p[3]:
                    f.px(x, y, p[:3])
        out.append(f)
    return out, [(0, 3), (1, 3)]


def v_pulse():
    """The hatch's core breathes: 5 blues, a white flash at the top."""
    ramps = [(B1, B2, B2), (B2, B3, B4), (B3, B4, B5), (B4, B5, B6), (B5, B6, W)]
    out = []
    for o, m, i in ramps:
        f = hatch_base()
        f.rect(4, 4, 11, 11, o)
        f.rect(5, 5, 10, 10, m)
        f.rect(6, 6, 9, 9, i)
        out.append(f)
    return out, [(0, 4), (1, 3), (2, 3), (3, 3), (4, 4), (3, 3), (2, 3), (1, 3)]


def v_arrows():
    """4 yellow arrows around the hole light up one after the other, then all blink (SB3-like)."""
    pts = {0: [(6, 4), (7, 4), (8, 4), (9, 4), (7, 5), (8, 5)],
           1: [(11, 6), (11, 7), (11, 8), (11, 9), (10, 7), (10, 8)],
           2: [(6, 11), (7, 11), (8, 11), (9, 11), (7, 10), (8, 10)],
           3: [(4, 6), (4, 7), (4, 8), (4, 9), (5, 7), (5, 8)]}

    def arrows(lit):
        f = hatch_base()
        f.rect(4, 4, 11, 11, B1)
        f.rect(6, 6, 9, 9, B3)
        f.rect(7, 7, 8, 8, B5)
        for d, ps in pts.items():
            for p in ps:
                f.px(*p, Y1 if d in lit else G1)
        return f
    out = [arrows(()), arrows((0,)), arrows((1,)), arrows((2,)), arrows((3,)), arrows((0, 1, 2, 3))]
    return out, [(1, 4), (2, 4), (3, 4), (4, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 6), (0, 3), (5, 6), (0, 3)]


def v_vortex():
    """A blue whirl turning inside the hatch (4 frames)."""
    still = hatch_base()
    still.rect(4, 4, 11, 11, B1)
    out = [still]
    for k in range(4):
        f = hatch_base()
        for y in range(4, 12):
            for x in range(4, 12):
                dx, dy = x - 7.5, y - 7.5
                r = math.hypot(dx, dy)
                a = math.atan2(dy, dx) - k * math.pi / 4 + r * 0.55
                v = (math.sin(2 * a) + 1) / 2
                c = B5 if v > 0.75 else B4 if v > 0.45 else B3 if v > 0.2 else B2
                if r < 1.2:
                    c = B6
                if r > 4.2:
                    c = B1 if v < 0.5 else B2
                f.px(x, y, c)
        out.append(f)
    return out, [(1, 3), (2, 3), (3, 3), (4, 3)]


def v_pad():
    """Round teleport pad: a ring of 8 lights chasing around a blue core."""
    lights = [(7, 1), (12, 3), (14, 7), (12, 12), (8, 14), (3, 12), (1, 8), (3, 3)]

    def pad(lit, core):
        f = F()
        for y in range(16):
            for x in range(16):
                r = math.hypot(x - 7.5, y - 7.5)
                if r < 8.0:
                    f.px(x, y, K)
                if r < 7.0:
                    f.px(x, y, G2 if y < 9 else G1)
                if r < 6.0 and y < 4:
                    f.px(x, y, G3)
                if r < 4.6:
                    f.px(x, y, K)
                if r < 3.7:
                    f.px(x, y, core[0])
                if r < 2.5:
                    f.px(x, y, core[1])
                if r < 1.2:
                    f.px(x, y, core[2])
        for i, (x, y) in enumerate(lights):
            f.px(x, y, Y1 if i in lit else (Y2 if (i + 1) % 8 in lit else G1))
        return f
    out = [pad((), (B1, B1, B2))] + [pad((i, (i + 4) % 8), (B3, B5, W) if i % 2 else (B3, B4, B6)) for i in range(4)]
    return out, [(1, 3), (2, 3), (3, 3), (4, 3)]


def v_shutter():
    """Two shutters slide open once, then the light inside blinks on / off like SB1's."""
    def shut(gap, lit):
        f = hatch_base()
        f.rect(4, 4, 11, 11, B4 if lit else B2)
        f.rect(6, 6, 9, 9, B6 if lit else B3)
        if lit:
            f.px(5, 5, W)
        r = 7 - gap
        if r >= 4:
            f.rect(4, 4, r, 11, G3)
            f.rect(r, 4, r, 11, G1)
            f.rect(15 - r, 4, 11, 11, G3)
            f.rect(15 - r, 4, 15 - r, 11, G4)
        return f
    out = [shut(g, False) for g in range(5)] + [shut(4, True)]
    return out, [(0, 8), (1, 4), (2, 4), (3, 4), (4, 4), (5, 3), (4, 3)]


DESIGNS = {
    "1_sb1": ("Escotilha do SB1", "a do SB1 / Unity: liga e desliga a cada 3 quadros", v_sb1),
    "2_pulse": ("Escotilha pulsando", "o miolo acende e apaga em 5 tons de azul, flash branco no pico", v_pulse),
    "3_arrows": ("Escotilha com setas", "4 setas amarelas acendem em volta, depois piscam juntas (estilo SB3)", v_arrows),
    "4_vortex": ("Escotilha com vórtice", "redemoinho azul girando dentro da escotilha", v_vortex),
    "5_pad": ("Plataforma de teleporte", "anel de luzes correndo em volta de um núcleo azul", v_pad),
    "6_shutter": ("Alçapão que abre", "as portinhas abrem uma vez e a luz pisca como no SB1", v_shutter),
}


def build():
    out = {}
    for k, (_, _, fn) in DESIGNS.items():
        frames, anim = fn()
        cols = {c for f in frames for r in f.p for c in r if c}
        assert len(cols) <= 15, (k, len(cols))
        out[k] = (frames, anim, len(cols))
    return out


if __name__ == "__main__":
    dst = sys.argv[1]
    meta = {}
    for k, (frames, anim, ncol) in build().items():
        sheet = Image.new("RGBA", (16 * len(frames), 16))
        for i, f in enumerate(frames):
            sheet.paste(f.img(), (16 * i, 0))
        sheet.save(os.path.join(dst, k + ".png"))
        meta[k] = {"title": DESIGNS[k][0], "desc": DESIGNS[k][1], "frames": len(frames), "anim": anim,
                   "colors": ncol}
    with open(os.path.join(dst, "designs.json"), "w", encoding="utf-8") as h:
        json.dump(meta, h, ensure_ascii=False, indent=1)
