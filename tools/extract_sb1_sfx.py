#!/usr/bin/env python3
"""Copies the samples of two Super Bomberman (USA) sounds into assets/sound.

    python tools/extract_sb1_sfx.py "Super Bomberman (USA).sfc"

Super Bomberman 1 plays its SFX with sound command $1F (player death) and
$16 (enemy death), both on voice 0 with ADSR $DF/$94 (seen in Mesen with a
log of the S-DSP writes, tools/spc_render.py turns such a log into a WAV):

  * player death: sample 0 (ARAM $2334, a long looped sample; only its start
    is heard), 8 key-ons alternating pitch $09C4 and $05DC, 61/96 ms apart;
  * enemy death: sample $0B (ARAM $ACF8, 774 bytes, no loop), one key-on at
    pitch $04B0.

The build (tools/sb6/features/game_sfx.py) rebuilds them as Hudson SFX of the
SB5 driver from these BRR files: sb1_death.brr (the first DEATH_BLOCKS blocks
of sample 0, the rest is never reached) and sb1_enemy.brr.
"""
import hashlib
import os
import sys

SHA1 = "5b99127cb3c60c5ebce11d9b91bd09914ebc53f2"
DEATH = (0x048EE4, 96 * 9)      # file offset, bytes (sample 0 of the sound set)
ENEMY = (0x05DFCA, 774)         # sample $0B, ends with an END block
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    rom = open(sys.argv[1], "rb").read()
    if hashlib.sha1(rom).hexdigest() != SHA1:
        sys.exit("not Super Bomberman (USA) (sha1 mismatch)")
    out = os.path.join(ROOT, "assets", "sound")
    for name, (o, n) in (("sb1_death.brr", DEATH), ("sb1_enemy.brr", ENEMY)):
        data = rom[o:o + n]
        if len(data) % 9:
            sys.exit(f"{name}: not whole BRR blocks")
        with open(os.path.join(out, name), "wb") as fh:
            fh.write(data)
        print(f"{name}: {n} bytes from ${o:06X}")


if __name__ == "__main__":
    main()
