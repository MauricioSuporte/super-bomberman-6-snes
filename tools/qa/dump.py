"""Reads the dumps of the QA engine's `dump` step (tools/mesen/qa.lua OPS.dump)."""
import numpy as np

VRAM, CG, OAM, WRAM = 0x10000, 512, 544, 0x2000


class Dump:
    def __init__(self, path):
        d = open(path, "rb").read()
        if d[:4] != b"QAD1":
            raise ValueError(f"{path}: not a QA dump")
        o = 4
        self.vram = np.frombuffer(d[o:o + VRAM], np.uint8)
        o += VRAM
        self.cg = np.frombuffer(d[o:o + CG], "<u2").astype(np.int32)
        o += CG
        self.oam = d[o:o + OAM]
        o += OAM
        self.wram = d[o:o + WRAM]
        o += WRAM
        self.bg1sc, self.bg2sc_reg, self.nba12, self.nba34, self.bg3sc, self.bgmode = d[o:o + 6]

    def w(self, a):
        return self.wram[a] | self.wram[a + 1] << 8

    def bg_sc(self, layer):
        """BGnSC of BG1 (0) / BG2 (1) / BG3 (2); BG2's from WRAM $0369 (the stage IRQ writes it)."""
        return (self.bg1sc, self.wram[0x0369], self.bg3sc)[layer]

    def map_word(self, layer, tx, ty):
        sc = self.bg_sc(layer)
        base = (sc >> 2) << 10
        size = sc & 3
        q = 0
        if size & 1 and tx >= 32:
            q += 1
        if size & 2 and ty >= 32:
            q += 2 if size & 1 else 1
        a = base + q * 0x400 + (ty & 31) * 32 + (tx & 31)
        a = (a & 0x7FFF) * 2
        return int(self.vram[a]) | int(self.vram[a + 1]) << 8

    def chr_base(self, layer):
        """Word address of BGn's tiles."""
        return ((self.nba12 >> (4 * layer)) & 0xF) << 12

    def tile(self, layer, n):
        """8 x 8 color indices of BG tile n of the layer (4bpp)."""
        a = ((self.chr_base(layer) + 16 * n) & 0x7FFF) * 2
        return planar(self.vram[a:a + 32])

    def obj_tile(self, n, name_base):
        a = ((name_base + 16 * n) & 0x7FFF) * 2
        return planar(self.vram[a:a + 32])


def planar(raw):
    raw = np.asarray(raw, np.uint8)
    t = np.zeros((8, 8), np.int32)
    for y in range(8):
        for p in range(4):
            v = int(raw[(2 * y if p < 2 else 16 + 2 * y) + (p & 1)])
            for x in range(8):
                t[y, x] |= ((v >> (7 - x)) & 1) << p
    return t
