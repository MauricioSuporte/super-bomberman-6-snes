-- Normal Game menus in Mesen (tools/menu_check.py): boots the hack, follows PLAN and logs, every frame something
-- changes, the screen (mode, menu state, brightness), the music and the SFX voice, so the checker can time each
-- press -> next screen lit and see whether a sound plays to its end.
-- env: SB6_OUT (log path), PLAN (comma list: a b start up down left right = press (held 4 frames, then 16 idle);
--   lit = wait until the screen is lit (brightness 15, no forced blank) for 20 frames; pick = wait for the SB6
--   picker's choosing state; title = wait for the title (mode 2, menu $1036 0, its music) lit; players = the
--   title's players menu ($1036 1) lit; wN = wait N frames;
--   mark:name; shot:name; oam:name = log OAM)
--   ready = the NORMAL MODE menu / a file list takes input (its task kept its pc 12 frames); item:N = down until
--   the menu's cursor is on item N (0 New Game, 1 Continue, 2 Erase File); stage = A every 50 frames until a
--   stage runs
-- log: "R f mode 1037 1036 0300 010A 0100 v0 pk 1032 1034 1038 v7" (v0 / v7 = voice 0's / 7's envelope > 0: the
--   SFX / the stream's music; pk = $7F:FC00;
--   menu cursor: item, Y, X), "T f 0:pppp" (the menus' task pc in bank $C7), "O f name
--   1034 1038 oam-hex", "S f AAAA"
--   (sound API call, A = group << 8 | id), "P f btn", "K f name" (mark), "E f msg"
local OUT = os.getenv("SB6_OUT") or "build/menu_check.txt"
local PLAN = {} for t in string.gmatch(os.getenv("PLAN") or "", "[^,]+") do PLAN[#PLAN + 1] = t end
local log = {}
local function L(s) log[#log + 1] = s end
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local function rm(a) return emu.read(a, emu.memType.snesMemory) end
-- SRAM: the menus depend on the saved files (New Game is skipped while every file is used), so the run starts
-- from a blank SRAM; the original goes back before Mesen writes its .srm.
local SRAM, sram0 = emu.memType.snesSaveRam, nil
local function fin(code)
  if sram0 then for i = 0, #sram0 do emu.write(i, sram0[i], SRAM) end end
  local h = io.open(OUT, "w") h:write(table.concat(log, "\n"), "\n") h:close() emu.stop(code or 0)
end
local f, step, btn, hold, idle, lit, waitn = 0, 1, nil, 0, 0, 0, nil
emu.addEventCallback(function()
  if hold > 0 and btn then local t = {} t[btn] = true emu.setInput(t, 0) end
end, emu.eventType.inputPolled)
emu.addMemoryCallback(function()
  local s = emu.getState()
  L(string.format("S %d %04X", f, s["cpu.a"] & 0xFFFF))
end, emu.callbackType.exec, 0xC00CED, 0xC00CED)
local BTN = {a = 1, b = 1, start = 1, up = 1, down = 1, left = 1, right = 1, select = 1, x = 1, y = 1}
local last, lastt, t0pc, t0n, tries = "", "", -1, 0, 0
local function stage_mode(m) return m >= 0x0D and m < 0x74 end
local TRACE = os.getenv("TRACE")
emu.addEventCallback(function()
  f = f + 1
  if f == 1 then
    local n = emu.getMemorySize(SRAM)
    sram0 = {}
    for i = 0, n - 1 do sram0[i] = emu.read(i, SRAM) emu.write(i, 0, SRAM) end
    L("X sram " .. n)
  end
  if f == 690 then        -- the game wrote a fresh SRAM: file 1 used (0 %, stage $0D), files 2-3 empty, so the
    local ok = emu.read(0x10, SRAM) == 0x53 and emu.read(0x42, SRAM) == 0xFF   -- menu has its 3 items
    if ok then
      emu.write(0x42, 0x00, SRAM)
      local sum = 0
      for i = 0x32, 0x6F do sum = sum + emu.read(i, SRAM) end           -- files: checksum word at $30
      emu.write(0x30, sum & 0xFF, SRAM) emu.write(0x31, (sum >> 8) & 0xFF, SRAM)
    end
    L("X sram file1 " .. (ok and "used" or "not initialized"))
  end
  if hold > 0 then hold = hold - 1 end
  if idle > 0 then idle = idle - 1 end
  local mode, b = r(0x1031), r(0x0300)
  local on = (b & 0x80) == 0 and (b & 0x0F) == 15
  lit = on and lit + 1 or 0
  local v0 = emu.read(0x08, emu.memType.spcDspRegisters) > 0 and 1 or 0
  local v7 = emu.read(0x78, emu.memType.spcDspRegisters) > 0 and 1 or 0
  local row = string.format("%02X %02X %02X %02X %02X %02X %d %02X %02X %02X %02X %d", mode, r(0x1037), r(0x1036), b,
    r(0x010A), r(0x0100), v0, rm(0x7FFC00), r(0x1032), r(0x1034), r(0x1038), v7)
  if row ~= last then L(string.format("R %d %s", f, row)) last = row end
  -- the menus' task (task 0, pc low / mid / bank at $0C90 / $0CB8 / $0CE0): waiting for input = same pc
  local pc = r(0x0C90) | (r(0x0CB8) << 8) | (r(0x0CE0) << 16)
  if pc ~= t0pc then t0pc, t0n = pc, 0 if pc >> 16 == 0xC7 then L(string.format("T %d 0:%04X", f, pc & 0xFFFF)) end
  else t0n = t0n + 1 end
  if TRACE then                        -- research: every script task in bank $C7
    local t = {}
    for i = 1, 39 do
      if r(0x0CE0 + i) == 0xC7 then t[#t + 1] = string.format("%d:%02X%02X", i, r(0x0CB8 + i), r(0x0C90 + i)) end
    end
    local s2 = table.concat(t, " ")
    if s2 ~= lastt then L(string.format("U %d %s", f, s2)) lastt = s2 end
  end
  if f > 20000 then L("E " .. f .. " timeout at step " .. step .. " " .. tostring(PLAN[step])) fin(1) return end
  if f < 700 or idle > 0 or hold > 0 then return end
  local t = PLAN[step]
  if not t then L("E " .. f .. " done") fin(0) return end
  local adv = false
  if BTN[t] then
    btn, hold, idle = t, 4, 20 L(string.format("P %d %s", f, t)) adv = true
  elseif t == "lit" then adv = lit >= 20
  elseif t == "pick" then adv = mode == 4 and rm(0x7FFC00) == 2 and lit >= 20
  elseif t == "title" then adv = mode == 2 and r(0x1036) == 0 and lit >= 20 and r(0x0100) == 1 and r(0x010A) == 1
  elseif t == "players" then adv = mode == 2 and r(0x1036) == 1 and lit >= 20
  elseif t == "ready" then                -- (not while the hand slides in: $C7:1220-$125C, the cursor's routines)
    local lo = t0pc & 0xFFFF
    adv = t0pc >> 16 == 0xC7 and t0n >= 12 and mode == 3 and not (lo >= 0x1220 and lo < 0x125D)
  elseif t:sub(1, 5) == "item:" then      -- the NORMAL MODE menu's cursor on item N (down presses)
    if r(0x1032) == tonumber(t:sub(6)) then adv = true tries = 0
    elseif tries > 6 then L("E " .. f .. " item not reached " .. t) fin(1) return
    else btn, hold, idle, tries = "down", 4, 16, tries + 1 L(string.format("P %d down", f)) end
  elseif t == "stage" then                -- A until a stage runs (any file, any question on the way)
    if stage_mode(mode) then adv = true
    else btn, hold, idle = "a", 4, 50 L(string.format("P %d a", f)) end
  elseif t:sub(1, 1) == "w" and tonumber(t:sub(2)) then
    waitn = waitn or tonumber(t:sub(2))
    waitn = waitn - 1
    if waitn <= 0 then waitn = nil adv = true end
  elseif t:sub(1, 4) == "oam:" then       -- OAM (544 bytes) and the menu cursor's place, for the hand's sprite
    local h = {}
    for i = 0, 543 do h[#h + 1] = string.format("%02X", emu.read(i, emu.memType.snesSpriteRam)) end
    L(string.format("O %d %s %02X %02X %s", f, t:sub(5), r(0x1034), r(0x1038), table.concat(h)))
    adv = true
  elseif t:sub(1, 5) == "mark:" then L(string.format("K %d %s", f, t:sub(6))) adv = true
  elseif t:sub(1, 5) == "shot:" then
    local h = io.open(OUT:gsub("%.txt$", "") .. "_" .. t:sub(6) .. ".png", "wb") h:write(emu.takeScreenshot()) h:close()
    adv = true
  else L("E " .. f .. " bad step " .. t) fin(1) return end
  if adv then step = step + 1 end
end, emu.eventType.endFrame)
