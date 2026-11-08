"""BRR encoder/decoder matching the S-DSP decoder bit for bit.

A BRR block is 9 bytes: header (shift << 4 | filter << 2 | loop << 1 | end)
followed by 16 signed 4-bit samples, high nibble first. The decoder (as in
blargg's/bsnes's S-DSP) keeps the previous two output samples p1/p2:

    s = (nibble << shift) >> 1
    filter 1: s += p1 >> 1 + (-p1 >> 5)
    filter 2: s += p1 - p2' + (p2' >> 4) + (p1 * -3 >> 6)     (p2' = p2 >> 1)
    filter 3: s += p1 - p2' + (p1 * -13 >> 7) + (p2' * 3 >> 4)
    output = int16(clamp16(s) * 2)

The encoder is greedy per block: every (filter, shift) pair is tried and the
one with the lowest squared error against the target is kept.
"""
import numpy as np

SHIFTS = np.arange(0, 13)


def _predict(filt, p1, p2):
    p2h = p2 >> 1
    if filt == 0:
        return np.zeros_like(p1)
    if filt == 1:
        return (p1 >> 1) + ((-p1) >> 5)
    if filt == 2:
        return p1 - p2h + (p2h >> 4) + ((p1 * -3) >> 6)
    return p1 - p2h + ((p1 * -13) >> 7) + ((p2h * 3) >> 4)


def _finish(s):
    s = np.clip(s, -32768, 32767) * 2
    return ((s + 32768) & 0xFFFF) - 32768  # int16 wrap


def encode(samples, first_filter0=True):
    """int16-range samples (len multiple of 16) -> BRR bytes (no loop/end flags)."""
    x = np.asarray(samples, dtype=np.int64)
    if len(x) % 16:
        raise ValueError("sample count must be a multiple of 16")
    out = bytearray()
    p1 = p2 = 0
    # Candidates: every (filter, shift) pair, evaluated in parallel.
    filts = np.repeat(np.arange(4), len(SHIFTS))
    shifts = np.tile(SHIFTS, 4)
    for b in range(len(x) // 16):
        blk = x[b * 16:(b + 1) * 16]
        allowed = np.ones(len(filts), bool)
        if b == 0 and first_filter0:
            allowed = filts == 0
        c1 = np.full(len(filts), p1, dtype=np.int64)
        c2 = np.full(len(filts), p2, dtype=np.int64)
        err = np.zeros(len(filts))
        nibs = np.zeros((len(filts), 16), dtype=np.int64)
        for i in range(16):
            pred = np.zeros(len(filts), dtype=np.int64)
            for f in range(1, 4):
                m = filts == f
                pred[m] = _predict(f, c1[m], c2[m])
            # want (n << shift) >> 1 ~= x/2 - pred  ->  n ~= (x - 2 pred) / 2^shift
            n = np.rint((blk[i] - 2 * pred) / (1 << shifts)).astype(np.int64)
            n = np.clip(n, -8, 7)
            best_v = None
            best_n = n
            for dn in (0, -1, 1):
                nn = np.clip(n + dn, -8, 7)
                v = _finish(((nn << shifts) >> 1) + pred)
                e = (v - blk[i]).astype(np.float64) ** 2
                if best_v is None:
                    best_v, best_e, best_n = v, e, nn
                else:
                    better = e < best_e
                    best_v = np.where(better, v, best_v)
                    best_e = np.where(better, e, best_e)
                    best_n = np.where(better, nn, best_n)
            err += best_e
            nibs[:, i] = best_n
            c2, c1 = c1, best_v
        err[~allowed] = np.inf
        k = int(np.argmin(err))
        out.append(int(shifts[k]) << 4 | int(filts[k]) << 2)
        nb = nibs[k] & 0xF
        out.extend(int(nb[j] << 4 | nb[j + 1]) for j in range(0, 16, 2))
        p1, p2 = int(c1[k]), int(c2[k])
    return bytes(out)


def decode(data):
    out = []
    p1 = p2 = 0
    for b in range(0, len(data), 9):
        hdr = data[b]
        shift, filt = hdr >> 4, hdr >> 2 & 3
        for j in range(16):
            byte = data[b + 1 + j // 2]
            nib = byte >> 4 if j % 2 == 0 else byte & 0xF
            nib = nib - 16 if nib >= 8 else nib
            s = (nib << shift) >> 1 if shift <= 12 else (-2048 if nib < 0 else 0)
            s += int(_predict(filt, np.int64(p1), np.int64(p2)))
            v = int(_finish(np.int64(s)))
            p2, p1 = p1, v
            out.append(v)
    return np.array(out, dtype=np.int64)
