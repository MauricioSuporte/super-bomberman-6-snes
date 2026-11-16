-- Super Bomberman (USA): plays one sound command in isolation and logs the S-DSP writes for tools/spc_render.py.
-- In stage 1-1 the bomb drop's request (A = $1E at $C4:8522, the SFX command routine) becomes TARGET (hex),
-- every other SFX request is skipped. Writes OUT_aram.bin / OUT_dsp.bin (at frame 1490) and OUT.txt.
-- env: TARGET (e.g. 1F player death, 16 enemy death), OUT (path prefix).
--   Mesen.exe --testrunner "Super Bomberman (USA).sfc" tools/mesen/sb1_sfx.lua
--   python tools/spc_render.py OUT.txt OUT_aram.bin OUT_dsp.bin out.wav --voices 0
local f=0
local log={}
local plan={}
local function press(fr,b,len) for i=0,(len or 4)-1 do plan[fr+i]=b end end
for k=0,11 do press(300+k*60,"start") end
press(1500,"a",4)
local TARGET=tonumber(os.getenv("TARGET"),16)
local OUT=os.getenv("OUT") or "sb1_sfx"
local W0, W1 = 1490, 1720
emu.addEventCallback(function() local b=plan[f] if b then local t={} t[b]=true emu.setInput(t,0) end end, emu.eventType.inputPolled)
emu.addMemoryCallback(function()
  local s=emu.getState()
  local a=s["cpu.a"]&0xFF
  if f<1400 then return end
  if a==0x1E and f>=1500 and f<1510 then
    s["cpu.a"]=(s["cpu.a"]&0xFF00)|TARGET emu.setState(s)
    log[#log+1]=string.format("C %d f=%d A=%02X",s["spc.cycle"],f,TARGET)
  else
    s["cpu.pc"]=0x8536 emu.setState(s)
  end
end, emu.callbackType.exec, 0xC48522, 0xC48522)
emu.addMemoryCallback(function(addr,val)
  if f<W0 or f>W1 then return end
  log[#log+1]=string.format("W %d %02X %02X", emu.getState()["spc.cycle"], emu.read(0xF2,emu.memType.spcMemory), val)
end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
emu.addEventCallback(function()
  f=f+1
  if f==W0 then
    local t={} for i=0,65535 do t[#t+1]=string.char(emu.read(i,emu.memType.spcRam)) end
    local h=io.open(OUT.."_aram.bin","wb") h:write(table.concat(t)) h:close()
    local d={} for i=0,127 do d[#d+1]=string.char(emu.read(i,emu.memType.spcDspRegisters)) end
    h=io.open(OUT.."_dsp.bin","wb") h:write(table.concat(d)) h:close()
    log[#log+1]=string.format("START %d",emu.getState()["spc.cycle"])
  end
  if f==W1 then local h=io.open(OUT..".txt","w") h:write(table.concat(log,"\n")) h:close() emu.stop(0) end
end, emu.eventType.endFrame)
