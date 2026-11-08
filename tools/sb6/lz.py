"""Compressor for the SB5 stream format decoded by $C0:1CB0/$C0:1CCC.

Control byte = mode (bits 5-7) + count-1 (bits 0-4), count 1..32:
  0 literal (count bytes follow)   1 previous+1   2 previous
  3..7 copy the byte 2/4/16/32/64 positions back (256-byte ring).
The encoder never references bytes before the start of the stream, so it
does not depend on the ring's initial contents.
"""

BACK = {3: 2, 4: 4, 5: 16, 6: 32, 7: 64}


def _run(data, i, mode):
    n = 0
    limit = min(32, len(data) - i)
    while n < limit:
        j = i + n
        if mode == 1:
            ok = j >= 1 and data[j] == (data[j - 1] + 1) & 0xFF
        elif mode == 2:
            ok = j >= 1 and data[j] == data[j - 1]
        else:
            k = BACK[mode]
            ok = j >= k and data[j] == data[j - k]
        if not ok:
            break
        n += 1
    return n


def compress(data):
    data = bytes(data)
    out = bytearray()
    lit = bytearray()

    def flush():
        while lit:
            chunk = lit[:32]
            out.append(len(chunk) - 1)
            out.extend(chunk)
            del lit[:32]

    i = 0
    while i < len(data):
        best_mode, best_len = 0, 0
        for mode in (2, 1, 3, 4, 5, 6, 7):
            n = _run(data, i, mode)
            if n > best_len:
                best_mode, best_len = mode, n
        if best_len >= 2:
            flush()
            out.append(best_mode << 5 | (best_len - 1))
            i += best_len
        else:
            lit.append(data[i])
            i += 1
            if len(lit) == 32:
                flush()
    flush()
    return bytes(out)


def decompress(stream, size):
    back = (0, 0, 0, 2, 4, 16, 32, 64)
    ring = [0] * 256
    idx = pos = 0
    out = bytearray()
    control = stream[pos]; pos += 1
    mode, count = control >> 5, (control & 31) + 1
    for i in range(size):
        if mode == 0:
            v = stream[pos]; pos += 1
        elif mode == 1:
            v = (ring[(idx - 1) & 255] + 1) & 255
        elif mode == 2:
            v = ring[(idx - 1) & 255]
        else:
            v = ring[(idx - back[mode]) & 255]
        ring[idx] = v; idx = (idx + 1) & 255; out.append(v)
        count -= 1
        if not count and i + 1 < size:
            control = stream[pos]; pos += 1
            mode, count = control >> 5, (control & 31) + 1
    return bytes(out), pos
