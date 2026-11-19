"""In-game SFX: cornered bomber, player death and enemy death.

  * cornered (animation $21: a bomb and no way out): the SB6 fan game's
    recording (assets/sound/cornered.wav), when a seat bomber's animation
    becomes $21 (setter $C0:11EC);
  * player death: Super Bomberman 1's (sound $1F), at once. SB5 asks for a
    group-3 stream there (id 1: a 2 KB voice sent to ARAM $5900 at 64 bytes a
    frame, then SFX $4F), which is why its sound comes late;
  * enemy death: Super Bomberman 1's (sound $16), when the enemy is hit
    ($C3:4D41, it turns into its death puff). SB5 only sounded group 2 id $33
    (SFX $57) ~70 frames later, with the score; that one is now silent.

The SB1 sounds are rebuilt as Hudson SFX from their own samples
(tools/extract_sb1_sfx.py): same ADSR, same pitches and the same note
pattern. All three are new SFX commands $5E-$60 (unused by SB5) whose
sequences and samples stay in ARAM while a stage is up:

  * R = $5900-$657F, SB5's group-3 voice buffer (nothing else writes there in
    a stage): the sequences, a silent END block, both SB1 samples and the
    first part (A) of the cornered recording;
  * the rest of the recording (B) just below the song's echo buffer ($DD00),
    or below the menu SFX samples ($B900) for a song that keeps them; A's
    last block loops into B (directory entry), or into the silent block when
    the song leaves no room for B (the sound is cut short then).

The CPU side (asm/game_sfx.asm) uploads R with the sets and songs that leave
it alone, sends the new commands only while R is in ARAM, and streams R back
(through SB5's own group-3 queue, set $48 = SB5's death voice, now unused)
after another group-3 voice has overwritten it.
"""
import os
import struct

import numpy as np

from .. import asar, brr
from ..rombuild import BuildError
from ..romlib import off
from . import title_music as tm

ASM = os.path.join(tm.ROOT, "asm", "game_sfx.asm")

R_BASE, R_END = 0x5900, 0x6580      # group-3 voice buffer; set 3 (stage SFX samples) starts at $6580
ECHO = 0xDD00                       # echo buffer of a song with EDL 4
MENU_SFX = tm.SFX_BASE              # $B900: the SB6 menu SFX samples of the songs that keep them
STREAM_SET = 0x48                   # set of SB5's death voice (group 3 id 1): becomes R
CMD_CORNER, CMD_ENEMY, CMD_DEATH = 0x5E, 0x5F, 0x60   # pointer table entries $3D-$3F (cmd - $21)
SRC_CORNER, SRC_DEATH, SRC_ENEMY = 0x1F, 0x3C, 0x3D   # directory entries no song or set uses
INST_DEATH, INST_ENEMY, INST_CORNER = 2, 3, 31        # instruments no set writes
PRIO = {CMD_CORNER: 0x1C, CMD_ENEMY: 0x06, CMD_DEATH: 0x1F}   # SB5: death voice $1F, enemy $06
CHANNEL = {CMD_CORNER: 0x08, CMD_ENEMY: 0x04, CMD_DEATH: 0x01}  # SFX channel 3 is unused by SB5's stage SFX
VOL, PAN = 0x4F, 0x0F
# Songs that must get the whole cornered sound: stage and battle music
# (music ids 6-$0F, $14, $15 in the stage scripts = songs 5-14, 19, 20).
STAGE_SONGS = list(range(5, 15)) + [19, 20]
SB1M_SONG = tm.N_SONGS + 1           # gs_song while SB1's World 1 music is in ARAM (features/sb1_music.py)
# Hudson pitch of note n (= 12 * octave + note) with the SFX tuning "04 0C 00 CE"
# (measured in Mesen: n 24 / 28 / 31 = $03F3 / $04FA / $05E9).
SFX_TUNING = bytes.fromhex("04 0C 00 CE")


def hudson_pitch(n):
    return 1011.0 * 2 ** ((n - 24) / 12)


# Super Bomberman 1, from the S-DSP writes (tools/extract_sb1_sfx.py):
SB1_ADSR = (0xDF, 0x94, 0x9E)
DEATH_HI, DEATH_LO = 0x09C4, 0x05DC  # pitches; 8 key-ons hi, lo, hi, ... 4 / 6 Hudson ticks (16 ms)
DEATH_NOTES = [(40, 4), (31, 6)] * 4  # (Hudson note, ticks): 40 plays hi after resampling, 31 = lo -16 cents
ENEMY_PITCH, ENEMY_NOTE, ENEMY_TICKS = 0x04B0, 27, 10   # note 27 = $04B2: the sample is used as is
CORNER_NOTES = range(30, 23, -1)     # highest note (sample rate) whose recording fits A + B
TICK_S = tm.SFX_TICK_MS / 1000.0


def _note(n):
    return (n // 12, n % 12) if n % 12 else (n // 12 - 1, 12)


def _seq(addr, cmd, inst, notes):
    """Hudson SFX: [channel mask, track pointer], then the track."""
    t = bytearray([0xD1, 0x00, 0xDD, inst, 0xD8, PAN, 0xD6, VOL, 0xE4])
    octave = None
    for n, ticks in notes:
        o, k = _note(n)
        if o != octave:
            t += bytes([0xD2, o])
            octave = o
        t += bytes([k << 4, ticks])
    t.append(0xD0)
    return bytes([CHANNEL[cmd], (addr + 3) & 0xFF, (addr + 3) >> 8]) + bytes(t)


def _end(data, loop=False):
    d = bytearray(data)
    d[-9] = (d[-9] & 0xFC) | (3 if loop else 1)
    return bytes(d)


def _death(sound_dir, cache_dir):
    raw = open(os.path.join(sound_dir, "sb1_death.brr"), "rb").read()
    pcm = brr.decode(raw).astype(np.float64)
    hi = hudson_pitch(DEATH_NOTES[0][0])
    y = tm.resampled(pcm, DEATH_HI, hi)           # played at `hi` it sounds as SB1's at DEATH_HI
    # longest note: ticks + ~10 ms of release, at the pitch it is played
    need = max((t * TICK_S + 0.01) * hudson_pitch(n) * 32000 / 4096 for n, t in DEATH_NOTES)
    n = int(np.ceil(need / 16)) * 16
    if n > len(y):
        raise BuildError("sb1_death.brr is shorter than the notes need")
    y = np.clip(np.rint(y[:n]), -32768, 32767).astype(np.int64)
    return _end(tm.encoded_pcm(y, cache_dir, "gsfx_death"))


def _corner(sound_dir, cache_dir, n):
    rate, x = tm.read_wav(os.path.join(sound_dir, "cornered.wav"))
    loud = np.flatnonzero(np.abs(x) > 0.003 * np.abs(x).max())
    x = x[loud[0]:loud[-1] + 1]
    to = hudson_pitch(n) * 32000 / 4096
    y = tm.resampled(x, rate, to)
    fade = min(len(y), round(to * 0.02))
    y[-fade:] *= np.linspace(1, 0, fade) ** 2
    y = np.concatenate([y, np.zeros(-len(y) % 16)])
    return tm.encoded_pcm(tm.to_pcm(y), cache_dir, f"gsfx_corner{n}"), len(y) / to


def _songs(rom, b_len):
    """Per song: bit 0 = R survives it, bit 1 = B fits below $DD00 (B1), bit 2 =
    B fits below the menu SFX samples it keeps (B2). One more byte (0) for
    a song record the table does not know, then SB1's World 1 music (R ok, no
    room for B: features/sb1_music.py, SB1M_SONG)."""
    safe = tm.song_table(rom)
    out = bytearray(tm.N_SONGS + 2)
    out[SB1M_SONG] = 1
    for song in range(tm.N_SONGS):
        rec = 0xDA0000 | struct.unpack_from("<H", rom, off(tm.SONG_TABLE + 2 * song))[0]
        start = end = struct.unpack_from("<H", rom, off(rec + 2))[0]
        a = rec + 4
        while rom[off(a)] != 0xFF:
            end += struct.unpack_from("<H", rom, off(tm.SAMPLE_SIZES + 2 * rom[off(a)]))[0]
            a += 1
        v = 0
        if end <= R_BASE or start >= R_END:
            v |= 1
        if safe[song] == 1:
            if end <= MENU_SFX - b_len:
                v |= 4
        elif _edl(rom, song) <= 4 and end <= ECHO - b_len:
            v |= 2
        out[song] = v
    return bytes(out)


def _edl(rom, song):
    t = off(tm.SET_TABLE + 3 * (0x27 + song))
    p = int.from_bytes(rom[t:t + 3], "little")
    if p >> 16 < 0xC0:
        return 99
    seqs = [b for b in tm._blocks(rom, p) if b[0] == 0x3000]
    if not seqs:
        return 99
    base, data = seqs[0]
    i, edl = struct.unpack_from("<H", data, 2)[0] - base, 99
    try:
        while data[i]:
            op, n = data[i], data[i + 1]
            if op == 1:
                i += 2 + 2 * bin(n).count("1")
            elif op in (2, 8):
                i += 2
            elif op in (3, 4):
                i += 2 + 4 * n
            elif op in (5, 6, 9):
                i += 2 + 2 * n
            elif op == 7:
                edl = data[i + 4] & 15 if n == 0 else 1
                i += 8 if n == 0 else 2
            else:
                return 99
    except IndexError:
        return 99
    return edl


def _song_gap(rom, song, b2):
    """Room for B in a song (B1 below the echo buffer, B2 below the menu SFX)."""
    rec = 0xDA0000 | struct.unpack_from("<H", rom, off(tm.SONG_TABLE + 2 * song))[0]
    end = struct.unpack_from("<H", rom, off(rec + 2))[0]
    a = rec + 4
    while rom[off(a)] != 0xFF:
        end += struct.unpack_from("<H", rom, off(tm.SAMPLE_SIZES + 2 * rom[off(a)]))[0]
        a += 1
    return (MENU_SFX if b2 else ECHO) - end


def _sets(rom):
    """Per set id 0-255: 1 when its upload writes into R."""
    out = bytearray(256)
    for s in range(256):
        t = off(tm.SET_TABLE + 3 * s)
        p = int.from_bytes(rom[t:t + 3], "little")
        if p >> 16 < 0xC0:
            out[s] = 1
            continue
        try:
            blocks = tm._blocks(rom, p)
        except Exception:
            out[s] = 1
            continue
        if any(a < R_END and a + len(d) > R_BASE for a, d in blocks):
            out[s] = 1
    return bytes(out)


def build(rom, sound_dir, cache_dir):
    """ARAM images and upload lists (see the module doc)."""
    enemy = open(os.path.join(sound_dir, "sb1_enemy.brr"), "rb").read()
    if len(enemy) % 9 or enemy[-9] & 3 != 1:
        raise BuildError("sb1_enemy.brr must end with an END block (no loop)")
    death = _death(sound_dir, cache_dir)
    silent = bytes([0x01]) + bytes(8)
    safe = tm.song_table(rom)
    b_max = min(_song_gap(rom, s, safe[s] == 1) for s in STAGE_SONGS) // 9 * 9

    # R: sequences, silent block, death, enemy, cornered A
    seq_len = len(_seq(0, CMD_DEATH, 0, DEATH_NOTES)) + len(_seq(0, CMD_ENEMY, 0, [(ENEMY_NOTE, 1)])) + \
        len(_seq(0, CMD_CORNER, 0, [(24, 1)]))
    fixed = seq_len + len(silent) + len(death) + len(enemy)
    a_max = (R_END - R_BASE - fixed) // 9 * 9
    for note in CORNER_NOTES:
        corner, seconds = _corner(sound_dir, cache_dir, note)
        if len(corner) <= a_max + b_max:
            break
    else:
        raise BuildError(f"cornered.wav: {len(corner)} bytes at the lowest rate, {a_max + b_max} fit")
    a_len = min(len(corner), a_max)
    part_a, part_b = corner[:a_len], corner[a_len:]
    ticks = int(np.ceil(seconds / TICK_S)) + 2
    if ticks > 255:
        raise BuildError("cornered.wav: too long for one SFX note")

    addr = R_BASE
    seqs = {}
    blob = bytearray()
    for cmd, inst, notes in ((CMD_DEATH, INST_DEATH, DEATH_NOTES), (CMD_ENEMY, INST_ENEMY, [(ENEMY_NOTE, ENEMY_TICKS)]),
                             (CMD_CORNER, INST_CORNER, [(note, ticks)])):
        s = _seq(addr + len(blob), cmd, inst, notes)
        seqs[cmd] = addr + len(blob)
        blob += s
    silent_at = addr + len(blob)
    blob += silent
    death_at = addr + len(blob)
    blob += death
    enemy_at = addr + len(blob)
    blob += enemy
    corner_at = addr + len(blob)
    if part_b:
        blob += _end(part_a, loop=True)
        part_b = _end(part_b)
    else:
        blob += _end(part_a)
    if len(blob) % 2:
        blob.append(0)                   # the group-3 stream sends words
    if R_BASE + len(blob) > R_END:
        raise BuildError("game SFX: R overflows")
    b1 = ECHO - len(part_b)
    b2 = MENU_SFX - len(part_b)

    l_r = tm._list([(R_BASE, bytes(blob))])
    patch = [(0x4410 + 2 * (c - 0x21), struct.pack("<H", seqs[c])) for c in (CMD_CORNER, CMD_ENEMY, CMD_DEATH)]
    patch += [(0x4550 + (CMD_CORNER - 0x21), bytes([PRIO[CMD_CORNER], PRIO[CMD_ENEMY], PRIO[CMD_DEATH]]))]
    adsr = bytes(SB1_ADSR)
    patch += [(0x44D0 + 4 * INST_DEATH, bytes([SRC_DEATH]) + adsr + bytes([SRC_ENEMY]) + adsr),
              (0x44D0 + 4 * INST_CORNER, bytes([SRC_CORNER, 0xFF, 0xE0, 0xA0])),
              (0xFD00 + 4 * SRC_DEATH, struct.pack("<HHHH", death_at, death_at, enemy_at, enemy_at)),
              (0xFE00 + 4 * SRC_DEATH, SFX_TUNING * 2),
              (0xFE00 + 4 * SRC_CORNER, SFX_TUNING)]
    l_patch = tm._list(patch)

    def dir_list(loop):
        return tm._list([(0xFD00 + 4 * SRC_CORNER, struct.pack("<HH", corner_at, loop))])

    lists = dict(L_R=l_r, L_PATCH=l_patch, L_DIR0=dir_list(silent_at), L_DIR1=dir_list(b1), L_DIR2=dir_list(b2),
                 L_B1=tm._list([(b1, part_b)]) if part_b else tm._list([]),
                 L_B2=tm._list([(b2, part_b)]) if part_b else tm._list([]))
    songs = _songs(rom, len(part_b))
    missing = [s for s in STAGE_SONGS if not songs[s] & 1 or (part_b and not songs[s] & 6)]
    if missing:
        raise BuildError(f"game SFX: stage songs {missing} leave no room")
    info = dict(r_bytes=len(blob), corner_note=note, corner_rate=hudson_pitch(note) * 32000 / 4096,
                corner_seconds=seconds, a=len(part_a), b=len(part_b), b1=b1, b2=b2,
                short=[s for s in range(tm.N_SONGS) if songs[s] & 1 and part_b and not songs[s] & 6],
                death=len(death), enemy=len(enemy))
    return lists, songs, _sets(rom), info


def apply(rb, sound_dir, cache_dir):
    """`ACTIVE` = the title stream flag of asm/title_music.asm ($0100)."""
    lists, songs, sets, info = build(rb.d, sound_dir, cache_dir)
    defs = {"ACTIVE": "$000100", "NSONGS": tm.N_SONGS, "RTL_C0": f"${tm.RTL_C0:06X}",
            "CMD_CORNER": f"${CMD_CORNER:02X}", "CMD_ENEMY": f"${CMD_ENEMY:02X}", "CMD_DEATH": f"${CMD_DEATH:02X}",
            "STREAM_SET": f"${STREAM_SET:02X}", "SB1M_SONG": f"${SB1M_SONG:02X}"}
    for name, data in lists.items():
        defs[name] = f"${rb.alloc('bulk', data, f'game SFX: upload list {name}'):06X}"
    defs["SONGS"] = f"${rb.alloc('bulk', songs, 'game SFX: per song (R ok, B1, B2)'):06X}"
    defs["SETS"] = f"${rb.alloc('bulk', sets, 'game SFX: sets that write into R'):06X}"
    region = rb.regions["bulk"]
    code_addr = region.cursor
    defs.update(CODE=f"${code_addr:06X}", CODE_END=f"${region.end:06X}")
    runs, syms = asar.assemble_into(rb.d, ASM, defs)
    lo, hi = off(code_addr), off(syms["end"])
    code = bytearray(rb.d[lo:hi])
    for o, data in runs:
        if o < lo or o + len(data) > hi:
            raise BuildError(f"game_sfx.asm wrote outside its allocation at file offset {o:06X}")
        code[o - lo:o - lo + len(data)] = data
    if rb.alloc("bulk", bytes(code), "game SFX: CPU code (asm/game_sfx.asm)") != code_addr:
        raise BuildError("game SFX code moved")

    a = syms["gs_anim"]
    rb.patch(0xC011EC, bytes.fromhex("99 9F 07 A9 00"), bytes([0x5C, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xEA]),
             "game SFX: animation setter (cornered $21 plays its sound)")
    e = syms["gs_enemy"]
    rb.patch(0xC34D41, bytes.fromhex("BD C2 16 8D 51 1D"), bytes([0x22, e & 0xFF, e >> 8 & 0xFF, e >> 16, 0xEA, 0xEA]),
             "game SFX: enemy hit (turns into its death puff) plays SB1's enemy death")
    # SB5's death voice set now streams R back after another group-3 voice
    t = tm.SET_TABLE + 3 * STREAM_SET
    lr = int(defs["L_R"][1:], 16)
    rb.patch(t, bytes(rb.d[off(t):off(t) + 3]), lr.to_bytes(3, "little"), "game SFX: set $48 = R (group-3 stream)")
    info["syms"] = syms
    info["sb1m_song"] = defs["SB1M_SONG"]
    return info


# SB5's death voice (upload list of set $48: one block of 1998 bytes for ARAM $5900, the end mark and the
# jump word; the next set's list starts right after). Its only pointer is the set table entry apply()
# moves to R; group 3 id 1 is the only request naming set $48 ($80:8765), no group-4 or music entry does,
# and no native set upload passes it.
OLD_DATA = [("free_d9", 0xD9E464, 2006, 0xEED80FAA, "freed SB5 death voice (sound set $48 upload list)")]


def free_old(rb):
    """After apply(): fills SB5's death voice with $FF and declares it as a free region."""
    t = off(tm.SET_TABLE + 3 * STREAM_SET)
    if int.from_bytes(rb.d[t:t + 3], "little") == OLD_DATA[0][1]:
        raise BuildError("game SFX: set $48 still points at SB5's death voice")
    for name, start, size, crc, purpose in OLD_DATA:
        rb.free_old(name, start, size, crc, purpose)
