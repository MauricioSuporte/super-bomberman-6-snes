-- Boots the hack, opens the Normal Game picker, presses PLAN there and waits in stage 1-1.
-- env: SB6_PLAYERS, SB6_OUT (prefix of the log/screenshots), PLAN (comma list of P1 buttons in the picker:
-- "a" = Bomberman, "right,a" = character 1; r/l change the color), STAGE_WAIT (frames in the stage), CANCEL=1
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
emu.addEventCallback(function() if hold>0 and btn then local t={} t[btn]=true emu.setInput(t,0) end end, emu.eventType.inputPolled)
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
    if stage and f-stage==(tonumber(os.getenv("STAGE_WAIT") or "520")) then shot("stage") L("chars "..hx(0x16C2,5).." pal "..hx(0x16DA,5).." 1D24/25="..hx(0x1D24,2).." count="..hx(0x129,1)) fin() end
  elseif st=="pick" then
    pt=pt+1
    if pt==2 then L("6269="..hx(0x6269,5).." 1039="..hx(0x1039,1)) end
    if wait>0 then wait=wait-1
    elseif pc9()==0xC68E68 and pt>150 then
      if step==1 then shot("pick"..picks.."_0") L("ready: 625F="..hx(0x625F,5).." 6264="..hx(0x6264,5).." 62AB="..hx(0x62AB,5).." 62B5="..hx(0x62B5,5).." 62BF="..hx(0x62BF,5).." 1038/39="..hx(0x1038,2).." cells="..hx(0x62C9,10).." slots="..hx(0x2B10,8).." refs="..hx(0x349,8)) end
      local b=PLAN[step]
      if os.getenv("CANCEL") and picks==1 then b=({"r","b"})[step] end
      if b then press(b) step=step+1 L(string.format("press %s (pt=%d)",b,pt))
        if b~="a" and b~="b" then wait=30 end
      end
    end
    if hold==0 and wait==20 and step>1 then shot("pick"..picks.."_"..(step-1)) L("  col="..hx(0x6264,5).." char="..hx(0x625F,5).." cg80="..cg(0x80,16).." 1038="..hx(0x1038,1).." 1040="..hx(0x1040,1)) end
    if mode~=4 then L(string.format("picker left f=%d pt=%d mode=%02X pc9=%06X 16C2=%s 16DA=%s",f,pt,mode,pc9(),hx(0x16C2,5),hx(0x16DA,5))) st="nav" step=1 phase=4 wait=60 end
    if pt>2500 then L("picker timeout pc9="..string.format("%06X",pc9()).." 1038/39="..hx(0x1038,2)) shot("timeout") fin() end
  end
  if f>14000 then L("timeout mode "..string.format("%02X",mode)) shot("end") fin() end
end, emu.eventType.endFrame)
