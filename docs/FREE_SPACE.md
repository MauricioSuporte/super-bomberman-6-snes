# Free space and ownership

`tools/build.py` registers each region with `add_region()`, which fails the
build if any byte is not `$FF` in the base ROM. Allocations are listed in
`build/sb6.map`.

## ROM

| Region | Size | Owner / rule |
|---|---|---|
| `$C1:FA00-$C1:FFFF` | 1.5 KB | `bank81`: palette tables and colors (must be in bank `$81`). Only free space in that bank. |
| `$E3:DD60-$E3:FFFF` | 8.7 KB | `e3_tables`: graphics archive tables (must be in bank `$E3`). |
| `$D0:6300-$D0:7FFF` | 7.4 KB | `d0`: stage theme tables (metatiles, collisions; must be in bank `$D0`). After theme `$2B`'s metatile table (ends `$D0:62EE`). |
| `$C0:4D70-$C0:5EFF`, `$C1:77F0-$C1:7EFF`, `$C2:4210-$C2:7EFF`, `$C3:7E90-$C3:7FEF`, `$C4:5A40-$C4:7EFF`, `$C5:6FA0-$C5:7EFF` | | `c0`..`c5`: co-op code that must sit in the bank of the routine it hooks (`JSR`/`JMP` targets, seat-loop stubs); `c5` also the magnet bomb (`asm/magnet.asm`) and World 1's item lists (`asm/stage_items.asm`). |
| `$C0:FED0-$C0:FFAF` | 224 B | `c0_hi`: `$FF` padding before the header; code reached by the IRQ entry (`JMP ($006D)` runs in bank `$80`, so above `$8000`): the SB6 HUD's line-23 -> line-31 IRQ stub (46 B). |
| `$E4:0000-$E4:FFFF` | 64 KB | `bulk`: hack code (65816), scripts, arrangements, title tiles. |
| `$E5:0000-$EB:176A` | 390 KB | streamed BRR (title music), 404 chunks of 162 bytes per bank. |
| `$EB:176A-$EB:FFA7`, `$FC:A200-$FC:D9AF`, `$FD:0000-$FF:FFA7` | ~270 KB | save file menu music (Normal Game file lists + picker), streamed BRR at 12 kHz (`music_fd`..`music_ff` and the tails of `audio_EB` / `title_fc`; segments in `asm/title_music.asm`). |
| `$EC:0000-$EF:FFFF` | 256 KB | `stream_ec`..`stream_ef`: bomber poses streamed one by one (DMA sources, `asm/bombers.asm`). `stream_ef` currently holds Super Bomberman 2's sound RAM image for the ZONE2 world map music (57 KB, `world_map.sound`), `stream_ed` the Hudson upload list of World 1's 1-1 music (SB1's song, 27.7 KB: sequence + samples, `sb1_music.py`). |
| `$F0:0000-$F2:FFFF` | 192 KB | `obj_f0`..`obj_f2`: OBJ sheets (raw 4bpp, 1 KB strips aligned to `$400`: bomber, Louie sheets recolored for palette entries 1-7) and the relocated OBJ sheet table (`tools/sb6/objsheets.py`). |
| `$F3:8000-$F3:FFFF` | 32 KB | `objmap`: sprite mappings and bomber animation scripts, addressed as bank `$B3` (the OAM builder needs WRAM in the data bank). |
| `$F4:8000-$F4:FFFF`, `$F5:8000-$F5:FFFF` | 64 KB | `objmap2`, `objmap3`: mappings/scripts of characters 1-9 (banks `$B4`, `$B5`), used when `objmap` is full. |
| `$F6:0000-$F9:FFFF` | 256 KB | `obj_f6`..`obj_f9`: OBJ sheets of edited characters 1-9 (after `obj_f0`..`obj_f2`). |
| `$FA:0000-$FB:FFFF` | 128 KB | `title_fa`, `title_fb`: animated title (`tools/sb6/features/title_anim.py`): raw tiles and map rows sent by DMA, job/frame tables, `asm/title_anim.asm` (~94 KB used). |
| `$FC:0000-$FC:A1FF` | 41 KB | `title_fc`: the title intro's sounds (pan + character drops) as streamed BRR chunks (must start the bank; the rest holds save menu music). |
| `$F3:0000-$F3:7FFF`, `$F4:0000-$F4:7FFF` | 64 KB | `sb1_f3`, `sb1_f4`: Super Bomberman 1's sound RAM image for the ZONE1 world map music (39 KB, `tools/sb6/features/world_map.py`), then world map data (~6 KB used in `sb1_f4`). |
| `$F5:0000-$F5:7FFF` | 32 KB | `wmap_f5`: the map's accept SFX player (4 KB sound RAM image), world map ZONE1/ZONE2 tiles, sea frames, ship light colors, set 1 arrangements (~21 KB used). |
| `$FC:D9B0-$FC:FFFF` | ~9 KB | unassigned. |
| `$D3:C670-$D3:E50D` | 7838 B | `free_d3`: was SB5's ZONE1/ZONE2 island tiles (set 3 archives `$0F`/`$10`), freed by `world_map.free_old_zones` (also listed as set 0 `$6E`/`$6F`, set 6 `$12`/`$13`: nothing loads them). Unused. |
| `$E2:1371-$E2:1B10` | 1952 B | `free_e2`: was SB5's ZONE1/ZONE2 island arrangements (set 4 `$0F`/`$10`). Unused. |
| `$C1:985E-$C1:99A5` | 328 B | `free_81`: was SB5's ZONE1/ZONE2 palettes (set 3 `$10`/`$11`, also set 6 `$3E`/`$3F`); bank `$81`, so it can hold palettes. Unused. |
| `$C5:E22D-$C5:EB44` | 2328 B | `free_c5_sheets`: was the stock OBJ sheet table (`$85:E22D`, 291 entries); its only reader `$C5:6B8C` reads the copy in the OBJ banks (`tools/sb6/objsheets.py` frees it in `finish()`, so it is declared after the bomber features have allocated). Also addressable as `$85:E22D`, i.e. fit for data that must sit in a `$80-$BF` bank (sprite mappings). Unused. |
| `$C4:3093-$C4:30C2` | 48 B | `free_c4_mine`: was SB5's mine setup (a bomb of ability `$20`); its only caller, the `JSR` at `$C4:3076`, is jumped over (`features/magnet.py`). Bank `$C4` code. Unused. |
| `$D5:9993-$D5:A544` | 2994 B | `free_d5`: was the Hudson boot logo's tiles (set 3 archive `$46`, LZ; same entry as set 0 `$A5`, set 6 `$49`, set 8 `$81`, stock OBJ sheet 165), freed by `boot_logo.free_old`. Unused. |
| `$DC:501D-$DC:6D0B` | 7407 B | `free_dc_zone1`: were SB5's ZONE1 stage music samples `$25`-`$26` (song 5's own; no other song lists them), freed by `sb1_music.free_old`: every World 1 stage with that music uploads its SB1 list instead of song 5; only SB5's ZONE1 stages outside the chain (`$0E`, `$0F`, `$12`-`$16`) would still upload them (checked in Mesen: 0 reads on 1-1..1-7, the title and the demo). Set `$2C` (the sequence) is kept: the stage scripts still send it and the lists copy its jingles. Unused. |
| `$D9:E464-$D9:EC39` | 2006 B | `free_d9`: was SB5's death voice (sound set `$48` upload list + end mark + jump word), freed by `game_sfx.free_old` once set `$48` points at R. Unused. |
| `$E2:0264-$E2:06B3` | 1104 B | `free_e2_title`: was SB5's title scene and logo arrangements (set 4 #2, #3), freed by `title.free_old`. Unused. |
| `$E2:07A2-$E2:07F3` | 82 B | `free_e2_copy`: was SB5's "(c) 1997 HUDSON SOFT" arrangement (set 4 #6). Unused. |
| `$E2:CAF3-$E2:CBE7` | 245 B | `free_e2_boot`: was the Hudson boot logo's arrangement (set 4 `$D3`). Unused. |
| `$C7:4000-$C7:FFFF`, `$C8:0000-$C8:FFFF`, `$C9:0000-$C9:7FFF` | 144 KB | `free_c7_sheets`, `free_c8_sheets`, `free_c9_sheets`: were SB5's playable characters' OBJ sheets 1-20 (raw 4bpp, set 0 archives 1-`$14`), freed by `bombers.free_stock_sheets` once every character's `[sheet, row]` table names only SB6 sheets (it fails the build otherwise, or if `assets/bomberman/sheet.png` edits them). Boss rivals use the same per-character tables. Louie sheets follow at `$C9:8000`. Free again (they held SB1's World 1 stage sound RAM images while SB1's driver played the stages); `$C7:4000` starts with 1-7's SB1 boss song list (32 KB, `sb1_music.late_alloc`); `$C8:0000` starts with 1-7's clown pictures (40 KB, `sb1_enemies.clown_alloc`: the first thing put there), then the title cursor; the chameleons' poses and the pause menu use `$C9`/`$C7`. |
| `$D6:A3ED-$D6:CAA6` | 9914 B | `free_d6`: was SB5's two title characters (set 3 OBJ archives `$61`/`$62`, LZ), freed by `title.free_old`; the byte at `$D6:A3EC` stays (the decompressor of archive `$60`, the menu cursor, reads it). Archive `$63` (the exit portal's beam, `$D6:CAA7`) follows and is kept (it used to be freed too: portals were invisible). Holds `asm/sb1_enemies.asm` (SB1 enemies' routines, 1-7's clown; bank `$E4` is full). |
| `$C7:00DE-$C7:0AB1` | 2516 B | `free_c7_options`: were SB5's Options (mode `$0B`), Sound / Sound Test and Password (mode 7) scripts and tables, freed by `options.free_old` (the mode table entries now point at the title's record). Bank `$C7`: fit for scripts. Unused. |
| `$E3:0000-$E3:127F` | 4736 B | `free_e3_options`: was the Options screen's tiles (set 3 archive `$92`, raw). Bank `$E3`, so it can also hold archive tables. Unused. |
| `$D4:9DFE-$D4:AFA8` | 4523 B | `free_d4_options`: was the Options / Password background (set 3 archive `$25`, LZ); its first byte `$D4:9DFD` stays (archive `$24`'s decompressor reads it). Unused. |
| `$E1:9DD9-$E1:A051`, `$E1:C03F-$E1:CC96` | 3793 B | `free_e1_options`, `free_e1_options2`: were the Options frame / menu / Stereo-Mono / Sound Test arrangements (set 6 `$C3`, `$DA-$DD`). Unused. |
| `$E2:C3FB-$E2:C7A2` | 936 B | `free_e2_password`: were the Password arrangements (set 4 `$C6`/`$C7`). Unused (slot `$C6` now points to the stage intro's dash, in `free_e2`). |
| `$D5:C9DB-$D5:CEAA` | 1232 B | `free_d5_font`: was SB5's stage intro / HUD font with ZONE (set 3 archive `$4D`, LZ), replaced by the WORLD one in `bulk` (`world1.text`); its first byte `$D5:C9DA` stays (the decompressor of the archive before may read it). Only that archive entry named it. Unused. |
| `$D9:D641-$D9:D795`, `$DA:CEFE-$DA:CF29` | 385 B | `free_d9_password`, `free_da_password`: were the Password music's sequence (sound set `$41`, music id `$1B`) and song `$1A`'s upload list. Unused. |
| `$CD:0885-$CD:15CC`, `$CD:1F39-$CD:31FA`, `$81:ACE8-$81:AD8B`, `$81:AE10-$81:AF17`, `$D0:A550-$D0:A5F6`, `$D0:A627-$D0:A72B` | 8.9 KB | `free_cd_stage2`, `free_cd_stage45`, `free_81_stage2`, `free_81_stage45`, `free_d0_maps1`, `free_d0_maps2`: were SB5's ZONE1 stage tiles (set 4 archives 2, 4, 5), palettes (set 4 palettes 2, 4, 5) and maps 2-4, 6-11, freed by `sb1_stages.apply` (World 1 uses SB1 4-4/6-4 tiles and its own maps; themes 4 and the other maps belong to stages no longer in the chain). The first byte of each archive/map range is kept: SB5's LZ reader (`$C0:1D46`) reads one command byte past the stream before. Checked with loads.lua / a read watch on stages `$0D $11 $18 $10 $17 $67-$69` and the attract demo: 0 reads. Unused. |
| `$D0:0286-$D0:0385`, `$D0:809C-$D0:80BB` | 288 B | `free_d0_themes45`, `free_d0_coll45`: were SB5's theme 4 and 5 metatile / collision tables (15 + 17 ids), freed by `sb1_stages.apply` (2026-11-21): 1-5 (theme 5) got its own 33-id tables in `d0` (the hard block lights), 1-7 (theme 4) already had its own; no other played stage names themes 4/5. Read watch on 1-4, 1-5, 1-6, 1-7: 0 reads of SB5's tables (1-6 / 1-7 read only their new tables placed here). Used by 1-6's theme `$28` tables and 1-7's collisions. |
| `$CB:0462-$CB:0D85`, `$CB:12E6-$CB:1AC6` | 4.3 KB | `free_cb_enemies1`, `free_cb_enemies2`: were SB5's enemy types 02, 03, 05, 06 OBJ tiles (set 8 archives 4, 5, 7, 8, LZ); now first hold the SB1 enemies' archives, freed by `sb1_enemies.apply` once those types show SB1's enemies. The first byte of each run is kept (SB5's LZ reader reads one byte past the archive before). Read watch on stages `$0D $11 $18 $10 $17 $68` and the attract demo: 0 reads. Unused. |
| `$81:893C-$81:897F` | 68 bytes | `free_81_tankpal`: was SB5's tank's 32-color OBJ palette (set 8 palette 4, named only by enemy type 04's record), freed by `sb1_enemies.apply` when type 04 became SB1 4-2's horned robot (palette `$31`, shared with the UFO / bomb robot). Read watch on stage `$10` (and `$0D`) with 4 players: 0 reads. Unused (bank `$81`: palettes). |
| `$C0:6001-$C0:6B89`, `$C0:6B8A-$C0:752F` | 5423 B | `free_c0_flames`, `free_c0_items`: were SB5's flame tiles (set 0 archive `$5D`, LZ) and item tiles (set 0 archive `$5E`, LZ), freed by `explosions.free_old` (2026-11-22); the first byte `$C0:6000` stays (the archive before reads one byte past its stream). Only those two archive entries name them (the stock OBJ sheet table and its copy list them as sheets `$5D`/`$5E`, which no object asks for: loads.lua logged no sheet `$5D`/`$5E`). Checked with a build that put the new archives in `free_c8_sheets`: read watch on `$C0:6001-$C0:752F` through the title, the attract demo and stages 1-1 and `$13` with 4 players dropping bombs: 0 reads (the same watch on the new data's place: 200+ reads at the stage load). Hold SB6's flame tiles (2889 B) and item icons (2440 B), LZ. |
| `$CA:D400-$CA:DDBD` | 2494 B | `free_ca_bombs`: was SB5's bomb sprites (set 0 archive `$23`, LZ), freed by `bombs.free_old` (2026-11-23). Named only by its archive entry (`$E3:BF74`) and the stock OBJ sheet table's copy (`$85:E345`, freed; the relocated copy of `ObjSheets` is pointed at SB6's too). Holds SB6's bomb sprites (2454 B, LZ) at the same address. |
| `$C1:90B8-$C1:90C5` | 14 B | `free_81_fire`: was SB5's fire colors (set 6 palette 2: `[$2B, 5, 5 colors]`, named only by set 6 id 2, loaded by every stage's set-up `$C5:13DC`), replaced by SB6's 6 colors in `bank81` (`explosions.fire_palette`). Unused (bank `$81`). |
| `$D8:FB02-$D8:FFEB` | 1258 B | `free_d8`: was SB5's title song sequence (sound set `$28`), freed by `title_music.free_old`, which also turns the title's `FF A0 02` music loads into skips. Unused. |
| `$DA:C512-$DA:C585` | 116 B | `free_da`: was song 1's upload list (sample directory / tuning). Unused. |
| `$DB:43FA-$DB:539E`, `$DB:66EC-$DB:84A0` | 11610 B | `free_db_a`, `free_db_b`: were samples 4, 5, 9 and `$0A`, used by song 1 only (its other samples are shared). Unused. |

Freeing SB5 data: `rb.free_old(name, start, size, crc32, purpose)` (`tools/sb6/rombuild.py`)
checks the original bytes' CRC32, fills them with `$FF` through `rb.patch` and declares the region;
each feature lists what it replaced in an `OLD_DATA` table (`world_map.OLD_ZONE_DATA`). Before freeing,
check every table that can name the data (archive, palette and arrangement windows of every set, the
stock OBJ sheet table, the sound set / song lists), the script ops and native callers that load it
(docs/ROM_MAP.md "Finding who loads a graphics item"), then run `tools/mesen/loads.lua` with
`LOADS_WATCH` set to the freed ranges (it logs CPU reads of every mirror) through the title (with the OPTIONS
submenu and QR), the attract demo, the Normal Game, the world map zones and a stage: it must report 0 reads.
Not freed, and why (checked 2026-11-16): SB5's intro (mode `$A9`, skipped since the boot logo goes to
mode 2) loads set 3 archives 3-6 / `$57-$5F`, palettes 4-7 / `$32-$3A`, sets 13-14 palettes, set 4
arrangement 1 and set 6 `$EB-$EF`, but the same items are loaded by scripts at `$C6:6Cxx-$C6:6Fxx` and
`$C6:EAxx-$C6:EFxx` (another scene, probably the ending) or through object data that was not traced;
the Hudson logo's palette (set 3 `$2B`, 68 bytes in bank `$81`) and the title characters' palette
(`$3C`) for the same reasons; the stock menu palettes outside mode 3 / the Normal Game picker. Options / Password (2026-11-18, `options.py`), kept because other screens load the same
ids: set 3 archives `$1D`, `$22`, `$26` (the Password characters; a Battle script loads `27 26` too), `$66`,
palettes `$1B`, `$1C`, `$41`, the Password fade palettes (set 13 `$BB-$C3`, ids computed like the
`$C4-$D5` fades of other screens), the Password song's samples (shared with songs 1, 9, `$0C`, `$0E`,
`$14`, `$19`) and the menu SFX. Freed
2026-11-18 (owner's call): SB5's title song and characters, and the character sheets 1-20, which
boss rivals would also show (they will be replaced).
SB6 HUD (2026-11-23, `features/hud.py`): SB5's HUD tiles for the Normal Game (set 3 archive `$4A`) are no
longer loaded by the HUD task, but `$C5:1144` (routine `$C5:1133`) loads `$4A` too, and the head art is cut
from it at build time; SB5's HUD arrangement, score / clock / lives printers (`$C4:2491`, `$C5:06CD`,
`$C5:0BEF`, `$C5:0C86`) still run for Battle and still write their (now hidden) rows in the Normal Game.
World 1's 1-6 (2026-11-19): SB5's arena maps `$8E`, `$90`, `$92` (stages `$67`/`$69`/`$6B`, 30-31 bytes LZ each at `$D0:CBA7`, `$D0:CBE3`, `$D0:CC20`): `$8E`'s list entry now names the 1-6 map, the others are no longer named by a played stage; too small to be worth a free (and `$90`/`$92` would still be read if SB5's own zone stages came back). Theme `$27`, set 4 archive `$1F` and palettes `$1B`/`$1C` stay: SB5's other arenas use them. 1-7's clown (2026-11-19): enemy type 07 now shows an empty picture, but its stock OBJ tiles (set 8 archive 9, LZ at `$CB:1AC7`) are also named by another archive table entry (set 0 entry `$2D`), so they stay; type 07's palette 7 of set 8 is rewritten in place. 1-4's UFO / robot (2026-11-19): set 8 archive `$31` (types `$35`/`$36`, LZ at `$CC:1818`, 1807 bytes) now points at the SB1 sheet, but another archive table (bank `$C5`, entry at `$C5:E4CD`) names the same data, so it stays. 1-4's horned robot (2026-11-21): SB5's tank tiles (set 8 archive 6, LZ at `$CB:0D86-$CB:12E5`) are no longer named by type 04's archive entry, but bank `$C5`'s archive table names them too (`$C5:E379`), so they stay.
`tools/mesen/loads.lua` also logs OBJ sheet pages (`sheet`), sound set and song uploads.

Budget note: streamed audio costs ~9 KB per second (16 kHz mono). The whole
free ROM held only ~2.5 minutes of it (now mostly used by the title and the
save menu music; 12 kHz costs ~6.75 KB/s), so streaming is for menus only;
in-game music should be converted to sequences for Hudson's driver (or a new
sequenced driver).

## WRAM

| Address | Owner |
|---|---|
| `$0100-$010D` | title music stream (active, sequence, pointer, bank, loader kick, frame, SFX toggle `$0107`), SB6 menu SFX (`$0108` samples in ARAM, `$0109` SB6 definitions active), `$010A` track (0 intro, 1 title, 2 save menu), `$010B` segment offset (word), `$010D` save music pending. Bottom of the stack page: in a 12 000-frame run (intro, title, menus, Zone 1) the stack never went below `$01B3`. The recomp's co-op mod also treats this area as free (`$011E`); keep new variables after `$0110`. |
| `$0110-$015C` | co-op (`asm/coop.asm`): `$0110` 6x4 distance arrays, `$0128` mount offset, `$0129` player count, `$012A` roster (word), `$012C` participant mask, `$012D` actor base, `$012E` co-op stage flag, `$012F` spawn check, `$0130-$0143` P3/P4 fields saved while benched, `$0144` benched seats (bit = 1 << seat), `$0145-$014E` scratch, `$014F-$0152` OBJ palette arbitration scratch, `$0153` highest static OBJ page, `$0154` co-op stage frame timer, `$0155` boss stage flag (word), `$0157` bench scratch (word), `$0159-$015A` P3/P4 spawn anchor x, `$015B-$015C` anchor y. Set by the boot hook after the reset clear. |
| `$7F:FE00-$7F:FE66` | streamed bomber poses (`asm/bombers.asm`): `+$00` mapping in each seat's page, `+$06` pending DMA per slot (2 * seat + half, `$A5`), `+$10` `$073F` set per seat, `+$1A` table entry per slot, `+$2E` VRAM per slot, `+$42` `$5AA5` once cleared (from the title, `pick_tick`), `+$44-$57` scratch, `+$58` stock `$073F` per seat (restored when another animation's pose follows), `+$62` animation of each seat's streamed pose. Ignored by the NMI until cleared. |
| `$7F:FE80-$7F:FEB2` | co-op OBJ pages (`asm/coop.asm`): `+$00` object whose strip `c5_record` saw sent to each of the 16 pages (`$FF` none; reset by SB5's page setup `$C5:6A14`), `+$10` its sheet, `+$20` its row, `+$30` `$A5` while an in-place strip waits for the NMI (`c5_urgent`), `+$31` its page * 2, `+$32` its queue entry. |
| `$7F:FF00-$7F:FF7F` | character selection (`asm/picker.asm`): `+$00` picker running, `+$01` choices valid, `+$02` choice of 5 seats, `+$08` color of 5 seats (also the color under each seat's cursor while choosing), `+$10` saved `$1032-$104F`, `+$30` saved `$1D20-$1D3F`, `+$58-$5B` scratch, `+$60` word scratch, `+$69` CGRAM shadow changed (sent when the VRAM queue is empty), `+$6A` fade the file list in (back from the picker). `$7F:E000-$7F:FFFF` was never written in a 12 000-frame run (title, menus, picker, Zone 1); flags are compared with exact values and cleared on the title, so they do not depend on the reset contents. |
| `$7F:FC00-$7F:FC7F` | SB6 character selection screen (`asm/picker.asm`, names `!st`...): `+$00` state (0 waiting for SB5's setup, 1 loading, 2 choosing, 3 all chosen, 4 leaving), `+$01` next VRAM job, `+$03` seat choosing, `+$04`/`+$05`/`+$06` cell with its cursor face / next / swap pending, `+$07`/`+$08` hover palettes' character / color, `+$09` cursor timer, `+$0A` exit wait, `+$0B` cursor tint, `+$10`-`+$47` per seat (4 bytes each: confirmed, cursor cell, chosen character, chosen color, row animation, its character, step, frames left, pose wanted, pose in VRAM, VRAM half, OBJ palette id, dimmed, victory held), `+$50-$60` OAM builder / scratch of the main loop, `+$70-$75` NMI scratch, `+$76` NMI count, `+$77` count at the last tick, `+$78` row steps left. Cleared by the open op. |
| `$7F:FD00-$7F:FD43` | animated title (`asm/title_anim.asm`): `+$00` `$5AA5` once started, `+$02` state (0 off, 1 loading, 2 waiting for the fade-in, 3 intro, 4 idle), `+$03` intro seen, `+$04` logo landed, `+$05` main screen layers, `+$06` list/frame offset, `+$08` loading the finished scene, `+$0A`/`+$0C` BG1/BG2 V scroll, `+$0E` pad held, `+$0F`-`+$15` idle counters and RNG, `+$16`-`+$1D` the two alternate-pose areas, `+$1E` 7 character timers, `+$26`-`+$2D` scratch, `+$2E`-`+$39` menu cursor (frames without input, animation 0 rest / 1-4 look around / 5 confirming / 6 confirmed, its frame and face, pose and sprite frame in VRAM, refresh counter, scratch, the cursor Y / menu `$1036` / menu Y `$1034` when the confirmation began), `+$3A` cursor visible last frame, `+$3B` forced resend, `+$3C` `FF 1A FC` frame wait, `+$3D` a pose in several steps holds both areas, `+$40` 2 words: each area's pending step record; `+$1C`-`+$1D` unused). Only read after the signature matches. |
| `$0188-$018C`, `$0196` | in-game SFX (`asm/game_sfx.asm`): `$0188` R in ARAM, `$0189` restore state, `$018A` restore wait, `$018B` song last uploaded, `$018C` command waiting for the next main-loop pass (cornered / enemy hit). `$0196`: a death sound waiting for R to come back (main-loop passes left, 0 = none). Zero after reset (0 = song 0, whose samples cover R). |
| `$018D-$0195` | world map music (`asm/title_music.asm`): `$018D` foreign driver running (0 Hudson's, 1 SB1's, 2 SB2's, 3 the accept SFX player, the SPC waiting in the IPL ROM), `$018E` the map's driver (set by `map_music`), `$018F` last port-0 command sent to it, `$0191` last port-1 command, `$0192` scratch (also `asm/world_map.asm`), `$0193` the map music was requested and plays, `$0194` upload part counter, `$0195` upload sequence; `$0190` map animation 0 off / 1-2 sea / 3-4 stars (`asm/world_map.asm`). Zero after reset. |
| `$7F:E000-$7F:E4FF` | 1-7's clown boss (`asm/sb1_enemies.asm` `clown`, `!CB`): `+$00` phase, `+$01` frames left (word), `+$03` SB1 state, `+$04` animation entry (word), `+$06` its frames, `+$07` picture wanted, `+$08` hits left, `+$0A`/`+$0C` center x / y (pixel . 1/256), `+$0E`/`+$10` speeds, `+$12` BG2 buffer shown, `+$13` picture in each buffer, `+$15` buffer being sent, `+$16` queue pointer after it, `+$18` red colors on, `+$19` players held (`$A5`, read by world1's `intro_pads`), `+$1A` BG2 on, `+$1B` (unused now), `+$1C` body's OBJ tile base, `+$1E` its palette slot, `+$1F` `$A5` while `clown_oam` draws, `+$20-$2D` scratch, seats to kill, touch box, explosion timer, body actor, `+$2E` white blink, `+$2F` picture shown, `+$30-$37` queue scratch, `+$38` (unused now: `hold_up` compares the animation shown), `+$39-$3B` darkness level / wanted / on, `+$40-$87` 8 shots (x, y, speeds, animation), `+$88-$9B` 4 explosions (x, y, age), `+$A0-$B0` OAM scratch, `+$B2-$B7` saved `$0308`, `$0313-$0317`; `$7F:E100-$7F:E1FF` OBJ palettes before the dark, `$7F:E200-$7F:E3FF` HDMA table (window 1), `$7F:E400-$7F:E4FF` OBJ palettes as dimmed. Cleared by `clown_start` (`FF 1A F6 05`); `clown_oam` acts only in stage `$68` with `+$1F` = `$A5`. |
| `$7F:FB00-$7F:FB03` | world map animation (`asm/world_map.asm`): sea frames left, sea frame, ship light frame, star half-line. |
| `$7F:FB40-$7F:FBAE` | SB6 stage HUD (`asm/hud.asm`): `+$00` `$A5` = SB6 HUD shown (cleared by every stage's HUD task, `hud_begin`; the stage IRQ, `hud_tick` and `time_gate` test it), `+$01` lives shown, `+$02` seat checked last, `+$03` seat, `+$04` its record (11 bytes: in the game, fire, speed, bombs, bomb type icon, 6 power-up icons), `+$0F` scratch, `+$10` the 4 records shown (`$FF` = draw again), `+$3C-$51` queue / copy scratch, `+$52` rows to queue (after the load / a pause), `+$53` each seat's head tile palettes, `+$57` queue source in bank `$7F`, `+$58-$69` head drawing scratch, `+$6A` each seat's BG3 block state drawn (redrawn only when it changes), `+$6E` parts of the rows left to queue (one per check: field rows, BG2, BG1, BG3). `$7F:EC00-$7F:EDFF`: the 4 seats' heads drawn at the stage load (128 bytes each, `build_heads`). VRAM while it is on (Normal Game stages): BG2 tiles `$D0-$F9` (SB5's HUD tiles, archive `$4A`, not loaded then; BG1 uses them too), BG2 map rows 28-31 of the lower screen (`$3F80-$3FFF`, cleared by SB5 at the stage load), BG1 map rows 24-27 of the same screen (`$3F00-$3F7F`, zero in every stage; BG1SC `$3C` in the HUD lines), BG3 tiles `$42-$7F` (`$5210-$53FF`: from `$59` zero in every World 1 stage; `$42-$58` are SB5's HUD tiles, archive `$4C`, only shown by its hidden HUD rows 63, 0-1), BG3 map rows 56-59 (`$4700-$477F`, SB5 fills rows 32-62 with blanks) and the field's BG3 rows 2-4 (`$4040-$409F`, blank in every World 1 stage: the panel's last lines and the lives tab). CGRAM 25-28 (items palette entries 9-12, `items.FIXED`): the heart's dark red, red, white (BG3 palette 6 = the heart) and the HUD's blue (palette 1 entry 12). CGRAM 15 (SB5's pink `$3DBF`, BG3 palette 3: unused by the Normal Game's BG3, the pause menu uses palettes 0 / 1 / 6) = the HUD's purple `hud.PURPLE` in Normal Game stages (`purple` in `asm/hud.asm` writes it to the CGRAM copy `$7E:2910` and sets `$0351`; Battle keeps the pink). |
| `$7F:FB10-$7F:FB13` | World 1 exit door (`asm/world1.asm`): door x (0 = not chosen), y (1-1 to 1-5: the middle cell (7, 6)), scratch (count, index). Reset by the stage's `FF 1A F6 03`. |
| `$7F:FB14-$7F:FB17` | World 1 portal (`asm/world1.asm` portal_task): `$FB14` = 1 while it makes the portal (`w1_kind` at `$C2:26AF` reads our kind), 2 while it asks for its sound (group 2 `$33`, which `asm/game_sfx.asm` mutes as a dead enemy's score), 0 from the stage start, `$FB15-$FB17` the door root (`$037C-$037E` at the clear op). |
| `$7F:F100-$7F:F6DF` | stage pause menu (`asm/pause.asm`): `$F100-$F5FF` BG3 tiles `$100+` saved while the menu's glyphs are in VRAM (416 bytes used), `$F600` `$5A` once a pause was opened, `+$01` state (0 none / Battle, 1 menu, 2 leaving the stage), `+$02` menu, `+$03` line, `+$04` text rows wanted, `+$06` glyphs in VRAM, `+$07` panel set by us, `+$08` CGRAM color 0 blacked (`+$09` word: its color), `+$0D`/`+$0E` new actions / directions, `+$0F` NMI scratch, `+$11` saved `$0AEA`, `+$20-$31` saved `$0306-$0317`, `+$40-$6F` STAGE label cells (top / bottom words), `+$70` cells, `+$71` first column, `+$72-$74` digits, `+$80-$DF` STAGE rows sent by the NMI. Set by `pm_open` at every pause; the NMI acts only after the signature. VRAM: BG3 tiles `$100-$119` (`$5800-$58CF`, glyphs + frame) only while the menu is up (their contents are put back); HDMA channel 7 (panel window) while the menu is up. |
| `$7F:F76F` | 1 while SB5's `$C3:4B7B` runs for an SB1 enemy or SB5's walker (`asm/sb1_enemies.asm` `sb1w`, `asm/coop.asm` `c3_walk`): `c3_near` skips the distances of far seats. |
| `$7F:F7CC-$7F:F7FF` | Start shield (`asm/coop.asm` `shield`, stage start only): `$F7CC-$F7CF` scratch (queue head, length, cell, direction), `$F7D0` pocket queue (24 cells), `$F7E8` its distances. |
| `$7F:F770-$7F:F7CB` | SB1 enemies (`asm/sb1_enemies.asm`): `$F770` speed per actor (SB1 `$19`: 0-2), `$F788` horned robot's frames seeing a player per actor (SB1 `$30`), `$F7A0-$F7A4` scratch (|dx|, |dy|, signs, seat), `$F7AE` `$0069` when the enemy list was built, `$F7AF` `$A5` = built, `$F7B0-$F7C8` enemy actors of this main loop pass (`$FF`-terminated). Cleared with `$7F:F700+` by World 1's stage start op. |
| `$7F:F700-$7F:F76E` | SB1 2-1's enemies in 1-2 (`asm/sb1_enemies.asm` `sb1w`): per actor (24 bytes each, from `+$00`): set up (`$A5`), SB1 direction, SB1 `$21` timer, direction of the animation shown; `+$60-$6E` scratch (kind, mask, saved position, direction tried, nearest seat and distance, word, own x / y / actor). Cleared with the chameleons' by World 1's stage start op (`asm/world1.asm`). |
| `$7F:F800-$7F:FAFF` | SB1 chameleons (`asm/chameleon.asm`): per actor (24 bytes each, from `+$000`): set up, phase, frames left, seat, own tile base low / high, own slot, changing into, FLICK entry, its frames, VRAM half, pose entry low / high, pose frames, facing, character; per VRAM half (words from `+$1A0`): owner, DMA pending, source, bank, columns, entry loaded; `+$200` DMAs queued this frame, `+$201` `$5A` halves set up, `+$202-$20E` scratch (`+$20D` the NMI's). Cleared by World 1's stage start op (`asm/world1.asm`); read by the NMI only in 1-3 after the signature. |
| `$7F:FB20-$7F:FB28` | World 1's 1-6 (`asm/world1.asm`): each seat's start x (`$FB20+seat`) and y (`$FB24+seat`), kept at the first rival's intro (spawn_reset puts them back before the Golden Bomber); `$FB28` frames / 256 since the Golden Bomber died (with `$FBFC`). |
| `$7F:FBD0-$7F:FBD3` | World 1's 1-6 stands blink (`asm/world1.asm` stand_task): phase, frames left, cycle, brightness. Set by `FF 1A F6 04`. |
| `$7F:FBD4-$7F:FBD6` | World 1's 1-6 rival intro (`asm/world1.asm` intro_task, intro_pads): phase (0 hold, 1 walking, 2 done), frames left once moving, the stage. Set by `FF 1A F6 07`. |
| `$7F:FB2C-$7F:FB3F` | Magnet bomb (`asm/magnet.asm`): a byte per bomb slot (0 normal, `$80` + frames before it looks for enemies again); cleared by both bomb allocators. |
| `$7F:E800-$7F:E9F8` | Louie abilities (`asm/louie_abilities.asm`): `+$00` frames each actor (24) stays frozen by `la_frozen`, `+$18` push frames left, `+$30` push direction, `+$48` each seat's (5) Black dash frames, `+$4D` dash cooldown, `+$52` dash direction, `+$57` impact hold, `+$5C` invincible frames after the dash, `+$61` `$15A2` bit 2 set by us, `+$66` afterimage frames left, `+$6B` positions in the history, `+$70` history index, `+$75` something to draw (read by `la_oam`), `+$80` 5 x 16 words of x, `+$120` 5 x 16 words of y (the last frames' positions), `+$1C0` a byte per bomb slot (20): rolls in a Yellow Louie train (cleared by both bomb allocators, `mg_alloc`), `+$1E0-$1F7` scratch, `+$1F8` the next egg's Louie in the egg test stage (`la_hatch`). Cleared during the first 2 frames of every co-op stage (`$0154` < 2). `$7F:E000-$7F:FFFF` was never written by SB5 (see `$7F:FF00` above). |
| `$7F:FBC0-$7F:FBCF` | Animated stage tiles (`asm/stage_anim.asm`): frame counter (`$FBC0+n`) and picture (`$FBC8+n`) of the stage's animation n (up to 8; 1-6's crowd has 3). |
| `$7F:FBDA-$7F:FBE7` | Animated stage tiles (`asm/stage_anim.asm`, 1-4's bumpers, 1-5's lights, 1-6's crowd, 1-7's electric fence): scratch (source, VRAM address, bytes left, entry size), the stage's first table row, `$FBE3` flame tile bytes sent (word), `$FBE5`/`$FBE6` row / animation being run, `$FBE7` frames before the flame tiles are sent (1-6's duels only: there SB5 writes tiles `$010-$01F` itself ~25 frames after the stage script; 0 elsewhere). |
| `$7F:FBFC` | World 1's 1-6: frames since the rival's object went away (next_rival), then since the stage end after the Golden (exit_task). |
| `$7F:FBFD-$7F:FBFE` | World 1's 1-6: the duel being fought (its old stage id `$67`/`$69`/`$6B`; all three are played in stage `$67`), 1 while next_rival makes the rival (`asm/world1.asm`). |
| `$7F:FBFB` | World 1's 1-6: seats whose start pose was turned up (`asm/world1.asm` face_up_start), bit per seat. Set by `FF 1A F6 07`. |
| `$7F:FBD7-$7F:FBD9` | World 1's 1-6 items (`asm/world1.asm` item_task): the stage, frames before the next item (word). Set by `FF 1A F6 07`. |
| `$7F:FBFA` | World 1's SB1 music (`asm/title_music.asm` `sb1m_song`, `SB1M_FLAG`): `$A5` = an SB1 song list overwrote set `$2C`'s sequence in ARAM (sent again before the next stage's ZONE1 samples). Any other value = no. |
| `$0160-$0187` | Louie palettes (`asm/louies.asm`): `$0160` half of each actor (24 bytes, 0 = none), `$0178` users of the 3 halves, `$017B` palette id in each half, `$017E` OBJ slot of the main / spare palette (0 = none), `$0180-$0187` scratch. Zero after reset; forgotten when the slot table loses the `$FF` mark (new stage). |

## ARAM (sound RAM)

On the ZONE1 / ZONE2 world map the whole SPC belongs to Super Bomberman 1's
driver (sound RAM `$0800-$A1BB`, plus the hack's tables and SB6's accept
recording at `$A200-$B283`) or Super Bomberman 2's (`$0800-$E6DF`,
`$FF00-$FF38`, a copy of the IPL ROM at `$FFC0`; echo buffer `$E700-$FEFF`),
uploaded through the IPL ROM with a loader at `$0200` (docs/ROM_MAP.md "World
map"); Hudson's driver is uploaded again, as at power-on, by the next non-SFX
request or on a zone without foreign music. Choosing a stage on ZONE2 uploads a
small player at `$0800-$1864` (SB6's accept recording on voice 0) that
returns to the IPL ROM. Nothing below survives that.

SB6 menu SFX: samples at `$B900-$DCFF` (~9 KB used), directory entries
`$39-$3B` (`$FDE4-$FDEF`) and `$3E` (`$FDF8`, the picker's color change,
only played by the stream driver: no instrument or Hudson definition), tuning `$FEE4-$FEEF` / `$FEF8`, instruments 28-30
(`$4540-$454B`), and the first 16 bytes of SB5's SFX 1/3/4 sequences
(`$45B0`, `$45F8`, `$4618`). Present only while the stream or a song that
leaves `$B900-$DCFF` alone is loaded (docs/ROM_MAP.md, "Sound").

In-game SFX (`tools/sb6/features/game_sfx.py`): R = `$5900-$6579`
(SB5's group-3 voice buffer; sequences of SFX `$5E-$60`, a silent END block,
the SB1 death and enemy samples, part A of the cornered recording) while the
current song leaves it alone; part B of the recording (1359 bytes) right
below `$DD00` (echo buffer), or below `$B900` for songs that keep the menu
SFX. Pointer table entries `$448A-$448F`, priorities `$458D-$458F`,
instruments 2-3 (`$44D8`) and 31 (`$454C`), directory / tuning entries `$1F`,
`$3C`, `$3D`. Sizes are printed by the build.

World 1's SB1 music (`tools/sb6/features/sb1_music.py`, SB1's songs as Hudson songs, uploaded instead of
SB5's ZONE1 samples while the stage loads): song table `$3000-$300B` (command 1 = SB1's song, 2-4 = SB5's
jingles), SB5's jingles where SB5 has them (`$3E00-$4240`), SB1's samples from `$8000`; SB1's header, tracks
and subroutines and the jingles' samples (SB5 directory entries 2, 3, `$0B-$0D`, 5.5 KB) in the rest of
`$300C-$43FF` and `$8000-$F4FF`: the song and the jingles use echo delay 1 (buffer `$F500-$FCFF`). The build
prints the ARAM left per stage (1-1 ~3.1 KB, 1-2 ~0.7 KB, 1-3 ~5.3 KB, 1-4 ~1.5 KB, 1-5 ~1.9 KB). ROM: one upload list per stage (~30-35 KB) in
`stream_ed` / `stream_ec` / `stream_ee` (build/sb6.map), the stage table in `bulk`. Directory / tuning entries 0-`$11` (SB1's samples take the ones the jingles do not use).
It covers part B of the cornered recording (`$D841`), so while it is loaded `gs_song` = `SB1M_SONG` (R kept,
no B: the cornered sound is cut short, as in songs 15, 16, 21, 23-26).

World 1's portal sound (`tools/sb6/features/portal_sfx.py`, 1-1 to 1-5): Hudson SFX `$62` (pointer `$4492`,
priority `$4591`), instrument 30 (`$4548`), directory / tuning entry `$3B` = the stage's copy of SB1's bell
(sample `$06` of its song, already uploaded by the SB1 music: no sample bytes of its own); its 50-byte track
in the SB1 song's list (`sb1_music.build` `portal`, from the ARAM the song leaves). Instrument 30 and entry `$3B`
are also the SB6 menu SFX's: `asm/game_sfx.asm` sends the portal's entries (after every set / song upload)
only while `gs_song` = `SB1M_SONG` on a stage of its table, when the menu SFX samples cannot be in ARAM.

While the title music streams, the stream driver owns `$7000-$B8FF`
(driver + SFX scripts `$7000-$72FF`, ring `$7300-$B89B`,
110 chunks; sizes are computed by the build), inside SB5's title-song
area; everything else (Hudson's code, sets, directories, echo buffer) is
untouched. The stream uses voice 7 and timer 0; the menu SFX samples are played
on voice 0 with timer 2 (4 ms ticks, `$FC = 0`). Release restores the DSP
registers it touched, `$F1` from Hudson's shadow `$1E` and `$FC` from `$21`.
