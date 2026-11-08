"""Shared helpers for the SB5 HiROM image (addresses are SNES $C0-$FF)."""

def off(addr):
    return addr & 0x3FFFFF

class Rom:
    def __init__(self, data):
        self.d = bytearray(data)
    def rb(self, a): return self.d[off(a)]
    def rw(self, a): return self.d[off(a)] | self.d[off(a) + 1] << 8
    def rl(self, a): return self.rw(a) | self.d[off(a) + 2] << 16

    def decompress(self, src, size):
        """$C0:1CB0 stream: control = mode (bits 5-7) + count-1 (bits 0-4);
        modes literal, prev+1, prev, copy -2/-4/-16/-32/-64 in a 256-byte ring.
        Returns (data, end_address)."""
        back = (0, 0, 0, 2, 4, 16, 32, 64)
        ring = [0] * 256
        idx = 0
        out = bytearray()
        control = self.rb(src); src += 1
        mode, count = control >> 5, (control & 31) + 1
        for i in range(size):
            if mode == 0:
                v = self.rb(src); src += 1
            elif mode == 1:
                v = (ring[(idx - 1) & 255] + 1) & 255
            elif mode == 2:
                v = ring[(idx - 1) & 255]
            else:
                v = ring[(idx - back[mode]) & 255]
            ring[idx] = v; idx = (idx + 1) & 255; out.append(v)
            count -= 1
            if not count and i + 1 < size:
                control = self.rb(src); src += 1
                mode, count = control >> 5, (control & 31) + 1
        return bytes(out), src

    # Graphics archives: table word $C0:1C96 + 2*set (bank $E3), 8-byte entries.
    def archive_entry_addr(self, gset, n):
        return 0xE30000 | (self.rw(0xC01C96 + 2 * gset) + (n - 1) * 8)

    def archive(self, gset, n):
        e = self.archive_entry_addr(gset, n)
        size = self.rw(e + 2) or 0x10000
        return dict(entry=e, vram=self.rw(e), size=size, src=self.rl(e + 4), flags=self.rb(e + 7))

    def archive_data(self, gset, n):
        a = self.archive(gset, n)
        if a['flags'] & 0x80:
            s = off(a['src'])
            return bytes(self.d[s:s + a['size']]), a['src'] + a['size']
        return self.decompress(a['src'], a['size'])
