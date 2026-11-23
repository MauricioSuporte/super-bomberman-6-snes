"""SB6 QA suites: scenarios on fixtures (tools/qa/engine.py) and what each one must show.

Facts measured in Mesen for these checks (SB5's ids unless said; docs/ROM_MAP.md has the routines):
  animations ($079F+obj), d = 0 right 1 down 2 left 3 up:
    walk 1+d, stand $46+d, punch $27+d, lift $2C, carry walk $2F+d, carry stand $4A+d, throw $33+d,
    idle (no input ~200 frames) $15, death $16, onto a Louie $17, off it (hit) $19, riding 9+d, cornered $21,
    victory $20, time up $1F; Louie (actor seat + $0128): walk $23+d, idle $3D+d
  sound: commands through $C0:0E7F ("C"): bomb $26, explosion $2A + fire range, pierce bomb's $34 + range,
    kick $27, punch $28, bounce $29, item $3F, lift (group 3 id 2) $50, Louie n's cry $48 + n, Louie hit $42,
    time up $58 + $55, cornered $5E, enemy death $5F, player death $60, 1-6 mecha death (crowd) $61; stage
    clear = request (0, $21) (command 3), boss victory music = request (0, $0F)
  abilities $7E:4ED5+seat: 01 remote, 02 kick, 04 power glove (blue: lift / throw), 08 boxing glove (red:
    punch, Y), 10 pierce, 20 mine, 40 (slow fuse); fire range $17CA+seat; time $0E1E minutes / $0E1D seconds
"""
from .engine import Fixture, Scenario

R, D, L, U = range(4)
DIRS = ("right", "down", "left", "up")
STEP = {R: (1, 0), D: (0, 1), L: (-1, 0), U: (0, -1)}
OPP = {R: L, L: R, D: U, U: D}

WALK, STAND, PUNCH, CARRY_WALK, CARRY_STAND, THROW, RIDE = 0x01, 0x46, 0x27, 0x2F, 0x4A, 0x33, 0x09
LIFT, IDLE, DEATH, MOUNT, DISMOUNT, CORNERED, VICTORY, TIMEUP = 0x2C, 0x15, 0x16, 0x17, 0x19, 0x21, 0x20, 0x1F
LOUIE_WALK, LOUIE_IDLE = 0x23, 0x3D
RIDE_ALL = (0x05, 0x14)       # riding: 4 animations per Louie kind (seen: $05-$08, $09-$0C, $0D-$10, $11-$14)
SFX = dict(bomb=0x26, kick=0x27, punch=0x28, bounce=0x29, item=0x3F, lift=0x50, louie_hit=0x42, timeup=0x58,
           cornered=0x5E, enemy=0x5F, death=0x60, crowd=0x61)
EXPLOSION, PIERCE = 0x2A, 0x34
LOUIE_CRY = 0x48
B_REMOTE, B_KICK, B_GLOVE, B_BOXING, B_PIERCE = 0x01, 0x02, 0x04, 0x08, 0x10

# fixtures: the 7 characters of the picker grid in two Normal Game starts, 4 players, 1-1
FX_A = Fixture("w1_0D_A", picks=((0, 0), (1, 1), (2, 2), (5, 3)))
FX_B = Fixture("w1_0D_B", picks=((3, 1), (4, 2), (6, 1), (0, 4)))
QUAD = ((3, 3), (11, 3), (3, 9), (11, 9))          # each seat's own 5 x 5 arena in 1-1 (no shared flames)
STAGES = {0x0D: "1-1", 0x11: "1-2", 0x18: "1-3", 0x10: "1-4", 0x17: "1-5", 0x67: "1-6", 0x68: "1-7"}


def stage_fx(stage):
    return Fixture(f"s{stage:02X}_4p", stage=stage, ready=120)


def cell(x, y):
    return y * 16 + x


def arenas(seats=range(4), r=2, k=1):
    """Clears each seat's quadrant (collision only) and puts the seat in its middle."""
    st = []
    for s in seats:
        cx, cy = QUAD[s]
        st += [[k, "cell", cell(x, y), 0] for y in range(cy - r, cy + r + 1) for x in range(cx - r, cx + r + 1)]
        st.append([k + 1, "place", s, cx, cy])
    return st


class Result(list):
    """[(check, ok, detail)]"""

    def ok(self, name, cond, detail=""):
        self.append((name, bool(cond), detail))
        return cond


def _has_seq(ids, want):
    """want appears in order (not necessarily adjacent) in ids."""
    it = iter(ids)
    return all(any(x == w for x in it) for w in want)


def _cmds(log, cmd, since=0):
    return [k for k, c in log.cmds if c == cmd and k >= since]


# ---------------------------------------------------------------- characters / picker
def picker_eval(fx):
    def ev(logs, boot):
        res = Result()
        l = logs["p_info"]
        chars, pals, objs = l.value("chars"), l.value("pals"), l.value("objs")
        slots = l.value("slots")
        cg = l.value("cg")
        for s, (c, k) in enumerate(fx.picks):
            res.ok(f"P{s + 1} character {c}", chars[s] == c, f"$16C2 = {chars[s]}")
        res.ok("4 different palettes", len(set(pals[:4])) == 4, " ".join(f"{p:02X}" for p in pals[:4]))
        pk = boot.get("picker_cg")
        for s in range(4):
            slot = slots[objs[s]] if objs[s] != 0xFF else None
            if slot is None:
                res.ok(f"P{s + 1} in the stage", False, "no object")
                continue
            got = cg[32 * slot + 2:32 * slot + 32]
            want = pk[32 * s + 2:32 * s + 32] if pk else None
            res.ok(f"P{s + 1} colors = picked colors", want is not None and got == want,
                   f"slot {slot}" + ("" if pk else ", no picker colors measured"))
        own = [slots[o] for o in objs[:4] if o != 0xFF]
        res.ok("every seat its own OBJ palette", len(set(own)) == 4, f"slots {own}")
        return res
    return ev


def picker_scenarios():
    return [Scenario("p_info", 3, steps=[[1, "read", "chars", 0x16C2, 5], [1, "read", "pals", 0x16DA, 5],
                                         [1, "read", "objs", 0x17FA, 4], [1, "read", "slots", 0x06DF, 0x30],
                                         [1, "readcg", "cg", 128, 128]])]


# ---------------------------------------------------------------- animations (+ their sounds and poses)
def anim_scenarios():
    sc = [Scenario("a_walk", 4 * 40 + 10, pose=(0, 1, 2, 3),
                   steps=arenas() + [[5 + 40 * d, "pad", s, DIRS[d], 36] for d in range(4) for s in range(4)]),
          Scenario("a_idle", 330, steps=[], pose=(0, 1, 2, 3))]
    for d in range(4):
        dx, dy = STEP[d]
        st, st2, st3 = arenas(), arenas(), arenas()
        for s in range(4):
            cx, cy = QUAD[s]
            o = 10 * s
            st += [[1, "poke", 0x4ED5 + s, B_BOXING], [6 + o, "pad", s, "a", 3], [12 + o, "place", s, cx - dx, cy - dy],
                   [20 + o, "pad", s, DIRS[d], 3], [28 + o, "pad", s, "y", 4]]
            st2 += [[1, "poke", 0x4ED5 + s, B_KICK], [6 + o, "pad", s, "a", 3], [12 + o, "place", s, cx - dx, cy - dy],
                    [20 + o, "pad", s, DIRS[d], 25]]
            # lift, walk with it one way, stand facing d, throw it at blocks: it must bounce on to a free cell
            st3 += [[1, "poke", 0x4ED5 + s, B_GLOVE], [3, "cell", cell(cx + 2 * dx, cy + 2 * dy), 0x80],
                    [3, "cell", cell(cx + 3 * dx, cy + 3 * dy), 0x80], [3, "cell", cell(cx + 4 * dx, cy + 4 * dy), 0x80],
                    [6 + o, "pad", s, "a", 3], [14 + o, "pad", s, "a", 70], [24 + o, "pad", s, DIRS[OPP[d]], 14],
                    [44 + o, "pad", s, DIRS[d], 3]]
        sc += [Scenario(f"a_punch_{DIRS[d]}", 100, steps=st, pose=(0, 1, 2, 3)),
               Scenario(f"a_kick_{DIRS[d]}", 90, steps=st2),
               Scenario(f"a_throw_{DIRS[d]}", 200, steps=st3, pose=(0, 1, 2, 3))]
    # cornered: walls all around, a bomb; then (not invincible) the death
    st = arenas()
    for s in range(4):
        cx, cy = QUAD[s]
        st += [[3, "cell", c, 0x30] for c in (cell(cx + 1, cy), cell(cx - 1, cy), cell(cx, cy + 1), cell(cx, cy - 1))]
        st += [[200 + 12 * s, "pad", s, "a", 3]]
    sc.append(Scenario("a_cornered_death", 520, steps=st, invincible=False, pose=(0, 1, 2, 3)))
    sc.append(Scenario("a_timeup", 300, steps=[[1, "poke", 0x0E1E, 0], [1, "poke", 0x0E1D, 2]], pose=(0, 1, 2, 3)))
    # victory: enemies burnt, the door's soft block blown, P1 on the door; the next stage must start
    sc.append(Scenario("a_victory", 900, steps=[[5, "burn", 30], [60, "door_blast", 0], [262, "door", 0],
                                                [264, "pad", 0, "down", 1]], pose=(0, 1, 2, 3)))
    # Louies: every seat takes an egg (types 0-3, then 4-5), rides 4 ways, then a bomb throws it off
    st = []
    side = ((1, "right"), (-1, "left"), (1, "right"), (-1, "left"))      # a free cell next to each corner start
    for s in range(4):
        o = 40 * s
        st += [[2 + o, "louie_type", s], [2 + o, "item", s, 0x15, side[s][0]], [3 + o, "pad", s, side[s][1], 20]]
    st += [[200 + 40 * d, "pad", s, DIRS[d], 36] for d in range(4) for s in range(4)]
    st += [[370, "read", "mobj", 0x17FA + 19, 5], [370, "read", "mchr", 0x16C2 + 19, 5], [370, "read", "slots", 0x06DF, 0x30],
           [370, "read", "pset", 0x2B10, 16], [370, "read", "pobj", 0x17FA, 4]]
    st += [[380 + 10 * s, "pad", s, "a", 3] for s in range(4)]
    sc.append(Scenario("a_louies", 700, steps=st, pose=(0, 1, 2, 3), invincible=False))
    for a, b in ((2, 3), (4, 5)):
        st = [[2, "louie_type", a], [2, "item", 0, 0x15, 1], [3, "pad", 0, "right", 20],
              [42, "louie_type", b], [42, "item", 1, 0x15, -1], [43, "pad", 1, "left", 20]]
        sc.append(Scenario(f"a_cries{a}{b}", 120, steps=st))
    return sc


def anim_eval(fx):
    chars = {s: c for s, (c, _) in enumerate(fx.picks)}

    def poses(res, tag, name, logs):
        """One check per scenario: every seat's frames are poses of its character's sheet."""
        from . import poses as P
        from .engine import pose_file
        try:
            l = logs[name]
            out = P.check(pose_file(tag, name), chars, until=min([k for k, m in l.modes[1:]] or [1 << 30]))
        except FileNotFoundError:
            res.ok(f"{name}: poses", False, "no pose dump")
            return
        bad = {a: v for a, v in out.items() if v[1] or not v[0]}
        res.ok(f"{name}: every frame a pose of the seat's character", not bad,
               "; ".join(f"P{a + 1} (char {chars[a]}) {v[1]} of {v[0]} frames torn, frame:anim "
                         + " ".join(f"{f}:{an:02X}" for f, an in v[2][:3]) for a, v in bad.items()))

    def ev(logs, boot, tag):
        res = Result()
        have = logs.keys()
        if "a_walk" in have:
            l = logs["a_walk"]
            for s in range(4):
                ids = l.anim_ids(s)
                res.ok(f"walk: P{s + 1} walks 4 ways", all(WALK + d in ids for d in range(4)), _ids(ids))
            poses(res, tag, "a_walk", logs)
        if "a_idle" in have:
            l = logs["a_idle"]
            for s in range(4):
                res.ok(f"idle: P{s + 1} plays $15", IDLE in l.anim_ids(s), _ids(l.anim_ids(s)))
        for d in range(4):
            n = DIRS[d]
            if f"a_punch_{n}" in have:
                l = logs[f"a_punch_{n}"]
                for s in range(4):
                    res.ok(f"punch {n}: P{s + 1} ${PUNCH + d:02X}", PUNCH + d in l.anim_ids(s), _ids(l.anim_ids(s)))
                res.ok(f"punch {n}: punch + bounce sounds x4", len(_cmds(l, SFX["punch"])) >= 4 and len(_cmds(l, SFX["bounce"])) >= 4,
                       f"punch {len(_cmds(l, SFX['punch']))}, bounce {len(_cmds(l, SFX['bounce']))}")
                poses(res, tag, f"a_punch_{n}", logs)
            if f"a_kick_{n}" in have:
                l = logs[f"a_kick_{n}"]
                res.ok(f"kick {n}: kick sound x4", len(_cmds(l, SFX["kick"])) >= 4, f"{len(_cmds(l, SFX['kick']))}")
            if f"a_throw_{n}" in have:
                l = logs[f"a_throw_{n}"]
                for s in range(4):
                    ids = l.anim_ids(s)
                    res.ok(f"throw {n}: P{s + 1} lift, carry, stand, throw",
                           _has_seq(ids, [LIFT, CARRY_WALK + OPP[d], CARRY_STAND + d, THROW + d]), _ids(ids))
                lifts = len([1 for k, g, i in l.reqs if (g, i) == (3, 2)])
                res.ok(f"throw {n}: lift sound x4", lifts >= 4 and _cmds(l, SFX["lift"]), f"{lifts} requests, {len(_cmds(l, SFX['lift']))} played")
                res.ok(f"throw {n}: bounces over taken cells", len(_cmds(l, SFX["bounce"])) >= 8,
                       f"{len(_cmds(l, SFX['bounce']))} bounce sounds (>= 2 per bomb)")
                poses(res, tag, f"a_throw_{n}", logs)
        if "a_cornered_death" in have:
            l = logs["a_cornered_death"]
            for s in range(4):
                ids = l.anim_ids(s)
                res.ok(f"cornered: P{s + 1} $21 then $16", _has_seq(ids, [CORNERED, DEATH]), _ids(ids))
            res.ok("cornered: sound $5E", _cmds(l, SFX["cornered"]), "")
            res.ok("death: 4 deaths, sound $60", len({s for _, s in l.deaths}) == 4 and _cmds(l, SFX["death"]),
                   f"deaths {l.deaths}, $60 x{len(_cmds(l, SFX['death']))}")
            poses(res, tag, "a_cornered_death", logs)
        if "a_timeup" in have:
            l = logs["a_timeup"]
            for s in range(4):
                res.ok(f"time up: P{s + 1} $1F", TIMEUP in l.anim_ids(s), _ids(l.anim_ids(s)))
            res.ok("time up: sounds $58 $55", _cmds(l, SFX["timeup"]) and _cmds(l, 0x55), "")
            poses(res, tag, "a_timeup", logs)
        if "a_victory" in have:
            l = logs["a_victory"]
            for s in range(4):
                res.ok(f"victory: P{s + 1} $20", VICTORY in l.anim_ids(s), _ids(l.anim_ids(s)))
            res.ok("victory: enemies' death sound", _cmds(l, SFX["enemy"]) or any(c == SFX["enemy"] for _, c in l.gsfx), "")
            res.ok("victory: clear jingle (request 0/$21)", any((g, i) == (0, 0x21) for _, g, i in l.reqs), "")
            res.ok("victory: next stage 1-2 ($11)", any(m == 0x11 for _, m in l.modes), f"modes {l.modes}")
            poses(res, tag, "a_victory", logs)
        if "a_louies" in have:
            l = logs["a_louies"]
            mobj, mchr = l.value("mobj"), l.value("mchr")
            slots, pset, pobj = l.value("slots"), l.value("pset"), l.value("pobj")
            for s in range(4):
                an = l.anims.get(s, [])
                ids = [a for _, a in an]
                jumps = [k for k, a in an if MOUNT <= a < MOUNT + 4]
                res.ok(f"Louie: P{s + 1} jumps on ($17-$1A)", any(k < 300 for k in jumps), _ids(ids))
                ride = {a for k, a in an if k < 380 and RIDE_ALL[0] <= a <= RIDE_ALL[1]}
                res.ok(f"Louie: P{s + 1} rides 4 ways (4 riding animations, $05-$14 by Louie)", len(ride) == 4, _ids(ids))
                res.ok(f"Louie: P{s + 1} thrown off when hit", any(k >= 380 for k in jumps), _ids(ids))
                lids = l.anim_ids(19 + s)
                res.ok(f"Louie: P{s + 1}'s Louie animates (walk 4 ways, idle)", len(set(lids)) >= 5, _ids(lids))
                res.ok(f"Louie: P{s + 1}'s Louie goes away when hit", l.objs.get(19 + s, [(0, 0)])[-1][1] == 0xFF,
                       f"objects {l.objs.get(19 + s)}")
            cries = [c - LOUIE_CRY for _, c in l.cmds if LOUIE_CRY <= c < LOUIE_CRY + 6]
            kinds = [mchr[i] for i in range(4)] if mchr else []
            res.ok("Louie: 4 hatches (types 0, 1, 2, 3): the 3rd and 4th become one of the 2 loaded kinds",
                   cries[:2] == [0, 1] and len(cries) == 4 and set(cries) <= {0, 1}, f"cries {cries}")
            res.ok("Louie: each cry = the Louie that came out", sorted(cries) == sorted(k for k in kinds if k < 6),
                   f"cries {cries}, Louies {kinds}")
            res.ok("Louie: hit sound $42 x4", len(_cmds(l, SFX["louie_hit"])) >= 4, f"{len(_cmds(l, SFX['louie_hit']))}")
            if mobj:
                lslots = {slots[o] for o in mobj[:4] if o != 0xFF}
                seats = {slots[o] for o in pobj if o != 0xFF}
                res.ok("Louie palettes: in Louie slots ($2B10 = $FF)", lslots and all(pset[sl] == 0xFF for sl in lslots),
                       f"Louie slots {sorted(lslots)}, ids {[pset[sl] for sl in sorted(lslots)]}")
                res.ok("Louie palettes: seats keep their own slots", len(seats) == 4 and not (seats & lslots), f"seats {sorted(seats)}")
                kinds = {mchr[i] for i in range(4) if mobj[i] != 0xFF}
                res.ok("Louie palettes: at most 2 Louie colors at once", len(kinds) <= 2, f"Louie characters {sorted(kinds)}")
            poses(res, tag, "a_louies", logs)
        for a, b in ((2, 3), (4, 5)):
            if f"a_cries{a}{b}" in have:
                l = logs[f"a_cries{a}{b}"]
                cries = [c - LOUIE_CRY for _, c in l.cmds if LOUIE_CRY <= c < LOUIE_CRY + 6]
                res.ok(f"Louie: cries of types {a} and {b} ($48 + type)", cries == [a, b], f"cries {cries}")
        return res
    return ev


def _ids(ids):
    return " ".join(f"{a:02X}" for a in ids[:24])


# ---------------------------------------------------------------- sounds of the bombs, enemies, items
def sfx_scenarios():
    def bombs(name, ranges, bits):
        st = []
        for s, f in enumerate(ranges):
            st += [[1, "poke", 0x17CA + s, f], [1, "poke", 0x4ED5 + s, bits], [5 + 40 * s, "pad", s, "a", 3]]
        return Scenario(name, 340, steps=st)
    return [bombs("s_fire", (1, 2, 5, 8), 0), bombs("s_pierce", (1, 3, 6, 8), B_PIERCE),
            Scenario("s_enemy", 120, steps=[[5, "burn", 30]]),
            Scenario("s_item", 60, steps=[[2, "item", 0, 0x01, 1], [5, "pad", 0, "right", 20]]),
            Scenario("s_remote", 140, steps=[[1, "poke", 0x4ED5, B_REMOTE], [5, "pad", 0, "a", 3], [100, "pad", 0, "b", 3]])]


def sfx_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        for name, base, ranges in (("s_fire", EXPLOSION, (1, 2, 5, 8)), ("s_pierce", PIERCE, (1, 3, 6, 8))):
            l = logs[name]
            res.ok(f"{name}: bomb drop $26 x4", len(_cmds(l, SFX["bomb"])) >= 4, f"{len(_cmds(l, SFX['bomb']))}")
            want = [base + f for f in ranges]
            got = [c for _, c in l.cmds if EXPLOSION < c <= PIERCE + 8]
            res.ok(f"{name}: explosion sound by range " + " ".join(f"${w:02X}" for w in want), got == want,
                   "got " + " ".join(f"${c:02X}" for c in got))
        l = logs["s_enemy"]
        res.ok("enemy death sound $5F", _cmds(l, SFX["enemy"]), "")
        l = logs["s_item"]
        res.ok("item pickup sound $3F", _cmds(l, SFX["item"]), "")
        l = logs["s_remote"]
        ex = [k for k, c in l.cmds if c == EXPLOSION + 2]
        res.ok("remote bomb explodes on B", ex and 100 <= ex[0] <= 110, f"explosion at {ex}")
        return res
    return ev


# ---------------------------------------------------------------- music (and the boot's title / menu music)
def music_scenarios():
    return [Scenario("m_music", 600, steps=[[1, "music"]] + [[k, "read", "song", 0x03CD, 1] for k in (10, 590)])]


def music_eval(stage):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["m_music"]
        u = l.values.get("music_stats")
        if u:
            b = u[-1][1]
            frames, busy, pages = b[0] | b[1] << 8, b[2] | b[3] << 8, b[4:]
            top = sorted(range(256), key=lambda p: -pages[p])[:3]
            res.ok(f"{STAGES[stage]}: music plays (voices sounding)", busy >= frames // 2,
                   f"{busy} of {frames} frames with a voice sounding")
            res.ok(f"{STAGES[stage]}: the save menu stream was released (SPC PC never $70xx-$77xx)",
                   not any(pages[0x70:0x78]),
                   "PC pages " + " ".join(f"${p:02X}:{pages[p] * 4}" for p in top))
        else:
            res.ok(f"{STAGES[stage]}: music measured", False, "no stats")
        res.ok(f"{STAGES[stage]}: >= 50 fps without input (stage frame 300 on)", all(r >= 50 for k, r in l.fps if k >= 240),
               f"{[r for _, r in l.fps]}")
        if stage == 0x0D:
            t = boot.get("title_music")
            res.ok("title: music streams ($0100 = 1, SPC PC in the stream driver $70xx-$77xx)", t and t[0] == 1 and 0x70 <= t[1] < 0x78,
                   f"$0100 = {t[0] if t else '?'}, SPC PC page ${t[1] if t else 0:02X}")
            m = boot.get("menu_music")
            res.ok("Normal Game menu: save menu music ($010A = 2)", m and m[0] == 2, f"$010A = {m[0] if m else '?'}")
        return res
    return ev


# ---------------------------------------------------------------- spawns: every seat's start in every stage
# The rule of tools/coop4_check.py (spawn_safety): with any random soft blocks each seat can drop a bomb and
# hide within 5 + 5 cells, no enemy starts fewer than 6 walking cells away, and a seat is shut in by soft
# blocks in stages that scatter them. Here from the stage fixture's savestate (seconds, not a full run).
CORNERS = ((0, 0), (1, 0), (0, 1), (1, 1))     # (right half, lower half) of P1-P4 outside the boss stages


def spawn_scenarios():
    return [Scenario("sp_start", 260, steps=[[k, "spawn"] for k in range(0, 260, 5)], invincible=False)]


def spawn_eval(stage):
    def ev(logs, boot):
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import coop4_check
        res = Result()
        l = logs["sp_start"]
        snap = [(int(m.split()[1]), m.split(" ", 3)[3].replace("|", "\n")) for m in l.msgs if " spawn " in m]
        name = STAGES[stage]
        has_en = [k for k, t in snap if t.split("enemies")[1].strip()]
        if not snap:
            res.ok(f"{name}: start state read", False, "no spawn line")
            return res
        k0 = has_en[0] + 60 if has_en else snap[-1][0]   # (1-6: no enemies, its rival is seat 4)

        text = min(snap, key=lambda s: abs(s[0] - k0))[1]
        seats = [int(x, 16) for x in text.split("seats ")[1].split("\n")[0].split()]
        res.ok(f"{name}: the 4 seats are in the stage", all(c != 0xFF for c in seats), " ".join(f"{c:02X}" for c in seats))
        res.ok(f"{name}: 4 different start cells", len(set(seats)) == 4, " ".join(f"({c & 15},{c >> 4})" for c in seats))
        if stage not in (0x67, 0x68):
            where = [((c & 15) >= 8, (c >> 4) >= 7) for c in seats]
            res.ok(f"{name}: P1-P4 start in their own corners (P1 top left, P2 top right, P3 bottom left, P4 bottom right)",
                   all(w == (bool(a), bool(b)) for w, (a, b) in zip(where, CORNERS)),
                   " ".join(f"P{s + 1}({c & 15},{c >> 4})" for s, c in enumerate(seats)))
        bad = coop4_check.spawn_safety(text, stage not in (0x67, 0x68))
        res.ok(f"{name}: every start is safe (bomb + hide with any soft blocks, enemies >= 6 cells, shut in)",
               not bad, "; ".join(bad))
        res.ok(f"{name}: nobody dies standing still at the start (stage frames 120-380)", not l.deaths,
               f"deaths {l.deaths}")
        return res
    return ev


# ---------------------------------------------------------------- 1-6: SB1 World 5's tournament
def b16_scenarios():
    st = [[k, "burn", 10, 4] for k in range(300, 3000, 150)]
    st += [[k, "read", "duel", 0x1FBFD, 1] for k in range(0, 3600, 50)]
    st += [[k, "read", "intro", 0x1FBD4, 1] for k in range(0, 400, 5)]
    st += [[k, "read", "pos", 0x182A, 4] for k in range(0, 400, 5)]
    st += [[k, "read", "items", 0x1152, 256] for k in range(0, 3600, 100)]
    st += [[k, "read", "imap", 0x145A, 256] for k in range(2400, 3100, 30)]
    st += [[k, "pad", s, ("left", "right", "up", "down")[s], 20] for k in range(5, 300, 40) for s in range(4)]
    return [Scenario("b16_duels", 3600, steps=st, watch=(4,), exec=(0xC54557,))]


def b16_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["b16_duels"]
        duels = []
        for _, v in l.values.get("duel", []):
            if not duels or duels[-1] != v[0]:
                duels.append(v[0])
        res.ok("1-6: duels white -> black -> Golden ($67 $69 $6B)", duels[:3] == [0x67, 0x69, 0x6B],
               " ".join(f"${d:02X}" for d in duels))
        deaths = [k for k, a in l.anims.get(4, []) if a == DEATH]
        res.ok("1-6: three rivals die", len(deaths) == 3, f"rival deaths at {deaths}")
        crowd = [k for k, c in l.cmds if c == SFX["crowd"]]
        dsfx = [k for k, c in l.cmds if c == SFX["death"]]
        res.ok("1-6: mechas' deaths = crowd $61 (x2)", len(deaths) == 3 and len([k for k in crowd if k < deaths[2]]) == 2,
               f"crowd at {crowd}")
        res.ok("1-6: Golden's death = death sound $60", len(deaths) == 3 and any(k >= deaths[2] - 2 for k in dsfx),
               f"$60 at {dsfx}")
        # intro: the players' pads are held while the rival walks in
        intro = l.values.get("intro", [])
        done = next((k for k, v in intro if v[0] >= 2), None)
        pos = l.values.get("pos", [])
        moved = [k for (k, v), (_, w) in zip(pos, pos[1:]) if done and k < done - 5 and v != w]
        res.ok("1-6 intro: players held until the rival is in", done is not None and not moved,
               f"intro done at {done}, moves at {moved[:5]}")
        rid = [a for _, a in l.anims.get(4, [])]
        res.ok("1-6 intro: rival walks in", WALK + 1 in rid, _ids(rid))
        for s in range(4):
            ids = [a for k, a in l.anims.get(s, []) if done and k < done - 5]   # ("intro" is read every 5 frames)
            res.ok(f"1-6 intro: P{s + 1} no idle / walk", not any(a == IDLE or WALK <= a < WALK + 4 for a in ids), _ids(ids))
        counts = [(k, sum(1 for b in v if b & 0x80)) for k, v in l.values.get("items", [])]
        res.ok("1-6: items appear during the duels", any(n > 0 for k, n in counts if 300 < k < 2500),
               " ".join(f"{k}:{n}" for k, n in counts[:20]))
        drops = [int(m.split()[1]) for m in l.msgs if " exec C54557 A=000B" in m]
        on_map = any(0x0B in v for _, v in l.values.get("imap", []))
        res.ok("1-6: the Golden drops the kick ($0B, SB5 $C5:4557 after its death)",
               len(deaths) == 3 and any(k > deaths[2] for k in drops),
               f"drop at {drops}" + ("" if on_map else " (burnt before it was seen: a bomb of the Golden's went off on it)"))
        res.ok("1-6: victory: all seats $20", all(VICTORY in l.anim_ids(s) for s in range(4)), "")
        res.ok("1-6: boss victory music (request 0/$0F)", any((g, i) == (0, 0x0F) for _, g, i in l.reqs), "")
        res.ok("1-6: next stage 1-7 ($68)", any(m == 0x68 for _, m in l.modes), f"modes {l.modes}")
        res.ok("1-6: >= 50 fps", all(r >= 50 for k, r in l.fps if 120 < k < (deaths[-1] if deaths else 3000)),
               f"worst {min([r for k, r in l.fps if 120 < k] or [0])}")
        return res
    return ev


# ---------------------------------------------------------------- 1-7: SB1 2-8's clown
def b17_scenarios():
    st = [[k, "burn_clown", 8] for k in range(560, 3000, 110)]
    st += [[k, "read", "clown", 0x1E000, 0x40] for k in range(0, 2400, 10)]
    st += [[k, "read", "pos", 0x182A, 4] for k in range(0, 600, 5)]
    st += [[k, "readcg", "bg3", 48, 16] for k in range(0, 2000, 50)]
    st += [[k, "pad", s, ("left", "right", "up", "down")[s], 20] for k in range(5, 400, 40) for s in range(4)]
    st += [[k, "read", "hdma", 0x1E200, 0xE0 * 2] for k in (400, 450)]
    return [Scenario("b17_fight", 2800, steps=st)]


def b17_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["b17_fight"]
        cl = l.values.get("clown", [])
        phase = [(k, v[0]) for k, v in cl]
        hits = [(k, v[8]) for k, v in cl]
        held = [(k, v[0x19]) for k, v in cl]
        fight = next((k for k, p in phase if p >= 3), None)
        res.ok("1-7 intro: players held ($7F:E019 = $A5) until the fight", any(v == 0xA5 for k, v in held if fight and k < fight),
               f"fight from {fight}")
        pos = l.values.get("pos", [])
        moved = [k for (k, v), (_, w) in zip(pos, pos[1:]) if fight and k < fight - 5 and v != w]
        res.ok("1-7 intro: nobody moves", fight is not None and not moved, f"moves at {moved[:5]}")
        for s in range(4):
            ids = [(k, a) for k, a in l.anims.get(s, []) if fight and k < fight]
            bad = [(k, a) for k, a in ids if a == IDLE or WALK <= a < WALK + 4]
            res.ok(f"1-7 intro: P{s + 1} faces up, no idle / walk", not bad and any(a == STAND + U for _, a in ids),
                   " ".join(f"{k}:{a:02X}" for k, a in ids[:10]))
        dark = [(k, v[0x39], v[0x3B]) for k, v in cl]
        res.ok("1-7 intro: the lights go out and come back",
               any(on for _, _, on in dark) and dark and not dark[-1][2], f"{[(k, a, b) for k, a, b in dark if b][:3]}")
        hd = l.value("hdma")
        hole = False
        if hd:
            lines = [(hd[2 * i], hd[2 * i + 1]) for i in range(0xE0)]
            hole = any(0 < a < b < 0xFF for a, b in lines[30:])
        res.ok("1-7 intro: window around the face (light hole)", hole, "")
        hs = [h for _, h in hits]
        res.ok("1-7: 8 hits to beat it", hs and max(hs) == 8 and 0 in hs, f"hits {sorted(set(hs), reverse=True)}")
        red = [(k, v[0x18], v[8]) for k, v in cl]
        bad = [(k, r_, h) for k, r_, h in red if fight and k > fight and (r_ == 1) != (h < 4) and h > 0]
        res.ok("1-7: red colors exactly below half the hits", red and not bad, f"wrong at {bad[:4]}")
        cg = l.values.get("bg3", [])
        if cg:
            def redness(b):
                w = [b[2 * i] | b[2 * i + 1] << 8 for i in range(16)]
                return sum(x & 31 for x in w) - sum(x >> 10 & 31 for x in w)
            first = redness(cg[0][1])
            res.ok("1-7: lower half turns red (BG palette 3)", any(redness(v) > first + 20 for _, v in cg),
                   f"red - blue: start {first}, max {max(redness(v) for _, v in cg)}")
        dead = next((k for k, p in phase if p >= 5), None)
        res.ok("1-7: death explosions (sound $2C)", dead and len([k for k, c in l.cmds if c == 0x2C and k > dead]) >= 10, "")
        res.ok("1-7: victory: all seats $20", all(VICTORY in l.anim_ids(s) for s in range(4)), "")
        res.ok("1-7: boss victory music (request 0/$0F)", any((g, i) == (0, 0x0F) for _, g, i in l.reqs), "")
        res.ok("1-7: next mode $1C", any(m == 0x1C for _, m in l.modes), f"modes {l.modes}")
        res.ok("1-7: no seat died", not l.deaths or all(k > (dead or 0) for k, _ in l.deaths), f"{l.deaths}")
        res.ok("1-7: >= 50 fps", all(r >= 50 for k, r in l.fps if 120 < k < (dead or 2000)),
               f"worst {min([r for k, r in l.fps if 120 < k < (dead or 2000)] or [0])}")
        return res
    return ev


# ---------------------------------------------------------------- 1-6 / 1-7: the seats while an intro holds them
# Held: 1-6 while a rival walks in or the stands blink before the Golden ($7F:FBD4 = 1 / 3), 1-7 while the clown
# appears ($7F:E019 = $A5, its phase $7F:E000 < 3). Every seat faces up ($1632 = 4) in the stand pose of its state:
# on foot $49, on a Louie ($1782 bit 7) its riding animation up (base $05/$09/$0D/$11 + 3), never SB5's idle ($15,
# on a Louie $3F-$40), and its Louie faces up too (the Louie's routine starts with the fade in, stage frame ~100).
# Fixtures with Louies: as one kept from the stage before (Fixture.mounts), stage frame 30 (before the fade in).
LOUIE_KINDS = (0, 2, 4, 5)                # three riding animation groups
RIDE_UP = (0x08, 0x0C, 0x10, 0x14)
HOLD_SKIP = range(0x16, 0x1B)             # death, jumping onto / thrown off a Louie: left alone
MOUNT0 = 19                               # mount actors = seat + $0128 (19 with 4 players)
LOUIE_FROM = 105                          # stage frame from which a Louie's facing is checked
HOLD_GRACE = 6


def mount_fx(stage):
    return Fixture(f"s{stage:02X}_4p_louies", stage=stage, ready=30, mounts=LOUIE_KINDS)


def hold_steps(stage, n):
    st = [[k, "read", "face", 0x1632, MOUNT0 + 4] for k in range(n)]
    st += [[k, "read", "ride", 0x1782, 4] for k in range(n)] + [[k, "lit", "lit"] for k in range(n)]
    if stage == 0x67:
        st += [[k, "read", "iph", 0x1FBD4, 1] for k in range(n)]
    else:
        st += [[k, "read", "chold", 0x1E000, 0x1A] for k in range(n)]
    return st


def hold_eval(res, l, stage, fx, label):
    """The checks above on every held frame the screen shows (HOLD_GRACE frames where a hold starts: 4 seats'
    new poses are 4 strips, one per NMI)."""
    if stage == 0x67:
        held = {k for k, v in l.values.get("iph", []) if v[0] in (1, 3)}
    else:
        held = {k for k, v in l.values.get("chold", []) if v[0x19] == 0xA5 and v[0] < 3}
    lit = {k for k, v in l.values.get("lit", []) if v[0]}
    held = {k for k in held if all(k - i in held for i in range(1, HOLD_GRACE + 1)) and k in lit}
    face = dict(l.values.get("face", []))
    ride = dict(l.values.get("ride", []))

    def anim_at(actor):
        ev, cur, j, out = l.anims.get(actor, []), None, 0, {}
        for k in sorted(face):
            while j < len(ev) and ev[j][0] <= k:
                cur = ev[j][1]
                j += 1
            out[k] = cur
        return out
    res.ok(f"{label}: held frames seen", len(held) > 20, f"{len(held)} frames")
    for s in range(4):
        an = anim_at(s)
        bad, louie_bad, rode = [], [], 0
        for k in sorted(held):
            if k not in face or not an.get(k) or an[k] in HOLD_SKIP:      # (0: not drawn yet)
                continue
            on = ride.get(k, b"\0" * 4)[s] & 0x80
            rode += bool(on)
            ok_anim = an[k] in RIDE_UP if on else an[k] == STAND + U
            if face[k][s] != 4 or not ok_anim:
                bad.append(f"{k}:{an[k]:02X}/{face[k][s]}")
            if on and k + fx.ready >= LOUIE_FROM and face[k][MOUNT0 + s] != 4:
                louie_bad.append(f"{k}:{face[k][MOUNT0 + s]}")
        what = "on a Louie" if fx.mounts else "on foot"
        res.ok(f"{label}: P{s + 1} ({what}) faces up while held, no idle", not bad and (rode > 0) == bool(fx.mounts),
               f"{len(bad)} frames wrong (frame:anim/facing) {' '.join(bad[:8])}; {rode} frames riding")
        if fx.mounts:
            res.ok(f"{label}: P{s + 1}'s Louie faces up while held", not louie_bad,
                   f"{len(louie_bad)} frames wrong (frame:facing) {' '.join(louie_bad[:8])}")


def hold16_scenarios():
    sc = b16_scenarios()[0]
    return [Scenario("hold16", 2200, steps=[s for s in sc.steps if s[0] < 2200 and s[1] != "read"] + hold_steps(0x67, 2200))]


def hold17_scenarios():
    return [Scenario("hold17", 620, steps=hold_steps(0x68, 620) +
                     [[k, "pad", s, ("left", "right", "up", "down")[s], 20] for k in range(5, 400, 40) for s in range(4)])]


def hold_eval_for(stage, fx):
    def ev(logs, boot, tag):
        res = Result()
        name = "hold16" if stage == 0x67 else "hold17"
        hold_eval(res, logs[name], stage, fx, f"{STAGES[stage]} held{' (Louies)' if fx.mounts else ''}")
        return res
    return ev


# ---------------------------------------------------------------- 1-3: chameleons
# Every chameleon (asm/chameleon.asm, state $7F:F800: set up +$000 = 1, phase +$018: 0 frog, 1 copy, 2 changing) has
# sprites on its spot ($182A/$1872 + (0-24, 0-32) in OAM) every frame while alive, as a frog, a copy of a player or
# changing (SB5's stand routine blanked the id $049F every few frames: copies walked unseen until they turned).
CHAM_FX = (Fixture("s18_4p_chamA", stage=0x18, ready=120, picks=((0, 0), (7, 1), (1, 2), (0, 3))),
           Fixture("s18_4p_chamB", stage=0x18, ready=120, picks=((3, 1), (4, 2), (6, 1), (5, 4))))


def cham_scenarios():
    import random
    rnd = random.Random(5)
    n = 2400
    st = []
    side = ((1, "right"), (-1, "left"), (1, "right"), (-1, "left"))
    for s in range(4):          # every seat on a Louie (as in the report: P2 on the pink one from 1-2)
        st += [[2 + 40 * s, "louie_type", LOUIE_KINDS[s]], [2 + 40 * s, "item", s, 0x15, side[s][0]],
               [3 + 40 * s, "pad", s, side[s][1], 20]]
    st += [[k, "pad", s, rnd.choice(DIRS), 22] for k in range(200, n, 24) for s in range(4)]
    st += [[k, "read", "cst", 0x1F800, 24] for k in range(n)] + [[k, "read", "cph", 0x1F818, 24] for k in range(n)]
    st += [[k, "read", "x", 0x182A, 24] for k in range(n)] + [[k, "read", "y", 0x1872, 24] for k in range(n)]
    st += [[k, "readoam", "oam"] for k in range(n)]
    return [Scenario("cham", n, steps=st)]


def cham_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["cham"]
        V = {n: dict(l.values.get(n, [])) for n in ("cst", "cph", "x", "y", "oam")}

        def seen(o, ax, ay):
            for s in range(128):
                x = o[4 * s] | ((o[512 + s // 4] >> (2 * (s % 4))) & 1) << 8
                y = o[4 * s + 1]
                if y < 0xE0 and 0 <= x - ax <= 24 and 0 <= y - ay <= 32:
                    return True
            return False
        bad, frames, copies = {}, 0, 0
        for k in sorted(V["cph"]):
            if k not in V["oam"]:
                continue
            for a in range(5, 24):
                if V["cst"][k][a] != 1 or V["cph"][k][a] > 2:
                    continue
                frames += 1
                copies += V["cph"][k][a] == 1
                if not seen(V["oam"][k], V["x"][k][a], V["y"][k][a]):
                    bad.setdefault(a, []).append(f"{k}:{V['cph'][k][a]}")
        res.ok("1-3: chameleons walk and change into players", frames > 1000 and copies > 300,
               f"{frames} chameleon frames, {copies} as a copy")
        res.ok("1-3: every chameleon drawn every frame (frog, copy, changing)", not bad,
               "; ".join(f"actor {a}: {len(v)} frames unseen (frame:phase) {' '.join(v[:6])}" for a, v in bad.items()))
        res.ok("1-3: >= 50 fps with 4 players on Louies and the chameleons",
               all(r >= 50 for k, r in l.fps if k > 120), f"worst {min([r for k, r in l.fps if k > 120] or [0])}")
        return res
    return ev


# ---------------------------------------------------------------- every stage, P3/P4 out at the start
# A seat of the roster out of the stage (it died without a life) joins with Start while a life is left
# (asm/coop_e4.asm e4_frame -> revive: the nearest safe floor to its spawn cell $4E8D/$4EA5). Its spawn
# cell must be its corner and as safe as a seat's that started there (e4_spawn_all sets it, e4_reserve keeps
# it clear and shut in); Start brings it in there.
def out_fx(stage):
    return Fixture(f"s{stage:02X}_4p_out34", stage=stage, ready=120, absent=(2, 3))


def spawn_out_scenarios(stage):
    t = 600 if stage == 0x68 else 270           # (1-7: the clown's intro holds every pad, Start too)
    st = [[k, "spawn"] for k in range(0, 260, 5)]
    st += [[t - 5, "poke", 0x1D23, 3], [t, "pad", 2, "start", 3], [t + 30, "pad", 3, "start", 3], [t + 70, "spawn"]]
    return [Scenario("sp_out", t + 80, steps=st, invincible=False)]


def spawn_out_eval(stage):
    def ev(logs, boot):
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import coop4_check
        res = Result()
        l = logs["sp_out"]
        snap = [(int(m.split()[1]), m.split(" ", 3)[3].replace("|", "\n")) for m in l.msgs if " spawn " in m]
        name = STAGES[stage]
        if not snap:
            res.ok(f"{name} (P3/P4 out): start state read", False, "no spawn line")
            return res

        def field(text, key):
            return [int(x, 16) for x in text.split(key + " ")[1].split("\n")[0].split()]
        start = [(k, t) for k, t in snap if k < 260]
        has_en = [k for k, t in start if t.split("enemies")[1].split("\n")[0].strip()]
        k0 = has_en[0] + 60 if has_en else start[-1][0]
        text = min(start, key=lambda s: abs(s[0] - k0))[1]
        seats, pts = field(text, "seats"), field(text, "points")
        res.ok(f"{name} (P3/P4 out): P1/P2 in the stage, P3/P4 out", seats[0] != 0xFF and seats[1] != 0xFF
               and seats[2] == 0xFF and seats[3] == 0xFF, " ".join(f"{c:02X}" for c in seats))
        if stage not in (0x67, 0x68):
            where = [((c & 15) >= 8, (c >> 4) >= 7) for c in pts]
            res.ok(f"{name} (P3/P4 out): P3/P4's spawn cells in their corners",
                   all(where[s] == tuple(map(bool, CORNERS[s])) for s in (2, 3)),
                   " ".join(f"P{s + 1}({c & 15},{c >> 4})" for s, c in enumerate(pts)))
        # every seat judged at its spawn cell, as if it stood there
        lines = text.split("\n")
        as_in = "\n".join("seats " + " ".join(f"{c if s < 2 else pts[s]:02X}" for s, c in enumerate(seats))
                          if x.startswith("seats ") else x for x in lines)
        bad = coop4_check.spawn_safety(as_in, stage not in (0x67, 0x68))
        res.ok(f"{name} (P3/P4 out): every spawn cell is safe (bomb + hide with any soft blocks, enemies >= 6 cells,"
               " shut in)", not bad, "; ".join(bad))
        after = field(snap[-1][1], "seats") if snap[-1][0] >= 260 else [0xFF] * 4
        dist = [abs((after[s] & 15) - (pts[s] & 15)) + abs((after[s] >> 4) - (pts[s] >> 4)) if after[s] != 0xFF else 99
                for s in (2, 3)]
        res.ok(f"{name} (P3/P4 out): Start brings P3/P4 in at their spawn cells", all(d <= 1 for d in dist),
               " ".join(f"P{s + 3}({c & 15},{c >> 4})" if c != 0xFF else f"P{s + 3} out" for s, c in enumerate(after[2:])))
        died = [(k, s) for k, s in l.deaths if k > 0]
        res.ok(f"{name} (P3/P4 out): nobody dies standing still", not died, f"deaths {died}")
        return res
    return ev
