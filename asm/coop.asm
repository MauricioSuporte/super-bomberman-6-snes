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
!PGOBJ    = $7FFE80    ; 16: object whose strip c5_record saw sent to the page ($FF = none)
!PGSHEET  = $7FFE90    ; 16: its sheet ($1CCC)
!PGROW    = $7FFEA0    ; 16: its row ($1CEA)
!URG      = $7FFEB0    ; (+1 page * 2, +2 entry) $A5: an in-place strip was put first in the queue (c5_urgent), until the NMI serves it
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
    jml !PICK_APPLY
.normal:
    lda $1D25
    and #$03
    cmp #$03
    beq +
    lda #$01
    sta !count
    jml !PICK_APPLY
+   lda !count
    cmp #$03
    bcs .coop
    lda #$02
    sta !count
    jml !PICK_APPLY
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
    jml !PICK_APPLY

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
    lda.l !URG
    cmp #$A5
    bne .alloc
    lda #$00
    sta.l !URG
    txa
    cmp.l !URG+2
    bne .alloc
    jsr c5_ownpage                ; c5_urgent already set this frame's OAM for the page on screen: keep
    bcc .got                        ;   to it, even if a page was freed since
.alloc:
    jsr c5_alloc
    bcs .fail
.got:
    jsr c5_record
    jsr $6B36
    jsr $6B77
    jmp $6AEE
.fail:
    ldy $1CD6,x
    jsr $6B56
    jmp $6AEE

; Page for entry X / object Y. SB5's own rule ($C5:6AF5) first: a free page ($FF); the object's page
; becomes $7F and is freed at the next upload, so the page on screen is never written while shown.
; With 4 bombers no $FF page is left: a $7F page is free as well (it was replaced at an earlier NMI,
; the OAM no longer shows it). Only without either the object's own page is reloaded in place.
c5_alloc:
    phx
    ldx #$00
-   lda $1D00,x
    bmi .free
    inx
    cpx #$10
    bcc -
    ldx #$00
-   lda $1D00,x
    cmp #$7F
    beq .free
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

; Object Y's own page for entry X (c5_urgent's strips); C set = it has none. Keeps X.
c5_ownpage:
    phx
    ldx #$0F
    tya
-   cmp $1D00,x
    beq c5_ownpage_got
    dex
    bpl -
    plx
    sec
    rts
c5_ownpage_got:
    txa
    asl a
    ora #$60
    sta $1D11
    clc
    plx
    rts
; Page $1D11 (VRAM high byte $60 + 2 * page) gets entry X's strip for object Y: kept per page
; (!PGOBJ / !PGSHEET / !PGROW) so that the same strip asked again is not sent again (c5_dedupe).
; M/X 8-bit; keeps X, Y.
c5_record:
    phx
    lda $1CCC,x
    pha
    lda $1CEA,x
    pha
    lda $1D11
    and #$1E
    lsr a
    tax
    pla
    sta.l !PGROW,x
    pla
    sta.l !PGSHEET,x
    tya
    sta.l !PGOBJ,x
    plx
    rts

; $C5:6A72 (STZ $1CFF in the strip queue $C5:6A6B: object Y, animation $A8, sheet $AB, row $AC,
; flags $AE). SB5 queues a walking bomber's strip again every frame and the NMI sends one strip per
; frame: with 4 bombers each one waited up to 4 frames for a new animation behind 1 KB copies of
; what its page already held. A strip already in the object's page (none queued for it) is not
; queued: its animation is set now, as the upload would ($C5:6B56). Co-op stages only.
c5_dedupe:
    stz $1CFF
    lda.l $7E0000|!coopst
    beq .queue
    lda $A8                         ; animation 0 (asked while getting on a Louie): SB5 never serves it
    beq .queue
    tya
    ldx #$09
-   cmp $1CD6,x
    beq .queue                      ; one is pending: SB5 replaces it
    dex
    bpl -
    ldx #$0F
-   cmp $1D00,x
    beq .page
    dex
    bpl -
.queue:
    rts
.page:
    cmp.l !PGOBJ,x
    bne .queue
    lda $AB
    cmp.l !PGSHEET,x
    bne .queue
    lda $AC
    cmp.l !PGROW,x
    bne .queue
    pla                             ; (our return address)
    pla
    lda $AE
    bmi .keep
    lda $A8
    jsl $C011EC
    jmp $6AA7
.keep:
    lda $A8
    cmp $079F,y                     ; the same animation, kept going: nothing to do (each call resolves the
    beq +                           ; mapping again, and a streamed character's pose is queued again: with
    jsl $C011DD                     ; 4 walking bombers every frame, 1-3 with chameleons fell to 34 fps)
+   jmp $6AA7

; $C5:6AA7 (LDA #$01 / STA $1CFF: end of the strip queue; entry X for object Y when $1D12 = 0, X >= 10:
; none free). With every OBJ page taken (4 bombers + 4 Louies) the strip goes into the page on screen
; (c5_alloc .own) and SB5 sets the animation in the NMI after the copy: that frame showed the old
; pose's pieces over the new tiles. One such strip per frame is served first by the next NMI ($1CFE)
; and its tile base ($073F) and animation are set now, before this frame's OAM is built: pose and
; tiles change in the same vblank. (The NMI sets it once more, as SB5 always did.)
c5_urgent:
    lda #$01
    sta $1CFF
    lda.l $7E0000|!coopst
    beq .out
    lda $A8                         ; animation 0: SB5's NMI never serves it (a free entry), nor do we
    beq .out
    lda $1D12
    bne .out
    cpx #$0A
    bcs .out
    tya
    cmp $1CD6,x                     ; entry X really queued for Y (c5_dedupe comes here with a page in X)
    bne .out
    lda.l !URG
    bne .out
    phx
    ldx #$0F
-   lda $1D00,x
    bmi .no                         ; a free page: SB5's double buffer works
    cmp #$7F
    beq .no
    dex
    bpl -
    tya
    ldx #$0F
-   cmp $1D00,x
    beq .yes
    dex
    bpl -
.no:
    plx
.out:
    rts
.yes:
    txa
    asl a
    sta.l !URG+1                    ; page * 2 (= $1D11 & $1F)
    plx
    stx $1CFE
    txa
    sta.l !URG+2                    ; the entry
    lda #$A5
    sta.l !URG
    phx
    phy
    lda.l !URG+1                    ; tile base as $C5:6B36: ((page * 2 - row) << 4), sign-extended
    sec
    sbc $1CEA,x
    rep #$20
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    bit #$0800
    beq +
    ora #$F000
+   sta $073F,y
    sep #$20
    lda $1CF4,x
    bmi +
    lda $1CE0,x
    jsl $C011EC
    bra ++
+   lda $1CE0,x
    jsl $C011DD
++  ply
    plx
    rts

; $C5:6A15 (STA $1D10 in SB5's page setup $C5:6A14): the pages are new, nothing is kept in them.
c5_pginit:
    sta $1D10
    phx
    ldx #$0F
    lda #$FF
-   sta.l !PGOBJ,x
    dex
    bpl -
    lda #$00
    sta.l !URG
    lda $1D10
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

; $C5:0171 (JSR $01B4 in the soft block scatter $C5:0141: keep-clear 3x3 of
; each bomber): then e4_reserve keeps an escape clear for every seat.
c5_reserve:
    jsr $01B4
    jsl e4_reserve
    rts

print "SYM end_c5 ", hex(pc())

; ===========================================================================
; Bank $C2
; ===========================================================================
org !C2

; $C2:1697 (stage spawn of P1/P2).
c2_spawn:
    jsl !PICK_SPAWN
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
    php                             ; ($C3:475C's 24-byte loop, unrolled: run
    rep #$20                        ;   for every enemy every frame)
    lda #$FFFF
    sta $0110
    sta $0112
    sta $0114
    sta $0116
    sta $0118
    sta $011A
    sta $011C
    sta $011E
    sta $0120
    sta $0122
    sta $0124
    sta $0126
    plp
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

; $C3:46CC (STA $9F / LDA $1842,X: distances from enemy X to seat Y, into
; $0110+ seat arrays, 4 seats x every enemy x every frame): while an SB1 enemy
; asks ($7F:F76F = 1: asm/sb1_enemies.asm, c3_walk), a seat 16 px or more away on
; either axis keeps the cleared $FF (only the contact test, < 8 px, reads them).
c3_near:
    sta $9F
    lda.l $7FF76F
    beq .full
    lda $182A,y
    sec
    sbc $182A,x
    bcs +
    eor #$FF
    inc a
+   cmp #$10
    bcs .far
    lda $1872,y
    sec
    sbc $1872,x
    bcs +
    eor #$FF
    inc a
+   cmp #$10
    bcs .far
.full:
    lda $1842,x
    jmp $46D1
.far:
    rts

; $C3:4B5A (STZ $1FF2 / JSR $4B7B: SB5's walker, contact and flames): its
; moves ($C3:4DA2, $C3:4610) never read the seat distances, so c3_near may skip
; far seats for it too. C = died, as $C3:4B7B.
c3_walk:
    stz $1FF2
    lda #$01
    sta.l $7FF76F
    jsr $4B7B
    lda #$00                        ; (keeps C)
    sta.l $7FF76F
    rts

; $C3:0452 (STA $1D51 in the enemy creation $C3:0450, A = type): e4_spawn
; may refuse it (C set): the creation fails as with no free actor.
c3_spawn:
    jsl e4_spawn
    bcs +
    rts
+   pla
    pla
    jmp $0512                       ; LDA #$FF / PLX / PLY / RTS

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
    lda.l $7E0347                   ; one slot, slot 3 free but not in the mask (the exit portal asks
    cmp #$01                        ;   for 4/5 = P3/P4's): slot 3 first, no seat moves
    bne +
    lda.l $7E2B13
    bne +
    lda.l $7E0348
    bit #$08
    bne +
    ora #$08
    sta.l $7E0348
    jmp $02E2                       ; search again
+   lda.l $7E0347
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

; (from c3_spawn, A = type; any DB: long addresses) 1-3's chameleons (type 05, stage $18) stop at
; cham_max[roster] (4 bombers and 7 chameleons copying them: over 90 sprites,
; tools/coop4_check.py). C set = not created ($1D50 does not count it).
; Keeps A, X, Y.
e4_spawn:
    sta.l $7E1D51
    cmp #$05
    bne .ok
    lda.l $7E1031
    cmp #$18
    bne .ok
    phx
    lda.l $7E012A                   ; roster: 2 (1-2 players), 3, 4 (P3/P4
    tax                             ;   join $1D25 only after the spawns)
    lda.l cham_max,x
    sta $A6
    stz $A5
    ldx #$05
-   lda.l $7E17FA,x
    bmi +
    lda.l $7E16C2,x
    cmp #$05
    bne +
    inc $A5
+   txa
    cmp.l $7E198C
    inx
    bcc -
    plx
    lda $A5
    cmp $A6
    bcc .ok
    lda.l $7E1D51
    sec
    rtl
.ok:
    lda.l $7E1D51
    clc
    rtl
cham_max:
    db 7,7,!CHAM2,!CHAM3,!CHAM4     ; by roster (2 = 1-2 players)

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


; ---- spawn safety (from c5_reserve, before the random soft blocks) --------
; SB5 keeps only the 3x3 around a bomber clear ($7E:2700 | $10 = no soft
; block): in a corner with an extra wall (1-2's lower left) that leaves a
; corridor where any bomb kills its owner. For each seat, the shortest
; straight run of k <= 4 free cells from its cell with a free cell beside
; its end is kept clear too: bomb on the start cell, hide around the corner
; (out of the blast for any fire range). tools/coop4_check.py checks it.
e4_reserve:
    php
    phb
    phk
    plb                             ; (res_dir / res_side)
    sep #$30
    ldx #$03                        ; seats out of the stage: SB5's 3x3 kept clear ($C5:01B4 does it for bombers)
-   jsr seat_out
    bcs +
    jsr keep3x3
+   dex
    bpl -
    ldx #$03
.seat:
    jsr seat_cell
    bcc +
    jmp .next
+
    sta.l $7E0000|!t0               ; start cell
    phx
    lda #$01
    sta.l $7E0000|!t1               ; k
.len:
    ldy #$00                        ; direction 0-3
.dir:
    lda.l $7E0000|!t0
    sta.l $7E0000|!t3
    lda.l $7E0000|!t1
    sta.l $7E0000|!t2
-   lda.l $7E0000|!t3               ; k cells along the direction free?
    clc
    adc.w res_dir,y
    sta.l $7E0000|!t3
    tax
    lda.l $7E2700,x                 ; $80: wall (the map at $1052 comes later)
    and #$80
    bne .nodir
    lda.l $7E0000|!t2
    dec a
    sta.l $7E0000|!t2
    bne -
    lda.l $7E0000|!t3               ; a free cell beside the end?
    clc
    adc.w res_side,y
    tax
    lda.l $7E2700,x                 ; $80: wall (the map at $1052 comes later)
    and #$80
    beq .found
    lda.l $7E0000|!t3
    sec
    sbc.w res_side,y
    tax
    lda.l $7E2700,x                 ; $80: wall (the map at $1052 comes later)
    and #$80
    beq .found
.nodir:
    iny
    cpy #$04
    bcc .dir
    lda.l $7E0000|!t1
    inc a
    sta.l $7E0000|!t1
    cmp #$05
    bcc .len
    bra .done
.found:
    jsr .keep                       ; the side cell, then the run back to the start
-   lda.l $7E0000|!t3
    tax
    jsr .keep
    lda.l $7E0000|!t3
    sec
    sbc.w res_dir,y
    sta.l $7E0000|!t3
    cmp.l $7E0000|!t0
    bne -
.done:
    plx
.next:
    dex
    bmi +
    jmp .seat
+   jsr shield
    plb
    plp
    rtl
.keep:
    lda.l $7E2700,x
    ora #$10
    sta.l $7E2700,x
    rts

; Seat X's start cell -> A, C clear: its bomber's ($16AA), or for a seat of the roster out of this stage
; (it may join with Start: e4_frame's revive starts from $4E8D/$4EA5, its corner) that spawn cell; C set: none.
; Keeps X.
seat_cell:
    lda.l $7E17FA,x
    bmi seat_out
    lda.l $7E16AA,x
    clc
    rts
; C clear + A = spawn cell only for a seat of the roster out of this stage.
seat_out:
    lda.l $7E17FA,x
    bpl .no
    txa
    cmp.l $7E0000|!roster
    bcs .no
    lda.l $7E4EA5,x
    asl a
    asl a
    asl a
    asl a
    ora.l $7E4E8D,x
    beq .no
    clc
    rts
.no:
    sec
    rts

; The 3x3 around cell A: no soft block ($7E:2700 | $10, as $C5:0230). Keeps X.
keep3x3:
    phx
    sec
    sbc #$11
    ldy #$03
-   tax
    lda.l $7E2700,x
    ora #$10
    sta.l $7E2700,x
    inx
    lda.l $7E2700,x
    ora #$10
    sta.l $7E2700,x
    inx
    lda.l $7E2700,x
    ora #$10
    sta.l $7E2700,x
    txa
    clc
    adc #$0E
    dey
    bne -
    plx
    rts

; Then every seat is shut in by soft blocks: its pocket (the cells kept clear, $10 and not $80, reachable
; from its cell within !SHMAX steps) gets a soft block, as the scatter's ($7E:2400 = 2, $7E:2700 | $90,
; one less of $0E1F for the random ones), on every cell around it the scatter could fill (no $F0 bit):
; an enemy must burn through one to reach a bomber at the start. Only when the scatter runs ($1D1A & $0C
; = 0) and while $0E1F lasts. tools/coop4_check.py checks it.
!SHQ   = $7FF7D0          ; pocket cells (queue), !SHN at most
!SHD   = $7FF7E8          ; their steps from the seat
!SHN   = 24
!SHMAX = 6
!SHI   = $7FF7CC          ; queue head, length, cell, direction
!SHL   = $7FF7CD
!SHC   = $7FF7CE
!SHR   = $7FF7CF
shield:
    lda.l $7E1D1A
    and #$0C
    beq +
    rts
+   ldx #$03
.seat:
    jsr seat_cell
    bcc +
    jmp .next
+   phx
    sta.l !SHQ
    lda #$00
    sta.l !SHD
    sta.l !SHI
    lda #$01
    sta.l !SHL
.pop:
    lda.l !SHI
    cmp.l !SHL
    bcc +
    jmp .done
+
    tax
    inc a
    sta.l !SHI
    lda.l !SHQ,x
    sta.l !SHC
    lda.l !SHD,x
    sta.l $7E0000|!t4               ; its steps
    ldy #$03
.dir:
    tya
    sta.l !SHR
    lda.l !SHC
    clc
    adc.w res_dir,y
    sta.l $7E0000|!t5               ; the neighbour
    tax
    lda.l $7E2700,x
    bmi .skip                       ; wall (or a soft block already)
    and #$10
    beq .edge
    jsr .known                      ; kept clear: in the pocket (once), if not too far
    beq .skip
    lda.l $7E0000|!t4
    cmp #!SHMAX
    bcs .skip
    lda.l !SHL
    cmp #!SHN
    bcs .skip
    tax
    inc a
    sta.l !SHL
    lda.l $7E0000|!t5
    sta.l !SHQ,x
    lda.l $7E0000|!t4
    inc a
    sta.l !SHD,x
    bra .skip
.edge:
    lda.l $7E2700,x                 ; around it: a soft block if the scatter could put one there
    and #$F0
    bne .skip
    lda.l $7E0E1F
    beq .skip
    dec a
    sta.l $7E0E1F
    lda #$02
    sta.l $7E2400,x
    lda.l $7E2700,x
    ora #$90
    sta.l $7E2700,x
.skip:
    lda.l !SHR
    tay
    dey
    bmi +
    jmp .dir
+   jmp .pop
.done:
    plx
.next:
    dex
    bmi +
    jmp .seat
+   rts
; Z set: the cell in !t5 is in the queue already
.known:
    ldx #$00
-   lda.l !SHQ,x
    cmp.l $7E0000|!t5
    beq +
    inx
    txa
    cmp.l !SHL
    bcc -
    lda #$01                        ; (Z clear)
+   rts

res_dir:  db $01, $FF, $10, $F0     ; right, left, down, up
res_side: db $10, $10, $01, $01     ; (and minus it)

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
print "SYM c4_seatcolor ", hex(c4_seatcolor)
print "SYM c4_colors ", hex(c4_colors)
print "SYM c0_palfail ", hex(c0_palfail)
print "SYM c0_vmadd ", hex(c0_vmadd)
print "SYM c4_cap ", hex(c4_cap)
print "SYM c5_charge ", hex(c5_charge)
print "SYM c5_settle ", hex(c5_settle)
print "SYM c5_service ", hex(c5_service)
print "SYM c5_dedupe ", hex(c5_dedupe)
print "SYM c5_pginit ", hex(c5_pginit)
print "SYM c5_urgent ", hex(c5_urgent)
print "SYM c5_clock ", hex(c5_clock)
print "SYM e4_frame ", hex(e4_frame)
print "SYM e4_tick ", hex(e4_tick)
print "SYM c2_spawn ", hex(c2_spawn)
print "SYM c2_story ", hex(c2_story)
print "SYM c2_bslot ", hex(c2_bslot)
print "SYM c3_fill ", hex(c3_fill)
print "SYM c3_record ", hex(c3_record)
print "SYM c3_near ", hex(c3_near)
print "SYM c3_walk ", hex(c3_walk)
print "SYM c3_spawn ", hex(c3_spawn)
print "SYM c5_reserve ", hex(c5_reserve)
print "SYM e4_reserve ", hex(e4_reserve)
print "SYM shield ", hex(shield)
print "SYM e4_spawn ", hex(e4_spawn)
print "SYM c0_damage ", hex(c0_damage)
