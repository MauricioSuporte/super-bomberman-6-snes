; World 1 (tools/sb6/features/world1.py): the SB1-style exit door.
;
; w1_op (FF 1A F6 n, through pick_op; M/X 8-bit, [$0D] = the F6, [$0A] = n,
; the op skips it): one exit portal per stage. With PORTALKIND (features/
; portal.py, 1-1 to 1-5) it is SB1's portal in the middle cell (7, 6) (the
; cell under it if that is a wall): portal_task (below) waits for the clear,
; that cell's soft block (and item) to be gone and a free OBJ palette slot
; 3-7 (the dead enemies' ones), then makes it from our own kind (w1_kind)
; with its sound (SB1's bell echo, features/portal_sfx.py: asked as SB5's
; portal sound, group 2 $33, which asm/game_sfx.asm swaps). Without PORTALKIND: SB5's portal
; queue ($7E:4DA3, 5 slots: state $41/$42, x $4DA8, y $4DAD; task $C5:3B60
; creates the portal once the stage is clear and waits while its cell holds
; a soft block) at a soft block chosen at random when the stage starts.
;   n = 3  (stage record, type 04: stage start) forget the door and start
;          a task (JSL $C020A1) that waits for the collision map (filled
;          some 50 frames after the type 04 scripts, which run one after
;          the other in one task: a sleep there would hold the stage setup)
;          and picks the door: a random cell with a soft block ($1052 & $E0
;          = $20) and no hidden item ($145A); none -> 0 (picked again at the
;          clear); then it ends (JSL $C021CE)
;   n = 1  (type 0D: all enemies dead) queue the portal at the door (a soft
;          block left, else a free floor cell)
;   n = 4  (1-6's third duel, type 04) the stands blink (stand_task, below)
;   n = 5  (1-7, type 04) start the electric fence's task (asm/stage_anim.asm) and the clown
;          boss's (asm/sb1_enemies.asm clown_start)
;   n = 6  (1-4, 1-5, 1-6, type 04) start the animated tiles' task (asm/stage_anim.asm)
;   n = 7  (1-6's duels, type 04) the rival walks in (intro_task, below)
;   n = 2  (type 0C) players on the door: like op $12 ($C2:0C67), the sum
;          of seat + 1 of the live bombers on the cell -> $0373, JSL $C174D1;
;          the seat SB5 saw stepping on the portal ($1CC8 = seat | $80,
;          $C4:2C77) counts even if it left the cell before this test runs
; State: $7F:FB10 door x (0 = not chosen), $7F:FB11 door y, $7F:FB12-$7F:FB13
; scratch, $7F:FB14 = 1 while portal_task makes the portal, $7F:FB15-$7F:FB17
; the door root ($037C-$037E at the clear op: $C2:265C gives it to the portal
; object, whose touch runs that root's 0C / 0B scripts) (docs/FREE_SPACE.md).

asar 1.90
hirom
org !ORG

!DX    = $7FFB10
!DY    = $7FFB11
!CNT   = $7FFB12
!K     = $7FFB13
!PKIND = $7FFB14               ; 1 while portal_task creates the portal: w1_kind reads our kind
!PROOT = $7FFB15               ; $037C-$037E (the door root) when the clear op ran: the portal object keeps it

w1_op:
    php
    sep #$30
    lda [$0A]                   ; n, then skip it
    pha
    rep #$20
    inc $0A
    sep #$20
    pla
    beq .pick
    dec a
    beq .queue
    dec a
    beq .touch
    dec a
    dec a
    bne +
    jsr stand_start             ; 4: the stands blink (1-6's Golden Bomber)
    plp
    rtl
+   dec a
    bne +
if !ANIMSTART
    jsl !ANIMSTART              ; 5: 1-7's electric fence (asm/stage_anim.asm)
endif
    jsl !CLOWNSTART             ;    and its clown (asm/sb1_enemies.asm clown_start)
    plp
    rtl
+   dec a
    bne +
if !ANIMSTART
    jsl !ANIMSTART              ; 6: animated stage tiles only (1-4's bumpers, 1-5's lights)
endif
    plp
    rtl
+   dec a
    bne +
    jsr intro_start             ; 7: 1-6's rival walks in
    plp
    rtl
+   lda #$00                    ; 3: forget, start the picking task
    sta.l !DX
    rep #$10                    ; and clear the SB1 enemies' state (asm/sb1_enemies.asm $7F:F700-$7F:F77F,
    ldx #$0400                  ; asm/chameleon.asm $7F:F800-$7F:FAFF)
-   dex
    sta.l $7FF700,x
    bne -
    sep #$10
    jsl $C020A1
    dl door_task
    db $60                      ; skipped: $C020A1 returns one byte past the dl (SB5's own callers have an RTS there)
    plp
    rtl

.touch:
    jsr touch
    plp
    rtl
.pick:
    jsr pick
    plp
    rtl
.queue:
    lda.l !DX
    bne +
    jsr center
+
if !PORTALKIND
    lda $037C                   ; the door root (its 0B / 0C scripts): $C2:265C gives it to the portal
    sta.l !PROOT
    lda $037D
    sta.l !PROOT+1
    lda $037E
    sta.l !PROOT+2
    jsl $C020A1                 ; SB1's portal (features/portal.py): portal_task, every frame until made
    dl portal_task
    db $60                      ; (skipped: $C020A1 returns one byte past the dl)
else
    ldx #$00
-   lda.l $7E4DA3,x
    bmi +
    inx
    cpx #$05
    bne -
    bra ++
+   lda #$41
    sta.l $7E4DA3,x
    lda.l !DX
    sta.l $7E4DA8,x
    lda.l !DY
    sta.l $7E4DAD,x
++
endif
    plp
    rtl

; World 1's portal: the middle of the field (x 7, y 6), the first free floor from there if it is a wall
center:
    lda #$07
    sta.l !DX
    lda #$06
    sta.l !DY
    lda.l $7E1052+$67
    bpl +
    jsr floor
+   rts

if !PORTALKIND
; Task (the stage is clear): once the portal's cell holds no soft block, no item / portal ($1152 & $C0)
; and an OBJ palette slot 3-7 is free (the enemies' are released when they go), makes the portal as
; SB5's processor $C5:3B60 does, with our kind (w1_kind), and ends. Its sound: asked as SB5's portal sound
; (group 2 $33) with PKIND = 2: asm/game_sfx.asm plays SB1's bell echo instead (features/portal_sfx.py).
portal_task:
    php
    sep #$30
    lda.l !DY
    asl a
    asl a
    asl a
    asl a
    ora.l !DX
    tax
    lda.l $7E1052,x
    and #$E0
    bne .wait
    lda.l $7E1152,x
    and #$C0
    bne .wait
    ldx #$03                    ; a free palette slot 3-7 (else SB5's failure path would move P3/P4)
-   lda.l $7E2B10,x
    beq +
    inx
    cpx #$08
    bne -
    bra .wait
+   jmp .make
.wait:
    plp
    rtl
.make:
    lda.l !DX
    sta $1D28
    stz $1D29
    lda.l !DY
    sta $1D2A
    stz $1D2B
    lda.l !PROOT
    sta $037C
    lda.l !PROOT+1
    sta $037D
    lda.l !PROOT+2
    sta $037E
    lda #$01
    sta.l !PKIND
    lda #$41
    jsl $C2265C
    php                         ; keep A (the new object's slot) and the carry
    pha
    lda #$00
    sta.l !PKIND
    pla
    plp
    bcs .wait2
    tax
    lda $199A,x
    tax
    jsl $C01F78
    lda $1D28
    sta $055F,x
    lda $1D29
    sta $0560,x
    lda $1D2A
    sta $05BF,x
    lda $1D2B
    sta $05C0,x
    lda #$02                    ; group 2 $33 (SB5's portal sound) with PKIND = 2: asm/game_sfx.asm, which
    sta.l !PKIND                ; mutes that id (a dead enemy's score), plays the portal's SFX $62 instead
    xba
    lda #$33
    jsl $C00CED
    lda #$00
    sta.l !PKIND
    jsl $C021CE                 ; end this task
.wait2:
    plp
    rtl

; $C2:26AF (object maker $C2:267D, M 8-bit, DBR $80): the kind's definition = $80:CDE0 + 10 (kind - 1),
; ours (bank $80, features/portal.py) while portal_task makes the portal
w1_kind:
    clc
    lda $B5
    adc #$E0
    sta $C9
    lda $B6
    adc #$CD
    sta $CA
    lda.l !PKIND
    beq +
    lda.b #!PORTALKIND&$FF
    sta $C9
    lda.b #(!PORTALKIND>>8)&$FF
    sta $CA
+   rtl
endif

door_task:
    php
    sep #$30
    lda.l $7E1052               ; corner cell: a wall once the map is in
    beq +
if !PORTALKIND
    jsr center
else
    jsr pick
endif
    jsl $C021CE                 ; end this task
+   plp
    rtl

; A = cell's flags ok? (soft block, no item) -> Z set when usable
soft:
    lda.l $7E1052,x
    and #$E0
    cmp #$20
    bne +
    lda.l $7E145A,x
+   rts

pick:
    lda #$00
    sta.l !DX
    sta.l !PKIND                ; (2 = the portal's sound: asm/game_sfx.asm lets that $33 through)
    sta.l !CNT
    ldx #$11                    ; field cells 17-206 (rows 1-11)
-   jsr soft
    bne +
    lda.l !CNT
    inc a
    sta.l !CNT
+   inx
    cpx #$CF
    bne -
    lda.l !CNT
    beq .out
    jsl $C01DC4                 ; random byte
-   cmp.l !CNT
    bcc +
    sec
    sbc.l !CNT
    bra -
+   sta.l !K
    ldx #$11
-   jsr soft
    bne +
    lda.l !K
    beq .got
    dec a
    sta.l !K
+   inx
    cpx #$CF
    bne -
.out:
    rts
.got:
    txa
    and #$0F
    sta.l !DX
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !DY
    rts

; no soft block left: the first free floor cell from the middle of the field
floor:
    ldx #$77                    ; x 7, y 7
-   lda.l $7E1052,x
    ora.l $7E1152,x
    beq +
    inx
    cpx #$CF
    bne -
    ldx #$11
    bra -
+   txa
    and #$0F
    sta.l !DX
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    sta.l !DY
    rts

touch:
    stz $9F
    lda $1CC8                   ; the seat SB5 saw entering the portal ($C4:2C77: seat | $80): it counts
    bpl +                       ; even if it moved off the cell before this test (a press right after)
    and #$07
    inc a
    sta $9F
    bra .done
+   ldx #$00
.seat:
    lda.l $7E15A2,x
    bmi .next
    lda.l $7E182A,x
    clc
    adc #$08
    lsr a
    lsr a
    lsr a
    lsr a
    cmp.l !DX
    bne .next
    lda.l $7E1872,x
    clc
    adc #$08
    and #$F0
    lsr a
    lsr a
    lsr a
    lsr a
    cmp.l !DY
    bne .next
    txa
    inc a
    clc
    adc $9F
    sta $9F
.next:
    inx
    cpx #$04
    bcc .seat
.done:
    lda $9F
    sta.l $7E0373
    jsl $C174D1
    rts

;-----------------------------------------------------------------------------
; knight_hit: $C3:49EC (LDA $1052,Y : AND #$04), the flame test of an enemy
; (X = actor, Y = its cell, M/X 8-bit; SEC = hit, through $C3:49F3). On
; World 1's 1-5 (stage !KNIGHT_STAGE) the knights (enemy type $08) are
; not hurt by a blast coming from the front, as in SB1's 6-4: facing
; $1632 (1 right, 2 down, 3 left, 4 up), the flame cells from the knight's
; one in that direction lead to the explosion's center ($1052 & 7 = 5).
; 1-7's clown (enemy type !CLOWN_TYPE) is tested on the 3 x 3 cells around it
; instead (asm/sb1_enemies.asm clown_hit).
knight_hit:
    lda $16C2,x                 ; 1-7's clown: flames on the 3 x 3 cells around it
    cmp #!CLOWN_TYPE
    bne +
    jsl !CLOWNHIT
    bcc .none
    jml $C349F3
+   lda $1052,y
    and #$04
    beq .none
    lda.l $7E1031
    cmp #!KNIGHT_STAGE
    bne .orig
    lda $16C2,x
    cmp #$08
    bne .orig
    ; flame cells: $1052 & 7 = 7 center, 5 horizontal arm, 6 vertical arm. Blocked (not hit) only when
    ; the knight stands on an arm along the way it faces and the center is ahead of it: a knight on the
    ; center, across an arm or turned away from the center (also in the middle of an explosion) is hit
    phx
    lda $1632,x
    dec a
    and #$03
    tax
    lda.l .axis,x               ; 5 facing left / right, 6 facing up / down
    sta.l !CNT
    lda $1052,y
    and #$07
    cmp.l !CNT
    bne .side                   ; on the center or across the arm
    lda.l .step,x
    sta.l !K
    tya
    tax
    lda #$0C                    ; at most 12 cells
    sta.l !CNT
-   txa
    clc
    adc.l !K
    tax
    lda.l $7E1052,x
    bit #$F8
    bne .side                   ; a wall, block, bomb...: the arm ends behind the knight
    and #$07
    cmp #$07
    beq .front                  ; the center ahead
    and #$04
    beq .side
    lda.l !CNT
    dec a
    sta.l !CNT
    bne -
.side:
    plx
.orig:
    jml $C349F3
.front:
    plx
.none:
    jml $C34A04                 ; CLC : RTS (not hit)
.axis:
    db $05, $06, $05, $06
.step:
    db $01, $10, $FF, $F0       ; right, down, left, up

; ---------------------------------------------------------------------------
; 1-6, the tournament (SB1 World 5's arena): three duels, stages !RIVAL1/2/3, each
; one rival (seat 4) drawn with character !RIVALCHAR's sheet and
; one column of its palette picture (rival_pal); the third is the Golden
; Bomber: 3 hits (2 hearts, $1662), kick (rival_stats), and the stands blink between the crowd and SB1 5-8's
; stone before it (stand_task). The arena is theme $28 / set 4 archive and palette $F0
; (features/sb1_stages.py "sb1_5-1"), ids past SB5's tables: arc_entry and
; bombers.asm's pal_lookup point at the World 1 entries.

; $C0:1B0E (archive loader, A = M 8-bit, Y = id - 1, X = set * 2): replaces
; LDA #$E3 / STA $C8 / REP #$20 / LDA $C01C96,X / STA $C6 (returns M 16-bit)
arc_entry:
    lda $0AE7
    cmp #$04
    bne .orig
    tya
    cmp #$EF
    bcc .orig
    lda.b #(!W1ARC-8*$EF)>>16
    sta $C8
    rep #$20
    lda.w #(!W1ARC-8*$EF)&$FFFF
    sta $C6
    rtl
.orig:
    lda #$E3
    sta $C8
    rep #$20
    lda.l $C01C96,x
    sta $C6
    rtl

; $C4:3CD5 (rival set-up $C4:3CCF, X = seat, A = character already in
; $16C2,X): replaces TAX / LDA $BB4E,X / CLC / ADC #$07 (A = palette id)
rival_pal:
    pha                         ; the character
    cpx #$04
    bne .stock
    phx
    jsr duel
    ldx #$02
-   cmp.l .stages,x
    beq .ours
    dex
    bpl -
    plx
.stock:
    plx                         ; (PLX after us restores the seat)
    lda $BB4E,x
    clc
    adc #$07
    rtl
.ours:
    lda #!RIVALCHAR             ; character !RIVALCHAR's sheet (features/world1.py RIVAL_CHAR)
    sta $16C2+4
    lda.l .ids,x
    plx
    plx
    rtl
.stages:
    db !RIVAL1, !RIVAL2, !RIVAL3
.ids:
    db !PAL1, !PAL2, !PAL3

!DST = $7FFBFD                  ; the duel being fought (its stage id: !RIVAL1/2/3; 1-6 is all stage !RIVAL1)
!RESP = $7FFBFE                 ; 1 while next_rival creates the rival (rival_pal / rival_stats read !DST)

; the duel whose rival is being set up: the stage's own, or !DST when next_rival makes it
duel:
    lda.l !RESP
    beq +
    lda.l !DST
    rts
+   lda.l $7E1031
    rts

; $C4:3D28 (end of the rival set-up: its stats from the character's table
; $C0:B9D4, here the last one): replaces LDA ($BD),Y / STA $167A,X (X =
; seat). 1-6's rivals (features/world1.py RIVAL_STATS): hearts ($1662: hits
; - 1), fire ($17CA), bombs ($7E:4EBD), abilities ($7E:4ED5: only the kick,
; bit 1, with $167A bit 6 from the table; the character's own gave SB5's
; mine bomb), speed ($15D2/$15EA: $00E0 = the players' start, + $20 per
; skate as SB5's item $C5:4232), AI level ($1D26)
rival_stats:
    lda ($BD),y
    sta $167A,x
    cpx #$04
    bne .out
    phx
    jsr duel
    ldx #$02
-   cmp.l .stages,x
    beq .found
    dex
    bpl -
    plx
.out:
    rtl
.found:
    lda.l .hp,x
    sta $1662+4
    lda.l .fire,x
    sta $17CA+4
    lda.l .bombs,x
    sta.l $7E4EBD+4
    lda.l .abil,x
    sta.l $7E4ED5+4
    lda.l .level,x
    sta $1D26
    lda.l .speed,x
    sta $15D2+4
    lda.l .speedhi,x
    sta $15EA+4
    plx
    rtl
.stages:
    db !RIVAL1, !RIVAL2, !RIVAL3
.hp:
    db !HP1, !HP2, !HP3
.fire:
    db !FIRE1, !FIRE2, !FIRE3
.bombs:
    db !BOMBS1, !BOMBS2, !BOMBS3
.abil:
    db !ABIL1, !ABIL2, !ABIL3
.level:
    db !LEVEL1, !LEVEL2, !LEVEL3
.speed:
    db !SPEED1&$FF, !SPEED2&$FF, !SPEED3&$FF
.speedhi:
    db !SPEED1>>8, !SPEED2>>8, !SPEED3>>8

; FF 1A F6 07 (1-6's duels, type 04): SB1 World 5's intro. The rival (seat
; 4) starts in the stands' corridor at (7, 1) (its FF 7C op); the task holds
; it there (no AI: $101F+4 = 0 makes it a pad-driven bomber with no input)
; until the collision map is in (and, before the Golden Bomber, the stands
; stopped blinking: !BPH = 3), opens the corridor (cells (7, 1), (7, 2) of
; $1052 = 0), then each frame (tasks run after the pad reader) freezes the
; four seats' pads and holds "down" on the rival's ($31+4; intro_pads does
; it before the objects run) until its y
; ($1872+4) reaches !INTROY (or it got stuck 120 frames after leaving),
; then gives it back to the AI, walls the corridor again and closes the
; gate (BG1 map words of the closed gate, SB1's doors). State $7F:FBD4
; phase, $FBD5 frames left, $FBD6 the stage.
!IPH = $7FFBD4
!IFR = $7FFBD5
!IST = $7FFBD6
!ITS = $7FFBD7                  ; item_task (below): the stage, frames left (word)
!ITT = $7FFBD8
!NXT = $7FFBFC                  ; frames since the rival died (next duel)
!NEXTWAIT = 90                  ; frames from the rival's death to the next rival
!GOLDWAIT = 300                 ; from the Golden Bomber's death to the stage end (5 s), or
!GOLDGRACE = 30                 ; once no item is left on the field (after this many frames)
!SPX = $7FFB20                  ; 4 bytes: each seat's start x ($182A), then 4 its y ($1872)
!GOLDN = $7FFB28                ; !NXT's carries (frames / 256)
!EXITWAIT = 450                 ; then to the next duel (SB5's boss victory: 433 frames)
!FUP = $7FFBFB                  ; seats whose start pose was turned up (face_up_start)

intro_start:
    lda.l $7E1031
    sta.l !DST
    lda #$00
    sta.l !RESP
    sta.l !IPH
    lda #$00
    sta.l !FUP
    lda.l $7E1031
    sta.l !IST
    sta.l !ITS
    rep #$20
    lda.w #!ITEMFIRST
    sta.l !ITT
    sep #$20
    jsl $C020A1
    dl intro_task
    db $60
    jsl $C020A1
    dl item_task
    db $60
    lda #$00
    sta.l !NXT
    sta.l !GOLDN
    rts

; SB1 World 5's items (its routine $C4:3523): once the rival walked in, every
; !ITEMEVERY frames, while fewer than 32 items lie on the field, one of the
; 16 entries of .pool (features/world1.py ITEM_POOL: SB1's table $C4:3553 in
; SB5 ids) appears on a random free floor cell (no wall, bomb, flame, item or
; bomber there; else tried again next frame, as SB1 does), through SB5's
; $C5:4557 (A = item, $AE = cell: the item map $145A, $1052 = $10, $1152
; bit 7, its metatile). State $7F:FBD7 the stage, $7F:FBD8 frames left (word).

item_task:
    php
    sep #$30
    lda.l $7E1031
    cmp.l !ITS
    beq +
    jsl $C021CE                 ; stage over
    plp
    rtl
+   lda.l !IPH
    cmp #$03
    bne +
    jsr golden_wait             ; the stands blink before the Golden Bomber
    bra .out
+   cmp #$02
    bne .out                    ; the rival is not in yet
    jsr face_up_start
    lda.l $7E15A2+4             ; the rival (seat 4): bit 7 = dead
    bpl .items
    jsr rival_dead
    bra .out
.items:
    rep #$20
    lda.l !ITT
    dec a
    sta.l !ITT
    sep #$20
    bne .out
    jsr item_place
    rep #$20
    lda.w #!ITEMEVERY
    bcs +
    lda.w #$0001                ; no free cell this time: next frame
+   sta.l !ITT
    sep #$20
.out:
    plp
    rtl

; after SB5's stage end (next_duel above): what the portal's exit script does, type
; 0B (`0F next`: $1031 = the next duel, $1D1E = 4), as the portal does once its
; player went in (SB5 waits ~475 frames there, the win sound)
exit_task:
    php
    sep #$30
    lda.l $7E1031
    cmp.l !ITS
    bne .end
    lda.l !NXT                  ; frames: !NXT + 256 * !GOLDN
    inc a
    sta.l !NXT
    bne .lo
    lda.l !GOLDN
    inc a
    sta.l !GOLDN
.lo:
    lda.l !GOLDN
    cmp #!EXITWAIT>>8
    bcc .out
    bne .due
    lda.l !NXT
    cmp #!EXITWAIT&$FF
    bcc .out
.due:
    lda.l $7E1D1E               ; what its op 0F does ($C2:0C20), not through the script engine (run
    and #$04                    ; from a task of ours, $C2:00D7 ended it twice and SB5 hung)
    bne .end
    lda.l !DST
    ldx #!NEXT1
    cmp #!RIVAL1
    beq +
    ldx #!NEXT2
    cmp #!RIVAL2
    beq +
    ldx #!NEXT3
+   txa
    sta.l $7E1031
    lda #$04
    sta.l $7E1D1E
.end:
    jsl $C021CE
.out:
    plp
    rtl

; a rival's death (SB5 $C4:3DED, X = its character, $AE = its cell): SB5 drops
; its character's item ($C4:B9CA); in 1-6 the white and black mechas drop
; nothing, the Golden Bomber the kick ($0B)
rival_item:
    lda.l $7E1031
    cmp #!RIVAL1
    bne .sb5
    lda.l !DST
    cmp #!RIVAL3
    bne .none
    lda #$0B
    bra .put
.sb5:
    lda.l $C4B9CA,x
    beq .none
.put:
    jsl $C54557
.none:
    rtl

; a bomber's death sound (SB5 $C4:367F, X = actor, M 8-bit): the death sound
; (group 3 id 1: SB1's, game_sfx), for 1-6's white and black mechas SB1 World
; 5's crowd instead (Hudson SFX !CHEERCMD, sent by gs_tick: its pending byte)
rival_sfx:
    txa
    cmp #$04
    bne .death
    lda.l $7E1031
    cmp #!RIVAL1
    bne .death
    lda.l !DST
    cmp #!RIVAL3
    beq .death
    lda #!CHEERCMD
    sta.l $00018C               ; game_sfx's !gs_pend
    rtl
.death:
    lda #$03
    xba
    lda #$01
    jsl $C00CED
    rtl

; 1-6's next duel, as in SB1 (one stage, no stage end): the rival (seat 4) made
; again in the stands' corridor (7, 1) the way op FF 7C does it ($C2:16EE:
; $1D28 / $1D2A = cell, A = character, X = seat, JSL $C4:3CB5: set-up with
; rival_pal / rival_stats, its object, $1D50 + 1, its death task $C4:3D94),
; the gate open again and intro_task as at the start (before the Golden
; Bomber the stands blink first, stand_task)
next_rival:
    lda.l !DST
    ldx #!RIVAL2
    cmp #!RIVAL1
    beq +
    ldx #!RIVAL3
+   txa
    sta.l !DST
    cmp #!RIVAL3
    bne make_rival
    lda #$03                    ; the Golden Bomber: the stands blink first (players held,
    sta.l !IPH                  ; intro_pads), then golden_wait makes it
    jsr stand_start
    rts

; item_task while !IPH = 3: the stands' blinking over (!BPH = 3) -> the Golden Bomber
golden_wait:
    lda.l $7FFBD0               ; stand_task's phase (!BPH)
    cmp #$03
    bcc +
    jsr make_rival
+   rts

make_rival:
    lda #$01
    sta.l !RESP
    lda #$07
    sta $1D28
    lda #$01
    sta $1D2A
    lda #$80                    ; seat 4 empty, as at the stage's start (the dead rival left $82:
    sta $15A2+4                 ; the new one came out dead)
    ldx #$04
    lda #$01
    jsl $C43CB5
    sep #$30
    lda #$00
    sta.l !RESP
    sta.l !IPH
    jsr gate_open
    jsl $C020A1
    dl intro_task
    db $60
    rts

; item_task, the rival dead: the next rival or the stage end once its time is up
rival_dead:
    lda.l $7E1D1E               ; SB5's stage end already running (bit 0)
    lsr a
    bcs .out
    lda $17FA+4                 ; its object gone (death animation over)
    cmp #$FF
    bne .out
    lda.l !NXT                  ; frames: !NXT + 256 * !GOLDN
    inc a
    sta.l !NXT
    bne +
    lda.l !GOLDN
    inc a
    sta.l !GOLDN
+   lda.l !DST
    cmp #!RIVAL3
    beq .golden
    lda.l !NXT
    cmp #!NEXTWAIT
    bcc .out
    lda #$00
    sta.l !NXT
    jmp next_rival              ; the next duel in this same stage
.golden:                        ; its kick item lies on the field: !GOLDWAIT frames to pick it
    lda.l !GOLDN
    bne .late
    lda.l !NXT
    cmp #!GOLDGRACE
    bcc .out
    jsr items_left              ; every item picked: the end at once
    beq .end
    lda.l !GOLDN
.late:
    cmp #!GOLDWAIT>>8
    bcc .out
    bne .end
    lda.l !NXT
    cmp #!GOLDWAIT&$FF
    bcc .out
.end:
    lda #$00
    sta.l !NXT
    sta.l !GOLDN
    jsl $C020A1                 ; exit_task: the type 0B script !EXITWAIT frames later
    dl exit_task
    db $60
    jsr victory_load
    pla                         ; (rival_dead's return)
    pla
    plp                         ; the next duel, as in SB1 (no portal): SB5's stage end as
    jml $C502AB                 ; when the last player went through the portal (sets $1D1E bit 0,
                                ; type 0A, win sound $22, ends this task)
.out:
    rts

; Z = no item on the field (item map $1152 bit 7, as item_place counts them)
items_left:
    ldx #$CF
-   lda $1152,x
    bmi +
    dex
    cpx #$FF
    bne -
    lda #$00
+   rts

; carry set = an item was placed (M/X 8-bit)
item_place:
    ldx #$CF
    ldy #$00
-   lda $1152,x
    bpl +
    iny
+   dex
    cpx #$FF
    bne -
    cpy #32
    bcs .fail
    lda #$CF
    jsl $C01DEB                 ; random 0-$CF
    tax
    lda $1052,x
    bne .fail
    lda $1152,x
    bmi .fail
    lda $145A,x
    bne .fail
    txa
    ldy #$04
-   cmp $16AA,y                 ; a bomber's cell
    beq .fail
    dey
    bpl -
    sta $AE
    lda #!ITEMLAST
    jsl $C01DEB                 ; random entry of the pool
    tax
    lda.l item_pool,x
    jsl $C54557
    sep #$30
    sec
    rts
.fail:
    clc
    rts

item_pool:
    db !ITEMPOOL

; $C0:0B54 (main loop, after the pad reader, before the objects): replaces
; JSL $C04733. While the rival walks in (!IPH = 1 in its stage) the four
; seats' pads are empty and the rival's says "down"; while 1-7's clown
; appears or dies (!CLOWNHOLD = $A5) the four seats' pads are empty.
; 1-7 (the clown comes from above): while the clown's intro holds the pads (!CLOWNHOLD = $A5 and its
; phase, !CLOWNHOLD - $19, under 3 = fight) every seat faces up (hold_up), from the first frame the bombers
; exist, before the fade in. SB5 starts play (~290 frames after the fade in) while the intro still holds the
; pads and would set its idle animation $15 (front).
start_up:
    lda.l $7E1031
    cmp #$68
    bne .rts
    lda.l !CLOWNHOLD
    cmp #$A5
    bne .rts
    lda.l !CLOWNHOLD-$19
    cmp #$03
    bcs .rts
    jmp hold_up
.rts:
    rts

; Seats held by an intro (1-6's rivals, 1-7's clown): each faces up in the stand pose of its state (on a
; Louie: its riding animation; before, a rider kept facing down in 1-7 and showed SB5's idle on a Louie
; while 1-6 held it), and SB5's frames-standing count ($17E2) stays 1, so nobody idles. A new animation
; only when the seat shows another one (one each frame cost 3 fps with 4 players). Left alone: death
; ($16), jumping onto / thrown off a Louie ($17-$1A), time up / victory ($1F/$20), a carried bomb. (Until the
; strip with the new pose is served, $079F still shows the old one: asked again, as SB5 does for a walk.)
hold_up:
    ldx #$03
.seat:
    lda $15A2,x
    bmi .next                   ; no bomber in this seat
    lda #$01                    ; standing, not idle: 0 would run SB5's 'just stopped' ($C4:43A4 -> $C4:4318) every
    sta $17E2,x                 ; frame, a new strip each frame (1 KB of vblank, the darkness' HDMA lost with 1P)
    lda $1782,x
    and #$08
    bne .next
    ldy $17FA,x
    lda $079F,y                 ; the animation shown (SB5's stage start pose $47 is set with $1632 = 4 already),
    sec                         ; counted from the character's first ($1692)
    sbc $1692,x
    cmp #$15
    beq .next
    cmp #$16
    bcc +
    cmp #$1A
    bcc .next
+   cmp #$1E
    beq .next
    cmp #$1F
    beq .next
    pha
    jsr up_base
    clc
    adc #$03                    ; (+ facing up - 1)
    cmp 1,s
    bne .turn
    pla
    lda $1632,x
    cmp #$04
    beq .next
    bra .set
.turn:
    pla
.set:
    jsr up_base
    phx
    ldy #$04                    ; up ($C4:3C24: A = animation - $1692, Y = facing, X = actor)
    jsl $C43C24
    plx
.next:
    dex
    bpl .seat
    rts

; A = the stand animation of seat X's state, counted from its first ($1692): on a Louie ($1782 bit 7) its
; riding animation (SB5's $C4:4346: $80:BB58 by the Louie's character, $16C2 + seat + $0128), else the
; stand pose $46 (+ facing - 1).
up_base:
    lda $1782,x
    bpl .foot
    phx
    txa
    clc
    adc $0128
    tax
    lda $16C2,x
    tax
    lda.l $80BB58,x
    plx
    rts
.foot:
    lda #$46
    sec
    sbc $1692,x
    rts

intro_pads:
    php
    sep #$30
    jsr start_up
    lda.l !CLOWNHOLD            ; 1-7's clown holds the players (its intro and death, asm/sb1_enemies.asm)
    cmp #$A5
    bne .rival
    lda.l $7E1031
    cmp #$68
    bne .rival
    ldx #$03
-   stz $2C,x
    stz $31,x
    stz $36,x
    stz $3B,x
    dex
    bpl -
    bra .go
.rival:
    lda.l !IPH
    cmp #$03                    ; stands blinking before the Golden Bomber: players held too
    beq +
    cmp #$01
    bne .go
+   lda.l $7E1031
    cmp.l !IST
    bne .go
    cmp #!RIVAL1
    beq +
    cmp #!RIVAL2
    beq +
    cmp #!RIVAL3
    bne .go
+   ldx #$04
-   stz $2C,x
    stz $31,x
    stz $36,x
    stz $3B,x
    dex
    bpl -
    lda #$04
    sta $31+4
    jsr hold_up                 ; the players face up, no idle
.go:
    plp
    jml $C04733

; the players face up, toward the stands' corridor the rival comes down (SB1);
; face_up_start (item_task, from the rival's arrival until each seat had it):
; SB5's start pose $15 (front only) becomes the stage start pose up ($49)
face_up_start:
    lda.l !FUP
    cmp #$0F
    beq .done
    ldx #$03
-   lda $15A2,x
    bmi +
    lda $179A,x
    cmp #$15
    bne +
    lda.l !FUP
    ora.l .bit,x
    sta.l !FUP
    phx
    ldy #$04
    lda #$45                    ; $46 + facing - 1 = $49 ($1692 = 1)
    sec
    sbc $1692,x
    clc
    adc #$01
    jsl $C43C24
    plx
+   dex
    bpl -
.done:
    rts
.bit:
    db $01, $02, $04, $08

face_up:
    ldx #$03
-   lda $15A2,x
    bmi +                       ; no bomber in this seat
    phx
    jsr up_base                 ; the stand pose up of its state (SB5's stage start / its riding animation)
    ldy #$04                    ; up ($C4:3C24: A = animation - the character's first $1692, Y = facing,
    jsl $C43C24                 ; X = actor)
    plx
+   dex
    bpl -
    rts

intro_task:
    php
    sep #$30
    lda.l $7E1031
    cmp.l !IST
    bne .end
    lda $17FA+4                 ; the rival's object
    cmp #$FF
    beq .out
    lda.l !IPH
    beq .wait
    dec a
    beq .walk
.end:
    jsl $C021CE
.out:
    plp
    rtl
.wait:
    stz $101F+4
    stz $31+4
    stz $2C+4
    stz $36+4
    stz $3B+4
    lda.l !DST
    cmp #!RIVAL3
    bne +
    lda.l $7FFBD0               ; stand_task's phase (!BPH)
    cmp #$03
    bcc .out                    ; the stands are still blinking
+   lda.l $7E1052               ; corner cell: a wall once the map is in
    bpl .out
    lda #$00
    sta $1052+$17
    sta $1052+$27
    lda #120
    sta.l !IFR
    lda #$01
    sta.l !IPH
    jsr face_up
    jsr keep_spawn
    bra .out
.walk:
    stz $101F+4
    ldx #$04
-   stz $2C,x
    stz $31,x
    stz $36,x
    stz $3B,x
    dex
    bpl -
    lda #$04                    ; down
    sta $31+4
    lda $1872+4
    cmp #!INTROY
    bcs .arrived
    cmp #$11
    bcc .out                    ; not moving yet (SB5's start)
    lda.l !IFR
    dec a
    sta.l !IFR
    bne .out
.arrived:
    stz $31+4
    lda #$01
    sta $101F+4
    lda #$80
    sta $1052+$17
    sta $1052+$27
    jsr gate
    lda #$02
    sta.l !IPH
    plp
    rtl

; FF 1A F6 04 (stage !RIVAL3, type 04): the stands blink. Task: after
; BWAIT frames, 5 times: fade to black (brightness in the INIDISP shadow
; $0300), stands empty on cycles 0/2/4 and full on 1/3 (BG1 map words
; through SB5's VRAM queue, $C0:0478/0497/04AC), hold, fade back in.
; State $7F:FBD0 phase, $FBD1 frames, $FBD2 cycle, $FBD3 brightness.
!BPH = $7FFBD0
!BFR = $7FFBD1
!BCY = $7FFBD2
!BBR = $7FFBD3

stand_start:
    lda #$00
    sta.l !BPH
    sta.l !BCY
    lda #90
    sta.l !BFR
    jsl $C020A1
    dl stand_task
    db $60
    rts

stand_task:
    php
    sep #$30
    lda.l !BFR
    beq +
    dec a
    sta.l !BFR
    plp
    rtl
+   lda.l !BPH
    beq .fadeout
    dec a
    beq .black
    dec a
    beq .fadein
    jsl $C021CE                 ; done
    bra .out
.fadeout:                       ; phase 0: brightness 15 -> 0, 2 frames a step
    lda.l !BBR
    bne +
    lda #$10
+   dec a
    sta.l !BBR
    sta $0300
    bne .two
    jsr stands
    lda.l !BCY
    cmp #$04
    bne +
    jsr spawn_reset             ; the last blackout: everyone back to the start, facing up
+   lda #$01
    sta.l !BPH
    lda #30
    sta.l !BFR
    bra .out
.black:                         ; phase 1 done: fade in
    lda #$02
    sta.l !BPH
    bra .out
.fadein:
    lda.l !BBR
    inc a
    sta.l !BBR
    sta $0300
    cmp #$0F
    bne .two
    lda #$00
    sta.l !BBR
    lda.l !BCY
    inc a
    sta.l !BCY
    cmp #$05
    bcc +
    lda #$03                    ; ends next frame
    sta.l !BPH
    bra .out
+   lda #$00
    sta.l !BPH
    lda #20
    sta.l !BFR
    bra .out
.two:
    lda #$01
    sta.l !BFR
.out:
    plp
    rtl

; the first duel's intro: keep every seat's start (spawn_reset)
keep_spawn:
    lda.l !DST
    cmp #!RIVAL1
    bne +
    ldx #$03
.seat:
    lda $15A2,x                 ; out of the stage (P3/P4 may join later with Start): its x/y are stale, its
    bmi .cell                   ; spawn cell ($4E8D/$4EA5, its start: coop_e4.asm e4_spawn_all) is where it starts
    lda $17FA,x
    cmp #$FF
    beq .cell
    lda $182A,x
    sta.l !SPX,x
    lda $1872,x
    sta.l !SPX+4,x
    bra .next
.cell:
    lda.l $7E4E8D,x             ; x = column * 16, y = row * 16 (cell = (x + 8) >> 4)
    asl
    asl
    asl
    asl
    sta.l !SPX,x
    lda.l $7E4EA5,x
    asl
    asl
    asl
    asl
    sta.l !SPX+4,x
.next:
    dex
    bpl .seat
+   rts

; before the Golden Bomber (stand_task, the screen black): each living seat back
; on its start cell (kept by intro_task), in the stage start pose facing up
; ($49, as face_up_start)
spawn_reset:
    ldx #$03
-   lda $15A2,x
    bmi +
    ldy $17FA,x                 ; its object: x $055F, y $05BF ($C4:31BD: $182A = $055F + $1D3B)
    lda.l !SPX,x
    sec
    sbc $182A,x
    clc
    adc $055F,y
    sta $055F,y
    lda.l !SPX,x
    sta $182A,x
    lda.l !SPX+4,x
    sec
    sbc $1872,x
    clc
    adc $05BF,y
    sta $05BF,y
    lda.l !SPX+4,x
    sta $1872,x
    stz $17E2,x
    jsr up_base                 ; (on a Louie: its riding animation, not the pose on foot)
    phx
    ldy #$04
    jsl $C43C24
    plx
+   dex
    bpl -
    rts

; queue the stands' BG1 map words: cycle even -> empty, odd -> crowd
stands:
    rep #$30
    lda.l !BCY
    and.w #$0001
    beq +
    lda.w #!BLINKN*6
+   clc
    adc.w #!BLINK&$FFFF
    tax
    ldy.w #!BLINKN
    jsr rows
    sep #$30
    rts

; the closed gate's BG1 map words (gate_open: the open one's, after them)
gate:
    rep #$30
    ldx.w #!GATE&$FFFF
    ldy.w #!GATEN
    jsr rows
    sep #$30
    rts

gate_open:
    rep #$30
    ldx.w #(!GATE+!GATEN*6)&$FFFF
    ldy.w #!GATEN
    jsr rows
    sep #$30
    rts

; Y rows (address, left word, right word) from X (bank of !BLINK) into SB5's VRAM queue; M/X 16-bit
rows:
    lda $0352
    pha
    lda.w #$0084
    sta $0352
-   lda.l (!BLINK&$FF0000),x
    sta $AE
    phx
    phy
    sep #$30                    ; (SB5's queue routines: PHX ... SEP #$30 / PLX)
    jsl $C00478
    rep #$30
    ply
    plx
    lda.l (!BLINK&$FF0000)+2,x
    sta $A5
    phx
    phy
    sep #$30
    jsl $C00497
    rep #$30
    ply
    plx
    lda.l (!BLINK&$FF0000)+4,x
    sta $A5
    phx
    phy
    sep #$30
    jsl $C00497
    jsl $C004AC
    rep #$30
    ply
    plx
    inx
    inx
    inx
    inx
    inx
    inx
    dey
    bne -
    pla
    sta $0352
    rts

; SB5's stage end ($C5:3ADC, M 8-bit; reached only for a stage left through its exit: $1D1E & $22 = 0, the
; clear bit just set by $C5:3D19): $1046 (the stage the world map and the save open, $4DB2) = the stage it
; leads to ($1031, written by the door's op 0F / exit_task / the clown), so the next stage is open on the map
; after a reset too (1-6 -> 1-7); the stage played when $1031 is not a stage
stage_last:
    lda $1031
    cmp #$0D
    bcc .played
    cmp #$74
    bcs .played
    sta $1046
    rtl
.played:
    lda $102F
    sta $1046
    rtl

;
; a save's flags ($C0:49C8, the loader's STA $7E2900,X, X = byte, DB = $30): flags 5 and 6 (byte 0 bits
; 5-6) are the title's / the attract demo's (one player forced at $C4:28B4, no stage clear at $C5:3A2D),
; set by the title script and cleared when the Normal Game opens; a save that kept them started every stage
; picked on the map afterwards with one player (after a game over or the pause's world map)
save_flags:
    cpx #$00
    bne +
    and #$9F
+   sta.l $7E2900,x
    rtl

print "SYM save_flags ", hex(save_flags)
; SB5's boss music (id $0F: set $35 + song $0E) through the sound API, as SB5's scripts load it (op 42,
; its hooks): $C5:02AB's sound $22 is then its command 3, SB5's boss victory ("major victory"); the
; stage's SB1 list has only ZONE1's jingles (no room for this one's 15 KB of samples). ~1 s of upload, at
; the stage's end (nothing moves); its command 1 is replaced by the victory a frame later. M/X 8-bit.
victory_load:
    php
    phb
    phd
    pea $0000
    pld
    sep #$30
    phx
    phy
    lda #$00
    xba
    lda #$0F
    jsl $C00CED
    sep #$30
    ply
    plx
    pld
    plb
    plp
    rts

print "SYM arc_entry ", hex(arc_entry)
if !PORTALKIND
print "SYM w1_kind ", hex(w1_kind)
endif
print "SYM rival_pal ", hex(rival_pal)
print "SYM rival_stats ", hex(rival_stats)
print "SYM intro_pads ", hex(intro_pads)
print "SYM w1_op ", hex(w1_op)
print "SYM knight_hit ", hex(knight_hit)
print "SYM rival_item ", hex(rival_item)
print "SYM rival_sfx ", hex(rival_sfx)
print "SYM stage_last ", hex(stage_last)
print "SYM end ", hex(pc())
