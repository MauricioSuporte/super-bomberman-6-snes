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

end:
print "SYM chameleon ", hex(chameleon)
print "SYM cham_hit ", hex(cham_hit)
print "SYM end ", hex(end)
