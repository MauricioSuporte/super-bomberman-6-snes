; Animated stage tiles (tools/sb6/features/sb1_stages.py `anim` / `soft_anim`):
; World 1's 1-7 (SB1 4-8's arena) has an electric fence that SB1 animates by
; sending a second picture of its tiles every 2 frames; 1-4 (SB1 4-4) the
; soft block's bumpers, 5 pictures of 3 frames. The build gives a stage's
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
; State: $7F:FBD8 frame counter, $7F:FBD9 picture, $7F:FBDA-$7F:FBE1
; scratch, $7F:FBE2 the stage's row offset, $7F:FBE3 flame bytes sent (word).

asar 1.90
hirom
org !ORG

!CNT   = $7FFBD8
!PIC   = $7FFBD9
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
    sta.l !CNT
    sta.l !PIC
    sta.l !FOFF
    sta.l !FOFF+1
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
    bra .out
+   jsr flames
    sep #$30
    lda.l !ROW
    tax
    lda.l !CNT
    inc a
    cmp.l !TABLE+1,x
    bcc .keep
    lda.l !PIC                  ; next picture
    inc a
    cmp.l !TABLE+2,x
    bcc +
    lda #$00
+   sta.l !PIC
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
    lda #$00
.keep:
    sta.l !CNT
.out:
    plp
    rtl

; the stage's flame tiles, !PART bytes a frame until all are sent (X = row offset, 8-bit)
flames:
    rep #$20
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
