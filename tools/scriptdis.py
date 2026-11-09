#!/usr/bin/env python3
"""Script VM disassembler (research): python tools/scriptdis.py ROM ADDR COUNT

Operand lengths come from the cartridge: op n at $C2:0AF5+n-1,
FF n at $C2:09D8+n-1, FE n at $C2:094D+n-1 (lengths after the sub-op byte).
"""
import sys

def off(a): return a & 0x3FFFFF

def main():
    rom = open(sys.argv[1], "rb").read()
    a = int(sys.argv[2].replace(":", ""), 16)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    for _ in range(n):
        op = rom[off(a)]
        if op == 0xFF:
            sub = rom[off(a) + 1]; ln = 2 + rom[off(0xC209D8) + sub - 1]
        elif op == 0xFE:
            sub = rom[off(a) + 1]; ln = 2 + rom[off(0xC2094D) + sub - 1]
        elif op == 0:
            ln = 1
        else:
            ln = 1 + rom[off(0xC20AF5) + op - 1]
        b = rom[off(a):off(a) + ln]
        print(f"{a>>16:02X}:{a&0xFFFF:04X}  {b.hex(' ')}")
        a += ln

main()
