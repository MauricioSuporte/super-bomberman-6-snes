; Normal Game for up to four players (port of the five-player co-op mod of
; SuperBomberman5SNESRecomp, normal_coop_mod.c + coop_corner_spawns_mod.c).
;
; Seats 3/4 are pads 3/4 (multitap on port 2; the cartridge's pad reader
; $C0:0A56 already fills the per-seat arrays $2C/$31/$36+seat for five pads).
; With one or two players every hook below takes the cartridge's own path:
; `!coopst` (this stage is a co-op stage) is set only by c4_stage_slots when
; `!count` >= 3, the mode is a campaign stage and the stage is not a boss
; stage ($67-$6E: P1/P2 fight the rival bombers alone, as in the original;
; P3/P4 sit out and get their bomber fields back at the next stage).
;
; Actor layout in a co-op stage (as in the recomp mod): seats 0-3 = actors
; 0-3, enemies 5-18 (`!mbase` caps the allocator), mounts rider + 19
; (`!mofs`, read by the 28 rider<->mount conversions instead of $1CBF),
; $1CBF = 5 bomber slots.
;
; Hooks and generated loop stubs: tools/sb6/features/coop.py.
; WRAM: $0110-$0147 (docs/FREE_SPACE.md); zeroed by the reset routine,
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
!bench    = $0130       ; 10 fields x 2 seats (P3/P4 benched in boss stages)
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
    rts

; $C4:3C75 (boss start: LDA $B9AE,Y / STA $1CBF). P1/P2 fight; P3/P4 are
; benched with their fields saved (the rivals take slots 2/3).
c4_boss_slots:
    stz !coopst
    lda #$02
    sta !roster
    stz !roster+1
    lda #$18
    sta !mbase
    lda !count
    cmp #$03
    bcc .done
    lda #$03
    sta $1D25
    sta $1D24
    lda !benched
    bne .done
    jsl e4_bench_save
.done:
    lda $B9AE,y
    sta $1CBF
    sta !mofs
    rts

; $C4:3794 (a player died): co-op keeps the last participant for the
; stock retry, every other dead seat leaves until it rejoins with Start.
c4_death:
    lda !coopst
    bne .coop
    lda $1D1A
    jmp $3797
.coop:
    ldx $8D
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
    beq .p3
    cmp #$03
    bne .stock
    lda #$40
    bra .set
.p3:
    lda #$80
.set:
    sta $0348
    pla
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
    php
    sep #$20
    lda.l $7E0000|!pmask
    and #$0F
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
print "SYM c4_cap ", hex(c4_cap)
print "SYM c5_charge ", hex(c5_charge)
print "SYM c5_settle ", hex(c5_settle)
print "SYM c5_service ", hex(c5_service)
print "SYM c5_clock ", hex(c5_clock)
print "SYM e4_frame ", hex(e4_frame)
print "SYM c2_spawn ", hex(c2_spawn)
print "SYM c2_story ", hex(c2_story)
print "SYM c3_fill ", hex(c3_fill)
print "SYM c3_record ", hex(c3_record)
print "SYM c0_damage ", hex(c0_damage)
