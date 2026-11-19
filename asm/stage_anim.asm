; Animated stage tiles (tools/sb6/features/sb1_stages.py `anim`): World 1's
; 1-7 (SB1 4-8's arena) has an electric fence that SB1 animates by sending a
; second picture of its tiles every 2 frames. The build gives those tiles
; one block of BG slots (VRAM word !VRAM, !SIZE bytes; the second frame's
; tiles in another ROM copy of the block). anim_start (JSL, from world1's
; op FF 1A F6 05 in the stage's type 04 script) starts a task that every
; !HALF frames copies the block of the frame due into SB5's VRAM queue
; (entries at $7E:8000 + write offset $0357: mode word $0084, size, VRAM
; address, data; the NMI sends them while there is vblank left, $C0:04E0),
; in entries of at most 256 bytes. It ends when stage !STAGE is over
; ($1031). State: $7F:FBD8 frame counter, $7F:FBDA-$7F:FBE1 scratch.

asar 1.90
hirom
org !ORG

!CNT   = $7FFBD8
!SRC   = $7FFBDA              ; word: source offset (bank !BANK)
!VR    = $7FFBDC              ; word: VRAM word address
!LEFT  = $7FFBDE              ; word: bytes left
!N     = $7FFBE0              ; word: bytes in this entry
!PART  = $0100

anim_start:
    php
    sep #$30
    lda #$00
    sta.l !CNT
    jsl $C020A1
    dl anim_task
    db $60                      ; skipped ($C020A1 returns past the dl)
    plp
    rtl

anim_task:
    php
    sep #$30
    lda.l $7E1031
    cmp #!STAGE
    beq +
    jsl $C021CE                 ; stage over: end the task
    bra .out
+   lda.l !CNT
    inc a
    cmp #!HALF*2
    bcc +
    lda #$00
+   sta.l !CNT
    beq .zero
    cmp #!HALF
    bne .out
    rep #$30
    lda.w #!SRC1&$FFFF
    bra .send
.zero:
    rep #$30
    lda.w #!SRC0&$FFFF
.send:
    sta.l !SRC
    lda.w #!VRAM
    sta.l !VR
    lda.w #!SIZE
    sta.l !LEFT
-   jsr part
    lda.l !LEFT
    bne -
.out:
    plp
    rtl

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
