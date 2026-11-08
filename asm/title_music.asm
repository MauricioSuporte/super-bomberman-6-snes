; SB6 title music: streams a BRR recording to the SPC700 while the title is up.
;
; Hooks (bytes verified and patched by tools/sb6/features/title_music.py):
;   $C0:0CED  sound API entry (A = id, B = group). Title music request
;             (group 0, id 2) uploads the stream driver instead of starting
;             SB5's title song. While streaming, menu SFX (group 2) are
;             dropped and any other request first gives the APU back to
;             Hudson's driver, then runs normally.
;   $C0:0B2C  main loop, once per frame before the wait for NMI: feeds the
;             stream.
;
; WRAM: $0100-$0106 (bottom of the stack page; the stack never went below
; $01B3 in a 12000-frame run, see docs/ROM_MAP.md).
;
; Defines: CODE (address), BLOB/BLOB_SIZE (driver + prefill image),
; ENTRY (ARAM entry), START_BANK/START_OFF (first chunk sent by the feeder),
; LOOP_BANK/LOOP_OFF, END_BANK/END_OFF (address after the last chunk).

asar 1.90
hirom
org !CODE

!active = $000100
!seq    = $000101
!ptr    = $000102
!bank   = $000104
!kick   = $000105       ; loader's last kick value
!frame  = $000106       ; NMI frame count at the last feed
!NMI_FRAMES = $000068   ; incremented by the NMI handler ($C0:F431)
!song   = $0003CD       ; Hudson song currently in ARAM ($FF = none)

APUIO0 = $002140
APUIO1 = $002141
APUIO2 = $002142
APUIO3 = $002143

!LOW_FREE = 60          ; free chunks >= 60 (under ~1.6 s buffered): send 2 a frame

; ---- $C0:0CED -------------------------------------------------------------
sound_hook:
    php
    rep #$30
    pha
    phx
    phy
    sep #$20
    lda $06,s               ; group
    cmp #$02
    bne .not_sfx
    lda.l !active
    bne .swallow            ; no SFX while streaming (port 0 is ours)
    bra .original
.not_sfx:
    cmp #$00
    bne .other
    lda $05,s               ; id
    cmp #$02
    bne .other
    lda.l !active
    bne .swallow
    jsr start_stream
    bra .swallow
.other:
    lda.l !active
    beq .original
    jsr release
.original:
    rep #$30
    ply
    plx
    pla
    plp
    sta $9F                 ; replaced instructions
    xba
    cmp #$10
    jml $C00CF2
.swallow:
    rep #$30
    ply
    plx
    pla
    plp
    rtl

; ---- $C0:0B2C -------------------------------------------------------------
loop_hook:
    php
    sep #$20
    lda.l !active
    beq +
    jsr feed
+   plp
    lda $03BF               ; replaced instructions
    bne +
    jml $C00B31
+   jml $C00B35

; Hudson's loader (port 1 = $10) -> upload driver + prefill to !BASE and
; JMP !ENTRY over the loader's final RET at $1041 -> end of upload runs it.
start_stream:
    php
    sep #$20
    rep #$10
-   lda #$10
    sta.l APUIO1
    lda.l APUIO0
    cmp #$AA
    bne -
    lda.l APUIO1
    cmp #$BB
    bne -
    rep #$20
    lda #!BASE
    sta.l APUIO2
    sep #$20
    lda #$01
    sta.l APUIO1
    lda #$CC
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    ldx #$0000
.byte:
    lda.l !BLOB,x
    sta.l APUIO1
    txa
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    inx
    cpx #!BLOB_SIZE
    bne .byte
    rep #$20
    lda #$1041
    sta.l APUIO2
    sep #$20
    lda #$01
    sta.l APUIO1
    jsr kick
    ldx #$0000
.patch:
    lda.l jmp_entry,x
    sta.l APUIO1
    txa
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    inx
    cpx #$0003
    bne .patch
    rep #$20
    lda #!ENTRY
    sta.l APUIO2
    sep #$20
    lda #$00
    sta.l APUIO1
    jsr kick                ; end of upload: the loader "returns" into the driver
    sta.l !kick
    inc a
    and #$7F
    sta.l !seq
    rep #$20
    lda #!START_OFF
    sta.l !ptr
    sep #$20
    lda #!START_BANK
    sta.l !bank
    lda.l !NMI_FRAMES
    sta.l !frame
    lda #$01
    sta.l !active
    lda #$FF
    sta.l !song             ; the ring overwrites SB5's title song
    plp
    rts

; Next loader command: port 0 = last index + 2 (never 0); waits for the echo.
; X = bytes sent in the block. Returns A = the value sent.
kick:
    txa
    inc a
    bne +
    inc a
+   sta.l APUIO0
-   cmp.l APUIO0
    bne -
    rts

jmp_entry:
    db $5F, !ENTRY&$FF, !ENTRY>>8

; Stream driver -> back into Hudson's driver (see asm/spc/stream.asm).
release:
    php
    sep #$20
    lda #$80
    sta.l APUIO0
-   lda.l APUIO3
    cmp #$A5
    bne -
    lda #$00                ; ports as the loader left them
    sta.l APUIO1
    rep #$20
    lda #!ENTRY
    sta.l APUIO2
    sep #$20
    lda.l !kick
    sta.l APUIO0
-   lda.l APUIO3
    cmp #$AA
    bne -
    lda #$00
    sta.l !active
    lda #$FF
    sta.l !song
    plp
    rts

; Sends 162-byte chunks if the ring has room: one per frame elapsed since the
; last call (the main loop runs at 60 or 30 Hz depending on the screen), plus
; one while the ring is low, never more than the free space.
feed:
    php
    phb
    sep #$20
    rep #$10
    phx
    phy
    lda.l APUIO3
    cmp #$5B
    beq +
    brl .out                ; driver not running
+
-   lda.l APUIO2
    cmp.l APUIO2
    bne -
    cmp #$00
    bne +
    brl .out
+   pha                     ; [1,s] = free chunks, then chunks to send
    lda.l !NMI_FRAMES
    sec
    sbc.l !frame
    xba
    lda.l !NMI_FRAMES
    sta.l !frame
    xba                     ; A = frames since the last call
    cmp #$03
    bcc +
    lda #$02
+   cmp #$00
    bne +
    inc a
+   xba
    lda $01,s
    cmp #!LOW_FREE
    xba                     ; A = per-frame count, C = ring low
    bcc +
    inc a
+   cmp $01,s
    bcc +
    lda $01,s
+   sta $01,s
.chunk:
    lda.l !bank
    pha
    plb
    rep #$20
    lda.l !ptr
    tay
    sep #$20
    ldx.w #54
    lda.l !seq
    xba                     ; B = sequence
.triple:
    lda.w $0000,y
    sta.l APUIO1
    iny
    lda.w $0000,y
    sta.l APUIO2
    iny
    lda.w $0000,y
    sta.l APUIO3
    iny
    xba
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    inc a
    and #$7F
    xba
    dex
    bne .triple
    xba
    sta.l !seq
    rep #$20
    tya
    cmp #$FF5F              ; next chunk would cross the bank
    bcc +
    lda #$0000
    sta.l !ptr
    sep #$20
    lda.l !bank
    inc a
    sta.l !bank
    bra ++
+   sta.l !ptr
    sep #$20
++  lda.l !bank
    cmp #!END_BANK
    bne .next
    rep #$20
    lda.l !ptr
    cmp #!END_OFF
    sep #$20
    bne .next
    rep #$20
    lda #!LOOP_OFF
    sta.l !ptr
    sep #$20
    lda #!LOOP_BANK
    sta.l !bank
.next:
    pla
    dec a
    beq .out
    pha
    brl .chunk
.out:
    ply
    plx
    plb
    plp
    rts

assert pc() <= !CODE_END, "title music code overflows its allocation"

print "SYM sound_hook ", hex(sound_hook)
print "SYM loop_hook ", hex(loop_hook)
print "SYM end ", hex(pc())
