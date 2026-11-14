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

## Layout

* `tools/sb6/features/<feature>.py` — one feature per module, `apply(rb, …)`.
* Native code called from a script: op `FF 1A nn` with nn >= `$F0`
  (`pick_op` in `asm/picker.asm`); add new values there.
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
  bomber_anims.txt per animation. Inserted only when something differs from
  Bomberman's; animations equal to his reuse his `[sheet, row]` and pieces,
  edited ones get new tiles. Palettes equal to his share his ids `$80 + n`.
  Animations over 32 tiles are streamed pose by pose (<= 16 tiles each,
  double-buffered page, `bomber_stream` / `stream_nmi` in asm/bombers.asm).
* Bomber colors: every column of `BombermanPallete.png` after the first is
  palette id `$80 + n` of set 0 (`pal_lookup`); columns 1-6 also replace the
  stock ids 1-6.
* OBJ palettes: a bomber owns all 16 colors of its slot. Louies and eggs
  live in halves of a Louie palette (`asm/louies.asm`, at most two Louie
  colors at once); new OBJ sheets are registered in `objsheets.ObjSheets`.

## Testing

New/edited characters: follow `.claude/skills/sb6-character/SKILL.md`
(walk test: `tools/mesen/walk_capture.lua` + `tools/walk_check.py`).

Mesen 2 headless: `Mesen.exe --testrunner ROM script.lua` (portable
`settings.json` with `AllowIoOsAccess` and SNES controllers on ports 1-2).
Lua: `emu.read(a, emu.memType.snesDebug | spcRam | spcDspRegisters)`,
`emu.getState()["spc.pc"]`, write callbacks on WRAM use bank-00 addresses,
input via `emu.setInput` in the `inputPolled` event. The boot logo (mode 1)
shows at frames ~56-410, then the hack goes straight to the title (mode 2,
the intro is skipped); an attract demo starts ~36 s later. Old scripts that
wait for frame ~5650 still work (the title is already up). Check: title music streams (`$0100` = 1, SPC PC in `$70xx`), Options →
back restarts it, Normal Game releases it (Hudson PC `$08xx`, stage music).

The testrunner ignores the multitap setting (every port lands on P1), so
P3/P4 input is injected by Lua with `emu.write` to `$2C/$31/$36+seat` from an
exec callback at `$C0:0AF9` (end of the pad reader).

## Sound gotchas

* Hudson's `$10` loader returns instead of jumping; the stream driver is
  started by patching its `RET` at `$1041` and returns through it.
* While streaming, every non-SFX request must release first; SFX go to the stream driver (move/accept) or are dropped.
* `$03CD` (song in ARAM) is set to `$FF` when the ring overwrites song 1.
* Title SFX: captured once with `tools/capture_sfx.py` into
  `assets/sound/title_sfx.json`, replayed by the stream driver on voice 0.
  Mesen `spc.cycle` runs at 2.048 MHz.
