#!/usr/bin/env python3
"""Minimal SPC700 disassembler.

    python tools/spc700dis.py ARAM.bin START [COUNT]

ARAM.bin is a 64 KiB dump (e.g. from Mesen's spcRam). Operand notation:
d = direct page byte, a = 16-bit absolute, i = immediate, r = relative
branch, b = dp.bit, m = mem.bit (13-bit address + 3-bit bit).
"""
import sys

T = {}


def op(code, text):
    T[code] = text


# Rows from the SPC700 opcode map.
for i, t in enumerate(["NOP", "TCALL 0", "SET1 d.0", "BBS d.0,r", "OR A,d", "OR A,!a", "OR A,(X)", "OR A,[d+X]",
                       "OR A,#i", "OR d,d", "OR1 C,m", "ASL d", "ASL !a", "PUSH PSW", "TSET1 !a", "BRK"]):
    op(i, t)
for i, t in enumerate(["BPL r", "TCALL 1", "CLR1 d.0", "BBC d.0,r", "OR A,d+X", "OR A,!a+X", "OR A,!a+Y", "OR A,[d]+Y",
                       "OR d,#i", "OR (X),(Y)", "DECW d", "ASL d+X", "ASL A", "DEC X", "CMP X,!a", "JMP [!a+X]"]):
    op(0x10 + i, t)
for i, t in enumerate(["CLRP", "TCALL 2", "SET1 d.1", "BBS d.1,r", "AND A,d", "AND A,!a", "AND A,(X)", "AND A,[d+X]",
                       "AND A,#i", "AND d,d", "OR1 C,/m", "ROL d", "ROL !a", "PUSH A", "CBNE d,r", "BRA r"]):
    op(0x20 + i, t)
for i, t in enumerate(["BMI r", "TCALL 3", "CLR1 d.1", "BBC d.1,r", "AND A,d+X", "AND A,!a+X", "AND A,!a+Y", "AND A,[d]+Y",
                       "AND d,#i", "AND (X),(Y)", "INCW d", "ROL d+X", "ROL A", "INC X", "CMP X,d", "CALL !a"]):
    op(0x30 + i, t)
for i, t in enumerate(["SETP", "TCALL 4", "SET1 d.2", "BBS d.2,r", "EOR A,d", "EOR A,!a", "EOR A,(X)", "EOR A,[d+X]",
                       "EOR A,#i", "EOR d,d", "AND1 C,m", "LSR d", "LSR !a", "PUSH X", "TCLR1 !a", "PCALL i"]):
    op(0x40 + i, t)
for i, t in enumerate(["BVC r", "TCALL 5", "CLR1 d.2", "BBC d.2,r", "EOR A,d+X", "EOR A,!a+X", "EOR A,!a+Y", "EOR A,[d]+Y",
                       "EOR d,#i", "EOR (X),(Y)", "CMPW YA,d", "LSR d+X", "LSR A", "MOV X,A", "CMP Y,!a", "JMP !a"]):
    op(0x50 + i, t)
for i, t in enumerate(["CLRC", "TCALL 6", "SET1 d.3", "BBS d.3,r", "CMP A,d", "CMP A,!a", "CMP A,(X)", "CMP A,[d+X]",
                       "CMP A,#i", "CMP d,d", "AND1 C,/m", "ROR d", "ROR !a", "PUSH Y", "DBNZ d,r", "RET"]):
    op(0x60 + i, t)
for i, t in enumerate(["BVS r", "TCALL 7", "CLR1 d.3", "BBC d.3,r", "CMP A,d+X", "CMP A,!a+X", "CMP A,!a+Y", "CMP A,[d]+Y",
                       "CMP d,#i", "CMP (X),(Y)", "ADDW YA,d", "ROR d+X", "ROR A", "MOV A,X", "CMP Y,d", "RETI"]):
    op(0x70 + i, t)
for i, t in enumerate(["SETC", "TCALL 8", "SET1 d.4", "BBS d.4,r", "ADC A,d", "ADC A,!a", "ADC A,(X)", "ADC A,[d+X]",
                       "ADC A,#i", "ADC d,d", "EOR1 C,m", "DEC d", "DEC !a", "MOV Y,#i", "POP PSW", "MOV d,#i"]):
    op(0x80 + i, t)
for i, t in enumerate(["BCC r", "TCALL 9", "CLR1 d.4", "BBC d.4,r", "ADC A,d+X", "ADC A,!a+X", "ADC A,!a+Y", "ADC A,[d]+Y",
                       "ADC d,#i", "ADC (X),(Y)", "SUBW YA,d", "DEC d+X", "DEC A", "MOV X,SP", "DIV YA,X", "XCN A"]):
    op(0x90 + i, t)
for i, t in enumerate(["EI", "TCALL 10", "SET1 d.5", "BBS d.5,r", "SBC A,d", "SBC A,!a", "SBC A,(X)", "SBC A,[d+X]",
                       "SBC A,#i", "SBC d,d", "MOV1 C,m", "INC d", "INC !a", "CMP Y,#i", "POP A", "MOV (X)+,A"]):
    op(0xA0 + i, t)
for i, t in enumerate(["BCS r", "TCALL 11", "CLR1 d.5", "BBC d.5,r", "SBC A,d+X", "SBC A,!a+X", "SBC A,!a+Y", "SBC A,[d]+Y",
                       "SBC d,#i", "SBC (X),(Y)", "MOVW YA,d", "INC d+X", "INC A", "MOV SP,X", "DAS A", "MOV A,(X)+"]):
    op(0xB0 + i, t)
for i, t in enumerate(["DI", "TCALL 12", "SET1 d.6", "BBS d.6,r", "MOV d,A", "MOV !a,A", "MOV (X),A", "MOV [d+X],A",
                       "CMP X,#i", "MOV !a,X", "MOV1 m,C", "MOV d,Y", "MOV !a,Y", "MOV X,#i", "POP X", "MUL YA"]):
    op(0xC0 + i, t)
for i, t in enumerate(["BNE r", "TCALL 13", "CLR1 d.6", "BBC d.6,r", "MOV d+X,A", "MOV !a+X,A", "MOV !a+Y,A", "MOV [d]+Y,A",
                       "MOV d,X", "MOV d+Y,X", "MOVW d,YA", "MOV d+X,Y", "DEC Y", "MOV A,Y", "CBNE d+X,r", "DAA A"]):
    op(0xD0 + i, t)
for i, t in enumerate(["CLRV", "TCALL 14", "SET1 d.7", "BBS d.7,r", "MOV A,d", "MOV A,!a", "MOV A,(X)", "MOV A,[d+X]",
                       "MOV A,#i", "MOV X,!a", "NOT1 m", "MOV Y,d", "MOV Y,!a", "NOTC", "POP Y", "SLEEP"]):
    op(0xE0 + i, t)
for i, t in enumerate(["BEQ r", "TCALL 15", "CLR1 d.7", "BBC d.7,r", "MOV A,d+X", "MOV A,!a+X", "MOV A,!a+Y", "MOV A,[d]+Y",
                       "MOV X,d", "MOV X,d+Y", "MOV d,d", "MOV Y,d+X", "INC Y", "MOV Y,A", "DBNZ Y,r", "STOP"]):
    op(0xF0 + i, t)


def length(text):
    n = 1
    n += text.count("!a") * 2
    n += text.count("m") and ("m" in text.split()[-1].split(",")[-1] or ",m" in text or " m" in text) * 2
    for tok in ("d", "i", "r"):
        pass
    return n


def decode(mem, pc):
    code = mem[pc]
    text = T[code]
    args = []
    p = pc + 1
    out = text
    # Operands appear in machine order: for "MOV d,d"/"OR d,d" etc. the source comes first in memory.
    two_dp = text.split()[-1] == "d,d" if " " in text else False
    imm_dp = text.endswith("d,#i")
    if two_dp:
        src, dst = mem[p], mem[p + 1]
        return f"{text.split()[0]} ${dst:02X},${src:02X}", 3
    if imm_dp:
        imm, dst = mem[p], mem[p + 1]
        return f"{text.split()[0]} ${dst:02X},#${imm:02X}", 3
    tokens = []
    i = 0
    s = text
    res = ""
    while i < len(s):
        if s.startswith("!a", i):
            v = mem[p] | mem[p + 1] << 8; p += 2
            res += f"${v:04X}"; i += 2
        elif s[i] == "m" and (i == 0 or not s[i - 1].isalpha()) and (i + 1 == len(s) or not s[i + 1].isalpha()):
            v = mem[p] | mem[p + 1] << 8; p += 2
            res += f"${v & 0x1FFF:04X}.{v >> 13}"; i += 1
        elif s[i] == "d" and (i == 0 or not s[i - 1].isalpha()) and (i + 1 == len(s) or not s[i + 1].isalpha()):
            res += f"${mem[p]:02X}"; p += 1; i += 1
        elif s[i] == "i" and s[i - 1] in "# " and (i + 1 == len(s) or not s[i + 1].isalpha()):
            res += f"${mem[p]:02X}"; p += 1; i += 1
        elif s[i] == "r" and (i + 1 == len(s)) and s[i - 1] in ", ":
            rel = mem[p]; p += 1
            rel = rel - 256 if rel >= 128 else rel
            res += f"${(p + rel) & 0xFFFF:04X}"; i += 1
        else:
            res += s[i]; i += 1
    return res, p - pc


def main():
    mem = open(sys.argv[1], "rb").read()
    pc = int(sys.argv[2], 16)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    for _ in range(count):
        text, n = decode(mem, pc)
        raw = " ".join(f"{mem[(pc + k) & 0xFFFF]:02X}" for k in range(n))
        print(f"{pc:04X}  {raw:<9} {text}")
        pc = (pc + n) & 0xFFFF


if __name__ == "__main__":
    main()
