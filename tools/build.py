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
from sb6.features import bomberman_sprites, bombers, boot_logo, coop, game_sfx, louies, menu_bg, options, picker, sb1_enemies, sb1_music, sb1_stages, title, title_music, world1, world_map  # noqa: E402
from sb6.objsheets import ObjSheets  # noqa: E402

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
    rb.add_region("d0", 0xD06300, 0xD08000, "stage theme tables (metatiles, collisions: must be in bank $D0)")
    for bank in range(0xF0, 0xF3):
        rb.add_region(f"obj_f{bank & 15}", bank << 16, (bank + 1) << 16, "OBJ sheets: raw 4bpp strips (bombers)")
    for bank in range(0xEC, 0xF0):
        rb.add_region(f"stream_{bank:02x}", bank << 16, (bank + 1) << 16, "bomber poses streamed one by one (DMA source)")
    rb.add_region("title_fc", 0xFC0000, 0xFD0000, "title intro: pan and drop sounds (streamed BRR, one bank); "
                  "save menu music after them")
    for bank in range(0xFD, 0x100):
        rb.add_region(f"music_{bank:02x}", bank << 16, (bank + 1) << 16, "streamed BRR audio (save menu music)")
    for bank in (0xFA, 0xFB):
        rb.add_region(f"title_f{bank & 15:x}", bank << 16, (bank + 1) << 16,
                      "animated title: tiles, maps, tables, code (DMA sources)")
    rb.add_region("objmap", 0xF38000, 0xF40000, "sprite mappings, used through bank $B3 (the drawer needs WRAM in DBR)")
    rb.add_region("objmap2", 0xF48000, 0xF50000, "sprite mappings of more characters (bank $B4)")
    rb.add_region("objmap3", 0xF58000, 0xF60000, "sprite mappings of more characters (bank $B5)")
    for bank in range(0xF6, 0xFA):
        rb.add_region(f"obj_f{bank & 15}", bank << 16, (bank + 1) << 16, "OBJ sheets: raw 4bpp strips (other characters)")
    # lower halves of $F3-$F5 (the upper halves are the sprite mappings)
    rb.add_region("sb1_f3", 0xF30000, 0xF38000, "SB1's sound RAM image (world map music), part 1")
    rb.add_region("sb1_f4", 0xF40000, 0xF48000, "SB1's sound RAM image, part 2; world map graphics")
    rb.add_region("wmap_f5", 0xF50000, 0xF58000, "world map graphics (ZONE1, ZONE2)")
    # $FF padding inside the code banks: code reached by JSR/JMP from the bank's own routines.
    rb.add_region("c0", 0xC04D70, 0xC05F00, "bank C0 code (co-op)")
    rb.add_region("c1", 0xC177F0, 0xC17F00, "bank C1 code (co-op)")
    rb.add_region("c2", 0xC24210, 0xC27F00, "bank C2 code (co-op)")
    rb.add_region("c3", 0xC37E90, 0xC37FF0, "bank C3 code (co-op)")
    rb.add_region("c4", 0xC45A40, 0xC47F00, "bank C4 code (co-op)")
    rb.add_region("c5", 0xC56FA0, 0xC57F00, "bank C5 code (co-op)")
    # SB5 data nothing reads any more (docs/FREE_SPACE.md); more is freed below once its pointers move
    world_map.free_old_zones(rb)     # SB5's ZONE1/ZONE2 data, replaced by the SB1 / SB2 maps
    boot_logo.free_old(rb)           # the Hudson logo's tiles and arrangement (boot logo in set 5)
    title.free_old(rb)               # SB5's title scene / logo / (c) arrangements (animated title)
    options.free_old(rb)             # SB5's Options screen tiles / arrangements (OPTIONS is a title submenu)

    boot = boot_logo.convert(os.path.join(ROOT, "assets", "HU3DSON LOGO.png"))
    print(f"boot logo: {boot['count']} tiles, palette error {boot['error']:.0f}")
    boot["preview"].save(os.path.join(args.out, "boot_logo_preview.png"))
    # in-game SFX (cornered, deaths): code called from the sound hooks of title_music
    gsfx = game_sfx.apply(rb, os.path.join(ROOT, "assets", "sound"), os.path.join(args.out, "cache"))
    print(f"game SFX: R = {gsfx['r_bytes']} bytes of ARAM $5900 (SB1 enemy death {gsfx['enemy']}); "
          f"cornered {gsfx['corner_seconds']:.2f} s at {gsfx['corner_rate']:.0f} Hz = {gsfx['a']} + {gsfx['b']} bytes "
          f"(B at ${gsfx['b1']:04X} / ${gsfx['b2']:04X}), cut short in songs {gsfx['short']}")
    # world map music: SB1's / SB2's own drivers and songs (switched by title_music's sound hook)
    maps = world_map.sound(rb, os.path.join(ROOT, "assets", "sound"), [["sb1_f3", "sb1_f4"], ["stream_ef"],
                                                                         ["wmap_f5"]], os.path.join(args.out, "cache"))
    # World 1's 1-1: SB1's music as a Hudson song (uploaded by title_music's sound hook)
    sb1m_defs, sb1m = sb1_music.apply(rb, os.path.join(ROOT, "assets", "sound"))
    maps["defs"].update(sb1m_defs, SB1M_SONG=gsfx["sb1m_song"])
    print(f"1-1 music (SB1's, Hudson song): {sb1m['notes']} notes, sequence {sb1m['seq']} bytes "
          f"({sb1m['subs']} subroutines), samples {sb1m['samples']} bytes, tempo {sb1m['tempo']} "
          f"({sb1m['unit_ms'] * 24:.2f} ms rows, SB1 {sb1m['row_ms']:.2f}), pitch within {sb1m['cents']:.1f} cents; "
          f"SB5's jingles ${sb1m['jingles'][0]:04X}-${sb1m['jingles'][1] - 1:04X} + {sb1m['jingle_samples']} bytes of "
          f"samples; {sb1m['aram_left']} bytes of ARAM left; list {sb1m['list']} bytes")
    print("world map music: " + ", ".join(f"{n}'s sound RAM ({b} bytes, {p} parts)" for n, b, p in maps["drivers"]))
    # the music first: the title intro starts its pan sound through the stream code
    music = title_music.apply(rb, os.path.join(ROOT, "assets", "title", "title_music.wav"),
                              os.path.join(ROOT, "assets", "sound"), os.path.join(args.out, "cache"), gsfx["syms"],
                              drop_frames=title.drop_frames(os.path.join(ROOT, "assets", "title")),
                              save_wav=os.path.join(ROOT, "assets", "sound", "save_menu_music.wav"),
                              save_regions=["music_fd", "music_fe", "music_ff", "title_fc"], sb1=maps)
    title_music.free_old(rb)         # SB5's title song: no longer uploaded (set $28, song 1, its own samples)
    print(f"title music: {music['seconds']:.1f} s, {music['bytes']} bytes BRR in banks "
          f"{', '.join(f'${b:02X}' for b in music['banks'])}; driver {music['driver']} B, ring {music['ring']} chunks, "
          f"CPU code {music['code']} B; intro sounds {music['pan']} bytes; SB6 menu SFX {music['sfx']} in "
          f"{music['sfx_bytes']} bytes of ARAM, kept by songs {music['safe']}")
    print(f"save menu music: {music['save_seconds']:.1f} s at 12 kHz in "
          f"{', '.join(f'${b:02X}:{lo:04X}-{hi:04X}' for b, lo, hi in music['save_segs'])}; "
          f"RMS gain x{music['save_gain']:.2f} -> VOL ${music['save_vol'][0]:02X}, MVOL ${music['save_vol'][1]:02X}")

    tinfo = title.apply(rb, os.path.join(ROOT, "assets", "title"), args.out, starts, cfg["version_text"], boot,
                        os.path.join(args.out, "cache"), music["pre_start"])
    st = tinfo["stats"]
    print(f"title: sky {st['sky']} tiles, scene {st['scene']} + 2 x {st['scratch']} for alternate poses, "
          f"logo {st['logo']}, falling waves {st['waves']}; {st['frames']} intro frames, {st['jobs']} transfers; "
          f"palette error {tinfo['error']:.0f} + logo {tinfo['logo_error']:.0f} (start {tinfo['start']})")

    bomber = bomberman_sprites.apply(rb, os.path.join(ROOT, "assets", "bomberman"))
    print(f"bomberman: {bomber['tiles']} tiles and {bomber['palettes']} palettes changed")

    sheets = ObjSheets(rb)
    louie = louies.apply(rb, base_rom, sheets)
    print(f"louies: palette halves, {louies.LAST - louies.FIRST + 1} sheets recolored for the low half")

    # bomber_sb6.png + BombermanPallete.png (SB6 art, own palettes) wins over bomber.png (SB5 colors)
    bdir = os.path.join(ROOT, "assets", "bombers")
    sb6_sheet, sb6_pal = os.path.join(bdir, "bomber_sb6.png"), os.path.join(bdir, "BombermanPallete.png")
    own_palettes = os.path.exists(sb6_sheet) and os.path.exists(sb6_pal)

    # Normal menu / picker background in blue (palettes returned by the bombers' palette hook)
    mbg = menu_bg.apply(rb)
    print(f"menu background: blue checker ${mbg['checker'][0]:04X} / ${mbg['checker'][1]:04X}")
    en_defs, en_info = sb1_enemies.apply(rb)     # World 1's SB1 enemies (their tables go through the bombers' hooks)
    clown = en_info.pop("_clown")                # 1-7's clown boss: its BG2 colors go into the arena's palette
    sb1_stages.STAGES["sb1_4-8"]["extra_pals"] = dict(zip(sb1_enemies.CLOWN_PALS, clown["pals"]))
    stages = sb1_stages.apply(rb)                # World 1's SB1 / SB6 stage pictures (1-6's palette id: pal_lookup)
    en_defs["W1PAL"] = f"${stages['sb6_1-6']['ext']['pal']:06X}"
    anim_start = stages.pop("anim")              # 1-7's electric fence (asm/stage_anim.asm, started by world1's op)
    print("SB1 enemies: " + ", ".join(f"{n} = type ${i['type']:02X} ({i['frames']} frames, {i['tiles']} tiles, "
                                      f"{i['colors']} colors)" for n, i in en_info.items()))
    if own_palettes:
        info = bombers.apply(rb, base_rom, sheets, sb6_sheet, sb6_pal, os.path.join(bdir, "bomber_anims.txt"), bdir,
                             menu_bg=mbg, enemies=en_defs)
    else:
        info = bombers.apply(rb, base_rom, sheets, os.path.join(bdir, "bomber.png"), chars_dir=bdir, menu_bg=mbg,
                             enemies=en_defs)
    sheets.finish()                  # also frees the stock OBJ sheet table (free_c5_sheets)
    bombers.free_stock_sheets(rb, base_rom)  # SB5's character sheets 1-20 (every character uses SB6 sheets)

    wmap = world_map.apply(rb, os.path.join(ROOT, "assets", "world_map"), args.out, ["wmap_f5", "sb1_f4"],
                           music["map_music"])
    print("world map: ZONE1 = SB1's World 1 map + SB5's START sign, ZONE2 = SB2's map: "
          + ", ".join(f"ZONE{i + 1} {t} tiles / {p} BG palettes" for i, (t, p) in enumerate(wmap["zones"]))
          + f"; sea in {wmap['frames']} frames, {wmap['lights']} light colors (preview build/world_map_preview.png)")

    w1 = world1.code(rb, stages["sb6_1-6"], anim_start, clown)
    print("world 1: stages " + ", ".join(world1.chain(rb)))
    for n, i in stages.items():
        print(f"world 1: {n} = {i['metatiles']} metatiles, {i['tiles']} tiles, {i['palettes']} palettes "
              f"({i['approx']} pixels approximated), {i['bytes']} bytes LZ")
    pick = picker.apply(rb, base_rom, info, tinfo["syms"], wmap["wmap_nmi"], wmap["wmap_op"], w1["w1_op"])
    print(f"picker: character + color (L/R) selection in the Normal Game, {pick['bomber_colors']} colors for Bomberman")

    coop.apply(rb, louie["louie_tick"], pick)
    print("co-op: Normal Game for 1-4 players (multitap on port 2)")
    options.apply(rb, title.SET)
    print("options: title submenu (DISCORD -> QR code); SB5's Options, Sound Test and Password screens freed")
    world1.text(rb, base_rom, args.out)
    print("world 1: WORLD instead of ZONE (stage intro, world map label; preview build/world_text_preview.png)")
    for ch in info["chars"] if info else []:
        n = ch["notes"]
        print(f"char{ch['char']}: Bomberman's layout, {n['edited']} animations redrawn in {ch['strips']} KB of tiles, "
              f"the others his; {ch['colors']} colors"
              + (" (his palettes)" if ch["shared"] else f" (own palettes from {ch['pal0']}"
                 + (", own key colors)" if n.get("own") else ")"))
              + (" - SHEET NOT PAINTED YET: Bomberman's art" if n.get("blank") else "")
              + ("".join(f"\n    more than 15 colors: {m}" for m in n.get("merged", [])))
              + (f", {ch['scripts']} own sequences" if ch["scripts"] else "")
              + (f"; {n['snapped']} pixels off-palette (nearest color used)" if n["snapped"] else ""))
    if info and info["sheet"]:
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
