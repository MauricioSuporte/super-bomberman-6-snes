"""Title music: the SB6 fan game's title track, streamed as BRR.

SB5's sound driver (Hudson) plays sequenced songs; the SB6 track only exists
as a recording, so the title streams it instead:

  * The recording is resampled to 16 kHz mono and BRR-encoded (9 bytes per
    16 samples, ~9 KB/s) into whole banks from $E5 on, in 162-byte chunks
    (18 BRR blocks = 18 ms) that never cross a bank.
  * When the game asks for the title music (sound API $C0:0CED, group 0 id 2)
    the CPU uploads asm/spc/stream.asm to ARAM $7000 (SB5's title song area)
    plus the first chunks, and the main loop sends 1-2 chunks per frame.
  * Any other non-SFX sound request first restarts Hudson's driver at $0800
    with an empty IPL upload (as $C0:0E31 does after a set load), then runs
    normally, so leaving the title restores the original game audio.
  * The title intro has its own short stream (the pan's sound and the four
    character drops, mixed on the intro's timeline) before the music.

Menu SFX (cursor move, accept, back: sound API group 2, ids 1, 4, 3) are the
SB6 fan game's recordings, in every menu:

  * three BRR samples live in ARAM $B900-$DCFF with directory entries
    $39-$3B, uploaded when the title stream starts or when a song that leaves
    that area alone is loaded (`song_table`: its samples end below $B900 and
    its echo buffer starts at $DD00 or above);
  * with them in place, Hudson's definitions of the three SFX (common set 1,
    ARAM $45B0...) are overwritten with "instrument, one long note"; a song
    that needs the area puts SB5's definitions back (the old beeps);
  * the stream driver plays the same samples from its own scripts.
"""
import hashlib
import os
import struct

import numpy as np

from .. import asar, brr
from ..romlib import off

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASM_CPU = os.path.join(ROOT, "asm", "title_music.asm")
ASM_SPC = os.path.join(ROOT, "asm", "spc", "stream.asm")

RATE = 16000              # pitch $0800
PALETTE_SFX = 0x1E        # group-2 id of the picker's color change sound
# The Normal Game's save file / character selection music: 40 s would take
# 360 KB at 16 kHz, so it streams at 12 kHz (270 KB, in the tails of the
# banks the title uses and banks $FD-$FF).
SAVE_RATE = 12000
SAVE_SET, SAVE_MODE = 0x1C, 3  # sound API group 4 id $1C, sent when mode 3 (Normal menu) starts
CHUNK = 162               # bytes: 18 BRR blocks
CHUNK_SAMPLES = 18 * 16
ARAM_BASE = 0x7000        # driver page; ring right after it
SFX_BASE = 0xB900         # SB6 menu SFX samples (ARAM), up to the echo buffer
SFX_END = 0xDD00          # echo buffer of a song with EDL 4
RING_LIMIT = SFX_BASE     # the ring stays below them (SB5's title song area ends at $CFDF)
MAX_SRC, MAX_SLOTS = 4, 8 # SFX samples / scripts the driver holds
PREFILL = 8               # chunks uploaded with the driver (144 ms)
PEAK = 0.89               # -1 dBFS before BRR
VOL, MVOL = 0x70, 0x60     # MVOL as Hudson uses on the SB5 title; one voice carries the whole mix
# Frames from the end of the driver upload (op FF 1A FB in the title's load
# script) to the first frame of the pan, measured in Mesen (tools note in
# docs/ROM_MAP.md); the prefill's 8 silent chunks are part of that wait.
PAN_LEAD_FRAMES = 14
PAN_REGION = "title_fc"   # one bank for the pan sound's chunks
# Menu SFX: Hudson group-2 id, recording, seconds kept, (octave, note) of the
# one note Hudson plays and the S-DSP pitch it gives with the tuning entry of
# SB5's own SFX sample (read from voice 0 in Mesen); the recording is
# resampled to that pitch, so each sound has its own rate (11.9 / 10 / 7.9 kHz).
MENU_SFX = [
    (1, "menu_move.wav", 0.20, (2, 7)),
    (4, "menu_confirm.wav", 0.70, (2, 4)),
    (3, "menu_back.wav", 0.72, (1, 12)),
    # the character picker's color change (Unity Sounds/Skin/change.wav): only
    # sent by asm/picker.asm while the save music streams, so it has no Hudson
    # definition (id $1E stays SB5's own when Hudson's driver plays)
    (PALETTE_SFX, "menu_palette.wav", 0.13, (2, 4)),
]
STREAM_ONLY = {PALETTE_SFX}
SFX_PITCH = {(2, 7): 0x05E9, (2, 4): 0x04FA, (1, 12): 0x03F3}
SFX_SRCN = 0x39           # directory entries $39-$3B ($FDE4, tuning $FEE4): no set or song uses them
# directory entry of each menu SFX sample: $39-$3B, then $3E ($3C/$3D are game_sfx.py's)
SFX_DIRS = (0x39, 0x3A, 0x3B, 0x3E)
SFX_INST = 28             # instruments 28-30 ($4540): after the world sets' 4-27
SFX_TICK_MS = 16.0        # Hudson's SFX tick
SFX_VOL, SFX_PAN = 0x4F, 0x0F
STREAM_SFX_VOL = 0x7F     # the same samples on the stream driver's voice 0
SET_TABLE, SONG_TABLE = 0x85F69B, 0xDAC2E0
SAMPLE_PTRS, SAMPLE_SIZES = 0xDAD042, 0xDAD1BF
N_SONGS = 33
RTL_C0 = 0xC01170         # an RTL in bank $C0 (to call its JSR routines)
HUDSON_LOADER = 0xDF2B3A  # ROM image of ARAM $0FF0 (Hudson's loader); $1041 = RET
BANK_LIMIT = 0x10000 - CHUNK  # the feeder moves to the next bank past this offset


def read_wav(path):
    """(rate, mono float samples in -1..1); PCM or float WAV."""
    import warnings
    from scipy.io import wavfile
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rate, x = wavfile.read(path)
    scale = 1.0 if x.dtype.kind == "f" else float(1 << (8 * x.dtype.itemsize - 1))
    x = x.astype(np.float64) / scale
    if x.ndim > 1:
        x = x.mean(1)
    return rate, x


def resampled(x, rate, to):
    from fractions import Fraction
    from scipy.signal import resample_poly
    fr = Fraction(to / rate).limit_denominator(2000)
    return resample_poly(x, fr.numerator, fr.denominator)


def to_pcm(y):
    y = y * (PEAK * 32767 / max(1e-9, np.abs(y).max()))
    return np.rint(y).astype(np.int64)


def load_pcm(path):
    rate, x = read_wav(path)
    y = resampled(x, rate, RATE)
    return to_pcm(y[:len(y) // CHUNK_SAMPLES * CHUNK_SAMPLES])


def encoded_stream(wav, cache_dir):
    """BRR bytes for the recording, cached by content hash (encoding takes ~1 min)."""
    with open(wav, "rb") as fh:
        h = hashlib.sha1(fh.read())
    h.update(repr((RATE, PEAK, CHUNK_SAMPLES, open(brr.__file__, "rb").read())).encode())
    cache = os.path.join(cache_dir, f"title_music_{h.hexdigest()[:16]}.brr")
    if os.path.isfile(cache):
        with open(cache, "rb") as fh:
            return fh.read()
    data = brr.encode(load_pcm(wav))
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache, "wb") as fh:
        fh.write(data)
    return data


def loop_pcm(wav, rate):
    """A looping recording at `rate`, stretched (FFT resampling, which treats
    the signal as periodic: the loop point stays seamless) to a whole number
    of chunks; float samples, not normalized."""
    from scipy.signal import resample
    r, x = read_wav(wav)
    n = max(1, round(len(x) * rate / r / CHUNK_SAMPLES)) * CHUNK_SAMPLES
    return resample(x, n)


def rms(pcm):
    return float(np.sqrt(np.mean(np.asarray(pcm, dtype=np.float64) ** 2)))


def encoded_pcm(pcm, cache_dir, name):
    h = hashlib.sha1(pcm.tobytes())
    h.update(open(brr.__file__, "rb").read())
    cache = os.path.join(cache_dir, f"{name}_{h.hexdigest()[:16]}.brr")
    if os.path.isfile(cache):
        with open(cache, "rb") as fh:
            return fh.read()
    data = brr.encode(pcm)
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache, "wb") as fh:
        fh.write(data)
    return data


def intro_stream(pan_wav, drop_wav, drop_frames, cache_dir):
    """The title intro's sounds as one chunk run: PAN_LEAD_FRAMES of silence
    (the stream starts while the screen is still black), the pan's sound with
    the character drops mixed in at their frames (counted from the first frame
    of the pan), and one silent chunk that the feeder repeats until the music
    replaces the stream."""
    rate, x = read_wav(pan_wav)
    mix = resampled(x, rate, RATE)
    if drop_frames:
        rate, x = read_wav(drop_wav)
        d = resampled(x, rate, RATE)
        last = round(max(drop_frames) * RATE / 60.0988) + len(d)
        mix = np.concatenate([mix, np.zeros(max(0, last - len(mix)))])
        for f in drop_frames:
            o = round(f * RATE / 60.0988)
            mix[o:o + len(d)] += d
    fade = RATE // 50
    mix[-fade:] *= np.linspace(1, 0, fade)
    pcm = to_pcm(mix)
    lead = max(0, round(PAN_LEAD_FRAMES * RATE / 60.0988) - PREFILL * CHUNK_SAMPLES)
    total = (lead + len(pcm) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES * CHUNK_SAMPLES + CHUNK_SAMPLES
    out = np.zeros(total, dtype=np.int64)
    out[lead:lead + len(pcm)] = pcm
    return encoded_pcm(out, cache_dir, "title_intro")


def menu_samples(sound_dir, cache_dir):
    """[(id, BRR bytes ending in an END block, pitch, octave, note, ticks)]."""
    out = []
    for sid, name, seconds, key in MENU_SFX:
        pitch = SFX_PITCH[key]
        rate, x = read_wav(os.path.join(sound_dir, name))
        loud = np.flatnonzero(np.abs(x) > 0.003 * np.abs(x).max())
        x = x[loud[0]:loud[0] + round(seconds * rate)]
        to = pitch * 32000 / 4096
        y = resampled(x, rate, to)
        fade = min(len(y), round(to * 0.06))
        y[-fade:] *= np.linspace(1, 0, fade) ** 2
        y = np.concatenate([y, np.zeros(-len(y) % 16)])
        data = bytearray(encoded_pcm(to_pcm(y), cache_dir, f"sfx_{sid}"))
        data[-9] |= 1                       # END without loop: the voice stops by itself
        ticks = int(np.ceil(len(y) / to * 1000 / SFX_TICK_MS)) + 2
        if ticks > 255:
            raise ValueError(f"{name}: too long for one SFX note")
        out.append((sid, bytes(data), pitch, key[0], key[1], ticks))
    return out


def _blocks(rom, addr):
    """Hudson upload list at a ROM address: [(ARAM address, data)]."""
    out = []
    while True:
        ln, dest = struct.unpack_from("<HH", rom, off(addr))
        if ln == 0:
            return out
        out.append((dest, bytes(rom[off(addr) + 4:off(addr) + 4 + ln])))
        addr += 4 + ln


def _list(blocks, tail=b""):
    return b"".join(struct.pack("<HH", len(d), a) + d for a, d in blocks) + b"\x00\x00" + tail


def song_table(rom):
    """One byte per song: 1 = the SB6 menu SFX samples survive while it plays
    (its samples end below SFX_BASE and its header sets an echo delay <= 4,
    so the echo buffer starts at $DD00 or above); 2 = its own samples cover
    the SFX tables ($4400-$46FF: the boot jingle, loaded before any set), so
    SB5's definitions must not be written back over them."""
    safe = bytearray(N_SONGS + 1)
    for song in range(N_SONGS):
        rec = 0xDA0000 | struct.unpack_from("<H", rom, off(SONG_TABLE + 2 * song))[0]
        end, a = struct.unpack_from("<H", rom, off(rec + 2))[0], rec + 4
        start = end
        while rom[off(a)] != 0xFF:
            end += struct.unpack_from("<H", rom, off(SAMPLE_SIZES + 2 * rom[off(a)]))[0]
            a += 1
        if start < 0x4700 and end > 0x4400:
            safe[song] = 2
            continue
        t = off(SET_TABLE + 3 * (0x27 + song))
        p = int.from_bytes(rom[t:t + 3], "little")
        if p >> 16 < 0xC0:
            continue
        seqs = [b for b in _blocks(rom, p) if b[0] == 0x3000]
        if not seqs:
            continue
        base, data = seqs[0]
        # header ops (driver $1398): 00 end, 01 mask + track pointers, 02 n, 03 n + 4n, 04 n + 4n,
        # 05/06/09 n + 2n, 07 echo (0 + volumes, EDL, feedback, FIR, flags; else defaults: EDL 1), 08 n
        i, edl = struct.unpack_from("<H", data, 2)[0] - base, None
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
                    raise IndexError
        except IndexError:
            continue
        if edl is not None and edl <= 4 and end <= SFX_BASE:
            safe[song] = 1
    return bytes(safe)


def menu_sfx_lists(rom, samples):
    """Hudson upload lists: the samples with their directory and tuning
    entries, the SB6 definitions of the three SFX, SB5's own definitions."""
    set1 = _blocks(rom, int.from_bytes(rom[off(SET_TABLE + 3):off(SET_TABLE + 6)], "little"))
    by_addr = {a: d for a, d in set1}
    table, inst, _ = struct.unpack("<HHH", by_addr[0x4400])
    ptrs = [p for p, in struct.iter_unpack("<H", by_addr[table]) if p]
    seq_base, seq = next((a, d) for a, d in set1 if a <= ptrs[0] < a + len(d))
    if inst + 4 * (SFX_INST + len(samples)) > 0x4550 or by_addr[0xFE80][:4] != bytes.fromhex("04 0C 00 CE"):
        raise RuntimeError("Hudson's common SFX set is not laid out as expected")
    tuning = by_addr[0xFE80][:4]
    blob, dirs, new, orig, instruments = bytearray(), [], [], [], bytearray()
    for k, (sid, data, pitch, octave, note, ticks) in enumerate(samples):
        start = SFX_BASE + len(blob)
        blob += data
        dirs.append((0xFD00 + 4 * SFX_DIRS[k], struct.pack("<HH", start, start)))
        dirs.append((0xFE00 + 4 * SFX_DIRS[k], tuning))
        if sid in STREAM_ONLY:
            continue
        instruments += bytes([SFX_DIRS[k], 0xFF, 0xE0, 0xA0])
        p = ptrs[sid - 1]
        room = min([q for q in ptrs if q > p] + [seq_base + len(seq)]) - p
        d = bytes([0x01, (p + 3) & 0xFF, (p + 3) >> 8,       # one track on SFX channel 0
                   0xD1, 0x00,                               # explicit note lengths
                   0xDD, SFX_INST + k, 0xD2, octave, 0xD8, SFX_PAN, 0xD6, SFX_VOL,
                   note << 4, ticks, 0xD0])
        if len(d) > room:
            raise RuntimeError("SFX definition does not fit over SB5's")
        new.append((p, d))
        orig.append((p, seq[p - seq_base:p - seq_base + len(d)]))
    if SFX_BASE + len(blob) > SFX_END:
        raise RuntimeError(f"menu SFX samples: {len(blob)} bytes, {SFX_END - SFX_BASE} fit")
    l_samples = _list([(SFX_BASE, bytes(blob))] + dirs)
    l_new = _list([(inst + 4 * SFX_INST, bytes(instruments))] + new)
    return l_samples, l_new, _list(orig), len(blob)


def chunk_positions(first_bank, count):
    """(bank, offset) of chunks 0..count (count = the position after the last)."""
    pos, bank, o = [], first_bank, 0
    for _ in range(count + 1):
        pos.append((bank, o))
        o += CHUNK
        if o > BANK_LIMIT:
            bank, o = bank + 1, 0
    return pos


def sfx_tables(samples, cache_dir):
    """Builds the driver's SFX scripts and the CPU's id -> slot table.

    Script format (asm/spc/stream.asm): pairs (DSP reg, value); $FE n = wait
    n * 4 ms; $FF = end. A script keys voice 0 off, waits, then sets the
    sample (an index in the driver's directory, copied from Hudson's entry),
    ADSR, pitch and volume and keys it on; the sample ends by itself."""
    if len(samples) > min(MAX_SLOTS, MAX_SRC):
        raise ValueError("too many SFX")
    srcs, scripts = [], []
    for k, (sid, _, pitch, _, _, _) in enumerate(samples):
        srcs.append(SFX_DIRS[k])
        scripts.append(bytes([0x5C, 0x01, 0xFE, 0x02,
                              0x04, k + 1, 0x05, 0xFF, 0x06, 0xE0, 0x02, pitch & 0xFF, 0x03, pitch >> 8,
                              0x00, STREAM_SFX_VOL, 0x01, STREAM_SFX_VOL, 0x5C, 0x00, 0x4C, 0x01,
                              0xFE, 0x02, 0xFF]))
    ids = [smp[0] for smp in samples]
    head = bytes([len(srcs)]) + bytes(srcs).ljust(MAX_SRC, b"\x00")
    offsets, pos = bytearray(), len(head) + 2 * MAX_SLOTS
    for sc in scripts:
        offsets += pos.to_bytes(2, "little")
        pos += len(sc)
    blob = head + bytes(offsets).ljust(2 * MAX_SLOTS, b"\x00") + b"".join(scripts)
    slots = bytearray(32)
    for k, sid in enumerate(ids):
        slots[sid] = k + 1
    os.makedirs(cache_dir, exist_ok=True)
    bin_path = os.path.join(cache_dir, "title_sfx_scripts.bin")
    slot_path = os.path.join(cache_dir, "title_sfx_slots.bin")
    with open(bin_path, "wb") as fh:
        fh.write(blob)
    with open(slot_path, "wb") as fh:
        fh.write(bytes(slots))
    return bin_path, slot_path, ids


def _h(v, digits):
    return f"${v:0{digits}X}"


def place_chunks(rb, regions, data, label):
    """Allocates whole chunks of `data` in the regions, in order, never across
    a bank; returns the segments [(bank, first offset, end offset)]."""
    segs, done = [], 0
    for name in regions:
        if done == len(data):
            break
        r = rb.regions[name]
        o = r.cursor & 0xFFFF
        room = (min(r.end, (r.cursor & ~0xFFFF) + 0xFFFF) - r.cursor) // CHUNK
        k = min(room, (len(data) - done) // CHUNK)
        if k <= 0:
            continue
        addr = rb.alloc(name, data[done:done + k * CHUNK], f"{label}: BRR chunks {done // CHUNK}-{done // CHUNK + k - 1}")
        segs.append((addr >> 16, o, o + k * CHUNK))
        done += k * CHUNK
    if done != len(data):
        raise RuntimeError(f"{label}: {len(data) - done} bytes do not fit in {regions}")
    return segs


def segment_table(tracks):
    """tracks = [(segments, loop index)] -> (bytes, offset of each track)."""
    out, starts = bytearray(), []
    for segs, loop in tracks:
        first = len(out)
        starts.append(first)
        for b, lo, hi in segs:
            assert b and 0 <= lo < hi <= 0xFFFF and (hi - lo) % CHUNK == 0
            out += struct.pack("<BHH", b, lo, hi)
        out += struct.pack("<BHH", 0, first + 5 * loop, 0)
    return bytes(out), starts


def apply(rb, wav, sound_dir, cache_dir, game_sfx, first_bank=0xE5, drop_frames=(), save_wav=None,
          save_regions=(), sb1=None):
    """sound_dir holds title_pan.wav, title_drop.wav and the menu SFX;
    drop_frames = frames of the intro (from the pan's first) where a wave of
    characters starts to fall; game_sfx = the symbols of asm/game_sfx.asm
    (in-game SFX, called from the hooks here); save_wav = the save file menu
    music, streamed at SAVE_RATE in save_regions (after the title's own
    banks), as loud (RMS) as the title music."""
    # Hudson's loader (uploaded at boot) must hold the RET the driver hooks.
    o = off(HUDSON_LOADER)
    if rb.d[o + 3:o + 9] != bytes.fromhex("8F AA F4 8F BB F5") or rb.d[o + 0x51:o + 0x54] != bytes.fromhex("6F CD 01"):
        raise RuntimeError("Hudson loader not where expected (ARAM $0FF0 image)")
    if rb.d[off(RTL_C0)] != 0x6B:
        raise RuntimeError("no RTL where the bank $C0 calls expect it")
    samples = menu_samples(sound_dir, cache_dir)
    l_samples, l_new, l_orig, sample_bytes = menu_sfx_lists(rb.d, samples)
    safe = song_table(rb.d)
    stream = encoded_stream(wav, cache_dir)
    n = len(stream) // CHUNK
    pos = chunk_positions(first_bank, n)

    # Stream data: one region per bank, filled up to the last whole chunk.
    banks = sorted({b for b, _ in pos[:n]})
    title_segs = []
    for b in banks:
        rb.add_region(f"audio_{b:02X}", b << 16, (b + 1) << 16,
                      "streamed BRR audio (title music)")
        idx = [i for i in range(n) if pos[i][0] == b]
        data = stream[idx[0] * CHUNK:(idx[-1] + 1) * CHUNK]
        addr = rb.alloc(f"audio_{b:02X}", data, f"title music BRR chunks {idx[0]}-{idx[-1]}")
        assert addr == b << 16 | pos[idx[0]][1]
        title_segs.append((b, pos[idx[0]][1], pos[idx[-1]][1] + CHUNK))

    # Save file menu music: same loudness (RMS) as the title music, through
    # the S-DSP volumes (the samples are normalized to the same peak).
    save_vol, save_mvol, save_segs, save_seconds, save_gain = VOL, MVOL, [], 0.0, 1.0
    if save_wav:
        save_pcm = to_pcm(loop_pcm(save_wav, SAVE_RATE))
        save_gain = rms(load_pcm(wav)) / rms(save_pcm)
        level = VOL * MVOL * save_gain
        save_mvol = min(0x7F, max(MVOL, round(level / VOL)))
        save_vol = min(0x7F, round(level / save_mvol))
        save = encoded_pcm(save_pcm, cache_dir, "save_music")
        save_seconds = len(save_pcm) / SAVE_RATE

    # Driver image uploaded to ARAM $7000: driver pages + first chunks. The
    # driver is sized first (asar pass with a large area), then the ring
    # takes every whole chunk up to the end of the title song area.
    sfx_bin, sfx_slots, sfx_ids = sfx_tables(samples, cache_dir)
    def rate_defs(rate, vol, mvol):
        return dict(PITCH=_h(round(rate * 4096 / 32000), 4), TIMER0=round(8000 * CHUNK_SAMPLES / rate),
                    VOL=_h(vol, 2), MVOL=_h(mvol, 2))

    spc_defs = dict(BASE=_h(ARAM_BASE, 4), PREFILL=PREFILL, SFX_BIN=sfx_bin.replace("\\", "/"))
    _, syms = asar.assemble_blob(ASM_SPC, 0x2000, dict(spc_defs, DRIVER_SIZE="$1000", CHUNKS=1,
                                                       **rate_defs(RATE, VOL, MVOL)))
    driver_size = (syms["end"] - ARAM_BASE + 0xFF) & ~0xFF
    ring_chunks = (RING_LIMIT - ARAM_BASE - driver_size) // CHUNK
    spc_defs.update(DRIVER_SIZE=_h(driver_size, 4), CHUNKS=ring_chunks)
    driver, _ = asar.assemble_blob(ASM_SPC, driver_size, dict(spc_defs, **rate_defs(RATE, VOL, MVOL)))
    save_driver, _ = asar.assemble_blob(ASM_SPC, driver_size,
                                        dict(spc_defs, **rate_defs(SAVE_RATE, save_vol, save_mvol)))
    # The prefill is silence: the stream that follows is the music or the intro's pan sound.
    silent = brr.encode(np.zeros(CHUNK_SAMPLES, dtype=np.int64))
    blob = driver + silent * PREFILL
    pan = intro_stream(os.path.join(sound_dir, "title_pan.wav"), os.path.join(sound_dir, "title_drop.wav"),
                       list(drop_frames), cache_dir)
    if pan[-CHUNK:] != silent:
        raise RuntimeError("the intro sounds must end in a silent chunk")
    pan_addr = rb.alloc(PAN_REGION, pan, "title intro: pan + character drop sounds, BRR chunks (the last one is silence)")
    if pan_addr & 0xFFFF or len(pan) > 0xFFFF:
        raise RuntimeError("the intro sounds must start their bank and fit in it")
    pan_segs = [(pan_addr >> 16, 0, len(pan) - CHUNK), (pan_addr >> 16, len(pan) - CHUNK, len(pan))]
    if save_wav:
        save_segs = place_chunks(rb, [f"audio_{banks[-1]:02X}"] + list(save_regions), save, "save file menu music")
    segs_bin, seg_starts = segment_table([(pan_segs, 1), (title_segs, 0), (save_segs or title_segs, 0)])
    segs_path = os.path.join(cache_dir, "stream_segs.bin")
    with open(segs_path, "wb") as fh:
        fh.write(segs_bin)
    entry = ARAM_BASE + 4
    jmp_entry = (0x1041, bytes([0x5F, entry & 0xFF, entry >> 8]))
    l_stream = _list([(ARAM_BASE, blob), jmp_entry], struct.pack("<H", entry))
    blob_addr = rb.alloc("bulk", l_stream, "title music: upload list = SPC stream driver + prefill (ARAM $7000), "
                         "JMP entry over the loader's RET")
    l_save = _list([(ARAM_BASE, save_driver + silent * PREFILL), jmp_entry], struct.pack("<H", entry))
    save_addr = rb.alloc("bulk", l_save, "save menu music: upload list = SPC stream driver at 12 kHz + prefill")
    samples_addr = rb.alloc("bulk", l_samples, "menu SFX: upload list = 3 BRR samples (ARAM $B900), directory "
                            "and tuning entries $39-$3B")
    new_addr = rb.alloc("bulk", l_new, "menu SFX: upload list = instruments 28-30 and SB6 definitions of SFX 1, 4, 3")
    orig_addr = rb.alloc("bulk", l_orig, "menu SFX: upload list = SB5's definitions of SFX 1, 4, 3")
    safe_addr = rb.alloc("bulk", safe, "menu SFX: songs that leave the samples alone (1 byte each, then 0)")

    # CPU code.
    region = rb.regions["bulk"]
    code_addr = region.cursor
    cpu_defs = dict(CODE=_h(code_addr, 6), CODE_END=_h(region.end, 6),
                    ENTRY=_h(entry, 4), L_STREAM=_h(blob_addr, 6), L_SAMPLES=_h(samples_addr, 6),
                    L_NEW=_h(new_addr, 6), L_ORIG=_h(orig_addr, 6), SFX_SAFE=_h(safe_addr, 6),
                    NSONGS=N_SONGS, SONG_TABLE=_h(SONG_TABLE, 6), RTL_C0=_h(RTL_C0, 6),
                    L_SAVE=_h(save_addr, 6), SEGS=segs_path.replace("\\", "/"),
                    SEG_PRE=_h(seg_starts[0], 4), SEG_TITLE=_h(seg_starts[1], 4), SEG_SAVE=_h(seg_starts[2], 4),
                    SAVE_SET=_h(SAVE_SET if save_wav else 0xFF, 2), SAVE_MODE=_h(SAVE_MODE, 2),
                    SFX_SLOTS=sfx_slots.replace("\\", "/"),
                    **((sb1 or {}).get("defs") or {"FD": "0"}),
                    **{f"GS_{k.upper()}": _h(game_sfx[f"gs_{k}"], 6) for k in ("sound", "tick", "set", "song")})
    runs, syms = asar.assemble_into(rb.d, ASM_CPU, cpu_defs)
    lo, hi = off(code_addr), off(syms["end"])
    for o, data in runs:
        if o < lo or o + len(data) > hi:
            raise RuntimeError(f"title_music.asm wrote outside its allocation at file offset {o:06X}")
    code = bytearray(rb.d[lo:hi])
    for o, data in runs:
        code[o - lo:o - lo + len(data)] = data
    if rb.alloc("bulk", bytes(code), "title music: CPU hooks, uploader, feeder") != code_addr:
        raise RuntimeError("code allocation moved")

    def jml(a):
        return bytes([0x5C, a & 0xFF, a >> 8 & 0xFF, a >> 16])

    rb.patch(0xC00CED, bytes.fromhex("85 9F EB C9 10"), jml(syms["sound_hook"]) + b"\xEA",
             "sound API: title music stream hook")
    rb.patch(0xC00B2C, bytes.fromhex("AD BF 03 D0 04"), jml(syms["loop_hook"]) + b"\xEA",
             "main loop: title music feeder")

    def jsl(a):
        return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16])

    rb.patch(0xC00E58, bytes.fromhex("20 62 0F 20 35 0F"), jsl(syms["set_hook"]) + b"\xEA\xEA",
             "sample set upload: SB6 menu SFX definitions again after it")
    rb.patch(0xC00F0A, bytes.fromhex("20 35 0F 9C D1 03"), jsl(syms["song_hook"]) + b"\xEA\xEA",
             "song upload: SB6 menu SFX samples and definitions when the song leaves them room")
    seconds = n * CHUNK_SAMPLES / RATE
    return dict(seconds=seconds, bytes=len(stream), banks=banks, code=len(code), driver=len(driver),
                ring=ring_chunks, sfx=sfx_ids, pre_start=syms["pre_start"], pan=len(pan),
                sfx_bytes=sample_bytes, safe=[i for i in range(N_SONGS) if safe[i] == 1],
                save_seconds=save_seconds, save_segs=save_segs, save_gain=save_gain,
                save_vol=(save_vol, save_mvol), map_music=syms.get("map_music", 0))
