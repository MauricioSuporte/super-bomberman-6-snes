"""Runs tools/mesen/qa.lua: one Mesen process per fixture, every scenario of it from one savestate.

A fixture is the game state at a stage frame after the picker (players, characters, colors, stage); its
savestate is cached in build/qa/states/<rom sha1>_<fixture>.mss, so only the first run after a build boots
the game (~8 s); the scenarios load it (a scenario of 400 frames takes ~1.5 s).
"""
import hashlib
import os
import subprocess
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MESEN = os.environ.get("MESEN", "D:/sb6-tools/mesen/Mesen.exe")
ROM = os.environ.get("SB6_ROM", os.path.join(ROOT, "build", "Super Bomberman 6.sfc"))
OUT = os.path.join(ROOT, "build", "qa")
LUA = os.path.join(ROOT, "tools", "mesen", "qa.lua")


def rom_sha1():
    return hashlib.sha1(open(ROM, "rb").read()).hexdigest()[:12]


def lua(v):
    """Python value -> Lua literal."""
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k} = {lua(x)}" for k, x in v.items()) + "}"
    return "{" + ", ".join(lua(x) for x in v) + "}"


@dataclass
class Fixture:
    name: str                       # cache key part (unique per settings)
    stage: int = 0x0D
    players: int = 4
    picks: tuple = ((0, 0), (1, 0), (2, 0), (3, 0))   # (character, color) per seat
    ready: int = 300                # stage frame of the savestate
    mounts: tuple = ()              # Louie type 0-5 per seat (-1 none): the stage starts with the seats riding
    absent: tuple = ()              # seats out of the stage at its start (as after dying without a life): Start
                                    # brings them in when a life is left

    def lua(self):
        d = {"stage": self.stage, "players": self.players, "ready": self.ready,
             "picks": [{"c": c, "k": k} for c, k in self.picks]}
        if self.mounts:
            d["mounts"] = list(self.mounts)
        if self.absent:
            d["absent"] = list(self.absent)
        return d


@dataclass
class Scenario:
    name: str
    len: int
    steps: list = field(default_factory=list)
    invincible: bool = True
    pose: tuple = ()                # actors whose OAM/VRAM is dumped every frame
    watch: tuple = ()               # more actors whose animation / object is logged
    exec: tuple = ()                # CPU addresses logged when run ("X k exec ...")
    dma: bool = False               # log every DMA ("Y") and NMI milestones ("Z")

    def lua(self):
        d = {"name": self.name, "len": self.len, "steps": self.steps, "invincible": self.invincible}
        if self.watch:
            d["watch"] = list(self.watch)
        if self.exec:
            d["exec"] = list(self.exec)
        if self.dma:
            d["dma"] = True
        if self.pose:
            d["rec"] = {"pose": list(self.pose)}
        return d


class Log:
    """Parsed QA_OUT of one scenario."""

    def __init__(self, name, lines):
        self.name, self.lines = name, lines
        self.anims = {}        # actor -> [(k, anim)]
        self.objs = {}         # actor -> [(k, obj)]
        self.reqs = []         # (k, group, id)
        self.port0 = []        # (k, cmd)
        self.ports = []        # (k, port 1-3, value)
        self.gsfx = []         # (k, cmd)
        self.cmds = []         # (k, cmd) through $C0:0E7F
        self.modes = []        # (k, mode)
        self.deaths = []       # (k, seat)
        self.fps = []          # (k, runs)
        self.values = {}       # name -> [(k, bytes)]
        self.msgs = []
        self.dma = []          # raw "Y" / "Z" lines
        self.clobber = []      # (k, page, owner, vram): static graphics written over a live sprite page
        for l in lines:
            f = l.split()
            t = f[0]
            if t == "A":
                self.anims.setdefault(int(f[2]), []).append((int(f[1]), int(f[3], 16)))
            elif t == "O":
                self.objs.setdefault(int(f[2]), []).append((int(f[1]), int(f[3], 16)))
            elif t == "Q":
                self.reqs.append((int(f[1]), int(f[2], 16), int(f[3], 16)))
            elif t == "P":
                self.port0.append((int(f[1]), int(f[2], 16)))
            elif t in ("P1", "P2", "P3"):
                self.ports.append((int(f[1]), int(t[1]), int(f[2], 16)))
            elif t == "C":
                self.cmds.append((int(f[1]), int(f[2], 16)))
            elif t == "G":
                self.gsfx.append((int(f[1]), int(f[2], 16)))
            elif t == "M":
                self.modes.append((int(f[1]), int(f[2], 16)))
            elif t == "D":
                self.deaths.append((int(f[1]), int(f[2])))
            elif t == "F":
                self.fps.append((int(f[1]), int(f[2])))
            elif t == "V":
                self.values.setdefault(f[2], []).append((int(f[1]), bytes.fromhex(f[3]) if len(f) > 3 else b""))
            elif t == "B":
                self.clobber.append((int(f[1]), int(f[2]), int(f[3], 16), int(f[4], 16)))
            elif t in ("Y", "Z"):
                self.dma.append(l)
            elif t in ("X", "W"):
                self.msgs.append(l)

    def anim_ids(self, actor, since=0, until=1 << 30):
        return [a for k, a in self.anims.get(actor, []) if since <= k < until]

    def value(self, name):
        v = self.values.get(name)
        return v[-1][1] if v else None

    def sfx_cmds(self):
        """SPC port 0 commands (bit 7 is the toggle)."""
        return [(k, c & 0x7F) for k, c in self.port0]


def run(fixture, scenarios, tag=None, timeout=900):
    """Runs the scenarios of one fixture; returns ({scenario name: Log}, engine messages)."""
    os.makedirs(os.path.join(OUT, "states"), exist_ok=True)
    tag = tag or fixture.name
    plan = os.path.join(OUT, f"{tag}.plan.lua")
    outp = os.path.join(OUT, f"{tag}.log")
    state = os.path.join(OUT, "states", f"{rom_sha1()}_{fixture.name}.mss")
    with open(plan, "w") as h:
        h.write("return " + lua({"fixture": fixture.lua(), "scenarios": [s.lua() for s in scenarios]}) + "\n")
    if os.path.exists(outp):
        os.remove(outp)
    env = dict(os.environ, QA_PLAN=plan, QA_OUT=outp, QA_STATE=state)
    try:
        subprocess.run([MESEN, "--testrunner", ROM, LUA], env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    logs, msgs, cur, buf = {}, [], None, []
    if os.path.exists(outp):
        for l in open(outp).read().splitlines():
            if l.startswith("S "):
                cur, buf = l[2:], []
            elif l.startswith("E ") and cur:
                logs[cur] = Log(cur, buf)
                cur = None
            elif cur:
                buf.append(l)
            else:
                msgs.append(l)
    if not any(m.startswith("X 0 fixture") for m in msgs) and os.path.exists(state) and not logs:
        os.remove(state)        # (a state that did not load: built again next time)
    return logs, msgs


def pose_file(tag, scenario):
    return os.path.join(OUT, f"{tag}.log_{scenario}.pose")
