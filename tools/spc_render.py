#!/usr/bin/env python3
"""Renders S-DSP voices to a WAV from a Mesen log of DSP writes (research tool).

    python tools/spc_render.py LOG[+LOG2...] ARAM DSP OUT.wav [--voices 0,1|all] [--from C] [--seconds S] [--echo]

LOG lines: "START <spc cycle>" (when ARAM and DSP were dumped), "W <spc cycle>
<dsp reg> <value>" for every S-DSP write and "C <spc cycle> ..." for the sound
request (rendering starts there unless --from is given). ARAM / DSP are the
64 KB / 128-byte dumps taken at START. Only the listed voices are mixed (the
others are the music), dry unless --echo, mono, 32 kHz. Logs of consecutive
runs can be joined with "+" (the ARAM / DSP dumps are those of the first). Used to turn the
Super Bomberman (USA) player / enemy death sounds into WAVs
(tools/mesen/sb1_sfx.lua makes the log).

It follows the S-DSP closely (BRR filters, ADSR/GAIN rates, noise, pitch
modulation) but uses cubic instead of Gaussian interpolation.
"""
import argparse
import struct
import wave

SPC_HZ = 2048000           # Mesen "spc.cycle" rate
RATE = 32000
CYC_PER_SAMPLE = SPC_HZ // RATE
PERIODS = [0, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192, 160, 128, 96, 80,
           64, 48, 40, 32, 24, 20, 16, 12, 10, 8, 6, 5, 4, 3, 2, 1]


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def clamp16(v):
    return max(-32768, min(32767, v))


class Voice:
    def __init__(self, n):
        self.n = n
        self.on = False
        self.env = 0
        self.mode = "release"
        self.addr = 0
        self.loop = 0
        self.buf = [0, 0, 0, 0]
        self.p1 = self.p2 = 0
        self.pos = 0
        self.end = False
        self.out = 0

    def key_on(self, aram, dirb, srcn):
        e = dirb + 4 * srcn
        self.addr = aram[e] | aram[e + 1] << 8
        self.loop = aram[e + 2] | aram[e + 3] << 8
        self.env, self.mode, self.on, self.end = 0, "attack", True, False
        self.buf, self.p1, self.p2, self.pos = [0, 0, 0, 0], 0, 0, 0
        self.block = []

    def decode(self, aram):
        if self.end:
            self.on = False
            self.env = 0
            return [0] * 16
        h = aram[self.addr]
        shift, filt = h >> 4, h >> 2 & 3
        out = []
        for i in range(16):
            b = aram[(self.addr + 1 + i // 2) & 0xFFFF]
            nib = (b >> 4) if i % 2 == 0 else (b & 15)
            nib = nib - 16 if nib & 8 else nib
            s = (nib << shift) >> 1 if shift <= 12 else (-2048 if nib < 0 else 0)
            p1, p2 = self.p1, self.p2 >> 1     # as tools/sb6/brr.py
            if filt == 1:
                s += (p1 >> 1) + ((-p1) >> 5)
            elif filt == 2:
                s += p1 - p2 + (p2 >> 4) + ((p1 * -3) >> 6)
            elif filt == 3:
                s += p1 - p2 + ((p1 * -13) >> 7) + ((p2 * 3) >> 4)
            s = s16(clamp16(s) << 1)
            self.p2, self.p1 = self.p1, s
            out.append(s)
        if h & 1:
            if h & 2:
                self.addr = self.loop
            else:
                self.end = True
        else:
            self.addr = (self.addr + 9) & 0xFFFF
        return out


def render(log, aram, dsp, voices, start=None, seconds=None, echo=False):
    lines = []
    for name in log.split("+"):
        lines += open(name).read().split("\n")
    t0 = next(int(l.split()[1]) for l in lines if l.startswith("START"))
    req = [int(l.split()[1]) for l in lines if l.startswith("C ")]
    writes = []
    for l in lines:
        p = l.split()
        if p and p[0] == "W":
            writes.append(((int(p[1]) - t0) // CYC_PER_SAMPLE, int(p[2], 16), int(p[3], 16)))
    regs = bytearray(dsp)
    aram = bytearray(aram)
    vs = [Voice(n) for n in range(8)]
    first = ((start if start is not None else (req[0] if req else t0)) - t0) // CYC_PER_SAMPLE
    total = writes[-1][0] + RATE if seconds is None else first + int(seconds * RATE)
    noise, counter, wi, out = 0x4000, 0, 0, []
    ebuf, epos, fir_l, fir_r = [0] * 0x10000, 0, [0] * 8, [0] * 8
    for t in range(total):
        while wi < len(writes) and writes[wi][0] <= t:
            _, r, v = writes[wi]
            wi += 1
            regs[r] = v
            if r == 0x4C:
                for n in range(8):
                    if v >> n & 1:
                        vs[n].key_on(aram, regs[0x5D] << 8, regs[n * 16 + 4])
            elif r == 0x5C:
                for n in range(8):
                    if v >> n & 1:
                        vs[n].mode = "release"
        counter = (counter - 1) % 30720
        nr = regs[0x6C] & 31
        if nr and counter % PERIODS[nr] == 0:
            noise = (noise >> 1) | (((noise << 14) ^ (noise << 13)) & 0x4000)
        mix = 0
        mix_l = mix_r = ein_l = ein_r = 0
        prev_out = 0
        for v in vs:
            base = v.n * 16
            if not v.on:
                prev_out = 0
                continue
            pitch = (regs[base + 2] | regs[base + 3] << 8) & 0x3FFF
            if regs[0x2D] >> v.n & 1 and v.n:
                pitch = (pitch + ((prev_out >> 5) * pitch >> 10)) & 0x7FFF
                pitch = min(pitch, 0x3FFF)
            # envelope
            a1, a2, g = regs[base + 5], regs[base + 6], regs[base + 7]
            env = v.env
            if v.mode == "release":
                env -= 8
            elif a1 & 0x80:
                if v.mode == "attack":
                    rate = (a1 & 15) * 2 + 1
                    step = 1024 if rate == 31 else 32
                    if counter % PERIODS[rate] == 0:
                        env += step
                    if env >= 0x7FF:
                        env, v.mode = 0x7FF, "decay"
                elif v.mode == "decay":
                    rate = (a1 >> 4 & 7) * 2 + 16
                    if counter % PERIODS[rate] == 0:
                        env -= ((env - 1) >> 8) + 1
                    if (env >> 8) == (a2 >> 5):
                        v.mode = "sustain"
                else:
                    rate = a2 & 31
                    if rate and counter % PERIODS[rate] == 0:
                        env -= ((env - 1) >> 8) + 1
            elif not g & 0x80:
                env = (g & 0x7F) * 16
            else:
                rate, m = g & 31, g >> 5 & 3
                if rate and counter % PERIODS[rate] == 0:
                    if m == 0:
                        env -= 32
                    elif m == 1:
                        env -= ((env - 1) >> 8) + 1
                    elif m == 2:
                        env += 32
                    else:
                        env += 32 if env < 0x600 else 8
            v.env = max(0, min(0x7FF, env))
            # sample
            while len(v.block) < 4 + (v.pos >> 12):
                v.block += v.decode(aram)
            i, fr = v.pos >> 12, (v.pos & 0xFFF) / 4096.0
            y0, y1, y2, y3 = (v.block[i + k] for k in range(4))
            s = y1 + 0.5 * fr * (y2 - y0 + fr * (2 * y0 - 5 * y1 + 4 * y2 - y3 + fr * (3 * (y1 - y2) + y3 - y0)))
            if regs[0x3D] >> v.n & 1:
                s = s16(noise << 1)
            v.pos += pitch
            drop = (v.pos >> 12) - 1
            if drop > 0:
                v.block = v.block[drop:]
                v.pos -= drop << 12
            o = int(s) * v.env >> 11
            prev_out = o
            if v.n in voices and t >= first:
                vl, vr = s16(regs[base] << 8) >> 8, s16(regs[base + 1] << 8) >> 8
                mix += (o * vl >> 7) + (o * vr >> 7)
                mix_l += o * vl >> 7
                mix_r += o * vr >> 7
                if regs[0x4D] >> v.n & 1:
                    ein_l += o * vl >> 7
                    ein_r += o * vr >> 7
        if echo:
            # echo: ring of EDL * 2 KB at ESA * 256, 8-tap FIR, feedback EFB, output EVOL (stereo samples)
            size = max(1, (regs[0x7D] & 15) * 512)
            base = regs[0x6D] << 6      # ESA * 256 bytes, in stereo samples of 4 bytes
            k = (base + epos) & 0x3FFF
            el, er = ebuf[2 * k], ebuf[2 * k + 1]
            fir_l = fir_l[1:] + [el]
            fir_r = fir_r[1:] + [er]
            fl = fr_ = 0
            for tap in range(8):
                c = s16(regs[tap * 16 + 0x0F] << 8) >> 8
                fl += fir_l[tap] * c >> 6
                fr_ += fir_r[tap] * c >> 6
            fb = s16(regs[0x0D] << 8) >> 8
            if not regs[0x6C] & 0x20:
                ebuf[2 * k] = clamp16(ein_l + (fl * fb >> 7)) & ~1
                ebuf[2 * k + 1] = clamp16(ein_r + (fr_ * fb >> 7)) & ~1
            epos = (epos + 1) % size
            mvl, mvr = s16(regs[0x0C] << 8) >> 8, s16(regs[0x1C] << 8) >> 8
            evl, evr = s16(regs[0x2C] << 8) >> 8, s16(regs[0x3C] << 8) >> 8
            l = (mix_l * mvl >> 7) + (fl * evl >> 7)
            r = (mix_r * mvr >> 7) + (fr_ * evr >> 7)
            if t >= first:
                out.append((l + r) / 2)
        elif t >= first:
            out.append(mix / 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("aram")
    ap.add_argument("dsp")
    ap.add_argument("out")
    ap.add_argument("--voices", default="0,1,2")
    ap.add_argument("--from", dest="start", type=int)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--echo", action="store_true", help="mix the echo (master/echo volumes, FIR, feedback)")
    a = ap.parse_args()
    voices = set(range(8)) if a.voices == "all" else {int(v) for v in a.voices.split(",")}
    out = render(a.log, open(a.aram, "rb").read(), open(a.dsp, "rb").read(), voices, a.start, a.seconds, a.echo)
    # trim trailing silence, normalise to -1 dBFS
    while out and abs(out[-1]) < 1:
        out.pop()
    peak = max(1.0, max(abs(x) for x in out))
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(round(x / peak * 29200))) for x in out))
    print(f"{a.out}: {len(out) / RATE:.3f} s, peak {peak:.0f}")


if __name__ == "__main__":
    main()
