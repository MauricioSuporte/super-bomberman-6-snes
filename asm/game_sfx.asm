; In-game SFX (tools/sb6/features/game_sfx.py): cornered bomber, player death
; and enemy death as Hudson SFX commands !CMD_CORNER / !CMD_DEATH /
; !CMD_ENEMY, whose sequences and samples live in ARAM R = $5900-$657F (SB5's
; group-3 voice buffer) plus, for the cornered recording, a part B below the
; song's echo buffer or menu SFX samples.
;
; Entry points:
;   gs_enemy  $C3:4D41 (JSL): an enemy hit by a flame starts its death:
;             !CMD_ENEMY.
;   gs_anim   $C0:11EC (animation setter, JML): A = animation, Y = object.
;             A seat bomber ($17FA + seat) whose animation becomes $21
;             (cornered) plays !CMD_CORNER.
;   gs_sound  JSL from sound_hook (asm/title_music.asm) while Hudson's driver
;             runs: A = id, B = group. Group 2 id $33 (score of a dead enemy) plays
;             nothing (the score of a dead enemy), group 3 id 1 (SB5's death voice stream) plays
;             !CMD_DEATH at once; C = 1 = handled. Any other group-3 voice is
;             streamed over R: R is marked missing and gs_tick brings it back.
;   gs_set    JSL from set_hook, inside the upload session ($9F = set).
;   gs_song   JSL from song_hook, inside the upload session (X = song).
;   gs_tick   JSL from loop_hook, once per main-loop pass: sends the command
;             gs_anim / gs_enemy left in !gs_pend (never from the object
;             code: the SPC handshake there cost char1/char4 the tiles of
;             animation $21).
;
; R is sent with a set or song upload when the current song leaves it alone
; (SONGS bit 0) and it is not known to be there; the patch list (pointer
; table entries, priorities, instruments, directory and tuning entries) after
; every set, which rewrites those tables. SONGS bits 1/2: the song has room
; for B below $DD00 / below the menu SFX ($B900); the cornered sample's
; directory entry then loops from A into B, else into a silent END block.
;
; Restoring R after another group-3 voice: wait until SB5's stream queue is
; idle, 120 more passes (the voice plays from R), then queue set !STREAM_SET
; (its list = R) with no command, and mark R present when the queue is idle
; again.
;
; WRAM $0188-$018C (docs/FREE_SPACE.md).

asar 1.90
hirom
org !CODE

!DEATH_WAIT = 150           ; main-loop passes a death sound may wait for R
!gs_valid = $000188         ; 1 = R (and the patches) are in ARAM
!gs_state = $000189         ; restore: 0 idle, 1 wait for the voice's stream, 2 wait, 3 R streaming
!gs_wait  = $00018A
!gs_song  = $00018B         ; song last uploaded (0 after reset = the boot jingle, over R)
!gs_dwait = $000196         ; a death sound waiting for R (passes left, 0 = none)
!gs_pend  = $00018C         ; command to send at the next main-loop pass (0 = none)
!RESTORE_WAIT = 120

macro c0call(addr)
    phk
    per ?back-1
    pea.w !RTL_C0-1
    jml <addr>
?back:
endmacro

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

; ---- $C0:11EC: STA $079F,Y / LDA #$00 --------------------------------------
gs_anim:
    php
    rep #$10
    sep #$20
    cmp #$21
    bne .orig
    phx
    rep #$20                ; whole A: $C0:11F8 uses B after a REP #$20
    pha
    sep #$20
    tyx
    lda.l $7E079F,x         ; animation before this one
    cmp #$21
    beq .skip
    txa
    ldx.w #4
-   cmp.l $7E17FA,x         ; a seat's bomber?
    beq .hit
    dex
    bpl -
    bra .skip
.hit:
    lda #!CMD_CORNER        ; sent by gs_tick: waiting for the SPC here delays
    sta.l !gs_pend          ; the frame and the animation's tile DMA is lost
.skip:
    rep #$20
    pla
    plx
.orig:
    plp
    sta $079F,y
    lda #$00
    jml $C011F1

; ---- $C3:4D41: LDA $16C2,X / STA $1D51 (M 8-bit) ----------------------------
; An enemy hit by a flame turns into its "puff" effect here: SB1's enemy
; death sound starts now (SB5 only played group 2 id $33 with the score).
gs_enemy:
    lda.l !gs_pend
    bne +                   ; the cornered sound goes first
    lda #!CMD_ENEMY
    sta.l !gs_pend
+   lda $16C2,x
    sta $1D51
    rtl

; A = command: sent through Hudson's $C0:0E7F when R is in ARAM and the
; title stream is not running. C = 1 when sent. Keeps X/Y.
play:
    xba
    lda.l !gs_valid
    beq .not
    lda.l !ACTIVE
    bne .not
    phb
    lda #$80                ; $0E7F reads $03C0 and $2140 with absolute addressing
    pha
    plb
    xba
    %c0call($C00E7F)
    plb
    sec
    rts
.not:
    xba
    clc
    rts

; ---- sound API (A = id, B = group, M 8-bit) ---------------------------------
gs_sound:
    php
    sep #$20
    xba
    cmp #$03
    beq .stream
    cmp #$02
    bne .no
    xba
    cmp #$33                ; score of a dead enemy (~70 frames after the hit): silent like SB1,
    bne .no                 ; gs_enemy played the death sound at the hit
    lda.l !gs_valid
    beq .no
    bra .yes
.stream:
    xba
    cmp #$01                ; SB5's death voice: never streamed (its set is R now)
    bne .clobber
    lda #!CMD_DEATH
    jsr play
    bcs .yes
    lda #!DEATH_WAIT        ; R is being restored after another voice: play it
    sta.l !gs_dwait         ; when R is back (gs_tick) instead of dropping it
    bra .yes
.clobber:
    lda #$00
    sta.l !gs_valid
    lda #$01
    sta.l !gs_state
.no:
    plp
    clc
    rtl
.yes:
    plp
    sec
    rtl

; ---- end of a set upload (session open, M/X 8-bit) --------------------------
gs_set:
    php
    sep #$30
    ldx $9F                 ; set ($C0:0E31)
    lda.l !SETS,x
    beq +
    lda #$00
    sta.l !gs_valid
+   jsr upload
    plp
    rtl

; ---- end of a song upload (session open, X = song) --------------------------
gs_song:
    php
    sep #$30
    txa
    sta.l !gs_song
    tax
    lda.l !SONGS,x
    and #$02
    beq +
    %sendlist(!L_B1)
+   lda.l !gs_song
    tax
    lda.l !SONGS,x
    and #$04
    beq +
    %sendlist(!L_B2)
+   jsr upload
    plp
    rtl

; R when missing, then the patches and the cornered sample's directory entry
; (M/X 8-bit, session open).
upload:
    lda.l !gs_song
    tax
    lda.l !SONGS,x
    and #$01
    bne +
    lda #$00                ; the song's samples lie over R
    sta.l !gs_valid
    sta.l !gs_state
    rts
+   lda.l !gs_valid
    bne +
    %sendlist(!L_R)
    lda #$01
    sta.l !gs_valid
    lda #$00
    sta.l !gs_state
+   %sendlist(!L_PATCH)
    lda.l $7E1031           ; 1-6's duels: SB1's crowd (features/crowd.py; its block is in the
    cmp #!CHEER_STAGE       ; stage's music list)
    bne +
    %sendlist(!L_CHEER)
+   lda.l !gs_song
    tax
    lda.l !SONGS,x
    and #$02
    beq +
    %sendlist(!L_DIR1)
    rts
+   lda.l !SONGS,x
    and #$04
    beq +
    %sendlist(!L_DIR2)
    rts
+   %sendlist(!L_DIR0)
    rts

; ---- main loop --------------------------------------------------------------
gs_tick:
    php
    sep #$30
    lda.l !gs_dwait
    beq +
    dec a
    sta.l !gs_dwait
    lda.l !gs_valid
    beq +
    lda #$00
    sta.l !gs_dwait
    lda #!CMD_DEATH
    phb
    phk
    plb
    jsr play
    plb
+    lda.l !gs_pend
    beq +
    phb
    phk
    plb
    jsr play                ; (dropped if R is missing or the title streams)
    plb
    lda #$00
    sta.l !gs_pend
+   lda.l !ACTIVE
    bne .out
    lda.l !gs_state
    beq .out
    cmp #$01
    bne .wait
    jsr idle
    bcc .out
    lda #!RESTORE_WAIT
    sta.l !gs_wait
    lda #$02
    sta.l !gs_state
    bra .out
.wait:
    cmp #$02
    bne .streaming
    jsr idle
    bcc .out
    lda.l !gs_wait
    dec a
    sta.l !gs_wait
    bne .out
    lda.l !gs_song
    tax
    lda.l !SONGS,x
    and #$01
    beq .stop
    lda #!STREAM_SET
    sta.l $0003C4           ; SB5's group-3 queue: set, no command after it
    lda #$03
    sta.l !gs_state
    bra .out
.streaming:
    jsr idle
    bcc .out
    lda #$01
    sta.l !gs_valid
.stop:
    lda #$00
    sta.l !gs_state
.out:
    plp
    rtl

; C = 1 when SB5's group-3 queue is empty and nothing is being streamed.
idle:
    lda.l $0003C4
    ora.l $0003C5
    bne +
    lda.l $0003C6
    ora.l $0003C7
    bne +
    sec
    rts
+   clc
    rts

assert pc() <= !CODE_END, "game SFX code overflows its allocation"

print "SYM gs_anim ", hex(gs_anim)
print "SYM gs_enemy ", hex(gs_enemy)
print "SYM gs_sound ", hex(gs_sound)
print "SYM gs_set ", hex(gs_set)
print "SYM gs_song ", hex(gs_song)
print "SYM gs_tick ", hex(gs_tick)
print "SYM end ", hex(pc())
