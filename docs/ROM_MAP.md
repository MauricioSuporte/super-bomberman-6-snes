# Super Bomberman 5 (USA) — ROM notes

What the hack relies on, verified with Mesen 2 traces and disassembly
(`tools/disasm65816.py`, `tools/spc700dis.py`). Addresses are SNES (HiROM:
file offset = address & `$3FFFFF`). See also the recomp's `AGENTS.md`.

## Hardware setup

* HiROM, 4 MB, header at file `$FFC0` (title), checksum `$FFDC-$FFDF`.
* Native vectors: RESET `$C0:F348` (S = `$01FF`, D = 0), NMI `$C0:F3BA`
  (→ `$80:F3BE`; increments `$68` at `$C0:F431`), IRQ `$C0:F468`.
* Main loop `$C0:0B2C`: if `$03BF` = 0 wait for NMI (`$C0:F496`), then
  `$C0:0B3E` tasks. Runs once per frame on the title.

## Compressed data (`$C0:1CB0` / `$C0:1CCC`)

Control byte = mode (bits 5-7) + count-1 (bits 0-4). Modes: 0 literal,
1 previous+1, 2 previous, 3-7 copy from 2/4/16/32/64 bytes back (256-byte
ring). Encoder: `tools/sb6/lz.py`.

## Graphics sets

`26 n` (script op) selects set `$0AE7`. Per set:

| What | Table | Entry |
|---|---|---|
| Archives (`27 n`, `$C0:1B04`) | word at `$C0:1C96 + 2*set`, bank `$E3` | 8 bytes: VRAM word, size, src24, flags (bit 7 raw, low bits type: 2 BG, 5 OBJ) |
| Palettes (`2A n`, `$C0:01AC`) | word at `$C0:0379 + 2*set`, bank `$81` | word at table + 2*(id-1) → `[dest, count, colors…]` into CGRAM shadow `$7E2910` |
| Arrangements (`FF 8D arr set layer x y`, drawer `$C0:001B`) | long at `$C0:8000 + 3*set` | words in the table's bank → parts `[w, h, x, y, mode]` + LZ low stream (+ high stream if mode 0), until a 0 width byte. Width must be even (`$C0:0135` writes 2 entries per step). |

Set 3 = SB5 title graphics, set 4 = SB5 arrangements. **Set 5 was null in all
three tables and now belongs to the hack** (archives 1 title tiles, 2 BG3
glyphs, 3 boot logo; palettes 1 title, 2 boot logo; arrangements 1 logo,
2 scene, 3 version, 4 1-4 PLAYER GAME, 5 boot logo). Sets 1 and 2 are also
null. The archive set table ends at `$C0:1CAF` (13 sets).

## Script VM

Dispatch `$C2:0230`; op table `$C2:04F8 + 2*op`; operand lengths
`$C2:0AF5 + op - 1`; `FF xx` ops at `$C2:0650 + 3*(xx-1)` (lengths
`$C2:09D8`), `FE xx` at `$C2:094D`. Ops used by the hack: `24 a24` call,
`00` return, `45 n` skip n bytes, `26 n` set, `27 n` archive, `2A n` palette,
`28 n` OBJ archive, `2C n 02` start task, `3A …` create object,
`42 id group` sound request, `FF 8D arr set layer x y` draw arrangement,
`FF 91 x y w h layer` clear rectangle, `FF 21 layer x16 y16` BG scroll
(shadows `$0319+2(l-1)` H, `$031F+2(l-1)` V), `FF 0C x0 y0 x1 y1 2` window
of the HDMA blink (WH2/WH3). `5D a` / `61 n` / `AE` are arithmetic on the
script accumulator (`61` = add).
* The BG3 drawers (`FF 8D`, `FF 91`) add the layer scroll back, so scrolling
  a layer does **not** move text drawn with them; move the arrangement rows.

## Boot (Hudson logo, intro)

* Mode `$01` shows the Hudson logo: script `$C7:0AC4`
  (`26 03 27 46 2A 2B` set 3 archive `$46` + palette `$2B` (32 colors at
  `$81:A34A`), `0D 08`, `FF BB 00`, `FF 8D D3 04 01 00 00` arrangement `$D3`
  of set 4 on BG1). Mode 1, BG1 only (map `$3000`, chr `$0000`).
* `$C7:0AF5` `0F A9` switches to mode `$A9` (intro, then the title). Start
  during the intro goes to mode 2 (title without intro).
* The hack loads the new logo from set 5 (archive 3, palette 2 with 128
  colors, arrangement 5) and changes `0F A9` to `0F 02`, so the intro is
  skipped (`tools/sb6/features/boot_logo.py`, `title.py`).
* Script pointer of the running script: `[$0A]` (fetch at `$C2:0397`).

## Title screen

* Mode 1. BG1 logo (map `$3000`), BG2 scene (map `$3800`), BG3 text (map
  `$4000`, chr `$5000`, CGRAM 0-3 = palette 8 of set 3). BG1/BG2 chr at
  `$0000` (768 tiles max). OBJ `$6000`.
* Intro path (mode `$A9`) setup script `$C6:FC93`; title without intro (mode
  2) handler list `$C7:1783` (2 = `$C7:17D1` load, 4 = `$C7:17DE` OBJ
  archives, 6 = `$C7:17E3` draw).
* Menu cursor Y is `$1034`: set to `$A0` when the title appears
  (`5B A0 60 34 10` at `$C6:FE6F` intro path, `$C7:184C` mode 2) and
  recomputed as item * 16 + `$A0` on each move (`$C7:1ABF`). The hack moves
  all three up with the text.
* SB5 extras removed by the hack: palette-cycling tasks `2C 12/13/14 02`
  (`$C6:FCBB`, `$C7:1832`) and the two characters (`$C6:FD7C`, `$C6:FDC9`,
  `$C7:1821`). Details in `tools/sb6/features/title.py`.
* BG3 text is art, not a font: tiles `$102-$13A` of set 3 archive `$96`
  (raw 2bpp, VRAM `$5810`). Letters are 8x16 (two tiles): stroke color 2,
  1-px outline color 1. Set 4 arrangements (table at `$C0:8000+3*4`):
  #4 `$E2:06B4` PUSH START (row `$10`), #5 `$E2:0706` menu (row `$12`),
  #6 `$E2:07A2` © HUDSON (row `$19`), #7 `$E2:07F4` menu variant (row `$12`).
  Header = `w h x y attr`.
* Menu clear blocks `FF 91 09 12 10 06 03` at `$C7:18B6`, `$C7:19B7`;
  PUSH START blink window `FF 0C 30 80 D0 90 02` at `$C6:FE63` (intro) and
  `$C7:181A` (mode 2); © draw `FF 8D 06 04 03 00 00` at `$C6:FE50`,
  `$C7:1802`. Cursor Y = item*16 + `$A0` (`61 A0` at `$C7:1ABF`).

## Sound (CPU side)

* API `$C0:0CED` (JSL; A = id, B = group, 8-bit):
  * group 2: menu SFX, command from `$80:86D0 + id` via `$C0:0E7F` (port 0,
    bit-7 toggle, waits for the echo);
  * group 3: queues a data stream (`$03C4`, sent by `$C0:106C`, command `$31`);
  * group 4: `$C0:114C` loads up to 3 sample sets from `$80:8789`;
  * group `$10`: driver commands on port 1 (`$1001` = stop);
  * others: `$80:8655 + 3*id` = `[set, song, cmd]` → `$C0:0E31` set upload
    (if ≠ `$03CE`), `$C0:0E9C` song upload (if ≠ `$03CD`), then the command
    twice through `$C0:0E7F`.
* Script music load `$C0:1171` uploads its song unconditionally.
* Title flow: `0401` (sets), `$C0:1171` song 1, `0002` = play title music.
  Options: `0204` → `1001` → `0401` → song 1 → `0002`.
* All APU port accesses are in `$C0:0DC0-$C0:1130`.

* Title menu SFX (group 2): `1` cursor move, `4` accept, `3` back (only
  on Options). Hudson plays them on voice 0, sample `$20` (DIR `$FD`),
  ADSR `$FF/$E0`, a frame every ~16 ms. Captured with
  `tools/mesen/sfx_capture.lua` on a base-ROM copy whose title song is
  silenced (cmd byte of `$80:8655` entry 2 = 0), converted by
  `tools/capture_sfx.py`. Mesen's `spc.cycle` counts at **2.048 MHz**.

## Sound driver (Hudson, ARAM)

* Uploaded at boot through the IPL ROM, entry `$0800` → init `$0880`. Main
  loop `$08C6`. Uses timer 1 (enable shadow `$1E`, targets `$1F+X`), stack
  in page 1 (SP `$3F`), echo buffer `$DD00` (EDL 4), sample directories
  `$FD00`/`$FE00`, `PCALL` routines at `$FF00-$FFBF`.
* Port 1 = `$10` enters **Hudson's own loader at `$0FF0`** (calls `$0965`,
  which clears the input ports, then signals `$AA`/`$BB`). It speaks the IPL
  protocol, but the final "jump" command just returns (`RET` at `$1041`) to
  the driver. The ROM image of `$0FF0` is at `$DF:2B3A`.
* `$0ADC` `JMP $FFC0` (real IPL) is a different, full-reset path.
* ARAM while the title is up: sets `$3000-$5924`, title song 1 at
  `$7000-$CFDF`.

## Hooks installed by the hack

| Address | Original | Purpose |
|---|---|---|
| `$C0:0CED` | `85 9F EB C9 10` | title music stream (`asm/title_music.asm`) |
| `$C0:0B2C` | `AD BF 03 D0 04` | stream feeder, once per main-loop pass |
| title scripts | see `tools/sb6/features/title.py` | SB6 title graphics |
| co-op | see `tools/sb6/features/coop.py` | 3/4-player Normal Game (below) |

## Normal Game co-op (3-4 players)

Ported from the recomp's `normal_coop_mod.c` / `coop_corner_spawns_mod.c`
(`docs/NORMAL_COOP.md` there). With 1-2 players every hook takes the stock
path (roster 2, actor base `$18`, mount offset from `$1CBF`).

* Pads: `$C0:0A56` already reads 5 seats (multitap BIOS `$C0:F1D7`, raw
  `$19-$27`). Per seat: held actions `$2C+s`, held dirs `$31+s`, new actions
  `$36+s`, new dirs `$3B+s`; bits A `$80` X `$40` L `$20` R `$10` B `$08`
  Y `$04` Select `$02` Start `$01`.
* Title players menu: `$1036` menu (1 = players), `$1032` cursor, `$1037`
  limit, confirm script at `$C7:18ED` (patched at `$C7:18F4`).
* Stage: `$1031` mode/stage (bosses `$67-$6E`), `$1D1A` bit 0 Battle,
  `$1D25` participant mask, `$1D24` 1/3, `$1D23` shared lives, `$1CBF`
  bomber slots + mount offset. Per seat: `$17FA` object (`$FF` none),
  `$15A2` status (`$80` dead), `$16AA` cell, `$4E8D/$4EA5` spawn tile,
  `$16C2/$16DA` character/palette id (`$C0:BB4E`: 1 white 2 black 3 red
  4 blue). Collision `$1052` static, `$1152` dynamic (16 columns).
* Stock rejoin `$C5:060E-$065C` (Start held, `JSR $065D`, `JSL $C42A69`
  spawn, `JSL $C428CF`, `DEC $1D23`); replaced by `e4_frame` in co-op.
* Seat loops bounded by 2 (22 sites) jump through stubs comparing with the
  roster; 28 mount-offset operands read `$0128`; the 6 distance arrays at
  `$C3` were moved to `$0110`.
* OBJ palette slots (`$C0:0295`: `$0346` palette id, `$0347` slots
  needed, `$0348` mask; per slot `$2B10` id, `$2B18` set, `$2B20` run,
  `$0349` references; object slot `$06DF+obj`; release `$C0:0345`; failure
  `$C0:0303`). Stock use: 0 stage, 1/2 P1/P2, 3-5 enemies (`$38`), 6-7
  eggs, loose Louies (`$C4:4C4E`, `$C4:4DAD`, `$C4:582B`, set 4 palettes
  `$30`/`$38`/table) and large stage objects (`$C0`). A ridden Louie writes
  its 8 colors into entries 8-15 of the rider's slot (`$C4:53EB`). Bomber
  colors: `$C4:37B0`.
* Co-op palettes: P3/P4 ask for mask `$F0` (slots 4/5 when free, so 6/7 stay
  for eggs and Louies). When a stage request fails, `c0_palfail` moves P3/P4
  off the slots it needs onto P1's slot (they show P1's colors; `$C4:37B0`
  does not repaint it) and searches again; `e4_tick` (main loop `$C0:0B44`)
  gives them a free slot 4-7 back every 16 frames. `$C5:060E` is not a
  per-frame hook: that task only runs while a player is dead.
* OBJ tile pages: `$1D00-$1D0F` owner of each 1 KB page at VRAM
  `$6000+$200*i` (object id, `$FF` free, `$7F` pending free, `$7E`
  static); `$1D10` pool size (init `$C5:6A14`: 5 in stages via `$C5:69DF`,
  8 via `$C5:6A00`), allocator `$C5:6AF5`, release loop `$C5:6B08` (from
  index `$1D10` down). Stage static sprites (bombs, items, enemies) are
  queued at pages 5+ and DMA'd by `$C0:0540` (`$0361` VRAM, `$035F` bytes)
  ~130 frames after the stage hook; how many pages they take depends on the
  stage (5 to all 11: stages `$41`,`$42`,`$44-$46`,`$60-$62` use all 16).
* Co-op pages: four bombers take four of the five pool pages, so eggs and
  Louies were drawn with a bomber's tiles. `c0_vmadd` (`$C0:0573`) records
  the highest static page written; 240 frames into the stage `e4_tick`
  frees every `$7E` page above it and sets `$1D10` = 15.
* P3/P4 spawn in the lower corners (moved to the nearest safe floor after
  the map copy, `$C5:3D5B`), use red/blue, and rejoin with Start at the
  nearest safe cell for one shared life. Boss stages `$67-$6E`: P3/P4 sit
  out (their fields are saved and restored for the next zone).


The full list with sizes is generated in `build/sb6.map`.
