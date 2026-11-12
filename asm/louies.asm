; Louie and egg colors in a palette of their own (tools/sb6/features/louies.py).
;
; The cartridge writes the 8 colors of a mount (set 0 palettes $50-$56; an
; egg uses $52, the pink Louie) into entries 8-15 of its rider's OBJ palette
; ($C4:53EB). The bombers now use all 15 colors of theirs, so mounts and eggs
; get OBJ palette slots that hold two sets of Louie colors each:
;
;   half 1  entries 8-15 of the main palette: the cartridge's tiles as they are
;   half 2  entries 1-7 + entry 8: tiles with pixels 9-15 turned into 1-7
;           (copies of sheets $15-$22, sheet id + !DELTA). Entry 8 is the dark
;           outline, the same color in every Louie palette.
;   half 3  entries 8-15 of a spare palette, only for an egg that finds both
;           halves of the main palette taken by other colors.
;
; A half is shared by every actor that wants the same palette id. An egg only
; appears when it gets a half; a hatching Louie whose colors are not loaded
; and finds no free half of the main palette becomes one of the two Louies
; that are there. The slots are taken from the top (7 down to 3) and marked
; with palette id $FF, set $FF, so no request of the game shares them.
;
; WRAM $0160-$0188 (docs/FREE_SPACE.md), zero after reset.

asar 1.90
hirom

!ACTORS = 24            ; actor arrays are 24 bytes apart
!lhalf  = $0160         ; per actor: 0 = none, 1-3 = half
!lref   = $0178         ; 3 bytes: actors on each half
!lid    = $017B         ; 3 bytes: palette id (set 0) loaded in each half
!lslot  = $017E         ; 2 bytes: OBJ slot of the main / spare palette (0 = none)
!lt0    = $0180         ; palette id wanted
!lt1    = $0181         ; 1 = egg (may use the spare palette)
!lt2    = $0182         ; scratch
!lt3    = $0183         ; actor
!lw0    = $0184         ; word scratch (load_half)
!lw1    = $0186         ; word scratch

org !E4

half_pal:
    db 0,0,1

; ---------------------------------------------------------------------------
; $C4:53EB (JSR; A = palette id of set 0, X = actor, Y = its object): gives
; the mount or egg a half and its object that palette slot.
louie_pal:
    php
    phb
    sep #$30
    phx
    phy
    pha
    lda #$7E
    pha
    plb
    pla
    cmp #$2E                        ; burning Louie ($C4:4FD5): colors kept,
    beq .out                        ;   other actors share them
    cpx #!ACTORS
    bcs .out
    sta !lt0
    stx !lt3
    jsr validate
    stz !lt1
    ldx !lt3
    lda $16C2,x
    cmp #$09
    bne +
    inc !lt1
+   lda !lhalf,x
    beq .new
    dec a
    tax
    lda !lid,x
    cmp !lt0
    bne .swap
    ldx !lt3                        ; same colors: nothing to load
    lda !lhalf,x
    bra .set
.swap:
    ldx !lt3
    lda !lhalf,x
    stz !lhalf,x
    jsr release
.new:
    jsr acquire
    bne +
    lda !lslot                      ; nothing free: share half 1 as it is
    beq .fail
    inc !lref
    lda #$01
+   ldx !lt3
    sta !lhalf,x
.set:
    dec a
    tax
    lda.l half_pal,x
    tax
    lda !lslot,x
    ply
    phy
    sta $06DF,y
    jsr gc
    bra .out
.fail:
    ply
    phy
    lda #$FF
    sta $06DF,y
.out:
    ply
    plx
    plb
    plp
    rtl

; $C4:500C (egg coming out of a soft block, replaces the test "fewer than 2
; eggs and Louies"): C clear when the egg can get its colors. Keeps X, Y.
louie_egg_ok:
    php
    phb
    sep #$30
    phx
    phy
    lda #$7E
    pha
    plb
    jsr gc
    lda $1D1A                       ; Battle keeps the cartridge's limit too
    and #$01
    beq +
    lda $1D38
    cmp #$02
    bcs .no
+   ldx #$02                        ; a half that already has the egg's colors
-   lda !lref,x
    beq +
    lda !lid,x
    cmp #$52
    beq .yes
+   dex
    bpl -
    lda !lslot
    beq .slot                       ; no main palette yet
    lda !lref
    beq .yes
    lda !lref+1
    beq .yes
.slot:                              ; a new palette (main or spare)
    ldx #$07
-   lda $2B10,x
    beq .yes
    dex
    cpx #$03
    bcs -
.no:
    ply
    plx
    plb
    plp
    sec
    rtl
.yes:
    ply
    plx
    plb
    plp
    clc
    rtl

; $C4:5148 (hatching: LDA #5 / JSL $C01DEB, a random Louie 0-5): A = Louie.
; Keeps X, Y.
louie_hatch:
    lda #$05
    jsl $C01DEB
    php
    phb
    sep #$30
    phx
    phy
    pha
    lda #$7E
    pha
    plb
    pla
    sta !lt2
    jsr gc                          ; the egg is gone: its half may be free
    ldx !lt2
    lda.l $80C40B,x
    sta !lt0
    ldx #$01
-   lda !lref,x
    beq .ok
    lda !lid,x
    cmp !lt0
    beq .ok
    dex
    bpl -
    lda #$01                        ; two other Louies: become one of them
    jsl $C01DEB
    tax
    lda !lid,x
    sec
    sbc #$50
    sta !lt2
.ok:
    lda !lt2
    ply
    plx
    plb
    plp
    rtl

; $C4:5458 (mount tiles: LDA ($BD),Y / STA $AB, the sheet of the animation;
; X = actor, DBR = $80): half 2 uses the recolored sheets.
louie_sheet:
    lda ($BD),y
    pha
    cpx #!ACTORS
    bcs +
    lda.l $7E0000|!lhalf,x
    cmp #$02
    bne +
    pla
    clc
    adc.b #!DELTA
    sta $AB
    rtl
+   pla
    sta $AB
    rtl

; Once per frame (main loop, from e4_tick): halves of actors that are gone.
louie_tick:
    php
    phb
    sep #$30
    lda #$7E
    pha
    plb
    jsr gc
    plb
    plp
    rtl

; ---------------------------------------------------------------------------
; Internal: M/X 8-bit, DBR = $7E.

; The slot table is cleared between stages: a palette whose slot lost its
; mark is forgotten with everything on it.
validate:
    ldy #$01
.pal:
    ldx !lslot,y
    beq .next
    lda $2B10,x
    cmp #$FF
    bne .drop
    lda #$7F                        ; objects released with this slot never
    sta $0349,x                     ;   free it
    bra .next
.drop:
    lda #$00
    sta !lslot,y
    cpy #$00
    bne +
    stz !lref
    stz !lref+1
    stz !lid
    stz !lid+1
    bra ++
+   stz !lref+2
    stz !lid+2
++  ldx #!ACTORS-1
-   lda !lhalf,x
    beq +
    cmp #$03
    bcc .main
    cpy #$00                        ; half 3 = spare palette
    beq +
    bra .clr
.main:
    cpy #$00
    bne +
.clr:
    stz !lhalf,x
+   dex
    bpl -
.next:
    dey
    bpl .pal
    rts

; Releases the halves of actors without an object.
gc:
    jsr validate
    ldx #!ACTORS-1
-   lda !lhalf,x
    beq +
    lda $17FA,x
    bpl +
    lda !lhalf,x
    stz !lhalf,x
    jsr release
+   dex
    bpl -
    rts

; A = half (1-3) losing an actor. Keeps X, Y.
release:
    phx
    phy
    dec a
    tax
    lda !lref,x
    beq .out
    dec a
    sta !lref,x
    bne .out
    stz !lid,x
    lda.l half_pal,x
    tay                             ; palette
    bne .spare
    lda !lref
    ora !lref+1
    bne .out
    bra .free
.spare:
    lda !lref+2
    bne .out
.free:
    ldx !lslot,y
    lda #$00
    sta !lslot,y
    cpx #$00
    beq .out
    stz $2B10,x
    stz $2B18,x
    stz $2B20,x
    stz $0349,x
.out:
    ply
    plx
    rts

; !lt0 = palette id, !lt1 = egg. Returns A (and Z) = half, 0 = none.
acquire:
    ldx #$00                        ; a half with these colors
-   lda !lref,x
    beq +
    lda !lid,x
    cmp !lt0
    beq .share
+   inx
    cpx #$02
    bcc -
    lda !lt1
    beq +
    lda !lref+2                     ; (the spare palette only holds eggs)
    bne .share
+   ldx #$00                        ; a free half of the main palette
-   lda !lref,x
    beq .take
    inx
    cpx #$02
    bcc -
    lda !lt1
    beq .none
    ldx #$02                        ; an egg: the spare palette
.take:
    lda.l half_pal,x
    tay
    jsr slot_get
    bcs .none
    lda #$01
    sta !lref,x
    lda !lt0
    sta !lid,x
    jsr load_half
    txa
    inc a
    rts
.share:
    inc !lref,x
    txa
    inc a
    rts
.none:
    lda #$00
    rts

; Y = palette (0 main, 1 spare): C clear when it has an OBJ slot (the highest
; free one of 7-3 is taken). Keeps X, Y.
slot_get:
    lda !lslot,y
    bne .ok
    phx
    ldx #$07
-   lda $2B10,x
    beq .found
    dex
    cpx #$03
    bcs -
    plx
    sec
    rts
.found:
    lda #$FF
    sta $2B10,x
    sta $2B18,x
    lda #$01
    sta $2B20,x
    lda #$7F
    sta $0349,x
    txa
    sta !lslot,y
    plx
.ok:
    clc
    rts

; Colors of palette id !lt0 (set 0: $81:8000 + 2*(id-1) -> [dest16, count16,
; 8 colors]) into half X+1 of the CGRAM shadow $7E:2910, and into the blink
; backup of that palette ($C1:0015), which $C4:2EC3 copies back. Keeps X.
load_half:
    phx
    rep #$30
    txa
    and #$00FF
    sta !lw0
    lda !lt0
    and #$00FF
    dec a
    asl a
    tax
    lda.l $818000,x
    sta $A8
    sep #$20
    lda #$81
    sta $AA
    rep #$20
    ldx !lw0
    lda.l half_pal,x
    and #$00FF
    tax
    lda !lslot,x
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc #$0080
    asl a
    sta !lw1                        ; shadow offset of the palette's entry 0
    clc
    adc #$0010
    tax                             ; entry 8
    lda !lw0
    cmp #$0001
    beq .low
    ldy #$0004
-   lda [$A8],y
    sta $2910,x
    inx
    inx
    iny
    iny
    cpy #$0014
    bcc -
    bra .done
.low:
    ldy #$0004                      ; outline -> entry 8
    lda [$A8],y
    sta $2910,x
    ldx !lw1
    inx
    inx
    ldy #$0006                      ; colors 1-7 -> entries 1-7
-   lda [$A8],y
    sta $2910,x
    inx
    inx
    iny
    iny
    cpy #$0014
    bcc -
.done:
    ldx !lw0
    lda.l half_pal,x
    and #$00FF
    tax
    sep #$30
    lda !lslot,x
    ora #$08
    jsl $C10015
    jsl $C0023E
    plx
    rts

print "SYM end_e4 ", hex(pc())
print "SYM louie_pal ", hex(louie_pal)
print "SYM louie_egg_ok ", hex(louie_egg_ok)
print "SYM louie_hatch ", hex(louie_hatch)
print "SYM louie_sheet ", hex(louie_sheet)
print "SYM louie_tick ", hex(louie_tick)
