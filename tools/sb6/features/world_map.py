"""World map: ZONE1 = Super Bomberman 1's World 1 map, ZONE2 = Super Bomberman 2's.

SB5's map script ($C7:1440, task 9, mode 3) loads, for every zone (also on
each L/R zone change, while the screen is dark), the lava background (set 3
archive $0E + arrangement $0E of set 4 on BG2) and, at $C7:148C, the BG3
archives $4C/$4D/$0D and palette $0F (CGRAM 0-15, whose entries 1-11 are also
the BG3 text colors); then it jumps on the zone ($1036, table at $C7:149B).
Zones 1 and 2 begin with

    27 nn  2A nn  FF 8D nn 04 01 00 00   island tiles, palettes 1-5, BG1
    ...
    2C 02 01  2C 03 01                   lava palette cycles (CGRAM $11-$1A)
    2C 09 01                             stage marker blink (OBJ CGRAM $92-$95)

The hack:
* $C7:1481 calls a script that runs `FF 1A F5` and then the same loads
  (first, since SB5 draws the lava arrangement relative to BG2's V scroll,
  which ZONE2's stars move) (wmap_op, asm/world_map.asm): per zone, the animation of asm/world_map.asm
  ($0190), CGADSUB shadow $0314 (SB5 subtracts half of BG2: the dark lava;
  off on ZONE1/ZONE2) and BG2 V scroll $0321, then the map music
  (asm/title_music.asm map_music: SB1's driver on ZONE1, SB2's on ZONE2,
  SB5's own map song elsewhere; switching drivers takes ~1-1.5 s of the dark
  screen);
* the first line of zones 1 and 2 calls a script that loads graphics set 1
  (null in the cartridge's three set tables): archives = BG1/BG2 tiles
  (raw) in the tiles SB5 reloads on every zone change (TILE_RANGES: $100-$1FF,
  the island's, then 1-$40, the lava's; tile 0 stays blank); palette n = BG palettes from 1
  (palette 0 stays the BG3 text's), arrangements on BG2 (sea / stars) and BG1 (island / ships);
* the lava cycles of zones 1 and 2 are skipped.

ZONE1: assets/world_map/zone1_sb1.png (SB1's island, clouds and tower) with
start_sign.png (SB5's START sign) on top; the sea is water.png, one 16x16
tile whose 7 frames the NMI sends every FRAME_TIME frames.
ZONE2: zone2_ships.png (SB2's ships, OBJ there, BG1 here) over zone2_stars.png
(BG2, 256x256, scrolled up half a pixel per frame like SB2's); the lights of
zone2_lights.png cycle their colors from zone2_lights.json (one color per
frame and light, 64 frames), written to CGRAM by the NMI.

Music: tools/extract_world_map.py made assets/sound/sb1_world_map.bin (SB1's
sound RAM $0800-$A1BB as SB1 uploads it at boot; song $87 on port 0) and
sb2_world_map.bin + _ff00.bin (SB2's $0800-$E6DF and $FF00-$FF38 while its map
song plays; song $02). sound() builds, per driver, an IPL upload list (a small
loader at $0200, plus extra blocks) and the image cut in parts for the loader
(3 bytes per handshake), and a table for asm/title_music.asm.
"""
import json
import os
import struct

import numpy as np
from PIL import Image

from .. import asar
from ..rombuild import BuildError
from ..romlib import off
from ..snesgfx import encode_4bpp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASM = os.path.join(ROOT, "asm", "world_map.asm")
SET = 1                   # graphics set of the map (null in the cartridge)
FIRST_PAL = 1             # BG palettes 1-7 (palette 0 = lava/BG3 text colors, kept)
MAX_PALS = 7
# BG tiles SB5 reloads on every zone change (VRAM words; chr base 0): $1000-$1FFF (tiles $100-$1FF, the
# zone's island) and $0000-$040F (tiles 0-$40, the lava); tiles $41-$FF and $200-$2FF are loaded once
# per map and must stay. Packed tile n goes to TILE_RANGES in order.
TILE_RANGES = ((0x100, 0x100), (0x001, 0x40))      # (first tile, count); tile 0 stays SB5's blank
# (the stages' BG3 map is mostly tile 0 and they do not reload it)
TILE_BASE = TILE_RANGES[0][0]
MAX_TILES = sum(n for _, n in TILE_RANGES)


def _vt(i):
    for first, n in TILE_RANGES:
        if i < n:
            return first + i
        i -= n
    raise BuildError("world map: too many tiles")


ROWS = 30                 # BG1 map rows drawn (V scroll 0 shows map lines 1-224)
WATER_TILE = 1            # ZONE1: tiles 1-4 = the sea tile (top left, top right, bottom left, bottom right)
FRAME_TIME = 12           # frames per sea frame (SB1: ~12, measured in Mesen)
WMAP_OP = 0xF5            # FF 1A F5 (asm/picker.asm pick_op)
COMMON_AT = 0xC71481
COMMON_ORIG = bytes.fromhex("26 03 27 0E FF 8D 0E 04 02 00 00 27 4C 27 4D 27 0D 2A 0F")
# FF 1A F5 runs first: SB5 draws the lava arrangement (FF 8D 0E) relative to BG2's V scroll ($0321),
# which ZONE2's stars leave anywhere
ZONES = {   # zone: (first line, its bytes, lava cycles address)
    1: (0xC714A9, bytes.fromhex("27 0F 2A 10 FF 8D 0F 04 01 00 00"), 0xC714B9),
    2: (0xC714D2, bytes.fromhex("27 10 2A 11 FF 8D 10 04 01 00 00"), 0xC714EB),
}
CYCLES_ORIG = bytes.fromhex("2C 02 01 2C 03 01")
MAP_REQ = 0x04            # SB5's map music: request group 0 id 4
STUB_AT = 0x1100          # Hudson driver code that its loader ($0FF0-$1043) does not use
LOADER_AT = 0x0200        # under SB1's / SB2's drivers
# foreign drivers (index 1, 2): sound RAM image, extra IPL blocks, entry, ready ports 2/3, song, echo
# xor of port 0, SFX for SB5's menu move / accept (SB1: port 1 commands 0 / 1; SB2: port 0 $51 / $52)
# $1036 = zone - 1: (animation start, driver, CGADSUB); the other zones (0, 0, $C2)
ZONE_TABLE = {0: (1, 1, 0x00), 1: (3, 2, 0x00)}
# the SPC's boot ROM ($FFC0-$FFFF): SB2's driver leaves it switched off ($F1 = $33), so its "back to the
# IPL" command 6 would jump into RAM; a copy goes there with the driver
IPL_ROM = bytes.fromhex("CD EF BD E8 00 C6 1D D0 FC 8F AA F4 8F BB F5 78 CC F4 D0 FB 2F 19 EB F4 D0 FC 7E F4 D0 0B"
                        "E4 F5 CB F4 D7 00 FC D0 F3 AB 01 10 EF 7E F4 10 EB BA F6 DA 00 BA F4 C4 F4 DD 5D D0 DB 1F"
                        "00 00 C0 FF")
DRIVERS = [
    dict(name="SB1", image="sb1_world_map.bin", extra=(), entry=0x0812, ready=(0x68, 0x09), song=0x87,
         echo=0x00, sfx=(0x00, 0x01)),
    dict(name="SB2", image="sb2_world_map.bin", extra=((0xFF00, "sb2_world_map_ff00.bin"), (0xFFC0, IPL_ROM)), entry=0x0800,
         ready=(0xAA, 0xAA), song=0x02, echo=0x80, sfx=(0x51, 0x52)),
]
# driver 3: SB6's menu accept recording when a stage is chosen on ZONE2 (asm/title_music.asm
# fd_sound .accept): one S-DSP voice, then back to the IPL ROM, whose $AA on port 0 is the "echo"
ACCEPT = dict(name="accept SFX", extra=(), entry=0x0800, ready=(0x53, 0x36), song=0x00, echo=0xAA, sfx=(0, 0))
ACCEPT_DIR = 0x0900       # S-DSP sample directory page; the sample follows its one entry
ACCEPT_MVOL, ACCEPT_VOL = 0x60, 0x7F   # as the stream driver plays the menu SFX
DRV_ENTRY = 24            # bytes per driver in the table (asm/title_music.asm)


# SB5's own ZONE1 / ZONE2 data, unused since apply() replaces both zones: set 3 archives $0F / $10 (island
# tiles, LZ), set 3 palettes $10 / $11, set 4 arrangements $0F / $10 (islands, BG1). The same tiles and
# palettes are also listed in sets 0 (archives $6E / $6F) and 6 (archives $12 / $13, palettes $3E / $3F),
# but no script loads them there (set 6 is only selected natively at $C5:13DE, for its ids 1 / 2) and the
# only script lines that load them are the zone lines apply() bypasses. Each block is contiguous.
OLD_ZONE_DATA = [
    ("free_d3", 0xD3C670, 7838, 0x121EA85B, "freed SB5 ZONE1/ZONE2 island tiles (set 3 archives $0F/$10)"),
    ("free_e2", 0xE21371, 1952, 0x025298F6, "freed SB5 ZONE1/ZONE2 island arrangements (set 4 $0F/$10)"),
    ("free_81", 0xC1985E, 328, 0x734615E7, "freed SB5 ZONE1/ZONE2 palettes (set 3 $10/$11), bank $81"),
]


def free_old_zones(rb):
    """Fills SB5's unused ZONE1 / ZONE2 data with $FF and declares it as free regions (the table
    entries stay: nothing loads them)."""
    for name, start, size, crc, purpose in OLD_ZONE_DATA:
        rb.free_old(name, start, size, crc, purpose)


def _accept_sample(sound_dir, cache_dir):
    """SB6's menu accept recording: (BRR ending in END without loop, S-DSP pitch)."""
    from .title_music import menu_samples
    return next((d, p) for sid, d, p, *_ in menu_samples(sound_dir, cache_dir) if sid == 4)


# SB1's sound RAM ($0800 header: instrument table $2200, directory $2300 (DIR $23), SFX $89F0,
# SFX map $A03C, instrument map $A0BC, sample map $A13C). SFX n: sequence = word $89F2 +
# 2 * [$A03C + n]: 8B instrument, 86 vol L R, 89 ADSR2 ADSR1, 80 raw pitch, 8D key on, 91 wait
# (ticks, ~22 ms), 8E key off, 92 end; SFX 1 (accept) plays on voice 0, the map song on 1-7.
SB1_ACCEPT_SEQ = 0x8A14
SB1_ACCEPT_TICKS = 34


def _sb1_accept(image, sound_dir, cache_dir):
    """SB1's accept SFX (port 1 command 1) plays SB6's recording, so the map song goes on: a new
    instrument 6 (instrument table moved to $A200, record $A210 = instrument 4's with sample 8),
    the directory moved to $A300 with entry 8 = the recording at $A330; SFX 1 = one note."""
    brr, pitch = _accept_sample(sound_dir, cache_dir)
    base = 0x0800
    img = bytearray(image)

    def at(a):
        return a - base

    def put(a, b, expect=None):
        if expect is not None and bytes(img[at(a):at(a) + len(expect)]) != expect:
            raise BuildError(f"world map: SB1's sound RAM at ${a:04X} is not as expected")
        img[at(a):at(a) + len(b)] = b

    if len(img) > at(0xA200):
        raise BuildError("world map: SB1's sound RAM reaches $A200")
    put(0x0E09, bytes([0xF6, 0x00, 0xA2]), bytes([0xF6, 0x00, 0x22]))      # instrument table
    put(0x0E0E, bytes([0xF6, 0x01, 0xA2]), bytes([0xF6, 0x01, 0x22]))
    put(0x1FA6, bytes([0xE8, 0xA3]), bytes([0xE8, 0x23]))                  # DIR
    put(0xA0BC + 6, b"\x06", bytes([0xFF]))                                     # instrument 6
    put(0xA13C + 8, b"\x08", bytes([0xFF]))                                     # sample 8
    record = bytearray(img[at(0x227C):at(0x227C) + 16])
    record[12] = 8
    seq = bytes([0xF5, 0x07, 0x8B, 0x06, 0x86, 0x7F, 0x7F, 0x89, 0xE0, 0xFF, 0x80, pitch & 0xFF, pitch >> 8,
                 0x8D, 0x91, SB1_ACCEPT_TICKS, 0x8E, 0x91, 0x02, 0x92])
    put(SB1_ACCEPT_SEQ, seq, bytes.fromhex("F5 07 8B 04 86 7F 7F 89 94 DD"))
    img += bytes(at(0xA200) - len(img))
    table = bytes(img[at(0x2200):at(0x2200) + 12]) + struct.pack("<H", 0xA210)
    directory = bytes(img[at(0x2300):at(0x2300) + 32]) + struct.pack("<HH", 0xA330, 0xA330)
    img += table.ljust(16, b"\x00") + bytes(record)
    img += bytes(at(0xA300) - len(img)) + directory.ljust(0x30, b"\x00") + brr
    return bytes(img)


def _accept_image(sound_dir, cache_dir):
    """SPC program at $0800 + directory + BRR: keys SB6's accept recording on voice 0 (pitch and
    sample as asm/spc/stream.asm plays it), sets the ready ports and jumps to the IPL ROM."""
    brr, pitch = _accept_sample(sound_dir, cache_dir)
    dsp = [(0x5C, 0xFF), (0x6C, 0x20), (0x0C, ACCEPT_MVOL), (0x1C, ACCEPT_MVOL), (0x2C, 0), (0x3C, 0),
           (0x4D, 0), (0x3D, 0), (0x2D, 0), (0x5D, ACCEPT_DIR >> 8),
           (0x00, ACCEPT_VOL), (0x01, ACCEPT_VOL), (0x02, pitch & 0xFF), (0x03, pitch >> 8), (0x04, 0),
           (0x05, 0xFF), (0x06, 0xE0), (0x5C, 0x00), (0x4C, 0x01)]
    code = b"".join(bytes([0x8F, r, 0xF2, 0x8F, v, 0xF3]) for r, v in dsp)
    code += bytes([0x8F, ACCEPT["ready"][0], 0xF6, 0x8F, ACCEPT["ready"][1], 0xF7, 0x5F, 0xC0, 0xFF])
    if 0x0800 + len(code) > ACCEPT_DIR:
        raise BuildError("world map: accept SFX program too long")
    start = ACCEPT_DIR + 16
    return code.ljust(ACCEPT_DIR - 0x0800, b"\x00") + struct.pack("<HH", start, start).ljust(16, b"\x00") + brr


def _bgr(c):
    r, g, b = (round(int(v) * 31 / 255) for v in c[:3])
    return r | g << 5 | b << 10


def _list(blocks, tail=b""):
    return b"".join(struct.pack("<HH", len(d), a) + d for a, d in blocks) + b"\x00\x00" + tail


def _loader(dest, n, entry):
    """$0200: n triples on ports 1-3 to dest (sequence on port 0 from 0, echoed); one more
    handshake, then port 0 = 0, ports 2/3 out = 0, JMP entry (the driver starts with ports 0-3 = 0)."""
    code = bytes([0xCD, 0x00,                          # MOV X,#0       sequence
                  0x8F, dest & 0xFF, 0x00,              # MOV $00,#lo    destination
                  0x8F, dest >> 8, 0x01,                # MOV $01,#hi
                  0x8F, n & 0xFF, 0x02,                 # MOV $02,#lo    triples
                  0x8F, n >> 8, 0x03,                   # MOV $03,#hi
                  0x8D, 0x00,                           # MOV Y,#0
                  0x3E, 0xF4, 0xD0, 0xFC]               # $0210: CMP X,$F4 / BNE
                 + [0xE4, 0xF5, 0xD7, 0x00, 0xFC, 0xD0, 0x02, 0xAB, 0x01]   # MOV A,$F5 / MOV [$00]+Y,A / INC Y / BNE / INC $01
                 + [0xE4, 0xF6, 0xD7, 0x00, 0xFC, 0xD0, 0x02, 0xAB, 0x01]
                 + [0xE4, 0xF7, 0xD7, 0x00, 0xFC, 0xD0, 0x02, 0xAB, 0x01]
                 + [0xD8, 0xF4, 0x3D, 0x1A, 0x02, 0xD0, 0xDA,   # MOV $F4,X / INC X / DECW $02 / BNE $0210
                    0x3E, 0xF4, 0xD0, 0xFC,                     # $0236: CMP X,$F4 / BNE   (final kick)
                    0xD8, 0xF4,                                 # MOV $F4,X
                    0xE4, 0xF4, 0xD0, 0xFC,                     # $023C: MOV A,$F4 / BNE   (port 0 = 0)
                    0x8F, 0x00, 0xF6, 0x8F, 0x00, 0xF7,         # MOV $F6,#0 / MOV $F7,#0
                    0x5F, entry & 0xFF, entry >> 8])            # JMP entry
    assert code[0x34] == 0xD0 and code[0x36] == 0x3E and code[0x3C] == 0xE4 and len(code) == 0x49
    return code


def sound(rb, snd_dir, regions, cache_dir):
    """Driver table + upload data for asm/title_music.asm. regions: one list of regions per driver."""
    stub = bytes([0x8F, 0x6C, 0xF2,      # MOV $F2,#$6C
                  0x8F, 0xE0, 0xF3,      # MOV $F3,#$E0: FLG soft reset, mute, no echo writes
                  0x8F, 0xB0, 0xF1,      # MOV $F1,#$B0: IPL ROM on, input ports cleared
                  0x5F, 0xC0, 0xFF])     # JMP $FFC0
    l_stub = _list([(STUB_AT, stub), (0x1041, bytes([0x5F, STUB_AT & 0xFF, STUB_AT >> 8]))],
                   struct.pack("<H", STUB_AT))
    stub_at = rb.alloc("bulk", l_stub, "map music: upload list = IPL stub at $1100 + JMP over Hudson's loader RET")
    table = bytearray()
    info = []
    for drv, regs in zip(DRIVERS + [ACCEPT], regions):
        image = (open(os.path.join(snd_dir, drv["image"]), "rb").read() if "image" in drv
                 else _accept_image(snd_dir, cache_dir))
        if drv["name"] == "SB1":
            image = _sb1_accept(image, snd_dir, cache_dir)
        size = len(image)
        image += bytes(-len(image) % 3)
        n = len(image) // 3
        blocks = [(LOADER_AT, _loader(0x0800, n, drv["entry"]))]
        blocks += [(a, f if isinstance(f, bytes) else open(os.path.join(snd_dir, f), "rb").read())
                   for a, f in drv["extra"]]
        load = rb.alloc("bulk", _list(blocks, struct.pack("<H", LOADER_AT)),
                        f"map music: {drv['name']} upload list = loader at $0200"
                        + "".join(f" + ${a:04X}" for a, _ in drv["extra"]))
        parts = []
        done = 0
        for r in regs:
            k = min(n - done, rb.regions[r].free() // 3)
            if k <= 0:
                continue
            a = rb.alloc(r, image[3 * done:3 * (done + k)],
                         f"map music: {drv['name']} sound RAM ${0x0800 + 3 * done:04X}-${0x0800 + 3 * (done + k) - 1:04X}")
            parts.append((a, k))
            done += k
            if done == n:
                break
        if done != n or len(parts) > 3:
            raise BuildError(f"world map: {drv['name']}'s sound RAM image does not fit in {regs}")
        parts += [(0, 0)] * (3 - len(parts))
        e = load.to_bytes(3, "little")
        for a, k in parts:
            e += a.to_bytes(3, "little") + struct.pack("<H", k)
        e += bytes([drv["ready"][0], drv["ready"][1], drv["song"], drv["echo"], drv["sfx"][0], drv["sfx"][1]])
        assert len(e) == DRV_ENTRY
        table += e
        info.append((drv["name"], size, len([p for p in parts if p[1]])))
    t = rb.alloc("bulk", bytes(table), "map music: driver table (asm/title_music.asm fd_table)")
    defs = {"FD": "1", "FD_TABLE": f"${t:06X}", "FD_STUB": f"${stub_at:06X}", "MAP_REQ": f"${MAP_REQ:02X}"}
    return {"defs": defs, "drivers": info}


def _dist(c, d):
    return sum(((c >> s & 31) - (d >> s & 31)) ** 2 for s in (0, 5, 10))


def _fit(sets, cap=15, seeds=(), most=99):
    """Greedy packing of color sets into palettes of <= cap colors, starting from the seed
    palettes. A set that fits nowhere once `most` palettes exist goes to the palette sharing the
    most colors with it (its other colors are drawn with that palette's closest ones)."""
    pals = [set(p) for p in seeds]
    where = [None] * len(sets)
    for i in sorted(range(len(sets)), key=lambda k: -len(sets[k])):
        s = sets[i]
        best = None
        for p, have in enumerate(pals):
            u = len(have | s)
            if u <= cap and (best is None or u - len(have) < best[0]):
                best = (u - len(have), p)
        if best is not None:
            pals[best[1]] |= s
            where[i] = best[1]
        elif len(pals) < most:
            pals.append(set(s))
            where[i] = len(pals) - 1
        else:
            where[i] = max(range(len(pals)), key=lambda p: len(pals[p] & s))
    return pals, where


class Packer:
    """BG tiles of one zone: cells of color keys (BGR15, or LIGHT + n for a cycling color, -1 =
    transparent), packed into <= MAX_PALS palettes; tiles deduplicated with flips."""
    LIGHT = 0x10000

    def __init__(self, name):
        self.name = name
        self.cells = []           # (layer, tx, ty, keys 8x8)
        self.sets = []
        self.tiles = [bytes(32)]  # tile 0 = empty
        self.known = {}
        self.merged = 0

    def add_layer(self, layer, keys, rows):
        for ty in range(rows):
            for tx in range(32):
                k = keys[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                if (k < 0).all():
                    continue
                cols = set(k[k >= 0].tolist())
                while len(cols) > 15:     # overlapping sprites: the least used color -> the closest one
                    plain = [c for c in cols if c < self.LIGHT]
                    c = min(plain, key=lambda c: (k == c).sum())
                    d = min((d for d in plain if d != c), key=lambda d: _dist(c, d))
                    k[k == c] = d
                    cols.discard(c)
                    self.merged += 1
                self.cells.append((layer, tx, ty, k))
                self.sets.append(cols)

    def add_set(self, cols):
        self.sets.append(set(cols))
        return len(self.sets) - 1

    def fit(self, light_start=(), seeds=()):
        self.pals, self.where = _fit(self.sets, seeds=seeds, most=MAX_PALS if seeds else 99)
        if len(self.pals) > MAX_PALS:
            raise BuildError(f"world map {self.name}: {len(self.pals)} palettes needed, {MAX_PALS} free")
        self.order = [sorted(p) for p in self.pals]
        self.lookup = [{c: i + 1 for i, c in enumerate(p)} for p in self.order]
        self.approx = 0
        for (lay, tx, ty, k), p in zip(self.cells, self.where):    # colors left out: the closest one
            for c in set(k[k >= 0].tolist()) - set(self.order[p]):
                plain = [d for d in self.order[p] if d < self.LIGHT]
                k[k == c] = min(plain, key=lambda d: _dist(c if c < self.LIGHT else light_start[c - self.LIGHT], d))
                self.approx += 1
        self.colors = []
        for p in self.order:
            self.colors += [0] + [light_start[c - self.LIGHT] if c >= self.LIGHT else c for c in p] + [0] * (15 - len(p))
        return self

    def light_cgram(self, n):
        """CGRAM addresses of light n (it may sit in several palettes)."""
        return [16 * (FIRST_PAL + p) + 1 + i for p, pal in enumerate(self.order)
                for i, c in enumerate(pal) if c == self.LIGHT + n]

    def tile_word(self, idx, pal):
        a = np.array(idx, np.uint8)
        for flip, arr in ((0, a), (0x4000, a[:, ::-1]), (0x8000, a[::-1, :]), (0xC000, a[::-1, ::-1])):
            k = arr.tobytes()
            if k in self.known:
                return _vt(self.known[k]) | flip | pal << 10
        self.known[a.tobytes()] = len(self.tiles)
        self.tiles.append(encode_4bpp(a.tolist()))
        return _vt(len(self.tiles) - 1) | pal << 10

    def layer_map(self, layer, rows):
        words = [TILE_BASE] * (32 * rows)             # its tile 0 is blank
        for (lay, tx, ty, k), s in zip(self.cells, self.where):
            if lay != layer:
                continue
            p = s
            idx = [[self.lookup[p][int(k[y, x])] if k[y, x] >= 0 else 0 for x in range(8)] for y in range(8)]
            words[ty * 32 + tx] = self.tile_word(idx, FIRST_PAL + p)
        return words

    def check(self):
        if len(self.tiles) > MAX_TILES:
            raise BuildError(f"world map {self.name}: {len(self.tiles)} tiles, {MAX_TILES} free")


def _keys(rgba):
    """RGBA picture -> BGR15 keys (-1 where alpha = 0)."""
    a = rgba.astype(int)
    r, g, b = (np.round(a[:, :, i] * 31 / 255).astype(int) for i in range(3))
    k = r | g << 5 | b << 10
    k[a[:, :, 3] == 0] = -1
    return k


def build_zone1(asset_dir):
    fg = np.array(Image.open(os.path.join(asset_dir, "zone1_sb1.png")).convert("RGBA"))
    sign = np.array(Image.open(os.path.join(asset_dir, "start_sign.png")).convert("RGBA"))
    m = sign[:, :, 3] > 0
    fg[m] = sign[m]
    pic = np.zeros((ROWS * 8, 256, 4), np.uint8)       # screen line y = map line y + 1
    pic[1:225] = fg[:224]
    water = np.array(Image.open(os.path.join(asset_dir, "water.png")).convert("RGB"))
    nframes = water.shape[1] // 16
    pk = Packer("ZONE1")
    pk.add_layer(1, _keys(pic), ROWS)
    wset = pk.add_set({_bgr(water[y, x]) for y in range(16) for x in range(water.shape[1])})
    pk.fit()
    wpal = pk.where[wset]
    frames = []
    for f in range(nframes):
        blk = b""
        for oy, ox in ((0, 0), (0, 8), (8, 0), (8, 8)):
            blk += encode_4bpp([[pk.lookup[wpal][_bgr(water[oy + y, 16 * f + ox + x])] for x in range(8)]
                                for y in range(8)])
        frames.append(blk)
    pk.tiles += [frames[0][32 * k:32 * k + 32] for k in range(4)]
    bg1 = pk.layer_map(1, ROWS)
    bg2 = [(TILE_BASE + WATER_TILE + (tx & 1) + 2 * (ty & 1)) | (FIRST_PAL + wpal) << 10
           for ty in range(ROWS) for tx in range(32)]
    pk.check()
    preview = np.zeros((224, 256, 3), np.uint8)
    for y in range(224):
        for x in range(256):
            preview[y, x] = water[(y + 1) % 16, x % 16]
    p = pic[1:225]
    a = p[:, :, 3] > 0
    preview[a] = p[a][:, :3]
    return dict(pk=pk, arrs=[(32, ROWS, bg2), (32, ROWS, bg1)], frames=frames, preview=preview)


def build_zone2(asset_dir):
    ships = np.array(Image.open(os.path.join(asset_dir, "zone2_ships.png")).convert("RGBA"))
    lights = np.array(Image.open(os.path.join(asset_dir, "zone2_lights.png")).convert("L")).astype(int)
    stars = np.array(Image.open(os.path.join(asset_dir, "zone2_stars.png")).convert("RGBA"))
    opal = np.array(Image.open(os.path.join(asset_dir, "zone2_palettes.png")).convert("L")).astype(int)
    lj = json.load(open(os.path.join(asset_dir, "zone2_lights.json")))
    table = lj["lights"]
    keys = _keys(ships)
    keys[lights > 0] = Packer.LIGHT + lights[lights > 0] - 1
    skeys = _keys(stars)
    seeds = [set(keys[opal == p].tolist()) for p in range(1, 6) if (opal == p).any()] + [set(skeys.flatten().tolist())]
    pic = np.full((ROWS * 8, 256), -1, int)
    pic[1:225] = keys[:224]
    pk = Packer("ZONE2")
    pk.add_layer(1, pic, ROWS)
    pk.add_layer(2, skeys, 32)
    pk.fit([t[0] for t in table], seeds)
    bg1 = pk.layer_map(1, ROWS)
    bg2 = pk.layer_map(2, 32)
    pk.check()
    writes = [(a, n) for n in range(len(table)) for a in pk.light_cgram(n)]
    period = lj["period"]
    blob = b"".join(bytes([a]) + struct.pack("<H", table[n][f]) for f in range(period) for a, n in writes)
    preview = stars[:224, :, :3].copy()
    s = ships[:224]
    m = s[:, :, 3] > 0
    preview[m] = s[m][:, :3]
    preview = preview.copy()
    return dict(pk=pk, arrs=[(32, 32, bg2), (32, ROWS, bg1)], lights=blob, nwrites=len(writes), period=period,
                preview=preview)


def apply(rb, asset_dir, out_dir, regions, map_music):
    from .title import arrangement, call, skip
    os.makedirs(out_dir, exist_ok=True)
    z1, z2 = build_zone1(asset_dir), build_zone2(asset_dir)
    Image.fromarray(np.concatenate([z1["preview"], z2["preview"]], 1)).save(
        os.path.join(out_dir, "world_map_preview.png"))
    zones = [z1, z2]

    arcs, pals, arrs, zarcs = [], [], [], []
    for n, z in enumerate(zones, 1):
        pk = z["pk"]
        ids = []
        rest = pk.tiles
        for first, cnt in TILE_RANGES:
            if not rest:
                break
            part, rest = rest[:cnt], rest[cnt:]
            at = rb.alloc(regions, b"".join(part), f"world map ZONE{n}: BG tiles ${first:03X}-${first + len(part) - 1:03X} "
                                                   f"(raw 4bpp)")
            arcs.append(struct.pack("<HH", 16 * first, 32 * len(part)) + at.to_bytes(3, "little") + bytes([0x82]))
            ids.append(len(arcs))
        zarcs.append(ids)
        pals.append(struct.pack("<HH", 16 * FIRST_PAL, 16 * len(pk.order))
                    + b"".join(struct.pack("<H", c) for c in pk.colors))
        arrs += [arrangement(w, h, 0, 0, words) for w, h, words in z["arrs"]]
    arc_table = rb.alloc("e3_tables", b"".join(arcs), "set 1 archive table: world map tiles "
                         + ", ".join(f"ZONE{n + 1} {ids}" for n, ids in enumerate(zarcs)))

    pblob = bytearray(2 * len(pals)) + b"".join(pals)
    pal_table = rb.alloc("bank81", bytes(pblob), "set 1 palette table: 1 / 2 = world map ZONE1 / ZONE2 BG palettes")
    pos = pal_table + 2 * len(pals)
    for i, p in enumerate(pals):
        pblob[2 * i:2 * i + 2] = struct.pack("<H", pos & 0xFFFF)
        pos += len(p)
    o = off(pal_table)
    rb.d[o:o + len(pblob)] = pblob

    blob = bytearray(2 * len(arrs)) + b"".join(arrs)
    arr_table = rb.alloc(regions, bytes(blob), "set 1 arrangement table: 1 sea (BG2), 2 island (BG1), "
                                               "3 stars (BG2), 4 ships (BG1)")
    pos = arr_table + 2 * len(arrs)
    for i, a in enumerate(arrs):
        blob[2 * i:2 * i + 2] = struct.pack("<H", pos & 0xFFFF)
        pos += len(a)
    if (arr_table & 0xFFFF) + len(blob) > 0x10000:
        raise BuildError("world map: arrangements cross a bank")
    o = off(arr_table)
    rb.d[o:o + len(blob)] = blob
    rb.patch(0xC01C96 + 2 * SET, b"\x00\x00", struct.pack("<H", arc_table & 0xFFFF), "archive set 1 -> $E3 table")
    rb.patch(0xC00379 + 2 * SET, b"\x00\x00", struct.pack("<H", pal_table & 0xFFFF), "palette set 1 -> $81 table")
    rb.patch(0xC08000 + 3 * SET, b"\x00\x00\x00", arr_table.to_bytes(3, "little"), "arrangement set 1 -> table")

    frames_at = rb.alloc(regions, b"".join(z1["frames"]), f"world map ZONE1: sea tile, {len(z1['frames'])} frames x 128 bytes")
    lights_at = rb.alloc(regions, z2["lights"], f"world map ZONE2: light colors, {z2['period']} frames x "
                                                f"{z2['nwrites']} CGRAM writes")
    for a, n in ((frames_at, len(b"".join(z1["frames"]))), (lights_at, len(z2["lights"]))):
        if (a & 0xFFFF) + n > 0x10000:
            raise BuildError("world map: animation data crosses a bank")

    common = bytes([0xFF, 0x1A, WMAP_OP]) + COMMON_ORIG + bytes([0x00])
    c_addr = rb.alloc("bulk", common, "world map: zone setup script (FF 1A F5, then SB5's lava, BG3, palette 0)")
    rb.patch(COMMON_AT, COMMON_ORIG, call(c_addr) + skip(13) + bytes(13), "world map: zone setup calls FF 1A F5 first")
    for n in (1, 2):
        at, orig, cycles = ZONES[n]
        script = bytes([0x26, SET] + [b for i in zarcs[n - 1] for b in (0x27, i)] + [0x2A, n,
                        0xFF, 0x8D, 2 * n - 1, SET, 0x02, 0x00, 0x00,
                        0xFF, 0x8D, 2 * n, SET, 0x01, 0x00, 0x00,
                        0x26, 0x03, 0x00])
        s_addr = rb.alloc("bulk", script, f"world map: ZONE{n} script (set 1 archives {zarcs[n - 1]}, palette {n}, arrangements "
                                          f"{2 * n - 1} BG2, {2 * n} BG1)")
        rb.patch(at, orig, call(s_addr) + skip(5) + bytes(5), f"world map: ZONE{n} loads its SB{n} map")
        rb.patch(cycles, CYCLES_ORIG, skip(4) + bytes(4), f"world map: ZONE{n} without the lava palette cycles")

    zt = bytearray()
    for zone in range(8):
        zt += bytes(ZONE_TABLE.get(zone, (0, 0, 0xC2)))
    region = rb.regions["bulk"]
    defines = {"ORG": f"${region.cursor:06X}", "FRAMES": f"${frames_at:06X}", "NFRAMES": str(len(z1["frames"])),
               "FTIME": str(FRAME_TIME), "WVRAM": f"${(TILE_BASE + WATER_TILE) * 16:04X}",
               "LIGHTS": f"${lights_at:06X}", "NLW": str(z2["nwrites"]), "LPERIOD": str(z2["period"]),
               "MAP_MUSIC": f"${map_music:06X}", "ZT": ",".join(f"${b:02X}" for b in zt)}
    runs, syms = asar.assemble_into(rb.d, ASM, defines)
    start, end = region.cursor, syms["end"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"world_map.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "world map: animations and FF 1A F5 (asm/world_map.asm)")
    return dict(wmap_nmi=syms["wmap_nmi"], wmap_op=syms["wmap_op"],
                zones=[(len(z["pk"].tiles), len(z["pk"].order)) for z in zones], frames=len(z1["frames"]),
                lights=z2["nwrites"])
