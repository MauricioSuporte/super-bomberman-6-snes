"""Louies and eggs in an OBJ palette of their own (asm/louies.asm).

The cartridge puts a mount's 8 colors in entries 8-15 of its rider's palette
(and an egg's in a player's), which the 15-color bombers now use. Mounts and
eggs get a palette slot with two halves instead: entries 8-15 (the stock
tiles) and entries 1-7 + 8, drawn with copies of the Louie sheets `$15-$22`
whose pixels 9-15 became 1-7 (pixel 8, the outline every Louie palette
shares, stays). Rules in asm/louies.asm.

Also here, because they come from the same change: a dying bomber keeps its
colors, and the invincibility blink blacks out all 16 colors.
"""
import os

from .. import asar
from ..objsheets import SHEET_TABLE
from ..rombuild import BuildError
from ..romlib import off

ASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "asm", "louies.asm")
FIRST, LAST = 0x15, 0x22     # Louie sheets
ANIM_TABLES = 0x80C415       # word per mount character -> [sheet, row] per animation
ANIMS = 34
EGG = 9                      # character of an egg: one [sheet, row] pair
# Test aid: extra items hidden in the soft blocks of a campaign stage
# ($1031: $0D = ZONE1 - 1), as (item, count): $15 egg, $0C power glove.
# Empty the dict to get the cartridge's items back.
TEST_ITEMS = {0x0D: [(0x15, 5), (0x0C, 5)]}


def _rows(rom):
    """Highest row (in $200 steps) each sheet is read at."""
    rows = {}
    for char in list(range(7)) + [EGG]:
        t = off(ANIM_TABLES + 2 * char)
        t = off(0x800000 | rom[t] | rom[t + 1] << 8)
        for i in range(1 if char == EGG else ANIMS):
            sheet, row = rom[t + 2 * i], rom[t + 2 * i + 1]
            if not FIRST <= sheet <= LAST:
                raise BuildError(f"louies: mount character {char} uses sheet ${sheet:02X}")
            rows[sheet] = max(rows.get(sheet, 0), row)
    return rows


def _low_half(tiles):
    """4bpp tiles with pixels 9-15 turned into 1-7 (0 and 8 stay)."""
    out = bytearray(tiles)
    for t in range(0, len(out) - 31, 32):
        for y in range(8):
            low = out[t + 2 * y] | out[t + 2 * y + 1] | out[t + 16 + 2 * y]
            out[t + 17 + 2 * y] &= ~low & 0xFF
    return bytes(out)


def apply(rb, base_rom, sheets):
    """`sheets`: sb6.objsheets.ObjSheets. Returns the asm symbols."""
    rows = _rows(base_rom)
    first = sheets.next_id
    for n in range(FIRST, LAST + 1):
        e = off(SHEET_TABLE + 8 * (n - 1))
        size = base_rom[e + 2] | base_rom[e + 3] << 8
        src = base_rom[e + 4] | base_rom[e + 5] << 8 | base_rom[e + 6] << 16
        # a page is 1 KB from row * $200, also past the sheet's own size
        length = max((size + 0x3FF) & ~0x3FF, rows.get(n, 0) * 0x200 + 0x400)
        sheets.add(_low_half(base_rom[off(src):off(src) + length]), f"louie: sheet ${n:02X} in colors 1-7")
    delta = first - FIRST

    reg = rb.regions["bulk"]
    runs, syms = asar.assemble_into(rb.d, ASM, {"E4": f"${reg.cursor:06X}", "DELTA": f"${delta:02X}"})
    start, end = reg.cursor, syms["end_e4"]
    out = bytearray(rb.d)
    for o, d in runs:
        if not (off(start) <= o and o + len(d) <= off(end)):
            raise BuildError(f"louies.asm wrote outside its section at file offset {o:06X}")
        out[o:o + len(d)] = d
    rb.alloc("bulk", bytes(out[off(start):off(end)]), "louie: palette halves (asm/louies.asm)")

    def jsl(name):
        a = syms[name]
        return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16])

    rb.patch(0xC453EB, bytes.fromhex("DA 48 9C E7 0A"), jsl("louie_pal") + b"\x60",
             "louie: mount/egg colors go to a Louie palette half")
    rb.patch(0xC4500C, bytes.fromhex("AD 38 1D C9 02 90 03 4C A1 50"),
             jsl("louie_egg_ok") + bytes.fromhex("90 04 4C A1 50 EA"),
             "louie: an egg appears only when it gets colors")
    rb.patch(0xC45148, bytes.fromhex("AD 1A 1D 89 01 F0"), jsl("louie_hatch") + bytes.fromhex("80 0F"),
             "louie: hatching picks a Louie whose colors fit")
    rb.patch(0xC45458, bytes.fromhex("B1 BD 85 AB"), jsl("louie_sheet"), "louie: tiles of the low half")

    rb.patch(0xC436B7, bytes.fromhex("20 B0 37"), b"\xEA\xEA\xEA", "bomber: death keeps the player's colors")
    rb.patch(0xC42EB7, bytes.fromhex("A9 07"), bytes.fromhex("A9 0F"), "bomber: blink blacks out all 16 colors")
    _test_eggs(rb)
    return syms


def _test_eggs(rb):
    """End of the stage item distribution ($C5:404C, after the stage's list at
    `$C4:E5C7` = [item, count, count with two players]): `$C5:40DE` (A = item)
    hides one more item in a random soft block without one."""
    if not TEST_ITEMS:
        return
    code = bytearray.fromhex("E2 10 AD 1A 1D 89 01 D0")   # SEP #$10 / LDA $1D1A / BIT #$01 / BNE out
    body = bytearray()
    for stage, items in TEST_ITEMS.items():
        for item, count in items:
            # LDA $1031 / CMP #stage / BNE next / LDY #count / - LDA #item / JSR $40DE / DEY / BNE -
            body += bytes([0xAD, 0x31, 0x10, 0xC9, stage, 0xD0, 0x0A, 0xA0, count,
                           0xA9, item, 0x20, 0xDE, 0x40, 0x88, 0xD0, 0xF8])
    code += bytes([len(body)]) + body
    addr = rb.regions["c5"].cursor
    code += bytes([0xA9, 0x01, 0x4C, 0x50, 0x40])          # out: LDA #$01 / JMP $4050
    if rb.alloc("c5", bytes(code), "test: extra items in a stage's soft blocks") != addr:
        raise BuildError("test items moved")
    rb.patch(0xC5404C, bytes.fromhex("E2 10 A9 01"), bytes([0x4C, addr & 0xFF, addr >> 8 & 0xFF, 0xEA]),
             "test: extra items after the stage's items")
