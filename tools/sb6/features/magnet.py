"""SB6's Magnet Bomb (Unity's MagnetBombAbility / MagnetBomb.cs) in place of SB5's mine.

Item $0F (SB5's mine, ability $7E:4ED5 bit $20, exclusive with the other bomb types) gives it: its field icon is
Unity's MagnetBombIcon (features/items.py), its HUD bomb type icon Unity's HUD/NormalGame/MagnetBomb.png
(features/hud.py), its bomb assets/bombs/MagnetBomb.png (OBJ tiles $12E / $100 / $102, animation 4: features/bombs.py).
A magnet bomb at rest looks along its row and column for an enemy and, one 2-12 cells away in view, gets kicked
toward it (rules in asm/magnet.asm). No bomb becomes a mine any more: SB5's mine setup is freed.
"""
import os

from .. import asar
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "magnet.asm")
ITEM = 0x0F                 # SB5's mine item
ABILITY = 0x20
ANIM = 4                    # type 0 animation 4: bombs.remap's script (OBJ tiles $12E / $100 / $102)
MAG = 0x7FFB2C              # a byte per bomb slot (20)
WAIT, AGAIN, RANGE = 60, 4, 12
# SB5's mine setup ($C4:3093, only called by the JSR at $C4:3076, now jumped over)
OLD_DATA = [("free_c4_mine", 0xC43093, 0x30, 0x9F7995A8, "was SB5's mine setup (a bomb of ability $20)")]


def _jsr(a):
    return bytes([0x20, a & 0xFF, a >> 8 & 0xFF])


def apply(rb):
    reg = rb.regions["c5"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"C5": f"${reg.cursor:06X}"})
    start, end = reg.cursor, syms["end_c5"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"magnet.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    if rb.alloc("c5", bytes(out[off(start):off(end)]), "magnet bomb: looks for enemies, kicked to them "
                                                         "(asm/magnet.asm)") != start:
        raise BuildError("magnet: code moved")
    a = syms["mg_place"]
    for at in (0xC51AFC, 0xC51BA5):
        rb.patch(at, bytes.fromhex("9E CC 0E"), _jsr(syms["mg_alloc"]), "magnet: a new bomb is not a magnet bomb")
    rb.patch(0xC43050, bytes.fromhex("29 11 99 CC 0E"), bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xEA]),
             "magnet: a bomb of an owner with ability $20 is a magnet bomb")
    # BIT #$20 / BEQ / JSR $3093 (the mine) / BRA -> BRA $307E
    rb.patch(0xC43072, bytes.fromhex("89 20 F0 08 20 93 30"), bytes.fromhex("80 0A EA EA EA EA EA"),
             "magnet: no bomb becomes a mine")
    for name, s, size, crc, purpose in OLD_DATA:
        rb.free_old(name, s, size, crc, purpose)
    rb.patch(0xC43646, bytes.fromhex("89 21"), bytes.fromhex("89 01"),
             "magnet: a dying bomber's magnet bombs stay (only remote bombs go off)")
    rb.patch(0xC51C49, bytes.fromhex("D0 EF"), bytes.fromhex("EA EA"),
             "magnet: every bomb of ability $20 shows animation 4 (the magnet bomb)")
    m = syms["mg_rest"]
    rb.patch(0xC51FEA, bytes.fromhex("4C 58 20"), bytes([0x4C, m & 0xFF, m >> 8 & 0xFF]),
             "magnet: a magnet bomb at rest looks for enemies")
    return syms
