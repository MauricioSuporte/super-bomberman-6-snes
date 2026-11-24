; SB6 stage HUD of the Normal Game (tools/sb6/features/hud.py has the overview and builds the tables).
;
; * hud_begin (JSL at $C5:054A, the stage HUD task's start): SB6 HUD off; returns LDA $1D1A.
; * hud_load (JSL at $C5:05C6, M 8): Battle loads SB5's HUD tiles (set 3 $49) as before; the Normal Game
;   queues the SB6 HUD's BG2 / BG3 tiles and each seat's head (build_heads: the character select's character
;   and skin), asks for the rows (!full) and turns the HUD on (!on = $A5).
; * hud_tick (JSL at $C5:06CD, every frame of the HUD task, M 8): without the SB6 HUD SB5's score redraw
;   test (A = $0069 ^ $10, Z); with it, every 4th frame: the rows when asked (after the load; after a pause,
;   whose menu rewrites BG3 rows: hud_irq asks while $1D1D is set), else the lives and one seat: its record
;   (build_rec) against the one shown, and when it changed its numbered cells, BG2 cells and BG3 block are
;   queued; returns Z clear (SB5's score is not drawn).
; * hud_irq / hud_irq_b (JSL from SB5's stage IRQ, line 0, D = $2100): the HUD lines' BG3 / BG2 vertical
;   scroll (SB6 rows or SB5's).
; * time_gate (JSL at $C5:042E, the clock task): with the SB6 HUD the clock task stops there (no countdown,
;   hurry or time up in the Normal Game).
;
; State $7F:FB40-$7F:FBAF, heads drawn in $7F:EC00-$7F:EDFF (docs/FREE_SPACE.md).

asar 1.90
hirom
org !ORG

!V      = $7FFB40
!on     = !V+$00        ; $A5 = SB6 HUD shown
!lv     = !V+$01        ; lives shown
!turn   = !V+$02        ; seat checked last
!seat   = !V+$03
!rec    = !V+$04        ; 11 bytes: act, fire, speed, bombs, bomb type, power-ups x 6
!t0     = !V+$0F
!cache  = !V+$10        ; 4 x 11: the records shown ($FF = draw again)
!qv     = !V+$3C        ; queue entry: VRAM word, bytes (words)
!qn     = !V+$3E
!src    = !V+$40        ; word
!left   = !V+$42        ; word
!cnt    = !V+$44        ; word
!seat7  = !V+$46        ; word: 7 * seat
!t1     = !V+$48
!t2     = !V+$4A        ; word
!bs     = !V+$4C        ; word: BG3 block source
!bv     = !V+$4E        ; word: its VRAM word
!bn     = !V+$50        ; word: rows left
!full   = !V+$52        ; rows to queue: 1 = at the next check, n = n checks later (0 = none)
!hpal   = !V+$53        ; 4: each seat's head tiles in palette 1 (bit per tile)
!qw     = !V+$57        ; 1 = qcopy reads WRAM bank $7F
!hs     = !V+$58        ; head being drawn: seat
!hb     = !V+$59        ; its tile palettes
!hr     = !V+$5A        ; word: its skin record (bank of the tables)
!hp     = !V+$5C        ; word: template pixel
!ht     = !V+$5E        ; tile 0-3
!hy     = !V+$5F
!hx     = !V+$60
!p0     = !V+$61        ; 4 bit planes of a row
!hd     = !V+$66        ; word: buffer offset
!cd     = !V+$68        ; row_words: code
!bst    = !V+$6A        ; per seat: BG3 block state drawn (0 in, 1 PUSH START, 2 blank; $FF = draw it)
!REC    = 11
!BUF    = $7FEC00       ; heads, 128 bytes per seat
!PK     = $7FFF00       ; asm/picker.asm: +1 choices valid, +2 choice (1-7) per seat, +8 color per seat

hud_begin:
    lda #$00
    sta.l !on
    lda.l $7E1D1A
    rtl

hud_load:
    lda.l $7E1D1A
    and #$01
    beq .normal
    lda #$49                    ; Battle: SB5's HUD tiles ($0AE7 = 3), its RTL returns to the task
    jml $C0180F
.normal:
    php
    rep #$30
    phx
    phy
    phb
    sep #$30
    lda #$7E
    pha
    plb
    rep #$30
    lda.w #!BG2TV
    ldx.w #!BG2T&$FFFF
    ldy.w #!BG2TN
    jsr qcopy
    lda.w #!BG3TV
    ldx.w #!BG3T&$FFFF
    ldy.w #!BG3TN
    jsr qcopy
    jsr build_heads
    jsr purple
    sep #$30
    lda #$01
    sta.l !full
    lda #$00
    sta.l !turn
    lda #$A5
    sta.l !on
    rep #$30
    plb
    ply
    plx
    plp
    rtl

; every row of the HUD (BG2 / BG3 HUD rows, the field's BG3 rows 2-4), every seat and the lives drawn again;
; M/X 16, DB $7E
full_rows:
    lda.w #!BG2MV
    ldx.w #!BG2M&$FFFF
    ldy.w #256
    jsr qcopy
    lda.w #!BG1MV
    ldx.w #!BG1M&$FFFF
    ldy.w #256
    jsr qcopy
    lda.w #!BG3MV
    ldx.w #!BG3M&$FFFF
    ldy.w #!BG3MN
    jsr qcopy
    lda.w #!FLDMV
    ldx.w #!FLDM&$FFFF
    ldy.w #192
    jsr qcopy
    sep #$30
    lda #$FF
    sta.l !lv
    ldx #4*!REC-1
-   sta.l !cache,x
    dex
    bpl -
    sta.l !bst                  ; the BG3 rows were queued blank: every block again
    sta.l !bst+1
    sta.l !bst+2
    sta.l !bst+3
    rep #$30
    rts

hud_tick:
    lda.l !on
    cmp #$A5
    beq .mine
    lda.l $7E0069               ; SB5: LDA $0069 / EOR #$10 / BIT #$1F
    eor #$10
    bit #$1F
    rtl
.mine:
    lda.l $7E0069               ; the check runs every 4th frame (a seat each time: all four in 16 frames)
    and #$03
    beq .work
    lda.b #$01                  ; Z clear: SB5's score redraw is skipped
    rtl
.work:
    php
    rep #$30
    phx
    phy
    phb
    sep #$30
    lda #$7E
    pha
    plb
    lda.l !full
    beq .check
    lda.w $1D1D                 ; paused: wait
    bne .done
    lda.l !full
    dec a
    sta.l !full
    bne .done
    rep #$30
    jsr full_rows
    sep #$30
    bra .done
.check:
    jsr purple
    sep #$30
    jsr lives
    lda.l !turn
    inc a
    and #$03
    sta.l !turn
    sta.l !seat
    tax
    jsr build_rec
    jsr compare
.done:
    rep #$30
    plb
    ply
    plx
    plp
    lda.b #$01                  ; Z clear: SB5's score redraw is skipped
    rtl

; CGRAM 15 = the HUD's purple (hud.py PURPLE: SB5's pink, BG3 palette 3, unused in the Normal Game) in the CGRAM
; copy, sent by SB5's NMI ($0351) when a palette load put the pink back; M/X any, DB $7E
purple:
    php
    rep #$20
    lda.l !PURPLEA
    cmp.w #!PURPLE
    beq +
    lda.w #!PURPLE
    sta.l !PURPLEA
    sep #$20
    lda #$01
    sta.l $7E0351
+   plp
    rts

; the shared lives ($1D23, 0-9): the tab's heart (2 BG3 tiles); M/X 8, DB $7E
lives:
    lda.w $1D23
    bpl +
    lda #$00
+   cmp #10
    bcc +
    lda #9
+   cmp.l !lv
    beq .same
    sta.l !lv
    rep #$30
    and.w #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc.w #!LIVSRC&$FFFF
    tax
    lda.w #!LIVESV
    ldy.w #32
    jsr qcopy
    sep #$30
.same:
    rts

; A = numbered tile (kind * 10 + value) -> X = its offset in the tables' bank; M/X 16
tile_src:
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc.w #!DYNSRC&$FFFF
    tax
    rts

; seat X's record into !rec (hud.py record()); M/X 8, DB $7E
build_rec:
    phx
    ldx #!REC-1
    lda #$00
-   sta.l !rec,x
    dex
    bpl -
    plx
    lda.w $17FA,x
    bmi .out
    lda.w $15A2,x
    bpl .in
.out:
    lda.w $0069                 ; out: PUSH START's blink phase (64 frames)
    asl a
    asl a
    lda #$00
    rol a
    sta.l !rec+1
    rts
.in:
    lda #$01
    sta.l !rec
    lda.w $17CA,x               ; fire range (full fire at 8)
    cmp #10
    bcc +
    lda #9
+   sta.l !rec+1
    cmp #8
    bcc +
    lda #!I_FULL
    sta.l !rec+7
+   lda.w $15EA,x               ; speed: 1 below $E0, else (speed - $C0) / $20, at most 9
    xba
    lda.w $15D2,x
    rep #$20
    cmp.w #$00E0
    bcs +
    lda.w #$00E0
+   sec
    sbc.w #$00C0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    cmp.w #10
    bcc +
    lda.w #9
+   sep #$20
    sta.l !rec+2
    lda.w $4EBD,x               ; bombs
    cmp #10
    bcc +
    lda #9
+   sta.l !rec+3
    lda.w $4ED5,x               ; abilities: bomb type remote > pierce > search > magnet (SB5's mine bit)
    sta.l !t0
    ldy #!I_REMOTE
    bit #$01
    bne .bt
    ldy #!I_PIERCE
    bit #$10
    bne .bt
    ldy #!I_SEARCH
    bit #$40
    bne .bt
    ldy #!I_MAGNET
    bit #$20
    bne .bt
    ldy #!I_NORMAL
.bt:
    tya
    sta.l !rec+4
    lda.w $1662,x               ; a heart (one more hit)
    beq +
    lda #!I_HEART
    sta.l !rec+5
+   lda.w $167A,x               ; bit 5 clear: through soft blocks
    and #$20
    bne +
    lda #!I_WPASS
    sta.l !rec+6
+   lda.l !t0                   ; kick, else bomb pass ($167A bit 6 clear)
    and #$02
    beq .nokick
    lda #!I_KICK
    bra .kp
.nokick:
    lda.w $167A,x
    and #$40
    bne .pu
    lda #!I_BPASS
.kp:
    sta.l !rec+8
.pu:
    lda.l !t0
    and #$08
    beq +
    lda #!I_PUNCH
    sta.l !rec+9
+   lda.l !t0
    and #$04
    beq .done
    lda #!I_GLOVE
    sta.l !rec+10
.done:
    rts

; !rec against seat !seat's cache: when it changed, the cache takes it and the seat is drawn; M/X 8
compare:
    lda.l !seat
    tax
    lda.l elevens,x
    tax
    phb
    lda #$7F
    pha
    plb
    lda #$00
    sta.w !t1&$FFFF
    ldy #$00
-   lda.w !rec&$FFFF,y
    cmp.w !cache&$FFFF,x
    beq +
    sta.w !cache&$FFFF,x
    lda #$01
    sta.w !t1&$FFFF
+   inx
    iny
    cpy #!REC
    bne -
    plb
    lda.l !t1
    beq +
    jsr draw_seat
+   rts

; queue seat !seat: numbered cells (in the game), BG2 rows A / B, BG3 block; M/X 8, DB $7E
draw_seat:
    lda.l !seat
    tax
    lda.l sevens,x
    sta.l !seat7
    lda #$00
    sta.l !seat7+1
    lda.l !rec
    beq .rows
    lda #$00
    jsr dyn_cell
    lda #$01
    jsr dyn_cell
    lda #$02
    jsr dyn_cell
.rows:
    rep #$30
    lda.l !seat                 ; rows A / B: BG2 (seats 1, 4) or BG1 (seats 2, 3)
    and.w #$00FF
    asl a
    tax
    lda.l rowa,x
    sta.l !bv
    ldx.w #0
    jsr row_words
    lda.l !bv
    clc
    adc.w #32
    ldx.w #7
    jsr row_words
    lda.l !seat                 ; BG3 block of (seat, state): BG3ROWS rows from blockw
    and.w #$00FF
    sta.l !t2
    asl a
    adc.l !t2                   ; seat * 3 + state (0 in, 1 PUSH START, 2 blank)
    sta.l !t2
    lda.l !rec
    and.w #$00FF
    bne +
    lda.l !rec+1
    and.w #$00FF
    eor.w #$0001
    inc a
    bra ++
+   lda.w #0
++  pha                         ; the block only when the seat's state changed (not with its numbers)
    lda.l !seat
    and.w #$00FF
    tax
    pla
    sep #$20
    cmp.l !bst,x
    bne +
    brl .same
+   sta.l !bst,x
    rep #$20
    and.w #$00FF
    clc
    adc.l !t2
    asl a
    tax
    lda.l blkoff,x
    sta.l !bs
    lda.l !seat
    and.w #$00FF
    asl a
    tax
    lda.l blkv,x
    sta.l !bv
    lda.l blkn,x
    sta.l !t2
    lda.w #!BG3ROWS
    sta.l !bn
-   lda.l !bs
    tax
    lda.l !t2
    tay
    lda.l !bv
    jsr qcopy
    lda.l !bs
    clc
    adc.l !t2
    sta.l !bs
    lda.l !bv
    clc
    adc.w #32
    sta.l !bv
    lda.l !bn
    dec a
    sta.l !bn
    bne -
.same:
    sep #$30
    rts

; A = kind (0 fire, 1 speed, 2 bombs): seat !seat's numbered tile = DYNSRC tile 10 * kind + value; M/X 8
dyn_cell:
    sta.l !t1
    tax
    lda.l !rec+1,x
    clc
    adc.l tens,x
    rep #$30
    and.w #$00FF
    jsr tile_src
    phx
    sep #$30
    lda.l !seat
    tax
    lda.l threes,x
    clc
    adc.l !t1
    rep #$30
    and.w #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc.w #!DYNV
    plx
    ldy.w #32
    jsr qcopy
    sep #$30
    rts

; A = VRAM word, X = first of 7 codes (codes: < $80 seat word n, 0-3 = head tiles with the seat's palettes,
; else the icon of record byte code & $7F); an out seat gets blanks. M/X 16, DB $7E
row_words:
    pha
    txa
    sta.l !src
    pla
    ldy.w #14
    jsr qopen
    lda.w #7
    sta.l !cnt
.w:
    lda.l !rec
    and.w #$00FF
    beq .blank
    lda.l !src
    tax
    lda.l codes,x
    and.w #$00FF
    sta.l !cd
    bit.w #$0080
    bne .icon
    clc
    adc.l !seat7
    asl a
    tax
    lda.l seatw,x
    pha
    lda.l !cd
    cmp.w #4
    bcs .plain
    lda.l !seat                 ; head tile: palette 1 when its bit is set
    and.w #$00FF
    tax
    lda.l !hpal,x
    and.w #$00FF
    sta.l !t2
    lda.l !cd
    tax
    lda.l !t2
-   dex
    bmi +
    lsr a
    bra -
+   and.w #$0001
    beq +
    pla
    and.w #$E3FF
    ora.w #$0400
    bra .put
+   pla
    and.w #$E3FF
    bra .put
.plain:
    pla
    bra .put
.icon:
    and.w #$007F
    tax
    lda.l !rec,x
    and.w #$00FF
    asl a
    tax
    lda.l iconw,x
    bra .put
.blank:
    lda.l iconw
.put:
    sta.w $8000,y
    iny
    iny
    lda.l !src
    inc a
    sta.l !src
    lda.l !cnt
    dec a
    sta.l !cnt
    beq +
    brl .w
+   jsr qclose
    rts

; each seat's head: the character select's character and skin (template + skin record), else SB5's head (the
; tiles hud_load sent). Variables: !hs seat, !t1 character, !hr skin record, !hb its tile palettes, !bs the
; template, !ht tile, !hp its pixel, !hy / !hx row / column, !t2 buffer offset of the tile; M/X 16, DB $7E
build_heads:
    sep #$20
    lda #$00
    sta.l !hpal
    sta.l !hpal+1
    sta.l !hpal+2
    sta.l !hpal+3
    sta.l !hs
.seat:
    lda.l !PK+1
    cmp #$01
    beq +
    brl .next
+   rep #$20
    lda.l !hs
    and.w #$00FF
    tax
    sep #$20
    lda.l !PK+2,x
    dec a
    cmp #!NCH
    bcc +
    brl .next
+   sta.l !t1
    lda.l !PK+8,x               ; skin
    sta.l !t0
    rep #$20
    lda.l !t1
    and.w #$00FF
    asl a
    asl a
    tax
    lda.l !t0
    and.w #$00FF
    cmp.l hchr+2,x              ; skins of the character
    bcc +
    brl .next
+   sta.l !t2                   ; record = hchr[c] + skin * HREC
    lda.w #0
    ldy.w #!HREC
-   clc
    adc.l !t2
    dey
    bne -
    clc
    adc.l hchr,x
    sta.l !hr
    tax
    lda.l !t1                   ; template = HTPL + (2c + (seat > 0)) * 256: seats 2-4 1 pixel left
    and.w #$00FF
    asl a
    sta.l !t2
    lda.l !hs
    and.w #$00FF
    beq +
    lda.w #1
+   clc
    adc.l !t2
    xba
    clc
    adc.w #!HTPL&$FFFF
    sta.l !bs
    sep #$20
    lda.l !hs                   ; tile palettes: bits 0-3 (P1's template), 4-7 (seats 2-4)
    beq +
    lda.l !DATABANK,x
    lsr a
    lsr a
    lsr a
    lsr a
    bra ++
+   lda.l !DATABANK,x
++  sta.l !hb
    pha
    rep #$20
    lda.l !hs
    and.w #$00FF
    tax
    sep #$20
    pla
    sta.l !hpal,x
    lda #$00
    sta.l !ht
.tile:
    rep #$20                    ; first pixel: template + (t >> 1) * 128 + (t & 1) * 8
    lda.l !ht
    and.w #$0002
    beq +
    lda.w #128
+   sta.l !hp
    lda.l !ht
    and.w #$0001
    beq +
    lda.w #8
+   clc
    adc.l !hp
    adc.l !bs
    sta.l !hp
    lda.l !hs                   ; buffer: seat * 128 + tile * 32
    and.w #$0003
    xba
    lsr a
    sta.l !t2
    lda.l !ht
    and.w #$0003
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc.l !t2
    sta.l !t2
    sep #$20
    lda.l !hb                   ; this tile's palette bit -> !t0 (0 / 1)
    sta.l !t0
    lda.l !ht
-   beq +
    pha
    lda.l !t0
    lsr a
    sta.l !t0
    pla
    dec a
    bra -
+   lda.l !t0
    and #$01
    sta.l !t0
    lda #$00
    sta.l !hy
.row:
    lda #$00
    sta.l !p0
    sta.l !p0+1
    sta.l !p0+2
    sta.l !p0+3
    sta.l !hx
.px:
    rep #$20
    lda.l !hx
    and.w #$00FF
    clc
    adc.l !hp
    tax
    lda.l !DATABANK,x           ; class
    and.w #$00FF
    sec                         ; map byte = record + 1 + class
    adc.l !hr
    tax
    sep #$20
    lda.l !DATABANK,x
    pha
    lda.l !t0
    beq +
    pla
    lsr a
    lsr a
    lsr a
    lsr a
    bra ++
+   pla
++  ldx.w #0
-   lsr a                       ; bit k of the entry -> plane k
    pha
    lda.l !p0,x
    rol a
    sta.l !p0,x
    pla
    inx
    cpx.w #4
    bne -
    lda.l !hx
    inc a
    sta.l !hx
    cmp #8
    bcc .px
    rep #$20                    ; the row: planes 0 / 1 at 2y, 2 / 3 at 16 + 2y
    lda.l !hy
    and.w #$00FF
    asl a
    clc
    adc.l !t2
    tax
    sep #$20
    lda.l !p0
    sta.l !BUF,x
    lda.l !p0+1
    sta.l !BUF+1,x
    lda.l !p0+2
    sta.l !BUF+16,x
    lda.l !p0+3
    sta.l !BUF+17,x
    rep #$20
    lda.l !hp
    clc
    adc.w #16
    sta.l !hp
    sep #$20
    lda.l !hy
    inc a
    sta.l !hy
    cmp #8
    bcs +
    brl .row
+   lda.l !ht
    inc a
    sta.l !ht
    cmp #4
    bcs +
    brl .tile
+   rep #$20                    ; the seat's 4 tiles to VRAM (from bank $7F)
    lda.l !hs
    and.w #$0003
    xba
    lsr a
    pha
    clc
    adc.w #!BUF&$FFFF
    tax
    pla
    lsr a                       ; seat * 64 words
    clc
    adc.w #!HEADV
    ldy.w #128
    pha
    sep #$20
    lda #$01
    sta.l !qw
    rep #$20
    pla
    jsr qcopy
    sep #$20
    lda #$00
    sta.l !qw
.next:
    sep #$20
    lda.l !hs
    inc a
    sta.l !hs
    cmp #4
    bcs +
    brl .seat
+   rep #$30
    rts

; SB5's VRAM queue ($7E:8000 ring, write offset $0357; entries [$0084, bytes, VRAM word, data] as
; asm/sb1_enemies.asm cqueue): A = VRAM word, Y = bytes -> Y = ring offset of the data; M/X 16, DB $7E
qopen:
    sta.l !qv
    tya
    sta.l !qn
    lda.w $0357
    tay
    lda.w #$0084
    sta.w $8000,y
    lda.l !qn
    sta.w $8002,y
    lda.l !qv
    sta.w $8004,y
    tya
    clc
    adc.w #6
    tay
    rts

qclose:
    lda.w $0357
    clc
    adc.w #6
    adc.l !qn
    and.w #$3FFF
    sta.w $0357
    rts

; A = VRAM word, X = source offset in the tables' bank (or bank $7F when !qw = 1), Y = bytes (even), in
; entries of up to 256 bytes; M/X 16, DB $7E
qcopy:
    sta.l !qv
    txa
    sta.l !src
    tya
    sta.l !left
.next:
    lda.l !left
    cmp.w #$0100
    bcc +
    lda.w #$0100
+   tay
    lda.l !qv
    jsr qopen
    lda.l !src
    tax
    lda.l !qn
    sta.l !cnt
    lda.l !qw
    and.w #$00FF
    bne .wram
-   lda.l !DATABANK,x
    sta.w $8000,y
    inx
    inx
    iny
    iny
    lda.l !cnt
    dec a
    dec a
    sta.l !cnt
    bne -
    bra .end
.wram:
-   lda.l $7F0000,x
    sta.w $8000,y
    inx
    inx
    iny
    iny
    lda.l !cnt
    dec a
    dec a
    sta.l !cnt
    bne -
.end:
    jsr qclose
    lda.l !src
    clc
    adc.l !qn
    sta.l !src
    lda.l !qn
    lsr a
    clc
    adc.l !qv
    sta.l !qv
    lda.l !left
    sec
    sbc.l !qn
    sta.l !left
    beq +
    brl .next
+   rts

; stage IRQ, line 0 (D = $2100, M/X 8): BG3 / BG2 vertical scroll of the HUD lines; a pause asks for the rows
hud_irq:
    lda.l !on
    cmp #$A5
    bne .stock
    lda.l $7E1D1D
    beq +
    lda #$04
    sta.l !full
+   lda.b #!VOFS3&$FF
    sta $12
    lda.b #!VOFS3>>8
    sta $12
    lda.b #!VOFS2&$FF
    sta $10
    lda.b #!VOFS2>>8
    sta $10
    lda #$3C                    ; BG1 (seats 2, 3): map $3C00 rows 24-27, 4 pixels right of BG2
    sta $07
    lda.b #!HOFS1&$FF
    sta $0D
    lda.b #!HOFS1>>8
    sta $0D
    lda.b #!VOFS1&$FF
    sta $0E
    lda.b #!VOFS1>>8
    sta $0E
    lda #$17                    ; TM: SB5's $16 + BG1
    sta $2C
    rtl
.stock:
    lda #$FC                    ; SB5: BG3 -4, BG2 256
    sta $12
    lda #$FF
    sta $12
    stz $10
    lda #$01
    sta $10
    rtl

; stage IRQ, line 21 ($C0:F0F1, after SB5's writes, D = $2100, DB $00, M/X 8): BG1 back to the field (BG1SC
; $0368, scroll $0331 / $0337: the NMI's copies; BG1's HUD rows are see-through from HUD line 20, so a late write
; shows nothing) and window 2 on x WINL-WINR for BG1 / BG2 (the backdrop behind the lives heart) until the
; line-31 IRQ (hud.py apply); then SB5's next IRQ line ($17)
hud_l21:
    lda.l !on
    cmp #$A5
    bne .out
    lda.w $0368
    sta $07
    lda.w $0331
    sta $0D
    lda.w $0332
    sta $0D
    lda.w $0337
    sta $0E
    lda.w $0338
    sta $0E
    lda #!WINL
    sta $28
    lda #!WINR
    sta $29
    lda.w $0306
    ora #$88
    sta $23
    lda.w $0311
    ora #$03
    sta $2E
    lda.w $0312                 ; the subscreen too (the pause adds half of it on the backdrop)
    ora #$03
    sta $2F
    lda.w $030D                 ; BG1 / BG2 windows combined with OR (SB5 leaves BG2's AND: with the pause's
    and #$F0                    ; window 1 on, window 2 alone would hide nothing); outside window 2 the same
    sta $2A
.out:
    lda #$17
    sta.w $4209
    rtl

hud_irq_b:                      ; ($C0:F12A's line 0 also sets BG1's vertical scroll $00FC; line $15 sets it again)
    jsl hud_irq
    lda #$FC
    sta $0E
    stz $0E
    rtl

time_gate:
    lda.l !on
    cmp #$A5
    bne .stock
    pla                         ; leave the clock task's frame as its RTL at $C5:048F does
    pla
    pla
    rtl
.stock:
    lda.l $7E34AD
    rtl

elevens: db 0, 11, 22, 33
sevens:  db 0, 7, 14, 21
threes:  db 0, 3, 6, 9
tens:    db 0, 10, 20
rowa:    dw !ROWA                           ; per seat: VRAM word of its row A (row B = + 32)
blkv:    dw !BLKV                           ; per seat: VRAM word of its BG3 block's first row
blkn:    dw !BLKN                           ; its bytes per row
codes:   db 0, 1, 4, 5, $85, $86, $87       ; row A: head TL, TR, fire, speed, heart, soft block pass, full fire
         db 2, 3, 6, $84, $88, $89, $8A     ; row B: head BL, BR, bombs, bomb type, kick / bomb pass, punch, glove
blkoff:  dw !BLKOFF                         ; per seat and state
hchr:    dw !HCHR                           ; per character: its skin records, skins
seatw:   dw !SEATW                          ; per seat: head TL, TR, BL, BR, fire, speed, bombs
iconw:   dw !ICONW
blockw:  dw !BLOCKW                         ; per seat and state (in, PUSH START, blank): BG3ROWS rows of BG3 words

print "SYM hud_begin ", hex(hud_begin)
print "SYM hud_load ", hex(hud_load)
print "SYM hud_tick ", hex(hud_tick)
print "SYM hud_irq ", hex(hud_irq)
print "SYM hud_irq_b ", hex(hud_irq_b)
print "SYM hud_l21 ", hex(hud_l21)
print "SYM time_gate ", hex(time_gate)
print "SYM build_heads ", hex(build_heads)
print "SYM draw_seat ", hex(draw_seat)
end:
print "SYM end ", hex(end)
