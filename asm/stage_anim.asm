; Animated stage tiles (tools/sb6/features/sb1_stages.py `anim` / `soft_anim`):
; World 1's 1-7 (SB1 4-8's arena) has an electric fence that SB1 animates by
; sending a second picture of its tiles every 2 frames; 1-4 (SB1 4-4) the
; soft block's bumpers, 5 pictures of 3 frames; 1-5 (SB1 6-4) the hard
; blocks' red light (off, lit, lit: 16 frames each); 1-6 (SB1 World 5) the
; crowd, 3 animations of 2 pictures (16, 24, 19 frames). The build gives a stage's
; animated tiles one block of BG slots and writes every picture of that
; block one after the other in ROM (all stages in bank !BANK), with a row of
; !TABLE: [stage, frames each picture stays, pictures, VRAM word (word),
; block bytes (word), first picture (long), flames' VRAM word (word), their
; bytes (word, 0 = none), their source (word, bank !BANK)] ... $FF. The
; flames (SB5's flame tiles drawn over the stage's own floor, tiles $010-$07F)
; are sent once when the task starts, one entry a frame.
; anim_start (JSL, from world1's op FF 1A F6 5 / 6 in the stage's type 04
; script) finds the stage's row and starts a task that every "frames held"
; frames copies the next picture into SB5's VRAM queue (entries at
; $7E:8000 + write offset $0357: mode word $0084, size, VRAM address, data;
; the NMI sends them while there is vblank left, $C0:04E0), in entries of at
; most 256 bytes. It ends when the stage is over ($1031).
; A stage can have several rows in a row (1-6's crowd: blocks of their own
; pace), run one after the other every frame, each with its own counter.
; State: $7F:FBC0-$7F:FBC7 frame counter and $7F:FBC8-$7F:FBCF picture of
; each animation, $7F:FBDA-$7F:FBE1 scratch, $7F:FBE2 the stage's first row
; offset, $7F:FBE3 flame bytes sent (word), $7F:FBE5-$7F:FBE6 row / animation
; being run, $7F:FBE7 frames before the flames are sent.

asar 1.90
hirom
org !ORG

!CNT   = $7FFBC0              ; 8 bytes: frame counter of each animation of the stage
!PIC   = $7FFBC8              ; 8 bytes: its picture
!CUR   = $7FFBE5              ; the row being run
!K     = $7FFBE6              ; its animation number
!FWAIT = $7FFBE7              ; frames before the flames are sent
!FDELAY = 60
!SRC   = $7FFBDA              ; word: source offset (bank !BANK)
!VR    = $7FFBDC              ; word: VRAM word address
!LEFT  = $7FFBDE              ; word: bytes left
!N     = $7FFBE0              ; word: bytes in this entry
!ROW   = $7FFBE2
!FOFF  = $7FFBE3              ; word: flame bytes sent
!ROWSZ = 16
!PART  = $0100

anim_start:
    php
    sep #$30
    ldx #$00
-   lda.l !TABLE,x
    cmp #$FF
    beq .none
    cmp.l $7E1031
    beq .found
    txa
    clc
    adc #!ROWSZ
    tax
    bra -
.found:
    txa
    sta.l !ROW
    lda #$00
    ldx #$0F                    ; every animation's counter and picture
-   sta.l !CNT,x
    dex
    bpl -
    sta.l !FOFF
    sta.l !FOFF+1
    lda.l $7E1031               ; 1-6's duels only (see flames)
    cmp #$67
    beq .wait
    cmp #$69
    beq .wait
    cmp #$6B
    bne +
.wait:
    lda #!FDELAY
    bra ++
+   lda #$00
++  sta.l !FWAIT
    jsl $C020A1
    dl anim_task
    db $60                      ; skipped ($C020A1 returns past the dl)
.none:
    plp
    rtl

anim_task:
    php
    sep #$30
    lda.l !ROW
    tax
    lda.l $7E1031
    cmp.l !TABLE,x
    beq +
    jsl $C021CE                 ; stage over: end the task
    plp
    rtl
+   jsr flames
    sep #$30
    phb
    lda #$7F
    pha
    plb
    lda.l !ROW
    sta.l !CUR
    lda #$00
    sta.l !K
.row:                           ; the stage's rows, one animation each
    lda.l !CUR
    tax
    lda.l !TABLE,x
    cmp.l $7E1031
    bne .out
    lda.l !K
    tay
    lda.w !CNT&$FFFF,y          ; (data bank $7F)
    inc a
    cmp.l !TABLE+1,x
    bcc .keep
    lda.w !PIC&$FFFF,y          ; next picture
    inc a
    cmp.l !TABLE+2,x
    bcc +
    lda #$00
+   sta.w !PIC&$FFFF,y
    tay
    rep #$20
    lda.l !TABLE+7,x            ; first picture + picture * size
-   cpy #$00
    beq +
    clc
    adc.l !TABLE+5,x
    dey
    bra -
+   sta.l !SRC
    lda.l !TABLE+3,x
    sta.l !VR
    lda.l !TABLE+5,x
    sta.l !LEFT
    rep #$10
-   jsr part
    lda.l !LEFT
    bne -
    sep #$30
    lda.l !K
    tay
    lda #$00
.keep:
    sta.w !CNT&$FFFF,y
    lda.l !K
    inc a
    sta.l !K
    lda.l !CUR
    clc
    adc #!ROWSZ
    sta.l !CUR
    jmp .row
.out:
    plb
    plp
    rtl

; the stage's flame tiles, !PART bytes a frame until all are sent (X = row offset, 8-bit), from
; at once, or in 1-6's duels !FDELAY frames after the task's start: there SB5 writes tiles $010-$01F
; itself some 25 frames after the type 04 script ($C0:1BC8 and $C5:14EF, CPU writes), over the first
; ones sent (in 1-4 / 1-5 / 1-7 waiting showed SB5's own tiles instead)
flames:
    lda.l !FWAIT
    beq +
    dec a
    sta.l !FWAIT
    rts
+   rep #$20
    lda.l !FOFF
    cmp.l !TABLE+12,x
    bcs .done
    clc
    adc.l !TABLE+14,x
    sta.l !SRC
    lda.l !FOFF
    lsr a
    clc
    adc.l !TABLE+10,x
    sta.l !VR
    lda.l !TABLE+12,x
    sec
    sbc.l !FOFF
    cmp.w #!PART
    bcc +
    lda.w #!PART
+   sta.l !LEFT
    clc
    adc.l !FOFF
    sta.l !FOFF
    rep #$10
    jsr part
.done:
    rts

; one queue entry: min(left, !PART) bytes from !SRC (bank !BANK) to VRAM word !VR; M/X 16-bit
part:
    lda.l !LEFT
    cmp.w #!PART
    bcc +
    lda.w #!PART
+   sta.l !N
    lda.l $7E0357
    tax
    lda.w #$0084                ; word writes, VMAIN $80
    sta.l $7E8000,x
    lda.l !N
    sta.l $7E8002,x
    lda.l !VR
    sta.l $7E8004,x
    txa
    clc
    adc.w #$8006
    tay                         ; destination (bank $7E)
    lda.l !SRC
    tax
    lda.l !N
    dec a
    phb
    db $54, $7E, !BANK          ; MVN $7E <- !BANK
    plb
    lda.l $7E0357
    clc
    adc.w #6
    adc.l !N
    and.w #$3FFF
    sta.l $7E0357
    lda.l !SRC
    clc
    adc.l !N
    sta.l !SRC
    lda.l !N
    lsr a
    clc
    adc.l !VR
    sta.l !VR
    lda.l !LEFT
    sec
    sbc.l !N
    sta.l !LEFT
    rts

print "SYM anim_start ", hex(anim_start)
print "SYM end ", hex(pc())
