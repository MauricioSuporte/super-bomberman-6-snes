#!/usr/bin/env python3
"""SB6 quality / regression tests in Mesen 2 headless (no AI involved): the Normal Game with 4 players.

    python tools/qa_check.py                 every suite but the slow ones (perf, flames)
    python tools/qa_check.py all             everything
    python tools/qa_check.py anims sfx       some suites
    python tools/qa_check.py --list          the suites
    python tools/qa_check.py -v ...          every check, not only the failures

Suites (tools/qa/suites.py has the scenarios and the ids they look for):
  picker   each seat's character and colors in the stage = what it picked (7 characters, 2 starts)
  anims    walk, idle $15, punch / kick / lift-carry-throw in 4 directions, cornered $21, death $16, time up $1F,
           victory $20 + next stage, Louies (get on, ride 4 ways, thrown off, their palettes, 2 colors at once),
           and every frame of each bomber = a pose of its character's sheet (tools/qa/poses.py)
  sfx      bomb, explosion by fire range, pierce bomb, enemy death, item, remote
  spawn    every stage: the 4 seats start in their corners, safe (bomb + hide with any soft blocks, no enemy
           within 6 cells, shut in by soft blocks), nobody dies standing still; and with P3/P4 out of the stage at
           its start (they join with Start): their spawn cells in their corners and as safe, Start brings them there
  music    each World 1 stage's music plays (Hudson driver), the title / save menu music, fps without input
  boss16   1-6: intro (players held, rival walks in), white -> black -> Golden, crowd / death sounds, items,
           the kick drop, victory, 1-7 next
  boss17   1-7: intro (players held facing up, no idle), lights out with the hole, 8 hits, red below half,
           death explosions, victory, mode $1C
           (1-6 and 1-7, on foot and with every seat on a Louie from the stage before: while an intro holds the
           players each one faces up in its stand / riding pose, its Louie too, never SB5's idle)
  chameleons 1-3 with 4 players on Louies (2 sets of characters): every chameleon drawn every frame (frog,
           copy of a player, changing), >= 50 fps
  fx       SB6's items (icons, colors, the border's blink, Full Fire without border, search bomb icon), explosions
           (flame tiles, fire colors), bombs (pictures, blues, on screen) and egg (pictures, colors, its idle loop
           and timing); every stage: a pierce bomb's flames in the normal colors, the HUD's colors (CGRAM 0-31)
           unchanged meanwhile, then the pause menu (opens, same colors / tiles / map as without a bomb) and resume
  hud      SB6's HUD (features/hud.py): every stage's HUD lines on screen = each seat's stats (fire, speed, bombs,
           bomb type, power-ups) and the lives, the clock stopped (no time up), >= 50 fps; 1-1: items picked up change
           the cells, P3/P4 out of the stage: empty blocks until they join; the heads of the characters / colors chosen
           (2 sets), the HUD during and after the pause menu; every stage again with 4 other characters / colors
           (all 7 characters over World 1) and every seat given items
  portal   World 1's exit portal (1-1 to 1-5): none while the middle cell holds a soft block, then SB1's portal
           there once every enemy is dead: appears (off / blank 3 frames x5, off 30), blinks on 3 / off 3, SB5's
           portal sound once, the cell becomes a portal, a player on it leads to the next stage
  (every scenario: SB5's static graphics queue never writes an OBJ page a bomber / Louie / egg owns)
  perf     tools/coop4_check.py (fps >= 50, Louie colors, P3/P4 colors, safe starts; ~1 min)
  flames   tools/flame_check.py (explosions look like 1-1's on every stage; ~1 min)

The first run after a build boots each fixture once (~10 s each, in parallel) and keeps its savestate in
build/qa/states (by the ROM's sha1); later runs only play the scenarios. Run after changing the ROM (not part of
tools/build.py). Exit code 1 when a check fails; build/qa/report.txt has every check.
Env: MESEN, SB6_ROM, JOBS (parallel Mesen processes, default 6).
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa import engine, suites as S  # noqa: E402

ROOT = engine.ROOT
JOBS = int(os.environ.get("JOBS", "6"))
SLOW = {"perf", "flames"}


def _jobs():
    """suite -> [(fixture, scenarios, evaluator, tag)] (one Mesen process each)."""
    out = {}
    for fx in (S.FX_A, S.FX_B):
        out.setdefault("picker", []).append((fx, S.picker_scenarios(), S.picker_eval(fx)))
        sc = S.anim_scenarios()
        ev = S.anim_eval(fx)
        third = (len(sc) + 2) // 3
        for i in range(3):            # (split: three processes per start)
            part = sc[i * third:(i + 1) * third]
            out.setdefault("anims", []).append((fx, part, ev, f"{fx.name}_anims{i}"))
    out["sfx"] = [(S.FX_A, S.sfx_scenarios(), S.sfx_eval(S.FX_A))]
    out["music"] = [(S.stage_fx(st), S.music_scenarios(), S.music_eval(st)) for st in S.STAGES]
    out["spawn"] = [(S.stage_fx(st), S.spawn_scenarios(), S.spawn_eval(st)) for st in S.STAGES]
    out["spawn"] += [(S.out_fx(st), S.spawn_out_scenarios(st), S.spawn_out_eval(st)) for st in S.STAGES]
    out["boss16"] = [(S.stage_fx(0x67), S.b16_scenarios(), S.b16_eval(None))]
    out["boss17"] = [(S.stage_fx(0x68), S.b17_scenarios(), S.b17_eval(None))]
    for st in (0x67, 0x68):
        name = "boss16" if st == 0x67 else "boss17"
        sc = S.hold16_scenarios() if st == 0x67 else S.hold17_scenarios()
        for fx in (S.Fixture(f"s{st:02X}_4p_hold", stage=st, ready=30), S.mount_fx(st)):
            out[name].append((fx, sc, S.hold_eval_for(st, fx), f"{fx.name}_{name}"))
    out["fx"] = [(S.FX_A, S.fx_scenarios(), S.fx_eval(S.FX_A))]
    out["fx"] += [(S.stage_fx(st), S.pierce_scenarios(st), S.pierce_eval(st), f"s{st:02X}_4p_pierce") for st in S.STAGES]
    out["hud"] = [(S.stage_fx(st), S.hud_scenarios(st), S.hud_eval(st), f"s{st:02X}_4p_hud") for st in S.STAGES]
    out["hud"].append((S.out_fx(0x0D), S.hud_out_scenarios(), S.hud_out_eval, "s0D_4p_hud_out"))
    out["hud"] += [(S.hud_var_fx(st), S.hud_var_scenarios(st), S.hud_var_eval(st), f"s{st:02X}_4p_hudvar") for st in S.STAGES]
    for fx in (S.FX_A, S.FX_B):
        out["hud"].append((fx, S.hud_pause_scenarios(), S.hud_pause_eval, f"{fx.name}_hud_pause"))
    out["chameleons"] = [(fx, S.cham_scenarios(), S.cham_eval(fx)) for fx in S.CHAM_FX]
    out["portal"] = [(S.portal_fx(st), S.portal_scenarios(st), S.portal_eval(st), f"s{st:02X}_portal")
                     for st in S.PORTAL_NEXT]
    norm = {}
    for name, js in out.items():
        norm[name] = [(j[0], j[1], j[2], j[3] if len(j) > 3 else f"{j[0].name}_{name}") for j in js]
    return norm


def _boot_values(msgs):
    vals = {}
    for m in msgs:
        f = m.split()
        if f[0] == "V" and len(f) > 3:
            vals[f[2]] = bytes.fromhex(f[3])
    return vals


def _external(cmd):
    t = time.time()
    p = subprocess.run([sys.executable] + cmd, cwd=ROOT, capture_output=True, text=True)
    res = S.Result()
    for line in p.stdout.splitlines():
        if line.strip():
            res.ok(line.strip()[:60], " FAIL " not in f" {line} ", line.strip())
    if p.returncode and all(ok for _, ok, _ in res):
        res.ok(" ".join(cmd), False, (p.stderr or p.stdout)[-400:])
    return res, time.time() - t


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    jobs = _jobs()
    names = list(jobs) + ["perf", "flames"]
    if "--list" in sys.argv:
        print(__doc__.split("Suites")[1].split("The first run")[0])
        return
    if args == ["all"]:
        want = names
    else:
        want = args or [n for n in names if n not in SLOW]
    bad_names = [n for n in want if n not in names]
    if bad_names:
        sys.exit(f"unknown suite(s) {bad_names}; --list")
    if not os.path.exists(engine.ROM):
        sys.exit(f"no ROM {engine.ROM}: python tools/build.py")
    t0 = time.time()
    todo = [(n, j) for n in want if n in jobs for j in jobs[n]]
    # 1. fixtures without a savestate of this ROM: boot them once (parallel)
    sha = engine.rom_sha1()
    sdir = os.path.join(engine.OUT, "states")
    for f in os.listdir(sdir) if os.path.isdir(sdir) else []:
        if not f.startswith(sha):          # savestates of older ROMs
            os.remove(os.path.join(sdir, f))
    fixtures = {j[0].name: j[0] for _, j in todo}
    need = [fx for fx in fixtures.values()
            if not os.path.exists(os.path.join(engine.OUT, "states", f"{sha}_{fx.name}.mss"))]
    if need:
        print(f"booting {len(need)} fixture(s): {', '.join(f.name for f in need)}", flush=True)
        with ThreadPoolExecutor(JOBS) as ex:
            list(ex.map(lambda fx: engine.run(fx, [], tag=f"{fx.name}_boot"), need))
    # 2. the scenarios
    results = {}

    def one(item):
        name, (fx, scs, ev, tag) = item
        t = time.time()
        logs, msgs = engine.run(fx, scs, tag=tag)
        boot = _boot_values(msgs)
        missing = [s.name for s in scs if s.name not in logs]
        if missing:
            r = S.Result()
            r.ok(f"{tag}: scenarios ran", False, f"missing {missing} (Mesen stopped? build/qa/{tag}.log)")
            return name, r, time.time() - t
        try:
            r = ev(logs, boot, tag) if ev.__code__.co_argcount == 3 else ev(logs, boot)
            hits = [(n, c) for n, l in logs.items() for c in l.clobber]
            r.ok(f"{tag}: no static graphics written over a bomber's / Louie's / egg's page", not hits,
                 ", ".join(f"{n} k{k} page {pg} (owner ${o:02X}) VRAM ${v:04X}" for n, (k, pg, o, v) in hits[:4]))
        except Exception as e:      # an evaluator bug must not hide the other suites
            import traceback
            r = S.Result()
            r.ok(f"{tag}: evaluation", False, traceback.format_exc(limit=3)[-600:])
        return name, r, time.time() - t

    ext = [n for n in want if n in SLOW]
    with ThreadPoolExecutor(JOBS) as ex:
        futs = [ex.submit(one, it) for it in todo]
        extf = {n: ex.submit(_external, ["tools/coop4_check.py"] if n == "perf" else ["tools/flame_check.py"]) for n in ext}
        for f in futs:
            name, r, dt = f.result()
            results.setdefault(name, []).extend(r)
        for n, f in extf.items():
            r, dt = f.result()
            results.setdefault(n, []).extend(r)
    # 3. report
    lines, fails, total = [], 0, 0
    for name in want:
        res = results.get(name, [])
        nb = sum(1 for _, ok, _ in res if not ok)
        fails += nb
        total += len(res)
        lines.append(f"== {name}: {len(res) - nb}/{len(res)} ok")
        for check, ok, detail in res:
            if verbose or not ok:
                lines.append(f"  {'ok  ' if ok else 'FAIL'}  {check}" + (f"  ({detail})" if detail else ""))
    full = []
    for name in want:
        for check, ok, detail in results.get(name, []):
            full.append(f"{name:7} {'ok  ' if ok else 'FAIL'}  {check}  {detail}")
    os.makedirs(engine.OUT, exist_ok=True)
    with open(os.path.join(engine.OUT, "report.txt"), "w") as h:
        h.write("\n".join(full) + "\n")
    print("\n".join(lines))
    print(f"{total - fails}/{total} checks ok, {fails} failed, {time.time() - t0:.0f} s  (build/qa/report.txt)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
