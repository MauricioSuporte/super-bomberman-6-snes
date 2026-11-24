"""World 1's portal sound (asm/world1.asm portal_task): candidate 2 of build/sb1sfx/compose.py ("Eco de sino"),
Super Bomberman 1's bell (its sample $06, as SB1's SFX $01 / $0E / $02 use it: SB1 pitch $1000, ADSR DD 94, GAIN 9E)
playing a fifth (0 for 3 ticks, +7 for 9 ticks) four times, quieter each time as SB1's echo ($01: S-DSP volume
$7E, $4F, $2C, $18).

Hudson SFX CMD ($62: SB5 points $61-$66 at a dummy; $61 is the crowd's). The bell is already in ARAM in every
stage that has the portal (1-1 to 1-5 play SB1 songs that use sample $06, features/sb1_music.py uploads it), so the
sound costs no sample bytes: its track goes in each of those songs' upload lists (sb1_music.build, `portal`), and
a list per stage (`entries`: SFX pointer, instrument INST, directory entry SRC = that stage's bell, tuning) is sent
by asm/game_sfx.asm after every set or song upload while the stage is one of them (game_sfx's PORTAL table,
filled by sb1_music.apply); the priority goes in game_sfx's own patch list (the stage SFX sets rewrite it).
"""
import struct

from . import sb1_music

CMD = 0x62
INST = 30                   # instrument entry no set writes (only whole-ARAM uploads; resent after each)
SRC = 0x3B                  # directory entry no set writes (same)
CHANNEL = 0x04              # SB1's enemy death's SFX channel (no enemy is left when the portal comes)
PRIO = 0x06
PAN = 0x0F
ADSR = (0xDD, 0x94, 0x9E)   # SB1's bell SFX
BELL = 0x06                 # SB1 sample (assets/sound/sb1_stage_*.bin)
SB1_PITCH = 0x1000          # the bell's pitch in SB1's SFX
NOTE0 = 48                  # Hudson note that plays SB1_PITCH (tuning MULT)
SFX_PITCH24, BASE_MULT = 1011.0, 0x040C   # SFX note 24 with tuning "04 0C 00 CE" (game_sfx.hudson_pitch)
MULT = round(BASE_MULT * SB1_PITCH / (SFX_PITCH24 * 2 ** ((NOTE0 - 24) / 12)))
STAGES = (0x0D, 0x11, 0x18, 0x10, 0x17)
# (semitones, ticks) of one figure, and SB1's S-DSP volume of each repeat
FIGURE = [(0, 3), (7, 9)]
ECHO_VOLS = [0x7E, 0x4F, 0x2C, 0x18]


def hudson_vol(dsp):
    """Hudson volume (centered pan) whose S-DSP level is closest to SB1's, scaled so $7E = the loudest."""
    top = sb1_music.VOL[0x4F]
    want = dsp / 0x7E * top
    return min(range(0x50), key=lambda v: abs(sb1_music.VOL[v] - want))


def _note(n):
    return (n // 12, n % 12) if n % 12 else (n // 12 - 1, 12)


def sequence(addr):
    """Hudson SFX at ARAM addr: [channel mask, track pointer], then the track."""
    t = bytearray([0xD1, 0x00, 0xDD, INST, 0xD8, PAN])
    octave = None
    for dsp in ECHO_VOLS:
        t += bytes([0xD6, hudson_vol(dsp)])
        for semis, ticks in FIGURE:
            o, k = _note(NOTE0 + semis)
            if o != octave:
                t += bytes([0xD2, o])
                octave = o
            t += bytes([k << 4, ticks])
    t.append(0xD0)
    return bytes([CHANNEL, (addr + 3) & 0xFF, (addr + 3) >> 8]) + bytes(t)


def entries(seq_addr, bell_dir):
    """Upload list blocks of one stage: bell_dir = the bell's directory entry there (start, loop)."""
    return [(0x4410 + 2 * (CMD - 0x21), struct.pack("<H", seq_addr)),
            (0x44D0 + 4 * INST, bytes([SRC]) + bytes(ADSR)),
            (0xFD00 + 4 * SRC, bytes(bell_dir)),
            (0xFE00 + 4 * SRC, struct.pack(">H", MULT) + bytes([0x00, 0xCE]))]


def prio():
    return (0x4550 + (CMD - 0x21), bytes([PRIO]))
