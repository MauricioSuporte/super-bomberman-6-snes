-- Super Bomberman (USA) stage capture (reference for porting SB1 stages, docs/ROM_MAP.md "Super Bomberman 1's stages").
--   STAGE=<hex 00-2F> SHOT_DIR=<dir with trailing /> Mesen.exe --testrunner "Super Bomberman (USA).sfc" tools/mesen/sb1_stages.lua
-- Normal Game via Start presses; on the world map (frame 1100) writes $00A4 (scene to play: world*8 + stage-1)
-- = STAGE; screenshots <STAGE>_<frame>.png at 1400 (intro "w - s START!"), 1700, 2000, 2600; logs APU port writes
-- (<STAGE>_apu.txt, frames 1100-2600) and the object table $0D00 + 64*i at frame 2000 (<STAGE>_obj.txt).
local OUT = os.getenv("SHOT_DIR") or "./"
local TARGET = tonumber(os.getenv("STAGE") or "0", 16)
local f = 0 local plan = {}
for k = 0, 8 do for i = 0, 3 do plan[300 + k * 60 + i] = "start" end end
emu.addEventCallback(function() local b = plan[f] if b then local t = {} t[b] = true emu.setInput(t, 0) end end, emu.eventType.inputPolled)
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
local function save(name, data) local h = io.open(OUT .. name, "wb") h:write(data) h:close() end
emu.addEventCallback(function() f = f + 1
  if f == 1100 then emu.write(0xA4, TARGET, emu.memType.snesWorkRam) end
  for _, t in ipairs(SH) do if f == t then save(string.format("%02X_%d.png", TARGET, t), emu.takeScreenshot()) end end
  if f == 2000 then save(string.format("%02X_obj.txt", TARGET), objs()) end
  if f == 2601 then save(string.format("%02X_apu.txt", TARGET), table.concat(apu, NL)) emu.stop(0) end
end, emu.eventType.endFrame)
