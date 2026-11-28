"""SB6's stage voices (the Unity fan game's StageIntroTransition "start" and EndStage's random "good"):
"Start" after SB5's stage start jingle (asked for with request (0, $20) when the players get control), START_DELAY
frames after it, before the stage music as in the fan game's 0.5 s wait, and one of three "good" voices at the stage clear
(request (0, $21), with SB5's clear jingle), in the stages of STAGES.

The recordings (assets/sound/voice_*.wav = the fan game's Resources/Sounds start.wav, good1-3.wav) are BRR at
RATE Hz (~22 KB of ROM), with the fan game's volumes (start 0.5, good1 0.5, good2 0.5, good3 1.0) relative to
each other. They are too long for the ARAM a stage leaves, so they play from a ring of NR blocks in the stage's
SB1 music list (features/sb1_music.py `voice`: the free ARAM right below SB5's echo buffer $DD00, game_sfx's
part B there included, which SB1 songs never send) as Hudson SFX (CMD for "start", CMD_GOOD for the good ones:
one note as long as the clip, so the music gets its voice back at once) whose sample loops over the ring:

  * the stage load uploads the ring with the first NR blocks of "start" (head list, asm/game_sfx.asm vs_reset);
  * a voice keys on when its first blocks are in the ring; while it plays, gs_tick (main loop, before SB5 waits
    for the NMI) sends the next blocks with Hudson's port-1 transfer (command $31, as SB5's group-3 voices),
    only behind the play position (estimated from the NMI count: K blocks a frame) and, unless the play
    position is about to catch up, only on the frame's idle time: Hudson's driver looks at port 1 only every
    ~100 lines and a word costs ~1.2 lines, so a transfer starts under line VSTART, is given up (port 1 = $7F, as
    SB5 does on a lag frame) without an answer by VACK and stops at VEND: no main-loop pass is lost for it;
  * after "start", the next "good" (picked at random) is loaded into the ring the same way, on idle time.

Every block of a clip is stored as the ring holds it: block j goes to ring block j mod NR, the ring's last
block has END + LOOP (on to the ring's start) unless it is the clip's last one (END only).
"""
import math
import os
import struct

import numpy as np

from ..rombuild import BuildError
from . import title_music as tm

# World 1 stages with voices: 1-1, 1-3 to 1-5 (their SB1 songs keep the cornered sound's part B free), 1-2 ("good"
# only, from its piano's ARAM: sb1_music.GOOD_RING), 1-6 (its first duel: the start jingle plays once, the next duels follow on without it and no clear
# jingle ends one)
STAGES = (0x0D, 0x11, 0x18, 0x10, 0x17, 0x67)
# the boss stages' end (1-6 after its Golden duel, 1-7): their boss's death asks for SB5's boss victory music (id $0F =
# set $35 + song END_SONG), which takes the SB1 song's ARAM; a "good" plays with the boss clear jingle (0/$22) from
# a ring in what that song leaves of the sequence area (END_LO: after its sequences, up to the SFX tables at
# $4400). Their record: stage byte END_KEY, found by vs_reset when gs_song = END_SONG on these stages
END_SONG, END_SET, END_KEY, END_STAGES = 0x0E, 0x35, 0xFE, (0x67, 0x68)   # ($1031 = $67 the whole tournament)
CLIPS = [("start", 0.5), ("good1", 0.5), ("good2", 0.5), ("good3", 1.0)]   # Unity's volumes
CMD, CMD_GOOD = 0x63, 0x64  # Hudson SFX (pointer table entries $42-$43: SB5 points $63-$66 at a dummy)
# "start" keys on START_DELAY main-loop passes after the start jingle's request: in 1-1 (measured in Mesen) the
# jingle's last note keys on ~84 frames in, the stage music (request (0, 6)) comes ~178 frames in, so "start"
# (~45 frames) plays between them and the music follows it ~0.6 s later (Unity waits 0.5 s)
START_DELAY = 95
INST = 29                   # instrument entry nothing in an SB1 World 1 stage uses (SB6 menu SFX's elsewhere)
SRC = 0x3E                  # directory entry (1-6's crowd / the picker's color change: not in these stages)
CHANNEL = 0x08              # SFX channel 3 (the cornered sound's: never at a stage start / clear)
PRIO, VOL, PAN = 0x1C, 0x4F, 0x0F
ADSR = (0xFF, 0xE0, 0x9E)   # full volume while held (the recording has its envelope), fast release
NOTE = 32                   # Hudson note; the tuning entry plays it at RATE
RATE_WANTED = 11025
BASE_MULT = 0x040C          # SFX tuning "04 0C 00 CE": note n = 1011 * 2^((n - 24) / 12)
PEAK = 0.89                 # the loudest clip (good2 at 0.5) at -1 dBFS
QUIET, FADE = 0.003, 0.01
QUIET_LOW_END = 0.01        # a lower "start" ends where it falls under -40 dB (RMS)
MIN_RING = 140              # blocks
HEAD = 64                   # blocks of a clip loaded after it is asked for (a good one) before it keys on
# "start" plays while 4 players run the stage: no idle time is left then (coop4_check), so every block sent while
# it plays costs frames. Per stage, START_STEPS semitones lower (its own sequence's note in that stage's song): 1-3
# so that it fits its ring whole (nothing sent while it plays); 1-1 keeps 11 kHz (its ring holds 55%: the rest
# streams, coop4 >= 50 fps), 1-4 / 1-5 (150 blocks: part B's ARAM only) as low as it still sounds like a voice
START_STEPS = {0x0D: 3, 0x18: 7, 0x10: 12, 0x17: 9, 0x67: 9}
# asm/game_sfx.asm vs_tick (blocks, scanlines): a transfer of at most CH blocks; the ring holds at least AHEAD
# blocks past the play position (3 frames + 5) and is written only BEHIND blocks behind it (key-on latency, the
# DSP's read-ahead); a voice is over TAIL blocks after its last; on idle time a transfer starts under line VSTART,
# is given up without an answer by VACK and sends pairs of blocks (~11 lines each) until VEND (the NMI: 225); a
# voice asked for waits WAIT passes for its first blocks
CH, AHEAD, BEHIND, TAIL, WAIT = 28, 24, 30, 30, 180
BEHIND_START = 12            # ("start" keys on ~1 frame after LAT, a good one ~2)
LAT = 2                     # frames from the SFX command to the S-DSP key-on (measured: 3) not counted as played
VSTART, VACK, VEND = 185, 195, 200
REC = 38                    # VOICE_TAB record: stage, entries list, head list, ring, NR, 5 x (clip, blocks), K of
#                             start (word; the good ones: K)
FPS = 60.0988
CACHE = os.path.join(tm.ROOT, "build", "cache")
# (after "c2"/"objmap3": what the character selection music leaves in code / table banks; the ROM is nearly
# full since char8: 2026-11-27)
REGIONS = ["free_db_b", "free_dc_zone1", "free_e3_options", "free_d3", "free_d4_options", "free_db_a", "free_d6",
           "obj_f6", "obj_f2", "free_e1_options2", "c2", "objmap3", "bulk", "d0", "c0", "e3_tables"]


def _mult():
    pitch = RATE_WANTED * 4096 / 32000
    return round(BASE_MULT * pitch / (1011.0 * 2 ** ((NOTE - 24) / 12)))


MULT = _mult()
# the rate Hudson plays NOTE at with MULT (the DSP pitch it writes, measured in Mesen: PITCH)
PITCH = 0x0584
RATE = PITCH * 32000 / 4096
K = round(RATE / 16 / FPS * 256)    # blocks a frame, 8.8 fixed point (asm/game_sfx.asm vs_tick)
PLAN = []           # [(stage, ring, nr, shared, steps)] (build: qa reads build/voice_plan.json)


def pitch(steps):
    """Hudson's pitch of NOTE - steps (12-TET from the measured PITCH; within 1 of what it writes)."""
    return round(PITCH * 2 ** (-steps / 12))


def rate(steps):
    return pitch(steps) * 32000 / 4096


def k_of(steps):
    return round(rate(steps) / 16 / FPS * 256)

_memo = {}


def _raw(sound_dir, name, vol, to, end=QUIET):
    rate, x = tm.read_wav(os.path.join(sound_dir, f"voice_{name}.wav"))
    loud = np.flatnonzero(np.abs(x) > QUIET * np.abs(x).max())
    x = x.astype(np.float64)
    w = 256                                 # the end: the last 256-sample window over `end` (RMS)
    rms = np.sqrt(np.convolve(x ** 2, np.ones(w) / w, mode="same"))
    tail = np.flatnonzero(rms > end * np.abs(x).max())
    x = x[loud[0]:max(loud[-1] if end == QUIET else 0, tail[-1]) + 1]
    y = tm.resampled(x, rate, to) * vol
    fade = min(len(y), round(to * FADE))
    y[-fade:] *= np.linspace(1, 0, fade) ** 2
    return np.concatenate([y, np.zeros(-len(y) % 32)])       # an even number of blocks


def _brr(y, gain, key):
    pcm = np.rint(y * gain).astype(np.int64)
    data = bytearray(tm.encoded_pcm(pcm, CACHE, key))
    if len(data) % 18:
        raise BuildError(f"voice {key}: {len(data)} bytes of BRR, not an even number of blocks")
    return data


def clips(sound_dir, steps=0):
    """[(BRR bytes, seconds)] in CLIPS order; an even number of blocks, the last one END. steps: "start" that many
    semitones lower (same gain)."""
    if (sound_dir, steps) in _memo:
        return _memo[(sound_dir, steps)]
    raw = [_raw(sound_dir, name, vol, RATE) for name, vol in CLIPS]
    gain = PEAK * 32767 / max(np.abs(y).max() for y in raw)
    out = [(_brr(y, gain, f"voice_{name}"), len(y) / RATE) for (name, _), y in zip(CLIPS, raw)]
    if steps:
        name, vol = CLIPS[0]
        y = _raw(sound_dir, name, vol, rate(steps), QUIET_LOW_END)
        out[0] = (_brr(y, gain, f"voice_{name}_low{steps}e"), len(y) / rate(steps))
    _memo[(sound_dir, steps)] = out
    return out


def ring_image(data, nr):
    """The clip's blocks with the flags the ring needs (block j sits at ring block j mod nr)."""
    d = bytearray(data)
    n = len(d) // 9
    for j in range(n):
        h = d[9 * j] & 0xFC
        if j == n - 1:
            h |= 1                       # END: the voice stops
        elif j % nr == nr - 1:
            h |= 3                       # END + LOOP: on to the ring's first block
        d[9 * j] = h
    return bytes(d)


def ticks(sound_dir, good, steps=0):
    secs = [s for _, s in clips(sound_dir, steps)]
    t = int(math.ceil(max(secs[1:] if good else secs[:1]) * 1000 / tm.SFX_TICK_MS)) + 2
    if t > 255:
        raise BuildError("voice SFX: too long for one SFX note")
    return t


def sequence(addr, sound_dir, good=False, steps=0, inst=INST):
    """The SFX at ARAM addr: one note as long as "start" / the longest good one (a clip stops itself with END)."""
    n = NOTE - (0 if good else steps)
    o, k = (n // 12, n % 12) if n % 12 else (n // 12 - 1, 12)
    track = bytes([0xD1, 0x00, 0xDD, inst, 0xD8, PAN, 0xD6, VOL, 0xE4, 0xD2, o, k << 4, ticks(sound_dir, good, steps), 0xD0])
    seq = bytes([CHANNEL, (addr + 3) & 0xFF, (addr + 3) >> 8]) + track
    return seq + (b"\x00" if len(seq) % 2 else b"")


def entries(seqs, ring, inst=INST, src=SRC):
    """Upload list blocks of one stage (sent after every set / song upload: the sets rewrite these tables)."""
    return [(0x4410 + 2 * (CMD - 0x21), struct.pack("<HH", *seqs)),
            (0x4550 + (CMD - 0x21), bytes([PRIO, PRIO])),
            (0x44D0 + 4 * inst, bytes([src]) + bytes(ADSR)),
            (0xFD00 + 4 * src, struct.pack("<HH", ring, ring)),
            (0xFE00 + 4 * src, struct.pack(">H", MULT) + bytes([0x00, 0xCE]))]


def table_size():
    if REC * len(STAGES) > 2 * 0xFF or REC % 2:       # (asm/game_sfx.asm vs_rec: a record's offset / 2)
        raise BuildError("voice SFX: VOICE_TAB's records past vs_rec's reach")
    return 1 + REC * (len(STAGES) + 1)


def end_layout(rom):
    """(first free byte of the sequence area, $4400) with SB5's boss victory music in ARAM (set END_SET)."""
    from . import sb1_music as M
    hi = 0x3000
    for dest, data in tm._blocks(rom, M._long(rom, tm.SET_TABLE + 3 * END_SET)):
        if dest < 0x4400:
            hi = max(hi, dest + len(data))
    return hi, 0x4400


_pending = []       # (record address, ring, nr, shared, steps) filled by late()


def fill(rb, table, stage_infos, sound_dir=None):
    """sb1_music.apply: stage_infos = [(stage, (seqs, ring, nr, shared, steps))]. Writes the records' stage, entries
    list, ring, NR and K (start's blocks a frame); late() adds the head list and the clips."""
    o = table & 0x3FFFFF
    if any(b != 0xFF for b in rb.d[o:o + table_size()]):
        raise BuildError("voice SFX: VOICE_TAB is not blank")
    for k, (stage, (seq, ring, nr, shared, steps, inst, src, head)) in enumerate(stage_infos):
        el = rb.alloc("bulk", tm._list(entries(seq, ring, inst, src)), f"voice SFX: stage ${stage:02X} table entries")
        rec = table + REC * k
        r = rec & 0x3FFFFF
        rb.d[r] = stage
        rb.d[r + 1:r + 4] = el.to_bytes(3, "little")
        struct.pack_into("<HH", rb.d, r + 7, ring, nr)
        struct.pack_into("<H", rb.d, r + 36, k_of(steps))
        _pending.append((rec, ring, nr, shared, steps, head))
        PLAN.append((stage, ring, nr, shared, steps, src, head is not None))
    # the end record: its sequences at the start of the free range, the ring after them; its head list = the
    # sequences (sent at the upload), no "start" (count 0), part B stays where SB5's songs keep it
    lo, hi = end_layout(rb.d)
    seqs = []
    a = lo
    for good in (False, True):
        sq = sequence(a, sound_dir, good)
        seqs.append((a, sq))
        a += len(sq)
    nr = (hi - a) // 9 & ~1
    ring = hi - 9 * nr
    if nr < MIN_RING:
        raise BuildError(f"voice SFX: SB5's boss victory music leaves {nr} blocks")
    el = rb.alloc("bulk", tm._list(entries(tuple(x for x, _ in seqs), ring)), "voice SFX: boss end table entries")
    rec = table + REC * len(stage_infos)
    r = rec & 0x3FFFFF
    rb.d[r] = END_KEY
    rb.d[r + 1:r + 4] = el.to_bytes(3, "little")
    struct.pack_into("<HH", rb.d, r + 7, ring, nr)
    struct.pack_into("<H", rb.d, r + 36, k_of(0))
    _pending.append((rec, ring, nr, False, 0, seqs))
    PLAN.append((END_KEY, ring, nr, False, 0, SRC, True))


def late(rb, sound_dir, part_b):
    """After every other ROM user (the character selection music takes what is left): the clips of each
    stage's ring size, the cornered sound's part B (clip 4, where the ring is B's ARAM: B goes back to the
    ring's last blocks after a voice; 0 blocks for a ring of its own) and the head lists. -> info"""
    images = {}
    total = 0
    for rec, ring, nr, shared, steps, head_blocks in _pending:
        cl = clips(sound_dir, steps)
        # the clips as they are (asm/game_sfx.asm vs_edge sets END + LOOP on a ring's last block as it sends it)
        for c in range(len(CLIPS)):
            key = (c, steps if c == 0 else 0)
            if key not in images and not (c == 0 and head_blocks is not None):
                lo_s = f" ({key[1]} semitones lower)" if key[1] else ""
                images[key] = rb.alloc(REGIONS, ring_image(cl[c][0], 1 << 20), f"voice SFX: {CLIPS[c][0]}{lo_s} (BRR)")
                total += len(cl[c][0])
        imgs = [(images.get((c, steps if c == 0 else 0), 0), len(cl[c][0]) // 9) for c in range(len(CLIPS))]
        if shared:
            if ring + 9 * nr != 0xDD00 or len(part_b) > 9 * nr or len(part_b) % 18:
                raise BuildError(f"voice SFX: ring ${ring:04X} ({nr} blocks) does not end with part B")
            if "b" not in images:
                images["b"] = rb.alloc(REGIONS, bytes(part_b), "voice SFX: the cornered sound's part B (back in rings)")
                total += len(part_b)
            imgs.append((images["b"], len(part_b) // 9))
        else:
            imgs.append((0, 0))
        if head_blocks is not None:
            imgs[0] = (imgs[0][0], 0)
            hl = rb.alloc(REGIONS, tm._list(head_blocks), f"voice SFX: ring {ring:04X}: the sequences (no 'start')")
            total += sum(len(b) + 4 for _, b in head_blocks)
        else:
            start = ring_image(cl[0][0], nr)
            head = start[:9 * min(nr, len(start) // 9)]
            hl = rb.alloc(REGIONS, tm._list([(ring, head)]), f"voice SFX: ring {ring:04X} with the start of 'start'")
            total += len(head) + 6
        r = rec & 0x3FFFFF
        rb.d[r + 4:r + 7] = hl.to_bytes(3, "little")
        for c, (a, n) in enumerate(imgs):
            rb.d[r + 11 + 5 * c:r + 14 + 5 * c] = a.to_bytes(3, "little")
            struct.pack_into("<H", rb.d, r + 14 + 5 * c, n)
    import json
    with open(os.path.join(tm.ROOT, "build", "voice_plan.json"), "w") as h:
        json.dump([dict(stage=st, ring=rg, nr=n, shared=sh, steps=sp, pitch=pitch(sp), src=sr, good_only=g,
                        start_blocks=len(clips(sound_dir, sp)[0][0]) // 9) for st, rg, n, sh, sp, sr, g in PLAN], h)
    secs = [s for _, s in clips(sound_dir)]
    return dict(bytes=total, seconds=secs, rate=RATE, rings=[(ring, nr, sh, sp) for _, ring, nr, sh, sp, _ in _pending])
