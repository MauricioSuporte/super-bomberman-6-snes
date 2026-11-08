#!/usr/bin/env python3
"""Turns a Mesen log of Hudson's DSP writes into replayable SFX scripts.

    python tools/capture_sfx.py LOG assets/sound/title_sfx.json

LOG comes from tools/mesen/sfx_capture.lua run on a copy of the base ROM whose
title song is silenced (see docs/ROM_MAP.md, "Title SFX"): lines
"CED f=<frame> A=<group><id> cyc=<spc cycle>" for sound requests and
"W <spc cycle> <dsp reg> <value>" for every S-DSP write.

Hudson plays the menu SFX on voice 0 with sample $20. For each group-2
request the script keeps voice 0's register writes and the KON/KOF writes,
from the first KOF/KON-related write until the last KOF, grouped in frames
(writes less than 8 ms apart) with the delay to the next frame in 4 ms units.
"""
import json
import sys

SPC_HZ = 2048000  # Mesen "spc.cycle" counts at 2.048 MHz
FRAME_GAP_MS = 8.0
TICK_MS = 4.0


def parse(path):
    blocks, cur = [], None
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "CED":
            a = int(p[2].split("=")[1], 16)
            cur = {"group": a >> 8, "id": a & 0xFF, "cyc": int(p[3].split("=")[1]), "writes": []}
            blocks.append(cur)
        elif p[0] == "W" and cur:
            cur["writes"].append((int(p[1]), int(p[2], 16), int(p[3], 16)))
    return blocks


def script(block):
    ws = [(c, r, v) for c, r, v in block["writes"]
          if r < 0x08 or (r in (0x4C, 0x5C) and v & 1)]
    # Active span: from the first KOF/KON to the last KOF after the last KON.
    kon = [i for i, (_, r, _) in enumerate(ws) if r == 0x4C]
    if not kon:
        return None
    kof = [i for i, (_, r, _) in enumerate(ws) if r == 0x5C]
    start = min([i for i in kof if i < kon[0]] or [kon[0]])
    ends = [i for i in kof if i > kon[-1]]
    end = ends[0] if ends else len(ws) - 1
    span = ws[start:end + 1]
    frames, last_t = [], None
    for c, r, v in span:
        t = (c - block["cyc"]) * 1000.0 / SPC_HZ
        if last_t is None or t - last_t > FRAME_GAP_MS:
            frames.append({"t": t, "w": []})
        frames[-1]["w"].append([r, v])
        last_t = t
    t0 = frames[0]["t"]
    out = []
    for k, fr in enumerate(frames):
        nxt = frames[k + 1]["t"] if k + 1 < len(frames) else None
        out.append({"at_ms": round(fr["t"] - t0, 2), "writes": fr["w"],
                    "wait": None if nxt is None else max(1, round((nxt - fr["t"]) / TICK_MS))})
    return out


def main():
    blocks = parse(sys.argv[1])
    sfx = {}
    for b in blocks:
        if b["group"] == 2 and f"{b['id']}" not in sfx:
            s = script(b)
            if s:
                sfx[str(b["id"])] = s
    doc = {"source": "Super Bomberman 5 (USA), Hudson driver, title menu (song silenced)",
           "voice": 0, "tick_ms": TICK_MS, "sfx": sfx}
    with open(sys.argv[2], "w") as fh:
        json.dump(doc, fh, indent=1)
    for k, v in sfx.items():
        print(f"sfx {k}: {len(v)} frames, {v[-1]['at_ms']:.0f} ms")


if __name__ == "__main__":
    main()
