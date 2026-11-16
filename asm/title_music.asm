; SB6 title music: streams a BRR recording to the SPC700 while the title is up.
;
; Hooks (bytes verified and patched by tools/sb6/features/title_music.py):
;   $C0:0CED  sound API entry (A = id, B = group). Title music request
;             (group 0, id 2) uploads the stream driver instead of starting
;             SB5's title song. While streaming, menu SFX (group 2) are
;             sent to the stream driver, which replays them (slots from
;             SFX_SLOTS, a 32-byte id -> slot table; 0 = no replay, dropped),
;             and any other request first gives the APU back to Hudson's
;             driver, then runs normally.
;   $C0:0B2C  main loop, once per frame before the wait for NMI: feeds the
;             stream.
;   $C0:0E58  end of a sample set upload, $C0:0F0A end of a song upload
;             (both still inside the upload session): the SB6 menu SFX.
;             Their three samples sit high in ARAM; a song that leaves that
;             area alone (SFX_SAFE, one byte per song) gets the samples (if
;             they are not there yet) and the SB6 definitions of SFX 1/3/4,
;             any other song gets SB5's definitions back (except one whose
;             own samples cover the SFX tables: SFX_SAFE = 2). A set upload
;             rewrites the definitions, so it is followed by the SB6 ones
;             again while they are in use.
;
; The same hooks call the in-game SFX code (asm/game_sfx.asm): GS_SOUND first
; in the sound API while Hudson's driver runs, GS_TICK every pass, GS_SET /
; GS_SONG inside the set / song upload sessions.
;
; Uploads go through the game's own routines in bank $C0 ($0F13 handshake,
; $0F62 list of [length, ARAM address, data] blocks ending in a zero length,
; $0F35 end + jump address read after the list); they end in RTS, so they are
; called with an RTL of that bank as their return address (RTL_C0).
;
; WRAM: $0100-$0109 (bottom of the stack page; the stack never went below
; $01B3 in a 12000-frame run, see docs/ROM_MAP.md).
;
; Defines: CODE (address), L_STREAM (upload list: driver + prefill, JMP entry
; over the loader's RET; then the entry address), ENTRY (ARAM entry),
; L_SAMPLES / L_NEW / L_ORIG (upload lists: SFX samples, SB6 and SB5 SFX
; definitions), SFX_SAFE, NSONGS, SONG_TABLE, RTL_C0,
; START_BANK/START_OFF (first chunk sent by the feeder),
; LOOP_BANK/LOOP_OFF, END_BANK/END_OFF (address after the last chunk),
; SFX_SLOTS (file), PRE_BANK/PRE_OFF/PRE_END_OFF/PRE_LOOP_OFF (the intro's
; sounds: their own bank, the last chunk is silence and repeats).

asar 1.90
hirom
org !CODE

!active = $000100
!seq    = $000101
!ptr    = $000102
!bank   = $000104
!kick   = $000105       ; loader's last kick value
!frame  = $000106       ; NMI frame count at the last feed
!sfxtog = $000107       ; bit 6 toggles so repeated SFX commands differ
!sfxok  = $000108       ; 1 = the SB6 menu SFX samples are in ARAM
!sfxnew = $000109       ; 1 = Hudson's SFX 1/3/4 are the SB6 definitions
!NMI_FRAMES = $000068   ; incremented by the NMI handler ($C0:F431)
!song   = $0003CD       ; Hudson song currently in ARAM ($FF = none)

APUIO0 = $002140
APUIO1 = $002141
APUIO2 = $002142
APUIO3 = $002143

!LOW_FREE = 60          ; free chunks >= 60 (under ~1.6 s buffered): send 2 a frame

; Calls a routine of bank $C0 that ends in RTS (M/X 8-bit, D = 0).
macro c0call(addr)
    phk
    per ?back-1
    pea.w !RTL_C0-1
    jml <addr>
?back:
endmacro

; Uploads a list of blocks inside an open session.
macro sendlist(addr)
    lda.b #<addr>
    sta $48
    lda.b #<addr>>>8
    sta $49
    lda.b #<addr>>>16
    sta $4A
    stz $03D1
    %c0call($C00F62)
endmacro

; ---- $C0:0CED -------------------------------------------------------------
sound_hook:
    php
    rep #$30
    pha
    phx
    phy
    sep #$20
    lda.l !active
    bne +
    lda $06,s               ; in-game SFX (asm/game_sfx.asm) while Hudson's driver runs
    xba
    lda $05,s
    jsl !GS_SOUND
    bcc +
    brl .swallow
+   lda $06,s               ; group
    cmp #$02
    bne .not_sfx
    lda.l !active
    beq .original
    lda $05,s               ; id
    cmp #$20
    bcs .swallow
    rep #$20
    and #$001F
    tax
    sep #$20
    lda.l sfx_slots,x
    beq .swallow            ; not replayable: dropped (port 0 is ours)
    jsr send_sfx
    bra .swallow
.not_sfx:
    cmp #$00
    bne .other
    lda $05,s               ; id
    cmp #$02
    bne .other
    lda.l !active
    beq +
    lda.l !bank             ; the title's pan sound is still streaming (the
    cmp #!PRE_BANK          ; intro ended or was skipped): the music replaces it
    bne .swallow
    jsr release
+   jsr start_stream
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

; A = slot (1-31): port 0 = $80 | toggle | slot, then waits for the echo.
send_sfx:
    pha
    lda.l !sfxtog
    eor #$40
    and #$40
    sta.l !sfxtog
    ora $01,s
    ora #$80
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    pla
    rts

sfx_slots:
    incbin "!SFX_SLOTS"

; ---- $C0:0B2C -------------------------------------------------------------
loop_hook:
    php
    sep #$20
    lda.l !active
    beq +
    jsr feed
+   jsl !GS_TICK
    plp
    lda $03BF               ; replaced instructions
    bne +
    jml $C00B31
+   jml $C00B35

; JSL (M/X 8-bit, from asm/title_anim.asm): streams the title intro's pan
; sound, then silence (its last chunk repeats) until the music is asked for.
pre_start:
    php
    sep #$20
    lda.l !active
    bne +
    jsr start_stream
    rep #$20
    lda #!PRE_OFF
    sta.l !ptr
    sep #$20
    lda #!PRE_BANK
    sta.l !bank
+   plp
    rtl

; Hudson's loader (port 1 = $10) <- the SFX samples (when they are not in
; ARAM), the SB6 SFX definitions, the driver + prefill and a JMP entry over
; the loader's final RET at $1041, so the end of the upload runs the driver.
start_stream:
    php
    sep #$30
    %c0call($C00F13)
    lda.l !sfxok
    bne +
    %sendlist(!L_SAMPLES)
    lda #$01
    sta.l !sfxok
+   %sendlist(!L_NEW)
    lda #$01
    sta.l !sfxnew
    %sendlist(!L_STREAM)
    %c0call($C00F35)        ; end of upload: the loader "returns" into the driver
    lda $4B                 ; the session's last kick
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

; ---- $C0:0E58 (JSR $0F62 : JSR $0F35), M/X 8-bit --------------------------
set_hook:
    %c0call($C00F62)        ; the set
    jsl !GS_SET             ; in-game SFX tables (and their samples when missing)
    lda.l !sfxnew
    beq +
    %sendlist(!L_NEW)       ; set 1 holds SB5's definitions
+   %c0call($C00F35)
    rtl

; ---- $C0:0F0A (JSR $0F35 : STZ $03D1), M/X 8-bit, $4F = the song's record --
song_hook:
    rep #$30
    ldx #$0000
-   lda.l !SONG_TABLE,x
    cmp $4F
    beq +
    inx
    inx
    cpx.w #2*!NSONGS
    bcc -
+   txa                     ; not in the table: the entry after the last is 0
    lsr
    tax
    sep #$30
    phx                     ; song number, for gs_song
    lda.l !SFX_SAFE,x
    beq .unsafe
    cmp #$02                ; the song's samples lie over the SFX tables (boot
    bne +                   ; jingle): nothing of ours is written into them
    lda #$00
    sta.l !sfxok
    sta.l !sfxnew
    bra .end
+
    lda.l !sfxok
    bne +
    %sendlist(!L_SAMPLES)
    lda #$01
    sta.l !sfxok
+   %sendlist(!L_NEW)
    lda #$01
    sta.l !sfxnew
    bra .end
.unsafe:
    lda #$00
    sta.l !sfxok
    sta.l !sfxnew
    %sendlist(!L_ORIG)
.end:
    plx
    jsl !GS_SONG            ; in-game SFX: samples, tables
    stz $03D1
    %c0call($C00F35)
    rtl

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
    cmp #!PRE_BANK
    bne +
    rep #$20
    lda.l !ptr
    cmp #!PRE_END_OFF
    bne ++
    lda #!PRE_LOOP_OFF
    sta.l !ptr
++  sep #$20
    bra .next
+   cmp #!END_BANK
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
print "SYM pre_start ", hex(pre_start)
print "SYM set_hook ", hex(set_hook)
print "SYM song_hook ", hex(song_hook)
print "SYM end ", hex(pc())
