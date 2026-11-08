local f=0
local log={}
local win=0
local seq={}
local function press(fr,btn,len) for i=0,(len or 3)-1 do seq[fr+i]=btn end end
press(6250,"down") press(6400,"down") press(6550,"up") press(6700,"start") press(7000,"b")
emu.addEventCallback(function()
  local b=seq[f] if b then local t={} t[b]=true emu.setInput(t,0) end
end, emu.eventType.inputPolled)
emu.addMemoryCallback(function()
  if f<6000 then return end
  local s=emu.getState()
  local a=s["cpu.a"]
  log[#log+1]=string.format("CED f=%d A=%04X cyc=%d", f, a, s["spc.cycle"])
  if (a>>8)&0xFF==2 then win=f+90 end
end, emu.callbackType.exec, 0xC00CED, 0xC00CED)
emu.addMemoryCallback(function(addr,val)
  if f>win or f<6000 then return end
  local s=emu.getState()
  log[#log+1]=string.format("W %d %02X %02X", s["spc.cycle"], emu.read(0xF2,emu.memType.spcMemory), val)
end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
emu.addEventCallback(function()
  f=f+1
  if f==6240 then
    local t={} for i=0,65535 do t[#t+1]=string.char(emu.read(i,emu.memType.spcRam)) end
    local h=io.open("D:/sb6-tools/work/aram_title.bin","wb") h:write(table.concat(t)) h:close()
    local d={} for i=0,127 do d[#d+1]=string.char(emu.read(i,emu.memType.spcDspRegisters)) end
    h=io.open("D:/sb6-tools/work/dsp_title.bin","wb") h:write(table.concat(d)) h:close()
  end
  if f==7150 then
    local h=io.open("D:/sb6-tools/work/sfxcap.txt","w") h:write(table.concat(log,"\n")) h:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
