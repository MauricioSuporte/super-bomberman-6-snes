-- Super Bomberman (USA): dumps for tools/extract_world_map.py.
--   Mesen.exe --testrunner "Super Bomberman (USA).sfc" tools/mesen/sb1_world_map.lua
-- env OUT = output directory. Writes aram_boot.bin (sound RAM at frame 125, right after the boot upload)
-- and m_vram<k>.bin / m_cgram<k>.bin / m_oam<k>.bin for 200 frames of the World 1 map (from frame 850;
-- Start is pressed every 60 frames from 300 to 780: title -> Normal Game -> map).
local OUT = os.getenv("OUT") or "."
local f = 0
local plan = {}
for k = 0, 8 do for i = 0, 3 do plan[300 + k * 60 + i] = "start" end end
local function dump(name, mt, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.char(emu.read(i, mt)) end
  local h = io.open(OUT .. "/" .. name, "wb") h:write(table.concat(t)) h:close()
end
emu.addEventCallback(function()
  local b = plan[f]
  if b then local t = {} t[b] = true emu.setInput(t, 0) end
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  f = f + 1
  if f == 125 then dump("aram_boot.bin", emu.memType.spcRam, 65536) end
  if f >= 850 and f < 1050 then
    local k = f - 850
    dump("m_vram" .. k .. ".bin", emu.memType.snesVideoRam, 65536)
    dump("m_cgram" .. k .. ".bin", emu.memType.snesCgRam, 512)
    dump("m_oam" .. k .. ".bin", emu.memType.snesSpriteRam, 544)
  end
  if f == 1050 then emu.stop(0) end
end, emu.eventType.endFrame)
