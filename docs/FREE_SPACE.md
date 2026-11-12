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
| `$EB:176A-$EF:FFFF` | ~320 KB | unassigned. |
| `$F0:0000-$F2:FFFF` | 192 KB | `obj_f0`..`obj_f2`: OBJ sheets (raw 4bpp, 1 KB strips aligned to `$400`: bomber, Louie sheets recolored for palette entries 1-7) and the relocated OBJ sheet table (`tools/sb6/objsheets.py`). |
| `$F3:8000-$F3:FFFF` | 32 KB | `objmap`: sprite mappings and bomber animation scripts, addressed as bank `$B3` (the OAM builder needs WRAM in the data bank). |
| `$F3:0000-$F3:7FFF`, `$F4:0000-$FF:FFFF` | ~800 KB | unassigned. |

Budget note: streamed audio costs ~9 KB per second (16 kHz mono). The whole
free ROM holds only ~2.5 minutes of it, so streaming is for the title only;
in-game music should be converted to sequences for Hudson's driver (or a new
sequenced driver).

## WRAM

| Address | Owner |
|---|---|
| `$0100-$0107` | title music stream (active, sequence, pointer, bank, loader kick, frame, SFX toggle `$0107`). Bottom of the stack page: in a 12 000-frame run (intro, title, menus, Zone 1) the stack never went below `$01B3`. The recomp's co-op mod also treats this area as free (`$011E`); keep new variables after `$0110`. |
| `$0110-$015C` | co-op (`asm/coop.asm`): `$0110` 6x4 distance arrays, `$0128` mount offset, `$0129` player count, `$012A` roster (word), `$012C` participant mask, `$012D` actor base, `$012E` co-op stage flag, `$012F` spawn check, `$0130-$0143` P3/P4 fields saved while benched, `$0144` benched seats (bit = 1 << seat), `$0145-$014E` scratch, `$014F-$0152` OBJ palette arbitration scratch, `$0153` highest static OBJ page, `$0154` co-op stage frame timer, `$0155` boss stage flag (word), `$0157` bench scratch (word), `$0159-$015A` P3/P4 spawn anchor x, `$015B-$015C` anchor y. Set by the boot hook after the reset clear. |
| `$0160-$0187` | Louie palettes (`asm/louies.asm`): `$0160` half of each actor (24 bytes, 0 = none), `$0178` users of the 3 halves, `$017B` palette id in each half, `$017E` OBJ slot of the main / spare palette (0 = none), `$0180-$0187` scratch. Zero after reset; forgotten when the slot table loses the `$FF` mark (new stage). |

## ARAM (sound RAM)

While the title music streams, the stream driver owns `$7000-$CF7D`
(driver + SFX scripts `$7000-$74FF`, ring `$7500-$CF7D`,
143 chunks; sizes are computed by the build), which is SB5's title-song
area; everything else (Hudson's code, sets, directories, echo buffer) is
untouched. The stream uses voice 7 and timer 0; the menu SFX are replayed
on voice 0 with timer 2 (4 ms ticks, `$FC = 0`). Release restores the DSP
registers it touched, `$F1` from Hudson's shadow `$1E` and `$FC` from `$21`.
