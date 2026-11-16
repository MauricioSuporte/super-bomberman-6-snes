-- Super Bomberman 2 (USA): dumps for tools/extract_world_map.py zone2.
--   Mesen.exe --testrunner "Super Bomberman 2 (USA).sfc" tools/mesen/sb2_world_map.lua
-- env OUT = output directory. Start at frames 300 (skips the intro) and 1150 (Normal Game); the map
-- (World 1, stars and ships) is up at frames ~1170-1500. Writes v1300.bin / c1300.bin / o1300.bin
-- (VRAM, CGRAM, OAM), aram1300.bin (sound RAM: driver, map song and samples, the song plays since
-- frame 1217) and cg.txt (CGRAM of every frame 1250-1499: "frame bg1_vscroll color0 ... color255").
local OUT = os.getenv("OUT") or "."
local f = 0
local function dump(name, mt, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.char(emu.read(i, mt)) end
  local h = io.open(OUT .. "/" .. name, "wb") h:write(table.concat(t)) h:close()
end
emu.addEventCallback(function()
  if (f >= 300 and f < 304) or (f >= 1150 and f < 1154) then emu.setInput({start = true}, 0) end
end, emu.eventType.inputPolled)
local cg = io.open(OUT .. "/cg.txt", "w")
emu.addEventCallback(function()
  f = f + 1
  if f >= 1250 and f < 1500 then
    local t = {}
    for i = 0, 255 do
      t[#t + 1] = string.format("%04X", emu.read(2 * i, emu.memType.snesCgRam) | (emu.read(2 * i + 1, emu.memType.snesCgRam) << 8))
    end
    cg:write(f .. " " .. emu.getState()["ppu.layers[0].vscroll"] .. " " .. table.concat(t, " ") .. "\n")
  end
  if f == 1300 then
    dump("v1300.bin", emu.memType.snesVideoRam, 65536)
    dump("c1300.bin", emu.memType.snesCgRam, 512)
    dump("o1300.bin", emu.memType.snesSpriteRam, 544)
    dump("aram1300.bin", emu.memType.spcRam, 65536)
  end
  if f == 1500 then cg:close() emu.stop(0) end
end, emu.eventType.endFrame)
