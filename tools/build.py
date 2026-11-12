#!/usr/bin/env python3
"""Builds "Super Bomberman 6.sfc" from the Super Bomberman 5 (USA) ROM.

    python tools/build.py [--base "Super Bomberman 5 (USA).sfc"] [--out build]

The output keeps the original 4 MB HiROM layout (repro-cart friendly). All
new data goes to free space listed below; every overwritten byte is verified
against the base ROM first. See docs/FREE_SPACE.md and build/sb6.map.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb6.rombuild import RomBuild, BuildError  # noqa: E402
from sb6.features import bomberman_sprites, bombers, boot_logo, coop, title, title_music  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.path.join(ROOT, "Super Bomberman 5 (USA).sfc"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build"))
    ap.add_argument("--search", action="store_true",
                    help="try many palette-quantizer starts and print the best (slow)")
    args = ap.parse_args()

    cfg_path = os.path.join(ROOT, "assets", "title", "convert.json")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    starts = [tuple(s) for s in cfg["palette_starts"]]
    if args.search:
        starts = [(seed, init) for init in ("mean", "hist") for seed in range(1, 17)]

    with open(args.base, "rb") as fh:
        base_rom = fh.read()
    rb = RomBuild(base_rom)

    # Free space (verified to be unused $FF in the base ROM).
    rb.add_region("bulk", 0xE40000, 0xE50000, "hack code, scripts and small data (E4); streamed audio from $E5")
    rb.add_region("e3_tables", 0xE3DD60, 0xE40000, "graphics archive tables (must be in bank $E3)")
    rb.add_region("bank81", 0xC1FA00, 0xC20000, "palette tables/colors (must be in bank $81)")
    for bank in range(0xF0, 0xF3):
        rb.add_region(f"obj_f{bank & 15}", bank << 16, (bank + 1) << 16, "OBJ sheets: raw 4bpp strips (bombers)")
    rb.add_region("objmap", 0xF38000, 0xF40000, "sprite mappings, used through bank $B3 (the drawer needs WRAM in DBR)")
    # $FF padding inside the code banks: code reached by JSR/JMP from the bank's own routines.
    rb.add_region("c0", 0xC04D70, 0xC05F00, "bank C0 code (co-op)")
    rb.add_region("c1", 0xC177F0, 0xC17F00, "bank C1 code (co-op)")
    rb.add_region("c2", 0xC24210, 0xC27F00, "bank C2 code (co-op)")
    rb.add_region("c3", 0xC37E90, 0xC37FF0, "bank C3 code (co-op)")
    rb.add_region("c4", 0xC45A40, 0xC47F00, "bank C4 code (co-op)")
    rb.add_region("c5", 0xC56FA0, 0xC57F00, "bank C5 code (co-op)")

    boot = boot_logo.convert(os.path.join(ROOT, "assets", "HU3DSON LOGO.png"))
    print(f"boot logo: {boot['count']} tiles, palette error {boot['error']:.0f}")
    boot["preview"].save(os.path.join(args.out, "boot_logo_preview.png"))
    info = title.apply(rb, os.path.join(ROOT, "assets", "title"), args.out, starts, cfg["version_text"], boot)
    print(f"title: {info['tiles']} tiles, palette error {info['error']:.0f} (start {info['start']}), "
          f"arrangements {info['arr_bytes']} bytes")

    music = title_music.apply(rb, os.path.join(ROOT, "assets", "title", "title_music.wav"),
                              os.path.join(ROOT, "assets", "sound", "title_sfx.json"),
                              os.path.join(args.out, "cache"))
    print(f"title music: {music['seconds']:.1f} s, {music['bytes']} bytes BRR in banks "
          f"{', '.join(f'${b:02X}' for b in music['banks'])}; driver {music['driver']} B, ring {music['ring']} chunks, "
          f"CPU code {music['code']} B; menu SFX replayed: {music['sfx']}")

    bomber = bomberman_sprites.apply(rb, os.path.join(ROOT, "assets", "bomberman"))
    print(f"bomberman: {bomber['tiles']} tiles and {bomber['palettes']} palettes changed")

    coop.apply(rb)
    print("co-op: Normal Game for 1-4 players (multitap on port 2)")

    # bomber_sb6.png + BombermanPallete.png (SB6 art, own palettes) wins over bomber.png (SB5 colors)
    bdir = os.path.join(ROOT, "assets", "bombers")
    sb6_sheet, sb6_pal = os.path.join(bdir, "bomber_sb6.png"), os.path.join(bdir, "BombermanPallete.png")
    if os.path.exists(sb6_sheet) and os.path.exists(sb6_pal):
        info = bombers.apply(rb, base_rom, sb6_sheet, sb6_pal, os.path.join(bdir, "bomber_anims.txt"))
    else:
        info = bombers.apply(rb, base_rom, os.path.join(bdir, "bomber.png"))
    if info:
        n = info["notes"]
        print(f"bomber: {info['poses']} poses in {info['strips']} KB of tiles, up to {info['max_pieces']} sprites per pose"
              + (f"; {n['edited']} poses from bomber_sb6.png ({n['colors']} colors), {n['legacy']} still SB5 art" if n else "")
              + (f"; {info['inexact']} pixels off-palette (nearest color used)" if info["inexact"] else ""))
    else:
        print("bomber: no sheet in assets/bombers, SB5 sprites kept (tools/bomber_sheet.py export --edit)")

    rb.set_title("SUPER BOMBERMAN 6")
    rb.fix_checksum()
    os.makedirs(args.out, exist_ok=True)
    out_rom = os.path.join(args.out, "Super Bomberman 6.sfc")
    with open(out_rom, "wb") as fh:
        fh.write(rb.d)
    with open(os.path.join(args.out, "sb6.map"), "w", encoding="utf-8") as fh:
        fh.write(rb.map_text())
    print(f"wrote {out_rom} ({len(rb.d)} bytes)")


if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        sys.exit(f"build failed: {e}")
