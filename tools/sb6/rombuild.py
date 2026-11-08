"""ROM image under construction: verified patches, free-space allocation, map.

Every change to an existing byte goes through `patch()`, which checks the
original bytes first, so a wrong address or a ROM revision mismatch fails the
build instead of silently corrupting the game.
"""
import hashlib

from .romlib import Rom, off

BASE_SHA1 = "417d5ace7e51baafb69d20ce15ff0894d91c70c5"  # Super Bomberman 5 (USA).sfc
ROM_SIZE = 4 * 1024 * 1024


class BuildError(Exception):
    pass


class Region:
    """A free area [start, end) in SNES address space that never crosses a bank."""

    def __init__(self, name, start, end, purpose):
        if start >> 16 != (end - 1) >> 16:
            raise ValueError(f"region {name} crosses a bank")
        self.name, self.start, self.end, self.purpose = name, start, end, purpose
        self.cursor = start

    def free(self):
        return self.end - self.cursor


class RomBuild(Rom):
    def __init__(self, data):
        if len(data) != ROM_SIZE:
            raise BuildError(f"base ROM must be {ROM_SIZE} bytes, got {len(data)}")
        sha1 = hashlib.sha1(data).hexdigest()
        if sha1 != BASE_SHA1:
            raise BuildError(f"unexpected base ROM sha1 {sha1}; expected {BASE_SHA1}")
        super().__init__(data)
        self.regions = {}
        self.allocs = []   # (address, size, region, label)
        self.patches = []  # (address, size, label)

    # ---- free space -------------------------------------------------------
    def add_region(self, name, start, end, purpose, fill=0xFF):
        o0, o1 = off(start), off(end - 1) + 1
        if any(b != fill for b in self.d[o0:o1]):
            raise BuildError(f"region {name} ${start:06X}-${end - 1:06X} is not free in the base ROM")
        self.regions[name] = Region(name, start, end, purpose)

    def alloc(self, region, data, label, align=1):
        """Places `data` in a region (never across a bank) and returns its address."""
        names = [region] if isinstance(region, str) else list(region)
        for name in names:
            r = self.regions[name]
            addr = (r.cursor + align - 1) // align * align
            if addr + len(data) <= r.end:
                o = off(addr)
                self.d[o:o + len(data)] = data
                r.cursor = addr + len(data)
                self.allocs.append((addr, len(data), name, label))
                return addr
        raise BuildError(f"no room for {label} ({len(data)} bytes) in {names}")

    # ---- patches ------------------------------------------------------------
    def patch(self, addr, expect, new, label):
        expect, new = bytes(expect), bytes(new)
        o = off(addr)
        cur = bytes(self.d[o:o + len(expect)])
        if cur != expect:
            raise BuildError(f"{label}: ${addr:06X} holds {cur.hex(' ')}, expected {expect.hex(' ')}")
        if len(new) > len(expect):
            raise BuildError(f"{label}: replacement longer than the verified bytes")
        self.d[o:o + len(new)] = new
        self.patches.append((addr, len(new), label))

    def w8(self, value):
        return bytes([value & 0xFF])

    @staticmethod
    def le16(v):
        return bytes([v & 0xFF, v >> 8 & 0xFF])

    @staticmethod
    def le24(v):
        return bytes([v & 0xFF, v >> 8 & 0xFF, v >> 16 & 0xFF])

    # ---- output -------------------------------------------------------------
    def set_title(self, title):
        raw = title.encode("ascii")
        if len(raw) > 21:
            raise BuildError("internal title longer than 21 characters")
        self.d[0xFFC0:0xFFD5] = raw.ljust(21, b" ")

    def fix_checksum(self):
        self.d[0xFFDC:0xFFE0] = b"\xFF\xFF\x00\x00"
        s = sum(self.d) & 0xFFFF
        self.d[0xFFDC:0xFFDE] = self.le16(s ^ 0xFFFF)
        self.d[0xFFDE:0xFFE0] = self.le16(s)

    def map_text(self):
        lines = ["# Super Bomberman 6 build map", "", "## Free-space regions"]
        for r in self.regions.values():
            used = r.cursor - r.start
            lines.append(f"{r.name:<14} ${r.start:06X}-${r.end - 1:06X}  used {used:6d} / {r.end - r.start:6d}  {r.purpose}")
        lines += ["", "## Allocations"]
        for a, n, reg, label in sorted(self.allocs):
            lines.append(f"${a:06X}  {n:6d}  {reg:<14} {label}")
        lines += ["", "## Patched original bytes"]
        for a, n, label in sorted(self.patches):
            lines.append(f"${a:06X}  {n:6d}  {label}")
        return "\n".join(lines) + "\n"
