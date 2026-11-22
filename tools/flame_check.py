#!/usr/bin/env python3
"""Explosions of every World 1 stage, in Mesen 2 headless (like tools/coop4_check.py).

    python tools/flame_check.py [STAGE_HEX ...]          (default: the whole World 1 chain and its bosses)

Runs tools/mesen/stage_test.lua with tools/mesen/flame_check.lua (on coop4_check.lua: 4 seats that walk and drop
bombs, nobody dies) on build/Super Bomberman 6.sfc and, every FLAME_STEP stage frames, takes VRAM, CGRAM, the BG
registers and the cells. Every BG1/BG2 map word showing a flame tile (tiles $010-$07F, palette 2) is checked
against SB5's see-through flame set (assets/stages/sb5_flames_bg1.bin, 1-1's), pixel by pixel:
  * fire: the set's fire pixels (color != 0) must be there unchanged (SB5's set-up $C5:140D rewriting the end
    tiles $010-$01F over ours showed as dots at the flames' ends);
  * around the fire (color 0 in the set): the layer must show what it showed at that map place before and after
    the explosion (the nearest records without a flame there, equal to each other: a burnt soft block or a taken
    item is skipped): see-through on a layer over the field (1-1, 1-2, 1-4, 1-5: flames on BG1), the floor on
    the field's own layer (1-6, 1-7 arenas; there one flame set can only draw one floor: over another kind of
    floor cell, e.g. SB1's shadow under a block in 1-7, the arena's most common floor is allowed and counted).
    SB5's set for a field layer drew its grass, grass shadows and sparks there (white dots, a changed floor);
  * place: a flame layer over the field must scroll with it (a multiple of 16 pixels apart: 1-4's BG1 used to
    drift with SB5's clouds) and most flame tiles (MIN_ON_CELL) must sit on cells holding a flame ($1052).
A stage fails on any bad tile, a misplaced layer, or no flame seen at all.
Env: MESEN (Mesen.exe), SB6_ROM (another ROM), END (stage frames, default 1500), JOBS (parallel runs, default 4), FLAME_STEP (default 6),
FLAME_FROM (default 250), FLAME_KEEP=1 keeps build/flame_check/<stage>.bin.
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from sb6.features.world1 import BOSSES, CHAIN  # noqa: E402
from coop4_check import MESEN, NAMES, ROM  # noqa: E402

ROM = os.environ.get("SB6_ROM", ROM)

OUT = os.path.join(ROOT, "build", "flame_check")
FLAMES = os.path.join(ROOT, "assets", "stages", "sb5_flames_bg1.bin")
FIRST, LAST = 0x10, 0x7F            # SB5's flame tiles, palette 2
VBYTES = 0xA000
HEAD = 4 + 4 + 6 + 8 + 256 + 512
REC = HEAD + VBYTES
MIN_ON_CELL = 0.9                   # share of flame tiles on a flame cell (_fire_cell)


def _planar(raw):
    """(n, 32) bytes of 4bpp tiles -> (n, 8, 8) color indices."""
    b = np.unpackbits(raw.reshape(-1, 2, 8, 2, 1), axis=-1, bitorder="big")
    # b[n, half, row, plane-in-half, x]
    return (b[:, 0, :, 0] | b[:, 0, :, 1] << 1 | b[:, 1, :, 0] << 2 | b[:, 1, :, 1] << 3).astype(np.int32)


def _records(path):
    data = open(path, "rb").read()
    out = []
    for o in range(0, len(data) - REC + 1, REC):
        r = data[o:o + REC]
        if r[:4] != b"FLM1":
            raise ValueError(f"{path}: bad record at {o}")
        f = int.from_bytes(r[4:8], "little")
        bg1sc, bg2sc, nba, field, flayer, d1a = r[8:14]
        sc = np.frombuffer(r[14:22], "<u2").astype(np.int32)
        out.append(dict(frame=f, sc=(bg1sc, bg2sc), nba=nba, field=field, flayer=flayer, d1a=d1a,
                        h=(int(sc[0]), int(sc[1])), v=(int(sc[2]), int(sc[3])),
                        cells=np.frombuffer(r[22:278], np.uint8),
                        cg=np.frombuffer(r[278:790], "<u2").astype(np.int32),
                        vram=np.frombuffer(r[790:790 + VBYTES], np.uint8)))
    return out


def _map(rec, layer):
    """BG1 (0) / BG2 (1) map words, rows ty, columns tx (32 or 64 each, by the BGnSC size bits)."""
    sc = rec["sc"][layer]
    base, size = (sc >> 2) << 10, sc & 3
    words = np.frombuffer(rec["vram"].tobytes(), "<u2")
    w, h = 64 if size & 1 else 32, 64 if size & 2 else 32
    m = np.zeros((h, w), np.int32)
    for sy in range(h // 32):
        for sx in range(w // 32):
            a = base + (sx + sy * (w // 32)) * 0x400
            if a + 0x400 <= len(words):
                m[32 * sy:32 * sy + 32, 32 * sx:32 * sx + 32] = words[a:a + 0x400].reshape(32, 32)
    return m


def _is_flame(w):
    t = w & 0x3FF
    return (t >= FIRST) & (t <= LAST) & ((w >> 10) & 7 == 2)


def _tile(rec, layer, w):
    """Colors (RGB555, -1 = see-through) of map word w's 8 x 8 picture, and its color indices."""
    t = w & 0x3FF
    base = (rec["nba"] >> (4 * layer) & 0x0F) * 0x2000     # BG12NBA: $1000 words a step
    a = base + 32 * t
    if a + 32 > VBYTES:
        return None, None
    idx = _planar(rec["vram"][a:a + 32].copy())[0]
    if w & 0x4000:
        idx = idx[:, ::-1]
    if w & 0x8000:
        idx = idx[::-1, :]
    col = np.where(idx == 0, -1, rec["cg"][((w >> 10) & 7) * 16 + idx])
    return col, idx


def _fire_cell(v):
    """$1052: bit 2 = flame (`& 7`: 7 center, 5 horizontal, 6 vertical), $83 = a wall the flame reached (its end
    is drawn there); a record late is still counted (the map follows the cells by a frame)."""
    return bool(v & 4) or v == 0x83


def analyse(recs, fire):
    res = dict(records=len(recs), tiles=0, bad_fire=0, bad_floor=0, common_floor=0, unchecked=0, on_cell=0,
               misplaced=0, examples=[], flame_layers=set())
    floors, late = {}, []
    maps = [[_map(r, 0), _map(r, 1)] for r in recs]
    flame = [[_is_flame(m) for m in ms] for ms in maps]
    for i, rec in enumerate(recs):
        for layer in (0, 1):
            ys, xs = np.nonzero(flame[i][layer])
            if not len(ys):
                continue
            res["flame_layers"].add(layer + 1)
            field = rec["field"] - 1 if rec["field"] in (1, 2) else 1
            dh = (rec["h"][layer] - rec["h"][field]) % 16
            dv = (rec["v"][layer] - rec["v"][field]) % 16
            if dh or dv:
                res["misplaced"] += len(ys)
                if len(res["examples"]) < 8:
                    res["examples"].append(f"frame {rec['frame']}: BG{layer + 1} flames {dh},{dv} px off BG{field + 1}'s"
                                           f" cells (scroll {rec['h'][layer]:04X}/{rec['v'][layer]:04X} vs "
                                           f"{rec['h'][field]:04X}/{rec['v'][field]:04X})")
            mh, mw = 8 * maps[i][layer].shape[0], 8 * maps[i][layer].shape[1]
            for ty, tx in zip(ys.tolist(), xs.tolist()):
                # on screen only (1-7's BG1 lower screen is never shown and holds other palette 2 tiles)
                sx, sy = (8 * tx - rec["h"][layer]) % mw, (8 * ty - rec["v"][layer]) % mh
                if not (sx < 256 or sx > mw - 8) or not (sy < 224 or sy > mh - 8):
                    continue
                w = int(maps[i][layer][ty, tx])
                res["tiles"] += 1
                where = f"frame {rec['frame']} BG{layer + 1} tile ({tx},{ty}) word {w:04X}"
                # its cell: map pixel -> screen -> the field layer's map pixel
                x = (8 * tx - rec["h"][layer] + rec["h"][field]) % 512
                y = (8 * ty - rec["v"][layer] + rec["v"][field]) % 512
                c, r_ = x // 16, y // 16
                if c < 16 and r_ < 16 and any(_fire_cell(recs[j]["cells"][16 * r_ + c]) for j in (i, i - 1) if j >= 0):
                    res["on_cell"] += 1
                col, idx = _tile(rec, layer, w)
                if col is None:
                    continue
                want = fire[(w & 0x3FF) - FIRST]
                if w & 0x4000:
                    want = want[:, ::-1]
                if w & 0x8000:
                    want = want[::-1, :]
                fmask = want != 0
                nfire = int((idx[fmask] != want[fmask]).sum())
                if nfire:
                    res["bad_fire"] += 1
                    if len(res["examples"]) < 8:
                        res["examples"].append(f"{where}: {nfire} fire pixels changed")
                # what this map place shows without a flame: the nearest records before and after
                before = next((j for j in range(i - 1, -1, -1) if not flame[j][layer][ty, tx]), None)
                after = next((j for j in range(i + 1, len(recs)) if not flame[j][layer][ty, tx]), None)
                if before is None or after is None:
                    res["unchecked"] += 1
                    continue
                cb, _ = _tile(recs[before], layer, int(maps[before][layer][ty, tx]))
                ca, _ = _tile(recs[after], layer, int(maps[after][layer][ty, tx]))
                if cb is None or ca is None or not np.array_equal(cb, ca):
                    res["unchecked"] += 1           # the place changed (soft block burnt, item taken, animation)
                    continue
                q = (ty & 1, tx & 1)
                if (cb >= 0).any():         # the flame replaces the place on its own layer (an arena's field)
                    key = cb.tobytes()
                    floors.setdefault(q, {})
                    floors[q][key] = floors[q].get(key, 0) + 1
                nfloor = int((col[~fmask] != cb[~fmask]).sum())
                if nfloor:
                    late.append((q, col, fmask, f"{where}: {nfloor} pixels around the fire differ from the place's own "
                                                f"(frames {recs[before]['frame']} / {recs[after]['frame']})"))
    # a flame on the field's own layer can only draw one floor (sb1_stages: the arena's most common floor cell):
    # on another kind of floor cell (SB1's shadow under a block) that floor is allowed, anything else is not
    for q, col, fmask, text in late:
        common = max(floors[q], key=floors[q].get) if floors.get(q) else None
        if common is not None and np.array_equal(col[~fmask], np.frombuffer(common, col.dtype).reshape(8, 8)[~fmask]):
            res["common_floor"] += 1
            continue
        res["bad_floor"] += 1
        if len(res["examples"]) < 8:
            res["examples"].append(text)
    return res


def run(stage):
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"{stage:02X}.bin")
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ, SB6_PLAYERS="4", PLAN="a", STAGE_WAIT="99999", SB6_OUT=os.path.join(OUT, f"{stage:02X}_nav"),
               OUT=os.path.join(OUT, f"{stage:02X}_run"), RING=os.path.join(ROOT, "tools", "mesen", "flame_check.lua"),
               COOP4_STAGE=f"{stage:02X}", COOP4_OUT=os.path.join(OUT, f"{stage:02X}_coop4.txt"),
               FLAME_OUT=out, END=os.environ.get("END", "1500"), SB6_LUA=os.path.join(ROOT, "tools", "mesen"))
    subprocess.run([MESEN, "--testrunner", ROM, os.path.join(ROOT, "tools", "mesen", "stage_test.lua")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    if not os.path.exists(out):
        return stage, None
    fire = _planar(np.frombuffer(open(FLAMES, "rb").read(), np.uint8).copy())
    res = analyse(_records(out), fire)
    if os.environ.get("FLAME_KEEP") != "1":
        os.remove(out)
    return stage, res


def main():
    stages = [int(a, 16) for a in sys.argv[1:]] or [s for s, _, _ in CHAIN] + [b for b, _, _ in BOSSES]
    with ThreadPoolExecutor(int(os.environ.get("JOBS", "4"))) as ex:
        results = list(ex.map(run, stages))
    bad = 0
    for stage, r in results:
        name = f"{NAMES.get(stage, '?'):5} ${stage:02X}"
        if r is None:
            print(f"{name}  FAIL  no result (picker or stage did not run)")
            bad += 1
            continue
        why = []
        if not r["tiles"]:
            why.append("no flame seen")
        if r["bad_fire"]:
            why.append(f"{r['bad_fire']} tiles with changed fire")
        if r["bad_floor"]:
            why.append(f"{r['bad_floor']} tiles with a wrong floor around the fire")
        if r["misplaced"]:
            why.append(f"{r['misplaced']} tiles off the field's cells")
        if r["tiles"] and r["on_cell"] < MIN_ON_CELL * r["tiles"]:
            why.append(f"only {r['on_cell']} of {r['tiles']} tiles on a flame cell")
        bad += bool(why)
        layers = "/".join(f"BG{n}" for n in sorted(r["flame_layers"])) or "-"
        print(f"{name}  {'FAIL' if why else 'ok  '}  {r['tiles']} flame tiles on {layers} in {r['records']} records "
              f"({r['unchecked']} without a steady place to compare), {r['on_cell']} on flame cells"
              + (f", {r['common_floor']} showing the arena's common floor over another floor cell" if r["common_floor"] else "")
              + (f"  <- {', '.join(why)}" if why else ""))
        for e in r["examples"] if why else []:
            print(f"        {e}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
