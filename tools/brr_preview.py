#!/usr/bin/env python3
"""Decodes a BRR stream to a WAV so the conversion can be heard without an emulator.

    python tools/brr_preview.py build/cache/title_music_*.brr build/title_music_preview.wav [rate]

The S-DSP's Gaussian interpolation is not modelled (the real output is a bit
duller in the highs)."""
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb6 import brr  # noqa: E402


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rate = int(sys.argv[3]) if len(sys.argv) > 3 else 16000
    with open(src, "rb") as fh:
        pcm = brr.decode(fh.read())
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(pcm, -32768, 32767).astype("<i2").tobytes())
    print(f"wrote {dst} ({len(pcm) / rate:.1f} s)")


if __name__ == "__main__":
    main()
