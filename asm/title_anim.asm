; Animated title (tools/sb6/features/title_anim.py builds the tables):
; the sky pans up, the characters fall in wave by wave, the logo drops in,
; then the logo's colors cycle and the characters change pose now and then.
;
; Everything runs in the NMI (title_nmi, called by pick_nmi after the game's
; VRAM queue, forced blank): one "job" per frame at most (a few DMAs to VRAM,
; <= 2560 bytes), the BG1/BG2 vertical scroll and the screen configuration
; (BG1 map 32x64 at $4800 with chr $6000, BG2 map 32x64 at $3800 with chr
; $0000). BG3 (the menu text) stays hidden until the logo has landed; the
; title's own script waits for that before it starts the music and reads the
; pads (script ops FF 1A F8-FB through pick_op).
;
; Job record (8 bytes): VRAM word, rows, bytes per row, source (24 bits); a
; row is one DMA, the next row goes 32 words further (a map rectangle).
;
; State: $7F:FD00-$7F:FD43 (docs/FREE_SPACE.md).

asar 1.90
hirom

!V      = $7FFD00
!sig    = !V+$00        ; $5AA5 = the variables below are valid
!state  = !V+$02        ; 0 off, 1 loading, 2 waiting for the fade-in, 3 intro, 4 idle
!seen   = !V+$03        ; 1 = the intro was shown (menus come back without it)
!done   = !V+$04        ; 1 = the logo has landed: text, music and pads
!tm     = !V+$05        ; main screen layers
!lp     = !V+$06        ; word: offset in the job list / in the intro's frames
!final  = !V+$08        ; 1 = loading the finished scene (no intro, or skipped)
!bg1v   = !V+$0A        ; word
!bg2v   = !V+$0C        ; word
!prev   = !V+$0E        ; Start/A held in the last frame
!cyc    = !V+$0F        ; idle: frame in the logo period
!lf     = !V+$10        ; logo frame
!drop   = !V+$11        ; frames of the logo's drop done
!rng    = !V+$12        ; word
!amask  = !V+$14        ; characters in their alternate pose
!rot    = !V+$15        ; last character tried
!sst    = !V+$16        ; 2 players (scratch areas): 0 free, 1/2 tile jobs, 3 cells pending, 4 last step
!sch    = !V+$18        ; ... character
!stm    = !V+$1A        ; ... frames left
!ctm    = !V+$1E        ; 7 characters: frames until the next alternate pose
!va     = !V+$26        ; word scratch
!ln     = !V+$28
!rows   = !V+$2A
!cs     = !V+$2B        ; scratch area being served
!t0     = !V+$2C
!cidle  = !V+$2E        ; cursor: frames without input (word)
!canim  = !V+$30        ; 0 rest, 1-4 looking around, 5 confirming, 6 confirmed (face kept)
!ct     = !V+$31        ; frame of the animation
!ceye   = !V+$32        ; its face
!cpose  = !V+$33        ; pose in VRAM ($FF = none)
!cref   = !V+$34        ; frames, for the periodic rewrite
!cany   = !V+$35        ; scratch: any button held
!ctile  = !V+$36        ; sprite frame (tile 0/2/4/6) that holds the pose
!cy     = !V+$37        ; $1034 - the sprite's Y at rest (held while SB5's cursor hops)
!cm     = !V+$38        ; menu $1036 when the confirmation began
!c34    = !V+$39        ; (unused)
!cvis   = !V+$3A        ; 1 = the cursor sprite was on screen in the last frame
!cforce = !V+$3B        ; frames the pose and colors are still sent again
!cw     = !V+$3C        ; FF 1A FC: 1 = its frame has been waited
!smul   = !V+$3D        ; 1 = player 0 shows a pose in several steps (both areas)
!cgo    = !V+$3E        ; FF 1A FD: 1 = the game accepted an item (the cursor confirms)
!sof    = !V+$40        ; 2 words: the pending step's record in !ALT

!BG1SC  = $4A           ; map $4800, 32x64
!BG2SC  = $3A           ; map $3800, 32x64
!NBA    = $06           ; BG1 chr $6000, BG2 chr $0000
!HIDDEN = $00FF         ; BG1 V scroll 256 (-1): the empty rows 32-63
!REST   = $03FF         ; V scroll -1: screen line 1 = map line 0
!ALTREC = 8             ; bytes per character in !ALT: conflicts, several steps, restore job, 2 step lists

org !ORG

; ---------------------------------------------------------------------------
; Scripts.
s_load:
    db $26,!SET,$27,$02             ; version glyphs (BG3)
    db $2A,$01                      ; the title's 128 BG colors
    db $26,$03,$27,$96,$2A,$08      ; SB5's BG3 font and text colors
    db $FF,$1A,$F8                  ; tiles and maps, one job per frame
    db $FF,$1A,$F9                  ; the task waits here until they are in VRAM
    db $FF,$1A,$FB                  ; the pan's sound (when the intro plays)
    db $00
; (the cartridge starts the music first; its upload holds the main loop for
; half a second, so the menu cursor is created and drawn before it)
s_wait:
    db $FF,$1A,$FA                  ; the task waits here until the logo has landed
    db $06,$04
    db $5B,!CURY,$60,$34,$10        ; menu cursor Y
    db $5B,$00,$5F,$36,$10          ; menu 0
    db $24,$D3,$1A,$C7              ; the cursor object
    db $5D,$99,$01,$86,$01,$49,.back_end-.back  ; [$0199] = 1: back from the character
.back:                                  ; selection with B: the players menu,
    db $5B,$00,$5F,$99,$01              ; cursor on the players count (as the
    db $FF,$91,$09,$0B,$10,$08,$03      ; NORMAL GAME accept at $C7:18B6)
    db $FF,$8D,!PLAYERS_ARR,!SET,$03,$00,$00
    db $5B,$01,$5F,$36,$10
    db $5D,$29,$01,$61,$FF,$5F,$32,$10  ; $1032 = [$0129] - 1
    db $24,$B5,$1A,$C7                  ; cursor Y
.back_end:
    db $FF,$1A,$FC                  ; a few frames: the cursor's tiles go through
    db $FF,$1A,$FC                  ; the VRAM queue, it is drawn and gets its
    db $FF,$1A,$FC                  ; SB6 pose (the upload must not share an NMI
    db $FF,$1A,$FC                  ; with them: it would run past the vblank)
    db $FF,$1A,$FC
    db $FF,$1A,$FC
    db $42,$02,$00                  ; title music
    db $00
; The title menu's accept ($C7:189C calls it instead of SFX 4 + $C7:1AEA):
; the cursor's confirmation starts only here, when the game takes the press.
s_accept:
    db $FF,$1A,$FD
    db $42,$04,$02                  ; SFX 4 (accept)
    db $24,$EA,$1A,$C7              ; SB5's wait (shortened: title.py ACCEPT_WAIT)
    db $00

; ---------------------------------------------------------------------------
; FF 1A F8-FA (from pick_op: A = the operand, M/X 8-bit, $0A-$0C = next op).
title_op:
    cmp #$FD
    bne +
    lda #$01                        ; ---- FD: an item was accepted (s_accept)
    sta.l !cgo
    rtl
+   cmp #$F9
    beq .waitload
    cmp #$FA
    beq .waitdone
    cmp #$FC
    bne +
    lda.l !cw                       ; ---- FC: the task sleeps one frame
    bne ++
    lda #$01
    sta.l !cw
    bra .again
++  lda #$00
    sta.l !cw
    rtl
+   cmp #$FB
    bne +
if !PANSND
    lda.l !final                    ; ---- FB: the pan's sound; it has its
    bne ++                          ; lead of silence for the fade-in
    jsl !PANSND
++
endif
    rtl
+   rep #$20                        ; ---- F8: start
    lda #$5AA5
    sta.l !sig
    lda #$0000
    sta.l !lp
    lda.l !rng
    adc $68
    ora #$0001
    sta.l !rng
    sep #$20
    lda #$00
    sta.l !done
    sta.l !final
    lda.l !seen
    cmp #$01
    bne +
    sta.l !final
+   lda #$13                        ; BG1 + BG2 + OBJ
    sta.l !tm
    lda #$FF
    sta.l !prev
    lda #$01
    sta.l !state
    rtl
.waitload:
    lda.l !state
    cmp #$01
    beq .again
    rtl
.waitdone:
    lda.l !state
    beq +                           ; not running: do not hold the title
    cmp #$05
    bcs +
    lda.l !done
    cmp #$01
    bne .again
+   rtl
.again:
    ; A script runs to its end inside one frame (there is no wait op), so the
    ; task itself is put to sleep: its saved script pointer goes back to this
    ; op, it resumes in the interpreter ($C2:0211 reloads that pointer) and
    ; control returns to the task runner ($C0:22F0 keeps its stack in $75).
    ldx $73
    rep #$20
    lda $0A
    sec
    sbc #$0003
    sep #$20
    sta $0C87,x
    xba
    sta $0CAF,x
    lda $0C
    sta $0CD7,x
    lda #$11
    sta $0BBF,x
    lda #$02
    sta $0BE7,x
    lda #$C2
    sta $0C0F,x
    rep #$20
    lda $75
    sec
    sbc #$0003
    tcs
    sep #$30
    rtl

; ---------------------------------------------------------------------------
; A (16-bit) = offset of a job: its rows to VRAM.
dojob:
    php
    rep #$30
    tax
    lda.l !JOBS+0,x
    sta.l !va
    lda.l !JOBS+3,x
    sta.l !ln
    lda.l !JOBS+5,x
    sta $4302
    sep #$20
    lda.l !JOBS+7,x
    sta $4304
    lda.l !JOBS+2,x
    sta.l !rows
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
-   rep #$20
    lda.l !va
    sta $2116
    clc
    adc #$0020
    sta.l !va
    lda.l !ln
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    lda.l !rows
    dec a
    sta.l !rows
    bne -
    plp
    rts

; 16-bit Galois LFSR; returns A (8-bit) = low byte.
rand:
    php
    rep #$20
    lda.l !rng
    lsr a
    bcc +
    eor #$B400
+   sta.l !rng
    plp
    lda.l !rng
    rts

; ---------------------------------------------------------------------------
; NMI (M/X 8-bit, DBR = 0, D = 0, forced blank).
title_nmi:
    php
    sep #$30
    lda $1031
    cmp #$01                        ; boot logo, stages and demos: the next title
    beq +                           ; plays its intro again
    cmp #$0D
    bcc ++
+   lda #$00
    sta.l !seen
++  rep #$20
    lda.l !sig
    cmp #$5AA5
    sep #$20
    bne .out
    lda.l !state
    beq .out
    cmp #$05
    bcs .out
    lda $1031
    cmp #$02
    beq .run
    lda $0300
    bpl .run                        ; another mode, the title still fading out
    lda #$00                        ; ---- off: the game's screen configuration
    sta.l !state
    lda $0368
    sta $2107
    lda $0369
    sta $2108
    lda $0371
    asl a
    asl a
    asl a
    tax
    lda.l $808016,x
    sta $210B
    lda $030F
    ora #$04
    sta $030F
.out:
    plp
    rtl

.run:
    lda.b #!BG1SC
    sta $2107
    lda.b #!BG2SC
    sta $2108
    lda.b #!NBA
    sta $210B
    lda.l !state
    cmp #$01
    beq .load
    cmp #$02
    bne +
    jmp .wait
+   cmp #$03
    bne +
    jmp .play
+   jmp .idle

; ---- 1: the job list, one per frame --------------------------------------
.load:
    rep #$30
    lda.l !lp
    tax
    lda.l !final
    and #$00FF
    bne +
    lda.l !INITA,x
    bra ++
+   lda.l !INITB,x
++  cmp #$FFFF
    beq .loaded
    pha
    txa
    inc a
    inc a
    sta.l !lp
    pla
    jsr dojob
    sep #$30
    brl .tail
.loaded:
    lda #$0000
    sta.l !lp
    lda.l !final
    and #$00FF
    bne +
    lda.w #!HIDDEN
    sta.l !bg1v
    lda.l !PLAY+2
    sta.l !bg2v
    sep #$30
    lda #$02
    sta.l !state
    brl .tail
+   sep #$30
    jsr idle_start
    lda.b #!NDROP                     ; the logo is already in place
    sta.l !drop
    jsr landed
    rep #$20
    lda.w #!REST
    sta.l !bg1v
    sta.l !bg2v
    sep #$20
    brl .tail

; ---- 2: the screen is still black ----------------------------------------
.wait:
    lda $0300
    bmi +
    lda #$03
    sta.l !state
+   brl .tail

; ---- 3: the intro, a record per frame: BG1 V, BG2 V, job -------------------
.play:
    lda $1A                         ; Start or A on pad 1 or 2 (raw words $19,
    ora $1C                         ; $1B: the actions in $2C are not decoded
    and #$10                        ; yet): straight to the end
    sta.l !t0
    lda $19
    ora $1B
    and #$80
    ora.l !t0
    tay
    lda.l !prev
    eor #$FF
    sta.l !t0
    tya
    sta.l !prev
    and.l !t0
    beq +
    lda #$00                        ; black while the finished scene loads
    sta.l !tm
    lda #$01
    sta.l !final
    sta.l !state
    rep #$20
    lda #$0000
    sta.l !lp
    sep #$20
    brl .tail
+   rep #$30
    lda.l !lp
    tax
    lda.l !PLAY+4,x
    cmp #$FFFE
    beq .played
    lda.l !PLAY+0,x
    sta.l !bg1v
    lda.l !PLAY+2,x
    sta.l !bg2v
    txa
    clc
    adc #$0006
    sta.l !lp
    lda.l !PLAY+4,x
    cmp #$FFFF
    beq +
    jsr dojob
+   sep #$30
    brl .tail
.played:
    sep #$30
    jsr idle_start
    lda #$00
    sta.l !drop
    lda #$04
    sta.l !state
    brl .tail

; ---- 4: logo drop, logo colors, alternate poses ----------------------------
.idle:
    jsr cursor                      ; first: its frame may follow the game's VRAM queue
    lda.l !drop
    cmp.b #!NDROP
    bcs .down
    asl a
    tax
    rep #$20
    lda.l !DROP,x
    sta.l !bg1v
    sep #$20
    lda.l !drop
    inc a
    sta.l !drop
    cmp.b #!NDROP
    bne .cycle
    jsr landed
    bra .cycle
.down:
    ldx.b #!NCHAR-1
-   lda.l !ctm,x
    beq +
    dec a
    sta.l !ctm,x
+   dex
    bpl -
    ldx #$01
-   lda.l !stm,x
    beq +
    dec a
    sta.l !stm,x
+   dex
    bpl -
.cycle:
    lda.l !cyc
    bne .serve
    lda.l !lf                       ; ---- next logo frame: its colors
    inc a
    cmp.b #!NLOGO
    bcc +
    lda #$00
+   sta.l !lf
    asl a
    tax
    rep #$20
    lda.l !LOGOPTR,x
    sta $4302
    lda.w #!CGLEN
    sta $4305
    sep #$20
    lda.b #!LOGOCG>>16
    sta $4304
    lda.b #!CGFIRST
    sta $2121
    stz $4300
    lda #$22
    sta $4301
    lda #$01
    sta $420B
    bra .next
.serve:
    lda.l !done
    cmp #$01
    bne .next
    lda.l !cyc
    ora.l !smul                     ; a pose in steps (!smul = 1): player 0 every frame
    dec a
    and #$01                        ; frames 1, 3: area 0; frames 2, 4: area 1
    sta.l !cs
    jsr alt_serve
.next:
    lda.l !cyc
    inc a
    cmp.b #!PERIOD
    bcc +
    lda #$00
+   sta.l !cyc

.tail:
    lda.l !tm
    sta $030F
    sta $212C
    lda.l !bg1v
    sta $210E
    lda.l !bg1v+1
    sta $210E
    lda.l !bg2v
    sta $2110
    lda.l !bg2v+1
    sta $2110
    plp
    rtl

bits:
    db $01,$02,$04,$08,$10,$20,$40,$80

; The idle state from its beginning (M/X 8-bit).
idle_start:
    lda #$00
    sta.l !cyc
    sta.l !lf
    sta.l !amask
    sta.l !rot
    sta.l !sst
    sta.l !sst+1
    sta.l !stm
    sta.l !stm+1
    sta.l !smul
    ldx.b #!NCHAR-1
-   jsr rand                        ; first alternate pose within ~4 s
    sta.l !ctm,x
    dex
    bpl -
    lda #$00
    sta.l !canim
    sta.l !ct
    sta.l !ceye
    sta.l !cref
    sta.l !cidle
    sta.l !cidle+1
    sta.l !cgo
    lda #$11                        ; rest Y offset until the first rest frame
    sta.l !cy
    lda #$FF
    sta.l !cpose
    lda #$00
    sta.l !cvis
    sta.l !cforce
    lda #$04
    sta.l !state
    rts

; ---------------------------------------------------------------------------
; The fan game's menu cursor (idle state, every frame; M/X 8-bit). SB5 draws
; its cursor as one 16x16 sprite, the first in OAM (OBJ palette 0; tile 0 at
; rest, tiles 2/4/6 while it hops after an accepted option); the pose is
; written over the 4 tiles of the frame in use and the colors over the
; palette. Rest pose; after !CURIDLE frames without input a look around
; (random direction and face); an accepted item (FF 1A FD from s_accept,
; not the pad: a press the game ignores does nothing): the confirmation,
; which plays to its end and whose face stays until the next input - SB5's
; hop is held still meanwhile (the fan game's cursor only nods), while the
; same menu and option are up.
; Tables from tools/sb6/features/title.py.
cursor:
    lda.l !done
    cmp #$01
    beq +
    rts
+   lda $1B                         ; pad 2 not plugged in reads $FFFF
    and $1C
    cmp #$FF
    bne +
    lda $19
    and #$F0
    ora $1A
    bra ++
+   lda $19
    ora $1B
    and #$F0
    ora $1A
    ora $1C
++  sta.l !cany
    lda.l !cgo                      ; the game accepted an item (FF 1A FD, its
    sta.l !t0                       ; accept path): presses it ignores - while it
    lda #$00                        ; waits, fades or shows the QR - never start
    sta.l !cgo                      ; a confirmation
    lda.l !canim                    ; confirmed in another menu (Normal Game ->
    cmp.b #!CURCONFIRM              ; players): back to rest and its looks around
    bcc +
    lda $1036
    cmp.l !cm
    beq +
    lda #$00
    sta.l !canim
    sta.l !cidle
    sta.l !cidle+1
+   lda.l !canim
    cmp.b #!CURCONFIRM
    beq .anim                       ; the confirmation plays to its end
    lda.l !t0
    beq +
    lda.b #!CUREYE
    sta.l !ceye
    lda $1036
    sta.l !cm
    lda.b #!CURCONFIRM
    bra .start
+   lda.l !cany
    beq +
    lda #$00                        ; any input: back to rest
    sta.l !canim
    sta.l !cidle
    sta.l !cidle+1
    bra .pose
+   lda.l !canim
    bne .anim
    rep #$20
    lda.l !cidle
    inc a
    sta.l !cidle
    cmp.w #!CURIDLE
    sep #$20
    bcc .pose
    jsr rand                        ; a look around
    lsr a
    lsr a
    and #$07
    cmp #$07
    bcc +
    lda #$03
+   sta.l !ceye
    jsr rand
    and #$03
    inc a
.start:
    sta.l !canim
    lda #$00
    sta.l !ct
.anim:
    lda.l !canim
    cmp.b #!CURCONFIRM+1
    bcs .pose
    lda.l !ct
    cmp.b #!CURANIM
    bcc .pose
    lda #$00                        ; ---- the animation ended
    sta.l !cidle
    sta.l !cidle+1
    lda.l !canim
    cmp.b #!CURCONFIRM
    bne +
    lda.b #!CURCONFIRM+1
    bra ++
+   lda #$00
++  sta.l !canim
.pose:
    lda.l !canim                    ; ---- A = pose: face * heads + head
    bne +
    lda #$00
    bra .show
+   cmp.b #!CURCONFIRM+1
    bcc +
    lda.b #!CUREYE*!CURHEADS
    bra .show
+   dec a                           ; sequence * length + step
    sta.l !t0
    asl a
    asl a
    asl a
    clc
    adc.l !t0
    adc.l !t0
    adc.l !t0
    sta.l !t0
    lda.l !ct
    tax
    inc a
    sta.l !ct
    lda.l !CURSTEPS,x
    clc
    adc.l !t0
    tax
    lda.l !CURSEQS,x
    sta.l !t0
    lda.l !ceye
    asl a
    asl a
    asl a
    clc
    adc.l !ceye
    clc
    adc.l !t0
.show:
    tay
    lda $08C0                       ; ---- no SB5 hop: an accepted item starts
    cmp #$E0                        ; the cursor object's hop script ($C0:C99D,
    bcs +                           ; frames 2/4/6, Y +1/-5, ~64 frames), which
    lda $08C1                       ; outlives the shortened wait into the next
    and #$06                        ; menu. At rest (frame 0) the Y offset from
    bne .hop                        ; the menu Y $1034 is measured; while it
    lda $1034                       ; hops the Y is held there.
    sec
    sbc $08C0
    sta.l !cy
    bra +
.hop:
    lda $1034
    sec
    sbc.l !cy
    sta $08C0                       ; OAM shadow and OAM (whichever the NMI
    stz $2102                       ; sends first)
    stz $2103
    lda $08BF
    sta $2104
    lda $08C0
    sta $2104
+   lda $08C1                       ; the sprite's frame
    and #$06
    tax
    lda $08C0                       ; the sprite has just appeared: the game
    cmp #$E0                        ; loaded its own tiles and colors for it
    bcc +
    lda #$00
    sta.l !cvis
    bra ++
+   lda.l !cvis
    bne ++
    lda #$01
    sta.l !cvis
    lda #$01
    sta.l !cforce
++  lda.l !cforce
    beq +
    dec a
    sta.l !cforce
    lda #$01                        ; (tiles only: the colors are already right,
    sta.l !t0                       ; and this NMI also carries the game's queue)
    bra .send
+   rep #$20                        ; the game's CGRAM copy holds other colors:
    lda.l $7E2A12                   ; only the colors are sent (the game's VRAM
    cmp.l !CURPAL                   ; queue is busy with its cursor right now)
    sep #$20
    beq +
    phx
    jsr curpal
    plx
+   lda.l !cref
    inc a
    sta.l !cref
    and #$1F
    beq +                           ; rewritten every 32 frames (the game may
    txa                             ; load its own cursor again)
    cmp.l !ctile
    bne +
    tya
    cmp.l !cpose
    bne +
    rts
+   lda #$00
    sta.l !t0
.send:
    txa
    sta.l !ctile
    tya
    sta.l !cpose
    rep #$20
    and #$00FF
    xba
    lsr a                           ; * 128
    clc
    adc.w #!CURPOSES
    sta $4302
    lda.l !ctile
    and #$0006
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$6000                      ; OBJ tiles t, t+1
    sta.l !va
    sta $2116
    lda #$0040
    sta $4305
    sep #$20
    lda.b #!CURPOSES>>16
    sta $4304
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    lda #$01
    sta $420B
    rep #$20
    lda.l !va
    clc
    adc #$0100                      ; OBJ tiles t+$10, t+$11
    sta $2116
    lda #$0040
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    lda.l !t0
    beq curpal
    rts

; The cursor's colors: to CGRAM 129-143 and to the game's CGRAM copy
; ($7E:2910, sent whole when dirty). M/X 8-bit; X is used.
curpal:
    ldx #$1D
-   lda.l !CURPAL,x
    sta.l $7E2A12,x
    dex
    bpl -
    rep #$20
    lda.w #!CURPAL
    sta $4302
    lda #$001E
    sta $4305
    sep #$20
    lda.b #!CURPAL>>16
    sta $4304
    lda #$81
    sta $2121
    stz $4300
    lda #$22
    sta $4301
    lda #$01
    sta $420B
    rts

; The logo is in place: the menu text appears, the title's script goes on.
landed:
    lda #$01
    sta.l !done
    sta.l !seen
    lda #$17
    sta.l !tm
    rep #$20
    lda.w #!REST
    sta.l !bg1v
    sta.l !bg2v
    sep #$20
    rts

; One service of player !cs (M/X 8-bit). A player shows a character's
; alternate pose as a list of steps (tables: features/title_anim.py): it sends
; the next step's tiles (to the scratch area the step uses) while the current
; step is shown, then its cells when the current step's time is over. A pose
; in several steps (!ALT+1 = 1) only starts in player 0, with player 1 free,
; and keeps both areas (!smul) until it ends.
alt_serve:
    lda.l !cs
    tax
    lda.l !sst,x
    bne +
    brl .free
+   cmp #$04
    bne +
    brl .last
+   cmp #$03
    beq .switch
    cmp #$02
    beq .tiles2
    lda #$02                        ; ---- 1: the pending step's first tile job
    sta.l !sst,x
    rep #$30
    jsr sptr
    lda.l !ALT+0,x
    bra .tjob
.tiles2:                            ; ---- 2: its second tile job
    lda #$03
    sta.l !sst,x
    rep #$30
    jsr sptr
    lda.l !ALT+2,x
.tjob:
    cmp #$FFFF
    beq +
    jsr dojob
    sep #$30
    rts
+   sep #$30                        ; no such job: the next state now
    brl alt_serve
.switch:                            ; ---- 3: tiles sent; its cells when the
    lda.l !stm,x                    ; step on screen is over
    beq +
    rts
+   rep #$30
    jsr sptr
    phx
    phy
    lda.l !ALT+4,x
    jsr dojob
    ply
    plx
    sep #$20
    lda.l !ALT+14,x                 ; the next step's frames (0: this was the last)
    sta.l !t0
    lda.l !ALT+6,x
    pha
    rep #$20
    txa
    clc
    adc #$0008
    tyx
    sta.l !sof,x
    sep #$30
    lda.l !cs
    tax
    pla
    sta.l !stm,x
    lda.l !t0
    beq +
    lda #$01                        ; more steps: load the next one
    sta.l !sst,x
    rts
+   lda #$04
    sta.l !sst,x
    rts
.last:                              ; ---- 4: the last step; when its time is
    lda.l !stm,x                    ; over, the standing pose's cells again
    beq +
    rts
+   lda #$00
    sta.l !sst,x
    cpx #$00
    bne +
    sta.l !smul
+   lda.l !sch,x
    tay
    tax
    lda.l bits,x
    eor #$FF
    and.l !amask
    sta.l !amask
    jsr rand
    and #$7F                        ; !ALTMIN .. !ALTMIN + 127 frames
    clc
    adc.b #!ALTMIN
    sta.l !ctm,x
    tya
    asl a
    asl a
    asl a
    tax
    rep #$20
    lda.l !ALT+2,x
    jsr dojob
    sep #$20
    rts
.free:
    ldy.b #!NCHAR                     ; a character whose time has come and whose
-   lda.l !rot                      ; box touches none of the poses shown
    inc a
    cmp.b #!NCHAR
    bcc +
    lda #$00
+   sta.l !rot
    tax
    lda.l !ctm,x
    bne .no
    txa
    asl a
    asl a
    asl a
    tax
    lda.l !ALT+0,x
    and.l !amask
    bne .no
    lda.l !ALT+1,x                  ; in several steps: player 0, player 1 free
    beq .start
    lda.l !cs
    bne .no
    lda.l !sst+1
    beq .start
.no:
    dey
    bne -
    rts
.start:                             ; X = !rot * 8
    lda.l !ALT+1,x
    pha
    lda.l !rot
    tax
    lda.l bits,x
    ora.l !amask
    sta.l !amask
    lda.l !cs
    tax
    pla
    beq +
    sta.l !smul
+   lda.l !rot
    sta.l !sch,x
    lda #$00
    sta.l !stm,x
    lda #$01
    sta.l !sst,x
    lda.l !rot                      ; its step list for this player's area
    asl a
    asl a
    asl a
    sta.l !t0
    txa
    asl a
    clc
    adc.l !t0
    tax
    rep #$30
    lda.l !ALT+4,x
    pha
    jsr sptr
    pla
    tyx
    sta.l !sof,x
    sep #$30
    brl alt_serve                   ; its first tile job now

; (M/X 16-bit) X = the step record of player !cs, Y = !cs * 2.
sptr:
    lda.l !cs
    and #$00FF
    asl a
    tay
    tax
    lda.l !sof,x
    tax
    rts

print "SYM end ", hex(pc())
print "SYM s_load ", hex(s_load)
print "SYM s_wait ", hex(s_wait)
print "SYM s_accept ", hex(s_accept)
print "SYM title_op ", hex(title_op)
print "SYM title_nmi ", hex(title_nmi)
