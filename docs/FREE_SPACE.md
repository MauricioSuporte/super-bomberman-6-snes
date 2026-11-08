# Free space and ownership

`tools/build.py` registers each region with `add_region()`, which fails the
build if any byte is not `$FF` in the base ROM. Allocations are listed in
`build/sb6.map`.

## ROM

| Region | Size | Owner / rule |
|---|---|---|
| `$C1:FA00-$C1:FFFF` | 1.5 KB | `bank81`: palette tables and colors (must be in bank `$81`). Only free space in that bank. |
| `$E3:DD60-$E3:FFFF` | 8.7 KB | `e3_tables`: graphics archive tables (must be in bank `$E3`). |
| `$E4:0000-$E4:FFFF` | 64 KB | `bulk`: hack code (65816), scripts, arrangements, title tiles. |
| `$E5:0000-$EB:176A` | 390 KB | streamed BRR (title music), 404 chunks of 162 bytes per bank. |
| `$EB:176A-$FF:FFFF` | ~1.3 MB | unassigned. |

Budget note: streamed audio costs ~9 KB per second (16 kHz mono). The whole
free ROM holds only ~2.5 minutes of it, so streaming is for the title only;
in-game music should be converted to sequences for Hudson's driver (or a new
sequenced driver).

## WRAM

| Address | Owner |
|---|---|
| `$0100-$0106` | title music stream (active, sequence, pointer, bank, loader kick, frame). Bottom of the stack page: in a 12 000-frame run (intro, title, menus, Zone 1) the stack never went below `$01B3`. The recomp's co-op mod also treats this area as free (`$011E`); keep new variables after `$0110`. |

## ARAM (sound RAM)

While the title music streams, the stream driver owns `$7000-$CEA7`
(driver `$7000-$71FF`, ring `$7200-$CEA7`), which is SB5's title-song area;
everything else (Hudson's code, sets, directories, echo buffer) is untouched.
