"""Normal Game for up to four players (asm/coop.asm).

Port of the five-player co-op mod of SuperBomberman5SNESRecomp
(src/normal_coop_mod.c with src/coop_corner_spawns_mod.c) to a cartridge
patch, limited to four seats (multitap on port 2):

  * title: NORMAL GAME -> 1/2/3/4 PLAYER GAME (players menu limit 3, the
    confirm block calls a script that stores the count in `!count`);
  * stage setup, spawns (P3 lower-left corner, P4 lower-right, moved to
    the nearest safe floor once the map exists), lives = players + 2,
    Start revives a dead seat, P3 red / P4 blue Bomberman;
  * every P1/P2-only seat loop (`CPX/CPY #$02`) compares with `!roster`
    (2 unless the stage is a co-op stage), the enemy -> player distance
    arrays move to four-seat arrays, mounts move to rider + 19.

With one or two players `!roster` = 2, `!mbase` = $18 and `!mofs` = $1CBF,
so the cartridge runs its own code paths.
"""
import os

from .. import asar
from ..romlib import off
from .title import PLAYERS_ARR, SET as TITLE_SET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ASM = os.path.join(ROOT, "asm", "coop.asm")

# Section name -> build region (free $FF space in that bank).
SECTIONS = {"c0": "c0", "c2": "c2", "c3": "c3", "c4": "c4", "c5": "c5", "e4": "bulk"}

ROSTER = 0x012A
MOFS = 0x0128
COUNT = 0x0129

# `CPX/CPY #$02` + branch: loops over P1/P2 only (recomp seat_loops,
# enemy_loops and the living-seat count $C5:02FF).
SEAT_LOOPS = [
    0xC20C9F,  # script op $12: players on a tile (exit warps, switches)
    0xC56195, 0xC561C6,  # stage floor gimmicks
    0xC16BA1,  # input hold on a cell
    0xC0373F,  # point damage: players take a direct hit
    0xC502FF,  # living players (retry / Game Over)
    0xC3119B, 0xC313A8, 0xC32CB2,  # large enemies' area hits
    0xC347FA, 0xC34816,  # enemy contact damage
    0xC315BF, 0xC31937, 0xC327AE, 0xC3296B, 0xC32EE8, 0xC33CA6, 0xC348AD,  # cell attacks
    0xC02DB0,  # area hit around a point (ZONE5 - 1 tower shock)
    0xC119AA, 0xC15D73,  # area hits
    0xC16B32,  # moving platforms carry players (ZONE5 - 25)
]

# Operands of `ADC/SBC/LDA/CPX $1CBF` that convert rider <-> mount (recomp
# offset_sites); they read `!mofs`.
MOUNT_OFFSET_OPERANDS = [
    0xC40275, 0xC40817, 0xC40B43, 0xC41E00, 0xC42BFD, 0xC43588, 0xC43CA2, 0xC43F97,
    0xC4434A, 0xC4435E, 0xC4443E, 0xC44F2F, 0xC451BF, 0xC454E4, 0xC45509,
    0xC4501A, 0xC45028, 0xC4504A, 0xC450AB, 0xC450B3, 0xC450E0, 0xC450EE, 0xC450FA,
    0xC5265A, 0xC43D39, 0xC43D51, 0xC43D6B, 0xC43D82,
]

DIST = 0x0110

# Boss start $C4:3C60 (Y = boss index; recomp boss_rider_sites): equipment of
# rival slot 2 (LDA #$02 / JSR $2906; slot 3 for the two-rival boss stays),
# the mounted rival's riding bit (LDX #$02 / STA $1782,X) and its mount
# (LDA #$02 / CLC / ADC $1CBF).
BOSS_RIDER_SITES = [0xC43C83, 0xC43C98, 0xC43C9F]
# $C4:3D30/$C4:3D69: P1/P2 mounts saved/restored around the boss start by
# literal actor (stock mounts 2/3 -> co-op 19/20, recomp mount_backups +17).
MOUNT_BACKUPS = [0xC43D3D, 0xC43D43, 0xC43D54, 0xC43D5A, 0xC43D71, 0xC43D77, 0xC43D89, 0xC43D8F]
RIVAL = 4  # bomber slot of the boss rival (P5)
BRANCHES = (0x10, 0x30, 0x90, 0xB0, 0xD0, 0xF0)


def _h(v, n):
    return f"${v:0{n}X}"


def _jmp(a):
    return bytes([0x4C, a & 0xFF, a >> 8 & 0xFF])


def _jsr(a):
    return bytes([0x20, a & 0xFF, a >> 8 & 0xFF])


def _jsl(a):
    return bytes([0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16])


def _assemble(rb):
    defines = {name.upper(): _h(rb.regions[reg].cursor, 6) for name, reg in SECTIONS.items()}
    runs, syms = asar.assemble_into(rb.d, ASM, defines)
    blocks = {}
    for name, reg in SECTIONS.items():
        start, end = rb.regions[reg].cursor, syms[f"end_{name}"]
        blocks[name] = (start, end)
    for o, data in runs:
        if not any(off(s) <= o and o + len(data) <= off(e) for s, e in blocks.values()):
            raise RuntimeError(f"coop.asm wrote outside its sections at file offset {o:06X}")
    out = bytearray(rb.d)
    for o, data in runs:
        out[o:o + len(data)] = data
    for name, (start, end) in blocks.items():
        if end > start:
            code = bytes(out[off(start):off(end)])
            if rb.alloc(SECTIONS[name], code, f"co-op: code (asm/coop.asm, bank {name.upper()})") != start:
                raise RuntimeError("co-op code allocation moved")
    return syms


def _seat_loop_stub(rb, site):
    """`CPX/CPY #$02` + Bcc at `site` -> JMP to a stub comparing with !roster."""
    b = bytes(rb.d[off(site):off(site) + 4])
    if b[0] not in (0xE0, 0xC0) or b[1] != 0x02 or b[2] not in BRANCHES:
        raise RuntimeError(f"seat loop ${site:06X}: unexpected bytes {b.hex(' ')}")
    rel = b[3] - 256 if b[3] >= 128 else b[3]
    fall, target = site + 4, site + 4 + rel
    cmp_abs = 0xEC if b[0] == 0xE0 else 0xCC  # CPX/CPY abs (DBR maps WRAM, as the site's own code)
    region = {0xC0: "c0", 0xC1: "c1", 0xC2: "c2", 0xC3: "c3", 0xC5: "c5"}[site >> 16]
    stub = (bytes([cmp_abs, ROSTER & 0xFF, ROSTER >> 8, b[2], 0x03])
            + _jmp(fall & 0xFFFF) + _jmp(target & 0xFFFF))
    addr = rb.alloc(region, stub, f"co-op: seat loop ${site:06X} bound = roster")
    rb.patch(site, b, _jmp(addr & 0xFFFF) + b"\xEA", f"co-op: seat loop ${site:06X} -> roster")


def _distances(rb):
    """Enemy -> player distances: six two-seat arrays at $1FF4-$1FFF become
    six four-seat arrays at DIST (recomp find_enemy_sites)."""
    n = 0
    for a in range(0xC31100, 0xC34900):
        o = off(a)
        if rb.d[o] in (0xB9, 0x99, 0x9D) and rb.d[o + 1] >= 0xF4 and rb.d[o + 2] == 0x1F:
            slot = rb.d[o + 1] - 0xF4
            new = DIST + 4 * (slot // 2) + slot % 2
            rb.patch(a + 1, rb.d[o + 1:o + 3], bytes([new & 0xFF, new >> 8]),
                     f"co-op: distance array ${0x1F00 + rb.d[o + 1]:04X} -> ${new:04X}")
            n += 1
    if n != 57:
        raise RuntimeError(f"expected 57 distance operands, found {n}")
    rb.patch(0xC34766, b"\x0C", b"\x18", "co-op: clear 6 x 4 distance bytes")


def _boss_rival(rb, syms):
    """Boss rival in bomber slot 4 (P5) instead of 2 (P3): port of the
    recomp's boss move with a fixed slot (ZONE3 - D's second rival keeps 3)."""
    for a in (0xC216B8, 0xC216EE):
        rb.patch(a, bytes.fromhex("A7 0D 3A AA"), _jsr(syms["c2_bslot"] & 0xFFFF) + b"\xEA",
                 "boss: scripted rival bomber slot 2 -> 4")
    for a in BOSS_RIDER_SITES:
        rb.patch(a, b"\x02", bytes([RIVAL]), f"boss: start ${a - 1:06X} rival slot 2 -> 4")
    for a in MOUNT_BACKUPS:
        o = off(a)
        if rb.d[o] not in (0xAD, 0x8D, 0xBD, 0x9D) or rb.d[o + 2] != 0x16 or rb.d[o + 1] not in (0xC4, 0xC5, 0xDC, 0xDD):
            raise RuntimeError(f"boss mount backup ${a:06X}: unexpected {rb.d[o:o + 3].hex(' ')}")
        rb.patch(a + 1, rb.d[o + 1:o + 2], bytes([rb.d[o + 1] + 17]), f"boss: mount backup ${a:06X} actor +17")
    # Boss choreography $C5:2600-$C5:39FF (recomp find_boss_sites): LDX #2
    # before $C4:3C24/$C4:3BDE, LDA #2 before $C4:2B3A/$C4:3BA3, LDA $17FC.
    n = {"ldx": 0, "lda": 0, "obj": 0}
    for pc in range(0xC52600, 0xC53A00):
        o = off(pc)
        b = rb.d[o:o + 12]
        if b[0] == 0xA2 and b[1] == 2 and b[2] == 0xA9:
            c = b[6:] if b[4] == 0xA0 else b[4:]
            if c[0] == 0x22 and c[3] == 0xC4 and (c[1], c[2]) in ((0x24, 0x3C), (0xDE, 0x3B)):
                rb.patch(pc + 1, b"\x02", bytes([RIVAL]), f"boss: choreography ${pc:06X} LDX rival")
                n["ldx"] += 1
        elif b[0] == 0xA9 and b[1] == 2 and b[2] == 0x22 and b[5] == 0xC4 and (b[3], b[4]) in ((0x3A, 0x2B), (0xA3, 0x3B)):
            rb.patch(pc + 1, b"\x02", bytes([RIVAL]), f"boss: choreography ${pc:06X} LDA rival")
            n["lda"] += 1
        elif b[0] == 0xAD and b[1] == 0xFC and b[2] == 0x17:
            rb.patch(pc + 1, b"\xFC", bytes([0xFA + RIVAL]), f"boss: choreography ${pc:06X} rival object")
            n["obj"] += 1
    if n != {"ldx": 57, "lda": 23, "obj": 18}:
        raise RuntimeError(f"boss choreography: unexpected rival operands {n}")


def _title_menu(rb):
    """1-4 PLAYER GAME on the title (script VM, see docs/ROM_MAP.md)."""
    # Players menu: arrangement 4 of the SB6 title set (8 rows), clear blocks
    # of 8 rows (row $0B after title.py's shift), cursor limit 3.
    rb.patch(0xC718BD, bytes.fromhex("FF 8D 07 04 03 00 00"),
             bytes([0xFF, 0x8D, PLAYERS_ARR, TITLE_SET, 0x03, 0x00, 0x00]), "title: 1-4 PLAYER GAME menu")
    for a in (0xC718B6, 0xC719B7):
        rb.patch(a, bytes.fromhex("FF 91 09 0B 10 06 03"), bytes.fromhex("FF 91 09 0B 10 08 03"),
                 "title: menu clear block 8 rows")
    rb.patch(0xC719E6, bytes.fromhex("5B 01"), bytes.fromhex("5B 03"), "title: players menu has 4 entries")

    # Confirm: the original one-player block (controller choice from $1040),
    # then 2/3/4 players; all of them end like the original ones.
    one = bytes(rb.d[off(0xC718FB):off(0xC71916)])  # 5d 40 10 49 0c ... 5f 24 1d
    if one != bytes.fromhex("5D 40 10 49 0C 5B 01 5F 25 1D 5B 01 5F 24 1D 45 0A 5B 02 5F 25 1D 5B 02 5F 24 1D"):
        raise RuntimeError("title: unexpected one-player block")

    def store_count(n):
        return bytes([0x5B, n, 0x5F, COUNT & 0xFF, COUNT >> 8])

    def two_or_more(n):  # P1+P2 as the stock two-player game; co-op adds the rest
        return bytes.fromhex("5B 03 5F 25 1D 5B 03 5F 24 1D") + store_count(n)

    bodies = [one + store_count(1), two_or_more(2), two_or_more(3), two_or_more(4)]
    end = bytes.fromhex("06 06 0F 03 00")
    # Layout: for k < 3: [cursor == k ? body_k, skip to end]; then body_3; end.
    parts = []
    for k, body in enumerate(bodies):
        parts.append((k, body))
    script = bytearray()
    tails = []
    for k, body in parts[:3]:
        block = body + b"\x45\x00"  # skip to end (patched below)
        script += bytes([0x5D, 0x32, 0x10, 0x86, k, 0x49, len(block)])
        tails.append(len(script) + len(block) - 1)
        script += block
    script += parts[3][1]
    for t in tails:
        script[t] = len(script) - (t + 1)
    script += end
    addr = rb.alloc("bulk", bytes(script), "script: title players menu confirm (1-4 players)")
    rel = 0xC71AA3 - 0xC718FB
    rb.patch(0xC718F4, bytes.fromhex("5D 32 10 86 00 49 25"),
             bytes([0x24, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16, 0x44, rel & 0xFF, rel >> 8]),
             "title: players menu confirm -> 1-4 players script")


def apply(rb):
    syms = _assemble(rb)
    s = lambda name: syms[name] & 0xFFFF

    rb.patch(0xC0F393, bytes.fromhex("E2 30 A9 00 48 AB"), _jsl(syms["coop_boot"]) + b"\xEA\xEA",
             "reset: co-op variables")
    # Bank C4
    rb.patch(0xC4286F, bytes.fromhex("A9 00 20 06 29"), _jmp(s("c4_reset")) + b"\xEA\xEA",
             "co-op: equipment reset for every seat")
    rb.patch(0xC428B4, bytes.fromhex("A9 06 22 72 03 C2"), _jmp(s("c4_tail")) + b"\xEA" * 3,
             "co-op: lives, P3/P4 colors, participants")
    rb.patch(0xC429CE, bytes.fromhex("A9 02 8D BF 1C"), _jsr(s("c4_stage_slots")) + b"\xEA\xEA",
             "co-op: stage bomber slots / roster")
    rb.patch(0xC42A60, bytes.fromhex("A9 05 8D BF 1C"), _jsr(s("c4_battle_slots")) + b"\xEA\xEA",
             "co-op: Battle keeps stock slots")
    rb.patch(0xC43C75, bytes.fromhex("B9 AE B9 8D BF 1C"), _jsr(s("c4_boss_slots")) + b"\xEA" * 3,
             "co-op: boss stages keep five bomber slots (rival in slot 4)")
    rb.patch(0xC43794, bytes.fromhex("AD 1A 1D"), _jmp(s("c4_death")), "co-op: death leaves the participants")
    for a in (0xC42AD8, 0xC42B8D):
        rb.patch(a, bytes.fromhex("8D 48 03"), _jsr(s("c4_palmask")), "co-op: P3/P4 OBJ palette slots 4-7")
    rb.patch(0xC453F0, bytes.fromhex("BD DA 16 1A"), _jsr(s("c4_mountslot")) + b"\xEA",
             "co-op: mount uses its rider's palette slot")
    rb.patch(0xC42260, bytes.fromhex("E0 18 90 F6 80 30"), _jmp(s("c4_cap")) + b"\xEA" * 3,
             "co-op: enemies stop below the mounts")
    # Bank C5
    rb.patch(0xC53B2D, bytes.fromhex("AD 23 1D"), _jsr(s("c5_charge")), "co-op: retry charges P3/P4")
    rb.patch(0xC53D5B, bytes.fromhex("FA AB 6B"), _jmp(s("c5_settle")), "co-op: settle P3/P4 after the map copy")
    rb.patch(0xC56AE3, bytes.fromhex("20 F5 6A B0 0A"), _jmp(s("c5_service")) + b"\xEA\xEA",
             "co-op: sprite page service")
    rb.patch(0xC542F5, bytes.fromhex("E0 18 90 E4"), _jmp(s("c5_clock")) + b"\xEA",
             "co-op: Clock does not freeze mounts")
    rb.patch(0xC5060E, bytes.fromhex("AD FA 17 0D FB 17"), _jsl(syms["e4_frame"]) + b"\xEA\xEA",
             "co-op: participants and Start rejoin")
    # Bank C2 / C3 / C0 / C1
    rb.patch(0xC21697, bytes.fromhex("AD 24 1D"), _jmp(s("c2_spawn")), "co-op: stage spawns")
    rb.patch(0xC21F2B, bytes.fromhex("AD 25 1D"), _jsr(s("c2_story")), "co-op: story scripts see 1/3")
    rb.patch(0xC34B8F, bytes.fromhex("20 5C 47"), _jsr(s("c3_fill")), "co-op: distances of P3/P4")
    rb.patch(0xC34393, bytes.fromhex("AD 25 1D"), _jsr(s("c3_record")), "co-op: campaign record mask")
    rb.patch(0xC0374D, bytes.fromhex("E0 05 90 27"), _jmp(s("c0_damage")) + b"\xEA",
             "co-op: point damage skips mounts")
    rb.patch(0xC00B44, bytes.fromhex("22 F0 22 C0"), _jsl(syms["e4_tick"]), "co-op: per-frame upkeep (palette slots)")
    rb.patch(0xC00573, bytes.fromhex("AD 61 03 8D 16 21"), _jsr(s("c0_vmadd")) + b"\xEA\xEA\xEA",
             "co-op: track static OBJ pages (VRAM DMA queue)")
    rb.patch(0xC00303, bytes.fromhex("A9 FF 38 80 3A"), _jmp(s("c0_palfail")) + b"\xEA\xEA",
             "co-op: OBJ palette slots full -> P3/P4 share P1's")
    rb.patch(0xC437B0, bytes.fromhex("48 9C E7 0A"), _jmp(s("c4_seatcolor")) + b"\xEA",
             "co-op: a bomber sharing P1's slot keeps P1's colors")
    for a in (0xC1002A, 0xC1004A):
        rb.patch(a, b"\x20", b"\x1F", "palette blink save/restore: 32 bytes (was 33, overran palette 15)")

    for site in SEAT_LOOPS:
        _seat_loop_stub(rb, site)
    for a in MOUNT_OFFSET_OPERANDS:
        rb.patch(a, b"\xBF\x1C", bytes([MOFS & 0xFF, MOFS >> 8]), f"co-op: mount offset operand ${a:06X}")
    _distances(rb)
    _boss_rival(rb, syms)
    _title_menu(rb)
    return dict(code=sum(1 for _ in syms))
