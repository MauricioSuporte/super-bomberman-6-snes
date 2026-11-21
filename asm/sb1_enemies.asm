; SB1 enemies with their own routines (tools/sb6/features/sb1_enemies.py). SB1 3-6's chameleons (1-3)
; are asm/chameleon.asm.

asar 1.90
hirom
org !ORG

; ---------------------------------------------------------------------------
; SB1 2-8's clown mask, World 1's 1-7 boss. Drawn on BG2 below the HUD: SB5's
; stage IRQ ($C0:F08D) draws the HUD with BG2 = its background, then at line
; 21 sets BG2's map ($0369), TM ($030F) and at line 23 BG2's scroll ($031B /
; $0321, low bytes) for the field, where BG2 was only seen in the margins.
; Tiles at VRAM $3400 (tiles $340-$37F of BG2's base 0: BG1's lower screen,
; never shown; $360-$37F are rewritten when the mouth opens / closes, as
; SB1's), maps at $4800 / $4C00 (free; blank = tile 0); colors in BG palettes
; 3 and 6 (the arena's palette leaves them free). Its body is an enemy (type
; !CLOWN_TYPE) with an empty picture: clown = its actor routine, SB5's walker
; and then the position of the clown's center (field pixels !CX / !CY, cell
; $16AA,x), which floats toward the nearest live player 1 px every !CSTEP
; frames over everything. Hits are SB5's: enemy hearts $1662,x (!CHP) and
; $085F,obj frames of blinking after a hit; clown_hit tests the 3 x 3 cells
; around the center for flames. clown_start (JSL, from world1's op 5) queues
; the tiles and the map and starts clown_task (BG2 off once it dies).
!CX    = $7FFBE8
!CY    = $7FFBE9
!CSEEN = $7FFBEA
!CTICK = $7FFBEB
!CSET  = $7FFBEC
!CQS   = $7FFBEE          ; queue scratch: source (word), VRAM, bytes left, entry size
!CQV   = $7FFBF0
!CQL   = $7FFBF2
!CQN   = $7FFBF4
!CVIS  = $7FFBF6          ; drawn this frame (not blinking)
!CBLK  = $7FFBF7          ; blink counter
!CMOUTH = $7FFBF8         ; frames left with the mouth so
!CMST  = $7FFBF9          ; 0 closed, 1 open
!CVTILES = $3400          ; VRAM: tiles $340-$37F of BG2's base 0 (BG1's unused lower screen): $340-$35F
!CVOWN = $3600            ; both pictures', $360-$37F the shown picture's own
!CVMAP = $4800            ; VRAM: BG2 maps, 32 x 32: mouth open $4800, closed $4C00
!COPENSC = $48
!CSHUT = $4C
!CTSHUT = 150             ; frames with the mouth closed / open (SB1: ~40-80 open every ~200)
!CTOPEN = 60
!CHUDSC = $3A
!CSTEP = 3
!CHP   = 6

clown_start:
    php
    sep #$30
    lda #$00
    sta.l !CSET
    sta.l !CSEEN
    lda #!CSHUT                 ; BG2's map below the HUD (SB5's IRQ writes it at line 21): mouth closed
    sta.l $7E0369
    lda #!CTSHUT
    sta.l !CMOUTH
    lda #$00
    sta.l !CMST
    rep #$30
    lda.w #!CTILES&$FFFF        ; shared tiles + the closed mouth's
    ldx.w #!CVTILES
    ldy.w #$0800
    jsr cqueue
    lda.w #!CMAP&$FFFF          ; both maps
    ldx.w #!CVMAP
    ldy.w #$1000
    jsr cqueue
    sep #$30
    jsl $C020A1
    dl clown_task
    db $60                      ; skipped ($C020A1 returns past the dl)
    plp
    rtl

clown_task:
    php
    sep #$30
    lda.l $7E1031
    cmp #!CSTAGE
    beq +
    jsl clown_stop
    jsl $C021CE                 ; stage over: end the task
    plp
    rtl
+   plp
    jml clown_tick

; queue Y bytes from bank !CBANK offset A to VRAM word X (entries of 256 bytes); M/X 16-bit
cqueue:
    sta.l !CQS
    txa
    sta.l !CQV
    tya
    sta.l !CQL
-   lda.l !CQL
    cmp.w #$0100
    bcc +
    lda.w #$0100
+   sta.l !CQN
    lda.l $7E0357
    tax
    lda.w #$0084
    sta.l $7E8000,x
    lda.l !CQN
    sta.l $7E8002,x
    lda.l !CQV
    sta.l $7E8004,x
    txa
    clc
    adc.w #$8006
    tay
    lda.l !CQS
    tax
    lda.l !CQN
    dec a
    phb
    db $54, $7E, !CBANK         ; MVN $7E <- !CBANK
    plb
    lda.l $7E0357
    clc
    adc.w #6
    adc.l !CQN
    and.w #$3FFF
    sta.l $7E0357
    lda.l !CQS
    clc
    adc.l !CQN
    sta.l !CQS
    lda.l !CQN
    lsr a
    clc
    adc.l !CQV
    sta.l !CQV
    lda.l !CQL
    sec
    sbc.l !CQN
    sta.l !CQL
    bne -
    rts

clown:
    phx
    jsl $C34B5A                 ; SB5's walker (contact with the players, death)
    sep #$30
    plx
    lda.l !CSET
    bne +
    lda #$01
    sta.l !CSET
    lda #!CHP
    sta $1662,x
    lda $182A,x
    clc
    adc #$08
    sta.l !CX
    lda $1872,x
    clc
    adc #$08
    sta.l !CY
+   lda #$03
    sta.l !CSEEN
    lda.l !CTICK                ; move every !CSTEP frames
    inc a
    cmp #!CSTEP
    bcc +
    lda #$00
+   sta.l !CTICK
    bne .place
    jsr target                  ; Y = seat, or $FF
    cpy #$FF
    beq .place
    lda $182A,y
    clc
    adc #$08
    cmp.l !CX
    beq .y
    lda.l !CX
    bcs +
    dec a
    dec a
+   inc a
    cmp #40
    bcc .y
    cmp #217
    bcs .y
    sta.l !CX
.y: lda $1872,y
    clc
    adc #$08
    cmp.l !CY
    beq .place
    lda.l !CY
    bcs +
    dec a
    dec a
+   inc a
    cmp #40
    bcc .place
    cmp #185
    bcs .place
    sta.l !CY
.place:
    lda.l !CX
    sec
    sbc #$08
    sta $182A,x
    lda.l !CY
    sec
    sbc #$08
    sta $1872,x
    lda.l !CY
    and #$F0
    sta.l !CQN
    lda.l !CX
    lsr a
    lsr a
    lsr a
    lsr a
    ora.l !CQN
    sta $16AA,x
    ; BG2 scroll (the IRQ uses its low bytes from line 23): the picture's top left = center - (!COX,
    ; !COY), screen = field - BG1 scroll
    rep #$20
    lda.l !CX
    and.w #$00FF
    sec
    sbc.w #!COX
    eor.w #$FFFF
    inc a
    clc
    adc $0319                   ; BG1 H scroll
    sta $031B
    lda.l !CY
    and.w #$00FF
    sec
    sbc.w #!COY
    eor.w #$FFFF
    inc a
    clc
    adc $031F                   ; BG1 V scroll
    sta $0321
    sep #$20
    lda.l !CMOUTH               ; the mouth: its own tiles and map
    dec a
    sta.l !CMOUTH
    bne .mouthed
    phx
    lda.l !CMST
    eor #$01
    sta.l !CMST
    beq .shut
    lda #!CTOPEN
    sta.l !CMOUTH
    lda #!COPENSC
    sta.l $7E0369
    rep #$30
    lda.w #!COPEN&$FFFF
    bra +
.shut:
    lda #!CTSHUT
    sta.l !CMOUTH
    lda #!CSHUT
    sta.l $7E0369
    rep #$30
    lda.w #!CCLOSED&$FFFF
+   ldx.w #!CVOWN
    ldy.w #$0400
    jsr cqueue
    sep #$30
    plx
.mouthed:
    lda #$01                    ; shown, but blinking after a hit ($085F + obj)
    sta.l !CVIS
    ldy $17FA,x
    bmi +
    lda $085F,y
    beq +
    lda.l !CBLK
    inc a
    sta.l !CBLK
    and #$04
    beq +
    lda #$00
    sta.l !CVIS
+   rtl

; nearest live player (seats 0-3) -> Y, $FF = none
target:
    ldy #$FF
    lda #$FF
    sta.l !CQN+1
    phx
    ldx #$00
-   lda $17FA,x                 ; a bomber object (as pick)
    cmp #$60
    bcs .next
    phy
    tay
    lda $04FF,y
    ply
    cmp #$10
    bcc .next
    cmp #$1A
    bcs .next
    lda $182A,x
    clc
    adc #$08
    sec
    sbc.l !CX
    bcs +
    eor #$FF
    inc a
+   sta.l !CQN
    lda $1872,x
    clc
    adc #$08
    sec
    sbc.l !CY
    bcs +
    eor #$FF
    inc a
+   clc
    adc.l !CQN
    bcs .next
    cmp.l !CQN+1
    bcs .next
    sta.l !CQN+1
    txy
.next:
    inx
    cpx #$04
    bcc -
    plx
    rts

; every frame (clown_task): BG2 on the field (TM shadow $030F, which the IRQ writes below the HUD) while
; the clown is drawn; off once its routine is no longer called (dead: !CSEEN)
clown_tick:
    php
    sep #$20
    lda.l !CSEEN
    beq .hide
    dec a
    sta.l !CSEEN
    beq .hide
    lda.l !CVIS
    beq .hide
    lda.l $7E030F
    ora #$02
    bra +
.hide:
    lda.l $7E030F
    and #$FD
+   sta.l $7E030F
    plp
    rtl

; stage over: BG2 back to the HUD's background
clown_stop:
    php
    sep #$20
    lda #!CHUDSC
    sta.l $7E0369
    lda.l $7E030F
    ora #$02
    sta.l $7E030F
    plp
    rtl

; flame test of the clown (from world1's knight_hit, X = actor, Y = its cell): a flame on one of the 3 x 3
; cells around it -> carry set
clown_hit:
    phy
    tya
    sec
    sbc #$11
    tay
    lda #$03
    sta.l !CQN
-   lda $1052,y
    ora $1053,y
    ora $1054,y
    and #$04
    bne .hit
    tya
    clc
    adc #$10
    tay
    lda.l !CQN
    dec a
    sta.l !CQN
    bne -
    ply
    clc
    rtl
.hit:
    ply
    sec
    rtl

; ---------------------------------------------------------------------------
; SB1 2-1's enemies in World 1's 1-2, moved as SB1 moves them (SB1 ROM, objects $1000+$40*n; docs/ROM_MAP.md
; "SB1's 2-1 enemies"): sb1_spring / sb1_pot / sb1_face are the actor routines of their records (types 02,
; 03, 06; called through JML [$A5], X = actor, Y = object, M/X 8-bit, DB = $80, RTL). Every frame: SB5's
; contact and flame step ($C3:4B7B, as SB5's walker $C3:4B5A), then SB1's brain and step, then SB5's sprite
; position and cell bit ($C3:4CFC). SB1's coordinates are SB5's + 8 (cell centers), its directions 0 up,
; 1 right, 2 down, 3 left (SB5's facing: 4, 1, 2, 3). SB1's step ($C6:360E): 1/2 px a frame (speed 0 of
; $C6:36BB), first 1 px toward the center of the column (row) when going up or down (sideways); a step
; that ends within 16 px of another enemy is taken back, and then 1 time in 4 (a random direction equal to
; its own) or when the way on is shut it turns around. A cell shuts the way ($C6:1562-$15CE: the next cell
; once the center is reached) when its $1052 has the kind's bits: SB5's enemy mask $E8 for SB1's $E0
; (walls, soft blocks, bombs), $C8 for the pot's $A0 (it goes through soft blocks). Animations restart at
; every new direction after a step (SB1 $C6:2814).
;   spring head ($C6:3947): straight on; at a wall, across toward the nearest live player (|dx| + |dy|,
;     $C6:39C0) when that way is open and the player is not in line, else a quarter turn clockwise;
;   pot ($C6:37B0): every 16-79 frames, on a cell's center, a random direction; at a wall a random one;
;   clown face ($C6:3774): at a wall turns around, every 3-6th wall a quarter turn clockwise instead.
!WSET  = $7FF700          ; per actor (24 bytes each): $A5 once set up
!WDIR  = $7FF718          ; SB1 direction
!WT    = $7FF730          ; SB1's $21: the pot's turn timer, the face's walls left
!WLAST = $7FF748          ; SB1's $22: direction of the animation shown ($FF: none yet)
!WKIND = $7FF760          ; scratch: 0 spring, 1 pot, 2 face
!WMASK = $7FF761          ; scratch: $1052 bits that shut the way
!WSAV  = $7FF762          ; scratch: x sub, x, y sub, y before a step
!WNEW  = $7FF766          ; scratch: direction tried
!WBEST = $7FF767          ; scratch: nearest seat
!WDIST = $7FF768          ; scratch: its distance (word)
!WTMP  = $7FF76A          ; scratch (word)
!WSX   = $7FF76C          ; scratch: own x, y, actor
!WSY   = $7FF76D
!WSELF = $7FF76E
!WNEAR = $7FF76F          ; 1 while $C3:4B7B runs for one of these: co-op's c3_near skips far seats

macro c3(addr)            ; JSR to a bank $C3 routine ending in RTS: it returns to the RTL at $C3:4B7A
    phk
    per ?back-1
    pea $4B79
    jml <addr>
?back:
endmacro

sb1_spring:
    lda #$00
    bra sb1w
sb1_pot:
    lda #$01
    bra sb1w
sb1_face:
    lda #$02
sb1w:
    sta.l !WKIND
    lda $0E20
    ora $0E21
    beq +
    jml $C34C13                 ; stop-watch: SB5's frozen enemy (contact and flames only), as $C5:4319
+   stz $1FF2
    lda #$01
    sta.l !WNEAR
    %c3($C34B7B)                ; contact with the players, flames
    lda #$00                    ; (keeps C)
    sta.l !WNEAR
    bcc +
    rtl                         ; dead
+   lda.l !WSET,x
    cmp #$A5
    beq +
    jsr wsetup
+   lda.l !WKIND
    beq .spring
    dec a
    beq .pot
    jsr face
    bra .done
.pot:
    jsr pot
    bra .done
.spring:
    jsr spring
.done:
    lda.l !WDIR,x               ; SB5's facing
    bne +
    lda #$04
+   sta $1632,x
    %c3($C34CFC)                ; sprite position, the cell's enemy bit
    rtl

; first frame: SB1's start (every enemy facing down, its animation from the start; $21 = $40 for the pot,
; 3 for the face, $22 = $FF), whole pixels
wsetup:
    lda #$A5
    sta.l !WSET,x
    lda #$02
    sta.l !WDIR,x
    lda #$FF
    sta.l !WLAST,x
    lda.l !WKIND
    cmp #$01
    bne +
    lda #$40
    bra .t
+   lda #$03
.t:
    sta.l !WT,x
    stz $1812,x
    stz $185A,x
    lda #$02
    jmp anim

spring:
    lda #$E8
    sta.l !WMASK
    lda.l !WDIR,x
    jsr blocked
    bne .wall
    jsr step
    bcs +
    jsr show
+   rts
.wall:
    jsr nearest
    bcc .turn
    lda.l !WDIR,x
    lsr a
    bcs .across
    lda $182A,y                 ; going up / down: right or left toward the player
    cmp $182A,x
    beq .turn
    lda #$01
    bcs .try
    lda #$03
    bra .try
.across:
    lda $1872,y                 ; going right / left: down or up
    cmp $1872,x
    beq .turn
    lda #$02
    bcs .try
    lda #$00
.try:
    sta.l !WNEW
    jsr blocked
    bne .turn
    lda.l !WNEW
    sta.l !WDIR,x
    rts
.turn:
    lda.l !WDIR,x
    inc a
    and #$03
    sta.l !WDIR,x
    rts

pot:
    lda #$C8
    sta.l !WMASK
    lda.l !WT,x
    dec a
    sta.l !WT,x
    bne .go
    inc a
    sta.l !WT,x
    lda $182A,x                 ; only on a cell's center
    ora $1872,x
    and #$0F
    bne .go
    jsl $C01DC4
    and #$3F
    clc
    adc #$10
    sta.l !WT,x
    jsl $C01DC4
    and #$03
    sta.l !WDIR,x
.go:
    lda.l !WDIR,x
    jsr blocked
    beq +
    jsl $C01DC4
    and #$03
    sta.l !WDIR,x
    rts
+   jsr step
    bcs +
    jsr show
+   rts

face:
    lda #$E8
    sta.l !WMASK
    lda.l !WDIR,x
    jsr blocked
    beq .go
    lda.l !WT,x
    dec a
    sta.l !WT,x
    bne .back
    lda.l !WDIR,x
    inc a
    and #$03
    sta.l !WDIR,x
    jsl $C01DC4
    and #$03
    clc
    adc #$03
    sta.l !WT,x
    rts
.back:
    lda.l !WDIR,x
    eor #$02
    sta.l !WDIR,x
    rts
.go:
    jsr step
    bcs +
    jsr show
+   rts

; after a step: a direction other than the animation's -> its animation from the start
show:
    lda.l !WDIR,x
    cmp.l !WLAST,x
    beq +
    sta.l !WLAST,x
    jsr anim
+   rts

; A = direction: the kind's animation of that facing, from its first frame
anim:
    cmp #$00
    bne +
    lda #$04
+   dec a
    sta.l !WTMP
    phx
    lda.l !WKIND
    tax
    lda.l .base,x
    plx
    clc
    adc.l !WTMP
    ldy $17FA,x
    phx
    phy
    jsl $C011EC
    sep #$30
    ply
    plx
    rts
.base:
    db !ASPRING, !APOT, !AFACE

; A = direction: A = the bits of !WMASK in the cell SB1 tests that way (Z set: open); Y lost
blocked:
    cmp #$01
    beq .r
    cmp #$02
    beq .d
    cmp #$03
    beq .l
    lda $1872,x                 ; up: row of y - 1, column of x + 8
    dec a
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$08
    bra .col
.d:
    lda $1872,x                 ; down: row of y + 16
    clc
    adc #$10
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$08
    bra .col
.r:
    lda $1872,x                 ; right: column of x + 16, row of y + 8
    clc
    adc #$08
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$10
    bra .col
.l:
    lda $1872,x                 ; left: column of x - 1
    clc
    adc #$08
    and #$F0
    sta.l !WTMP
    lda $182A,x
    dec a
.col:
    lsr a
    lsr a
    lsr a
    lsr a
    ora.l !WTMP
    tay
    lda $1052,y
    and.l !WMASK
    rts

; SB1's step: carry set when it was taken back (another enemy within 16 px)
step:
    lda $1812,x
    sta.l !WSAV
    lda $182A,x
    sta.l !WSAV+1
    lda $185A,x
    sta.l !WSAV+2
    lda $1872,x
    sta.l !WSAV+3
    lda.l !WDIR,x
    lsr a
    bcs .side
    lda $182A,x                 ; up / down: 1 px toward the column's center
    and #$0F
    beq +
    cmp #$08
    bcs .xin
    dec $182A,x
    bra +
.xin:
    inc $182A,x
+   lda.l !WDIR,x
    bne .down
    lda $185A,x
    sec
    sbc #$80
    sta $185A,x
    lda $1872,x
    sbc #$00
    sta $1872,x
    bra .moved
.down:
    lda $185A,x
    clc
    adc #$80
    sta $185A,x
    lda $1872,x
    adc #$00
    sta $1872,x
    bra .moved
.side:
    lda $1872,x                 ; right / left: 1 px toward the row's center
    and #$0F
    beq +
    cmp #$08
    bcs .yin
    dec $1872,x
    bra +
.yin:
    inc $1872,x
+   lda.l !WDIR,x
    cmp #$01
    bne .left
    lda $1812,x
    clc
    adc #$80
    sta $1812,x
    lda $182A,x
    adc #$00
    sta $182A,x
    bra .moved
.left:
    lda $1812,x
    sec
    sbc #$80
    sta $1812,x
    lda $182A,x
    sbc #$00
    sta $182A,x
.moved:
    jsr touching
    bcs .back
    rts
.back:
    lda.l !WSAV
    sta $1812,x
    lda.l !WSAV+1
    sta $182A,x
    lda.l !WSAV+2
    sta $185A,x
    lda.l !WSAV+3
    sta $1872,x
    jsl $C01DC4
    and #$03
    cmp.l !WDIR,x
    beq .rev
    lda.l !WDIR,x
    jsr blocked
    beq .stay
.rev:
    lda.l !WDIR,x
    eor #$02
    sta.l !WDIR,x
.stay:
    sec
    rts

; carry set: another live enemy (actors 5 to $198C with an enemy type) within 16 px both ways
touching:
    lda $182A,x
    sta.l !WSX
    lda $1872,x
    sta.l !WSY
    txa
    sta.l !WSELF
    ldy #$05
.loop:                              ; (every enemy, every frame: cheapest tests first)
    lda $17FA,y
    bmi .next
    lda $182A,y
    sec
    sbc.l !WSX
    bcs +
    eor #$FF
    inc a
+   cmp #$10
    bcs .next
    lda $1872,y
    sec
    sbc.l !WSY
    bcs +
    eor #$FF
    inc a
+   cmp #$10
    bcs .next
    tya
    cmp.l !WSELF
    beq .next
    lda $16C2,y
    beq .next
    lda $15A2,y
    bmi .next
    sec
    rts
.next:
    cpy $198C
    iny
    bcc .loop
    clc
    rts

; Y = the live player nearest (|dx| + |dy|; the lowest seat on a tie), carry clear when none
nearest:
    lda #$FF
    sta.l !WBEST
    sta.l !WDIST
    sta.l !WDIST+1
    ldy #$00
.loop:
    lda $17FA,y
    bmi .next
    lda $15A2,y
    bmi .next
    lda $182A,y
    sec
    sbc $182A,x
    bcs +
    eor #$FF
    inc a
+   sta.l !WTMP
    lda #$00
    sta.l !WTMP+1
    lda $1872,y
    sec
    sbc $1872,x
    bcs +
    eor #$FF
    inc a
+   rep #$20
    and #$00FF
    clc
    adc.l !WTMP
    cmp.l !WDIST
    bcs +
    sta.l !WDIST
    sep #$20
    tya
    sta.l !WBEST
+   sep #$20
.next:
    iny
    cpy #$05
    bcc .loop
    lda.l !WBEST
    tay
    cmp #$FF
    beq +
    sec
    rts
+   clc
    rts

end:

print "SYM clown ", hex(clown)
print "SYM clown_start ", hex(clown_start)
print "SYM clown_tick ", hex(clown_tick)
print "SYM clown_hit ", hex(clown_hit)
print "SYM sb1_spring ", hex(sb1_spring)
print "SYM sb1_pot ", hex(sb1_pot)
print "SYM sb1_face ", hex(sb1_face)
print "SYM end ", hex(end)
