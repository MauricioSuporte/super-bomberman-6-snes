# Free space and ownership

`tools/build.py` registers each region with `add_region()`, which fails the
build if any byte is not `$FF` in the base ROM. Allocations are listed in
`build/sb6.map`.

## ROM

| Region | Size | Owner / rule |
|---|---|---|
| `$C1:FA00-$C1:FFFF` | 1.5 KB | `bank81`: palette tables and colors (must be in bank `$81`). Only free space in that bank. |
| `$E3:DD60-$E3:FFFF` | 8.7 KB | `e3_tables`: graphics archive tables (must be in bank `$E3`). |
| `$C0:4D70-$C0:5EFF`, `$C1:77F0-$C1:7EFF`, `$C2:4210-$C2:7EFF`, `$C3:7E90-$C3:7FEF`, `$C4:5A40-$C4:7EFF`, `$C5:6FA0-$C5:7EFF` | | `c0`..`c5`: co-op code that must sit in the bank of the routine it hooks (`JSR`/`JMP` targets, seat-loop stubs). |
| `$E4:0000-$E4:FFFF` | 64 KB | `bulk`: hack code (65816), scripts, arrangements, title tiles. |
| `$E5:0000-$EB:176A` | 390 KB | streamed BRR (title music), 404 chunks of 162 bytes per bank. |
| `$EB:176A-$EB:FFA7`, `$FC:A200-$FC:D9AF`, `$FD:0000-$FF:FFA7` | ~270 KB | save file menu music (Normal Game file lists + picker), streamed BRR at 12 kHz (`music_fd`..`music_ff` and the tails of `audio_EB` / `title_fc`; segments in `asm/title_music.asm`). |
| `$EC:0000-$EF:FFFF` | 256 KB | `stream_ec`..`stream_ef`: bomber poses streamed one by one (DMA sources, `asm/bombers.asm`). `stream_ef` currently holds Super Bomberman 2's sound RAM image for the ZONE2 world map music (57 KB, `world_map.sound`). |
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
| `$D5:9993-$D5:A544` | 2994 B | `free_d5`: was the Hudson boot logo's tiles (set 3 archive `$46`, LZ; same entry as set 0 `$A5`, set 6 `$49`, set 8 `$81`, stock OBJ sheet 165), freed by `boot_logo.free_old`. Unused. |
| `$D9:E464-$D9:EC39` | 2006 B | `free_d9`: was SB5's death voice (sound set `$48` upload list + end mark + jump word), freed by `game_sfx.free_old` once set `$48` points at R. Unused. |
| `$E2:0264-$E2:06B3` | 1104 B | `free_e2_title`: was SB5's title scene and logo arrangements (set 4 #2, #3), freed by `title.free_old`. Unused. |
| `$E2:07A2-$E2:07F3` | 82 B | `free_e2_copy`: was SB5's "(c) 1997 HUDSON SOFT" arrangement (set 4 #6). Unused. |
| `$E2:CAF3-$E2:CBE7` | 245 B | `free_e2_boot`: was the Hudson boot logo's arrangement (set 4 `$D3`). Unused. |
| `$C7:4000-$C7:FFFF`, `$C8:0000-$C8:FFFF`, `$C9:0000-$C9:7FFF` | 144 KB | `free_c7_sheets`, `free_c8_sheets`, `free_c9_sheets`: were SB5's playable characters' OBJ sheets 1-20 (raw 4bpp, set 0 archives 1-`$14`), freed by `bombers.free_stock_sheets` once every character's `[sheet, row]` table names only SB6 sheets (it fails the build otherwise, or if `assets/bomberman/sheet.png` edits them). Boss rivals use the same per-character tables. Louie sheets follow at `$C9:8000`. Now SB1's World 1 stage sound RAM images (`world1.stage_drivers`, see build/sb6.map). |
| `$D6:A3ED-$D6:CAA6` | 9914 B | `free_d6`: was SB5's two title characters (set 3 OBJ archives `$61`/`$62`, LZ), freed by `title.free_old`; the byte at `$D6:A3EC` stays (the decompressor of archive `$60`, the menu cursor, reads it). Archive `$63` (the exit portal's beam, `$D6:CAA7`) follows and is kept (it used to be freed too: portals were invisible). Unused. |
| `$C7:00DE-$C7:0AB1` | 2516 B | `free_c7_options`: were SB5's Options (mode `$0B`), Sound / Sound Test and Password (mode 7) scripts and tables, freed by `options.free_old` (the mode table entries now point at the title's record). Bank `$C7`: fit for scripts. Unused. |
| `$E3:0000-$E3:127F` | 4736 B | `free_e3_options`: was the Options screen's tiles (set 3 archive `$92`, raw). Bank `$E3`, so it can also hold archive tables. Unused. |
| `$D4:9DFE-$D4:AFA8` | 4523 B | `free_d4_options`: was the Options / Password background (set 3 archive `$25`, LZ); its first byte `$D4:9DFD` stays (archive `$24`'s decompressor reads it). Unused. |
| `$E1:9DD9-$E1:A051`, `$E1:C03F-$E1:CC96` | 3793 B | `free_e1_options`, `free_e1_options2`: were the Options frame / menu / Stereo-Mono / Sound Test arrangements (set 6 `$C3`, `$DA-$DD`). Unused. |
| `$E2:C3FB-$E2:C7A2` | 936 B | `free_e2_password`: were the Password arrangements (set 4 `$C6`/`$C7`). Unused. |
| `$D5:C9DB-$D5:CEAA` | 1232 B | `free_d5_font`: was SB5's stage intro / HUD font with ZONE (set 3 archive `$4D`, LZ), replaced by the WORLD one in `bulk` (`world1.text`); its first byte `$D5:C9DA` stays (the decompressor of the archive before may read it). Only that archive entry named it. Unused. |
| `$D9:D641-$D9:D795`, `$DA:CEFE-$DA:CF29` | 385 B | `free_d9_password`, `free_da_password`: were the Password music's sequence (sound set `$41`, music id `$1B`) and song `$1A`'s upload list. Unused. |
| `$CD:0885-$CD:15CC`, `$CD:1F39-$CD:31FA`, `$81:ACE8-$81:AD8B`, `$81:AE10-$81:AF17`, `$D0:A550-$D0:A5F6`, `$D0:A627-$D0:A72B` | 8.9 KB | `free_cd_stage2`, `free_cd_stage45`, `free_81_stage2`, `free_81_stage45`, `free_d0_maps1`, `free_d0_maps2`: were SB5's ZONE1 stage tiles (set 4 archives 2, 4, 5), palettes (set 4 palettes 2, 4, 5) and maps 2-4, 6-11, freed by `sb1_stages.apply` (World 1 uses SB1 4-4/6-4 tiles and its own maps; themes 4 and the other maps belong to stages no longer in the chain). The first byte of each archive/map range is kept: SB5's LZ reader (`$C0:1D46`) reads one command byte past the stream before. Checked with loads.lua / a read watch on stages `$0D $11 $18 $10 $17 $67-$69` and the attract demo: 0 reads. Unused. |
| `$CB:0462-$CB:0D85`, `$CB:1654-$CB:1AC6` | 3.4 KB | `free_cb_enemies1`, `free_cb_enemies2`: were SB5's enemy types 02, 03, 06 OBJ tiles (set 8 archives 4, 5, 8, LZ), freed by `sb1_enemies.apply` once those types show SB1's enemies. The first byte of each run is kept (SB5's LZ reader reads one byte past the archive before). Read watch on stages `$0D $11 $18 $10 $17 $68` and the attract demo: 0 reads. Unused. |
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
| `$7F:FF00-$7F:FF7F` | character selection (`asm/picker.asm`): `+$00` picker running, `+$01` choices valid, `+$02` choice of 5 seats, `+$08` color of 5 seats (also the color under each seat's cursor while choosing), `+$10` saved `$1032-$104F`, `+$30` saved `$1D20-$1D3F`, `+$58-$5B` scratch, `+$60` word scratch, `+$69` CGRAM shadow changed (sent when the VRAM queue is empty), `+$6A` fade the file list in (back from the picker). `$7F:E000-$7F:FFFF` was never written in a 12 000-frame run (title, menus, picker, Zone 1); flags are compared with exact values and cleared on the title, so they do not depend on the reset contents. |
| `$7F:FC00-$7F:FC7F` | SB6 character selection screen (`asm/picker.asm`, names `!st`...): `+$00` state (0 waiting for SB5's setup, 1 loading, 2 choosing, 3 all chosen, 4 leaving), `+$01` next VRAM job, `+$03` seat choosing, `+$04`/`+$05`/`+$06` cell with its cursor face / next / swap pending, `+$07`/`+$08` hover palettes' character / color, `+$09` cursor timer, `+$0A` exit wait, `+$0B` cursor tint, `+$10`-`+$47` per seat (4 bytes each: confirmed, cursor cell, chosen character, chosen color, row animation, its character, step, frames left, pose wanted, pose in VRAM, VRAM half, OBJ palette id, dimmed, victory held), `+$50-$60` OAM builder / scratch of the main loop, `+$70-$75` NMI scratch, `+$76` NMI count, `+$77` count at the last tick, `+$78` row steps left. Cleared by the open op. |
| `$7F:FD00-$7F:FD3C` | animated title (`asm/title_anim.asm`): `+$00` `$5AA5` once started, `+$02` state (0 off, 1 loading, 2 waiting for the fade-in, 3 intro, 4 idle), `+$03` intro seen, `+$04` logo landed, `+$05` main screen layers, `+$06` list/frame offset, `+$08` loading the finished scene, `+$0A`/`+$0C` BG1/BG2 V scroll, `+$0E` pad held, `+$0F`-`+$15` idle counters and RNG, `+$16`-`+$1D` the two alternate-pose areas, `+$1E` 7 character timers, `+$26`-`+$2D` scratch, `+$2E`-`+$39` menu cursor (frames without input, animation 0 rest / 1-4 look around / 5 confirming / 6 confirmed, its frame and face, pose and sprite frame in VRAM, refresh counter, scratch, the cursor Y / menu `$1036` / menu Y `$1034` when the confirmation began), `+$3A` cursor visible last frame, `+$3B` forced resend, `+$3C` `FF 1A FC` frame wait). Only read after the signature matches. |
| `$0188-$018C` | in-game SFX (`asm/game_sfx.asm`): `$0188` R in ARAM, `$0189` restore state, `$018A` restore wait, `$018B` song last uploaded, `$018C` command waiting for the next main-loop pass (cornered / enemy hit). Zero after reset (0 = song 0, whose samples cover R). |
| `$018D-$0195` | world map music (`asm/title_music.asm`): `$018D` foreign driver running (0 Hudson's, 1 SB1's, 2 SB2's, 3 the accept SFX player, the SPC waiting in the IPL ROM), `$018E` the map's driver (set by `map_music`), `$018F` last port-0 command sent to it, `$0191` last port-1 command, `$0192` scratch (also `asm/world_map.asm`), `$0193` the map music was requested and plays, `$0194` upload part counter, `$0195` upload sequence; `$0190` map animation 0 off / 1-2 sea / 3-4 stars (`asm/world_map.asm`). Zero after reset. |
| `$7F:FB00-$7F:FB03` | world map animation (`asm/world_map.asm`): sea frames left, sea frame, ship light frame, star half-line. |
| `$7F:FB10-$7F:FB13` | World 1 exit door (`asm/world1.asm`): door x (0 = not chosen), y, scratch (count, index). Reset by the stage's `FF 1A F6 03`. |
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

While the title music streams, the stream driver owns `$7000-$B8FF`
(driver + SFX scripts `$7000-$72FF`, ring `$7300-$B89B`,
110 chunks; sizes are computed by the build), inside SB5's title-song
area; everything else (Hudson's code, sets, directories, echo buffer) is
untouched. The stream uses voice 7 and timer 0; the menu SFX samples are played
on voice 0 with timer 2 (4 ms ticks, `$FC = 0`). Release restores the DSP
registers it touched, `$F1` from Hudson's shadow `$1E` and `$FC` from `$21`.
