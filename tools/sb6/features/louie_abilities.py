"""SB6's Louie abilities (SB5 Recomp's "Louie improvements" mod, SB6 Unity's Louie abilities) on SB5's routines.

* Red Louie: its punch also stuns the enemy in the cell ahead (Normal Game, 3 s; SB5's clock routine).
* Yellow Louie: a bomb ahead rolls away with the row of bombs after it; a rolling train takes the bombs it meets
  along and kicks a soft block on; a kicked soft block kicks the bomb it stops at.
* Black Louie (SB5's bosses' Louie) hatches out of eggs too (0-6) and dashes: 3 cells, invincible, pushing the first
  enemy 2 cells, or else an opponent bomber (a boss rival; any other bomber in Battle), stunned as by the Red punch.
* Green and Black dashes leave afterimages (OAM copies of the rider and Louie, flickering).

Rules and addresses: asm/louie_abilities.asm; docs/ROM_MAP.md "Louie abilities".
"""
import os

from .. import asar
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "louie_abilities.asm")
LA = 0x7FE800               # state (docs/FREE_SPACE.md), $1F8 bytes
TRAIN = LA + 0x1C0          # a byte per bomb slot
RED_T, DASH_T, CD_T, IMP_T, PUSH_T, PUSH_F, INV_T, GHOST_T = 180, 30, 40, 16, 16, 30, 30, 12
BLACK = 6
HOOKS = {   # address: (SB5's bytes, symbol, how)
    0xC45560: ("20 82 55", "la_red", "jsr"),
    0xC43180: ("8D C2 1C", "la_speed", "jsr"),
    0xC45797: ("BD 52 10 C9 30", "la_yahead", "jsr"),
    0xC45973: ("BD 52 10 C9 30", "la_bnext", "jsr"),
    0xC45427: ("64 A5 64 AE", "la_lanim", "jsr"),
}


def _jsl_target(rb, at):
    b = rb.d[off(at):off(at) + 4]
    if b[0] != 0x22:
        raise BuildError(f"louie_abilities: no JSL at ${at:06X}")
    return b[1] | b[2] << 8 | b[3] << 16


def apply(rb):
    from . import stage_items
    c4, c5 = rb.regions["c4"], rb.regions["c5"]
    pads, oam = _jsl_target(rb, 0xC00B54), _jsl_target(rb, 0xC00B5D)
    egg = stage_items.LOUIE_TEST if stage_items.LOUIE_TEST is not None else 0xFF
    runs, syms = asar.assemble_into(rb.d, ASM, {"C4": f"${c4.cursor:06X}", "C5": f"${c5.cursor:06X}",
                                                "PADS": f"${pads:06X}", "OAM": f"${oam:06X}",
                                                "EGG_STAGE": f"${egg:02X}"})
    secs = [(c4.cursor, syms["end_c4"]), (c5.cursor, syms["end_c5"])]
    out = bytearray(rb.d)
    for o, d in runs:
        if not any(off(s) <= o and o + len(d) <= off(e) for s, e in secs):
            raise BuildError(f"louie_abilities.asm wrote outside its sections at file offset {o:06X}")
        out[o:o + len(d)] = d
    for reg, (s, e), what in (("c4", secs[0], "Louie abilities: Red stun, Yellow trains, Black dash, afterimages"),
                              ("c5", secs[1], "Louie abilities: a train bomb's next cell")):
        if rb.alloc(reg, bytes(out[off(s):off(e)]), what + " (asm/louie_abilities.asm)") != s:
            raise BuildError("louie_abilities: code moved")
    for at, (old, sym, how) in HOOKS.items():
        a = syms[sym]
        new = bytes([0x20, a & 0xFF, a >> 8 & 0xFF])
        old = bytes.fromhex(old)
        rb.patch(at, old, new + b"\xEA" * (len(old) - 3), f"louie abilities: {sym}")
    a = syms["la_black"]
    rb.patch(0xC45527, bytes.fromhex("2F 55"), bytes([a & 0xFF, a >> 8 & 0xFF]),
             "louie abilities: the Black Louie's Y (was RTS) dashes")
    hatch = _jsl_target(rb, 0xC45148)       # asm/louies.asm louie_hatch
    a = syms["la_hatch"]
    rb.patch(hatch, bytes.fromhex("A9 06 22 EB 1D C0"), bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xEA, 0xEA]),
             "louie abilities: an egg's Louie (0-6 at random; one of each in order in the egg test stage)")
    a = syms["la_roll_t"]
    rb.patch(0xC52182, bytes.fromhex("20 1B 22"), bytes([0x20, a & 0xFF, a >> 8 & 0xFF]),
             "louie abilities: a Yellow Louie train's bomb takes resting bombs along / kicks soft blocks")
    for at, sym, old in ((0xC00B54, "la_pads", pads), (0xC00B5D, "la_oam", oam)):
        a = syms[sym]
        rb.patch(at, bytes([0x22, old & 0xFF, old >> 8 & 0xFF, old >> 16]),
                 bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16]), f"louie abilities: {sym} (then the old routine)")
    return syms
