-- Logs every graphics load of the SB5 engine: archives ($C0:1B04, A = id, set $0AE7), palette
-- lookups ($C0:01DE, A = id, set $0AE7) and arrangements ($C0:001B, A = id, set $0340), once per
-- (kind, set, id, mode), plus CPU reads of the ROM ranges in LOADS_WATCH (freed SB5 data, all HiROM
-- mirrors), into LOADS_OUT. Used to check that freed data is never read (docs/FREE_SPACE.md).
-- On its own it just runs (boot logo, title, attract demo) until LOADS_FRAMES; LOADS_NAV=<script>
-- also runs that script of this folder (e.g. picker_nav.lua: title -> Normal Game -> picker -> stage).
-- env: LOADS_OUT (default build/loads.txt), LOADS_FRAMES (default 6000), LOADS_NAV, SB6_LUA (this folder),
-- LOADS_WATCH ("C5E22D-C5EB44,D59993-D5A544,...", SNES addresses, inclusive).
local DIR = os.getenv("SB6_LUA") or "D:/super-bomberman-6-snes/tools/mesen"
local OUT = os.getenv("LOADS_OUT") or "build/loads.txt"
local FRAMES = tonumber(os.getenv("LOADS_FRAMES") or "6000")
local seen, lines, frame = {}, {}, 0
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local function flush()
  local h = io.open(OUT, "w") h:write(table.concat(lines, "\n") .. "\n") h:close()
end
local function rec(kind, set)
  local id = emu.getState()["cpu.a"] & 0xFF
  local key = string.format("%s %02X %02X %02X", kind, set, id, r(0x1031))
  if not seen[key] then seen[key] = true lines[#lines + 1] = key .. string.format(" f=%d", frame) end
end
emu.addMemoryCallback(function() rec("arc", r(0x0AE7)) end, emu.callbackType.exec, 0xC01B04, 0xC01B04)
emu.addMemoryCallback(function() rec("pal", r(0x0AE7)) end, emu.callbackType.exec, 0xC001DE, 0xC001DE)
emu.addMemoryCallback(function() rec("arr", r(0x0340)) end, emu.callbackType.exec, 0xC0001B, 0xC0001B)
-- OBJ sheet pages ($C5:6B85: A = sheet - 1), sound set and song uploads ($C0:0E31 / $C0:0E9C: A = id)
local function rec1(kind, d) return function()
  local id = (emu.getState()["cpu.a"] + d) & 0xFF
  local key = string.format("%s %02X %02X", kind, id, r(0x1031))
  if not seen[key] then seen[key] = true lines[#lines + 1] = key .. string.format(" f=%d", frame) end
end end
emu.addMemoryCallback(rec1("sheet", 1), emu.callbackType.exec, 0xC56B85, 0xC56B85)
emu.addMemoryCallback(rec1("sndset", 0), emu.callbackType.exec, 0xC00E31, 0xC00E31)
emu.addMemoryCallback(rec1("song", 0), emu.callbackType.exec, 0xC00E9C, 0xC00E9C)
local reads = 0
for lo, hi in string.gmatch(os.getenv("LOADS_WATCH") or "", "(%x+)-(%x+)") do
  lo, hi = tonumber(lo, 16), tonumber(hi, 16)
  local bank, a0, a1 = lo >> 16 & 0x3F, lo & 0xFFFF, hi & 0xFFFF
  local banks = {0xC0 | bank, 0x40 | bank}
  if a0 >= 0x8000 then banks[#banks + 1] = 0x80 | bank banks[#banks + 1] = bank end
  for _, b in ipairs(banks) do
    emu.addMemoryCallback(function(addr)
      reads = reads + 1
      if reads <= 200 then
        lines[#lines + 1] = string.format("READ %06X pc=%06X mode=%02X f=%d", addr, emu.getState()["cpu.k"] << 16 |
          emu.getState()["cpu.pc"], r(0x1031), frame)
      end
    end, emu.callbackType.read, b << 16 | a0, b << 16 | a1)
  end
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then flush() end
  if frame >= FRAMES then lines[#lines + 1] = "watched reads: " .. reads flush() emu.stop(0) end
end, emu.eventType.endFrame)
if os.getenv("LOADS_NAV") then
  local stop = emu.stop
  emu.stop = function(c) lines[#lines + 1] = "watched reads: " .. reads flush() stop(c) end
  dofile(DIR .. "/" .. os.getenv("LOADS_NAV"))
end
