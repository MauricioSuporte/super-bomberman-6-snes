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
  * Menu SFX are silent while the stream plays (the stream owns port 0).
"""
import hashlib
import os
import wave

import numpy as np

from .. import asar, brr
from ..romlib import off

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ASM_CPU = os.path.join(ROOT, "asm", "title_music.asm")
ASM_SPC = os.path.join(ROOT, "asm", "spc", "stream.asm")

RATE = 16000              # pitch $0800
CHUNK = 162               # bytes: 18 BRR blocks
CHUNK_SAMPLES = 18 * 16
ARAM_BASE = 0x7000        # driver page; ring right after it
RING_CHUNKS = 148         # ring $7200-$CEA7 (title song area ends at $CFDF)
DRIVER_SIZE = 0x200
PREFILL = 8               # chunks uploaded with the driver (144 ms)
PEAK = 0.89               # -1 dBFS before BRR
VOL, MVOL = 0x70, 0x60     # MVOL as Hudson uses on the SB5 title; one voice carries the whole mix
HUDSON_LOADER = 0xDF2B3A  # ROM image of ARAM $0FF0 (Hudson's loader); $1041 = RET
BANK_LIMIT = 0x10000 - CHUNK  # the feeder moves to the next bank past this offset


def load_pcm(path):
    from scipy.signal import resample_poly
    with wave.open(path) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: need 16-bit PCM")
        ch, rate = w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64)
    x = x.reshape(-1, ch).mean(1)
    g = np.gcd(RATE, rate)
    y = resample_poly(x, RATE // g, rate // g)
    y *= PEAK * 32767 / max(1.0, np.abs(y).max())
    n = len(y) // CHUNK_SAMPLES * CHUNK_SAMPLES
    return np.rint(y[:n]).astype(np.int64)


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


def chunk_positions(first_bank, count):
    """(bank, offset) of chunks 0..count (count = the position after the last)."""
    pos, bank, o = [], first_bank, 0
    for _ in range(count + 1):
        pos.append((bank, o))
        o += CHUNK
        if o > BANK_LIMIT:
            bank, o = bank + 1, 0
    return pos


def _h(v, digits):
    return f"${v:0{digits}X}"


def apply(rb, wav, cache_dir, first_bank=0xE5):
    # Hudson's loader (uploaded at boot) must hold the RET the driver hooks.
    o = off(HUDSON_LOADER)
    if rb.d[o + 3:o + 9] != bytes.fromhex("8F AA F4 8F BB F5") or rb.d[o + 0x51:o + 0x54] != bytes.fromhex("6F CD 01"):
        raise RuntimeError("Hudson loader not where expected (ARAM $0FF0 image)")
    stream = encoded_stream(wav, cache_dir)
    n = len(stream) // CHUNK
    pos = chunk_positions(first_bank, n)

    # Stream data: one region per bank, filled up to the last whole chunk.
    banks = sorted({b for b, _ in pos[:n]})
    for b in banks:
        rb.add_region(f"audio_{b:02X}", b << 16, (b + 1) << 16,
                      "streamed BRR audio (title music)")
        idx = [i for i in range(n) if pos[i][0] == b]
        data = stream[idx[0] * CHUNK:(idx[-1] + 1) * CHUNK]
        addr = rb.alloc(f"audio_{b:02X}", data, f"title music BRR chunks {idx[0]}-{idx[-1]}")
        assert addr == b << 16 | pos[idx[0]][1]

    # Driver image uploaded to ARAM $7000: driver pages + first chunks.
    spc_defs = dict(BASE=_h(ARAM_BASE, 4), CHUNKS=RING_CHUNKS, PREFILL=PREFILL,
                    VOL=_h(VOL, 2), MVOL=_h(MVOL, 2))
    driver = asar.assemble_blob(ASM_SPC, DRIVER_SIZE, spc_defs)
    blob = driver + stream[:PREFILL * CHUNK]
    blob_addr = rb.alloc("bulk", blob, "title music: SPC stream driver + prefill (ARAM $7000)")

    # CPU code.
    region = rb.regions["bulk"]
    code_addr = region.cursor
    cpu_defs = dict(CODE=_h(code_addr, 6), CODE_END=_h(region.end, 6),
                    BASE=_h(ARAM_BASE, 4), ENTRY=_h(ARAM_BASE + 4, 4),
                    BLOB=_h(blob_addr, 6), BLOB_SIZE=_h(len(blob), 4),
                    START_BANK=_h(pos[PREFILL][0], 2), START_OFF=_h(pos[PREFILL][1], 4),
                    LOOP_BANK=_h(pos[0][0], 2), LOOP_OFF=_h(pos[0][1], 4),
                    END_BANK=_h(pos[n][0], 2), END_OFF=_h(pos[n][1], 4))
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
    seconds = n * CHUNK_SAMPLES / RATE
    return dict(seconds=seconds, bytes=len(stream), banks=banks, code=len(code), driver=len(driver))
