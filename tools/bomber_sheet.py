#!/usr/bin/env python3
"""Editable pose sheet of the player bomber.

    python tools/bomber_sheet.py export            # writes assets/bombers/bomber_sb5.png (reference)
    python tools/bomber_sheet.py export --edit     # also creates assets/bombers/bomber.png if missing
    python tools/bomber_sheet.py check             # validates assets/bombers/bomber.png

`python tools/build.py` inserts assets/bombers/bomber.png when it exists.
Each cell is one pose, already assembled; the label says which animation it
belongs to and in which order the poses play. Keep the picture size, paint
inside the cells only, transparent (or magenta FF00FF) background.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb6 import bomber  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "assets", "bombers")
SHEET = os.path.join(DIR, "bomber.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "check"])
    ap.add_argument("--base", default=os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"))
    ap.add_argument("--edit", action="store_true", help="export: also create bomber.png (never overwrites)")
    ap.add_argument("--sheet", default=SHEET)
    args = ap.parse_args()
    with open(args.base, "rb") as fh:
        rom = fh.read()
    br = bomber.BomberRom(rom)

    if args.command == "export":
        os.makedirs(DIR, exist_ok=True)
        im = bomber.export_sheet(br, 0, "SUPER BOMBERMAN 5 - Bomberman (jogador) - folha de poses")
        ref = os.path.join(DIR, "bomber_sb5.png")
        im.save(ref)
        print(f"wrote {ref}")
        if args.edit:
            if os.path.exists(args.sheet):
                print(f"{args.sheet} already exists, not overwritten")
            else:
                im.save(args.sheet)
                print(f"wrote {args.sheet}")
        return

    sb6, pal = os.path.join(DIR, "bomber_sb6.png"), os.path.join(DIR, "BombermanPallete.png")
    if args.sheet == SHEET and os.path.exists(sb6) and os.path.exists(pal):
        anims = os.path.join(DIR, "bomber_anims.txt")
        if os.path.exists(anims):
            br = bomber.BomberRom(rom, bomber.load_scripts(anims))
            print(f"bomber_anims.txt: {len(br.scripts)} animations with their own sequence")
        cells, _, n = bomber.read_sheet_recolor(br, sb6, pal)
        inexact = n["snapped"]
        print(f"bomber_sb6.png: {n['edited']} edited poses, {n['legacy']} still SB5 art, {n['colors']} of 15 colors"
              f" ({len(n['fixed'])} not in the palette picture: {', '.join('%02X%02X%02X' % c for c in n['fixed'])})")
    else:
        cells, inexact = bomber.read_sheet(br, args.sheet)
    strips, anim_strip, mappings = bomber.convert(br, cells)
    pieces = [len(p) for p in mappings.values()]
    print(f"ok: {len(mappings)} poses, {len(strips)} strips ({len(strips)} KB of tiles), "
          f"{max(pieces)} sprites in the largest pose, {sum(pieces) / len(pieces):.1f} on average")
    if inexact:
        print(f"warning: {inexact} pixels are not palette colors (nearest color used)")


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
