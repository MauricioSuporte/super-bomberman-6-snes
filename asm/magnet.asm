; SB6's Magnet Bomb (tools/sb6/features/magnet.py) in place of SB5's mine.
;
; Item $0F (SB5's mine) sets ability bit $20 ($7E:4ED5+seat, exclusive with remote / pierce / search: $C5:438C).
; Patched outside this file: no bomb becomes a mine ($C4:3072, SB5's mine setup is freed), a dying bomber's bit $20
; bombs do not go off with it ($C4:3646). Like SB5's search bomb, only a bomber's first bomb out is a magnet bomb
; (animation 4 by SB5's own test at $C5:1C46, !MAG by mg_place); the others are normal bombs. Each bomb slot (0-19) has a byte in !MAG: 0 = a normal bomb, $80 + n = a magnet bomb that looks
; again in n frames.
;
; A magnet bomb at rest (SB5's bomb update, $C5:1FEA) looks along its row and column (Unity MagnetBomb.cs: 4
; directions, 12 cells, the view stops at a wall, a soft block, a bomb or a bomber) for the nearest enemy (actors
; 5 and up, alive). One 2 or more cells away: the bomb is kicked that way (SB5's kick: rolling, speed 2, its sound)
; and rolls until something stops it, next to the enemy. Then it waits 60 frames at rest before looking again
; (Unity: reattractDelaySeconds = 1); nothing in view: it looks again 4 frames later (Unity: every 0.08 s).

asar 1.90
hirom

!MAG = $7FFB2C          ; 20 bytes (docs/FREE_SPACE.md)
!RANGE = 12
!WAIT = 60
!AGAIN = 4

org !C5

; $C5:1AFC / $C5:1BA5 (both bomb allocators, X = bomb): was STZ $0ECC,X
mg_alloc:
    stz $0ECC,x
    pha
    lda #$00
    sta.l !MAG,x
    sta.l $7FE9C0,x             ; not in a Yellow Louie train (asm/louie_abilities.asm !TRAIN)
    pla
    rts

; $C4:3050 (a bomber drops a bomb; A = its abilities, X = seat, Y = bomb): was AND #$11 / STA $0ECC,Y
mg_place:
    pha
    and #$11
    sta $0ECC,y
    pla
    and #$20
    beq +
    lda $1752,x                 ; bombs out, this one counted: only the first is a magnet bomb (like SB5's search
    dec                         ; bomb, $C4:3064)
    beq .first
    lda #$00
    bra +
.first:
    lda #$80                    ; a magnet bomb: looks at once
+   phx
    tyx
    sta.l !MAG,x
    plx
    rtl

; $C5:1FEA (JMP; a bomb at rest, X = bomb, DB = $80, M/X 8-bit): was JMP $2058
mg_rest:
    lda.l !MAG,x
    bpl .out
    and #$7F
    beq .look
    lda.l !MAG,x
    dec
    sta.l !MAG,x
.out:
    jmp $2058
.look:
    lda $0F38,x                 ; (between two cells: not now)
    and #$0F
    bne .out
    jsr mg_find
    bcc .none
    sta $B2
    lda $0E90,x                 ; SB5's kick ($C5:22E6): rolling, that direction, speed 2
    and #$E0
    ora #$10
    ora $B2
    sta $0E90,x
    lda #$10
    sta $0F38,x
    lda #$02
    sta $0F4C,x
    lda $0EE0,x
    and #$FE
    sta $0EE0,x
    lda #$02
    xba
    lda #$07                    ; SB5's kick sound
    jsl $C00CED
    lda #$80|!WAIT
    sta.l !MAG,x
    jmp $2058
.none:
    lda #$80|!AGAIN
    sta.l !MAG,x
    jmp $2058

; Direction (1 right, 2 down, 3 left, 4 up; carry set) of the nearest enemy in view 2-12 cells away, else carry
; clear. X = bomb (kept). Scratch (SB5's bomb code temporaries): $9F, $A1, $A5-$A8 (nearest enemy each way),
; $B1 (bomb cell), $B3, $B4.
mg_find:
    phx
    lda $0E7C,x
    sta $B1
    lda #$FF
    sta $A5
    sta $A6
    sta $A7
    sta $A8
    ldx $198C                   ; last actor
.actor:
    cpx #$05                    ; (0-4: the bombers)
    bcc .ways
    lda $17FA,x
    bmi .next
    lda $15A2,x
    bmi .next
    lda $16AA,x
    eor $B1
    beq .next
    bit #$F0
    beq .row
    bit #$0F
    bne .next
    lda $16AA,x                 ; same column: distance in rows
    lsr
    lsr
    lsr
    lsr
    sta $9F
    lda #$01                    ; (way index: down)
    sta $B4
    lda $B1
    lsr
    lsr
    lsr
    lsr
    bra .dist
.row:
    lda $16AA,x
    and #$0F
    sta $9F
    stz $B4                     ; right
    lda $B1
    and #$0F
.dist:
    sec
    sbc $9F                     ; bomb - enemy
    bcs .before
    eor #$FF                    ; enemy after the bomb: right / down
    inc
    bra .keep
.before:
    pha                         ; enemy before the bomb: left / up
    lda $B4
    ora #$02
    sta $B4
    pla
.keep:
    phx
    ldx $B4
    cmp $A5,x
    bcs +
    sta $A5,x
+   plx
.next:
    dex
    bra .actor
.ways:
    lda #$FF
    sta $B3                     ; best distance
    stz $B4                     ; best way + 1
    ldx #$00
.way:
    lda $A5,x
    cmp #$02
    bcc .skip
    cmp #!RANGE+1
    bcs .skip
    cmp $B3
    bcs .skip
    phx
    jsr mg_clear
    plx
    bcc .skip
    lda $A5,x
    sta $B3
    txa
    inc
    sta $B4
.skip:
    inx
    cpx #$04
    bcc .way
    plx
    lda $B4
    cmp #$01                    ; carry set = found
    rts

; Carry set if the cells between the bomb ($B1) and the nearest enemy of way X (0 right, 1 down, 2 left, 3 up;
; $A5,X cells away) are free: no wall, soft block or bomb ($1052 & $E8), no bomber.
mg_clear:
    lda $A5,x
    dec
    sta $9F                     ; cells to test
    lda.l $808CCD,x             ; SB5's cell steps ($80:8CCC + way 1-4)
    sta $A1
    lda $B1
.cell:
    clc
    adc $A1
    tax
    lda $1052,x
    and #$E8
    bne .no
    txa
    ldy #$04
-   pha
    lda $17FA,y
    bmi +
    lda $15A2,y
    bmi +
    pla
    cmp $16AA,y
    beq .no
    bra ++
+   pla
++  dey
    bpl -
    dec $9F
    bne .cell
    sec
    rts
.no:
    clc
    rts

end_c5:

print "SYM mg_alloc ", hex(mg_alloc)
print "SYM mg_place ", hex(mg_place)
print "SYM mg_rest ", hex(mg_rest)
print "SYM end_c5 ", hex(end_c5)
