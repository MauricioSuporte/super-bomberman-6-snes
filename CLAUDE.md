# CLAUDE.md

Super Bomberman 6: SNES ROM hack of *Super Bomberman 5 (USA)*. See README.md
(Portuguese, for the owner) and docs/.

## Invariants

* Output is always `python tools/build.py` from the untouched base ROM
  (sha1 checked) + this repo. Never hand-edit a ROM; never commit ROMs.
* The ROM stays 4 MB HiROM (repro carts / real hardware). Anything that only
  works in emulators is a bug.
* Change original bytes only with `rb.patch(addr, expected, new, label)`.
* New data/code only with `rb.alloc(region, data, label)` in regions declared
  in `tools/build.py` (verified `$FF`). Bank-bound tables: palettes in `$81`
  (`bank81`), archive tables in `$E3` (`e3_tables`).
* asar output is taken back by diff (`tools/sb6/asar.py`) and must stay inside
  its allocation; symbols come from `print "SYM name ", hex(label)` lines.
* New WRAM/ARAM usage goes in docs/FREE_SPACE.md; new findings in
  docs/ROM_MAP.md.
* When SB6 replaces an SB5 resource (graphics, palette, arrangement, song,
  sample, table), free the old data in the same change: prove nothing reads
  it (every set's tables, script ops, native callers, sound lists), list it
  in the feature's `OLD_DATA` and call `rb.free_old` (CRC32 check, `$FF`,
  region), then run `tools/mesen/loads.lua` with `LOADS_WATCH` = the freed
  ranges (0 reads). In doubt, keep it and note why under "Not freed" in
  docs/FREE_SPACE.md.

## Layout

* `tools/sb6/features/<feature>.py` — one feature per module, `apply(rb, …)`.
* Native code called from a script: op `FF 1A nn` with nn >= `$F0`
  (`pick_op` in `asm/picker.asm`, `$F0-$F4` its own); add new values there (`$F5` is the
  world map's, `$F8-$FB` the animated title's). Scripts cannot spin in a loop (SB5's `FD 0E n 00 00` sleeps n frames, used by
  `features/options.py`): a native op that must wait puts
  its task to sleep (`title_op` `.again`, docs/ROM_MAP.md "Script tasks").
* Title scene (BG1/BG2): `features/title_anim.py` builds pictures, palettes,
  tile slots and per-frame job tables from `assets/title/layout.json`
  (positions and timings copied from the Unity scene); `asm/title_anim.asm`
  plays them from the NMI. `simulate()` replays the tables on a software
  VRAM at build time; new title animation goes through jobs, not arrangements.
  The menu cursor (`assets/title/Cursor.png`: heads, faces) is SB5's sprite 0
  with its tiles and colors rewritten by `cursor` in the same NMI player
  (`cursor_tables` in `features/title.py` holds the Unity sequences).
* `asm/*.asm` 65816, `asm/spc/*.asm` SPC700 (asar 1.91, `asar 1.90` mode).
* Shared: `rombuild.py` (patch/alloc/map), `lz.py` (SB5 compression),
  `snesgfx.py` (4bpp + palettes), `compose.py` (Unity title layout),
  `brr.py` (BRR codec), `romlib.py`.
* Player bomber: `assets/bombers/bomber.png` is a pose sheet (one 64x64 cell
  per pose, `tools/bomber_sheet.py export|check`); `bomber.py` cuts it into
  pieces/strips at build time. Sprite mappings and animation scripts
  (`assets/bombers/bomber_anims.txt`: pose order, frames, loop point) go in
  `objmap` (bank `$B3`), never in a `$C0-$FF` bank.
* Characters 1-9 (object type `$10 + n`, own mapping/script tables) are laid
  out like Bomberman: `char<n>_sb6.png` = bomber_sb6.png's layout, colors and
  sequences (`bomber_sheet.py template`), `char<n>_pallete.png` =
  BombermanPallete.png's format, `char<n>_anims.txt` overrides
  bomber_anims.txt per animation. Every character with a sheet is inserted
  (in game and in the picker grid), even one still equal to Bomberman's
  (then it costs only its tables); animations equal to his reuse his `[sheet, row]` and pieces,
  edited ones get new tiles. Palettes equal to his share his ids `$5A + n`.
  Animations over 32 tiles are streamed pose by pose (<= 16 tiles each,
  double-buffered page, `bomber_stream` / `stream_nmi` in asm/bombers.asm).
* Title OPTIONS: `features/options.py` turns it into a title submenu (DISCORD ->
  QR code from `assets/options/discord_qr.png`, BG3 set 5 arrangements 6-7);
  new options go there (menu `$1036` 3, QR/modal 4). SB5's Options, Sound
  Test and Password screens are freed (modes `$0B`/7 lead to the title).
* Character select (Normal Game): `features/picker.py` + `asm/picker.asm`
  redraw SB5's Battle picker like the SB6 fan game's SkinSelect: SB5's
  script sets the screen up, then its task sleeps in `pk_loop` while
  `pick_tick` (logic, OAM) and `pick_nmi` (VRAM) run ours. Grid = the
  columns of `assets/picker/CharacterSelectPortrait.png`; one seat chooses
  at a time; top row = animations 02 / 20 of each character (<= 8 16x16
  sprites per pose). State in `$7F:FC00` (docs/FREE_SPACE.md).
* Bomber colors: every column of `BombermanPallete.png` after the first is
  palette id `$5A + n` of set 0 (`OWN_ID`, `pal_lookup`); columns 1-6 also
  replace the stock ids 1-6. A `char<n>_pallete.png` whose first column is
  not Bomberman's (e.g. 44-column pictures with extra rows) means the sheet
  is painted with those key colors: own 15-color layout (`own_layout` in
  `sb6/bomber.py`; over 15 colors the least used entries are merged into
  the closest, listed by the build), shared by characters with the same
  picture. Cells still equal to bomber_sb6.png are drawn with the nearest
  colors.
* Items, explosions, bombs, eggs drawn like SB6 (Unity sheets `assets/items/sb6_items_sheet.png` =
  Itens.png, `assets/eggs`): `features/items.py` (icons in palette 1, the border's blink: set 0 archive `$5E`,
  script at `$85:EDA1`; Full Fire without border), `features/explosions.py` (flame tiles `$010-$07F` from
  Itens.png's Explosion* cells, fire in palette 2 entries 8-13 from set 6 palette 2; a pierce bomb's flames are
  the normal ones: no BG palette is free, palette 0 entries 8-15 are the HUD's / pause's BG3 colors),
  `features/bombs.py` (OBJ archive `$23`, blues in palette `$58` entries 1-4, gray 9, outline 14; a pierce
  flame never covers a burning soft block: `explosions.SKIP_CODE`), `features/eggs.py` (sheet `$1A`
  columns 6-15, SB6's idle loop in own tables via `asm/bombers.asm`, palette id `$51`).
  Checked by `qa_check.py fx` (also the HUD colors and the pause menu on every stage).
* Stage HUD (Normal Game): `features/hud.py` + `asm/hud.asm` draw SB6 Unity's NormalGameHud (`assets/hud`)
  on BG2 / BG1 (seats 2-3, 4 pixels right) tiles `$D0-$F9` / BG3 tiles `$42-$7F` in hidden map rows that SB5's
  stage IRQ scrolls to (no clock, no score: the clock task stops); dividers, PUSH START blinking for a seat out
  of the stage; its last lines and the lives tab are in the field's BG3 rows 2-4 (heart over the backdrop through
  window 2: `hud_l21`, a line-31 IRQ in `c0_hi`; IRQ handlers run in bank `$80`, so above `$8000`); heads = the
  picker's character / color (`assets/hud/portraits`, drawn at the stage load; CGRAM 15 = a purple for them in the Normal Game); `hud_tick` checks one seat every
  4th frame, queues only changes and redraws every row after a pause. Battle keeps SB5's HUD. Checked by
  `qa_check.py hud` (screen = `hud.render()` of the seats' RAM and picks on every stage, during / after a pause).
* OBJ palettes: a bomber owns all 16 colors of its slot. Louies and eggs
  live in halves of a Louie palette (`asm/louies.asm`, at most two Louie
  colors at once); new OBJ sheets are registered in `objsheets.ObjSheets`.

## Testing

**After changing the ROM run `python tools/qa_check.py`** (`all` adds coop4 + flames, `--list`, `-v`): the
regression suites in Mesen headless, no AI tokens (tools/qa/suites.py: picker colors, every animation in 4
directions with a frame-by-frame pose check, SFX ids, music, every stage's 4 starts (also with P3/P4 out of the
stage, joining with Start: `Fixture.absent`), 1-6 / 1-7 flows and their
intro holds on foot and on Louies (`Fixture.mounts`: Louies kept from the stage before), 1-3's chameleons drawn
every frame; every
scenario fails if SB5's static graphics queue writes a page a bomber / Louie / egg owns). Fixtures (4 players, picks,
stage) are booted once per ROM sha1 and kept as savestates (`build/qa/states`); scenarios load them
(`tools/mesen/qa.lua` steps: pad, poke, place, item, burn, blast, door, louie_type...). A new feature gets
a scenario + checks there; ids and addresses it relies on are listed at the top of tools/qa/suites.py.

**SB6 is played as the Normal Game with 4 players and Louies: every stage has
to stay playable that way.** OBJ palette slots: 0 stage, P1-P4 one each, one
Louie palette (two Louie colors at once, `asm/louies.asm`) -> at most 2 slots
for a stage's enemies (kinds can share one, `pal` in `sb1_enemies.KINDS`).
Per-frame cost matters as much (4 bombers, their bombs, the enemies: 16x16
pieces, no per-frame loops over every actor). After changing a stage, its
enemies or per-frame code, run `python tools/coop4_check.py [stage ...]`
(Mesen, 4 seats, nobody dies, everyone bombs; fails under 50 fps, without
Louie colors, with P3/P4 on borrowed colors, or with an unsafe start). A stage that cannot pass is
not shipped quietly: propose a change to the owner (fewer enemies, shared
palettes, simpler poses) and list it under "Known 4-player failures" in
docs/ROM_MAP.md.

**Every seat's start must be safe (all 4 corners, every stage).** No seat may
start where it has to die to open a way, or next to an enemy. The check
fails a seat that, with every random soft block it could get, cannot drop a
bomb and hide from it (any fire range) within 5 + 5 cells, or that has an
enemy starting fewer than 6 walking cells away (soft blocks ignored). A seat out of the stage (it joins with Start)
is judged at its spawn cell (`$4E8D`/`$4EA5`), which must be its corner.
`e4_reserve` (asm/coop.asm) keeps a bomb-and-hide run clear for each seat
when the soft blocks are scattered; enemy starts go where the check allows
(`sb1_enemies.STAGE_ENEMIES`). Never ship a stage failing this.

**Explosions must look like 1-1's on every stage.** After changing a stage's
tiles, palettes, BG layers, scripts or `asm/stage_anim.asm`, run
`python tools/flame_check.py [stage ...]` (Mesen, 4 seats dropping bombs):
every flame tile on screen must keep SB6's fire pixels and colors
(`features/explosions.py` `tiles()`, a pierce bomb's too), show the place's own floor around the
fire (see-through on BG1 over a BG2 field; an arena drawing flames on its
field layer may show its most common floor), scroll with the field and sit
on flame cells. A new stage draws its flames on BG1 over the field (`$0F61`
= 1, SB5's see-through set) unless its field is BG1.

New/edited characters: follow `.claude/skills/sb6-character/SKILL.md`
(walk test: `tools/mesen/walk_capture.lua` + `tools/walk_check.py`).

Mesen 2 headless: `Mesen.exe --testrunner ROM script.lua` (portable
`settings.json` with `AllowIoOsAccess` and SNES controllers on ports 1-2).
Lua: `emu.read(a, emu.memType.snesDebug | spcRam | spcDspRegisters)`,
`emu.getState()["spc.pc"]`, write callbacks on WRAM use bank-00 addresses,
input via `emu.setInput` in the `inputPolled` event. The boot logo (mode 1)
shows at frames ~56-410, then the hack goes straight to the title (mode 2,
SB5's intro is skipped; the title's own intro runs at frames ~450-670,
music and pads from ~730); an attract demo starts ~36 s later. Old scripts that
wait for frame ~5650 still work (the title is already up). Check: title music streams (`$0100` = 1, SPC PC in `$70xx`), OPTIONS opens
the DISCORD submenu / QR on the title (`features/options.py`; SB5's Options
and Password screens are gone), Normal Game switches to the save menu music (`$010A` = 2,
voice 7 pitch `$0600`, through the picker), the stage releases it (Hudson PC
`$08xx`, stage music).

The testrunner ignores the multitap setting (every port lands on P1), so
P3/P4 input is injected by Lua with `emu.write` to `$2C/$31/$36+seat` from an
exec callback at `$C0:0AF9` (end of the pad reader).

## Sound gotchas

* Hudson's `$10` loader returns instead of jumping; the stream driver is
  started by patching its `RET` at `$1041` and returns through it.
* While streaming, every non-SFX request must release first; SFX go to the stream driver (move/accept/back) or are dropped.
* `$03CD` (song in ARAM) is set to `$FF` when the ring overwrites song 1.
* Menu SFX 1/4/3 (move/accept/back) are recordings (`assets/sound/menu_*.wav`)
  kept as samples at ARAM `$B900-$DCFF`; Hudson's definitions of those SFX
  are swapped in and out by the song/set upload hooks (`song_hook`,
  `set_hook` in `asm/title_music.asm`), the stream driver plays the same
  samples from scripts. A song whose samples or echo buffer reach that
  area gets SB5's beeps back; changing the notes in `MENU_SFX` means
  reading the new pitch from voice 0 in Mesen (`SFX_PITCH`).
* In-game SFX (cornered, SB1's player and enemy deaths: `features/game_sfx.py`,
  `asm/game_sfx.asm`; every other stage sound is SB5's) are Hudson SFX `$5E-$60` whose data sits in ARAM
  `$5900-$657F` (SB5's group-3 voice buffer) + a part below the echo buffer;
  title_music's sound/set/song/loop hooks call `gs_*`. Only send them while
  `$0188` = 1 (R in ARAM). Research: `tools/spc_render.py` turns a Mesen log
  of S-DSP writes into a WAV.
* Stage music is Hudson's (World 1 included). 1-1 to 1-5 and 1-7 play SB1's World 1-4 and 6 songs and its boss song
  converted to Hudson songs (`features/sb1_music.py` `STAGES`, from `assets/sound/sb1_w<n>_song.txt`,
  made by `tools/sb1_song.py` from a Mesen DSP log of SB1; 1-6 plays `sb1_w5m_song.txt`, made by `tools/midi_song.py` from khinsider's MIDI, with SB1's samples; the other `*m_song.txt` MIDI versions are kept unused): `sb1m_song` in
  `asm/title_music.asm` uploads it instead of SB5's ZONE1 samples while the
  stage loads (never while a stage runs: an upload freezes the game), with
  SB5's jingles kept as commands 2-4; Hudson still counts set `$2C` as loaded, so the
  next stage's ZONE1 sequence is sent again by `sb1m_song` (`SB1M_FLAG`). Hudson instruments need release GAIN bit 7 set, and a
  track must reset channel state left by the previous song (`FE 04`, `FE 01`).
* The title intro's sounds (pan, drops) are one pre-mixed stream in bank
  `$FC`; `PAN_LEAD_FRAMES` is the measured wait from its start to the pan.
  Mesen `spc.cycle` runs at 2.048 MHz.
