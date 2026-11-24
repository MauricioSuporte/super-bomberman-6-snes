"""Items hidden in the soft blocks of World 1's stages (asm/stage_items.asm): one of each, whatever the players.

SB5's lists ($C4:E5C7, per stage [item, count, count with two players]) stay for Battle and the other stages.
SB5 item ids (docs/ROM_MAP.md): 1 fire, 2 bomb, 3 skate, 4 remote (SB6's control bomb), 5 bomb pass, 7 vest
(invincible suit), 8 clock (stops the enemies), 9 1-up, $0B kick, $0D pierce, $0F magnet bomb (SB5's mine,
features/magnet.py), $10 search bomb, $11 boxing glove (SB6's red glove: punch), $14 heart, $15 egg.
"""
import os

from .. import asar
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "stage_items.asm")
FIRE, BOMB, SKATE, CONTROL, BOMB_PASS, VEST, CLOCK, ONE_UP, KICK, PIERCE, MAGNET, SEARCH, BOXING, HEART, EGG = \
    0x01, 0x02, 0x03, 0x04, 0x05, 0x07, 0x08, 0x09, 0x0B, 0x0D, 0x0F, 0x10, 0x11, 0x14, 0x15
BASIC = [BOMB, FIRE, SKATE]
# stage ($102F) -> items, one each (in this order while soft blocks are left)
ITEMS = {
    0x0D: BASIC + [CLOCK, VEST],                # 1-1
    0x11: BASIC + [EGG, KICK, MAGNET],          # 1-2
    0x18: BASIC + [BOXING, PIERCE],             # 1-3
    0x10: BASIC + [EGG, SEARCH],                # 1-4
    0x17: BASIC + [ONE_UP, HEART, BOMB_PASS, CONTROL],   # 1-5
}
NAMES = {FIRE: "fire", BOMB: "bomb", SKATE: "skate", BOMB_PASS: "bomb pass", VEST: "vest", CLOCK: "clock",
         ONE_UP: "1-up", KICK: "kick", MAGNET: "magnet bomb", BOXING: "boxing glove", HEART: "heart", EGG: "egg",
         CONTROL: "control bomb", PIERCE: "pierce bomb", SEARCH: "search bomb"}


def apply(rb):
    table = []
    for stage, items in ITEMS.items():
        if not items or 0 in items or 0xFF in items:
            raise BuildError(f"stage_items: bad list for stage ${stage:02X}")
        table += [stage] + items + [0]
    table.append(0xFF)
    reg = rb.regions["c5"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"C5": f"${reg.cursor:06X}",
                                                "TABLE": ",".join(f"${b:02X}" for b in table)})
    start, end = reg.cursor, syms["end_c5"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"stage_items.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    if rb.alloc("c5", bytes(out[off(start):off(end)]), "stage items: World 1's lists (asm/stage_items.asm)") != start:
        raise BuildError("stage_items: code moved")
    a = syms["si_spread"]
    rb.patch(0xC53FEF, bytes.fromhex("AD 1A 1D"), bytes([0x4C, a & 0xFF, a >> 8 & 0xFF]),
             "stage items: World 1's own lists")
    return {f"${s:02X}": [NAMES.get(i, f"${i:02X}") for i in items] for s, items in ITEMS.items()}
