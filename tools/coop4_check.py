#!/usr/bin/env python3
"""Every World 1 stage with 4 players and Louies (the SB6 Normal Game target), in Mesen 2 headless.

    python tools/coop4_check.py [STAGE_HEX ...]          (default: the whole World 1 chain)
    PLAYERS=3 python tools/coop4_check.py 18            (2-4 players; default 4)

Runs tools/mesen/stage_test.lua with tools/mesen/coop4_check.lua on build/Super Bomberman 6.sfc (4 seats, nobody
dies, everyone walks and drops bombs) and fails a stage when:
  * the main loop runs below MIN_FPS in some second (stage frames 300 .. END),
  * an egg could not appear for lack of OBJ colors in some frame (no Louie palette and no free slot 3-7:
    stage + 4 bombers + the Louie palette leave 2 slots for the enemies' palettes),
  * P3 / P4 had to borrow P1's / P2's colors (c0_palfail) in some frame,
  * a seat's start is not safe (spawn_safety, from the stage's state a few frames after the enemies appear):
    - no escape: in the worst case of the random soft blocks (every cell the scatter may fill is filled;
      $7E:2700 & $10 = kept clear, asm/coop.asm e4_reserve) the bomber cannot drop a bomb within ESC_STEPS
      cells and hide from it within ESC_STEPS more, for any fire range (flames stop at walls/soft blocks),
    - an enemy starts fewer than MIN_ENEMY_STEPS cells away (walking distance around walls, soft blocks
      ignored: they burn, and some enemies pass them).
Env: MESEN (Mesen.exe), END (stage frames, default 1500), JOBS (parallel runs, default 4), PLAYERS (2-4, default
4), COOP4_BOMB (frames between each bomber's bombs, default 60; 0 = none: every enemy stays alive).
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
ESC_STEPS = 5                    # cells to the bomb spot, then to the hiding spot (a bomb burns in ~2.5 s)
MIN_ENEMY_STEPS = 6              # (SB5's 1-1 for 2 players: 6)
STEPS = (1, -1, 16, -16)
NAMES = {s: f"1-{n}" for s, n, _ in CHAIN}
NAMES.update({0x67: "1-6a", 0x69: "1-6b", 0x6B: "1-6c", 0x68: "1-7"})


def _bfs(start, free, limit=99):
    dist, todo = {start: 0}, [start]
    for c in todo:
        if dist[c] >= limit:
            continue
        for d in STEPS:
            n = c + d
            if 0 <= n < 256 and n not in dist and free(n):
                dist[n] = dist[c] + 1
                todo.append(n)
    return dist


def spawn_safety(res):
    """Problems of the seats' starts (see the module doc), [] when every seat is safe."""
    lines = {l.split(" ", 1)[0]: l.split(" ", 1)[1] for l in res.splitlines() if " " in l}
    if "map" not in lines:
        return ["no start state"]
    m, keep = bytes.fromhex(lines["map"]), bytes.fromhex(lines["keep"])
    seats = [int(x, 16) for x in lines["seats"].split()]
    enemies = [int(x.split(":")[0], 16) for x in lines.get("enemies", "").split()]
    scatter = any(k & 0x80 for k in keep)                # random soft blocks were placed this stage
    def free(c):
        return not m[c] & 0xB0 and (not scatter or keep[c] & 0x10)
    def blast(b):
        out = {b}
        for d in STEPS:
            c = b + d
            while 0 <= c < 256:
                out.add(c)
                if not free(c):
                    break
                c += d
        return out
    bad = []
    for seat, c in enumerate(seats):
        if c == 0xFF:
            continue
        safe = any(set(_bfs(b, free, ESC_STEPS)) - blast(b) for b in _bfs(c, free, ESC_STEPS))
        if not safe:
            bad.append(f"P{seat + 1} at ({c & 15},{c >> 4}) cannot bomb and hide")
        walk = _bfs(c, lambda n: not m[n] & 0x80)
        near = [e for e in enemies if walk.get(e, 99) < MIN_ENEMY_STEPS]
        for e in near:
            bad.append(f"P{seat + 1} at ({c & 15},{c >> 4}): enemy at ({e & 15},{e >> 4}) {walk[e]} cells away")
    return bad


def run(stage):
    os.makedirs(OUT, exist_ok=True)
    res = os.path.join(OUT, f"{stage:02X}.txt")
    if os.path.exists(res):
        os.remove(res)
    env = dict(os.environ, SB6_PLAYERS=os.environ.get("PLAYERS", "4"), PLAN="a", STAGE_WAIT="99999", SB6_OUT=os.path.join(OUT, f"{stage:02X}_nav"),
               OUT=os.path.join(OUT, f"{stage:02X}_run"), RING=os.path.join(ROOT, "tools", "mesen", "coop4_check.lua"),
               COOP4_STAGE=f"{stage:02X}", COOP4_OUT=res, END=os.environ.get("END", "1500"),
               SB6_LUA=os.path.join(ROOT, "tools", "mesen"))
    subprocess.run([MESEN, "--testrunner", ROM, os.path.join(ROOT, "tools", "mesen", "stage_test.lua")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    if not os.path.exists(res):
        return stage, None
    text = open(res).read()
    f = text.split()
    return stage, dict(fps=int(f[f.index("fps") + 1]), louie=int(f[f.index("louie") + 1]),
                       shared=int(f[f.index("shared") + 1]), enemies=int(f[f.index("enemies") + 1]), frames=int(f[f.index("frames") + 1]),
                       slots=" ".join(f[f.index("slots") + 1:f.index("seconds")]), spawn=spawn_safety(text))


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
        why += r["spawn"]
        bad += bool(why)
        print(f"{name}  {'FAIL' if why else 'ok  '}  worst {r['fps']} fps, {r['enemies']} enemies, slots {r['slots']}"
              + (f"  <- {', '.join(why)}" if why else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
