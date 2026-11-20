#!/usr/bin/env python3
"""Super Bomberman (USA) song -> note list for tools/sb6/features/sb1_music.py (research tool).

    python tools/sb1_song.py LOG OUT.txt [--loop-search MIN MAX] [--grid 8]

LOG = S-DSP writes of SB1's own driver playing the song from its start, one line per register change:
"START <cycle>", "W <spc cycle> <reg> <value>" (the .spc way, docs/ROM_MAP.md "Super Bomberman 1's sound
driver": a Mesen snapshot of a stage with the song's port 0 command toggled, played by
`Mesen.exe --testrunner X.spc` with a Lua write callback on $F3 that logs changed values and every
KON/KOFF). SB1's driver runs on a 12 ms tick (timer 0 target 96); it keys a note on with KON and ends it by
switching the voice to GAIN mode (ADSR1 = 0, GAIN = the sample's release, e.g. $B4) one or two ticks
before the next note. OUT lists:

    inst <srcn> <ADSR1> <ADSR2> <release GAIN>
    row <ms>         length of a row (16th note) = 24 units
    loop <unit>      the loop start; the song repeats [loop, end) forever
    end <unit>
    <unit> <length> <srcn> <pitch> <VOL L> <VOL R> <voice>    (hex srcn/pitch/volumes, units decimal)

The loop is found as the shortest period (MIN..MAX ticks) after which every note repeats (same voice,
sample, pitch and volumes, +-1 tick). SB1 keys notes on up to ~11 ms off its musical grid (the driver loop's
timing), so times are snapped to quarters of a row (the 16th note, fitted: 133.5 ms in World 1's song) and
written in units of 1/24 row; lengths (key-on to release) are rounded to units.
"""
import argparse
import collections
import math

TICK = 0.012 * 2048000      # SB1 tick in Mesen spc.cycle units


def notes_of(path):
    regs = [[0] * 10 for _ in range(8)]
    cur = [None] * 8
    out, t0 = [], None
    for line in open(path):
        p = line.split()
        if p[0] == "START":
            t0 = int(p[1])
            continue
        if p[0] != "W":
            continue
        c, r, v = int(p[1]), int(p[2], 16), int(p[3], 16)
        t = (c - t0) / TICK
        if r < 0x80 and (r & 15) < 10:
            vo = r >> 4
            regs[vo][r & 15] = v
            n = cur[vo]
            if n is not None and n["rel"] is None and r & 15 == 5 and v == 0:
                n["rel"] = t
        elif r == 0x4C:
            for vo in range(8):
                if v >> vo & 1:
                    g = regs[vo]
                    n = dict(t=t, v=vo, srcn=g[4], pitch=g[2] | g[3] << 8, vl=g[0], vr=g[1],
                             adsr=(g[5], g[6], g[7]), rel=None)
                    out.append(n)
                    cur[vo] = n
        elif r == 0x5C:
            for vo in range(8):
                if v >> vo & 1 and cur[vo] is not None and cur[vo]["rel"] is None:
                    cur[vo]["rel"] = t
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out")
    ap.add_argument("--loop-search", nargs=2, type=int, default=(1000, 9000))
    ap.add_argument("--grid", type=int, default=4, choices=(4, 8, 12, 24),
                    help="steps a row for the key-ons of fast runs (a note that would land on the previous one of its voice)")
    a = ap.parse_args()
    notes = notes_of(a.log)
    t0 = notes[0]["t"]
    for n in notes:
        n["tt"] = round(n["t"] - t0)
        n["d"] = None if n["rel"] is None else max(1, round(n["rel"] - t0) - n["tt"])
    last = notes[-1]["tt"]
    keys = collections.Counter((n["tt"], n["v"], n["srcn"], n["pitch"], n["vl"], n["vr"]) for n in notes)

    def found(n, L):
        return any(keys[(n["tt"] + L + e, n["v"], n["srcn"], n["pitch"], n["vl"], n["vr"])] for e in (-1, 0, 1))

    best = None
    for L in range(a.loop_search[0], min(a.loop_search[1], last)):
        bad = [n["tt"] for n in notes if n["tt"] + L < last - 30 and not found(n, L)]
        start = max(bad) + 1 if bad else 0
        if last - (start + L) < 200:
            continue          # the repeat must be seen for a while
        if best is None or start < best[1]:
            best = (L, start)
    if best is None:
        raise SystemExit("no loop found")
    L, start = best
    # the musical grid: the row length R (ms) and phase that fit the key-ons best (half-row grid)
    ms = [(n["t"] - t0) * 12.0 for n in notes]
    import numpy as np
    x = np.array(ms)
    fit = []
    for R in np.arange(100.0, 200.0, 0.01):
        ph = np.angle(np.exp(2j * np.pi * x / (R / 2)).mean())
        g = R / 2
        r = (x - ph / (2 * np.pi) * g) / g
        fit.append((np.sqrt(np.mean(((r - np.round(r)) * g) ** 2)), R, ph / (2 * np.pi) * g))
    _, R, off = min(fit)
    rows = round(L * 12.0 / R)
    R = L * 12.0 / rows
    ph = np.angle(np.exp(2j * np.pi * x / R).mean()) / (2 * np.pi) * R     # phase of the rows
    U = R / 24

    def unit(t_ms):
        q = (t_ms - ph) / R                      # rows: most key-ons sit within +-4/24 of a row
        k = math.floor(q)
        f = q - k
        if f <= 5 / 24 or f >= 19 / 24:
            return int(round(q)) * 24
        return k * 24 + int(round(f * 4)) * 6    # the few others: quarter rows

    step = 24 // a.grid
    last_u = {}
    for n, t in zip(notes, ms):
        n["u"] = unit(t)
        if n["u"] <= last_u.get(n["v"], -1):     # a fast run: the --grid step instead of the row
            n["u"] = max(int(round((t - ph) / R * a.grid)) * step, last_u[n["v"]] + step)
        last_u[n["v"]] = n["u"]
        # key-on to release in whole SB1 ticks (both sides jitter alike), then in units
        n["du"] = None if n["rel"] is None else max(1, int(round(round(n["rel"] - n["t"]) * 12.0 / U)))
    loop = min(n["u"] for n in notes if n["tt"] >= start)
    loop = int(round(loop / 24.0)) * 24
    end = loop + rows * 24
    nxt = {}
    for n in reversed(notes):
        n["next"] = nxt.get(n["v"])
        nxt[n["v"]] = n["u"]
    # lengths jitter by a tick like the key-ons: values within 2 units of each other (chained) are one
    # length, written as the most common of them
    counts = collections.Counter(n["du"] for n in notes if n["du"] is not None)
    canon, group = {}, []
    for d in sorted(counts):
        if group and d - group[-1] > 2:
            best = max(group, key=lambda k: counts[k])
            canon.update({k: best for k in group})
            group = []
        group.append(d)
    if group:
        best = max(group, key=lambda k: counts[k])
        canon.update({k: best for k in group})
    for n in notes:
        if n["du"] is not None:
            n["du"] = canon[n["du"]]
    inst = {}
    lines = []
    for n in notes:
        if n["u"] >= end:
            break
        lim = (n["next"] if n["next"] is not None else end) - n["u"]
        d = n["du"]
        if d is None or d > lim:
            d = lim
        if d <= 0:
            raise SystemExit(f"notes collide on voice {n['v']} at unit {n['u']}")
        inst.setdefault(n["srcn"], n["adsr"])
        lines.append(f"{n['u']} {d} {n['srcn']:02X} {n['pitch']:04X} {n['vl']:02X} {n['vr']:02X} {n['v']}")
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("# Super Bomberman (USA) song, from the S-DSP writes of its driver (tools/sb1_song.py)\n")
        for s, (a1, a2, gain) in sorted(inst.items()):
            fh.write(f"inst {s:02X} {a1:02X} {a2:02X} {gain:02X}\n")
        fh.write(f"row {R:.3f}\nloop {loop}\nend {end}\n")
        fh.write("\n".join(lines) + "\n")
    print(f"{len(lines)} notes, row {R:.3f} ms, loop at row {loop // 24} ({loop * U / 1000:.2f} s), "
          f"{rows} rows ({rows * R / 1000:.2f} s) repeated")


if __name__ == "__main__":
    main()
