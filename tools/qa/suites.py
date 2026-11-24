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
  World 1 portal: object type ($04FF+obj) 6, mapping $049F+obj 1 off / 2 on / 3 blank, cell $1152 bit 6, door cell
    $7F:FB10/11, request (2, $33) when it appears; enemy HP $1662+actor (knights 2, 180 frames grace after a hit)
"""
import os

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
    # (the Normal Game's clock stops with the SB6 HUD, asm/hud.asm time_gate: turned off here to see the pose)
    sc.append(Scenario("a_timeup", 300, steps=[[1, "poke", 0x1FB40, 0], [1, "poke", 0x0E1E, 0], [1, "poke", 0x0E1D, 2]],
                       pose=(0, 1, 2, 3)))
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


# ---------------------------------------------------------------- SB6's items, item border, explosions, bombs, egg
# features/items.py, explosions.py, bombs.py, eggs.py. Seat 0's arena shows the 20 items (show_item: $C5:4557),
# seats 1 (pierce) and 2 drop a bomb, seat 3's arena shows an egg; OAM every frame (the bombs, the egg's loop),
# dumps (tools/qa/dump.py) while the flames are up.
FX_DUMPS = tuple(range(150, 200, 5))
FX_RING = range(40, 116)             # frames whose CGRAM entry 18 (the items' border) is read
FX_OAM = range(10, 196)              # frames whose OAM is read
BG_SC_SHADOW = 0x0368                # BG1SC / BG2SC as the stage writes them (WRAM $0368 / $0369)
OBJ_BASE = 0x6000                    # OBJ name base (word) in a stage
HUD_CG = 32                          # BG3's colors in a stage: CGRAM 0-31 (8 palettes of 4: the HUD, the pause menu)
# but CGRAM 18 (BG palette 1 entry 2 = the items' blinking border, features/items.py) and, in the pause, color 0
# (the pause's NMI makes it black for the panel and puts it back: a dump may see either)
# (the pause's NMI makes it black for the panel and puts it back: a dump may see either); entries 4, 8 ... 28 are
# BG3's see-through color 0 of palettes 1-7 (never drawn by BG3; 4 differs between runs)
HUD_SKIP = (16 + 2,) + tuple(range(4, 32, 4))


def hud_colors(cg, skip=HUD_SKIP):
    return [int(v) for i, v in enumerate(cg[:HUD_CG]) if i not in skip]


def egg_pieces(o):
    """(body, left shadow, right shadow) OAM entries of the egg (features/eggs.py mappings: a 16 x 16 piece then
    two 8 x 8 ones side by side, one Louie half palette), or None."""
    e = _oam(o)
    for i in range(len(e) - 2):
        b, l, r = e[i:i + 3]
        if b[4] and not l[4] and not r[4] and b[3] == l[3] == r[3] >= 3 and r[2] == l[2] + 1 and r[0] == l[0] + 8                 and r[1] == l[1] and 0 < l[1] - b[1] <= 16:
            return b, l, r
    return None


def _flame_words(d, layers=(0, 1)):
    """{(layer, map index): word} of the flame tiles ($010-$07F) on BG1 / BG2."""
    import numpy as np
    w = np.frombuffer(d.vram.tobytes(), "<u2")
    out = {}
    for layer in layers:
        sc = d.wram[BG_SC_SHADOW + layer]
        a0, n = (sc >> 2) << 10, (1, 2, 2, 4)[sc & 3]
        m = w[[(a0 + i) & 0x7FFF for i in range(1024 * n)]]
        for i in np.nonzero(((m & 0x3FF) >= 0x10) & ((m & 0x3FF) < 0x80))[0]:
            out[layer, int(i)] = int(m[i])
    return out


def _oam(o):
    """[(x, y, tile, palette, big)] of the visible OAM entries, in OAM order."""
    out = []
    for i in range(128):
        x, y, t, a = o[4 * i:4 * i + 4]
        hi = o[512 + i // 4] >> (2 * (i % 4))
        if y >= 0xE0:
            continue
        out.append((x | (hi & 1) << 8, y, t | (a & 1) << 8, (a >> 1) & 7, hi >> 1 & 1))
    return out


def egg_frames(seq):
    """SB6 egg frame shown in each OAM read ([(k, oam bytes)]): its body (16 x 16) followed by its two shadow pieces
    (8 x 8, same palette) tell the frame by tile and line distances (features/eggs.py mappings)."""
    import struct
    from sb6.features import eggs
    base = bytes(open(os.path.join(_root(), "Super Bomberman 5 (USA).sfc"), "rb").read())
    sig = {}
    for f, m in enumerate(eggs.mappings(base)):
        (bx, by, bt, _), (sx, sy, st, _) = struct.unpack_from("<hhHB", m, 1), struct.unpack_from("<hhHB", m, 8)
        sig.setdefault((bt - st, by - sy), 1 if f == 3 else f)      # frame 3 = frame 1's pieces
    out = []
    for k, o in seq:
        p = egg_pieces(o)
        out.append((k, sig.get((p[0][2] - p[1][2], p[0][1] - p[1][1])) if p else None))
    return out


def _root():
    from .engine import ROOT
    return ROOT


def fx_scenarios():
    st = arenas()
    cx, cy = QUAD[0]
    cells = [cell(x, y) for y in range(cy - 2, cy + 3) for x in range(cx - 2, cx + 3)
             if abs(x - cx) + abs(y - cy) > 1]
    for i in range(1, 0x15):
        st.append([4, "show_item", cells[i - 1], i])
    ex, ey = QUAD[3]
    st += [[4, "show_item", cell(ex + 1, ey + 1), 0x15]]
    st += [[3, "poke", 0x4ED5 + 1, B_PIERCE], [3, "poke", 0x4ED5 + 2, 0], [10, "pad", 1, "a", 3], [10, "pad", 2, "a", 3]]
    st += [[k, "readcg", "ring", 18, 1] for k in FX_RING]
    st += [[k, "readcg", "hud", 0, HUD_CG] for k in (8, FX_DUMPS[-1])]
    st += [[k, "readoam", "oam"] for k in FX_OAM]
    st += [[k, "dump", f"d{k}"] for k in FX_DUMPS]
    return [Scenario("fx", FX_DUMPS[-1] + 2, steps=st)]


def fx_eval(fx):
    import numpy as np
    from sb6.features import bombs, eggs, explosions, items
    from sb6.features.louies import _low_half
    from sb6.snesgfx import encode_4bpp
    from .dump import Dump
    from .engine import OUT, ROOT
    tiles, words, ring, _, _ = items.build()
    flames = explosions.tiles()
    fire = explosions.fire_words()
    base = open(os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"), "rb").read()
    egg = eggs.tiles(base)
    egg_cols = [(r >> 3) | (g >> 3) << 5 | (b >> 3) << 10 for r, g, b in eggs._palette(base)]
    bomb_pics, _ = bombs.pictures(base)
    bomb_pal = bombs.palette(base)

    def words_of(d, sc):
        """{(screen, i): word} of a BG map (BGnSC value; 32 x 32 screens)."""
        size, a0 = sc & 3, (sc >> 2) << 10
        n = (1, 2, 2, 4)[size]
        w = np.frombuffer(d.vram.tobytes(), "<u2")
        return {(s, i): int(w[(a0 + 1024 * s + i) & 0x7FFF]) for s in range(n) for i in range(1024)}

    def ev(logs, boot, tag):
        res = Result()
        l = logs["fx"]
        dumps = {k: Dump(os.path.join(OUT, f"{tag}.log_fx_d{k}.dump")) for k in FX_DUMPS}
        d0 = dumps[FX_DUMPS[0]]
        # ---- items: tiles $080-$0CF and palette 1
        a = (d0.chr_base(1) + 16 * items.TILES) * 2
        res.ok("items: tiles $080-$0CF = SB6's icons (VRAM)", d0.vram[a:a + len(tiles)].tobytes() == tiles,
               f"BG2 tiles at word {d0.chr_base(1):04X}")
        got = [int(v) for v in d0.cg[16:32]]
        res.ok("items: palette 1 = SB6's item colors (but the border)",
               all(got[e] == words[e] for e in items.ICON_ENTRIES), " ".join(f"{v:04X}" for v in got))
        m2 = words_of(d0, d0.wram[BG_SC_SHADOW + 1])
        shown = {i for i in range(1, 0x15)
                 if sum(1 for w in m2.values() if (w & 0x1C00) == 0x0400 and (w & 0x3FF) - 0x7C - 4 * i in range(4)) >= 4}
        res.ok("items: the 20 items drawn on the field in palette 1", len(shown) == 20,
               f"missing {sorted(set(range(1, 0x15)) - shown)}")
        idx = items.build()[4]
        no_ring = [i for i in items.NO_BORDER if (idx[i] == items.BORDER_ENTRY).any()]
        res.ok("items: Full Fire has no blinking border (no pixel in the border's entry)", not no_ring,
               f"items {no_ring}")
        sb = tiles[128 * (0x10 - 1):128 * 0x10]
        res.ok("items: the slow fuse bomb ($10) shows SB6's search bomb icon",
               items.ICONS[0x10] == "SearchBombIcon" and d0.vram[a + 128 * 15:a + 128 * 16].tobytes() == sb)
        # ---- the border's blink: SB6's colors in its order
        seq = [int.from_bytes(v, "little") for k, v in sorted(l.values.get("ring", []))]
        want = items.blink_sequence()
        ok = len(seq) >= 2 * len(want) and any(
            all(seq[j] == want[(j + o) % len(want)] for j in range(len(seq))) for o in range(len(want)))
        res.ok("items: border blinks SB6's red / orange / yellow in its order (items.BLINK)", ok,
               " ".join(f"{v:04X}" for v in seq[:18]))
        # ---- flames: SB6's, in palette 2 for both bombs (the pierce one too: no palette 0 swap)
        normal = pal0 = 0
        okt = okc = True
        for k, d in dumps.items():
            a = (d.chr_base(0) + 16 * 0x10) * 2
            okt &= d.vram[a:a + len(flames)].tobytes() == flames
            okc &= [int(v) for v in d.cg[32 + explosions.FIRE.start:32 + explosions.FIRE.stop]] == fire
            fl = _flame_words(d, (0,))
            normal = max(normal, sum(1 for w in fl.values() if (w & 0x1C00) == 0x0800))
            pal0 = max(pal0, sum(1 for w in fl.values() if (w & 0x1C00) == 0))
        res.ok("explosions: tiles $010-$07F = SB6's flames (Itens.png, VRAM, every dump)", okt)
        res.ok(f"explosions: palette 2 entries {explosions.FIRE.start}-{explosions.FIRE.stop - 1} = SB6's fire", okc)
        res.ok("explosions: the normal and the pierce bomb's flames in palette 2", normal >= 16 and pal0 == 0,
               f"{normal} palette 2 BG1 flame tiles, {pal0} in palette 0")
        hud = [hud_colors(np.frombuffer(v, "<u2")) for k, v in sorted(l.values.get("hud", []))]
        res.ok("HUD: BG3's colors (CGRAM 0-31 but the items' border) untouched by the explosions",
               len(hud) == 2 and hud[0] == hud[1], " / ".join(" ".join(f"{c:04X}" for c in h) for h in hud))
        # ---- bombs: SB6's pictures in VRAM, SB6's blues in OBJ palette 0, on screen
        vr = d0.vram.tobytes()
        bad = [f"${t:03X}" for t, p in bomb_pics.items()
               if any(vr[(OBJ_BASE + 16 * (t + 16 * dy + dx)) * 2:(OBJ_BASE + 16 * (t + 16 * dy + dx)) * 2 + 32]
                      != encode_4bpp(p[8 * dy:8 * dy + 8, 8 * dx:8 * dx + 8]) for dy in (0, 1) for dx in (0, 1))]
        res.ok("bombs: SB6's bomb pictures in VRAM (normal, pierce, remote, search)", not bad, f"wrong {bad}")
        got = [int(v) for v in d0.cg[128:144]]
        res.ok("bombs: OBJ palette 0 = palette $58 with SB6's blues", got == bomb_pal,
               " ".join(f"{v:04X}" for v in got))
        seen = set()
        for k, o in l.values.get("oam", []):
            for x, y, t, pal, big in _oam(o):
                if pal == 0 and big:
                    seen.add(t)
        res.ok("bombs: a normal bomb (large / medium / small) on screen", {0x10C, 0x10E, 0x120} <= seen,
               " ".join(f"{t:03X}" for t in sorted(seen)))
        res.ok("bombs: a pierce bomb (large / medium / small) on screen", {0x128, 0x12A, 0x12C} <= seen)
        # ---- egg
        d = dumps[FX_DUMPS[0]]
        eg = egg_pieces(d.oam)
        res.ok("egg: on screen (a Louie half palette)", eg)
        if eg:
            slot = eg[0][3]
            half = [int(v) for v in d.cg[128 + 16 * slot:128 + 16 * slot + 16]]
            # entries 8-15 (the stock tiles) or 1-7 + 8 (the copy with pixels 9-15 -> 1-7: asm/louies.asm)
            res.ok("egg: SB6's colors (palette id $51 in a Louie half)",
                   half[8:16] == egg_cols or half[1:8] == egg_cols[1:8],
                   f"slot {slot}: " + " ".join(f"{v:04X}" for v in half))
            body = egg[min(egg)]
            res.ok("egg: SB6's pictures in VRAM", body in vr or _low_half(body) in vr)
        fr = [f for k, f in egg_frames(sorted(l.values.get("oam", [])))]
        runs = []
        for f in fr:
            if not runs or runs[-1][0] != f:
                runs.append([f, 0])
            runs[-1][1] += 1
        tl = [{3: 1}.get(f, f) for f in eggs.timeline()]
        want = []
        for f in tl:
            if not want or want[-1][0] != f:
                want.append([f, 0])
            want[-1][1] += 1
        inner = runs[1:-1]           # the first / last runs are cut by the reads
        order = [f for f, _ in inner]
        names = [f for f, _ in want]
        ok = None not in order and len(order) >= len(names) and any(
            order == [names[(o + j) % len(names)] for j in range(len(order))] for o in range(len(names)))
        res.ok("egg: SB6's idle loop (frames 0 1 2 1 0 1 2 1 7 4 5 6 7 1)", ok,
               " ".join(f"{f}x{n}" for f, n in runs))
        if ok:
            o0 = next(o for o in range(len(names)) if order == [names[(o + j) % len(names)] for j in range(len(order))])
            durs = [(n, want[(o0 + j) % len(want)][1]) for j, (_, n) in enumerate(inner)]
            res.ok("egg: SB6's timing (8 frames a step, 38 on the last)", all(abs(a - b) <= 2 for a, b in durs),
                   " ".join(f"{a}/{b}" for a, b in durs))
        return res
    return ev


# The pierce bomb on every World 1 stage, with the HUD and the pause menu: P1 (invincible) drops pierce bombs from
# its start (A pressed until the stage's intro lets it: the flames are up around frames 235-265 in 1-1; the 1-6 /
# 1-7 intros hold the players longer); then Start opens the pause menu and Start again resumes. A second scenario,
# "plain", does the same without a bomb: its HUD and pause menu are the reference (same frames, same clock).
def pierce_dumps(stage):
    return tuple(range(300, 900, 8)) if stage in (0x67, 0x68) else tuple(range(200, 330, 6))


PAUSE_STAGES = tuple(s for s in STAGES if s != 0x67)      # 1-6 has no pause ($1D1A = 8, docs/ROM_MAP.md)
BURN_STAGE = 0x0D                                        # cell (x, y) = BG1 map tiles (2x, 2y) (no scroll)
PAUSE_FROM = 430                                         # Start is read once $0AEE is set (1-3: frame ~363)
PAUSE_WAIT, RESUME_WAIT = 40, 50                         # frames from Start to the pause / resume dumps
PANEL = (range(9, 24), range(3, 29))                       # the pause menu's frame on BG3 (rows, columns)
BG3_TILES = 0x5000 * 2                                     # BG3 tiles $000-$1FF (2bpp) in a stage (byte address)


def _pause_steps(stage, last):
    if stage not in PAUSE_STAGES:
        return [], last
    p = max(last + 10, PAUSE_FROM)
    st = [[p, "pad", 0, "start", 3], [p + PAUSE_WAIT, "dump", "pause"],
          [p + PAUSE_WAIT + 10, "pad", 0, "start", 3], [p + PAUSE_WAIT + 10 + RESUME_WAIT, "dump", "resume"]]
    return st, p + PAUSE_WAIT + 10 + RESUME_WAIT


def pierce_scenarios(stage):
    last = pierce_dumps(stage)[-1]
    pause, end = _pause_steps(stage, last)
    st = [[1, "invincible", 1], [2, "poke", 0x4ED5, B_PIERCE]] + [[k, "pad", 0, "a", 3] for k in range(6, last - 130, 20)]
    if stage == BURN_STAGE:
        st.append([2, "poke", 0x17CA, 3])       # fire range 3: the flames reach P1's soft blocks
    st += [[k, "dump", f"d{k}"] for k in pierce_dumps(stage)]
    plain = [[1, "invincible", 1], [pierce_dumps(stage)[0], "dump", "hud"]]
    return [Scenario("pierce", end + 2, steps=st + pause), Scenario("plain", end + 2, steps=plain + pause)]


def pierce_eval(stage):
    from sb6.features import explosions
    from .dump import Dump
    from .engine import OUT
    fire = explosions.fire_words()

    def ev(logs, boot, tag):
        res = Result()
        name = STAGES.get(stage, f"${stage:02X}")
        dump = lambda sc, n: Dump(os.path.join(OUT, f"{tag}.log_{sc}_{n}.dump"))
        c2s, at0, at2 = [], set(), set()
        okf = True
        hud_ok, hud_bad = True, []
        first = None
        for k in pierce_dumps(stage):
            d = dump("pierce", f"d{k}")
            fl = _flame_words(d)
            if first is None:
                first = d
            c2 = sum(1 for w in fl.values() if (w & 0x1C00) == 0x0800)
            at2 |= {p for p, w in fl.items() if (w & 0x1C00) == 0x0800}
            at0 |= {p for p, w in fl.items() if (w & 0x1C00) == 0}       # (1-7's own palette 0 tiles: elsewhere)
            c2s.append(c2)
            if c2:
                okf &= [int(v) for v in d.cg[32 + explosions.FIRE.start:32 + explosions.FIRE.stop]] == fire
            if hud_colors(d.cg) != hud_colors(first.cg):
                hud_ok = False
                hud_bad.append(k)
        both = len(at0 & at2)
        res.ok(f"{name}: a pierce bomb's flames in palette 2 (no palette 0 swap)", max(c2s) >= 8 and not both,
               f"{max(c2s)} palette 2 flame words, {both} flame places also in palette 0")
        res.ok(f"{name}: palette 2 entries {explosions.FIRE.start}-{explosions.FIRE.stop - 1} = SB6's fire", okf)
        if stage == BURN_STAGE:
            burning = over = 0
            for k in pierce_dumps(stage):
                d = dump("pierce", f"d{k}")
                fl = _flame_words(d, (0,))
                for c in range(256):
                    v = d.wram[0x1052 + c]
                    if v & 0x20 and v & 0x0F and not v & 0x80:      # a soft block burning in a flame cell
                        burning += 1
                        x, y = 2 * (c & 15), 2 * (c >> 4)
                        over += any((0, (y + dy) * 32 + x + dx) in fl for dy in (0, 1) for dx in (0, 1))
            res.ok(f"{name}: a pierce bomb's flame never covers a burning soft block (only its burning picture, "
                   "as in SB5)", burning and not over, f"{burning} burning flame cells seen, {over} with a flame")
        res.ok(f"{name}: HUD colors (BG3, CGRAM 0-31) unchanged while a pierce bomb's flames burn", hud_ok,
               f"changed at frames {hud_bad[:5]}")
        ref = dump("plain", "hud")
        res.ok(f"{name}: HUD colors = the same frame without a bomb",
               hud_colors(first.cg) == hud_colors(ref.cg), " ".join(f"{v:04X}" for v in hud_colors(first.cg)))
        if stage not in PAUSE_STAGES:
            return res
        pz, rz = dump("pierce", "pause"), dump("plain", "pause")
        rows, cols = PANEL
        panel = lambda d: [d.map_word(2, x, y) for y in rows for x in cols]
        glyphs = sum(1 for w in panel(pz) if 0x100 <= (w & 0x3FF) <= 0x119)
        res.ok(f"{name}: pause menu open (stage frozen, SB6's frame and font on BG3)",
               pz.wram[0x1D1D] == 1 and glyphs >= 40, f"$1D1D = {pz.wram[0x1D1D]}, {glyphs} menu tiles")
        res.ok(f"{name}: pause menu colors (CGRAM 0-31) = without a bomb",
               hud_colors(pz.cg, HUD_SKIP + (0,)) == hud_colors(rz.cg, HUD_SKIP + (0,)),
               " ".join(f"{a:04X}/{b:04X}" for a, b in zip(hud_colors(pz.cg), hud_colors(rz.cg)) if a != b))
        res.ok(f"{name}: pause menu tiles and map = without a bomb",
               panel(pz) == panel(rz) and pz.vram[BG3_TILES:BG3_TILES + 0x200 * 16].tobytes()
               == rz.vram[BG3_TILES:BG3_TILES + 0x200 * 16].tobytes())
        ra, rb = dump("pierce", "resume"), dump("plain", "resume")
        res.ok(f"{name}: resumed (Start), the menu gone and the HUD colors back",
               ra.wram[0x1D1D] == 0 and hud_colors(ra.cg) == hud_colors(rb.cg)
               and not any(0x100 <= (w & 0x3FF) <= 0x119 for w in panel(ra)),
               f"$1D1D = {ra.wram[0x1D1D]}, colors {'ok' if hud_colors(ra.cg) == hud_colors(rb.cg) else 'differ'}, "
               f"{sum(1 for w in panel(ra) if 0x100 <= (w & 0x3FF) <= 0x119)} menu tiles left")
        res.ok(f"{name}: after the pause, the HUD (BG3 rows 0-2) = without a bomb",
               [ra.map_word(2, x, y) for y in range(3) for x in range(32)]
               == [rb.map_word(2, x, y) for y in range(3) for x in range(32)])
        return res
    return ev


# ---------------------------------------------------------------- SB6 HUD (Normal Game, features/hud.py)
# Every stage: the HUD lines on screen (scanlines 1-20) = hud.render() of each seat's
# stats read from WRAM in the same frame (no clock, no score); the clock stopped (time poked to 0:02: no time up);
# >= 50 fps. 1-1: items picked up through SB5's handlers change the cells (fire, full fire, bombs, speed, bomb
# types, kick / bomb pass, punch, glove, heart, soft block pass) and the lives digit; with P3/P4 out of the
# stage their blocks are empty until they join with Start.
HUD_ON = 0x1FB40                     # asm/hud.asm !on ($A5 = shown); poke / read: >= $10000 = bank $7F
HUD_READS = (("bombs", 0x4EBD, 4), ("ab", 0x4ED5, 4), ("on", HUD_ON, 1), ("picks", 0x1FF00, 16))
# (frame, seat, item): SB5 item ids (features/items.py ICONS)
HUD_ITEMS = ((300, 0, 0x01), (300, 1, 0x0B), (300, 2, 0x10), (300, 3, 0x14),
             (310, 0, 0x0E), (310, 1, 0x11), (310, 2, 0x06), (310, 3, 0x03),
             (320, 0, 0x02), (320, 1, 0x0C), (320, 2, 0x0D), (320, 3, 0x04),
             (330, 3, 0x05))
HUD_SHOT = 300                       # the stage has faded in


def _hud_shot(k, name):
    return [[k, "dump", name], [k, "shot", name]] + [[k, "read", f"{name}_{n}", a, c] for n, a, c in HUD_READS]


def hud_scenarios(stage):
    st = [[1, "invincible", 1], [200, "poke", 0x0E1E, 0], [200, "poke", 0x0E1D, 2], [210, "read", "t0", 0x0E1C, 3],
          [400, "read", "t1", 0x0E1C, 3]] + _hud_shot(HUD_SHOT, "base")
    sc = [Scenario("h_base", 410, steps=st)]
    if stage == 0x0D:
        st = [[1, "invincible", 1]] + [[k, "item", s, i] for k, s, i in HUD_ITEMS]
        st += [[330, "poke", 0x1D23, 4]] + _hud_shot(370, "items")
        sc.append(Scenario("h_items", 375, steps=st))
    return sc


def hud_var_fx(stage):
    """Every stage with other characters / colors than stage_fx's: each stage 4 different characters of the
    character select's 7 (all 7 over World 1) and colors spread over their first 25."""
    i = list(STAGES).index(stage)
    return Fixture(f"s{stage:02X}_4p_hudvar", stage=stage, ready=120,
                   picks=tuple(((i + 2 * s) % 7, (5 * i + 7 * s + 3) % 25) for s in range(4)))


def hud_var_scenarios(stage):
    """The HUD with those picks, then every seat given items (as 1-1's h_items) on this stage."""
    st = [[1, "invincible", 1]] + _hud_shot(HUD_SHOT, "base")
    st += [[k + 40, "item", s, i] for k, s, i in HUD_ITEMS] + [[370, "poke", 0x1D23, 4]] + _hud_shot(410, "items")
    return [Scenario("h_var", 415, steps=st)]


def _hud_item_checks(res, name, recs, lives):
    hud, _ = _hud_tables()
    p1, p2, p3, p4 = recs
    res.ok(f"{name}: P1 fire 8 with Full Fire's icon, 2 bombs", p1[1] == 8 and p1[7] == hud.I_FULL and p1[3] == 2, f"{p1}")
    res.ok(f"{name}: P2 kick, punch, power glove", p2[8:11] == (hud.I_KICK, hud.I_PUNCH, hud.I_GLOVE), f"{p2}")
    res.ok(f"{name}: P3 pierce bomb (over the search bomb), soft block pass", p3[4] == hud.I_PIERCE and p3[6] == hud.I_WPASS,
           f"{p3}")
    res.ok(f"{name}: P4 heart, speed 2, remote bomb, bomb pass",
           p4[5] == hud.I_HEART and p4[2] == 2 and p4[4] == hud.I_REMOTE and p4[8] == hud.I_BPASS, f"{p4}")
    res.ok(f"{name}: lives digit 4", lives == 4, f"{lives}")


def hud_var_eval(stage):
    def ev(logs, boot, tag):
        res = Result()
        name = f"{STAGES[stage]} other picks"
        l = logs.get("h_var")
        if not res.ok(f"{name}: HUD scenario ran", l, ""):
            return res
        fx = hud_var_fx(stage)
        pk = l.value("base_picks")
        chars = [c + 1 for c, _ in fx.picks]        # (colors: the picker skips those taken, so not the presses)
        cols = list(pk[8:12]) if pk else []
        res.ok(f"{name}: the character select's choices: characters {chars}, 4 different colors, not the first",
               pk is not None and pk[1] == 1 and list(pk[2:6]) == chars and len(set(cols)) == 4
               and sum(1 for c in cols if c) >= 3, f"{pk.hex() if pk else '?'}")
        recs, _ = _hud_screen(res, name, tag, "h_var", "base", l)
        res.ok(f"{name}: 4 seats in the HUD", all(r[0] for r in recs), f"{recs}")
        recs, lives = _hud_screen(res, f"{name}, items", tag, "h_var", "items", l)
        _hud_item_checks(res, f"{name}, items", recs, lives)
        res.ok(f"{name}: >= 50 fps with the HUD", all(r >= 50 for k, r in l.fps if k >= 240), f"{[r for _, r in l.fps]}")
        return res
    return ev


def hud_pause_scenarios():
    """1-1 (both character sets): the HUD during the pause menu and after it (its menu rewrites BG3)."""
    st = [[1, "invincible", 1]] + _hud_shot(HUD_SHOT, "base") + [[320, "pad", 0, "start", 3]] + _hud_shot(380, "pause")
    st += [[400, "pad", 0, "start", 3]] + _hud_shot(470, "resume")
    return [Scenario("h_pause", 475, steps=st)]


def hud_out_scenarios():
    st = [[1, "invincible", 1], [5, "poke", 0x1D23, 3]] + _hud_shot(HUD_SHOT, "out")
    st += _hud_shot(HUD_SHOT + 64, "out2")             # PUSH START's other blink phase
    st += [[380, "pad", 2, "start", 3]] + _hud_shot(470, "join")
    return [Scenario("h_out", 475, steps=st)]


_HUD = {}


def _hud_tables():
    if not _HUD:
        import struct
        from sb6.features import hud, items
        from sb6.romlib import off
        from .engine import ROM
        rom = open(ROM, "rb").read()
        base = open(os.path.join(_root(), "Super Bomberman 5 (USA).sfc"), "rb").read()
        p1 = list(struct.unpack("<16H", rom[off(items.PALETTE) + 4:off(items.PALETTE) + 36]))
        _HUD.update(hud=hud, t=hud.build(base, p1))
    return _HUD["hud"], _HUD["t"]


def _hud_recs(d, l, name):
    hud, _ = _hud_tables()
    bombs, ab = l.value(f"{name}_bombs"), l.value(f"{name}_ab")
    recs = []
    for s in range(4):
        act = d.wram[0x17FA + s] < 0x80 and not d.wram[0x15A2 + s] & 0x80
        recs.append(hud.record(act, d.wram[0x17CA + s], d.wram[0x15D2 + s] | d.wram[0x15EA + s] << 8, bombs[s], ab[s],
                               d.wram[0x167A + s], d.wram[0x1662 + s]))
    return recs, min(d.wram[0x1D23], 9)


def _hud_screen(res, label, tag, sc, name, l):
    """The screenshot's HUD lines against hud.render(); returns the seat records."""
    import numpy as np
    from PIL import Image
    from .dump import Dump
    from .engine import OUT
    hud, t = _hud_tables()
    d = Dump(os.path.join(OUT, f"{tag}.log_{sc}_{name}.dump"))
    recs, lives = _hud_recs(d, l, name)
    on = l.value(f"{name}_on")
    res.ok(f"{label}: SB6 HUD on ($7F:FB40 = $A5)", on and on[0] == 0xA5, f"{on.hex() if on else '?'}")
    cg = [int(v) for v in d.cg]
    picks = l.value(f"{name}_picks")
    shot = np.asarray(Image.open(os.path.join(OUT, f"{tag}.log_{sc}_{name}.png")).convert("RGB")).astype(int) >> 3
    # an out seat's PUSH START blinks with the frame of its last check (one seat every 4th frame): both phases
    # the backdrop behind the heart (window 2; x WINL is never the heart's): CGRAM 0, or the HUD's blue while the
    # pause blacks CGRAM 0 for the field only
    bk = tuple(int(v) for v in shot[1 + 25, hud.WIN[0]])
    backs = {tuple(hud.rgb5(c)): c for c in (cg[0], hud.P0[hud.BLUE[0]])}
    res.ok(f"{label}: the lives heart's backdrop is CGRAM 0 or the HUD's blue", bk in backs, f"{bk}")
    backdrop = backs.get(bk, cg[0])
    out = [s for s in range(4) if not recs[s][0]]
    best = None
    for m in range(1 << len(out)):
        rr = [list(r) for r in recs]
        for i, s in enumerate(out):
            rr[s][1] = m >> i & 1
        w, o = hud.render(t, cg[16:32], [tuple(r) for r in rr], lives, p0=cg[:16], picks=picks, backdrop=backdrop)
        diff = int(((shot[1:1 + len(w)] != w).any(2) & o).sum())
        if best is None or diff < best[0]:
            best = (diff, w, o, [tuple(r) for r in rr])
    _, want, own, recs = best
    n = len(want)                                              # (screenshot row y + 1 = HUD line y)
    own = own.copy()
    for k in range(128):                                       # the game's sprites are drawn over the HUD (SB5 too)
        x, y, _, _ = d.oam[4 * k:4 * k + 4]
        hb = d.oam[512 + k // 4] >> (2 * (k % 4)) & 3
        x, sz = x - 256 if hb & 1 else x, 16 if hb >> 1 else 8
        if y < 0xE0:
            own[max(y - 1, 0):max(y + sz - 1, 0), max(x, 0):max(x + sz, 0)] = False
    # HUD line 20's start: on busy frames (1-2, 1-6, the pause menu) the line-21 IRQ's scroll writes land after
    # screen line 21 starts, whose first pixels (up to 16 seen) then show HUD line 21's dark green
    same = (shot[1 + 20, :32] == want[21, :32]).all(1)
    k = int(np.argmin(same)) if not same.all() else 32
    own[20, :k] = False
    bad = (shot[1:1 + n] != want).any(2) & own
    rows = sorted({int(y) for y in np.nonzero(bad)[0]})
    where = [(int(y), int(x)) for y, x in zip(*np.nonzero(bad))][:6]
    # a chosen head never touches its grid: the HEAD_GAP columns left of the grid's line (x + 16) are the HUD's
    # blue on the head's lines (2-17) for every seat in the game (heads of the character select only)
    if picks and picks[1] == 1:
        blue = np.array(hud.rgb5(cg[hud.BLUE[0]]))
        gap = []
        for s, r in enumerate(recs):
            if not r[0]:
                continue
            x = hud.SEAT_X[s] + 16
            col = shot[1 + 2:1 + 18, x - hud.HEAD_GAP:x]
            sprite = own[2:18, x - hud.HEAD_GAP:x]
            gap.append((s + 1, int(((col != blue).any(2) & sprite).sum())))
        res.ok(f"{label}: {hud.HEAD_GAP} pixel of blue between each head and its grid (every seat in the game)",
               gap and all(n == 0 for _, n in gap), f"(seat, pixels not blue) {gap}")
    res.ok(f"{label}: HUD on screen = each seat's stats / PUSH START, heads of the chosen characters, dividers, "
           f"the lives tab (lines 1-31)",
           not bad.any(), f"{int(bad.sum())} pixels differ, HUD lines {rows[:8]} (line, x: {where}); records {recs}, lives {lives}, "
           f"picks {picks.hex() if picks else '?'}")
    return recs, lives


def hud_eval(stage):
    def ev(logs, boot, tag):
        import numpy as np
        res = Result()
        name = STAGES[stage]
        l = logs.get("h_base")
        if not res.ok(f"{name}: HUD scenario ran", l, ""):
            return res
        recs, _ = _hud_screen(res, name, tag, "h_base", "base", l)
        hud, _ = _hud_tables()
        from .dump import Dump
        from .engine import OUT
        cg15 = int(Dump(os.path.join(OUT, f"{tag}.log_h_base_base.dump")).cg[hud.PURPLE_ENTRY])
        res.ok(f"{name}: CGRAM {hud.PURPLE_ENTRY} = the HUD's purple (SB6's purple skins)", cg15 == hud.PURPLE,
               f"${cg15:04X} (want ${hud.PURPLE:04X})")
        res.ok(f"{name}: 4 seats in the HUD", all(r[0] for r in recs), f"{recs}")
        t0, t1 = l.value("t0"), l.value("t1")
        res.ok(f"{name}: the clock stopped at 0:02 (no time limit in the Normal Game)",
               t0 is not None and t0 == t1 and t1[1:] == bytes([2, 0]), f"{t0.hex() if t0 else '?'} -> {t1.hex() if t1 else '?'}")
        res.ok(f"{name}: no time up", not any(TIMEUP in l.anim_ids(s) for s in range(4)) and not _cmds(l, SFX["timeup"]), "")
        res.ok(f"{name}: >= 50 fps with the HUD", all(r >= 50 for k, r in l.fps if k >= 240), f"{[r for _, r in l.fps]}")
        if stage == 0x0D:
            hud, t = _hud_tables()
            bad = []
            blue = np.array(hud.rgb5(hud.HUD_P0[hud.BLUE[0]]))
            for c in range(len(t["heads"])):
                for k in range(t["head_counts"][c]):
                    picks = bytes([0, 1] + [c + 1] * 4 + [0, 0] + [k] * 4 + [0] * 4)
                    img, _ = hud.render(t, t["p1"], [hud.record(1, 1, 0xC0, 1, 0, 0, 0)] * 4, 3, picks=picks)
                    for s in range(4):
                        x = hud.SEAT_X[s] + 16
                        if (img[2:18, x - hud.HEAD_GAP:x] != blue).any():
                            bad.append((hud.PORTRAITS[c], k + 1, s + 1))
            res.ok("every character and color of the character select in every seat (hud.render): a pixel of blue "
                   "between the head and its grid", not bad, f"{len(bad)} touch: {bad[:6]}")
        l = logs.get("h_items")
        if l:
            hud, _ = _hud_tables()
            recs, lives = _hud_screen(res, f"{name} items", tag, "h_items", "items", l)
            _hud_item_checks(res, "items", recs, lives)
        return res
    return ev


def hud_pause_eval(logs, boot, tag):
    res = Result()
    l = logs.get("h_pause")
    if not res.ok("1-1 pause: HUD scenario ran", l, ""):
        return res
    for name in ("base", "pause", "resume"):
        _hud_screen(res, f"1-1 {name}", tag, "h_pause", name, l)
    return res


def _push_centered(res, label, tag, sc, name, recs):
    """PUSH START of each out seat shown in this shot: its pixels' left / right margins in the blue between the
    seat's dividers (hud.blue_span) differ by at most 1."""
    import numpy as np
    from PIL import Image
    from .engine import OUT
    hud, _ = _hud_tables()
    shot = np.asarray(Image.open(os.path.join(OUT, f"{tag}.log_{sc}_{name}.png")).convert("RGB")).astype(int) >> 3
    text = [np.array(hud.rgb5(hud.P0[e])) for e in (1, 2, 3)]   # BG3 palette 0: PUSH START's colors
    seen = []
    for s, r in enumerate(recs):
        if r[0] or not r[1]:
            continue
        a, b = hud.blue_span(s)
        part = shot[1 + 2:1 + 19, a:b + 1]                     # HUD lines 2-18
        xs = np.nonzero(np.any([(part == c).all(2) for c in text], 0).any(0))[0]
        if not len(xs):
            seen.append((s + 1, None))
            continue
        seen.append((s + 1, int(xs[0]), int(b - a - xs[-1])))
    res.ok(f"{label}: PUSH START centered between the seat's dividers (left / right margins within 1 pixel)",
           seen and all(len(v) == 3 and abs(v[1] - v[2]) <= 1 for v in seen), f"(seat, left, right) {seen}")


def hud_out_eval(logs, boot, tag):
    res = Result()
    l = logs.get("h_out")
    if not res.ok("1-1 P3/P4 out: HUD scenario ran", l, ""):
        return res
    recs, lives = _hud_screen(res, "1-1 P3/P4 out", tag, "h_out", "out", l)
    res.ok("P3/P4 out: their blocks out, lives 3", [r[0] for r in recs] == [1, 1, 0, 0] and lives == 3, f"{recs}, {lives}")
    recs2, _ = _hud_screen(res, "1-1 P3/P4 out, 64 frames later", tag, "h_out", "out2", l)
    _push_centered(res, "1-1 P3/P4 out", tag, "h_out", "out" if recs[2][1] else "out2", recs if recs[2][1] else recs2)
    ph = [(r[1], r2[1]) for r, r2 in zip(recs[2:], recs2[2:])]
    res.ok("P3/P4 out: PUSH START blinks (shown in one shot, hidden in the other)",
           [r[0] for r in recs2] == [1, 1, 0, 0] and all(sorted(p) == [0, 1] for p in ph), f"{ph}")
    recs, lives = _hud_screen(res, "1-1 P3 joined", tag, "h_out", "join", l)
    res.ok("P3 joined with Start: its block drawn, lives 2", [r[0] for r in recs] == [1, 1, 1, 0] and lives == 2,
           f"{recs}, {lives}")
    return res


# ---------------------------------------------------------------- portal
# World 1's exit portal (features/portal.py, asm/world1.asm portal_task): SB1's, at the middle cell (7, 6) once
# every enemy is dead and that cell's soft block is gone; appears (off 3 / blank 3 x 5, off 30), then open
# (on 3 / off 3); SB5's portal sound (group 2 $33) when it appears; a player on it ends the stage.
PORTAL_CELL = 0x67
PORTAL_SFX_CMD = 0x62                    # features/portal_sfx.py CMD (SB1's bell echo; asm/game_sfx.asm sends it
                                         # instead of SB5's $57 when the portal asks for group 2 $33)
PORTAL_TYPE = 6
PORTAL_NEXT = {0x0D: 0x11, 0x11: 0x18, 0x18: 0x10, 0x10: 0x17, 0x17: 0x67}
PORTAL_FROM, PORTAL_TO = 120, 340        # the cell's soft block goes at PORTAL_FROM; per-frame reads until PORTAL_TO


def portal_fx(stage):
    return Fixture(f"s{stage:02X}_4p_r300", stage=stage, ready=300)


def portal_scenarios(stage):
    c = PORTAL_CELL
    st = [[1, "cell", c, 0x30], [1, "poke", 0x145A + c, 0], [1, "poke", 0x1152 + c, 0], [5, "burn", 30]]
    if stage == 0x17:                    # 1-5's knights: 2 HP and 180 frames of grace after a hit -> one burn, 1 HP
        st += [[1, "poke", 0x1662 + x, 1] for x in range(5, 24)]
    st += [
          [100, "read", "t100", 0x04FF, 0x60], [PORTAL_FROM, "cell", c, 0]]
    st += [[PORTAL_FROM - 2, "dsplog"]]
    st += [[k, "read", f"m{k}", 0x049F, 0x60] for k in range(PORTAL_FROM, PORTAL_TO)]
    st += [[PORTAL_TO - 1, "read", "t", 0x04FF, 0x60], [PORTAL_TO - 1, "read", "dyn", 0x1152 + c, 1],
           [PORTAL_TO - 1, "read", "door", 0x1FB10, 2], [PORTAL_TO, "door", 0], [PORTAL_TO + 2, "pad", 0, "down", 1]]
    st += [[k, "read", f"d{k}", 0x1152 + c, 1] for k in range(PORTAL_FROM, PORTAL_TO, 10)]
    return [Scenario("portal", PORTAL_TO + 900, steps=st)]


def _runs(seq):
    out = []
    for v in seq:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def _portal_sound(res, name, l, tag):
    """What the S-DSP played: SB1's bell (directory entry portal_sfx.SRC = that stage's copy of SB1's sample $06),
    the fifth (pitch $1000 / x1.5) four times, each pair quieter (SB1's echo)."""
    from sb6.features import portal_sfx as P
    regs, kon = {}, []
    for k, cyc, r, v in l.dsp:
        regs[r] = v
        if r == 0x4C and v:
            for n in range(8):
                if v >> n & 1 and regs.get(n * 16 + 4) == P.SRC:
                    b = n * 16
                    kon.append((k, regs.get(b + 2, 0) | regs.get(b + 3, 0) << 8, regs.get(b, 0), regs.get(b + 5), regs.get(b + 6)))
    lo, hi = P.SB1_PITCH, P.SB1_PITCH * 2 ** (7 / 12)
    pitches = [p for _, p, _, _, _ in kon]
    vols = [v for _, _, v, _, _ in kon]
    ok = (len(kon) == 8 and all(abs(p - (lo if i % 2 == 0 else hi)) / p < 0.003 for i, p in enumerate(pitches))
          and all(vols[i] == vols[i + 1] for i in range(0, 8, 2)) and all(vols[i] > vols[i + 2] for i in range(0, 6, 2))
          and all((a1, a2) == P.ADSR[:2] for _, _, _, a1, a2 in kon))
    res.ok(f"{name}: the S-DSP plays SB1's bell echo (8 key-ons of directory ${P.SRC:02X}: $1000 / a fifth up, "
           "4 times quieter, ADSR DD 94)", ok, " ".join(f"{k}:{p:04X}/{v:02X}" for k, p, v, _, _ in kon[:10]))
    try:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "build", "qa",
                            f"{tag}.log_portal")
        aram, dsp = open(base + "_aram.bin", "rb").read(), open(base + "_dsp.bin", "rb").read()
    except OSError as e:
        res.ok(f"{name}: directory ${P.SRC:02X} is SB1's bell", False, str(e))
        return
    d = dsp[0x5D] << 8
    s = aram[d + 4 * P.SRC] | aram[d + 4 * P.SRC + 1] << 8
    img = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "assets", "sound", "sb1_stage_w1.bin"), "rb").read()
    bell = img[0x6BD8 - 0x800:0x6BD8 - 0x800 + 4005]          # SB1 sample $06 (same in every World 1 song)
    res.ok(f"{name}: directory ${P.SRC:02X} is SB1's bell (sample $06, 4005 bytes) in this stage's ARAM",
           aram[s:s + len(bell)] == bell, f"${s:04X}")


def portal_eval(stage):
    name = STAGES[stage]

    def ev(logs, boot, tag):
        res = Result()
        l = logs.get("portal")
        if not l:
            res.ok(f"{name}: portal scenario ran", False, "no log")
            return res
        t100, t = l.value("t100"), l.value("t")
        res.ok(f"{name}: no portal while the middle cell holds a soft block",
               PORTAL_TYPE not in t100, f"types {t100.hex()}")
        objs = [i for i, v in enumerate(t) if v == PORTAL_TYPE]
        res.ok(f"{name}: one portal object", len(objs) == 1, f"type 6 objects {objs}")
        res.ok(f"{name}: the door is the middle cell (7, 6)", l.value("door") == bytes([7, 6]), l.value("door").hex())
        if len(objs) == 1:
            o = objs[0]
            seq = [l.value(f"m{k}")[o] for k in range(PORTAL_FROM, PORTAL_TO)]
            runs = [r for r in _runs(seq) if r[0]]
            want = [[1, 3], [3, 3]] * 5       # the frame it is made also sends its sound (SPC handshake): 3 or 4
            res.ok(f"{name}: portal appears (off 3 / blank 3 x5, off 30)", runs[1:10] == want[1:]
                   and runs[0][0] == 1 and runs[0][1] in (3, 4) and runs[10][0] == 1
                   and 30 <= runs[10][1] <= 32,
                   " ".join(f"{v}x{n}" for v, n in runs[:14]))
            opened = runs[11:-1]
            res.ok(f"{name}: then blinks on 3 / off 3", len(opened) >= 6 and all(
                (v, n) in ((2, 3), (1, 3)) for v, n in opened) and opened[0][0] == 2,
                " ".join(f"{v}x{n}" for v, n in runs[11:20]))
        marks = " ".join(f"{l.value(f'd{k}')[0]:02X}" for k in range(PORTAL_FROM, PORTAL_TO, 10))
        res.ok(f"{name}: the cell is a portal ($1152 bit 6)", bool(l.value("dyn")[0] & 0x40), marks)
        snd = [k for k, g, i in l.reqs if (g, i) == (2, 0x33)]
        res.ok(f"{name}: portal sound once (group 2 $33), after the block", len(snd) == 1 and snd[0] >= PORTAL_FROM,
               f"at {snd}")
        sent = [k for k, c in l.cmds if c == PORTAL_SFX_CMD and snd and snd[0] <= k <= snd[0] + 1]
        res.ok(f"{name}: its sound reaches the SPC (command ${PORTAL_SFX_CMD:02X}; asm/game_sfx.asm mutes $33 "
               "otherwise)", len(sent) == 1, f"commands {[(k, hex(c)) for k, c in l.cmds if k >= PORTAL_FROM][:6]}")
        _portal_sound(res, name, l, tag)
        res.ok(f"{name}: entering it leads to ${PORTAL_NEXT[stage]:02X}",
               any(m == PORTAL_NEXT[stage] for _, m in l.modes), f"modes {l.modes}")
        return res
    return ev
