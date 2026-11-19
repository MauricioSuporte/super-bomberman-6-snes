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
;   n = 4  (1-6's third duel, type 04) the stands blink (stand_task, below)
;   n = 5  (1-7, type 04) start the electric fence's task (asm/stage_anim.asm) and the clown
;          boss's (asm/sb1_enemies.asm clown_start)
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
    dec a
    dec a
    bne +
    jsr stand_start             ; 4: the stands blink (1-6's Golden Bomber)
    plp
    rtl
+   dec a
    bne +
if !ANIMSTART
    jsl !ANIMSTART              ; 5: 1-7's electric fence (asm/stage_anim.asm)
endif
    jsl !CLOWNSTART             ;    and its clown (asm/sb1_enemies.asm clown_start)
    plp
    rtl
+   lda #$00                    ; 3: forget, start the picking task
    sta.l !DX
    ldx #$B0                    ; and clear the chameleons' state (asm/sb1_enemies.asm, $7F:FB20-$7F:FBCF)
-   dex
    sta.l $7FFB20,x
    cpx #$00
    bne -
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
; 1-7's clown (enemy type !CLOWN_TYPE) is tested on the 3 x 3 cells around it
; instead (asm/sb1_enemies.asm clown_hit).
knight_hit:
    lda $16C2,x                 ; 1-7's clown: flames on the 3 x 3 cells around it
    cmp #!CLOWN_TYPE
    bne +
    jsl !CLOWNHIT
    bcc .none
    jml $C349F3
+   lda $1052,y
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

; ---------------------------------------------------------------------------
; 1-6, the tournament (SB6 Unity scene): three duels, stages !RIVAL1/2/3, each
; one rival (seat 4) drawn with character 1's sheet (the mecha bomber) and
; one column of its palette picture (rival_pal); the third is the Golden
; Bomber: 3 hits (2 hearts, $1662), kick (rival_stats), and the stands blink between the crowd and empty before
; it (stand_task). The arena is theme $28 / set 4 archive and palette $F0
; (features/sb1_stages.py "sb6_1-6"), ids past SB5's tables: arc_entry and
; bombers.asm's pal_lookup point at the World 1 entries.

; $C0:1B0E (archive loader, A = M 8-bit, Y = id - 1, X = set * 2): replaces
; LDA #$E3 / STA $C8 / REP #$20 / LDA $C01C96,X / STA $C6 (returns M 16-bit)
arc_entry:
    lda $0AE7
    cmp #$04
    bne .orig
    tya
    cmp #$EF
    bcc .orig
    lda.b #(!W1ARC-8*$EF)>>16
    sta $C8
    rep #$20
    lda.w #(!W1ARC-8*$EF)&$FFFF
    sta $C6
    rtl
.orig:
    lda #$E3
    sta $C8
    rep #$20
    lda.l $C01C96,x
    sta $C6
    rtl

; $C4:3CD5 (rival set-up $C4:3CCF, X = seat, A = character already in
; $16C2,X): replaces TAX / LDA $BB4E,X / CLC / ADC #$07 (A = palette id)
rival_pal:
    pha                         ; the character
    cpx #$04
    bne .stock
    phx
    lda.l $7E1031
    ldx #$02
-   cmp.l .stages,x
    beq .ours
    dex
    bpl -
    plx
.stock:
    plx                         ; (PLX after us restores the seat)
    lda $BB4E,x
    clc
    adc #$07
    rtl
.ours:
    lda #$01                    ; character 1 (the mecha bomber sheet)
    sta $16C2+4
    lda.l .ids,x
    plx
    plx
    rtl
.stages:
    db !RIVAL1, !RIVAL2, !RIVAL3
.ids:
    db !PAL1, !PAL2, !PAL3

; $C4:3D28 (end of the rival set-up: its stats from the character's table
; $C0:B9D4, here the last one): replaces LDA ($BD),Y / STA $167A,X (X =
; seat). 1-6's rivals: 1 hit (no heart), the Golden Bomber 3 (2 hearts) and
; the kick ($167A bit 6 + $7E:4ED5 bit 1, as item $0B gives)
rival_stats:
    lda ($BD),y
    sta $167A,x
    cpx #$04
    bne .out
    lda.l $7E1031
    cmp #!RIVAL1
    beq .one
    cmp #!RIVAL2
    beq .one
    cmp #!RIVAL3
    bne .out
    lda $167A,x
    ora #$40
    sta $167A,x
    lda.l $7E4ED5+4
    ora #$02
    sta.l $7E4ED5+4
    lda #$02
    bra +
.one:
    lda #$00
+   sta $1662,x
.out:
    rtl

; FF 1A F6 04 (stage !RIVAL3, type 04): the stands blink. Task: after
; BWAIT frames, 5 times: fade to black (brightness in the INIDISP shadow
; $0300), stands empty on cycles 0/2/4 and full on 1/3 (BG1 map words
; through SB5's VRAM queue, $C0:0478/0497/04AC), hold, fade back in.
; State $7F:FBD0 phase, $FBD1 frames, $FBD2 cycle, $FBD3 brightness.
!BPH = $7FFBD0
!BFR = $7FFBD1
!BCY = $7FFBD2
!BBR = $7FFBD3

stand_start:
    lda #$00
    sta.l !BPH
    sta.l !BCY
    lda #90
    sta.l !BFR
    jsl $C020A1
    dl stand_task
    db $60
    rts

stand_task:
    php
    sep #$30
    lda.l !BFR
    beq +
    dec a
    sta.l !BFR
    bra .out
+   lda.l !BPH
    beq .fadeout
    dec a
    beq .black
    dec a
    beq .fadein
    jsl $C021CE                 ; done
    bra .out
.fadeout:                       ; phase 0: brightness 15 -> 0, 2 frames a step
    lda.l !BBR
    bne +
    lda #$10
+   dec a
    sta.l !BBR
    sta $0300
    bne .two
    jsr stands
    lda #$01
    sta.l !BPH
    lda #30
    sta.l !BFR
    bra .out
.black:                         ; phase 1 done: fade in
    lda #$02
    sta.l !BPH
    bra .out
.fadein:
    lda.l !BBR
    inc a
    sta.l !BBR
    sta $0300
    cmp #$0F
    bne .two
    lda #$00
    sta.l !BBR
    lda.l !BCY
    inc a
    sta.l !BCY
    cmp #$05
    bcc +
    lda #$03                    ; ends next frame
    sta.l !BPH
    bra .out
+   lda #$00
    sta.l !BPH
    lda #20
    sta.l !BFR
    bra .out
.two:
    lda #$01
    sta.l !BFR
.out:
    plp
    rtl

; queue the stands' BG1 map words: cycle even -> empty, odd -> crowd
stands:
    rep #$30
    lda $0352
    pha
    lda.w #$0084
    sta $0352
    lda.l !BCY
    and.w #$0001
    beq +
    lda.w #!BLINKN*6
+   clc
    adc.w #!BLINK&$FFFF
    tax
    ldy.w #!BLINKN
-   lda.l (!BLINK&$FF0000),x
    sta $AE
    phx
    phy
    sep #$30                    ; (SB5's queue routines: PHX ... SEP #$30 / PLX)
    jsl $C00478
    rep #$30
    ply
    plx
    lda.l (!BLINK&$FF0000)+2,x
    sta $A5
    phx
    phy
    sep #$30                    ; (SB5's queue routines: PHX ... SEP #$30 / PLX)
    jsl $C00497
    rep #$30
    ply
    plx
    lda.l (!BLINK&$FF0000)+4,x
    sta $A5
    phx
    phy
    sep #$30
    jsl $C00497
    jsl $C004AC
    rep #$30
    ply
    plx
    inx
    inx
    inx
    inx
    inx
    inx
    dey
    bne -
    pla
    sta $0352
    sep #$30
    rts

print "SYM arc_entry ", hex(arc_entry)
print "SYM rival_pal ", hex(rival_pal)
print "SYM rival_stats ", hex(rival_stats)
print "SYM w1_op ", hex(w1_op)
print "SYM knight_hit ", hex(knight_hit)
print "SYM end ", hex(pc())
