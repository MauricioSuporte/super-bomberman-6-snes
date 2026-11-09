; Bank $E4 part of asm/coop.asm (included at its end, still under org !E4).

; Benched seats: a co-op seat >= !roster (P4 in ZONE3 - D) keeps its
; bomber fields in !bench (field-major, index field * 2 + seat - 2) and
; !benched bit (1 << seat) until a stage that seats it again.
e4_bench_save:
    php
    phb
    sep #$20
    rep #$10
    pea $7E7E
    plb
    plb
    ldx #$0002
.seat:
    txa
    cmp !roster
    bcc .next                       ; fights this stage
    cmp !count
    bcs .next                       ; nobody in this seat
    lda.l seat_bits,x
    and !benched
    bne .next                       ; already saved
    lda.l seat_bits,x
    ora !benched
    sta !benched
    jsr bench_out
.next:
    inx
    cpx #$0004
    bcc .seat
    plb
    plp
    rtl

e4_bench_restore:
    php
    phb
    sep #$20
    rep #$10
    pea $7E7E
    plb
    plb
    ldx #$0002
.seat:
    txa
    cmp !roster
    bcs .next                       ; still sitting out
    lda.l seat_bits,x
    and !benched
    beq .next
    lda.l seat_bits,x
    eor #$FF
    and !benched
    sta !benched
    jsr bench_in
.next:
    inx
    cpx #$0004
    bcc .seat
    plb
    plp
    rtl

; X = seat (16-bit index, M = 8, DBR = $7E). Keeps X.
bench_out:
    phx
    stx !bseat
    ldy #$0000
-   rep #$20
    tyx
    lda.l bench_table,x
    clc
    adc !bseat
    tax                             ; field of this seat
    tya
    clc
    adc !bseat
    sec
    sbc #$0002
    phy
    tay                             ; bench slot
    sep #$20
    lda $0000,x
    sta !bench,y
    ply
    iny
    iny
    cpy #$0014
    bcc -
    plx
    rts

bench_in:
    phx
    stx !bseat
    ldy #$0000
-   rep #$20
    tyx
    lda.l bench_table,x
    clc
    adc !bseat
    tax
    tya
    clc
    adc !bseat
    sec
    sbc #$0002
    phy
    tay
    sep #$20
    lda !bench,y
    sta $0000,x
    ply
    iny
    iny
    cpy #$0014
    bcc -
    plx
    rts

bench_table:
    %bench_fields()

; ---- $C5:060E: once per stage frame, after the stock HUD selector -------
; Co-op: masks from the participants, then Start revives a dead seat
; (one shared life each, while a teammate lives), as the stock P1/P2
; rejoin does. Returns N clear so the stock two-seat rejoin is skipped.
e4_frame:
    lda.l $7E0000|!coopst
    bne .coop
    lda $17FA
    ora $17FB
    rtl
.coop:
    php
    sep #$30
    jsl e4_set_masks
    lda.l $7E1D1E
    and #$A7
    bne .out
    lda.l $7E1D23
    beq .out
    bmi .out
    ldx #$00
-   txa
    cmp.l $7E0000|!roster
    bcs .out                        ; nobody alive: stock retry / Game Over
    lda.l $7E17FA,x
    ora.l $7E15A2,x
    bpl .alive
    inx
    bra -
.alive:
    ldx #$00
.seat:
    txa
    cmp.l $7E0000|!roster
    bcs .done
    lda.l $7E17FA,x
    bpl .next
    lda $2C,x                       ; held actions (direct page, as $C5:0633)
    and #$01
    beq .next
    txa
    sta.l $7E0000|!t6
    jsr revive
    lda.l $7E1D23
    beq .done
.skip:
    lda.l $7E0000|!t6
    tax
.next:
    inx
    bra .seat
.done:
    jsl e4_set_masks
.out:
    plp
    lda #$00
    rtl

; $C0:0B44 (main loop, JSL $C022F0 once per frame): co-op upkeep.
e4_tick:
    jsl $C022F0
    php
    sep #$30
    lda.l $7E0000|!coopst
    beq +
    lda.l $7E0000|!xtimer
    cmp #$F0
    bcs ++
    inc a
    sta.l $7E0000|!xtimer
    cmp #$F0
    bne ++
    jsr lend_pages
++  jsr reclaim
+   plp
    rtl

; Four seconds into a co-op stage (its static sprite graphics are in VRAM by
; then): OBJ pages above the last static one ($7E, never written: c0_vmadd)
; join the animation pool, so eggs and Louies get tiles with four bombers.
; $1D10 = 15 lets the stock release loop ($C5:6B08) cover all 16 pages.
lend_pages:
    lda.l $7E0000|!objmax
    inc a
    tax
-   cpx #$10
    bcs +
    lda.l $7E1D00,x
    cmp #$7E
    bne ++
    lda #$FF
    sta.l $7E1D00,x
++  inx
    bra -
+   lda #$0F
    sta.l $7E1D10
    rts

; Every 16 frames, a P3/P4 bomber sharing P1's/P2's palette slot (or left
; without one) takes a free slot 4-7 back and gets its colors (not while
; riding: the Louie's colors live in the same palette).
reclaim:
    lda.l $7E0068
    and #$0F
    bne .out
    ldx #$02
.seat:
    txa
    cmp.l $7E0000|!roster
    bcs .out
    lda.l $7E17FA,x
    cmp #$60
    bcs .next
    tay                             ; Y = object
    phx
    tax
    lda.l $7E06DF,x
    plx
    cmp #$03
    bcc .borrow
    cmp #$08
    bcc .next
.borrow:
    sta.l $7E0000|!t7               ; old slot
    txa
    clc
    adc.l $7E0000|!mofs
    phx
    tax
    lda.l $7E17FA,x                 ; mount object
    plx
    cmp #$60
    bcc .next
    phx
    ldx #$04
-   lda.l $7E2B10,x
    beq .free
    inx
    cpx #$08
    bcc -
    plx
.out:
    rts
.free:
    txa
    sta.l $7E0000|!t9               ; new slot
    plx
    lda.l $7E0000|!t7
    cmp #$08
    bcs +
    jsl $C00345                     ; release the shared reference
+   phx
    lda.l $7E16DA,x
    pha
    lda.l $7E0000|!t9
    tax
    pla
    sta.l $7E2B10,x
    lda #$01
    sta.l $7E0349,x
    sta.l $7E2B20,x
    lda #$00
    sta.l $7E2B18,x
    tyx
    lda.l $7E0000|!t9
    sta.l $7E06DF,x
    plx
    lda.l $7E16DA,x
    jsl c4_colors
.next:
    inx
    jmp .seat

; Revives seat !t6 at the safe cell nearest to its spawn (one shared life).
revive:
    lda.l $7E0000|!t6
    tax
    lda.l $7E4E8D,x
    sta.l $7E0000|!t0
    lda.l $7E4EA5,x
    sta.l $7E0000|!t1
    jsr nearest
    cmp #$FF
    bne +
    rts
+    pha
    lda.l $7E0000|!t6
    sta $8D
    jsl c5_revive_fx
    lda.l $7E0000|!t6
    tax
    pla
    pha
    and #$0F
    sta.l $7E1D28
    sta.l $7E4E8D,x
    pla
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l $7E1D2A
    sta.l $7E4EA5,x
    lda #$01
    sta.l $7E15A2,x
    txa
    jsl $C42A69
    lda.l $7E0000|!t6
    jsl $C428CF
    lda.l $7E1D23
    dec a
    sta.l $7E1D23
    lda.l $7E0000|!t6
    tax
    lda.l seat_bits,x
    ora.l $7E0000|!pmask
    sta.l $7E0000|!pmask
    lda $36,x                       ; this Start does not also pause
    and #$FE
    sta $36,x
    rts

; ---- spawn (from $C2:1697) ------------------------------------------------
e4_spawn_all:
    php
    sep #$30
    jsl e4_bench_save               ; seats this stage cannot hold (Continue)
    lda.l $7E0000|!benched
    beq +
    jsl e4_bench_restore
+   jsr anchors
    ldx #$00
.seat:
    txa
    cmp.l $7E0000|!roster
    bcs .done
    lda.l seat_bits,x
    and.l $7E0000|!pmask
    beq .next
    cpx #$02
    bcs .extra
    lda.l $7E4E8D,x
    sta.l $7E1D28
    lda.l $7E4EA5,x
    sta.l $7E1D2A
    bra .spawn
.extra:                             ; P3/P4 spawn at their anchors (see anchors)
    lda.l $7E0000|!anchx-2,x
    sta.l $7E1D28
    sta.l $7E4E8D,x
    lda.l $7E0000|!anchy-2,x
    sta.l $7E1D2A
    sta.l $7E4EA5,x
    lda #$01
    sta.l $7E15A2,x
.spawn:
    txa
    jsl $C42A69
.next:
    inx
    bra .seat
.done:
    lda #$01
    sta.l $7E0000|!spawnchk
    plp
    rtl

; Spawn anchors of P3/P4 (M = X = 8). Regular stages: lower corners. Boss
; stages (recomp spawn_tile): P3 two tiles left of P1's spawn, P4 two tiles
; right of P2's, on P1's row; e4_settle moves them to the nearest safe
; floor once the arena exists.
anchors:
    lda.l $7E0000|!bossst
    bne .boss
    lda.l corner_x
    sta.l $7E0000|!anchx
    lda.l corner_x+1
    sta.l $7E0000|!anchx+1
    lda.l corner_y
    sta.l $7E0000|!anchy
    lda.l corner_y+1
    sta.l $7E0000|!anchy+1
    rts
.boss:
    lda.l $7E4E8D                   ; P1 x - 2 (at least column 1)
    cmp #$03
    bcs +
    lda #$03
+   sec
    sbc #$02
    sta.l $7E0000|!anchx
    lda.l $7E4E8E                   ; P2 x + 2 (at most column 13)
    cmp #$0C
    bcc +
    lda #$0B
+   clc
    adc #$02
    sta.l $7E0000|!anchx+1
    lda.l $7E4EA5
    sta.l $7E0000|!anchy
    sta.l $7E0000|!anchy+1
    rts

; ---- after the stage map is copied ($C5:3D5B): P3/P4 off walls -----------
e4_settle:
    php
    sep #$30
    lda #$00
    sta.l $7E0000|!spawnchk
    ldx #$02
.seat:
    txa
    cmp.l $7E0000|!roster
    bcc +
    plp
    rtl
+   lda.l seat_bits,x
    and.l $7E0000|!pmask
    beq .next
    lda.l $7E17FA,x
    bmi .next
    lda.l $7E15A2,x
    bmi .next
    lda.l $7E16AA,x
    beq .next
    sta.l $7E0000|!t4               ; current cell
    txa
    sta.l $7E0000|!t6
    lda.l $7E0000|!t4
    and #$0F
    tax
    lda.l $7E0000|!t4
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    jsr safe_xy
    bcs .keep
    lda.l $7E0000|!t6
    tax
    lda.l $7E0000|!anchx-2,x
    sta.l $7E0000|!t0
    lda.l $7E0000|!anchy-2,x
    sta.l $7E0000|!t1
    jsr nearest
    cmp #$FF
    beq .keep
    sta.l $7E0000|!t5               ; new cell
    jsr move_seat
.keep:
    lda.l $7E0000|!t6
    tax
.next:
    inx
    bra .seat

; Moves seat !t6 from cell !t4 to cell !t5 (world, object and spawn data).
move_seat:
    lda.l $7E0000|!t6
    tax
    lda.l $7E0000|!t5
    sta.l $7E16AA,x
    and #$0F
    sta.l $7E4E8D,x
    lda.l $7E0000|!t5
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l $7E4EA5,x
    ; dx
    lda.l $7E0000|!t5
    and #$0F
    sta.l $7E0000|!t2
    lda.l $7E0000|!t4
    and #$0F
    sta.l $7E0000|!t3
    lda.l $7E0000|!t2
    sec
    sbc.l $7E0000|!t3
    jsr scale16                     ; -> !t0/!t1 = 16 * signed A
    lda.l $7E182A,x
    clc
    adc.l $7E0000|!t0
    sta.l $7E182A,x
    lda.l $7E17FA,x
    phx
    tax
    rep #$20
    lda.l $7E055F,x
    clc
    adc.l $7E0000|!t0
    sta.l $7E055F,x
    sep #$20
    plx
    ; dy
    lda.l $7E0000|!t5
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l $7E0000|!t2
    lda.l $7E0000|!t4
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l $7E0000|!t3
    lda.l $7E0000|!t2
    sec
    sbc.l $7E0000|!t3
    jsr scale16
    lda.l $7E1872,x
    clc
    adc.l $7E0000|!t0
    sta.l $7E1872,x
    lda.l $7E17FA,x
    phx
    tax
    rep #$20
    lda.l $7E05BF,x
    clc
    adc.l $7E0000|!t0
    sta.l $7E05BF,x
    sep #$20
    plx
    rts

; A (signed byte) * 16 -> !t0/!t1 (16-bit). M = 8 on entry and exit.
scale16:
    rep #$20
    and #$00FF
    cmp #$0080
    bcc +
    ora #$FF00
+   asl a
    asl a
    asl a
    asl a
    sta.l $7E0000|!t0
    sep #$20
    rts

; ---- safe floor search (recomp normal_coop_mod.c floor_at/safe_at/nearest)
; Nearest safe cell to (!t0, !t1) for seat !t6 -> A ($FF = none).
nearest:
    lda #$FF
    sta.l $7E0000|!t4               ; best cell
    sta.l $7E0000|!t5               ; best distance
    ldy #$01
.row:
    ldx #$01
.col:
    txa
    sec
    sbc.l $7E0000|!t0
    bcs +
    eor #$FF
    inc a
+   sta.l $7E0000|!t2
    tya
    sec
    sbc.l $7E0000|!t1
    bcs +
    eor #$FF
    inc a
+   clc
    adc.l $7E0000|!t2
    cmp.l $7E0000|!t5
    bcs .next
    sta.l $7E0000|!t3
    jsr safe_xy
    bcc .next
    lda.l $7E0000|!t3
    sta.l $7E0000|!t5
    tya
    asl a
    asl a
    asl a
    asl a
    sta.l $7E0000|!t2
    txa
    ora.l $7E0000|!t2
    sta.l $7E0000|!t4
.next:
    inx
    cpx #$0E
    bcc .col
    iny
    cpy #$0C
    bcc .row
    lda.l $7E0000|!t4
    rts

; C = cell (X, Y) is floor, holds no other living seat (!t6 excluded) and
; has a floor neighbour. Preserves X and Y.
safe_xy:
    jsr floor_xy
    bcc .no
    tya
    asl a
    asl a
    asl a
    asl a
    sta.l $7E0000|!t7
    txa
    ora.l $7E0000|!t7
    sta.l $7E0000|!t7               ; cell
    phx
    ldx #$00
-   txa
    cmp.l $7E0000|!roster
    bcs .free
    cmp.l $7E0000|!t6
    beq +
    lda.l $7E17FA,x
    bmi +
    lda.l $7E15A2,x
    bmi +
    lda.l $7E16AA,x
    cmp.l $7E0000|!t7
    beq .taken
+   inx
    bra -
.taken:
    plx
.no:
    clc
    rts
.free:
    plx
    dex
    jsr floor_xy
    inx
    bcs .yes
    inx
    jsr floor_xy
    dex
    bcs .yes
    dey
    jsr floor_xy
    iny
    bcs .yes
    iny
    jsr floor_xy
    dey
    bcs .yes
    clc
    rts
.yes:
    sec
    rts

; C = cell (X, Y) inside the field (1-13, 1-11), static collision clear of
; $E0 and dynamic of $C0 ($1052 / $1152, 16 columns). Preserves X, Y.
floor_xy:
    cpx #$01
    bcc .no
    cpx #$0E
    bcs .no
    cpy #$01
    bcc .no
    cpy #$0C
    bcs .no
    phx
    tya
    asl a
    asl a
    asl a
    asl a
    sta.l $7E0000|!t9
    txa
    ora.l $7E0000|!t9
    tax
    lda.l $7E1052,x
    and #$E0
    bne .nox
    lda.l $7E1152,x
    and #$C0
    bne .nox
    plx
    sec
    rts
.nox:
    plx
.no:
    clc
    rts
