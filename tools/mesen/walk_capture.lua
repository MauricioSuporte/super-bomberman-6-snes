-- Walk test of a bomber: picks a character with PLAN (picker_nav.lua), waits T0 frames in stage 1-1 and walks
-- right, down, left, up twice (100 frames each), dumping per frame the bomber object, the OAM and VRAM
-- $6000-$67FF (OBJ pages 0-4) into WALK_OUT. Analyse with `python tools/walk_check.py WALK_OUT <char>`.
-- env: SB6_LUA (this folder, default D:/super-bomberman-6-snes/tools/mesen), WALK_OUT, T0 (default 900),
-- PLAN, STAGE_WAIT (> T0 + 800, e.g. 5000).
local DIR = os.getenv("SB6_LUA") or "D:/super-bomberman-6-snes/tools/mesen"
dofile(DIR .. "/picker_nav.lua")
local T0 = tonumber(os.getenv("T0") or "900")
local n = 0 local st = nil
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local OUT = io.open(os.getenv("WALK_OUT") or "walk.bin", "wb")
local DIRS = {"right", "down", "left", "up", "right", "down", "left", "up"}
emu.addEventCallback(function()
  if st and n-st >= T0 and n-st < T0+8*100 then
    local t = {} t[DIRS[math.floor((n-st-T0)/100)+1]] = true emu.setInput(t, 0)
  end
end, emu.eventType.inputPolled)
emu.addEventCallback(function() n = n+1
  local m = r(0x1031)
  if not st and m >= 0x0D and m < 0x74 then st = n end
  if st and n-st >= T0-10 and n-st < T0+8*100 then
    local obj = r(0x17FA)
    local page = 255 for i = 0, 15 do if r(0x1D00+i) == obj then page = i end end
    local t = {string.char(obj, page, r(0x049F+obj), r(0x079F+obj), r(0x073F+obj), r(0x0740+obj))}
    for i = 0, 543 do t[#t+1] = string.char(emu.read(i, emu.memType.snesSpriteRam)) end
    for i = 0, 5*1024-1 do t[#t+1] = string.char(emu.read(0xC000+i, emu.memType.snesVideoRam)) end
    OUT:write(table.concat(t))
  end
  if st and n-st == T0+8*100 then OUT:close() emu.stop(0) end
end, emu.eventType.endFrame)
