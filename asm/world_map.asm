; World map (tools/sb6/features/world_map.py): ZONE1 = Super Bomberman 1's
; map (its sea animation), ZONE2 = Super Bomberman 2's (scrolling stars,
; ship lights).
;
; wmap_op (FF 1A F5, through pick_op): run by the map's zone setup ($C7:1481, before the lava,
; every zone, also on L/R changes while the screen is dark). From the zone
; ($1036) table zt: the animation (!WZ), CGADSUB shadow $0314 (SB5's $C2
; darkens the lava on BG2; 0 on ZONE1/ZONE2), BG2 V scroll $0321 = 0, then
; the map music: asm/title_music.asm map_music, A = foreign driver (0 SB5's
; own map song, 1 SB1's, 2 SB2's).
;
; wmap_nmi (called by pick_nmi, forced blank), while the map is up: mode
; ($1031) 3 and task 9 running the map's script ($C7:1300-$C7:17FF); another
; mode turns it off (and puts BG2's V scroll back), a mode-3 screen with task
; 9 elsewhere (fades) only pauses it.
; * ZONE1: the sea (BG2) is one 16x16 tile everywhere (tiles $101-$104, VRAM
;   !WVRAM); the next of its !NFRAMES frames every !FTIME NMIs.
; * ZONE2: BG2 (stars, a 256-line picture) goes up one line every 2 frames;
;   the ship lights' CGRAM entries get their colors of the frame (!LPERIOD
;   frames, !NLW writes each: CGRAM address, color).
;
; State: !WZ ($0190: 0 off, 1 sea start, 2 sea, 3 stars start, 4 stars),
; $7F:FB00-$7F:FB03 (docs/FREE_SPACE.md).

asar 1.90
hirom
org !ORG

!WZ    = $000190
!timer = $7FFB00
!frame = $7FFB01
!lf    = $7FFB02
!half  = $7FFB03

wmap_nmi:
    php
    sep #$30
    lda.l !WZ
    beq .out
    lda.l $7E1031
    cmp #$03
    bne .off
    lda.l $7E0CE0               ; task 9's script pointer (bank, high byte)
    cmp #$C7
    bne .out
    lda.l $7E0CB8
    cmp #$13
    bcc .out
    cmp #$18
    bcc .run
.out:
    plp
    rtl
.off:
    lda.l !WZ
    cmp #$03
    bcc +
    rep #$20
    lda #$0000
    sta.l $7E0321               ; BG2 V scroll back
    sep #$20
+   lda #$00
    sta.l !WZ
    plp
    rtl
.run:
    lda.l !WZ
    cmp #$03
    bcc .sea
    jmp stars

.sea:
    cmp #$02
    beq +
    lda #$02
    sta.l !WZ
    lda #$00
    sta.l !frame
    lda #!FTIME
    sta.l !timer
    plp
    rtl
+   lda.l !timer
    dec a
    sta.l !timer
    beq +
    plp
    rtl
+   lda #!FTIME
    sta.l !timer
    lda.l !frame
    inc a
    cmp #!NFRAMES
    bcc +
    lda #$00
+   sta.l !frame
    rep #$20
    and #$00FF
    xba                         ; * 256
    lsr                         ; * 128
    clc
    adc.w #!FRAMES&$FFFF
    sta $4302
    lda.w #!WVRAM
    sta $2116
    lda #$0080
    sta $4305
    sep #$20
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    lda.b #!FRAMES>>16
    sta $4304
    lda #$01
    sta $420B
    plp
    rtl

stars:
    cmp #$04
    beq +
    lda #$04
    sta.l !WZ
    lda #$00
    sta.l !lf
    sta.l !half
    plp
    rtl
+   lda.l !half                 ; half a line per frame
    eor #$01
    sta.l !half
    bne +
    rep #$20
    lda.l $7E0321
    inc a
    and #$00FF
    sta.l $7E0321
    sep #$20
+   lda.l !lf
    inc a
    cmp #!LPERIOD
    bcc +
    lda #$00
+   sta.l !lf
    rep #$30
    and #$00FF
    asl a
    tax
    lda.l lofs,x
    tax
    sep #$20
    ldy.w #!NLW
-   lda.l !LIGHTS,x
    sta $2121
    lda.l !LIGHTS+1,x
    sta $2122
    lda.l !LIGHTS+2,x
    sta $2122
    inx
    inx
    inx
    dey
    bne -
    plp
    rtl

lofs:
!i = 0
while !i < !LPERIOD
    dw !i*!NLW*3
    !i #= !i+1
endif

; ---- FF 1A F5 (M/X 8-bit) --------------------------------------------------
wmap_op:
    php
    sep #$30
    lda.l $7E1036               ; zone
    and #$07
    sta.l $000192               ; scratch
    asl a
    clc
    adc.l $000192
    tax                         ; * 3
    lda.l zt,x
    sta.l !WZ
    lda.l zt+2,x
    sta.l $7E0314
    rep #$20
    lda #$0000
    sta.l $7E0321
    sep #$20
    lda.l zt+1,x
    jsl !MAP_MUSIC
    plp
    rtl

zt:                             ; per zone 0-7: animation start, driver, CGADSUB
    db !ZT

print "SYM wmap_nmi ", hex(wmap_nmi)
print "SYM wmap_op ", hex(wmap_op)
print "SYM end ", hex(pc())
