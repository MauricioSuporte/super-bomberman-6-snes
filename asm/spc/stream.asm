; SB6 streaming driver for the S-SMP (SPC700).
;
; Plays one BRR voice (voice 7) from a ring buffer that the SNES CPU keeps
; filling, so a long recording (the SB6 title music) can play without fitting
; in ARAM, and replays SB5's menu sound effects on voice 0 from DSP-write
; scripts captured from Hudson's driver (tools/capture_sfx.py).
;
; How it runs: the CPU uploads this driver through Hudson's own loader
; (ARAM $0FF0, entered with command $10 on port 1) together with a 3-byte
; block that turns the loader's final RET at $1041 into JMP entry. The driver
; puts the RET back, saves what it changes (zero page $10-$1D, DSP registers,
; timers 0 and 2) and on release restores everything and executes that RET,
; so Hudson's driver continues exactly as after a normal upload.
;
; ARAM use: !BASE .. ring end only (driver !DRIVER_SIZE bytes, then the ring),
; inside the area of SB5's title song, which the game reloads when needed.
; SFX samples stay where Hudson loaded them; their directory entries are
; copied into this driver's directory.
;
; Port protocol (CPU -> SPC):
;   port 0 = sequence number $00-$7F; ports 1-3 = 3 data bytes. The SPC copies
;            the bytes and echoes the sequence on port 0. A chunk is 54
;            consecutive sequences (162 bytes = 18 BRR blocks = 18 ms).
;   port 0 = $80 | toggle << 6 | n, n = 1..31: play SFX slot n (echoed).
;   port 0 = $80: release. The SPC restores Hudson's state, sets port 3 =
;            $A5, waits for port 0 = the loader's last kick value (the CPU
;            first puts ports 1-3 back as the loader left them), then sets
;            port 3 = $AA and returns to Hudson.
; SPC -> CPU while streaming: port 2 = free chunks in the ring, port 3 = $5B.
;
; Defines: BASE (ARAM address, page aligned), DRIVER_SIZE, CHUNKS (ring size
; in chunks), PREFILL (chunks uploaded with the driver), VOL, MVOL, SFX_BIN
; (file: [nsrc][4 Hudson sample numbers][8 script offsets][scripts]; script =
; reg,value pairs, $FE n = wait n * 4 ms, $FF = end).

asar 1.90
arch spc700
norom
org 0
base !BASE

!RING = !BASE+!DRIVER_SIZE
!RING_END = !RING+(!CHUNKS*162)
!LAST_HEADER = !RING_END-9
!SV = $70               ; stream voice (DSP register base)
!SV_BIT = $80
!MAX_SRC = 4

!HUDSON_TIMERS = $1E    ; Hudson's shadow of $F1 (it runs timer 1)
!HUDSON_T2 = $21        ; Hudson's shadow of $FC

; zero page $10-$1D (saved and restored)
!ptr    = $10       ; word: ARAM write pointer of the next chunk
!slot   = $12       ; ring slot of the next chunk
!level  = $13       ; chunks buffered and not yet played
!seq    = $14       ; last port 0 value handled
!state  = $15       ; 0 = buffering (voice off), 1 = playing
!ticks  = $16
!ticks2 = $17
!sfx    = $18       ; word: next SFX script byte
!sfx_wait = $1A     ; 4 ms ticks before the next SFX frame (signed)
!sfx_on = $1B
!p      = $1C       ; word, init only
!ZP_SAVE = 14

dir:
    dw !RING, !RING                 ; sample 0: start and loop = ring start
    skip 4*!MAX_SRC                 ; samples 1..: copies of Hudson's entries

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

    mov x,#!ZP_SAVE-1
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

    ; Directory entries of the SFX samples, from Hudson's directory.
    mov !ticks,#0                   ; i
    mov !ticks2,#4                  ; destination offset in dir
.copy_dir:
    mov a,!ticks
    cmp a,sfx_bin
    beq .dir_done
    mov x,a
    mov a,sfx_bin+1+x
    mov y,#4
    mul ya
    mov !p,a
    mov a,y
    clrc
    adc a,save_dsp                  ; Hudson's DIR (first saved register)
    mov !p+1,a
    mov y,#0
-   mov a,(!p)+y
    mov x,!ticks2
    mov dir+x,a
    inc !ticks2
    inc y
    cmp y,#4
    bne -
    inc !ticks
    bra .copy_dir
.dir_done:

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
    mov !sfx_on,#0
    mov $fa,#144                    ; timer 0: 8 kHz / 144 = one tick per chunk
    mov $fc,#0                      ; timer 2: 64 kHz / 256 = 4 ms (SFX)
    mov a,!HUDSON_TIMERS
    and a,#$ca                      ; timers 0/2 off, no port clear
    mov $f1,a
    or a,#$04
    mov $f1,a                       ; timer 2 on
    mov a,$ff
    mov $f2,#$6c : mov $f3,#$20     ; unmute (echo writes stay off)
    mov $f7,#$5b

main:
    ; ---- SFX frames (timer 2) ----
    mov a,$ff
    mov !ticks2,a
    mov a,!sfx_on
    beq .stream
    mov a,!sfx_wait
    setc
    sbc a,!ticks2
    mov !sfx_wait,a
    beq .sfx_run
    bpl .stream
.sfx_run:
    call sfx_step

.stream:
    mov a,$fd                       ; chunks played since the last read
    mov !ticks,a
    mov a,!state
    beq .report
    mov a,!level
    setc
    sbc a,!ticks
    bcs .keep
    ; Underrun: stop and rebuffer from the ring start.
    mov $f2,#$5c : mov $f3,#!SV_BIT
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
    mov $f2,#$4c : mov $f3,#!SV_BIT ; key on the stream voice
    mov a,!HUDSON_TIMERS
    and a,#$ca
    or a,#$04
    mov $f1,a
    or a,#$01
    mov $f1,a                       ; restart timer 0 with the voice
    mov a,$fd
    mov !state,#1
.poll:
    mov a,$f4
    cmp a,!seq
    beq .to_main
    mov !seq,a
    mov y,a                         ; N = bit 7 of the port value
    bpl .chunk
    and a,#$1f
    bne +
    jmp release
+   mov y,!seq
    mov $f4,y                       ; acknowledge the command
    dec a
    asl a
    mov x,a
    mov a,sfx_bin+1+!MAX_SRC+x
    clrc
    adc a,#sfx_bin&$ff
    mov !sfx,a
    mov a,sfx_bin+2+!MAX_SRC+x
    adc a,#sfx_bin>>8
    mov !sfx+1,a
    mov !sfx_wait,#0
    mov !sfx_on,#1
.to_main:
    jmp main

    ; A chunk starts: the first 3 bytes are already in ports 1-3.
.chunk:
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
    bne .done
    mov !slot,#0
    mov !ptr,#!RING&$ff
    mov !ptr+1,#!RING>>8
    mov a,!LAST_HEADER              ; the chunk just written ends the ring
    or a,#$03
    mov !LAST_HEADER,a
.done:
    jmp main

; Writes SFX frames until the next wait leaves time to spare.
sfx_step:
    mov y,#0
.next:
    mov a,(!sfx)+y
    cmp a,#$fe
    beq .wait
    bcs .end
    mov $f2,a
    inc y
    mov a,(!sfx)+y
    mov $f3,a
    inc y
    bra .next
.wait:
    inc y
    mov a,(!sfx)+y
    clrc
    adc a,!sfx_wait
    mov !sfx_wait,a
    inc y
    mov a,y
    clrc
    adc a,!sfx
    mov !sfx,a
    mov a,!sfx+1
    adc a,#0
    mov !sfx+1,a
    mov a,!sfx_wait
    beq sfx_step
    bmi sfx_step
    ret
.end:
    mov !sfx_on,#0
    ret

release:
    mov $f2,#$6c : mov $f3,#$60     ; mute, echo writes off
    mov $f2,#$5c : mov $f3,#!SV_BIT|$01 ; key off the stream and SFX voices
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
    mov $f1,a                       ; Hudson's timers as they were
    mov $fc,!HUDSON_T2
    mov $f6,#$aa                    ; Hudson's idle outputs ($08C0)
    mov $f7,#$a5
-   mov a,$f4
    cmp a,save_kick
    bne -
    mov $f4,a                       ; the loader's echo of its last kick
    mov x,#!ZP_SAVE-1
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

; DSP registers the driver changes (restored on release; DIR first, KOF and
; FLG last).
dsp_save_regs:
    db $5d
    db $00,$01,$02,$03,$04,$05,$06,$07
    db $70,$71,$72,$73,$74,$75,$76,$77
    db $0c,$1c,$2c,$3c,$0d,$2d,$3d,$4d,$5c,$6c
dsp_save_end:
!DSP_SAVE = 27
assert dsp_save_end-dsp_save_regs == !DSP_SAVE

dsp_init:
    db $6c,$60                      ; FLG: mute, echo writes off
    db $5c,$ff                      ; key off every voice
    db $4d,$00, $2d,$00, $3d,$00    ; EON, PMON, NON
    db $2c,$00, $3c,$00, $0d,$00    ; echo volume, feedback
    db $5d,dir>>8
    db !SV+0,!VOL, !SV+1,!VOL       ; stream voice volume
    db !SV+2,$00, !SV+3,$08         ; pitch $0800 = 16 kHz
    db !SV+4,$00                    ; source 0
    db !SV+5,$00, !SV+7,$7f         ; GAIN mode, direct full
    db $0c,!MVOL, $1c,!MVOL
dsp_init_end:

save_kick: db 0
save_zp: skip !ZP_SAVE
save_dsp: skip !DSP_SAVE

sfx_bin:
    incbin "!SFX_BIN"

assert pc() <= !RING, "stream driver does not fit below the ring"
print "SYM end ", hex(pc())
