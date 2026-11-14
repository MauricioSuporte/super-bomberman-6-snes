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
* Seen in Mesen: the first archive sent after Battle's character picker
  (`29 22 F0 08` from a new script) reaches VRAM wrong, the same archive
  sent again after others is right (the Normal menu always sends `$0C`
  first). Cause not traced; `asm/picker.asm` sends `$22` twice.

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
| `$C7:10E2`, `$C7:0E27` | `24 4C 12 C7` | file confirm -> character selection (`asm/picker.asm`, below) |
| `$C2:069B` | `7C 46 C1` | script op `FF 1A nn`: nn >= `$F0` runs `pick_op` |
| `$C0:F421` | `22 E0 04 C0` | NMI: cursor glyph tiles of the picker (`pick_nmi`) |
| `$C0:01FA` | `A9 81 85 AA C2 30` | palette lookup: ids `$80+` of set 0 = bomber palettes (`pal_lookup`, `asm/bombers.asm`) |

## Script VM details, pads, OAM (found for the character selection)

* Fetch `$C2:038F`: the operand pointer is `[$0D]`, `$0A-$0C` already
  points at the next op when the handler runs (and is saved per task in
  `$0C87/$0CAF/$0CD7 + task`, so task 9 reads `$0C90/$0CB8/$0CE0`). Plain
  ops are `JSR`-called (word table), `FF` ops are entered with
  `JML [$00BD]` (3-byte pointers at `$C2:0650 + 3*(n-1)`, all 255 used),
  X = task (`$73`), Y = 1, M/X 8-bit, return `RTL`.
* Call `24 a24` (`$C2:1714`) pushes the 3-byte return address on the script
  stack `$7E:2000 + $10` and increments `$0CFF + task`; `00` pops it
  (`$C2:02FE`). A script whose bank is below `$C6` is dropped
  (`$C2:0254`).
* Tests set a flag (`$0373/$0374`, `$C1:74D1`): `86 v` acc == v, `8A v`
  acc != v, `96 v` acc < v; `49 n` skips n bytes when false, `47 n` when
  true, `45 n` always; `44/48/46 rel16` the same with a word. `30 n` selects
  the pad (`$1042`, `$FF` = any), `31 mask` tests new actions (`$36+pad`),
  `34 mask` directions.
* Pad reader `$C0:0A56` (raw words at `$19 + 2*pad`): `$2C+pad` held actions
  = A `$80`, X `$40`, L `$20`, R `$10`, B `$08`, Y `$04`, Select `$02`,
  Start `$01`; `$31+pad` directions (up 8, down 4, left 2, right 1);
  `$36+pad` new actions, `$3B+pad` new directions, `$40+pad` repeats.
* Main loop: `$C0:0B41` pad reader, `$C0:0B44` `JSL $C022F0` runs every
  task (scripts, objects, the OAM builder `$C0:1459`). OAM shadow `$08BF`
  (x, y, tile, attributes x 128), high bits `$0ABF`; the builder fills from
  sprite 0 and hides only the sprites it used the frame before (`$03D5` =
  sprites left free), y = `$E0`.
* NMI `$C0:F3BE`: forced blank, the frame's transfers, `JSL $C004E0` (VRAM
  queue) last, then the screen is turned back on.

## Character selection (Battle's picker, used by the Normal Game)

* Script `$C6:89CF`, ends with `00` after its fade-out, so it can be called
  with `24`. Inputs: `$6269+seat` (1 = human, 0 = not playing: an X in the
  portrait row; the recomp uses 2 = CPU), `$1038` = 0. Outputs:
  `$625F+seat` choice (1-9), `$6264+seat` color, `$1040` = `$FF` when it was
  left with B (any pad). It counts the seats in `$1039` and ends by itself
  when `$1038` (confirmed) reaches it. Mode `$1031` must be 4.
* State while it runs: `$62AB+pad` seat of the pad's cursor, `$62B5+seat`
  0 pending / 1 choosing / `$FF` confirmed, `$62BF+seat` portrait object,
  `$62C9+cell` character of the 10 grid cells, `$62D3+cell` its color.
  Main loop at `$C6:8E68` (the pc of task 9 while it waits); the main part
  is `$C6:8B48-$C6:8EE3`.
* Colors: portrait = palette id `$80:BB4E[char] + color` (set 0) in the OBJ
  palette slot of the portrait object; grid cell = 8-color BG strip, id
  `$C2:130B + 7*char + color`, CGRAM index `$C2:1301 + cell` (an index with
  bit 3 set shares its first entry with the strip below: skip it).
* Screen: OBJ tiles at `$6000`; the cursor sheet uses tiles `$01-$23` of the
  first page, portraits take pages from tile `$100`. Cursor label: tiles
  `6+2n` (digit) and `7+2n` ("P"), attributes `$3C`, the "P" one sprite
  before the digit; ink colors 15, 3, 9, 11 (P1-P4), outline 1.
* It replaces the Normal menu's VRAM `$08F0-$15EF` and BG2 map; the menu's
  loader script is `$C7:0B47` (mode 3 init steps: `$C7:0B24`, `$C7:0B47`,
  `$C7:0B6E`, `$C7:0B71`).
* Normal menu: state machine `$C7:0BB9` on `$1037`, each state a called
  script (`$C7:100E` New Game file list, `$C7:0D59` Continue file list).
  File confirm: `42 04 02 / 24 4C 12 C7` (`$C7:124C` = 64-frame fade) at
  `$C7:10DF` and `$C7:0E24`; what follows uses `$1032` (file).
* Hack (`asm/picker.asm`, `tools/sb6/features/picker.py`): the confirm calls
  a script that fades, saves `$1032-$104F` and `$1D20-$1D3F`, runs the
  picker for the game's seats and restores; confirmed choices go to
  `$16C2+seat` / `$16DA+seat` and are applied again after the player reset
  (`$C4:28B4`, co-op `c4_tail`) and at the stage spawn (`$C2:1697`, not in
  boss stages). B reloads the menu graphics, drops the call and jumps to
  the file list. L / R (per frame, `pick_tick` from `e4_tick`): color of
  the seat under the pad's cursor, portrait slot = seat (shared slots are
  split first), grid strip. The label "L + R" uses 12 tiles at `$F0`
  (generated by the build, sent by the NMI hook when the picker's loop
  starts) in the last 12 OAM sprites; the stock digit and "P" move 40
  lines down. Colors per character: tables `chpal` (palette id of color 0,
  `$80 + n` = own palettes, 0 = the cartridge's `$80:BB4E[char] + color`)
  and `chcol` (count; 6 for the stock characters). The portrait keeps the
  cartridge's id (color mod 6): its art is SB5's. Tested in Mesen: New
  Game with 1, 2 and 4 players, B and back in. Not tested: Continue (needs
  a save), Game Over -> Continue, boss stages.
* Palette lookup `$C0:01DE` (A = id, set `$0AE7`): `[$A8]` = `$81:` word of
  the set's table (`$C0:0379 + 2*set`) at `2*(id-1)`; every loader goes
  through it (`$C0:01AC`, `$C0:01C8`, the slot allocator `$C0:0295`, which
  takes 16 colors when the palette's count says so). Hack: with
  `BombermanPallete.png`, ids `$80 + n` of set 0 are the picture's columns
  (n = 0 is column 1; table and data in `$E4`, the hook also sets the bank
  in `$AA`); ids 1-6 are replaced in place by columns 1-6, so Battle and
  the co-op defaults keep working. A Bomberman chosen in the picker uses
  `$16DA` = `$80 + color`.
* Grid figures of the picker: BG1 (map `$3000`), 2x3 tiles mirrored
  (`2C91 6C91 / 2CA1 6CA1 / 2CA0 6CA0` for the first cell at tiles 5-6 x
  16-18; empty tile `$211C`), 8 colors each. Hack, only in the Normal Game:
  the first cell (Bomberman) is emptied and drawn as two 16x16 sprites with
  the SB6 pose facing the screen (`bombers.STAND`; tiles `$C0-$C3` and
  `$D0-$D3`, OBJ palette 5, which no object of the screen uses with up to
  four seats; OAM sprites 114/115).
  The first redrawn character of the first row (1-4, with `stand` and own
  palettes; today character 1) gets the same treatment in its cell (BG
  tiles x = 5 + 5*char): tiles `$C4-$C7` / `$D4-$D7`, OBJ palette 7 (CGRAM
  `$F0`, refs 0 with four seats), OAM sprites 112/113, colors = its own
  palette (`$80 + paltab index`, `XPAL` + color).

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
  `$C0:0303`). Stock use: 0 stage (bombs, items: set 0 id `$58`), 1/2 P1/P2,
  3-5 enemies (`$38`), 6-7 (`$C0`) player effects `$C4:4C23`/`$C4:4D82`
  (set 4 palettes `$30`, `$38` = 32 colors, two slots) and large stage
  objects (`$C4:57C5`, table `$80:C21C` by stage). Bomber colors:
  `$C4:37B0`. Mounts and eggs: "Mounts (Louies) and eggs" below.
* Co-op palettes: P3/P4 ask for mask `$F0` (slots 4/5 when free, so 6/7 stay
  for the Louie palettes; `$D0` in boss stages, where slot 5 belongs to the
  rival in seat 4 and its mount: sharing it let the intro blink restore
  `$C1:0035` paint P4's reclaimed slot black). When a stage request fails, `c0_palfail` moves P3/P4
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
  nearest safe cell for one shared life.
* Boss stages `$67-$6E` (`!bossst`): script ops `$C2:16B8/$C2:16EE`
  (`LDA [$0D] / DEC A / TAX`, 1-based bomber slot) create the rival; boss
  start `$C2:16E6` → `$C4:3C60` (A = boss index 0-8, tables `$C0:B9A5`
  graphics, `$B9AE` `$1CBF` = 3, or 4 for index 4 = two rivals, `$B9B7`
  rival mount type, `$FF` none): `$C4:3C7F JSR $3D30` saves P1/P2 mounts
  (literal actors `$16C4/$16C5`, `$16DC/$16DD`), `$C4:3C82` equips slot 2
  (`$3C8B` slot 3 when Y = 4), `$C4:3C97` seats the mounted rival (slot 2,
  mount `2 + $1CBF`). Choreography `$C5:2600-$C5:39FF` names the rival by
  literal: 57 `LDX #2` before `JSL $C4:3C24/$C4:3BDE`, 23 `LDA #2` before
  `JSL $C4:2B3A/$C4:3BA3`, 18 `LDA $17FC` (slot 3: 6 + 3 + 3 operands).
  The hack moves the slot-2 rival to slot 4 (P5) in every one of them, boss
  stages always use the five-slot layout (`$1CBF` = 5, mounts rider + 19,
  rival mount 23, mount backups +17) and P3/P4 fight (spawn two tiles left
  of P1 / right of P2, then the nearest safe floor). `$6A` (two rivals,
  slots 3/4): P4 sits out with its fields saved for the next stage.
  Rival flags `$101F+seat` of seats 2-4 are cleared at the player reset.

## Object sprites (bombers)

* Per object type `T` (`$04FF+obj`; every bomber is `$10`): animation table
  `$C0:171D + 3T` (long) -> word per animation id (`$079F+obj`, 1-based) ->
  script of `[mapping, frames]` pairs, a zero frame count restarts it
  (`$C0:11F8` loads the pair at offset `$07FF+obj` into `$049F`/`$07A0` and
  makes the table's bank the data bank, so scripts also need a `$80-$BF`
  bank; step `$C0:1254`: timer `$07A0` counts down, `$FF` = hold forever, so
  `[0, $FF]` ends an animation with nothing drawn, e.g. death `$16`; the
  game itself waits 60 frames after a death starts); mapping table `$C0:16CC + 3T` (long) -> word
  per mapping id (`$049F+obj`) -> `[count]` + count x `[x16, y16, tile16,
  attr]` (`$C0:1289` stores the pointer in `$7E:2EEA+obj`, bank `$7E:2F4A`).
  attr: bit 0 = 16x16 (OBSEL 8x8/16x16), `$40`/`$80` flips, `$20` in every
  stock piece. A count of 0 loops 256 times.
* OAM builder `$C0:152E`: sets DBR to the mapping's bank and keeps using
  absolute WRAM addresses, so **mappings must sit in `$80-$BF`** (upper half
  of a ROM bank), never in `$C0-$FF`. Tile = mapping tile + `$073F+obj`.
* Bomber tiles are dynamic: `$C4:3A27` (A = animation, X = seat) reads
  `[sheet, row]` at `($80:BB66 + 2*char) + 2*(anim - $1692+seat)` and queues
  it (`$C5:6A6B`: `$1CCC` sheet, `$1CEA` row, `$1CD6` object, `$1CE0`
  animation). `$C5:6B77` DMAs **1 KB (32 tiles = 2 rows of 16)** from
  `sheet source + row*$200` to the object's page; `$C5:6B36` sets
  `$073F = (page*2 - row) * 16`, so mapping tiles are numbered from the top
  of the sheet. All poses of one animation share those 32 tiles.
  While a bomber walks the stock code queues its animation again every
  frame: each NMI loads the strip into a newly allocated page (they rotate,
  e.g. 0-1-2) and `$C0:11DD` re-runs the current step, so the OAM shown in
  a frame uses the page allocated one NMI before.
* Hack, streamed poses (`asm/bombers.asm`): an animation whose poses do not
  fit 32 tiles together gets one block per pose (<= 16 tiles, 8 columns x 2
  rows, region `stream_ec`+). The page is a double buffer: `bomber_stream`
  (from `bomber_map`, each mapping resolve) moves `$073F` to the other half
  and queues the pose; `stream_nmi` (replaces `JSL $C56AAF` at `$C0:F41D`,
  right after the OAM DMA of the same vblank) DMAs both rows. Pending DMAs
  are per half: after the stock reload of the page in the NMI, the half
  still shown needs its pose again in the same NMI as the next pose.
  Checked in Mesen frame by frame (OAM + VRAM rebuilt): character 1 walking
  in all four directions, every frame a complete pose.
* OBJ sheet table `$85:E22D`, 8 bytes per sheet (1-based): `[0, 0, size16,
  source24, $85]`. White bomber = character 0 = sheets 1/2 (`$C7:4000`
  `$2000` bytes, `$C7:6000` `$1800`, raw 4bpp); characters 1-9 use sheets
  3-20. Louies: `$C4:5442`, table `$80:C415`.
* Bomber type `$10`: animations 1-`$4D`, mappings 1-`$A3` (none shared
  between animations), groups of four animations = right, down, left, up.
  Art uses colors 1-8 only (9-15 of the slot are the ridden Louie's).
* Character n (0-9) is object type `$80:BB44[n]` = `$10 + n`, each with its
  own mapping and script tables (same animation numbers 1-`$4D`, 161-195
  mappings, up to 12 poses in one animation). In every type the mapping word
  table is followed directly by the animation word table (that is how its
  length is known) and every script ends in `00 00`. Palette ids
  `$80:BB4E[n] + color` (colors 0-5; +6 burnt, +7 one more variant).
  The cartridge overlaps pieces and even the tiles of 16x16 pieces, so some
  animations use all 32 tiles: the converter edits those on the cartridge's
  own tiles (`bomber._stock_anim`) instead of cutting them again.
* Hack, characters 1-9 (`char<n>_sb6.png`): `bomber_map` / `bomber_anim`
  read one long per character (`0` = stock) for seat bombers whose type
  matches the seat's character; `bomber_loop` covers types `$10-$19`.
  Edited palettes are 16-color entries after Bomberman's in the `pal_lookup`
  table; a byte per stock id 1-`$50` (0 = stock) redirects the id, and
  `bomber_palcount` loads 16 colors for redirected ids. Tested in Mesen:
  characters 1, 2 and 5 with recolored art / changed palettes, 1 player.
* Hack (`tools/sb6/objsheets.py`, `features/bombers.py`): the sheet table
  is copied to `$F0` with new sheets from id 97 (`$C5:6B86`, `$C5:6B8C`;
  Louie copies first, then the bomber's), `$80:BB7A` is
  rewritten, and `bomber_map` (hook at `$C0:12A4`) gives seat bombers of
  character 0 a new mapping table in `$B3:8000+`.
* Hack, `assets/bombers/bomber_anims.txt` (optional): the same bombers get
  their own script table, also in `objmap` (`bomber_anim`, replaces
  `LDA $C0171F,X` at `$C0:120E`), with new mapping ids from `$F1` for poses
  the cartridge does not have. `bomber_loop` (`$C0:126A`) makes the first
  byte of a type `$10` terminator the offset to restart at (every stock
  type `$10` script ends in `00 00`; other types have junk there and keep
  restarting at 0).
* Bomber colors `$C4:37B0` (A = palette id of set 0, Y = object): copies
  **9** colors (`LDA #$09 / STA $AB` at `$C4:37C1`) of the entry
  `[dest16, count16, colors]` at `($81:8000 + 2*(id-1))` to CGRAM
  `$80 + slot*16`. Ids 1-4 = white, black, red, blue (`$81:80B2`, 22 bytes
  each). With `assets/bombers/bomber_sb6.png` + `BombermanPallete.png` the
  hack repoints ids 1-4 to 16-color entries in `bank81` and `bomber_palcount`
  loads 16 colors for them (mounts no longer write there, see below).
* Death `$C4:3690`: when the cell has a flame (`$1052` bit 2 and bits 0-1,
  not bit 7) the bomber is repainted with palette id `$C0:BB4E[char] + 6`
  (burnt colors, `JSR $37B0` at `$C4:36B7`), then animation `$15` for 60
  frames. The hack removes the repaint.
* Invincibility blink `$C4:2E90` (every 8 frames): `$C1:0059` fills colors
  0-7 of the bomber's palette with black (`LDA #$07` at `$C4:2EB7`, the
  hack makes it `$0F`), `$C4:2EC3` copies the palette back from the backup
  `$7E:2CEA + 32*n` (`$C1:0035`; saved by `$C1:0015`, A = 8 + slot).

## Mounts (Louies) and eggs

* Actors: a mount is actor rider + `$1CBF`; an egg on the map is a mount
  actor too (character 9, `$C4:500A`, X = cell; any free actor of
  `[$1CBF, 2*$1CBF)`). `$1D38` counts eggs + mounts; the cartridge lets an
  egg appear only while it is < 2. Per mount character (`$16C2+actor`, 0-9):
  `$80:C3ED` first animation, `$C3F7` object flags, `$C401` object type,
  `$C40B` palette id of set 0 (`$50`-`$56`, 8 colors each, the first one is
  the same dark outline `$1466` in all of them; egg = `$52`, the pink
  Louie), `$C415` word -> `[sheet, row]` per animation (sheets `$15-$22`;
  egg: sheet `$1A` row 2). The tiles only use pixels 0 and 8-15.
* Stage items: list per campaign stage at `$C4:E5C7` (`[item, count, count
  with two players]`, 0 ends a stage), spread by `$C5:404C`; `$C5:40DE` (A =
  item) hides one item in a random soft block. Ids:
  `$0C` power glove, `$11` boxing glove, `$15` egg. Test items:
  `TEST_ITEMS` in tools/sb6/features/louies.py.
* Egg item = `$15` in the item map `$145A+cell` (`$1152+cell` bit 7 = item
  on the cell, copied to `$1CCB` for the player's cell). Hidden in soft
  blocks (`$C5:40D1` places two); when the block burns `$C5:457D` calls
  `$C4:500A` and removes the item if it fails. Pickup `$C4:2DD1` ->
  `$C4:50A6` (egg actor removed) -> task `$C4:5148`: `JSL $C01DEB` with
  A = 5 (random 0-5, inclusive) = Louie character, cry `$28 + n`,
  `$C4:4F25` creates the mount (A = character, X = rider). Not picked up
  while riding (`$C5:4111`).
* `$C4:4F25` first moves whatever sits in the rider's mount actor (an egg)
  to another free actor (`$C4:50DB`). A rider that is hit loses the mount
  (`$C4:51AB` -> `$C4:4FC3`: 48 frames, palette `$2E` when the cell burns).
  A mount is kept for the next stage (`$C4:2BF2`: `$1782+seat` bit 7).
* Colors, stock: `$C4:53EB` (A = palette id, X = actor, Y = object, four
  callers) copies 8 colors to entries 8-15 of OBJ slot `$16DA+actor` + 1
  (the rider's, or a player's for an egg) and gives the object that slot.
* Colors, hack (`asm/louies.asm`, `tools/sb6/features/louies.py`): the
  bombers use all 15 colors, so `$C4:53EB` now hands out halves of a Louie
  palette: an OBJ slot taken from the top (7 down to 3, marked with palette
  id `$FF` / set `$FF` in `$2B10`/`$2B18`) with entries 8-15 for one palette
  id (stock tiles) and entries 1-7 (+ the shared outline in 8) for another,
  drawn with copies of sheets `$15-$22` whose pixels 9-15 became 1-7 (sheet
  id + delta, chosen at `$C4:5458`). Actors with the same palette id share a
  half. An egg needs a half with `$52` (or a free one, or a second "spare"
  palette if a slot is free), otherwise it does not appear (`$C4:500C`; the
  count limit stays only in Battle). At `$C4:5148` a Louie whose colors are
  not loaded and finds no free half becomes one of the two Louies of the
  palette. Halves are released when their actor loses its object
  (`louie_tick`, once per frame from `e4_tick`), the slot when both are
  free; the burn palette `$2E` is ignored. Not handled yet: stages that
  need the top slots for something else (bosses, zone 5): whoever asks last
  gets no slot.

The full list with sizes is generated in `build/sb6.map`.

## Bomberman sprites (`tools/sb6/features/bomberman_sprites.py`)

* Archive table `$85:E22D + (n-1)*8`: VRAM word, size, src24, flags (`$85`
  raw OBJ for `$01-$22`, compressed from `$23`). Bomberman's art is raw
  archives `$01` (`$C7:4000`, `$2000`) and `$02` (`$C7:6000`, `$1800`); bomber
  pages hold (archive, half) per animation (`$1CCC/$1CEA`, upload `$C5:6B77`).
  Louies `$15-$22` (table `$C0:C415`). Frame pieces: count + 7 bytes
  (dx, dy, tile, attr; attr bit 0 = 16x16, `$40/$80` flips); sets `$C0:16CC`,
  animations `$C0:171D` (bomber object set `$10`).
* Bomber palettes: set 0 (`$81:8000`), id = `$C0:BB4E[char] + color`;
  Bomberman ids 1-7, `[dest $80, count 9, colors]`.
