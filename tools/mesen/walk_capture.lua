-- Animation test of a bomber: picks a character with PLAN (picker_nav.lua) and plays stage 1-1, dumping per
-- frame the bomber object, the OAM and the OBJ VRAM ($6000-$7FFF) into WALK_OUT.
-- Analyse with `python tools/walk_check.py WALK_OUT <char>`.
-- TEST=walk (default): waits T0 frames, walks right, down, left, up twice (100 frames each).
-- TEST=trap: walls the start cell in ($1052 cells $12 and $21) and drops a bomb: the cornered
--   animation $21 (1 2 [ 3 4 3 5) until the blast, then the death $16 (300 frames).
-- TEST=anim ANIM=<hex>: from T0 = 420 the idle animation $15 is replaced by ANIM in the setter `JSL $C0:11EC`
--   (A = animation), so any animation can be watched standing (300 frames).
-- TEST=lift: gives the Power Glove ($7E4ED5 bit 2), drops a bomb, lifts it (A held), walks down with it
--   and stands (300 frames); screenshots WALK_OUT_lift<n>.png every 50 frames.
-- TEST=rest: walks right 24 frames, then stands (400 frames from T0 = 900): a character that walks in place
--   (bombers.WALK_AT_REST) shows its walk poses in the stand animation $46, then the idle $15.
-- env: SB6_LUA (this folder, default D:/super-bomberman-6-snes/tools/mesen), WALK_OUT, T0 (default 900),
-- PLAN, STAGE_WAIT (> T0 + 800, e.g. 5000).
local DIR = os.getenv("SB6_LUA") or "D:/super-bomberman-6-snes/tools/mesen"
dofile(DIR .. "/picker_nav.lua")
local T0 = tonumber(os.getenv("T0") or "900")
local n = 0 local st = nil
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local OUT = io.open(os.getenv("WALK_OUT") or "walk.bin", "wb")
local DIRS = {"right", "down", "left", "up", "right", "down", "left", "up"}
local TRAP = os.getenv("TEST") == "trap"
local FORCE = os.getenv("TEST") == "anim" and tonumber(os.getenv("ANIM") or "20", 16)
local LIFT = os.getenv("TEST") == "lift"
local REST = os.getenv("TEST") == "rest"
if TRAP or FORCE or LIFT then T0 = 420 end
local LEN = (TRAP or FORCE or LIFT) and 300 or REST and 400 or 8*100
if FORCE then
  emu.addMemoryCallback(function()
    local s = emu.getState()
    if st and n-st >= T0-10 and s["cpu.y"] & 0xFF == r(0x17FA) and s["cpu.a"] & 0xFF == 0x15 then
      s["cpu.a"] = (s["cpu.a"] & 0xFF00) | FORCE
      emu.setState(s)
    end
  end, emu.callbackType.exec, 0xC011EC, 0xC011EC)
end
emu.addEventCallback(function()
  if LIFT then
    local k = st and n-st-T0 or -1
    if (k >= 0 and k < 6) or (k >= 20 and k < 240) then
      local t = {a = true} if k >= 80 and k < 96 then t.down = true end emu.setInput(t, 0)
    end
  elseif TRAP then
    if st and n-st >= T0 and n-st < T0+6 then emu.setInput({a = true}, 0) end
  elseif FORCE then
  elseif REST then
    if st and n-st >= T0 and n-st < T0+24 then emu.setInput({right = true}, 0) end
  elseif st and n-st >= T0 and n-st < T0+LEN then
    local t = {} t[DIRS[math.floor((n-st-T0)/100)+1]] = true emu.setInput(t, 0)
  end
end, emu.eventType.inputPolled)
emu.addEventCallback(function() n = n+1
  local m = r(0x1031)
  if not st and m >= 0x0D and m < 0x74 then st = n end
  if TRAP and st and n-st == T0-10 then
    emu.write(0x1052+0x12, 0x30, emu.memType.snesWorkRam) emu.write(0x1052+0x21, 0x30, emu.memType.snesWorkRam)
  end
  if REST and st and n-st >= T0-10 then     -- enemies held by the stop watch (they would walk into him)
    emu.write(0x0E20, 0xFF, emu.memType.snesWorkRam) emu.write(0x0E21, 0xFF, emu.memType.snesWorkRam)
  end
  if REST and st and n-st == T0+60 and os.getenv("IDLE_AT") then   -- frames standing: the idle comes sooner
    emu.write(0x17E2, tonumber(os.getenv("IDLE_AT")), emu.memType.snesWorkRam)
  end
  if LIFT and st and n-st == T0-10 then
    emu.write(0x4ED5, emu.read(0x4ED5, emu.memType.snesWorkRam) | 4, emu.memType.snesWorkRam)
  end
  if LIFT and st and n-st > T0 and (n-st-T0) % 50 == 0 then
    local h = io.open((os.getenv("WALK_OUT") or "walk.bin"):gsub("%.bin$", "") .. "_lift" .. (n-st-T0) .. ".png", "wb")
    h:write(emu.takeScreenshot()) h:close()
  end
  if st and n-st >= T0-10 and n-st < T0+LEN then
    local obj = r(0x17FA)
    local page = 255 for i = 0, 15 do if r(0x1D00+i) == obj then page = i end end
    local t = {string.char(obj, page, r(0x049F+obj), r(0x079F+obj), r(0x073F+obj), r(0x0740+obj))}
    for i = 0, 543 do t[#t+1] = string.char(emu.read(i, emu.memType.snesSpriteRam)) end
    for i = 0, 16*1024-1 do t[#t+1] = string.char(emu.read(0xC000+i, emu.memType.snesVideoRam)) end
    OUT:write(table.concat(t))
  end
  if st and n-st == T0+LEN then OUT:close() emu.stop(0) end
end, emu.eventType.endFrame)
