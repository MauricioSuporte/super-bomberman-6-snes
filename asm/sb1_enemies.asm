; SB1 3-6's chameleons in World 1's 1-3 (tools/sb6/features/sb1_enemies.py): an enemy that is a frog
; (its own pictures) for a while, then a copy of a live player's bomber, then a frog again.
;
; chameleon = the actor routine of its type record (SB5's walkers run $C3:4B5A, called through JML [$A5]
; with X = actor, M/X 8-bit, and ending in RTL). It runs $C3:4B5A itself, then, in the copy phase, gives
; the enemy's object the sprite the player's object shows now: the resolved mapping ($7E:2EEA/$7E:2F4A +
; obj), the tile base ($073F + obj, word) and the palette slot ($06DF + obj), and holds its own script
; ($07A0 + obj = $FF) so that nothing resolves it again. The enemy's own slot and tile base come back
; before $C3:4B5A runs (a hit there releases the object's slot) and when it turns into a frog again.
; Players: actors 0-4, object $17FA + seat, a bomber while its type ($04FF + obj) is $10-$19.
; State per actor (cleared by World 1's stage start op, asm/world1.asm; docs/FREE_SPACE.md):

asar 1.90
hirom
org !ORG

!CST   = $7FFB20      ; 1 once set up
!CTM   = $7FFB38      ; frames left in the phase
!CPH   = $7FFB50      ; 0 frog, 1 copy
!CSEAT = $7FFB68      ; seat copied
!COWNL = $7FFB80      ; own tile base (low, high), own palette slot
!COWNH = $7FFB98
!COWNS = $7FFBB0
!COPY  = 240          ; frames as a bomber
!FROG  = 150          ; frames as a frog
!TMP   = $7FFBC8

chameleon:
    jsr restore
    phx
    jsl $C34B5A
    sep #$30
    plx
    jsr tick
    rtl

; copy phase: own slot / tile base back on the object (X = actor; keeps X)
restore:
    lda.l !CPH,x
    beq +
    ldy $17FA,x
    lda.l !COWNS,x
    sta $06DF,y
    lda.l !COWNL,x
    sta $073F,y
    lda.l !COWNH,x
    sta $0740,y
+   rts

tick:
    ldy $17FA,x
    lda $04FF,y
    cmp #$07
    beq +
    rts                         ; hit: no longer an enemy sprite
+   lda.l !CST,x
    bne +
    lda #$01
    sta.l !CST,x
    lda #$00
    sta.l !CPH,x
    txa                         ; frogs first, each turning at another time
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$14
    sta.l !CTM,x
+   lda.l !CTM,x
    dec a
    sta.l !CTM,x
    bne .run
    lda.l !CPH,x
    bne .tofrog
    jsr pick                    ; frog -> copy of a live player (none: frog a while more)
    bcc .stay
    sta.l !CSEAT,x
    ldy $17FA,x
    lda $06DF,y
    sta.l !COWNS,x
    lda $073F,y
    sta.l !COWNL,x
    lda $0740,y
    sta.l !COWNH,x
    lda #$01
    sta.l !CPH,x
    lda #!COPY
    sta.l !CTM,x
    bra .run
.stay
    lda #$40
    sta.l !CTM,x
    rts
.tofrog
    jsr restore
    lda #$00
    sta.l !CPH,x
    lda #!FROG
    sta.l !CTM,x
    ldy $17FA,x                 ; its own animation again
    lda $079F,y
    phx
    jsl $C011EC
    sep #$30
    plx
    rts
.run
    lda.l !CPH,x
    bne +
    rts
+   phx
    lda.l !CSEAT,x
    tax
    lda $17FA,x
    tax                         ; X = the player's object
    lda $04FF,x
    cmp #$10
    bcc .gone
    cmp #$1A
    bcs .gone
    lda $073F,x
    sta $073F,y
    lda $0740,x
    sta $0740,y
    lda $06DF,x
    sta $06DF,y
    lda #$FF
    sta $07A0,y
    lda.l $7E2EEA,x             ; (no long,Y: through !TMP with X = the enemy's object)
    sta.l !TMP+2
    lda.l $7E2EEB,x
    sta.l !TMP+3
    lda.l $7E2F4A,x
    sta.l !TMP+4
    lda.l $7E2F4B,x
    sta.l !TMP+5
    tyx
    lda.l !TMP+2
    sta.l $7E2EEA,x
    lda.l !TMP+3
    sta.l $7E2EEB,x
    lda.l !TMP+4
    sta.l $7E2F4A,x
    lda.l !TMP+5
    sta.l $7E2F4B,x
    plx
    rts
.gone                           ; the player died / left: frog again
    plx
    jmp .tofrog

; a live player for actor X: seats from X mod 5 on; carry set and A = seat, else carry clear. Keeps X.
pick:
    txa
-   cmp #$05
    bcc +
    sbc #$05
    bra -
+   sta.l !TMP
    lda #$05
    sta.l !TMP+1
    phx
-   lda.l !TMP
    tax
    lda $17FA,x
    cmp #$60
    bcs .next
    tay
    lda $04FF,y
    cmp #$10
    bcc .next
    cmp #$1A
    bcs .next
    txa
    plx
    sec
    rts
.next
    lda.l !TMP
    inc a
    cmp #$05
    bcc +
    lda #$00
+   sta.l !TMP
    lda.l !TMP+1
    dec a
    sta.l !TMP+1
    bne -
    plx
    clc
    rts

;-----------------------------------------------------------------------------
; cham_hit: replaces the JSL at $C3:4D41 (enemy hit, X = actor; asm/game_sfx.asm gs_enemy goes on): a
; chameleon hit while it looks like a player gets its own palette slot back before SB5 releases the
; object's slot (the hit can come from outside its routine).
cham_hit:
    lda $16C2,x
    cmp #!CHAM_TYPE
    bne +
    jsr restore
    lda #$00
    sta.l !CPH,x
+   jml !GS_ENEMY

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

end:

print "SYM clown ", hex(clown)
print "SYM clown_start ", hex(clown_start)
print "SYM clown_tick ", hex(clown_tick)
print "SYM clown_hit ", hex(clown_hit)
print "SYM chameleon ", hex(chameleon)
print "SYM cham_hit ", hex(cham_hit)
print "SYM end ", hex(end)
