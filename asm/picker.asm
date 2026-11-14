; Character + color selection in the Normal Game
; (tools/sb6/features/picker.py; port of normal_character_mod.c and
; selection_color_mod.c of SuperBomberman5SNESRecomp).
;
; Confirming a file (New Game $C7:10E2, Continue $C7:0E27) calls the scripts
; below instead of the fade $C7:124C: fade, then Battle's character picker
; ($C6:89CF, it returns to its caller) with the game's seats as humans, then
; back to the file's own flow. B in the picker ($1040 = $FF on return) goes
; back to the file list. The script variables the picker uses are saved
; around it. The picker replaces the menu's graphics, so the way back loads
; them again ($C7:0B47, the menu's own loader script).
;
; Native code is reached from a script through `FF 1A nn` (handler
; $C1:467C, its table entry at $C2:069B now points here): nn >= $F0 is ours.
;
; In the picker L / R change the color of the seat's cursor (white, black,
; red, blue, green, yellow; with the SB6 art, Bomberman has the !BCOLS
; palettes of BombermanPallete.png and its cell of the grid, a BG figure of
; 8 colors in the cartridge, is drawn as a sprite with the SB6 pose; so is
; the cell of character !XCH when its sheet was redrawn). The cursor's label shows "L + R" above the cell and
; the player number below (OAM shadow rewritten after the game built it).
;
; State: $7F:FF00-$7F:FF7F (docs/FREE_SPACE.md).

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
!refs    = !PK+$50      ; 8 bytes (palette slot references)
!s0      = !PK+$58      ; scratch
!s1      = !PK+$59
!s2      = !PK+$5A
!s3      = !PK+$5B
!gfx     = !PK+$5C      ; $FF = glyph tiles are in VRAM
!drawn   = !PK+$5D      ; 1 = glyph sprites are in the OAM shadow
!cellpal = !PK+$5E      ; 1 = the Bomberman cell's sprite has colors
!GOAM    = 112          ; first sprite owned here (4-aligned): 2 for the !XCH cell,
!GHIGH   = $0ADB         ;   2 for the Bomberman cell (!CS0, !CS1), then the
!GLY     = 116          ;   12 glyphs; high bits $0ABF + !GOAM/4
!CS0     = $0A87         ; OAM shadow of sprite 114 ($08BF + 4*114)
!CS1     = $0A8B         ; ... 115
!CPAL    = $D0           ; CGRAM index of the cell sprite's colors (OBJ palette 5)
!XS0     = $0A7F         ; OAM shadow of sprite 112: cell of character !XCH
!XS1     = $0A83         ; ... 113
!XCPAL   = $F0           ; its colors (OBJ palette 7, free with up to four seats)
!w0      = !PK+$60      ; word scratch
!w1      = !PK+$62
!oamn    = !PK+$64      ; 4 bytes: OAM offset/4 of each seat's number

org !E4

script_new:
    db $24,$4C,$12,$C7              ; the file menu's own fade
    db $FF,$1A,$F0                  ; open
    db $24,$CF,$89,$C6              ; Battle's character picker
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
; replaced (VRAM $08F0-$15EF and the BG2 map; the tiles below $08F0 are the
; same on both screens). The first archive sent after the picker comes out
; wrong (the menu sends $0C before $22; seen in Mesen, cause not traced), so
; $22 is sent again at the end.
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

; ---------------------------------------------------------------------------
; FF 1A nn (M/X 8-bit, [$0D] = operand, $0A-$0C = next op, $73 = task).
pick_op:
    lda [$0D]
    cmp #$F0
    bcs +
    jml $C1467C
+   phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp #$F1
    beq .close
    bcc .open
    ldx #$0E                        ; ---- F2 / F3: go to a file list
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
    sta.l !col,x
    dex
    bpl -
    stz $1038
    lda #$04
    sta $1031
    lda #$01
    sta.l !live
    lda #$00
    sta.l !on
    sta.l !gfx
    sta.l !cellpal
    plb
    rtl

.close:
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

; A = character (0-8), !s1 = color: A = palette id of set 0. Bomberman with
; the SB6 art and the characters drawn on his layout have their own palettes,
; ids chpal[char] + color (asm/bombers.asm; chpal 0 = the cartridge's).
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

; Palette id of the portrait of seat X's character (!s2, color !s1): the
; cartridge's id for the characters 1-8 (color mod 6), palid for Bomberman.
portid:
    lda.l !s2
    bne +
    lda.l !s3
    rts
+   phx
    tax
    lda.l !s1
-   cmp #$06
    bcc +
    sbc #$06
    bra -
+   clc
    adc.l $80BB4E,x
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
    lda.l !drawn
    cmp #$01
    bne +
    jsr hide
+   lda $1031
    cmp #$02                        ; title: a new session
    bne +
    lda #$00
    sta.l !on
    sta.l !live
if !SCLR
    jsl !SCLR                       ; streamed poses (asm/bombers.asm)
endif
    bra .out
+   cmp #$04
    bne .out
    lda.l !live
    cmp #$01
    bne .out
    lda $0CE0                       ; task 9 inside the picker's main part
    cmp #$C6
    bne .out
    lda $0CB8
    xba
    lda $0C90
    rep #$20
    cmp #$8B48
    bcc .out
    cmp #$8EE4
    bcs .out
    sep #$20
    jsr buttons
    jsr isolate
if !OWN
    lda.l !cellpal
    cmp #$01
    beq +
    lda #$80
    ldx.b #!CPAL
    ldy #$10
    jsr upload
if !XCH
    lda.b #!XPAL
    ldx.b #!XCPAL
    ldy #$10
    jsr upload
endif
    lda #$01
    sta.l !cellpal
+
endif
    ldx #$04
-   jsr color
    dex
    bpl -
    jsr label
.out:
    plb
    plp
    rtl

; A = colors of the character chosen by seat X (0 = none: random cell).
colcount:
    lda $625F,x
    beq .none
    cmp #$0A
    bcs .none
    phx
    tax
    lda.l chcol-1,x                 ; colors of each character
    plx
    cmp #$00                        ; (Z for the callers)
    rts
.none:
    lda #$00
    rts

; L / R of each pad -> color of the seat its cursor is on ($62AB), while the
; seat is choosing ($62B5 = 1). New presses: $36+pad, R = $10, L = $20.
buttons:
    ldy #$04
.pad:
    ldx $62AB,y
    cpx #$05
    bcs .next
    lda $62B5,x
    cmp #$01
    bne .next
    jsr colcount
    beq .next
    sta.l !s0
    lda $0036,y
    and #$30
    cmp #$10
    beq .r
    cmp #$20
    bne .next
    lda.l !col,x                    ; L: previous
    bne +
    lda.l !s0
+   dec a
    bra .set
.r:
    lda.l !col,x                    ; R: next
    inc a
    cmp.l !s0
    bcc .set
    lda #$00
.set:
    sta.l !col,x
.next:
    dey
    bpl .pad
    rts

; Portraits that show the same palette share an OBJ palette slot. Each seat
; gets slot = seat when the slots 0-4 have no other owner.
isolate:
    ldx #$07
-   lda $0349,x
    sta.l !refs,x
    dex
    bpl -
    ldx #$04
.seat:
    ldy $62BF,x
    cpy #$60
    bcs .next
    lda $06DF,y
    cmp #$08
    bcs .no
    tay
    lda $2B18,y
    bne .no
    phx
    tyx
    lda.l !refs,x
    beq .nopl
    dec a
    sta.l !refs,x
    plx
.next:
    dex
    bpl .seat
    ldx #$04
-   lda.l !refs,x
    bne .no
    dex
    bpl -
    ldx #$04
.give:
    ldy $62BF,x
    cpy #$60
    bcs +
    txa
    sta $06DF,y
    lda #$01
    sta.l !refs,x
    stz $2B18,x
+   dex
    bpl .give
    ldx #$07
-   lda.l !refs,x
    sta $0349,x
    dex
    bpl -
.no:
    rts
.nopl:
    plx
    rts

; Seat X: its color in $6264, in its portrait and in its cell of the grid.
color:
    jsr colcount
    bne +
    rts
+   sta.l !s0
    lda.l !col,x
    cmp.l !s0
    bcc +
    lda #$00
    sta.l !col,x
+   sta $6264,x
    sta.l !s1                       ; color
    lda $625F,x
    dec a
    sta.l !s2                       ; character
    jsr palid
    sta.l !s3                       ; palette id
    ldy $62BF,x                     ; portrait
    cpy #$60
    bcs .grid
    txa
    cmp $06DF,y
    bne .grid
    lda $2B18,x
    bne .grid
    lda $0349,x
    cmp #$01
    bne .grid
    jsr portid                      ; the portrait is SB5 art: the cartridge's colors
    sta $2B10,x
    phx
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
    cmp #$80
    bcs +
    cmp.b #!PALS+1
    bcc +
    ldy #$09
+   jsr upload
    plx
.grid:
    lda $62B5,x
    cmp #$01
    bne .out
    lda.l !s2
    inc a
    ldy #$00
-   cmp $62C9,y
    beq .cell
    iny
    cpy #$0A
    bcc -
.out:
    rts
.cell:
    lda.l !s1
    sta $62D3,y
if !OWN
    lda.l !s2                       ; Bomberman: the cell is a sprite
    bne +
    phx
    lda.l !s3
    ldx.b #!CPAL
    ldy #$10
    jsr upload
    plx
    rts
+
if !XCH
    cmp.b #!XCH                     ; the other redrawn character: a sprite too
    bne +
    phx
    lda.l !s1
    clc
    adc.b #!XPAL
    ldx.b #!XCPAL
    ldy #$10
    jsr upload
    plx
    rts
+
endif
endif
    phx
    lda.l !s2                       ; strip palette id: $C2:130B + 7*char + color
    asl a
    asl a
    asl a
    sec
    sbc.l !s2
    clc
    adc.l !s1
    tax
    lda.l $C2130B,x
    pha
    tyx
    lda.l $C21301,x                 ; CGRAM index of the cell's strip
    tax
    pla
    ldy #$08
    jsr upload
    plx
    rts

; A = palette id of set 0 ($81:8000 + 2*(id-1) -> [dest16, count16, colors];
; $80 + n = Bomberman's own palette n, table !PALTAB),
; X = CGRAM index, Y = colors. A strip in the upper half of a BG palette
; keeps its first entry (shared with the lower half). Sets the CGRAM dirty
; flag when something changed.
upload:
    cmp #$00
    bne +
    rts
+
    rep #$30
    and #$00FF
    phx
    cmp #$0080
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
if !OWN
    sec
    sbc #$0080
    cmp.w #!PALN                    ; Bomberman's and the other characters' own palettes
    bcs .bad
    asl a
    tax
    lda.l !PALTAB,x
    clc
    adc #$0004
    sta $A8
    lda.w #!PALTAB>>16
    bra .src
endif
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
    lda.l !w0
    cmp #$0008
    bne .loop
    txa
    and #$0010
    beq .loop
    inx
    inx
    iny
    iny
    lda #$0007
    sta.l !w0
.loop:
    lda [$A8],y
    cmp $2910,x
    beq +
    sta $2910,x
    lda #$0001
    sta $0351
+   inx
    inx
    iny
    iny
    lda.l !w0
    dec a
    sta.l !w0
    bne .loop
    sep #$30
.out:
    sep #$30
    rts

; ---------------------------------------------------------------------------
; Cursor label. The game draws "1P".."4P" above the cell: two 8x8 sprites,
; tiles 6+2n / 7+2n of the first OBJ page, attributes $3C. They move 40
; lines down and three sprites "L", "+", "R" (tiles !GTILE + 3n + 0..2,
; unused by the picker's sheet, drawn at build time in the label's style
; and sent to VRAM by pick_nmi) take their place, in the last 12 sprites of
; the OAM shadow ($08BF, 4 bytes per sprite; high bits $0ABF; $03D5 =
; sprites left free by the builder; hidden sprites have y = $E0).
label:
    lda.l !gfx
    cmp #$FF
    beq +
-   rts                             ; tiles not in VRAM yet
+   lda $03D5                       ; sprites the builder left free
    cmp.b #128-!GOAM
    bcc -
    lda #$01
    sta.l !drawn
if !OWN
    lda $62C9                       ; Bomberman's cell (the first one): two
    cmp #$01                        ;   16x16 sprites over the blanked figure
    bne +
    lda #$28
    sta !CS0
    sta !CS1
    lda #$77
    sta !CS0+1
    lda #$87
    sta !CS1+1
    lda.b #!CTILE
    sta !CS0+2
    lda.b #!CTILE+2
    sta !CS1+2
    lda #$2A                        ; palette 5, priority 2
    sta !CS0+3
    sta !CS1+3
    lda !GHIGH                      ; sprites 114/115 are 16x16, x < 256
    and #$0F
    ora #$A0
    sta !GHIGH
+
if !XCH
    lda $62C9+!XCH                  ; cell !XCH: the same, 40 pixels per cell
    cmp.b #!XCH+1
    bne +
    lda.b #$28+40*!XCH
    sta !XS0
    sta !XS1
    lda #$77
    sta !XS0+1
    lda #$87
    sta !XS1+1
    lda.b #!XTILE
    sta !XS0+2
    lda.b #!XTILE+2
    sta !XS1+2
    lda #$2E                        ; palette 7, priority 2
    sta !XS0+3
    sta !XS1+3
    lda !GHIGH                      ; sprites 112/113 are 16x16, x < 256
    and #$F0
    ora #$0A
    sta !GHIGH
+
endif
endif
    lda #$FF
    sta.l !oamn
    sta.l !oamn+1
    sta.l !oamn+2
    sta.l !oamn+3
    rep #$10
    ldx #$0000
.scan:
    lda $08C0,x
    cmp #$B1                        ; y + 48 must stay on screen
    bcs .nx
    lda $08C2,x
    cmp #$3C
    bne .nx
    lda $08C1,x
    cmp #$06
    bcc .nx
    cmp #$0D
    bcs .nx
    bit #$01
    bne .nx                         ; odd = the "P", found from its number
    sec
    sbc #$06
    lsr a                           ; seat
    phx
    rep #$20
    and #$00FF
    tay
    txa
    lsr a
    lsr a                           ; sprite
    tyx
    sep #$20
    sta.l !oamn,x
    plx
.nx:
    inx
    inx
    inx
    inx
    cpx.w #!GOAM*4
    bcc .scan
    sep #$10

    ldx #$03
.seat:
    lda.l !oamn,x
    beq .skip                       ; (the "P" is the sprite before it)
    cmp #$80
    bcs .skip
    phx
    sta.l !s0
    txa
    sta.l !s1
    jsr relabel
    plx
.skip:
    dex
    bpl .seat
    rts

; !s0 = sprite of the number, !s1 = seat.
relabel:
    rep #$30
    lda.l !s0
    and #$00FF
    asl a
    asl a
    tax
    sep #$20                        ; the "P": previous sprite, 8 to the right
    lda.l !s1
    asl a
    clc
    adc #$07
    cmp $08C1-4,x
    bne .quit
    lda $08C0-4,x
    cmp $08C0,x
    bne .quit
    lda $08BF,x
    clc
    adc #$08
    cmp $08BF-4,x
    bne .quit
    lda $08BF,x
    sec
    sbc #$04
    sta.l !s2                       ; x of the "L"
    lda $08C0,x
    sta.l !s3                       ; y of the label
    clc
    adc #$28
    sta $08C0,x
    sta $08C0-4,x
    lda.l !s1                       ; first glyph tile
    asl a
    clc
    adc.l !s1
    pha
    clc
    adc.b #!GTILE
    sta.l !s0
    pla                             ; sprites !GLY + 3*seat ...
    rep #$20
    and #$00FF
    asl a
    asl a
    clc
    adc.w #!GLY*4
    tax
    sep #$20
    ldy #$0003
-   lda.l !s2
    sta $08BF,x
    clc
    adc #$08
    sta.l !s2
    lda.l !s3
    sta $08C0,x
    lda.l !s0
    sta $08C1,x
    inc a
    sta.l !s0
    lda #$3C
    sta $08C2,x
    inx
    inx
    inx
    inx
    dey
    bne -
.quit:
    sep #$30
    rts

; The glyph sprites leave the screen (the OAM builder only hides the sprites
; it used the frame before).
hide:
    rep #$10
    ldx.w #!GOAM*4
    lda #$E0
-   sta $08C0,x
    inx
    inx
    inx
    inx
    cpx #$0200
    bcc -
    sep #$10
    stz !GHIGH                      ; small, x < 256
    stz !GHIGH+1
    stz !GHIGH+2
    stz !GHIGH+3
    lda #$00
    sta.l !drawn
    rts

; ---------------------------------------------------------------------------
; NMI ($C0:F421, JSL $C004E0 = the VRAM transfers of the frame; M/X 8-bit,
; DBR = 0, forced blank): sends the 12 glyph tiles once the picker's screen
; is up; the frame before, the 8 tiles of the Bomberman cell's sprite (the
; SB6 pose, rows !CTILE and !CTILE + $10) and the empty BG tiles under it.
pick_nmi:
    jsl $C004E0
    php
    sep #$20
    lda.l !live
    cmp #$01
    bne .quit
    lda.l $7E1031
    cmp #$04
    bne .quit
    lda.l !gfx
    cmp #$FF
    beq .quit
    lda.l $7E0CE0
    cmp #$C6
    bne .quit
    rep #$20
    lda.l $7E0CB8
    and #$00FF
    xba
    sta.l !w1
    lda.l $7E0C90
    and #$00FF
    ora.l !w1
    cmp #$8E68                      ; the picker's main loop
    beq +
.quit:
    plp
    rtl
+
    sep #$20
    lda #$80
    sta $2115
if !OWN
    lda.l !gfx
    cmp #$01
    bne .first
    brl .glyphs
.first:
    rep #$20                        ; first frame: the Bomberman cell
    lda #$1801
    sta $4300
    lda.w #cell_tiles
    sta $4302
    lda #$0080
    sta $4305
    lda.w #!CVRAM
    sta $2116
    sep #$20
    lda.b #cell_tiles>>16
    sta $4304
    lda #$01
    sta $420B
    rep #$20
    lda.w #!CVRAM+$100
    sta $2116
    lda #$0080
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    lda.l $7E62C9
    cmp #$01
    bne +
    rep #$20                        ; its figure leaves BG1 (map $3000,
    lda #$3205                      ;   tiles 5-6 x 16-18; $211C = empty)
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    lda #$3225
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    lda #$3245
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    sep #$20
+
if !XCH
    rep #$20                        ; the !XCH cell: tiles and its figure off BG1
    lda.w #xcell_tiles
    sta $4302
    lda #$0080
    sta $4305
    lda.w #!XVRAM
    sta $2116
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    lda.w #!XVRAM+$100
    sta $2116
    lda #$0080
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    lda.l $7E62C9+!XCH
    cmp.b #!XCH+1
    bne +
    rep #$20
    lda.w #$3205+5*!XCH
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    lda.w #$3225+5*!XCH
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    lda.w #$3245+5*!XCH
    sta $2116
    lda #$211C
    sta $2118
    sta $2118
    sep #$20
+
endif
    lda #$01
    sta.l !gfx
    bra .out
.glyphs:
endif
    rep #$20
    lda.w #!GVRAM
    sta $2116
    lda #$1801
    sta $4300
    lda.w #glyph_tiles
    sta $4302
    lda.w #12*32
    sta $4305
    sep #$20
    lda.b #glyph_tiles>>16
    sta $4304
    lda #$01
    sta $420B
    lda #$FF
    sta.l !gfx
.out:
    plp
    rtl

chpal:
    db !CHPAL
chcol:
    db !CHCOL

if !OWN
cell_tiles:
    incbin "!CELL"
endif
if !XCH
xcell_tiles:
    incbin "!XCELL"
endif
glyph_tiles:
    incbin "!GLYPHS"

print "SYM end_e4 ", hex(pc())
print "SYM script_new ", hex(script_new)
print "SYM script_cont ", hex(script_cont)
print "SYM pick_op ", hex(pick_op)
print "SYM pick_apply ", hex(pick_apply)
print "SYM pick_spawn ", hex(pick_spawn)
print "SYM pick_tick ", hex(pick_tick)
print "SYM pick_nmi ", hex(pick_nmi)
