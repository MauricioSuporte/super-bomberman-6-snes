#!/usr/bin/env python3
"""Normal Game menus in Mesen 2 headless (tools/mesen/menu_check.lua): one player, title -> players count ->
character selection -> NORMAL MODE menu and back with B, each of its items (New Game / Continue / Erase File) and
back, then a file -> the stage.

    python tools/menu_check.py          (also run by tools/qa_check.py, suite "menus")

Checks: every accept / back sound plays to its end (the menu's stream driver keeps playing it while the next
screen loads: the music switches tracks in place), the music of each screen (stream track: 1 title, 3 character
selection, 2 save files; Hudson's driver in the stage), the character selection's last confirmation shows its
animation before the fade, the NORMAL MODE menu answers quickly (A on an item -> its file list taking input,
B -> the menu) and its hand cursor shows its own sprite in the menu and every list. Prints one "ok" / "FAIL" line per check; exit code 1 when one fails.
Env: MESEN, SB6_ROM.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESEN = os.environ.get("MESEN", "D:/sb6-tools/mesen/Mesen.exe")
ROM = os.environ.get("SB6_ROM", os.path.join(ROOT, "build", "Super Bomberman 6.sfc"))
LUA = os.path.join(ROOT, "tools", "mesen", "menu_check.lua")
OUT = os.path.join(ROOT, "build", "qa", "menu_check.txt")

SFX_MIN = 38            # frames the accept / back sounds play (0.70 / 0.72 s recordings, tools/sb6/features/title_music.py)
MENU_READY = 50         # A on a NORMAL MODE item -> its list takes input; B on a list -> the menu (frames; SB5's
                        # hand cursor slides in for 19 of them)
HAND = (0x02, 0x2E)     # the hand cursor: one 16x16 sprite, tile / attributes (animation $46), at X = [$1038],
HAND_DY = -17           # Y = [$1034] - 17
PICK_SHOW = 12          # frames the picker's last confirmation shows before its fade
PICK_DARK = (35, 70)    # ... and until the screen is dark
LIST_X, MENU_X = 0x30, 0x48     # hand cursor X ($1038) in a file list / the menu
ITEMS = ("New Game", "Continue", "Erase File")

# Players menu with pads 1-2 plugged in (the testrunner's ports, no multitap): down, down, up, down -> 2, 1, 2, 1
# PLAYER GAME (the cursor stops at the pads plugged in, asm/picker.asm FF 1A F7)
PADS = [("down", 1), ("down", 0), ("up", 1), ("down", 0)]
PLAN = ["title", "start", "players", "w10"] + [x for i, (b, _) in enumerate(PADS) for x in (b, "w10", f"mark:pads{i}")]
PLAN += ["w10", "mark:title_accept", "start", "pick", "w20",
        "mark:pick_accept", "a", "ready", "oam:menu", "w10", "mark:menu_back", "b", "pick", "w20",
        "mark:pick_back", "b", "players", "w20", "start", "pick", "w20", "a", "ready"]
for i in range(3):
    PLAN += [f"item:{i}", "w20", f"mark:open{i}", "a", "ready", f"oam:list{i}", "w10", f"mark:back{i}", "b", "ready",
             f"oam:back{i}"]
PLAN += ["item:0", "w20", "a", "ready", "w10", "mark:file", "stage", "w240", "mark:end"]


def parse(path):
    rows, presses, marks, pcs, sounds, end = [], [], {}, [], [], None
    oams = {}
    for line in open(path).read().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "R":
            v = [int(x, 16) for x in f[2:]]
            rows.append((int(f[1]), dict(mode=v[0], state=v[1], menu=v[2], bright=v[3], track=v[4], active=v[5],
                                          v0=v[6], pk=v[7], item=v[8], y=v[9], x=v[10], v7=v[11])))
        elif f[0] == "P":
            presses.append((int(f[1]), f[2]))
        elif f[0] == "K":
            marks[f[2]] = int(f[1])
        elif f[0] == "T":
            pcs.append((int(f[1]), int(f[2].split(":")[1], 16)))
        elif f[0] == "S":
            sounds.append((int(f[1]), int(f[2], 16)))
        elif f[0] == "O":
            oams[f[2]] = (int(f[3], 16), int(f[4], 16), bytes.fromhex(f[5]))
        elif f[0] == "E":
            end = line
    parse.oams = oams
    return rows, presses, marks, pcs, sounds, end


def sprites(oam):
    """Visible OAM entries: (x, y, tile, attributes, large)."""
    out = []
    for i in range(128):
        x, y, t, a = oam[4 * i:4 * i + 4]
        hi = oam[512 + i // 4] >> (2 * (i % 4)) & 3
        if y < 0xE0:
            out.append((x | (hi & 1) << 8, y, t, a, hi >> 1))
    return out


def hand_ok(entry):
    """The hand cursor drawn where the menu's cursor is, with its own sprite (not another tile)."""
    if entry is None:
        return False, "no OAM"
    y, x, oam = entry
    sp = sprites(oam)
    hit = [s for s in sp if abs(s[0] - x) <= 2 and abs(s[1] - (y + HAND_DY)) <= 2]
    ok = any((s[2], s[3]) == HAND for s in hit)
    return ok, f"sprites at the cursor {[(f'${s[2]:02X}', f'${s[3]:02X}') for s in hit]}, {len(sp)} visible"


class Timeline:
    def __init__(self, rows):
        self.rows = rows

    def at(self, frame):
        cur = self.rows[0][1]
        for f, r in self.rows:
            if f > frame:
                break
            cur = r
        return cur

    def first(self, start, cond, stop=None):
        for f, r in self.rows:
            if f >= start and (stop is None or f < stop) and cond(r):
                return f
        if cond(self.at(start)):
            return start
        return None

    def during(self, a, b):
        out = [self.at(a)]
        out += [r for f, r in self.rows if a < f < b]
        return out


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    env = dict(os.environ, SB6_OUT=OUT, PLAN=",".join(PLAN))
    try:
        subprocess.run([MESEN, "--testrunner", ROM, LUA], env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600)
    except subprocess.TimeoutExpired:
        pass
    bad = 0

    def check(label, ok, detail=""):
        nonlocal bad
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} menus: {label}" + (f"  ({detail})" if detail else ""))

    if not os.path.exists(OUT):
        check("Mesen ran the menus", False, f"no {OUT}")
        return 1
    rows, presses, marks, pcs, sounds, end = parse(OUT)
    check("the plan ran to its end", bool(end) and end.endswith("done"), end or "no end line")
    if not rows or not end or not end.endswith("done"):
        return 1
    tl = Timeline(rows)

    def press_after(name):
        k = marks.get(name)
        return next((f for f, _ in presses if k is not None and f >= k), None)

    def next_press(f):
        return next((p for p, _ in presses if p > f), None)

    def sound_len(p):
        """Frames voice 0 (the stream driver's / Hudson's SFX voice) keeps playing from the press on."""
        on = tl.first(p, lambda r: r["v0"] == 1, p + 4)
        if on is None:
            return 0
        off = tl.first(on, lambda r: r["v0"] == 0)
        nxt = next_press(p)
        if nxt is not None and (off is None or off > nxt):       # another sound on the next press
            off = nxt
        return (off if off is not None else rows[-1][0]) - p

    def ready(p):
        """The menu task's input loop: its last pc change before the next press."""
        nxt = next_press(p) or rows[-1][0]
        ch = [f for f, _ in pcs if p < f < nxt]
        return ch[-1] if ch else None

    def music(label, p, until, track):
        rs = tl.during(p, until)
        released = [r for r in rs if r["active"] != 1]
        tr = tl.at(until)["track"]
        check(f"{label}: the stream goes on (no upload, the sound plays), track {track}",
              not released and tr == track, f"track {tr}, released {len(released)} frames")
        sw = tl.first(p, lambda r: r["track"] == track)
        on = tl.first(sw + 2, lambda r: r["v7"] == 1) if sw is not None else None
        check(f"{label}: track {track} plays (stream voice on) once the screen is lit",
              on is not None and on <= until, f"switch at +{sw - p if sw is not None else '-'}, music at "
              f"+{on - p if on is not None else '-'}, lit at +{until - p}")

    # 0. players menu: only the pads plugged in
    got = [tl.at(marks[f"pads{i}"])["item"] if f"pads{i}" in marks else None for i in range(len(PADS))]
    check("players menu with pads 1-2 plugged in: the cursor stays on 1-2 PLAYER GAME",
          got == [n for _, n in PADS], f"{' '.join(b for b, _ in PADS)} -> {got}")

    # 1. title -> character selection
    p = press_after("title_accept")
    n = sound_len(p) if p else 0
    check("title players count accept: its sound plays to the end", n >= SFX_MIN, f"{n} frames")
    lit = tl.first(p, lambda r: r["mode"] == 4 and r["pk"] == 2 and r["bright"] == 0x0F) if p else None
    check("players count -> character selection lit", lit is not None, f"{lit - p if lit else '-'} frames")
    if lit:
        music("title -> character selection", p, lit, 3)

    # 2. last confirmation -> save files
    p = press_after("pick_accept")
    n = sound_len(p) if p else 0
    check("character selection's last confirmation: its sound plays to the end", n >= SFX_MIN, f"{n} frames")
    fade = tl.first(p + 2, lambda r: r["mode"] == 4 and r["bright"] != 0x0F) if p else None
    dark = tl.first(p + 2, lambda r: r["bright"] & 0x80) if p else None
    check(f"... its animation shows {PICK_SHOW}+ frames before the fade, dark after {PICK_DARK[0]}-{PICK_DARK[1]}",
          fade is not None and dark is not None and fade - p >= PICK_SHOW and PICK_DARK[0] <= dark - p <= PICK_DARK[1],
          f"fade at +{fade - p if fade else '-'}, dark at +{dark - p if dark else '-'}")
    menu = tl.first(p + 2, lambda r: r["mode"] == 3 and r["bright"] == 0x0F) if p else None
    check("... then the NORMAL MODE menu lit", menu is not None, f"{menu - p if menu else '-'} frames")
    if menu:
        music("character selection -> save files", p, menu, 2)

    # 3. B: save files -> character selection -> title
    p = press_after("menu_back")
    n = sound_len(p) if p else 0
    check("B on the NORMAL MODE menu: its sound plays to the end", n >= SFX_MIN, f"{n} frames")
    lit = tl.first(p, lambda r: r["mode"] == 4 and r["pk"] == 2 and r["bright"] == 0x0F) if p else None
    check("... back to the character selection", lit is not None, f"{lit - p if lit else '-'} frames")
    if lit:
        music("save files -> character selection", p, lit, 3)
    p = press_after("pick_back")
    n = sound_len(p) if p else 0
    check("B on the character selection: its sound plays to the end", n >= SFX_MIN, f"{n} frames")
    lit = tl.first(p, lambda r: r["mode"] == 2 and r["menu"] == 1 and r["bright"] == 0x0F) if p else None
    check("... back to the title's players menu", lit is not None, f"{lit - p if lit else '-'} frames")
    if lit:
        music("character selection -> title", p, lit, 1)

    oams = parse.oams
    ok, d = hand_ok(oams.get("menu"))
    check("NORMAL MODE menu: the hand cursor is drawn (its sprite at the cursor)", ok, d)

    # 4. NORMAL MODE menu items and back
    for i, name in enumerate(ITEMS):
        p = press_after(f"open{i}")
        if p is None:
            check(f"{name}: pressed", False)
            continue
        n = sound_len(p)
        check(f"{name}: the accept sound plays to the end", n >= SFX_MIN, f"{n} frames")
        r = ready(p)
        opened = r is not None and tl.at(r)["x"] == LIST_X
        check(f"{name}: A -> its file list takes input within {MENU_READY} frames",
              opened and r - p <= MENU_READY, f"{r - p if r else '-'} frames, cursor X ${tl.at(r)['x'] if r else 0:02X}")
        ok, d = hand_ok(oams.get(f"list{i}"))
        check(f"{name}: the file list's hand cursor is drawn", ok, d)
        b = press_after(f"back{i}")
        n = sound_len(b) if b else 0
        check(f"{name}: B -> its sound plays to the end", n >= SFX_MIN, f"{n} frames")
        r = ready(b) if b else None
        back = r is not None and tl.at(r)["x"] == MENU_X and tl.at(r)["mode"] == 3
        check(f"{name}: B -> the NORMAL MODE menu takes input within {MENU_READY} frames",
              back and r - b <= MENU_READY, f"{r - b if r else '-'} frames")
        ok, d = hand_ok(oams.get(f"back{i}"))
        check(f"{name}: B -> the menu's hand cursor is drawn", ok, d)

    # 5. a file -> the stage (Hudson's driver back: SB5's song request before the stage releases the stream)
    p = press_after("file")
    n = sound_len(p) if p else 0
    check("a file chosen: the accept sound plays to the end", n >= SFX_MIN, f"{n} frames")
    st = tl.first(p, lambda r: 0x0D <= r["mode"] < 0x74) if p else None
    song = next((f for f, s in sounds if p and f > p and s >> 8 == 0), None)
    rel = tl.first(p, lambda r: r["active"] == 0) if p else None
    check("... a song request releases the stream (Hudson's driver), then the stage starts",
          st is not None and song is not None and rel is not None and song <= rel <= st and tl.at(st)["active"] == 0,
          f"song at +{song - p if song else '-'}, released at +{rel - p if rel else '-'}, stage at +{st - p if st else '-'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
