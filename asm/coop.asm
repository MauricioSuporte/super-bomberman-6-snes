; Normal Game for up to four players (port of the five-player co-op mod of
; SuperBomberman5SNESRecomp, normal_coop_mod.c + coop_corner_spawns_mod.c).
;
; Seats 3/4 are pads 3/4 (multitap on port 2; the cartridge's pad reader
; $C0:0A56 already fills the per-seat arrays $2C/$31/$36+seat for five pads).
; With one or two players every hook below takes the cartridge's own path:
; `!coopst` (this stage is a co-op stage) is set only by c4_stage_slots when
; `!count` >= 3 and the mode is a campaign stage.
;
; Boss stages ($67-$6E, `!bossst`): the rival bomber is created in bomber
; slot 4 (P5) instead of slot 2 (P3), so up to four players fight it.
; ZONE3 - D ($6A) has two rivals (slots 3/4): three players fight, P4 sits
; out with its bomber fields saved for the next stage. Boss stages always
; use the five-slot layout below, also with one or two players.
;
; Actor layout in a co-op stage (as in the recomp mod): seats 0-3 = actors
; 0-3, enemies 5-18 (`!mbase` caps the allocator), mounts rider + 19
; (`!mofs`, read by the 28 rider<->mount conversions instead of $1CBF),
; $1CBF = 5 bomber slots.
;
; Hooks and generated loop stubs: tools/sb6/features/coop.py.
; WRAM: $0110-$0154 (docs/FREE_SPACE.md); zeroed by the reset routine,
; initialised by `coop_boot` ($80:F393).

asar 1.90
hirom

!DIST     = $0110       ; 6 arrays x 4 seats (enemy -> player distances)
!mofs     = $0128       ; mount offset (rider + !mofs)
!count    = $0129       ; players chosen on the title (1-4)
!roster   = $012A       ; seats looped over in this stage (word, 2 = stock)
!pmask    = $012C       ; co-op participation mask
!mbase    = $012D       ; first mount actor (enemies stop below; $18 = stock)
!coopst   = $012E       ; 1 = this stage runs the co-op rules
!spawnchk = $012F       ; settle P3/P4 once the stage map exists
!bench    = $0130       ; 10 fields x 2 seats (benched seats: P4 in ZONE3 - D)
!benched  = $0144
!t0       = $0145       ; scratch (E4 routines, DBR = $7E)
!t1       = $0146
!t2       = $0147
!t3       = $0148
!t4       = $0149
!t5       = $014A
!t6       = $014B
!t7       = $014C
!t8       = $014D
!t9       = $014E
!pfneed   = $014F       ; OBJ palette arbitration (c0_palfail), own scratch:
!pfrun    = $0150       ;   it can run inside revive/spawn, which use !t0-!t9
!pftgt    = $0151
!pfslot   = $0152
!objmax   = $0153       ; highest OBJ page (0-15) written by static stage graphics
!xtimer   = $0154       ; frames since the co-op stage started (extra pages)
!bossst   = $0155       ; word: 1 = boss stage (rival in slot 4, five-slot layout)
!bseat    = $0157       ; word: seat being benched / restored (E4 scratch)
!anchx    = $0159       ; 2 bytes: spawn anchor x of P3/P4 (corner or beside P1/P2)
!anchy    = $015B       ; 2 bytes: spawn anchor y of P3/P4

; Bomber fields kept for benched seats (recomp seat_fields).
macro bench_fields()
    dw $16C2,$16DA,$1662,$167A,$1782,$15D2,$15EA,$17CA,$4EBD,$4ED5
endmacro

; ===========================================================================
; Bank $C4
; ===========================================================================
org !C4

; $C4:286F: equipment reset for every chosen seat (stock: P1, P2).
c4_reset:
    lda #$00
    jsr $2906
    lda #$01
    jsr $2906
    lda !count
    cmp #$03
    bcc +
    lda #$02
    jsr $2906
    lda !count
    cmp #$04
    bcc +
    lda #$03
    jsr $2906
+   jmp $2879

; $C4:28B4 (tail of the player reset, ends with RTL): forced one-player
; sessions as in the original; co-op lives = players + 2, P3 red, P4 blue.
c4_tail:
    stz $1021                       ; rival flags ($101F) of seats 2-4: the
    stz $1022                       ;   last boss start set them (ZONE3 - D
    stz $1023                       ;   uses P4's seat)
    lda #$06
    jsl $C20372
    bcs .forced
    lda #$05
    jsl $C20372
    bcc .normal
.forced:
    lda #$01
    sta $1D25
    sta $1D24
    sta !count
    rtl
.normal:
    lda $1D25
    and #$03
    cmp #$03
    beq +
    lda #$01
    sta !count
    rtl
+   lda !count
    cmp #$03
    bcs .coop
    lda #$02
    sta !count
    rtl
.coop:
    clc
    adc #$02
    sta $1D23
    stz $16C4
    stz $16C5
    lda $80BB4E                     ; Bomberman: white, black, red, blue...
    clc
    adc #$02
    sta $16DC                       ; P3 red
    inc a
    sta $16DD                       ; P4 blue
    lda #$07
    ldx !count
    cpx #$04
    bne +
    lda #$0F
+   sta !pmask
    stz !benched
    rtl

; $C4:29CE (stage init, stock LDA #2 / STA $1CBF).
c4_stage_slots:
    jsl e4_boss_check
    bcs .boss
    stz !bossst
    jsl e4_coop_check
    bcs .coop
    lda #$02
    sta $1CBF
    sta !mofs
    sta !roster
    stz !roster+1
    lda #$18
    sta !mbase
    stz !coopst
    rts
.coop:
    lda #$05
    sta $1CBF
    lda #19
    sta !mofs
    sta !mbase
    lda !count
    sta !roster
    stz !roster+1
    lda #$01
    sta !coopst
    lda #$04
    sta !objmax
    stz !xtimer
    rts
; Boss stage: five bomber slots (players 0-3, rival 4; ZONE3 - D: 3/4),
; mounts at rider + 19, enemies 5-18, for every player count.
.boss:
    lda #$01
    sta !bossst
    stz !bossst+1
    lda #$05
    sta $1CBF
    lda #19
    sta !mofs
    sta !mbase
    lda #$02
    sta !roster
    stz !roster+1
    stz !coopst
    lda !count
    cmp #$03
    bcc .rts
    lda $1031
    cmp #$6A
    bne +
    lda !count
    cmp #$04
    bcc +
    lda #$03                        ; two rivals: P1-P3 fight
    bra ++
+   lda !count
++  sta !roster
    lda #$01
    sta !coopst
    lda #$04
    sta !objmax
    stz !xtimer
.rts:
    rts

; $C4:2A60 (Battle: LDA #5 / STA $1CBF).
c4_battle_slots:
    lda #$05
    sta $1CBF
    sta !mofs
    lda #$02
    sta !roster
    stz !roster+1
    lda #$18
    sta !mbase
    stz !coopst
    stz !bossst
    rts

; $C4:3C75 (boss start, Y = boss index: LDA $B9AE,Y / STA $1CBF, 3 or 4 =
; rivals in slots 2/3). The rivals now take slots 4 (and 3), so the stage
; keeps its five-slot layout; co-op seats the boss cannot hold (P4 in
; ZONE3 - D) are benched with their fields saved before the rival takes
; them.
c4_boss_slots:
    lda #$05
    sta $1CBF
    lda #19
    sta !mofs
    sta !mbase
    lda !coopst
    beq +
    jsl e4_bench_save
+   rts

; $C4:3794 (a player died): co-op keeps the last participant for the
; stock retry, every other dead seat leaves until it rejoins with Start.
c4_death:
    lda !coopst
    bne .coop
    lda $1D1A
    jmp $3797
.coop:
    ldx $8D
    txa
    cmp.l $7E0000|!roster           ; a rival: no participant leaves
    bcs +
    lda.l seat_bits,x
    eor #$FF
    and !pmask
    beq +
    sta !pmask
+   jsl e4_set_masks
    rts

; $C4:2AD8 / $C4:2B8D (STA $0348 with A = 2 << seat): P3/P4 take OBJ
; palette slots 7/6 (slots 3-5 belong to the stage's enemies).
c4_palmask:
    pha
    lda !coopst
    beq .stock
    lda $04,s                       ; seat (PHX before the mask loop)
    cmp #$02
    bcc .stock
    cmp.l $7E0000|!roster           ; a boss rival in slot 3/4: stock mask
    bcs .stock
    lda #$F0                        ; P3/P4: any of slots 4-7, lowest first
    ;   (4/5 are free in most stages; 6/7 stay for eggs, loose Louies and
    ;   large stage objects, mask $C0, as in the 1-2 player game)
    sta $0348
    lda.l $7E0000|!bossst           ; boss stage: slot 5 is the rival's
    beq +                           ;   (seat 4 asks for mask $20)
    lda #$D0
    sta $0348
+   pla
    rts
.stock:
    pla
    sta $0348
    rts

; $C4:53F0 (LDA $16DA,X / INC A: mount palette slot = rider seat + 1):
; a co-op mount uses its rider object's slot.
c4_mountslot:
    lda !coopst
    beq .stock
    phx
    lda $16DA,x
    tax
    lda $17FA,x
    bmi .none
    tax
    lda $06DF,x
    cmp #$08
    bcs .none
    plx
    rts
.none:
    plx
.stock:
    lda $16DA,x
    inc a
    rts

; $C4:37B0 (PHA / STZ $0AE7: write a bomber's colors into its slot): a
; P3/P4 bomber sharing P1's/P2's slot (c0_palfail) must not paint it, and a
; failed slot ($FF) is never written.
c4_seatcolor:
    pha
    lda.l $7E0000|!coopst
    beq .go
    lda $06DF,y
    cmp #$08
    bcs .skip
    cmp #$03
    bcs .go
    cpx #$02
    bcc .go
    txa
    cmp.l $7E0000|!roster
    bcs .go
.skip:
    pla
    stz $0AE7
    rts
.go:
    stz $0AE7
    jmp $37B4

; From E4 (reclaim): colors of seat X's object Y, palette id A.
c4_colors:
    jsr $37B0
    rtl

; $C4:2260 (actor allocator: CPX #$18 / BCC / BRA): enemies stop below
; the co-op mounts.
c4_cap:
    cpx !mbase
    bcs +
    jmp $225A
+   jmp $2296

print "SYM end_c4 ", hex(pc())

; ===========================================================================
; Bank $C5
; ===========================================================================
org !C5

; $C5:3B2D (LDA $1D23 after the stock P1/P2 charges of a stage retry).
c5_charge:
    lda !coopst
    beq +
    lda $1D25
    bit #$04
    beq ++
    dec $1D23
++  bit #$08
    beq +
    dec $1D23
+   lda $1D23
    rts

; $C5:3D5B (PLX / PLB / RTL after the stage map copy to $1052).
c5_settle:
    plx
    plb
    php
    pha
    lda.l $7E0000|!spawnchk
    beq +
    jsl e4_settle
+   pla
    plp
    rtl

; $C5:6AE3 (page request service): with co-op a page can be refilled by
; its own object, and a request no page can hold leaves the queue.
c5_service:
    lda.l $7E0000|!coopst
    bne .coop
    jsr $6AF5
    bcs +
    jmp $6AE8
+   jmp $6AF2
.coop:
    jsr c5_alloc
    bcs .fail
    jsr $6B36
    jsr $6B77
    jmp $6AEE
.fail:
    ldy $1CD6,x
    jsr $6B56
    jmp $6AEE

c5_alloc:
    phx
    ldx #$00
-   lda $1D00,x
    bmi .free
    inx
    cpx #$10
    bcc -
    ldx #$0F
    tya
-   cmp $1D00,x
    beq .own
    dex
    bpl -
    ldy #$7F
    jmp $6B04
.free:
    jmp $6B04
.own:
    txa
    asl a
    ora #$60
    sta $1D11
    clc
    plx
    rts

; Revive feedback of the stock rejoin ($C5:065D), callable from E4.
c5_revive_fx:
    jsr $065D
    rtl

; $C5:42F5 (Clock item: CPX #$18 / BCC / ...): mounts are not frozen.
c5_clock:
    cpx !mbase
    bcs +
    jmp $42DD
+   jmp $42F9

print "SYM end_c5 ", hex(pc())

; ===========================================================================
; Bank $C2
; ===========================================================================
org !C2

; $C2:1697 (stage spawn of P1/P2).
c2_spawn:
    lda !coopst
    bne +
    lda $1D24
    jmp $169A
+   jsl e4_spawn_all
    rts

; $C2:1F2B (LDA $1D25 / JSL $C1:74D1): story scripts know one or two
; players; co-op passes the one/three flag.
c2_story:
    lda !coopst
    beq +
    lda $1D24
    rts
+   lda $1D25
    rts

; $C2:16B8 / $C2:16EE (script ops that create a bomber: LDA [$0D] / DEC A
; / TAX, 1-based slot). In boss stages the rival scripted into slot 2 (P3)
; goes to slot 4 (P5); ZONE3 - D's second rival keeps slot 3.
c2_bslot:
    lda [$0D]
    dec a
    cmp #$02
    bne +
    lda.l $7E0000|!bossst
    beq ++
    lda #$04
    bra +
++  lda #$02
+   tax
    rts

print "SYM end_c2 ", hex(pc())

; ===========================================================================
; Bank $C3
; ===========================================================================
org !C3

; $C3:4B8F (JSR $475C): clear the distances, then fill seats 2+.
c3_fill:
    jsr $475C
    phy
    ldy #$02
-   cpy !roster
    bcs +
    lda $15A2,y
    and #$80
    bne ++
    jsr $46CC
++  iny
    bra -
+   ply
    rts

; $C3:4393 (LDA $1D25 / STA $7E4DA2): the campaign record keeps the
; stock one/two-player mask.
c3_record:
    lda $1D25
    and #$03
    bne +
    lda #$01
+   rts

print "SYM end_c3 ", hex(pc())

; ===========================================================================
; Bank $C0
; ===========================================================================
org !C0

; $C0:374D (CPX #$05 / BCC): enemy point damage skips players, rivals and
; co-op mounts.
c0_damage:
    cpx #$05
    bcc +
    cpx !mbase
    bcs +
    jmp $3751
+   jmp $3778

; $C0:0303 (no OBJ palette slot: LDA #$FF / SEC / BRA $0342). Port of the
; recomp's palette_full: the stage wins. A P3/P4 request (mask $F0) shares
; P1's slot (P2's if P1 has none) and shows P1's colors; any other request
; that would fit if P3/P4 left their slots moves them to that shared slot
; and searches again. e4_frame gives them a slot of their own back.
c0_palfail:
    lda.l $7E0000|!coopst
    beq .fail
    jsr pf_target
    beq .fail
    sta.l $7E0000|!pftgt
    lda.l $7E0348
    cmp #$F0
    beq +
    cmp #$D0                        ; P3/P4 in a boss stage
    bne .stage
+
    lda.l $7E0000|!pftgt
    tax
    jmp $033D                       ; INC $0349,X / return slot X, C clear
.stage:
    lda.l $7E0347
    sta.l $7E0000|!pfneed
    lda #$00
    sta.l $7E0000|!pfrun
    ldx #$00
.scan:
    lda.l $7E0348
    and.l pf_bits,x
    beq .reset
    lda.l $7E2B10,x
    beq .use
    jsr pf_seat_owned
    bcc .reset
.use:
    lda.l $7E0000|!pfrun
    inc a
    sta.l $7E0000|!pfrun
    cmp.l $7E0000|!pfneed
    bcs .found
    bra .next
.reset:
    lda #$00
    sta.l $7E0000|!pfrun
.next:
    inx
    cpx #$08
    bcc .scan
.fail:
    lda #$FF
    sec
    jmp $0342
.found:
    txa
    sec
    sbc.l $7E0000|!pfneed
    inc a
    tax                             ; first slot of the run
    lda.l $7E0000|!pfneed
    tay
.move:
    lda.l $7E2B10,x
    beq +
    jsr pf_share
+   inx
    dey
    bne .move
    jmp $02E2                       ; search again

; A/Z = slot the seats can share (1 = P1, else 2), 0 = none.
pf_target:
    lda.l $7E2B11
    beq +
    lda.l $7E034A
    beq +
    lda #$01
    rts
+   lda.l $7E2B12
    beq +
    lda.l $7E034B
    beq +
    lda #$02
    rts
+   lda #$00
    rts

; C = slot X (3-7, in use) belongs to the bomber of seat 2/3. Keeps X.
pf_seat_owned:
    cpx #$03
    bcc .no
    lda.l $7E0349,x
    beq .no
    txa
    sta.l $7E0000|!pfslot
    ldy #$02
-   tya
    cmp.l $7E0000|!roster
    bcs .no
    phx
    tyx
    lda.l $7E17FA,x
    cmp #$60
    bcs +
    tax
    lda.l $7E06DF,x
    plx
    cmp.l $7E0000|!pfslot
    beq .yes
    bra ++
+   plx
++  iny
    bra -
.yes:
    sec
    rts
.no:
    clc
    rts

; Objects on slot X (the seat's bomber and mount) move to !pftgt, which
; takes over their references; slot X is freed. Keeps X and Y.
pf_share:
    phy
    txa
    sta.l $7E0000|!pfslot
    ldx #$00
-   lda.l $7E06DF,x
    cmp.l $7E0000|!pfslot
    bne +
    lda.l $7E0000|!pftgt
    sta.l $7E06DF,x
+   inx
    inx
    cpx #$60
    bcc -
    lda.l $7E0000|!pftgt
    tax
    lda.l $7E0000|!pfslot
    tay
    lda.l $7E0349,x
    phx
    tyx
    clc
    adc.l $7E0349,x
    plx
    sta.l $7E0349,x
    tyx
    lda #$00
    sta.l $7E0349,x
    sta.l $7E2B10,x
    sta.l $7E2B18,x
    sta.l $7E2B20,x
    ply
    rts

; $C0:0573 (VRAM DMA queue: LDA $0361 / STA $2116, M = 16): in co-op stages,
; note the highest OBJ page that receives static stage graphics (page owner
; $7E), so e4_tick can lend the pages above it to eggs and Louies.
c0_vmadd:
    lda $0361
    sta $2116
    pha
    php
    sep #$20
    lda.l $7E0000|!coopst
    beq .out
    rep #$20
    lda $02,s                       ; VRAM word address
    cmp #$6A00
    bcc .out
    cmp #$8000
    bcs .out
    lda $035F                       ; bytes
    lsr a
    beq .out
    dec a
    clc
    adc $02,s                       ; last word written
    cmp #$8000
    bcc +
    lda #$7FFF
+   sec
    sbc #$6000
    and #$1E00
    xba
    lsr a                           ; A = last page (B = 0)
    rep #$10
    phx
    tax
    sep #$20
    lda.l $7E1D00,x
    cmp #$7E
    bne +
    txa
    cmp.l $7E0000|!objmax
    bcc +
    sta.l $7E0000|!objmax
+   rep #$10
    plx
.out:
    plp
    pla
    rts

pf_bits:
    db $01,$02,$04,$08,$10,$20,$40,$80

print "SYM end_c0 ", hex(pc())

; ===========================================================================
; Bank $E4 (bulk)
; ===========================================================================
org !E4

seat_bits:
    db $01,$02,$04,$08,$10
corner_x:
    db 1,13
corner_y:
    db 11,11
roster_bits:
    db $00,$01,$03,$07,$0F,$1F

; C = 1 when the stage being set up is a campaign boss stage ($67-$6E).
e4_boss_check:
    php
    sep #$20
    lda.l $7E1D1A
    lsr a
    bcs .no                         ; Battle
    lda.l $7E1031
    cmp #$67
    bcc .no
    cmp #$6F
    bcs .no
    plp
    sec
    rtl
.no:
    plp
    clc
    rtl

; $80:F393 (after the WRAM clear): stock values.
coop_boot:
    sep #$30
    lda #$02
    sta.l $7E0000|!roster
    sta.l $7E0000|!mofs
    lda #$18
    sta.l $7E0000|!mbase
    lda #$00                        ; the replaced LDA #0 / PHA / PLB
    pha
    plb
    rtl

; C = 1 when the stage being set up runs the co-op rules.
e4_coop_check:
    php
    sep #$20
    lda.l $7E0000|!count
    cmp #$03
    bcc .no
    lda.l $7E1D1A
    lsr a
    bcs .no                         ; Battle
    lda.l $7E1031
    cmp #$0D
    bcc .no
    cmp #$74
    bcs .no
    cmp #$67
    bcc .yes
    cmp #$6F
    bcc .no                         ; boss stages $67-$6E
.yes:
    plp
    sec
    rtl
.no:
    plp
    clc
    rtl

; $1D25 = co-op participants, $1D24 = 3 with two or more of them.
e4_set_masks:
    phx
    php
    sep #$30
    lda.l $7E0000|!roster
    tax
    lda.l $7E0000|!pmask
    and.l roster_bits,x
    bne +
    lda #$01
+   sta.l $7E1D25
    ; popcount > 1 ?
    sta.l $7E0000|!t0
    dec a
    and.l $7E0000|!t0
    beq +
    lda #$03
    bra ++
+   lda #$01
++  sta.l $7E1D24
    plp
    plx
    rtl


incsrc "coop_e4.asm"

print "SYM end_e4 ", hex(pc())

print "SYM coop_boot ", hex(coop_boot)
print "SYM c4_reset ", hex(c4_reset)
print "SYM c4_tail ", hex(c4_tail)
print "SYM c4_stage_slots ", hex(c4_stage_slots)
print "SYM c4_battle_slots ", hex(c4_battle_slots)
print "SYM c4_boss_slots ", hex(c4_boss_slots)
print "SYM c4_death ", hex(c4_death)
print "SYM c4_palmask ", hex(c4_palmask)
print "SYM c4_mountslot ", hex(c4_mountslot)
print "SYM c4_seatcolor ", hex(c4_seatcolor)
print "SYM c4_colors ", hex(c4_colors)
print "SYM c0_palfail ", hex(c0_palfail)
print "SYM c0_vmadd ", hex(c0_vmadd)
print "SYM c4_cap ", hex(c4_cap)
print "SYM c5_charge ", hex(c5_charge)
print "SYM c5_settle ", hex(c5_settle)
print "SYM c5_service ", hex(c5_service)
print "SYM c5_clock ", hex(c5_clock)
print "SYM e4_frame ", hex(e4_frame)
print "SYM e4_tick ", hex(e4_tick)
print "SYM c2_spawn ", hex(c2_spawn)
print "SYM c2_story ", hex(c2_story)
print "SYM c2_bslot ", hex(c2_bslot)
print "SYM c3_fill ", hex(c3_fill)
print "SYM c3_record ", hex(c3_record)
print "SYM c0_damage ", hex(c0_damage)
