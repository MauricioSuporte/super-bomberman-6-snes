; In-stage pause menu of the Normal Game (tools/sb6/features/pause.py has the
; overview).
;
; SB5's pause task ($C5:0000): Start sets $1D1D = 1 at $C5:0058 (the stage
; freezes), draws PAUSE! / WORLD n - nn on BG3, then every frame from
; $C5:009E tests Start (JSR $00B7) and unpauses at $C5:000C ($1D1D = 0,
; BG3 rows 3-31 cleared, music back). The hack:
; * pm_open (JSL at $C5:0058): $1D1D = 1 as before; in the Normal Game also
;   sets up the menu (state below) and the panel: inside color window 1
;   BG1/BG2/OBJ leave the main screen for the subscreen, the main screen is
;   BG3 over a black backdrop and color math adds half the subscreen there
;   (every OBJ palette dims, not only 4-7); the window's rows come from
;   HDMA channel 7 (window 1 left/right per line, $0AEA kept at $80 by the
;   NMI); $0306-$0317 and $0AEA are saved and put back on resume.
; * pm_tick (JML at $C5:009E, every paused frame, M/X 8-bit): Battle keeps
;   the Start test; the menu reads the new actions / directions of the live
;   seats ($36+s, $3B+s, as $00B7 does) and leaves through $C5:000C
;   (resume) or $C5:00A6 (RTL: still paused). Yes on a question ends the
;   stage: $1D1A bit 6 off (no clear), $1031 = 3 + $631A = 1 (world map) or
;   $1031 = 2 (title, its intro skipped), $1D1D = 0, $1D1E bit 2 (SB5's stage end).
; * pause_nmi (called by pick_nmi after the VRAM queue, forced blank): saves
;   BG3 tiles $100+ and loads the glyphs and frame tiles, sends the frame
;   (top row, sides of rows 10-16) and the text rows of the state with the
;   bottom of the frame; after a resume blanks them and puts the tiles back.
;
; * intro_label (JSL at $C5:0CEB, the stage intro task): STAGE w-s with set 4
;   arrangement $E0 (features/world1.py) and SB5's digits, as in the pause.
;
; State $7F:F100-$7F:F6DF (docs/FREE_SPACE.md).

asar 1.90
hirom
org !ORG

!buf   = $7FF100        ; saved BG3 tiles (up to $500 bytes)
!V     = $7FF600
!sig   = !V+$00         ; $5A once pm_open ran
!st    = !V+$01         ; 0 none (Battle / resumed), 1 menu up, 2 leaving the stage
!menu  = !V+$02         ; 0 main list, 1 world map question, 2 title question
!sel   = !V+$03         ; selected line
!scr   = !V+$04         ; text rows wanted (pause.py build_tables)
!tiles = !V+$06         ; 1 = the glyphs are in VRAM (the stage's tiles in !buf)
!dim   = !V+$07         ; 1 = panel set by us (old shadows in !sv)
!bdf   = !V+$08         ; 1 = CGRAM color 0 made black by the NMI (old color in !bd)
!bd    = !V+$09         ; word
!ch    = !V+$11         ; $0AEA (HDMA channels)
!sv    = !V+$20         ; $12 bytes: $0306-$0317 (windows, screens, color math)
!lt    = !V+$40         ; label cells: top words (12)
!lb    = !V+$58         ; bottom words (12)
!ln    = !V+$70         ; label cells
!lc    = !V+$71         ; label's first column
!lbuf  = !V+$80         ; $60 bytes: STAGE rows (2 x 24 words)
!dw    = !V+$72         ; label digits: world, stage tens, units
!dt    = !V+$73
!du    = !V+$74
!na    = !V+$0D         ; new actions of the live seats
!nd    = !V+$0E         ; new directions
!w     = !V+$0F         ; NMI word scratch
!SEEN  = $7FFD03        ; asm/title_anim.asm !seen: 1 = the title comes back without its intro

; --- entry of SB5's pause ($C5:0058, replaces LDA #$01 / STA $1D1D)
pm_open:
    lda #$01
    sta.l $7E1D1D
    phx
    lda #$00
    sta.l !st
    sta.l !tiles                    ; (a stage left through the menu kept them)
    lda.l $7E1D1A
    and #$01
    beq +
    jmp .done                       ; Battle: SB5's pause
+   lda #$5A
    sta.l !sig
    lda #$00
    sta.l !menu
    sta.l !sel
    sta.l !dim
    lda #$01
    sta.l !scr
    lda.l $7E0AEA                   ; the stage's own color math / windows (1-4's transparency) are
    ora.l $7E033E                   ; saved and replaced while it is frozen
    bmi +                           ; HDMA channel 7 busy: no panel
    lda.l $7E0AEA
    sta.l !ch
    lda #$80                        ; only our channel while frozen (the stage's own HDMA, e.g.
    sta.l $7E0AEA                   ; 1-4's, may write the window registers too)
    ldx #$11                        ; $0306-$0317 -> !sv
-   lda.l $7E0306,x
    sta.l !sv,x
    dex
    bpl -
    lda #$22                        ; window 1 on BG1, BG2, OBJ and color
    sta.l $7E0306
    sta.l $7E0308
    lda #$00
    sta.l $7E0307
    sta.l $7E0312                   ; TSW
    lda #$13                        ; subscreen BG1, BG2, OBJ; masked from the main screen inside
    sta.l $7E0310                   ; the window, where the main screen is BG3 over the backdrop
    sta.l $7E0311                   ; (black while paused, see the NMI)
    lda #$12                        ; math inside the window only, with the subscreen
    sta.l $7E0313
    lda #$60                        ; add, half, on the backdrop: (black + scene) / 2; every OBJ
    sta.l $7E0314                   ; palette, BG3 (main screen) untouched
    lda #$00                        ; fixed color black (empty subscreen)
    sta.l $7E0315
    sta.l $7E0316
    sta.l $7E0317
    lda #$01
    sta.l !dim
+   jsr label
    lda #$01
    sta.l !st
.done:
    plx
    rtl

; --- every paused frame ($C5:009E)
pm_tick:
    lda.l !st
    cmp #$01
    beq menu
    cmp #$02
    beq stay                        ; leaving: the stage end takes over
    jsr pads                        ; Battle: SB5's Start test
    lda.l !na
    and #$01
    beq stay
resume:
    jml $C5000C
stay:
    jml $C500A6

menu:
    jsr label
    jsr pads
    lda.l !na
    and #$81                        ; Start, A
    bne accept
    lda.l !na
    and #$08                        ; B
    bne back
    lda.l !nd
    and #$08
    bne up
    lda.l !nd
    and #$04
    bne down
    jmp show

up:
    lda.l !sel
    dec a
    bpl +
    jsr count
    dec a
+   sta.l !sel
    lda #$01
    jsr sfx
    jmp show

down:
    lda.l !sel
    inc a
    sta.l !sel
    jsr count
    cmp.l !sel
    bne +
    lda #$00
    sta.l !sel
+   lda #$01
    jsr sfx
    jmp show

back:
    lda.l !menu
    bne to_main
    jmp close                       ; main list: B resumes
to_main:
    lda.l !menu                     ; question -> its line of the main list
    sta.l !sel
    lda #$00
    sta.l !menu
    lda #$03
    jsr sfx
    jmp show

accept:
    lda.l !menu
    bne .question
    lda.l !sel
    bne +
    jmp close                       ; RESUME
+   sta.l !menu                     ; RETURN TO ... -> its question, NO selected
    lda #$00
    sta.l !sel
    lda #$04
    jsr sfx
    jmp show
.question:
    lda.l !sel
    beq to_main                     ; NO
    lda #$04                        ; YES: leave the stage
    jsr sfx
    jsr undim
    lda #$02
    sta.l !st
    lda.l $7E1D1A
    and #$BF                        ; not cleared ($C5:3D19)
    sta.l $7E1D1A
    lda.l !menu
    cmp #$01
    bne .title
    lda #$01
    sta.l $7E631A                   ; the Normal Game menu starts on the world map
    lda #$03
    bra .mode
.title:
    lda #$01                        ; as SB6's pause: the title without its intro
    sta.l !SEEN
    lda #$02
.mode:
    sta.l $7E1031
    lda #$00
    sta.l $7E1D1D
    lda.l $7E1D1E
    ora #$04                        ; SB5's stage end
    sta.l $7E1D1E
    jml $C500A6

close:
    jsr undim
    lda #$00
    sta.l !st                       ; the NMI puts the tiles back
    jml $C5000C

show:
    lda.l !menu
    bne +
    lda.l !sel                      ; main list: 1 + line
    inc a
    bra ++
+   asl a                           ; question: 2 + 2 * menu + line
    inc a
    inc a
    clc
    adc.l !sel
++  sta.l !scr
    jml $C500A6

count:                              ; -> A = lines of the menu
    lda.l !menu
    bne +
    lda #$03
    rts
+   lda #$02
    rts

pads:                               ; new actions / directions of the live seats (as $C5:00B7)
    phx
    lda #$00
    sta.l !na
    sta.l !nd
    ldx #$04
-   lda.l $7E17FA,x
    bmi +
    lda.l $7E0036,x
    ora.l !na
    sta.l !na
    lda.l $7E003B,x
    ora.l !nd
    sta.l !nd
+   dex
    bpl -
    plx
    rts

sfx:                                ; A = group 2 (menu) SFX: 1 move, 3 back, 4 accept
    phx
    phy
    pha
    lda #$02
    xba
    pla
    jsl $C00CED
    ply
    plx
    rts

undim:
    lda.l !dim
    beq +
    phx
    ldx #$11
-   lda.l !sv,x
    sta.l $7E0306,x
    dex
    bpl -
    lda.l !ch
    sta.l $7E0AEA
    plx
    lda #$00
    sta.l !dim
+   rts

; --- NMI (pick_nmi, after the VRAM queue; DBR 0, forced blank)
pause_nmi:
    php
    sep #$30
    lda.l !sig
    cmp #$5A
    bne .quit
    lda $4212                       ; past the VBlank (SB5's NMI work ran long): VRAM / CGRAM writes
    bpl .quit                       ; would be lost, next NMI
    lda.l !bdf                      ; color 0 back once the panel is gone
    beq +
    lda.l !dim
    beq ++
    lda.l !st
    cmp #$01
    beq +
++  stz $2121
    lda.l !bd
    sta $2122
    lda.l !bd+1
    sta $2122
    lda #$00
    sta.l !bdf
+   rep #$20                        ; SB5's queue not done: it ran out of VBlank (the screen may be
    lda.l $7E0355                   ; back on, VRAM writes would be lost); next NMI
    cmp.l $7E0357
    sep #$20
    bne .quit
    lda.l !st
    cmp #$01
    beq +
    jmp .closed
+   lda.l $7E1D1D
    bne +
.quit:
    plp
    rtl
+
    lda.l !tiles
    bne .rows
    lda #$80
    sta $2115
    rep #$20
    lda #!GLYPHVRAM                 ; the stage's tiles -> !buf
    sta $2116
    lda $2139                       ; dummy word: the read latch gives the first word twice
    lda #$3981                      ; B -> A, mode 1, $2139/$213A
    sta $4300
    lda.w #!buf&$FFFF
    sta $4302
    lda #!GLYPHBYTES
    sta $4305
    sep #$20
    lda.b #!buf>>16
    sta $4304
    lda #$01
    sta $420B
    rep #$20
    lda #!GLYPHVRAM                 ; the glyphs
    sta $2116
    lda #$1801
    sta $4300
    lda.w #!GLYPHS&$FFFF
    sta $4302
    lda #!GLYPHBYTES
    sta $4305
    sep #$20
    lda.b #!GLYPHS>>16
    sta $4304
    lda #$01
    sta $420B
    sta.l !tiles
.rows:
    lda.l !dim
    beq +
    lda #$80                        ; SB5 reloads $0AEA from $033E now and then ($0AE9)
    sta.l $7E0AEA
    lda #$01                        ; HDMA 7: window 1 left / right per line ($0AEA enables it)
    sta $4370
    lda #$26
    sta $4371
    rep #$20
    lda.w #!HDMA&$FFFF
    sta $4372
    sep #$20
    lda.b #!HDMA>>16
    sta $4374
    lda.l !bdf                      ; backdrop black (inside the panel the main screen is BG3 over it)
    bne ++
    stz $2121
    lda $213B
    sta.l !bd
    lda $213B
    and #$7F
    sta.l !bd+1
    lda #$01
    sta.l !bdf
++  stz $2121
    stz $2122
    stz $2122
+   lda #$01                        ; the frame's top row and sides
    jsr frame
    ldx #$00                        ; STAGE rows (pm_tick builds them in !lbuf)
-   rep #$20
    lda #!LVRAM+!LC0
    cpx #$00
    beq +
    lda #!LVRAM+!LC0+32
+   sta $2116
    lda #$1801
    sta $4300
    lda.w #!lbuf&$FFFF
    cpx #$00
    beq +
    lda.w #(!lbuf+$30)&$FFFF
+   sta $4302
    lda #$0030
    sta $4305
    sep #$20
    lda.b #!lbuf>>16
    sta $4304
    lda #$01
    sta $420B
    inx
    cpx #$02
    bne -
    lda.l !scr                      ; every NMI, after SB5's queue: its PAUSE! / WORLD writes (fills
    jsr rows                        ; of whole rows) keep coming for a few frames
.out:
    plp
    rtl
.closed:
    cmp #$00
    bne .out                        ; leaving the stage: the next scene loads its own
    lda.l !tiles
    beq .out
    lda #$00                        ; blank rows, then the stage's tiles back
    jsr frame
    lda #$00
    jsr rows
    rep #$20
    lda #!GLYPHVRAM
    sta $2116
    lda #$1801
    sta $4300
    lda.w #!buf&$FFFF
    sta $4302
    lda #!GLYPHBYTES
    sta $4305
    sep #$20
    lda.b #!buf>>16
    sta $4304
    lda #$01
    sta $420B
    lda #$00
    sta.l !tiles
    jmp .out

rows:                               ; A = screen: !SCRBYTES bytes to BG3 rows from !ROWVRAM
    tax
    lda #$80
    sta $2115
    rep #$20
    txa
    and #$00FF
    sta.l !w
    lda #$0000                      ; * !SCRBYTES
    cpx #$00
    beq +
-   clc
    adc.w #!SCRBYTES
    dex
    bne -
+   clc
    adc.w #!SCREENS&$FFFF
    sta $4302
    lda #!ROWVRAM
    sta $2116
    lda #$1801
    sta $4300
    lda #!SCRBYTES
    sta $4305
    sep #$20
    lda.b #!SCREENS>>16
    sta $4304
    lda #$01
    sta $420B
    rts

frame:                              ; A = 1 frame, 0 blank: row !TOPROW, sides of the rows below
    tax
    lda #$80
    sta $2115
    rep #$20
    lda #!TOPVRAM
    sta $2116
    txa
    and #$00FF
    beq +
    lda.w #!TOPROW&$FFFF
    bra ++
+   lda.w #!BLANKROW&$FFFF
++  sta $4302
    lda #$1801
    sta $4300
    lda #$0040
    sta $4305
    sep #$20
    lda.b #!TOPROW>>16
    sta $4304
    lda #$01
    sta $420B
    rep #$20
    ldy #!SIDEROWS
    lda #!TOPVRAM+32+!PLEFT
-   sta $2116
    pha
    lda #!BLANK
    cpx #$00
    beq +
    lda #!LEFT
+   sta $2118
    pla
    pha
    clc
    adc.w #!SIDEGAP
    sta $2116
    lda #!BLANK
    cpx #$00
    beq +
    lda #!RIGHT
+   sta $2118
    pla
    clc
    adc #$0020
    dey
    bne -
    sep #$20
    rts

label:                              ; STAGE w-s -> !lbuf (rows LROW/+1, columns LC0-LC1; main loop, not NMI)
    phx
    phy
    phb
    lda #$7F
    pha
    phk
    plb
    lda.l $7E102F                   ; SB5 writes the digits ($1CB7, $1CB9-$1CBA) for stages $0D-$66 only
    cmp #$67
    bcc .num
    sec                             ; bosses: World 1's numbers (pause.py BOSSNUM), else no label
    sbc #$67
    cmp.b #bossend-bossnum
    bcs .none
    tax
    lda.w bossnum,x
    beq .none
    pha
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !dw
    lda #$00
    sta.l !dt
    pla
    and #$0F
    sta.l !du
    bra .cells
.none:
    ldx #$00
    jmp .count
.num:
    lda.l $7E1CB7
    sta.l !dw
    lda.l $7E1CB9
    sta.l !dt
    lda.l $7E1CBA
    sta.l !du
.cells:
    rep #$10
    ldx #$0000
-   lda.w ltop,x                    ; "STAGE "
    sta.l !lt,x
    lda.w lbot,x
    sta.l !lb,x
    inx
    cpx #$000C
    bne -
    sep #$10
    ldx #$0C
    lda.l !dw                       ; world digit
    jsr .digit
    lda #$0A                        ; "-"
    jsr .digit
    lda.l !dt                       ; stage: tens (when not 0), units
    beq +
    jsr .digit
+   lda.l !du
    jsr .digit
.count:
    txa
    lsr a
    sta.l !ln
    eor #$FF
    sec
    adc #$10                        ; centered on column 16
    lsr a
    clc
    adc #$08
    sta.l !lc
    plb
    ldy #$00                        ; !lbuf: top row then bottom, columns LC0..LC1
.row:
    lda #!LC0
.col:
    pha
    sec
    sbc.l !lc
    cmp.l !ln
    bcs .blank
    asl a
    tax
    cpy #$30
    bcs +
    lda.l !lt,x
    sta.w !lbuf&$FFFF,y
    lda.l !lt+1,x
    bra .put
+   lda.l !lb,x
    sta.w !lbuf&$FFFF,y
    lda.l !lb+1,x
    bra .put
.blank:
    lda.b #!BLANK
    sta.w !lbuf&$FFFF,y
    lda.b #!BLANK>>8
.put:
    sta.w (!lbuf+1)&$FFFF,y
    iny
    iny
    pla
    inc a
    cmp #!LC1+1
    bne .col
    cpy #$60
    bne .row
    plb
    ply
    plx
    rts
.digit:                             ; A = 0-9, $0A "-": SB5's big font
    clc
    adc #$82
    sta.l !lt,x
    clc
    adc #$10
    sta.l !lb,x
    lda #$20
    sta.l !lt+1,x
    sta.l !lb+1,x
    inx
    inx
    rts

bossnum:                            ; stage $67 + i: world << 4 | stage (0 = none)
    db !BOSSNUM
bossend:
ltop:
    dw !LS0, !LS0+1, !LS0+2, !LS0+3, !LS0+4, !BLANK
lbot:
    dw !LS0+$10, !LS0+$11, !LS0+$12, !LS0+$13, !LS0+$14, !BLANK

; --- stage intro (JSL from $C5:0CEB, set 4 chosen; M/X 8-bit): set 4 arrangement $E0 = "STAGE  -"
; (features/world1.py) and SB5's digits $EA+, centred on column 16, stage number without its leading 0
intro_label:
    lda.l $7E102F
    asl a
    tax
    rep #$20
    lda.l $808A8A,x                 ; decimal word: world * 1000 + stage
    sep #$20
    jsl $C04672                     ; -> digits $1CB6-$1CBA
    lda #$09                        ; cells: STAGE, gap, w, -, s (+ the tens)
    ldx $1CB9
    beq +
    inc a
+   eor #$FF
    sec
    adc #$10
    lsr a
    clc
    adc #$08
    pha                             ; first column
    sta $1D28
    lda #$0E
    sta $1D2A
    lda #$E0
    jsl $C00009
    lda $01,s
    clc
    adc #$06
    sta $1D28
    lda #$0E
    sta $1D2A
    lda $1CB7
    clc
    adc #$EA
    jsl $C00009
    lda $01,s                       ; the digit's blank cell covered $E0's dash: set 4 $C6 = "-"
    clc
    adc #$07
    sta $1D28
    lda #$0E
    sta $1D2A
    lda #$C6
    jsl $C00009
    lda $01,s
    clc
    adc #$08
    sta $01,s
    lda $1CB9
    beq +
    lda $01,s
    sta $1D28
    inc a
    sta $01,s
    lda #$0E
    sta $1D2A
    lda $1CB9
    clc
    adc #$EA
    jsl $C00009
+   pla
    sta $1D28
    lda #$0E
    sta $1D2A
    lda $1CBA
    clc
    adc #$EA
    jsl $C00009
    rtl

end:
print "SYM pm_open ", hex(pm_open)
print "SYM pm_tick ", hex(pm_tick)
print "SYM pause_nmi ", hex(pause_nmi)
print "SYM intro_label ", hex(intro_label)
print "SYM end ", hex(end)
