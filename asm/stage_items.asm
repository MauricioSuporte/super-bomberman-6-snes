; Items hidden in the soft blocks of a Normal Game stage (tools/sb6/features/stage_items.py).
;
; SB5 spreads each stage's list at $C4:E5C7 ([item, count, count with two players]..., 0) from $C5:3FEF, one item
; per JSR $40DE (a random soft block without an item, from cell $AE) while soft blocks are left ($0E1F). Stages
; in !TABLE ([stage, item..., 0]..., $FF) get exactly those items instead; Battle and every other stage keep SB5's.
; Entered with M 8-bit, X 16-bit, X = the stage's offset in SB5's list, DB = $84.

asar 1.90
hirom

org !C5

si_spread:
    lda $1D1A
    bit #$01
    bne .sb5                    ; Battle
    phx
    ldx #$0000
.find:
    lda.l si_table,x
    cmp #$FF
    beq .none
    cmp $102F
    beq .found
-   inx
    lda.l si_table,x
    bne -
    inx
    bra .find
.found:
    inx
    lda.l si_table,x
    beq .done
    phx
    phy
    sep #$10
    jsr $40DE
    rep #$10
    ply
    plx
    dec $0E1F
    bne .found
.done:
    plx
    jmp $404C
.none:
    plx
.sb5:
    lda $1D1A                   ; (SB5's LDA $1D1A at $C5:3FEF)
    jmp $3FF2

si_table:
    db !TABLE
end_c5:

print "SYM si_spread ", hex(si_spread)
print "SYM end_c5 ", hex(end_c5)
