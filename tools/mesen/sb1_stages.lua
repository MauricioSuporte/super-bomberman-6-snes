-- Super Bomberman (USA) stage capture (reference for porting SB1 stages, docs/ROM_MAP.md "Super Bomberman 1's stages").
--   STAGE=<hex 00-2F> SHOT_DIR=<dir with trailing /> Mesen.exe --testrunner "Super Bomberman (USA).sfc" tools/mesen/sb1_stages.lua
-- Normal Game via Start presses; on the world map (frame 1100) writes $00A4 (scene to play: world*8 + stage-1)
-- = STAGE; screenshots <STAGE>_<frame>.png at 1400 (intro "w - s START!"), 1700, 2000, 2600; logs APU port writes
-- (<STAGE>_apu.txt, frames 1100-2600) and the object table $0D00 + 64*i at frame 2000 (<STAGE>_obj.txt).
-- ARAM=1: also the sound RAM (<STAGE>_aram.bin, 64 KB) and the DSP registers (<STAGE>_dsp.bin) at frame 2300.
local OUT = os.getenv("SHOT_DIR") or "./"
local TARGET = tonumber(os.getenv("STAGE") or "0", 16)
local f = 0 local plan = {}
for k = 0, 8 do for i = 0, 3 do plan[300 + k * 60 + i] = "start" end end
emu.addEventCallback(function() local b = plan[f] if b then local t = {} for x in b:gmatch("[^+]+") do t[x] = true end emu.setInput(t, 0) end end, emu.eventType.inputPolled)
local SH = {1400, 1700, 2000, 2600}
local NL = string.char(10)
local apu = {} local last = {}
emu.addMemoryCallback(function(addr, value)
  if f >= 1100 and f < 2600 then local a = addr & 3
    if last[a] ~= value then last[a] = value apu[#apu+1] = string.format("f%d p%d=%02X", f, a, value) end end
end, emu.callbackType.write, 0x002140, 0x002143)
local function objs()
  local t = {}
  for i = 0, 0x4B do local b = 0x0D00 + i * 0x40
    local q = {} for o = 0, 0x3F do q[#q+1] = string.format("%02X", emu.read(b + o, emu.memType.snesWorkRam)) end
    t[#t+1] = string.format("%04X ", b) .. table.concat(q)
  end return table.concat(t, NL) end
local FIRSTCMD = tonumber(os.getenv("FIRSTCMD") or "", 16)
local function save(name, data) local h = io.open(OUT .. name, "wb") h:write(data) h:close() end
-- VIDEO=<frame>: VRAM, CGRAM, OAM and the last values written to $2100-$2133 (<STAGE>_vram.bin, _cgram.bin,
-- _oam.bin, _ppu.bin) at that frame
local VIDEOSFX = os.getenv("VIDEOSFX")
local VIDEO = {}
for v in string.gmatch(os.getenv("VIDEO") or "", "%d+") do VIDEO[tonumber(v)] = true end
-- MOVES="1560:right:16,1580:b:4": P1 input (frame : buttons '+' : frames)
for item in string.gmatch(os.getenv("MOVES") or "", "[^,]+") do
  local f0, b, n = item:match("(%d+):([%w+]+):(%d+)")
  for k = tonumber(f0), tonumber(f0) + tonumber(n) - 1 do plan[k] = b end
end
local ppu = {}
for i = 0, 0x33 do ppu[i] = 0 end
emu.addMemoryCallback(function(addr, value) ppu[addr & 0xFF] = value end, emu.callbackType.write, 0x002100, 0x002133)
local function video()
  local function dump(mt, n) local t = {} for i = 0, n - 1 do t[#t + 1] = string.char(emu.read(i, mt)) end return table.concat(t) end
  local sfx = VIDEOSFX and ("_" .. f) or ""
  save(string.format("%02X_vram%s.bin", TARGET, sfx), dump(emu.memType.snesVideoRam, 0x10000))
  save(string.format("%02X_cgram%s.bin", TARGET, sfx), dump(emu.memType.snesCgRam, 0x200))
  save(string.format("%02X_oam%s.bin", TARGET, sfx), dump(emu.memType.snesSpriteRam, 544))
  local t = {} for i = 0, 0x33 do t[#t + 1] = string.char(ppu[i]) end
  save(string.format("%02X_ppu%s.bin", TARGET, sfx), table.concat(t))
  save(string.format("%02X_video%s.png", TARGET, sfx), emu.takeScreenshot())
end
-- FIRSTCMD=<hex>: when the CPU writes it to port 0 (the first command after the stage's upload), the sound RAM
-- as uploaded (<STAGE>_upload.bin, 64 KB)
if FIRSTCMD then
  local done = false
  emu.addMemoryCallback(function(addr, value)
    if not done and f >= 1100 and value == FIRSTCMD then
      done = true
      local t = {} for i = 0, 0xFFFF do t[#t+1] = string.char(emu.read(i, emu.memType.spcRam)) end
      save(string.format("%02X_upload.bin", TARGET), table.concat(t))
    end
  end, emu.callbackType.write, 0x002140, 0x002140)
end
-- KONLOG=1: every key-on (S-DSP $4C) from frame 1100 with its frame (<STAGE>_kon.txt)
local kon = {}
if os.getenv("KONLOG") then
  emu.addMemoryCallback(function(addr, val)
    if f >= 1100 and emu.read(0xF2, emu.memType.spcMemory) == 0x4C and val ~= 0 then kon[#kon + 1] = string.format("%d %02X", f, val) end
  end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
end
emu.addEventCallback(function() f = f + 1
  if f == 2600 and os.getenv("KONLOG") then save(string.format("%02X_kon.txt", TARGET), table.concat(kon, NL)) end
  if f == 1100 then emu.write(0xA4, TARGET, emu.memType.snesWorkRam) end
  if VIDEO[f] then video() end
  for _, t in ipairs(SH) do if f == t then save(string.format("%02X_%d.png", TARGET, t), emu.takeScreenshot()) end end
  if f == 2000 then save(string.format("%02X_obj.txt", TARGET), objs()) end
  if os.getenv("ARAM") and f == 2300 then
    local t = {} for i = 0, 0xFFFF do t[#t+1] = string.char(emu.read(i, emu.memType.spcRam)) end
    save(string.format("%02X_aram.bin", TARGET), table.concat(t))
    t = {} for i = 0, 0x7F do t[#t+1] = string.char(emu.read(i, emu.memType.spcDspRegisters)) end
    save(string.format("%02X_dsp.bin", TARGET), table.concat(t))
  end
  if f == 2601 then save(string.format("%02X_apu.txt", TARGET), table.concat(apu, NL)) emu.stop(0) end
end, emu.eventType.endFrame)
