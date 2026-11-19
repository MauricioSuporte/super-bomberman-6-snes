"""Super Bomberman 1's 1-1 music as a Hudson (SB5 driver) song.

assets/sound/sb1_w1_song.txt (tools/sb1_song.py, from the S-DSP writes of SB1's own driver) lists the
song's notes on its musical grid (24 units per row, the 16th note): start, length until the release,
sample, S-DSP pitch, volumes L/R and SB1's voice. The build turns them into a Hudson song and uploads
SB1's own samples (assets/sound/sb1_stage_w1.bin) with SB1's ADSR and release GAIN:

  * one track per musical line (SB1 deals its notes to voices 3-7 as they come; here the notes of a sample
    group, simultaneous ones split by pitch) on channels 2-7 (CHANNELS: the sparsest line on 2, where
    SB5's stage SFX cut in); a note keeps its length up to the release (Hudson's key-off writes the
    instrument's release GAIN, as SB1 does), then rests; intro, loop point (EB) at the loop row, jump back
    (EC) at the end;
  * pitch: per sample a tuning multiplier (entry $FE00 + 4 * dir) that puts SB1's pitches on Hudson's
    semitones; volume: the Hudson volume / pan pair whose S-DSP VOL L/R is closest to SB1's;
  * bars (16 rows) used more than once by any line become subroutines (DF addr ... FF; they set their
    own instrument / octave / volume / pan), a bar repeated in a row a DD n ... DE loop;
  * tempo: op D1 with Hudson's tick (4 ms * 256 / $38 per unit, $38 from the tempo byte) = row / 24.

It replaces SB5's ZONE1 song (set $2C = its sequence, song 5 = its samples) on the STAGES, uploaded with
it while the stage loads (asm/title_music.asm sb1m_song, hooked at the song upload $C0:0E9C): music id 6
then only sends command 1, as in SB5, with no upload once the stage runs. Commands 2-4 of SB5's song
(the stage start jingle and the others) are kept: their data stays where SB5 has it ($3E00-$4240), with
their samples (directory entries $02, $03, $0B-$0D) moved where there is room. ARAM: the song table at
$3000 (command 1 -> SB1's song, 2-4 -> SB5's), SB1's samples from $8000, the rest (SB1's header, tracks
and subroutines, the jingles' samples) in the free parts of $300C-$43FF and $8000-$F4FF: the song and
the jingles use an echo delay of 1 (buffer $F500-$FCFF; none of them has an echo voice).
"""
import math
import os
import struct

from .. import brr
from ..rombuild import BuildError
from ..romlib import off
from . import title_music as tm

# World 1 stages that play SB1 songs: (stage id, song name: assets/sound/sb1_<name>_song.txt, SB1's sound RAM
# assets/sound/sb1_stage_<name>.bin)
STAGES = [(0x0D, "w1"), (0x11, "w2")]
SB5_SET, SB5_SONG = 0x2C, 0x05       # SB5's ZONE1 song: its sequence (set), its samples (song)
# SB5 directory entries the jingles name but never play: only the start jingle's percussion records (no key-on
# of it in Mesen, the jingle keeps its percussion off) -> a silent block (2187 bytes saved)
SILENT_DIRS = (0x02,)
# kept when the song leaves room (else an SB1 sample alike plays them): the other jingles' percussion (3 KB)
OPTIONAL_DIRS = (0x03,)


def _zcr(data):
    x = brr.decode(data)
    return sum(1 for a, b in zip(x, x[1:]) if (a < 0) != (b < 0)) / max(1, len(x) - 1)
SEQ_BASE, SEQ_END = 0x3000, 0x4400
SAMPLE_BASE = 0x8000
ECHO_DELAY = 1                       # EDL of the song and of SB5's jingles: echo buffer $F500-$FCFF
ECHO_BASE = 0xFD00 - 0x800 * ECHO_DELAY
SB1_DIR = 0x2300                     # SB1's sample directory in its sound RAM
IMAGE_BASE = 0x0800                  # assets/sound/sb1_stage_w1.bin = SB1's sound RAM from $0800
UNITS_PER_ROW = 24                   # sb1_<name>_song.txt (in ARAM 24, 16 or 12: see build)
ROWS_PER_BAR = 16

# Hudson driver, measured in Mesen (docs/ROM_MAP.md "Hudson songs"):
TEMPO_TABLE = [0, 2, 4, 5, 7, 9, 11, 13, 14, 16, 18, 20, 22, 23, 25, 27, 29, 31, 33, 34, 36, 38, 40, 42, 43,
               45]                   # ARAM $12AD: op D1 t -> $38 = t - TABLE[t / 10] - (t % 10 >= 5)
TIMER_MS = 4.0                       # the driver adds $38 / 256 ticks every 4 ms
BASE_PITCH, BASE_MULT, TUNING_TAIL = 0x0430, 0x040C, bytes([0x00, 0xCE])   # note 24, entry "04 0C 00 CE"
# S-DSP VOL of volume v (op D9 0-$50, more = $50) with the pan full on that side; pan p (op DA 0-30):
# L = VOL[v] * PAN[30 - p] / 127, R = VOL[v] * PAN[p] / 127 (rounded down)
VOL = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 6, 6, 7, 7, 8, 8, 9,
       9, 10, 10, 11, 12, 13, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 25, 26, 28, 29, 31, 33, 35, 37, 39, 42,
       44, 47, 50, 53, 56, 60, 63, 67, 71, 75, 80, 85, 90, 95, 101, 107, 113, 120, 127, 127]
PAN = [0x00, 0x07, 0x0D, 0x14, 0x1A, 0x21, 0x27, 0x2E, 0x34, 0x3A, 0x40, 0x45, 0x4B, 0x50, 0x55, 0x5A, 0x5E,
       0x63, 0x67, 0x6B, 0x6E, 0x71, 0x74, 0x77, 0x79, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F, 0x7F]
# sequence ops and their operand bytes (driver table $17D9)
OPS = {0xD0: 0, 0xD1: 1, 0xD2: 1, 0xD3: 0, 0xD4: 0, 0xD5: 1, 0xD6: 1, 0xD7: 0, 0xD8: 0, 0xD9: 1, 0xDA: 1, 0xDB: 1,
       0xDC: 1, 0xDD: 1, 0xDE: 0, 0xDF: 2, 0xE0: 2, 0xE1: 1, 0xE2: 3, 0xE3: 1, 0xE4: 2, 0xE5: 3, 0xE6: 0, 0xE7: 1,
       0xE8: 1, 0xE9: 3, 0xEA: 0, 0xEB: 0, 0xEC: 0, 0xED: 0, 0xEE: 0, 0xEF: 2, 0xF0: 1, 0xF1: 2, 0xF2: 1, 0xF3: 1,
       0xFE: 1, 0xFF: 0}


def tempo_38(t):
    t = max(t, 10)
    return t - TEMPO_TABLE[t // 10] - (1 if t % 10 >= 5 else 0)


def tempo_for(unit_ms):
    want = 1024.0 / unit_ms          # $38
    best = min(range(10, 256), key=lambda t: abs(tempo_38(t) - want))
    return best, TIMER_MS * 256 / tempo_38(best)


def pitch_of(note, mult):
    return BASE_PITCH * 2 ** ((note - 24) / 12) * mult / BASE_MULT


def volume_pan(vl, vr):
    """Hudson (volume, pan) whose S-DSP VOL L/R is closest to (vl, vr)."""
    best = None
    for v in range(0x51):
        for p in range(31):
            l, r = VOL[v] * PAN[30 - p] // 127, VOL[v] * PAN[p] // 127
            e = (l - vl) ** 2 + (r - vr) ** 2
            if best is None or e < best[0]:
                best = (e, v, p)
    return best[1], best[2]


# ---------------------------------------------------------------------------------------------------------
# Input

def read_song(path):
    notes, meta = [], {"inst": {}}
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        p = line.split()
        if p[0] in ("loop", "end"):
            meta[p[0]] = int(p[1])
        elif p[0] == "row":
            meta["row"] = float(p[1])
        elif p[0] == "inst":
            meta["inst"][int(p[1], 16)] = tuple(int(x, 16) for x in p[2:5])
        else:
            t, d, s, pitch, vl, vr, v = p
            notes.append(dict(t=int(t), d=int(d), srcn=int(s, 16), pitch=int(pitch, 16), vl=int(vl, 16),
                              vr=int(vr, 16), voice=int(v)))
    return notes, meta


def sb1_samples(image, srcns):
    """{srcn: (BRR bytes, loop offset)} from SB1's sound RAM image."""
    a = bytearray(0x10000)
    a[IMAGE_BASE:IMAGE_BASE + len(image)] = image
    out = {}
    for s in srcns:
        start, loop = struct.unpack_from("<HH", a, SB1_DIR + 4 * s)
        p = start
        while not a[p] & 1:
            p += 9
        out[s] = (bytes(a[start:p + 9]), loop - start)
    return out


# ---------------------------------------------------------------------------------------------------------
# SB5's ZONE1 song (kept: its commands 2.., the jingles)

def _w(rom, a):
    return struct.unpack_from("<H", rom, off(a))[0]


def _long(rom, a):
    return int.from_bytes(rom[off(a):off(a) + 3], "little")


def sb5_zone1(rom):
    """-> (ARAM image of set $2C + song 5, {directory entry: (address, bytes)} of song 5's samples)."""
    img = bytearray(0x10000)
    for dest, data in tm._blocks(rom, _long(rom, tm.SET_TABLE + 3 * SB5_SET)):
        img[dest:dest + len(data)] = data
    rec = 0xDA0000 | _w(rom, tm.SONG_TABLE + 2 * SB5_SONG)
    for dest, data in tm._blocks(rom, 0xDA0000 | _w(rom, rec)):         # its directory / tuning entries
        img[dest:dest + len(data)] = data
    a, q, samples = _w(rom, rec + 2), rec + 4, {}
    while rom[off(q)] != 0xFF:
        i = rom[off(q)]
        n = _w(rom, tm.SAMPLE_SIZES + 2 * i)
        src = _long(rom, tm.SAMPLE_PTRS + 3 * i)
        img[a:a + n] = rom[off(src):off(src) + n]
        samples[len(samples)] = (a, n)
        a, q = a + n, q + 1
    for d, (a, n) in samples.items():
        if struct.unpack_from("<H", img, 0xFD00 + 4 * d)[0] != a:
            raise BuildError(f"SB1 music: SB5 song {SB5_SONG} directory entry {d:02X} is not its sample {d}")
    return img, samples


def song_heads(img):
    table = struct.unpack_from("<H", img, SEQ_BASE)[0]
    heads = []
    while struct.unpack_from("<H", img, table + 2 * len(heads))[0]:
        heads.append(struct.unpack_from("<H", img, table + 2 * len(heads))[0])
    return heads


def sb5_jingles(img):
    """SB5's commands 2..: (the ARAM range of their headers, tracks and data, the directory entries
    their instruments / percussion use, addresses of their echo delay bytes)."""
    lo, hi, dirs, edl = 0x10000, 0, set(), []
    for h in song_heads(img)[1:]:
        p, tracks = h, []
        while img[p]:
            op = img[p]
            if op == 1:
                m = img[p + 1]
                p += 2
                for ch in range(8):
                    if m >> ch & 1:
                        tracks.append(struct.unpack_from("<H", img, p)[0])
                        p += 2
            elif op in (2, 8):
                p += 2
            elif op in (3, 4):                     # instruments / percussion: n records, byte 0 = directory
                n = img[p + 1]
                dirs |= {img[p + 2 + 4 * i] for i in range(n)}
                p += 2 + 4 * n
            elif op in (5, 6, 9):                  # n pointers to data
                n = img[p + 1]
                for i in range(n):
                    x = struct.unpack_from("<H", img, p + 2 + 2 * i)[0]
                    lo, hi = min(lo, x), max(hi, x + 1)
                p += 2 + 2 * n
            elif op == 7:
                if img[p + 1] == 0:
                    edl.append(p + 4)
                    p += 8
                else:
                    p += 2
            else:
                raise BuildError(f"SB1 music: SB5 song header op {op:02X} at ${p:04X}")
        lo, hi = min(lo, h), max(hi, p + 1)
        todo, seen = list(tracks), set()
        while todo:
            t = todo.pop()
            if t in seen:
                continue
            seen.add(t)
            i = t
            while True:
                b = img[i]
                if b >= 0xD0:
                    if b not in OPS:
                        raise BuildError(f"SB1 music: SB5 song op {b:02X} at ${i:04X}")
                    if b in (0xDF, 0xE0):
                        todo.append(struct.unpack_from("<H", img, i + 1)[0])
                    i += 1 + OPS[b]
                    if b in (0xFF, 0xEC, 0xE0):
                        break
                else:
                    i += 2 if b & 7 == 0 else 1
            lo, hi = min(lo, t), max(hi, i)
    return (lo, hi), sorted(dirs), edl


# ---------------------------------------------------------------------------------------------------------
# Hudson sequence

def header(tracks, instruments):
    """Hudson V2 song header (tracks: {channel: address})."""
    mask, ptrs = 0, b""
    for ch in sorted(tracks):
        mask |= 1 << ch
        ptrs += struct.pack("<H", tracks[ch])
    h = bytes([0x01, mask]) + ptrs
    h += bytes([0x02, 0x00])                       # timebase: lengths as written
    h += bytes([0x08, 0x00])                       # no velocity byte
    h += bytes([0x03, len(instruments)]) + b"".join(instruments)
    h += bytes([0x07, 0x00, 0x00, 0x00, ECHO_DELAY, 0x00, 0x00, 0x00])   # echo: silent, no voice
    return h + bytes([0x00])


def _lengths(n):
    while n > 0:
        k = min(n, 255)
        yield k
        n -= k


DRUMS = (3, 4, 5)                    # SB1's drum samples: one line
CHANNELS = (7, 6, 5, 4, 3, 2)        # busiest line first; 2 (shared with SB5's stage SFX) gets the sparsest


def lines_of(notes):
    """Musical lines: per sample (the drums together), simultaneous notes split by pitch, highest first."""
    srcns = sorted({n["srcn"] for n in notes})
    groups = [tuple(x for x in srcns if x in DRUMS)] + [(x,) for x in srcns if x not in DRUMS]
    out = {}
    for g in groups:
        ends = []
        for n in sorted((n for n in notes if n["srcn"] in g), key=lambda n: (n["t"], -n["pitch"])):
            for i, e in enumerate(ends):
                if e <= n["t"]:
                    ends[i] = n["t"] + n["d"]
                    break
            else:
                i = len(ends)
                ends.append(n["t"] + n["d"])
            out.setdefault((g, i), []).append(n)
    return out


def channels_of(lines):
    """Lines -> {channel: notes}: busiest lines first, a line joins a channel whose notes it never overlaps."""
    chans = []
    for ln in sorted(lines, key=lambda ln: (-len(lines[ln]), ln)):
        ns = lines[ln]
        for c in chans:
            if all(n["t"] + n["d"] <= m["t"] or m["t"] + m["d"] <= n["t"] for n in ns for m in c):
                c.extend(ns)
                break
        else:
            chans.append(list(ns))
    if len(chans) > len(CHANNELS):
        raise BuildError(f"SB1 music: {len(chans)} lines that overlap, {len(CHANNELS)} channels")
    chans.sort(key=lambda c: -len(c))
    return {CHANNELS[i]: sorted(c, key=lambda n: n["t"]) for i, c in enumerate(chans)}


def bar_bytes(key, st, bar):
    """key = (overhang in, ((t, d, inst, octave, key, vol, pan), ...)); st = state before (None = unknown)
    -> (bytes, state after)."""
    over, notes = key
    st = list(st) if st else [None] * 4
    out = bytearray()
    cur = over
    for t, d, ins, octave, k, v, p in notes:
        if t > cur:
            for x in _lengths(t - cur):
                out += bytes([0x00, x])
        for i, (val, op) in enumerate(((ins, 0xD6), (octave, 0xD2), (v, 0xD9), (p, 0xDA))):
            if st[i] != val:
                out += bytes([op, val])
                st[i] = val
        parts = list(_lengths(d))
        for j, x in enumerate(parts):
            out += bytes([k << 4 | (0x08 if j < len(parts) - 1 else 0), x])
        cur = t + d
    if cur < bar:
        for x in _lengths(bar - cur):
            out += bytes([0x00, x])
    return bytes(out), tuple(st)


def line_bars(notes, nbars, inst_of, tune, volpan, bar):
    """Bar keys of one line (overhang in, notes relative to the bar)."""
    by = {}
    for n in notes:
        by.setdefault(n["t"] // bar, []).append(n)
    keys, over = [], 0
    for b in range(nbars):
        ns = []
        end = b * bar + over
        for n in sorted(by.get(b, []), key=lambda n: n["t"]):
            note = tune[n["srcn"]][1][n["pitch"]]
            v, p = volpan[(n["vl"], n["vr"])]
            ns.append((n["t"] - b * bar, n["d"], inst_of[n["srcn"]], note // 12, note % 12 + 1, v, p))
            end = max(end, n["t"] + n["d"])
        keys.append((over, tuple(ns)))
        over = max(0, end - (b + 1) * bar)
    return keys


def assemble(lines_keys, loop_bar, tempo, bar):
    """lines_keys: {channel: [bar key]} -> (tracks(sub addresses) -> {channel: bytes}, {channel: size},
    [subroutine bytes]). A bar repeated in a row becomes a DD n .. DE loop (an item); a bar used more than
    once (any channel) a subroutine; then stretches of items found more than once become subroutines
    (DF addr .. FF) that may call the bar ones (the driver keeps a 16-byte call / loop stack per channel:
    at most DF, DD, DF here), chosen greedily by the bytes they save."""
    seqs = {}
    for ch, keys in lines_keys.items():
        items, b = [], 0
        while b < len(keys):
            r = 1
            while b + r < len(keys) and keys[b + r] == keys[b] and not (b < loop_bar <= b + r):
                r += 1
            items.append((keys[b], r, b))
            b += r
        seqs[ch] = items

    uses = {}
    for items in seqs.values():
        for it in items:
            uses[it[0]] = uses.get(it[0], 0) + 1
    body = {k: bar_bytes(k, None, bar) for k in uses}
    single = [k for k, n in uses.items() if n >= 2 and len(body[k][0]) > 4]
    single_index = {k: i for i, k in enumerate(single)}
    addr = {}                                    # subroutine index -> ARAM address (set by tracks())

    def item_bytes(it, st):
        k, r = it[0], it[1]
        if k in single_index:
            a = addr.get(single_index[k], 0)
            inner, st = bytes([0xDF, a & 0xFF, a >> 8]), body[k][1]
        else:
            inner, st = bar_bytes(k, None if r > 1 else st, bar)
        if r > 1:
            return bytes([0xDD, r]) + inner + bytes([0xDE]), st
        return inner, st

    def seg_bytes(seg):
        out, st = bytearray(), None
        for it in seg:
            data, st = item_bytes(it, st)
            out += data
        return bytes(out) + bytes([0xFF]), st

    subs = [((k, 1),) for k in single]          # segments of (key, r); the bar subroutines first
    MAXLEN = 16
    while True:
        occ = {}
        for ch, items in seqs.items():
            for i in range(len(items)):
                for n in range(2, MAXLEN + 1):
                    seg = items[i:i + n]
                    if len(seg) < n or any(it[0] == "call" for it in seg):
                        break
                    if any(it[2] == loop_bar for it in seg[1:]):
                        break
                    occ.setdefault(tuple((it[0], it[1]) for it in seg), []).append((ch, i))
        best = None
        for seg, where in occ.items():
            used, last = 0, {}
            for ch, i in where:                 # non-overlapping, left to right
                if i >= last.get(ch, -1):
                    used += 1
                    last[ch] = i + len(seg)
            if used < 2:
                continue
            size = len(seg_bytes(seg)[0])
            gain = used * (size - 1) - size - 3 * used
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, seg)
        if best is None:
            break
        seg = best[1]
        idx = len(subs)
        subs.append(seg)
        n = len(seg)
        for ch, items in seqs.items():
            out, i = [], 0
            while i < len(items):
                if tuple((it[0], it[1]) for it in items[i:i + n]) == seg and \
                        all(it[0] != "call" for it in items[i:i + n]):
                    out.append(("call", idx, items[i][2]))
                    i += n
                else:
                    out.append(items[i])
                    i += 1
            seqs[ch] = out

    def sub_body(i):
        if i < len(single):
            return body[single[i]][0] + bytes([0xFF]), body[single[i]][1]
        return seg_bytes(subs[i])

    def tracks(sub_addr):
        addr.update(enumerate(sub_addr))
        out = {}
        for ch, items in sorted(seqs.items()):
            t = bytearray()
            if ch == max(seqs):
                t += bytes([0xD1, tempo])
            # full-length notes, no transpose / detune; FE 04: percussion mode off, FE 01: voice out of the
            # $8D mask (both are channel state the previous song may leave on)
            t += bytes([0xD5, 0x08, 0xE7, 0x00, 0xE1, 0x00, 0xFE, 0x04, 0xFE, 0x01])
            st = None
            for it in items:
                if it[2] == loop_bar:
                    t.append(0xEB)
                if it[0] == "call":
                    a = sub_addr[it[1]]
                    t += bytes([0xDF, a & 0xFF, a >> 8])
                    st = sub_body(it[1])[1]
                else:
                    data, st = item_bytes(it, st)
                    t += data
            t.append(0xEC)
            out[ch] = bytes(t)
        return out

    sizes = {ch: len(t) for ch, t in tracks([0] * len(subs)).items()}
    sub_sizes = [len(sub_body(i)[0]) for i in range(len(subs))]

    def build_all(sub_addr):
        """-> ({channel: bytes}, [subroutine bytes]) with the subroutines at sub_addr."""
        tr = tracks(sub_addr)
        return tr, [sub_body(i)[0] for i in range(len(subs))]

    return build_all, sizes, sub_sizes


class Space:
    """Free ARAM ranges; alloc() takes the smallest range the block fits in."""

    def __init__(self, ranges):
        self.ranges = [list(r) for r in ranges if r[1] > r[0]]

    def alloc(self, size, what):
        fit = [r for r in self.ranges if r[1] - r[0] >= size]
        if not fit:
            raise BuildError(f"SB1 music: no ARAM left for {what} ({size} bytes, {self.free()} free)")
        r = min(fit, key=lambda r: r[1] - r[0])
        r[0] += size
        return r[0] - size

    def free(self):
        return sum(e - s for s, e in self.ranges)


# ---------------------------------------------------------------------------------------------------------

def build(image, path, rom):
    notes, meta = read_song(path)
    loop, end, row = meta["loop"], meta["end"], meta["row"]
    srcns = sorted({n["srcn"] for n in notes})
    zimg, zsamples = sb5_zone1(rom)
    heads = song_heads(zimg)
    (jlo, jhi), jdirs, jedl = sb5_jingles(zimg)
    table_end = SEQ_BASE + 2 + 2 * (len(heads) + 1)
    if jlo < table_end or jhi > SEQ_END:
        raise BuildError(f"SB1 music: SB5's jingles at ${jlo:04X}-${jhi:04X} leave no room for the table")
    free_dirs = [d for d in range(0x12) if d not in jdirs]
    if len(srcns) > len(free_dirs):
        raise BuildError("SB1 music: too many samples")
    dir_of = {s: free_dirs[k] for k, s in enumerate(srcns)}
    dirs, tunings = bytearray(0x48), bytearray(0x48)
    # SB1's samples from $8000
    smp = sb1_samples(image, srcns)
    blob = bytearray()
    for s in srcns:
        data, loop_off = smp[s]
        a = SAMPLE_BASE + len(blob)
        struct.pack_into("<HH", dirs, 4 * dir_of[s], a, a + loop_off)
        blob += data
    blocks = [(SAMPLE_BASE, bytes(blob))]
    space = Space([(table_end, jlo), (jhi, SEQ_END), (SAMPLE_BASE + len(blob), ECHO_BASE)])
    # SB5's jingles where SB5 has them (echo delay 1), their samples wherever they fit
    jimg = bytearray(zimg[jlo:jhi])
    for p in jedl:
        jimg[p - jlo] = ECHO_DELAY
    blocks.append((jlo, bytes(jimg)))
    jbytes, silent, aliased = 0, None, {}

    def put_sb5(d):
        start, n = zsamples[d]
        loop_off = struct.unpack_from("<H", zimg, 0xFD00 + 4 * d + 2)[0] - start
        a = space.alloc(n, f"SB5 sample {d:02X}")
        blocks.append((a, bytes(zimg[start:start + n])))
        struct.pack_into("<HH", dirs, 4 * d, a, a + loop_off)
        return n

    for d in jdirs:
        tunings[4 * d:4 * d + 4] = zimg[0xFE00 + 4 * d:0xFE04 + 4 * d]
        if d in OPTIONAL_DIRS:
            continue
        if d in SILENT_DIRS:
            if silent is None:
                silent = space.alloc(9, "a silent block")
                blocks.append((silent, bytes([0x03]) + bytes(8)))
            struct.pack_into("<HH", dirs, 4 * d, silent, silent)
            continue
        jbytes += put_sb5(d)
    # tuning: multiplier per sample, note per pitch
    tune, worst = {}, 0.0
    for s in srcns:
        ps = sorted({n["pitch"] for n in notes if n["srcn"] == s})
        semis = [12 * math.log2(p / BASE_PITCH) for p in ps]
        c = math.atan2(sum(math.sin(2 * math.pi * x) for x in semis), sum(math.cos(2 * math.pi * x) for x in semis))
        c /= 2 * math.pi
        mult = round(BASE_MULT * 2 ** (c / 12))
        notemap = {}
        for p, x in zip(ps, semis):
            n = 24 + round(x - c)
            if not 0 <= n < 96:
                raise BuildError(f"SB1 music: sample {s:02X} pitch {p:04X} out of Hudson's range")
            notemap[p] = n
            worst = max(worst, abs(1200 * math.log2(pitch_of(n, mult) / p)))
        tune[s] = (mult, notemap)
        tunings[4 * dir_of[s]:4 * dir_of[s] + 4] = struct.pack(">H", mult) + TUNING_TAIL
    # instruments: one per sample (its directory entry, SB1's ADSR and release GAIN)
    inst_of, instruments = {}, []
    for k, s in enumerate(srcns):
        a1, a2, gain = meta["inst"][s]
        if not gain & 0x80:
            # Hudson reads an instrument with a release GAIN under $80 another way (byte 3 must have bit 7):
            # SB1's 00 (direct, volume 0) becomes $9F, the fastest linear decrease (~2 ms)
            gain = 0x9F
        instruments.append(bytes([dir_of[s], a1, a2, gain]))
        inst_of[s] = k
    volpan = {(n["vl"], n["vr"]): volume_pan(n["vl"], n["vr"]) for n in notes}
    # units a row: 24 (as written), 16 or 12, whichever has the tempo closest to SB1's (the driver's tempo
    # byte is coarse, and too fast tempos need fewer units)
    best = None
    for units in (24, 16, 12):
        if any(n["t"] * units % UNITS_PER_ROW for n in notes):
            continue
        tempo, unit_ms = tempo_for(row / units)
        err = abs(unit_ms * units / row - 1)
        if best is None or err < best[0] - 1e-4:
            best = (err, units, tempo, unit_ms)
    err, units, tempo, unit_ms = best
    if err > 0.01:
        raise BuildError(f"SB1 music: no tempo within 1 % of SB1's ({err * 100:.1f} %)")
    if units != UNITS_PER_ROW:
        for n in notes:
            n["t"] = n["t"] * units // UNITS_PER_ROW
            n["d"] = max(1, round(n["d"] * units / UNITS_PER_ROW))
        loop, end = loop * units // UNITS_PER_ROW, end * units // UNITS_PER_ROW
        if any(n["t"] + n["d"] > m["t"] for ns in lines_of(notes).values() for n, m in zip(ns, ns[1:])):
            raise BuildError(f"SB1 music: notes overlap at {units} units a row")
    bar = ROWS_PER_BAR * units
    if loop % bar or end % bar:
        raise BuildError("SB1 music: loop / end not on a bar")
    chans = channels_of(lines_of(notes))
    keys = {ch: line_bars(ns, end // bar, inst_of, tune, volpan, bar) for ch, ns in chans.items()}
    build_all, sizes, sub_sizes = assemble(keys, loop // bar, tempo, bar)
    hl = len(header({ch: 0 for ch in keys}, instruments))
    head = space.alloc(hl + sum(sizes.values()), "the song's header and tracks")
    taddr, a = {}, head + hl
    for ch in sorted(sizes):
        taddr[ch] = a
        a += sizes[ch]
    sub_addr = [0] * len(sub_sizes)
    for i in sorted(range(len(sub_sizes)), key=lambda i: -sub_sizes[i]):
        sub_addr[i] = space.alloc(sub_sizes[i], "a subroutine")
    tr, subs = build_all(sub_addr)
    for a, data in zip(sub_addr, subs):
        blocks.append((a, data))
    # SB5 samples kept only when there is room; else the SB1 sample of the song that sounds most alike
    # (zero-crossing rate) plays in their place
    for d in OPTIONAL_DIRS:
        if d not in jdirs:
            continue
        try:
            jbytes += put_sb5(d)
        except BuildError:
            start, n = zsamples[d]
            z = _zcr(bytes(zimg[start:start + n]))
            s = min(srcns, key=lambda s: abs(_zcr(smp[s][0]) - z))
            dirs[4 * d:4 * d + 4] = dirs[4 * dir_of[s]:4 * dir_of[s] + 4]
            aliased[d] = s
    blocks.append((head, header(taddr, instruments) + b"".join(tr[ch] for ch in sorted(tr))))
    # song table: command 1 = SB1's song, 2.. = SB5's (their headers where SB5 has them)
    blocks.append((SEQ_BASE, struct.pack(f"<{len(heads) + 2}H", SEQ_BASE + 2, head, *heads[1:], 0)))
    blocks += [(0xFD00, bytes(dirs)), (0xFE00, bytes(tunings))]
    seq = hl + sum(sizes.values()) + sum(map(len, subs))
    info = dict(seq=seq, samples=len(blob), notes=len(notes), tempo=tempo, unit_ms=unit_ms, row_ms=row,
                cents=worst, channels=sorted(keys), subs=len(subs), units=units, jingles=(jlo, jhi), jingle_dirs=jdirs,
                jingle_samples=jbytes, aram_left=space.free(), head=head, aliased=aliased)
    return tm._list(blocks, bytes([0x00, 0x08])), info


def apply(rb, sound_dir):
    """-> (asm defines, [info per stage]). SB1M_TABLE: per stage [stage id, upload list (long)], then $FF."""
    table, infos = bytearray(), []
    for stage, name in STAGES:
        image = open(os.path.join(sound_dir, f"sb1_stage_{name}.bin"), "rb").read()
        lst, info = build(image, os.path.join(sound_dir, f"sb1_{name}_song.txt"), rb.d)
        a = rb.alloc(["stream_ed", "stream_ec", "free_c8_sheets", "free_c7_sheets"], lst,
                     f"SB1 music of stage ${stage:02X} ({name}): Hudson upload list (sequence, samples)")
        if (a & 0xFFFF) + len(lst) > 0x10000:
            raise BuildError("SB1 music: an upload list crosses a bank")
        table += bytes([stage]) + a.to_bytes(3, "little")
        infos.append(dict(info, stage=stage, name=name, list=len(lst)))
    table.append(0xFF)
    t = rb.alloc("bulk", bytes(table), "SB1 music: stage -> upload list")
    defs = {"SB1M_SB5SONG": f"${SB5_SONG:02X}", "SB1M_TABLE": f"${t:06X}"}
    return defs, infos
