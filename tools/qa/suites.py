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
    punch, Y), 10 pierce, 20 magnet bomb (SB5's mine), 40 search bomb; fire range $17CA+seat; time $0E1E minutes / $0E1D seconds
  World 1 portal: object type ($04FF+obj) 6, mapping $049F+obj 1 off / 2 on / 3 blank, cell $1152 bit 6, door cell
    $7F:FB10/11, request (2, $33) when it appears; enemy HP $1662+actor (knights 2, 180 frames grace after a hit)
  Louie abilities: Y on a Louie -> $C4:54F6 by type $16C2 (0 red punch: $15BA, request (2, $38); 1 green dash: $1782
    bit 0; 2 pink jump: $1782 bit 1, (2, $23); 3 yellow; 4 bomb throw: $0E90 bit 5; 5 a bomb under the rider; 6 black,
    SB6: (2, $35)); enemy routine pointer $155A/$1572/$158A+actor; SB6 state $7F:E800 (!PUSH +$18, !TRAIN +$1C0);
    $15A2 bit 2 = no flame test (also SB5's start shield), $170A vest timer; these fixtures' main loop runs from
    scenario frame ~52 (steps at T0 + k)
"""
import os

from . import engine
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

# fixtures: the 8 characters of the picker grid in three Normal Game starts, 4 players, 1-1 (FX_C: char7 twice,
# P1 on color 31 = palette id $FC + seat, past the direct ids; P3 on color 4)
FX_A = Fixture("w1_0D_A", picks=((0, 0), (1, 1), (2, 2), (5, 3)))
FX_B = Fixture("w1_0D_B", picks=((3, 1), (4, 2), (6, 1), (0, 4)))
FX_C = Fixture("w1_0D_C", picks=((7, 30), (1, 0), (7, 3), (2, 5)))
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
        st2 = [[1, "burn", 4]] + st2            # (no enemy in a kicked bomb's way: it depends on the fixture)
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
            p = boot.get("picker_music")
            res.ok("character selection (before the save files): its music streams ($010A = 3, $0100 = 1)",
                   p and p[0] == 3 and p[1] == 1, f"$010A = {p[0] if p else '?'}, $0100 = {p[1] if p else '?'}")
            m = boot.get("menu_music")
            res.ok("Normal Game menu after the picker: save menu music ($010A = 2)", m and m[0] == 2,
                   f"$010A = {m[0] if m else '?'}")
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


# ---------------------------------------------------------------- game over -> continue (co-op)
# Every seat dies without a life, P3 last: SB5's game over ($C5:3B37) runs the player reset ($C4:286F, co-op
# c4_tail). $1D25 was co-op's participant mask then ($04): it left !count ($0129) 1 and a stage with no bomber,
# retried forever. Continue (Start on the game over screen and the world map) must bring the 4 seats back.
def gameover_scenarios():
    st = [[5, "poke", 0x1D23, 0]] + [[400 + 120 * i, "burn", 30, s] for i, s in enumerate((0, 1, 3, 2))]
    st += [[k, "read", "m", 0x1031, 1] for k in range(0, 2100, 10)]
    st += [[k, "read", "c", 0x0129, 4] for k in range(0, 2100, 10)]
    st += [[k, "read", "o", 0x17FA, 4] for k in range(0, 2100, 10)]
    st += [[k, "pad", 0, "start", 4] for k in range(700, 1700, 90)]
    return [Scenario("gameover", 2100, steps=st, invincible=False)]


def gameover_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["gameover"]
        m, c, o = (dict(l.values.get(n, [])) for n in ("m", "c", "o"))
        over = next((k for k in sorted(m) if m[k][0] == 0x08), None)
        back = next((k for k in sorted(m) if over and k > over and m[k][0] == 0x0D), None)
        res.ok("game over (P3 last) -> continue: the stage starts again", back is not None, f"game over {over}, stage {back}")
        end = max(o) if o else None
        res.ok("continue: 4 players again (!count 4, every seat in !pmask), 4 bombers in the stage",
               back is not None and c[end][0] == 4 and c[end][3] == 0x0F and all(b != 0xFF for b in o[end]),
               f"count/roster/pmask {c[end].hex() if end else '-'}, objects {o[end].hex() if end else '-'}")
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
        from sb6.features import voice_sfx as V
        starts = [k for k, c in l.cmds if c == V.CMD]
        jing = [k for k, g, i in l.reqs if (g, i) == (0, 0x20) and (len(deaths) < 3 or k < deaths[2])]   # (not 1-7's)
        # (the start jingle plays once, when the white duel begins: the next duels follow on without it)
        res.ok("1-6: SB6's \"start\" voice after the start jingle (SFX $63)",
               len(jing) >= 1 and all(any(j < k < j + 120 for k in starts) for j in jing),
               f"jingles {jing}, $63 at {starts}")
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
        placed = [int(m.split()[1]) for m in l.msgs if " exec C54557 " in m]   # (an item may be taken within 100 frames)
        res.ok("1-6: items appear during the duels", any(n > 0 for k, n in counts if 300 < k < 2500)
               or any(300 < k < 2500 for k in placed),
               f"placed at {placed[:8]}; " + " ".join(f"{k}:{n}" for k, n in counts[:20]))
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


# 1-6 with P3/P4 out at the start (they join with Start later): before the Golden Bomber (the stands' last
# blackout, asm/world1.asm spawn_reset) every seat goes back to its start: P1/P2 where they started, P3/P4 their
# spawn cells $4E8D/$4EA5 (keep_spawn; before, their stale x/y from before they joined). x = column * 16,
# y = row * 16 ($182A / $1872); intro phase $7F:FBD4 (3 = the stands blink, then 0 / 1 the Golden walks in).
def b16_out_scenarios():
    st = [[0, "read", "sx", 0x4E8D, 4], [0, "read", "sy", 0x4EA5, 4], [0, "read", "x0", 0x182A, 4],
          [0, "read", "y0", 0x1872, 4], [265, "poke", 0x1D23, 3], [270, "pad", 2, "start", 3], [300, "pad", 3, "start", 3]]
    st += [[k, "burn", 10, 4] for k in range(400, 3000, 150)]
    st += [[k, "pad", s, ("left", "right", "up", "down")[s], 20] for k in range(340, 1200, 40) for s in range(4)]
    st += [[k, "read", "iph", 0x1FBD4, 1] for k in range(0, 3600, 5)]
    st += [[k, "read", "x", 0x182A, 4] for k in range(0, 3600, 5)]
    st += [[k, "read", "y", 0x1872, 4] for k in range(0, 3600, 5)]
    return [Scenario("b16_out", 3600, steps=st)]


def b16_out_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["b16_out"]
        sx, sy, x0, y0 = (l.value(n) for n in ("sx", "sy", "x0", "y0"))
        want = [(x0[s], y0[s]) if s < 2 else (sx[s] * 16, sy[s] * 16) for s in range(4)] if sx and x0 else None
        iph = dict(l.values.get("iph", []))
        xs, ys = dict(l.values.get("x", [])), dict(l.values.get("y", []))
        blink = [k for k in sorted(iph) if iph[k][0] == 3]
        after = next((k for k in sorted(iph) if blink and k > blink[-1]), None)
        got = [(xs[after][s], ys[after][s]) for s in range(4)] if after in xs else None
        cell = lambda p: f"({(p[0] + 8) >> 4},{(p[1] + 8) >> 4})"
        res.ok("1-6 (P3/P4 joined later): before the Golden every seat is back at its start",
               bool(want and got) and got == want,
               f"at {after}: " + (" ".join(cell(p) for p in got) if got else "-") +
               " want " + (" ".join(cell(p) for p in want) if want else "-"))
        return res
    return ev


# ---------------------------------------------------------------- 1-7: SB1 2-8's clown
CLOWN_HITT, CLOWN_INVT = 96, 192    # asm/sb1_enemies.asm !HITT, !INVT


def b17_scenarios():
    st = [[k, "burn_clown", 8] for k in range(560, 3000, 110)]
    st += [[k, "read", "clown", 0x1E000, 0x40] for k in range(0, 2400, 10)]
    st += [[k, "read", "pos", 0x182A, 4] for k in range(0, 600, 5)]
    st += [[k, "readcg", "bg3", 48, 16] for k in range(0, 2000, 50)]
    st += [[k, "pad", s, ("left", "right", "up", "down")[s], 20] for k in range(5, 400, 40) for s in range(4)]
    st += [[k, "read", "hdma", 0x1E200, 0xE0 * 2] for k in (400, 450)]
    st += [[k, "read", "cwh", 0x1E000, 0x40] for k in range(500, 2700)]     # every frame: the hits' blink / pictures
    st += [[1, "hdmawatch", 3600]]
    return [Scenario("b17_fight", 3600, steps=st)]


# 1-7's darkness with one player (P2-P4 out of the stage, PUSH START): the intro's hold rewrote SB5's
# frames-standing count to 0 every frame, SB5 sent the stand pose's strip again each frame (1 KB of vblank) and
# the NMI ended on lines 2-130 of the next frame, after the HDMA init: stray lit lines, the light hole gone.
B17_1P = Fixture("s68_1p", stage=0x68, players=1, ready=30)


def b17_dark_scenarios():
    st = [[1, "hdmawatch", 1500]]
    st += [[k, "read", "clown", 0x1E000, 0x40] for k in range(0, 1500, 10)]
    st += [[k, "shot", f"f{k:04d}"] for k in range(420, 520, 4)]
    return [Scenario("b17_dark", 1500, steps=st)]


def dark_lines(path):
    """Mean brightness of each line of a screenshot at its sides (x 24-71, 184-231: outside the light hole)."""
    from PIL import Image
    px = Image.open(path).convert("RGB").load()
    xs = list(range(24, 72, 2)) + list(range(184, 232, 2))
    return [sum(sum(px[x, y]) for x in xs) / len(xs) for y in range(224)]


def hdma_ok(res, l, who):
    late = [h for h in l.hdma_late if h[2]]     # (a late write of 0, nothing on: loading, fades, harmless)
    res.ok(f"1-7 {who}: the NMI ends inside the vblank (HDMA never turned on on a visible line)", not late,
           f"{len(late)} late, e.g. {late[:6]}")


def b17_dark_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["b17_dark"]
        hdma_ok(res, l, "1P darkness")
        cl = dict(l.values.get("clown", []))
        dark = []
        for k in range(420, 520, 4):
            from .engine import OUT
            p = os.path.join(OUT, f"{tag}.log_b17_dark_f{k:04d}.png")
            c = cl.get(k - k % 10)
            if os.path.exists(p) and c and c[0x3B] and c[0x39] >= 24:
                dark.append((k, dark_lines(p)))
        if not dark:
            res.ok("1-7 1P darkness: screenshots of the dark intro", False, "no frame with the darkness on")
            return res
        base = [sorted(L[y] for _, L in dark)[len(dark) // 2] for y in range(224)]
        bad = [(k, [y for y in range(32, 210) if L[y] > base[y] + 40][:6]) for k, L in dark]
        bad = [b for b in bad if b[1]]
        res.ok("1-7 1P darkness: no lit lines across the dark screen (same picture every frame)", not bad,
               f"{len(dark)} frames; bright lines {bad[:4]}")
        return res
    return ev


def b17_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs["b17_fight"]
        hdma_ok(res, l, "4P darkness / fight")
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
        # a hit: stunned (phase 4) CLOWN_HITT frames, invulnerable ($3C) CLOWN_INVT frames, white silhouette ($2E)
        # meanwhile 4 frames in 8; the hit counter ($08) unchanged until it is over
        cw = l.values.get("cwh", [])
        first = next((k for k, v in cw if v[0] == 4), None)
        stun = [k for k, v in cw if first and k >= first and v[0] == 4]
        stun = len([k for i, k in enumerate(stun) if k - first == i])
        inv = [(k, v) for k, v in cw if first and k > first and v[0x3C]]
        inv = [(k, v) for i, (k, v) in enumerate(inv) if k - first - 1 == i]
        runs = []
        for k, v in inv:                # the picture shown ($2F): white (7-10) or not; SB1's own white flash after
            w = 7 <= v[0x2F] <= 10      # the stun (states $14 / $18) must not add to the blink
            if runs and runs[-1][0] == w:
                runs[-1][1] += 1
            else:
                runs.append([w, 1])
        # (video frames: a lag frame, under 60 fps, holds the game a frame: a run may last one frame more)
        lens = [n for _, n in runs[1:-1]]
        ihits = {v[8] for k, v in inv}
        after = [v for k, v in cw if inv and k == inv[-1][0] + 1]
        res.ok(f"1-7 hit: stunned {CLOWN_HITT} frames, invulnerable {CLOWN_INVT} (moving again meanwhile), blinking "
               "white 4 frames in 8, the picture again after it",
               CLOWN_HITT <= stun <= CLOWN_HITT * 21 // 20 and CLOWN_INVT <= len(inv) + 1 <= CLOWN_INVT * 21 // 20 and lens
               and all(4 <= n <= 6 for n in lens) and len(ihits) == 1 and after and after[0][0x2E] == 0,
               f"stunned {stun}, invulnerable {len(inv) + 1}, hits {sorted(ihits)}, runs {[n for _, n in runs]}")
        # the stun's picture ($07): D (3, the hurt face) after a hit while it runs crying (state $03 = $0C), else N (0)
        faces, bad = [], []
        for (k0, v0), (k1, v1) in zip(cw, cw[1:]):
            if v0[0] == 3 and v1[0] == 4 and k1 == k0 + 1:
                want = 3 if v0[3] == 0x0C else 0
                got = {v[7] for k, v in cw if k1 + 2 <= k < k1 + CLOWN_HITT - 4 and v[0] == 4}
                faces.append((k1, v0[3], sorted(got)))
                if got != {want}:
                    bad.append(k1)
        res.ok("1-7 hit: stunned with the hurt face (D) when hit while running (state $0C), else N",
               faces and not bad and any(s == 0x0C for _, s, _ in faces),
               " ".join(f"{k}:state {s:02X} pics {g}" for k, s, g in faces))
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


def one_fx(stage):
    """A one-player Normal Game: P2-P4 out of the stage (not chosen on the title), they may join with Start."""
    return Fixture(f"s{stage:02X}_1p", stage=stage, players=1, ready=120)


def spawn_out_scenarios(stage, out=(2, 3)):
    t = 600 if stage == 0x68 else 270           # (1-7: the clown's intro holds every pad, Start too)
    st = [[k, "spawn"] for k in range(0, 260, 5)]
    st += [[t - 5, "poke", 0x1D23, 3]] + [[t + 30 * i, "pad", s, "start", 3] for i, s in enumerate(out)]
    end = t + 30 * len(out) + 40
    st += [[end, "spawn"], [end, "read", "pals", 0x16DA, 4], [end, "read", "chars", 0x16C2, 4],
           [end, "read", "picks", 0x1FF02, 4], [end, "read", "cols", 0x1FF08, 4]]
    return [Scenario("sp_out", end + 10, steps=st, invincible=False)]


def spawn_out_eval(stage, out=(2, 3)):
    def ev(logs, boot):
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import coop4_check
        res = Result()
        l = logs["sp_out"]
        snap = [(int(m.split()[1]), m.split(" ", 3)[3].replace("|", "\n")) for m in l.msgs if " spawn " in m]
        who = "/".join(f"P{s + 1}" for s in out) + " out"
        name = f"{STAGES[stage]} ({who})"
        if not snap:
            res.ok(f"{name}: start state read", False, "no spawn line")
            return res

        def field(text, key):
            return [int(x, 16) for x in text.split(key + " ")[1].split("\n")[0].split()]
        start = [(k, t) for k, t in snap if k < 260]
        has_en = [k for k, t in start if t.split("enemies")[1].split("\n")[0].strip()]
        k0 = has_en[0] + 60 if has_en else start[-1][0]
        text = min(start, key=lambda s: abs(s[0] - k0))[1]
        seats, pts = field(text, "seats"), field(text, "points")
        res.ok(f"{name}: the chosen seats in the stage, the others out",
               all((seats[s] == 0xFF) == (s in out) for s in range(4)), " ".join(f"{c:02X}" for c in seats))
        if stage not in (0x67, 0x68):
            where = [((c & 15) >= 8, (c >> 4) >= 7) for c in pts]
            res.ok(f"{name}: the out seats' spawn cells in their corners",
                   all(where[s] == tuple(map(bool, CORNERS[s])) for s in out),
                   " ".join(f"P{s + 1}({c & 15},{c >> 4})" for s, c in enumerate(pts)))
        # every seat judged at its spawn cell, as if it stood there
        lines = text.split("\n")
        as_in = "\n".join("seats " + " ".join(f"{c if s not in out else pts[s]:02X}" for s, c in enumerate(seats))
                          if x.startswith("seats ") else x for x in lines)
        bad = coop4_check.spawn_safety(as_in, stage not in (0x67, 0x68))
        res.ok(f"{name}: every spawn cell is safe (bomb + hide with any soft blocks, enemies >= 6 cells,"
               " shut in)", not bad, "; ".join(bad))
        after = field(snap[-1][1], "seats") if snap[-1][0] >= 260 else [0xFF] * 4
        dist = [abs((after[s] & 15) - (pts[s] & 15)) + abs((after[s] >> 4) - (pts[s] >> 4)) if after[s] != 0xFF else 99
                for s in out]
        res.ok(f"{name}: Start brings them in at their spawn cells", all(d <= 1 for d in dist),
               " ".join(f"P{s + 1}({after[s] & 15},{after[s] >> 4})" if after[s] != 0xFF else f"P{s + 1} out"
                        for s in out))
        died = [(k, s) for k, s in l.deaths if k > 0]
        res.ok(f"{name}: nobody dies standing still", not died, f"deaths {died}")
        if len(out) == 3:
            # not chosen: Bomberman (character 0, picker choice 1) in SB5's colors P2 black, P3 red, P4 blue
            # (palette ids $80:BB4E + seat), and the HUD's heads read the same choices
            pals, chars, picks, cols = (l.value(x) for x in ("pals", "chars", "picks", "cols"))
            res.ok(f"{name}: the joiners are Bomberman, P2 black / P3 red / P4 blue (in game and the HUD's choices)",
                   bool(pals) and all(chars[s] == 0 and pals[s] == pals[0] + s and picks[s] == 1 and cols[s] == s
                                      for s in out),
                   f"chars {chars.hex() if chars else None} pals {pals.hex() if pals else None} "
                   f"picks {picks.hex() if picks else None} cols {cols.hex() if cols else None}")
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
    bomb_pics, bomb_small, _ = bombs.pictures(base)
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
        res.ok("items: the search bomb item ($10) shows SB6's search bomb icon",
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
        bad += [f"${t:03X}" for t, p in bomb_small.items()
                if vr[(OBJ_BASE + 16 * t) * 2:(OBJ_BASE + 16 * t) * 2 + 32] != encode_4bpp(p)]
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
    character select's 8 (all 8 over World 1) and colors spread over their first 25."""
    i = list(STAGES).index(stage)
    return Fixture(f"s{stage:02X}_4p_hudvar", stage=stage, ready=120,
                   picks=tuple(((i + 2 * s) % 8, (5 * i + 7 * s + 3) % 25) for s in range(4)))


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


def hud_dead_scenarios():
    """1-1 with no life left: P2 dies (its own bomb, the start shield off), then P1 pauses and resumes; no DMA into
    VRAM on a visible line meanwhile (vramlate: lost on the console), the HUD drawn again whole (P2's GAME OVER)."""
    st = [[1, "vramlate"], [5, "poke", 0x1D23, 0], [200, "pad", 1, "a", 3]]
    st += [[k, "poke", 0x15A3, 1] for k in range(190, 260, 2)] + [[k, "poke", 0x170B, 0] for k in range(190, 260, 2)]
    st += [[450, "pad", 0, "start", 3], [526, "pad", 0, "start", 3]] + _hud_shot(620, "dead") + _hud_shot(684, "dead2")
    return [Scenario("h_dead", 690, steps=st, invincible=False)]


def hud_dead_eval(logs, boot, tag):
    res = Result()
    l = logs.get("h_dead")
    if not res.ok("1-1 P2 dead, paused: HUD scenario ran", l, ""):
        return res
    late = [x for x in l.lines if x.startswith("DL ")]
    res.ok("P2 dead, pause and resume: no DMA into VRAM on a visible line (its writes would be lost)", not late,
           f"{late[:4]}")
    recs, lives = _hud_screen(res, "1-1 P2 dead, after a pause", tag, "h_dead", "dead", l)
    recs2, _ = _hud_screen(res, "1-1 P2 dead, after a pause, 64 frames later", tag, "h_dead", "dead2", l)
    res.ok("P2 dead with no life left: its block blinks GAME OVER after the pause, the others in the game",
           [r[0] for r in recs] == [1, 0, 1, 1] and sorted((recs[1][1], recs2[1][1])) == [0, 2] and lives == 0,
           f"{recs[1]}, {recs2[1]}, lives {lives}")
    return res


def hud_out_scenarios():
    st = [[1, "invincible", 1], [5, "poke", 0x1D23, 3]] + _hud_shot(HUD_SHOT, "out")
    st += _hud_shot(HUD_SHOT + 64, "out2")             # PUSH START's other blink phase
    st += [[380, "pad", 2, "start", 3]] + _hud_shot(470, "join")
    st += [[480, "poke", 0x1D23, 0]] + _hud_shot(540, "over")     # no life left: P4 (out) shows GAME OVER,
    st += _hud_shot(604, "over2")                                  # blinking as PUSH START
    st += [[620, "poke", 0x1D23, 1]] + _hud_shot(668, "life") + _hud_shot(732, "life2")   # a life: PUSH START
    return [Scenario("h_out", 740, steps=st)]


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
                               d.wram[0x167A + s], d.wram[0x1662 + s], d.wram[0x0069], d.wram[0x1D23]))
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
            rr[s][1] = (m >> i & 1) * (2 if lives == 0 else 1)     # (shown: GAME OVER with no life left)
        w, o = hud.render(t, cg[16:32], [tuple(r) for r in rr], lives, p0=cg[:16], picks=picks, backdrop=backdrop)
        diff = int(((shot[1:1 + len(w)] != w).any(2) & o).sum())
        if best is None or diff < best[0]:
            best = (diff, w, o, [tuple(r) for r in rr])
    _, want, own, recs = best
    n = len(want)                                              # (screenshot row y + 1 = HUD line y)
    own = own.copy()                                           # (sprites pass under the HUD: none excluded)
    # HUD line 20's start: on busy frames (1-2, 1-6, the pause menu) the line-21 IRQ's scroll writes land after
    # screen line 21 starts, whose first pixels (up to 16 seen) then show HUD line 21's dark green, or (1-7) the
    # line drawn with the scroll before the write: the first pixels of line 20 up to its first right one (<= 16)
    same = (shot[1 + 20, :32] == want[21, :32]).all(1)
    k = int(np.argmin(same)) if not same.all() else 32
    right = (shot[1 + 20, :17] == want[20, :17]).all(1)
    if not right[:k + 1].any() and right.any():
        k = max(k, int(np.argmax(right)))
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
    recs, lives = _hud_screen(res, "1-1 no life left", tag, "h_out", "over", l)
    recs2, _ = _hud_screen(res, "1-1 no life left, 64 frames later", tag, "h_out", "over2", l)
    ph = sorted((recs[3][1], recs2[3][1]))
    res.ok("no life left: P4 (out of the stage) blinks GAME OVER instead of PUSH START (shown in one shot, hidden "
           "in the other)", lives == 0 and recs[3][0] == recs2[3][0] == 0 and ph == [0, 2]
           and [r[0] for r in recs[:3]] == [1, 1, 1], f"{recs[3]}, {recs2[3]}, lives {lives}")
    recs, lives = _hud_screen(res, "1-1 a life again", tag, "h_out", "life", l)
    recs2, _ = _hud_screen(res, "1-1 a life again, 64 frames later", tag, "h_out", "life2", l)
    ph = sorted((recs[3][1], recs2[3][1]))
    res.ok("a life again (0 -> 1): P4 blinks PUSH START again, no GAME OVER", lives == 1 and ph == [0, 1],
           f"{recs[3]}, {recs2[3]}, lives {lives}")
    return res


# Sprites pass under the HUD (asm/hud.asm: OBJ out of TM on the HUD lines, window 2 behind the lives heart):
# every seat walks up into the field's top row (P1 / P2 under the lives tab), on foot and on a Louie; the screenshot's
# HUD lines (1-31, the tab included) must equal hud.render() with no pixel of a sprite, while those sprites reach
# into the HUD lines (OAM) and are seen below them.
TOP_X = (7, 8, 3, 11)                   # each seat's column (cells 7 / 8 are under the lives tab, x 116-139)
TOP_SHOTS = (250, 290, 330)
HUD_LINES = 22                          # screen lines 0-21 = HUD lines 1-22 (the panel); the tab goes on to 30
TAB_X, TAB_LAST = (116, 139), 29        # the lives tab: x, last screen line


def top_fx(stage, mounted):
    return mount_fx(stage) if mounted else stage_fx(stage)


def hud_top_scenarios(stage):
    st = [[1, "invincible", 1], [2, "item", 0, 0x08, 1], [4, "pad", 0, "right", 16]]    # the clock: enemies frozen
    for s, x in enumerate(TOP_X):
        st += [[24, "cell", cell(x, y), 0] for y in (1, 2)] + [[25, "place", s, x, 1]]
        st += [[k, "poke", 0x170A + s, 0] for k in (6, 150, 200)]      # no start shield blink in the shots
        st += [[200, "pad", s, "up", 140]]
    st.append([22, "evict", 3])                 # (frozen enemies of the top rows: a rider next to one loses its Louie)
    for k in TOP_SHOTS:
        st += _hud_shot(k, f"top{k}") + [[k, "read", f"top{k}_xy", 0x182A, 24], [k, "read", f"top{k}_y", 0x1872, 24]]
    return [Scenario("h_top", TOP_SHOTS[-1] + 5, steps=st)]


def _sprites(d):
    """[(x, y, size)] of the visible OAM entries (screen line y = OAM y + 1)."""
    out = []
    for k in range(128):
        x, y = d.oam[4 * k], d.oam[4 * k + 1]
        hb = d.oam[512 + k // 4] >> (2 * (k % 4)) & 3
        x, sz = x - 256 if hb & 1 else x, 16 if hb >> 1 else 8
        if y < 0xE0 and -sz < x < 256:
            out.append((x, y + 1, sz))
    return out


def hud_top_eval(stage, mounted):
    def ev(logs, boot, tag):
        res = Result()
        name = f"{STAGES[stage]} {'on Louies' if mounted else 'on foot'}"
        l = logs.get("h_top")
        if not res.ok(f"{name}: top row scenario ran", l, ""):
            return res
        from .dump import Dump
        from .engine import OUT
        reach, tab, below = set(), set(), set()
        for k in TOP_SHOTS:
            label = f"{name}, seats at the top row (frame {k})"
            _hud_screen(res, label, tag, "h_top", f"top{k}", l)
            d = Dump(os.path.join(OUT, f"{tag}.log_h_top_top{k}.dump"))
            spr = _sprites(d)
            for s in range(4):
                obj = d.wram[0x17FA + s]
                if obj >= 0x80 or d.wram[0x15A2 + s] & 0x80:
                    continue
                sx = d.w(0x055F + obj) & 0x1FF
                mine = [(x, y, z) for x, y, z in spr if sx - 8 <= x <= sx + 16]
                if any(y < HUD_LINES for x, y, z in mine):
                    reach.add(s)
                if any(y + z > HUD_LINES + 8 for x, y, z in mine):
                    below.add(s)
                if any(y <= TAB_LAST and x < TAB_X[1] and x + z > TAB_X[0] for x, y, z in mine):
                    tab.add(s)
            ride = [d.wram[0x1782 + s] >> 7 for s in range(4)]
            if mounted:
                res.ok(f"{label}: every seat rides its Louie", ride == [1] * 4, f"{ride}")
        if mounted:         # (on foot a bomber's head reaches the lives tab only)
            res.ok(f"{name}: every rider's sprites reach into the HUD's panel lines (so the HUD checks above saw "
                   f"them pass under)", reach == {0, 1, 2, 3}, f"seats {sorted(s + 1 for s in reach)}")
        res.ok(f"{name}: P1 / P2's sprites reach under the lives tab", tab == {0, 1}, f"seats {sorted(s + 1 for s in tab)}")
        res.ok(f"{name}: the seats are still drawn below the HUD", below == {0, 1, 2, 3},
               f"seats {sorted(s + 1 for s in below)}")
        return res
    return ev


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


# ---------------------------------------------------------------- stage items, magnet bomb
# features/stage_items.py: World 1's soft blocks hide exactly ITEMS[stage] (item map $145A; SB5 spreads them over
# the fixture's first frames: read at frame 60, before anyone burns a block). features/magnet.py: item $0F (SB5's
# mine) = ability $20 = SB6's magnet bomb (bomb slot arrays: $0E2C object, $0E40 fuse (0 = free), $0E68 owner, $0E7C
# cell, $0E90 motion; the object's animation $079F+obj = type 0 animation 4). Enemies: actors 5 and up (cell $16AA),
# frozen by the clock's timer $0E20 (word).
B_MAGNET = 0x20
MAGNET_ANIM = 4
MAG = 0x7FFB2C                  # features/magnet.py: a byte per bomb slot ($80 + n = a magnet bomb)
MAG_DIST = 4                    # the enemy, 4 cells away: the bomb stops 3 cells away, next to it


def items_scenarios():
    return [Scenario("i_map", 64, steps=[[60, "read", "map", 0x145A, 256]])]


def items_eval(stage):
    from sb6.features import stage_items as SI
    name = STAGES[stage]

    def ev(logs, boot, tag):
        res = Result()
        l = logs.get("i_map")
        m = l.value("map") if l else None
        if not m:
            res.ok(f"{name}: item map read", False, "no log")
            return res
        got = sorted(v for v in m if v)
        want = sorted(SI.ITEMS[stage])
        res.ok(f"{name}: soft blocks hide {', '.join(SI.NAMES.get(i, f'${i:02X}') for i in SI.ITEMS[stage])}", got == want,
               " ".join(f"{v:02X}" for v in got))
        return res
    return ev


def _bomb_reads(k0, k1, every=2):
    return [[k, "read", "bombs", 0x0E2C, 0x78] for k in range(k0, k1, every)]


def _bombs(l):
    """[(k, [(slot, owner, cell, motion, obj)] of the live bombs)] from the "bombs" reads ($0E2C + 6 arrays)."""
    out = []
    for k, b in l.values.get("bombs", []):
        live = [(i, b[0x3C + i], b[0x50 + i], b[0x64 + i], b[i]) for i in range(20) if b[0x14 + i]]
        out.append((k, live))
    return out


def _magnet_pull(name, d, soft=False):
    """P1 takes the clock (every enemy frozen), then stands MAG_DIST cells from a frozen enemy that lies in direction
    d (qa.lua `align`: the line cleared, no other enemy in P1's row / column; soft: a soft block in its middle) and
    drops a magnet bomb."""
    st = [[1, "poke", 0x4ED5, B_MAGNET], [2, "item", 0, 0x08, 1], [4, "pad", 0, "right", 16],
          [40, "align", 0, d, MAG_DIST], [42, "read", "at", 0x16AA, 1]]
    if soft:
        st.append([41, "soft_mid", 0])
    st += [[50, "pad", 0, "a", 3]] + _bomb_reads(52, 170)
    return Scenario(name, 170, steps=st)


def _path(l, seat=0):
    path = []
    for k, live in _bombs(l):
        for i, owner, c, mo, obj in live:
            if owner == seat and (not path or path[-1] != c):
                path.append(c)
    return path


def magnet_scenarios():
    sc = [_magnet_pull(f"m_pull_{DIRS[d]}", d) for d in range(4)]
    sc.append(_magnet_pull("m_blocked", 0, soft=True))
    # the item: P1 walks onto item $0F, then drops a bomb (no enemy left to pull it)
    st = arenas() + [[1, "burn", 20], [4, "item", 0, 0x0F, 1], [6, "pad", 0, "right", 16], [40, "read", "ab", 0x4ED5, 4],
                     [96, "pad", 0, "a", 3], [104, "read", "bombs", 0x0E2C, 0x78], [104, "read", "anims", 0x079F, 0x60]]
    st += [[k, "readoam", "oam"] for k in range(104, 170)]
    sc.append(Scenario("m_item", 170, steps=st))
    # two bombs out: only the first is a magnet bomb (like SB5's search bomb), the second a normal one
    st = arenas() + [[1, "burn", 20], [1, "poke", 0x4ED5, B_MAGNET], [1, "poke", 0x4EBD, 2], [96, "pad", 0, "a", 3],
                     [100, "pad", 0, "right", 16], [124, "pad", 0, "a", 3], [130, "read", "bombs", 0x0E2C, 0x78],
                     [130, "read", "anims", 0x079F, 0x60], [130, "read", "mag", MAG, 20]]
    sc.append(Scenario("m_second", 132, steps=st))
    # the control bomb's frames, the search bomb's, the enemy death puff (none of the magnet bomb's tiles)
    st = arenas() + [[1, "poke", 0x4ED5, B_REMOTE], [6, "pad", 0, "a", 3]] + [[k, "readoam", "oam"] for k in range(10, 60)]
    sc.append(Scenario("m_control", 60, steps=st))
    st = arenas() + [[1, "burn", 20], [1, "poke", 0x4ED5, 0x40], [96, "pad", 0, "a", 3]]   # (no enemy left to chase)
    st += [[k, "readoam", "oam"] for k in range(100, 160)]
    sc.append(Scenario("m_search", 160, steps=st))
    sc.append(Scenario("m_puff", 60, steps=[[5, "burn", 30]] + [[k, "readoam", "oam"] for k in range(5, 60)]))
    return sc


def _oam_flip(o):
    """[(tile, palette, big, h flip)] of the visible OAM entries."""
    out = []
    for i in range(128):
        x, y, t, a = o[4 * i:4 * i + 4]
        hi = o[512 + i // 4] >> (2 * (i % 4))
        if y < 0xE0:
            out.append((t | (a & 1) << 8, (a >> 1) & 7, hi >> 1 & 1, a >> 6 & 1))
    return out


def magnet_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        for d in range(4):
            name = f"m_pull_{DIRS[d]}"
            l = logs.get(name)
            if not l:
                continue
            dx, dy = STEP[d]
            al = l.value("align")
            if not al or len(al) < 2:
                res.ok(f"magnet {DIRS[d]}: an enemy to line up with", False, al.hex() if al else "no log")
                continue
            p1, en = al[0], al[1]
            step = dx + 16 * dy
            want = [(p1 + i * step) & 0xFF for i in range(MAG_DIST)]
            path = _path(l)
            stay = [k for k, live in _bombs(l) for i, owner, c, mo, obj in live if owner == 0 and c == want[-1] and not mo & 0x10]
            # (then it waits a second and may look again: another enemy may pull it on)
            res.ok(f"magnet {DIRS[d]}: the bomb goes to the frozen enemy {MAG_DIST} cells away ({en:02X}), stops next to it",
                   path[:len(want)] == want and len(stay) * 2 >= 40, " ".join(f"{c:02X}" for c in path) + f" (want {' '.join(f'{c:02X}' for c in want)})")
            res.ok(f"magnet {DIRS[d]}: kick sound", len(_cmds(l, SFX["kick"])) >= 1, f"{len(_cmds(l, SFX['kick']))}")
        l = logs.get("m_blocked")
        if l:
            al = l.value("align")
            path = _path(l)
            res.ok("magnet: a soft block between the bomb and the enemy: the bomb stays",
                   bool(al) and len(al) >= 2 and path == [al[0]], " ".join(f"{c:02X}" for c in path))
        l = logs.get("m_item")
        if l:
            ab = l.value("ab")
            res.ok("magnet item: P1 gets ability $20", bool(ab and ab[0] & B_MAGNET), ab.hex() if ab else "")
            mine = [(i, obj) for k, live in _bombs(l) for i, owner, c, mo, obj in live if owner == 0]
            anims = l.value("anims")
            res.ok("magnet item: P1's bomb shows animation 4 (the magnet bomb)",
                   bool(mine) and anims and all(anims[obj] == MAGNET_ANIM for i, obj in mine),
                   f"{[(i, hex(obj), hex(anims[obj]) if anims else '') for i, obj in mine]}")
            seq = []
            for k, o in l.values.get("oam", []):
                f = [t for t, pal, big, fl in _oam_flip(o) if pal == 0 and big and t in (0x12E, 0x100, 0x102)]
                if f and (not seq or seq[-1] != f[0]):
                    seq.append(f[0])
            want = [0x100, 0x12E, 0x100, 0x102]
            res.ok("magnet bomb: frames medium large medium small", any(seq[i:i + 4] == want for i in range(4)),
                   " ".join(f"{t:03X}" for t in seq))
        l = logs.get("m_second")
        if l:
            mine = sorted((i, obj) for k, live in _bombs(l) for i, owner, c, mo, obj in live if owner == 0)
            anims, mag = l.value("anims"), l.value("mag")
            got = [(anims[obj] if anims else None, mag[i] >> 7 if mag else None) for i, obj in mine]
            res.ok("magnet: only the first of two bombs out is a magnet bomb (animation 4, then 1 normal)",
                   len(got) == 2 and sorted(got) == [(1, 0), (MAGNET_ANIM, 1)], f"(anim, magnet) {got}")
        l = logs.get("m_control")
        if l:
            seq, flip = [], False
            for k, o in l.values.get("oam", []):
                f = [(t, fl) for t, pal, big, fl in _oam_flip(o) if pal == 0 and big and t in (0x122, 0x124, 0x126)]
                flip |= any(fl for t, fl in f)
                if f and (not seq or seq[-1] != f[0][0]):
                    seq.append(f[0][0])
            ok = len(seq) >= 5 and all(seq[i + 1] == (0x122, 0x124, 0x126)[((0x122, 0x124, 0x126).index(seq[i]) + 1) % 3]
                                       for i in range(len(seq) - 1))
            res.ok("control bomb: frames 1 2 3 1 2 3, never mirrored", ok and not flip,
                   " ".join(f"{t:03X}" for t in seq) + (" (mirrored)" if flip else ""))
        l = logs.get("m_search")
        if l:
            seq = []
            for k, o in l.values.get("oam", []):
                e = [(t, big) for t, pal, big, fl in _oam_flip(o) if pal == 0]
                f = (1 if (0x0EC, 1) in e else 2 if (0x0EE, 0) in e else 3 if (0x0EF, 0) in e and (0x0FF, 0) in e
                     else 4 if (0x0FE, 0) in e and (0x0FF, 0) in e else 0)
                if f and (not seq or seq[-1] != f):
                    seq.append(f)
            ok = len(seq) >= 5 and all(seq[i + 1] == seq[i] % 4 + 1 for i in range(len(seq) - 1))
            res.ok("search bomb: frames 1 2 3 4 (8 x 8 pieces)", ok, " ".join(map(str, seq)))
            ys = sorted({y for k, o in l.values.get("oam", []) for x, y, t, pal, big in _oam(o) if pal == 0 and t == 0x0EC})
            res.ok("search bomb: floats (its top 2 pixels up and down)", len(ys) == 3 and ys[-1] - ys[0] == 2,
                   " ".join(map(str, ys)))
        for name in ("m_puff", "m_control", "m_item", "m_search"):
            l = logs.get(name)
            if not l:
                continue
            bad, smoke = set(), False
            for k, o in l.values.get("oam", []):
                for t, pal, big, fl in _oam_flip(o):
                    if pal == 0 and not big and t in (0x100, 0x101, 0x110, 0x111, 0x102, 0x103, 0x112, 0x113, 0x0EB):
                        bad.add(t)
                    if pal == 0 and big and (t in (0x0EA, 0x0EB) or name != "m_item" and t in (0x100, 0x102, 0x12E)):
                        bad.add(t)
                    smoke |= pal == 0 and not big and t == 0x0FB
            res.ok(f"{name}: no sprite on the magnet bomb's tiles but its own (the death puff, the Louie shadow)",
                   not bad, " ".join(f"{t:03X}" for t in sorted(bad)))
            if name == "m_puff":
                res.ok("enemy death puff: its small smoke from tile $0FB", smoke)
        return res
    return ev


# ---- Louie abilities (features/louie_abilities.py, asm/louie_abilities.asm; SB5's $C4:551B by type)
LA_FX = Fixture("s0D_4p_la", stage=0x0D, ready=200, mounts=(0, 1, 3, 6))      # P1 red, P2 green, P3 yellow, P4 black
LB_FX = Fixture("s0D_4p_lb", stage=0x0D, ready=200, mounts=(2, 4, 5, -1))     # P1 pink, P2 type 4, P3 type 5
RED, GREEN, PINK, YELLOW, BLUE4, PURPLE5, BLACK = 0, 1, 2, 3, 4, 5, 6
RED_T, DASH_T, PUSH_PX = 180, 30, 32          # asm/louie_abilities.asm RED_T, DASH_T, 2 cells
SND_PUNCH, SND_BLACK, SND_PINK = (2, 0x38), (2, 0x35), (2, 0x23)   # sound requests (group, id): SB5's Red punch,
#                                                                     the Black dash, SB5's pink jump
GSLOT, GHOST_T = 104, 12
ROW = 5                                       # a free row (odd): the tests clear it
T0 = 60                                       # (these fixtures' main loop runs from scenario frame ~52: steps at T0 + k)


def _at(sc):
    """The scenarios' frames from T0 on (the evaluations read them back as k - T0: _back)."""
    for x in sc:
        x.steps = [[st[0] + T0] + st[1:] for st in x.steps]
        x.len += T0
    return sc


def _back(logs):
    for l in logs.values():
        if getattr(l, "_t0", False):
            continue
        l._t0 = True
        l.values = {n: [(k - T0, v) for k, v in lst] for n, lst in l.values.items()}
        l.reqs = [(k - T0, g, i) for k, g, i in l.reqs]
        l.cmds = [(k - T0, c) for k, c in l.cmds]
        l.anims = {a: [(k - T0, v) for k, v in lst] for a, lst in l.anims.items()}
    return logs


def _row(y=ROW, k=1):
    return [[k, "cell", cell(x, y), 0] for x in range(1, 14)]


def _acts(k0, k1, every=1):
    return [[k, "read", "act", 0x182A, 0x78] for k in range(k0, k1, every)]


def _xy(b, a):
    return b[a] | b[0x18 + a] << 8, b[0x48 + a] | b[0x60 + a] << 8


def _track(l, a):
    return [(k, _xy(b, a)) for k, b in l.values.get("act", [])]


def _reqs(l, want, k0=0, k1=1 << 30):
    return [k for k, g, i in l.reqs if (g, i) == want and k0 <= k < k1]


def louie_scenarios_a():
    """LA_FX: P1 red, P2 green, P3 yellow, P4 black (stage 1-1, riding from the start)."""
    sc = []
    # Red: an enemy (frozen by the clock to line up) right of P1; Y stuns it RED_T frames; then the clock ends
    # (the fixture is saved while the stage still fades in: the seats move from frame ~21 on, the clock taken then)
    st = [[2, "item", 0, 0x08, 1], [4, "pad", 0, "right", 34], [40, "align", 0, R, 1], [41, "poke", 0x1632, 1],
          [42, "read", "cells", 0x16AA, 24], [42, "read", "h0", 0x155A, 0x48], [44, "pad", 0, "y", 2],
          [52, "poke", 0x0E20, 0], [52, "poke", 0x0E21, 0], [60, "read", "h1", 0x155A, 0x48],
          [300, "read", "h2", 0x155A, 0x48]] + _acts(44, 330, 2)
    sc.append(Scenario("l_red_enemy", 330, steps=st))
    # Red: SB5's punch on a player (P2 next to P1) stuns it; a miss makes no sound
    st = _row() + [[3, "place", 0, 3, ROW], [3, "place", 1, 4, ROW], [6, "poke", 0x1632, 1], [6, "poke", 0x170A + 1, 0],
                   [20, "pad", 0, "y", 2]]
    st += [[k, "read", "stun", 0x15BA, 5] for k in range(20, 50)]
    st += [[60, "place", 1, 9, ROW], [90, "pad", 0, "y", 2]]
    sc.append(Scenario("l_red_player", 130, steps=st, invincible=False))
    # Green (P2) and Black (P4) dash right along the row (enemies burnt first): distance, sound, afterimages
    for seat, name in ((1, "green"), (3, "black")):
        st = [[1, "burn", 20]] + _row(k=40) + [[41, "place", seat, 1, ROW], [42, "poke", 0x1632 + seat, 1],
                                               [60, "pad", seat, "y", 2], [60, "read", "obj", 0x17FA, 24]]
        st += [[k, "poke", 0x170A + s, 0] for k in (44, 50, 56) for s in range(4)]       # (no shield blink)
        st += _acts(56, 150) + [[k, "readoam", "oam"] for k in range(50, 150)]
        st += [[k, "read", "ride", 0x1782 + seat, 1] for k in range(56, 150)]
        sc.append(Scenario(f"l_{name}_dash", 150, steps=st, watch=(MOUNT0 + seat,)))
    # Black: a flame on the rider while it dashes (not invincible otherwise): it keeps its Louie; without a dash: lost
    for dash in (True, False):
        st = [[1, "burn", 20]] + _row(k=40) + [[41, "place", 3, 1, ROW], [42, "poke", 0x1632 + 3, 1],
                                               [44, "poke", 0x170A + 3, 0], [44, "poke", 0x15A2 + 3, 0x01]]   # (no shield)
        st += [[k, "read", "skip", 0x15A2 + 3, 1] for k in range(56, 80)]
        if dash:
            st.append([60, "pad", 3, "y", 2])
        st += [[66, "burn", 12, 3], [120, "read", "ride", 0x1782, 5], [120, "read", "dead", 0x15A2, 5]]
        sc.append(Scenario(f"l_black_{'shield' if dash else 'plain'}", 130, steps=st, invincible=False))
    # Black: an enemy 3 cells ahead (clock) is pushed 2 cells, the dash stops on it
    st = [[2, "item", 3, 0x08, -1], [4, "pad", 3, "left", 34], [40, "align", 3, R, 3], [41, "beyond", 3],
          [41, "poke", 0x1632 + 3, 1], [42, "read", "cells", 0x16AA, 24], [44, "pad", 3, "y", 2]] + _acts(42, 140)
    st += [[k, "read", "push", 0x1FE818, 24] for k in range(42, 140)]          # asm/louie_abilities.asm !PUSH
    st += [[k, "read", "imp", 0x1FE857 + 3, 1] for k in range(42, 140)]     # !IMP
    st += [[k, "read", "mobj", 0x17FA + MOUNT0 + 3, 1] for k in range(42, 140)]
    st += [[k, "read", "maps", 0x049F, 0x60] for k in range(42, 140)]
    sc.append(Scenario("l_black_push", 140, steps=st, watch=(MOUNT0 + 3,)))
    # Yellow (P3): three bombs in a row ahead roll away together
    k = 40
    bombs = [[2, "poke", 0x4EBD + 2, 6], [1, "burn", 20]] + _row(k=k)
    for x in (5, 4, 3):
        bombs += [[k + 1, "place", 2, x, ROW], [k + 2, "pad", 2, "a", 2]]
        k += 6
    st = bombs + [[k + 1, "place", 2, 2, ROW], [k + 2, "poke", 0x1632 + 2, 1], [k + 6, "pad", 2, "y", 2]]
    st += _bomb_reads(k + 4, k + 90) + [[k + 90, "read", "map", 0x1052, 256]]
    sc.append(Scenario("l_yellow_train", k + 92, steps=st))
    # Yellow: a bomb rolls into a resting bomb 4 cells on (both go on); a bomb rolls into a soft block (kicked on)
    st = [[2, "poke", 0x4EBD + 2, 6], [1, "burn", 20]] + _row(k=40) + [
        [41, "place", 2, 7, ROW], [42, "pad", 2, "a", 2], [47, "place", 2, 3, ROW], [48, "pad", 2, "a", 2],
        [53, "place", 2, 2, ROW], [54, "poke", 0x1632 + 2, 1], [58, "pad", 2, "y", 2]]
    st += _bomb_reads(56, 140)
    sc.append(Scenario("l_yellow_pickup", 140, steps=st))
    st = [[2, "poke", 0x4EBD + 2, 6], [1, "burn", 20]] + _row(k=40) + [
        [41, "place", 2, 3, ROW], [42, "pad", 2, "a", 2], [47, "place", 2, 2, ROW], [48, "poke", 0x1632 + 2, 1],
        [48, "cell", cell(7, ROW), 0x30], [52, "pad", 2, "y", 2]]
    st += _bomb_reads(50, 180) + [[k, "read", "map", 0x1052, 256] for k in (50, 179)]
    sc.append(Scenario("l_yellow_soft", 180, steps=st))
    # Yellow: SB5's soft block kick, then the block stops at a bomb, which rolls on
    st = [[2, "poke", 0x4EBD + 2, 6], [1, "burn", 20]] + _row(k=40) + [
        [41, "place", 2, 9, ROW], [42, "pad", 2, "a", 2], [47, "place", 2, 2, ROW], [48, "poke", 0x1632 + 2, 1],
        [48, "cell", cell(3, ROW), 0x30], [52, "pad", 2, "y", 2]]
    st += _bomb_reads(50, 150) + [[k, "read", "map", 0x1052, 256] for k in (50, 149)]
    sc.append(Scenario("l_yellow_block", 150, steps=st))
    sc.append(_mount_walk())
    sc.append(_red_walk())
    return _at(sc)


def _red_walk():
    """P1 on the Red Louie (its mappings are type 0's, as the bombs') walks down, right, up, left: every pose drawn
    the same each time it shows."""
    st = [[1, "burn", 20], [2, "place", 0, 3, 3]] + [[k, "poke", 0x170A, 0] for k in range(2, 200, 8)]
    for i, d in enumerate(("down", "right", "up", "left")):
        st.append([10 + 44 * i, "pad", 0, d, 40])
    return Scenario("l_red_walk", 190, steps=st, pose=(MOUNT0,))


def _mount_walk():
    """Every seat on its Louie, 4 cells apart in row 5, walks right, turns left, turns right: with 4 bombers + 4 Louies
    every OBJ page is taken and the strips go into the pages on screen (asm/coop.asm c5_urgent / c5_defer)."""
    st = _row(5, 1) + [[k, "poke", 0x170A + s, 0] for k in range(2, 100, 8) for s in range(4)]
    for s, x in enumerate((1, 5, 9, 13)):          # (4 cells apart: a Louie bumping into another is not this test)
        st += [[2, "place", s, x, 5], [10, "pad", s, "right", 24], [40, "pad", s, "left", 24],
               [70, "pad", s, "right", 24]]
    return Scenario("l_mount_walk", 100, steps=st, pose=tuple(range(MOUNT0, MOUNT0 + 4)))


def louie_scenarios_b():
    """LB_FX: P1 pink, P2 type 4, P3 type 5; and the Black Louie out of an egg (P4, on foot)."""
    sc = []
    st = [[1, "burn", 20]] + _row(k=40) + [[41, "place", 0, 3, ROW], [42, "poke", 0x1632, 1], [41, "cell", cell(4, ROW), 0x30],
                                           [60, "pad", 0, "y", 2]] + _acts(56, 120)
    st += [[k, "read", "ride", 0x1782, 1] for k in range(56, 100)] + [[k, "readoam", "oam"] for k in range(64, 78, 2)]
    sc.append(Scenario("l_pink_jump", 120, steps=st))
    # (SB5's other abilities, as they were: their sounds)
    st = [[1, "burn", 20]] + _row(k=40) + [[41, "place", 1, 4, ROW], [42, "pad", 1, "a", 2], [47, "place", 1, 3, ROW],
                                           [48, "poke", 0x1632 + 1, 1], [54, "pad", 1, "y", 2]] + _bomb_reads(50, 110)
    sc.append(Scenario("l_type4_bomb", 110, steps=st))
    st = [[2, "poke", 0x4EBD + 2, 6], [1, "burn", 20]] + _row(k=40) + [[41, "place", 2, 2, ROW], [42, "poke", 0x1632 + 2, 1],
                                                                         [54, "pad", 2, "y", 2]]
    st += _bomb_reads(50, 100)
    sc.append(Scenario("l_type5_line", 100, steps=st))
    sc.append(_mount_walk())
    return _at(sc)


def louie_egg_scenarios():
    """FX_A (1-1), nobody on a Louie: P4 hatches the Black Louie (an egg's draw 0-6 forced to 6)."""
    st = [[2, "louie_type", BLACK], [2, "item", 3, 0x15, -1], [3, "pad", 3, "left", 20],
          [150, "read", "mchr", 0x16C2 + MOUNT0, 5], [150, "read", "ride", 0x1782, 5], [150, "read", "mobj", 0x17FA + MOUNT0, 5],
          [150, "read", "slots", 0x06DF, 0x30], [170, "pad", 3, "up", 20]]
    sc = [Scenario("l_black_egg", 200, steps=st, pose=(3,))]
    # 1-1 (features/stage_items.py LOUIE_TEST): eggs hatch red, green, ... black in the order taken
    # (two at once: a third Louie color would become one of these two, asm/louies.asm)
    st = [[2, "item", 0, 0x15, 1], [3, "pad", 0, "right", 20], [42, "item", 1, 0x15, -1], [43, "pad", 1, "left", 20],
          [150, "read", "mchr", 0x16C2 + MOUNT0, 5],
          [150, "read", "ride", 0x1782, 5]]
    from sb6.features import stage_items
    if stage_items.LOUIE_TEST == 0x0D:            # (only while the test eggs are in)
        sc.append(Scenario("l_egg_order", 160, steps=st))
    return sc


# Opponent bombers (asm/louie_abilities.asm bomber_hit): a boss rival (1-6, seat 4) and, in Battle ($1D1A bit 0,
# poked here around the dash), any other bomber get SB5's Red punch stun ($15BA) and are pushed PUSH_PX by the Black
# dash (with their Louie); a Normal Game teammate is not. 1-6: after the first rival walked in (intro phase 2).
LR_FX = Fixture("s67_4p_rb", stage=0x67, ready=30, mounts=(RED, BLACK, -1, -1))     # P1 red, P2 black


def louie_rival_scenarios():
    R = ROW
    st = [[k, "cell", cell(x, R), 0] for k in (440, 540) for x in range(1, 14)]
    st += [[k, "place", s, x, R] for k in (448, 449) for s, x in ((0, 3), (4, 4))]
    st += [[449, "poke", 0x1632, 1], [450, "pad", 0, "y", 2], [400, "read", "iph", 0x1FBD4, 1]]
    st += [[k, "read", "stun", 0x15BA, 5] for k in range(446, 470, 2)]
    # walls above / below the rival's run: its AI (random, seeded by the boot) must not walk out of the row
    st += [[540, "cell", cell(x, y), 0x30] for x in range(4, 9) for y in (R - 1, R + 1)]
    st += [[k, "place", s, x, R] for k in (548, 549) for s, x in ((1, 3), (4, 5))]
    st += [[549, "poke", 0x1632 + 1, 1], [550, "pad", 1, "y", 2]]
    st += [[k, "read", "x", 0x182A, 5] for k in range(440, 620, 2)]
    return [Scenario("l_rival", 620, steps=st)]


def louie_battle_scenarios():
    """LA_FX (1-1): P4 on the Black Louie dashes into P3 (on its Yellow Louie), with / without the Battle flag."""
    sc = []
    for battle in (True, False):
        st = [[1, "burn", 20]] + _row(k=40) + [[41, "place", 3, 1, ROW], [41, "place", 2, 4, ROW], [42, "poke", 0x1632 + 3, 1],
                                               [60, "pad", 3, "y", 2]]
        st += [[k, "poke", 0x170A + s, 0] for k in range(44, 60, 6) for s in range(4)]
        if battle:
            st += [[k, "poke", 0x1D1A, 0x01] for k in range(55, 110)] + [[110, "poke", 0x1D1A, 0]]
        st += [[k, "read", "x", 0x182A, 5] for k in range(56, 120, 2)] + [[k, "read", "stun", 0x15BA, 5] for k in range(56, 120, 8)]
        sc += _at([Scenario("l_battle_push" if battle else "l_mate_push", 120, steps=st)])
    return sc


def louie_rival_eval(fx):
    def ev(logs, boot, tag):
        res = Result()
        l = logs.get("l_rival")
        if l:
            iph = l.value("iph")
            st = [v[4] for k, v in l.values.get("stun", []) if k >= 452]
            res.ok("Red Louie: the punch stuns a boss rival (1-6, seat 4: $15BA)", bool(iph and iph[0] == 2 and st and all(st)),
                   f"intro {iph.hex() if iph else '-'}, stun {st[:4]}")
            xs = dict(l.values.get("x", []))
            x0, x1 = xs.get(550, [0] * 5)[4], xs.get(618, [0] * 5)[4]
            res.ok(f"Black Louie: the dash pushes a boss rival {PUSH_PX} pixels", x1 - x0 == PUSH_PX, f"rival x {x0} -> {x1}")
        for name, want in (("l_battle_push", PUSH_PX), ("l_mate_push", 0)):
            l = logs.get(name)
            if not l:
                continue
            _back({name: l})
            xs = dict(l.values.get("x", []))
            x0, x1 = xs.get(56, [0] * 5)[2], xs.get(118, [0] * 5)[2]
            stun = any(v[2] for k, v in l.values.get("stun", []))
            what = "Battle: an opponent (P3 on its Louie)" if want else "Normal Game: a teammate"
            res.ok(f"Black Louie: {what} is {'pushed' if want else 'not pushed'} by the dash",
                   x1 - x0 == want and stun == bool(want), f"P3 x {x0} -> {x1}, stunned {stun}")
        return res
    return ev


def _ghost_pairs(o, axis_sign):
    """Afterimage copies in an OAM dump: (entry i, later entry j with i's tile / attributes, x displacement)."""
    ents = []
    for i in range(128):
        x, y, t, a = o[4 * i:4 * i + 4]
        hi = o[512 + i // 4] >> (2 * (i % 4))
        if y < 0xE0:
            ents.append((i, x | (hi & 1) << 8, y, t, a))
    out = []
    for p, (i, xi, yi, ti, ai) in enumerate(ents):
        for j, xj, yj, tj, aj in ents[p + 1:]:
            dx = ((xj - xi + 256) % 512) - 256
            if (tj, aj) == (ti, ai) and abs(yj - yi) <= 1 and 6 <= -axis_sign * dx <= 64:
                out.append((i, j, dx))
    return out


def louie_eval(part):
    def ev(logs, boot, tag):
        res = Result()
        _back(logs)
        if part == "a":
            _eval_red(res, logs)
            _eval_dash(res, logs)
            _eval_yellow(res, logs)
        else:
            _eval_b(res, logs)
        _eval_mount_walk(res, logs, tag)
        return res
    return ev


def _eval_mount_walk(res, logs, tag):
    from . import poses as P
    from .engine import pose_file
    try:
        seen, bad = P.mount_glitches(pose_file(tag, "l_mount_walk"), range(MOUNT0, MOUNT0 + 4), 14, 98, base=T0)
    except FileNotFoundError:
        res.ok("4 riders walking, turning: every frame a Louie pose", False, "no pose dump")
        return
    res.ok("4 riders walking, turning (every OBJ page taken): no Louie frame torn (a picture shown 1 frame only)",
           seen > 100 and not bad, f"{seen} frames, torn {bad[:8]}")
    from .engine import ROM, ROOT
    from sb6.romlib import off
    new, old = open(ROM, "rb").read(), open(os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"), "rb").read()
    diff = []
    w = lambda d, a: d[off(a)] | d[off(a) + 1] << 8
    for an in range(0x16, 0x5A):            # the Red / Green Louies' type 0 animations and their mappings
        a0 = 0xC50000 | w(old, 0xC581EE + 2 * (an - 1))
        for i in range(64):
            mp, fr = old[off(a0 + 2 * i)], old[off(a0 + 2 * i + 1)]
            if not fr:
                break
            if mp:
                ma, mb = 0xC50000 | w(old, 0xC58000 + 2 * (mp - 1)), 0xC50000 | w(new, 0xC58000 + 2 * (mp - 1))
                n = old[off(ma)]
                if old[off(ma):off(ma) + 1 + 7 * n] != new[off(mb):off(mb) + 1 + 7 * n]:
                    diff.append(mp)
            if fr == 0xFF:
                break
    res.ok("Red / Green Louie mappings (type 0 animations $16-$59) as SB5's (the bombs' remap leaves them)",
           not diff, f"{sorted(set(diff))[:12]}")
    if "l_red_walk" in logs:
        try:
            seen, bad = P.mount_mismatch(pose_file(tag, "l_red_walk"), MOUNT0, 12, 188, base=T0)
        except FileNotFoundError:
            seen, bad = 0, ["no pose dump"]
        res.ok("Red Louie walking 4 ways: each pose always drawn the same (no piece lost: its mappings are not the "
               "bombs')", seen > 80 and not bad, f"{seen} frames, {bad[:6]}")


def louie_egg_eval():
    def ev(logs, boot, tag):
        res = Result()
        _eval_egg(res, logs)
        return res
    return ev


def _moved(tr, k0, k1):
    return len({p for k, p in tr if k0 <= k < k1}) > 1


def _enemy(l):
    al, cells = l.value("align"), l.value("cells")
    if not (al and len(al) > 1 and cells):
        return None, al
    en = [a for a in range(5, 24) if cells[a] == al[1]]
    return (en[0] if en else None), al


def _eval_red(res, logs):
    l = logs.get("l_red_enemy")
    if l:
        a, al = _enemy(l)
        if a is None:
            res.ok("Red Louie: an enemy lined up next to P1", False, al.hex() if al else "no log")
        else:
            cells = l.value("cells")
            tr = _track(l, a)
            h0, h1, h2 = l.value("h0"), l.value("h1"), l.value("h2")
            hp = lambda h: h[a] | h[0x18 + a] << 8 | h[0x30 + a] << 16
            res.ok("Red Louie: the enemy's routine is ours while stunned, SB5's again after",
                   hp(h1) >> 16 == 0xC4 and 0x5A40 <= hp(h1) & 0xFFFF < 0x7F00 and hp(h2) != hp(h1),
                   f"before {hp(h0):06X} stunned {hp(h1):06X} after {hp(h2):06X}")
            res.ok(f"Red Louie: the stunned enemy stays still ~{RED_T} frames (the clock over at 52)",
                   not _moved(tr, 54, 44 + RED_T - 10), f"{sorted({p for k, p in tr if 54 <= k < 214})[:4]}")
            res.ok("Red Louie: it walks again after the stun", _moved(tr, 44 + RED_T + 10, 330),
                   f"{sorted({p for k, p in tr if k >= 234})[:4]}")
            others = [b for b in range(5, 24) if b != a and cells[b] and _moved(_track(l, b), 60, 200)]
            res.ok("Red Louie: the other enemies walk (only the punched one is stunned)", bool(others), f"{others}")
            n = _reqs(l, SND_PUNCH, 44, 60)
            res.ok("Red Louie: one punch sound for the enemy hit", len(n) == 1, f"{n}")
    l = logs.get("l_red_player")
    if l:
        stun = [k for k, v in l.values.get("stun", []) if v[1]]
        res.ok("Red Louie: SB5's punch still stuns a player ahead ($15BA)", bool(stun), f"{stun[:3]}")
        res.ok("Red Louie: punch sound on the player, none on a miss",
               len(_reqs(l, SND_PUNCH, 20, 50)) == 1 and not _reqs(l, SND_PUNCH, 88, 130), f"{_reqs(l, SND_PUNCH)}")


def _eval_dash(res, logs):
    for seat, name in ((1, "green"), (3, "black")):
        l = logs.get(f"l_{name}_dash")
        if not l:
            continue
        tr = dict(_track(l, seat))
        x0 = tr.get(58, (0, 0))[0]
        xe = tr.get(110, (0, 0))[0]
        xe = tr.get(130, (0, 0))[0]
        if name == "black":
            d = [tr[k][0] - tr[k - 1][0] for k in range(62, 62 + DASH_T) if k in tr and k - 1 in tr]
            res.ok(f"Black Louie: dashes ~3 cells right ({DASH_T} frames, at most 2 pixels a frame)",
                   40 <= xe - x0 <= 56 and max(d, default=9) <= 2, f"{x0} -> {xe}, steps {d}")
            res.ok("Black Louie: dash sound", len(_reqs(l, SND_BLACK, 58, 70)) == 1, f"{_reqs(l, SND_BLACK)}")
            end = 61 + DASH_T
            # SB5's unused shoulder charge ($1F-$22 = $1E + facing; right = $1F), then walking / standing again
            an = l.anims.get(MOUNT0 + seat, [])
            during = [a for k, a in an if 62 <= k < end]
            after = [a for k, a in an if k >= end]
            res.ok("Black Louie (Y alone): the whole dash on the shoulder charge ($1F, facing right), then not any more",
                   bool(during) and all(a == 0x1F for a in during) and bool(after) and not 0x1F <= after[-1] <= 0x22,
                   f"during {[hex(a) for a in during]}, after {[hex(a) for a in after]}")
        else:
            ride = [k for k, v in l.values.get("ride", []) if v[0] & 1]
            res.ok("Green Louie: SB5's dash ($1782 bit 0), moves right", bool(ride) and xe - x0 >= 32,
                   f"dash frames {ride[:1]}..{ride[-1:]}, {x0} -> {xe}")
            end = ride[-1] if ride else 110
        pre, during, lags, high = [], [], set(), []
        for k, o in l.values.get("oam", []):
            g = _ghost_pairs(o, 1)
            shown = sum(1 for i in range(128) if o[4 * i + 1] < 0xE0) > 8         # (the rider not blinked out)
            (pre if k < 60 else during).append((k, len(g), shown))
            if 75 <= k < end:
                lags |= {dx for i, j, dx in g}
                high += [j for i, j, dx in g if j >= GSLOT]
        seen = [k for k, n, sh in during if 75 <= k < end and sh]
        on = [k for k, n, sh in during if 75 <= k < end and sh and n >= 2]
        res.ok(f"{name} dash: afterimages (copies of the rider / Louie behind it) on >= 90% of the frames it shows",
               bool(seen) and len(on) * 10 >= len(seen) * 9 and all(n == 0 for k, n, sh in pre),
               f"{len(on)}/{len(seen)} frames; before the dash {[n for k, n, sh in pre if n]}")
        res.ok(f"{name} dash: afterimages at two distances (6 / 12 frames, a flicker), below OAM {GSLOT}",
               len({abs(v) // 4 for v in lags}) >= 2 and not high, f"{sorted(lags)} {high[:3]}")
        gone = [k for k, n, sh in during if k >= end + 14 and n]
        res.ok(f"{name} dash: afterimages gone {GHOST_T} frames after it", not gone, f"dash end {end}: {gone}")
    for dash in (True, False):
        l = logs.get(f"l_black_{'shield' if dash else 'plain'}")
        if not l:
            continue
        ride, dead = l.value("ride"), l.value("dead")
        kept = bool(ride and ride[3] & 0x80 and dead and not dead[3] & 0x80)
        pre = [v[0] for k, v in l.values.get("skip", []) if k < 60]
        res.ok(f"Black Louie {'shield' if dash else 'plain'}: no SB5 shield on the rider before ($15A2 bit 2)",
               bool(pre) and not any(v & 4 for v in pre), f"{pre[:3]}")
        if dash:
            res.ok("Black Louie: invincible while dashing (a flame on it: still riding, alive)", kept,
                   f"ride {ride.hex() if ride else ''} dead {dead.hex() if dead else ''}")
        else:
            res.ok("Black Louie: (control) the same flame without a dash costs the Louie", not kept,
                   f"ride {ride.hex() if ride else ''}")
    l = logs.get("l_black_push")
    if l:
        a, al = _enemy(l)
        if a is None:
            res.ok("Black Louie push: an enemy lined up 3 cells ahead", False, al.hex() if al else "no log")
        else:
            tr, me = dict(_track(l, a)), dict(_track(l, 3))
            on = [k for k, v in l.values.get("push", []) if v[a]]
            if not on:
                res.ok("Black Louie: the dash pushes the enemy ahead", False, "no push")
            else:
                k0, k1 = on[0] - 1, on[-1] + 1
                ex0, ex1 = tr[k0][0], tr[k1][0]
                res.ok(f"Black Louie: the enemy ahead is pushed {PUSH_PX} pixels (frames {k0}-{k1})", ex1 - ex0 == PUSH_PX,
                       f"{ex0} -> {ex1}")
                res.ok("Black Louie: the dash stops at the enemy (no pass through)", me[k1][0] < ex1 and me[139][0] == me[k1][0],
                       f"P4 {me[42][0]} -> {me[k1][0]} -> {me[139][0]}, enemy {ex1}")
        # the impact: 15 frames (0.25 s) on the shoulder charge's last pose (mapping of its pair 7: right = 79;
        # !IMP is read after that frame's count: 14 nonzero reads)
        imp = [k for k, v in l.values.get("imp", []) if v[0]]
        mobj = dict(l.values.get("mobj", []))
        maps = dict(l.values.get("maps", []))
        held = [maps[k][mobj[k][0]] for k in imp if k in maps and k in mobj]
        an = [a for k, a in l.anims.get(MOUNT0 + 3, []) if 44 <= k < (imp[0] if imp else 140)]
        res.ok("Black Louie: the whole dash on the shoulder charge, then its last pose held 15 frames where it hit",
               14 <= len(imp) <= 15 and set(held) == {79} and an and all(a == 0x1F for a in an),
               f"hold frames {len(imp)}, mappings {sorted(set(held))}, animations {[hex(a) for a in an]}")


def _bomb_cells(l, seat=None):
    """[(k, sorted cells of the live bombs)]"""
    return [(k, sorted(c for i, owner, c, mo, obj in live if seat is None or owner == seat)) for k, live in _bombs(l)]


def _eval_yellow(res, logs):
    l = logs.get("l_yellow_train")
    if l:
        seq = _bomb_cells(l, 2)
        first = seq[0][1] if seq else []
        last = seq[-1][1] if seq else []
        want0 = [cell(x, ROW) for x in (3, 4, 5)]
        want1 = [cell(x, ROW) for x in (11, 12, 13)]
        together = all(len(c) == 3 and c[2] - c[0] == 2 for k, c in seq)
        res.ok("Yellow Louie: a row of 3 bombs rolls away together to the wall", first == want0 and last == want1 and together,
               f"{[hex(c) for c in first]} -> {[hex(c) for c in last]}")
        m = l.value("map")
        res.ok("Yellow Louie: the bombs' cells are marked at the end ($1052 bit 6)",
               bool(m) and bool(last) and all(m[c] & 0x40 for c in last), " ".join(f"{m[c]:02X}" for c in last) if m else "")
        n = len(_cmds(l, SFX["kick"]))
        res.ok("Yellow Louie: a kick sound", n >= 1, f"{n}")
    l = logs.get("l_yellow_pickup")
    if l:
        seq = _bomb_cells(l, 2)
        last = seq[-1][1] if seq else []
        res.ok("Yellow Louie: the rolling bomb takes the bomb it meets along",
               last == [cell(12, ROW), cell(13, ROW)], f"{[hex(c) for c in last]}")
    l = logs.get("l_yellow_soft")
    if l:
        seq = _bomb_cells(l, 2)
        last = seq[-1][1] if seq else []
        m1 = dict(l.values.get("map", [])).get(179)
        res.ok("Yellow Louie: the bomb stops at a soft block, which slides on to the wall",
               last == [cell(6, ROW)] and bool(m1) and m1[cell(7, ROW)] != 0x30 and m1[cell(13, ROW)] == 0x30,
               f"bomb {[hex(c) for c in last]}, map 7: {m1[cell(7, ROW)]:02X} 13: {m1[cell(13, ROW)]:02X}" if m1 else "")
    l = logs.get("l_yellow_block")
    if l:
        seq = _bomb_cells(l, 2)
        last = seq[-1][1] if seq else []
        m1 = dict(l.values.get("map", [])).get(149)
        res.ok("Yellow Louie: SB5's soft block kick; the block stops at a bomb, which rolls on to the wall",
               last == [cell(13, ROW)] and bool(m1) and m1[cell(3, ROW)] != 0x30 and m1[cell(8, ROW)] == 0x30,
               f"bomb {[hex(c) for c in last]}, map 3: {m1[cell(3, ROW)]:02X} 8: {m1[cell(8, ROW)]:02X}" if m1 else "")


def _eval_b(res, logs):
    l = logs.get("l_pink_jump")
    if l:
        tr = dict(_track(l, 0))
        jump = [k for k, v in l.values.get("ride", []) if v[0] & 2]
        res.ok("Pink Louie: SB5's jump ($1782 bit 1) and its sound", bool(jump) and len(_reqs(l, SND_PINK, 58, 70)) == 1,
               f"{jump[:1]}..{jump[-1:]} sound {_reqs(l, SND_PINK)}")
        # its shadow on the ground (type 0 animation $0A, mapping 39: SB5's quarter $0EB drawn 4 times, flipped;
        # features/bombs.py), the 16 x 16 ellipse while the rider is up
        # (from 4 frames into the jump: its first frame follows the pad by 1-2 frames, as the boot's timing falls)
        bad = []
        for k, o in l.values.get("oam", []):
            if jump and k < jump[0] + 4:
                continue
            ps = [(o[4 * i], o[4 * i + 1], o[4 * i + 3] & 0xC0) for i in range(128)
                  if o[4 * i + 2] == 0xEB and not o[4 * i + 3] & 1 and o[4 * i + 1] < 0xE0]
            xs, ys = {x for x, _, _ in ps}, {y for _, y, _ in ps}
            if not (len(ps) == 4 and {f for _, _, f in ps} == {0, 0x40, 0x80, 0xC0} and len(xs) == len(ys) == 2
                    and max(xs) - min(xs) == 8 and max(ys) - min(ys) == 8):
                bad.append((k, ps))
        res.ok("Pink Louie: a shadow on the ground under the jump (4 pieces of tile $0EB, flipped)",
               l.values.get("oam") and not bad, f"{bad[:2]}")
    l = logs.get("l_type4_bomb")
    if l:
        fly = [(k, c, mo) for k, live in _bombs(l) for i, owner, c, mo, obj in live if mo & 0x30]
        res.ok("type 4 Louie: the bomb ahead is sent off (moving / flying)", bool(fly), f"{fly[:3]}")
    l = logs.get("l_type5_line")
    if l:
        got = sorted({c for k, c in _bomb_cells(l, 2) if k >= 54 for c in c})
        res.ok("type 5 Louie: SB5's Y drops a bomb under the rider ($C4:300C)", got == [cell(2, ROW)],
               f"{[hex(c) for c in got]}")
    hatch = _hatch_range()
    res.ok("eggs: louie_hatch draws 0-6 (the Black Louie too)", hatch == 6, f"{hatch}")


def _eval_egg(res, logs):
    l = logs.get("l_egg_order")
    if l:
        mchr, ride = l.value("mchr"), l.value("ride")
        got = [mchr[s] if ride and ride[s] & 0x80 else None for s in range(2)] if mchr else []
        res.ok("1-1 egg test: the eggs hatch Louies 0, 1, ... in the order taken (one of each, la_hatch)",
               got == [0, 1], f"{got}")
    l = logs.get("l_black_egg")
    if l:
        mchr, ride, mobj, slots = (l.value(n) for n in ("mchr", "ride", "mobj", "slots"))
        ok = bool(mchr and ride and mobj and mchr[3] == BLACK and ride[3] & 0x80 and mobj[3] < 0x80)
        res.ok("Black Louie: hatches out of an egg (type 6), P4 rides it", ok,
               f"types {mchr.hex() if mchr else ''} ride {ride.hex() if ride else ''}")
        res.ok("Black Louie: its own colors (a Louie palette slot)", ok and slots[mobj[3]] != 0xFF,
               f"slot {slots[mobj[3]] if ok else ''}")
        res.ok("Black Louie: its cry", len(_cmds(l, LOUIE_CRY + BLACK)) >= 1, f"{[hex(c) for k, c in l.cmds]}")
        ups = [a for k, a in l.anims.get(3, []) if k >= 170]
        res.ok("Black Louie: P4 rides it (a riding animation walking up)", any(RIDE_ALL[0] <= a <= RIDE_ALL[1] for a in ups)
               or any(a >= 0x05 for a in ups), f"{[hex(a) for a in ups]}")


def _hatch_range():
    p = os.path.join(_root(), "build", "Super Bomberman 6.sfc")
    if not os.path.exists(p):
        return None
    d = open(p, "rb").read()
    o = lambda a: ((a >> 16) & 0x3F) << 16 | (a & 0xFFFF)
    j = d[o(0xC45148):o(0xC45148) + 4]
    t = j[1] | j[2] << 8 | j[3] << 16
    b = d[o(t):o(t) + 4]
    if b[0] == 0x22:                       # (louie_abilities' la_hatch: SB5's random draw in its .random path)
        t = b[1] | b[2] << 8 | b[3] << 16
    i = d.find(bytes.fromhex("22 EB 1D C0"), o(t), o(t) + 64)
    return d[i - 1] if i >= 2 and d[i - 2] == 0xA9 else None


# ---------------------------------------------------------------- SB6 stage voices
# features/voice_sfx.py (asm/game_sfx.asm vs_*), stages voice_sfx.STAGES: "start" START_DELAY passes after SB5's
# stage start jingle is asked for (request 0/$20: after the jingle, before the music), a random "good" at the clear
# jingle (0/$21), as Hudson SFX voice_sfx.CMD / CMD_GOOD whose sample (directory voice_sfx.SRC) loops over a ring of
# BRR blocks = the cornered sound's part B ARAM (game_sfx b1-$DCFF), filled by the main loop behind the play
# position on idle time; after a voice, part B goes back there (the cornered sound is silent meanwhile, $7F:FBB1).
# Checked: the command and the S-DSP key-on (pitch; no other key-on ever plays directory SRC), every block the
# voice plays was in the ring before it played (no underrun) and no block was written until the one it replaces had
# played (2 blocks of margin), the clip plays to its END, B back afterwards (byte for byte), no main-loop pass lost
# while a voice plays or loads (frames without the loop hook $C0:0B2C). Cornered ($5E, directory game_sfx
# SRC_CORNER): its part A loops into B and plays to B's last block, in every stage whose SB1 song keeps B.
VOICE_HOOK = 0xC00B2C
VOICE_WRAM = 0x1FBE8                 # $7F:FBE8: on, record, clip, sent (word), pos (word), play... (game_sfx.asm)
VOICE_BOK = 0x1FBB1                  # $7F:FBB1: 1 = part B in ARAM
VOICE_B = 4                          # clip number of part B


def _part_b():
    from sb6.features import game_sfx
    rom = open(engine.ROM, "rb").read()
    return game_sfx.build(bytearray(rom), os.path.join(engine.ROOT, "assets", "sound"),
                          os.path.join(engine.ROOT, "build", "cache"))[3]["part_b"]


def voice_fx(stage=0x0D):
    return Fixture(f"s{stage:02X}_4p_voice", stage=stage, ready=2)


def _voice_steps(dsp_from, ring):
    return [[dsp_from, "dsplog"], [dsp_from, "spcwatch", ring[0], ring[1], 3]]


def voice_start_scenarios(ring):
    n = 640
    st = _voice_steps(150, ring) + [[k, "read", "vs", VOICE_WRAM, 18] for k in range(0, n, 4)]
    st += [[k, "read", "bok", VOICE_BOK, 1] for k in range(0, n, 4)] + [[n - 5, "dsplog"]]
    return [Scenario("v_start", n, steps=st, exec=(VOICE_HOOK,))]


def voice_clear_scenarios(stage, ring):
    n = 560
    sc = portal_scenarios(stage)[0]
    st = [s for s in sc.steps if s[1] != "dsplog" and not (s[1] == "read" and str(s[2])[:1] in "md")]
    st += _voice_steps(300, ring) + [[n - 5, "dsplog"]]
    st += [[k, "read", "vs", VOICE_WRAM, 18] for k in range(300, n, 4)]
    st += [[k, "read", "bok", VOICE_BOK, 1] for k in range(300, n, 4)]
    return [Scenario("v_clear", n, steps=st, exec=(VOICE_HOOK,))]


def voice_end_scenarios(stage, ring):
    """The boss stages' end (voice_sfx.END_STAGES): the 1-6 tournament / the 1-7 fight up to the boss clear jingle
    (0/$22, after SB5's boss victory music is uploaded) and 90 frames on: "good" from the end ring."""
    if stage == 0x68:
        sc, n, w = b17_scenarios()[0], 2800, 2600
    else:
        sc, n, w = b16_scenarios()[0], 3300, 2560   # (the Golden's death moves with the ROM: ~2640-2950)
    st = [s for s in sc.steps if s[0] < n and s[1] in ("burn_clown", "burn", "pad")]
    st += _voice_steps(w, ring) + [[n - 5, "dsplog"]]
    st += [[k, "read", "vs", VOICE_WRAM, 18] for k in range(w, n, 4)]
    st += [[k, "read", "bok", VOICE_BOK, 1] for k in range(w, n, 4)]
    return [Scenario("v_end", n, steps=st, exec=(VOICE_HOOK,))]


def corner_scenarios(b_lo):
    """P1 walled in with a bomb ~500 frames into the stage (after "start": B back)."""
    st = arenas([0])
    cx, cy = QUAD[0]
    st += [[3, "cell", c, 0x30] for c in (cell(cx + 1, cy), cell(cx - 1, cy), cell(cx, cy + 1), cell(cx, cy - 1))]
    st += [[208, "dsplog"], [208, "spcwatch", b_lo, 0xDCFF, 3], [206, "read", "bok", VOICE_BOK, 1],
           [220, "pad", 0, "a", 3], [315, "dsplog"]]
    return [Scenario("v_corner", 320, steps=st)]


def _voice_ring(l, ring, nr, ns, src=None):
    """-> (key-ons [(k, voice, pitch)], clips played to their end (blocks), worst lead, worst margin behind,
    problems)"""
    from sb6.features import voice_sfx as V
    regs, kons = {}, []
    for k, cyc, r, v in l.dsp:
        regs[r] = v
        if r == 0x4C:
            for n in range(8):
                if v >> n & 1 and regs.get(16 * n + 4) == (V.SRC if src is None else src):
                    kons.append((k, n, regs.get(16 * n + 2, 0) | regs.get(16 * n + 3, 0) << 8))
    playing, P, last_p, F, played = False, 0, 0, None, []
    lead, gapw, bad, ki = 10 ** 9, 10 ** 9, [], 0
    for kind, k, addr, brr in l.spc:
        while ki < len(kons) and kons[ki][0] <= k:
            playing, P, last_p = True, 0, 0
            F = nr - 1 if F is None else F       # (the ring was filled before the watch began)
            ki += 1
        if playing and ring <= brr < ring + 9 * nr:
            p = (brr - ring) // 9
            d = (p - last_p) % nr
            if F + 1 in ns and P + d > F:
                playing = False                  # past its last block: END (the S-DSP goes on silently)
                played.append(F + 1)
            elif d > 40:
                bad.append(f"{k}: jumped {last_p}->{p}")
            P, last_p = P + d, p
        if kind == "A" and ring <= addr < ring + 9 * nr and (addr - ring) % 9 == 0:
            w = (addr - ring) // 9
            if F is None:
                j = w
            elif w == 0 and (F + 1) % nr:
                j, playing = 0, False            # another clip's first blocks
            else:
                dd = (w - F - 1) % nr
                j = F + 1 + (dd if dd < nr // 2 else dd - nr)
            if playing and j >= nr:
                gapw = min(gapw, P - (j - nr))
                if P - (j - nr) < 2:
                    bad.append(f"{k}: block {j} written over {j - nr} while block {P} plays")
            F = j if F is None or j == 0 else max(F, j)
        if playing and P >= F and F + 1 in ns:
            playing = False                      # its last block (END)
            played.append(F + 1)
        if playing:
            lead = min(lead, F - P)
            if F < P:
                bad.append(f"{k}: block {P} plays, the ring holds up to {F}")
        if len(bad) > 8:
            break
    return kons, played, lead, gapw, bad


def _voice_lags(l, k0, n):
    hooks = set()
    for m in l.msgs:
        f = m.split()
        if len(f) > 3 and f[2] == "exec" and int(f[3], 16) == VOICE_HOOK:
            hooks.add(int(f[1]))
    return [k for k in range(k0, k0 + n) if k not in hooks]


def voice_plan(stage):
    """build/voice_plan.json (voice_sfx.late): ring, nr, shared (B goes back to the ring's top), steps ("start"
    that many semitones lower), pitch of "start", its blocks."""
    import json
    return {p["stage"]: p for p in json.load(open(os.path.join(engine.ROOT, "build", "voice_plan.json")))}[stage]


def _aram(tag, name):
    return open(os.path.join(engine.OUT, f"{tag}.log_{name}_aram.bin"), "rb").read()


def voice_eval(kind, stage, tag):
    sn = STAGES.get(stage, f"${stage:02X}")

    def ev(logs, boot):
        from sb6.features import crowd, voice_sfx as V
        res = Result()
        name = "v_" + kind
        l = logs.get(name)
        if not res.ok(f"{sn} voice {kind}: scenario ran", l is not None, ""):
            return res
        try:
            aram = _aram(tag, name)
        except OSError as e:
            res.ok(f"{sn} voice {kind}: ARAM dump", False, str(e))
            return res
        plan = voice_plan(V.END_KEY if kind == "end" else stage)
        ring, nr, shared = plan["ring"], plan["nr"], plan["shared"]
        src = plan.get("src", V.SRC)
        clips = V.clips(os.path.join(engine.ROOT, "assets", "sound"), plan["steps"])
        ns = [len(d) // 9 for d, _ in clips]
        pitch = plan["pitch"] if kind == "start" else V.PITCH
        rate = pitch * 32000 / 4096
        res.ok(f"{sn} voice {kind}: directory ${src:02X} = the ring (${ring:04X}, {nr} blocks"
               f"{', part B at its top' if shared else ''})",
               (aram[0xFD00 + 4 * src] | aram[0xFD01 + 4 * src] << 8) == ring, "")
        jingle = {"start": 0x20, "clear": 0x21, "end": 0x22}[kind]
        asked = [k for k, g, i in l.reqs if (g, i) == (0, jingle)]
        if kind == "start" and plan.get("good_only"):
            # (1-2: "good" only, its ring is the song's piano: "start" never asked for, never keyed on)
            kons = _voice_ring(l, ring, nr, set(ns), src)[0]
            music = [k for k, g, i in l.reqs if (g, i) == (0, 6)]
            res.ok(f"{sn} voice start: none (good only): jingle, music, no voice SFX, no key-on of ${src:02X}",
                   bool(asked and music) and not [c for k, c in l.cmds if c in (V.CMD, V.CMD_GOOD)] and not kons,
                   f"jingle {asked[:1]}, music {music[:1]}, key-ons {kons[:2]}")
            wr = [x for x in l.spc if x[0] == "A"]
            res.ok(f"{sn} voice start: the song's sample at the ring (${ring:04X}) never written while the stage plays",
                   not wr, f"writes {wr[:3]}")
            return res
        sfx = V.CMD if kind == "start" else V.CMD_GOOD
        after = [(k, c) for k, c in l.cmds if c in (V.CMD, V.CMD_GOOD) and asked and k >= asked[0]]
        cmd = [k for k, c in after]
        lo, hi = (V.START_DELAY - 1, V.START_DELAY + 2) if kind == "start" else (0, 20)
        res.ok(f"{sn} voice {kind}: jingle (0/${jingle:02X}) -> SFX ${sfx:02X} {lo}-{hi} frames later",
               bool(asked and cmd and after[0][1] == sfx and lo <= cmd[0] - asked[0] <= hi),
               f"jingle {asked[:2]}, SFX {cmd[:3]}")
        if kind == "start":
            music = [k for k, g, i in l.reqs if (g, i) == (0, 6)]
            ends = cmd[0] + 2 + ns[0] * 16 * 60 // int(rate) if cmd else 0
            res.ok(f"{sn} voice start: after the jingle's last note, over before the stage music",
                   bool(cmd and asked and music and cmd[0] - asked[0] >= 90 and ends < music[0]),
                   f"jingle {asked[:1]}, start {cmd[:1]}-{ends}, music {music[:1]}")
        kons, played, lead, gapw, bad = _voice_ring(l, ring, nr, set(ns), src)
        kons = [x for x in kons if asked and x[0] >= asked[0]]
        res.ok(f"{sn} voice {kind}: one key-on of directory ${src:02X} at pitch ${pitch:04X} (+-3), <= 6 frames after it",
               bool(len(kons) == 1 and abs(kons[0][2] - pitch) <= 3 and cmd and 0 <= kons[0][0] - cmd[0] <= 6),
               " ".join(f"{k}:v{n}:{p:04X}" for k, n, p in kons))
        want = [ns[0]] if kind == "start" else ns[1:]
        res.ok(f"{sn} voice {kind}: the clip plays to its END from the ring (${ring:04X}, {nr} blocks)",
               bool(played and played[0] in want), f"played {played}, clip blocks {want}")
        res.ok(f"{sn} voice {kind}: every block in the ring before it plays, none written over an unplayed one",
               not bad and lead >= 0 and gapw >= 2,
               f"worst lead {lead}, worst margin behind {gapw}; " + "; ".join(bad[:4]))
        k0 = kons[0][0] if kons else 0
        if kons:
            lags = _voice_lags(l, k0, 70)
            res.ok(f"{sn} voice {kind}: no main-loop pass lost while it plays", not lags, f"lost {lags}")
        vs = dict(l.values.get("vs", []))
        bok = dict(l.values.get("bok", []))
        b = _part_b()
        if kind == "end" or plan.get("good_only"):   # (SB5's boss victory song: B as SB5's songs have it, nobody
            # cornered; 1-2: no B in ARAM, the stage is over)
            return res
        if not shared:
            res.ok(f"{sn} voice {kind}: part B stays in ARAM ($7F:FBB1 = 1 until the clear jingle)",
                   all(v[0] == 1 for k, v in bok.items() if vs.get(k, b"\0")[0] == 0xA5
                       and not (kind == "clear" and asked and k >= asked[0]))
                   and aram[crowd.HIGH_LO - len(b):crowd.HIGH_LO] == b, "")
            return res
        back = [k for k in sorted(vs) if k > k0 and vs[k][0] == 0xA5 and vs[k][2] == VOICE_B
                and (vs[k][3] | vs[k][4] << 8) == len(b) // 9 and vs[k][7] == 2 and bok.get(k, b"\0")[0] == 1]
        res.ok(f"{sn} voice {kind}: then part B goes back to the ring's top on idle time ($7F:FBB1 = 1)", bool(back),
               f"back at {back[:1]}")
        if back and kons:
            lags = _voice_lags(l, k0 + 70, max(0, back[0] - k0 - 70))
            res.ok(f"{sn} voice {kind}: no main-loop pass lost while B loads", not lags, f"lost {lags}")
            res.ok(f"{sn} voice {kind}: part B back byte for byte", aram[crowd.HIGH_LO - len(b):crowd.HIGH_LO] == b, "")
        if kind == "start":
            silent = [k for k in sorted(bok) if asked and asked[0] <= k and bok[k][0] != 1]
            res.ok(f"{sn} voice start: the cornered sound waits for B only while the voice holds the ring",
                   bool(back) and all(k < back[0] for k in silent), f"B missing at {silent[:1]}-{silent[-1:]}")
        return res
    return ev


def corner_eval(stage, tag):
    sn = STAGES.get(stage, f"${stage:02X}")

    def ev(logs, boot):
        from sb6.features import crowd, game_sfx as G
        res = Result()
        l = logs.get("v_corner")
        if not res.ok(f"{sn} cornered: scenario ran", l is not None, ""):
            return res
        aram = _aram(tag, "v_corner")
        b = _part_b()
        b1 = crowd.HIGH_LO - len(b)
        from sb6.features import voice_sfx as V
        voiced = stage in V.STAGES
        first = [v for k, v in l.values.get("bok", [])][:1]
        res.ok(f"{sn} cornered: part B in ARAM (${b1:04X}-$DCFF{', $7F:FBB1 = 1' if voiced else ''})",
               aram[b1:crowd.HIGH_LO] == b and (not voiced or (first and first[0][0] == 1)), "")
        loop = aram[0xFD00 + 4 * G.SRC_CORNER + 2] | aram[0xFD00 + 4 * G.SRC_CORNER + 3] << 8
        res.ok(f"{sn} cornered: part A loops into B (directory ${G.SRC_CORNER:02X})", loop == b1, f"loop ${loop:04X}")
        cmd = [k for k, c in l.cmds if c == G.CMD_CORNER]
        res.ok(f"{sn} cornered: SFX ${G.CMD_CORNER:02X}", bool(cmd), f"{cmd[:3]}")
        regs, kon = {}, None
        for k, cyc, r, v in l.dsp:
            regs[r] = v
            if r == 0x4C and v & 8 and regs.get(0x34) == G.SRC_CORNER and kon is None:
                kon = k
        last = max([brr for kind, k, a, brr in l.spc if kind == "B" and kon is not None and k >= kon
                    and b1 <= brr < crowd.HIGH_LO] or [0])
        res.ok(f"{sn} cornered: plays through part B to its end (sampled once a frame: within 12 blocks)",
               bool(kon is not None and last >= crowd.HIGH_LO - 9 * 12), f"key-on {kon}, last block ${last:04X}")
        writes = [k for kind, k, a, brr in l.spc if kind == "A"]
        res.ok(f"{sn} cornered: nothing written into B meanwhile", not writes, f"{writes[:3]}")
        return res
    return ev


# ---------------------------------------------------------------- pause -> RETURN TO WORLD MAP: the stage markers
# SB5's marker op ($C2:0EBD) loaded the marker sheet with the width of the stage's last sprite load ($0AE4): after
# 1-3 (6 columns) the open stages' flags (OBJ tile 12) showed stage tiles (features/world1.py markers: $C0:1F03).
# Each stage: pause, RETURN TO WORLD MAP, YES; on the map every marker sprite (OAM palette 1, 8x8) must use OBJ
# columns the map's allocator gave out ($7E:2FAA: 16 columns per 1 KB page, $FF free).
WMAP_MAP = 270                      # frames from Start to a world map with its markers up (~235 measured)


def wmap_scenarios(stage):
    p = 910 if stage == 0x68 else PAUSE_FROM            # (1-7's intro holds the players: as pierce_scenarios)
    n = p + WMAP_MAP
    st = [[p, "pad", 0, "start", 3], [p + 40, "pad", 0, "down", 3], [p + 60, "pad", 0, "start", 3],
          [p + 80, "pad", 0, "down", 3], [p + 100, "pad", 0, "start", 3]]
    st += [[k, "read", "m", 0x1031, 1] for k in range(p, n, 10)]
    st += [[n - 2, "read7e", "omap", 0x2FAA, 256], [n - 2, "readoam", "oam"]]
    return [Scenario("wmap", n, steps=st)]


def wmap_eval(stage):
    name = STAGES[stage]

    def ev(logs, boot, tag):
        res = Result()
        l = logs["wmap"]
        modes = [v[0] for _, v in l.values.get("m", [])]
        res.ok(f"{name}: pause -> RETURN TO WORLD MAP -> YES leads to the map (mode 3)", 3 in modes,
               f"modes {sorted(set(modes))}")
        omap, o = l.value("omap"), l.value("oam")
        if omap is None or o is None:
            res.ok(f"{name}: world map dumped", False, "")
            return res
        marks, bad = 0, []
        for s in range(128):
            y, attr = o[4 * s + 1], o[4 * s + 3]
            big = (o[512 + s // 4] >> (2 * (s % 4) + 1)) & 1
            if y >= 0xE0 or (attr >> 1) & 7 != 1 or big:
                continue
            t = o[4 * s + 2] | (attr & 1) << 8
            marks += 1
            col = 16 * (t >> 5) + (t & 15)
            if omap[col] == 0xFF:
                bad.append(f"sprite {s} tile ${t:02X} (column {col} free)")
        res.ok(f"{name}: the world map shows its 7 stage markers", marks >= 7, f"{marks} marker sprites")
        res.ok(f"{name}: every marker drawn from the marker sheet's columns (not the stage's leftovers)", not bad,
               "; ".join(bad[:4]))
        return res
    return ev
