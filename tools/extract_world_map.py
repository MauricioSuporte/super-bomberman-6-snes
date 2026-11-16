#!/usr/bin/env python3
"""Makes the ZONE1 world map assets from Mesen dumps (research tool, run once).

    python tools/extract_world_map.py SB1_DIR SB5_PREFIX
    python tools/extract_world_map.py zone2 SB2_DIR

SB1_DIR holds the dumps of tools/mesen/sb1_world_map.lua run on Super
Bomberman (USA): m_vram<k>.bin / m_cgram<k>.bin / m_oam<k>.bin for 200
frames of its world map (World 1) and aram_boot.bin (sound RAM right after the
boot upload). SB5_PREFIX is the dump of SB6's own ZONE1-1 map (VRAM, CGRAM:
<prefix>_vram.bin, <prefix>_cgram.bin) for the START sign.

Writes assets/world_map/:
  * zone1_sb1.png  - SB1's island and clouds (BG1, 16x16 tiles) plus the
    center tower (an OBJ in SB1), screen space 256x224, alpha 0 = sea;
  * water.png      - the sea tile (BG2, one 16x16 tile, SB1 rewrites its
    pixels): its 7 frames left to right;
  * start_sign.png - SB5's START sign (pixels of the sign only), screen space;
and assets/sound/sb1_world_map.bin: SB1's sound RAM $0800-$A1BB (driver,
songs, samples) as uploaded at boot; the world map music is its song command
$87. Above $A1BB SB1 never writes (power-on garbage).

zone2: SB2_DIR holds the dumps of tools/mesen/sb2_world_map.lua run on Super
Bomberman 2 (USA) (its World map: stars and the five ships). Writes
assets/world_map/:
  * zone2_stars.png  - the star field (SB2's BG1, 256x256: its 256x512 map
    repeats every 256 lines); SB2 scrolls it up half a pixel per frame;
  * zone2_ships.png  - the ships (all OBJ in SB2, palettes 1-5; Bomberman,
    palette 0, is left out), screen space 256x224, alpha 0 = stars;
  * zone2_palettes.png - per pixel of the ships: its OBJ palette (1-5);
  * zone2_lights.png - per pixel of the ships: 0, or 1 + the light whose
    color cycles (8 CGRAM entries of OBJ palettes 1, 2, 5);
  * zone2_lights.json - {"period": 64, "lights": [[64 BGR15 colors], ...]},
    one color per frame for each light (SB2 cycles them by 16 / 20-23 frames);
and assets/sound/sb2_world_map.bin (SB2's sound RAM $0800-$E6DF while the map
song plays: driver, songs, samples; song command $02 on port 0) plus
sb2_world_map_ff00.bin ($FF00-$FF38: the driver's PCALL routines).

SB1's screen: BG1 map $5000, BG2 map $5400 (32x32 of 16x16 tiles), chr $0000,
V scroll -1 (screen line y = map line y); OBJ chr at VRAM $C000 bytes. SB6's
map has V scroll 0 (screen line y = map line y + 1); the build shifts.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATER_DUMPS = (0, 10, 23, 33, 42, 90, 102)    # one dump per frame of the sea tile (seen changing there)
TOWER_FIRST_TILE = 0x180                      # OBJ tiles of the center tower ($180-$1C2; Bomberman is below)
SIGN_COLORS = {(139, 82, 41), (32, 32, 32), (74, 41, 16), (255, 255, 0), (189, 115, 65), (222, 222, 0)}
SIGN_BOARD = (24, 100, 64, 120)               # SB5 BG1 map pixels (x0, y0, x1, y1)
SIGN_POST = (30, 120, 44, 140)
ARAM_FIRST, ARAM_END = 0x0800, 0xA1BC


def rgb(cg, i):
    w = cg[2 * i] | cg[2 * i + 1] << 8
    return (w & 31) * 255 // 31, (w >> 5 & 31) * 255 // 31, (w >> 10 & 31) * 255 // 31


def tile(vram, byteaddr):
    out = np.zeros((8, 8), np.int16)
    for y in range(8):
        for p in range(4):
            b = vram[(byteaddr + (p // 2) * 16 + y * 2 + (p & 1)) & 0xFFFF]
            for x in range(8):
                out[y, x] |= (b >> (7 - x) & 1) << p
    return out


def big(vram, t):
    o = np.zeros((16, 16), np.int16)
    o[:8, :8], o[:8, 8:] = tile(vram, t * 32), tile(vram, (t + 1) * 32)
    o[8:, :8], o[8:, 8:] = tile(vram, (t + 16) * 32), tile(vram, (t + 17) * 32)
    return o


def layer16(vram, mapword):
    """SB1 BG layer of 16x16 tiles -> 512x512 CGRAM indices (-1 = transparent)."""
    idx = np.full((512, 512), -1, np.int16)
    for ty in range(32):
        for tx in range(32):
            a = 2 * (mapword + ty * 32 + tx)
            e = vram[a] | vram[a + 1] << 8
            px = big(vram, e & 0x3FF)
            if e & 0x4000:
                px = px[:, ::-1]
            if e & 0x8000:
                px = px[::-1, :]
            idx[ty * 16:ty * 16 + 16, tx * 16:tx * 16 + 16] = np.where(px > 0, (e >> 10 & 7) * 16 + px, -1)
    return idx


SB2_LIGHTS = (156, 157, 158, 172, 173, 220, 221, 222)   # CGRAM entries SB2 cycles (OBJ palettes 1, 2, 5)
SB2_PERIOD = 64
SB2_ARAM = (0x0800, 0xE6E0)
SB2_FF00 = (0xFF00, 0xFF39)


def zone2(sb2):
    rd = lambda p: open(p, "rb").read()
    v, cg, oam = rd(f"{sb2}/v1300.bin"), rd(f"{sb2}/c1300.bin"), rd(f"{sb2}/o1300.bin")
    out = os.path.join(ROOT, "assets", "world_map")
    # stars: BG1, map $4000 (words), 16x16 tiles, chr 0; the top 256 lines repeat below
    stars = np.zeros((256, 256, 3), np.uint8)
    for ty in range(16):
        for tx in range(16):
            a = 2 * (0x4000 + ty * 32 + tx)
            e = v[a] | v[a + 1] << 8
            px = big(v, e & 0x3FF)
            if e & 0x4000:
                px = px[:, ::-1]
            if e & 0x8000:
                px = px[::-1, :]
            for y in range(16):
                for x in range(16):
                    stars[ty * 16 + y, tx * 16 + x] = rgb(cg, (e >> 10 & 7) * 16 + px[y, x]) if px[y, x] else rgb(cg, 0)
    Image.fromarray(stars).save(os.path.join(out, "zone2_stars.png"))
    # ships: OBJ (8x8 / 16x16, chr VRAM $C000), lower OAM index on top, palette 0 (Bomberman) left out
    ships = np.zeros((224, 256, 4), np.uint8)
    lights = np.zeros((224, 256), np.uint8)
    opal = np.zeros((224, 256), np.uint8)
    for i in range(127, -1, -1):
        x, y, t, a = oam[4 * i:4 * i + 4]
        hi = oam[512 + i // 4] >> (2 * (i % 4)) & 3
        if hi & 1:
            x -= 256
        pal = a >> 1 & 7
        if pal == 0 or 224 <= y < 240:
            continue
        size = 16 if hi & 2 else 8
        tn = t | (a & 1) << 8
        for ty in range(size // 8):
            for tx in range(size // 8):
                px = tile(v, 0xC000 + ((tn + ty * 16 + tx) & 0x1FF) * 32)
                for yy, xx in zip(*np.nonzero(px)):
                    sx = x + (size - 8 - 8 * tx + 7 - xx if a & 0x40 else 8 * tx + xx)
                    sy = (y + (size - 8 - 8 * ty + 7 - yy if a & 0x80 else 8 * ty + yy)) & 255
                    if 0 <= sx < 256 and sy < 224:
                        c = 128 + pal * 16 + px[yy, xx]
                        ships[sy, sx] = rgb(cg, c) + (255,)
                        lights[sy, sx] = SB2_LIGHTS.index(c) + 1 if c in SB2_LIGHTS else 0
                        opal[sy, sx] = pal
    Image.fromarray(ships).save(os.path.join(out, "zone2_ships.png"))
    Image.fromarray(lights).save(os.path.join(out, "zone2_lights.png"))
    Image.fromarray(opal).save(os.path.join(out, "zone2_palettes.png"))
    rows = [l.split() for l in open(f"{sb2}/cg.txt")]
    seq = [[int(r[2 + c], 16) for c in SB2_LIGHTS] for r in rows]
    start = 40                                  # past the first, longer step of OBJ palette 5
    for k in range(start, len(seq) - SB2_PERIOD):
        if seq[k] != seq[k + SB2_PERIOD]:
            raise SystemExit(f"zone2: the lights do not repeat every {SB2_PERIOD} frames (frame {rows[k][0]})")
    table = [[seq[start + f][j] for f in range(SB2_PERIOD)] for j in range(len(SB2_LIGHTS))]
    cg0 = [cg[2 * c] | cg[2 * c + 1] << 8 for c in SB2_LIGHTS]
    import json
    with open(os.path.join(out, "zone2_lights.json"), "w") as fh:
        json.dump({"period": SB2_PERIOD, "cgram": list(SB2_LIGHTS), "at_dump": cg0, "lights": table}, fh)
    aram = rd(f"{sb2}/aram1300.bin")
    snd = os.path.join(ROOT, "assets", "sound")
    with open(os.path.join(snd, "sb2_world_map.bin"), "wb") as fh:
        fh.write(aram[SB2_ARAM[0]:SB2_ARAM[1]])
    with open(os.path.join(snd, "sb2_world_map_ff00.bin"), "wb") as fh:
        fh.write(aram[SB2_FF00[0]:SB2_FF00[1]])
    print(f"wrote {out}: zone2_stars.png, zone2_ships.png, zone2_lights.png/.json "
          f"({len(SB2_LIGHTS)} lights, {(lights > 0).sum()} px); sb2_world_map.bin "
          f"({SB2_ARAM[1] - SB2_ARAM[0]} bytes) + _ff00.bin")


def main():
    if sys.argv[1] == "zone2":
        return zone2(sys.argv[2])
    sb1, sb5 = sys.argv[1], sys.argv[2]
    rd = lambda p: open(p, "rb").read()
    vram, cg, oam = rd(f"{sb1}/m_vram0.bin"), rd(f"{sb1}/m_cgram0.bin"), rd(f"{sb1}/m_oam0.bin")
    out = os.path.join(ROOT, "assets", "world_map")
    os.makedirs(out, exist_ok=True)

    # island + clouds (BG1) and the tower (OBJ), screen space
    b1 = layer16(vram, 0x5000)[:224, :256]
    img = np.zeros((224, 256, 4), np.uint8)
    for y, x in zip(*np.nonzero(b1 >= 0)):
        img[y, x] = rgb(cg, b1[y, x]) + (255,)
    for i in range(128):
        x, y, t, a = oam[4 * i:4 * i + 4]
        hi = oam[512 + i // 4] >> (2 * (i % 4)) & 3
        tn = t | (a & 1) << 8
        if y >= 224 or tn < TOWER_FIRST_TILE:
            continue
        size = 16 if hi & 2 else 8
        for ty in range(size // 8):
            for tx in range(size // 8):
                px = tile(vram, 0xC000 + ((tn + ty * 16 + tx) & 0x1FF) * 32)
                for yy, xx in zip(*np.nonzero(px)):
                    sx, sy = x + tx * 8 + xx, y + ty * 8 + yy
                    if sx < 256 and sy < 224:
                        img[sy, sx] = rgb(cg, 128 + (a >> 1 & 7) * 16 + px[yy, xx]) + (255,)
    Image.fromarray(img).save(os.path.join(out, "zone1_sb1.png"))

    # the sea tile's frames (BG2 is tile $200 everywhere, palette 1)
    strip = np.zeros((16, 16 * len(WATER_DUMPS), 3), np.uint8)
    for n, k in enumerate(WATER_DUMPS):
        v, c = rd(f"{sb1}/m_vram{k}.bin"), rd(f"{sb1}/m_cgram{k}.bin")
        px = big(v, 0x200)
        for y in range(16):
            for x in range(16):
                strip[y, 16 * n + x] = rgb(c, 16 + px[y, x])
    Image.fromarray(strip).save(os.path.join(out, "water.png"))

    # SB5's START sign: BG1 (map $3000, 64x32 of 8x8 tiles, chr $0000), map line y = screen line y - 1
    v5, c5 = rd(f"{sb5}_vram.bin"), rd(f"{sb5}_cgram.bin")
    sign = np.zeros((224, 256, 4), np.uint8)
    for my in range(SIGN_BOARD[1], SIGN_POST[3]):
        for mx in range(SIGN_BOARD[0], SIGN_BOARD[2]):
            box = SIGN_BOARD if my < SIGN_BOARD[3] else SIGN_POST
            if not box[0] <= mx < box[2]:
                continue
            a = 2 * (0x3000 + (my // 8) * 32 + mx // 8)
            e = v5[a] | v5[a + 1] << 8
            px = tile(v5, (e & 0x3FF) * 32)
            if e & 0x4000:
                px = px[:, ::-1]
            if e & 0x8000:
                px = px[::-1, :]
            c = px[my % 8, mx % 8]
            if c and rgb(c5, (e >> 10 & 7) * 16 + c) in SIGN_COLORS:
                sign[my - 1, mx] = rgb(c5, (e >> 10 & 7) * 16 + c) + (255,)
    Image.fromarray(sign).save(os.path.join(out, "start_sign.png"))

    aram = rd(f"{sb1}/aram_boot.bin")
    with open(os.path.join(ROOT, "assets", "sound", "sb1_world_map.bin"), "wb") as fh:
        fh.write(aram[ARAM_FIRST:ARAM_END])
    print(f"wrote {out}: zone1_sb1.png, water.png ({len(WATER_DUMPS)} frames), start_sign.png; "
          f"sb1_world_map.bin ({ARAM_END - ARAM_FIRST} bytes)")


if __name__ == "__main__":
    main()
