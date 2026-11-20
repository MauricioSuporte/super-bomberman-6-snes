; SB1 3-6's chameleons in World 1's 1-3 (tools/sb6/features/sb1_enemies.py `chameleon`): an enemy that
; walks as a frog (its own pictures) or as a copy of a live player's character, as SB1's ($C6:69FB,
; read in its ROM and checked frame by frame in Mesen):
;
; * it walks 192-255 frames, then stops and changes: 63 frames as it was, then the two looks alternate
;   (FLICK: new 1, old 3, ... new 3, old 1, new) and it walks with the new look at once (SB1 stands 32
;   more frames with it: left out, owner's call);
; * the copy walks with the character's own walk animation (01-04 by facing), not the player's sprite,
;   and stands on that animation's first pose while changing;
; * a flame kills it in any form (SB1's copy only blinks and turns back: owner's call), with its own
;   look back for SB5's death.
;
; chameleon = the actor routine of type 05's record (called through JML [$A5], X = actor, M/X 8-bit,
; RTL). It walks with SB5's walker $C3:4B5A and stands with $C3:4C13 (the stop-watch routine: contact
; and flames, no movement; its `$0800,obj` = 0 also stops the object's script). The copy's look: the
; resolved mapping ($7E:2EEA/$7E:2F4A + obj) of a pose of CTAB, its tiles in a VRAM half of its own
; (8 columns x 2 rows, OBJ pages 12-15 = tiles $180-$1FF, unused by 1-3's static sprites; claimed with
; owner $7D, which neither the allocator nor the release loop nor co-op's lend_pages touch), DMA'd by
; cham_nmi in the NMI that sends the OAM built with it ($03D3), the copied player's palette slot, and
; its own script held ($07A0 = $FF). The own tile base and slot come back when it is a frog again.
;
; CTAB (built by sb1_enemies.chameleon): word per (character 0-9, facing 1-4) -> entries of 8 bytes
; [frames, mapping24, source24, columns] (columns 0 = nothing to load), ended by [0, loop entry16].
; State per actor and per half: docs/FREE_SPACE.md ($7F:F800-$7F:FAFF, cleared by World 1's stage
; start op, asm/world1.asm). Players: actors 0-4, object $17FA + seat, a bomber while its type
; ($04FF + obj) is $10-$19; character of a seat = $16C2 + seat.

asar 1.90
hirom
org !ORG

!B     = $7FF800
!CST   = !B+$000          ; 1 once set up
!CPH   = !B+$018          ; 0 frog walking, 1 copy walking, 2 changing, 4 dead
!CTM   = !B+$030          ; frames left walking / blinking
!CSEAT = !B+$048          ; seat copied
!COWNL = !B+$060          ; own tile base (low, high), own palette slot
!COWNH = !B+$078
!COWNS = !B+$090
!CTGT  = !B+$0A8          ; changing into: 0 frog, 1 copy
!CSTEP = !B+$0C0          ; FLICK entry
!CFT   = !B+$0D8          ; frames left in it
!CHALF = !B+$0F0          ; 2 * VRAM half, $FF none
!CPL   = !B+$108          ; CTAB entry of the copy's pose (low, high)
!CPHI  = !B+$120
!CPF   = !B+$138          ; frames left in the pose
!CDIR  = !B+$150          ; facing of the pose's animation
!CCHR  = !B+$168          ; character copied
!HOWN  = !B+$1A0          ; per half (index 2k): owner actor + 1, 0 free, $FF not usable
!HPEND = !B+$1B0          ; $A5 = DMA pending
!HSRC  = !B+$1C0          ; source (word)
!HBANK = !B+$1D0          ; source bank
!HW    = !B+$1E0          ; columns
!HLOAD = !B+$1F0          ; CTAB entry in the half (word, 0 = none)
!CBUD  = !B+$200          ; DMAs queued since the last NMI that sent them
!CINIT = !B+$201          ; $5A once the halves are set up
!TE    = !B+$202          ; scratch: entry (word)
!TK    = !B+$204          ; scratch: 2 * half (word)
!TN    = !B+$206          ; scratch: row bytes (word), seat search
!TA    = !B+$208          ; scratch: actor, half owner
!TW    = !B+$209          ; scratch: columns
!TBK   = !B+$20A          ; scratch: source bank
!TS    = !B+$20B          ; scratch: source (word)
!NT    = !B+$20D          ; NMI scratch: row bytes (word)
!BUDGET = 3               ; pose DMAs per frame (<= 512 bytes each)
!HPAGE = 12               ; first OBJ page of the halves

chameleon:
    ldy $17FA,x
    lda.l !CST,x
    bne +
    jsr setup
+   lda.l !CPH,x
    beq frog_walk
    dec a
    bne +
    jmp copy_walk
+   dec a
    bne +
    jmp changing
+   rtl

; --- frog: SB5's walker; after its time, a live player to copy and a VRAM half -> changing
frog_walk:
    phx
    jsl $C34B5A
    sep #$30
    plx
    ldy $17FA,x
    jsr alive
    bcc .out
    lda.l !CTM,x
    dec a
    sta.l !CTM,x
    bne .out
    jsr pick
    bcc .later
    sta.l !CSEAT,x
    jsr halfget
    bcc .later
    phx
    lda.l !CSEAT,x
    tax
    lda $16C2,x
    plx
    cmp #10
    bcc +
    lda #$00
+   sta.l !CCHR,x
    lda #$01
    jsr change_start
.out
    rtl
.later                          ; nobody to copy / no half: a frog a while more
    lda #$40
    sta.l !CTM,x
    rtl

; --- copy: SB5's walker (a flame kills it, as a frog; its own look comes back for the death)
copy_walk:
    jsr player_ok
    bcs +
    jmp gone
+   phx
    jsl $C34B5A
    sep #$30
    plx
    ldy $17FA,x
    jsr alive
    bcs +
    jmp died
+   lda $1632,x                 ; turned: that facing's animation (as soon as its pose is in VRAM)
    cmp.l !CDIR,x
    beq .step
    jsr dir_try
    bra .time
.step
    jsr step_pose
.time
    lda.l !CTM,x
    dec a
    sta.l !CTM,x
    bne .show
    lda #$00
    jsr change_start
.show
    jsr show_copy
    rtl

; --- changing (standing): FLICK; flames kill
changing:
    phx
    jsl $C34C13
    sep #$30
    plx
    ldy $17FA,x
    jsr alive
    bcs +
    jmp died
+   lda.l !CFT,x
    dec a
    sta.l !CFT,x
    bne .show
    lda.l !CSTEP,x
    inc a
    sta.l !CSTEP,x
    cmp #32
    bcs .done
    phx
    tax
    lda.l flick_frames,x
    plx
    sta.l !CFT,x
.show
    lda.l !CSTEP,x
    phx
    tax
    lda.l flick_new,x
    plx
    eor.l !CTGT,x               ; 0 = the copy's look (new look into a copy, old look into a frog)
    bne .frog
    jsr want_cur
    bcc .frog
    jsr show_copy
    rtl
.frog
    jsr show_frog
    rtl
.done                           ; walking again with the new look
    lda #$01
    sta $0800,y
    jsr walk_time
    lda.l !CTGT,x
    sta.l !CPH,x
    bne +
    jsr to_frog
    rtl
+   jsr show_copy
    rtl

; the copied player is gone: a frog at once (its palette slot may go to someone else)
gone:
    jsr to_frog
    lda #$00
    sta.l !CPH,x
    lda #$01
    sta $0800,y
    jsr walk_time
    rtl

; dying (or no longer an enemy): own look, half released, nothing more
died:
    lda #$04
    sta.l !CPH,x
    jsr release
    cpy #$60
    bcs +
    lda $04FF,y
    cmp #$07
    bne +
    jsr own_look
+   rtl

;-----------------------------------------------------------------------------
; helpers: X = actor, Y = object (kept unless said), M/X 8-bit

setup:
    lda #$01
    sta.l !CST,x
    lda #$00
    sta.l !CPH,x
    lda #$FF
    sta.l !CHALF,x
    lda $073F,y
    sta.l !COWNL,x
    lda $0740,y
    sta.l !COWNH,x
    lda $06DF,y
    sta.l !COWNS,x
    jsr walk_time
    lda.l !CINIT
    cmp #$5A
    beq .out
    phx                         ; the halves: pages 12-15 static and never written in 1-3 ($7E), or free
    ldx #$00
-   lda $1D00+!HPAGE,x
    cmp #$7E
    beq .mine
    cmp #$FF
    beq .mine
    lda #$FF
    bra +
.mine
    lda #$7D
    sta $1D00+!HPAGE,x
    lda #$00
+   sta.l !TA
    phx
    txa
    asl a
    asl a
    tax
    lda.l !TA
    sta.l !HOWN,x
    sta.l !HOWN+2,x
    lda #$00
    sta.l !HPEND,x
    sta.l !HPEND+2,x
    sta.l !HLOAD,x
    sta.l !HLOAD+1,x
    sta.l !HLOAD+2,x
    sta.l !HLOAD+3,x
    plx
    inx
    cpx #$04
    bcc -
    lda #$00
    sta.l !CBUD
    lda #$5A
    sta.l !CINIT
    plx
.out
    rts

; carry set while the object is still a live enemy
alive:
    cpy #$60
    bcs .no
    lda $04FF,y
    cmp #$07
    bne .no
    lda $15A2,x
    bmi .no
    sec
    rts
.no
    clc
    rts

; the copied seat's object is still a bomber -> carry set
player_ok:
    phx
    lda.l !CSEAT,x
    tax
    lda $17FA,x
    plx
    cmp #$60
    bcs .no
    phx
    tax
    lda $04FF,x
    plx
    cmp #$10
    bcc .no
    cmp #$1A
    bcs .no
    sec
    rts
.no
    clc
    rts

; 192-255 frames walking (SB1: $C6:69ED)
walk_time:
    txa
    asl a
    asl a
    asl a
    clc
    adc $0069
    adc $0068
    and #$3F
    ora #$C0
    sta.l !CTM,x
    rts

; a live player (seats from a varying one): carry set and A = seat, else carry clear. Keeps X, Y.
pick:
    phy
    txa
    clc
    adc $0069
-   cmp #$05
    bcc +
    sbc #$05
    bra -
+   sta.l !TN
    lda #$05
    sta.l !TN+1
    phx
-   lda.l !TN
    tax
    lda $17FA,x
    cmp #$60
    bcs .next
    tay
    lda $04FF,y
    cmp #$10
    bcc .next
    cmp #$1A
    bcs .next
    txa
    plx
    ply
    sec
    rts
.next
    lda.l !TN
    inc a
    cmp #$05
    bcc +
    lda #$00
+   sta.l !TN
    lda.l !TN+1
    dec a
    sta.l !TN+1
    bne -
    plx
    ply
    clc
    rts

; a free VRAM half -> CHALF, carry set; else carry clear. Keeps X, Y.
halfget:
    phx
    txa
    inc a
    sta.l !TA
    ldx #$00
-   lda.l !HOWN,x
    beq .got
    inx
    inx
    cpx #$10
    bcc -
    plx
    clc
    rts
.got
    lda.l !TA
    sta.l !HOWN,x
    lda #$00
    sta.l !HPEND,x
    sta.l !HLOAD,x
    sta.l !HLOAD+1,x
    txa
    plx
    sta.l !CHALF,x
    sec
    rts

release:
    lda.l !CHALF,x
    cmp #$FF
    beq +
    phx
    tax
    lda #$00
    sta.l !HOWN,x
    sta.l !HPEND,x
    plx
    lda #$FF
    sta.l !CHALF,x
+   rts

; A = the look it changes into (0 frog, 1 copy): standing, FLICK from its start; into the copy, on the
; first pose of its facing's animation (a copy changing back keeps the pose it walked with)
change_start:
    sta.l !CTGT,x
    pha
    lda #$02
    sta.l !CPH,x
    lda #$00
    sta.l !CSTEP,x
    lda.l flick_frames
    sta.l !CFT,x
    lda #$FF
    sta $07A0,y
    pla                         ; both ways: standing on the first pose of its facing's walk
    lda.l !CHALF,x
    cmp #$FF
    beq +
    lda $1632,x
    jsr anim_entry
    bcc +
    lda $1632,x
    sta.l !CDIR,x
    jsr set_pose
    jsr want_cur
+   rts

; A = facing (1-4) -> !TE = the first entry of the copied character's animation, carry set (clear when
; the facing is out of range)
anim_entry:
    dec a
    cmp #$04
    bcs .no
    sta.l !TE
    lda.l !CCHR,x
    asl a
    asl a
    clc
    adc.l !TE
    asl a
    phx
    rep #$30
    and #$00FF
    tax
    lda.l !CTAB,x
    sta.l !TE
    sep #$30
    plx
    sec
    rts
.no
    clc
    rts

; the pose of entry !TE: CPL/CPHI, CPF = its frames
set_pose:
    lda.l !TE
    sta.l !CPL,x
    lda.l !TE+1
    sta.l !CPHI,x
    phx
    rep #$30
    lda.l !TE
    tax
    sep #$20
    lda.l !CTB,x
    sep #$30
    plx
    sta.l !CPF,x
    rts

; walking: next pose when its frames are over (once its tiles can be sent)
step_pose:
    lda.l !CPF,x
    dec a
    sta.l !CPF,x
    bne .out
    phx
    lda.l !CPL,x
    sta.l !TE
    lda.l !CPHI,x
    sta.l !TE+1
    rep #$30
    lda.l !TE
    clc
    adc #$0008
    tax
    sep #$20
    lda.l !CTB,x
    bne +
    rep #$20                    ; [0, loop entry]
    lda.l !CTB+1,x
    tax
+   rep #$20
    txa
    sta.l !TE
    sep #$30
    plx
    jsr want
    bcc .wait
    jsr set_pose
.out
    rts
.wait
    lda #$01
    sta.l !CPF,x
    rts

; turned: the new facing's animation from its first pose (once its tiles can be sent)
dir_try:
    lda $1632,x
    jsr anim_entry
    bcc .out
    jsr want
    bcc .out
    lda $1632,x
    sta.l !CDIR,x
    jsr set_pose
.out
    rts

; the current pose (CPL/CPHI) in the half -> carry
want_cur:
    lda.l !CPL,x
    sta.l !TE
    lda.l !CPHI,x
    sta.l !TE+1
; entry !TE in the actor's half: carry set when it is there (or queued for the NMI that sends the OAM
; built now), clear when it cannot be queued this frame. Keeps X, Y, !TE.
want:
    lda.l !CHALF,x
    cmp #$FF
    bne +
    clc
    rts
+   phx
    phy
    sta.l !TK
    lda #$00
    sta.l !TK+1
    rep #$30
    lda.l !TK
    tax                         ; X = 2 * half
    lda.l !HLOAD,x
    cmp.l !TE
    beq .yes
    lda.l !TE
    tax                         ; X = entry
    sep #$20
    lda.l !CTB+7,x              ; columns
    beq .none
    sta.l !TW
    lda.l !CBUD
    cmp #!BUDGET
    bcs .no
    inc a
    sta.l !CBUD
    lda.l !CTB+6,x
    sta.l !TBK
    rep #$20
    lda.l !CTB+4,x
    sta.l !TS
    lda.l !TK
    tax                         ; X = 2 * half: pending cleared first, then the fields, then pending
    sep #$20
    lda #$00
    sta.l !HPEND,x
    rep #$20
    lda.l !TS
    sta.l !HSRC,x
    lda.l !TE
    sta.l !HLOAD,x
    sep #$20
    lda.l !TBK
    sta.l !HBANK,x
    lda.l !TW
    sta.l !HW,x
    lda #$A5
    sta.l !HPEND,x
    bra .yes
.none                           ; nothing to load (empty pose)
    rep #$20
    lda.l !TK
    tax
    lda.l !TE
    sta.l !HLOAD,x
.yes
    sep #$30
    ply
    plx
    sec
    rts
.no
    sep #$30
    ply
    plx
    clc
    rts

;-----------------------------------------------------------------------------
; looks

; own tile base and palette slot
own_look:
    lda.l !COWNL,x
    sta $073F,y
    lda.l !COWNH,x
    sta $0740,y
    lda.l !COWNS,x
    sta $06DF,y
    rts

; the frog standing: own look, its last frame ($1E7E: kept by $C3:4C13) resolved again
show_frog:
    jsr own_look
    lda #$FF
    sta $07A0,y
    lda $1E7E,x
    beq +
    sta $049F,y
    phx
    phy
    jsl $C01289
    sep #$30
    ply
    plx
+   rts

; a frog again: half released, own look, its animation from the start, script stepping
to_frog:
    jsr release
    jsr own_look
    lda #$01
    sta $0800,y
    lda $079F,y
    phx
    phy
    jsl $C011EC
    sep #$30
    ply
    plx
    rts

; the copy: the half's tiles with the mapping of the pose that is in it (the current pose once it could be
; queued: never a pose whose tiles are not there), the copied player's palette slot, own script held;
; nothing in the half yet: the frog
show_copy:
    lda.l !CHALF,x
    cmp #$FF
    bne +
    jmp show_frog
+   jsr want_cur                ; (queued now, or already there, or the pose in the half stays)
    lda.l !CHALF,x
    phx
    rep #$30
    and #$00FF
    tax
    lda.l !HLOAD,x
    sta.l !TE
    sep #$30
    plx
    lda.l !TE
    ora.l !TE+1
    bne +
    jmp show_frog
+   lda.l !CHALF,x
    phx
    tax
    lda.l half_tile,x
    sta $073F,y
    lda.l half_tile+1,x
    sta $0740,y
    plx
    phx
    lda.l !CSEAT,x
    tax
    lda $17FA,x
    tax
    lda $06DF,x
    plx
    sta $06DF,y
    lda #$FF
    sta $07A0,y
    phx
    phy
    rep #$30
    lda.l !TE
    tax
    lda.l !CTB+1,x      ; mapping (low, high), bank
    pha
    sep #$20
    lda.l !CTB+3,x
    sta.l !TN
    rep #$20
    tya
    and #$00FF
    tax
    pla
    sta.l $7E2EEA,x
    sep #$20
    lda.l !TN
    sta.l $7E2F4A,x
    sep #$30
    ply
    plx
    rts

;-----------------------------------------------------------------------------
; cham_nmi: replaces the JSL at $C0:F41D (NMI, after the OAM DMA): the queued poses, when this NMI sent
; the OAM built with them ($03D3); then the call it replaced.
cham_nmi:
    php
    phb
    sep #$20
    rep #$10
    lda #$00
    pha
    plb
    lda $1031
    cmp #!STAGE
    bne .skip
    lda.l !CINIT
    cmp #$5A
    bne .skip
    lda $03D3
    bne .go
.skip
    jmp .out
.go
    ldx #$0000
-   lda.l !HPEND,x
    cmp #$A5
    bne .next
    lda #$00
    sta.l !HPEND,x
    lda.l !HW,x
    rep #$20
    and #$000F
    asl a
    asl a
    asl a
    asl a
    asl a
    sta.l !NT
    sta $4305
    lda.l !HSRC,x
    sta $4302
    lda.l half_vram,x
    sta $2116
    sep #$20
    lda.l !HBANK,x
    sta $4304
    lda #$80
    sta $2115
    lda #$01
    sta $4300
    lda #$18
    sta $4301
    lda #$01
    sta $420B
    rep #$20                    ; row 1: 16 tiles further, the source goes on
    lda.l half_vram,x
    clc
    adc #$0100
    sta $2116
    lda.l !NT
    sta $4305
    sep #$20
    lda #$01
    sta $420B
.next
    inx
    inx
    cpx #$0010
    bcc -
    lda #$00
    sta.l !CBUD
.out
    plb
    plp
    jml !NMINEXT

;-----------------------------------------------------------------------------
; cham_hit: replaces the JSL at $C3:4D41 (enemy hit, X = actor; game_sfx's gs_enemy goes on): a chameleon
; killed outside its routine gets its own palette slot back before SB5 releases the object's slot.
cham_hit:
    lda $16C2,x
    cmp #!CHAM_TYPE
    bne +
    lda.l !CST,x
    beq +
    phy
    ldy $17FA,x
    cpy #$60
    bcs ++
    jsr release
    jsr own_look
++  ply
    lda #$04
    sta.l !CPH,x
+   jml !GS_ENEMY

;-----------------------------------------------------------------------------
; SB1's table ($C6:6BFC, read from the start when it changes into a copy): frames of each entry and
; whether it shows the new look. SB1 then stands 32 frames with the new look; here it walks at once.
flick_frames:
    db 63, 1, 3, 1, 3, 1, 3, 1, 2, 1, 2, 1, 2, 1, 1, 1, 1, 1, 1, 2, 1, 2, 1, 2, 1, 3, 1, 3, 1, 3, 1, 1
flick_new:
    db 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1
; per half (2k): tile base, VRAM word address (page 12 + k / 2, columns 8 * (k & 1))
half_tile:
    dw $0180, $0188, $01A0, $01A8, $01C0, $01C8, $01E0, $01E8
half_vram:
    dw $7800, $7880, $7A00, $7A80, $7C00, $7C80, $7E00, $7E80

end:

print "SYM chameleon ", hex(chameleon)
print "SYM cham_hit ", hex(cham_hit)
print "SYM cham_nmi ", hex(cham_nmi)
print "SYM end ", hex(end)
