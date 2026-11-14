; Player bomber sprites rebuilt from the pose sheets of assets/bombers
; (tools/sb6/features/bombers.py, tools/sb6/bomber.py).
;
; $C0:1289 resolves the sprite mapping of an object from its type
; ($C0:16CC + 3*type -> word table). Character n is type $10 + n, and its
; tiles are loaded by seat ($80:BB66 + 2*character), so the new piece layout
; is given only to the objects that are a seat's bomber ($17FA + seat) of
; that character ($16C2 + seat): cut-scene bombers keep the cartridge's
; table. !CHARMAP / !CHARANIM: one long per character, bank 0 = stock.
;
; Entry: M/X 8-bit, Y = object, $5B-$5D = stock table (long), X free.
; Replaces `LDA $049F,Y / DEC A` at $C0:12A4.

asar 1.90
hirom

; Streamed poses (bomber_stream / stream_nmi). An animation whose poses do not
; fit one 1 KB strip together has a block per pose (<= 16 tiles, 8 columns x 2
; rows, tools/sb6/bomber.py convert). The bomber's 32-tile page is used as two
; halves: a new pose is DMA'd into the half not shown and $073F (tile base of
; the object) moves to it. The DMA runs in the NMI right before the stock
; strip queue ($C0:F41D), in the same vblank as the OAM built with the new
; $073F. !CHARSTREAM: per character [offset16 in bank $E4, mapping count];
; at that offset, per mapping id: [source24, columns] (0 columns = not
; streamed). State per seat at $7F:FE00 (docs/FREE_SPACE.md).
!SB      = $7FFE00
; Pending DMAs are kept per half (slot = 2 * seat + half): while walking the
; stock code reloads the page every frame, so the half still shown may need
; its pose again in the same NMI as the other half's new one.
!SLAST   = !SB+$00      ; 5: mapping in the page (0 = none)
!SPEND   = !SB+$06      ; 10 slots: $A5 = DMA pending
!SEXP    = !SB+$10      ; 5 words: $073F we set (another value: the stock code reloaded the page)
!SENT    = !SB+$1A      ; 10 words: table entry (offset in $E4) of the pending pose
!SVRAM   = !SB+$2E      ; 10 words: VRAM word address of the half
!SINIT   = !SB+$42      ; $5AA5 once cleared (stream_clear, from the title)
!SSEAT   = !SB+$44      ; scratch from here
!SCNT    = !SB+$45
!SOFF    = !SB+$46
!SM      = !SB+$48
!SENTRY  = !SB+$4A
!SPT     = !SB+$4C
!SVB     = !SB+$4E
!SCUR    = !SB+$50
!SVT     = !SB+$52
!SLEN    = !SB+$54
!SH      = !SB+$56

org !E4
; Carry set and X = 3 * character when object Y is a seat's bomber whose
; type matches the seat's character. Clobbers A, X.
bomber_ours:
    LDA $04FF,Y
    CMP #$10
    BCC .no
    CMP #$1A
    BCS .no
    TYA
    LDX #$04
-   CMP $17FA,X
    BEQ .seat
    DEX
    BPL -
.no
    CLC
    RTS
.seat
    TXA
    STA.l !SSEAT
    LDA $04FF,Y
    SEC
    SBC #$10
    CMP $16C2,X
    BNE .no
    ASL A
    CLC
    ADC $16C2,X
    TAX
    SEC
    RTS

bomber_map:
    JSR bomber_ours
    BCC .stock
    PHX
    JSR bomber_stream
    PLX
    LDA.l !CHARMAP+2,X
    BEQ .stock
    STA $5D
    REP #$20
    LDA.l !CHARMAP,X
    STA $5B
    SEP #$20
.stock
    LDA $049F,Y
    DEC A
    RTL

; Mapping of seat bomber Y just resolved (X = 3 * character, seat in !SSEAT):
; a streamed pose goes to the other half of the page. M/X 8-bit; keeps Y.
bomber_stream:
    LDA.l !CHARSTREAM+2,X
    BEQ .rts
    STA.l !SCNT
    LDA.l !CHARSTREAM,X
    STA.l !SOFF
    LDA.l !CHARSTREAM+1,X
    STA.l !SOFF+1
    TYX
    LDA.l $7E049F,X
    STA.l !SM
    BEQ .forget
    DEC A
    CMP.l !SCNT
    BCS .forget
    REP #$30
    AND #$00FF
    ASL A
    ASL A
    CLC
    ADC.l !SOFF
    STA.l !SENTRY
    TAX
    SEP #$20
    LDA.l $E40003,X                 ; columns
    SEP #$10
    BNE .str
.forget
    LDA.l !SSEAT
    TAX
    LDA #$00
    STA.l !SLAST,X
.rts
    RTS
.str
    TYA                             ; page of the object
    LDX #$0F
-   CMP.l $7E1D00,X
    BEQ .page
    DEX
    BPL -
    BRA .forget
.page
    REP #$20
    TXA
    AND #$00FF
    ASL A
    ASL A
    ASL A
    ASL A
    ASL A
    STA.l !SPT                      ; first tile of the page
    ASL A
    ASL A
    ASL A
    ASL A
    CLC
    ADC #$6000
    STA.l !SVB                      ; its VRAM word address
    TYX
    LDA.l $7E073F,X
    STA.l !SCUR
    SEP #$20
    LDA.l !SSEAT
    ASL A
    TAX
    REP #$20
    LDA.l !SCUR
    CMP.l !SEXP,X
    BNE .b                          ; the stock code reloaded the page
    SEP #$20
    LDA.l !SSEAT
    TAX
    LDA.l !SM
    CMP.l !SLAST,X
    BNE +
    RTS                             ; same pose, same page
+   TXA
    ASL A
    TAX
    REP #$20
    LDA.l !SCUR
    SEC
    SBC.l !SPT
    CMP #$0008
    BEQ .a                          ; B shown: next in A
.b
    LDA #$0008
    BRA .set
.a
    LDA #$0000
.set
    STA.l !SH                       ; 0 / 8: half
    CLC
    ADC.l !SPT
    STA.l !SEXP,X
    STA.l !SCUR
    LDA.l !SH
    ASL A
    ASL A
    ASL A
    ASL A
    CLC
    ADC.l !SVB
    STA.l !SVT                      ; VRAM of the half
    LDA.l !SH
    LSR A
    LSR A
    STA.l !SH                       ; 0 / 2
    TXA
    ASL A
    CLC
    ADC.l !SH
    TAX                             ; slot * 2
    LDA.l !SVT
    STA.l !SVRAM,X
    LDA.l !SENTRY
    STA.l !SENT,X
    TXA
    LSR A
    TAX                             ; slot
    SEP #$20
    LDA #$A5
    STA.l !SPEND,X
    TYX
    LDA.l !SCUR
    STA.l $7E073F,X
    LDA.l !SCUR+1
    STA.l $7E0740,X
    LDA.l !SSEAT
    TAX
    LDA.l !SM
    STA.l !SLAST,X
    RTS
; NMI, replaces `JSL $C56AAF` at $C0:F41D: the pending poses to VRAM.
stream_nmi:
    PHP
    PHB
    SEP #$20
    REP #$10
    LDA #$00
    PHA
    PLB
    REP #$20
    LDA.l !SINIT
    CMP #$5AA5
    BNE .out
    LDX #$0000
-   JSR stream_one
    INX
    CPX #$000A
    BCC -
.out
    PLB
    PLP
    JML $C56AAF

; Slot X (16-bit): its pending pose, rows 0 and 1. Keeps X.
stream_one:
    SEP #$20
    LDA.l !SPEND,X
    CMP #$A5
    BEQ +
    RTS
+   LDA #$00
    STA.l !SPEND,X
    REP #$20
    PHX
    TXA
    ASL A
    TAX
    LDA.l !SVRAM,X
    STA.l !SVT
    AND #$E000
    CMP #$6000                      ; OBJ pages only
    BNE .skip
    LDA.l !SENT,X
    TAX
    SEP #$20
    LDA.l $E40003,X                 ; columns
    BEQ .skip
    CMP #$09
    BCS .skip
    REP #$20
    AND #$00FF
    ASL A
    ASL A
    ASL A
    ASL A
    ASL A
    STA.l !SLEN                     ; bytes of one row
    STA $4305
    LDA.l $E40000,X
    STA $4302
    LDA.l !SVT
    STA $2116
    SEP #$20
    LDA.l $E40002,X
    STA $4304
    LDA #$80
    STA $2115
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    REP #$20                        ; row 1: 16 tiles further, the source goes on
    LDA.l !SVT
    CLC
    ADC #$0100
    STA $2116
    LDA.l !SLEN
    STA $4305
    SEP #$20
    LDA #$01
    STA $420B
.skip
    REP #$20
    PLX
    RTS

; Forgets the streamed poses (from the title, asm/picker.asm pick_tick).
stream_clear:
    PHP
    REP #$30
    PHX
    LDX #$0040
    LDA #$0000
-   STA.l !SB,X
    DEX
    DEX
    BPL -
    LDA #$5AA5
    STA.l !SINIT
    PLX
    PLP
    RTL

; Animation scripts ($C0:11F8, table $C0:171D + 3*type). The same bombers
; get the scripts of assets/bombers/*_anims.txt. Replaces
; `LDA $C0171F,X` (table bank) at $C0:120E; $5B = table address, already set.
bomber_anim:
    LDA $C0171F,X
    PHA
    JSR bomber_ours
    BCC +
    LDA.l !CHARANIM+2,X
    BEQ +
    STA 1,S
    REP #$20
    LDA.l !CHARANIM,X
    STA $5B
    SEP #$20
+   PLA
    RTL

; Script step ($C0:1254): a pair with 0 frames restarts the script. For the
; bomber types $10-$19 the pair's first byte is the offset to restart at (0
; in every stock script of those types). Replaces `CMP #$00 / BNE / STA $07FF,Y` at $C0:126A; returns Z set
; when the script restarted ($C0:11F8 is then called again).
; A = frames just loaded, Y = object, $049F,Y = first byte of the pair.
bomber_loop:
    CMP #$00
    BNE .done
    LDA $04FF,Y
    CMP #$10
    BCC .zero
    CMP #$1A
    BCS .zero
    LDA $049F,Y
    BRA .set
.zero
    LDA #$00
.set
    STA $07FF,Y
    LDA #$00
.done
    RTL

; Bomber colors ($C4:37B0, A = palette id of set 0, pushed): the cartridge
; loads 9 colors (0-8); the palettes rebuilt from the sheets (ids 1 to
; !PALS, id 0 counts as 1, and the ids replaced through !XLAT) have 16.
; Replaces `LDA #$09 / STA $AB` at $C4:37C1; the id is at 4,S.
bomber_palcount:
    LDA 4,S
    CMP #$80                        ; (own palettes, below)
    BCS .all
    CMP.b #!PALS+1
    BCC .all
    CMP #$51
    BCS .nine
    PHP
    REP #$30
    PHX
    AND #$00FF
    TAX
    LDA.l !XLAT-1,X
    PLX
    PLP
    CMP #$00
    BNE .all
.nine
    LDA #$09
    BRA +
.all
    LDA #$10
+   STA $AB
    RTL

; Palette lookup ($C0:01DE: A = id, set $0AE7 -> [$A8] = palette, bank $81).
; Ids $80 + n of set 0 are the bomber palettes of BombermanPallete.png
; (column n + 1), table !PALTAB (words, data in the table's bank). The other
; characters' palettes follow them in the table: !XLAT (byte per id 1-$50,
; 0 = stock) is the table entry + 1 that replaces a stock id. Replaces
; `LDA #$81 / STA $AA / REP #$30` at $C0:01FA; Y = id - 1, X free.
pal_lookup:
    LDA #$81
    STA $AA
    LDA $0AE7
    BNE +
    CPY #$7F
    BCS .own
    CPY #$50
    BCS +
    TYX
    LDA.l !XLAT,X
    BEQ +
    DEC A
    BRA .tab
.own
    TYA
    SEC
    SBC #$7F
.tab
    TAY
    REP #$20
    LDA.w #!PALTAB
    STA $A8
    SEP #$20
    LDA.b #!PALTAB>>16
    STA $AA
+   REP #$30
    RTL

print "SYM end_e4 ", hex(pc())
print "SYM bomber_palcount ", hex(bomber_palcount)
print "SYM pal_lookup ", hex(pal_lookup)
print "SYM bomber_map ", hex(bomber_map)
print "SYM bomber_anim ", hex(bomber_anim)
print "SYM bomber_loop ", hex(bomber_loop)
print "SYM stream_nmi ", hex(stream_nmi)
print "SYM stream_clear ", hex(stream_clear)
