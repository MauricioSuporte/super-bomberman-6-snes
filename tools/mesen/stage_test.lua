-- Stage test harness: boots the hack, picks Bomberman (picker_nav.lua) and plays the first stage.
-- env:
--   OUT      output prefix (screenshots OUT_<frame>.png, log OUT.txt)
--   PATCH    ROM patches applied at power-on, "C61B48=00 01;C61B52=00" (SNES address = hex bytes)
--   SHOTS    stage frames to screenshot, "60,300,900"
--   MOVES    P1 input in the stage, "300:right:40,400:a:4" (start frame : buttons '+' : frames)
--   KILL     frame (stage-relative) at which every enemy object is removed (see kill() below)
--   POKE     "frame:addr=val,..." WRAM writes at stage frames (addr hex, bank 7E)
--   END      last stage frame (default 1500)
--   FOLLOW   1 = keep logging after the first stage (mode changes and screenshots go on, frames count from the
--            first stage)
local DIR = os.getenv("SB6_LUA") or "D:/super-bomberman-6-snes/tools/mesen"
local OUT = os.getenv("OUT") or "build/stage_test"
local NL = string.char(10)
local log = {}
local function L(s) log[#log + 1] = s end
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local function rw(a) return r(a) | (r(a + 1) << 8) end
local function shot(name) local h = io.open(OUT .. "_" .. name .. ".png", "wb") h:write(emu.takeScreenshot()) h:close() end

local function prg(a) return ((a >> 16) & 0x3F) * 0x10000 + (a & 0xFFFF) end
for item in string.gmatch(os.getenv("PATCH") or "", "[^;]+") do
  local addr, bytes = item:match("(%x+)=([%x ]+)")
  local a = prg(tonumber(addr, 16))
  for b in bytes:gmatch("%x%x") do emu.write(a, tonumber(b, 16), emu.memType.snesPrgRom) a = a + 1 end
end

local SHOTS = {}
for v in string.gmatch(os.getenv("SHOTS") or "", "%d+") do SHOTS[tonumber(v)] = true end
local DUMPS = {}   -- DUMP="300,600": WRAM ($7E/$7F), VRAM and CGRAM dumps OUT_wram/_vram/_cgram<frame>.bin
for v in string.gmatch(os.getenv("DUMP") or "", "%d+") do DUMPS[tonumber(v)] = true end
local MOVES = {}
for item in string.gmatch(os.getenv("MOVES") or "", "[^,]+") do
  local f, b, n = item:match("(%d+):([%w+]+):(%d+)")
  MOVES[#MOVES + 1] = {tonumber(f), b, tonumber(n)}
end
local POKES = {}
for item in string.gmatch(os.getenv("POKE") or "", "[^;]+") do
  local f, rest = item:match("(%d+):(.+)")
  for addr, val in rest:gmatch("(%x+)=(%x+)") do
    POKES[#POKES + 1] = {tonumber(f), tonumber(addr, 16), tonumber(val, 16)}
  end
end
local killing = false
local KILLF = tonumber(os.getenv("KILLF") or "")
local KILL = tonumber(os.getenv("KILL") or "-1")
local ENDF = tonumber(os.getenv("END") or "1500")
local FOLLOW = os.getenv("FOLLOW") == "1"

-- stage start: first frame with $1031 in the stage range
local f, st, last = 0, nil, -1
emu.addEventCallback(function()
  if not st then return end
  local k = f - st
  local t = {}
  for _, m in ipairs(MOVES) do
    if k >= m[1] and k < m[1] + m[3] then for b in m[2]:gmatch("[^+]+") do t[b] = true end end
  end
  if next(t) then emu.setInput(t, 0) end
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  f = f + 1
  local m = r(0x1031)
  if m ~= last then L(string.format("f=%d mode %02X%s", f, m, st and string.format(" (stage frame %d)", f - st) or "")) last = m end
  if not st and m >= 0x0D and m < 0x74 then st = f end
  if not st then return end
  local k = f - st
  if KILLF and k >= KILLF and k < KILLF + 20 then   -- flames on every enemy actor's cell (actors 5-23 with $16C2 != 0)
    for x = 5, 23 do
      if r(0x17FA + x) ~= 0xFF and r(0x16C2 + x) ~= 0 then
        local c = r(0x16AA + x)
        emu.write(0x1052 + c, tonumber(os.getenv("FLAME") or "05", 16), emu.memType.snesWorkRam)
      end
    end
  end
  if k == KILL then emu.write(0x1D50, 0, emu.memType.snesWorkRam) killing = true end
  for _, p in ipairs(POKES) do if p[1] == k then emu.write(p[2], p[3], emu.memType.snesWorkRam) end end
  if SHOTS[k] then shot(tostring(k)) end
  if DUMPS[k] then
    local t = {} for i = 0, 0x1FFFF do t[#t + 1] = string.char(emu.read(i, emu.memType.snesWorkRam)) end
    local h = io.open(OUT .. "_wram" .. k .. ".bin", "wb") h:write(table.concat(t)) h:close()
    t = {} for i = 0, 0xFFFF do t[#t + 1] = string.char(emu.read(i, emu.memType.snesVideoRam)) end
    h = io.open(OUT .. "_vram" .. k .. ".bin", "wb") h:write(table.concat(t)) h:close()
    t = {} for i = 0, 0x1FF do t[#t + 1] = string.char(emu.read(i, emu.memType.snesCgRam)) end
    h = io.open(OUT .. "_cgram" .. k .. ".bin", "wb") h:write(table.concat(t)) h:close()
    t = {} for i = 0, 543 do t[#t + 1] = string.char(emu.read(i, emu.memType.snesSpriteRam)) end
    h = io.open(OUT .. "_oam" .. k .. ".bin", "wb") h:write(table.concat(t)) h:close()
  end
  if k == ENDF then
    local h = io.open(OUT .. ".txt", "w") h:write(table.concat(log, NL)) h:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)

-- WATCH="1031,1D50": log every distinct PC that reads (R) / writes (W) these WRAM bytes once the stage started
--   ("W1D50"), with the value
local seenpc = {}
for item in string.gmatch(os.getenv("WATCH") or "", "[^,]+") do
  local kind, addr = item:match("^([RW]?)(%x+)$")
  local a = tonumber(addr, 16)
  local cbt = kind == "W" and emu.callbackType.write or emu.callbackType.read
  local fn = function(address, value)
    if not st then return end
    local s = emu.getState()
    local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
    local key = string.format("%s%04X@%06X", kind, a, pc)
    if not seenpc[key] then seenpc[key] = 1 L(string.format("%s %04X pc=%06X v=%02X frame %d", kind == "W" and "W" or "R", a, pc, value, f - st)) end
  end
  emu.addMemoryCallback(fn, cbt, a, a)
  emu.addMemoryCallback(fn, cbt, 0x7E0000 + a, 0x7E0000 + a)
end

-- KILL=<stage frame>: fakes "all enemies dead": $1D50 = 0 and, at the next task-runner call ($C0:22F0), a stub at
-- $7F:F000 runs JSL $C5:3B4E (the clear check that runs the record's type $0D entries = the exits) then returns
-- to the main loop. The enemies themselves stay (they still hurt).
if KILL >= 0 then
  local function kcb()
    if not killing then return end
    killing = false
    local stub = {0x08, 0xE2, 0x30, 0x22, 0x4E, 0x3B, 0xC5, 0x28, 0x5C, 0xF0, 0x22, 0xC0}  -- PHP SEP#30 JSL PLP JML
    for i, b in ipairs(stub) do emu.write(0x7FF000 + i - 1, b, emu.memType.snesMemory) end
    local s = emu.getState()
    s["cpu.k"] = 0x7F s["cpu.pc"] = 0xF000
    emu.setState(s)
    L(string.format("kill: clear check called at stage frame %d", f - st))
  end
  emu.addMemoryCallback(kcb, emu.callbackType.exec, 0xC022F0, 0xC022F0)
  emu.addMemoryCallback(kcb, emu.callbackType.exec, 0x8022F0, 0x8022F0)
end

-- STAGE=<hex>: the first stage played is this one instead of 1-1 (the map's write of $0D to $1031 is replaced)
local STAGE = tonumber(os.getenv("STAGE") or "", 16)
if STAGE then
  local done = false
  local fn = function(address, value)
    if not done and value == 0x0D then done = true L("stage remapped") return STAGE end
  end
  emu.addMemoryCallback(fn, emu.callbackType.write, 0x1031, 0x1031)
  emu.addMemoryCallback(fn, emu.callbackType.write, 0x7E1031, 0x7E1031)
end

-- EXEC="E4AC6D,C53B4E": log every call of these addresses (stage frame, A, X, Y, [$0A] byte)
for item in string.gmatch(os.getenv("EXEC") or "", "[^,]+") do
  local a = tonumber(item, 16)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local p = emu.read(0x0A, emu.memType.snesWorkRam) | (emu.read(0x0B, emu.memType.snesWorkRam) << 8) | (emu.read(0x0C, emu.memType.snesWorkRam) << 16)
    L(string.format("exec %06X frame %s A=%04X X=%04X Y=%04X [$0A]=%06X:%02X", a, st and tostring(f - st) or ("boot " .. f),
      s["cpu.a"], s["cpu.x"], s["cpu.y"], p, emu.read(p, emu.memType.snesMemory)))
  end, emu.callbackType.exec, a, a)
end

-- picker_nav drives the menus; its own stop comes at STAGE_WAIT (keep it beyond END)
dofile(DIR .. "/picker_nav.lua")
