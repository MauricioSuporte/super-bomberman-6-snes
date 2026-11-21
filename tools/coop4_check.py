#!/usr/bin/env python3
"""Every World 1 stage with 4 players and Louies (the SB6 Normal Game target), in Mesen 2 headless.

    python tools/coop4_check.py [STAGE_HEX ...]          (default: the whole World 1 chain)

Runs tools/mesen/stage_test.lua with tools/mesen/coop4_check.lua on build/Super Bomberman 6.sfc (4 seats, nobody
dies, everyone walks and drops bombs) and fails a stage when:
  * the main loop runs below MIN_FPS in some second (stage frames 300 .. END),
  * an egg could not appear for lack of OBJ colors in some frame (no Louie palette and no free slot 3-7:
    stage + 4 bombers + the Louie palette leave 2 slots for the enemies' palettes),
  * P3 / P4 had to borrow P1's / P2's colors (c0_palfail) in some frame.
Env: MESEN (Mesen.exe), END (stage frames, default 1500), JOBS (parallel runs, default 4).
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from sb6.features.world1 import BOSSES, CHAIN  # noqa: E402

MESEN = os.environ.get("MESEN", "D:/sb6-tools/mesen/Mesen.exe")
ROM = os.path.join(ROOT, "build", "Super Bomberman 6.sfc")
OUT = os.path.join(ROOT, "build", "coop4")
MIN_FPS = 50                     # (SB5's own 1-1 measures 53-60 under this load)
NAMES = {s: f"1-{n}" for s, n, _ in CHAIN}
NAMES.update({0x67: "1-6a", 0x69: "1-6b", 0x6B: "1-6c", 0x68: "1-7"})


def run(stage):
    os.makedirs(OUT, exist_ok=True)
    res = os.path.join(OUT, f"{stage:02X}.txt")
    if os.path.exists(res):
        os.remove(res)
    env = dict(os.environ, SB6_PLAYERS="4", PLAN="a", STAGE_WAIT="99999", SB6_OUT=os.path.join(OUT, f"{stage:02X}_nav"),
               OUT=os.path.join(OUT, f"{stage:02X}_run"), RING=os.path.join(ROOT, "tools", "mesen", "coop4_check.lua"),
               COOP4_STAGE=f"{stage:02X}", COOP4_OUT=res, END=os.environ.get("END", "1500"),
               SB6_LUA=os.path.join(ROOT, "tools", "mesen"))
    subprocess.run([MESEN, "--testrunner", ROM, os.path.join(ROOT, "tools", "mesen", "stage_test.lua")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    if not os.path.exists(res):
        return stage, None
    f = open(res).read().split()
    return stage, dict(fps=int(f[f.index("fps") + 1]), louie=int(f[f.index("louie") + 1]),
                       shared=int(f[f.index("shared") + 1]), frames=int(f[f.index("frames") + 1]),
                       slots=" ".join(f[f.index("slots") + 1:]))


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
        if r["fps"] < MIN_FPS:
            why.append(f"{r['fps']} fps")
        if r["louie"]:
            why.append(f"no Louie colors in {r['louie']} frames")
        if r["shared"]:
            why.append(f"P3/P4 without own colors in {r['shared']} frames")
        bad += bool(why)
        print(f"{name}  {'FAIL' if why else 'ok  '}  worst {r['fps']} fps, slots {r['slots']}"
              + (f"  <- {', '.join(why)}" if why else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
