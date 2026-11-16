; Character + color selection in the Normal Game, laid out like the SB6 fan
; game's SkinSelect scene (tools/sb6/features/picker.py has the overview).
;
; Confirming a file (New Game $C7:10E2, Continue $C7:0E27) calls the scripts
; below instead of the fade $C7:124C: fade, then Battle's character picker
; ($C6:89CF) for its screen (checker, frame, title). When its task (9)
; reaches the picker's main loop ($C6:8E68) it is sent to `pk_loop` instead,
; a script op that sleeps every frame while pick_tick / pick_nmi run the SB6
; picker; when it is done the task goes on at $C6:8EC4 (the stock end:
; fade-out, `00` back to our script). B on player 1 leaves with $1040 = $FF:
; the menu's graphics are loaded again and the file list comes back. The
; script variables the picker uses are saved around it.
;
; Native code is reached from a script through `FF 1A nn` (handler
; $C1:467C, its table entry at $C2:069B now points here): nn >= $F0 is ours.
;
; Screen: BG1 inside the frame (rows 5-24) is ours: portraits at rest
; (BG palettes 3, 4, 7) and the one under the cursor (5, 6), tiles $160+.
; OBJ: the whole OAM shadow is rewritten every frame (the stock objects of
; the picker stay alive but are never drawn): the cursor and the player
; cursors in OBJ palette 4 (tiles 0-11, 16+), the characters of the player
; row in palettes 0-3 (tiles $100 + $40 * seat, two halves of $20).
;
; State: $7F:FF00-$7F:FF7F (the choices, kept for the campaign) and
; $7F:FC00-$7F:FC7F (the screen) (docs/FREE_SPACE.md).

asar 1.90
hirom

!count   = $0129        ; players (asm/coop.asm)
!benched = $0144
!bossst  = $0155

!PK      = $7FFF00
!live    = !PK+$00      ; 1 = the picker runs for the Normal Game
!on      = !PK+$01      ; 1 = the campaign uses the choices below
!char    = !PK+$02      ; 5 bytes: choice (1-9)
!col     = !PK+$08      ; 5 bytes: color
!save1   = !PK+$10      ; $1032-$104F
!save2   = !PK+$30      ; $1D20-$1D3F
!s0      = !PK+$58      ; scratch
!s1      = !PK+$59
!s2      = !PK+$5A
!s3      = !PK+$5B
!w0      = !PK+$60      ; word scratch
!palpend = !PK+$69      ; 1 = the CGRAM shadow changed (sent once the VRAM queue is empty)
!fadein  = !PK+$6A      ; 1 = back from the picker: fade the file list in

; screen state, bank $7F (DB = $7F in the tick: short addresses)
!st      = $FC00        ; 0 waiting for SB5's setup, 1 loading, 2 choosing, 3 all chosen, 5 fading out, 4 leaving
!job     = $FC01        ; word: next record of pk_jobs
!act     = $FC03        ; seat choosing ($FF none)
!hov     = $FC04        ; cell shown with its cursor face ($FF none)
!hovw    = $FC05        ; cell the NMI must show next
!hjob    = $FC06        ; 1 = the NMI swaps the cells
!hcell   = $FC07        ; character / color in the hover palettes
!hcol    = $FC08
!tick    = $FC09        ; cursor corners (0-119)
!wait    = $FC0A        ; frames before leaving
!tint    = $FC0B        ; word: cursor color sent
!conf    = $FC10        ; 4: 1 = confirmed
!pidx    = $FC14        ; 4: cursor cell of each seat
!pchar   = $FC18        ; 4: confirmed character
!pcol    = $FC1C        ; 4: confirmed color
!kind    = $FC20        ; 4: player row animation 0 none / 1 walk / 2 victory
!achar   = $FC24        ; 4: its character
!step    = $FC28        ; 4: step of the sequence
!tim     = $FC2C        ; 4: frames left on the step
!want    = $FC30        ; 4: pose to show ($FF none)
!shown   = $FC34        ; 4: pose in VRAM ($FF none)
!half    = $FC38        ; 4: VRAM half shown (0 / 1)
!epal    = $FC3C        ; 4: palette id in OBJ palette 0-3 + seat
!edim    = $FC40        ; 4: 1 = dimmed
!stop    = $FC44        ; 4: 1 = the victory reached its last pose
!oi      = $FC50        ; word: OAM offset of the next sprite
!ox      = $FC52
!oy      = $FC53
!ot      = $FC54
!oa      = $FC55
!big     = $FC56
!cx      = $FC57
!cy      = $FC58
!e       = $FC59
!t0      = $FC5A        ; word scratch
!t1      = $FC5C
!t2      = $FC5E
!lim     = $FC60        ; poses sent this NMI
!SL      = $7FFC00      ; the same with long addresses
!SLst    = $7FFC00

!DBANK   = (!PK_BGMAP>>16)
!nt0     = !SL+$70      ; NMI scratch (words)
!nt1     = !SL+$72
!nt2     = !SL+$74
!WAITF   = 72           ; frames from the last confirmation to the fade (its victory plays)

org !E4

script_new:
    db $24,$4C,$12,$C7              ; the file menu's own fade
    db $FF,$1A,$F0                  ; open
    db $24,$CF,$89,$C6              ; Battle's character picker (its screen; our picker inside)
    db $FF,$1A,$F1                  ; close; B: drops the call, skips the 00
    db $00
    db $24 : dl menu_gfx            ; the menu's graphics again
    db $FF,$1A,$F2                  ; -> $C7:100E, the New Game file list
script_cont:
    db $24,$4C,$12,$C7
    db $FF,$1A,$F0
    db $24,$CF,$89,$C6
    db $FF,$1A,$F1
    db $00
    db $24 : dl menu_gfx
    db $FF,$1A,$F3                  ; -> $C7:0D59, the Continue file list

; The part of the menu's loader script ($C7:0B47) that the picker's screen
; replaced (VRAM $08F0-$15EF and the BG2 map; $1600-$1F1F, the portraits,
; is archive $93's tail; the tiles below $08F0 are the same on both
; screens). The first archive sent after the picker comes out wrong (the
; menu sends $0C before $22; seen in Mesen, cause not traced), so $22 is
; sent again at the end.
menu_gfx:
    db $26,$03
    db $29,$22,$F0,$08
    db $29,$6D,$50,$0A
    db $29,$1C,$10,$0F
    db $29,$93,$C0,$10
    db $29,$22,$F0,$08
    db $2A,$0E
    db $FF,$8E,$4A,$04,$02,$00,$00
    db $FF,$8E,$4A,$04,$02,$20,$00
    db $00

; task 9 runs this instead of the stock main loop
pk_loop:
    db $FF,$1A,$F4

; ---------------------------------------------------------------------------
; FF 1A nn (M/X 8-bit, [$0D] = operand, $0A-$0C = next op, $73 = task).
pick_op:
    lda [$0D]
    cmp #$F0
    bcs +
    jml $C1467C
+
if !TITLE_OP
    cmp #$F8                        ; F8-FC: the animated title (asm/title_anim.asm)
    bcc +
    jml !TITLE_OP
+
endif
if !WMAP_OP
    cmp #$F5                        ; F5: world map zone setup (asm/world_map.asm)
    bne +
    jml !WMAP_OP
+
endif
    cmp #$F4
    bne +
    brl .wait
+   phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp #$F1
    beq .close
    bcc .open
    pha                             ; ---- F2 / F3: go to a file list
    lda #$01                        ; the screen is dark (the picker faded out)
    sta.l !fadein
    pla
    ldx #$0E
    ldy #$10                        ; $C7:100E
    cmp #$F2
    beq +
    ldx #$59                        ; $C7:0D59
    ldy #$0D
+   stx $0A
    sty $0B
    lda #$C7
    sta $0C
    plb
    rtl

.open:
    ldx #$1D
-   lda $1032,x
    sta.l !save1,x
    dex
    bpl -
    ldx #$1F
-   lda $1D20,x
    sta.l !save2,x
    dex
    bpl -
    ldx #$04
-   lda #!OFFSEAT
    cpx !count
    bcs +
    lda #$01
+   sta $6269,x
    txa
    sta.l !col,x                    ; default colors: P1 white, P2 black, P3 red, P4 blue
    dex
    bpl -
    stz $1038
    lda #$04
    sta $1031
    lda #$01
    sta.l !live
    lda #$00
    sta.l !on
    sta.l !palpend
    ldx #$7F
-   sta.l !SL,x
    dex
    bpl -
    plb
    rtl

.close:
    rep #$30                        ; the picker's sprites go (the OAM builder only
    ldx #$01FC                      ; hides the ones it drew itself)
-   lda #$E000
    sta $08BF,x
    dex
    dex
    dex
    dex
    bpl -
    ldx #$001E
-   stz $0ABF,x
    dex
    dex
    bpl -
    sep #$30
    lda $1040
    sta.l !s1                       ; $FF = left with B
    ldx #$04
-   lda $625F,x
    sta.l !char,x
    dex
    bpl -
    ldx #$1D
-   lda.l !save1,x
    sta $1032,x
    dex
    bpl -
    ldx #$1F
-   lda.l !save2,x
    sta $1D20,x
    dex
    bpl -
    lda #$03
    sta $1031
    lda #$00
    sta.l !live
    sta.l !SLst
    lda.l !s1
    bne .cancel
    lda #$01
    sta.l !on
    jsl pick_apply
    plb
    rtl
.cancel:
    lda #$00
    sta.l !on
    rep #$20                        ; drop the call from the file's script
    lda $10
    sec
    sbc #$0003
    sta $10
    inc $0A                         ; and skip the script's 00
    sep #$20
    ldx $73
    dec $0CFF,x
    plb
    rtl

.wait:
    lda.l !SLst                     ; ---- F4: the picker runs; leave when it says so
    cmp #$04
    bne .again
    lda #$C4                        ; $C6:8EC4: the stock end of the picker
    sta $0A
    lda #$8E
    sta $0B
    lda #$C6
    sta $0C
    rtl
.again:
    ; the task sleeps: its saved script pointer goes back to this op and it
    ; resumes in the interpreter ($C2:0211), see asm/title_anim.asm
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
; The choices go to the bombers: character $16C2+seat, palette $16DA+seat.
; Called after the player reset ($C4:28B4) and from the close op. Keeps all.
pick_apply:
    php
    sep #$30
    pha
    phx
    lda.l !on
    cmp #$01
    bne .out
    lda.l $7E1D1A                   ; Battle
    and #$01
    bne .out
    ldx #$00
-   txa
    cmp.l $7E0000|!count
    bcs .out
    lda.l !char,x
    dec a
    cmp #$09
    bcs +
    sta.l $7E16C2,x
    pha
    lda.l !col,x
    sta.l !s1
    pla
    jsr palid
    sta.l $7E16DA,x
+   inx
    cpx #$04
    bcc -
.out:
    plx
    pla
    plp
    rtl

; A = character (0-8), !s1 = color: A = palette id of set 0 (chpal + color,
; asm/bombers.asm; chpal 0 = the cartridge's).
palid:
    phx
    tax
    lda.l chpal,x
    beq +
    clc
    adc.l !s1
    plx
    rts
+   lda.l $80BB4E,x
    clc
    adc.l !s1
    plx
    rts

; Stage spawn ($C2:1697): again, unless seats are lent to boss rivals.
pick_spawn:
    php
    sep #$20
    pha
    lda.l $7E0000|!bossst
    ora.l $7E0000|!benched
    bne +
    jsl pick_apply
+   pla
    plp
    rtl

; ---------------------------------------------------------------------------
; Once per frame (main loop, after the tasks and the OAM builder).
pick_tick:
    php
    phb
    sep #$30
    lda #$7E
    pha
    plb
    lda $1031
    cmp #$02                        ; title: a new session
    bne +
    lda #$00
    sta.l !on
    sta.l !live
    sta.l !SLst
    sta.l !fadein
if !SCLR
    jsl !SCLR                       ; streamed poses (asm/bombers.asm)
endif
    bra .out
+   cmp #$03
    bne +
    lda.l !fadein
    cmp #$01
    bne .out
    jsr fadein
    bra .out
+   cmp #$04
    bne .out
    lda.l !live
    cmp #$01
    bne .out
    lda #$7F
    pha
    plb
    jsr np_tick
.out:
    plb
    plp
    rtl

; back on the file list: once the menu's graphics are in VRAM (queue
; empty), brightness 0 -> 15, one step per tick (DB = $7E)
fadein:
    rep #$20
    lda $0355
    cmp $0357
    sep #$20
    bne .out
    lda $0300
    bpl +
    lda #$00
    bra ++
+   inc a
++  sta $0300
    cmp #$0F
    bcc .out
    lda #$00
    sta.l !fadein
.out:
    rts

np_tick:
    lda !st
    bne .loaded
    lda #$02                        ; SB5's setup: only the background shows
    sta.l $7E030F
    lda.l $7E0CE0                   ; task 9 at the stock main loop?
    cmp #$C6
    bne +
    lda.l $7E0CB8
    cmp #$8E
    bne +
    lda.l $7E0C90
    cmp #$68
    bne +
    jsr redirect
    jsr setup
    lda #$01
    sta !st
+   rts
.loaded:
    cmp #$01
    bne +
    lda #$02
    sta.l $7E030F
    rts
+   lda #$13                        ; BG1, BG2, sprites
    sta.l $7E030F
    lda !st
    cmp #$02
    bne +
    jsr logic
+   lda.l !SL+$76                   ; video frames since the last tick (the picker runs at 30 Hz)
    sec
    sbc.l !SL+$77
    beq .anim
    cmp #$05
    bcc +
    lda #$04
+   sta $FC78
    lda.l !SL+$76
    sta.l !SL+$77
-   lda $FC78
    beq .anim
    dec $FC78
    jsr anims
    bra -
.anim:
    jsr colors
    jsr oam
    lda !st
    cmp #$03
    bne +
    dec !wait
    bne +
    lda #$05
    sta !st
+   lda !st
    cmp #$05                        ; fade-out: the stock end and the file script
    bne +                           ; load graphics with the screen still on
    lda.l $7E0300                   ; INIDISP shadow
    and #$0F
    beq .dark
    dec a
    sta.l $7E0300
    bra +
.dark:
    lda #$80                        ; forced blank until the next screen fades in
    sta.l $7E0300
    lda #$04
    sta !st
+   jsr palflush
    rts

; task 9 resumes in pk_loop
redirect:
    lda.b #pk_loop
    sta.l $7E0C90
    lda.b #pk_loop>>8
    sta.l $7E0CB8
    lda.b #pk_loop>>16
    sta.l $7E0CE0
    lda #$11
    sta.l $7E0BBF+9
    lda #$02
    sta.l $7E0BE7+9
    lda #$C2
    sta.l $7E0C0F+9
    lda #$00
    sta.l $7E0B97+9
    rts

; first state, the colors of the portraits at rest and of the cursors
setup:
    rep #$20
    lda.w #!PK_JOBS&$FFFF
    sta !job
    sep #$20
    lda #$FF
    sta !act
    sta !hov
    sta !hovw
    sta !hcell
    sta !hcol
    ldx #$03
-   sta !want,x
    sta !shown,x
    stz !kind,x
    stz !conf,x
    stz !pidx,x
    stz !half,x
    stz !epal,x
    dex
    bpl -
    rep #$30
    ldx #$0000                      ; [CGRAM byte offset, 15 colors] per palette
    ldy.w #!NSTATIC
.pal:
    phy
    lda.l !PK_STATIC,x
    tay
    inx
    inx
    lda #$000F
    sta !t0
-   lda.l !PK_STATIC,x
    phx
    tyx
    sta.l $7E2912,x
    plx
    inx
    inx
    iny
    iny
    dec !t0
    bne -
    ply
    dey
    bne .pal
    ldx #$0000
-   lda.l !PK_PAL4,x
    sta.l $7E2912+$180,x            ; OBJ palette 4 (CGRAM 192)
    inx
    inx
    cpx #$001E
    bcc -
    sep #$30
    lda #$01
    sta.l !palpend
    rts

; ---------------------------------------------------------------------------
; Pad of the seat choosing: arrows (new or repeated, $40+pad: right 1,
; left 2, down 4, up 8), L / R color, A / Start confirm, B back.
logic:
    ldx #$00
-   txa
    cmp.l $7E0000|!count
    bcs .none
    lda !conf,x
    beq .found
    inx
    cpx #$04
    bcc -
.none:
    lda #$FF
    sta !act
    rts
.found:
    stx !act
    lda $40,x
    and #$0F
    beq .lr
    jsr move
    rts
.lr:
    lda $36,x
    and #$30
    beq .ab
    jsr recolor
    rts
.ab:
    lda $36,x
    and #$08
    beq +
    jsr back
    rts
+   lda $36,x
    and #$81
    beq +
    jsr confirm
+   rts

; A = arrows, X = seat
move:
    sta !t0
    lda !pidx,x
    sta !t1                         ; old
    jsr colrow                      ; !t2 = column, A = row start
    sta !t1+1
    lda !t0
    lsr a
    bcc .left
    lda !t1+1                       ; right: next in the row, wraps
    clc
    adc #!GCOLS-1
    jsr clampn
    cmp !t1
    beq +
    bcc +
    lda !t1
    inc a
    bra .set
+   lda !t1+1
    bra .set
.left:
    lsr a
    bcc .down
    lda !t2
    beq +
    lda !t1
    dec a
    bra .set
+   lda !t1+1
    clc
    adc #!GCOLS-1
    jsr clampn
    bra .set
.down:
    lsr a
    bcc .up
    lda !t1
    clc
    adc #!GCOLS
    cmp #!N
    bcc .set
    lda !t2
    bra .fit
.up:
    lda !t1
    sec
    sbc #!GCOLS
    bcs .set
    lda #!LASTROW                   ; the same column on the last row
    clc
    adc !t2
.fit:
-   cmp #!N
    bcc .set
    sec
    sbc #!GCOLS
    bcs -
    lda #$00
.set:
    cmp !t1
    beq +
    sta !pidx,x
    jsr fitcol
    lda #$01                        ; cursor move
    jsr sfx
+   rts

; A = cell: !t2 = column, A = first cell of its row
colrow:
    sta !t2
    lda #$00
-   pha
    lda !t2
    cmp #!GCOLS
    bcc +
    sbc #!GCOLS
    sta !t2
    pla
    clc
    adc #!GCOLS
    bra -
+   pla
    rts

; A = min(A, N - 1)
clampn:
    cmp #!N
    bcc +
    lda #!N-1
+   rts

; the seat's color must exist for the character under its cursor
fitcol:
    phx
    lda !pidx,x
    tay
    lda.l !col,x
    tyx
    cmp.l chcol,x
    plx
    bcc +
    lda #$00
    sta.l !col,x
+   rts

; L / R: previous / next color of the character under the cursor
recolor:
    sta !t0
    lda !pidx,x
    phx
    tax
    lda.l chcol,x
    plx
    sta !t1
    lda !t0
    and #$10
    beq .l
    lda.l !col,x
    inc a
    cmp !t1
    bcc .set
    lda #$00
    bra .set
.l: lda.l !col,x
    bne +
    lda !t1
+   dec a
.set:
    sta.l !col,x
    lda #!PALSFX
    jsr sfx
    rts

; B: the previous player chooses again; nobody before: back to the files
back:
    dex
    bmi .leave
-   lda !conf,x
    bne +
    dex
    bpl -
    bra .leave
+   stz !conf,x
    lda #$03
    jsr sfx
    rts
.leave:
    lda #$FF
    sta.l $7E1040
    lda #$05
    sta !st
    lda #$03
    jsr sfx
    rts

; A / Start: the character and color, unless another player has them
confirm:
    stx !e
    ldy #$00
-   cpy !e
    beq +
    lda !conf,y
    beq +
    lda !pchar,y
    cmp !pidx,x
    bne +
    phx
    tyx
    lda.l !col,x
    plx
    cmp.l !col,x
    bne +
    lda #$03                        ; taken
    jsr sfx
    rts
+   iny
    cpy #$04
    bcc -
    lda !pidx,x
    sta !pchar,x
    lda.l !col,x
    sta !pcol,x
    lda #$01
    sta !conf,x
    lda #$04
    jsr sfx
    ldx #$00                        ; everybody chose: the picker's outputs
-   txa
    cmp.l $7E0000|!count
    bcs .all
    lda !conf,x
    beq .out
    inx
    bra -
.all:
    ldx #$00
-   txa
    cmp.l $7E0000|!count
    bcs +
    lda !pchar,x
    inc a
    sta.l $7E625F,x
    lda !pcol,x
    sta.l $7E6264,x
    inx
    bra -
+   lda #$00
    sta.l $7E1040
    lda #!WAITF
    sta !wait
    lda #$03
    sta !st
    lda #$FF
    sta !act
.out:
    rts

; A = SFX id (group 2)
sfx:
    phx
    phy
    phb
    pha
    lda #$7E
    pha
    plb
    lda #$02
    xba
    pla
    jsl $C00CED
    plb
    ply
    plx
    rts

; ---------------------------------------------------------------------------
; Player row: what each seat shows and its sequence (walk down, looping;
; victory once, then its last pose).
anims:
    ldx #$00
.seat:
    txa
    cmp.l $7E0000|!count
    bcc +
    rts
+   lda !conf,x
    beq +
    lda #$02
    ldy !pchar,x
    bra .have
+   cpx !act
    bne +
    lda #$01
    ldy !pidx,x
    bra .have
+   lda #$00
    ldy #$00
.have:
    sta !t0
    sty !t0+1
    cmp !kind,x
    bne .new
    tya
    cmp !achar,x
    bne .new
    lda !kind,x
    beq .none
    lda !stop,x
    bne .next
    dec !tim,x
    bne .next
    inc !step,x
    jsr seqread                     ; A = frames (0: end), !t1 = pose
    bne .pose
    lda !kind,x
    cmp #$02
    beq +
    stz !step,x                     ; walk: again
    jsr seqread
    bra .pose
+   dec !step,x                     ; victory: stays on its last pose
    lda #$01
    sta !stop,x
    jsr seqread
    bra .pose
.new:
    lda !t0
    sta !kind,x
    lda !t0+1
    sta !achar,x
    stz !step,x
    stz !stop,x
    lda !kind,x
    beq .none
    jsr seqread
.pose:
    sta !tim,x
    lda !t1
    sta !want,x
    bra .next
.none:
    lda #$FF
    sta !want,x
.next:
    inx
    cpx #$04
    bcs +
    brl .seat
+
    rts

; seat X: A = frames of its step (Z: end of the sequence), !t1 = its pose
seqread:
    phx
    lda !step,x
    sta !t2
    lda !achar,x
    asl a
    tay
    lda !kind,x
    rep #$30
    and #$00FF
    cmp #$0002
    tyx
    bcs +
    lda.l !PK_WALKP,x
    bra ++
+   lda.l !PK_WINP,x
++  sta !t1
    lda !t2
    and #$00FF
    sta !t2
    asl a
    adc !t2
    adc !t1
    tax
    sep #$20
    lda.l !DBANK<<16,x
    sta !t1
    lda.l (!DBANK<<16)+2,x
    sep #$10
    plx
    cmp #$00
    rts

; ---------------------------------------------------------------------------
; Colors: each seat's character (OBJ palette seat; dimmed while choosing,
; as the Unity preview), the cursor, the portrait under the cursor.
colors:
    ldx #$00
.seat:
    stx !e
    txa
    cmp.l $7E0000|!count
    bcs .cursor
    lda !kind,x
    beq .next
    cmp #$02
    beq +
    lda.l !col,x                    ; choosing: under the cursor, dimmed
    sta.l !s1
    lda !pidx,x
    ldy #$01
    bra ++
+   lda !pcol,x
    sta.l !s1
    lda !pchar,x
    ldy #$00
++  sty !t0
    jsr palid
    cmp !epal,x
    bne +
    lda !t0
    cmp !edim,x
    beq .next
    lda !epal,x
+   sta !epal,x
    lda !t0
    sta !edim,x
    lda !epal,x
    pha
    txa
    asl a
    asl a
    asl a
    asl a
    ora #$80
    tax                             ; CGRAM index
    pla
    ldy #$10
    jsr upload_l
    ldx !e
    lda !edim,x
    beq .next
    jsr dim
.next:
    ldx !e
    inx
    stx !e
    cpx #$04
    bcc .seat
.cursor:
    ldx !act
    bmi .hover
    lda !pidx,x
    asl a
    tay
    lda.l !col,x
    rep #$30
    and #$00FF
    asl a
    sta !t0
    tyx
    lda.l !PK_TINTP,x
    clc
    adc !t0
    tax
    lda.l !DBANK<<16,x
    cmp !tint
    beq +
    sta !tint
    sta.l $7E2910+$184              ; OBJ palette 4, entry 2
    sep #$20
    lda #$01
    sta.l !palpend
+   sep #$30
.hover:
    lda !hjob                       ; the NMI has not swapped the cells yet
    bne .out
    ldx !act
    lda #$FF
    cpx #$04
    bcs +
    lda !pidx,x
+   cmp !hov
    beq +
    sta !hovw
    lda #$01
    sta !hjob
+   ldx !act
    cpx #$04
    bcs .out
    lda !pidx,x
    cmp !hcell
    bne +
    lda.l !col,x
    cmp !hcol
    beq .out
+   lda !pidx,x                     ; hover palettes: 30 colors of character / color
    sta !hcell
    lda.l !col,x
    sta !hcol
    jsr hovpal
.out:
    rts

; 2 x 15 colors from pk_hcol<c> + 60 * color to BG palettes 5 and 6
hovpal:
    lda !hcol
    sta.l $004202
    lda #60
    sta.l $004203
    lda !hcell
    asl a
    tax
    nop
    nop
    rep #$30
    lda.l $004216
    clc
    adc.l !PK_HCOLP,x
    tax
    ldy #$0000
-   lda.l !DBANK<<16,x
    phx
    tyx
    sta.l $7E2910+$A2,x             ; CGRAM 81-95
    plx
    inx
    inx
    iny
    iny
    cpy #$001E
    bcc -
    ldy #$0000
-   lda.l !DBANK<<16,x
    phx
    tyx
    sta.l $7E2910+$C2,x             ; CGRAM 97-111
    plx
    inx
    inx
    iny
    iny
    cpy #$001E
    bcc -
    sep #$30
    lda #$01
    sta.l !palpend
    rts

; OBJ palette of seat !e: colors 1-15 halfway to the checker behind
dim:
    lda !e
    rep #$30
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    tax
    ldy #$000F
-   lda.l $7E2910+$102,x
    lsr a
    and #$3DEF
    clc
    adc.w #(!SHADE>>1)&$3DEF
    sta.l $7E2910+$102,x
    inx
    inx
    dey
    bne -
    sep #$30
    rts

; upload with DB = $7E (A = palette id, X = CGRAM index, Y = colors)
upload_l:
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    jsr upload
    plb
    rts

; ---------------------------------------------------------------------------
; OAM shadow ($7E:08BF, 4 bytes per sprite; high bits $0ABF): the cursor,
; the characters of the player row, the player cursors; the rest hidden.
oam:
    rep #$30
    ldx #$0000
    lda #$E000
-   sta.l $7E08BF,x                 ; x 0, y $E0
    inx
    inx
    inx
    inx
    cpx #$0200
    bcc -
    lda #$0000
    ldx #$001E
-   sta.l $7E0ABF,x
    dex
    dex
    bpl -
    stz !oi
    sep #$30
    jsr cursor
    jsr row
    jsr brackets
    rts

; one sprite (!ox, !oy, !ot, !oa; !big = 16x16)
put:
    rep #$10
    ldx !oi
    cpx #$0200
    bcs .full
    lda !ox
    sta.l $7E08BF,x
    lda !oy
    sta.l $7E08C0,x
    lda !ot
    sta.l $7E08C1,x
    lda !oa
    sta.l $7E08C2,x
    lda !big
    beq +
    rep #$20
    txa
    lsr a
    lsr a
    pha
    lsr a
    lsr a
    tay                             ; high table byte
    pla
    and #$0003
    tax
    sep #$20
    lda.l bigbit,x
    tyx
    ora.l $7E0ABF,x
    sta.l $7E0ABF,x
    ldx !oi
+   inx
    inx
    inx
    inx
    stx !oi
.full:
    sep #$10
    rts

bigbit:
    db $02,$08,$20,$80

; corners (breathing 0 1 2 1, half a second each), "L / R" above, "nP" below
cursor:
    ldx !act
    cpx #$04
    bcc +
    rts
+   lda !pidx,x
    tay
    tyx
    lda.l !PK_CELLX,x
    sta !cx
    lda.l !PK_CELLY,x
    sta !cy
    stz !big
    lda #$38                        ; priority 3, palette 4
    sta !oa
    lda !tick
    inc a
    cmp #120
    bcc +
    lda #$00
+   sta !tick
    ldx #$00
-   cmp #30
    bcc +
    sbc #30
    inx
    bra -
+   lda.l breathe,x
    sta !e
    ldx #$00                        ; four corners: x, y = center +- (20 + e) / (12 + e)
.corner:
    lda !cx
    clc
    adc.l cdx,x
    jsr signe
    sta !ox
    lda !cy
    clc
    adc.l cdy,x
    jsr signe2
    sta !oy
    stx !ot
    phx
    jsr put
    plx
    inx
    cpx #$04
    bcc .corner
    ldx #$00                        ; L / R and the number
.glyph:
    lda !cx
    clc
    adc.l gdx,x
    sta !ox
    lda !cy
    clc
    adc.l gdy,x
    sta !oy
    lda.l gtile,x
    cpx #$03
    bne +
    clc
    adc !act                        ; the player's digit
+   sta !ot
    phx
    jsr put
    plx
    inx
    cpx #$05
    bcc .glyph
    rts

; corner offsets: x / y with the sign of the expansion in X: A -= e for the
; left / top corners, += e for the right / bottom ones
signe:
    pha
    txa
    and #$01                        ; TR, BR: right
    bra signc
signe2:
    pha
    txa
    and #$02                        ; BL, BR: bottom
signc:
    beq +
    pla
    clc
    adc !e
    rts
+   pla
    sec
    sbc !e
    rts

breathe:
    db 0,1,2,1
cdx:
    db -20,12,-20,12
cdy:
    db -20,-20,12,12
gdx:
    db -8,-2,3,-8,0
gdy:
    db -24,-24,-24,12,12
gtile:
    db 4,5,6,7,11

; the characters of the player row, from the poses in VRAM
row:
    lda #$01
    sta !big
    ldx #$00
.seat:
    stx !e
    txa
    cmp.l $7E0000|!count
    bcc +
    brl .out
+
    lda !kind,x
    beq .next
    lda !shown,x
    cmp #$FF
    beq .next
    jsr entryxy                     ; !cx, !cy: feet
    ldx !e
    lda !shown,x
    rep #$30
    and #$00FF
    sta !t0
    asl a
    adc !t0
    tax
    lda.l !PK_POSEP,x
    sta $A8
    sep #$20
    lda.l !PK_POSEP+2,x
    sta $AA
    sep #$10
    lda [$A8]                       ; blocks
    beq .next
    sta !t1
    ldx !e                          ; tile = $40 * seat + $20 * half + 2k (second table)
    lda !half,x
    asl a
    asl a
    asl a
    asl a
    asl a
    sta !t2
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    ora !t2
    sta !ot
    txa
    asl a
    ora #$31                        ; priority 3, palette = seat, second table
    sta !oa
    ldy #$01
.block:
    lda [$A8],y
    clc
    adc !cx
    sta !ox
    iny
    lda [$A8],y
    clc
    adc !cy
    sta !oy
    iny
    phy
    jsr put
    ply
    lda !ot
    clc
    adc #$02
    sta !ot
    dec !t1
    bne .block
.next:
    ldx !e
    inx
    cpx #$04
    bcs +
    brl .seat
+
.out:
    stz !big
    rts

; seat !e: !cx = its cursor's x, !cy = feet; A = cursor x
entryxy:
    lda.l $7E0000|!count
    dec a
    asl a
    asl a
    clc
    adc !e
    tax
    lda.l !PK_ENTX,x
    pha
    clc
    adc #16
    sta !cx
    lda #!ENTY+!FEET
    sta !cy
    pla
    rts

; the player cursors (Unity P1-P4 Cursor): bright when confirmed, dimmer
; while choosing, dimmest while waiting
brackets:
    stz !big
    lda #$38
    sta !oa
    ldx #$00
.seat:
    stx !e
    txa
    cmp.l $7E0000|!count
    bcs .out
    jsr entryxy
    sta !cx
    ldx !e
    ldy #$02
    lda !conf,x
    beq +
    ldy #$00
    bra ++
+   cpx !act
    bne ++
    ldy #$01
++  sty !t0                         ; step; tile = BTILE + BN * (3 * seat + step)
    txa
    asl a
    adc !e
    adc !t0
    sta.l $004202
    lda #!BN
    sta.l $004203
    nop
    nop
    nop
    lda.l $004216
    clc
    adc #!BTILE
    sta !ot
    ldx #$00
.tile:
    lda.l !PK_BXY,x
    clc
    adc !cx
    sta !ox
    lda.l !PK_BXY+1,x
    clc
    adc #!ENTY
    sta !oy
    phx
    jsr put
    plx
    inc !ot
    inx
    inx
    cpx #2*!BN
    bcc .tile
    ldx !e
    inx
    cpx #$04
    bcc .seat
.out:
    rts

; ---------------------------------------------------------------------------
; A = palette id of set 0 ($81:8000 + 2*(id-1) -> [dest16, count16, colors];
; ids !OWNID+ = the bombers' own palettes, table !PALTAB), X = CGRAM index,
; Y = colors. DB = $7E. Flags the CGRAM shadow when something changed.
upload:
    cmp #$00
    bne +
    rts
+
    rep #$30
    and #$00FF
    phx
    cmp.w #!OWNID
    bcs .own
    cmp #$0050
    bcs .bad
    dec a
    asl a
    tax
    lda.l $818000,x
    clc
    adc #$0004
    sta $A8
    lda #$0081
    bra .src
.own:
    sec
    sbc.w #!OWNID
    cmp.w #!PALN
    bcs .bad
    asl a
    tax
    lda.l !PALTAB,x
    clc
    adc #$0004
    sta $A8
    lda.w #!PALTAB>>16
    bra .src
.bad:
    plx
    bra .out
.src:
    sep #$20
    sta $AA
    rep #$20
    pla
    and #$00FF
    asl a
    tax
    tya
    and #$00FF
    sta.l !w0
    ldy #$0000
.loop:
    lda [$A8],y
    sta $2910,x
    inx
    inx
    iny
    iny
    lda.l !w0
    dec a
    sta.l !w0
    bne .loop
    lda #$0001
    sta.l !palpend
.out:
    sep #$30
    rts

; The CGRAM upload ($0351, NMI $C0:0244) takes time from the VRAM queue
; ($7E:8000 ring, $0355 read / $0357 write): the shadow is only flagged
; once the queue is empty.
palflush:
    lda.l !palpend
    beq +
    rep #$20
    lda.l $7E0355
    cmp.l $7E0357
    sep #$20
    bne +
    lda #$01
    sta.l $7E0351
    lda #$00
    sta.l !palpend
+   rts

; ---------------------------------------------------------------------------
; NMI ($C0:F421, JSL $C004E0 = the VRAM transfers of the frame; M/X 8-bit,
; DBR = 0, forced blank): the picker's loads, one group per NMI while the
; screen is hidden; then the portrait swaps and the poses of the player row.
pick_nmi:
    jsl $C004E0
if !TITLE_NMI
    jsl !TITLE_NMI                  ; the animated title's transfers and scroll
endif
if !WMAP_NMI
    jsl !WMAP_NMI                   ; the ZONE1 world map's sea (asm/world_map.asm)
endif
    php
    sep #$30
    lda.l !SL+$76                   ; NMIs seen: the player row counts video frames
    inc a
    sta.l !SL+$76
    lda.l !live
    cmp #$01
    bne .quit
    lda.l $7E1031
    cmp #$04
    bne .quit
    lda.l !SLst
    beq .quit
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    lda.b #!DBANK
    sta $4304
    lda.l !SLst
    cmp #$01
    bne +
    jsr nmi_load
    bra .quit
+   jsr nmi_hover                   ; C set: a swap was made (the VBlank is used up)
    bcs .quit
    jsr nmi_poses
.quit:
    plp
    rtl

; one group of pk_jobs: [vram, source, size, -, last]
nmi_load:
    rep #$30
    lda.l !SL+$01                   ; !job
    tax
.rec:
    lda.l !DBANK<<16,x
    cmp #$FFFF
    beq .done
    sta $2116
    lda.l (!DBANK<<16)+2,x
    sta $4302
    lda.l (!DBANK<<16)+4,x
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    lda.l (!DBANK<<16)+7,x
    rep #$20
    pha
    txa
    clc
    adc #$0008
    tax
    pla
    and #$0001
    beq .rec
    txa
    sta.l !SL+$01
    sep #$30
    rts
.done:
    sep #$30
    lda #$02
    sta.l !SLst
    rts

; the cell that had the cursor gets its portrait at rest back, the new one
; its cursor face (16 tiles, 4 map rows of 4 entries each)
nmi_hover:
    lda.l !SL+$06                   ; !hjob
    bne +
    clc
    rts
+   lda.l !SL+$04                   ; !hov
    cmp #$FF
    beq +
    ldx #$00
    jsr cellswap
+   lda.l !SL+$05                   ; !hovw
    sta.l !SL+$04
    cmp #$FF
    beq +
    ldx #$02
    jsr cellswap
+   lda #$00
    sta.l !SL+$06
    sec
    rts

; A = cell, X = 0 at rest / 2 cursor face
cellswap:
    rep #$30
    and #$00FF
    sta.l !nt0
    txy
    xba                             ; tiles: 512 bytes per cell
    asl a
    clc
    adc.l swaptab,x                 ; rest / cursor tiles
    sta $4302
    lda.l !nt0
    xba                             ; 256 words per cell
    clc
    adc.w #!PTILE*16
    sta $2116
    lda #$0200
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    lda.l !nt0                      ; map: 16 words per cell
    asl a
    asl a
    asl a
    asl a
    asl a
    tyx
    clc
    adc.l swaptab+4,x
    sta $4302
    lda.l !nt0
    asl a
    tax
    lda.l !PK_CELLV,x
    ldy #$0004
-   sta $2116
    pha
    lda #$0008
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    pla
    clc
    adc #$0020
    dey
    bne -
    sep #$30
    rts

swaptab:
    dw !PK_RTILES, !PK_HTILES, !PK_RMAP, !PK_HMAP

; poses: into the hidden half of the seat's VRAM, one per NMI
nmi_poses:
    lda #$00
    sta.l !SL+$60                   ; !lim
    ldx #$00
.seat:
    lda.l !SL+$30,x                 ; !want
    cmp.l !SL+$34,x                 ; !shown
    beq .next
    sta.l !SL+$34,x
    cmp #$FF
    beq .next
    lda.l !SL+$38,x                 ; !half
    eor #$01
    sta.l !SL+$38,x
    lda.l !SL+$34,x
    phx
    jsr posedma
    plx
    lda.l !SL+$60
    inc a
    sta.l !SL+$60
    cmp #$01                        ; one pose per NMI (up to 1 KB)
    bcs .out
.next:
    inx
    cpx #$04
    bcc .seat
.out:
    lda.b #!DBANK
    sta $4304
    rts

; seat X, pose A, half !half: two rows of 64 * blocks bytes
posedma:
    sta.l !nt0
    lda #$00
    sta.l !nt0+1
    txa                             ; VRAM $7000 + $400 * seat + $200 * half
    asl a
    ora.l !SL+$38,x
    rep #$30
    and #$00FF
    xba
    asl a
    clc
    adc #$7000
    sta.l !nt1
    lda.l !nt0
    asl a
    adc.l !nt0
    tax
    lda.l !PK_POSEP,x
    sta.l !nt2
    sep #$20
    lda.l !PK_POSEP+2,x
    sta $4304
    rep #$20
    lda.l !nt2
    tax
    sep #$20
    lda $4304                       ; the record's first byte, in its bank
    pha
    plb
    lda $0000,x                     ; blocks
    pha
    lda #$00
    pha
    plb
    pla
    rep #$20
    and #$00FF
    sta.l !nt0
    asl a
    inc a
    adc.l !nt2
    sta $4302                       ; top row after [n, n x (dx, dy)]
    lda.l !nt0
    xba
    lsr a
    lsr a                           ; 64 * n
    sta.l !nt0
    sta $4305
    lda.l !nt1
    sta $2116
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    lda.l !nt0
    sta $4305
    lda.l !nt1
    clc
    adc #$0100
    sta $2116
    sep #$20
    lda #$01
    sta $420B
    sep #$30
    rts

chpal:
    db !CHPAL
chcol:
    db !CHCOL

print "SYM end_e4 ", hex(pc())
print "SYM script_new ", hex(script_new)
print "SYM script_cont ", hex(script_cont)
print "SYM pick_op ", hex(pick_op)
print "SYM pick_apply ", hex(pick_apply)
print "SYM pick_spawn ", hex(pick_spawn)
print "SYM pick_tick ", hex(pick_tick)
print "SYM pick_nmi ", hex(pick_nmi)
