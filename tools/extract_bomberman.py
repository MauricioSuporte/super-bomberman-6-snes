"""Extracts the editable Bomberman sprite sheet and palettes.

    python tools/extract_bomberman.py ROM.sfc [--out assets/bomberman]

Works on the base ROM or a built Super Bomberman 6 (the hack does not move
them). build.py re-encodes the PNGs and patches only what changed.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb6.features import bomberman_sprites  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("rom")
ap.add_argument("--out", default=os.path.join(ROOT, "assets", "bomberman"))
args = ap.parse_args()
with open(args.rom, "rb") as fh:
    bomberman_sprites.extract(fh.read(), args.out)
print(f"wrote {args.out}/sheet.png and palettes.png")
