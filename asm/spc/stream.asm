; SB6 streaming driver for the S-SMP (SPC700).
;
; Plays one BRR voice from a ring buffer that the SNES CPU keeps filling, so a
; long recording (the SB6 title music) can play without fitting in ARAM.
;
; How it runs: the CPU uploads this driver through Hudson's own loader
; (ARAM $0FF0, entered with command $10 on port 1) together with a 3-byte
; block that turns the loader's final RET at $1041 into JMP entry. The driver
; puts the RET back, saves what it changes (zero page $10-$17, DSP registers,
; timer 0) and on release restores everything and executes that RET, so
; Hudson's driver continues exactly as after a normal upload.
;
; ARAM use: !BASE .. ring end only (driver $200 bytes, then the ring), inside
; the area of SB5's title song, which the game reloads when needed.
;
; Port protocol (CPU -> SPC):
;   port 0 = sequence number $00-$7F; ports 1-3 = 3 data bytes. The SPC copies
;            the bytes and echoes the sequence on port 0. A chunk is 54
;            consecutive sequences (162 bytes = 18 BRR blocks = 18 ms).
;   port 0 with bit 7 set = release. The SPC restores Hudson's state, sets
;            port 3 = $A5, waits for port 0 = the loader's last kick value
;            (the CPU first puts ports 1-3 back as the loader left them),
;            then sets port 3 = $AA and returns to Hudson.
; SPC -> CPU while streaming: port 2 = free chunks in the ring, port 3 = $5B.
;
; Defines: BASE (ARAM address, page aligned), CHUNKS (ring size in chunks),
; PREFILL (chunks uploaded with the driver), VOL, MVOL.

asar 1.90
arch spc700
norom
org 0
base !BASE

!RING = !BASE+$200
!RING_END = !RING+(!CHUNKS*162)
!LAST_HEADER = !RING_END-9

!HUDSON_TIMERS = $1E    ; Hudson's shadow of $F1 (it runs timer 1)

; zero page (saved and restored)
!ptr   = $10        ; word: ARAM write pointer of the next chunk
!slot  = $12        ; ring slot of the next chunk
!level = $13        ; chunks buffered and not yet played
!seq   = $14        ; last sequence acknowledged
!state = $15        ; 0 = buffering (voice off), 1 = playing
!ticks = $16

dir:
    dw !RING, !RING                 ; sample 0: start and loop = ring start

entry:
    push p
    push a
    push x
    push y
    clrp
    mov a,#$6f                      ; Hudson's loader: RET / MOV X,#$01
    mov $1041,a
    mov a,#$cd
    mov $1042,a
    mov a,#$01
    mov $1043,a

    mov x,#7
-   mov a,$10+x
    mov save_zp+x,a
    dec x
    bpl -
    mov x,#0
-   mov a,dsp_save_regs+x
    mov $f2,a
    mov a,$f3
    mov save_dsp+x,a
    inc x
    cmp x,#dsp_save_end-dsp_save_regs
    bne -
    mov a,$f4
    mov save_kick,a
    mov !seq,a

    mov x,#0
-   mov a,dsp_init+x
    mov $f2,a
    inc x
    mov a,dsp_init+x
    mov $f3,a
    inc x
    cmp x,#dsp_init_end-dsp_init
    bne -

    ; The last ring block loops back to the ring start. Set it now so an
    ; underrun before the first wrap still stays inside the ring.
    mov a,#$03
    mov !LAST_HEADER,a

    mov !ptr,#(!RING+!PREFILL*162)&$ff
    mov !ptr+1,#(!RING+!PREFILL*162)>>8
    mov !slot,#!PREFILL
    mov !level,#!PREFILL
    mov !state,#0
    mov $fa,#144                    ; timer 0: 8 kHz / 144 = one tick per chunk
    mov a,!HUDSON_TIMERS
    and a,#$ce                      ; timer 0 off, no port clear
    mov $f1,a
    mov $f2,#$6c : mov $f3,#$20     ; unmute (echo writes stay off)
    mov $f7,#$5b

main:
    mov a,$fd                       ; chunks played since the last read
    mov !ticks,a
    mov a,!state
    beq .report
    mov a,!level
    setc
    sbc a,!ticks
    bcs .keep
    ; Underrun: stop and rebuffer from the ring start.
    mov $f2,#$5c : mov $f3,#$01
    mov !state,#0
    mov !level,#0
    mov !slot,#0
    mov !ptr,#!RING&$ff
    mov !ptr+1,#!RING>>8
    bra .report
.keep:
    mov !level,a
.report:
    mov a,#!CHUNKS-1
    setc
    sbc a,!level
    mov $f6,a                       ; free chunks
    mov a,!state
    bne .poll
    mov a,!level
    cmp a,#!PREFILL
    bcc .poll
    ; Start (or restart) playback at the ring start.
    mov $f2,#$5c : mov $f3,#$00
    mov $f2,#$4c : mov $f3,#$01     ; key on voice 0
    mov a,!HUDSON_TIMERS
    and a,#$ce
    mov $f1,a
    or a,#$01
    mov $f1,a                       ; restart timer 0 with the voice
    mov a,$fd
    mov !state,#1
.poll:
    mov a,$f4
    cmp a,!seq
    beq main
    mov y,a                         ; N = bit 7 of the port value
    bmi release

    ; A chunk starts: the first 3 bytes are already in ports 1-3.
    mov !seq,a
    mov x,#54
    mov y,#0
.triple:
    mov a,$f5 : mov (!ptr)+y,a : inc y
    mov a,$f6 : mov (!ptr)+y,a : inc y
    mov a,$f7 : mov (!ptr)+y,a : inc y
    mov a,!seq
    mov $f4,a                       ; acknowledge
    dec x
    beq .stored
    inc a
    and a,#$7f
    mov !seq,a
.wait:
    cmp a,$f4
    bne .wait
    bra .triple
.stored:
    inc !level
    mov a,!ptr
    clrc
    adc a,#162
    mov !ptr,a
    mov a,!ptr+1
    adc a,#0
    mov !ptr+1,a
    inc !slot
    mov a,!slot
    cmp a,#!CHUNKS
    bne .to_main
    mov !slot,#0
    mov !ptr,#!RING&$ff
    mov !ptr+1,#!RING>>8
    mov a,!LAST_HEADER              ; the chunk just written ends the ring
    or a,#$03
    mov !LAST_HEADER,a
.to_main:
    jmp main

release:
    mov $f2,#$6c : mov $f3,#$60     ; mute, echo writes off
    mov $f2,#$5c : mov $f3,#$01     ; key off the stream voice
    mov y,#0                        ; let the DSP see the key off
-   nop
    dbnz y,-
    mov x,#0
-   mov a,dsp_save_regs+x
    mov $f2,a
    mov a,save_dsp+x
    mov $f3,a
    inc x
    cmp x,#dsp_save_end-dsp_save_regs
    bne -
    mov a,!HUDSON_TIMERS
    and a,#$cf
    mov $f1,a                       ; timer 0 off, Hudson's timers as they were
    mov $f6,#$aa                    ; Hudson's idle outputs ($08C0)
    mov $f7,#$a5
-   mov a,$f4
    cmp a,save_kick
    bne -
    mov $f4,a                       ; the loader's echo of its last kick
    mov x,#7
-   mov a,save_zp+x
    mov $10+x,a
    dec x
    bpl -
    mov $f7,#$aa
    pop y
    pop x
    pop a
    pop p
    ret                             ; = the loader's RET at $1041

; DSP registers the driver changes (restored on release; KOF and FLG last).
dsp_save_regs:
    db $00,$01,$02,$03,$04,$05,$06,$07
    db $0c,$1c,$2c,$3c,$0d,$2d,$3d,$4d,$5d,$5c,$6c
dsp_save_end:
assert dsp_save_end-dsp_save_regs == 19

dsp_init:
    db $6c,$60                      ; FLG: mute, echo writes off
    db $5c,$ff                      ; key off every voice
    db $4d,$00, $2d,$00, $3d,$00    ; EON, PMON, NON
    db $2c,$00, $3c,$00, $0d,$00    ; echo volume, feedback
    db $5d,dir>>8
    db $00,!VOL, $01,!VOL           ; voice 0 volume
    db $02,$00, $03,$08             ; pitch $0800 = 16 kHz
    db $04,$00                      ; source 0
    db $05,$00, $07,$7f             ; GAIN mode, direct full
    db $0c,!MVOL, $1c,!MVOL
dsp_init_end:

save_kick: db 0
save_zp: skip 8
save_dsp: skip 19

assert pc() <= !RING, "stream driver does not fit below the ring"
