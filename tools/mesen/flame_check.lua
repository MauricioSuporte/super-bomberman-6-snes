-- Explosion check of one stage (RING of stage_test.lua, run by tools/flame_check.py): coop4_check.lua plays the
-- stage COOP4_STAGE with 4 seats that walk and drop bombs (nobody dies); from stage frame FLAME_FROM to END every
-- FLAME_STEP frames this appends a record to FLAME_OUT:
--   "FLM1", stage frame (u32), BG1SC, BG2SC ($0369, the field's: the IRQ writes it), BG12NBA, $1B7C, $0F61,
--   $1D1A, scroll words $0331 $0333 $0337 $0339 (BG1 H, BG2 H, BG1 V, BG2 V: the NMI copies), $1052-$1151 (cells),
--   CGRAM (512 bytes), VRAM bytes $0000-$9FFF (words $0000-$4FFF: tiles $000-$3FF of BG1/BG2 and their maps)
dofile((os.getenv("SB6_LUA") or "D:/super-bomberman-6-snes/tools/mesen") .. "/coop4_check.lua")

local FSTG = tonumber(os.getenv("COOP4_STAGE") or "0D", 16)
local FROM = tonumber(os.getenv("FLAME_FROM") or "250")
local STEP = tonumber(os.getenv("FLAME_STEP") or "6")
local FEND = tonumber(os.getenv("END") or "1500") - 4
local FOUT = os.getenv("FLAME_OUT") or "build/flame_check.bin"
local VBYTES = 0xA000

local reg = {[0x07] = 0, [0x0B] = 0}
emu.addMemoryCallback(function(addr, value) reg[addr & 0xFF] = value end, emu.callbackType.write, 0x002107, 0x00210B)

local function rb(a) return emu.read(a, emu.memType.snesWorkRam) end
local fh = io.open(FOUT, "wb")
local fr, fst = 0, nil
emu.addEventCallback(function()
  fr = fr + 1
  if not fst then
    if fr > 600 and rb(0x1031) == FSTG then fst = fr end
    return
  end
  local k = fr - fst
  if k < FROM or k > FEND or (k - FROM) % STEP ~= 0 or not fh then return end
  local t = {"FLM1", string.char(k & 0xFF, (k >> 8) & 0xFF, (k >> 16) & 0xFF, 0),
             string.char(reg[0x07], rb(0x0369), reg[0x0B], rb(0x1B7C), rb(0x0F61), rb(0x1D1A))}
  for _, a in ipairs({0x0331, 0x0333, 0x0337, 0x0339}) do t[#t + 1] = string.char(rb(a), rb(a + 1)) end
  for i = 0, 255 do t[#t + 1] = string.char(rb(0x1052 + i)) end
  for i = 0, 0x1FF do t[#t + 1] = string.char(emu.read(i, emu.memType.snesCgRam)) end
  for i = 0, VBYTES - 1 do t[#t + 1] = string.char(emu.read(i, emu.memType.snesVideoRam)) end
  fh:write(table.concat(t))
  if k + STEP > FEND then fh:close() fh = nil end
end, emu.eventType.endFrame)
