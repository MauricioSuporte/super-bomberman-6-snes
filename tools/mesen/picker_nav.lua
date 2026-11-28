-- Boots the hack, opens the Normal Game picker, presses PLAN there and waits in stage 1-1.
-- env: SB6_PLAYERS, SB6_OUT (prefix of the log/screenshots), PLAN (comma list of P1 buttons in the picker:
-- "a" = Bomberman, "right,a" = character 1, 5 cells per row: "down,a" = character 5; r/l change the color;
-- with SB6_PLAYERS > 1 every seat confirms in turn, so repeat "a" per seat), STAGE_WAIT (frames in the stage), CANCEL=1
local N = tonumber(os.getenv("SB6_PLAYERS") or "1")
local OUT = os.getenv("SB6_OUT") or "build/picker_nav"
local PLAN = {} for k in string.gmatch(os.getenv("PLAN") or "r,r,right,a", "[^,]+") do PLAN[#PLAN+1]=k end
local f=0 local log={} local phase=0 local btn=nil local hold=0 local wait=0
local function r(a) return emu.read(a,emu.memType.snesWorkRam) end
local function hx(a,n) local t={} for i=0,n-1 do t[#t+1]=string.format("%02X",r(a+i)) end return table.concat(t," ") end
local function L(s) log[#log+1]=s end
local function press(b) btn=b hold=4 wait=40 end
local function shot(name) local h=io.open(OUT.."_"..name..".png","wb") h:write(emu.takeScreenshot()) h:close() end
local function pc9() return r(0xC90)|(r(0xCB8)<<8)|(r(0xCE0)<<16) end
local function cg(i0,n) local t={} for i=i0,i0+n-1 do t[#t+1]=string.format("%02X%02X",emu.read(i*2+1,emu.memType.snesCgRam),emu.read(i*2,emu.memType.snesCgRam)) end return table.concat(t," ") end
local function fin() local h=io.open(OUT..".txt","w") h:write(table.concat(log,"\n")) h:close() emu.stop(0) end
-- title: pads 3/4 plugged in (the testrunner has no multitap; the players menu stops at the pads plugged in)
emu.addMemoryCallback(function() if r(0x1031)==2 then emu.write(0x25,1,emu.memType.snesWorkRam) emu.write(0x26,1,emu.memType.snesWorkRam) end end, emu.callbackType.exec, 0xC00AF9, 0xC00AF9)
emu.addEventCallback(function() if hold>0 and btn then local t={} t[btn]=true emu.setInput(t,0) end end, emu.eventType.inputPolled)
-- P2_PROBE=1: in the picker, pad 2 presses every button in turn (20 frames apart), logging BG1 map rows 5-10 of
-- the top row's right half after each (research: SB5's stock picker drawing over ours)
local P2B={"start","a","b","x","y","select","l","r","up","down","left","right"}
local p2i, p2hold = 0, 0
emu.addEventCallback(function() if p2hold>0 then local t={} t[P2B[p2i]]=true emu.setInput(t,1) end end, emu.eventType.inputPolled)
-- VRAM_WATCH=1: "vw f line pc addr value" for VRAM writes to BG1 map rows 6-9, columns 20-27 (the 2P slot)
if os.getenv("VRAM_WATCH") then
  local seen = 0
  emu.addMemoryCallback(function(a, v)
    local w = a >> 1
    local r, c = (w - 0x3000) >> 5, (w - 0x3000) & 31
    if r >= 6 and r <= 9 and c >= 20 and c <= 27 and seen < 4000 then
      seen = seen + 1
      local s = emu.getState()
      log[#log+1] = string.format("vw %d %d %02X%04X %04X %02X", f, s["ppu.scanline"], s["cpu.k"], s["cpu.pc"], a, v)
    end
  end, emu.callbackType.write, 0x6000, 0x6400, emu.cpuType.snes, emu.memType.snesVideoRam)
  local function dw(a, v)
    local s = emu.getState()
    for ch = 0, 7 do
      if v & (1 << ch) ~= 0 then
        local b = 0x4300 + 16 * ch
        local bb = emu.read(b + 1, emu.memType.snesDebug)
        local n = emu.read(b + 5, emu.memType.snesDebug) | (emu.read(b + 6, emu.memType.snesDebug) << 8)
        if n == 0 then n = 65536 end
        local va = s["ppu.vramAddress"]
        if (bb == 0x18 or bb == 0x19) and va < 0x3140 and va + n // 2 > 0x30D4 then
          log[#log+1] = string.format("dma %d line %d pc %02X%04X ch %d va %04X n %d src %02X%04X", f, s["ppu.scanline"], s["cpu.k"], s["cpu.pc"], ch, va, n,
            emu.read(b + 4, emu.memType.snesDebug), emu.read(b + 2, emu.memType.snesDebug) | (emu.read(b + 3, emu.memType.snesDebug) << 8))
        end
      end
    end
  end
  emu.addMemoryCallback(dw, emu.callbackType.write, 0x420B, 0x420B)
  emu.addMemoryCallback(dw, emu.callbackType.write, 0x80420B, 0x80420B)
end
local st="nav" local pt=0 local step=1 local lastmode=-1 local stage=nil local picks=0
emu.addEventCallback(function()
  f=f+1
  if hold>0 then hold=hold-1 end
  local mode=r(0x1031)
  if mode~=lastmode then L(string.format("f=%d mode %02X pc9=%06X st=%s",f,mode,pc9(),st)) lastmode=mode end
  if st=="nav" then
    if mode==4 then st="pick" pt=0 picks=picks+1 L("picker opened f="..f)
    elseif wait>0 then wait=wait-1 else
      if f>700 and phase==0 and mode~=3 and r(0x1036)==0 then press("start") phase=1
      elseif phase==1 and r(0x1036)==1 then phase=2
      elseif phase==2 then if r(0x1032)<N-1 then press("down") else phase=3 end
      elseif phase==3 then press("start") phase=4
      elseif phase==4 and mode==3 and f%60==0 then press("start")
      elseif phase==1 and r(0x1036)==0 and f%60==0 then press("start") end
    end
    if mode>=0x0D and mode<0x74 and not stage then stage=f L("stage reached mode "..string.format("%02X",mode)) end
    if stage and (f-stage==560 or f-stage==600) then shot("stage"..(f-stage)) L("obj "..hx(0x17FA,6).." st "..hx(0x15A2,5).." x "..hx(0x1602,4)) end
    if stage and f-stage==(tonumber(os.getenv("STAGE_WAIT") or "520")) then shot("stage") L("chars "..hx(0x16C2,5).." pal "..hx(0x16DA,5).." 1D24/25="..hx(0x1D24,2).." count="..hx(0x129,1).." cg90="..cg(0x90,16).." cgA0="..cg(0xA0,16)) fin() end
  elseif st=="pick" then
    pt=pt+1
    if p2hold>0 then p2hold=p2hold-1 end
    if os.getenv("P2_PROBE") and pt>=150 and (pt-150)%20==0 then
      local m={} for r=5,10 do for c=16,29 do m[#m+1]=string.format("%04X",emu.read(2*(0x3000+32*r+c),emu.memType.snesVideoRam)|(emu.read(2*(0x3000+32*r+c)+1,emu.memType.snesVideoRam)<<8)) end end
      L(string.format("p2 after %s: %s", P2B[p2i] or "-", table.concat(m," ")))
      if p2i<#P2B then p2i=p2i+1 p2hold=4 else shot("p2probe") fin() end
    end
    if pt==2 then L("6269="..hx(0x6269,5).." 1039="..hx(0x1039,1)) end
    if wait>0 then wait=wait-1
    elseif emu.read(0x7FFC00,emu.memType.snesMemory)==2 and pt>100 then   -- SB6 picker ready (asm/picker.asm !st)
      if step==1 and os.getenv("VRAM_DUMP") then local h=io.open(OUT.."_vram.bin","wb") local t={} for i=0,65535 do t[#t+1]=string.char(emu.read(i,emu.memType.snesVideoRam)) end h:write(table.concat(t)) h:close() end
      if step==1 then shot("pick"..picks.."_0") L("ready: 625F="..hx(0x625F,5).." 6264="..hx(0x6264,5).." 62AB="..hx(0x62AB,5).." 62B5="..hx(0x62B5,5).." 62BF="..hx(0x62BF,5).." 1038/39="..hx(0x1038,2).." cells="..hx(0x62C9,10).." slots="..hx(0x2B10,8).." refs="..hx(0x349,8)) end
      local b=PLAN[step]
      if os.getenv("CANCEL") and picks==1 then b=({"r","b"})[step] end
      if b then press(b) step=step+1 L(string.format("press %s (pt=%d)",b,pt))
        if b~="a" and b~="b" then wait=30 end
      end
    end
    if hold==0 and wait==20 and step>1 then shot("pick"..picks.."_"..(step-1)) L("  col="..hx(0x6264,5).." char="..hx(0x625F,5).." cg80="..cg(0x80,16).." p4="..string.format("%02X %02X",emu.read(0x7FFF68,emu.memType.snesMemory),emu.read(0x7FFF6A,emu.memType.snesMemory)).." cgC0="..cg(0xC0,16).." cgF0="..cg(0xF0,16).." 1038="..hx(0x1038,1).." 1040="..hx(0x1040,1)) end
    if mode~=4 then L(string.format("picker left f=%d pt=%d mode=%02X pc9=%06X 16C2=%s 16DA=%s",f,pt,mode,pc9(),hx(0x16C2,5),hx(0x16DA,5))) st="nav" step=1 phase=4 wait=60 end
    if pt>2500 then L("picker timeout pc9="..string.format("%06X",pc9()).." 1038/39="..hx(0x1038,2)) shot("timeout") fin() end
  end
  if f>14000 then L("timeout mode "..string.format("%02X",mode)) shot("end") fin() end
end, emu.eventType.endFrame)
