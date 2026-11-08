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
* `asm/*.asm` 65816, `asm/spc/*.asm` SPC700 (asar 1.91, `asar 1.90` mode).
* Shared: `rombuild.py` (patch/alloc/map), `lz.py` (SB5 compression),
  `snesgfx.py` (4bpp + palettes), `compose.py` (Unity title layout),
  `brr.py` (BRR codec), `romlib.py`.

## Testing

Mesen 2 headless: `Mesen.exe --testrunner ROM script.lua` (portable
`settings.json` with `AllowIoOsAccess` and SNES controllers on ports 1-2).
Lua: `emu.read(a, emu.memType.snesDebug | spcRam | spcDspRegisters)`,
`emu.getState()["spc.pc"]`, write callbacks on WRAM use bank-00 addresses,
input via `emu.setInput` in the `inputPolled` event. The title appears near
frame 5650 (intro cannot be skipped earlier); an attract demo starts ~36 s
later. Check: title music streams (`$0100` = 1, SPC PC in `$70xx`), Options →
back restarts it, Normal Game releases it (Hudson PC `$08xx`, stage music).

## Sound gotchas

* Hudson's `$10` loader returns instead of jumping; the stream driver is
  started by patching its `RET` at `$1041` and returns through it.
* While streaming, every non-SFX request must release first; SFX go to the stream driver (move/accept) or are dropped.
* `$03CD` (song in ARAM) is set to `$FF` when the ring overwrites song 1.
* Title SFX: captured once with `tools/capture_sfx.py` into
  `assets/sound/title_sfx.json`, replayed by the stream driver on voice 0.
  Mesen `spc.cycle` runs at 2.048 MHz.
