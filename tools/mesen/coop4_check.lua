-- 4-player check of one stage (RING of stage_test.lua; run by tools/coop4_check.py): seats 2-4 join in the
-- picker, the stage COOP4_STAGE is forced (the first stage id written to $1031 is replaced, whatever the save
-- says), every bomber is kept alive by the test ($C4:2D2B takes the "still invincible" path), and from stage
-- frame 260 they walk and drop bombs. Measured over stage frames 300 .. END:
--   fps     main loop passes ($C0:0B4A) per 60 frames, worst window
--   louie   frames in which an egg could not appear for lack of colors (asm/louies.asm louie_egg_ok: no Louie
--           palette (slot set $FF) and no free slot 3-7)
--   shared  frames in which P3/P4 show another seat's colors (palette slot 1/2, c0_palfail)
-- Result: one line to COOP4_OUT.
local STG = tonumber(os.getenv("COOP4_STAGE") or "0D", 16)
local OUTF = os.getenv("COOP4_OUT") or "build/coop4.txt"
local ENDF = tonumber(os.getenv("END") or "1500")
local BOMB = tonumber(os.getenv("COOP4_BOMB") or "60")   -- frames between bombs, 0 = none
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local function cell(a)                                  -- actor's cell (docs/ROM_MAP.md: player cell)
  return ((r(0x182A + a) + 8) & 0xFF) >> 4 | ((r(0x1872 + a) + 8) & 0xF0)
end
local function r7(a) return emu.read(0x7F0000 + a, emu.memType.snesMemory) end

-- seats 2-4: input written after the pad reader (the testrunner puts every port on P1)
local inj = {}
emu.addMemoryCallback(function()
  for seat, v in pairs(inj) do
    emu.write(0x2C + seat, v[1], emu.memType.snesWorkRam)
    emu.write(0x31 + seat, v[2], emu.memType.snesWorkRam)
    emu.write(0x36 + seat, v[3] or 0, emu.memType.snesWorkRam)
  end
end, emu.callbackType.exec, 0xC00AF9, 0xC00AF9)

-- the stage
local forced = false
local function force(a, v) if not forced and v >= 0x0D and v < 0x74 then forced = true return STG end end
emu.addMemoryCallback(force, emu.callbackType.write, 0x1031, 0x1031)
emu.addMemoryCallback(force, emu.callbackType.write, 0x7E1031, 0x7E1031)

-- nobody dies (test side only)
emu.addMemoryCallback(function()
  local s = emu.getState() s["cpu.pc"] = 0x2D3E emu.setState(s)
end, emu.callbackType.exec, 0xC42D2B, 0xC42D2B)

local f, st, cur, t = 0, nil, -1, 0
local runs, worst, louie, shared, frames = 0, 999, 0, 0, 0
local wins = {}
local enemies = 0
local start = ""
local snapk = nil
local DIRS = {1, 2, 4, 8}
emu.addMemoryCallback(function() if st then runs = runs + 1 end end, emu.callbackType.exec, 0xC00B4A, 0xC00B4A)
emu.addEventCallback(function()
  f = f + 1
  local mode = r(0x1031)
  inj = {}
  if mode == 4 and r7(0xFC00) == 2 then                -- picker (asm/picker.asm): seat s presses right s times, A
    local s = r7(0xFC03)
    if s ~= cur then cur = s t = 0 end
    t = t + 1
    if s >= 1 and s <= 3 then
      for k = 1, s do if t >= 20 * k and t < 20 * k + 4 then inj[s] = {0, 1} end end
      if t >= 20 * s + 40 and t < 20 * s + 44 then inj[s] = {0x80, 0, t == 20 * s + 40 and 0x80 or 0} end
    end
  end
  if not st and forced and mode == STG then st = f end
  if not st then return end
  local k = f - st
  if k > 260 then
    for seat = 0, 3 do inj[seat] = {(BOMB > 0 and k % BOMB < 3) and 0x80 or 0, DIRS[((k // 50) + seat) % 4 + 1]} end
  end
  if k >= 300 then
    frames = frames + 1
    local ok = false
    for i = 0, 7 do if r(0x2B18 + i) == 0xFF then ok = true end end
    for i = 3, 7 do if r(0x2B10 + i) == 0 then ok = true end end
    if not ok then louie = louie + 1 end
    for seat = 2, 3 do
      local o = r(0x17FA + seat)
      if o < 0x80 and r(0x06DF + o) < 3 then shared = shared + 1 end
    end
    if k % 60 == 59 then if runs < worst then worst = runs end wins[#wins + 1] = runs runs = 0 end
  elseif k == 299 then runs = 0 enemies = r(0x1D50) end
  if not snapk and (r(0x1D50) > 0 or k == 240) then snapk = k + 60 end   -- (the map is filled ~50 frames later)
  if k == snapk then                                    -- start state for the spawn-safety rule (tools/coop4_check.py)
    local t = {}
    for i = 0, 255 do t[#t + 1] = string.format("%02X", r(0x1052 + i)) end
    start = "map " .. table.concat(t) .. "\nkeep"
    t = {}
    for i = 0, 255 do t[#t + 1] = string.format("%02X", r(0x2700 + i)) end   -- $10: no random soft block
    start = start .. " " .. table.concat(t) .. "\nseats"
    for seat = 0, 3 do
      local o = r(0x17FA + seat)
      start = start .. string.format(" %02X", (o < 0x80 and r(0x15A2 + seat) < 0x80) and cell(seat) or 0xFF)
    end
    start = start .. "\nfire"
    for seat = 0, 3 do start = start .. string.format(" %d", r(0x4EBD + seat)) end
    start = start .. "\nenemies"
    for a = 5, r(0x198C) do
      if r(0x17FA + a) < 0x80 and r(0x16C2 + a) ~= 0 then start = start .. string.format(" %02X:%02X", cell(a), r(0x16C2 + a)) end
    end
    start = start .. "\n"
  end
  if k == ENDF - 2 then
    local slots = ""
    for i = 0, 7 do slots = slots .. string.format(" %02X", r(0x2B10 + i)) end
    local h = io.open(OUTF, "w")
    h:write(string.format("stage %02X frames %d fps %d louie %d shared %d enemies %d slots%s\n", STG, frames, worst, louie, shared, enemies, slots))
    h:write("seconds " .. table.concat(wins, " ") .. "\n")
    h:write(start)
    h:close()
  end
end, emu.eventType.endFrame)
