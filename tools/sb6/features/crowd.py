"""The crowd (the SB6 fan game's Audience sound) as Hudson SFX !CMD, when 1-6's white or black mecha dies.

assets/sound/audience.wav (from the fan game's Assets/Sounds/Audience.mp3, 3.3 s, loud for its first 1.75 s)
is cut where it falls under QUIET of its peak (faded out over FADE s), resampled to RATE Hz and BRR-encoded,
played once (no loop). Its ~18 KB do not fit game_sfx's R, so it is part of 1-6's music upload list (features/sb1_music.py, songs
in SONGS), in two pieces around the cornered sound's part B (layout()), and
asm/game_sfx.asm sends the table entries (patch(): SFX pointer, priority, instrument, directory and tuning)
after every set or song upload while the stage is 1-6's ($1031 = STAGE). World 1's asm (rival_sfx) asks for it
when the white or black mecha dies, instead of the death sound.
"""
import os
import struct

import numpy as np

from ..rombuild import BuildError
from . import title_music as tm

CMD = 0x61                  # SFX pointer table entry $40 ($61-$66 point at a dummy in SB5)
INST = 29                   # instrument no SFX of 1-6's set uses (garbage there)
SRC = 0x3E                  # directory entry nothing else uses
PRIO, CHANNEL, VOL, PAN = 0x1F, 0x01, 0x4F, 0x0F     # as SB1's death (game_sfx): its SFX channel
ADSR = (0xFF, 0xE0, 0x9E)   # full volume while held (the recording has its own envelope), fast release
RATE = 8000                 # Hz: ~14.7 KB for the 2.8 s kept (what fits around B in 1-6)
QUIET, FADE = 0.012, 0.25
NOTE = 32                   # Hudson note; the tuning entry plays the sample at RATE
BASE_MULT = 0x040C          # SFX tuning "04 0C 00 CE": note n = 1011 * 2^((n - 24) / 12)
SONGS = ("w5m",)
HIGH_LO, HIGH_HI = 0xDD00, 0xF500   # above game_sfx's part B (SB5's echo buffer), up to the SB1 lists' echo buffer
_memo_seconds = 0.0
STAGE = 0x67
CACHE = os.path.join(tm.ROOT, "build", "cache")
_memo = {}


def _sample(sound_dir):
    if sound_dir in _memo:
        return _memo[sound_dir]
    rate, x = tm.read_wav(os.path.join(sound_dir, "audience.wav"))
    loud = np.flatnonzero(np.abs(x) > QUIET * np.abs(x).max())
    x = x[loud[0]:loud[-1] + 1].astype(np.float64)
    y = tm.resampled(x, rate, RATE)
    fade = min(len(y), round(RATE * FADE))
    y[-fade:] *= np.linspace(1, 0, fade) ** 2
    y = np.concatenate([y, np.zeros(-len(y) % 16)])
    os.makedirs(CACHE, exist_ok=True)
    data = bytearray(tm.encoded_pcm(tm.to_pcm(y), CACHE, "crowd"))
    data[-9] = (data[-9] & 0xFC) | 1           # END, no loop
    _memo[sound_dir] = (bytes(data), len(y) / RATE)
    return _memo[sound_dir]


def _seq(at):
    """The SFX sequence at ARAM `at` (one held note, as long as the sample)."""
    ticks = int(np.ceil(_memo_seconds * 1000 / tm.SFX_TICK_MS)) + 2
    if ticks > 255:
        raise BuildError("crowd: too long for one SFX note")
    o, k = (NOTE // 12, NOTE % 12) if NOTE % 12 else (NOTE // 12 - 1, 12)
    track = bytes([0xD1, 0x00, 0xDD, INST, 0xD8, PAN, 0xD6, VOL, 0xE4, 0xD2, o, k << 4, ticks, 0xD0])
    seq = bytes([CHANNEL, (at + 3) & 0xFF, (at + 3) >> 8]) + track
    return seq + (b"\x00" if len(seq) % 2 else b"")


def layout(sound_dir, b_lo):
    """The crowd in two pieces around game_sfx's cornered part B ([b_lo, HIGH_LO), below the SB5 songs'
    echo buffer): sequence + the first part of the sample ending at b_lo (its last block loops into the
    second part), the second part from HIGH_LO up to the SB1 lists' echo buffer.
    -> [(ARAM address, bytes)...], sample start, loop address."""
    global _memo_seconds
    smp, _memo_seconds = _sample(sound_dir)
    room = (HIGH_HI - HIGH_LO) // 9 * 9
    n2 = min(room, len(smp) - 9)
    p1, p2 = bytearray(smp[:len(smp) - n2]), smp[len(smp) - n2:]
    if n2:
        p1[-9] = (p1[-9] & 0xFC) | 3            # END + LOOP: on into the second part
    n_seq = len(_seq(0))
    at = b_lo - n_seq - len(p1)
    blocks = [(at, _seq(at) + bytes(p1))]
    if n2:
        blocks.append((HIGH_LO, bytes(p2)))
    return blocks, at + n_seq, HIGH_LO if n2 else at + n_seq


def patch(sound_dir, b_lo):
    """Table entries for asm/game_sfx.asm (a Hudson upload list's blocks)."""
    blocks, smp, loop = layout(sound_dir, b_lo)
    at = blocks[0][0]
    pitch = RATE * 4096 / 32000
    mult = round(BASE_MULT * pitch / (1011.0 * 2 ** ((NOTE - 24) / 12)))
    return [(0x4410 + 2 * (CMD - 0x21), struct.pack("<H", at)),
            (0x4550 + (CMD - 0x21), bytes([PRIO])),
            (0x44D0 + 4 * INST, bytes([SRC]) + bytes(ADSR)),
            (0xFD00 + 4 * SRC, struct.pack("<HH", smp, loop)),
            (0xFE00 + 4 * SRC, struct.pack(">H", mult) + bytes([0x00, 0xCE]))]
