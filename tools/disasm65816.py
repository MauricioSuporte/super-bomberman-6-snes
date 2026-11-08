#!/usr/bin/env python3
"""Minimal 65816 disassembler for the SB5 HiROM image (used for research).

Usage: python tools/disasm65816.py ROM ADDR [COUNT] [--m8] [--x8]
ADDR is a SNES address such as C0:0580 or C00580. The M/X flags are tracked
through REP/SEP in straight-line code; pass --m8/--x8 for the entry state.
"""
import sys

# mnemonic, addressing mode
OPS = """
00 BRK imm8|01 ORA (dp,X)|02 COP imm8|03 ORA sr,S|04 TSB dp|05 ORA dp|06 ASL dp|07 ORA [dp]|08 PHP imp|09 ORA #m|0A ASL A|0B PHD imp|0C TSB abs|0D ORA abs|0E ASL abs|0F ORA long
10 BPL rel|11 ORA (dp),Y|12 ORA (dp)|13 ORA (sr,S),Y|14 TRB dp|15 ORA dp,X|16 ASL dp,X|17 ORA [dp],Y|18 CLC imp|19 ORA abs,Y|1A INC A|1B TCS imp|1C TRB abs|1D ORA abs,X|1E ASL abs,X|1F ORA long,X
20 JSR abs|21 AND (dp,X)|22 JSL long|23 AND sr,S|24 BIT dp|25 AND dp|26 ROL dp|27 AND [dp]|28 PLP imp|29 AND #m|2A ROL A|2B PLD imp|2C BIT abs|2D AND abs|2E ROL abs|2F AND long
30 BMI rel|31 AND (dp),Y|32 AND (dp)|33 AND (sr,S),Y|34 BIT dp,X|35 AND dp,X|36 ROL dp,X|37 AND [dp],Y|38 SEC imp|39 AND abs,Y|3A DEC A|3B TSC imp|3C BIT abs,X|3D AND abs,X|3E ROL abs,X|3F AND long,X
40 RTI imp|41 EOR (dp,X)|42 WDM imm8|43 EOR sr,S|44 MVP mv|45 EOR dp|46 LSR dp|47 EOR [dp]|48 PHA imp|49 EOR #m|4A LSR A|4B PHK imp|4C JMP abs|4D EOR abs|4E LSR abs|4F EOR long
50 BVC rel|51 EOR (dp),Y|52 EOR (dp)|53 EOR (sr,S),Y|54 MVN mv|55 EOR dp,X|56 LSR dp,X|57 EOR [dp],Y|58 CLI imp|59 EOR abs,Y|5A PHY imp|5B TCD imp|5C JML long|5D EOR abs,X|5E LSR abs,X|5F EOR long,X
60 RTS imp|61 ADC (dp,X)|62 PER rell|63 ADC sr,S|64 STZ dp|65 ADC dp|66 ROR dp|67 ADC [dp]|68 PLA imp|69 ADC #m|6A ROR A|6B RTL imp|6C JMP (abs)|6D ADC abs|6E ROR abs|6F ADC long
70 BVS rel|71 ADC (dp),Y|72 ADC (dp)|73 ADC (sr,S),Y|74 STZ dp,X|75 ADC dp,X|76 ROR dp,X|77 ADC [dp],Y|78 SEI imp|79 ADC abs,Y|7A PLY imp|7B TDC imp|7C JMP (abs,X)|7D ADC abs,X|7E ROR abs,X|7F ADC long,X
80 BRA rel|81 STA (dp,X)|82 BRL rell|83 STA sr,S|84 STY dp|85 STA dp|86 STX dp|87 STA [dp]|88 DEY imp|89 BIT #m|8A TXA imp|8B PHB imp|8C STY abs|8D STA abs|8E STX abs|8F STA long
90 BCC rel|91 STA (dp),Y|92 STA (dp)|93 STA (sr,S),Y|94 STY dp,X|95 STA dp,X|96 STX dp,Y|97 STA [dp],Y|98 TYA imp|99 STA abs,Y|9A TXS imp|9B TXY imp|9C STZ abs|9D STA abs,X|9E STZ abs,X|9F STA long,X
A0 LDY #x|A1 LDA (dp,X)|A2 LDX #x|A3 LDA sr,S|A4 LDY dp|A5 LDA dp|A6 LDX dp|A7 LDA [dp]|A8 TAY imp|A9 LDA #m|AA TAX imp|AB PLB imp|AC LDY abs|AD LDA abs|AE LDX abs|AF LDA long
B0 BCS rel|B1 LDA (dp),Y|B2 LDA (dp)|B3 LDA (sr,S),Y|B4 LDY dp,X|B5 LDA dp,X|B6 LDX dp,Y|B7 LDA [dp],Y|B8 CLV imp|B9 LDA abs,Y|BA TSX imp|BB TYX imp|BC LDY abs,X|BD LDA abs,X|BE LDX abs,Y|BF LDA long,X
C0 CPY #x|C1 CMP (dp,X)|C2 REP imm8|C3 CMP sr,S|C4 CPY dp|C5 CMP dp|C6 DEC dp|C7 CMP [dp]|C8 INY imp|C9 CMP #m|CA DEX imp|CB WAI imp|CC CPY abs|CD CMP abs|CE DEC abs|CF CMP long
D0 BNE rel|D1 CMP (dp),Y|D2 CMP (dp)|D3 CMP (sr,S),Y|D4 PEI dp|D5 CMP dp,X|D6 DEC dp,X|D7 CMP [dp],Y|D8 CLD imp|D9 CMP abs,Y|DA PHX imp|DB STP imp|DC JML [abs]|DD CMP abs,X|DE DEC abs,X|DF CMP long,X
E0 CPX #x|E1 SBC (dp,X)|E2 SEP imm8|E3 SBC sr,S|E4 CPX dp|E5 SBC dp|E6 INC dp|E7 SBC [dp]|E8 INX imp|E9 SBC #m|EA NOP imp|EB XBA imp|EC CPX abs|ED SBC abs|EE INC abs|EF SBC long
F0 BEQ rel|F1 SBC (dp),Y|F2 SBC (dp)|F3 SBC (sr,S),Y|F4 PEA abs|F5 SBC dp,X|F6 INC dp,X|F7 SBC [dp],Y|F8 SED imp|F9 SBC abs,Y|FA PLX imp|FB XCE imp|FC JSR (abs,X)|FD SBC abs,X|FE INC abs,X|FF SBC long,X
"""
TABLE = {}
for line in OPS.strip().splitlines():
    for item in line.split("|"):
        code, mn, mode = item.split(" ", 2)
        TABLE[int(code, 16)] = (mn, mode)

SIZE = {"imp": 0, "A": 0, "imm8": 1, "dp": 1, "(dp,X)": 1, "sr,S": 1, "[dp]": 1,
        "(dp),Y": 1, "(dp)": 1, "(sr,S),Y": 1, "dp,X": 1, "dp,Y": 1, "[dp],Y": 1,
        "rel": 1, "abs": 2, "abs,X": 2, "abs,Y": 2, "(abs)": 2, "(abs,X)": 2,
        "[abs]": 2, "rell": 2, "mv": 2, "long": 3, "long,X": 3}


def rom_offset(addr):
    return addr & 0x3FFFFF  # HiROM: $C0-$FF map linearly to the 4 MB image


def parse_addr(text):
    return int(text.replace(":", "").replace("$", ""), 16)


def disasm(rom, addr, count, m8=False, x8=False):
    out = []
    for _ in range(count):
        off = rom_offset(addr)
        op = rom[off]
        mn, mode = TABLE[op]
        if mode == "#m":
            n = 1 if m8 else 2
        elif mode == "#x":
            n = 1 if x8 else 2
        else:
            n = SIZE[mode]
        raw = rom[off + 1: off + 1 + n]
        val = int.from_bytes(raw, "little") if n else 0
        pc16 = addr & 0xFFFF
        if mode in ("#m", "#x"):
            arg = f"#${val:0{n*2}X}"
        elif mode == "imm8":
            arg = f"#${val:02X}"
        elif mode == "rel":
            tgt = (pc16 + 2 + (val - 256 if val > 127 else val)) & 0xFFFF
            arg = f"${addr >> 16:02X}:{tgt:04X}"
        elif mode == "rell":
            tgt = (pc16 + 3 + (val - 65536 if val > 32767 else val)) & 0xFFFF
            arg = f"${addr >> 16:02X}:{tgt:04X}"
        elif mode == "mv":
            arg = f"${raw[1]:02X},${raw[0]:02X}"
        elif mode in ("imp",):
            arg = ""
        elif mode == "A":
            arg = "A"
        else:
            width = {1: 2, 2: 4, 3: 6}[n]
            arg = mode.replace("dp", "$" + f"{val:0{width}X}", 1) if "dp" in mode else \
                mode.replace("long", "$" + f"{val:06X}").replace("abs", "$" + f"{val:04X}")
        hexb = " ".join(f"{b:02X}" for b in rom[off: off + 1 + n])
        out.append(f"{addr >> 16:02X}:{pc16:04X}  {hexb:<12} {mn} {arg}")
        if op == 0xC2:
            m8 = m8 and not (val & 0x20); x8 = x8 and not (val & 0x10)
        elif op == 0xE2:
            m8 = m8 or bool(val & 0x20); x8 = x8 or bool(val & 0x10)
        addr = (addr & 0xFF0000) | ((pc16 + 1 + n) & 0xFFFF)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom = open(args[0], "rb").read()
    start = parse_addr(args[1])
    count = int(args[2]) if len(args) > 2 else 40
    print("\n".join(disasm(rom, start, count, "--m8" in sys.argv, "--x8" in sys.argv)))
