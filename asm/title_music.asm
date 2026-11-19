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
; Tracks: 0 = the title intro's sounds (the last chunk is silence and
; repeats until the music replaces it), 1 = the title music, 2 = the save
; file / character selection music of the Normal Game. The save music starts
; on the main-loop pass after the menu's sample set request (group 4, id
; SAVE_SET) in mode SAVE_MODE ($1031), and plays through the picker until
; the stage's stop request releases it. Each track is a run of segments
; (SEGS file: bank, first chunk offset, end offset; a 0 bank ends the run,
; its word is the segment to loop to), so a track can use bank tails.
;
; Defines: CODE (address), L_STREAM / L_SAVE (upload lists: driver at the
; track's rate + prefill, JMP entry over the loader's RET; then the entry
; address), ENTRY (ARAM entry), L_SAMPLES / L_NEW / L_ORIG (upload lists:
; SFX samples, SB6 and SB5 SFX definitions), SFX_SAFE, NSONGS, SONG_TABLE,
; RTL_C0, SEGS (file), SEG_PRE / SEG_TITLE / SEG_SAVE (offsets of each
; track's first segment), SAVE_SET, SAVE_MODE, SFX_SLOTS (file).

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
!track  = $00010A       ; track streaming (0 intro, 1 title, 2 save menu)
!seg    = $00010B       ; word: offset in segs of the segment being sent
!pend   = $00010D       ; 1 = start the save music on the next main-loop pass
!NMI_FRAMES = $000068   ; incremented by the NMI handler ($C0:F431)
!MODE   = $7E1031       ; game mode (3 = Normal Game menu)
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
if !FD
    jsr fd_sound            ; SB1's / SB2's drivers (world map music)
    bcc +
    brl .swallow
+
endif
    lda.l !active
    bne +
    lda $06,s               ; in-game SFX (asm/game_sfx.asm) while Hudson's driver runs
    xba
    lda $05,s
    jsl !GS_SOUND
    bcc +
    brl .swallow
+   lda $06,s               ; World 1's 1-1: SB1's music (tools/sb6/features/sb1_music.py)
    bne +
    lda $05,s
    cmp #!SB1M_ID
    bne +
    lda.l !MODE
    cmp #!SB1M_STAGE
    bne +
    jsr sb1m_play
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
    lda.l !track            ; the title's pan sound (the intro ended or was
    cmp #$01                ; skipped) or the save music: the title music
    beq .swallow            ; replaces it
    jsr release
+   lda #$00
    sta.l !pend
    lda #$01
    jsr start_stream
    bra .swallow
.other:
    lda #$00                ; any other request cancels a pending save music
    sta.l !pend
    lda $06,s
    cmp #$04
    bne +
    lda $05,s
    cmp #!SAVE_SET
    bne +
    lda.l !MODE
    cmp #!SAVE_MODE
    bne +
    lda #$01                ; Normal Game menu: the save music once the set is in
    sta.l !pend
+   lda.l !active
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

; SB1's 1-1 music instead of SB5's ZONE1 song (music id !SB1M_ID on stage
; !SB1M_STAGE): one upload session with its list (sequence at $3000, samples,
; directory and tuning entries) and game_sfx's cornered entry looped into its
; silent block (the song covers B1), then the song command twice, as the API
; does. Set and song are marked unknown so the next request uploads its own.
sb1m_play:
    php
    phb
    sep #$30
    lda #$80                ; Hudson's routines use absolute $03Cx / $214x
    pha
    plb
    lda #!SB1M_ID
    sta.l $0003CC
    lda #$FF
    sta.l $0003CE
    sta.l $0003CD
    lda #!SB1M_SONG         ; game_sfx's gs_song: R stays, no room for the cornered sound's part B
    sta.l $00018B
    %c0call($C00F13)        ; open the upload session
    %sendlist(!SB1M_LIST)
    %sendlist(!L_DIR0)
    %c0call($C00F35)        ; close it (the driver runs on)
    lda #!SB1M_CMD
    %c0call($C00E7F)
    lda #!SB1M_CMD
    %c0call($C00E7F)
    plb
    plp
    rts

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
    beq .idle
    jsr feed
    bra +
.idle:
    lda.l !pend
    beq +
    lda #$00
    sta.l !pend
    lda #$02
    jsr start_stream
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
    lda #$00
    jsr start_stream
+   plp
    rtl

; A = track. Hudson's loader (port 1 = $10) <- the SFX samples (when they
; are not in ARAM), the SB6 SFX definitions, the driver at the track's rate +
; prefill and a JMP entry over the loader's final RET at $1041, so the end of
; the upload runs the driver.
start_stream:
    php
    sep #$30
    pha
    %c0call($C00F13)
    lda.l !sfxok
    bne +
    %sendlist(!L_SAMPLES)
    lda #$01
    sta.l !sfxok
+   %sendlist(!L_NEW)
    lda #$01
    sta.l !sfxnew
    lda $01,s
    cmp #$02
    beq .save
    %sendlist(!L_STREAM)
    bra .sent
.save:
    %sendlist(!L_SAVE)
.sent:
    %c0call($C00F35)        ; end of upload: the loader "returns" into the driver
    lda $4B                 ; the session's last kick
    sta.l !kick
    inc a
    and #$7F
    sta.l !seq
    pla
    sta.l !track
    rep #$30
    and #$00FF
    asl
    tax
    lda.l seg_start,x
    sta.l !seg
    tax
    lda.l segs+1,x
    sta.l !ptr
    sep #$20
    lda.l segs,x
    sta.l !bank
    sep #$30
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

if !FD
; ---- Super Bomberman 1's / 2's sound drivers on the world map ---------------
; ZONE1 plays SB1's map song with SB1's own driver, ZONE2 SB2's with SB2's
; (tools/sb6/features/world_map.py). The map's zone setup calls map_music
; (asm/world_map.asm wmap_op) with the zone's driver (0 = Hudson's, SB5's map
; song); SB5's map music request (group 0, id !MAP_REQ) then starts it, or,
; when the map song already plays (an L/R zone change), map_music switches
; drivers itself. Starting a driver: when Hudson's runs, its loader gets a
; stub at $1100 (mute, IPL ROM on, JMP $FFC0) and a JMP to it over the
; loader's final RET; the IPL ROM gets the driver's list (a loader at $0200,
; extra blocks) and the loader takes the sound RAM image from $0800, 3 bytes
; per handshake (SB1 39 KB ~1 s, SB2 57 KB ~1.5 s), then jumps to the
; driver's cold start; then its song command. Leaving: SB1 port 0 $37, SB2
; port 1 command 6 make them jump back to the IPL ROM; then either the next
; driver or Hudson's ($C0:0CCF, SB5's own sound init at power-on: sets $58
; and $56). While a foreign driver runs, SB5's menu SFX 1 (move) and 4
; (accept) become its own (table), other SFX, data streams and driver
; commands (group $10) are dropped, and any other request first brings
; Hudson's driver back, then runs normally.
;
; fd_table, per driver (24 bytes): upload list (3), 3 x (image part (3),
; triples (2)), ready values of ports 2 / 3, song command, echo xor of port 0,
; SFX move / accept.
!fdon   = $00018D           ; foreign driver running (0 = Hudson's)
!fdreq  = $00018E           ; the map's driver (set by map_music)
!fdcmd  = $00018F           ; last command on port 0
!fdp1   = $000191           ; last command on port 1
!fdtmp  = $000192           ; scratch
!mapon  = $000193           ; 1 = the map music was requested (and plays)
!fdpart = $000194           ; part counter
!fdseq  = $000195           ; upload sequence

; In: [$07,s]/[$08,s] = id / group (sound_hook's frame, +2 for the JSR).
; C set = request consumed.
fd_sound:
    lda $08,s               ; group
    bne .notmap
    lda $07,s
    cmp #!MAP_REQ
    bne .notmap
    lda #$01                ; ---- the map music
    sta.l !mapon
    lda.l !fdreq
    cmp.l !fdon
    beq .same
    lda.l !fdon
    beq .from_hudson
    jsr fd_leave            ; foreign -> IPL ROM
    lda.l !fdreq
    bne +
    jsr fd_hudson           ; -> Hudson's driver, which plays the request
    clc
    rts
+   jsr fd_upload
    sec
    rts
.from_hudson:
    lda #$00
    sta.l !pend
    lda.l !active
    beq +
    jsr release
+   jsr fd_start
    sec
    rts
.same:
    lda.l !fdon             ; the same music again: Hudson's plays it, a foreign one is kept
    beq .pass
    sec
    rts
.notmap:
    lda.l !fdon
    bne .foreign
    lda $08,s
    bne .pass
    lda #$00                ; another song: the map is left
    sta.l !mapon
    sta.l !fdreq
.pass:
    clc
    rts
.foreign:
    lda $08,s
    cmp #$02
    beq .sfx
    cmp #$03
    beq .eat_far
    cmp #$10
    beq .eat_far
    jsr fd_leave            ; anything else: Hudson's driver back first
    jsr fd_hudson
    lda #$00
    sta.l !mapon
    sta.l !fdreq
    clc
    rts
.eat_far:
    sec
    rts
.sfx:
    lda.l !fdon
    cmp #$03                ; driver 3 (the SPC waits in the IPL ROM): dropped
    beq .eat
    lda $07,s
    cmp #$04
    bne +
    lda.l !fdon             ; accept: SB1's own SFX 1 plays SB6's recording
    cmp #$02                ; (tools/sb6/features/world_map.py _sb1_accept); SB2's
    beq .accept             ; driver gives way to driver 3
+   lda.l !fdon
    jsr fd_x                ; X = table offset
    lda $07,s
    cmp #$01
    beq +
    cmp #$04
    bne .eat
    inx
+   lda.l fd_table+22,x     ; the driver's own SFX
    sta.l !fdtmp
    lda.l !fdon
    cmp #$01
    bne .sfx2
    lda.l !fdp1             ; SB1: port 1, new when bit 7 changes, echoed
    and #$80
    eor #$80
    ora.l !fdtmp
    sta.l !fdp1
    sta.l APUIO1
-   cmp.l APUIO1
    bne -
    bra .eat
.sfx2:
    lda.l !fdcmd            ; SB2: port 0 (with the songs), new when it changes, echoed xor $80
    and #$80
    eor #$80
    ora.l !fdtmp
    sta.l !fdcmd
    sta.l APUIO0
    eor #$80
-   cmp.l APUIO0
    bne -
.eat:
    sec
    rts
.accept:                    ; accept on ZONE2 (a stage is chosen): SB6's recording, played
    lda.l !fdreq            ; by driver 3 (one voice, then the IPL ROM: the sample
    pha                     ; keeps playing until the next request brings Hudson's
    lda #$03                ; driver back); the map's driver stays !fdreq for L/R
    sta.l !fdreq
    jsr fd_leave
    jsr fd_upload
    pla
    sta.l !fdreq
    sec
    rts

; X = (A - 1) * 24: the driver's entry in fd_table. M 8-bit.
fd_x:
    dec a
    sta.l !fdtmp
    asl a
    clc
    adc.l !fdtmp            ; * 3
    asl a
    asl a
    asl a                   ; * 24
    sta.l !fdtmp
    lda #$00
    xba
    lda.l !fdtmp
    tax                     ; (X may be 16-bit: B = 0)
    rts

; Hudson's driver (or the stream driver) -> IPL ROM -> !fdreq.
fd_start:
    php
    sep #$30
    %c0call($C00F13)        ; Hudson's loader
    %sendlist(!FD_STUB)
    %c0call($C00F35)        ; its RET is a JMP to the stub now: SPC -> IPL ROM
    jsr fd_upload
    plp
    rts

; IPL ROM -> driver !fdreq, playing its song.
fd_upload:
    php
    sep #$30
    lda.l !fdreq
    jsr fd_x
    %c0call($C00F13)        ; the IPL ROM ($AA/$BB)
    lda.l !fdreq
    jsr fd_x
    lda.l fd_table+0,x
    sta $48
    lda.l fd_table+1,x
    sta $49
    lda.l fd_table+2,x
    sta $4A
    stz $03D1
    %c0call($C00F62)        ; loader at $0200 (+ extra blocks)
    %c0call($C00F35)        ; run it
    lda #$03
    sta.l !fdpart
    lda.l !fdreq
    jsr fd_x                ; X = entry, then + 5 per part
    lda #$00
    sta.l !fdseq
.part:
    rep #$30
    phx
    lda.l fd_table+6,x      ; triples
    tay
    lda.l fd_table+3,x      ; source offset
    pha
    sep #$20
    lda.l fd_table+5,x      ; source bank
    plx
    cpy.w #$0000
    beq +
    pha
    lda.l !fdseq
    xba
    pla                     ; A = bank, B = sequence
    jsr fd_send
    xba
    sta.l !fdseq
+   rep #$20
    pla                     ; table position
    clc
    adc.w #5
    tax
    sep #$20
    lda.l !fdpart
    dec a
    sta.l !fdpart
    bne .part
    sep #$10
    lda #$00                ; final kick: ports 1-3 = 0, then port 0 = 0
    sta.l APUIO1
    sta.l APUIO2
    sta.l APUIO3
    lda.l !fdseq
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    lda #$00
    sta.l APUIO0
    lda.l !fdreq
    jsr fd_x
-   lda.l APUIO2            ; ready: the driver's init writes these
    cmp.l fd_table+18,x
    bne -
    lda.l APUIO3
    cmp.l fd_table+19,x
    bne -
    lda #$00
    sta.l !fdp1
    sta.l !fdcmd
    lda.l fd_table+20,x     ; the song (0: none)
    beq +
    sta.l !fdcmd
    sta.l APUIO0
    eor.l fd_table+21,x
-   cmp.l APUIO0            ; echoed when taken
    bne -
+
    lda.l !fdreq
    sta.l !fdon
    lda #$FF
    sta.l !song             ; nothing of Hudson's is left in ARAM
    sta.l $0003CE
    lda #$00
    sta.l !sfxok
    sta.l !sfxnew
    sta.l $000188           ; asm/game_sfx.asm: R not in ARAM, idle
    sta.l $000189
    sta.l $00018B
    sta.l $00018C
    plp
    rts

; A = source bank, X = offset, Y = triples, B = sequence (kept, next); M 8-bit, X 16-bit.
fd_send:
    phb
    pha
    plb
.triple:
    lda.w $0000,x
    sta.l APUIO1
    lda.w $0001,x
    sta.l APUIO2
    lda.w $0002,x
    sta.l APUIO3
    xba
    sta.l APUIO0
-   cmp.l APUIO0
    bne -
    inc a
    xba
    inx
    inx
    inx
    dey
    bne .triple
    plb
    rts

; Foreign driver -> IPL ROM (it jumps to $FFC0 after muting).
fd_leave:
    php
    sep #$30
    lda.l !fdon
    cmp #$03                ; driver 3 is already back in the IPL ROM
    beq ++
    cmp #$02
    beq +
    lda.l !fdcmd            ; SB1 (1, stage drivers 4+): port 0 command $37
    and #$80
    eor #$80
    ora #$37
    sta.l APUIO0
    bra ++
+   lda.l !fdp1             ; SB2: port 1 command 6 (its RAM copy of the IPL ROM)
    and #$80
    eor #$80
    ora #$06
    sta.l APUIO1
    eor #$80
-   cmp.l APUIO1            ; taken (the handshake below writes port 1)
    bne -
++  lda #$00
    sta.l !fdon
    plp
    rts

; IPL ROM -> Hudson's driver (SB5's power-on sound init, waits for $AA/$BB).
fd_hudson:
    php
    sep #$30
    jsl $C00CCF
    lda #$00
    sta.l $000188
    sta.l $000189
    sta.l $00018B
    sta.l $00018C
    plp
    rts

; JSL, A = the map's driver (asm/world_map.asm wmap_op, a script op: the
; screen is dark). Switches now when the map music already plays.
map_music:
    php
    phb
    phd
    sep #$30
    pha
    lda #$80
    pha
    plb
    pea $0000
    pld
    pla
    sta.l !fdreq
    lda.l !mapon
    beq .done               ; the map music request will do it
    lda.l !fdreq
    cmp.l !fdon
    beq .done
    lda.l !fdon
    beq .from_hudson
    jsr fd_leave
    lda.l !fdreq
    bne +
    jsr fd_hudson           ; back to SB5's map song
    lda #$00
    xba
    lda #!MAP_REQ
    jsl $C00CED
    bra .done
+   jsr fd_upload
    bra .done
.from_hudson:
    lda #$00
    sta.l !pend
    lda.l !active
    beq +
    jsr release
+   jsr fd_start
.done:
    pld
    plb
    plp
    rtl

fd_table = !FD_TABLE
print "SYM map_music ", hex(map_music)
endif

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
    rep #$30                ; Y = offset after the chunk: end of the segment?
    lda.l !seg
    tax
    tya
    cmp.l segs+3,x
    bne .store
    txa
    clc
    adc #$0005
    tax
    sep #$20
    lda.l segs,x
    bne +
    rep #$20                ; end of the run: the segment it loops to
    lda.l segs+1,x
    tax
    sep #$20
    lda.l segs,x
+   sta.l !bank
    rep #$20
    txa
    sta.l !seg
    lda.l segs+1,x
.store:
    sta.l !ptr
    sep #$20
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

; Segments of every track: bank, offset of the first chunk, offset after the
; last; a 0 bank ends a track, followed by the offset of its loop segment.
segs:
    incbin "!SEGS"
seg_start:
    dw !SEG_PRE, !SEG_TITLE, !SEG_SAVE

assert pc() <= !CODE_END, "title music code overflows its allocation"

print "SYM sound_hook ", hex(sound_hook)
print "SYM loop_hook ", hex(loop_hook)
print "SYM pre_start ", hex(pre_start)
print "SYM set_hook ", hex(set_hook)
print "SYM song_hook ", hex(song_hook)
print "SYM end ", hex(pc())
