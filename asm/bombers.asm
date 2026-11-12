; Player bomber sprites rebuilt from assets/bombers/bomber.png
; (tools/sb6/features/bombers.py, tools/sb6/bomber.py).
;
; $C0:1289 resolves the sprite mapping of an object from its type
; ($C0:16CC + 3*type -> word table). Every bomber is type $10 and shares one
; mapping table, so the new piece layout is given only to the objects that
; are a seat's bomber ($17FA + seat) of character 0 ($16C2 + seat): rivals
; and cut-scene bombers keep the cartridge's table.
;
; Entry: M/X 8-bit, Y = object, $5B-$5D = stock table (long), X free.
; Replaces `LDA $049F,Y / DEC A` at $C0:12A4.

asar 1.90
hirom

org !E4
; Z set when object Y is a seat's bomber of character 0. Clobbers A, X.
bomber_ours:
    LDA $04FF,Y
    CMP #$10
    BNE .no
    TYA
    LDX #$04
-   CMP $17FA,X
    BEQ .seat
    DEX
    BPL -
.no
    RTS
.seat
    LDA $16C2,X
    RTS

bomber_map:
    JSR bomber_ours
    BNE .stock
    REP #$20
    LDA.w #!MAPTAB
    STA $5B
    SEP #$20
    LDA.b #!MAPTAB>>16
    STA $5D
.stock
    LDA $049F,Y
    DEC A
    RTL

; Animation scripts ($C0:11F8, table $C0:171D + 3*type). The same bombers
; get the scripts of assets/bombers/bomber_anims.txt. Replaces
; `LDA $C0171F,X` (table bank) at $C0:120E; $5B = table address, already set.
bomber_anim:
    LDA $C0171F,X
    PHA
    JSR bomber_ours
    BNE +
    REP #$20
    LDA.w #!ANIMTAB
    STA $5B
    SEP #$20
    LDA.b #!ANIMTAB>>16
    STA 1,S
+   PLA
    RTL

; Script step ($C0:1254): a pair with 0 frames restarts the script. For type
; $10 the pair's first byte is the offset to restart at (0 in every stock
; script). Replaces `CMP #$00 / BNE / STA $07FF,Y` at $C0:126A; returns Z set
; when the script restarted ($C0:11F8 is then called again).
; A = frames just loaded, Y = object, $049F,Y = first byte of the pair.
bomber_loop:
    CMP #$00
    BNE .done
    LDA $04FF,Y
    CMP #$10
    BNE .zero
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
; loads 9 colors (0-8); the palettes rebuilt from the sheet (ids 1 to
; !PALS, id 0 counts as 1) have 16. Replaces `LDA #$09 / STA $AB` at
; $C4:37C1; the id is at 4,S.
bomber_palcount:
    LDA 4,S
    CMP.b #!PALS+1
    LDA #$09
    BCS +
    LDA #$10
+   STA $AB
    RTL

print "SYM end_e4 ", hex(pc())
print "SYM bomber_palcount ", hex(bomber_palcount)
print "SYM bomber_map ", hex(bomber_map)
print "SYM bomber_anim ", hex(bomber_anim)
print "SYM bomber_loop ", hex(bomber_loop)
