-- SB6 QA engine (run by tools/qa.py; never by hand).  One Mesen process = one fixture + many scenarios:
--   1. fixture: boot, title -> Normal Game -> picker (each seat picks its character / color) -> stage, until the
--      stage frame `ready`; then a savestate.  Python passes QA_STATE: when that file exists (same ROM sha1 +
--      fixture) the boot is skipped and the state is loaded at the first main-loop pass.
--   2. every scenario starts from that state, runs its steps for `len` frames, its recorders write to QA_OUT.
-- QA_PLAN = a Lua file returning {fixture = {...}, scenarios = {...}} (written by tools/qa/plan.py).
--
-- Output lines (QA_OUT, text):  "S <name>" scenario start, "E <name>" end, and per frame k (0 = scenario start):
--   A k actor anim          animation id change ($079F+obj) of a watched actor (seats 0-4, their mounts = seat +
--                           $0128 (co-op mount offset), scenario.watch)
--   O k actor obj           object change of a watched actor ($17FA+actor, FF = none)
--   Q k group id            sound request ($C0:0CED: A = id, B = group)
--   C k cmd                 command sent through $C0:0E7F (SB5's SFX / song command handshake)
--   P k cmd                 SPC port 0 value written by the CPU ($2140, bit 7 = toggle; P1-P3: ports 1-3)
--   G k cmd                 in-game SFX left in $018C by asm/game_sfx.asm
--   M k mode                $1031 change
--   D k seat                seat status bit 7 set ($15A2: dead)
--   F k runs                main-loop passes in the last 60 frames (every 60 frames)
--   V k name value...       values asked by a "read" step (hex bytes)
--   X k text                engine messages / errors
-- Pose dumps (rec.pose = {actor...}): QA_OUT .. "_<scenario>.pose": per frame and actor
--   actor, obj, page, mapping, anim, slot, OAM (544), OBJ VRAM $6000-$7FFF (16 KB).
local PLAN = dofile(os.getenv("QA_PLAN"))
local OUTP = os.getenv("QA_OUT")
local STATEF = os.getenv("QA_STATE")
local FX = PLAN.fixture
local out = io.open(OUTP, "w")
local function W(s) out:write(s, "\n") end
local function r(a) return emu.read(a, emu.memType.snesWorkRam) end
local function rw(a) return r(a) | (r(a + 1) << 8) end
local function wr(a, v) emu.write(a, v & 0xFF, emu.memType.snesWorkRam) end
local function rm(a) return emu.read(a, emu.memType.snesMemory) end
local function wm(a, v) emu.write(a, v & 0xFF, emu.memType.snesMemory) end
local function hexs(a, n, mem)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.format("%02X", emu.read(a + i, mem or emu.memType.snesWorkRam)) end
  return table.concat(t)
end
local function fin(code)
  out:close()
  emu.stop(code or 0)
end

-- ---------------------------------------------------------------- pads: every seat injected after the pad reader
local inj = {}           -- seat -> {held actions, held dirs, new actions, new dirs}
local prev = {}          -- seat -> last injected held (to make "new" presses)
local BTN = {a = {0x80, 0}, x = {0x40, 0}, l = {0x20, 0}, r = {0x10, 0}, b = {0x08, 0}, y = {0x04, 0},
             select = {0x02, 0}, start = {0x01, 0}, right = {0, 1}, left = {0, 2}, down = {0, 4}, up = {0, 8}}
local function pad(seat, names)
  local a, d = 0, 0
  for n in names:gmatch("[^+]+") do local b = BTN[n] if b then a = a | b[1] d = d | b[2] end end
  local e = inj[seat] or {0, 0}
  inj[seat] = {e[1] | a, e[2] | d}
end
emu.addMemoryCallback(function()
  for seat = 0, 4 do
    local v = inj[seat]
    local p = prev[seat] or {0, 0}
    if v then
      wr(0x2C + seat, v[1]) wr(0x31 + seat, v[2])
      wr(0x36 + seat, v[1] & ~p[1]) wr(0x3B + seat, v[2] & ~p[2]) wr(0x40 + seat, v[2] & ~p[2])
      prev[seat] = v
    else
      prev[seat] = nil
    end
  end
  if r(0x1031) == 2 then wr(0x25, 1) wr(0x26, 1) end   -- title: pads 3/4 plugged in (no multitap here; the players menu needs them)
end, emu.callbackType.exec, 0xC00AF9, 0xC00AF9)

-- ---------------------------------------------------------------- state
local frame = 0          -- frames since power-on (this process)
local phase = STATEF and io.open(STATEF, "rb") and "load" or "boot"
local stage0 = nil       -- frame the stage started
local want = nil         -- "save" / "load" at the next main-loop pass
local saved = nil
local sc_i, sc, k = 0, nil, 0   -- current scenario, its frame
local invincible = false
local runs = 0

local function cell_of(actor) return ((r(0x182A + actor) + 8) & 0xFF) >> 4 | ((r(0x1872 + actor) + 8) & 0xF0) end

-- ---------------------------------------------------------------- recorders
local watch = {}          -- actor -> {obj, anim}
local function rec_on() return sc ~= nil end
emu.addMemoryCallback(function()
  if not rec_on() then return end
  local s = emu.getState()
  W(string.format("Q %d %02X %02X", k, (s["cpu.a"] >> 8) & 0xFF, s["cpu.a"] & 0xFF))
end, emu.callbackType.exec, 0xC00CED, 0xC00CED)
emu.addMemoryCallback(function()                 -- SFX / song command through the handshake $C0:0E7F (A = command)
  if rec_on() then W(string.format("C %d %02X", k, emu.getState()["cpu.a"] & 0xFF)) end
end, emu.callbackType.exec, 0xC00E7F, 0xC00E7F)
local lastp = {}
local function port_w(addr, v)
  local p = addr & 3
  if rec_on() and v ~= lastp[p] then W(string.format("%s %d %02X", p == 0 and "P" or ("P" .. p), k, v)) end
  lastp[p] = v
end
emu.addMemoryCallback(port_w, emu.callbackType.write, 0x2140, 0x2143)
emu.addMemoryCallback(port_w, emu.callbackType.write, 0x802140, 0x802143)
local function gs_w(addr, v) if rec_on() and v ~= 0 then W(string.format("G %d %02X", k, v)) end end
for _, a in ipairs({0x018C, 0x80018C, 0x7E018C}) do emu.addMemoryCallback(gs_w, emu.callbackType.write, a, a) end
emu.addMemoryCallback(function() runs = runs + 1 end, emu.callbackType.exec, 0xC00B4A, 0xC00B4A)

-- no seat 0-3 dies while `invincible` ($C4:2D2B takes the "still invincible" path, as tools/mesen/coop4_check.lua)
emu.addMemoryCallback(function()
  if not invincible then return end
  local s = emu.getState()
  if (s["cpu.x"] & 0xFF) < 4 then s["cpu.pc"] = 0x2D3E emu.setState(s) end   -- X = actor: seats 0-3 only (not rivals)
end, emu.callbackType.exec, 0xC42D2B, 0xC42D2B)

-- forced animation (step "force_anim"): the setter $C0:11EC gets A = id when Y = the actor's object
local forced = {}         -- obj -> anim
emu.addMemoryCallback(function()
  if not next(forced) then return end
  local s = emu.getState()
  local a = forced[s["cpu.y"] & 0xFF]
  if a and (s["cpu.a"] & 0xFF) ~= a then s["cpu.a"] = (s["cpu.a"] & 0xFF00) | a emu.setState(s) end
end, emu.callbackType.exec, 0xC011EC, 0xC011EC)

-- Louie type of the next hatch (step "louie_type"): A after the random number of asm/louies.asm louie_hatch
-- (LDA #5 / JSL $C0:1DEB at $E4:5E3C; its palette rule comes after, so a third type still becomes one of two)
local louie_type = nil
local function prg(a) return emu.read(((a >> 16) & 0x3F) * 0x10000 + (a & 0xFFFF), emu.memType.snesPrgRom) end
local HATCH = (prg(0xC4514B) << 16 | prg(0xC4514A) << 8 | prg(0xC45149)) + 6   -- JSL louie_hatch at $C4:5148
emu.addMemoryCallback(function()
  if louie_type then
    local s = emu.getState() s["cpu.a"] = (s["cpu.a"] & 0xFF00) | louie_type emu.setState(s)
    louie_type = nil
  end
end, emu.callbackType.exec, HATCH, HATCH)

-- scenario.profile = {from, to}: instructions per 16-byte code block between those scenario frames (finish())
local prof = nil
local prof_on = false
for _, scx in ipairs(PLAN.scenarios) do if scx.profile then prof_on = true end end
if prof_on then
  local function pcb(a)
    if prof and sc and sc.profile and k >= sc.profile[1] and k < sc.profile[2] then
      local b = a >> 4
      prof[b] = (prof[b] or 0) + 1
    end
  end
  emu.addMemoryCallback(pcb, emu.callbackType.exec, 0x800000, 0xFFFFFF)
  emu.addMemoryCallback(pcb, emu.callbackType.exec, 0x008000, 0x3FFFFF)
end

-- scenario.exec = {addresses}: "X k exec <addr> A=.. X=.." when the CPU runs them (research / checks of a routine)
local execs = {}
for _, scx in ipairs(PLAN.scenarios) do
  for _, a in ipairs(scx.exec or {}) do
    if not execs[a] then
      execs[a] = true
      emu.addMemoryCallback(function()
        if sc and sc.exec then
          local s = emu.getState()
          local sp = s["cpu.sp"]
          W(string.format("X %d exec %06X A=%04X X=%04X Y=%04X $AE=%02X $AF=%02X ret=%02X%02X%02X $BD=%02X%02X%02X sl=%d", k, a, s["cpu.a"], s["cpu.x"],
            s["cpu.y"], r(0xAE), r(0xAF), r(sp + 3), r(sp + 2), r(sp + 1), r(0xBF), r(0xBE), r(0xBD), s["ppu.scanline"] or -1))
        end
      end, emu.callbackType.exec, a, a)
    end
  end
end

-- scenario.dma = true: "Y k scanline forcedblank channel bbus size vram" for every DMA started ($420B), and
-- "Z k scanline name" when the NMI reaches stream_nmi / the stock strip upload (research of the vblank budget)
-- Always: "B k page owner vram" when SB5's VRAM queue ($C0:0540, static graphics) writes an OBJ page owned by an
-- animated object (bomber, Louie, egg: $1D00 owner below $7D), i.e. a static load over a live sprite.
local function dma_w(addr, v)
  if not sc or v == 0 then return end
  local st = emu.getState()
  if v & 1 ~= 0 and (st["cpu.pc"] & 0xFF00) == 0x0500 and (st["cpu.k"] & 0x3F) == 0 then
    local va = st["ppu.vramAddress"]
    if va >= 0x6000 and va < 0x8000 then
      local pg = (va - 0x6000) >> 9
      local own = emu.read(0x1D00 + pg, emu.memType.snesDebug)
      if own < 0x7D then W(string.format("B %d %d %02X %04X", k, pg, own, va)) end
    end
  end
  if not sc.dma then return end
  for ch = 0, 7 do
    if v & (1 << ch) ~= 0 then
      local b = 0x4300 + 16 * ch
      local size = emu.read(b + 5, emu.memType.snesDebug) | (emu.read(b + 6, emu.memType.snesDebug) << 8)
      W(string.format("Y %d %d %d %d %02X %d %04X %02X%04X %02X%04X", k, st["ppu.scanline"], st["ppu.forcedBlank"] and 1 or 0, ch,
        emu.read(b + 1, emu.memType.snesDebug), size == 0 and 65536 or size, st["ppu.vramAddress"], st["cpu.k"], st["cpu.pc"],
        emu.read(b + 4, emu.memType.snesDebug), emu.read(b + 2, emu.memType.snesDebug) | (emu.read(b + 3, emu.memType.snesDebug) << 8)))
    end
  end
end
emu.addMemoryCallback(dma_w, emu.callbackType.write, 0x420B, 0x420B)
emu.addMemoryCallback(dma_w, emu.callbackType.write, 0x80420B, 0x80420B)
for name, a in pairs({nmi_stream = 0xC0F41D, stock = 0xC56AAF, oam_build = 0xC0152E, queue = 0xC56A6B, resolve = 0xC01289, mainloop = 0xC00B4A}) do
  emu.addMemoryCallback(function()
    if sc and sc.dma then W(string.format("Z %d %d %s", k, emu.getState()["ppu.scanline"], name)) end
  end, emu.callbackType.exec, a, a)
end

-- stage forcing (fixture.stage): the first stage id written to $1031 is replaced
local stage_forced = phase == "load"   -- (a loaded fixture is already in its stage)
local function force(a, v)
  if FX.stage and not stage_forced and v >= 0x0D and v < 0x74 then
    stage_forced = true
    for _, seat in ipairs(FX.absent or {}) do wr(0x012C, r(0x012C) & ~(1 << seat)) end   -- out of the stage (co-op !pmask)
    return FX.stage
  end
end
emu.addMemoryCallback(force, emu.callbackType.write, 0x1031, 0x1031)
emu.addMemoryCallback(force, emu.callbackType.write, 0x7E1031, 0x7E1031)

-- fixture.mounts[seat + 1] = Louie type 0-5 (-1 none): the seat starts the stage on it, as with a Louie kept from
-- the stage before ($C4:2BF2: $1782 + seat bit 7, the Louie's character in $16C2 + seat + $0128)
if FX.mounts then
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local seat = s["cpu.x"] & 0xFF
    local t = FX.mounts[seat + 1]
    if seat < 4 and t and t >= 0 then
      wr(0x1782 + seat, r(0x1782 + seat) | 0x80)
      wr(0x16C2 + seat + r(0x0128), t)
    end
  end, emu.callbackType.exec, 0xC42BF2, 0xC42BF2)
end

-- ---------------------------------------------------------------- pose dumps
local posef = nil
local function pose_dump(list)
  local t = {}
  for _, actor in ipairs(list) do
    local obj = r(0x17FA + actor)
    local page = 255
    for i = 0, 15 do if obj ~= 0xFF and r(0x1D00 + i) == obj then page = i end end
    local o = obj == 0xFF and 0 or obj
    t[#t + 1] = string.char(actor, obj, page, r(0x049F + o), r(0x079F + o), r(0x06DF + o),
                            r(0x055F + o), r(0x0560 + o), r(0x05BF + o), r(0x05C0 + o))   -- (+ screen x, y)
  end
  local oam = {}
  for i = 0, 543 do oam[#oam + 1] = string.char(emu.read(i, emu.memType.snesSpriteRam)) end
  local vr = {}
  for i = 0, 16 * 1024 - 1 do vr[#vr + 1] = string.char(emu.read(0xC000 + i, emu.memType.snesVideoRam)) end
  posef:write(string.char(#list), table.concat(t), table.concat(oam), table.concat(vr))
end

-- ---------------------------------------------------------------- steps
-- step = {frame, op, ...}; ops:
--   pad seat "a+right" n       hold for n frames
--   poke addr val              WRAM ($7E:addr; addr >= $10000 = $7F bank)
--   pokew addr word
--   cell c v                   $1052 + c = v (static collision)
--   item seat item [dc]        puts item `item` on the seat's cell + dc (item map $145A, $1152 bit 7)
--   place seat x y             moves the seat's object to cell (x, y)
--   read name addr n           logs n bytes (V line)
--   readcg name idx n          logs CGRAM colors idx .. idx+n-1
--   readoam name               logs the OAM (544 bytes)
--   lit name                   logs the screen brightness (0 = forced blank)
--   wlog addr [n]              logs every later write to $7E:addr .. +n-1 with its PC (W lines, raw in Log.msgs)
--   force_anim actor id        forces animation id on the actor (nil id = stop)
--   invincible 0/1
--   kill                       $1D50 = 0 + the clear check (stage_test.lua KILL)
--   burn [n [actor]]           for n frames (20) a flame ($05) on the cell of every enemy actor (5-23, not mounts) or of
--                              that actor only
--   evict row                  enemies on map rows <= row moved to row 11 (same column)
--   louie_type n               the next egg hatches Louie type n (0-6)
--   beyond n                   the n cells past the last align's enemy cleared (not pillars)
--   blast seat cell            the seat drops a bomb in line with `cell` (nearest free cell; soft blocks between cleared)
--   door seat                  the seat stands on World 1's exit door
--   burn_clown n               n frames of flames around 1-7's clown
--   read7e name addr n         V line, n bytes of $7E:addr (WRAM above $1FFF)
--   shot name                  screenshot QA_OUT_<scenario>_<name>.png
--   dump name                  VRAM / CGRAM / OAM / WRAM $0000-$1FFF to QA_OUT_<scenario>_<name>.dump (tools/qa/dump.py)
--   show_item cell item        a visible item on the cell (SB5's $C5:4557)
local killing = false
local burning = 0
local burnt = {}           -- cell -> value before the flame
local burn_actor = nil
local function place(seat, x, y)
  local obj = r(0x17FA + seat)
  if obj == 0xFF then return end
  local px, py = (x * 16 - rw(0x1D3B)) & 0xFFFF, (y * 16 - rw(0x1D3D)) & 0xFFFF   -- (cell = (x + 8) >> 4)
  wr(0x055F + obj, px) wr(0x0560 + obj, px >> 8)
  wr(0x05BF + obj, py) wr(0x05C0 + obj, py >> 8)
end
local OPS = {}
function OPS.pad(st) pad(st[3], st[4]) end      -- (held every frame of [f, f+n), see run_steps)
function OPS.poke(st) if st[3] >= 0x10000 then wm(0x7F0000 + (st[3] & 0xFFFF), st[4]) else wr(st[3], st[4]) end end
function OPS.pokew(st) wr(st[3], st[4]) wr(st[3] + 1, st[4] >> 8) end
function OPS.cell(st) wr(0x1052 + st[3], st[4]) end
function OPS.item(st)
  local c = cell_of(st[3])
  if st[5] then c = c + st[5] end
  wr(0x145A + c, st[4]) wr(0x1152 + c, r(0x1152 + c) | 0x80)
end
function OPS.place(st) place(st[3], st[4], st[5]) end
-- evict row: every enemy actor (5 to $198C, not a mount) on map rows <= row moves to the bottom row (row 11), same
-- column (actor x/y, cell $16AA, its object; frozen by the clock first: the HUD tests' riders next to one lose
-- their Louie)
function OPS.evict(st)
  local mo = r(0x0128)
  for a = 5, r(0x198C) do
    local mount = a >= mo and a < mo + 5
    local obj = r(0x17FA + a)
    if not mount and obj ~= 0xFF and r(0x16C2 + a) ~= 0 and (r(0x16AA + a) >> 4) <= st[3] then
      local c = r(0x16AA + a)
      local y = 11 * 16
      local dy = y - r(0x1872 + a)
      wr(0x1872 + a, y) wr(0x188A + a, 0)
      wr(0x16AA + a, (11 << 4) | (c & 15))
      wr(0x1152 + c, r(0x1152 + c) & ~0x10)
      local py = (r(0x05BF + obj) | (r(0x05C0 + obj) << 8)) + dy
      wr(0x05BF + obj, py) wr(0x05C0 + obj, py >> 8)
    end
  end
end
function OPS.read(st) W(string.format("V %d %s %s", k, st[3], hexs(st[4] >= 0x10000 and (0x7F0000 + (st[4] & 0xFFFF)) or st[4], st[5], st[4] >= 0x10000 and emu.memType.snesMemory or nil))) end
-- spawn: the start state of tools/coop4_check.py spawn_safety ("V k spawn <text>", lines joined by "|")
function OPS.spawn(st)
  local t = {"map " .. hexs(0x1052, 256), "keep " .. hexs(0x2700, 256)}
  local seats, en = {}, {}
  for seat = 0, 3 do
    local o = r(0x17FA + seat)
    seats[#seats + 1] = string.format("%02X", (o < 0x80 and r(0x15A2 + seat) < 0x80) and cell_of(seat) or 0xFF)
  end
  for a = 5, r(0x198C) do
    if r(0x17FA + a) < 0x80 and r(0x16C2 + a) ~= 0 then en[#en + 1] = string.format("%02X:%02X", cell_of(a), r(0x16C2 + a)) end
  end
  t[#t + 1] = "seats " .. table.concat(seats, " ")
  local pts = {}               -- each seat's spawn cell ($4E8D x / $4EA5 y: where a revive with Start starts looking)
  for seat = 0, 3 do pts[#pts + 1] = string.format("%02X", (r(0x4EA5 + seat) << 4 | r(0x4E8D + seat)) & 0xFF) end
  t[#t + 1] = "points " .. table.concat(pts, " ")
  t[#t + 1] = "enemies " .. table.concat(en, " ")
  W(string.format("X %d spawn %s", k, table.concat(t, "|")))
end
function OPS.lit(st)          -- lit name: V line, 1 byte = screen brightness (0 while forced blank)
  local c = emu.getState()
  W(string.format("V %d %s %02X", k, st[3], c["ppu.forcedBlank"] and 0 or (c["ppu.screenBrightness"] or 0)))
end
function OPS.read7e(st) W(string.format("V %d %s %s", k, st[3], hexs(0x7E0000 + st[4], st[5], emu.memType.snesMemory))) end
function OPS.readoam(st) W(string.format("V %d %s %s", k, st[3], hexs(0, 544, emu.memType.snesSpriteRam))) end
function OPS.spcpc(st)        -- spcpc name: V line, the SPC700 PC (2 bytes, big endian) and its ports 0-3 as the CPU sees them
  local c = emu.getState()
  W(string.format("V %d %s %04X%02X%02X%02X%02X", k, st[3], c["spc.pc"] or 0, emu.read(0xF4, emu.memType.spcMemory), emu.read(0xF5, emu.memType.spcMemory), emu.read(0xF6, emu.memType.spcMemory), emu.read(0xF7, emu.memType.spcMemory)))
end
-- dsplog: from its frame on, every S-DSP write "SW k <spc cycle> <reg> <value>", and once the S-DSP / ARAM
-- at that moment ("SD <cycle>" + QA_OUT_<scenario>_aram.bin / _dsp.bin: tools/spc_render.py renders the log)
local dsp_on = false
function OPS.dsplog(st)
  dsp_on = true
  local t = {} for i = 0, 65535 do t[#t + 1] = string.char(emu.read(i, emu.memType.spcRam)) end
  local h = io.open(OUTP .. "_" .. sc.name .. "_aram.bin", "wb") h:write(table.concat(t)) h:close()
  local d = {} for i = 0, 127 do d[#d + 1] = string.char(emu.read(i, emu.memType.spcDspRegisters)) end
  h = io.open(OUTP .. "_" .. sc.name .. "_dsp.bin", "wb") h:write(table.concat(d)) h:close()
  W(string.format("SD %d", emu.getState()["spc.cycle"]))
end
do
  local want = false
  for _, s in ipairs(PLAN.scenarios) do
    for _, st in ipairs(s.steps or {}) do if st[2] == "dsplog" then want = true end end
  end
  if want then
    emu.addMemoryCallback(function(a, v)
      if not sc or not dsp_on then return end
      W(string.format("SW %d %d %02X %02X", k, emu.getState()["spc.cycle"], emu.read(0xF2, emu.memType.spcMemory), v))
    end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
  end
end
-- spcwatch {k, "spcwatch", lo, hi, voice}: from its frame on, every SPC write to ARAM lo..hi
-- "SA k addr brr" (brr = the S-DSP voice's current BRR block address) and, every frame, "SB k brr"
-- (the SB6 stage voices' ring, features/voice_sfx.py)
local spcw = nil
function OPS.spcwatch(st) spcw = st end
do
  local want = nil
  for _, s in ipairs(PLAN.scenarios) do
    for _, st in ipairs(s.steps or {}) do if st[2] == "spcwatch" then want = st end end
  end
  if want then
    local key = "spc.dsp.voices[" .. want[5] .. "].brrAddress"
    emu.addMemoryCallback(function(a)
      if not sc or not spcw then return end
      W(string.format("SA %d %04X %04X", k, a & 0xFFFF, emu.getState()[key]))
    end, emu.callbackType.write, want[3], want[4], emu.cpuType.spc, emu.memType.spcMemory)
    emu.addEventCallback(function()
      if sc and spcw then W(string.format("SB %d %04X", k, emu.getState()[key])) end
    end, emu.eventType.endFrame)
  end
end
-- wlog steps: the callbacks are set up when the script loads (Mesen ignores ones added later); each logs
-- from its step's frame on, in the scenarios that have it
local wlog_on = {}
function OPS.wlog(st) wlog_on[st[3]] = true end
do
  local seen = {}
  for _, s in ipairs(PLAN.scenarios) do
    for _, st in ipairs(s.steps or {}) do
      if st[2] == "wlog" and not seen[st[3]] then
        seen[st[3]] = true
        local base = st[3]
        local function cb(a, v)
          if not sc or not wlog_on[base] then return end
          local c = emu.getState()
          W(string.format("W %d %04X %02X %02X:%04X A=%04X X=%04X Y=%04X", k, a & 0xFFFF, v, c["cpu.k"], c["cpu.pc"], c["cpu.a"], c["cpu.x"], c["cpu.y"]))
        end
        local n = (st[4] or 1) - 1
        for _, bank in ipairs(base < 0x2000 and {0x00, 0x7E, 0x80} or {0x7E}) do      -- (low RAM: every mirror the code uses)
          emu.addMemoryCallback(cb, emu.callbackType.write, bank * 0x10000 + base, bank * 0x10000 + base + n)
        end
      end
    end
  end
end
-- vramlate: from its step on, every DMA into VRAM ($4301 = $18 / $19) started on a visible line (1-224, the
-- screen on: $2100 bit 7 clear) is logged "DL k line pc": its writes are lost on the real console
local vramlate_on = false
function OPS.vramlate(st) vramlate_on = true end
do
  local want = false
  for _, s in ipairs(PLAN.scenarios) do
    for _, st in ipairs(s.steps or {}) do if st[2] == "vramlate" then want = true end end
  end
  if want then
    local inidisp = 0x80
    emu.addMemoryCallback(function(a, v) inidisp = v end, emu.callbackType.write, 0x2100, 0x2100)
    emu.addMemoryCallback(function(a, v) inidisp = v end, emu.callbackType.write, 0x802100, 0x802100)
    local function cb(a, v)
      if not sc or not vramlate_on then return end
      for ch = 0, 7 do
        if v & (1 << ch) ~= 0 then
          local b = emu.read(0x4301 + 16 * ch, emu.memType.snesDebug)
          local line = emu.getState()["ppu.scanline"]
          if (b == 0x18 or b == 0x19) and line >= 1 and line <= 224 and inidisp & 0x80 == 0 then
            W(string.format("DL %d %d %06X", k, line, emu.getState()["cpu.k"] << 16 | emu.getState()["cpu.pc"]))
          end
        end
      end
    end
    emu.addMemoryCallback(cb, emu.callbackType.write, 0x420B, 0x420B)
    emu.addMemoryCallback(cb, emu.callbackType.write, 0x80420B, 0x80420B)
  end
end
function OPS.readcg(st) W(string.format("V %d %s %s", k, st[3], hexs(st[4] * 2, st[5] * 2, emu.memType.snesCgRam))) end
function OPS.force_anim(st) local obj = r(0x17FA + st[3]) if obj ~= 0xFF then forced[obj] = st[4] end end
function OPS.unforce(st) forced = {} end
function OPS.invincible(st) invincible = st[3] == 1 end
function OPS.kill(st) wr(0x1D50, 0) killing = true end
function OPS.burn(st) burning = st[3] or 20 burn_actor = st[4] end
local clown_burn = 0
function OPS.burn_clown(st) clown_burn = st[3] or 20 end
local extra_pads = {}       -- {seat, buttons, until k}
function OPS.blast(st)      -- blast seat cell: the seat stands next to `cell` (a free neighbour) and drops a bomb
  local c = st[4]
  for dist = 1, 8 do                -- the nearest free cell in line (soft blocks between are cleared: no picture)
    for _, d in ipairs({-16, 16, -1, 1}) do
      local n = c + d * dist
      local ok = n >= 0 and n < 256 and r(0x1052 + n) == 0
      for j = 1, dist - 1 do if r(0x1052 + c + d * j) & 0x80 ~= 0 then ok = false end end
      if ok then
        for j = 1, dist - 1 do wr(0x1052 + c + d * j, 0) end
        if r(0x17CA + st[3]) < dist then wr(0x17CA + st[3], dist) end
        place(st[3], n & 15, n >> 4)
        extra_pads[#extra_pads + 1] = {st[3], "a", k + 4, k + 7}
        return
      end
    end
  end
  W("X " .. k .. " blast: no free cell next to " .. c)
end
function OPS.door_blast(st) OPS.blast({st[1], "blast", st[3], (rm(0x7FFB11) << 4) | rm(0x7FFB10)}) end
local music = nil           -- step "music": {frames, frames with a voice sounding, SPC PC pages seen}
function OPS.music(st) music = {0, 0, {}, 0} end
local function music_flush()   -- "V k music_stats": frames, frames with a voice sounding, SPC PC pages / 4, key-ons
  if not music then return end
  local pages = {}
  for pg = 0, 255 do pages[#pages + 1] = string.format("%02X", math.min(255, (music[3][pg] or 0) // 4)) end
  W(string.format("V %d music_stats %02X%02X%02X%02X%s%02X%02X", k, music[1] & 0xFF, music[1] >> 8, music[2] & 0xFF,
    music[2] >> 8, table.concat(pages), music[4] & 0xFF, music[4] >> 8))
  music = nil
end
function OPS.music_end(st) music_flush() end     -- step "music_end": the stats of the frames since "music"
function OPS.door(st)       -- door seat: the seat stands on World 1's exit door ($7F:FB10 x, y; asm/world1.asm)
  place(st[3], rm(0x7FFB10), rm(0x7FFB11))
end
-- regwatch: "RW k scanline pc addr value" for every CPU write to the window / color math registers ($2123-$2133),
-- HDMAEN ($420C) and channel 7's registers ($4370-$437A) from frame st[1] to st[3] (research)
local rw_until, rw_on = -1, false
function OPS.regwatch(st)
  rw_until = st[3]
  if rw_on then return end
  rw_on = true
  local function cb(a, v)
    if k > rw_until then return end
    local s = emu.getState()
    W(string.format("RW %d %d %02X%04X %04X %02X", k, s["ppu.scanline"], s["cpu.k"], s["cpu.pc"], a & 0xFFFF, v))
  end
  emu.addMemoryCallback(cb, emu.callbackType.write, 0x2123, 0x2133)
  emu.addMemoryCallback(cb, emu.callbackType.write, 0x420C, 0x420C)
  emu.addMemoryCallback(cb, emu.callbackType.write, 0x4370, 0x437A)
end
-- watchw a0 a1 until: "WW k scanline pc addr value" for every CPU write to WRAM a0-a1 (bank-00 addresses)
-- until frame `until` (research)
function OPS.watchw(st)
  local stop = st[5]
  emu.addMemoryCallback(function(a, v)
    if k > stop then return end
    local s = emu.getState()
    W(string.format("WW %d %d %02X%04X %04X %02X", k, s["ppu.scanline"], s["cpu.k"], s["cpu.pc"], a & 0xFFFF, v))
  end, emu.callbackType.write, st[3], st[4])
end
-- caller a until: "CA k pc ret" at each execution of a (24-bit) until frame `until`: the JSL return address
-- (stack bytes S+1..S+3) and the one below it (research)
function OPS.caller(st)
  local stop = st[4]
  emu.addMemoryCallback(function()
    if k > stop then return end
    local s = emu.getState()
    local sp = s["cpu.sp"]
    local b = {}
    for i = 1, 9 do b[i] = emu.read(sp + i, emu.memType.snesDebug) end
    W(string.format("CA %d %06X %02X%02X%02X %02X%02X%02X %02X%02X%02X", k, st[3], b[3], b[2], b[1], b[6], b[5], b[4], b[9], b[8], b[7]))
  end, emu.callbackType.exec, st[3], st[3])
end
-- hdmawatch until: "HL k scanline value" for every CPU write to HDMAEN ($420C) on a visible line (0-224) until
-- frame `until`: the NMI ending after the HDMA init of line 0 (an HDMA channel runs uninitialised that frame)
function OPS.hdmawatch(st)
  local stop = st[3]
  emu.addMemoryCallback(function(a, v)
    if k > stop then return end
    local line = emu.getState()["ppu.scanline"]
    if line <= 224 then W(string.format("HL %d %d %02X", k, line, v)) end
  end, emu.callbackType.write, 0x420C, 0x420C)
end
function OPS.shot(st) local h = io.open(OUTP .. "_" .. sc.name .. "_" .. st[3] .. ".png", "wb") h:write(emu.takeScreenshot()) h:close() end
-- dump name: QA_OUT_<scenario>_<name>.dump = "QAD1" + VRAM (64 KB) + CGRAM (512) + OAM (544) + WRAM $0000-$1FFF (8 KB)
--   + BG1SC, BG2SC, BG12NBA, BG34NBA, BG3SC, BGMODE as last written (the field's BG2SC is in WRAM $0369, the scrolls in $0331-$0339)
local ppureg = {[0x05] = 0, [0x07] = 0, [0x08] = 0, [0x09] = 0, [0x0B] = 0, [0x0C] = 0}
local function ppu_w(addr, v) ppureg[addr & 0xFF] = v end
emu.addMemoryCallback(ppu_w, emu.callbackType.write, 0x002105, 0x00210C)
emu.addMemoryCallback(ppu_w, emu.callbackType.write, 0x802105, 0x80210C)
function OPS.dump(st)
  local h = io.open(OUTP .. "_" .. sc.name .. "_" .. st[3] .. ".dump", "wb")
  local t = {"QAD1"}
  local function chunk(mem, a, n)
    local c = {}
    for i = 0, n - 1 do c[#c + 1] = string.char(emu.read(a + i, mem)) end
    t[#t + 1] = table.concat(c)
  end
  chunk(emu.memType.snesVideoRam, 0, 0x10000)
  chunk(emu.memType.snesCgRam, 0, 512)
  chunk(emu.memType.snesSpriteRam, 0, 544)
  chunk(emu.memType.snesWorkRam, 0, 0x2000)
  t[#t + 1] = string.char(ppureg[0x07], ppureg[0x08], ppureg[0x0B], ppureg[0x0C], ppureg[0x09], ppureg[0x05])
  h:write(table.concat(t))
  h:close()
end
function OPS.louie_type(st) louie_type = st[3] end
function OPS.mark(st) W(string.format("X %d mark %s", k, st[3])) end

local function run_steps()
  inj = {}
  for _, p in ipairs(extra_pads) do if k >= p[3] and k < p[4] then pad(p[1], p[2]) end end
  for _, st in ipairs(sc.steps or {}) do
    if st[2] == "pad" then
      if k >= st[1] and k < st[1] + (st[5] or 1) then OPS.pad(st) end
    elseif st[1] == k then
      local fn = OPS[st[2]]
      if fn then fn(st) else W("X " .. k .. " unknown op " .. tostring(st[2])) end
    end
  end
end

-- the clear check of a "kill" step (stage_test.lua): a stub calling JSL $C5:3B4E from the task runner
-- show_item cell item: SB5's visible item placement $C5:4557 (A = item, $AE = cell: $145A, $1052 = $10, $1152 bit 7,
-- the item's metatile on the field layer), one per pass of the task runner (queue)
local shows = {}
function OPS.show_item(st) shows[#shows + 1] = {st[3], st[4]} end
-- align seat way n: the seat stands n cells from a live enemy, the enemy that way (0 right, 1 down, 2 left, 3 up),
-- the cells between cleared ($1052); no other enemy in the seat's row or column. "V k align <seat cell><enemy cell>"
-- (FF: no enemy fits). For the magnet bomb's tests (enemies frozen by the clock first).
local last_align
function OPS.align(st)
  local seat, d, n = st[3], st[4], st[5]
  local dx, dy = ({1, 0, -1, 0})[d + 1], ({0, 1, 0, -1})[d + 1]
  local last = r(0x198C)
  local function alive(a) return r(0x17FA + a) < 0x80 and r(0x15A2 + a) < 0x80 end
  for a = 5, last do
    if alive(a) and r(0x16C2 + a) ~= 0 and r(0x16AA + a) == cell_of(a) then   -- (an enemy on its cell: not an egg)
      local c = cell_of(a)
      local ex, ey = c & 15, c >> 4
      local px, py = ex - n * dx, ey - n * dy
      local ok = px >= 1 and px <= 13 and py >= 1 and py <= 11 and (px % 2 == 1 or py % 2 == 1)
      if dy == 0 and py % 2 == 0 or dx == 0 and px % 2 == 0 then ok = false end   -- (a lane between pillars)
      local fx, fy = ex + 3 * dx, ey + 3 * dy        -- (room past the enemy: a push, the beyond cells)
      if fx < 1 or fx > 13 or fy < 1 or fy > 11 then ok = false end
      for b = 5, last do
        if ok and b ~= a and alive(b) then
          local cb = cell_of(b)
          for i = -1, n + 4 do       -- (another enemy on the lane, from behind the seat to past the enemy)
            if cb == (py + i * dy) * 16 + px + i * dx then ok = false end
          end
          local bx, by = cb & 15, cb >> 4     -- (nor near the seat in its row / column: a magnet bomb's other ways)
          if by == py and math.abs(bx - px) <= n + 1 or bx == px and math.abs(by - py) <= n + 1 then ok = false end
        end
      end
      if ok then
        for i = 0, n - 1 do wr(0x1052 + (py + i * dy) * 16 + px + i * dx, 0) end
        place(seat, px, py)
        last_align = {px, py, dx, dy, n}
        W(string.format("V %d align %02X%02X", k, py * 16 + px, ey * 16 + ex))
        return
      end
    end
  end
  -- none on a free lane: the first live enemy (frozen by the clock in the tests that align) moves to (7, 5)
  for a = 5, last do
    if alive(a) and r(0x16C2 + a) ~= 0 then
      local ex, ey = 7, 5
      local c0 = r(0x16AA + a)
      local ddx, ddy = ex * 16 - r(0x182A + a), ey * 16 - r(0x1872 + a)
      wr(0x182A + a, ex * 16) wr(0x1842 + a, 0) wr(0x1872 + a, ey * 16) wr(0x188A + a, 0)
      wr(0x16AA + a, ey * 16 + ex)
      wr(0x1152 + c0, r(0x1152 + c0) & ~0x10) wr(0x1152 + ey * 16 + ex, r(0x1152 + ey * 16 + ex) | 0x10)
      local obj = r(0x17FA + a)
      local ox = (r(0x055F + obj) | (r(0x0560 + obj) << 8)) + ddx
      local oy = (r(0x05BF + obj) | (r(0x05C0 + obj) << 8)) + ddy
      wr(0x055F + obj, ox) wr(0x0560 + obj, ox >> 8) wr(0x05BF + obj, oy) wr(0x05C0 + obj, oy >> 8)
      local px, py = ex - n * dx, ey - n * dy
      for i = 0, n - 1 do wr(0x1052 + (py + i * dy) * 16 + px + i * dx, 0) end
      place(seat, px, py)
      last_align = {px, py, dx, dy, n}
      W(string.format("V %d align %02X%02X", k, py * 16 + px, ey * 16 + ex))
      return
    end
  end
  W(string.format("V %d align FF", k))
end
-- beyond n: the n cells past the enemy of the last align (inside the field, not a pillar) cleared
function OPS.beyond(st)
  if last_align then
    local px, py, dx, dy, n = last_align[1], last_align[2], last_align[3], last_align[4], last_align[5]
    for i = n + 1, n + st[3] do
      local x, y = px + i * dx, py + i * dy
      if x >= 1 and x <= 13 and y >= 1 and y <= 11 and (x % 2 == 1 or y % 2 == 1) then wr(0x1052 + y * 16 + x, 0) end
    end
  end
end
-- soft_mid: a soft block ($30) 2 cells from the seat of the last align, toward its enemy
function OPS.soft_mid(st)
  if last_align then
    local px, py, dx, dy = last_align[1], last_align[2], last_align[3], last_align[4]
    wr(0x1052 + (py + 2 * dy) * 16 + px + 2 * dx, 0x30)
  end
end
local function kcb()
  if not killing and #shows > 0 then
    local c, it = shows[1][1], shows[1][2]
    table.remove(shows, 1)
    -- PHP / SEP #$30 / LDA #cell / STA $AE / LDA #item / JSL $C5:4557 / PLP / JML $C0:22F0
    local stub = {0x08, 0xE2, 0x30, 0xA9, c & 0xFF, 0x85, 0xAE, 0xA9, it & 0xFF, 0x22, 0x57, 0x45, 0xC5, 0x28,
                  0x5C, 0xF0, 0x22, 0xC0}
    for i, b in ipairs(stub) do wm(0x7FF000 + i - 1, b) end
    local s = emu.getState() s["cpu.k"] = 0x7F s["cpu.pc"] = 0xF000 emu.setState(s)
    return
  end
  if not killing then return end
  killing = false
  local stub = {0x08, 0xE2, 0x30, 0x22, 0x4E, 0x3B, 0xC5, 0x28, 0x5C, 0xF0, 0x22, 0xC0}
  for i, b in ipairs(stub) do wm(0x7FF000 + i - 1, b) end
  local s = emu.getState() s["cpu.k"] = 0x7F s["cpu.pc"] = 0xF000 emu.setState(s)
end
emu.addMemoryCallback(kcb, emu.callbackType.exec, 0xC022F0, 0xC022F0)

-- ---------------------------------------------------------------- scenario control
local function begin(i)
  sc_i, sc, k = i, PLAN.scenarios[i], 0
  if not sc then
    W("END")
    fin(0)
    return
  end
  watch, forced, invincible, runs, killing, extra_pads, burning, clown_burn, burnt = {}, {}, sc.invincible ~= false, 0, false, {}, 0, 0, {}
  dsp_on = false
  shows = {}
  wlog_on = {}
  spcw = nil
  W("S " .. sc.name)
  if sc.rec and sc.rec.pose then posef = io.open(OUTP .. "_" .. sc.name .. ".pose", "wb") end
  prof = sc.profile and {} or nil
end
local function finish()
  if prof then      -- scenario.profile: "J bank:addr>>4 n" instructions run per 16-byte block (research of the frame cost)
    for a, n in pairs(prof) do W(string.format("J %05X %d", a, n)) end
    prof = nil
  end
  music_flush()
  W("E " .. sc.name)
  if posef then posef:close() posef = nil end
  out:flush()
  sc = nil
  if sc_i < #PLAN.scenarios then want = "load" else begin(sc_i + 1) end
end

emu.addMemoryCallback(function()
  if want == "save" then
    saved = emu.createSavestate()
    if STATEF then
      local h = io.open(STATEF, "wb") h:write(saved) h:close()
      h = io.open(STATEF .. ".txt", "w") h:write(table.concat(bootv, string.char(10))) h:close()
    end
    for _, l in ipairs(bootv) do W(l) end
    want = nil
    W("X 0 fixture saved at frame " .. frame)
    begin(1)
  elseif want == "load" then
    if not saved then
      local h = io.open(STATEF, "rb") saved = h:read("a") h:close() W("X 0 fixture loaded")
      h = io.open(STATEF .. ".txt", "r")
      if h then W(h:read("a")) h:close() end
    end
    emu.loadSavestate(saved)
    want = nil
    begin(sc_i + 1)
  end
end, emu.callbackType.exec, 0xC00B4A, 0xC00B4A)

-- ---------------------------------------------------------------- boot + picker (only without a saved fixture)
local tphase, wait, held, hold = 0, 0, nil, 0
local pk = {seat = -1, t = 0, plan = nil}
local function press(b) held = b hold = 4 wait = 40 end
emu.addEventCallback(function()
  if phase == "boot" and hold > 0 and held then local t = {} t[held] = true emu.setInput(t, 0) end
end, emu.eventType.inputPolled)

local function seat_plan(s)
  local p = (FX.picks or {})[s + 1] or {c = s, k = 0}
  local seq = {}
  for _ = 1, p.c % 5 do seq[#seq + 1] = "right" end
  for _ = 1, p.c // 5 do seq[#seq + 1] = "down" end
  for _ = 1, p.k or 0 do seq[#seq + 1] = "r" end
  seq[#seq + 1] = "a"
  return seq
end

local lastmode = -1
bootv = {}               -- fixture facts measured while booting (kept next to the savestate, QA_STATE .. ".txt")
emu.addEventCallback(function()
  frame = frame + 1
  if phase == "load" then
    if frame == 2 then want = "load" sc_i = 0 phase = "run" end
    return
  end
  if phase == "boot" then
    if hold > 0 then hold = hold - 1 end
    local mode = r(0x1031)
    if mode ~= lastmode then W(string.format("X %d boot mode %02X", frame, mode)) lastmode = mode end
    inj = {}
    if mode == 4 and rm(0x7FFC00) == 2 then                -- SB6 picker ready: seat $7F:FC03 chooses
      local s = rm(0x7FFC03)
      if s ~= pk.seat then pk.seat, pk.t, pk.plan = s, 0, seat_plan(s) end
      pk.t = pk.t + 1
      local i = (pk.t - 48) // 24 + 1                       -- one press every 24 frames, held 4
      if pk.t >= 48 and pk.t % 24 < 4 and pk.plan[i] then
        pad(s, pk.plan[i])
        if i == #pk.plan and s == (FX.players or 4) - 1 then pk.last = frame end
      end

    elseif wait > 0 then
      wait = wait - 1
    elseif mode ~= 4 then
      local N = FX.players or 4
      if frame > 700 and tphase == 0 and mode ~= 3 and r(0x1036) == 0 then press("start") tphase = 1
      elseif tphase == 1 and r(0x1036) == 1 then tphase = 2
      elseif tphase == 2 then if r(0x1032) < N - 1 then press("down") else tphase = 3 end
      elseif tphase == 3 then press("start") tphase = 4
      elseif tphase == 4 and mode == 3 and frame % 60 == 0 then press("start")
      elseif tphase == 1 and r(0x1036) == 0 and frame % 60 == 0 then press("start") end
    end
    if pk.last and frame == pk.last + 40 then         -- every seat confirmed: the player row's colors (OBJ palettes 0-3)
      bootv[#bootv + 1] = "V 0 picker_cg " .. hexs(0x100, 0x80, emu.memType.snesCgRam)
    end
    if frame == 800 and mode == 2 then                 -- title: the music streams ($0100 = 1, SPC PC $70xx)
      bootv[#bootv + 1] = string.format("V 0 title_music %02X%02X", r(0x0100), (emu.getState()["spc.pc"] >> 8) & 0xFF)
    end
    if mode == 4 and rm(0x7FFC00) == 2 and not pk.chosen then  -- the picker (first): its music ($010A = 3)
      pk.chosen = frame
    end
    if pk.chosen and frame == pk.chosen + 60 then
      bootv[#bootv + 1] = string.format("V 0 picker_music %02X%02X", r(0x010A), r(0x0100))
    end
    if mode == 3 and pk.last and not pk.menu then pk.menu = frame end   -- the save files, after the picker
    if pk.menu and frame == pk.menu + 120 and mode == 3 then  -- Normal Game menu: save menu music ($010A = 2)
      bootv[#bootv + 1] = string.format("V 0 menu_music %02X", r(0x010A))
    end
    if not stage0 and mode >= 0x0D and mode < 0x74 and (not FX.stage or mode == FX.stage) then stage0 = frame end
    if stage0 and frame - stage0 == (FX.ready or 300) then want = "save" phase = "run" end
    if frame > 16000 then W("X " .. frame .. " boot timeout mode " .. string.format("%02X", mode)) fin(1) end
    return
  end
  -- run
  if not sc then return end
  run_steps()
  if burning > 0 then
    burning = burning - 1
    local mo = r(0x0128)
    for x = (burn_actor and 0 or 4), 23 do
      local mount = x >= mo and x < mo + 5
      local hit = burn_actor and x == burn_actor or (not burn_actor and x >= 5 and not mount and r(0x16C2 + x) ~= 0)
      if hit and r(0x17FA + x) ~= 0xFF then
        local c = r(0x16AA + x)
        if not burnt[c] then burnt[c] = r(0x1052 + c) end
        wr(0x1052 + c, 0x05)
      end
    end
    if burning == 0 then for c, v in pairs(burnt) do wr(0x1052 + c, v) end burnt = {} end
  end
  if clown_burn > 0 then               -- flames on the free cells around the clown's center ($7F:E00B x, $7F:E00D y)
    clown_burn = clown_burn - 1
    local c = (((rm(0x7FE00B) + 8) & 0xFF) >> 4) | (((rm(0x7FE00D) + 8) & 0xF0))
    for _, d in ipairs({0, 1, -1, 16, -16}) do
      local n = c + d
      if n >= 0 and n < 256 and (burnt[n] ~= nil or r(0x1052 + n) == 0) then
        if burnt[n] == nil then burnt[n] = r(0x1052 + n) end
        wr(0x1052 + n, 0x05)
      end
    end
    if clown_burn == 0 then for n, v in pairs(burnt) do wr(0x1052 + n, v) end burnt = {} end
  end
  -- recorders (end of frame k)
  local mo = r(0x0128)
  if mo == 0 or mo > 0x20 then mo = r(0x1CBF) end
  local list = {0, 1, 2, 3, 4}
  for s = 0, 4 do list[#list + 1] = s + mo end
  for _, a in ipairs(sc.watch or {}) do list[#list + 1] = a end
  for _, a in ipairs(list) do
    local obj = r(0x17FA + a)
    local w = watch[a]
    local an = obj ~= 0xFF and r(0x079F + obj) or 0
    if not w or w[1] ~= obj then W(string.format("O %d %d %02X", k, a, obj)) end
    if obj ~= 0xFF and (not w or w[2] ~= an or w[1] ~= obj) then W(string.format("A %d %d %02X", k, a, an)) end
    watch[a] = {obj, an}
  end
  for s = 0, 3 do
    local d = r(0x15A2 + s) & 0x80
    if d ~= 0 and not (watch["d" .. s]) then W(string.format("D %d %d", k, s)) end
    watch["d" .. s] = d ~= 0
  end
  local m = r(0x1031)
  if m ~= watch.mode then W(string.format("M %d %02X", k, m)) watch.mode = m end
  if k % 60 == 59 then W(string.format("F %d %d", k, runs)) runs = 0 end
  if posef then pose_dump(sc.rec.pose) end
  if music then
    music[1] = music[1] + 1
    local any = false
    music[5] = music[5] or {}
    for v = 0, 7 do
      local e = emu.read(v * 16 + 8, emu.memType.spcDspRegisters)
      if e > 0 then any = true end
      if e >= (music[5][v] or 0) + 0x10 then music[4] = music[4] + 1 end     -- an attack: a note started
      music[5][v] = e
    end
    if any then music[2] = music[2] + 1 end
    local pg = (emu.getState()["spc.pc"] >> 8) & 0xFF
    music[3][pg] = (music[3][pg] or 0) + 1
  end
  k = k + 1
  if k >= sc.len then finish() end
end, emu.eventType.endFrame)
