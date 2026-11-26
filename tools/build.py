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
from sb6.features import bomberman_sprites, bombers, bombs, boot_logo, coop, eggs, explosions, game_sfx, hud, items, louie_abilities, louies, menu_bg, options, pause, picker, portal, magnet, sb1_enemies, sb1_music, sb1_stages, stage_items, title, title_music, world1, world_map  # noqa: E402
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
                  "menu music after them")
    for bank in range(0xFD, 0x100):
        rb.add_region(f"music_{bank:02x}", bank << 16, (bank + 1) << 16, "streamed BRR audio (save file / character selection music)")
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
    rb.add_region("c0_hi", 0xC0FED0, 0xC0FFB0, "bank C0 code above $8000 (IRQ handlers: they run in bank $80)")
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
    explosions.free_old(rb)          # SB5's flame and item tiles (set 0 archives $5D / $5E: SB6's replace them)
    bombs.free_old(rb)               # SB5's bomb sprites (set 0 archive $23: SB6's replace them)

    boot = boot_logo.convert(os.path.join(ROOT, "assets", "HU3DSON LOGO.png"))
    print(f"boot logo: {boot['count']} tiles, palette error {boot['error']:.0f}")
    boot["preview"].save(os.path.join(args.out, "boot_logo_preview.png"))
    # in-game SFX (cornered, deaths): code called from the sound hooks of title_music
    gsfx = game_sfx.apply(rb, os.path.join(ROOT, "assets", "sound"), os.path.join(args.out, "cache"))
    game_sfx.free_old(rb)            # SB5's death voice (set $48 now uploads R)
    print(f"game SFX: R = {gsfx['r_bytes']} bytes of ARAM $5900 (SB1 death {gsfx['death']}, enemy {gsfx['enemy']}); "
          f"cornered {gsfx['corner_seconds']:.2f} s at {gsfx['corner_rate']:.0f} Hz = {gsfx['a']} + {gsfx['b']} bytes "
          f"(B at ${gsfx['b1']:04X} / ${gsfx['b2']:04X}), cut short in songs {gsfx['short']}")
    # world map music: SB1's / SB2's own drivers and songs (switched by title_music's sound hook)
    maps = world_map.sound(rb, os.path.join(ROOT, "assets", "sound"), [["sb1_f3", "sb1_f4"], ["stream_ef"],
                                                                         ["wmap_f5"]], os.path.join(args.out, "cache"))
    # World 1's 1-1: SB1's music as a Hudson song (uploaded by title_music's sound hook)
    sb1m_defs, sb1m = sb1_music.apply(rb, os.path.join(ROOT, "assets", "sound"), gsfx["b1"], gsfx["portal_table"])
    maps["defs"].update(sb1m_defs, SB1M_SONG=gsfx["sb1m_song"])
    for m in sb1m:
        print(f"stage ${m['stage']:02X} music (SB1 {m['name']}, Hudson song): {m['notes']} notes, sequence "
              f"{m['seq']} bytes ({m['subs']} subroutines), samples {m['samples']} bytes, tempo {m['tempo']} "
              f"({m['unit_ms'] * m['units']:.2f} ms rows, SB1 {m['row_ms']:.2f}), pitch within {m['cents']:.1f} "
              f"cents; SB5's jingles + {m['jingle_samples']} bytes of samples"
              + (f" (SB1 samples for SB5's {m['aliased']})" if m['aliased'] else "")
              + f"; {m['aram_left']} bytes of ARAM left; list {m['list']} bytes")
    sb1_music.free_old(rb)           # SB5's ZONE1 stage music samples (song 5's own; the SB1 lists replace it)
    print("world map music: " + ", ".join(f"{n}'s sound RAM ({b} bytes, {p} parts)" for n, b, p in maps["drivers"]))
    # the music first: the title intro starts its pan sound through the stream code
    music = title_music.apply(rb, os.path.join(ROOT, "assets", "title", "title_music.wav"),
                              os.path.join(ROOT, "assets", "sound"), os.path.join(args.out, "cache"), gsfx["syms"],
                              drop_frames=title.drop_frames(os.path.join(ROOT, "assets", "title")),
                              save_wav=os.path.join(ROOT, "assets", "sound", "save_menu_music.wav"),
                              save_regions=["music_fd", "music_fe", "music_ff", "title_fc"], sb1=maps,
                              char_wav=os.path.join(ROOT, "assets", "sound", "char_select_music.wav"))
    title_music.free_old(rb)         # SB5's title song: no longer uploaded (set $28, song 1, its own samples)
    print(f"title music: {music['seconds']:.1f} s, {music['bytes']} bytes BRR in banks "
          f"{', '.join(f'${b:02X}' for b in music['banks'])}; driver {music['driver']} B, ring {music['ring']} chunks, "
          f"CPU code {music['code']} B; intro sounds {music['pan']} bytes; SB6 menu SFX {music['sfx']} in "
          f"{music['sfx_bytes']} bytes of ARAM, kept by songs {music['safe']}")
    print(f"save menu music: {music['save_seconds']:.1f} s at 12 kHz in "
          f"{', '.join(f'${b:02X}:{lo:04X}-{hi:04X}' for b, lo, hi in music['save_segs'])}; "
          f"RMS gain x{music['save_gain']:.2f} -> VOL ${music['save_vol'][0]:02X}, MVOL ${music['save_vol'][1]:02X}")

    bomber = bomberman_sprites.apply(rb, os.path.join(ROOT, "assets", "bomberman"))
    print(f"bomberman: {bomber['tiles']} tiles and {bomber['palettes']} palettes changed")

    sheets = ObjSheets(rb)
    egg_defs = eggs.apply(rb)        # SB6's egg (sheet $1A tiles, own frames, palette id $51): before the Louie half copies
    bo = bombs.apply(rb, base_rom, sheets, preview=os.path.join(args.out, "bombs_preview.png"))
    print(f"bombs: {bo['pictures']} SB6 bomb pictures ({bo['lz']} bytes LZ at ${bo['at']:06X}), SB6 blues in "
          f"palette $58, mean error {bo['error']:.1f} (Lab; build/bombs_preview.png)")
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
    en_defs.update(egg_defs)                     # the egg's frames: the same hooks
    portal_defs, portal_w1, pinfo = portal.apply(rb)   # World 1's exit portal (SB1's): its type 6 tables too
    en_defs.update(portal_defs)
    print(f"portal: SB1's exit ({pinfo['colors']} colors, {pinfo['bytes']} bytes of tiles), set 7 archive / palette 1")
    clown = en_info.pop("_clown")                # 1-7's clown boss: its BG2 colors go into the arena's palette
    sb1_stages.STAGES["sb1_4-8"]["extra_pals"] = dict(zip(sb1_enemies.CLOWN_PALS, clown["pals"]))
    stages = sb1_stages.apply(rb)                # World 1's SB1 / SB6 stage pictures (1-6's palette id: pal_lookup)
    en_defs["W1PAL"] = f"${stages['sb1_5-1']['ext']['pal']:06X}"
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
    brm = bombs.remap(rb)            # magnet bomb animation (free_c5_sheets), mappings off its freed tiles
    print(f"bombs: magnet bomb animation at ${brm['anim']:06X}; mappings moved off its tiles: {brm['mappings']}")
    bombers.free_stock_sheets(rb, base_rom)  # SB5's character sheets 1-20 (every character uses SB6 sheets)
    sb1_music.late_alloc(rb)                     # 1-7's boss song: first thing in free_c7_sheets
    sb1_enemies.clown_alloc(rb, clown["bg"])  # 1-7's clown pictures (first in free_c8_sheets)
    cham = sb1_enemies.chameleon(rb, info, sheets, en_info)   # 1-3's chameleons walk as the characters
    print(f"chameleons: {cham['streamed']} streamed poses reused, {cham['cut']} cut from strips "
          f"({cham['blocks']} blocks, up to {cham['widest']} columns), {cham['scripts']} walk scripts")

    # SB6's explosions (flame tiles, fire colors in every stage palette) and items (icons,
    # palette 1, the border's blink: its script in free_c5_sheets); after sb1_stages (World 1's palettes)
    fx = explosions.apply(rb)
    explosions.fire_palette(rb)
    it = items.apply(rb, preview=os.path.join(args.out, "items_preview.png"))
    print(f"explosions: SB6 flame tiles ({fx['lz']} bytes LZ), fire colors (set 6 palette 2); "
          f"items: {it['tiles'] // 128} SB6 icons ({it['lz']} bytes LZ) in "
          f"{it['colors']} colors + the blinking border, mean error {it['error']:.1f} (Lab; build/items_preview.png)")
    mag = magnet.apply(rb)
    sit = stage_items.apply(rb)
    print("magnet bomb: item $0F (SB5's mine, freed) -> SB6's magnet bomb (kicked toward an enemy in its row / "
          f"column); code ${mag['mg_alloc']:06X}-${mag['end_c5']:06X}")
    print("stage items: " + "; ".join(f"{s} " + ", ".join(v) for s, v in sit.items()))

    # after the stock sheets are freed: the title's alternate pose steps also use free_c8_sheets
    tinfo = title.apply(rb, os.path.join(ROOT, "assets", "title"), args.out, starts, cfg["version_text"], boot,
                        os.path.join(args.out, "cache"), music["pre_start"])
    st = tinfo["stats"]
    print(f"title: sky {st['sky']} tiles, scene {st['scene']} + 2 x {st['scratch']} for alternate poses, "
          f"logo {st['logo']}, falling waves {st['waves']}; {st['frames']} intro frames, {st['jobs']} transfers; "
          f"palette error {tinfo['error']:.0f} + logo {tinfo['logo_error']:.0f} (start {tinfo['start']})")

    wmap = world_map.apply(rb, os.path.join(ROOT, "assets", "world_map"), args.out, ["wmap_f5", "sb1_f4"],
                           music["map_music"])
    print("world map: ZONE1 = SB1's World 1 map + SB5's START sign, ZONE2 = SB2's map: "
          + ", ".join(f"ZONE{i + 1} {t} tiles / {p} BG palettes" for i, (t, p) in enumerate(wmap["zones"]))
          + f"; sea in {wmap['frames']} frames, {wmap['lights']} light colors (preview build/world_map_preview.png)")

    w1 = world1.code(rb, stages["sb1_5-1"], anim_start, clown, portal_w1)
    print("world 1: stages " + ", ".join(world1.chain(rb)))
    print("world 1: map markers " + ", ".join(world1.markers(rb)))
    for n, i in stages.items():
        print(f"world 1: {n} = {i['metatiles']} metatiles, {i['tiles']} tiles, {i['palettes']} palettes "
              f"({i['approx']} pixels approximated), {i['bytes']} bytes LZ")
    pz = pause.apply(rb)             # in-stage pause menu (Normal Game): its NMI part goes through pick_nmi
    print(f"pause: RESUME / RETURN TO WORLD MAP / RETURN TO TITLE in the Normal Game ({pz['tiles']} BG3 glyphs)")
    hz = hud.apply(rb, base_rom, os.path.join(args.out, "hud_preview.png"))
    print(f"hud: SB6 status HUD in the Normal Game ({hz['bg3_tiles']} BG3 tiles; clock stopped), "
          f"preview build/hud_preview.png")
    pick = picker.apply(rb, base_rom, info, tinfo["syms"], wmap["wmap_nmi"], wmap["wmap_op"], w1["w1_op"],
                        pz["pause_nmi"], music["music_track"])
    print(f"picker: character + color (L/R) selection in the Normal Game, {pick['bomber_colors']} colors for Bomberman")

    coop.apply(rb, louie["louie_tick"], pick)
    print("co-op: Normal Game for 1-4 players (multitap on port 2)")
    options.apply(rb, title.SET)
    print("options: title submenu (DISCORD -> QR code); SB5's Options, Sound Test and Password screens freed")
    la = louie_abilities.apply(rb)   # after world1 / sb1_enemies: chains their main-loop JSLs
    print("louie abilities: Red stuns enemies, Yellow kicks bomb trains, Black Louie hatches and dashes, "
          f"Green / Black afterimages; code ${la['la_red'] & 0xFFFFFF:06X}-${la['end_c4']:06X}")
    world1.text(rb, base_rom, args.out)
    print("world 1: STAGE w-s in the stage intro, WORLD instead of ZONE on the world map label (preview build/world_text_preview.png)")
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

    # last: the character selection music takes what the other features left (title_music.CHAR_REGIONS)
    char_segs = music["place_char"]()
    print(f"character selection music: {music['char_seconds']:.1f} s at 12 kHz in {len(char_segs)} segments ("
          + ", ".join(f"${b:02X}:{lo:04X}-{hi:04X}" for b, lo, hi in char_segs)
          + f"); RMS gain x{music['char_gain']:.2f} -> VOL ${music['char_vol'][0]:02X}, MVOL ${music['char_vol'][1]:02X}")

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
