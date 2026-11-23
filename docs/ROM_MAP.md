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
three tables and now belongs to the hack** (archives 1-2 BG3 glyphs, 3 boot
logo; palettes 1 title, 2 boot logo; arrangements 3 version, 4 1-4 PLAYER
GAME, 5 boot logo; 1-2 are unused copies of 3). Sets 1 and 2 are also
null. The archive set table ends at `$C0:1CAF` (13 sets).

### Finding who loads a graphics item (checked when freeing SB5 data)

* Archives are one array of 8-byte entries, `$E3:BE60-$E3:C82F` (314 entries); every set is a window
  of up to 255 ids into it (set 0 from `$BE60`, 8 `$BF80`, 6 `$C140`, 3 `$C158`, 4 `$C608`), so one
  entry has several names (set 3 `$46` = set 0 `$A5` = set 6 `$49` = set 8 `$81`). The stock OBJ sheet
  table `$85:E22D` (291 entries, read only by `$C5:6B8C`) is another copy of the same entries (the
  first 106 identical). Script ops: `27 n`, `28 n` (`$C0:18F6`, OBJ), `29 n vram16` (`$C0:17F3`);
  native `JSL $C0:180F` / `$C0:18F6` with `LDA #n` (set 3: `$47` at `$C0:329D`; `$49`-`$4F` in
  `$C5:0555-$C5:3C1D`).
* Palette word tables (bank `$81`) exist for sets 0, 3, 4, 6, 8 and 12-15 (`$C0:0379` holds 16
  words: 12 `$C6A8`, 13 `$D55E`, 14 `$E4D8`, 15 `$F8A4`); windows overlap like the archives (set 6 id
  `$3E` = set 3 id `$10`). Loads: `2A n`, native `JSL $C0:01AC` / `$C0:01C8`, and object palettes
  through the slot allocator `$C0:0295` with ids from object data (the title's `$3B`/`$3C` come that
  way: no `2A` names them), which is why unreferenced-looking palettes are hard to prove unused.
* Arrangements name their set in the op: `FF 8D/8E/8F/90 id set ...` (`$C1:74E5-$C1:7511`; drawer
  entries `$C0:0000` / `$0009` / `$0012` / `$001B`, set in `$0340`), `FF 49 ... set base` (numbers:
  ids base + digit). Native callers pass set 4 ids `$15`, `$1B`+, `$D4`, `$DC-$E3`, `$E7-$EA`+ and
  set 6 digit ids `$0B`+.
* Raw byte searches give many false hits (`2A 2B` appears 40 times, mostly in data): decode the script
  around a hit (`tools/scriptdis.py`; valid ops are `00-$A9`, `FE`, `FF`) and find its `26 n`.
  `tools/mesen/loads.lua` logs every load (kind, set, id, mode) and CPU reads of given ROM ranges.

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
  skipped (`tools/sb6/features/boot_logo.py`, `title.py`). The Hudson logo's
  tiles (set 3 archive `$46`, `$D5:9993`) and arrangement (set 4 `$D3`,
  `$E2:CAF3`) are freed (docs/FREE_SPACE.md); its palette `$2B` stays.
* Mode `$A9` is SB5's story intro (frames ~526-5900 of a base-ROM boot, then
  the title with its intro), only reached from the boot script. Its graphics
  (set 3 archives 3-6, `$57-$5F`; palettes 4-7, `$32-$3A`; sets 13/14 fade
  palettes; set 4 arrangement 1, set 6 `$EB-$EF`) are also loaded by the
  scripts at `$C6:6Cxx-$C6:6Fxx` and `$C6:EAxx-$C6:EFxx` (another scene,
  probably the ending), so they are kept.
* Script pointer of the running script: `[$0A]` (fetch at `$C2:0397`).

## Title screen

* Mode 1. Cartridge: BG1 logo (map `$3000`), BG2 scene (map `$3800`), BG3
  text (map `$4000`, chr `$5000`, CGRAM 0-3 = palette 8 of set 3), BG1/BG2
  chr at `$0000`, OBJ `$6000` (all maps 64x32: screen configuration 0 of
  `$80:8015`, 8 bytes per configuration = OBSEL, `$210B`, `$210C`,
  `$2107-$210A`; set by `$C0:076F`, shadows `$0368+`, only `$2109` is
  rewritten every NMI). On the title only OBJ tiles `$00-$17` (the menu
  cursor) and VRAM `$4000-$47FF`, `$5800-$5BFF` (BG3) are used.
* Hack, animated title (`tools/sb6/features/title_anim.py`,
  `asm/title_anim.asm`; the Unity title's pan, drops, logo and alternate
  poses): while its state is on, the NMI sets BG1 = map `$4800` 32x64 + chr
  `$6000` (tiles `$18-$1FF`: blank, logo, two areas for the falling waves),
  BG2 = map `$3800` 32x64 + chr `$0000` (tiles 0-`$37F`: BG1's old map is
  tile space), writes both V scrolls (-1 at rest: screen line 1 = map line
  0) and `$212C` (BG3 hidden until the logo lands), and runs one job per
  frame (rows of DMA, <= 2560 bytes; the NMI then ends at scanline <= 257).
  The logo's 6 frames are 2 BG palettes (6-7) rewritten every 5 frames
  straight into CGRAM (the shadow `$7E2910` keeps frame 1). It turns itself
  off, restoring `$2107/$2108/$210B`, on the first blanked frame of another
  mode. Script ops `FF 1A F8` start (finished scene when the intro was
  already seen since the last boot logo / stage), `F9` / `FA` put the task
  to sleep until the tiles are loaded / the logo has landed (see "Script
  tasks" below), `FB` starts the intro's sound stream (pan + character
  drops, `asm/title_music.asm` `pre_start`) when the intro is going to play.
  Start or A (raw pad words `$19`/`$1B`; the actions in `$2C+` are not
  decoded during the intro) skips to the finished scene. Checked in Mesen:
  VRAM after the intro equal to the build's simulation, skip, the OPTIONS
  submenu and QR, Normal Game to stage 1, attract demo and back.
* Title flow in mode 2: task 5 runs the handlers (forced blank from the end
  of the boot logo's fade), fade-in over 16 frames, then the task at
  `$C7:1847` (`06 04`, `42 02 00` music, cursor Y, `24 D3 1A C7` PUSH START
  loop) - the hack makes it wait for the intro first. SB5's Options was mode
  `$0B` (gone, below), the Normal menu 3, the attract demos `$0D`/`$74`; the mode byte changes
  when the fade-out starts.
* Bomber palette ids: the cartridge's set 0 ends at `$59`; the SB6
  palettes are ids `$5A`+ (`OWN_ID`, `pal_lookup` / picker `upload`), room
  for 166 palettes. Characters with their own key colors
  (`char<n>_pallete.png` column 0 differs from Bomberman's) get their own
  15-color layout; characters with the same picture share it (and its
  palette entries) when their colors fit together.
* Title menu cursor: one 16x16 sprite, the first in OAM (shadow
  `$08BF` X, `$08C0` Y, `$08C1` tile, `$08C2` attributes `$20`), OBJ
  palette 0 (CGRAM 128-143), tile 0 at rest; after an accepted option it
  hops: tiles `02 04 02 06` and Y +1/-5, a 25-frame loop that goes on until
  the menu changes. SB6
  (`cursor` in `asm/title_anim.asm`, tables from `cursor_tables` in
  `features/title.py`, art `assets/title/Cursor.png`) sends the fan game's
  pose (4 tiles, 63 poses = 7 faces x 9 heads) to whichever of the frames
  0/2/4/6 the shadow asks for (VRAM `$6000 + $20*tile`, lower row `+$100`)
  and its 15 colors to CGRAM 129-143, from the NMI while the title idles;
  during the confirmation it writes the Y of the moment A/Start was pressed
  to the shadow and to OAM (no hop). Looks around after 180 frames without
  input; pads read from `$19-$1C` (pad 2 = `$FFFF` when unplugged).
  The game loads its own cursor tiles through its VRAM queue (`$C0:0580`,
  8 x 32 bytes per NMI) and its colors through the CGRAM copy `$7E:2910`
  (sent whole when dirty): SB6 writes its colors into that copy too and
  re-sends its pose the frame the sprite appears (Y < `$E0`). A confirmed
  face goes back to rest when the menu `$1036` changes (Normal Game ->
  players). The mode-2 wait script creates the cursor (`24 D3 1A C7`)
  before the music upload (which holds the main loop ~0.5 s), waiting six
  frames (`FF 1A FC`) so the game's tile queue and the upload do not share
  an NMI.
* Script tasks: a script runs to its end inside one frame unless it sleeps
  with `FD 0E n 00 00` (n frames; see the title menu below) (`05/06/07/08 n` set / clear / toggle / test flag n of
  `$7E:2900`). The interpreter loop is `$C2:0222`; after every op the next
  op's address is saved in `$0C87/$0CAF/$0CD7 + task`; `00` returns from a
  `24` call and, at depth -1 (`$0CFF + task`), ends the task. The task
  runner `$C0:22F0` keeps its stack pointer in `$75` and calls each task at
  its resume address `$0BBF/$0BE7/$0C0F + task` (`$0B97 + task` = frames to
  skip first). So a native op that must wait rewinds the saved script
  pointer to itself, sets the resume address to `$C2:0211` (reloads that
  pointer and continues), sets S = `$75` - 3 and `RTL`s to the runner
  (`title_op` `.again`). Looping inside the script instead holds the whole
  main loop (nothing else runs, e.g. the stream feeder).
* Mode table `$C6:0000`: mode n -> `$C6:0000 + 3*(n-1)` = record of 3-byte
  pointers (handler list, task scripts, label tables, `00` end; mode 2 =
  `$C7:177A`: handlers `$C7:1786`, task `$C7:183E`, labels `$C7:1AA4`). Mode 7
  (Password) was `$C7:08BD`, mode `$0B` (Options) `$C7:00DE`.
* Script op `FD 0E n 00 00` puts the task to sleep n frames (SB5's wait loop
  `$C7:1B0B`, `$103A` frames, `FD 0E 01` at `$C7:1B36`): a script may wait
  this way; an accepted title item waits 64 frames there (`$C7:1AEA`) with
  the cursor hopping, then reaches the menu checks at `$C7:18A3`.
* Title menu (task `$C7:1872`, every frame): `$1036` menu (0 NORMAL / BATTLE
  / OPTIONS, 1 players, 2 unused in the title), `$1032` item, `$1037` last
  item (set per menu at `$C7:19D3`). A/Start: `$C7:189C` SFX 4 + `$C7:1AEA`,
  then menu 0 item 0 -> players menu (`$C7:18A3`), `$C7:18D5` menu 0 item 2
  -> mode `$0B`, `$C7:18ED`.. the other menus (menu 0 item 1 -> Battle, mode
  4 at `$C7:1941`), `$C7:19A2` B (menus 1/2 -> back block `$C7:19B4`),
  `$C7:19F7`/`$C7:1A47` down/up. Attract demo: native task `$C5:6ECA`,
  30 x 64 frames without a new action/direction (`$C5:6F2C`/`$6F3B`), then
  `$C5:6EF3` picks a demo mode from `$C5:6F1C`.
* Hack, OPTIONS submenu (`tools/sb6/features/options.py`): `$C7:18D5` calls
  `s_confirm` (menu 0 item 2: menu 3 = DISCORD, set 5 arrangement 6; menu 3:
  menu 4 + QR code = set 5 arrangement 7, 20x20 BG3 tiles of 2x2 modules
  over the title, BG3 window shadow `$0307` off while it is up, any new
  button closes it), `$C7:19AD` calls `s_back` (menu 2 as before, menu 3
  -> main menu with the cursor on OPTIONS). `$C5:6ECA`'s input test reports
  input while mode 2 shows menu 3/4 (no attract demo during a QR scan).
  SB5's Options / Sound Test / Password screens are freed; mode table
  entries 7 and `$0B` point at mode 2's record.
* Intro path (mode `$A9`) setup script `$C6:FC93`; title without intro (mode
  2) handler list `$C7:1783` (2 = `$C7:17D1` load, 4 = `$C7:17DE` OBJ
  archives, 6 = `$C7:17E3` draw).
* Menu cursor Y is `$1034`: set to `$A0` when the title appears
  (`5B A0 60 34 10` at `$C6:FE6F` intro path, `$C7:184C` mode 2) and
  recomputed as item * 16 + `$A0` on each move (`$C7:1ABF`). The hack moves
  all three up with the text.
* SB5's title arrangements set 4 #2 (scene), #3 (logo) and #6 (© line) are
  no longer drawn and are freed (`title.free_old`, docs/FREE_SPACE.md); #4, #5
  and #7 stay.
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
* Group 3 in detail: `$80:8765 + 2*id` = `[set, command]`; the task at
  `$C0:0FEC` takes the set's first upload block and sends it with port-1
  command `$31` (`$C0:106C`, at most `$40` bytes per main-loop pass, skipped
  on lag frames), then sends the command as an SFX (`$03C3`, `$C0:1135`).
  Every set targets ARAM `$5900` (the voice buffer, up to `$70F1`). Id 1 =
  player death (set `$48`, `$7CE` bytes, SFX `$4F`; callers `$C4:3674`
  Battle, `$C4:3684` Normal): ~32 frames of transfer before the sound, the
  "late" death sound (the hack points set `$48` at its R list and frees the
  original list `$D9:E464-$D9:EC39`; no other request, group-4 entry or music
  id names set `$48`). Ids 2 (`$C4:2FA3`), 3 (`$C4:33F6`, Battle), 4
  (`$C5:08C8`); 5-13 = SFX `$26-$2E`, 14-17 = SFX `$68`.
* SFX command c (port 0, `$C0:0E7F`) = entry c - `$21` of Hudson's pointer
  table `$4410` (priority `$4550 + entry`). Group 2 id `$33` = enemy death
  (`$C5:3BD6`, SFX `$57`), id `$0C` explosion (`$2C`), id 6 bomb drop
  (`$26`). Commands `$5D-$66` are referenced by no table (entries `$3D-$45`
  all point at one sequence). SB5's stage SFX use channel masks 1/2/4 only.
* Stage music: script ops `42 id 00` with ids 6-`$0E` (worlds), `$0F`,
  `$14`, `$15` (songs 5-14, 19, 20).
* Hack, in-game SFX (`tools/sb6/features/game_sfx.py`, `asm/game_sfx.asm`):
  SFX `$5E` cornered (recording), `$5F` enemy death and `$60` player death
  (Super Bomberman 1's samples and notes: its sound commands `$16` / `$1F`
  via `$C4:8522`, voice 0, ADSR `$DF/$94`; death = 8 key-ons alternating
  pitch `$09C4` / `$05DC`, enemy = one at `$04B0`). Group 3 id 1 is answered
  by `gs_sound` (the death sound now starts with animation `$16`), animation
  `$21` of a seat bomber by `gs_anim`. The object code never talks to the
  SPC: `gs_anim`/`gs_enemy` leave the command in `$018C` and `gs_tick`
  (main loop) sends it; waiting for the SPC inside the setter delayed the
  frame and characters 1/4 lost the tile DMA of animation `$21`. Enemy hit: `$C3:4D41` (the enemy object becomes type 0 with
  its death "puff", animation from `$C3:B930`) calls `gs_enemy`; SB5's own
  enemy sound, group 2 id `$33` (`$C5:3BD6`), comes ~70 frames later with
  the score and is now silent. Set `$48`
  now uploads R (used to restore it after another group-3 voice). Hudson
  note n (12 * octave + note) with tuning `04 0C 00 CE` plays at
  ~1011 * 2^((n-24)/12).
* Script music load `$C0:1171` uploads its song unconditionally.
* Title flow: `0401` (sets), `$C0:1171` song 1, `0002` = play title music.
  SB5's Options (gone): `0204` → `1001` → `0401` → song 1 → `0002`. The song 1 load is
  script `FF A0 02` (op `$A0` = `$C0:1171`, music id 2 = set `$28` + song 1;
  table `$80:8655` + 3 * id: [set, song, ?]) at `$C7:17B8` (title, also after
  Options) and `$C6:FCFF` (intro path); the hack turns both into `45 01`
  (skip) and frees the song (`title_music.free_old`), so the title comes up
  ~88 frames sooner.
* Normal Game menu (mode 3, file lists and the picker): `1001` then `041C`
  (sets) and no music in SB5; the stage then sends `1001`, `0004`. Hack:
  `041C` in mode 3 arms the save menu music (`$010D`), which the main-loop
  hook starts once the set is in (stream track 2, 12 kHz; the next non-SFX
  request releases it). Tracks are segment runs (`segs` in
  `asm/title_music.asm`), so the save music fills the tails of `$EB` / `$FC`
  and banks `$FD-$FF`.
* All APU port accesses are in `$C0:0DC0-$C0:1130`.

* Menu SFX (group 2): `1` cursor move, `4` accept, `3` back. SB5 plays
  them on voice 0, sample `$20` (DIR `$FD`), ADSR `$FF/$E0`, a tick every
  ~16 ms (seen with `tools/mesen/sfx_capture.lua` / `tools/capture_sfx.py`,
  research tools the build no longer uses). Mesen's `spc.cycle` counts at
  **2.048 MHz**. The hack replaces the three with recordings (below).
* Uploads: `$C0:0F13` handshake (port 1 = `$10`, waits `$AA`/`$BB`, kick
  `$4B` = `$CC`), `$C0:0F62` sends the list at `[$48]` = blocks `[length,
  ARAM address, data]` until a zero length (`$03D1` = 1: one raw block of
  `$4C` bytes to `$03CF`), `$C0:0F35` ends the session (jump address = the
  two bytes after the list; Hudson's loader ignores it). All end in `RTS`.
  Sets: `$85:F69B + 3*set` -> list. Songs: `$DA:C2E0 + 2*song` -> record in
  bank `$DA` = [list pointer, first sample address, sample ids, `$FF`];
  samples `$DA:D042 + 3*id` (sizes `$DA:D1BF + 2*id`) are sent one after
  the other. Music id n = set `$26 + n` (its sequence, at `$3000`) + song
  n - 1.

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
* ARAM while the title is up (SB5): sets `$3000-$5924`, title song 1 at
  `$7000-$CFDF` (the hack no longer uploads song 1; the stream owns ARAM).
* ARAM map from the upload lists: song sequences `$3000-$4240` (sets
  `$27-$3F`); SFX tables and sequences `$4400-$554C` (common set 1: header
  `$4400` = pointers to the SFX pointer table `$4410`, the instruments
  `$44D0` (4 bytes: sample, ADSR1, ADSR2, gain; 0-1 common, 4-27 world
  sets from `$44E0`) and the priorities `$4550`; world sets 2-14 continue
  those tables); voice sets `$5600-$575E`; SFX samples `$5800-$5847`
  (common), `$5900+` / `$6580-$7FB1` (world); song samples from `$5900`,
  `$7000`, `$8000` or `$9000` up to `$E0F4` at most; directory `$FD00 +
  4*n` and tuning `$FE00 + 4*n` (songs use entries 0-`$14`, sets
  `$20-$38`). Echo buffer = `$FD00 - $800 * EDL`; EDL comes from the song
  header (op `07 00 volL volR EDL feedback FIR flags`; `07 nn` = defaults,
  EDL 1; boot jingle 11, most songs 3-4).
* Song header (first word list at `$3000`, then ops at driver `$1398`):
  `00` end, `01 mask + pointers` tracks, `02 n`, `03 n + 4n` instruments,
  `04 n + 4n`, `05/06/09 n + 2n`, `07` echo, `08 n`.
* SFX engine (driver `$28B2`, 4 channels, state at `$0679-$06EC`): an SFX =
  [channel mask, track pointer per set bit]. Track bytes below `$D0` are
  notes (high nibble 1-12 = note, 0 = rest; with default length 0 the next
  byte is the length in ticks, else length = default * (low nibble + 1));
  `D0` end, `D1 n` default length, `D2 n` octave, `D3`/`D4` octave up /
  down, `D5` tie, `D6 n` volume (max `$4F`), `D7 n` volume add, `D8 n` pan
  (0-`$1F`), `D9 n` pan add, `DA n` detune, `DB n` detune add, `DC n`
  pitch slide, `DD n` instrument, `DE n` transpose, `E0 n` ... `E1` loop,
  `E2 n` transpose add, `E3`/`E4` echo on / off, `E5 a16` jump, `E8 lo hi
  len` raw pitch (needs a note played before on that channel), `E9 n len`
  raw pitch add. Pitch of a note = table(note + 12 * octave + tuning byte
  2 + transpose) scaled by tuning bytes 0-1, + detune.
* Hack, SB6 menu SFX (`tools/sb6/features/title_music.py`): the three
  recordings are BRR samples at ARAM `$B900-$DCFF` (directory / tuning
  entries `$39-$3B`, instruments 28-30 at `$4540`); SFX 1/3/4 become
  `01 ptr, D1 00, DD inst, D2 octave, D8 0F, D6 4F, note, ticks, D0`
  written over SB5's sequences. Notes (octave 2 note 7, octave 2 note 4,
  octave 1 note 12) give pitches `$05E9`, `$04FA`, `$03F3` (read from
  voice 0 in Mesen), and each recording is resampled to its pitch. Only
  songs that leave the area alone keep them (3 Normal menu, 18 Battle
  menu, 26, 10, 16, 20, 28, 29, 31, 32: samples end below `$B900` and EDL
  <= 4); loading any other song puts SB5's sequences back, so stages still
  beep - except song 0 (the boot jingle): its voice sample sits at
  `$3400-$94C8`, over the SFX tables, so nothing is written there (doing
  it cut "By Hudson" short; set 1 is loaded afterwards anyway). Not covered: a song that changes EDL in a track, the group-3 data
  stream.

## Hooks installed by the hack

| Address | Original | Purpose |
|---|---|---|
| `$C0:0CED` | `85 9F EB C9 10` | title music stream (`asm/title_music.asm`) |
| `$C0:0B2C` | `AD BF 03 D0 04` | stream feeder, once per main-loop pass |
| `$C0:0E58` | `20 62 0F 20 35 0F` | set upload: SB6 menu SFX definitions again (`set_hook`) |
| `$C0:0F0A` | `20 35 0F 9C D1 03` | song upload: SB6 menu SFX samples + definitions, or SB5's back (`song_hook`) |
| `$C0:11EC` | `99 9F 07 A9 00` | animation setter: cornered `$21` of a seat bomber plays SFX `$5E` (`gs_anim`, `asm/game_sfx.asm`) |
| `$C3:4D41` | `BD C2 16 8D 51 1D` | enemy hit: SB1's enemy death SFX `$5F` (`gs_enemy`) |
| `$85:F69B + 3*$48` | set `$48` pointer | group-3 set of SB5's death voice -> upload list of R (in-game SFX) |
| title scripts | see `tools/sb6/features/title.py` | SB6 title graphics |
| `$C7:1847` | `06 04 42 02 00 5B A0 60 34 10` | title: music and PUSH START wait for the intro |
| `$C7:18D5`, `$C7:19AD` | OPTIONS -> mode `$0B`; B test of menu 2 | OPTIONS submenu / DISCORD QR (`tools/sb6/features/options.py`) |
| `$C5:6ECA` | `20 2C 6F` | attract demo timer: no demo while the OPTIONS submenu / QR is up |
| `$C6:0012`, `$C6:001E` | modes 7 / `$0B` | mode table: the freed Password / Options screens lead to the title's record |
| co-op | see `tools/sb6/features/coop.py` | 3/4-player Normal Game (below) |
| `$C7:10E2`, `$C7:0E27` | `24 4C 12 C7` | file confirm -> character selection (`asm/picker.asm`, below) |
| `$C2:069B` | `7C 46 C1` | script op `FF 1A nn`: nn >= `$F0` runs `pick_op` |
| `$C0:F421` | `22 E0 04 C0` | NMI: the SB6 picker's VRAM loads, portrait swaps and poses (`pick_nmi`), which first calls `title_nmi` |
| `$C5:0058` | `A9 01 8D 1D 1D` | pause entry: also opens the SB6 pause menu in the Normal Game (`pm_open`, `asm/pause.asm`) |
| `$C5:009E` | `20 B7 00 F0` | each paused frame: the pause menu (`pm_tick`) instead of SB5's Start test (Battle keeps it) |
| `$C0:01FA` | `A9 81 85 AA C2 30` | palette lookup: ids `$80+` of set 0 = bomber palettes (`pal_lookup`, `asm/bombers.asm`) |
| `$C7:1481` | zone setup script (19 bytes) | calls a copy that runs `FF 1A F5` first (`wmap_op`: map animation, `$0314`, `$0321`, map music driver) |
| `$C7:14A9`, `$C7:14B9` | zone 1 map script | ZONE1 world map = SB1's (`tools/sb6/features/world_map.py`, below) |
| `$C7:14D2`, `$C7:14EB` | zone 2 map script | ZONE2 world map = SB2's |
| `$C0:1C98`, `$C0:037B`, `$C0:8003` | set 1 (null) | world map archive / palette / arrangement tables |

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
  a script that fades, saves `$1032-$104F` and `$1D20-$1D3F`, calls the
  picker script for its screen and restores; confirmed choices go to
  `$16C2+seat` / `$16DA+seat` and are applied again after the player reset
  (`$C4:28B4`, co-op `c4_tail`) and at the stage spawn (`$C2:1697`, not in
  boss stages). B reloads the menu graphics, drops the call and jumps to
  the file list.
* SB6 screen (the SB6 fan game's SkinSelect): SB5's setup runs with only BG2
  shown (`$030F` = 2, about 70 frames); when task 9 reaches `$C6:8E68` its
  saved pointer is set to `pk_loop` (`FF 1A F4`, sleeps every frame), so
  SB5's loop and objects never run (their OAM is overwritten every frame
  by `pick_tick`). The NMI then loads, one group per frame: BG1 rows 5-24
  (map `$3000`, cols 2-29), portrait tiles at `$1600` (BG tile `$160`+, the
  menu's archive `$93` tail, reloaded by `menu_gfx`), glyph and player
  cursor tiles at OBJ `$6000` (tiles 0-11, 16+); the static colors go to BG
  palettes 3, 4, 7 and OBJ palette 4. Afterwards `$030F` = `$13`. When all
  seats confirm, the outputs `$625F/$6264` are written, the victory plays
  72 frames, then the picker fades out itself (brightness in the INIDISP
  shadow `$0300`, then `$80`) and the task goes on at `$C6:8EC4` (no fade
  there: `00` back to the file script, which loads the next screen's
  graphics with the screen on, and SB5's picker objects are drawn again
  once `pick_tick` lets go); B on the first seat sets `$1040` = `$FF` and
  does the same. The close op hides all 128 OAM entries (the builder only
  hides its own), and after B the file list is faded in by `pick_tick`
  once the VRAM queue is empty (the file list script does not fade in).
* Grid: one cell per character with a column in
  `CharacterSelectPortrait.png` (7, chars 0-6; chars 7-9 are left out), 5
  per row. Resting portraits use the default color (BG palettes 3/4/7,
  shared); the cell under the cursor is swapped by the NMI to its cursor
  face (16 tiles + 16 map words per cell) in BG palettes 5/6, whose 30
  colors are chosen per character and color (`pk_hcol`). Cursor: OBJ
  palette 4, entry 2 = the skin's tint (`pk_tint`), corners breathing
  0/1/2/1 every 30 frames, "L / R" above, digit + "P" below.
* Player row: per seat a cursor (Unity P1-P4 Cursor, 3 brightness steps
  pending / choosing / confirmed) and the character as up to 8 16x16
  sprites from the second OBJ table (tiles `$40*seat + $20*half`, VRAM
  `$7000 + $400*seat + $200*half`, double buffered; one pose per NMI, none
  when a portrait was swapped), OBJ palette = seat (`chpal + color`, the
  choosing seat's colors halved toward the background). Walk down (anim 2)
  loops while choosing; the victory (anim 20) plays once and holds its last
  pose. Timing in video frames (NMI count `$7F:FC76`, the picker's logic
  runs at 30 Hz): the step `$C0:1254` takes 1 off the timer per call and a
  walking bomber is stepped twice a frame (1-1: 4 frames per walk pose,
  8 when pushing a wall), so walk = script frames / 2, victory = script
  frames (`ROW_DIV`). Pose records: `[n, n x (dx, dy), top tiles, bottom tiles]`.
* Sounds: move 1, accept 4, back / taken 3, color change `$1E` (Unity
  `Sounds/Skin/change.wav`, stream driver slot 4, ARAM directory `$3E`).
  Tested in Mesen: 1, 2 and 4 players, B undoing the previous player, B to
  the file list and back in, wraps, same character with another color,
  stage receiving the choices. Not tested: Continue (needs a save), real
  hardware.
* Menu background (checkerboard + heads): palette 0 of set 3 id 14
  (`$81:9796`, Normal menu, orange) or id 70 (`$81:A9F6`, Battle's picker,
  green checker, grey heads, entry 6 = the grid's red X); the checker
  scrolls by swapping entries 3-4 from cycle tables at `$81:E216` (orange,
  18 records `[3, 2, c, c]`) and `$81:E2A6` (green). The Normal picker
  showed Battle's green until the menu's cycle wrote orange again. Hack
  (`tools/sb6/features/menu_bg.py`): blue copies of both, returned by
  `pal_lookup` for id 14 in mode 3 and id 70 while `$7F:FF00` = 1; the
  orange cycle table is recolored in place.
* Palette lookup `$C0:01DE` (A = id, set `$0AE7`): `[$A8]` = `$81:` word of
  the set's table (`$C0:0379 + 2*set`) at `2*(id-1)`; every loader goes
  through it (`$C0:01AC`, `$C0:01C8`, the slot allocator `$C0:0295`, which
  takes 16 colors when the palette's count says so). Hack: with
  `BombermanPallete.png`, ids `$80 + n` of set 0 are the picture's columns
  (n = 0 is column 1; table and data in `$E4`, the hook also sets the bank
  in `$AA`); ids 1-6 are replaced in place by columns 1-6, so Battle and
  the co-op defaults keep working. A Bomberman chosen in the picker uses
  `$16DA` = `$80 + color`.
* Grid figures of SB5's picker: BG1 (map `$3000`), 2x3 tiles mirrored
  (`2C91 6C91 / 2CA1 6CA1 / 2CA0 6CA0` for the first cell at tiles 5-6 x
  16-18; empty tile `$211C`), 8 colors each (replaced by the SB6 screen).
* CGRAM upload vs the VRAM queue: `$0351` = 1 makes the NMI (`$C0:0244`) DMA
  512 bytes of CGRAM from `$7E2910` and spend `$02C0` of the frame's DMA
  budget `$0365`; the VRAM queue (`$C0:04E0`, entries at `$7E:8000`, read
  `$0355` / write `$0357`) then stops early and splits the portrait's
  two-pass transfers (`$2115` = 00 then 80): the top box shows garbage that
  looks like a blinking cursor. The picker only sets `$0351` when
  `$0355` = `$0357` (`palflush`, flag `$7F:FF69`).

## World map (Normal Game, mode 3)

* Script `$C7:1440` in task 9 (idle loop around `$C7:13AC`; `$0CB8`/`$0CE0`
  = task 9's script pointer high byte / bank). Every zone: set 3, archive
  `$0E` (lava tiles, VRAM `$0000`) + arrangement `$0E` of set 4 on BG2, BG3
  archives `$4C`, `$4D`, `$0D`, palette `$0F` (CGRAM 0-15: lava palette 0,
  whose entries 1-11 are also the BG3 text colors), then `5D 36 10` /
  `FF A6 00 06` jump on the zone `$1036` (word table `$C7:149B`, entries
  0-6). Zone 1 (`$C7:14A9`): archive `$0F` (island, VRAM `$1000`), palette
  `$10` (CGRAM 16-95), arrangement `$0F` on BG1, `FD 0E 01 00 00`,
  `2C 02 01` / `2C 03 01` (lava palette cycles: set `$0D` palettes `$06-$14`
  -> CGRAM `$11-$15`, `$15-$23` -> `$16-$1A`, every ~4 frames),
  `2C 09 01` (stage marker blink, palettes `$4C-$4F` -> OBJ CGRAM `$92-$95`),
  `FF 8D 48 04 03 00 00` (ZONE text, BG3). Map music: request group 0 id 4,
  after `1001`.
* Screen: mode 1, BG1 map `$3000`, BG2 map `$3800` (64x32, 8x8 tiles, chr
  `$0000`), BG3 map `$4000` chr `$5000` (ZONE n - m, the "R" arrow), V scroll
  0 (screen line y = map line y + 1). Stage markers and the zone badge are
  OBJ. CGADSUB shadow `$0314` = `$C2` (BG2 subtract-half with COLDATA
  `$0315-$0317` = 10/10/10: the dark lava); the PPU shadows `$0300+` are
  copied by the NMI at `$C0:F6xx` with D = `$0300`.
* `$1036` = zone - 1 here. L / R re-run the script from `$C7:1481` (lava,
  BG3, then the zone jump) while the screen is dark; no music request is
  sent on a zone change. SB5 reloads per zone only tiles 0-`$40` (lava,
  archive `$0E`) and from `$100` (the island archive); tiles `$41-$FF`
  (archive `$0C` and others) and `$200+` are loaded once per map. The lava
  arrangement (`FF 8D 0E 04 02`) is drawn relative to BG2's V scroll
  `$0321`: it must be 0 first. The stages do not reload tiles 0-`$40` and
  their BG3 map is mostly tile 0: it must stay blank.
* Hack: `$C7:1481` calls a copy of the setup that first runs `FF 1A F5`
  (`wmap_op`, `asm/world_map.asm`): per zone the animation, `$0314` (0 on
  ZONE1/ZONE2), `$0321` = 0 and the music driver (`map_music`). Zones 1 and
  2 call a script that loads set 1 (archives = raw tiles at `$100-$1FF`
  then 1-`$40`, palette n = BG palettes 1-5 / 1-7, arrangements: ZONE1 1 sea
  on BG2 / 2 island on BG1, ZONE2 3 stars on BG2 (32x32) / 4 ships on BG1);
  their lava cycles are skipped. SB5's own ZONE1/ZONE2 data (set 3 archives
  `$0F`/`$10`, palettes `$10`/`$11`, set 4 arrangements `$0F`/`$10`) is
  filled with `$FF` and free (docs/FREE_SPACE.md); the copies in sets 0 / 6
  are table entries only, no script loads them. ZONE1's sea is one 16x16 tile (`$101-$104`)
  whose 7 frames `asm/world_map.asm` DMAs every 12 frames; ZONE2's stars
  scroll up 1 line every 2 frames (`$0321`) and the ship lights write 8 CGRAM
  entries per frame (64-frame cycle). Both from `pick_nmi` while mode 3 and
  task 9 is in `$C7:1300-$C7:17FF`.
* Stage markers: `$C2:1070` = 3-byte pointers per zone (0-5) to entries
  `x y stage n` ending with `00 00 00 00` (zone 1 `$C2:1082`). Script op
  `$18` (`$C2:0EBD`, zone) creates object `$48` per entry (8x8 flag at
  x, y - 9; OBJ palette 6 = `$4DB2`, 7 = cleared, 5 otherwise); op `$19`
  (`$C2:0F76`, zone x y) returns the stage whose box `[x-8, x+12)` x
  `[y-8, y+12)` holds the cursor (`$103A`, `$103C`) and draws the label
  "- n" (`$C5:0DA7`: set 4 arrangement `$1B + n - 1`); op `$1A`
  (`$C2:100B`) puts the cursor on a stage (`$7E:4DBA`/`$4DBC`). The map
  script (`$C7:128B`) plays the marker under the cursor on START when it is
  the zone's first stage (`$1046`), `$4DB2`, or cleared (op `08`: bit
  stage + 3 of `$7E:2900`); the cursor moves freely.
* Hack (`features/world1.py` `markers`): zone 1 = 7 markers 1-1..1-7
  (`$0D $11 $18 $10 $17 $67 $68`, n = 1-7) where
  `assets/world_map/zone1_stages.png` has its digits; ZONE2 loses `$68`/`$69`
  and ZONE3 `$6B` (World 1's stages now).
* SB1's map (for reference): BG1 map `$5000` (island, clouds; 16x16 tiles),
  BG2 map `$5400` (tile `$200` everywhere, palette 1), V scroll -1, the
  center tower is OBJ (tiles `$180-$1C2`, palette 4); only the sea tile
  changes (VRAM `$2000-$211F`), the clouds do not move. Shown ~250 frames,
  then the stage.


## Pause (stages)

* SB5's pause is the native task `$C5:0000` (registered with the stage
  tasks by `$C5:3A30`; not in stages with `$1D1A` = 8, e.g. 1-6): from its
  loop `$C5:003B` it waits for Start (`JSR $00B7`: OR of `$36+s` of the
  seats whose object `$17FA+s` is not `$FF`, bit 0) while `$0AEE & $7F`,
  `$1D1C` = 0 and `$1D1E` bit 2 clear. Pause (`$C5:0058`): `$1D1D` = 1
  (the stage freezes), BG3 arrangement `$DF` (PAUSE!, rows 14-15) at
  `$1D28`/`$1D2A`, WORLD n - nn (rows 11-12, `$C5:00CD`, stages
  `$0D-$66`; digits `$1CB7` world, `$1CB9`/`$1CBA` stage, from
  `$80:8A8A` + 2 * `$102F` through `JSL $C04672`), sound group `$10` id 6 + group 2 id 5; then every frame
  `$C5:009E` tests Start -> `$C5:000C`: `$1D1D` = 0, `$C0:09CC` fills BG3
  rows 3-31 (queue fill entries), group `$10` id 7 + group 2 id 5. Task
  yield = `JSL $C02160` (the return address becomes the task's resume
  point); a plain `RTL` keeps the old one.
* Flags 5 / 6 of `$7E:2900` (`$C2:0372`): set by the title script (frame
  ~729, cleared when the Normal Game opens); either one forces a
  one-player session at `$C4:28B4` (co-op's `c4_tail`) and skips the stage
  tasks at `$C5:3A2D`. A save written while one was set brought it back
  with the save (`$C0:49C8`, the loader): every stage picked on the map
  after a game over or the pause's world map started with one player.
  `save_flags` (`asm/world1.asm`) clears them on load.
* Stage end: `$1D1E` bit 2 (op `0F n` = `$1031` n + bit 2). The end task
  (`$C5:3AA7`) then checks `$1D1E & $22` (deaths: lives, game over mode
  8), else `JSR $3D19` (clear flag of `$102F` only when `$1D1A` bit 6),
  `$1046` = `$102F`, `JSL $C048CC` (save), fade, mode `$1031`. Mode 3 with
  `$7E:631A` = 1 starts the Normal Game menu in state 4 (world map,
  `$C7:0B95`; also used by `$C6:E8F7` after a zone); the script clears it.
* PPU shadows (copied by the NMI at `$C0:F685` with D = `$0300`): `$0302`
  `$2105`, `$0306-$0312` `$2123-$212F`, `$0313` CGWSEL, `$0314` CGADSUB,
  `$0315-$0317` COLDATA r/g/b.
* BG3 in a stage: tiles `$5000` (2bpp, HUD `$00-$3F`, font `$80-$F8`;
  `$100-$1FF` = leftovers of other screens), map `$4000` 32x64; palettes
  0 (HUD: `$18C6` / `$35AD` / `$7FFF`) and 6 (`$00BF` / `$01FF` / `$033F`)
  are the same in every stage checked (1-1, 1-3, 1-4, 1-7).
* The VRAM queue can run past the VBlank (e.g. the unpause's fills): the
  NMI then turns the screen on before the hooks after `$C0:04E0` run, and
  their VRAM writes are lost; `asm/pause.asm` waits for `$0355` = `$0357`.
  VRAM reads (`$2139`/`$213A`, VMAIN `$80`): the first word after setting
  the address comes twice, so one dummy word read first.
* Hack (`tools/sb6/features/pause.py`, `asm/pause.asm`): in the Normal
  Game the pause shows the SB6 fan game's menu under PAUSE! (RESUME /
  RETURN TO WORLD MAP / RETURN TO TITLE, then RETURN TO ...? NO / YES) on
  BG3 rows 17-21 with an own 8x8 font in tiles `$100-$111` and a frame
  (BG3 palette 6, tiles `$112-$119`, rows 9-23 x columns 3-28; all saved
  and put back by the NMI); WORLD n - nn is redrawn every NMI as STAGE
  n-m (letters S/T/A/G/E of the stage font, tiles `$A6-$AA` / `$B6-$BA`,
  palette 1, SB5's digits `$82-$8C`; bosses `$67-$70` from World 1's
  numbers; the rows are built in `!lbuf` by the main loop and sent by
  DMA: building them in the NMI ran past the VBlank and lost the glyph
  upload, and the NMI part now quits when `$4212` bit 7 is clear). Darkened
  panel: inside color window 1 BG1/BG2/OBJ are masked from the main
  screen (`$0306` = `$0308` = `$22`, TMW `$13`) and drawn on the
  subscreen (TS `$13`), the main screen is BG3 over the backdrop (CGRAM
  color 0 made black by the NMI, put back after), and color math adds
  half the subscreen on the backdrop (`$0313` = `$12`, `$0314` = `$60`,
  fixed color 0): the scene at half brightness, every OBJ palette
  included (color math on OBJ only reaches palettes 4-7, which left
  1-4's tanks bright); the window's left/right per line come from
  HDMA channel 7 on `$2126`/`$2127` (`$0AEA` = `$80` while paused, kept
  by the NMI since SB5 reloads it from `$033E`); the stage's own windows,
  color math (1-4 uses `$0308` = `$20`, `$0313`/`$0314`) and HDMA channels
  are saved and put back on resume. Yes: `$1D1A` bit 6 off, `$631A` = 1 + mode 3
  or mode 2 (with `asm/title_anim.asm`'s intro-seen flag `$7F:FD03` = 1:
  the title comes back without its intro, as in SB6), `$1D1D` = 0,
  `$1D1E` bit 2. World map: lives, characters and
  colors are kept; about 5 s of black screen (the Normal menu's loading
  and the map driver upload, as after a zone); the save menu music is not
  started on that way in (`asm/title_music.asm` checks `$631A`).

## Stages: records, portals, clear (World 1)

* Mode table `$C6:0000 + 3*(stage-1)` -> record = 3-byte pointers to roots
  (`000000` ends); root = `[type][ptr24]`... `00`. `$C2:00D7` (A = type)
  runs that type's script of every root, one after the other in **one
  task** (a sleep in a type `04` script holds the rest of the stage setup).
  Types seen: `01` setup (`10 nn`, `42 set group` sounds, `FF A0 id` music),
  `0E` music on, `06` palette cycling, `02` map (`2A pal 27 arc 0A map`),
  `04` stage start (enemies `A2 x y type`, items `21 ...`), `0D` all enemies
  dead, `0B` portal exit (`0F dest` = next mode), `0C` portal touch test.
* Stage `$0D` (1-1) record `$C6:1ADB`; bosses `$67-$70` in bank `$C7`
  (`$67` `$C7:1B47`, rival boss index by `FF 7C 03 07 03 n`; portals behind
  route flags `08 f 49 n`, `83` = not).
* World 1's 1-6 (`features/world1.py` RIVALS, `asm/world1.asm`): stages
  `$67` -> `$69` -> `$6B` -> `$68`, each one rival in seat 4. Rival set-up
  `$C4:3CCF` (A = character, X = seat; from op `FF 7C 03 slot x y char`,
  `$C2:16EE` -> `$C4:3CB5`): `$16C2` = character, `$16DA` = palette id
  (`$80:BB4E[char]` + 7; hook `rival_pal` at `$C4:3CD5`: character 5, ids
  `$5A`/`$5B`/`$6D` = columns 2/3/21 of the palette picture), then the
  character's stats from the table at `$C0:B9D4` (word per character ->
  `$1D26`, hearts + 1 -> `$1662`, bombs `$7E:4EBD`, fire `$17CA`, speed
  `$15D2`/`$15EA`, abilities `$7E:4ED5`, `$167A`; hook `rival_stats` at
  `$C4:3D28`). A bomber with hearts (`$1662`) loses one per hit and blinks.
  Kick = `$167A` bit 6 + `$7E:4ED5` bit 1 (item `$0B`, `$C5:43AB`); item
  handlers: table `$C5:4195` (item id - 1). Boss start op `$C2:16E6`
  (`LDA [$0D] / JSL $C43C60`) runs before the rival set-up. Stats table
  entry: `$1D26` (AI level), hearts + 1, bombs (max 8), fire (range, max
  8; items 1 / `$0E` raise `$17CA`, whose picture is the fire), speed lo/hi, `$7E:4ED5`, `$167A`; the players start with speed
  `$00E0`. Character 1's entry has `$7E:4ED5` = `$20` (SB5's mine bomb):
  `rival_stats` now writes every stat (`world1.RIVAL_STATS`: white 1 bomb /
  1 fire / speed `$E0`, black 2/2/`$100`, golden 3/3/`$120` + 3 hits +
  kick; skate item `$C5:4232` = speed + `$20`, max `$200`; down `$C5:421C`,
  min `$80`). AI level `$1D26` = Battle's COM level (`$7E:625B` - 1: 0 EASY,
  1 NORMAL, 2 HARD, 3 SUPER; the menu's last level `$7E:6247` is 3, 4 once
  SUPER is unlocked); the three rivals use 0 (EASY).
* 1-6's next duel: boss stages with a rival skip SB5's clear task
  (`$C5:3A2D`, `$1D1A` = 8); a dead rival (`$C4:3D98`: `$15A2` bit 7 and
  `$17FA` = `$FF`) only drops its item (`$C4:3DED`) and decrements `$1D50`,
  so no portal ever came. The kept portal root (`$C71BE3` / `$C71F6D` /
  `$C721AD`) also tests route flag 4 in its `0D` / `0C` scripts (`08 04
  49 04 11 ...`; SB5 picks one of six portals by flags). With the clear
  task (`$C5:3B4E`) and flag 4 the portal works as in SB5: entering it ->
  `$C5:02AB` (`$1D1E` bit 0, type `0A`, `$C0:4637`, win sound `$22`, ends
  the task), ~475 frames later a script runs `0F next` (`$C2:0C20`:
  `$1031` = next, `$1D1E` = 4) and `$C5:3AAC` leaves the stage. SB6 plays
  the three duels in stage `$67` alone, as SB1 (`world1.asm` next_rival):
  90 frames after the rival's object is gone (`$17FA` = `$FF`) seat 4 is
  set empty (`$15A2` = `$80`, else the new rival comes out dead) and made
  again as op `FF 7C` does (`$C2:16EE`: `$1D28` / `$1D2A` = cell (7, 1), A
  = character, X = 4, `JSL $C4:3CB5`: set-up, object `$C4:2A69`, `$1D50`
  + 1, death task `$C4:3D94`); `rival_pal` / `rival_stats` read the duel
  (`$7F:FBFD`) while `$7F:FBFE` = 1; the gate opens (its open map words
  follow the closed ones), intro_task walks it in. Before the Golden the
  stands blink first with nobody in seat 4 (intro phase 3: intro_pads
  holds the players' pads), then golden_wait makes it and opens the gate.
  In the last blackout spawn_reset puts every living seat back on its
  start (kept at the first intro): a bomber's x / y are its object's
  (`$055F,obj` / `$05BF,obj`, obj = `$17FA,seat`; `$C4:31BD` makes
  `$182A` / `$1872` from them + `$1D3B` / `$1D3D` every frame), pose `$46`
  facing up. A rival's death item (`$C4:3E10`, table `$C4:B9CA` by
  character) goes through rival_item: in 1-6 the white and black drop
  nothing, the Golden the kick (`$0B`); the stage ends 420 frames after
  the Golden's object went away (time to pick it up): 300 frames after
  its death, or as soon as no item is left on the field (`$1152` bit 7,
  checked from 30 frames on).
* SB1 World 5's crowd: SB1 sounds `$0D` / `$12` (World 5's set only: it
  adds sample 9, `$C5:8DD4` in SB1's ROM, 3627 bytes, looped whole), voice
  0, pitch `$0674`, ADSR `$CC/$EC`, VOL `$4F`, released after 3.4 s.
  SB6 plays the fan game's Audience.mp3 instead (`assets/sound/audience.wav`,
  2.8 s at 8 kHz, ~14.7 KB, no loop), in two pieces around the cornered
  sound's part B (`$D7B1-$DCFF`): sequence + first part ending at `$D7B1`
  (its last block END+LOOP, the directory's loop address = the second
  part), second part from `$DD00` (`crowd.layout`). Every SB1 stage list
  keeps `[B, $DD00)` free (`sb1_music.build` `b_lo`; SB1 samples that do
  not fit below it go above `$DD00`): before, the 18 KB crowd in 1-6 and
  the SB1 samples of 1-1, 1-2, 1-4 and 1-5 ran over part B (the cornered
  sound was cut). Hudson SFX `$61` (`features/crowd.py`; SB5's entries `$61-$66`
  point at a dummy), instrument 29 (garbage in 1-6's set, no SFX there uses
  it), directory `$3E`; sequence + sample at the top of 1-6's music list
  (under the echo buffer, `$F500`), table entries sent by game_sfx's
  upload while `$1031` = `$67`. A bomber's death sound (`$C4:367F`) goes
  through rival_sfx: 1-6's white and black mechas ask for `$61` (game_sfx's
  pending byte `$018C`), every other bomber gets the death sound.
* SB5's flame tiles have two sets: one drawn on the field's own layer
  (palette 2 entries 5-10 = its grass around the fire, 1 and 4 its
  shadow, sparks in the grass) and one drawn on BG1 over a BG2 field
  (color 0 around the fire; 1-1, 1-2, 1-5). `assets/stages/sb5_flames_bg1.bin`
  = the second (1-1's VRAM words `$0100-$07FF`); the first set is no
  longer used (its grass shadows were the white dots of 1-4/1-7).
* SB1's MIDIs (`assets/SB1 midi`, khinsider): melodic 8-interval n-grams
  of each voice of `assets/sound/sb1_w<n>_song.txt` against each MIDI
  track: W1 `level-1-3-`, W2 `level-2`, W3 `level-3`, W4 `level-4`, W5
  (1-6) `level.mid`, W6 `level-6`. After the Golden: `victory_load`, `JML $C5:02AB`, 450 frames later
  `$1031` = `$68` / `$1D1E` = 4 written directly (exit_task). Running type
  `0B` through `$C2:00D7` from our task ended it twice and hung SB5.
  Stages `$69` / `$6B` stay in the ROM (records unchanged) but nothing
  leads there.
* Bomber facing: `JSL $C4:3C24` (A = animation - `$1692,x`, Y = facing 1
  right 2 down 3 left 4 up, X = actor) sets `$1632` and the animation
  `$179A` + facing - 1. Stage start pose `$46-$49` (SB5 shows `$47` with
  `$1632` already 4); when play starts SB5 sets `$15` (front only). The
  animation base of a seat's state: `$C4:42EC` (input after standing:
  `$17E2` = 0; `$1782` bit 7 = on a Louie -> `$C4:4346`: base `$80:BB58`
  indexed by the Louie's character `$16C2 + seat + $0128`; bit 3 = carrying
  -> `$2E`; else 0 = walk). A Louie copies its rider's facing in its own
  routine (`$C4:5289`) and sets its animation (`$C4:547F`, bank-local);
  that routine runs from stage frame ~100 (the fade in). While an intro
  holds the pads (1-6: a rival walks in / the stands blink, `intro_pads`;
  1-7: the clown's intro, phase < 3, `start_up`, from the first frame the
  bombers exist, before the fade in) `hold_up` keeps each seat facing up in
  the stand pose of its state (`up_base`: on a Louie its riding animation,
  else `$46`) and `$17E2` = 0 (no idle), asking for a new animation only
  when `$079F` shows another one (one every frame cost 3 fps with 4
  players); death, getting on / thrown off a Louie, time up, victory and a
  carried bomb are left alone. Before: riders kept facing down in 1-7, and
  in 1-6 showed SB5's idle on a Louie (`$3F`/`$40`) through the stands'
  blink and got the pose on foot `$49` from `spawn_reset` (now `up_base`
  too). After the intro the players are free. SB5 starts play during the intro (~stage frame
  511, lights still out) and sets its idle `$15` (front): `start_up` turns it
  back to the pose up (`$179A - $1692` = `$14`), so nobody idles until the fight.
* Boss victory (1-6, 1-7): SB5 plays it with sound `$22` (`$C5:02D9`,
  stages `$67-$70`; `$21` elsewhere) = command 3 of the song in ARAM; after
  ZONE1-A that is set `$35` + song `$0E` (music id `$0F`, the boss music),
  whose command 3 is the boss victory ("major victory", ~433 frames). The
  SB1 lists of 1-6/1-7 hold only ZONE1's jingles (their command 3 is the
  normal clear) and have no room for its ~15 KB of samples, so
  `victory_load` (world1.asm, sb1_enemies.asm) requests music id `$0F`
  through `$C0:0CED` right before `$C5:02AB` (~80 frames of upload while
  the players stand; its command 1 is replaced by the victory a frame
  later). Calling `$C0:0E31` / `$C0:0E9C` directly instead (past the
  hooks of `$C0:0CED`) crashed into data at `$C0:C77C`.
* 1-6's type `0E` script (`42 j 03` boss jingle, `FD 0E 40 00 00`,
  music, `01`) is `42 06 00 01 00`: the music right after the stage
  intro jingle (`sb1_music.MUSIC_SCRIPTS`).
* 1-6's items like SB1 World 5 (`asm/world1.asm` item_task, from the
  rival's arrival): SB1 5-1's routine `$C4:3523` (SB1 ROM) places one item
  every 640 frames (`$0280`) while fewer than `$20` are on the field
  (`$0C91`), on a random free cell (`$C4:3B6E`, retried next frame), from
  the 16-entry table `$C4:3553` [1,1,2,2,3,4,5,A,B,C,D,9,9,9,F,F] (SB1 ids,
  pictures from `$C3:0870`: 1 bomb, 2 fire, 3 heart, 4 skate, 5 vest, 6
  1-up, 7 bomb with speed lines, 8 wall pass, 9 clock, A full fire, B
  remote, C kick, D boxing glove, E rice ball, F skull). SB5 places a
  visible item with `$C5:4557` (A = item, `$AE` = cell, 8-bit; `$145A` =
  item, `$1052` = `$10`, `$1152` bit 7, metatile `$047E` + 4 x item via
  `$C0:420A`, pushed on the `$4DF0` list). SB5 item ids (pictures checked
  in the 1-6 arena; 1-6 spawns only 2, 1, 3, `$0C`, `$11`, `$0B`, 5): 1 fire, 2 bomb, 3 skate, 4 remote (red bomb), 5
  bomb pass?, 6 wall pass (bricks), 7 vest, 8 clock, 9 1-up (Bomberman's
  head), `$0A` (power glove), `$0B` kick, `$0C` punch (blue glove), `$0D`
  line bomb, `$0E` full fire, `$0F` pierce?, `$10` mine?, `$11` boxing
  glove, `$12`/`$13` skull, `$14` heart, `$15` egg. Random number: `JSL
  $C0:1DEB` with A = n gives 0..n.
* Character abilities of CPU bombers (`$C4:01FE`): `$7D` = character
  (`$16C2 & $0F`, 0 for a pad bomber), `JMP ($C4:0205,X)`: entry 2
  (`$C4:029B`) puts soft blocks (`$C4:2161` -> `$C4:218F` -> `$C0:4383`,
  `$30` in the cell `$0FBA`, every `$28` frames, `$1029`) in front of the
  bomber; entries 1, 3, 5 = `RTS`, 4 `$0310`, 6 `$0459`, 7 `$04F0`, 8
  `$05D7`, 9 `$03F4`. A 1-6 rival as character 2 filled the arena with
  soft blocks drawn as the floor (the arena's soft block picture): the
  rivals are character 5 (`RTS`).
* 1-6's intro (SB1 World 5): `FF 7C 03 07 03 n` (`$C7:1D1E`, `$C7:1FC1`,
  `$C7:2294`, x 7 y 3) now puts the rival at (7, 1) in the stands'
  corridor; `FF 1A F6 07` starts `intro_task`: `$101F+4` = 0 (the rival
  becomes a pad-driven bomber, no AI) until the map is in (and, in `$6B`,
  the stands stopped blinking), corridor cells `$1052+$17/$27` = 0, then
  `intro_pads` (`$C0:0B54`, the main loop's `JSL $C04733` after the pad
  reader; objects run before the tasks, `$C0:0B44`) empties seats 0-3's
  pads and holds down on the rival's (`$31+4`) until `$1872+4` >= `$50`
  (7, 5); then `$101F+4` = 1, the corridor walls again and the closed gate
  (SB1's doors, BG1 map words) is queued. The type 01 script's `10 10`
  (16 random soft blocks, drawn as the floor: invisible) is dropped.
* Bomber death sound (Normal Game, `$C4:367F`): `LDA $101F,X / BNE` skipped
  group 3 id 1 for CPU bombers; NOPed: rivals die with SB1's death sound
  (`gs_sound` -> SFX `$60`), as in SB1. A death while R is missing (being
  restored after another group-3 voice) waits for it, up to 150 main-loop
  passes (`$0196`), instead of being dropped.
* Arena field = BG1, map at VRAM word `$3000` (32 wide; cell (c, r) TL at
  `$3000 + 64r + 2c`), BG tiles from word `$1000` (tile `$100`); an arena
  draws columns 0-14. 1-6 = theme `$28` (named by no SB5 script; only ops
  `0A`/`0B` write `$1B7D`) with set 4 archive / palette `$F0`: ids past
  SB5's tables, through `arc_entry` (`$C0:1B0E`, the archive loader
  `$C0:1B04`: A = id, `$0AE7` set, entry `[$C6] + 8*(id-1)` in bank `$E3`)
  and `pal_lookup` (`asm/bombers.asm`, the palette's word table + colors in
  `bulk`).
* SB5's VRAM queue (main thread): `$C0:0478` opens an entry (`$AE` = VRAM
  word address, header word `$0352` = mode, `$0084` = words, VMAIN `$80`),
  `$C0:0497` appends the word in `$A5`, `$C0:04AC` closes it (size, write
  offset `$0357`); all three start with PHX and end SEP #$30 / PLX, so call
  them with X 8-bit. Ring `$7E:8000-$BFFF` (entries are written straight
  past its end and the offsets masked with `$3FFF`): header mode, size,
  VRAM address, then the data. The NMI (`$C0:04E0`) sends entries while the
  scanline allows it (size < 8: CPU writes, else DMA channel 0). The NMI
  hook `stream_nmi` (`asm/bombers.asm`) runs before `$C5:6AAF`, which
  relies on channel 0's registers and on the vblank time left: a long DMA
  there corrupts the later transfers (flames, HUD).
* 1-6's stands (`stand_task`): fade to black through the INIDISP shadow
  `$0300`, the stands' BG1 map words queued (SB1 5-1's crowd / 5-8's stone),
  fade back; 1-7's electric
  fence (`asm/stage_anim.asm`): SB1 4-8 sends a second picture of 27
  tiles every 2 frames; the hack keeps the fence's tiles in one block of
  slots at the archive's end (29 tiles) and a task queues the frame due
  (entries of 256 bytes) every 2 frames. 1-4's soft blocks (SB1 4-4's
  bumpers, their lights turn): SB1 rewrites BG tiles 2/3/`$12`/`$13` (and
  6/7/`$16`/`$17`, the same bumper over a shadow) with 5 pictures, 3 frames
  each (`assets/stages/sb1_4-4_soft_anim.png`, from SB1's VRAM); the soft
  block's 4 tiles get their own slots and the same task plays them. The
  task's table (`[stage, frames held, pictures, VRAM word, size, first
  picture]`) is started by world1's op `FF 1A F6 05` (1-7) / `06` (1-4,
  1-5, 1-6). 1-6's crowd (SB1 World 5): SB1 swaps BG tiles `$20-$27` /
  `$30-$37` (4 blocks of 16x16) between 2 pictures, each block at its own
  pace: 16, 24 and 19 frames (the last two blocks together, the side
  columns); a stage can have several rows in the task's table, one per
  animation (`anim_groups`, `anim_stages` in `sb1_stages.STAGES`), each
  with its own counter.
* Flames' layer: an explosion cell (`$C5:1E77`) selects layer `$0F61`
  (`JSL $C007B8`: `$036F` = that layer's map base, `$C0:420A` queues the
  cell's 4 words at `$7F:0400-$0CFF`, sent by `$C0:42EB`); `$0F61` = 3 -
  `$1B7C` at the stage start (`$C5:1381`; 1 = BG1 over the field), or op
  `FF 79 n` (`$C2:16CD`, also `$1D1A` |= 2 when n != `$1B7C`). Flames are
  BG tiles `$010-$07F` (palette 2, tile n always in quadrant n & 3 of its
  cell, never flipped). SB5's stage `$10` put them on BG2 (`FF 79 02`; BG1
  held its clouds: `FF 21 01` scroll, `FF 42 01` drift, `FF 26 41 02 12`
  color math BG1 + half the subscreen), replacing the floor cell: on SB1's
  floors that showed SB5's grass and its shadows. Hack: 1-4 drops those
  ops (`world1.DROP_OPS`) and draws its flames on BG1 like 1-1; the
  animation task (`asm/stage_anim.asm`, once, 60 frames after its start:
  SB5's set-up `$C5:140D`, skipped when `$1D1A` bit 1, rewrites the end
  tiles `$010-$01F` 25-35 frames in, mixed with SB5's floor tile
  `$7E:35D3`, which showed as dots at the flames' ends; 256 bytes a
  frame; checked by `tools/flame_check.py`) sends the BG1 set to 1-4 and 1-5, and to the arenas (1-6, 1-7:
  field = BG1, flames on it) the BG1 set with its color 0 pixels taken
  from the floor cell (colors in palette 2 entries 5-10). One set draws
  one floor: in 1-7 a flame over a cell under a block hides SB1's shadow
  row there (the arena's most common floor cell is drawn instead).
* Burning soft blocks (SB1 stages): SB1 draws them on BG1 (tiles `$1C0-$1CA`,
  palette 7, 6 pictures of 12/10/8/6/4/2 frames); `sb1_stages` puts 5 of them
  (`assets/stages/<stage>_burn.png`, from SB1's VRAM) in SB5's 5 burning
  frames (palette 3).
* Stage `$17`'s type `06` script: `FF DF` (`$C5:4A94`, theme 5's version of
  `FF DD`; `$C5:4AB6` rewrites tiles `$12C-$12F`, the 1-5 borders): dropped.
* Stage `$10`'s type `06` script: `FF DD` (`$C5:49A1`) creates SB5's
  decoration objects; one (`$C5:49D7`) rewrites tiles `$12C-$12F` every
  ~100 frames (the SB1 pillars there turned into arches): dropped, with
  the clouds (see "Flames' layer").
* Stage IRQ (`$C0:F08D`, vector `JMP ($006D)`, `$033D` = `$A1`): line 0
  draws the HUD (TM `$16`, BG2 = its background: map `$3A` (`$3800`, 32 x
  64), scroll 0); line `$15` writes BG2SC = `$0369`, TM = `$030F` and BG3's
  scroll for the field; line `$17` BG2's scroll from `$0333`/`$0339` (low
  bytes of the NMI copies of `$031B`/`$0321`). BG12NBA is not split (0).
  In stage `$68` VRAM `$3400-$37FF` (BG1's lower screen, 32 x 64 map at
  `$3000`, never shown) and `$4800-$4FFF` were zero; BG2's HUD rows above
  line 21 come from the lower screen of its map (`$3C00-$3C5F`, written
  over -> garbage in the HUD), its upper screen `$3800-$3BFF` (the theme's
  margin pattern) is never shown in `$68`, where `$0369` is the clown's.
* 1-7's clown (`asm/sb1_enemies.asm` `clown*`, `features/sb1_enemies.py`
  `clown_bg`; SB1's boss: "SB1 2-8's clown" below): 23 pictures of
  `assets/enemies/sb1_2-8_clown_frames.png` (`tools/sb1_clown_frames.py`,
  drawn from SB1's own frame tables; row 1 = SB1's red flash palette) on
  BG2 below the HUD through the IRQ above, double-buffered: tiles
  `$340-$37F` (`$3400`) + map `$4800`, tiles `$380-$3BF` (`$3800`) + map
  `$4C00` (64 tiles each, 16 x 15 map words; a picture goes into the buffer
  not shown through the VRAM queue `$7E:8000` and `$0369` switches once the
  queue's read pointer `$0355` passed it); scroll `$031B`/`$0321`, hidden
  by `$030F` bit 1; colors in BG palettes 3 and 6 (`extra_pals` of
  "sb1_4-8"), a color = its normal and its red value (23 pairs). Pictures,
  maps and both palette sets: 40 KB at `$C8:0000` (`free_c8_sheets`, put
  there by `clown_alloc` after `bombers.free_stock_sheets`; the code, in
  `free_d6`, is assembled first with that address). Body = enemy type 07
  (record: routine `clown`, empty mapping; its OBJ tiles / palette are the
  shots' and explosions', `assets/enemies/sb1_2-8_fx.png`, drawn by
  `clown_oam` into OAM slots 104-127 after SB5's builder, `JSL` at
  `$C0:0B5D`): placed on the clown's center every frame (`$C3:4CFC`); SB1's
  rules (states, tables, speeds, hits) run in its routine, contact kills go
  through SB5's `$C3:47C9` with the seat distances (`$0110+`) set to 0 for
  the seats touched. 8 hits (SB1 18); after a hit it blinks with its white
  silhouettes (pictures 7-10, `!CWH`: no red flash), below half its hits
  it keeps SB1's red colors softened (`hp_pal`; `CLOWN_RED` = 0.4 of the red over its own). The sinking shows every picture
  (the next one waits until the queue sent it). The body is never killed
  (SB5's enemy death sound / burst and, with `$1D50` = 0, the clear task's
  door are not wanted): the routine stops drawing it and starts
  `clown_win`, SB5's stage end as 1-6's after the Golden Bomber (`$C5:02AB`:
  `$1D1E` bit 0, type 0A script = win pose, sound `$22`, after `victory_load`), and `clown_task`
  ends the stage into `$1C` 450 frames later (the whole victory; `!CTIM` is a word, written 16-bit) (`$1031`, `$1D1E` = 4: what op
  0F does). `clown_stop` (stage over) puts `$0369` back but leaves BG2 off:
  turned on, BG2 showed its HUD map's upper screen over the fading field,
  where buffer 1's tiles now are (a screen of garbage at the end). The dark
  (SB1: subscreen BG2 subtracted, with a hole around the face): the fixed
  color (`$0315-$0317`, up to (20, 22, 10) in 24 steps, back in 8)
  subtracted from BG1, BG3 and the backdrop (`$0313` = `$20`, `$0314` =
  `$A5`) except inside color window 1 (`$0308` = `$20`), whose left/right
  per line come from HDMA channel 7 (`!CHT`, `$033E`/`$0AEA` bit 7): the
  HUD lines (0-20) and, once the face shows, an oval 88 x 104 around it;
  OBJ palettes dimmed in CGRAM alike (math reaches OBJ palettes 4-7 only),
  Pictures over 64 tiles (3 tiles in all) lose their emptiest tiles to
  the closest other tile in any of its 4 flips, or to blank when that
  errs less (`clown_bg`; an unflipped closest tile left stray pixels on
  the edges of the death pictures).
  colors SB5 writes meanwhile (the start blink's restore `$C1:0035` every
  frame) taken as the new originals (`obj_watch`). Players face up
  from the stage's first frame to the end of the intro (`start_up`) and their pads are held (`intro_pads`, `$7F:E019` =
  `$A5`) during the intro and the death. Started by `FF 1A F6 05` (with
  the fence). Music: SB1's boss song converted from SB1's driver
  (`sb1_boss_song.txt`), no SB5 boss jingle.
* Boss stages: `$C5:3A2D` skips SB5's stage tasks (`$C4:221D`, `$C5:024D`,
  `$C5:0000`, the clear task `$C5:3B4E`) when `$1D1A` = 8; stage `$68`
  without its rival runs them (`$1D1A` = `$40`). Op `FF 7C slot x y char`
  (`$C2:16E6`) = `JSL $C43C60` (boss start: the rival's AI task `$C4:007B`)
  then the rival set-up. Op `10 n` (`$C2:0C32`) = `$0E1F`, the soft blocks
  scattered at random (`$C5:0160`, map id 2 at `$7E:2400`, unless `$1D1A &
  $0C` or `$0E24`); SB5's arenas have `10 10` in their type 01 script.
* Enemies alive `$1D50` (+1 `$C3:050B`, -1 in the death routine
  `$C3:0649-$065A`). The clear check is a native task `$C5:3B4E` (started by
  `$C5:3A58` `JSL $C020A1 / dl`): `$1D50` = 0 -> `LDA #$0D / JSL $C200D7`
  (type `0D` scripts), then it becomes the portal processor `$C5:3B60`.
  Poking `$1D50` = 0 in a test clears the stage (the enemies stay).
* Portal queue `$7E:4DA3` (5 slots, `$FF` free; state `$41`/`$42` from
  `JSL $C20372` with op `$11`'s first operand; x `$4DA8`, y `$4DAD`). Op
  `11 label x y` (`$C2:0C38`) queues; the processor waits while the cell has
  `$1052 & $E0` (soft block) or `$1152 & $C0`, then creates the portal
  (object `$04FF` = 6, `$04A0` = `$26`), SFX group 2 `$33`, archive set 3
  `$63` (its beam tiles, OBJ `$160+`, `$D6:CAA7`). Op `12 x y`
  (`$C2:0C67`): sum of seat + 1 of the bombers on the cell -> `$0373`,
  `JSL $C174D1`. Player cell = (`$182A`+8)>>4, ((`$1872`+8)&`$F0`)>>4.
* Soft block scatter `$C5:0141` (op `10 n`): `$7E:2700` per cell, `$80`
  wall (`$1052` is filled later), `$10` kept clear (`$C5:01B4`: row 12, each
  enemy's cell, the 3x3 around each bomber, offsets at `$80:8A7A`), `$90`
  soft block placed; `$0E1F` blocks go to random cells without `$F0`. Hack:
  `c5_reserve` at `$C5:0171` (`JSR $01B4`) -> `e4_reserve` also keeps clear,
  per seat, the shortest straight run of 1-4 free cells with a free cell
  beside its end (bomb on the start, hide around the corner: safe for any
  fire range); 1-2's lower-left corner (extra walls) needs 4. Then
  `shield` (same file) walls each seat's pocket in: from the seat's cell it
  walks up to 6 steps through cells kept clear (`$10`, no `$80`) and puts a
  soft block (`$7E:2400` = 2, `$7E:2700 |= $90`, one of the `$0E1F` random
  ones) on every free neighbour of the pocket, so no enemy can walk in
  before the seat bombs its way out (only while the scatter runs, `$1D1A &
  $0C` = 0). `coop4_check.py` checks it on the CHAIN stages ("shut in": every
  free edge cell of the pocket is a soft block, no enemy starts inside).
* Soft blocks are random each play (`$1052` = `$30`, walls `$80`); the
  collision map is filled ~50 frames after the type `04` scripts. Items:
  `$145A` + cell. RNG: `JSL $C01DC4` (A = random byte).
* Native tasks: `JSL $C020A1` + inline `dl routine` registers one (called
  every frame by the runner, M/X 8-bit); it returns one byte past the `dl`
  (SB5's callers put an `RTS` there that never runs: leave a filler byte).
  `JSL $C021CE` ends the current one.
* Script op at `$C0:1171` (stage records' music entries): set + song from
  the table `$80:8655` (3 bytes per id) straight into Hudson's driver; it
  returns with M/X 8-bit.
* Enemies: one routine `$C3:4B5A` for all (type `$16C2,x`, cell `$16AA,x`,
  facing `$1632,x` 1 right 2 down 3 left 4 up, HP `$1662,x`); flame test
  `$C3:49EC` (Y = cell): `$1052 & 4` = flame (`& 7`: 7 center, 5
  horizontal arm, 6 vertical; walls hit by flame `$83`, bombs `$50`), then a hit costs 1 HP and gives 180 frames
  (`$085F`) of grace; 0 HP -> `SEC` -> death `$C3:4D1C`/`$4D41`. Knights
  (type `$08`, SB5 1-11 = `$17`) have 4 HP (type record byte 14, `$C3:00DA`; the hack: 2). Hack: `knight_hit`
  (`asm/world1.asm`) skips the hit on 1-5 only when a knight stands on an
  arm along the way it faces and the center is ahead (checked every frame:
  a knight turned away mid-explosion is hit); 1-5 keeps only its two knights (SB1 6-4).
* Enemy type records: 16 bytes at `$C3:005C + 16*(type-1)`, 15 copied to
  `$1D41+` by `$C3:0000` (`[arc, pal, slot mask, T|flags, first anim, ...,
  routine24 ($C3:4B5A), data16, ...]`): set 8 archive (OBJ tiles, LZ; tile
  2i = VRAM tile i of a 16-tile row, 2i+1 the one under it, 32 per page),
  set 8 palette (16 colors), palette slots `$38` (3-5: at most 3 enemy
  palettes at once), object type T (7 for walkers), animation base `$1692`;
  a walker shows base + facing - 1. Stage use of types (`A2 x y type`):
  01 `$0D/$0E`, 02 `$0F/$12`, 03 `$13/$14/$16`, 04 `$10`, 05 `$11/$12/$16`,
  06 `$14`, 07 `$18-$1B`, 08 `$15/$17`. T 7: animations 1-`$27`, mappings
  1-`$D5`.
* Hack (`features/sb1_enemies.py`, `tools/sb1_enemy_frames.py`): types 02,
  03, 06 = type 01's record with SB1 2-1's spring head / pot / clown face
  (archives 4, 5, 8 and palettes 2, 3, 6 of set 8 rewritten; T 7
  animations `$60+` and mappings `$D6+` in `objmap`, read through
  `enemy_anim` / `enemy_map` in `asm/bombers.asm`; these three are mapping
  page 1: a second table with the same ids, chosen by `enemy_map` when the
  object's animation is `!ENANIM2` or above) and SB1's routines
  (`sb1_spring` / `sb1_pot` / `sb1_face`, `asm/sb1_enemies.asm`, below);
  1-2 (`$11`) places 2 springs, 2 pots, 2 clowns on SB1's start cells (SB1 has 4 springs: 8 enemies dipped to 44 fps with 4 players)
  (`STAGE_ENEMIES`). 1-4 (`$10`) places 3 of SB1
  4-4's 4 UFOs, its bomb robot and 2 of SB1 4-2's horned robots instead of
  SB5's 2 tanks: types `$35` / `$36` (placed by no SB5 stage; they share set
  8 archive and palette `$31`, one sheet) and type `04` (SB5's tank, only in
  `$10`: archive 6 rewritten, its 32-color palette 4 freed); the three share
  palette `$31` (pal group `w14`, 27 colors merged to 15: 1 enemy OBJ slot),
  mapping page 2 (`!ENANIM3`), routines `sb1_ufo` / `sb1_bot` / `sb1_horn`. Type 05 = SB1 3-6's
  chameleon (1-3 = `$18`, 7 of them): record routine `chameleon`
  (`asm/chameleon.asm`, built after the characters by `sb1_enemies.chameleon`). Actor routine pointer =
  record bytes 9-11 (called through `JML [$A5]`, X = actor, M/X 8-bit, RTL).
* SB1's 2-1 enemies (SB1 ROM, scene `$08`, objects `$1000+$40*n`, list from `$0F40` linked by `+$06`;
  `$00` routine24, `$08` animation (+1), `$0B` entries, `$0C` entry, `$0D` frames left, `$0E` priority,
  `$0F` tile slot, `$10-$11` x (sub, px), `$13-$14` y, `$16` direction table (4 animation words, bank `$18`),
  `$19` speed, `$1E`/`$1F` palette add, `$20` direction 0 up 1 right 2 down 3 left, `$21` timer, `$22`
  direction of the animation shown): create (stage list, cell center `(x & $F0) | 8`, `$20` = 2) ->
  init (`$16`, first animation, `$21`, `$22` = `$FF`, `$19` = 0) -> routine: brain, flame `$C6:0BDE`,
  contact `$C6:34FC` with `$40` = `$0C0C` (a player within 12 px both ways dies), draw `$C6:2576`.
  Spring head `$C6:6428` (brain `$C6:3947`, table `$C6:7D1B`, animations `$C6:4386/43A7/43C8/43E9` by
  direction: 8 entries, 5 pictures, frames 16 3 4 6 8 6 4 3), pot `$C6:653A` (brain `$C6:37B0`, `$21` =
  `$40`, `$C6:448A`: 8 pictures x 9), clown face `$C6:7181` (brain `$C6:3774`, `$21` = 3, `$C6:4AFC`: 13
  entries, 8 pictures, 21 7 7 7 7 7 21 10 12 10 21 13 12). Animation = [count] + [frame24, frames]; frame
  = [count] + [dx, dy, slot, tile, attr] (`$C6:25EA`, see `tools/sb1_enemy_frames.py`); `$C6:2814`
  restarts it (every turn after a step, even to the same animation). Way shut `$C6:3495` (`$42` bits of
  the cell word at `$0916 + 64 * row + 2 * column`, `$80` wall, `$40` soft block, `$20` bomb; tested
  cells `$C6:1562` up (x, y - 9), `$15CE` right (x + 8, y), `$1586` down (x, y + 8), `$15AA` left (x - 9,
  y)): `$E0` for spring and face, `$A0` for the pot (it walks through soft blocks). Step `$C6:360E`:
  speed table `$C6:36BB` (speed 0 = `$80` = 1/2 px), first 1 px toward the column's (row's) center, then
  `$C6:34BD`: another listed object within 16 px both ways -> position back, a random direction equal to
  its own or the way shut -> turned around, carry set (no animation update). Brains: spring = way shut
  -> nearest live player (`$C6:39C0`, P1 / P2 by |dx| + |dy|) -> across toward it (`$C6:35EA`
  right / left, `$C6:35FD` down / up; in line = quarter turn clockwise), taken if open, else quarter turn
  clockwise; pot = `$21` - 1, at 0 on a cell's center (`$C4:23F7`) `$21` = 16-79 and a random direction,
  way shut -> random direction; face = way shut -> `$21` - 1: not 0 = turn around, 0 = quarter turn
  clockwise and `$21` = 3-6. Death `$C6:33C0`: 32 frames standing, palette `$0E` every other frame.
* SB1's 4-2 / 4-4 enemies (objects as above; creates in the stage lists at `$C3:0Dxx`, a create sets `$1A`
  extra hits, `$20` = 2; init sets `$16`, `$19` speed, `$21`, `$22` = `$FF`, `$3D` score rank): UFO (4-4)
  `$C6:74C5`, table `$C6:7DA3` (one animation `$C6:5842`, 4 pictures x 12), `$1A` = 1, `$21` = 1, `$1C` =
  `$E0`, brain `$C6:383A`: on a cell's center (`$C4:23F7`) or at a shut way, nearest player (`$C6:39C0`);
  `$21` = 0 -> `$21` = 1, straight on; else `$21` = 0 and across toward the player (`$C6:35EA` / `$35FD`) if
  open and not in line, else straight on, a quarter turn clockwise if shut. Bomb robot (4-4) `$C6:5FDE`,
  table `$C6:7D13` (up `$41BE`, right `$41CF`, down `$41E0`, left `$41F1`: 4 pictures x 1 frame), `$1A` = 4,
  `$19` = 2, `$21` = `$40`, the clown face's brain `$C6:3774`. Horned robot (4-2) `$C6:5A34` (create
  `$C6:59F8` area, init `$C6:5A0A`), table `$C6:7D03` (up `$3E7E` 3 pictures x 2, right `$3E8F` / down
  `$3EB8` / left `$3EE5` 6 pictures 16 3 3 3 3 16 ...), 40 px wide sideways, brain `$C6:3ADF`: for P1, P2
  (`$C6:3B64`): a live player within `$0C` across and `$50` along the axis it goes on (`$C6:359F`), else
  the other axis; the way toward it (`$C6:35E2`) unless that is behind it or shut -> taken; seen -> on the
  center across its way `$30` + 1, at `$20` speed + 1 for that step (`$30` stays `$1F`), else no step;
  not seen -> `$30` = 0, straight on, at a wall `$C6:3807` (the face's turn). Speeds `$C6:36BB` (32 bytes
  each, 4 directions x (dx, dy) words): 0 = `$80`, 1 = `$100`, 2 = `$180` sub-pixels a frame. Flames
  `$C6:0BDE`: `$1A` > 0 -> `$1A` - 1 and 32 frames (`$1B`) blinking. The 4-2 yellow saucers that open are
  `$C6:6202` (table `$C6:7DAB`), the dark ones that hide `$C6:7C94` (pot brain).
* Hack, SB1 2-1's enemies (`asm/sb1_enemies.asm` `sb1w`): stop-watch -> `$C3:4C13`; else SB5's
  `$C3:4B7B` (contact, flames: SB5's rule, |dx| and |dy| < 8 (`$C3:47C9`), not SB1's 12), SB1's brain and
  step on SB5's coordinates (SB1's - 8: centers at `& $0F` = 0; `$1812`/`$185A` the sub-pixels), the
  other enemies = actors 5-`$198C` with `$16C2` != 0, alive; masks `$E8` / `$C8` of `$1052` (SB5's
  enemy mask, without `$20` soft blocks for the pot), SB5 facing from the direction, then `$C3:4CFC`.
  Bank `$C3` RTS routines are called by pushing `$4B79` (the RTL at `$C3:4B7A`) and the return address.
  Animations: kind's first + facing - 1 (`$C0:11EC`). Sheets from SB1's tables (32 x 64 cells; SB1
  piece (dx, dy) = SB5 piece (dx, dy - 1)), cut on the grid that needs the fewest new tiles, then into
  16x16 pieces (`_cover` / `_kind_big`) within the OBJ pages the 8x8 cut takes: about 2 sprites per enemy
  instead of 6-10 (with 4 players and 8 enemies `$C0:152E`, the OAM builder, made the main loop miss
  every other frame). Pot and clown share one OBJ palette (set 8 palette 3, `pal` in `KINDS`, 25 colors
  merged to 15 by `_group_colors`; the clown's palette 6 keeps SB5's colors, unread): with 4 players 1-2
  needs stage, 4 bombers and the Louie palette (an egg appears only if a slot 3-7 is free,
  `louie_egg_ok`), which leaves 2 slots for its enemies.
* SB1's chameleon (SB1 ROM, scene `$15` = 3-6, objects `$1140+$40*n`): walk state `$C6:69FB` (timer
  `$30` = 192-255 from `$C6:69ED`, form `$31`: 1 frog, 0 bomber), change `$C6:6AE3` -> `$C6:6B29`
  (standing, `$C6:6B64`): `$36` = 32 frames, then the 32 entries `[frog?, frames]` of `$C6:6BFC`
  (read backwards when it becomes a bomber), each switching palette `$1F` / tile base `$0F` (frog: own;
  bomber: P1's or P2's palette at random and the players' tiles, `$C4:293B + 2*dir`) and the animation's
  first frame. Seen in Mesen: 63 frames as before, new 1 / old 3 x3, new 1 / old 2 x3, 1 / 1 x3,
  new 2 / old 1 x3, new 3 / old 1 x3, new 32, then it walks (143 frames). A flame (`$C6:0BDE`) kills a
  frog or a changing chameleon (`$C6:33C0`); a bomber blinks 32 frames (`$C6:6A93`, palette `$0E`) and
  changes back into a frog.
* SB5 enemy details used by `asm/chameleon.asm`: `$C3:4C13` is the stop-watch routine (enemies frozen
  by `$0E20/$0E21`): contact and flames (`$C3:4B7B` with `$1FF3` = `$FF`) without moving, and
  `$0800,obj` = 0; `$0800,obj` = script steps per frame (1 at creation `$C0:132D`, 2 for a walking
  bomber); `$15A2,x` bit 2 skips the walker's flame test (`$C3:4BB2`); a flame death sets `$15A2` bit 7
  and the actor routine `$C3:4D0E` (`$C4:2374`). Main loop `$C0:0B4A` clears `$03D3`, `$C0:0B59` builds
  the OAM and sets it: the NMI sends the OAM (`$C0:14F9`) only when it is set, so a DMA done in the same
  NMI only when `$03D3` != 0 matches the OAM shown (`cham_nmi`).
* Hack, chameleons (`asm/chameleon.asm`): frog walk (`$C3:4B5A`), change (`$C3:4C13`, FLICK = SB1's
  table without its final 32 standing frames), copy walk (`$C3:4B5A`; a flame kills the copy too, unlike
  SB1). The copy is drawn only with the pose whose tiles are in its half (`HLOAD`), the frog until one is.
  The copy: a live seat at random, its character's walk 01-04 by
  facing from CTAB (per character and facing `[frames, mapping24, source24, columns]`; poses streamed
  for the players are reused, the others are cut out of the animation's strip: the columns its pieces
  use, renumbered, checked pixel by pixel; at most 5 columns), tiles in a VRAM half of its own (OBJ
  pages 12-15 = tiles `$180-$1FF`, 8 halves of 8 x 2 tiles, owner `$7D` set by the first chameleon:
  1-3's static sprites end at page 9; co-op's `lend_pages` only lends `$7E` pages), at most 3 pose DMAs
  queued per frame, sent by `cham_nmi` (JSL at `$C0:F41D`, then the bombers' `stream_nmi`); the
  player's palette slot; own script held (`$07A0` = `$FF`). `cham_hit` (JSL at `$C3:4D41`, then
  `gs_enemy`) restores the own slot of one killed outside its routine. Checked in Mesen frame by frame
  (Bomberman = cut poses, character 1 = streamed poses): no frame with the wrong tiles.
  Unseen copies (fixed): the OAM builder (`$C0:146F`) skips an object whose mapping id `$049F` is 0 (and
  one whose blink count `$085F` is odd). `$C3:4C13` is SB5's stop-watch routine: after the contact /
  flame test it blinks the enemy by clearing `$049F` on the frames its table (`$B934`, by `$0E20` and the
  frame counter `$0069`) says; with no stop watch running (`$0E20` = 0) it still reaches that table, so a
  changing chameleon was blanked every few frames, and a copy whose change ended on such a frame walked
  with id 0 (its script is held) until it turned: up to 35 frames unseen. `show_copy` now puts the frog's
  last id (`$1E7E`) back when `$049F` is 0 and no stop watch runs. `tools/qa_check.py chameleons` checks
  every chameleon has sprites on its spot every frame.
* Stage field (BG2), type `02` script `2A n 27 n 0A map theme` (set 4):
  op `0A` (`$C2:0BED`, `$1B7E` map, `$1B7D` theme; `$C0:3550`/`$357B`).
  Map m = 16 x 13 metatile ids (LZ, row 13 = 0) at the first 24-bit
  pointer of the list named by the 3 bytes at `$D0:A000 + 3*(m-1)`. Theme t:
  metatile table at word `$D0:0000 + 2*(t-1)` (bank `$D0`, 4 BG2 words TL TR
  BL BR per id; table size = up to the next theme's), collision table at
  word `$D0:8000 + 2*(t-1)` (`$80` wall, `$30` soft, `$00` floor per id).
  Id 2 = the soft block scattered at random; a burnt block shows the map's
  id again. Burning frames: tiles `$126`, `$122`, `$11E`, `$11A`, `$116`
  (4 each) in palette 3, ~8 frames apiece; flames = tiles `$050-$07B`
  palette 2. Set 4 archive n = BG tiles from `$100` (LZ; theme 2 `$1600`
  bytes), palette n = CGRAM `$20`/`$30` + 80/64 colors (palettes 2/3-6).
  Theme 2 = stages `$0F`/`$10`, 5 = `$15-$17`, 4 = `$13`/`$14`. Stage
  `$10`'s type `06` script draws SB5's clouds on BG1 (`FF 8D DA 04`,
  `FF 8D DB 04`, set 4 arrangements).
* Hack (`features/sb1_stages.py`, pictures from `tools/sb1_stage_assets.py`):
  1-4 (`$10`) = SB1 4-4, 1-5 (`$17`) = SB1 6-4: new map, metatiles,
  collisions, archive and palette for themes 2 / 5 (5's tables are new
  ones in bank `$D0`, 33 ids); SB1 draws its stages on BG1 in 16x16-tile mode, 17
  x 13 entries (walls 2 wide): SB5 column c = SB1 column c + 1. SB5 shows
  BG2 8 pixels to the right (column 0 at screen x 8): screen x 0-7 is the
  right half of column 15 wrapped around, so that half gets SB1 column 0's
  right half (`wrap`, 1-4 / 1-5 / 1-6). 1-5's hard blocks blink like SB1
  6-4's (SB1 swaps BG tiles `$14`/`$15`: light off 16 frames, lit 32;
  `asm/stage_anim.asm`, op `FF 1A F6 06`). 1-7
  (`$68`, boss arena: `2A 1B 27 1F 0B 27 0C 8F`, op `0B` = theme, `0C` =
  map + draw without soft blocks; theme `$27`, archive `$1F`, palette `$1B`
  are shared by all arenas `$67-$73`, `$9C-$9F`) = SB1 4-8: its script now
  names archive / palette 4 (freed slots) and theme 4, whose tables are new
  ones in freed bank `$D0` room (`free_d0_maps*`).
* Stage intro text (task `$C5:0CD9`, `$0D` <= `$102F` < `$67`): set 4
  arrangement `$E0` centred on column `$10` (`JSL $C00000`), digits = set 4
  `$EA + digit` at columns `$11`, `$15`, `$16` row `$0E` (`JSL $C00009`) from
  the decimal word `$80:8A8A + 2*$102F` (1001 = "1 - 01"; split by
  `$C0:4672` into `$1CB6-$1CBA`). Font = BG3 set 3 archive `$4D` (LZ, VRAM
  `$5400`, tiles `$80-$F6`: digits, PAUSE!, ZONE `$A6-$AB`, START, TIME,
  HURRY UP!). World map label "ZONE" + digit: BG3 tiles 1-8 / `$11-$18` +
  `$0A`+ of set 3 archive `$0D` (raw, `$E3:D110`).
* Hack (`tools/sb6/features/world1.py`, `asm/world1.asm`): the stage
  intro and the pause read STAGE w-s: archive `$4D` re-packed in `bulk`
  with S T A G E (8 x 16, `features/pause.py` LETTERS) in tiles
  `$A6-$AA` / `$B6-$BA`, arrangement `$E0` = "STAGE  -" (8 wide, in
  `free_e2`), placed with the digits by `intro_label` (`asm/pause.asm`,
  `JSL` + `BRA` at `$C5:0CEB`: centred on column 16, the stage without
  its leading 0; SB5's digit arrangements `$EA+` are 2 wide, digit +
  blank, so the world digit's blank covers `$E0`'s dash and the dash is
  drawn again after it as set 4 `$C6` = "-" + blank, the slot of the
  freed Password arrangement; a 1-wide arrangement hangs `$C0:0009`); "WORLD" on the world map label (archive `$0D` tiles
  redrawn in place); World 1 = `$0D`, `$11`, `$18`, `$10`, `$17` (1-1..1-5, one door
  each: op `FF 1A F6 n`, the door hides in a random soft block, picked by a
  native task once the map is in), then bosses `$67` -> `$69` (1-6) -> `$68`
  (1-7) -> `$1C`. 1-7 has no rival (its `FF 7C` root and the portal root
  are dropped, so is `10 10`, and the World 1 door root): the clown (type 07
  at 7, 4); its routine ends the stage into `$1C`. A cleared stage's end stores
  the stage it leads to in `$1046` (`stage_last`, `$C5:3ADC`), so the map
  (and a reloaded save) opens 1-7 after 1-6.

## SB1 2-8's clown (Super Bomberman (USA), HiROM, file offset = address & `$3FFFFF`)

* Object `$1000`, created at `$C7:3CDA`: x `$88`, y `$5E` (obj; the face's
  center is y - `$20`), 18 hits (`$32`), `$0314` |= 8 (players and timer
  frozen), obj `$0E` = `$30`, `$0F` = 4, `$1E` = 8 (OBJ palettes 4-6, the
  white silhouettes 7). SB1 draws every piece 8 px left of obj x.
* Intro: `$3D21` 224 frames, then the field goes dark by color math
  (CGADSUB `$9F` subtracting subscreen BG2: field about -(20, 22, 10) in
  5-bit, the clown -(4, 4, 0), the bombers untouched), `$3D4E` 128 frames,
  animation `$3A58` (N16 N6 I6 N4 I4 N4 I4 I6 N6 I10 N44, I = the eye
  glint), lights on, state `$24`, main routine `$3DBC`.
* `$3DBC`: target = nearest player (`$C6:39C0`); per axis acceleration +-1
  (x: + when the player's x >= its own; y: + when its y - `$20` < the
  player's) up to speed +-`$40` (1/256 px a frame; both doubled in state
  `$0C`), added unless the speed already equals the cap; position x
  clamped to `$3F00-$D000`, obj y to `$5000-$C000`. Flames: `$C6:370B`
  with `$2020` (cells within 32 px of the center); contact `$C6:353D` with
  `$1010` (16 px). Animation end (`$C6:2576`) -> `$C7:3EC9`: state =
  next[state], animation = anim[state] (tables `$C7:425C` word + next byte
  per state / 4, after-hit `$C7:428E`): 0 N255; 4 intro; 8 D10 E7 F13 ->
  `$0C` (hit `$2C`); `$0C` F128 (crying, fast) -> `$24` (hit `$2C`; speeds
  zeroed at its end); `$10` G255; `$14`/`$18`/`$1C`/`$20` N/D/E/G
  alternating with their white silhouettes 3 + 3 frames, 10 times (G 12)
  -> 8 (`$20` -> `$10`); `$24` N28 O22 loop (hit `$28`); `$28` N255 ->
  `$14`; `$2C` N255 -> `$18`. Pictures N `$2B58`, O `$3452`, I `$2C0D`,
  D `$2D7D`, E `$2E32`, F `$2EFB`, G `$2FC4`, white `$308D` `$3142`
  `$31F7` `$3389`.
* Hit (`$3EF1`): hits - 1 (0: death `$3FF8`), `$16` = `$60` stunned frames
  (`$3F6B`: no move, no flames, contact on, its animation plays, OBJ
  palettes `$0C-$0E` = `$C7:3FF0` (`0D 10 11` / red `12 12 12`) by stun &
  2), state = after-hit[state], 8 shots (`$C7:412A`, directions 0-7: speeds
  `$C7:421C` (0, -`$F0`), (`$A0`, -`$A0`), (`$F0`, 0) ..., offsets from the
  center `$C7:423C` (0, -48), (29, -35), (40, -8), (29, 19), (0, 32) ...;
  routine `$C7:4158`, OBJ palette 0, animation `$3C2E` 4 pictures 3/1/3/1
  frames, gone off the screen, contact `$C6:34FC` 8 px, over walls). Red
  palette: `7C1F 007F 0018 001F 000C 0013 001A 0119 0011 0017 0011 0012
  000C 053F 0011 01DF`.
* The dark seen in Mesen: CGWSEL `$02` / CGADSUB `$9F` all along; BG2
  (map `$5400`, palette 1) is a darkness layer, color 4 = (20, 20, 11)
  with an oval hole about 41 x 48 px with a 2-color soft edge (colors 1-2:
  (4, 4, 1), ...) on the face; its colors step down over ~24 frames
  (frames 1562-1586 of a run) and back up over ~8 (1786-1792).
* Death (`$3FF8`): `$0314` |= 8, 385 frames of `$3B8F` (G / white G) and
  the red flash, explosions (`$C6:31D7` with `$C7:40AA`: one every 4
  frames at the center +- (random & `$3F`, minus when bit 0 is clear) on
  each axis, animation `$C6:2F23` 5/4/2/1/1 frames, 32 x 32 = one 16 x 16
  tile mirrored, sounds `$15` every 16 frames, `$1B` every 32), then
  `$3BF9` sinks (G13 then 12 frames `$3507`-`$3A1C`, sound `$18`), the
  players' win pose (`$C4:1AD8`), 128 frames, the map.

## Super Bomberman 1's sound driver (ZONE1 map music)

* Boot: IPL upload to `$0800`, a second stage loader, then cold start
  `$0812` (clears `$0000-$07FF`, inits, writes `$68`/`$09` to ports 2/3,
  main loop `$0846`). All songs and samples stay in ARAM (`$0800-$A1BB`; SB1
  never writes above, Mesen fills it with power-on garbage); per-stage data
  is uploaded later. No echo on the map song (EDL 0, FLG `$20`).
* Port 0 = music / control, port 1 = SFX: a command is new when its bit 7
  differs from the last one; the driver echoes it. Port 0 `$37`-`$3F`: table
  `$0890` (`$37` = stop, IPL ROM on, `JMP $FFC0`; `$3A` / `$3B` fade in /
  out; `$3E` cold restart); lower values = songs (`$87`: world map song,
  ~60 s loop). Port 1: SFX 0 = cursor move, 1 = accept.
* Hack (`asm/title_music.asm` `sb1_*`, data from `world_map.sound`): on the
  ZONE1 map's music request Hudson's loader gets a stub at `$1100` (FLG
  `$E0`, `$F1` = `$B0`, `JMP $FFC0`) and `JMP $1100` over its `RET` at
  `$1041`; the IPL ROM gets a loader at `$0200` that takes 3 bytes per
  handshake (~1 s for the 39 KB, limited by the SPC loop) and jumps to
  `$0812`; then `$87`. The next non-SFX request sends `$37` and calls
  `$C0:0CCF` (SB5's own power-on sound init: sets `$58`, `$56`, `$03CD` /
  `$03CE` = `$FF`); the in-game SFX state `$0188-$018C` is cleared.
  Checked in Mesen: the key-on sequence and timing equal SB1's; stage
  music and in-game SFX after the map.
* World 1 stages play on Hudson's driver with SB5's stage SFX (SB1's player and enemy deaths: game_sfx). 1-1
  (stage `$0D`), 1-2 (`$11`), 1-3 (`$18`), 1-4 (`$10`) and 1-5 (`$17`) play SB1's World 1, 2, 3, 4 and 6 songs
  converted to Hudson songs (`tools/sb6/features/sb1_music.py` `STAGES`,
  see "Hudson songs"; `asm/title_music.asm` `sb1m_song`, table
  `SB1M_TABLE` = [stage, list] ... `$FF`), hooked at the start of Hudson's
  song upload `$C0:0E9C` (A = song; `PHY PHX`, then `$C0:0EA2`, ends with
  `PLX PLY RTS` at `$C0:0F10`), uploads its list instead of song 5 (SB5's
  ZONE1 samples) on that stage; the stage script loads set `$2C` + song 5
  unconditionally (`$C0:1171`) while the screen is black, so music id 6
  (`[$2C, 5, 1]`) and the start jingle (group 0 `$20`: command 2) only send
  commands. The list keeps SB5's commands 2-4 (jingles, `$3E00-$4240` with
  their samples) and makes command 1 SB1's song. Uploading it at music id 6
  instead (after the jingle) froze the game ~80 frames. SB5's percussion
  sample (directory 2) of the start jingle never sounds (silent block in
  the lists); directory 3 (other jingles' percussion) is kept when there
  is room, else it names SB1's most alike sample (1-2: SB1's kick). The
  1-1 to 1-5 play SB1's own songs converted from Mesen DSP logs of SB1 (`sb1_w<n>_song.txt`,
  `tools/sb1_song.py`; 2026-11-22: back from the MIDI versions, which stay in `sb1_w<n>m_song.txt`
  for reference); 1-7 also plays SB1's own boss song (`sb1_boss_song.txt`, the owner's choice over the
  MIDI `sb1_bossm_song.txt`); 1-6 plays a song made from khinsider's MIDI (`tools/midi_song.py`;
  `sb1_music.IMAGES` = the SB1 sound RAM of its samples). World 2's song (1-2) and the boss song (1-7)
  are too long to leave the cornered sound's part B free (`NO_PART_B`): their lists take that ARAM too, which
  is safe because gs_song = SB1M_SONG never sends B (the cornered sound plays part A only there).
  coop4_check with the driver songs: 1-1..1-5 at 52-55 fps, 1-7 at 54.
  1-6's duels (`$67`/`$69`/`$6B`) play SB1's World 5 song from a MIDI (`sb1_w5m_song.txt`, made by
  `tools/midi_song.py` from khinsider's `level.mid`: a 2-beat pickup + 20 bars looped, as the SB6 fan
  game's; each MIDI track matched to SB1's song note by note: lead = SB1 sample 01 (MIDI note - 89),
  bass = 02 (- 56), chords and track 6 = 07 (- 72), drums = 04 (38 at SB1's pitch `$0799`, 40 + 65 at
  `$0993`); every pitch is one SB1's song plays; 694 notes, 940-byte sequence, 6-7 voices, same samples
  as SB1's dump `sb1_w5_song.txt` (8 voices, a 32-bar intro and a 60-bar loop; no stage plays it now):
  `sb1_music.IMAGES`; the converter
  also takes channels 1 and 0 when a song needs them, as SB5's own songs do; at 12 units a row, `sb1_music.SONG_UNITS`: at 24 its
  4.2 ms ticks kept Hudson's driver so busy that the CPU's handshake `$C0:0E7F` waited up to ~20 ms per
  sound command, 1-6 at 47 fps with 4 players); their type 01 scripts load and play SB5's boss music (id
  `$0F` = set `$35` + song `$0E`, `FF A0 0F` while loading, `42 0F 00` after the intro): both name id 6
  now (`sb1_music.MUSIC_SCRIPTS`; a play op naming another id than the one loaded uploads it then, ~90
  frames frozen). 1-7 (`$68`) plays SB1's boss song the same way (`boss`: `sb1_boss_song.txt`, a DSP log of SB1 2-8 from its
  song command `$8A`; the MIDI version `bossm`, khinsider's `boss-battle.mid`, is kept unused; SB1 loops it over
  24.5 bars, so its sequence is cut in half bars; samples from `sb1_stage_boss.bin` = SB1 2-8's sound RAM;
  its 32 KB list is the first thing in `free_c7_sheets`, `sb1_music.LATE`). SB5's boss music (set `$35`,
  song `$0E`) is no longer played by a World 1 stage;
  SB5's ZONE1 song is no longer heard; its own samples (`$25`, `$26`) are freed (`free_dc_zone1`). The list overwrites set
  `$2C`'s sequence while `$03CE` still says `$2C` (set to `$FF`, music id 6
  would send the set again over the list): `sb1m_song` marks `SB1M_FLAG`
  and, on the next upload of song 5 for a stage without SB1 music, sends set
  `$2C` first (else that stage ran SB1's tracks over SB5's samples: random
  SPC code, a black screen after 1-2's door). SB1's sample directory is
  DSP DIR `$2300` (World 3: `$2400`). World 4's song (SB1 song `$0B`) has
  fast runs of 30 ms notes: `tools/sb1_song.py --grid 8` puts the key-ons
  that would land on their voice's previous one on an 8-step grid. SB1's per-world sound RAM images
  (`assets/sound/sb1_stage_*.bin`, Mesen snapshot at SB1's first stage
  command) stay as the source of SB1's samples and of future conversions.
* Hudson songs (measured in Mesen on SB5's driver):
  * Song table at ARAM `$3000`: word -> table of header pointers (command
    1 = entry 0). Header ops: `01 mask` + a track pointer per channel,
    `02 shift` timebase, `03 n` + n instruments `[dir, ADSR1, ADSR2,
    release GAIN]`, `04` percussion, `07 0 EVOL-L EVOL-R EDL EFB FIR EON`,
    `08 0` no velocity byte, `00` end. The release GAIN must have bit 7
    set: the key-on code (`$1E61`) reads an instrument whose byte 3 is
    below `$80` as a 2-byte record and loads garbage SRCN/ADSR.
  * Notes: `key << 4 | tie 8 | length index` (index 0: a length byte
    follows; key 0 = rest); note = 12 * octave (`D2`) + key - 1. Ops
    (table at `$17D9`, `op - $D0`): `D1` tempo, `D5` quantize (8 = full),
    `D6` instrument, `D9` volume, `DA` pan (0-30), `DD n`..`DE` repeat,
    `DF addr` call / `FF` return, `EB` loop point, `EC` jump to it, `E1`
    detune, `E7` transpose. `FE n` (sub-op table `$1839`): 3 / 4 set /
    clear bit 3 of `$AE+x` (percussion mode), 0 clears bit 7, 1 / `E6`
    clear / set the voice in mask `$8D`. These survive a new song: a track
    that does not use them must reset them (`FE 04`, `FE 01`).
  * Time: the 4 ms timer adds `$38` / 256 ticks per period;
    `$38` = t - `[$12AD + t / 10]` - (t % 10 >= 5) for `D1 t` (table `00
    02 04 05 07 09 0B 0D 0E 10 12 14 16 17 19 1B 1D 1F 21 22 24 26 28 2A
    2B 2D`), >> timebase. t = 224 -> 5.565 ms per unit. A busy driver loses
    ticks (SB1's song runs 0.1-0.9 % slow).
  * Pitch with tuning entry `04 0C 00 CE` (`$FE00 + 4 * dir`): note 24 =
    `$0430`, linear in the big-endian multiplier (bytes 0-1); fine byte
    `00` vs `CE` ~0.75 %.
  * Volume `D9 v` (0-`$50`) at full pan on one side gives S-DSP VOL
    0,0,0,1,1,1,1,1,1,1,1,2,2,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,6,6,7,7,8,8,9,9,
    10,10,11,12,13,13,14,15,16,17,18,19,20,22,23,25,26,28,29,31,33,35,37,
    39,42,44,47,50,53,56,60,63,67,71,75,80,85,90,95,101,107,113,120,127,127;
    pan p: R = VOL * PT[p] / 127, L = VOL * PT[30 - p] / 127, PT = 00 07 0D
    14 1A 21 27 2E 34 3A 40 45 4B 50 55 5A 5E 63 67 6B 6E 71 74 77 79 7B 7C
    7D 7E 7F 7F. MVOL `$60` (as SB1).
* SB1's stage songs (`tools/sb1_song.py`, from a DSP log of a .spc of
  SB1 restarted at the song: Mesen snapshot of SB1 in the stage, port 0's
  toggle bit flipped; World 1 = song `$02`, World 2 = `$04`): music on
  voices 2-7, every note ends with ADSR1 = 0 and its release GAIN (`$B4`;
  0 for the drum samples 3-5). Key-ons jitter +-11 ms around the rows on
  SB1's 12 ms timer. World 1: rows of 133.547 ms, 128 rows of intro, 512
  looped; World 2: 101.875 ms, 32 + 768. The converter regroups the notes
  into musical lines (by sample, the drums together, simultaneous notes
  split by pitch), packs lines that never overlap into at most 6 channels,
  bars used twice become subroutines, then repeated runs of bars too
  (calling the bar ones: the driver's call / loop stack is 16 bytes per
  channel, `$03AC + 16 * ch`, depth `$03A4 + ch`), runs of one bar
  `DD`/`DE`; 24, 16 or 12 units a row, whichever tempo is closest.
* Research: `tools/spc_render.py --voices all --echo` renders a DSP log
  (several logs joined with `+`); the map song capture needed the CPU
  frozen (the map lasts ~4 s in SB1) and runs of < 100 s per Mesen call.

* Super Bomberman 2's map (frames ~1170-1500 after Start at 300 and 1150):
  stars on BG1 (256x512 map repeating every 256 lines, V scroll +1 every 2
  frames), ships all OBJ (chr `$C000`, palettes 1-5; Bomberman palette 0),
  lights = CGRAM 156-158, 172-173, 220-222 cycled with a 64-frame period.

* SB1's sound RAM layout: header at `$0800` = instrument table `$2200`
  (6 words -> 16-byte records, byte 12 = sample index), directory `$2300`
  (DIR `$23`, set at `$1FA6`), SFX `$89F0`, SFX map `$A03C`, instrument map
  `$A0BC`, sample map `$A13C`. Port 1 command -> `$0202`; SFX n = sequence
  at word `$89F2 + 2*[$A03C+n]`: `8B` instrument, `86` volume L R, `89`
  ADSR2 ADSR1, `80` raw pitch, `8D` key on, `91 n` wait (~22 ms ticks), `8E`
  key off, `92` end. SFX 0/1 play on voice 0, the map song on 1-7.
* Hack (`world_map._sb1_accept`): instrument table moved to `$A200` (+
  instrument 6 = record `$A210`, sample 8), directory moved to `$A300`
  (+ entry 8 = SB6's accept recording at `$A330`), SFX 1 = one note of it.

## Super Bomberman 1's stages (reference for porting)

* Scene index `$0D10` (object at `$0D00`: `$C4:694F` `LDA $C32EEF,X`, word
  table of scene scripts in bank `$C3`, X = scene * 2): `$00-$2F` = stages
  (world * 8 + stage - 1; stage 8 = boss), `$30` battle, `$31` title,
  `$39` world map. `$C4:63A9` copies `$00A4` (the scene to play next, set by
  the map) into `$0D10` (old one to `$0D16`). Writing `$00A4` on the map
  (frame ~1100 after Start x9 from frame 300) plays any stage, boss included;
  `tools/mesen/sb1_stages.lua` does it and screenshots (output of all 48:
  `build/sb1_stages/`, README there lists themes / enemies).
* Stage grid: `$C4:7B33` unpacks the layout from the scene script pointer
  `[$53]` to `$7E:4800` (cells) / `$7E:4A00`, then 13 rows x 17 into
  `$0916+` (collision, 2 bytes per cell, row stride `$40`) and `$04F4`/`$0514`.
* Animated BG tiles: 6-4's hard block light = tiles `$14`/`$15` (BG1 chars
  at VRAM 0) rewritten in VRAM, off 16 frames / lit 32 (no CGRAM change).
* Music (port 0, value & `$7F`; bit 7 toggles per command): world 1 `$02`,
  2 `$04`, 3 `$06`, 4 `$0B`, 5 `$14`, 6 `$08`. Boss stages send `$3E` (cold
  restart, new upload) and then `$0A` (1-8, 2-8), `$17` (3-8), `$18` (4-8),
  `$19` (5-8), `$1A` (6-8) from the uploaded set.

## Super Bomberman 2's sound driver (ZONE2 map music)

* Cold start `$0800`; ready = ports 2/3 `$AA`/`$AA`. Port 0: values
  1-`$40` = song value-1 (map: 2), `$41+` = SFX (move `$51`, accept `$52`);
  a command is new when it differs from the last, echoed xor `$80`. Port 1
  command 6 = FLG `$E0`, `JMP $FFC0`; SB2 turns the IPL ROM off (`$F1` =
  `$33`), so the hack uploads a copy of the IPL ROM to RAM `$FFC0` (with the
  `$FF00-$FF38` PCALL routines). Image: ARAM `$0800-$E6DF` taken on the map
  (`tools/extract_world_map.py zone2`, `tools/mesen/sb2_world_map.lua`).
* Hack: `asm/title_music.asm` `fd_*` handles both foreign drivers through a
  table per driver (`world_map.sound`): upload list, image parts, ready
  values, song, echo, SFX. A zone change switches drivers in `map_music`
  (SB1 <-> SB2 directly through the IPL ROM, ~1-1.5 s; back to Hudson's via
  `$C0:0CCF` and SB5's map song request). Accept (SFX 4, a stage is
  chosen): on ZONE1 SB1's own SFX 1, which the build makes play SB6's
  recording (below), so the map song goes on; on ZONE2 it uploads "driver 3" (`ACCEPT` in `world_map.sound`, ~4 KB,
  ~7 frames): a program at `$0800` keys SB6's accept recording on voice 0
  (directory `$0900`), sets ports 2/3 = `$53`/`$36` and jumps to the IPL ROM;
  the voice plays on until the stage's set request brings Hudson's driver
  back (`$C0:0CCF`). Reloading Hudson's driver there instead blocks ~2 s and
  its SFX 4 does not sound before a set/song is loaded. Move stays the
  foreign driver's own SFX.

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
  gives them a free slot 4-7 back every 16 frames, and saves that slot's blink backup (`$C1:0015`):
  the death / blink restore `$C1:0035` copies it back, and without it a P3/P4 that reclaimed slot 6/7
  (1-2: its 3 enemy palettes take 3-5) died black. A one-slot request whose mask leaves out a free slot 3
  (the exit portal asks for `$30` = slots 4/5, P3/P4's) gets slot 3 first (`c0_palfail`): P3 kept P1's colors
  for ~20 frames when 1-1's portal appeared.
* `$C3:46CC` (distances from enemy X to seat Y into the `$0110+` arrays, 4 seats x every enemy x every
  frame) -> `c3_near`: while `$7F:F76F` = 1 a seat 16 px or more away on either axis keeps `$FF`. Set
  around `$C3:4B7B` by the SB1 enemies (`sb1w`) and by SB5's walker `$C3:4B5A` (`c3_walk`), whose moves
  (`$C3:4DA2`, `$C3:4610`) never read the arrays; only the contact test `$C3:47C9` (< 8 px) does. The
  chasers' nearest-seat routine `$C3:4641` (callers `$C3:0DAB` .. `$C3:41CA`) is never under the flag.
  1-2 with 4 players dropping bombs: 35 -> 50-60 fps.
* `$C3:475C` (clears the 24 bytes of seat distances at `$0110`, every enemy every frame) is unrolled
  in co-op's `c3_fill`. `$C5:060E` is not a
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
  the highest static page written; at count 32 of `$0154` (it runs once the
  start blink is over; the static loads end by count 2-6) `e4_tick` frees
  every `$7E` page above it and sets `$1D10` = 15. The lent pages are marked
  used (`$7E`) in SB5's OBJ VRAM map `$7E:2FAA` (16 columns per page, `$FF`
  free, first fit from `$0AE8` by `$C0:1A3C`, freed by owner through
  `$C0:196D` when an enemy kind's last object goes), so no later load lands
  on them. The exit portal (created by `$C5:3B60`, 38 columns in one run)
  fits in the columns the dead enemies free in 1-2 to 1-5; in 1-1 they free
  only 2 pages, so 1-1 (and any stage not in `lend_w1`) keeps the first 3
  free pages above the static ones for it (before: it was loaded at
  `$7400-$79FF`, over P3's page, ~60 frames of garbage).
* OBJ page allocator in co-op (`asm/coop.asm`): SB5's rule (`$C5:6AF5`) is a
  double buffer: an object gets a free page, its old one becomes `$7F` and
  is freed at the next upload, so the page on screen is never written. With
  four bombers no `$FF` page is left: `c5_alloc` takes a `$7F` page too, and
  only with neither reloads the object's own page. SB5 queues a walking
  bomber's strip again every frame (`$C4:3A27` -> `$C5:6A6B`) and the NMI
  sends one 1 KB strip per frame (`$C5:6AAF`, round robin from `$1CFE`):
  `c5_dedupe` (`$C5:6A72`) does not queue a strip already in the object's
  page (`c5_record` keeps owner / sheet `$1CCC` / row `$1CEA` per page at
  `$7F:FE80`) and sets its animation at once, as the upload would
  (`$C5:6B56`: `$1CF4` bit 7 -> `$C0:11DD` keep the frame, else `$C0:11EC`).
  Animation 0 requests (getting on a Louie) are never served by SB5 (`$1CE0`
  = 0 is a free entry) and are left alone. With every page taken (4 bombers
  + 4 Louies) `c5_urgent` (`$C5:6AA7`) puts one in-place strip per frame
  first (`$1CFE`) and sets its tile base (`$073F` = (page * 2 - row) << 4,
  sign-extended, as `$C5:6B36`) and animation before the OAM is built
  (in a frame the strip requests run before the OAM builder), and
  `c5_service` keeps it in that page even if one was freed since.
  A kept strip whose animation is the one shown and kept going (`$AE` bit 7)
  calls nothing: `$C0:11DD` resolves the mapping again, and for a streamed
  character queues its pose again; with 4 bombers walking every frame 1-3
  (chameleons, Louies, characters 3/4/6/5) fell to 34 fps (now 51-55).
  Measured (4 bombers walking, 1-1): VRAM bytes per NMI 2052 -> 1047 on
  average, last DMA of the NMI ending at line 253 -> 238 on average, worst
  261 -> 258 (vblank ends at 261).
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
  3-20. Louies: `$C4:5442`, table `$80:C415`. In the hack every character's
  `[sheet, row]` table (`$80:BB66` + 2 * char) names SB6 sheets only, and
  sheets 1-20 (`$C7:4000-$C9:7FFF`) are freed (`bombers.free_stock_sheets`).
  Boss rivals (`$C4:3C60`, tables `$C0:B9A5`) use the same per-character
  tables.
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
  is copied to `$F0` with new sheets from id 97 (`$C5:6B86`, `$C5:6B8C`, its
  only reader; the stock table `$85:E22D-$85:EB44` is then freed;
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
* Bomber animations seen: `$15` idle, `$47` stage start, `$21` cornered
  (a bomb and no way out; set by `JSL $C0:11EC` with A = `$21`, e.g.
  `$C0:3013`, `$C1:1099`, `$C3:1485`), `$16` death. At a script loop point the
  mapping resolver `$C0:1289` runs once with a stray id before the real pose
  (same frame): hooks on it must not act on that first call.
* Stage items: list per campaign stage at `$C4:E5C7` (`[item, count, count
  with two players]`, 0 ends a stage), spread by `$C5:404C`; `$C5:40DE` (A =
  item) hides one item in a random soft block. Ids:
  `$0C` power glove, `$11` boxing glove, `$15` egg. Test items:
  `TEST_ITEMS` in tools/sb6/features/louies.py.
* Power Glove lift: `$C5:2395` (bomb under the bomber, `$0E90` |= `$40`,
  carried) sets the bomb's height `$0680,Y` from `$C5:2403`: seats < 5 not on
  a Louie read `$C5:242C[$16C2]` (one byte per character 0-9, stock
  `13 0B 18 18 14 1C 12 12 12 12`); on a Louie `$12` (`$1A` character 5),
  others `$1A`. While carried `$C5:20B9` copies the owner's x/y (y + 1) into
  the bomb. The build sets each inserted character's byte to Bomberman's +
  (his head top - the character's) over the carry poses `$2F-$3A`
  (`tools/sb6/features/bombers.py`, `_carry_top`).
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
  archives `$01` (`$C7:4000`, `$2000`) and `$02` (`$C7:6000`, `$1800`), no
  longer drawn and freed: edit `assets/bombers` instead of `sheet.png`; bomber
  pages hold (archive, half) per animation (`$1CCC/$1CEA`, upload `$C5:6B77`).
  Louies `$15-$22` (table `$C0:C415`). Frame pieces: count + 7 bytes
  (dx, dy, tile, attr; attr bit 0 = 16x16, `$40/$80` flips); sets `$C0:16CC`,
  animations `$C0:171D` (bomber object set `$10`).
* Bomber palettes: set 0 (`$81:8000`), id = `$C0:BB4E[char] + color`;
  Bomberman ids 1-7, `[dest $80, count 9, colors]`.

## Gameplay ids measured for the QA suites (`tools/qa_check.py`, Mesen, 1-1 with 4 players)

* Bomber animations (`$079F+obj`), d = 0 right, 1 down, 2 left, 3 up: walk `1+d`, stand `$46+d`, punch
  (boxing glove, Y) `$27+d`, lift (power glove, A held on the bomb) `$2C`, carry walk `$2F+d`, carry stand
  `$4A+d`, throw `$33+d`, idle `$15`, death `$16`, jump onto / thrown off a Louie `$17-$1A` (by facing),
  riding `$05-$14` (four per Louie kind: `$05-$08`, `$09-$0C`, `$0D-$10`, `$11-$14`), cornered `$21`,
  victory `$20`, time up `$1F` (all seats; then they die and the stage restarts). Louie actors = seat +
  `$0128` (19-22 with 4 players): their own walk / idle ids by kind (e.g. `$23-$26`, `$3D-$40`).
* Idle: `$17E2+seat` counts frames standing (input resets it); SB5 sets `$15` when it runs out (~210
  frames). 1-7's `start_up` (asm/world1.asm) zeroes it while the intro holds the pads: seat 2 comes out
  ~40 frames before the others and showed `$15` for 4 frames at stage frame ~412.
* Sounds (command sent by `$C0:0E7F`): bomb `$26`, kick `$27`, punch `$28`, bounce `$29` (once per
  landing, again on each taken cell it hops over), explosion `$2A` + fire range (request group 2 id `$0A`
  + range), pierce bomb's explosion `$34` + range (id `$14` + range), item `$3F`, lift = group 3 id 2
  (stream) then `$50`, Louie cry `$48` + kind (id `$28` + n), Louie hit `$42`, time up `$58` + `$55`,
  stage clear = request (0, `$21`) (command 3).
* Abilities `$7E:4ED5+seat`: `01` remote (B), `02` kick (item `$0B`), `04` power glove (item `$0C`),
  `08` boxing glove (item `$11`), `10` pierce (item `$0D`), `20` mine (item `$0F`), `40` item `$10`
  (later fuse). Items `05` / `06` clear `$167A` bits 6 / 5. Fire range `$17CA+seat`.
* Time: `$0E1E` minutes, `$0E1D` seconds, `$0E1C` frames.
* 1-6's Golden drops the kick at its cell 60 frames after its death (`$C4:3E10` -> `$C5:4557`); a bomb of
  its own going off there 6 frames later burnt it in the QA run (as any item in a flame).

## Known 4-player failures

Torn bomber poses (fixed): with 4 players some frames showed a bomber with tiles of another pose (walking
streamed characters 17-34 of 84 frames, Bomberman 2-3; lift / throw starts; ~40 frames when 1-1's exit portal
appeared; getting on / thrown off Louies). Measured causes: no free OBJ page with 4 bombers, so SB5's strip
upload rewrote the page on screen (`c5_alloc` took its own page); the portal loaded over P3's lent page; with
4 Louies too every page is taken. See "Co-op pages" / "OBJ page allocator in co-op" above.
`tools/qa_check.py anims` checks every frame; a bomber at the top edge of the screen (SB5 hides the pieces
above line 0, as with one player) is accepted when what is left is part of a pose.

Start safety (`tools/coop4_check.py` spawn_safety) passes on every World 1 stage: SB1 enemy starts next to the
lower corners were moved (1-2 spring (13,9) -> (11,7); 1-3 chameleons (13,8), (1,8), (11,11) -> (11,7), (3,7),
(7,11); 1-4 UFOs (3,9), (11,11) -> (5,7), (7,11); 1-4's horned robots at (7,3), (9,9)). 1-4 leaves out the
UFO at (5,7): with SB1 4-4's 4 UFOs, its bomb robot and the 2 horned robots (7 enemies) 4 players measured
45-49 fps; with 3 UFOs 51-60.

1-3's chameleons are created by number of players: `coop.CHAMELEONS` (by roster `$012A`: 2 = 1-2 players
-> 7, 3 -> 6, 4 -> 5), `c3_spawn` at `$C3:0452` (the enemy creation `$C3:0450`, A = type) -> `e4_spawn`: a
type 05 in stage `$18` past the count fails as with no free actor (`$C3:0512`, not counted in `$1D50`).
P3/P4 join `$1D25` only after the spawns. Measured (4 players, 6 chameleons): 50-52 fps; 7 with 3: 47.

`python tools/coop4_check.py` (4 seats, nobody dies, everyone walks and drops a bomb a second; 2026-11-21):
every World 1 stage passes (worst second 52-57 fps; 1-4 53 with one enemy OBJ palette).

| Stage | Worst | Why | Proposal |
|---|---|---|---|
| (none) | | | |

