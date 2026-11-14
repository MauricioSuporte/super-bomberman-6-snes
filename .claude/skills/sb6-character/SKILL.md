---
name: sb6-character
description: Add or edit a playable SB6 character (char2..char9, "chat_2 em diante") from its pose sheet char<n>_sb6.png - colors, palette, walk 12321454, big sprites (streaming), picker cell and the Mesen walk test. Use when the user asks to create/ajustar/inserir/testar um personagem, sprite sheet charN, paleta do personagem, animação de andar, or a character "não cabe".
---

# SB6 character from a pose sheet (what we learned doing char1)

Read CLAUDE.md first (invariants: build only with `python tools/build.py`,
4 MB HiROM, `rb.patch`/`rb.alloc`, document WRAM in docs/FREE_SPACE.md and
findings in docs/ROM_MAP.md). Answer the owner in Portuguese.

## Files (assets/bombers)

| File | Role |
|---|---|
| `bomber_sb6.png` + `BombermanPallete.png` | Reference: layout, colors, sequences. Everything is compared to it. |
| `bomber_anims.txt` | Sequences of every bomber (Bomberman and chars). Walk 01-04 = `8 : 1*5 2 3 2 1*5 4 5 4`. |
| `char<n>_sb6.png` | The sheet the owner paints. Same size/layout as bomber_sb6.png (2560x1024, 64x64 cells, 1st column of each block = label). |
| `char<n>_pallete.png` | BombermanPallete.png's format: column 1 = Bomberman's key colors, columns 2.. = colors chosen with L/R in the picker (all of them, not only 6). |
| `char<n>_anims.txt` | Optional: only the sequences that differ from bomber_anims.txt. Avoid it: the owner wants chars to animate like Bomberman. |
| `char<n>_sb5.png` | Cartridge art, reference only (never read by the build). |

`n` = position in the CHARACTER SELECT grid counting from Bomberman's
neighbour. Object type of char n in game = `$10 + n` (`$16C2` = n).

## Workflow

1. Start from the template (only if the sheet is not painted yet; `--force`
   overwrites the owner's work, confirm first):
   `python tools/bomber_sheet.py template <n>`
2. The owner paints `char<n>_sb6.png` **with bomber_sb6.png's colors** (palette
   shared with Bomberman unless char<n>_pallete.png differs). Cells equal to
   Bomberman's reuse his tiles; any other cell counts as an edited animation.
   A color that is not in the palette is snapped (<= distance 200) or is an
   error. If the owner re-saves with old colors, remap only those pixels.
3. `python tools/bomber_sheet.py check` - must print `char<n>: ok ...`;
   it lists the animations that go "streamed pose by pose".
4. `python tools/bomber_sheet.py labels` if sequences changed (rewrites the
   label column of every sheet).
5. `python tools/build.py` - prints `char<n>: Bomberman's layout, N animations
   redrawn ... colors (his/own palettes)`. A silent failure means a stale ROM:
   always check the `wrote ... (4194304 bytes)` line.
6. Test in Mesen (below). Then update README.md (Portuguese) if the owner's
   workflow changed.

## Rules the build applies (tools/sb6/features/bombers.py, tools/sb6/bomber.py)

* A character is inserted only when sheet, palette or sequences differ from
  Bomberman's; otherwise the cartridge art stays.
* Animations with the same pose count and cells as Bomberman's reuse his
  `[sheet, row]` and mapping blobs (no ROM cost). Edited ones get new tiles.
  An animation whose pose count differs from his also counts as edited.
* Unplayed cells (not in the sequence) are ignored.
* Palette ids: `$80 + paltab index`; a shared palette uses Bomberman's ids.
  `xlat` maps the stock ids (base + n, n < 6) for Battle and co-op defaults.
* Picker: `chpal`/`chcol` per character (first color id, color count) in
  asm/picker.asm. The grid cell sprite of the first redrawn character of row
  0 uses OBJ palette 7, tiles `$C4-$C7/$D4-$D7`, OAM 112/113
  (`XCELL_CHARS = range(1, 5)` in tools/sb6/features/picker.py). The big top
  portrait stays the cartridge's art and colors (color mod 6).

## Big characters: 32-tile limit and streaming

* Stock engine: all poses of one animation share one 1 KB strip = 32 tiles
  8x8 (2 rows of 16), DMA'd into the object's OBJ page `$6000 + $200*i`.
  Identical or mirrored pieces count once. char1's lasso made the walk
  exceed 32 tiles.
* Fix in place: an animation over 32 tiles is **streamed pose by pose**
  (`convert(..., stream=True)` -> `_stream_anim`): each pose is a block of
  <= 16 tiles (8 columns x 2 rows, max 32x32 px), stored in regions
  `stream_ec..stream_ef` (banks `$EC-$EF`, ~256 B per pose). The page
  becomes a double buffer (halves at `$073F` + 0 / + 8);
  `bomber_stream` (hooked from `bomber_map` at `$C0:12A4`) queues the new
  pose into the hidden half, `stream_nmi` (JSL at `$C0:F41D`, before
  `$C5:6AAF`) DMAs it. State at `$7F:FE00-$7F:FE57`.
* While walking the stock code reloads the animation each frame into a new
  page (pages rotate); the OAM shown uses the page allocated one NMI
  earlier. Pending DMAs are kept per half (one slot per seat lost the first
  frame of every pose change - fixed).
* Script loops (`[` in a sequence, and the end of a looping sequence): the
  interpreter resolves `$C0:1289` once with a stray id (e.g. `$04`) and then
  with the real pose, in the same frame. Each stream entry is
  `[source16, animation, columns | (bank - $EC) << 4]`; `bomber_stream`
  ignores a streamed id of another animation and a non-streamed id while
  the seat's streamed animation (`SLANIM`) is still playing. A non-streamed
  pose of another animation restores the stock `$073F` (`SSTK`) and cancels
  the pending DMAs. (Bug seen: char1's cornered animation `$21` turned into
  garbage after its first loop.)
* If a single pose needs more than 16 tiles the build names it; options:
  redraw smaller, or widen POSE_TILES (loses the double buffer / DMA time).
* Not tested yet: 2-4 players with streamed characters at once, Battle mode,
  real hardware. Say so when reporting.

## Mesen test (headless) - run it for EVERY new character

Run both tests for the new character and for Bomberman (`PLAN=a`, char 0,
regression) after each build. Check the build printed
`wrote ... (4194304 bytes)` first: `tail -1` hides asar errors and the test
then runs on a stale ROM.

Picker navigation: `tools/mesen/picker_nav.lua` (env `PLAN` = P1 buttons in
the picker: `a` = Bomberman, `right,a` = char1; other chars: move the cursor
and confirm with the `SB6_OUT_pick1_*.png` screenshots; `r`/`l` = color).

Walk test (`TEST=walk`, default; every frame must be a complete pose,
sequence 1 2 3 2 1 4 5 4) and cornered test (`TEST=trap`: walls the start
cell in by poking `$1052` cells `$12`/`$21` with `$30` and drops a bomb ->
animation `$21` "encurralado" `1 2 [ 3 4 3 5`, then the death `$16`):

```sh
PLAN="right,a" SB6_OUT="D:/super-bomberman-6-snes/build/walk_c1" STAGE_WAIT=5000 \
WALK_OUT="D:/super-bomberman-6-snes/build/walk_c1.bin" \
  /d/sb6-tools/mesen/Mesen.exe --testrunner "build/Super Bomberman 6.sfc" tools/mesen/walk_capture.lua
python tools/walk_check.py build/walk_c1.bin 1 build/walk_c1.png
TEST=trap PLAN="right,a" SB6_OUT=".../build/trap_c1" STAGE_WAIT=5000 WALK_OUT=".../build/trap_c1.bin"   /d/sb6-tools/mesen/Mesen.exe --testrunner "build/Super Bomberman 6.sfc" tools/mesen/walk_capture.lua
python tools/walk_check.py build/trap_c1.bin 1 --anim 21
```

The capture holds the whole OBJ VRAM (`$6000-$7FFF`): a big character's
page can be past page 4 (char1 drew from tiles `$A0+`). `walk_check.py`
keeps the sprites of OBJ palette 1 (player 1) and drops enemies/bombs.
For another animation, reproduce its trigger the same way (WRAM pokes from
Lua) and pass `--anim <hex>`; a "NONE" frame = the right mapping drawn with
wrong tiles (look at it: render the frame, compare `$073F`, `$1D00` pages
and `$7F:FE00` state per frame).

`walk_check.py` rebuilds the bomber from OAM + VRAM pages 0-4 and matches it
against the sheet: expect `frames: 810 no matching pose: 0`, runs like
`01-1x.. 01-2x.. 01-3x.. 01-2x.. 01-1x.. 01-4x.. 01-5x.. 01-4x..` in all
four directions, and look at the PNG strip. Run Bomberman (`PLAN=a`, char 0)
too as a regression. The stage-start invincibility blink makes the first
frames "-" (nothing drawn): normal.

Other useful facts: the bomber object is `$17FA`; animation `$079F,Y`,
mapping `$049F,Y`, script step `$07A0,Y`; animation setter `JSL $C0:11EC`
(A = animation). Idle in stage = animation `$15`; stage start = `$47`;
cornered (bomb, no way out) = `$21`; death = `$16`. Collision map `$1052`
(16 columns, `$80` wall, `$30` soft block), player 1 cell `$16AA` (`$11` at
the start of 1-1). Test items in ZONE1-1
(eggs, power gloves): `TEST_ITEMS` in tools/sb6/features/louies.py.

## Pitfalls seen

* `rm` globs in test commands deleted scripts - name outputs distinctly.
* `SB6_OUT` + `.txt` is picker_nav's log: don't reuse that path for your own
  output.
* asar branch out of range: use `BRL`/subroutines; regions must not cross a
  bank (one region per bank).
* `PLX`/`PLA` change Z: re-test with `CMP #$00` before branching.
