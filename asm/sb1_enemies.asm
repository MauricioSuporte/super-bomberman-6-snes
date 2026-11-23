; SB1 enemies with their own routines (tools/sb6/features/sb1_enemies.py). SB1 3-6's chameleons (1-3)
; are asm/chameleon.asm.

asar 1.90
hirom
org !ORG

macro c3(addr)            ; JSR to a bank $C3 routine ending in RTS: it returns to the RTL at $C3:4B7A
    phk
    per ?back-1
    pea $4B79
    jml <addr>
?back:
endmacro

; ---------------------------------------------------------------------------
; World 1's 1-7 boss = SB1 2-8's clown mask, run by SB1's own rules and tables
; (SB1 $C7:3CDA-$C7:4129, docs/ROM_MAP.md "SB1 2-8's clown"). SB1 coordinates
; -> SB5's: x - 16, y as they are (the face's center = SB1 obj y - 32).
;   intro: players held (world1's intro_pads reads !CHOLD) and turned up, !CWAIT frames, the field
;     darkens step by step (SB1 subtracts its BG2 on the subscreen: field - (20, 22, 10), with a hole
;     around the face; here the fixed color on BG1 / BG3 / the backdrop outside an HDMA window, the
;     players' OBJ palettes dimmed alike), 128 frames, the face appears in its light (SB1 animation
;     $3A58, the eye glint), lights back on.
;   fight (SB1 $3DBC): it accelerates toward the nearest live player, 1/256 px a frame per frame on
;     each axis up to 1/4 px a frame (doubled while it cries, state $0C), over everything, the center
;     kept in x 47-192, y 48-160; a flame on one of the 5 x 5 cells around its center is a hit (!CHP
;     hits; SB1: 18), a player within 16 px of its center dies. Hit (SB1 $3EF1): 96 frames stunned (no
;     move, no flames; it blinks with its white silhouette), 8 shots out in 8 directions (SB1 $C7:412A:
;     15/16 px a frame straight, 10/16 diagonal; a player within 8 px dies; gone off the screen), and
;     its expression goes on by SB1's state tables ($C7:425C animation, next, after a hit). Below half
;     its hits it keeps SB1's red flash colors.
;   death (SB1 $3FF8): players held, 385 frames of white flashes with an explosion every 4 frames 0-63
;     px around it (SB1 $C6:31D7), then it sinks into the floor ($3BF9, every frame shown); the body is
;     not killed (no SB5 enemy death, no door): SB5's stage end as after 1-6 (clown_win: win pose,
;     music) and !CEND frames later the next stage !CNEXT.
; Drawn on BG2 below the HUD (SB5's stage IRQ $C0:F08D sets BG2's map $0369
; at line 21, TM $030F and the scroll $031B / $0321 at line 23): two buffers,
; tiles $340-$37F (VRAM $3400, BG1's unused lower screen) + map $4800 and
; tiles $380-$3BF (VRAM $3800: the upper screen of BG2's HUD map, whose rows
; above line 21 come from its lower screen $3C00, the HUD's) + map $4C00; a new picture goes into the buffer not shown through SB5's VRAM
; queue ($7E:8000, write $0357 / read $0355) and is shown once the NMI sent
; it (an alternation between two pictures costs nothing after that). Picture
; table at !CTAB (features/sb1_enemies.py clown_bg): per picture its tiles
; (offset, bytes) and its 16 x 15 map (word = tile + 1 | palette | priority |
; flips, 0 blank); !CPAL: BG palettes !CPAL1 / !CPAL2 colors 1-15, normal
; then red. Its body is an enemy (type !CLOWN_TYPE) with an empty picture
; placed on the center (SB5's cell bit, its death and the stage's exit); its
; OBJ tiles and palette are the shots' and explosions', drawn by clown_oam
; (OAM slots 104-127, after SB5's builder). clown_start (JSL, world1's op 5)
; sets it up and starts clown_task (BG2 on / off, stage over).
!CB    = $7FE000
!CPH   = !CB+$00          ; phase: 0 wait, 1 dark, 2 appears, 3 fight, 4 hit, 5 dying, 6 sinking, 7 sunk,
                          ; 9 gone (clown_task: the stage's end)
!CTIM  = !CB+$01          ; frames left (word)
!CST   = !CB+$03          ; SB1 state ($31: 0, 4 ... $34)
!CAP   = !CB+$04          ; animation entry (word, this bank)
!CAF   = !CB+$06          ; its frames left
!CWANT = !CB+$07          ; picture to show (0-22)
!CHITS = !CB+$08          ; hits left
!CXP   = !CB+$0A          ; center x, y (words: pixel . 1/256)
!CYP   = !CB+$0C
!CVX   = !CB+$0E          ; speeds (1/256 px a frame)
!CVY   = !CB+$10
!CSHOW = !CB+$12          ; BG2 buffer shown (0 / 1)
!CPIC  = !CB+$13          ; picture in buffer 0 / 1 ($FF none)
!CPEND = !CB+$15          ; buffer + 1 being sent (0 none)
!CQEND = !CB+$16          ; the queue's write pointer after its entries (word)
!CFL   = !CB+$18          ; colors in CGRAM: 0 normal, 1 red
!CHOLD = !CB+$19          ; $A5: players' pads held (asm/world1.asm intro_pads)
!CVIS  = !CB+$1A          ; BG2 on
!CKILL = !CB+$1B          ; $A5: clown_hit lets SB5 kill the body
!CTB   = !CB+$1C          ; the body's OBJ tile base ($073F, word)
!CSL   = !CB+$1E          ; its palette slot ($06DF)
!CON   = !CB+$1F          ; $A5: clown_oam draws
!CT0   = !CB+$20          ; scratch words
!CT1   = !CB+$22
!CT2   = !CB+$24
!CT3   = !CB+$26
!CKM   = !CB+$28          ; seats to kill this frame (bits)
!CRAD  = !CB+$29          ; touch: distance, x, y
!CTX   = !CB+$2A
!CTY   = !CB+$2B
!CEXT  = !CB+$2C          ; dying: frames (explosion every 4, sound every 16)
!CACT  = !CB+$2D          ; the body's actor
!CQS   = !CB+$30          ; queue: source, VRAM, bytes left, entry size (words)
!CQV   = !CB+$32
!CQL   = !CB+$34
!CQN   = !CB+$36
!SHX   = !CB+$40          ; 8 shots: x, y (words, pixel . 1/256), speeds
!SHY   = !CB+$50
!SHVX  = !CB+$60
!SHVY  = !CB+$70
!SHA   = !CB+$80          ; 0 none, else animation step + 1 (1-8)
!EXX   = !CB+$88          ; 4 explosions: x, y (words), age (0 none, 1-13)
!EXY   = !CB+$90
!EXA   = !CB+$98
!OX    = !CB+$A0          ; clown_oam: screen x, y, field x, y, tile, flips, OAM offset, name, index
!OY    = !CB+$A2
!OFX   = !CB+$A4
!OFY   = !CB+$A6
!OTL   = !CB+$A8
!OFL   = !CB+$AA
!OSL   = !CB+$AC
!ONM   = !CB+$AE
!OI    = !CB+$B0
!CWH   = !CB+$2E          ; 1: the white silhouette of the picture is shown (blink after a hit)
!CSHW  = !CB+$2F          ; picture pic_tick shows (!CWANT or its white one)
!CFUP  = !CB+$38          ; seats turned up by world1's start_up (!CLOWNHOLD + $1F there)
!CDL   = !CB+$39          ; darkness: level now, level wanted (0-!CDMAX), 1 = on
!CDT   = !CB+$3A
!CDON  = !CB+$3B
!CDSV  = !CB+$B2          ; saved $0308, $0313, $0314, $0315-$0317 (6 bytes)
!CSAVE = $7FE100          ; CGRAM OBJ palettes while dark (256 bytes)
!CHT   = $7FE200          ; HDMA table of window 1 (the light around the clown)
!CDIM  = $7FE400          ; the OBJ palettes as dimmed (256 bytes): a color SB5 rewrote is taken as new
!CWAIT = 180              ; frames from the stage's start to the dark (SB1: 224 from its creation)
!CHP   = 8                ; hits (SB1: 18)
!CEND  = 450              ; frames from the end of the sinking to the next stage (SB5's boss victory: 433)
!CDMAX = 24               ; darkness steps (SB1: about 24 frames down, 8 up)
!CRX   = 44               ; the light: half width / height around the face's center
!CRY   = 52
!CHUDL = 24               ; screen lines of the HUD (no darkness; features/hud.py: HUD lines 0-22 on lines 1-23)
!CTABL = 8                ; then lines of the HUD's lives tab: window = its columns (hud.TAB_X, TAB_W)
!CTOP  = (!CHUDL+!CTABL)    ; first line the field may be dark
!CBUF0 = $3400            ; VRAM: buffer tiles, maps (BG2SC values), first tile
!CBUF1 = $3800
!CSC0  = $48
!CSC1  = $4C
!CHUDSC = $3A

clown_start:
    php
    rep #$30
    lda.w #$0000
    ldx.w #$00FE
-   sta.l !CB,x
    dex
    dex
    bpl -
    sep #$30
    lda #$FF
    sta.l !CPIC
    sta.l !CPIC+1
    lda #!CHP
    sta.l !CHITS
    lda #!CWAIT
    sta.l !CTIM
    lda #$78                    ; SB1's start: obj ($88, $5E)
    sta.l !CXP+1
    lda #$3E
    sta.l !CYP+1
    lda #$A5
    sta.l !CHOLD
    sta.l !CON
    lda #!CSC0
    sta.l $7E0369
    rep #$30
    ldx.w #$4800                ; both maps blank
    ldy.w #$1000
    jsr qzero
    sep #$30
    jsl $C020A1
    dl clown_task
    db $60                      ; skipped ($C020A1 returns past the dl)
    plp
    rtl

clown_task:
    php
    sep #$30
    lda.l $7E1031
    cmp #!CSTAGE
    beq +
    jsl clown_stop
    jsl $C021CE                 ; stage over: end the task
    plp
    rtl
+   lda.l !CPH
    cmp #$09
    bne .shown
    rep #$20                    ; the clown is gone: as SB1 (128 frames, then the next stage); SB5's clear
    lda.l !CTIM                 ; task does not run in this boss stage ($C5:3A2D: flag 6 of $7E:2900)
    dec a
    sta.l !CTIM
    sep #$20
    bne .shown
    lda.l $7E1D1E               ; what op 0F does ($C2:0C20; as world1's exit_task)
    and #$04
    bne .shown
    lda #!CNEXT
    sta.l $7E1031
    lda #$04
    sta.l $7E1D1E
.shown:
    lda.l !CVIS
    beq .hide
    lda.l $7E030F
    ora #$02
    bra +
.hide:
    lda.l $7E030F
    and #$FD
+   sta.l $7E030F
    plp
    rtl

; stage over: BG2 back to the HUD's background
clown_stop:
    php
    sep #$20
    jsr dark_off
    sep #$20
    lda #!CHUDSC                ; BG2's HUD map back; BG2 stays off on the field while the stage fades
    sta.l $7E0369               ; out (its upper screen $3800 holds buffer 1's tiles: garbage on the
    lda #$00                    ; screen); the next stage sets TM ($030F) itself
    sta.l !CON
    sta.l !CHOLD
    sta.l !CKILL
    plp
    rtl

; flame test of the body (world1's knight_hit, X = actor, Y = its cell): only when the clown is over
clown_hit:
    lda.l !CKILL
    cmp #$A5
    beq +
    clc
    rtl
+   sec
    rtl

; SB5's boss music (id $0F: set $35 + song $0E) through the sound API, as SB5's scripts load it (op 42,
; its hooks): $C5:02AB's sound $22 is then its command 3, SB5's boss victory ("major victory"); the
; stage's SB1 list has only ZONE1's jingles (no room for this one's 15 KB of samples). ~1 s of upload, at
; the stage's end (nothing moves); its command 1 is replaced by the victory a frame later. M/X 8-bit.
victory_load:
    php
    phb
    phd
    pea $0000
    pld
    sep #$30
    phx
    phy
    lda #$00
    xba
    lda #$0F
    jsl $C00CED
    sep #$30
    ply
    plx
    pld
    plb
    plp
    rts

; ---- the body's actor routine (X = actor, Y = object, M/X 8-bit, DB = $80) ----
clown:
    lda $073F,y
    sta.l !CTB
    lda $0740,y
    sta.l !CTB+1
    lda $06DF,y
    sta.l !CSL
    txa
    sta.l !CACT
    jsr dark_tick
    lda.l !CPH
    cmp #$08
    bcc +
    rtl                         ; gone: the body stays, invisible and harmless, until the stage ends
+   lda #$00
    sta.l !CKM
    lda.l !CPH
    asl a
    tax
    jsr (.phases,x)
    jsr shots
    jsr booms
    lda.l !CKM
    beq +
    jsr killseats
+   jsr place
    jsr pic_tick
    rtl
.phases:
    dw ph_wait, ph_dark, ph_appear, ph_fight, ph_hit, ph_dying, ph_sink, ph_sunk

; the end (the clown sunk): no SB5 death for the body (its sound, its burst; SB5's clear and the door
; never come: $1D50 keeps it); SB5's stage end as after 1-6's Golden Bomber (players' win pose, win
; music), the next stage !CEND frames later (clown_task)
clown_win:
    sep #$30
    jml $C502AB                 ; sets $1D1E bit 0, type 0A script, sound $22; ends this task

ph_wait:
    jsr tick
    bne +
    jsr dark_on
    lda #128
    sta.l !CTIM
    lda #$01
    sta.l !CPH
+   rts

ph_dark:
    jsr tick
    bne +
    lda #$01                    ; the light around the face (SB1: a hole in its BG2 darkness)
    jsr hdma_build
    lda #$01
    sta.l !CVIS
    lda #$04
    jsr anim_set
    lda #$02
    sta.l !CPH
+   rts

ph_appear:
    jsr anim_step
    bcc +
    lda #$00                    ; lights back on, step by step (dark_tick)
    sta.l !CDT
    lda #$00
    sta.l !CHOLD
    lda #$24
    jsr anim_set
    lda #$03
    sta.l !CPH
+   rts

ph_fight:
    jsr chase
    jsr flames
    bcs .hit
    jsr touch_boss
    jsr anim_step
    bcc .rts
    lda.l !CST
    cmp #$0C
    bne +
    jsr stop
+   lda.l !CST
    lsr a
    lsr a
    tax
    lda.l st_next,x
    jsr anim_set
.rts:
    rts
.hit:
    lda.l !CHITS
    dec a
    sta.l !CHITS
    beq .death
    jsr hp_pal
    lda #$60
    sta.l !CTIM
    lda.l !CST
    lsr a
    lsr a
    tax
    lda.l st_hit,x
    jsr anim_set
    jsr spawn_shots
    lda #$04
    sta.l !CPH
    rts
.death:
    jsr hp_pal
    lda #$A5
    sta.l !CHOLD
    rep #$20
    lda.w #385
    sta.l !CTIM
    sep #$20
    lda #$00
    sta.l !CEXT
    lda #$20
    jsr anim_set
    lda #$05
    sta.l !CPH
    rts

ph_hit:
    lda.l !CTIM                 ; its white silhouette 4 frames in 8 (SB1 flashed red: the owner wants white)
    lsr a
    lsr a
    and #$01
    sta.l !CWH
    jsr touch_boss
    jsr anim_step
    jsr tick
    bne +
    jsr stop
    lda #$00
    sta.l !CWH
    lda.l !CST
    lsr a
    lsr a
    tax
    lda.l st_next,x
    jsr anim_set
    lda #$03
    sta.l !CPH
+   rts

ph_dying:
    jsr tick
    beq .sink
    jsr anim_step
    lda.l !CEXT
    inc a
    sta.l !CEXT
    and #$03
    bne +
    jsr spawn_boom
+   lda.l !CEXT
    and #$0F
    bne +
    jsr boom_sound
+   rts
.sink:
    lda #$34
    jsr anim_set
    jsr boom_sound
    lda #$06
    sta.l !CPH
    rts

ph_sink:
    lda.l !CPEND                ; each frame of the sinking stays until it was on the screen (a picture
    bne +                       ; takes a few frames through the VRAM queue: the last ones were skipped)
    lda.l !CSHOW
    tax
    lda.l !CPIC,x
    cmp.l !CWANT
    bne +
    jsr anim_step
    bcc +
    lda #$00
    sta.l !CVIS
    lda #$10
    sta.l !CTIM
    lda #$07
    sta.l !CPH
+   rts

ph_sunk:
    jsr tick
    bne +
    lda #$00                    ; nothing left on the screen
    ldx #$07
-   sta.l !SHA,x
    dex
    bpl -
    ldx #$03
-   sta.l !EXA,x
    dex
    bpl -
    sta.l !CON
    sta.l !CHOLD
    rep #$20                    ; a word: !CEND is over 255
    lda.w #!CEND
    sta.l !CTIM
    sep #$20
    lda #$09
    sta.l !CPH
    jsr victory_load            ; here, not in clown_win: an upload inside a task crashed (its stack)
    jsl $C020A1                 ; SB5's stage end in a task of its own
    dl clown_win
    db $60
+   rts

; !CTIM - 1 (word); Z = it reached 0 (M 8-bit)
tick:
    rep #$20
    lda.l !CTIM
    dec a
    sta.l !CTIM
    sep #$20
    rts

stop:
    rep #$20
    lda.w #$0000
    sta.l !CVX
    sta.l !CVY
    sep #$20
    rts

boom_sound:
    phx
    phy
    lda #$02                    ; group 2 id $0C: SB5's explosion
    xba
    lda #$0C
    jsl $C00CED
    sep #$30
    ply
    plx
    rts

; ---- SB1's expressions: state A ($31) -> its animation ----
anim_set:
    sta.l !CST
    lsr a
    tax
    rep #$20
    lda.l st_anim,x
    sta.l !CAP
    sep #$20
anim_load:
    phb
    phk
    plb
    rep #$30
    lda.l !CAP
    tax
    sep #$20
    lda.w $0000,x
    sta.l !CWANT
    lda.w $0001,x
    sta.l !CAF
    sep #$30
    plb
    rts

; one frame of the animation: C = it ended (then it starts again)
anim_step:
    lda.l !CAF
    dec a
    sta.l !CAF
    bne .go
    rep #$20
    lda.l !CAP
    clc
    adc.w #$0002
    sta.l !CAP
    sep #$20
    jsr anim_load
    lda.l !CWANT
    cmp #$FF
    bne .go
    lda.l !CST
    jsr anim_set
    sec
    rts
.go:
    clc
    rts

; SB1's tables ($C7:425C animation, $C7:425E next, $C7:428E after a hit), per state / 4; pictures: 0 N,
; 1 O (mouth open), 2 I (eye glint), 3 D, 4 E, 5 F (crying), 6 G, 7-10 white N, D, E, G, 11-22 sinking
st_anim:
    dw a_n, a_intro, a_def, a_f, a_g, a_nw, a_dw, a_ew, a_gw, a_no, a_n, a_n, a_n, a_sink
st_next:
    db $00, $04, $0C, $24, $00, $08, $08, $08, $10, $24, $14, $18, $00, $34
st_hit:
    db $00, $04, $2C, $2C, $00, $08, $08, $08, $10, $28, $14, $18, $00, $34
a_n:
    db 0, 255, $FF
a_intro:
    db 0, 16, 0, 6, 2, 6, 0, 4, 2, 4, 0, 4, 2, 4, 2, 6, 0, 6, 2, 10, 0, 44, $FF
a_def:
    db 3, 10, 4, 7, 5, 13, $FF
a_f:
    db 5, 128, $FF
a_g:
    db 6, 255, $FF
a_nw:
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db 0, 3, 7, 3
    db $FF
a_dw:
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db 3, 3, 8, 3
    db $FF
a_ew:
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db 4, 3, 9, 3
    db $FF
a_gw:
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db 6, 3, 10, 3
    db $FF
a_no:
    db 0, 28, 1, 22, $FF
a_sink:
    db 6, 13, 11, 4, 12, 4, 13, 3, 14, 3, 15, 2, 16, 2, 17, 2, 18, 2, 19, 2, 20, 2, 21, 2, 22, 1, $FF

; ---- SB1 $3DBC: toward the nearest live player ----
chase:
    jsr target
    cpy #$FF
    bne +
    rts
+   lda $182A,y
    clc
    adc #$08
    sta.l !CT0
    lda $1872,y
    clc
    adc #$08
    sta.l !CT0+1
    ldx #$00                    ; x: + when the player's x >= its own
    lda.l !CT0
    cmp.l !CXP+1
    jsr axis
    ldx #$02                    ; y: + when its own y < the player's
    lda.l !CYP+1
    cmp.l !CT0+1
    rol a
    eor #$01
    lsr a
    ; (falls through)

; one axis (X = 0 x, 2 y; C = toward +): speed +- 1 a frame up to +- $40 (doubled in state $0C), position
; kept in SB1's box
axis:
    rep #$20
    lda.w #$0001
    bcs +
    lda.w #$FFFF
+   sta.l !CT1
    bmi +
    lda.w #$0040
    bra ++
+   lda.w #$FFC0
++  sta.l !CT2
    sep #$20
    lda.l !CST
    cmp #$0C
    rep #$20
    bne +
    lda.l !CT1
    asl a
    sta.l !CT1
    lda.l !CT2
    asl a
    sta.l !CT2
+   lda.l !CVX,x
    cmp.l !CT2
    beq +
    clc
    adc.l !CT1
    sta.l !CVX,x
+   clc
    adc.l !CXP,x
    cmp.l .lo,x
    bcs +
    lda.l .lo,x
    bra ++
+   cmp.l .hi,x
    bcc ++
    lda.l .hi,x
++  sta.l !CXP,x
    sep #$20
    rts
.lo:
    dw $2F00, $3000
.hi:
    dw $C000, $A000

; nearest live player (seats 0-3) -> Y, $FF = none
target:
    ldy #$FF
    lda #$FF
    sta.l !CT3+1
    ldx #$00
-   jsr alive
    bcc .next
    lda $182A,x
    clc
    adc #$08
    sec
    sbc.l !CXP+1
    bcs +
    eor #$FF
    inc a
+   sta.l !CT3
    lda $1872,x
    clc
    adc #$08
    sec
    sbc.l !CYP+1
    bcs +
    eor #$FF
    inc a
+   clc
    adc.l !CT3
    bcs .next
    cmp.l !CT3+1
    bcs .next
    sta.l !CT3+1
    txy
.next:
    inx
    cpx #$04
    bcc -
    rts

; seat X alive -> C (keeps X)
alive:
    lda $17FA,x                 ; a bomber object
    cmp #$60
    bcs .no
    phy
    tay
    lda $04FF,y
    ply
    cmp #$10
    bcc .no
    cmp #$1A
    bcs .no
    sec
    rts
.no:
    clc
    rts

; SB1 $C6:370B with $2020: a flame on a cell within 32 px of the center (5 x 5 cells) -> C
flames:
    lda.l !CXP+1
    sec
    sbc #$20
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !CT0
    lda.l !CXP+1
    clc
    adc #$20
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !CT0+1
    lda.l !CYP+1
    sec
    sbc #$20
    and #$F0
    sta.l !CT1
    lda.l !CYP+1
    clc
    adc #$20
    and #$F0
    sta.l !CT1+1
.row:
    lda.l !CT0
    sta.l !CT2
.col:
    lda.l !CT1
    ora.l !CT2
    tax
    lda $1052,x
    and #$04
    bne .hit
    lda.l !CT2
    cmp.l !CT0+1
    beq .down
    inc a
    sta.l !CT2
    bra .col
.down:
    lda.l !CT1
    cmp.l !CT1+1
    beq .none
    clc
    adc #$10
    sta.l !CT1
    bra .row
.none:
    clc
    rts
.hit:
    sec
    rts

; SB1 $C6:353D with $1010: a player within 16 px of the center
touch_boss:
    lda.l !CXP+1
    sta.l !CTX
    lda.l !CYP+1
    sta.l !CTY
    lda #$10
    sta.l !CRAD
    ; (falls through)

; live seats whose center is closer than !CRAD on both axes to (!CTX, !CTY) -> !CKM
touch:
    ldx #$00
-   jsr alive
    bcc .next
    lda $182A,x
    clc
    adc #$08
    sec
    sbc.l !CTX
    bcs +
    eor #$FF
    inc a
+   cmp.l !CRAD
    bcs .next
    lda $1872,x
    clc
    adc #$08
    sec
    sbc.l !CTY
    bcs +
    eor #$FF
    inc a
+   cmp.l !CRAD
    bcs .next
    lda.l !CKM
    ora.l bits,x
    sta.l !CKM
.next:
    inx
    cpx #$04
    bcc -
    rts
bits:
    db $01, $02, $04, $08

; SB5's contact test $C3:47C9 (seat distances in co-op's $0110 arrays: < 8 px kills) for the seats in !CKM
killseats:
    ldx #$03
-   lda.l !CKM
    and.l bits,x
    beq +
    lda #$00
    bra ++
+   lda #$FF
++  sta $0110,x
    sta $0114,x
    sta $0118,x
    sta $011C,x
    dex
    bpl -
    lda.l !CACT
    tax
    ldy $17FA,x
    %c3($C347C9)
    rts

; the body on the center (SB5's position, cell bit), BG2 scrolled so that the picture's (!COX, !COY) is there
place:
    lda.l !CACT
    tax
    lda.l !CXP+1
    sec
    sbc #$08
    sta $182A,x
    lda.l !CYP+1
    sec
    sbc #$08
    sta $1872,x
    lda.l !CYP+1
    and #$F0
    sta.l !CT0
    lda.l !CXP+1
    lsr a
    lsr a
    lsr a
    lsr a
    ora.l !CT0
    sta $16AA,x
    lda #$02
    sta $1632,x
    ldy $17FA,x
    %c3($C34CFC)                ; sprite position, the cell's enemy bit
    rep #$20
    lda.l !CXP
    xba
    and.w #$00FF
    sec
    sbc.w #!COX
    eor.w #$FFFF
    inc a
    clc
    adc $0319                   ; BG1 H scroll
    sta $031B
    lda.l !CYP
    xba
    and.w #$00FF
    sec
    sbc.w #!COY
    eor.w #$FFFF
    inc a
    clc
    adc $031F                   ; BG1 V scroll
    sta $0321
    sep #$30
    rts

; ---- the pictures ----
; the wanted picture: shown from the buffer holding it, else sent into the other one (shown once sent)
pic_tick:
    lda.l !CWANT
    sta.l !CSHW
    lda.l !CWH
    beq +
    lda.l !CWANT
    cmp #!CPICS
    bcs +
    tax
    lda.l white_of,x
    sta.l !CSHW
+   lda.l !CPEND
    beq .idle
    rep #$20
    lda.l $7E0357               ; bytes still queued
    sec
    sbc.l $7E0355
    and.w #$3FFF
    sta.l !CT0
    lda.l !CQEND
    sec
    sbc.l $7E0355
    and.w #$3FFF
    beq .sent
    cmp.l !CT0
    bcc .wait
    beq .wait
.sent:
    sep #$30
    lda.l !CPEND
    dec a
    tax
    lda #$00
    sta.l !CPEND
    lda.l !CSHW
    cmp.l !CPIC,x
    bne .idle
    txa
    sta.l !CSHOW
    jsr setsc
    rts
.wait:
    sep #$30
    rts
.idle:
    lda.l !CSHOW
    tax
    lda.l !CSHW
    cmp #!CPICS
    bcs .rts
    cmp.l !CPIC,x
    beq .rts
    txa
    eor #$01
    tax
    lda.l !CSHW
    cmp.l !CPIC,x
    bne .load
    txa
    sta.l !CSHOW
    jsr setsc
.rts:
    rts
.load:
    sta.l !CPIC,x
    txa
    inc a
    sta.l !CPEND
    dec a
    sta.l !CT3
    jsr loadpic
    rts

setsc:
    lda.l !CSHOW
    beq +
    lda #!CSC1
    bra ++
+   lda #!CSC0
++  sta.l $7E0369
    rts

; picture !CSHW into buffer !CT3 (tiles, then the map with that buffer's tile numbers)
loadpic:
    rep #$30
    lda.l !CSHW
    and.w #$00FF
    sta.l !CT0
    asl a
    clc
    adc.l !CT0
    asl a
    tax
    lda.l !CTAB+4,x             ; map
    pha
    lda.l !CTAB+2,x             ; bytes
    tay
    lda.l !CT3
    and.w #$00FF
    beq +
    lda.l !CTAB,x
    ldx.w #!CBUF1
    jsr cqueue
    lda.w #!CBUF1/16-1
    sta.l !CT0
    lda.w #$4C00
    bra ++
+   lda.l !CTAB,x
    ldx.w #!CBUF0
    jsr cqueue
    lda.w #!CBUF0/16-1
    sta.l !CT0
    lda.w #$4800
++  sta.l !CQV
    pla
    sta.l !CQS
    jsr qmap
    lda.l $7E0357
    sta.l !CQEND
    sep #$30
    rts

; queue Y bytes from bank !CBANK offset A to VRAM word X (entries of 256 bytes); M/X 16-bit
cqueue:
    sta.l !CQS
    txa
    sta.l !CQV
    tya
    sta.l !CQL
-   lda.l !CQL
    cmp.w #$0100
    bcc +
    lda.w #$0100
+   sta.l !CQN
    lda.l $7E0357
    tax
    lda.w #$0084
    sta.l $7E8000,x
    lda.l !CQN
    sta.l $7E8002,x
    lda.l !CQV
    sta.l $7E8004,x
    txa
    clc
    adc.w #$8006
    tay
    lda.l !CQS
    tax
    lda.l !CQN
    dec a
    phb
    db $54, $7E, !CBANK         ; MVN $7E <- !CBANK
    plb
    lda.l $7E0357
    clc
    adc.w #6
    adc.l !CQN
    and.w #$3FFF
    sta.l $7E0357
    lda.l !CQS
    clc
    adc.l !CQN
    sta.l !CQS
    lda.l !CQN
    lsr a
    clc
    adc.l !CQV
    sta.l !CQV
    lda.l !CQL
    sec
    sbc.l !CQN
    sta.l !CQL
    bne -
    rts

; queue Y zero bytes to VRAM word X (entries of 256 bytes); M/X 16-bit
qzero:
    txa
    sta.l !CQV
    tya
    sta.l !CQL
-   lda.l $7E0357
    tax
    lda.w #$0084
    sta.l $7E8000,x
    lda.w #$0100
    sta.l $7E8002,x
    lda.l !CQV
    sta.l $7E8004,x
    ldy.w #$0080
    lda.w #$0000
--  sta.l $7E8006,x
    inx
    inx
    dey
    bne --
    txa
    clc
    adc.w #6
    and.w #$3FFF
    sta.l $7E0357
    lda.l !CQV
    clc
    adc.w #$0080
    sta.l !CQV
    lda.l !CQL
    sec
    sbc.w #$0100
    sta.l !CQL
    bne -
    rts

; queue the 16 x 15 map at bank !CBANK offset !CQS to the 32 x 32 map at VRAM !CQV, nonzero words + !CT0
; (one entry of 32 words per row: the right half blank); M/X 16-bit
qmap:
    phb
    pea.w (!CBANK<<8)|!CBANK
    plb
    plb
    lda.w #15
    sta.l !CQL
.row:
    lda.l $7E0357
    tax
    lda.w #$0084
    sta.l $7E8000,x
    lda.w #64
    sta.l $7E8002,x
    lda.l !CQV
    sta.l $7E8004,x
    txa
    clc
    adc.w #6
    tax
    lda.l !CQS
    tay
    clc
    adc.w #32
    sta.l !CQN
-   lda.w $0000,y
    beq +
    clc
    adc.l !CT0
+   sta.l $7E8000,x
    inx
    inx
    iny
    iny
    tya
    cmp.l !CQN
    bne -
    sta.l !CQS
    ldy.w #16
    lda.w #$0000
-   sta.l $7E8000,x
    inx
    inx
    dey
    bne -
    txa
    and.w #$3FFF
    sta.l $7E0357
    lda.l !CQV
    clc
    adc.w #32
    sta.l !CQV
    lda.l !CQL
    dec a
    sta.l !CQL
    bne .row
    plb
    rts

; ---- colors ----
; A = 0 the clown's colors, 1 SB1's red flash (BG palettes !CPAL1 / !CPAL2, sent at the next NMI)
setpal:
    cmp.l !CFL
    beq .rts
    sta.l !CFL
    phb
    pea $7E7E
    plb
    plb
    rep #$30
    and.w #$00FF
    beq +
    lda.w #60
+   tax
    ldy.w #$0000
-   lda.l !CPAL,x
    sta.w $2910+32*!CPAL1+2,y
    lda.l !CPAL+30,x
    sta.w $2910+32*!CPAL2+2,y
    inx
    inx
    iny
    iny
    cpy.w #30
    bne -
    sep #$30
    lda #$01
    sta.w $0351                 ; whole CGRAM at the next NMI
    plb
.rts:
    rts

; below half its hits: SB1's red flash colors for good (setpal 1), else its own
hp_pal:
    lda.l !CHITS
    cmp #!CHP/2
    lda #$00
    bcs +
    inc a
+   jmp setpal

; the white silhouette of a picture (N D E G -> 7 8 9 10; the others have none)
white_of:
    db 7, 1, 2, 8, 9, 5, 10, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22

; ---- the dark (SB1: its BG2 subtracted on the subscreen, with a hole around the face) ----
; the fixed color subtracted from BG1, BG3 and the backdrop below the HUD (color math, CGWSEL / CGADSUB
; shadows), except inside window 1 (HDMA channel 7: the light around the face); OBJ palettes dimmed in
; CGRAM by the same amounts (color math on OBJ only reaches palettes 4-7). !CDL steps to !CDT: +1 a
; frame down, -3 up; back at 0 everything is put back.
dark_on:
    phb
    pea $7E7E
    plb
    plb
    rep #$30
    ldx.w #$00FE
-   lda.w $2A10,x
    sta.l !CSAVE,x
    sta.l !CDIM,x
    dex
    dex
    bpl -
    sep #$30
    lda.w $0308
    sta.l !CDSV
    lda.w $0313
    sta.l !CDSV+1
    lda.w $0314
    sta.l !CDSV+2
    lda.w $0315
    sta.l !CDSV+3
    lda.w $0316
    sta.l !CDSV+4
    lda.w $0317
    sta.l !CDSV+5
    plb
    lda #$00
    jsr hdma_build
    lda #$01                    ; HDMA 7: window 1 left / right per line
    sta.l $004370
    lda #$26
    sta.l $004371
    lda.b #!CHT
    sta.l $004372
    lda.b #!CHT>>8
    sta.l $004373
    lda.b #!CHT>>16
    sta.l $004374
    lda.l !CDSV
    and #$0F
    ora #$20                    ; color window: window 1
    sta.l $7E0308
    lda #$20                    ; no color math inside it; the fixed color
    sta.l $7E0313
    lda #$A5                    ; subtract, on BG1, BG3, the backdrop
    sta.l $7E0314
    lda #$00
    sta.l $7E0315
    sta.l $7E0316
    sta.l $7E0317
    sta.l !CDL
    lda #!CDMAX
    sta.l !CDT
    lda #$01
    sta.l !CDON
    lda.l $7E033E               ; channel 7 on (SB5 reloads $0AEA from $033E)
    ora #$80
    sta.l $7E033E
    lda.l $7E0AEA
    ora #$80
    sta.l $7E0AEA
    rts

dark_tick:
    lda.l !CDON
    beq .rts
    jsr obj_watch
    lda.l !CDL
    cmp.l !CDT
    beq .rts
    bcc .up
    sec
    sbc #$03
    bpl +
    lda #$00
+   cmp.l !CDT
    bcs .set
    lda.l !CDT
    bra .set
.up:
    inc a
.set:
    sta.l !CDL
    jsr dark_apply
    lda.l !CDL
    bne .rts
    jsr dark_off
.rts:
    rts

dark_apply:
    lda.l !CDL
    tax
    lda.l dk_r,x
    sta.l $7E0315
    lda.l dk_g,x
    sta.l $7E0316
    lda.l dk_b,x
    sta.l $7E0317
    txa
    beq obj_dim
    cmp.l !CDT
    beq obj_dim
    and #$01                    ; OBJ colors every other step (the whole CGRAM is sent)
    beq obj_dim
    rts

; the OBJ palettes = !CSAVE dimmed by level !CDL (also kept in !CDIM)
obj_dim:
    phb
    pea $7E7E
    plb
    plb
    rep #$30
    lda.l !CDL
    and.w #$00FF
    tax
    lda.l dk_r,x
    and.w #$00FF
    sta.l !CT0
    lda.l dk_g,x
    and.w #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    sta.l !CT1
    lda.l dk_b,x
    and.w #$00FF
    xba
    asl a
    asl a
    sta.l !CT2
    ldx.w #$00FE
-   lda.l !CSAVE,x
    sta.w $2A10,x
    dex
    dex
    bpl -
    ldx.w #$0100
-   jsr dimpal
    cpx.w #$0200
    bne -
    ldx.w #$00FE
-   lda.w $2A10,x
    sta.l !CDIM,x
    dex
    dex
    bpl -
    sep #$30
    lda #$01
    sta.w $0351                 ; whole CGRAM at the next NMI
    plb
    rts

; OBJ colors SB5 wrote while dark (a bomber's blink restore $C1:0035 every frame at the start, a palette
; loaded): the new color is the one to dim, the palettes dimmed again
obj_watch:
    rep #$30
    lda.w #$0000
    sta.l !CT3
    ldx.w #$00FE
-   lda.l $7E2A10,x
    cmp.l !CDIM,x
    beq +
    sta.l !CSAVE,x
    lda.w #$0001
    sta.l !CT3
+   dex
    dex
    bpl -
    lda.l !CT3
    sep #$30
    beq +
    jmp obj_dim
+   rts

; everything as before the dark (also clown_stop's)
dark_off:
    lda.l !CDON
    beq .rts
    lda #$00
    sta.l !CDON
    lda.l !CDSV
    sta.l $7E0308
    lda.l !CDSV+1
    sta.l $7E0313
    lda.l !CDSV+2
    sta.l $7E0314
    lda.l !CDSV+3
    sta.l $7E0315
    lda.l !CDSV+4
    sta.l $7E0316
    lda.l !CDSV+5
    sta.l $7E0317
    lda.l $7E033E
    and #$7F
    sta.l $7E033E
    lda.l $7E0AEA
    and #$7F
    sta.l $7E0AEA
    rep #$30
    ldx.w #$00FE
-   lda.l !CSAVE,x
    sta.l $7E2A10,x
    dex
    dex
    bpl -
    sep #$30
    lda #$01
    sta.l $7E0351
.rts:
    rts

; the fixed color by level (SB1: -(20, 22, 10) at full dark)
dk_r:
    db 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 8, 9, 10, 11, 12, 12, 13, 14, 15, 16, 17, 18, 18, 19, 20
dk_g:
    db 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 16, 17, 18, 19, 20, 21, 22
dk_b:
    db 0, 0, 1, 1, 2, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6, 6, 7, 7, 8, 8, 8, 9, 9, 10, 10
; half width of the light per line from its center
oval:
    db 44, 44, 44, 44, 44, 44, 44, 44, 43, 43, 43, 43, 43, 43, 42, 42, 42, 42, 41, 41, 41, 40, 40, 39, 39, 39, 38, 38, 37, 37, 36, 35, 35, 34, 33, 33, 32, 31, 30, 29, 28, 27, 26, 25, 23, 22, 21, 19, 17, 15, 12, 9, 0

; !CHT: the HUD's lines without darkness (window = the whole line), the lives tab's lines (window = its columns),
; then the field: no window (all dark)
; or, A = 1, the oval around the face's screen position (window = the light). M/X 8-bit, DB = $80.
hdma_build:
    sta.l !CT3
    rep #$10
    ldx.w #$0000
    lda #!CHUDL
    sta.l !CHT,x
    lda #$00
    sta.l !CHT+1,x
    lda #$FF
    sta.l !CHT+2,x
    inx
    inx
    inx
    lda #!CTABL
    sta.l !CHT,x
    lda #116
    sta.l !CHT+1,x
    lda #139
    sta.l !CHT+2,x
    inx
    inx
    inx
    lda.l !CT3
    bne .hole
    lda #224-!CTOP
    jsr .gap
    jmp .end
.hole:
    rep #$20
    lda.l !CXP                  ; screen x = field x - BG1 H scroll
    xba
    and.w #$00FF
    sec
    sbc $0319
    and.w #$00FF
    sta.l !CT0
    jsr .cy
    sec
    sbc.w #!CRY                 ; first line of the light
    bmi +
    cmp.w #!CTOP
    bcs ++
+   lda.w #!CTOP
++  sta.l !CT1                  ; line
    sep #$20
    sec
    sbc #!CTOP
    jsr .gap
.line:
    lda.l !CT1
    cmp #224
    bcs .end
    rep #$20                    ; dy = |line - center y|
    lda.l !CT1
    and.w #$00FF
    sta.l !CT2
    jsr .cy
    sec
    sbc.l !CT2
    bpl +
    eor.w #$FFFF
    inc a
+   cmp.w #!CRY+1
    sep #$20
    bcs .rest
    phx
    tax
    lda.l oval,x
    plx
    sta.l !CT2
    lda #$01
    sta.l !CHT,x
    lda.l !CT0
    sec
    sbc.l !CT2
    bcs +
    lda #$00
+   sta.l !CHT+1,x
    lda.l !CT0
    clc
    adc.l !CT2
    bcc +
    lda #$FF
+   sta.l !CHT+2,x
    inx
    inx
    inx
    lda.l !CT1
    inc a
    sta.l !CT1
    bra .line
.rest:                          ; below the light
    lda #224
    sec
    sbc.l !CT1
    beq .end
    bcc .end
    jsr .gap
.end:
    lda #$00
    sta.l !CHT,x
    sep #$30
    rts
; the face's screen line (M 16-bit)
.cy:
    lda.l !CYP
    xba
    and.w #$00FF
    sec
    sbc $031F
    and.w #$00FF
    rts
; A lines without window (entries of up to 127 lines)
.gap:
    beq .gr
    cmp #128
    bcc +
    pha
    lda #127
    jsr .gap1
    pla
    sec
    sbc #127
    bra .gap
+   jsr .gap1
.gr:
    rts
.gap1:
    sta.l !CHT,x
    lda #$FF
    sta.l !CHT+1,x
    lda #$00
    sta.l !CHT+2,x
    inx
    inx
    inx
    rts

; 16 colors at CGRAM shadow offset X - (!CT0, !CT1, !CT2), each channel down to 0; M/X 16-bit, DB = $7E
dimpal:
    lda.w #16
    sta.l !CT3
-   lda.w $2910,x
    and.w #$001F
    sec
    sbc.l !CT0
    bpl +
    lda.w #$0000
+   sta.l !CQN
    lda.w $2910,x
    and.w #$03E0
    sec
    sbc.l !CT1
    bpl +
    lda.w #$0000
+   ora.l !CQN
    sta.l !CQN
    lda.w $2910,x
    and.w #$7C00
    sec
    sbc.l !CT2
    bpl +
    lda.w #$0000
+   ora.l !CQN
    sta.w $2910,x
    inx
    inx
    lda.l !CT3
    dec a
    sta.l !CT3
    bne -
    rts

; ---- shots (SB1 $C7:412A / $4158) and explosions (SB1 $C6:31D7) ----
spawn_shots:
    rep #$30
    ldx.w #14
-   lda.l !CXP
    clc
    adc.l shot_dx,x
    sta.l !SHX,x
    lda.l !CYP
    clc
    adc.l shot_dy,x
    sta.l !SHY,x
    lda.l shot_vx,x
    sta.l !SHVX,x
    lda.l shot_vy,x
    sta.l !SHVY,x
    dex
    dex
    bpl -
    sep #$30
    ldx #$07
    lda #$01
-   sta.l !SHA,x
    dex
    bpl -
    rts
shot_dx:                        ; SB1 $C7:423C (from the center), $C7:421C
    dw 0<<8, 29<<8, 40<<8, 29<<8, 0<<8, -29<<8, -40<<8, -29<<8
shot_dy:
    dw -48<<8, -35<<8, -8<<8, 19<<8, 32<<8, 19<<8, -8<<8, -35<<8
shot_vx:
    dw $0000, $00A0, $00F0, $00A0, $0000, -$A0, -$F0, -$A0
shot_vy:
    dw -$F0, -$A0, $0000, $00A0, $00F0, $00A0, $0000, -$A0

; every frame: the shots fly (gone off the screen), a player within 8 px of one dies
shots:
    ldx #$07
.l: lda.l !SHA,x
    beq .next
    inc a
    cmp #$09
    bcc +
    lda #$01
+   sta.l !SHA,x
    phx
    txa
    asl a
    tax
    rep #$20
    lda.l !SHX,x
    clc
    adc.l !SHVX,x
    sta.l !SHX,x
    lda.l !SHY,x
    clc
    adc.l !SHVY,x
    sta.l !SHY,x
    sep #$20
    lda.l !SHX+1,x
    cmp #$04
    bcc .off
    cmp #$FC
    bcs .off
    sta.l !CTX
    lda.l !SHY+1,x
    cmp #$D4
    bcs .off
    sta.l !CTY
    lda #$08
    sta.l !CRAD
    jsr touch
    plx
    bra .next
.off:
    plx
    lda #$00
    sta.l !SHA,x
.next:
    dex
    bpl .l
    rts

; explosions: 13 frames each
booms:
    ldx #$03
-   lda.l !EXA,x
    beq +
    inc a
    cmp #14
    bcc ++
    lda #$00
++  sta.l !EXA,x
+   dex
    bpl -
    rts

; a new one 0-63 px from the center on each axis (SB1 $C6:32C8: random & $3F, bit 0 clear = minus)
spawn_boom:
    ldx #$03
-   lda.l !EXA,x
    beq +
    dex
    bpl -
    rts
+   lda #$01
    sta.l !EXA,x
    txa
    asl a
    sta.l !CT2
    jsr rnd_off
    sta.l !CT1
    lda.l !CXP+1
    and.w #$00FF
    clc
    adc.l !CT1
    pha
    jsr rnd_off
    sta.l !CT1
    lda.l !CYP+1
    and.w #$00FF
    clc
    adc.l !CT1
    pha
    sep #$30
    lda.l !CT2
    tax
    rep #$20
    pla
    sta.l !EXY,x
    pla
    sta.l !EXX,x
    sep #$30
    rts

; A = +- (random & $3F), minus when its bit 0 is clear (M left 16-bit, X/Y lost)
rnd_off:
    sep #$30
    jsl $C01DC4
    sep #$30
    and #$3F
    sta.l !CT0
    lda #$00
    sta.l !CT0+1
    rep #$20
    lda.l !CT0
    bit.w #$0001
    bne +
    eor.w #$FFFF
    inc a
+   rts

; ---- OAM: after SB5's builder ($C0:0B5D) ----
clown_oam:
    jsl $C01459
    php
    sep #$30
    lda.l $7E1031
    cmp #!CSTAGE
    beq +
    brl .out
+   lda.l !CON
    cmp #$A5
    beq +
    brl .out
+   phb
    pea $7E7E
    plb
    plb
    rep #$30
    ldx.w #104*4                ; slots 104-127: hidden, 16x16
-   lda.w #$E000
    sta.w $08BF,x
    inx
    inx
    inx
    inx
    cpx.w #128*4
    bne -
    sep #$30
    lda #$AA
    ldx #$05
-   sta.w $0ABF+26,x
    dex
    bpl -
    rep #$20
    lda.w #104*4
    sta.l !OSL
    sep #$20
    lda #$07
    sta.l !OI
.shot:
    lda.l !OI
    tax
    lda.l !SHA,x
    beq .nshot
    tax
    lda.l shot_pic-1,x
    sta.l !OTL
    lda #$00
    sta.l !OTL+1
    sta.l !OFL
    lda.l !OI
    asl a
    tax
    rep #$20
    lda.l !SHX,x
    xba
    and.w #$00FF
    sec
    sbc.w #8
    sta.l !OFX
    lda.l !SHY,x
    xba
    and.w #$00FF
    sec
    sbc.w #8
    sta.l !OFY
    sep #$20
    jsr spr
.nshot:
    lda.l !OI
    dec a
    sta.l !OI
    bpl .shot
    lda #$03
    sta.l !OI
.boom:
    lda.l !OI
    tax
    lda.l !EXA,x
    beq .nboom
    tax
    lda.l boom_pic-1,x
    sta.l !OTL
    lda #$00
    sta.l !OTL+1
    lda.l !OI
    asl a
    tax
    rep #$20
    lda.l !EXX,x
    sec
    sbc.w #16
    sta.l !OFX
    lda.l !EXY,x
    sec
    sbc.w #16
    sta.l !OFY
    sep #$20
    lda #$00
    jsr spr4
    rep #$20
    lda.l !OFX
    clc
    adc.w #16
    sta.l !OFX
    sep #$20
    lda #$40
    jsr spr4
    rep #$20
    lda.l !OFY
    clc
    adc.w #16
    sta.l !OFY
    sep #$20
    lda #$C0
    jsr spr4
    rep #$20
    lda.l !OFX
    sec
    sbc.w #16
    sta.l !OFX
    sep #$20
    lda #$80
    jsr spr4
.nboom:
    lda.l !OI
    dec a
    sta.l !OI
    bmi +
    brl .boom
+   plb
.out:
    plp
    rtl

spr4:
    sta.l !OFL
    ; (falls through)

; a 16x16 sprite: field (!OFX, !OFY) top left, tile !OTL of the body's page, flips !OFL; M/X 8-bit, DB = $7E
spr:
    rep #$30
    lda.l !OSL
    cmp.w #128*4
    bcc +
    brl .skip
+   tax
    lda.l !OFX
    sec
    sbc.w $0319
    sta.l !OX
    clc
    adc.w #16
    cmp.w #256+16
    bcc +
    brl .skip
+
    lda.l !OFY
    sec
    sbc.w $031F
    dec a
    sta.l !OY
    clc
    adc.w #16
    cmp.w #224+16
    bcc +
    brl .skip
+
    lda.l !CTB
    clc
    adc.l !OTL
    sta.l !ONM
    sep #$20
    lda.l !OX
    sta.w $08BF,x
    lda.l !OY
    sta.w $08C0,x
    lda.l !ONM
    sta.w $08C1,x
    lda.l !CSL
    asl a
    ora #$30
    ora.l !OFL
    sta.l !CT3
    lda.l !ONM+1
    and #$01
    ora.l !CT3
    sta.w $08C2,x
    lda.l !OX+1
    and #$01
    beq +
    rep #$20
    txa
    lsr a
    lsr a
    and.w #$0003
    sta.l !CT3
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    lda.l !CT3
    tax
    sep #$20
    lda.l hbit,x
    ora.w $0ABF,y
    sta.w $0ABF,y
+   rep #$20
    lda.l !OSL
    clc
    adc.w #4
    sta.l !OSL
.skip:
    sep #$30
    rts
hbit:
    db $01, $04, $10, $40
shot_pic:                       ; SB1 $3C2E: pictures 0, 1, 2, 3 for 3, 1, 3, 1 frames (tiles 2 * picture)
    db 0, 0, 0, 2, 4, 4, 4, 6
boom_pic:                       ; SB1 $C6:2F23: pictures 4-8 for 5, 4, 2, 1, 1 frames
    db 8, 8, 8, 8, 8, 10, 10, 10, 10, 12, 12, 14, 32

print "SYM clown_hold ", hex(!CHOLD)
print "SYM clown_killseats ", hex(killseats)

; ---------------------------------------------------------------------------
; SB1 2-1's enemies in World 1's 1-2, moved as SB1 moves them (SB1 ROM, objects $1000+$40*n; docs/ROM_MAP.md
; "SB1's 2-1 enemies"): sb1_spring / sb1_pot / sb1_face are the actor routines of their records (types 02,
; 03, 06; called through JML [$A5], X = actor, Y = object, M/X 8-bit, DB = $80, RTL). Every frame: SB5's
; contact and flame step ($C3:4B7B, as SB5's walker $C3:4B5A), then SB1's brain and step, then SB5's sprite
; position and cell bit ($C3:4CFC). SB1's coordinates are SB5's + 8 (cell centers), its directions 0 up,
; 1 right, 2 down, 3 left (SB5's facing: 4, 1, 2, 3). SB1's step ($C6:360E): 1/2 px a frame (speed 0 of
; $C6:36BB), first 1 px toward the center of the column (row) when going up or down (sideways); a step
; that ends within 16 px of another enemy is taken back, and then 1 time in 4 (a random direction equal to
; its own) or when the way on is shut it turns around. A cell shuts the way ($C6:1562-$15CE: the next cell
; once the center is reached) when its $1052 has the kind's bits: SB5's enemy mask $E8 for SB1's $E0
; (walls, soft blocks, bombs), $C8 for the pot's $A0 (it goes through soft blocks). Animations restart at
; every new direction after a step (SB1 $C6:2814).
;   spring head ($C6:3947): straight on; at a wall, across toward the nearest live player (|dx| + |dy|,
;     $C6:39C0) when that way is open and the player is not in line, else a quarter turn clockwise;
;   pot ($C6:37B0): every 16-79 frames, on a cell's center, a random direction; at a wall a random one;
;   clown face ($C6:3774): at a wall turns around, every 3-6th wall a quarter turn clockwise instead.
; SB1 4-4's UFO and bomb robot and SB1 4-2's horned robot in World 1's 1-4 (types $35, $36, $04):
;   UFO ($C6:74C5, brain $C6:383A): on every cell's center (every other frame there, $21) and at a wall, across
;     toward the nearest live player when that way is open and the player is not in line, else straight on,
;     a quarter turn clockwise when that is shut;
;   bomb robot ($C6:5FDE): the clown face's brain at speed 2 (1.5 px a frame, $21 = $40);
;   horned robot ($C6:5A34, brain $C6:3ADF): a live player within 12 px across and 80 px along its way, or
;     along the other axis (that one first when going up / down), not behind it and that way open: it turns
;     that way, stops on the cell's center for 32 frames (its animation turns) and then runs at speed 1 (1 px
;     a frame) while the player stays in sight; nobody in sight -> straight on, at a wall the clown face's
;     turn ($C6:3807).
; Speeds ($C6:36BB): 0 = 1/2 px, 1 = 1 px, 2 = 1 1/2 px a frame.
!WSET  = $7FF700          ; per actor (24 bytes each): $A5 once set up
!WDIR  = $7FF718          ; SB1 direction
!WT    = $7FF730          ; SB1's $21: the pot's turn timer, the face's walls left
!WLAST = $7FF748          ; SB1's $22: direction of the animation shown ($FF: none yet)
!WKIND = $7FF760          ; scratch: 0 spring, 1 pot, 2 face
!WMASK = $7FF761          ; scratch: $1052 bits that shut the way
!WSAV  = $7FF762          ; scratch: x sub, x, y sub, y before a step
!WNEW  = $7FF766          ; scratch: direction tried
!WBEST = $7FF767          ; scratch: nearest seat
!WDIST = $7FF768          ; scratch: its distance (word)
!WTMP  = $7FF76A          ; scratch (word)
!WSX   = $7FF76C          ; scratch: own x, y, actor
!WSY   = $7FF76D
!WSELF = $7FF76E
!WNEAR = $7FF76F          ; 1 while $C3:4B7B runs for one of these: co-op's c3_near skips far seats
!WSPD  = $7FF770          ; per actor: SB1's $19 speed (0-2)
!WSEEN = $7FF788          ; per actor: horned robot, frames seeing a player on a center (SB1's $30)
!WADX  = $7FF7A0          ; scratch: |dx|, |dy| to a seat, player at or right of / below it
!WADY  = $7FF7A1
!WSGX  = $7FF7A2
!WSGY  = $7FF7A3
!WSEAT = $7FF7A4          ; scratch: seat looked at
!WLX   = $7FF7AE          ; $0069 (main loop passes) when !WLIST was built
!WLV   = $7FF7AF          ; $A5: !WLIST built
!WLIST = $7FF7B0          ; enemy actors this frame, $FF-terminated (24 at most + 1)


sb1_spring:
    lda #$00
    bra sb1w
sb1_pot:
    lda #$01
    bra sb1w
sb1_face:
    lda #$02
    bra sb1w
sb1_ufo:
    lda #$03
    bra sb1w
sb1_bot:
    lda #$04
    bra sb1w
sb1_horn:
    lda #$05
sb1w:
    sta.l !WKIND
    lda $0E20
    ora $0E21
    beq +
    jml $C34C13                 ; stop-watch: SB5's frozen enemy (contact and flames only), as $C5:4319
+   stz $1FF2
    lda #$01
    sta.l !WNEAR
    %c3($C34B7B)                ; contact with the players, flames
    lda #$00                    ; (keeps C)
    sta.l !WNEAR
    bcc +
    rtl                         ; dead
+   lda.l !WSET,x
    cmp #$A5
    beq +
    jsr wsetup
+   lda.l !WKIND
    beq .spring
    cmp #$01
    beq .pot
    cmp #$03
    beq .ufo
    cmp #$05
    beq .horn
    jsr face                    ; clown face, bomb robot
    bra .done
.horn:
    jsr horn
    bra .done
.ufo:
    jsr ufo
    bra .done
.pot:
    jsr pot
    bra .done
.spring:
    jsr spring
.done:
    lda.l !WDIR,x               ; SB5's facing
    bne +
    lda #$04
+   sta $1632,x
    %c3($C34CFC)                ; sprite position, the cell's enemy bit
    rtl

; first frame: SB1's start (every enemy facing down, its animation from the start; $21 = $40 for the pot and
; the bomb robot, 1 for the UFO, else 3; $22 = $FF; speed 2 for the bomb robot, else 0), whole pixels
wsetup:
    lda #$A5
    sta.l !WSET,x
    lda #$02
    sta.l !WDIR,x
    lda #$FF
    sta.l !WLAST,x
    lda #$00
    sta.l !WSPD,x
    sta.l !WSEEN,x
    phx
    lda.l !WKIND
    tax
    lda.l .t21,x
    plx
    sta.l !WT,x
    lda.l !WKIND
    cmp #$04
    bne +
    lda #$02
    sta.l !WSPD,x
+   stz $1812,x
    stz $185A,x
    lda #$02
    jmp anim
.t21:
    db $03, $40, $03, $01, $40, $03

spring:
    lda #$E8
    sta.l !WMASK
    lda.l !WDIR,x
    jsr blocked
    bne .wall
    jsr step
    bcs +
    jsr show
+   rts
.wall:
    jsr nearest
    bcc .turn
    lda.l !WDIR,x
    lsr a
    bcs .across
    lda $182A,y                 ; going up / down: right or left toward the player
    cmp $182A,x
    beq .turn
    lda #$01
    bcs .try
    lda #$03
    bra .try
.across:
    lda $1872,y                 ; going right / left: down or up
    cmp $1872,x
    beq .turn
    lda #$02
    bcs .try
    lda #$00
.try:
    sta.l !WNEW
    jsr blocked
    bne .turn
    lda.l !WNEW
    sta.l !WDIR,x
    rts
.turn:
    lda.l !WDIR,x
    inc a
    and #$03
    sta.l !WDIR,x
    rts

pot:
    lda #$C8
    sta.l !WMASK
    lda.l !WT,x
    dec a
    sta.l !WT,x
    bne .go
    inc a
    sta.l !WT,x
    lda $182A,x                 ; only on a cell's center
    ora $1872,x
    and #$0F
    bne .go
    jsl $C01DC4
    and #$3F
    clc
    adc #$10
    sta.l !WT,x
    jsl $C01DC4
    and #$03
    sta.l !WDIR,x
.go:
    lda.l !WDIR,x
    jsr blocked
    beq +
    jsl $C01DC4
    and #$03
    sta.l !WDIR,x
    rts
+   jsr step
    bcs +
    jsr show
+   rts

face:
    lda #$E8
    sta.l !WMASK
    lda.l !WDIR,x
    jsr blocked
    beq facego
; at a wall (SB1 $C6:3807): $21 - 1; not 0 = turn around, 0 = quarter turn clockwise and $21 = 3-6
facewall:
    lda.l !WT,x
    dec a
    sta.l !WT,x
    bne .back
    lda.l !WDIR,x
    inc a
    and #$03
    sta.l !WDIR,x
    jsl $C01DC4
    and #$03
    clc
    adc #$03
    sta.l !WT,x
    rts
.back:
    lda.l !WDIR,x
    eor #$02
    sta.l !WDIR,x
    rts
facego:
    jsr step
    bcs +
    jsr show
+   rts

;   UFO (SB1 $C6:383A)
ufo:
    lda #$E8
    sta.l !WMASK
    lda $182A,x                 ; on a cell's center: choose
    ora $1872,x
    and #$0F
    beq .choose
    lda.l !WDIR,x
    jsr blocked
    bne .choose
.go:
    jsr step
    bcs +
    jsr show
+   rts
.choose:
    jsr nearest                 ; (Y = seat or $FF)
    lda.l !WT,x                 ; first frame there: straight on
    bne .turn
    inc a
    sta.l !WT,x
    lda.l !WDIR,x
    jsr blocked
    beq .go
    rts
.turn:
    lda #$00
    sta.l !WT,x
    cpy #$FF
    beq .straight
    lda.l !WDIR,x
    lsr a
    bcs .across
    lda $182A,y                 ; going up / down: right or left toward the player
    cmp $182A,x
    beq .straight
    lda #$01
    bcs .try
    lda #$03
    bra .try
.across:
    lda $1872,y                 ; going right / left: down or up
    cmp $1872,x
    beq .straight
    lda #$02
    bcs .try
    lda #$00
.try:
    sta.l !WNEW
    jsr blocked
    bne .straight
    lda.l !WNEW
    sta.l !WDIR,x
    bra .go
.straight:
    lda.l !WDIR,x
    jsr blocked
    beq .go
    lda.l !WDIR,x
    inc a
    and #$03
    sta.l !WDIR,x
    rts

;   horned robot (SB1 $C6:3ADF)
horn:
    lda #$E8
    sta.l !WMASK
    jsr sees
    bcc .seen
    lda #$00
    sta.l !WSEEN,x
    lda.l !WDIR,x
    jsr blocked
    beq .go
    jmp facewall
.go:
    jsr step
    bcs +
    jsr show
+   rts
.seen:
    lda.l !WDIR,x               ; on the center across its way?
    lsr a
    bcs .row
    lda $182A,x
    bra .mid
.row:
    lda $1872,x
.mid:
    and #$0F
    bne .go
    lda.l !WSEEN,x
    inc a
    sta.l !WSEEN,x
    cmp #$20
    beq .run
    jmp show                    ; waiting: only the new way's animation
.run:
    dec a
    sta.l !WSEEN,x
    lda #$01
    sta.l !WSPD,x
    jsr step
    lda #$00                    ; (keeps C)
    sta.l !WSPD,x
    bcs +
    jsr show
+   rts

; carry clear: a live player in the horned robot's sight, its way turned toward the first one (SB1 $C6:3B64,
; P1 then P2; here every seat)
sees:
    ldy #$00
.loop:
    lda $17FA,y
    bmi .next
    lda $15A2,y
    bmi .next
    lda $182A,y                 ; (quick: |dx| and |dy| < 80, one of them < 12)
    sec
    sbc $182A,x
    bcs +
    eor #$FF
    inc a
+   cmp #$50
    bcs .next
    sta.l !WADX
    lda $1872,y
    sec
    sbc $1872,x
    bcs +
    eor #$FF
    inc a
+   cmp #$50
    bcs .next
    cmp #$0C
    bcc .in
    lda.l !WADX
    cmp #$0C
    bcs .next
.in:
    tya
    sta.l !WSEAT
    jsr look
    bcc .yes
    lda.l !WSEAT
    tay
.next:
    iny
    cpy #$05
    bcc .loop
    sec
.yes:
    rts

; Y = seat: within 80 px along and 12 px across the axis it goes on, else the other axis: toward the player
; unless that is behind it or shut (carry set), else that way taken (carry clear); Y lost
look:
    lda #$01
    sta.l !WSGX
    sta.l !WSGY
    lda $182A,y
    sec
    sbc $182A,x
    bcs +
    eor #$FF
    inc a
    pha
    lda #$00
    sta.l !WSGX
    pla
+   sta.l !WADX
    lda $1872,y
    sec
    sbc $1872,x
    bcs +
    eor #$FF
    inc a
    pha
    lda #$00
    sta.l !WSGY
    pla
+   sta.l !WADY
    lda.l !WDIR,x
    lsr a
    bcc .vert
    jsr hband
    bcc .h
    jsr vband
    bcc .v
    rts
.vert:
    jsr vband
    bcc .v
    jsr hband
    bcc .h
    rts
.h:
    lda.l !WSGX                 ; right / left
    beq +
    lda #$01
    bra .try
+   lda #$03
    bra .try
.v:
    lda.l !WSGY                 ; down / up
    beq +
    lda #$02
    bra .try
+   lda #$00
.try:
    sta.l !WNEW
    eor #$02
    cmp.l !WDIR,x
    beq .no
    lda.l !WNEW
    jsr blocked
    bne .no
    lda.l !WNEW
    sta.l !WDIR,x
    clc
    rts
.no:
    sec
    rts

; carry clear: |dx| < 80 and |dy| < 12 (hband), |dx| < 12 and |dy| < 80 (vband)
hband:
    lda.l !WADX
    cmp #$50
    bcs +
    lda.l !WADY
    cmp #$0C
+   rts
vband:
    lda.l !WADX
    cmp #$0C
    bcs +
    lda.l !WADY
    cmp #$50
+   rts

; after a step: a direction other than the animation's -> its animation from the start
show:
    lda.l !WDIR,x
    cmp.l !WLAST,x
    beq +
    sta.l !WLAST,x
    jsr anim
+   rts

; A = direction: the kind's animation of that facing, from its first frame
anim:
    cmp #$00
    bne +
    lda #$04
+   dec a
    sta.l !WTMP
    phx
    lda.l !WKIND
    tax
    lda.l .base,x
    plx
    clc
    adc.l !WTMP
    ldy $17FA,x
    phx
    phy
    jsl $C011EC
    sep #$30
    ply
    plx
    rts
.base:
    db !ASPRING, !APOT, !AFACE, !AUFO, !ABOT, !AHORN

; A = direction: A = the bits of !WMASK in the cell SB1 tests that way (Z set: open); Y lost
blocked:
    cmp #$01
    beq .r
    cmp #$02
    beq .d
    cmp #$03
    beq .l
    lda $1872,x                 ; up: row of y - 1, column of x + 8
    dec a
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$08
    bra .col
.d:
    lda $1872,x                 ; down: row of y + 16
    clc
    adc #$10
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$08
    bra .col
.r:
    lda $1872,x                 ; right: column of x + 16, row of y + 8
    clc
    adc #$08
    and #$F0
    sta.l !WTMP
    lda $182A,x
    clc
    adc #$10
    bra .col
.l:
    lda $1872,x                 ; left: column of x - 1
    clc
    adc #$08
    and #$F0
    sta.l !WTMP
    lda $182A,x
    dec a
.col:
    lsr a
    lsr a
    lsr a
    lsr a
    ora.l !WTMP
    tay
    lda $1052,y
    and.l !WMASK
    rts

; SB1's step ($C6:360E, speed !WSPD: (speed + 1) / 2 px): carry set when it was taken back (another enemy
; within 16 px)
step:
    lda.l !WSPD,x               ; !WTMP = sub-pixels, !WTMP+1 = pixels of the step
    inc a
    lsr a
    sta.l !WTMP+1
    lda #$00
    ror a
    sta.l !WTMP
    lda $1812,x
    sta.l !WSAV
    lda $182A,x
    sta.l !WSAV+1
    lda $185A,x
    sta.l !WSAV+2
    lda $1872,x
    sta.l !WSAV+3
    lda.l !WDIR,x
    lsr a
    bcs .side
    lda $182A,x                 ; up / down: 1 px toward the column's center
    and #$0F
    beq +
    cmp #$08
    bcs .xin
    dec $182A,x
    bra +
.xin:
    inc $182A,x
+   lda.l !WDIR,x
    bne .down
    lda $185A,x
    sec
    sbc.l !WTMP
    sta $185A,x
    lda $1872,x
    sbc.l !WTMP+1
    sta $1872,x
    bra .moved
.down:
    lda $185A,x
    clc
    adc.l !WTMP
    sta $185A,x
    lda $1872,x
    adc.l !WTMP+1
    sta $1872,x
    bra .moved
.side:
    lda $1872,x                 ; right / left: 1 px toward the row's center
    and #$0F
    beq +
    cmp #$08
    bcs .yin
    dec $1872,x
    bra +
.yin:
    inc $1872,x
+   lda.l !WDIR,x
    cmp #$01
    bne .left
    lda $1812,x
    clc
    adc.l !WTMP
    sta $1812,x
    lda $182A,x
    adc.l !WTMP+1
    sta $182A,x
    bra .moved
.left:
    lda $1812,x
    sec
    sbc.l !WTMP
    sta $1812,x
    lda $182A,x
    sbc.l !WTMP+1
    sta $182A,x
.moved:
    jsr touching
    bcs .back
    rts
.back:
    lda.l !WSAV
    sta $1812,x
    lda.l !WSAV+1
    sta $182A,x
    lda.l !WSAV+2
    sta $185A,x
    lda.l !WSAV+3
    sta $1872,x
    jsl $C01DC4
    and #$03
    cmp.l !WDIR,x
    beq .rev
    lda.l !WDIR,x
    jsr blocked
    beq .stay
.rev:
    lda.l !WDIR,x
    eor #$02
    sta.l !WDIR,x
.stay:
    sec
    rts

; carry set: another live enemy (actors 5 to $198C with an enemy type) within 16 px both ways. The enemies'
; actors are listed once a main loop pass (!WLIST, rebuilt when $0069 changes), so each step looks at the
; enemies only, not at every actor.
touching:
    lda.l !WLV                  ; (0 after the stage start's clear: no list yet)
    cmp #$A5
    bne +
    lda $0069                   ; main loop passes ($C0:0B3E)
    cmp.l !WLX
    beq ++
+   jsr wlist
++  lda $182A,x                 ; !WSX / !WSY = own x / y - 15: another's - that = d + 15, within 16 px
    sec                         ; both ways <=> below 31 (positions never differ by 241+)
    sbc #$0F
    sta.l !WSX
    lda $1872,x
    sec
    sbc #$0F
    sta.l !WSY
    txa
    sta.l !WSELF
    phx
    ldx #$00
.loop:
    lda.l !WLIST,x
    bmi .none
    inx
    tay
    lda $17FA,y
    bmi .loop
    lda $182A,y
    sec
    sbc.l !WSX
    cmp #$1F
    bcs .loop
    lda $1872,y
    sec
    sbc.l !WSY
    cmp #$1F
    bcs .loop
    tya
    cmp.l !WSELF
    beq .loop
    lda $15A2,y
    bmi .loop
    plx
    sec
    rts
.none:
    plx
    clc
    rts

; !WLIST = the active actors 5 to $198C with an enemy type ($16C2), then $FF
wlist:
    phx
    ldx #$00
    ldy #$05
.loop:
    lda $17FA,y
    bmi .next
    lda $16C2,y
    beq .next
    tya
    sta.l !WLIST,x
    inx
.next:
    cpy $198C
    iny
    bcc .loop
    lda #$FF
    sta.l !WLIST,x
    lda $0069
    sta.l !WLX
    lda #$A5
    sta.l !WLV
    plx
    rts

; Y = the live player nearest (|dx| + |dy|; the lowest seat on a tie), carry clear when none
nearest:
    lda #$FF
    sta.l !WBEST
    sta.l !WDIST
    sta.l !WDIST+1
    ldy #$00
.loop:
    lda $17FA,y
    bmi .next
    lda $15A2,y
    bmi .next
    lda $182A,y
    sec
    sbc $182A,x
    bcs +
    eor #$FF
    inc a
+   sta.l !WTMP
    lda #$00
    sta.l !WTMP+1
    lda $1872,y
    sec
    sbc $1872,x
    bcs +
    eor #$FF
    inc a
+   rep #$20
    and #$00FF
    clc
    adc.l !WTMP
    cmp.l !WDIST
    bcs +
    sta.l !WDIST
    sep #$20
    tya
    sta.l !WBEST
+   sep #$20
.next:
    iny
    cpy #$05
    bcc .loop
    lda.l !WBEST
    tay
    cmp #$FF
    beq +
    sec
    rts
+   clc
    rts

end:

print "SYM clown ", hex(clown)
print "SYM clown_start ", hex(clown_start)
print "SYM clown_oam ", hex(clown_oam)
print "SYM clown_hit ", hex(clown_hit)
print "SYM sb1_spring ", hex(sb1_spring)
print "SYM sb1_pot ", hex(sb1_pot)
print "SYM sb1_face ", hex(sb1_face)
print "SYM sb1_ufo ", hex(sb1_ufo)
print "SYM sb1_bot ", hex(sb1_bot)
print "SYM sb1_horn ", hex(sb1_horn)
print "SYM end ", hex(end)
