#!/usr/bin/env python3
"""Editable pose sheets of the playable characters.

    python tools/bomber_sheet.py export            # writes the *_sb5.png references
    python tools/bomber_sheet.py export --edit     # also creates the editable files that are missing
    python tools/bomber_sheet.py template 3 --force   # char3_sb6.png / char3_pallete.png = Bomberman's again
    python tools/bomber_sheet.py check             # validates the edited sheets

Bomberman: bomber_sb5.png (reference), bomber.png / bomber_sb6.png (edited).
Characters 1-9: char<n>_sb5.png (the cartridge's art, reference only) and
char<n>_sb6.png, laid out exactly like bomber_sb6.png (same animations,
poses and sequences: bomber_anims.txt, overridable per animation in
char<n>_anims.txt) and painted with its colors; char<n>_pallete.png has
BombermanPallete.png's format (column 1 = Bomberman's key colors, the other
columns = the colors chosen with L / R). `python tools/build.py` inserts a
character once something differs from Bomberman's; animations left equal to
his use his tiles.
Each cell is one pose, already assembled; the label says which animation it
belongs to and in which order the poses play. Keep the picture size, paint
inside the cells only, transparent (or magenta FF00FF) background.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb6 import bomber  # noqa: E402
from sb6.features import bombers  # noqa: E402
from sb6.features.bombers import CHARS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "assets", "bombers")
SHEET = os.path.join(DIR, "bomber.png")


def char_files(c):
    return tuple(os.path.join(DIR, f"char{c}{s}") for s in ("_sb5.png", "_sb6.png", "_pallete.png", "_anims.txt"))


def export_chars(rom, edit):
    """char<n>_sb5.png: the cartridge's art of each character (reference, SB5 layout).
    --edit: also the editable char<n>_sb6.png / char<n>_pallete.png that are missing (template)."""
    for c in CHARS:
        br = bomber.BomberRom(rom, None, c)
        variants = bomber.char_palettes(rom, c, 6)
        key = bomber.key_colors(variants[0])
        im = bomber.export_sheet(br, c, f"SUPER BOMBERMAN 5 - personagem {c} - folha de poses (referencia)", key)
        ref = char_files(c)[0]
        im.save(ref)
        print(f"wrote {ref}")
        if edit:
            template(c, force=False)


def template(c, force):
    """char<n>_sb6.png = bomber_sb6.png (same poses, sequences and colors) with
    its own title; char<n>_pallete.png = BombermanPallete.png. Repaint the
    cells that change; untouched animations stay Bomberman's in the game."""
    _, sheet, pal, _ = char_files(c)
    src, src_pal = os.path.join(DIR, "bomber_sb6.png"), os.path.join(DIR, "BombermanPallete.png")
    for path, make in ((sheet, lambda: _titled(src, f"SUPER BOMBERMAN 6 - personagem {c} - folha de poses (layout do "
                                                    f"bomber_sb6.png)")),
                       (pal, lambda: Image.open(src_pal).convert("RGB"))):
        if os.path.exists(path) and not force:
            print(f"{path} already exists, not overwritten (--force)")
            continue
        make().save(path)
        print(f"wrote {path}")


def _titled(path, title):
    im = Image.open(path).convert("RGBA")
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 0, im.width - 1, 16), fill=(24, 28, 40, 255))
    dr.text((6, 4), title, fill=(255, 255, 255, 255))
    return im


def relabel(rom):
    """Rewrites the label column of bomber_sb6.png and char<n>_sb6.png with the
    current sequences (bomber_anims.txt, char<n>_anims.txt); the art is kept."""
    anims = os.path.join(DIR, "bomber_anims.txt")
    base = bomber.load_scripts(anims) if os.path.exists(anims) else {}
    paths = [(os.path.join(DIR, "bomber_sb6.png"), {})]
    paths += [(char_files(c)[1], bomber.load_scripts(char_files(c)[3]) if os.path.exists(char_files(c)[3]) else {})
              for c in CHARS]
    for path, own in paths:
        if not os.path.exists(path):
            continue
        im = Image.open(path).convert("RGBA")
        bomber.draw_labels(im, bomber.BomberRom(rom, {**base, **own}, 0))
        im.save(path)
        print(f"labels of {path}")


def check_chars(rom, ref):
    """ref: Bomberman's sheet as read (None without bomber_sb6.png + BombermanPallete.png)."""
    for c in CHARS:
        _, sheet, pal, scripts = char_files(c)
        if not (os.path.exists(sheet) and os.path.exists(pal)):
            continue
        if ref is None:
            print(f"char{c}: needs bomber_sb6.png + BombermanPallete.png (its layout and colors)")
            continue
        try:
            own = bomber.load_scripts(scripts, ref["br"].cols) if os.path.exists(scripts) else {}
            brc = bomber.BomberRom(rom, {**ref["br"].scripts, **own}, 0)
            cells, edited, n = bomber.read_sheet_like(brc, sheet, ref["sheet"], ref["br"], ref["cells"],
                                                      ref["notes"]["cmap"], ref["notes"]["sb5"])
            same = dict(ref["br"].poses())
            edited |= {a for a, maps in brc.poses() if len(maps) != len(same[a])}
            pals = bombers._char_palettes(ref["palette"], pal, ref["notes"]["used"])
            strips, _, mappings, streamed = bomber.convert(brc, cells, edited, stream=True)
        except ValueError as e:
            raise ValueError(f"char{c}: {e}")
        shared = pals == ref["palettes"]
        if not (edited or own or not shared):
            print(f"char{c}: same as bomber_sb6.png, not inserted (the cartridge's art stays)")
            continue
        pieces = [len(p) for p in mappings.values()] or [0]
        print(f"char{c}: ok, {len(edited)} animations redrawn ({len(strips)} KB of tiles, {max(pieces)} sprites in the "
              f"largest pose), the others Bomberman's; {len(pals)} colors"
              + (" (Bomberman's)" if shared else " (own)")
              + (f", {len(own)} animations with their own sequence" if own else "")
              + (f"; streamed pose by pose (more than 32 tiles together): {', '.join('%02X' % a for a in sorted(streamed))}"
                 if streamed else "")
              + (f"; warning: {n['snapped']} pixels are not palette colors (nearest color used)" if n["snapped"] else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "check", "template", "labels"])
    ap.add_argument("chars", nargs="*", type=int, help="template: characters (1-9)")
    ap.add_argument("--force", action="store_true", help="template: overwrite char<n>_sb6.png / char<n>_pallete.png")
    ap.add_argument("--base", default=os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"))
    ap.add_argument("--edit", action="store_true", help="export: also create the editable files (never overwrites)")
    ap.add_argument("--sheet", default=SHEET)
    args = ap.parse_args()
    with open(args.base, "rb") as fh:
        rom = fh.read()
    br = bomber.BomberRom(rom)

    if args.command == "labels":
        relabel(rom)
        return

    if args.command == "template":
        for c in args.chars or CHARS:
            template(c, args.force)
        return

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
        export_chars(rom, args.edit)
        return

    sb6, pal = os.path.join(DIR, "bomber_sb6.png"), os.path.join(DIR, "BombermanPallete.png")
    ref = None
    if args.sheet == SHEET and os.path.exists(sb6) and os.path.exists(pal):
        anims = os.path.join(DIR, "bomber_anims.txt")
        if os.path.exists(anims):
            br = bomber.BomberRom(rom, bomber.load_scripts(anims))
            print(f"bomber_anims.txt: {len(br.scripts)} animations with their own sequence")
        cells, pals, n = bomber.read_sheet_recolor(br, sb6, pal)
        ref = dict(sheet=sb6, palette=pal, br=br, cells=cells, notes=n, palettes=pals)
        inexact = n["snapped"]
        print(f"bomber_sb6.png: {n['edited']} edited poses, {n['legacy']} still SB5 art, {n['colors']} of 15 colors"
              f" ({len(n['fixed'])} not in the palette picture: {', '.join('%02X%02X%02X' % c for c in n['fixed'])})")
    else:
        cells, inexact = bomber.read_sheet(br, args.sheet)
    strips, anim_strip, mappings, streamed = bomber.convert(br, cells, stream=True)
    pieces = [len(p) for p in mappings.values()]
    print(f"ok: {len(mappings)} poses, {len(strips)} strips ({len(strips)} KB of tiles), "
          f"{max(pieces)} sprites in the largest pose, {sum(pieces) / len(pieces):.1f} on average")
    if inexact:
        print(f"warning: {inexact} pixels are not palette colors (nearest color used)")
    check_chars(rom, ref)


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
