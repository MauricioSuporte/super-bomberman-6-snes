; SB6's Louie abilities (tools/sb6/features/louie_abilities.py; SB5 Recomp's "Louie improvements" mod and SB6
; Unity's RedLouiePunchStun / YellowLouieKick / BlackLouieDashPush / Green|BlackLouieDashAnimator), on SB5's own
; routines. Y while riding runs SB5's ability of the Louie's type ($C4:54F6, table $C4:551B by type 0-9, $8D = the
; rider, $1D39 = its Louie):
;
; * Red (type 0, $C4:5530): SB5's punch stuns a player in the cell ahead; in the Normal Game an enemy there is
;   stunned too for RED_T frames (la_red): its routine is put aside as SB5's clock does ($C4:22CC) for
;   la_frozen, which runs SB5's stop-watch routine $C3:4C13 (contact and flames still count; blinking in the last
;   second as with the clock) and gives the routine back ($C4:2319) when the time is up. One punch sound
;   (group 2 $38) for a hit, none for a miss.
; * Yellow (type 3, $C4:577D): SB5 kicks the soft block ahead (task $C4:57B8, which already passes its motion
;   on to the next soft block). A bomb ahead instead: the bomb and the resting bombs right after it in that line
;   roll away together (la_yahead / kick_row: the front one through SB5's kick $C5:2293, the others with the same
;   motion), a "train" (!TRAIN per bomb slot). A train bomb meeting a resting bomb takes it (and its row) along,
;   meeting a soft block stops and kicks the block on (la_roll, at $C5:2182); a kicked soft block stopping at a
;   bomb kicks it (la_bnext, $C4:5973).
; * Black (type 6, SB5's bosses' Louie, now also out of eggs: asm/louies.asm louie_hatch draws 0-6): no SB5
;   ability (RTS); la_black starts a dash: DASH_T frames in the facing direction at 1.6 pixels a frame (la_speed
;   at $C4:3180), the pads held that way (la_pads after the pad reader), the rider invincible (SB5's vest timer
;   $170A kept at 2: it blinks as with the vest, $15A2 bit 2). The first enemy ahead (Normal Game) is pushed
;   2 cells (2 pixels a frame,
;   stopped by walls / bombs / soft blocks; frozen meanwhile by la_frozen), the dash holds IMP_T frames and the
;   rider stays invincible INV_T frames more. Sound: group 2 $35.
; * Green (type 1, SB5's dash $C4:56DB: $1782 bit 0) and Black's dash leave afterimages (la_oam, after SB5's
;   OAM builder): the rider's and its Louie's OAM entries drawn again where they were 6 (even frames) or 12
;   (odd frames) frames before, behind the real sprites, one at a time (a flicker: see-through), GHOST_T frames
;   past the dash.
;
; Opponent bombers (a boss rival: seat >= the roster; in Battle every other bomber): SB5's Red punch already stuns
; them; the Black dash with no enemy ahead pushes the first one in its lane 2 cells, stunned as by the punch
; (bomber_hit / bomber_push). No enemy effects in boss stages ($0155, 1-7) nor in Battle. State $7F:E800-$7F:E9F8 (docs/FREE_SPACE.md).

asar 1.90
hirom

!LA      = $7FE800
!FRZ     = !LA+$00      ; 24: frames an actor stays frozen by la_frozen
!PUSH    = !LA+$18      ; 24: frames of push left
!PDIR    = !LA+$30      ; 24: push direction 1-4
!DASH    = !LA+$48      ; 5 seats: dash frames left
!CD      = !LA+$4D      ; 5: frames before the next dash
!DDIR    = !LA+$52      ; 5: dash direction 1-4
!IMP     = !LA+$57      ; 5: impact hold frames left
!INV     = !LA+$5C      ; 5: invincible frames left after the dash
!SET4    = !LA+$61      ; 5: $15A2 bit 2 set by us
!GT      = !LA+$66      ; 5: afterimage frames left
!GN      = !LA+$6B      ; 5: positions in the history
!GI      = !LA+$70      ; 5: history index
!ANY     = !LA+$75      ; something to do (dash, ghosts, cooldown)
!HX      = !LA+$80      ; 5 x 16 words: positions (x) of the last frames
!HY      = !LA+$120     ; 5 x 16 words (y)
!TRAIN   = !LA+$1C0     ; 20: bomb slot rolls in a Yellow Louie train (cleared by magnet.asm's mg_alloc)
!SCR     = !LA+$1E0     ; 24 bytes scratch
!HATCH   = !LA+$1F8     ; the next egg's Louie in the egg test stage (!EGG_STAGE)
!END     = !LA+$1F9

!RED_T   = 180
!DASH_T  = 30
!CD_T    = 40
!IMP_T   = 15                ; (0.25 s on the shoulder charge's last pose, where it hit)
!PUSH_T  = 16
!PUSH_F  = 30           ; frames a pushed enemy stays frozen
!INV_T   = 30
!GHOST_T = 12
!GSLOT   = 104          ; afterimage OAM entries stay below 104 (1-7's clown has 104-127)
!GMAX    = 16           ; entries per afterimage

org !C4

; ================================================================ helpers (M/X 8-bit, DB = a WRAM bank)
; carry set when actor X is alive (object, not dying / dead)
alive:
    lda $17FA,x
    bmi .no
    lda $15A2,x
    and #$C0
    bne .no
    sec
    rts
.no:
    clc
    rts

; carry set in a boss stage (1-6 rivals, 1-7's clown) or in Battle: no enemy effects there
no_enemies:
    lda $1D1A
    lsr a
    bcs .yes
    lda $0155
    bne .yes
    lda $1031
    cmp #$68
    beq .yes
    clc
    rts
.yes:
    sec
    rts

; A = cell: carry clear and Y = the slot of a resting bomb there (not carried, rolling, flying, held; no mine).
; Keeps A, X.
bomb_at:
    sta.l !SCR+15
    phx
    ldx #$13
-   lda $0E40,x
    beq .next
    lda $0E7C,x
    cmp.l !SCR+15
    bne .next
    lda $0E90,x
    and #$F8
    bne .next
    lda $0EE0,x
    and #$40
    bne .next
    lda $0ECC,x
    and #$20
    bne .next
    txy
    plx
    lda.l !SCR+15
    clc
    rts
.next:
    dex
    bpl -
    plx
    lda.l !SCR+15
    sec
    rts

; A = cell, X = a bomb slot: carry clear and Y = another live bomb on that cell. Keeps A, X.
other_bomb_at:
    sta.l !SCR+15
    txa
    sta.l !SCR+14
    phx
    ldx #$13
-   txa
    cmp.l !SCR+14
    beq .next
    lda $0E40,x
    beq .next
    lda $0E7C,x
    cmp.l !SCR+15
    bne .next
    txy
    plx
    lda.l !SCR+15
    clc
    rts
.next:
    dex
    bpl -
    plx
    lda.l !SCR+15
    sec
    rts

dcell: db 0, 1, 16, -1, -16                 ; cell step by direction 1 right, 2 down, 3 left, 4 up
dpad:  db 0, $01, $04, $02, $08             ; held direction bits ($31) by direction

; X = actor, A = frames: frozen by la_frozen (its routine kept as SB5's clock keeps it); the longer time wins
freeze:
    pha
    lda $155A,x
    cmp.b #la_frozen&$FF
    bne .install
    lda $1572,x
    cmp.b #la_frozen>>8&$FF
    bne .install
    lda $158A,x
    cmp.b #la_frozen>>16
    beq .set
.install:
    lda $8D
    pha
    stx $8D
    lda.b #la_frozen>>16
    sta $B0
    lda.b #la_frozen>>8&$FF
    xba
    lda.b #la_frozen&$FF
    jsl $C422CC
    pla
    sta $8D
    lda $155A,x                 ; (SB5's list of 32 kept routines was full: not frozen)
    cmp.b #la_frozen&$FF
    bne .fail
    lda #$00
    sta.l !FRZ,x
    sta.l !PUSH,x
.set:
    pla
    cmp.l !FRZ,x
    bcc +
    sta.l !FRZ,x
+   rts
.fail:
    pla
    rts

; ================================================================ Red Louie
; $C4:5560 (was JSR $5582: a player on cell A; carry clear = found, A = that player): enemies on the cell
; are stunned first (Normal Game); the punch sound once when only an enemy was hit
la_red:
    phx
    pha
    lda #$00
    sta.l !SCR+13
    jsr no_enemies
    bcs .players
    ldx #$05
-   cpx $012D
    bcs .players
    cpx #24
    bcs .players
    jsr alive
    bcc .next
    lda $16AA,x
    cmp $01,s
    bne .next
    lda #!RED_T
    jsr freeze
    lda #$01
    sta.l !SCR+13
.next:
    inx
    bra -
.players:
    pla
    plx
    jsr $5582
    bcc .rts
    lda.l !SCR+13
    beq .miss
    lda #$02
    xba
    lda #$38
    jsl $C00CED
.miss:
    sec
.rts:
    rts

; an enemy's routine while frozen (JML [$A5] from the actor loop $C4:2223: X = actor, Y = object, DB = $80)
la_frozen:
    lda.l !FRZ,x
    beq .wake
    dec a
    sta.l !FRZ,x
    beq .wake
    lda.l !PUSH,x
    beq +
    dec a
    sta.l !PUSH,x
    jsr push_step
+   lda $0E20
    pha
    lda $0E21
    pha
    lda.l !FRZ,x
    cmp #$3C
    bcs .still
    sta $0E20                   ; the last second: SB5's clock blink (1 = walking again)
    stz $0E21
    bra .run
.still:
    lda #$01
    sta $0E21
.run:
    jsl $C34C13
    pla
    sta $0E21
    pla
    sta $0E20
    rtl
.wake:
    lda #$00
    sta.l !PUSH,x
    jml $C42319

; ---------------------------------------------------------------- push: 2 pixels (X = actor, Y = its object)
pdx: dw 0, 2, 0, -2, 0
pdy: dw 0, 0, 2, 0, -2
edx: dw 8, 14, 8, 2, 8                      ; the leading edge, from the actor's position
edy: dw 8, 8, 14, 8, 2

push_step:
    phy
    txa
    sta.l !SCR+12               ; the actor
    lda.l !PDIR,x
    asl a
    tax
    rep #$20
    lda.l pdx,x
    sta.l !SCR+4                ; dx
    lda.l pdy,x
    sta.l !SCR+6                ; dy
    lda.l edx,x
    sta.l !SCR+16
    lda.l edy,x
    sta.l !SCR+18
    sep #$20
    lda.l !SCR+12
    tax
    lda $1842,x
    xba
    lda $182A,x
    rep #$20
    clc
    adc.l !SCR+4
    sta.l !SCR                  ; new x
    clc
    adc.l !SCR+16
    lsr a
    lsr a
    lsr a
    lsr a
    and.w #$000F
    sta.l !SCR+8
    sep #$20
    lda $188A,x
    xba
    lda $1872,x
    rep #$20
    clc
    adc.l !SCR+6
    sta.l !SCR+2                ; new y
    clc
    adc.l !SCR+18
    and.w #$00F0
    ora.l !SCR+8
    sep #$20
    tay                         ; the cell the leading edge enters: a wall, a soft block or a bomb stops it
    lda $1052,y                 ; (not $1152: the enemy marks the cell it walks to)
    and #$E8
    beq .go
    jmp .stop
.go:
    rep #$20
    lda.l !SCR
    sep #$20
    sta $182A,x
    xba
    sta $1842,x
    rep #$20
    lda.l !SCR+2
    sep #$20
    sta $1872,x
    xba
    sta $188A,x
    ply                         ; the object
    phy
    rep #$20
    lda $055F,y
    clc
    adc.l !SCR+4
    sta $055F,y
    lda $05BF,y
    clc
    adc.l !SCR+6
    sta $05BF,y
    sep #$20
    cpx #$05
    bcs .enemy
    lda $1782,x                 ; a bomber (bomber_push; SB5 makes its cell from its object): its Louie too
    bpl .rts
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tay
    lda $17FA,y
    bmi .rts
    tay
    rep #$20
    lda $055F,y
    clc
    adc.l !SCR+4
    sta $055F,y
    lda $05BF,y
    clc
    adc.l !SCR+6
    sta $05BF,y
    sep #$20
    bra .rts
.enemy:
    rep #$20
    lda.l !SCR+2                ; the centre's cell
    clc
    adc.w #8
    and.w #$00F0
    sta.l !SCR+8
    lda.l !SCR
    clc
    adc.w #8
    lsr a
    lsr a
    lsr a
    lsr a
    and.w #$000F
    ora.l !SCR+8
    sep #$20
    cmp $16AA,x
    beq .rts
    pha
    ldy $16AA,x                 ; the cell left: no enemy there any more
    lda $1152,y
    and #$EF
    sta $1152,y
    pla
    sta $16AA,x
.rts:
    ply
    rts
.stop:
    lda #$00
    sta.l !PUSH,x
    ply
    rts

; ================================================================ Black Louie: the dash
; table $C4:551B entry 6 (JSR (,X) from $C4:5514; $8D = the rider)
la_black:
    ldx $8D
    cpx #$04
    bcs .rts
    lda.l !DASH,x
    ora.l !CD,x
    ora.l !INV,x
    bne .rts
    lda $1632,x
    beq .rts
    cmp #$05
    bcs .rts
    sta.l !DDIR,x
    lda #!DASH_T
    sta.l !DASH,x
    lda #!CD_T
    sta.l !CD,x
    lda #$00
    sta.l !IMP,x
    lda #$01
    sta.l !ANY
    lda #$02
    xba
    lda #$35
    jsl $C00CED
    lda #$1E                    ; the Louie's shoulder charge: animations $1F-$22 (SB5's, the boss's only)
    jsr louie_anim
.rts:
    rts

; Seat X's Louie (a dash): the shoulder charge again if SB5 replaced it (a dash started with Y alone: the rider
; starts walking and SB5 sets the Louie's walk). Keeps X.
shoulder_keep:
    phx
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tax
    ldy $17FA,x
    lda $1692,x
    clc
    adc #$1E
    plx                         ; (before the CMP: PLX sets Z by the seat, which made seats 2-4 restart the
    cmp $079F,y                 ; charge every frame: stuck on its first pose)
    beq +
    lda #$1E
    jsr louie_anim
+   rts

; Impact hold: the rider stops and SB5 sets the Louie's stand: back to the shoulder charge's last pose.
shoulder_stay:
    phx
    txa
    clc
    adc $0128
    tax
    ldy $17FA,x
    lda $1692,x
    clc
    adc #$1E
    plx                         ; (before the CMP, as in shoulder_keep)
    cmp $079F,y
    bne shoulder_hold
    rts

; Seat X's Louie hit something with the shoulder charge: its last pose (the script's last pair, held $FF frames)
; until the impact hold (!IMP) is over. Keeps X.
shoulder_hold:
    jsr shoulder_keep
    phx
    txa
    clc
    adc $0128
    tax
    ldy $17FA,x
    plx
    lda #$0E                    ; offset of pair 7 in every shoulder script ($1F-$22: 6 poses, the 4th 5 then $FF)
    sta $07FF,y
    lda $079F,y
    jsl $C011DD                 ; (resolves the pair at $07FF, keeps the timer)
    lda #$FF
    sta $07A0,y
    rts

; $C4:5427 (STZ $A5 / STZ $AE: a mount's animation A for mount actor X, from $C4:547F): while its rider's
; Black Louie dash / impact hold lasts, SB5's walk / stand requests are dropped (only the shoulder charge,
; $1E + base, goes on), so the charge shows from the first frame even when the dash starts with Y alone.
la_lanim:
    pha
    txa
    sec
    sbc $0128                   ; (co-op: !mofs, asm/coop.asm)
    bcc .go
    cmp #$04
    bcs .go
    phx
    tax
    lda.l !DASH,x
    ora.l !IMP,x
    plx
    cmp #$00
    beq .go
    lda $01,s
    sec
    sbc $1692,x
    cmp #$1E
    beq .go
    pla
    pla                         ; (our return address: back to $C4:5427's caller)
    pla
    rts
.go:
    pla
    stz $A5
    stz $AE
    rts

; seat X's Louie plays animation $1692 (its base: 1-4 by facing) + A ($C4:547F, as the Red Louie's punch).
; Keeps X.
louie_anim:
    phx
    pha
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tax
    pla
    jsr $547F
    plx
    rts

; $C4:3180 (was STA $1CC2: A = pixels walked this frame, X = actor; Z by A for the BEQ after): a dash goes
; 1.6 pixels a frame (2 2 1 2 1)
la_speed:
    cpx #$04
    bcs .st
    pha
    lda.l !DASH,x
    beq .n
    lda.l !IMP,x
    bne .n
    lda.l !DASH,x
-   cmp #$05
    bcc +
    sbc #$05
    bra -
+   cmp #$02
    lda #$01
    bcc +
    inc a
+   sta $01,s
.n:
    pla
.st:
    sta $1CC2
    cmp #$00
    rts

; carry set when seat X rides a live Black Louie (Y = the Louie)
riding_black:
    lda $1782,x
    bpl .no
    jsr alive
    bcc .no
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tay
    lda $16C2,y
    cmp #$06
    bne .no
    lda $17FA,y
    bmi .no
    sec
    rts
.no:
    clc
    rts

; after the pad reader (JSL from $C0:0B54, every frame, before the tasks)
la_pads:
    jsl !PADS
    php
    sep #$30
    phb
    lda #$80
    pha
    plb
    lda $012E                   ; a co-op stage's first frames: nothing left from the last stage
    beq +
    lda $0154
    cmp #$02
    bcs +
    jsr clear_all
    bra .out
+   lda $1D1D                   ; (paused)
    bne .out
    lda #$00
    sta.l !ANY
    ldx #$03
.seat:
    lda.l !DASH,x               ; (a seat with nothing going on: a few cycles)
    ora.l !CD,x
    ora.l !INV,x
    ora.l !GT,x
    bne +
    lda $1782,x                 ; (Green Louie's dash, bit 0 on a Louie)
    and #$81
    cmp #$81
    bne ++
+   jsr seat_frame
++  dex
    bpl .seat
    jsr bomber_push
.out:
    plb
    plp
    rtl

clear_all:
    rep #$10
    ldx.w #!END-!LA-1
    lda #$00
-   sta.l !LA,x
    dex
    bpl -
    sep #$10
    rts

; one seat (X) a frame: cooldown, the dash (pads, enemies ahead, invincibility), the afterimage history
seat_frame:
    lda.l !CD,x
    beq +
    dec a
    sta.l !CD,x
    lda #$01
    sta.l !ANY
+   lda.l !DASH,x
    bne .dash
    lda.l !INV,x
    bne +
    jmp .ghost
+
    dec a
    sta.l !INV,x
    beq .over
    jsr riding_black
    bcc .over
    jsr invul
    bra .ghost
.over:
    lda #$00
    sta.l !INV,x
    jsr release
    bra .ghost
.dash:
    jsr riding_black
    bcs .ok
    lda #$00
    sta.l !DASH,x
    sta.l !IMP,x
    sta.l !INV,x
    jsr release
    bra .ghost
.ok:
    jsr invul
    lda.l !IMP,x
    beq .move
    jsr shoulder_stay
    stz $31,x
    bra .pads
.move:
    jsr shoulder_keep
    phx
    lda.l !DDIR,x
    tax
    lda.l dpad,x
    plx
    sta $31,x
    jsr dash_hit
.pads:
    stz $3B,x
    lda $36,x
    and #$FB
    sta $36,x
    lda.l !IMP,x
    beq .count
    dec a
    sta.l !IMP,x
    bne .ghost
    lda #$00
    sta.l !DASH,x
    bra .ended
.count:
    lda.l !DASH,x
    dec a
    sta.l !DASH,x
    bne .ghost
.ended:
    lda #$00                    ; walking again (SB5 sets the stand pose if the pad is let go)
    jsr louie_anim
    lda.l !INV,x
    bne .ghost
    jsr release
.ghost:
    jmp ghost_rec

; seat X invincible this frame: SB5's vest timer at least 2, $15A2 bit 2
invul:
    lda #$01
    sta.l !ANY
    lda $15A2,x
    and #$04
    bne +
    lda $15A2,x
    ora #$04
    sta $15A2,x
    lda #$01
    sta.l !SET4,x
+   lda $1722,x
    bne +
    lda $170A,x
    cmp #$02
    bcs +
    lda #$02
    sta $170A,x
+   rts

release:
    lda.l !SET4,x
    beq +
    lda #$00
    sta.l !SET4,x
    lda $15A2,x
    and #$FB
    sta $15A2,x
+   rts

; seat X dashes: the first enemy just ahead (in its lane, 1-20 pixels in front) is pushed; the dash holds.
; No enemy: an opponent bomber ahead (a boss rival, any other bomber in Battle: bomber_hit) is pushed too.
dash_hit:
    txa
    sta.l !SCR+12               ; seat
    lda.l !DDIR,x
    sta.l !SCR+13
    lda $1842,x
    xba
    lda $182A,x
    rep #$20
    sta.l !SCR+8                ; seat x
    sep #$20
    lda $188A,x
    xba
    lda $1872,x
    rep #$20
    sta.l !SCR+10               ; seat y
    sep #$20
    jsr no_enemies
    bcc +
    jmp .none
+   ldx #$05
.loop:
    cpx $012D
    bcc +
    jmp .none
+
    cpx #24
    bcc +
    jmp .none
+
    jsr alive
    bcs +
    jmp .next
+
    lda.l !PUSH,x
    beq +
    jmp .next
+
    lda $1842,x
    xba
    lda $182A,x
    rep #$20
    sec
    sbc.l !SCR+8
    sta.l !SCR+4                ; dx
    sep #$20
    lda $188A,x
    xba
    lda $1872,x
    rep #$20
    sec
    sbc.l !SCR+10
    sta.l !SCR+6                ; dy
    sep #$20
    lda.l !SCR+13
    cmp #$02
    beq .down
    cmp #$03
    beq .left
    cmp #$04
    beq .up
    rep #$20                    ; right: forward dx, side dy
    lda.l !SCR+4
    sta.l !SCR
    lda.l !SCR+6
    bra .test
.left:
    rep #$20
    lda.l !SCR+4
    eor.w #$FFFF
    inc a
    sta.l !SCR
    lda.l !SCR+6
    bra .test
.down:
    rep #$20
    lda.l !SCR+6
    sta.l !SCR
    lda.l !SCR+4
    bra .test
.up:
    rep #$20
    lda.l !SCR+6
    eor.w #$FFFF
    inc a
    sta.l !SCR
    lda.l !SCR+4
.test:
    clc
    adc.w #9
    cmp.w #19
    bcs .miss
    lda.l !SCR
    dec a
    cmp.w #20
    bcs .miss
    sep #$20
    lda #!PUSH_F
    jsr freeze                  ; (first: a new freeze clears the push)
    lda #!PUSH_T
    sta.l !PUSH,x
    lda.l !SCR+13
    sta.l !PDIR,x
    lda.l !SCR+12
    tax
    lda #!IMP_T
    sta.l !IMP,x
    lda #!INV_T+!IMP_T
    sta.l !INV,x
    jmp shoulder_hold
.miss:
    sep #$20
.next:
    inx
    jmp .loop
.none:
    jmp bomber_hit

; dash_hit, no enemy hit: the first opponent bomber (seats 0-4 but the rider) in the lane ahead (!SCR+8/+10 the
; rider's x / y, !SCR+12 the rider, !SCR+13 the direction) gets SB5's Red punch stun ($15BA |= direction, as
; $C4:5565) and is pushed 2 cells by la_pads (push_step, !PUSH / !PDIR of actors 0-4); the dash holds as on an enemy
bomber_hit:
    ldx #$04
.seat:
    txa
    cmp.l !SCR+12
    beq .next
    jsr opponent
    bcc .next
    jsr alive
    bcc .next
    lda.l !PUSH,x
    bne .next
    jsr in_lane
    bcc .next
    lda #!PUSH_T
    sta.l !PUSH,x
    lda.l !SCR+13
    sta.l !PDIR,x
    ora $15BA,x
    sta $15BA,x
    lda.l !SCR+12
    tax
    lda #!IMP_T
    sta.l !IMP,x
    lda #!INV_T+!IMP_T
    sta.l !INV,x
    jmp shoulder_hold
.next:
    dex
    bpl .seat
    lda.l !SCR+12
    tax
    rts

; carry set when seat X is an opponent: in Battle every bomber, in the Normal Game a rival (seat >= the
; roster, asm/coop.asm !roster: the boss bombers of 1-6 and the zones' boss stages)
opponent:
    lda $1D1A
    lsr a
    bcs .yes
    txa
    cmp $012A
    bcs .yes
    clc
    rts
.yes:
    sec
    rts

; carry set when actor X is in the dash's lane ahead (1-20 pixels in front, within 9 pixels to the side). M 8-bit.
in_lane:
    lda $1842,x
    xba
    lda $182A,x
    rep #$20
    sec
    sbc.l !SCR+8
    sta.l !SCR+4                ; dx
    sep #$20
    lda $188A,x
    xba
    lda $1872,x
    rep #$20
    sec
    sbc.l !SCR+10
    sta.l !SCR+6                ; dy
    sep #$20
    lda.l !SCR+13
    cmp #$02
    beq .down
    cmp #$03
    beq .left
    cmp #$04
    beq .up
    rep #$20
    lda.l !SCR+4
    sta.l !SCR
    lda.l !SCR+6
    bra .test
.left:
    rep #$20
    lda.l !SCR+4
    eor.w #$FFFF
    inc a
    sta.l !SCR
    lda.l !SCR+6
    bra .test
.down:
    rep #$20
    lda.l !SCR+6
    sta.l !SCR
    lda.l !SCR+4
    bra .test
.up:
    rep #$20
    lda.l !SCR+6
    eor.w #$FFFF
    inc a
    sta.l !SCR
    lda.l !SCR+4
.test:
    clc
    adc.w #9
    cmp.w #19
    bcs .no
    lda.l !SCR
    dec a
    cmp.w #20
    bcs .no
    sep #$21
    rts
.no:
    sep #$20
    clc
    rts

; la_pads, every frame: seats 0-4 being pushed (bomber_hit) move 2 pixels
bomber_push:
    ldx #$04
-   lda.l !PUSH,x
    beq +
    jsr alive
    bcc .off
    lda.l !PUSH,x
    dec a
    sta.l !PUSH,x
    ldy $17FA,x
    jsr push_step
    bra +
.off:
    lda #$00
    sta.l !PUSH,x
+   dex
    bpl -
    rts

; ---------------------------------------------------------------- afterimages: history (seat X)
ghost_rec:
    lda.l !DASH,x
    beq +
    lda.l !IMP,x
    beq .on
    bra .off
+   lda $1782,x                 ; Green Louie's dash: on a Louie, bit 0
    bpl .off
    and #$01
    beq .off
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tay
    lda $16C2,y
    cmp #$01
    bne .off
.on:
    lda.l !GT,x
    bne +
    lda #$00                    ; a new trail
    sta.l !GN,x
+   lda #!GHOST_T
    sta.l !GT,x
    bra .rec
.off:
    lda.l !GT,x
    beq .rts
    dec a
    sta.l !GT,x
.rec:
    lda #$01
    sta.l !ANY
    lda.l !GI,x
    inc a
    and #$0F
    sta.l !GI,x
    asl a
    sta.l !SCR+15
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    ora.l !SCR+15
    tay                         ; seat * 32 + index * 2
    phx
    lda $1842,x
    xba
    lda $182A,x
    tyx
    rep #$20
    sta.l !HX,x
    sep #$20
    plx
    phx
    lda $188A,x
    xba
    lda $1872,x
    tyx
    rep #$20
    sta.l !HY,x
    sep #$20
    plx
    lda.l !GN,x
    cmp #$10
    bcs .rts
    inc a
    sta.l !GN,x
.rts:
    rts

; ---------------------------------------------------------------- afterimages: OAM (after SB5's builder)
; JSL from $C0:0B5D: the builder left $57 = OAM entries free, $58 = the next entry's offset; the entries written
; here count as used ($57), so the next frame's builder hides them
la_oam:
    jsl !OAM
    php
    sep #$30
    lda.l !ANY
    bne +
    plp
    rtl
+   phb
    lda #$7E
    pha
    plb
    ldx #$03
-   lda.l !GT,x
    beq +
    jsr ghost_draw
+   dex
    bpl -
    plb
    plp
    rtl

; seat X: its afterimage of 6 (even frames) or 12 (odd frames) frames ago (DB $7E)
ghost_draw:
    txa
    sta.l !SCR+12
    lda $0069
    and #$01
    beq +
    lda #12
    bra ++
+   lda #6
++  sta.l !SCR+13
    cmp.l !GN,x
    bcc +
    rts
+   lda.l !GI,x
    sec
    sbc.l !SCR+13
    and #$0F
    asl a
    sta.l !SCR+15
    txa
    asl a
    asl a
    asl a
    asl a
    asl a
    ora.l !SCR+15
    tay                         ; history entry
    lda $1842,x
    xba
    lda $182A,x
    rep #$20
    sta.l !SCR
    sep #$20
    lda $188A,x
    xba
    lda $1872,x
    rep #$20
    sta.l !SCR+2
    tyx
    lda.l !HX,x
    sec
    sbc.l !SCR
    sta.l !SCR+4                ; dx (then - now)
    lda.l !HY,x
    sec
    sbc.l !SCR+2
    sta.l !SCR+6                ; dy
    lda.l !SCR+4
    bpl +
    eor.w #$FFFF
    inc a
+   sta.l !SCR+8
    lda.l !SCR+6
    bpl +
    eor.w #$FFFF
    inc a
+   clc
    adc.l !SCR+8
    cmp.w #6                    ; (not apart yet: none)
    sep #$20
    lda.l !SCR+12
    tax
    bcs +
    rts
+   ldy $17FA,x
    bpl +
    rts
+   lda $06DF,y
    sta.l !SCR+10               ; the rider's OBJ palette
    rep #$20
    lda $055F,y
    sta.l !SCR                  ; its screen x / y
    lda $05BF,y
    sta.l !SCR+2
    sep #$20
    txa
    clc
    adc $0128                   ; (co-op: !mofs, asm/coop.asm)
    tay
    lda $17FA,y
    tay
    bmi +
    lda $06DF,y
    bra ++
+   lda #$FF
++  sta.l !SCR+11               ; its Louie's
    lda #!GMAX
    sta.l !SCR+14
    lda #$80
    sec
    sbc $57
    bne +
    rts
+   sta.l !SCR+9                ; the builder's entries
    rep #$10
    ldx.w #0
.scan:
    lda $08C2,x
    lsr a
    and #$07
    cmp.l !SCR+10
    beq .mine
    cmp.l !SCR+11
    bne .next
.mine:
    lda $08C0,x
    cmp #$E0
    bcs .next
    sec
    sbc.l !SCR+2
    clc
    adc #48
    cmp #64
    bcs .next
    lda $08BF,x
    sec
    sbc.l !SCR
    clc
    adc #32
    cmp #64
    bcs .next
    jsr ghost_entry
    bcs .done
.next:
    inx
    inx
    inx
    inx
    lda.l !SCR+9
    dec a
    sta.l !SCR+9
    bne .scan
.done:
    sep #$10
    lda.l !SCR+12
    tax
    rts

; OAM entry at X (16-bit offset) again, moved by (!SCR+4, !SCR+6), as the next entry; carry set = no more.
; Keeps X.
ghost_entry:
    lda $57
    cmp.b #128-!GSLOT+1
    bcs +
    jmp .full
+
    lda.l !SCR+14
    bne +
    jmp .full
+
    dec a
    sta.l !SCR+14
    rep #$20                    ; its high bits (x bit 8, size)
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    txa
    lsr a
    lsr a
    sep #$20
    and #$03
    sta.l !SCR+22
    lda $0ABF,y
-   pha
    lda.l !SCR+22
    beq +
    dec a
    sta.l !SCR+22
    pla
    lsr a
    lsr a
    bra -
+   pla
    and #$03
    sta.l !SCR+8
    rep #$20
    lda $08BF,x
    and.w #$00FF
    sta.l !SCR+16
    lda.l !SCR+8
    lsr a
    bcc +
    lda.l !SCR+16
    ora.w #$FF00
    sta.l !SCR+16
+   lda.l !SCR+16
    clc
    adc.l !SCR+4
    sta.l !SCR+16               ; new x
    clc
    adc.w #16
    cmp.w #16+256
    bcc +
    jmp .skip
+
    lda $08C0,x
    and.w #$00FF
    clc
    adc.l !SCR+6
    sta.l !SCR+18               ; new y
    clc
    adc.w #16
    cmp.w #16+224
    bcc +
    jmp .skip
+
    ldy $58
    sep #$20
    lda.l !SCR+16
    sta $08BF,y
    lda.l !SCR+18
    sta $08C0,y
    lda $08C1,x
    sta $08C1,y
    lda $08C2,x
    sta $08C2,y
    lda.l !SCR+17
    and #$01
    sta.l !SCR+15
    lda.l !SCR+8
    and #$02
    ora.l !SCR+15
    sta.l !SCR+20               ; its high bits
    lda #$03
    sta.l !SCR+21               ; their mask
    lda $58
    lsr a
    lsr a
    and #$03
    beq +
-   pha
    lda.l !SCR+20
    asl a
    asl a
    sta.l !SCR+20
    lda.l !SCR+21
    asl a
    asl a
    sta.l !SCR+21
    pla
    dec a
    bne -
+   rep #$20
    tya
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
    lda.l !SCR+21
    eor #$FF
    and $0ABF,y
    ora.l !SCR+20
    sta $0ABF,y
    rep #$20
    lda $58
    clc
    adc.w #4
    sta $58
    sep #$20
    dec $57
    clc
    rts
.skip:
    sep #$20
    clc
    rts
.full:
    sec
    rts

; ================================================================ Yellow Louie
; $C4:5797 (was LDA $1052,X / CMP #$30: X = the cell ahead, $8D = the rider; Z set = a soft block, kicked by
; SB5): a resting bomb there rolls away with the row after it
la_yahead:
    txa
    jsr bomb_at
    bcs .native
    phx
    pha
    ldy $8D
    lda $1632,y
    plx
    jsr kick_row
    plx
    lda #$00
    cmp #$30                    ; (Z clear: no soft block)
    rts
.native:
    lda $1052,x
    cmp #$30
    rts

; $C4:5973 (was LDA $1052,X / CMP #$30: X = the cell past the kicked soft block that just stopped, $73 = its
; task; Z set = a soft block there, kicked on by SB5): a resting bomb there rolls on (with its row)
la_bnext:
    txa
    jsr bomb_at
    bcs .native
    phx
    ldx $73
    lda $0C87,x
    lsr a
    and #$07
    plx
    phx
    jsr kick_row
    plx
    lda #$00
    cmp #$30
    rts
.native:
    lda $1052,x
    cmp #$30
    rts

; A = direction 1-4, X = the cell of a resting bomb: it and the resting bombs right after it that way (the row)
; roll together: the front one through SB5's kick (from the cell behind it: its checks and sound), the others
; with the same motion. Carry clear = they roll (Yellow Louie trains), set = blocked. X, Y changed.
kick_row:
    sta.l !SCR+20
    txa
    sta.l !SCR+21               ; the first cell
    sta.l !SCR+22               ; the front cell
    jsr bomb_at
    bcc +
    rts
+   tya
    sta.l !SCR+19               ; the front bomb
    lda #$0C
    sta.l !SCR+23
.front:
    lda.l !SCR+20
    tax
    lda.l !SCR+22
    clc
    adc.l dcell,x
    jsr bomb_at
    bcs .found
    sta.l !SCR+22
    tya
    sta.l !SCR+19
    lda.l !SCR+23
    dec a
    sta.l !SCR+23
    bne .front
.found:
    lda $8A
    pha
    lda.l !SCR+20
    tax
    lda.l !SCR+22
    sec
    sbc.l dcell,x
    sta $8A
    lda.l !SCR+20
    jsl $C52293
    pla
    sta $8A
    bcc +
    rts
+   lda.l !SCR+19
    tax
    lda #$01
    sta.l !TRAIN,x
    lda.l !SCR+21
    sta.l !SCR+18               ; the row behind it, from the first cell
.follow:
    lda.l !SCR+18
    cmp.l !SCR+22
    beq .done
    jsr bomb_at
    bcs .step
    lda.l !SCR+20
    ora #$10
    sta $0E90,y
    lda #$10
    sta $0F38,y
    lda #$02
    sta $0F4C,y
    lda $0EE0,y
    and #$FE
    sta $0EE0,y
    tyx
    lda #$01
    sta.l !TRAIN,x
.step:
    lda.l !SCR+20
    tax
    lda.l !SCR+18
    clc
    adc.l dcell,x
    sta.l !SCR+18
    bra .follow
.done:
    clc
    rts

; A = direction 1-4, Y = a soft block's cell: SB5's Yellow Louie task ($C4:57B8, as $C4:579E makes it) kicks it
spawn_block:
    sta.l !SCR+20
    tya
    sta.l !SCR+21
    phx
    phy
    tax
    jsl $C02069
    dw $57B8
    bcs +
    tax
    lda.l !SCR+21
    sta $0C5F,x
    lda.l !SCR+20
    asl a
    sta $0C87,x
+   ply
    plx
    rts

; a rolling bomb's next cell (JSL from la_roll_t at $C5:2182: X = the bomb, A = the cell ahead, DB $80);
; carry clear = the cell counts as free (a train goes on), set = SB5's test decides ($C5:221B)
la_roll:
    pha
    lda.l !TRAIN,x
    beq .native
    lda $01,s
    jsr other_bomb_at
    bcs .soft
    lda $0E90,y
    and #$10
    beq .still
    lda $0E90,y
    eor $0E90,x
    and #$07
    bne .native
    pla                         ; the train's bomb ahead rolls the same way
    clc
    rtl
.still:
    lda $0E90,y
    and #$F8
    bne .native
    phx
    lda $0E90,x
    and #$07
    pha
    lda $03,s
    tax
    pla
    jsr kick_row                ; the bomb (and its row) joins the train
    plx
    bcs .native
    pla
    clc
    rtl
.soft:
    lda $01,s
    tay
    lda $1052,y
    cmp #$30
    bne .native
    lda $0E90,x                 ; a soft block: kicked on, the bomb stops
    and #$07
    jsr spawn_block
.native:
    pla
    sec
    rtl

; ================================================================ eggs
; asm/louies.asm louie_hatch (JSL, was LDA #$06 / JSL $C01DEB: A = the Louie, 0-6 at random): in the egg test stage
; (!EGG_STAGE, features/stage_items.py LOUIE_TEST: 1-1 hides one egg per Louie) the eggs hatch Louies 0, 1, ... 6
; in the order they are taken (from 0 again each time the stage starts: clear_all)
la_hatch:
    php
    sep #$20
    lda.l $7E1D1A
    lsr a
    bcs .random                 ; (Battle)
    lda.l $7E102F
    cmp #!EGG_STAGE
    bne .random
    lda.l !HATCH
    pha
    inc a
    cmp #$07
    bcc +
    lda #$00
+   sta.l !HATCH
    pla
    plp
    rtl
.random:
    plp
    lda #$06
    jsl $C01DEB
    rtl

print "SYM la_red ", hex(la_red)
print "SYM la_lanim ", hex(la_lanim)
print "SYM la_hatch ", hex(la_hatch)
print "SYM la_frozen ", hex(la_frozen)
print "SYM la_black ", hex(la_black)
print "SYM la_speed ", hex(la_speed)
print "SYM la_pads ", hex(la_pads)
print "SYM la_oam ", hex(la_oam)
print "SYM la_yahead ", hex(la_yahead)
print "SYM la_bnext ", hex(la_bnext)
print "SYM la_roll ", hex(la_roll)
end_c4:
print "SYM end_c4 ", hex(end_c4)

org !C5

; $C5:2182 (was JSR $221B: X = a rolling bomb, A = the cell ahead; carry set = taken, the bomb stops)
la_roll_t:
    phy                         ; (Y = the bomb's object, still used after)
    pha
    jsl la_roll
    pla
    ply
    bcc .free
    jsr $221B
    bcc .rts
    pha
    lda #$00
    sta.l !TRAIN,x
    pla
    sec
.rts:
    rts
.free:
    clc
    rts

print "SYM la_roll_t ", hex(la_roll_t)
end_c5:
print "SYM end_c5 ", hex(end_c5)
