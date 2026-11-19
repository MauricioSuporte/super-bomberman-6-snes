"""Super Bomberman 1's 1-1 music as a Hudson (SB5 driver) song.

assets/sound/sb1_w1_song.txt (tools/sb1_song.py, from the S-DSP writes of SB1's own driver) lists the
song's notes on its musical grid (24 units per row, the 16th note): start, length until the release,
sample, S-DSP pitch, volumes L/R and SB1's voice. The build turns them into a Hudson song and uploads
SB1's own samples (assets/sound/sb1_stage_w1.bin) with SB1's ADSR and release GAIN:

  * one track per musical line (SB1 deals its notes to voices 3-7 as they come; here the notes of a sample
    group, simultaneous ones split by pitch) on channels 2-7 (CHANNELS: the sparsest lines on 2-3, where
    SB5's stage SFX cut in); a note keeps its length up to the release (Hudson's key-off writes the
    instrument's release GAIN, as SB1 does), then rests; intro, loop point (EB) at the loop row, jump back
    (EC) at the end;
  * pitch: per sample a tuning multiplier (entry $FE00 + 4 * dir) that puts SB1's pitches on Hudson's
    semitones; volume: the Hudson volume / pan pair whose S-DSP VOL L/R is closest to SB1's;
  * bars (16 rows) used more than once by any line become subroutines (DF addr ... FF; they set their
    own instrument / octave / volume / pan), a bar repeated in a row a DD n ... DE loop;
  * tempo: op D1 with Hudson's tick (4 ms * 256 / $38 per unit, $38 from the tempo byte) = row / 24.

ARAM: $3000 the song table (cmd 1 -> header) and the sequence (below the SFX tables at $4400); $8000 up
the samples (below the echo buffer of EDL 4 at $DD00, kept with no echo voice); directory / tuning
entries 0..n-1. asm/title_music.asm (sb1m_play) uploads it instead of SB5's ZONE1 song when stage $0D
asks for music id 6 (after SB5's own start jingle), with the cornered SFX's directory entry looped into
its silent block (game_sfx L_DIR0: the samples cover its part B), and marks set / song as unknown
($03CE / $03CD = $FF) so the next request uploads its own.
"""
import math
import os
import struct

from ..rombuild import BuildError
from . import title_music as tm

STAGE, MUSIC_ID, CMD = 0x0D, 0x06, 0x01
SEQ_BASE, SEQ_END = 0x3000, 0x4400
SAMPLE_BASE, SAMPLE_END = 0x8000, 0xDD00
SB1_DIR = 0x2300                     # SB1's sample directory in its sound RAM
IMAGE_BASE = 0x0800                  # assets/sound/sb1_stage_w1.bin = SB1's sound RAM from $0800
UNITS_PER_ROW = 24

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


def tempo_38(t):
    t = max(t, 10)
    v = t - TEMPO_TABLE[t // 10] - (1 if t % 10 >= 5 else 0)
    return v


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
    h += bytes([0x07, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00])   # echo: silent, EDL 4 ($DD00), no voice
    return h + bytes([0x00])


def _lengths(n):
    while n > 0:
        k = min(n, 255)
        yield k
        n -= k


BAR = 16 * UNITS_PER_ROW
# musical lines (SB1 spreads them over its voices as they come): the samples of each group, the voices of
# the group's simultaneous notes, highest pitch first; Hudson channel of each line (2 / 3 are the ones SB5's
# SFX and game_sfx's cornered sound borrow most: the sparsest lines)
GROUPS = [(2,), (3, 4, 5), (6,), (7,), (0,)]
CHANNELS = {((2,), 0): 7, ((3, 4, 5), 0): 6, ((6,), 0): 5, ((7,), 0): 4, ((7,), 1): 3, ((0,), 0): 2}


def lines_of(notes):
    out = {}
    for g in GROUPS:
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
    if any(n["srcn"] not in sum(GROUPS, ()) for n in notes):
        raise BuildError("SB1 music: a sample in no line group")
    return out


class Writer:
    """Serializes abstract bars: notes (start, length, instrument, octave, key, volume, pan) and rests."""

    def __init__(self):
        self.st = None

    def bar(self, key, st):
        """key = (overhang in, ((t, d, inst, octave, key, vol, pan), ...)); st = state before (None =
        unknown). -> (bytes, state after)."""
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
        if cur < BAR:
            for x in _lengths(BAR - cur):
                out += bytes([0x00, x])
        return bytes(out), tuple(st)


def line_bars(notes, nbars, inst_of, tune, volpan):
    """Bar keys of one line (overhang in, notes relative to the bar)."""
    by = {}
    for n in notes:
        by.setdefault(n["t"] // BAR, []).append(n)
    keys, over = [], 0
    for b in range(nbars):
        ns = []
        end = b * BAR + over
        for n in sorted(by.get(b, []), key=lambda n: n["t"]):
            note = tune[n["srcn"]][1][n["pitch"]]
            v, p = volpan[(n["vl"], n["vr"])]
            ns.append((n["t"] - b * BAR, n["d"], inst_of[n["srcn"]], note // 12, note % 12 + 1, v, p))
            end = max(end, n["t"] + n["d"])
        keys.append((over, tuple(ns)))
        over = max(0, end - (b + 1) * BAR)
    return keys


def assemble(lines_keys, loop_bar, tempo, base):
    """lines_keys: {channel: [bar key]} -> (sequence bytes from `base`, {channel: address}, info).
    Bars used more than once (any line) become subroutines; runs of one bar become DD n .. DE loops."""
    w = Writer()
    uses = {}
    for keys in lines_keys.values():
        b = 0
        while b < len(keys):
            r = 1
            while b + r < len(keys) and keys[b + r] == keys[b] and not (b < loop_bar <= b + r):
                r += 1
            uses[keys[b]] = uses.get(keys[b], 0) + 1
            b += r
    body = {k: w.bar(k, None) for k in uses}
    subs = [k for k, n in uses.items() if n >= 2 and len(body[k][0]) > 4]
    sub_index = {k: i for i, k in enumerate(subs)}
    # layout: tracks first (sizes need the subroutine addresses: two passes)
    def tracks(sub_addr):
        out = {}
        for ch, keys in sorted(lines_keys.items()):
            t = bytearray()
            if ch == max(lines_keys):
                t += bytes([0xD1, tempo])
            # full-length notes, no transpose / detune; FE 04: percussion mode off, FE 01: voice out of the
            # $8D mask (both are channel state the previous song may leave on)
            t += bytes([0xD5, 0x08, 0xE7, 0x00, 0xE1, 0x00, 0xFE, 0x04, 0xFE, 0x01])
            st = None
            b = 0
            while b < len(keys):
                if b == loop_bar:
                    t.append(0xEB)
                r = 1
                while b + r < len(keys) and keys[b + r] == keys[b] and not (b < loop_bar <= b + r):
                    r += 1
                k = keys[b]
                if r > 1:
                    t += bytes([0xDD, r])
                if k in sub_index:
                    a = sub_addr[sub_index[k]]
                    t += bytes([0xDF, a & 0xFF, a >> 8])
                    st = body[k][1]
                elif r > 1:
                    t += body[k][0]
                    st = body[k][1]
                else:
                    data, st = w.bar(k, st)
                    t += data
                if r > 1:
                    t.append(0xDE)
                b += r
            t.append(0xEC)
            out[ch] = bytes(t)
        return out

    sub_bytes = [body[k][0] + bytes([0xFF]) for k in subs]
    tr = tracks([0] * len(subs))
    addr = base
    taddr = {}
    for ch in sorted(tr):
        taddr[ch] = addr
        addr += len(tr[ch])
    sub_addr = []
    for sb in sub_bytes:
        sub_addr.append(addr)
        addr += len(sb)
    tr = tracks(sub_addr)
    data = b"".join(tr[ch] for ch in sorted(tr)) + b"".join(sub_bytes)
    return data, taddr, dict(subs=len(subs), sub_bytes=sum(map(len, sub_bytes)))


def build(image, path):
    notes, meta = read_song(path)
    loop, end, row = meta["loop"], meta["end"], meta["row"]
    srcns = sorted({n["srcn"] for n in notes})
    if len(srcns) > 16:
        raise BuildError("SB1 music: too many samples")
    # samples: directory entries 0.. in srcn order, packed from $8000
    smp = sb1_samples(image, srcns)
    blob, dirs, dir_of = bytearray(), bytearray(), {}
    for k, s in enumerate(srcns):
        data, loop_off = smp[s]
        a = SAMPLE_BASE + len(blob)
        dirs += struct.pack("<HH", a, a + loop_off)
        blob += data
        dir_of[s] = k
    if SAMPLE_BASE + len(blob) > SAMPLE_END:
        raise BuildError(f"SB1 music: samples ({len(blob)} bytes) overflow ${SAMPLE_END:04X}")
    # tuning: multiplier per sample, note per pitch
    tune, tunings, worst = {}, bytearray(), 0.0
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
        tunings += struct.pack(">H", mult) + TUNING_TAIL
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
    tempo, unit_ms = tempo_for(row / UNITS_PER_ROW)
    if loop % BAR or end % BAR:
        raise BuildError("SB1 music: loop / end not on a bar")
    lines = lines_of(notes)
    if set(lines) - set(CHANNELS):
        raise BuildError(f"SB1 music: lines without a channel: {sorted(set(lines) - set(CHANNELS))}")
    keys = {CHANNELS[ln]: line_bars(ns, end // BAR, inst_of, tune, volpan) for ln, ns in lines.items()}
    hl = len(header({ch: 0 for ch in keys}, instruments))
    body, taddr, cinfo = assemble(keys, loop // BAR, tempo, SEQ_BASE + 6 + hl)
    seq = struct.pack("<HHH", SEQ_BASE + 2, SEQ_BASE + 6, 0) + header(taddr, instruments) + body
    if SEQ_BASE + len(seq) > SEQ_END:
        raise BuildError(f"SB1 music: sequence ({len(seq)} bytes) overflows ${SEQ_END:04X}")
    blocks = [(SEQ_BASE, seq), (SAMPLE_BASE, bytes(blob)), (0xFD00, bytes(dirs)), (0xFE00, bytes(tunings))]
    info = dict(seq=len(seq), samples=len(blob), notes=len(notes), tempo=tempo, unit_ms=unit_ms,
                row_ms=row, cents=worst, channels=sorted(keys), **cinfo)
    return tm._list(blocks, bytes([0x00, 0x08])), info


def apply(rb, sound_dir):
    image = open(os.path.join(sound_dir, "sb1_stage_w1.bin"), "rb").read()
    lst, info = build(image, os.path.join(sound_dir, "sb1_w1_song.txt"))
    a = rb.alloc(["stream_ed", "free_c8_sheets"], lst, "SB1 1-1 music: Hudson upload list (sequence, samples)")
    if (a & 0xFFFF) + len(lst) > 0x10000:
        raise BuildError("SB1 music: the upload list crosses a bank")
    defs = {"SB1M_ID": f"${MUSIC_ID:02X}", "SB1M_STAGE": f"${STAGE:02X}", "SB1M_CMD": f"${CMD:02X}",
            "SB1M_LIST": f"${a:06X}"}
    return defs, info
