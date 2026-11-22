"""MIDI -> song text for tools/sb6/features/sb1_music.py (the format of tools/sb1_song.py's output).

    python tools/midi_song.py [w1m w2m w3m w4m w5m w6m]

`auto` songs (World 1-4 and 6) are fitted to SB1's song (fit()): the MIDI's ticks a row and time offset, per
track (per note in a drum track) the SB1 sample and transpose with the most notes in common; a note SB1 also
plays there takes SB1's exact pitch and volume, a track the sequencer moved a little gets SB1's time back, a
voice the MIDI leaves out is taken from SB1's song, and notes held longer than SB1's are cut where SB1's song
has fewer voices at once (limit_voices). World 5 (w5m) is mapped by hand (MAPS):

Each MIDI track (or drum note) is played by one of SB1's samples of the stage's sound RAM image
(assets/sound/sb1_stage_<image>.bin): MAPS names, per song, the MIDI file, the sample, the semitones between
the MIDI note and the sample's pitch, SB1's volume and ADSR. The pitch of a MIDI note is SB1's own pitch for
that note where SB1's song (`ref`) plays it (same sample, MIDI note + transpose), else the nearest one's
scaled by semitones. Times: 24 units a row (the MIDI's 16th note), `row` ms each (SB1's tempo), loop and end
from the MIDI's "Start" / "End" markers (the part before Start is the intro).
"""
import math
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SOUND = os.path.join(ROOT, "assets", "sound")

# song name -> MIDI, SB1 reference song, ms a row, the instruments of SB1's song kept (srcn: ADSR1 ADSR2 GAIN),
# tracks: MIDI track index -> (srcn, transpose, vol L/R) or {drum note: (srcn, SB1 pitch, vol)}
MAPS = {
    # SB1 World 5 (1-6): "Super Bomberman - Stage 5" sequenced by Joao Buaes (khinsider level.mid); matched to
    # SB1's song note by note (assets/sound/sb1_w5_song.txt): lead = sample 01, bass = 02, the three chord
    # voices and the held note of track 6 = 07, drums = 04 (snare 38 at SB1's low pitch, 40 + 65 its high one)
    "w5m": dict(midi="SB1 midi/level.mid", ref="sb1_w5_song.txt", row=101.875,
                tracks={2: (0x01, -89, 0x26), 1: (0x02, -56, 0x26), 3: (0x07, -72, 0x22), 4: (0x07, -72, 0x22),
                        5: (0x07, -72, 0x22), 6: (0x07, -72, 0x22),
                        7: {38: (0x04, 0x0799, 0x1E), 40: (0x04, 0x0993, 0x1E), 65: None}}),
    # the other World 1 songs: fitted to SB1's (fit(): `auto`), khinsider's MIDIs of SB1's World 1-4 and 6
    "w1m": dict(midi="SB1 midi/level-1-3-.mid", ref="sb1_w1_song.txt", auto=True),
    "w2m": dict(midi="SB1 midi/level-2.mid", ref="sb1_w2_song.txt", auto=True),
    "w3m": dict(midi="SB1 midi/level-3.mid", ref="sb1_w3_song.txt", auto=True),
    "w4m": dict(midi="SB1 midi/level-4.mid", ref="sb1_w4_song.txt", auto=True),
    "w6m": dict(midi="SB1 midi/level-6.mid", ref="sb1_w6_song.txt", auto=True),
    # SB1's boss song (2-8's clown, 1-7): khinsider's boss-battle.mid fitted to SB1's (sb1_boss_song.txt, a DSP
    # log of SB1 2-8 from its song command $8A)
    "bossm": dict(midi="SB1 midi/boss-battle.mid", ref="sb1_boss_song.txt", auto=True),
}
DRUM_NOTES = 6          # a track with at most this many different notes is fitted note by note (drums)
OFFSETS = range(-48, 49)


def read_ref(path):
    """SB1's song: ({srcn: [(row, semitones from $1000, pitch, vl, vr)]}, {"row", "loop", "end"}, inst lines)."""
    notes, meta, inst = {}, {}, {}
    for line in open(path, encoding="utf-8"):
        p = line.split("#")[0].split()
        if not p:
            continue
        if p[0] in ("row", "loop", "end"):
            meta[p[0]] = float(p[1])
        elif p[0] == "inst":
            inst[int(p[1], 16)] = " ".join(p)
        elif p[0].lstrip("-").isdigit():
            pitch = int(p[3], 16)
            notes.setdefault(int(p[2], 16), []).append(
                (int(p[0]) / 24, 12 * math.log2(pitch / 0x1000), pitch, int(p[4], 16), int(p[5], 16)))
    return notes, meta, inst


def fit(m):
    """Fits the MIDI to SB1's song: the MIDI ticks a row (a 32nd, 16th or 8th note), one time offset, and per
    track (per note in a drum track) SB1's sample and transpose with the most notes in common (same row, same
    pitch); a note SB1 also plays there takes SB1's pitch and volume, the others the track's transpose and the
    sample's usual volume. -> (notes [(unit, length, srcn, pitch, vl, vr)], loop unit, end unit, inst lines)."""
    div, tracks, markers = read_midi(os.path.join(ROOT, "assets", m["midi"]))
    ref, meta, inst = read_ref(os.path.join(SOUND, m["ref"]))
    at = {s: {} for s in ref}
    for s, l in ref.items():
        for r, x, pitch, vl, vr in l:
            at[s].setdefault(round(r), []).append((x, pitch, vl, vr))

    def score(ml, s, off):
        cnt = {}
        for r, n in ml:
            for x, *_ in at[s].get(round(r) + off, ()):
                k = round(x - n)
                cnt[k] = cnt.get(k, 0) + 1
        return max(((c, k) for k, c in cnt.items()), default=(0, 0))

    def groups(tpr):
        for k, ns in enumerate(tracks):
            if not ns:
                continue
            keys = sorted({n for _, n, _ in ns})
            if len(keys) <= DRUM_NOTES:
                for n in keys:
                    yield (k, n), [x for x in ns if x[1] == n]
            else:
                yield (k, None), ns

    best = None
    for tpr in (div // 8, div // 4, div // 2):
        for off in OFFSETS:
            tot = sum(max(score([(t / tpr, n) for t, n, _ in g], s, off)[0] for s in ref)
                      for _, g in groups(tpr))
            if best is None or tot > best[0]:
                best = (tot, tpr, off)
    _, tpr, off0 = best
    notes, report, pairs = [], [], []
    chosen = []
    for key, g in groups(tpr):
        ml = [(t / tpr, n) for t, n, _ in g]
        # a track the sequencer moved a little (SB1 World 2's second voice: 2 rows late) keeps SB1's time
        (c, tr), s, off = max(((score(ml, s, o), s, o) for s in ref for o in range(off0 - 4, off0 + 5)),
                              key=lambda x: (x[0][0] - (x[2] != off0) * len(ml) // 4, x[2] == off0))
        chosen.append((key, g, ml, c, tr, s, off))
        pairs.append((s, tr))
    for key, g, ml, c, tr, s, off in chosen:
        vol = max(set((vl, vr) for *_, vl, vr in ref[s]), key=[(vl, vr) for *_, vl, vr in ref[s]].count)
        report.append(f"track {key[0]}{'' if key[1] is None else f' note {key[1]}'}: sample {s:02X} "
                      f"{tr:+d}{'' if off == off0 else f' (moved {off - off0:+d} rows)'}, {c}/{len(g)} notes as SB1's")
        drum_pitch = None
        if key[1] is not None:          # a drum: SB1's pitch it matched most
            hits = [p for r, n in ml for x, p, *_ in at[s].get(round(r) + off, ()) if round(x - n) == tr]
            drum_pitch = max(set(hits), key=hits.count) if hits else pitch_for(s, key[1] + tr, ref_pitches(ref))
        for t, n, d in g:
            r = t / tpr + off
            same = [x for x in at[s].get(round(r), ()) if round(x[0] - n) == tr]
            if not same and key[1] is None:     # SB1 plays this note there with another sample of the song
                for s2, tr2 in pairs:
                    same = [x for x in at[s2].get(round(r), ()) if round(x[0] - n) == tr2]
                    if same:
                        break
            else:
                s2 = s
            if same:
                _, pitch, vl, vr = same[0]
                notes.append((round(r * 24), max(1, round(d * 24 / tpr)), s2, pitch, vl, vr))
                continue
            else:
                pitch = drum_pitch or pitch_for(s, n + tr, ref_pitches(ref))
                vl, vr = vol
            notes.append((round(r * 24), max(1, round(d * 24 / tpr)), s, pitch, vl, vr))
    if "Start" in markers and "End" in markers:
        loop, end = (round((markers[x] / tpr + off0) * 24) for x in ("Start", "End"))
    else:
        loop, end = int(meta["loop"]), int(meta["end"])
    notes = [n for n in notes if n[0] < end]
    # a voice of SB1's song the MIDI leaves out (World 1's sample 00, 4's and 6's 01: under a fifth of its
    # notes in the MIDI): SB1's own notes, as tools/sb1_song.py logged them
    have = {}
    for t, d, s, pitch, *_ in notes:
        have.setdefault(s, set()).add((t, pitch))
    lengths = sb1_lengths(os.path.join(SOUND, m["ref"]))
    for s, l in ref.items():
        mine = [x for x in l if x[0] * 24 < end]
        hit = sum(1 for r, x, pitch, *_ in mine if (round(r * 24), pitch) in have.get(s, ()))
        if mine and hit < len(mine) / 5:
            notes += [(round(r * 24), lengths[(round(r * 24), s, pitch)], s, pitch, vl, vr)
                      for r, x, pitch, vl, vr in mine]
            report.append(f"sample {s:02X}: SB1's {len(mine)} notes (not in the MIDI)")
    notes = limit_voices(notes, os.path.join(SOUND, m["ref"]))
    print(f"{m['midi']}: {tpr} ticks a row, offset {off0} rows; " + "; ".join(report))
    return notes, loop, end, meta["row"], inst


DRUM_SAMPLES = (3, 4, 5)        # one line in sb1_music (DRUMS)


def _poly(ns):
    ev = sorted([(t, 1) for t, d in ns] + [(t + d, -1) for t, d in ns])
    cur = top = 0
    for _, e in ev:
        cur += e
        top = max(top, cur)
    return top


def limit_voices(notes, ref_path):
    """MIDI notes held longer than SB1's overlap more: per sample (SB1's drums together) at most as many at
    once as SB1's song has; a note that would be one too many cuts the one ending first."""
    group = lambda s: -1 if s in DRUM_SAMPLES else s
    cap = {}
    for (t, s, pitch), d in sb1_lengths(ref_path).items():
        cap.setdefault(group(s), []).append((t, d))
    cap = {g: _poly(ns) for g, ns in cap.items()}
    out, active = [], {}
    for n in sorted(notes, key=lambda n: (n[0], -n[3])):
        g = group(n[2])
        act = [x for x in active.get(g, []) if out[x] and out[x][0] + out[x][1] > n[0]]
        if len(act) >= cap.get(g, 1) and all(out[x][0] == n[0] for x in act):
            out.append(None)            # as many starting together already (SB1 World 6's layered snares)
            continue
        while len(act) >= cap.get(g, 1):
            i = min((x for x in act if out[x][0] < n[0]), key=lambda x: out[x][0] + out[x][1])
            out[i] = (out[i][0], max(1, n[0] - out[i][0])) + out[i][2:]
            act.remove(i)
        out.append(n)
        active[g] = act + [len(out) - 1]
    return [n for n in out if n]


def sb1_lengths(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        p = line.split("#")[0].split()
        if p and p[0].lstrip("-").isdigit():
            out[(int(p[0]), int(p[2], 16), int(p[3], 16))] = int(p[1])
    return out


def ref_pitches(ref):
    return {s: {p for _, _, p, _, _ in l} for s, l in ref.items()}


def _vlq(d, i):
    v = 0
    while True:
        b = d[i]
        i += 1
        v = v << 7 | b & 0x7F
        if not b & 0x80:
            return v, i


def read_midi(path):
    """-> (ticks a quarter, [[(start, note, length)] per track], {marker: tick})."""
    d = open(path, "rb").read()
    div = struct.unpack(">H", d[12:14])[0]
    i, tracks, markers = 14, [], {}
    while i < len(d):
        ln = struct.unpack(">I", d[i + 4:i + 8])[0]
        i += 8
        end, t, run, on, notes = i + ln, 0, 0, {}, []
        while i < end:
            dt, i = _vlq(d, i)
            t += dt
            st = d[i]
            if st == 0xFF:
                n, j = _vlq(d, i + 2)
                if d[i + 1] == 6:
                    markers[d[j:j + n].decode("latin-1")] = t
                i = j + n
                continue
            if st in (0xF0, 0xF7):
                n, j = _vlq(d, i + 1)
                i = j + n
                continue
            if st & 0x80:
                run = st
                i += 1
            ty, ch = run & 0xF0, run & 15
            if ty in (0xC0, 0xD0):
                i += 1
                continue
            a, b = d[i], d[i + 1]
            i += 2
            if ty == 0x90 and b:
                on[(ch, a)] = t
            elif ty in (0x80, 0x90) and (ch, a) in on:
                s = on.pop((ch, a))
                notes.append((s, a, t - s))
        tracks.append(sorted(notes))
        i = end
    return div, tracks, markers


def ref_song(path):
    inst, pitches = {}, {}
    for line in open(path, encoding="utf-8"):
        p = line.split("#")[0].split()
        if not p:
            continue
        if p[0] == "inst":
            inst[int(p[1], 16)] = line.split("#")[0].strip()
        elif p[0].lstrip("-").isdigit():
            pitches.setdefault(int(p[2], 16), set()).add(int(p[3], 16))
    return inst, pitches


def pitch_for(srcn, note, pitches):
    """SB1's pitch for semitone `note` of sample srcn: its pitches are numbered round(semitones from $1000 - c),
    c = their common detune (SB1 tunes each sample a fraction of a semitone off)."""
    xs = {p: 12 * math.log2(p / 0x1000) for p in pitches[srcn]}
    c = math.atan2(sum(math.sin(2 * math.pi * x) for x in xs.values()),
                   sum(math.cos(2 * math.pi * x) for x in xs.values())) / (2 * math.pi)
    known = {round(x - c): p for p, x in xs.items()}
    best = min(known, key=lambda k: abs(k - note))
    return round(known[best] * 2 ** ((note - best) / 12))


def convert(name):
    m = MAPS[name]
    if m.get("auto"):
        notes, loop, end, row, inst = fit(m)
        shift = max(0, -min(t for t, *_ in notes))
        used = sorted({x[2] for x in notes})
        out = [f"# {name}: from assets/{m['midi']} by tools/midi_song.py (fitted to {m['ref']}: SB1's samples)"]
        out += [inst[s] for s in used]
        out += [f"row {row}", f"loop {loop + shift}", f"end {end + shift}"]
        for t, d, srcn, pitch, vl, vr in sorted(notes, key=lambda x: (x[0], x[2], -x[3])):
            out.append(f"{t + shift} {d} {srcn:02X} {pitch:04X} {vl:02X} {vr:02X} 0")
        path = os.path.join(SOUND, f"sb1_{name}_song.txt")
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
        print(f"{path}: {len(notes)} notes, samples {used}, loop {loop + shift} end {end + shift}")
        return
    div, tracks, markers = read_midi(os.path.join(ROOT, "assets", m["midi"]))
    inst, pitches = ref_song(os.path.join(SOUND, m["ref"]))
    tick16 = div // 4
    start, loop, end = None, markers["Start"], markers["End"]
    notes = []
    for k, spec in m["tracks"].items():
        for s, n, d in tracks[k]:
            if s >= end:                       # the MIDI writes the loop twice
                continue
            if isinstance(spec, dict):
                x = spec[n]
                if x is None:                  # layered with another drum note
                    continue
                srcn, pitch, vol = x
            else:
                srcn, tr, vol = spec
                pitch = pitch_for(srcn, n + tr, pitches)
            notes.append((s, d, srcn, pitch, vol))
    start = min(s for s, *_ in notes)
    unit = lambda t: (t - start) * 24 // tick16          # 24 units a row
    used = sorted({x[2] for x in notes})
    out = [f"# {name}: from assets/{m['midi']} by tools/midi_song.py (SB1's samples, as {m['ref']})"]
    out += [inst[s] for s in used]
    out += [f"row {m['row']}", f"loop {unit(loop)}", f"end {unit(end)}"]
    for s, d, srcn, pitch, vol in sorted(notes, key=lambda x: (x[0], x[2], -x[3])):
        out.append(f"{unit(s)} {max(1, d * 24 // tick16)} {srcn:02X} {pitch:04X} {vol:02X} {vol:02X} 0")
    path = os.path.join(SOUND, f"sb1_{name}_song.txt")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print(f"{path}: {len(notes)} notes, samples {used}, loop {unit(loop)} end {unit(end)}")


if __name__ == "__main__":
    for name in sys.argv[1:] or MAPS:
        convert(name)
