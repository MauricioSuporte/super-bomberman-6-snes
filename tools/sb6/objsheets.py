"""Relocated OBJ sheet table (`$85:E22D`, read only by `$C5:6B77`).

The cartridge's table has no room for new sheets, so the features that add
dynamic sprite tiles (bombers, Louies) register them here; `finish()` writes
one copy of the table with the new entries and points the loader at it.
Sheet ids are bytes; a tile page is 1 KB at `source + row * $200`.
"""
from .romlib import off

SHEET_TABLE = 0x85E22D
COPIED_SHEETS = 96           # stock ids kept (bombers use 1-20, Louies $15-$22)
OBJ = ["obj_f0", "obj_f1", "obj_f2", "obj_f6", "obj_f7", "obj_f8", "obj_f9"]


class ObjSheets:
    def __init__(self, rb):
        self.rb = rb
        self.entries = bytearray(rb.d[off(SHEET_TABLE):off(SHEET_TABLE) + 8 * COPIED_SHEETS])

    @property
    def next_id(self):
        return len(self.entries) // 8 + 1

    def add(self, blob, label):
        """Stores raw 4bpp tiles and returns the new sheet id."""
        sheet = self.next_id
        if sheet > 0xFF:
            raise ValueError("OBJ sheet ids are bytes")
        addr = self.rb.alloc(OBJ, blob, label, align=0x400)
        self.entries += bytes([0, 0, len(blob) & 0xFF, len(blob) >> 8 & 0xFF,
                               addr & 0xFF, addr >> 8 & 0xFF, addr >> 16, 0x85])
        return sheet

    def finish(self):
        if len(self.entries) == 8 * COPIED_SHEETS:
            return
        rb = self.rb
        table = rb.alloc(OBJ, bytes(self.entries), "OBJ sheet table (copy of $85:E22D + new sheets)")
        rb.patch(0xC56B86, bytes.fromhex("A9 85"), bytes([0xA9, table >> 16]), "OBJ sheet table bank")
        rb.patch(0xC56B8C, bytes.fromhex("A9 2D E2"), bytes([0xA9, table & 0xFF, table >> 8 & 0xFF]),
                 "OBJ sheet table address")
