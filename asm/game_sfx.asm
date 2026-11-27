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
;   gs_tick   JSL from loop_hook, once per main-loop pass (also feeds the SB6
;             stage voices' ring, vs_tick): sends the command
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
; SB6 stage voices' WRAM (vs_* below; docs/FREE_SPACE.md)
!vs_on   = $7FFBE8          ; $A5 = the stage loaded with its voices
!vs_rec  = $7FFBE9          ; its record (offset in !VOICE_TAB / 2: up to 510)
!vs_clip = $7FFBEA          ; clip in the ring (0 start, 1-3 good), $FF none
!vs_sent = $7FFBEB          ; word: its blocks in the ring
!vs_pos  = $7FFBED          ; word: ring block the next one goes to
!vs_play = $7FFBEF          ; 1 while it plays, 2 nothing to do (the next one ready / none left)
!vs_last = $7FFBF0          ; NMI count ($0068) at the last pass
!vs_acc  = $7FFBF1          ; 3 bytes: blocks played (at most) x 256 since the key-on
!vs_want = $7FFBF4          ; clip to play once its first blocks are in, $FF none
!vs_wait = $7FFBF5          ; passes it may still wait
!vs_lim  = $7FFBF6          ; word: blocks the ring may hold now
!vs_need = $7FFBF8          ; word: blocks the ring must hold now
!vs_delay = $7FFBB0         ; main-loop passes before "start" is asked for (0 = none)
!vs_bok   = $7FFBB1         ; 1 = the ring holds the cornered sound's part B (clip !VS_BCLIP)
!vs_lat   = $7FFBB2         ; frames after the SFX command not counted as played (Hudson keys on later)
!vs_key  = $7FFBB3          ; stage byte of the record in use (a stage, or !VS_END_KEY)
!vs_song = $7FFBB4          ; gs_song it was found for
!vs_pair  = $7FFC80         ; 18 bytes: a ring's last two blocks, END + LOOP set (vs_edge)


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
    lda.l !vs_on            ; a stage with voices: only while part B is in ARAM
    cmp #$A5
    bne +
    lda.l !vs_bok
    beq .skip
+   lda #!CMD_CORNER        ; sent by gs_tick: waiting for the SPC here delays
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
    cmp #$00
    bne +
    xba
    jsr vs_ask              ; the stage start / clear jingles: SB6's voices (the jingle plays too)
    bra .no
+   cmp #$03
    beq .stream
    cmp #$02
    bne .no
    xba
    cmp #$33                ; score of a dead enemy (~70 frames after the hit): silent like SB1,
    bne .no                 ; gs_enemy played the death sound at the hit
    lda.l $7FFB14           ; 2: World 1's portal asks for the same id ($33 = SB5's portal sound;
    cmp #$02                ; asm/world1.asm portal_task, docs/FREE_SPACE.md): SB1's bell echo instead
    bne +                   ; (features/portal_sfx.py), SB5's when R is not in ARAM
    lda #!CMD_PORTAL
    jsr play
    bcs .yes
    bra .no
+
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
+   jsr cs_stage            ; SB1 music keeping B free, no voices there: B now
    bcc +
    %sendlist(!L_B1)
+   jsr vs_reset
    jsr upload
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
+   lda.l !gs_song          ; World 1's portal sound (features/portal_sfx.py): only while an SB1 song
    cmp #!SB1M_SONG         ; (its bell) is in ARAM: elsewhere instrument 30 / directory $3B are the SB6
    bne ++                  ; menu SFX's (docs/FREE_SPACE.md)
    ldx #$00                ; the stage's list of its entries (pointer, instrument, the stage's SB1 bell,
.portal:                    ; tuning), if it has one
    lda.l !PORTAL_TAB,x
    cmp #$FF
    beq ++
    cmp.l $7E1031
    beq +
    inx
    inx
    inx
    inx
    bra .portal
+   lda.l !PORTAL_TAB+1,x
    sta $48
    lda.l !PORTAL_TAB+2,x
    sta $49
    lda.l !PORTAL_TAB+3,x
    sta $4A
    stz $03D1
    %c0call($C00F62)
++  jsr vs_entries
    lda.l !vs_on            ; SB1 music with voices (B in their ring between them) or keeping B
    cmp #$A5
    beq .dir1
    jsr cs_stage
    bcs .dir1
    lda.l !gs_song
    tax
    lda.l !SONGS,x
    and #$02
    beq +
.dir1:
    %sendlist(!L_DIR1)
    rts
+   lda.l !SONGS,x
    and #$04
    beq +
    %sendlist(!L_DIR2)
    rts
+   %sendlist(!L_DIR0)
    rts

; C = SB1's music in ARAM on a stage of !CORNER_TAB (its list keeps B free; M/X 8-bit)
cs_stage:
    lda.l !gs_song
    cmp #!SB1M_SONG
    bne .no
    ldx #$00
-   lda.l !CORNER_TAB,x
    cmp #$FF
    beq .no
    cmp.l $7E1031
    beq .yes
    inx
    bra -
.yes:
    sec
    rts
.no:
    clc
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
+   jsr vs_tick
    lda.l !ACTIVE
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

; ---- SB6 stage voices (tools/sb6/features/voice_sfx.py) ---------------------
; "start" !VS_DELAY passes after the stage start jingle is asked for (once it
; has played, just before the stage music), a random "good" with the clear
; jingle.
; The voice SFX !VS_CMD plays a sample looping over a ring of NR BRR blocks
; (ARAM below $DD00); its clip is sent into the ring a few blocks at a time
; by vs_tick (end of each main-loop pass), behind the play position, on the
; frame's idle time unless the play position is about to reach them.
; !VOICE_TAB records (!VS_REC bytes, $FF after the last): +0 stage, +1 table
; entries list, +4 head list (the ring with "start"'s first blocks), +7 ring
; (ARAM), +9 NR (blocks), +11 + 5 * clip: its blocks (long), +14 + 5 * clip:
; their count (even). WRAM $7F:FBE8-$7F:FBF9 (docs/FREE_SPACE.md).

; group 0 request A: $20 stage start jingle -> start, $21 clear jingle / $22
; boss clear jingle -> good
vs_ask:
    pha
    lda.l !vs_on
    cmp #$A5
    bne .out
    lda $01,s
    cmp #$20
    bne +
    php                     ; a record without "start" (1-2: its ring is a
    rep #$10                ; sample of the song, free only once it is over)
    phx
    jsr vs_x
    rep #$20
    lda.l !VOICE_TAB+14,x
    sep #$20
    beq ++
    plx
    plp
    lda #!VS_DELAY          ; the jingle first: start just before the music
    sta.l !vs_delay
    bra .out
++  plx
    plp
    bra .out
+   cmp #$21
    beq +
    cmp #$22                ; (the boss clear jingle: only the end record is on then)
    bne .out
+   lda #$00                ; B's ARAM goes to the voice
    sta.l !vs_bok
    lda.l !vs_clip          ; a good one already (being) loaded
    beq +
    cmp #!VS_BCLIP
    bcc .want
+   jsr vs_pick
.want:
    sta.l !vs_want
    lda #!VS_WAIT
    sta.l !vs_wait
    lda.l !vs_play
    cmp #$02
    bne .out
    lda #$00
    sta.l !vs_play
.out:
    pla
    rts

; A = 1-3 (M 8-bit)
vs_pick:
    lda.l $000068
    clc
    adc.l $000069
-   cmp #$03
    bcc +
    sbc #$03
    bra -
+   inc a
    rts

; X (16-bit) = the record in use (vs_rec = its offset / 2). M 8-bit, X 8-bit in.
vs_x:
    rep #$30
    lda.l !vs_rec
    and #$00FF
    asl a
    tax
    sep #$20
    rts

; end of a song upload (session open, M/X 8-bit): the record of the stage (an
; SB1 song) or the boss stages' end record (SB5's boss victory song, 1-6's
; Golden / 1-7: "good" with the boss clear jingle), the ring with its head list
vs_reset:
    lda #$00
    sta.l !vs_on
    lda.l !gs_song
    sta.l !vs_song
    cmp #!SB1M_SONG
    bne +
    lda.l $7E1031
    bra .key
+   cmp #!VS_END_SONG
    beq +
-   rts
+   lda.l $7E1031
    cmp #!VS_END_ST1
    beq +
    cmp #!VS_END_ST2
    bne -
+   lda #!VS_END_KEY
.key:
    sta.l !vs_key
    rep #$10
    ldx #$0000
-   lda.l !VOICE_TAB,x
    cmp #$FF
    bne ++
    sep #$10
    rts
++  cmp.l !vs_key
    beq +
    rep #$20
    txa
    clc
    adc.w #!VS_REC
    tax
    sep #$20
    bra -
+   rep #$20
    txa
    lsr a
    sep #$20
    sta.l !vs_rec
    lda.l !VOICE_TAB+4,x
    sta $48
    lda.l !VOICE_TAB+5,x
    sta $49
    lda.l !VOICE_TAB+6,x
    sta $4A
    sep #$10
    stz $03D1
    %c0call($C00F62)
    jsr vs_x
    rep #$20
    lda.l !VOICE_TAB+14,x   ; start's blocks in the ring: min(its count, NR)
    cmp.l !VOICE_TAB+9,x
    bcc +
    lda.l !VOICE_TAB+9,x
+   sta.l !vs_sent
    cmp.l !VOICE_TAB+9,x
    bcc +
    lda #$0000
+   sta.l !vs_pos
    sep #$20
    lda #$00
    sta.l !vs_clip
    sta.l !vs_play
    lda #$FF
    sta.l !vs_want
    lda #$00
    sta.l !vs_delay
    sta.l !vs_bok
    lda.l !VOICE_TAB+14+5*!VS_BCLIP,x   ; a ring of its own: part B stays in ARAM
    bne +
    lda #$01
    sta.l !vs_bok
+   sep #$10
    lda #$A5
    sta.l !vs_on
.out:
    rts

; after every set / song upload (session open, M/X 8-bit): the SFX's tables
vs_entries:
    lda.l !vs_on
    cmp #$A5
    bne +
    lda.l !ACTIVE           ; (a menu stream: entry $3E / instrument 29 are the SB6 menu SFX's)
    bne +
    lda.l !gs_song
    cmp.l !vs_song
    bne +
    jsr vs_x
    lda.l !VOICE_TAB+1,x
    sta $48
    lda.l !VOICE_TAB+2,x
    sta $49
    lda.l !VOICE_TAB+3,x
    sta $4A
    sep #$10
    stz $03D1
    %c0call($C00F62)
+   rts

; ---- main loop (M/X 8-bit) ----
vs_tick:
    lda.l !vs_on
    cmp #$A5
    bne +
    lda.l !vs_delay         ; "start" waits for the jingle to be over
    beq ++
    dec a
    sta.l !vs_delay
    bne ++
    lda #$00
    sta.l !vs_want
    lda #!VS_WAIT
    sta.l !vs_wait
    lda.l !vs_play
    cmp #$02
    bne ++
    lda #$00
    sta.l !vs_play
++  lda.l !vs_play
    cmp #$02
    bne ++
+   rts
++  lda.l !ACTIVE           ; Hudson's driver only (no menu stream, no world map driver)
    ora.l $00018D
    beq +
    rts
+   lda.l !vs_key           ; still the stage it was found for
    cmp #!VS_END_KEY
    beq +
    cmp.l $7E1031
    beq +
    rts
+   phb
    phd
    pea $0000
    pld
    lda.b #!VOICE_TAB>>16
    pha
    plb
    rep #$20
    lda $48
    pha
    lda $4A
    pha
    lda $4C
    pha
    sep #$20
    jsr vs_run
    rep #$20
    pla
    sta $4C
    pla
    sta $4A
    pla
    sta $48
    sep #$30
    pld
    plb
    rts

; D = 0, B = !VOICE_TAB's bank, M/X 8-bit
vs_run:
    lda.l $000068
    sec
    sbc.l !vs_last
    sta $4D                 ; frames since the last pass
    lda.l $000068
    sta.l !vs_last
    rep #$30
    lda.l !vs_rec
    and #$00FF
    asl a
    tax                     ; X = the stage's record
    lda.l !vs_clip
    and #$00FF
    cmp #$00FF
    bne +
    brl .ask
+   pha
    asl a
    asl a
    clc
    adc $01,s
    sta $01,s
    txa
    clc
    adc $01,s
    tay                     ; Y = record + 5 * clip
    pla
    sep #$20
    lda.l !vs_play
    bne .playing
    brl .idle

.playing:
    lda.l !vs_lat           ; the first frames: the S-DSP has not keyed on yet
    beq ++
    cmp $4D
    bcc +
    lda $4D
+   sta $4C
    lda.l !vs_lat
    sec
    sbc $4C
    sta.l !vs_lat
    lda $4D
    sec
    sbc $4C
    sta $4D
++  lda $4D
    cmp #$08
    bcc +
    lda #$08
+   sta $4D
-   lda $4D
    beq +
    dec $4D
    rep #$20
    lda.l !vs_clip          ; start: its record's K, the good ones !VS_K
    and #$00FF
    beq .kstart
    lda.w #!VS_K
    bra .kadd
.kstart:
    lda.w !VOICE_TAB+36,x
.kadd:
    clc
    adc.l !vs_acc
    sta.l !vs_acc
    sep #$20
    lda.l !vs_acc+2
    adc #$00
    sta.l !vs_acc+2
    bra -
+   rep #$20
    lda.l !vs_acc+1         ; P = blocks played (at most)
    clc
    adc.w #!VS_AHEAD
    sta.l !vs_need          ; in the ring before the next pass can come
    sec
    sbc.w #!VS_AHEAD+!VS_BEHIND
    pha
    lda.l !vs_clip          ; start: keyed on sooner after its command than a good one
    and #$00FF
    bne +
    lda $01,s
    clc
    adc.w #!VS_BEHIND-!VS_BEHIND_START
    sta $01,s
+   pla
    clc
    adc.w !VOICE_TAB+9,x
    sta.l !vs_lim           ; over blocks surely played
    lda.l !vs_acc+1
    sec
    sbc.w #!VS_TAIL
    bcc .stream
    cmp.w !VOICE_TAB+14,y
    bcc .stream
    sep #$20                ; over
    lda #$00
    sta.l !vs_play
    rep #$20                ; after a voice: the cornered sound's part B back at the ring's top
    lda.w !VOICE_TAB+14+5*!VS_BCLIP,x
    beq .nob
    eor #$FFFF
    sec
    adc.w !VOICE_TAB+9,x
    sta.l !vs_pos
    lda #$0000
    sta.l !vs_sent
    sep #$20
    lda #!VS_BCLIP
    sta.l !vs_clip
    rts
.nob:
    sep #$20                ; (a ring of its own)
    lda #$FF
    sta.l !vs_clip
    rts
.stream:
    lda.l !vs_lim
    cmp.w !VOICE_TAB+14,y
    bcc +
    lda.w !VOICE_TAB+14,y
+   and #$FFFE
    sta.l !vs_lim
    sep #$20
    jmp vs_fill

.idle:                      ; the clip's first blocks (min(count, NR))
    rep #$20
    lda.w !VOICE_TAB+14,y
    cmp.w !VOICE_TAB+9,x
    bcc +
    lda.w !VOICE_TAB+9,x
+   and #$FFFE
    sta.l !vs_lim
    lda #$0000
    sta.l !vs_need
    sep #$20
    jsr vs_fill
.ask:
    sep #$20
    lda.l !vs_want
    cmp #$FF
    bne +
    lda.l !vs_clip          ; nothing asked for: done once the ring holds the next one
    cmp #$FF
    beq ++
    rep #$20
    lda.l !vs_sent
    cmp.l !vs_lim
    sep #$20
    bcc +++
    lda.l !vs_clip
    cmp #!VS_BCLIP
    bne ++
    lda #$01                ; B is back: the cornered sound may play again
    sta.l !vs_bok
++  lda #$02
    sta.l !vs_play
+++ rts
+   cmp.l !vs_clip
    beq +
    sta.l !vs_clip          ; another clip: its first blocks first
    lda #$00
    sta.l !vs_bok
    rep #$20
    lda #$0000
    sta.l !vs_sent
    sta.l !vs_pos
    sep #$20
    bra .count
+   rep #$20
    lda.l !vs_sent          ; key on with HEAD blocks in (or all it has)
    cmp.w #!VS_HEAD
    bcs +
    cmp.l !vs_lim
+   sep #$20
    bcc .count
    lda #$FF                ; key on
    sta.l !vs_want
    lda #$01
    sta.l !vs_play
    lda #!VS_LAT
    sta.l !vs_lat
    lda #$00
    sta.l !vs_acc
    sta.l !vs_acc+1
    sta.l !vs_acc+2
    lda.l $000068
    sta.l !vs_last
    rep #$20
    lda.l !vs_sent
    cmp.w !VOICE_TAB+9,x
    bcc +
    lda #$0000
+   sta.l !vs_pos
    sep #$30
    phb
    lda #$80                ; $0E7F reads $03C0 and $2140 with absolute addressing
    pha
    plb
    lda.l !vs_clip          ; start / good: their own note lengths
    beq +
    lda #!VS_CMD_GOOD
    bra ++
+   lda #!VS_CMD
++  %c0call($C00E7F)
    plb
    rts
.count:
    lda.l !vs_wait
    dec a
    sta.l !vs_wait
    bne .out
    lda #$FF
    sta.l !vs_want
.out:
    rts

; Sends blocks while vs_sent < vs_lim. Hudson's driver answers a port-1
; command only now and then (~every 100 lines), so a transfer starts only
; while this frame has time left (no NMI since the pass began, V count under
; !VS_VSTART), gives the command up (as SB5 does on a lag frame) when no
; answer comes before !VS_VACK, and sends pairs of blocks until !VS_VEND.
; While vs_sent < vs_need (the play position is close) it waits for the
; answer and sends up to vs_need whatever the time. None while SB5's group-3
; queue works. M 8-bit, X = record, Y = record + 5 * clip (16-bit).
vs_fill:
    bra .next
.out:
    sep #$20
    rts
.next:
    rep #$20
    lda.l !vs_sent
    cmp.l !vs_lim
    bcs .out
    sep #$20
    lda.l $0003C4
    ora.l $0003C5
    ora.l $0003C6
    ora.l $0003C7
    bne .out
    stz $4D                 ; blocks it must send (0: on idle time only)
    rep #$20
    lda.l !vs_need
    sec
    sbc.l !vs_sent
    bcc +
    beq +
    inc a
    and #$FFFE
    cmp.w #$00FE
    bcc ++
    lda.w #$00FE
++  sep #$20
    sta $4D
    bra .go
+   sep #$20
    lda.l $000068
    cmp.l $00006A
    bne .out
    jsr vline
    cmp.w #!VS_VSTART
    sep #$20
    bcs .out
.go:
    rep #$20
    lda.l !vs_lim           ; blocks: min(lim - sent, NR - pos, !VS_CH), even
    sec
    sbc.l !vs_sent
    cmp.w #!VS_CH
    bcc +
    lda.w #!VS_CH
+   pha
    lda.w !VOICE_TAB+9,x
    sec
    sbc.l !vs_pos
    cmp $01,s
    bcs +
    sta $01,s
+   pla
    and #$FFFE
    sep #$20
    sta $4C
    cmp $4D
    bcs +
    sta $4D
+   jsr vs_edge             ; C: the ring's last pair, from !vs_pair
    rep #$20
    bcs .dest
    lda.l !vs_sent          ; from the clip's block vs_sent
    jsr nine
    clc
    adc.w !VOICE_TAB+11,y
    sta $48
    sep #$20
    lda.w !VOICE_TAB+13,y
    sta $4A
.dest:
    rep #$20
    lda.l !vs_pos           ; to ring block vs_pos
    jsr nine
    clc
    adc.w !VOICE_TAB+7,x
    jsr vs_send             ; -> A = blocks sent
    rep #$20
    and #$00FF
    bne +
    brl .out
+   pha
    clc
    adc.l !vs_sent
    sta.l !vs_sent
    pla
    clc
    adc.l !vs_pos
    cmp.w !VOICE_TAB+9,x
    bcc +
    lda #$0000
+   sta.l !vs_pos
    brl .next

; The clips are stored as they are: a transfer reaching the ring's last block
; while the clip goes on after it sends the blocks before that pair first,
; then the pair alone from a copy whose last block has END + LOOP (on to the
; ring's start). M 8-bit, X/Y 16-bit (record, record + 5 * clip), $4C/$4D the
; transfer's blocks. -> C set: $48-$4A = !vs_pair, $4C = 2.
vs_edge:
    rep #$20
    lda $4C
    and #$00FF
    pha
    clc
    adc.l !vs_pos
    cmp.w !VOICE_TAB+9,x
    bne .no
    lda $01,s
    clc
    adc.l !vs_sent
    cmp.w !VOICE_TAB+14,y
    bcs .no
    pla
    sep #$20
    lda $4C
    cmp #$03
    bcc .pair
    sbc #$02                ; the blocks before it first
    sta $4C
    cmp $4D
    bcs +
    sta $4D
+   clc
    rts
.no:
    pla
    sep #$20
    clc
    rts
.pair:
    lda $4D
    cmp #$03
    bcc +
    lda #$02
    sta $4D
+   rep #$20
    lda.l !vs_sent
    jsr nine
    clc
    adc.w !VOICE_TAB+11,y
    sta $48
    sep #$20
    lda.w !VOICE_TAB+13,y
    sta $4A
    phx
    phy
    ldy.w #$0000
-   lda [$48],y
    tyx
    sta.l !vs_pair,x
    iny
    cpy.w #$0012
    bne -
    lda.l !vs_pair+9
    and #$FC
    ora #$03
    sta.l !vs_pair+9
    ply
    plx
    rep #$20
    lda.w #!vs_pair&$FFFF
    sta $48
    sep #$20
    lda.b #!vs_pair>>16
    sta $4A
    sec
    rts

nine:                       ; A (16-bit) * 9
    pha
    asl a
    asl a
    asl a
    clc
    adc $01,s
    sta $01,s
    pla
    rts

vline:                      ; -> A (16-bit) = V count (M 16-bit on return)
    sep #$20
    lda.l $002137           ; latch the H/V counters
    lda.l $00213F
    lda.l $00213D
    xba
    lda.l $00213D
    and #$01
    xba
    rep #$20
    rts

; Hudson's port-1 transfer (command $31, as SB5's $C0:106C) of up to $4C
; blocks (even) from [$48] to ARAM A: at least $4D blocks (then the answer
; is awaited whatever the time), more while V < !VS_VEND. Gives the command
; up when $4D = 0 and the driver has not answered by !VS_VACK.
; In: M 16-bit, X/Y 16-bit (kept), D = 0. Out: M 8-bit, A = blocks sent.
vs_send:
    phy
    sta.l $002142           ; ports 2-3: the ARAM address
    sep #$20
    lda #$31
    ora.l $0003C1
    sta.l $002141
    eor #$80
    sta.l $0003CA
.ack:
    lda.l $002141
    cmp.l $002141
    bne .ack
    cmp.l $0003CA
    beq .acked
    lda $4D
    bne .ack
    jsr vline
    cmp.w #!VS_VACK
    sep #$20
    bcc .ack
    lda #$7F                ; no answer in time: given up (as SB5's $C0:1126)
    sta.l $002141
    lda.l $0003C1
    eor #$80
    sta.l $0003C1
    ply
    lda #$00
    rts
.acked:
    stz $4B                 ; byte counter (port 1)
    ldy #$0000
    lda #$00
    pha                     ; [1,s] = blocks sent
.pair:
    lda $01,s
    cmp $4C
    bcs .end                ; all it may send
    cmp $4D
    bcc .more               ; still owed
    jsr vline
    cmp.w #!VS_VEND
    sep #$20
    bcs .end
.more:
    lda #$09
    pha                     ; [1,s] = words left in the pair
.word:
    rep #$20
    lda [$48],y
    sta.l $002142
    sep #$20
    lda $4B
    sta.l $002141
-   lda.l $002141
    cmp.l $002141
    bne -
    cmp $4B
    bne -
    inc $4B
    inc $4B
    iny
    iny
    lda $01,s
    dec a
    sta $01,s
    bne .word
    pla
    lda $01,s
    clc
    adc #$02
    sta $01,s
    bra .pair
.end:
    lda $4B
    inc a
    sta.l $002141
-   lda.l $002142
    cmp.l $002142
    bne -
    cmp #$AA
    bne -
    lda #$7F
    sta.l $002141
    lda.l $0003C1
    eor #$80
    sta.l $0003C1
    pla                     ; blocks sent
    ply
    rts

assert pc() <= !CODE_END, "game SFX code overflows its allocation"

print "SYM gs_anim ", hex(gs_anim)
print "SYM gs_enemy ", hex(gs_enemy)
print "SYM gs_sound ", hex(gs_sound)
print "SYM gs_set ", hex(gs_set)
print "SYM gs_song ", hex(gs_song)
print "SYM gs_tick ", hex(gs_tick)
print "SYM vs_tick ", hex(vs_tick)
print "SYM vs_send ", hex(vs_send)
print "SYM end ", hex(pc())
