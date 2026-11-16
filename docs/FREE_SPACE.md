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
| `$EC:0000-$EF:FFFF` | 256 KB | `stream_ec`..`stream_ef`: bomber poses streamed one by one (DMA sources, `asm/bombers.asm`). |
| `$F0:0000-$F2:FFFF` | 192 KB | `obj_f0`..`obj_f2`: OBJ sheets (raw 4bpp, 1 KB strips aligned to `$400`: bomber, Louie sheets recolored for palette entries 1-7) and the relocated OBJ sheet table (`tools/sb6/objsheets.py`). |
| `$F3:8000-$F3:FFFF` | 32 KB | `objmap`: sprite mappings and bomber animation scripts, addressed as bank `$B3` (the OAM builder needs WRAM in the data bank). |
| `$F4:8000-$F4:FFFF`, `$F5:8000-$F5:FFFF` | 64 KB | `objmap2`, `objmap3`: mappings/scripts of characters 1-9 (banks `$B4`, `$B5`), used when `objmap` is full. |
| `$F6:0000-$F9:FFFF` | 256 KB | `obj_f6`..`obj_f9`: OBJ sheets of edited characters 1-9 (after `obj_f0`..`obj_f2`). |
| `$FA:0000-$FB:FFFF` | 128 KB | `title_fa`, `title_fb`: animated title (`tools/sb6/features/title_anim.py`): raw tiles and map rows sent by DMA, job/frame tables, `asm/title_anim.asm` (~94 KB used). |
| `$FC:0000-$FC:A1FF` | 41 KB | `title_fc`: the title intro's sounds (pan + character drops) as streamed BRR chunks (must start the bank; the rest holds save menu music). |
| `$F3:0000-$F5:7FFF` (lower halves), `$FC:D9B0-$FC:FFFF` | ~105 KB | unassigned. |

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
| `$7F:FF00-$7F:FF7F` | character selection (`asm/picker.asm`): `+$00` picker running, `+$01` choices valid, `+$02` choice of 5 seats, `+$08` color of 5 seats, `+$10` saved `$1032-$104F`, `+$30` saved `$1D20-$1D3F`, `+$50` scratch, `+$5C` glyph tiles sent, `+$5D` glyph sprites drawn, `+$5E` cell sprite colors loaded, `+$60` scratch, `+$64` OAM of the seat numbers, `+$68` character whose grid cell uses OBJ palette 4, `+$69` CGRAM shadow changed (sent when the VRAM queue is empty), `+$6A` high byte of that word, `+$6C` character whose grid cell holds the tiles for OBJ palette 4. `$7F:E000-$7F:FFFF` was never written in a 12 000-frame run (title, menus, picker, Zone 1); flags are compared with exact values and cleared on the title, so they do not depend on the reset contents. |
| `$7F:FD00-$7F:FD3C` | animated title (`asm/title_anim.asm`): `+$00` `$5AA5` once started, `+$02` state (0 off, 1 loading, 2 waiting for the fade-in, 3 intro, 4 idle), `+$03` intro seen, `+$04` logo landed, `+$05` main screen layers, `+$06` list/frame offset, `+$08` loading the finished scene, `+$0A`/`+$0C` BG1/BG2 V scroll, `+$0E` pad held, `+$0F`-`+$15` idle counters and RNG, `+$16`-`+$1D` the two alternate-pose areas, `+$1E` 7 character timers, `+$26`-`+$2D` scratch, `+$2E`-`+$39` menu cursor (frames without input, animation 0 rest / 1-4 look around / 5 confirming / 6 confirmed, its frame and face, pose and sprite frame in VRAM, refresh counter, scratch, the cursor Y / menu `$1036` / menu Y `$1034` when the confirmation began), `+$3A` cursor visible last frame, `+$3B` forced resend, `+$3C` `FF 1A FC` frame wait). Only read after the signature matches. |
| `$0188-$018C` | in-game SFX (`asm/game_sfx.asm`): `$0188` R in ARAM, `$0189` restore state, `$018A` restore wait, `$018B` song last uploaded, `$018C` command waiting for the next main-loop pass (cornered / enemy hit). Zero after reset (0 = song 0, whose samples cover R). |
| `$0160-$0187` | Louie palettes (`asm/louies.asm`): `$0160` half of each actor (24 bytes, 0 = none), `$0178` users of the 3 halves, `$017B` palette id in each half, `$017E` OBJ slot of the main / spare palette (0 = none), `$0180-$0187` scratch. Zero after reset; forgotten when the slot table loses the `$FF` mark (new stage). |

## ARAM (sound RAM)

SB6 menu SFX: samples at `$B900-$DCFF` (~9 KB used), directory entries
`$39-$3B` (`$FDE4-$FDEF`), tuning `$FEE4-$FEEF`, instruments 28-30
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
