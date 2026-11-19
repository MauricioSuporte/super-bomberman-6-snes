; World 1 (tools/sb6/features/world1.py): the SB1-style exit door.
;
; w1_op (FF 1A F6 n, through pick_op; M/X 8-bit, [$0D] = the F6, [$0A] = n,
; the op skips it): one exit portal per stage, hidden in a soft block chosen
; at random when the stage starts. SB5's portal queue ($7E:4DA3, 5 slots:
; state $41/$42, x $4DA8, y $4DAD; task $C5:3B60 creates the portal once
; the stage is clear and waits while its cell holds a soft block) does the
; rest, so the door shows up when its block burns after the last enemy died
; (at once if it already burnt).
;   n = 3  (stage record, type 04: stage start) forget the door and start
;          a task (JSL $C020A1) that waits for the collision map (filled
;          some 50 frames after the type 04 scripts, which run one after
;          the other in one task: a sleep there would hold the stage setup)
;          and picks the door: a random cell with a soft block ($1052 & $E0
;          = $20) and no hidden item ($145A); none -> 0 (picked again at the
;          clear); then it ends (JSL $C021CE)
;   n = 1  (type 0D: all enemies dead) queue the portal at the door (a soft
;          block left, else a free floor cell)
;   n = 2  (type 0C) players on the door: like op $12 ($C2:0C67), the sum
;          of seat + 1 of the live bombers on the cell -> $0373, JSL $C174D1
; State: $7F:FB10 door x (0 = not chosen), $7F:FB11 door y, $7F:FB12-$7F:FB13
; scratch (docs/FREE_SPACE.md).

asar 1.90
hirom
org !ORG

!DX    = $7FFB10
!DY    = $7FFB11
!CNT   = $7FFB12
!K     = $7FFB13

w1_op:
    php
    sep #$30
    lda [$0A]                   ; n, then skip it
    pha
    rep #$20
    inc $0A
    sep #$20
    pla
    beq .pick
    dec a
    beq .queue
    dec a
    beq .touch
    lda #$00                    ; 3: forget, start the picking task
    sta.l !DX
    jsl $C020A1
    dl door_task
    db $60                      ; skipped: $C020A1 returns one byte past the dl (SB5's own callers have an RTS there)
    plp
    rtl

.touch:
    jsr touch
    plp
    rtl
.pick:
    jsr pick
    plp
    rtl
.queue:
    lda.l !DX
    bne +
    jsr pick
    lda.l !DX
    bne +
    jsr floor
+   ldx #$00
-   lda.l $7E4DA3,x
    bmi +
    inx
    cpx #$05
    bne -
    bra ++
+   lda #$41
    sta.l $7E4DA3,x
    lda.l !DX
    sta.l $7E4DA8,x
    lda.l !DY
    sta.l $7E4DAD,x
++  plp
    rtl

door_task:
    php
    sep #$30
    lda.l $7E1052               ; corner cell: a wall once the map is in
    beq +
    jsr pick
    jsl $C021CE                 ; end this task
+   plp
    rtl

; A = cell's flags ok? (soft block, no item) -> Z set when usable
soft:
    lda.l $7E1052,x
    and #$E0
    cmp #$20
    bne +
    lda.l $7E145A,x
+   rts

pick:
    lda #$00
    sta.l !DX
    sta.l !CNT
    ldx #$11                    ; field cells 17-206 (rows 1-11)
-   jsr soft
    bne +
    lda.l !CNT
    inc a
    sta.l !CNT
+   inx
    cpx #$CF
    bne -
    lda.l !CNT
    beq .out
    jsl $C01DC4                 ; random byte
-   cmp.l !CNT
    bcc +
    sec
    sbc.l !CNT
    bra -
+   sta.l !K
    ldx #$11
-   jsr soft
    bne +
    lda.l !K
    beq .got
    dec a
    sta.l !K
+   inx
    cpx #$CF
    bne -
.out:
    rts
.got:
    txa
    and #$0F
    sta.l !DX
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !DY
    rts

; no soft block left: the first free floor cell from the middle of the field
floor:
    ldx #$77                    ; x 7, y 7
-   lda.l $7E1052,x
    ora.l $7E1152,x
    beq +
    inx
    cpx #$CF
    bne -
    ldx #$11
    bra -
+   txa
    and #$0F
    sta.l !DX
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !DY
    rts

touch:
    stz $9F
    ldx #$00
.seat:
    lda.l $7E15A2,x
    bmi .next
    lda.l $7E182A,x
    clc
    adc #$08
    lsr a
    lsr a
    lsr a
    lsr a
    cmp.l !DX
    bne .next
    lda.l $7E1872,x
    clc
    adc #$08
    and #$F0
    lsr a
    lsr a
    lsr a
    lsr a
    cmp.l !DY
    bne .next
    txa
    inc a
    clc
    adc $9F
    sta $9F
.next:
    inx
    cpx #$04
    bcc .seat
    lda $9F
    sta.l $7E0373
    jsl $C174D1
    rts

;-----------------------------------------------------------------------------
; knight_hit: $C3:49EC (LDA $1052,Y : AND #$04), the flame test of an enemy
; (X = actor, Y = its cell, M/X 8-bit; SEC = hit, through $C3:49F3). On
; World 1's 1-5 (stage !KNIGHT_STAGE) the knights (enemy type $08) are
; not hurt by a blast coming from the front, as in SB1's 6-4: facing
; $1632 (1 right, 2 down, 3 left, 4 up), the flame cells from the knight's
; one in that direction lead to the explosion's center ($1052 & 7 = 5).
knight_hit:
    lda $1052,y
    and #$04
    beq .none
    lda.l $7E1031
    cmp #!KNIGHT_STAGE
    bne .orig
    lda $16C2,x
    cmp #$08
    bne .orig
    phx
    lda $1632,x
    dec a
    and #$03
    tax
    lda.l .step,x
    sta.l !K
    tya
    tax
    lda #$0C                    ; at most 12 cells
    sta.l !CNT
-   txa
    clc
    adc.l !K
    tax
    lda.l $7E1052,x
    and #$07
    cmp #$05
    beq .front
    and #$04
    beq .side
    lda.l !CNT
    dec a
    sta.l !CNT
    bne -
.side:
    plx
.orig:
    jml $C349F3
.front:
    plx
.none:
    jml $C34A04                 ; CLC : RTS (not hit)
.step:
    db $01, $10, $FF, $F0       ; right, down, left, up

print "SYM w1_op ", hex(w1_op)
print "SYM knight_hit ", hex(knight_hit)
print "SYM end ", hex(pc())
