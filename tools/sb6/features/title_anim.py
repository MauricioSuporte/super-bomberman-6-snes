"""Animated title: the Unity title's intro and idle animation as VRAM transfers.

What the Unity scene does (TitleScreenVerticalPanIntro + TitleScreenDropIntro,
values in assets/title/layout.json):
  1. the sky pans from the bottom of the 256x334 picture to its top (2 s);
  2. the seven characters fall in from above, from the middle outwards
     (falling pose, 0.3 s per wave), and land in their standing pose;
  3. the logo drops in (0.25 s) and keeps cycling its 6 frames (0.08 s each);
  4. every 2-4 s each character shows its alternate pose for a while; some
     move 1 px every 0.1 s meanwhile (`alt_steps`: one picture per step).

How it is done on the SNES (Mode 1; code in asm/title_anim.asm, run from the
NMI, one "job" = a few DMAs of at most CHUNK bytes per frame):
  * BG2 (chr $0000, tiles 0-$37F, map 32x64 at $3800): the whole sky for the
    pan (V scroll), then the scene. Characters overlap, so a landing replaces
    the map rows with the picture "sky + characters landed so far"; its tiles
    are sent while the wave is still falling, into slots of the lower sky
    (off screen after the pan).
  * BG1 (chr $6000, the OBJ area: only tiles 0-$17 are the menu cursor; map
    32x64 at $4800): the falling wave (V scroll 256 -> 0), then the logo. The
    logo's frames only differ in colors (a few 4-color ramps moving), so its
    tiles are fixed and LOGO_PALETTES BG palettes are rewritten per frame:
    a palette entry is a color per frame.
  * Alternate poses: the tiles go to one of two scratch areas of BG2 and the
    bounding box of the changed cells is rewritten (and written back after).
    Two poses run at once only when their boxes do not touch. A pose in
    several steps uses both areas (the next step's tiles go to the other
    one while a step is shown) and runs alone.
This module composes the pictures, picks the 8 BG palettes for all of them,
allocates the tile slots and writes the job tables; `simulate()` runs the same
tables on a software VRAM (the build checks every stage against its picture).
"""
import hashlib
import os
import pickle

import numpy as np
from PIL import Image

from ..compose import _alpha_paste, _binary_alpha, character_positions, compose_logo, load_layout
from ..snesgfx import PaletteSlot, W, assign_palettes, cgram_block, to5

CHUNK = 2560            # bytes of DMA per job (80 tiles): ~15 scanlines of vblank
BG2_MAP = 0x3800        # 32x64
BG1_MAP = 0x4800        # 32x64
BG2_SLOTS = 0x380       # tiles 0-$37F = VRAM $0000-$37FF (BG1's old map is tile space now)
BG1_CHR = 0x6000
BG1_FIRST, BG1_END = 0x18, 0x200   # OBJ tiles $00-$17 are the menu cursor
SCRATCH = 2             # alternate poses at once
ALTREC = 8              # bytes per character in the alternate pose table (asm/title_anim.asm !ALTREC)
TEXT_ENTRIES = (1, 2, 3)
FPS = 60
SWAP_FRAMES = 2         # landing: BG2 map, then BG1 map of the next wave
EXACT_LOGO_SEQS = 64    # at most this many color sequences: palettes chosen among them (exact_logo_palettes)
BG_WEIGHT = 4           # title scene palettes: weight of the sky / ground colors around the characters
BG_FIXED = 3            # ... and how many of them every scene palette keeps (assign_weighted)
LOGO_PALETTES = 3       # the last BG palettes: the logo's animated colors
ANIM_WEIGHT = 100         # logo colors that change between frames weigh this much more in the palette fit
CACHE_VERSION = 4


def ease(t):
    """Unity's AnimationCurve.EaseInOut(0, 0, 1, 1)."""
    return 3 * t * t - 2 * t * t * t


def encode_4bpp(idx):
    b = np.packbits(((idx[:, :, None] >> np.arange(4)) & 1).astype(np.uint8), axis=1)[:, 0, :]
    return b[:, :2].tobytes() + b[:, 2:].tobytes()


def decode_4bpp(data):
    a = np.frombuffer(data, np.uint8)
    out = np.zeros((8, 8), np.uint8)
    for p in range(4):
        col = a[(p // 2) * 16 + (p & 1):(p // 2) * 16 + 16:2]
        out |= (np.unpackbits(col[:, None], axis=1) << p).astype(np.uint8)
    return out


def canon(idx):
    """(tile bytes, hflip, vflip): the cell is the tile drawn with those flips."""
    best = None
    for hf in (0, 1):
        for vf in (0, 1):
            t = idx[:, ::-1] if hf else idx
            t = t[::-1] if vf else t
            e = encode_4bpp(t)
            if best is None or e < best[0]:
                best = (e, hf, vf)
    return best


# ---------------------------------------------------------------------------
# pictures
# ---------------------------------------------------------------------------
def snap_logos(logos, asset_dir, files):
    """The resized logo frames with each opaque pixel set to the closest color
    sequence (its colors in the 6 frames) of the original pictures.

    The resize blends neighbors into thousands of sequences, which the two
    animated palettes could only average: the light band running over SUPER and
    BOMBERMAN faded away. The originals use about 30 sequences, which fit."""
    src = np.stack([np.array(Image.open(os.path.join(asset_dir, f)).convert("RGBA")) for f in files])
    ok = (src[..., 3] > 0).all(0)
    seqs = np.unique(src[:, ok, :3].transpose(1, 0, 2).reshape(ok.sum(), -1), axis=0).astype(np.float64)
    st = np.stack([np.array(im.convert("RGBA")) for im in logos])
    op = st[0, ..., 3] > 0
    px = st[:, op, :3].transpose(1, 0, 2).reshape(op.sum(), -1).astype(np.float64)
    best = np.empty(len(px), np.int64)
    for i in range(0, len(px), 4096):
        best[i:i + 4096] = (((px[i:i + 4096, None, :] - seqs[None]) ** 2).sum(-1)).argmin(1)
    out = []
    for k, im in enumerate(logos):
        a = np.array(im.convert("RGBA"))
        a[op, :3] = seqs[best][:, 3 * k:3 * k + 3].astype(np.uint8)
        out.append(Image.fromarray(a, "RGBA"))
    return out


class Pictures:
    def __init__(self, asset_dir):
        self.dir = asset_dir
        self.L = L = load_layout(asset_dir)
        A = L["animation"]
        self.names = [c["name"] for c in L["characters"]]
        self.by_name = {c["name"]: c for c in L["characters"]}
        self.pos = character_positions(L)
        n = len(self.names)
        mid = n // 2
        self.waves = [[mid]] + [[i for i in (mid - d, mid + d) if 0 <= i < n] for d in range(1, mid + 1)]
        self.pan_frames = round(A["pan_seconds"] * FPS)
        self.drop_frames = round(A["characters_drop_seconds"] * FPS)
        self.logo_frames = round(A["logo_drop_seconds"] * FPS)
        self.logo_period = round(A["logo_frame_seconds"] * FPS)
        self.logo_start = A["logo_start_above"]
        self.alt_interval = [round(v * FPS) for v in A["alt_interval_seconds"]]

        sky = Image.open(os.path.join(asset_dir, L["background"]["file"])).convert("RGBA")
        sw, sh = L["screen"]
        self.pan_from = sky.height - sh - L["background"]["crop_top"]
        rows = (sky.height + 7) // 8
        full = Image.new("RGBA", (sw, rows * 8), (0, 0, 0, 255))
        full.paste(sky, (0, 0))
        if rows * 8 > sky.height:  # repeat the last line into the padding
            last = sky.crop((0, sky.height - 1, sw, sky.height))
            for y in range(sky.height, rows * 8):
                full.paste(last, (0, y))
        self.sky = _binary_alpha(full)
        opaque = Image.new("RGBA", self.sky.size, self.sky.getpixel((0, 0))[:3] + (255,))
        self.sky = Image.alpha_composite(opaque, self.sky)
        top = L["background"]["crop_top"]
        self.sky_top = self.sky.crop((0, top, sw, top + sh))
        if top:
            raise ValueError("background.crop_top must be 0 (the pan ends at the top of the picture)")

        clear = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        landed = {}
        self.stages, self.falling = [], []
        for wave in self.waves:
            self.falling.append(self.scene({self.names[i]: "falling" for i in wave}, clear))
            for i in wave:
                landed[self.names[i]] = "file"
            self.stages.append(self.scene(landed, self.sky_top))
        self.final = self.stages[-1]
        self.alts, self.alt_frames = [], []   # per character: a picture and frames per step
        for name in self.names:
            poses = {m: "file" for m in self.names}
            poses[name] = "alt"
            steps, frames = self.steps(name)
            self.alts.append([self.scene(poses, self.sky_top, {name: st}) for st in steps])
            self.alt_frames.append(frames)
        self.logos = []
        for f in L["logo"]["frames"]:
            logo, (lx, ly) = compose_logo(asset_dir, L, f)
            cv = Image.new("RGBA", (sw, (ly + logo.height + 7) // 8 * 8), (0, 0, 0, 0))
            cv.paste(logo, (lx, ly))
            self.logos.append(cv)
        self.logos = snap_logos(self.logos, asset_dir, L["logo"]["frames"])

    def steps(self, name):
        """[(character shift, extra shift)] (Unity: x right, y up) and frames of each step."""
        c = self.by_name[name]
        st = c.get("alt_steps")
        if not st:
            return [((0, 0), (0, 0))], [round(c.get("alt_seconds", 0.5) * FPS)]
        if st["move"] not in ("character", "extra"):
            raise ValueError(f"title: {name}: alt_steps.move must be 'character' or 'extra'")
        n = round(st["seconds"] * FPS)
        out = [(tuple(o), (0, 0)) if st["move"] == "character" else ((0, 0), tuple(o)) for o in st["offsets"]]
        return out, [n] * len(out)

    def sprite(self, name, pose):
        c = self.by_name[name]
        im = Image.open(os.path.join(self.dir, c[pose])).convert("RGBA")
        if im.size != tuple(c["size"]):
            im = im.resize(tuple(c["size"]), Image.NEAREST)
        return _binary_alpha(im)

    def scene(self, poses, base, shift=None):
        """`poses`: {name: "file" | "falling" | "alt"} drawn back to front on `base`;
        `shift`: {name: ((dx, dy), (edx, edy))} added to an alternate pose and its extra."""
        canvas = base.copy()
        for name in self.L["draw_order"]:
            pose = poses.get(name)
            if not pose:
                continue
            c = self.by_name[name]
            x, y = self.pos[name]
            (sx, sy), (ex_, ey_) = (shift or {}).get(name, ((0, 0), (0, 0)))
            if pose == "alt":
                ox, oy = c.get("alt_offset", [0, 0])
                x, y = x + ox + sx, y - oy - sy
            canvas = _alpha_paste(canvas, self.sprite(name, pose), x, y)
            extra = c.get("alt_extra")
            if pose == "alt" and extra:
                # child of the character: anchored at its bottom center, pivot in the middle
                e = _binary_alpha(Image.open(os.path.join(self.dir, extra["file"])).convert("RGBA"))
                w, h = c["size"]
                ex = round(x + w / 2 + extra["offset"][0] + ex_ - e.width / 2)
                ey = round(y + h - extra["offset"][1] - ey_ - e.height / 2)
                canvas = _alpha_paste(canvas, e, ex, ey)
        return canvas


# ---------------------------------------------------------------------------
# palettes: every distinct 8x8 cell of every picture is assigned once
# ---------------------------------------------------------------------------
class Bag:
    name = "u"

    def __init__(self):
        self.ids, self.items = {}, []

    def add(self, px):
        key = px.tobytes()
        if key not in self.ids:
            self.ids[key] = len(self.items)
            self.items.append(px)
        return self.ids[key]

    def cells(self):
        for i, px in enumerate(self.items):
            yield i, 0, px, np.ones(len(px), dtype=bool)


def grid(img):
    rgb, mask = to5(img)
    th, tw = rgb.shape[0] // 8, rgb.shape[1] // 8
    rgb = rgb.reshape(th, 8, tw, 8, 3).transpose(0, 2, 1, 3, 4).reshape(th, tw, 64, 3)
    mask = mask.reshape(th, 8, tw, 8).transpose(0, 2, 1, 3).reshape(th, tw, 64)
    return rgb, mask


def background_colors(P):
    """Sky / ground colors seen in the cells that mix them with a character
    (final scene), most used first."""
    sky = to5(P.sky_top)[0].astype(np.int16)
    fin = to5(P.final)[0].astype(np.int16)
    bg = (sky == fin).all(-1)
    cnt = {}
    for ty in range(bg.shape[0] // 8):
        for tx in range(bg.shape[1] // 8):
            m = bg[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            if m.any() and not m.all():
                for c in sky[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8][m]:
                    cnt[tuple(int(v) for v in c)] = cnt.get(tuple(int(v) for v in c), 0) + 1
    return [list(c) for c, _ in sorted(cnt.items(), key=lambda x: -x[1])]


def assign_weighted(bag, slots, bg_colors, bg_weight, bg_fixed, iterations=25, seed=1, init="mean"):
    """snesgfx.assign_palettes for the title: the colors of the sky / ground seen
    around the characters (`bg_colors`) weigh `bg_weight` times more, and the
    first `bg_fixed` of them are in every palette. A cell mixing a character
    and the sky draws its sky with its own palette: a missing blue shows a
    square around the character."""
    from ..snesgfx import _kmeans_labels
    cells = [px for _, _, px, _ in bag.cells()]
    bgk = {tuple(c) for c in bg_colors}
    fixed = np.array(bg_colors[:bg_fixed], dtype=np.float64).reshape(-1, 3)
    wts = [np.array([bg_weight if tuple(p) in bgk else 1.0 for p in px]) for px in cells]

    def fit(members, mw, cap):
        pix = np.concatenate(members)
        ww = np.concatenate(mw)
        uniq, inv = np.unique(pix, axis=0, return_inverse=True)
        cw = np.bincount(inv.reshape(-1), weights=ww)
        if len(uniq) <= cap:
            return uniq.astype(np.float64)
        keep = [tuple(f) for f in fixed]
        free = [i for i in np.argsort(-cw) if tuple(uniq[i]) not in keep][:cap - len(fixed)]
        c = np.concatenate([fixed, uniq[free].astype(np.float64)])
        u = uniq.astype(np.float64)
        for _ in range(12):
            lab = (((u[:, None, :] - c[None]) ** 2) * W).sum(-1).argmin(1)
            new = c.copy()
            for j in range(len(fixed), len(c)):
                sel = lab == j
                if sel.any():
                    new[j] = (u[sel] * cw[sel, None]).sum(0) / cw[sel].sum()
            if np.allclose(new, c):
                break
            c = new
        return np.clip(np.rint(c), 0, 31)

    def err(i, pal):
        d = (((cells[i][:, None, :].astype(np.float64) - pal[None]) ** 2) * W).sum(-1)
        return (d.min(1) * wts[i]).sum()

    rng = np.random.default_rng(seed)
    k = len(slots)
    means = np.array([c.mean(0) for c in cells])
    if init == "mean":
        lab = _kmeans_labels(means, means[rng.choice(len(means), k, replace=False)])
    else:
        allpx = np.concatenate(cells).astype(np.float64)
        uniq, counts = np.unique(allpx, axis=0, return_counts=True)
        from ..snesgfx import _kmeans
        book = _kmeans(uniq, counts.astype(np.float64), 48,
                       uniq[rng.choice(len(uniq), min(48, len(uniq)), replace=False)])
        feats = []
        for px in cells:
            d = (((px[:, None, :].astype(np.float64) - book[None]) ** 2) * W).sum(-1)
            hh = np.bincount(d.argmin(1), minlength=len(book)).astype(np.float64)
            feats.append(np.sqrt(hh / hh.sum()))
        feats = np.array(feats)
        lab = _kmeans_labels(feats, feats[rng.choice(len(feats), k, replace=False)], weights=None)

    def refit(lab):
        for j, s in enumerate(slots):
            sel = [i for i in range(len(cells)) if lab[i] == j]
            if sel:
                s.colors = fit([cells[i] for i in sel], [wts[i] for i in sel], len(s.free)).astype(np.int16)
    for _ in range(iterations):
        refit(lab)
        new = np.array([int(np.argmin([err(i, s.colors) if len(s.colors) else 1e18 for s in slots]))
                        for i in range(len(cells))])
        if (new == lab).all():
            break
        lab = new
    refit(lab)
    total = sum(err(i, slots[lab[i]].colors) for i in range(len(cells)))
    return {("u", i, 0): slots[lab[i]].index for i in range(len(cells))}, total


def quantize(bag, starts, cache_dir, n_slots, bg_colors=(), bg_weight=1, bg_fixed=0):
    h = hashlib.sha1(repr((CACHE_VERSION, starts, TEXT_ENTRIES, n_slots, list(map(tuple, bg_colors)),
                           bg_weight, bg_fixed)).encode())
    items = [px for _, _, px, _ in bag.cells()]
    for px in items:
        h.update(px.tobytes())
        h.update(b"|")
    path = os.path.join(cache_dir, f"title_palettes_{h.hexdigest()[:16]}.pkl") if cache_dir else None
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)

    def make_slots():
        free0 = [e for e in range(1, 16) if e not in TEXT_ENTRIES]
        return [PaletteSlot(0, free0)] + [PaletteSlot(i, range(1, 16)) for i in range(1, n_slots)]

    best = None
    for seed, init in starts:
        slots = make_slots()
        if bg_weight == 1 and not bg_fixed:
            assignment, err = assign_palettes([bag], slots, seed=seed, init=init)
        else:
            assignment, err = assign_weighted(bag, slots, bg_colors, bg_weight, bg_fixed, seed=seed, init=init)
        if best is None or err < best[2]:
            best = (assignment, slots, err, (seed, init))
    assignment, slots, err, start = best
    res = dict(pal=[assignment[("u", i, 0)] for i in range(len(items))],
               colors=[s.colors for s in slots], free=[list(s.free) for s in slots],
               error=float(err), start=start)
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(res, fh)
    return res


def exact_logo_palettes(px, uniq, wv, n_pal, rng, restarts=24):
    """Palettes made of the logo's own color sequences (no averages): each
    palette is a set of at most 15 of them, each cell takes the palette that
    draws it best (a missing sequence -> the closest one present). Local search
    (swap one sequence) from random starts. Keeps whole animated ramps (the
    pink of SUPER, the orange of BOMBERMAN, the green of 6) instead of merging
    the small ones into still colors."""
    k = len(uniq)
    key = {tuple(u): i for i, u in enumerate(uniq)}
    hist = np.zeros((len(px), k))
    for c, p in enumerate(px):
        for v in p:
            hist[c, key[tuple(v)]] += 1
    dist = (((uniq[:, None, :] - uniq[None]) ** 2) * wv).sum(-1)     # k x k
    size = min(15, k)

    def cell_cost(members):
        return hist @ dist[:, members].min(1)

    def total(pals):
        return np.min([cell_cost(m) for m in pals], axis=0).sum()

    best = None
    for _ in range(restarts):
        pals = [list(rng.choice(k, size, replace=False)) for _ in range(n_pal)]
        cost = total(pals)
        improved = True
        while improved:
            improved = False
            for j in range(n_pal):
                others = np.min([cell_cost(m) for i, m in enumerate(pals) if i != j], axis=0)                     if n_pal > 1 else np.full(len(px), np.inf)
                for slot in range(size):
                    for cand in range(k):
                        if cand in pals[j]:
                            continue
                        trial = pals[j][:slot] + [cand] + pals[j][slot + 1:]
                        c = np.minimum(others, cell_cost(trial)).sum()
                        if c < cost - 1e-9:
                            pals[j], cost, improved = trial, c, True
        if best is None or cost < best[0]:
            best = (cost, [list(m) for m in pals])
    return [uniq[sorted(m)] for m in best[1]]


def logo_palettes(vec, mask, n_pal, seed=1, rounds=12):
    """Animated palettes for the logo.

    `vec`: (th, tw, 64, 3 * frames) 5-bit colors of every pixel in every frame,
    `mask`: (th, tw, 64) opaque. Returns (cells [(tx, ty)], palette of each
    cell, entries (n_pal, 15, 3 * frames), indices per cell (8x8, 0 = clear),
    error)."""
    wv = np.tile(W, vec.shape[-1] // 3)
    cells = [(tx, ty) for ty in range(mask.shape[0]) for tx in range(mask.shape[1]) if mask[ty, tx].any()]
    px = [vec[ty, tx][mask[ty, tx]].astype(np.float64) for tx, ty in cells]
    rng = np.random.default_rng(seed)

    def kmeans(points, weights, k, iters=20):
        c = points[np.argsort(-weights)[:k]].copy()
        for _ in range(iters):
            lab = (((points[:, None, :] - c[None]) ** 2) * wv).sum(-1).argmin(1)
            for j in range(len(c)):
                sel = lab == j
                if sel.any():
                    c[j] = (points[sel] * weights[sel, None]).sum(0) / weights[sel].sum()
        return np.clip(np.rint(c), 0, 31)

    def fit(members):
        uniq, counts = np.unique(np.concatenate(members), axis=0, return_counts=True)
        if len(uniq) <= 15:
            return uniq
        return kmeans(uniq, counts.astype(np.float64), 15)

    def err(p, pal):
        return (((p[:, None, :] - pal[None]) ** 2) * wv).sum(-1).min(1).sum()

    def fit_all(lab):
        return [fit([px[i] for i in range(len(px)) if lab[i] == j] or [px[0]]) for j in range(n_pal)]

    uniq = np.unique(np.concatenate(px), axis=0)
    if len(uniq) <= EXACT_LOGO_SEQS:
        pals = exact_logo_palettes(px, uniq, wv, n_pal, rng)
        lab = np.array([int(np.argmin([err(p, pal) for pal in pals])) for p in px])
    else:
        means = np.array([p.mean(0) for p in px])
        cen = means[rng.choice(len(means), n_pal, replace=False)]
        lab = (((means[:, None, :] - cen[None]) ** 2) * wv).sum(-1).argmin(1)
        for _ in range(rounds):
            pals = fit_all(lab)
            new = np.array([int(np.argmin([err(p, pal) for pal in pals])) for p in px])
            if (new == lab).all():
                break
            lab = new
        pals = fit_all(lab)
    entries = np.zeros((n_pal, 15, vec.shape[-1]))
    for j, pal in enumerate(pals):
        entries[j, :len(pal)] = pal
    idx = []
    total = 0.0
    for (tx, ty), j in zip(cells, lab):
        d = (((vec[ty, tx][:, None, :].astype(np.float64) - pals[j][None]) ** 2) * wv).sum(-1)
        e = d.argmin(1) + 1
        total += d.min(1)[mask[ty, tx]].sum()
        e[~mask[ty, tx]] = 0
        idx.append(e.reshape(8, 8).astype(np.uint8))
    return cells, [int(v) for v in lab], entries.astype(np.int64), idx, total


class Jobs:
    """8-byte records: VRAM word, rows, bytes per row, source (24 bits)."""

    def __init__(self, put):
        self.rec, self.sim, memo = [], [], {}

        def once(data, label):   # equal blobs (a pose's tiles for each scratch area) are stored once
            if data not in memo:
                memo[data] = put(data, label)
            return memo[data]
        self.put = once

    def add(self, vram, data, rows=1, label=""):
        """Returns the job's offset in the table. `data` = rows x equal lengths."""
        per = len(data) // rows
        if per * rows != len(data) or per > CHUNK or per % 2:
            raise ValueError(f"bad job {label}: {len(data)} bytes in {rows} rows")
        addr = self.put(bytes(data), label)
        self.rec.append((vram, rows, per, addr))
        self.sim.append((vram, rows, per, bytes(data)))
        return 8 * (len(self.rec) - 1)

    def chunks(self, vram, data, label):
        """A long run of tile data as jobs of at most CHUNK bytes."""
        addr = self.put(bytes(data), label)
        out = []
        for o in range(0, len(data), CHUNK):
            part = data[o:o + CHUNK]
            self.rec.append((vram + o // 2, 1, len(part), addr + o))
            self.sim.append((vram + o // 2, 1, len(part), bytes(part)))
            out.append(8 * (len(self.rec) - 1))
        return out

    def table(self):
        return b"".join(bytes([v & 0xFF, v >> 8, r, n & 0xFF, n >> 8, a & 0xFF, a >> 8 & 0xFF, a >> 16])
                        for v, r, n, a in self.rec)

    def run(self, vram, off):
        v, rows, per, data = self.sim[off // 8]
        for r in range(rows):
            a = (v + 32 * r) * 2
            vram[a:a + per] = data[r * per:(r + 1) * per]


def words_bytes(words):
    return b"".join(bytes([w & 0xFF, w >> 8]) for w in words)


def build(asset_dir, starts, reserved, put, cache_dir=None):
    """`put(data, label)` stores a blob and returns its SNES address.

    Returns the tables (bytes), the CGRAM words and what `simulate` needs."""
    P = Pictures(asset_dir)
    bag = Bag()

    def register(img):
        rgb, mask = grid(img)
        ids = np.full(mask.shape[:2], -1, dtype=np.int64)
        for ty in range(mask.shape[0]):
            for tx in range(mask.shape[1]):
                m = mask[ty, tx]
                if m.any():
                    # the transparent pixels are part of the cell's identity
                    ids[ty, tx] = bag.add(np.concatenate([rgb[ty, tx][m], np.full((1, 3), -1, np.int16),
                                                          m[:, None].astype(np.int16).repeat(3, 1)]))
        return rgb, mask, ids

    # A cell's entry in the bag carries its mask after a (-1,-1,-1) marker, so
    # equal pixels with different holes stay different cells; the quantizer
    # must only see the colors.
    class ColorBag(Bag):
        def cells(self_inner):
            for i, px in enumerate(bag.items):
                n = int(np.flatnonzero((px == -1).all(1))[0])
                yield i, 0, px[:n], np.ones(n, dtype=bool)
    color_bag = ColorBag()

    sky = register(P.sky)
    stages = [register(im) for im in P.stages]
    alts = [[register(im) for im in steps] for steps in P.alts]
    falls = [register(im) for im in P.falling]
    # logo: fixed tiles, colors per frame
    lg = [grid(im) for im in P.logos]
    lvec = np.concatenate([g[0] for g in lg], axis=-1)
    lcells, lpal, lentries, lidx, lerr = logo_palettes(lvec, lg[0][1], LOGO_PALETTES)
    n_scene = 8 - LOGO_PALETTES

    bg = background_colors(P)
    q = quantize(color_bag, starts, cache_dir, n_scene, bg, BG_WEIGHT, BG_FIXED)
    pal_of = q["pal"]
    colors = [np.asarray(c, dtype=np.float64) for c in q["colors"]]
    free = [np.asarray(f) for f in q["free"]]

    def indices(rgb64, mask64, slot):
        d = (((rgb64[:, None, :].astype(np.float64) - colors[slot][None]) ** 2) * W).sum(-1)
        e = free[slot][d.argmin(1)]
        e[~mask64] = 0
        return e.reshape(8, 8).astype(np.uint8)

    tile_cache = {}

    def cell_tile(layer, ty, tx):
        """(tile bytes, palette, hflip, vflip) of a registered picture's cell; None = empty."""
        rgb, mask, ids = layer
        u = int(ids[ty, tx])
        if u < 0:
            return None
        if u not in tile_cache:
            t, hf, vf = canon(indices(rgb[ty, tx], mask[ty, tx], pal_of[u]))
            tile_cache[u] = (t, pal_of[u], hf, vf)
        return tile_cache[u]

    BLANK = bytes(32)

    # ---- BG2 tile slots ---------------------------------------------------
    def tiles_of(layer, rows=None):
        _, mask, _ = layer
        out = []
        for ty in (rows or range(mask.shape[0])):
            for tx in range(mask.shape[1]):
                out.append(cell_tile(layer, ty, tx)[0])
        return out

    def ordered(seq):
        return list(dict.fromkeys(seq))

    sky_rows = sky[1].shape[0]
    sky_tiles = ordered(tiles_of(sky))
    sky_set = set(sky_tiles)
    stage_tiles = [ordered(tiles_of(s)) for s in stages]
    final_set = set(stage_tiles[-1])
    later = set(tiles_of(sky, range(28)))          # needed after the pan
    for s in stage_tiles:
        later |= set(s)
    in_final = [t for t in sky_tiles if t in final_set and t != BLANK]
    low_only = [t for t in sky_tiles if t not in later and t != BLANK]
    top_other = [t for t in sky_tiles if t in later and t not in final_set and t != BLANK]
    slot = {BLANK: 0}
    for t in in_final + low_only + top_other:
        slot[t] = len(slot)
    n_sky = len(slot)
    if n_sky > BG2_SLOTS:
        raise ValueError(f"title: the sky needs {n_sky} tiles, BG2 has {BG2_SLOTS}")
    # free after the pan: the lower sky's slots, then the ones past the sky
    pool = [slot[t] for t in low_only] + list(range(n_sky, BG2_SLOTS))
    stage_new = []   # per stage: [(slot, tile)] sent before its landing
    first = {}
    for s, tl in enumerate(stage_tiles):
        for t in tl:
            if t not in sky_set:
                first.setdefault(t, s)
    new_final = [t for t in stage_tiles[-1] if t not in sky_set]
    new_final.sort(key=lambda t: first[t])           # stable: one run per stage
    transient = [t for t in first if t not in final_set]
    transient.sort(key=lambda t: first[t])
    if len(new_final) + len(transient) > len(pool):
        raise ValueError(f"title: {len(new_final) + len(transient)} scene tiles, {len(pool)} slots free after the pan")
    for t in new_final + transient:
        slot[t] = pool.pop(0)
    for s in range(len(stages)):
        stage_new.append(sorted((slot[t], t) for t in new_final + transient if first[t] == s))
    final_hi = 1 + max(slot[t] for t in final_set)

    def bg2_words(layer, rows, lookup=slot):
        out = []
        for ty in rows:
            for tx in range(32):
                t, pal, hf, vf = cell_tile(layer, ty, tx)
                out.append(lookup[t] | pal << 10 | hf << 14 | vf << 15)
        return out

    # ---- alternate poses --------------------------------------------------
    final_words = bg2_words(stages[-1], range(28))
    alt_info = []
    for c, layers in enumerate(alts):
        steps, cells = [], set()
        for layer in layers:
            tl = tiles_of(layer, range(28))
            new = ordered(t for t in tl if t not in final_set)
            look = dict(slot)
            for j, t in enumerate(new):
                look[t] = ("scratch", j)
            for ty in range(28):
                for tx in range(32):
                    if cell_tile(layer, ty, tx) != cell_tile(stages[-1], ty, tx):
                        cells.add((tx, ty))
            steps.append(dict(new=new, look=look, layer=layer))
        if not cells:
            raise ValueError(f"title: {P.names[c]}'s alternate pose changes nothing")
        x0, x1 = min(x for x, _ in cells), max(x for x, _ in cells)   # the box of every step
        y0, y1 = min(y for _, y in cells), max(y for _, y in cells)
        if (x1 - x0 + 1) % 2:      # keep rows an even number of words (not required, tidy DMAs)
            x1 = x1 + 1 if x1 < 31 else x1
        alt_info.append(dict(steps=steps, box=(x0, y0, x1, y1), frames=P.alt_frames[c], multi=len(steps) > 1))
    scr_size = max(len(st["new"]) for a in alt_info for st in a["steps"])
    scr_base = [final_hi + i * scr_size for i in range(SCRATCH)]
    if final_hi + SCRATCH * scr_size > BG2_SLOTS:
        raise ValueError(f"title: no room for {SCRATCH} alternate poses of {scr_size} tiles after tile {final_hi}")

    # ---- BG1 tile slots ---------------------------------------------------
    n_logo = len(lcells)
    b1_blank = BG1_FIRST
    logo_base = BG1_FIRST + 1
    w_base = logo_base + n_logo
    w_room = (BG1_END - w_base) // 2
    wave_region = [(w_base, w_room), (w_base + w_room, w_room)]  # even waves, odd waves
    blank_word = b1_blank
    logo_tiles = b"".join(encode_4bpp(i) for i in lidx)
    logo_rows = lg[0][1].shape[0]

    def logo_map(rows):
        words = [blank_word] * (32 * rows)
        for j, (tx, ty) in enumerate(lcells):
            words[ty * 32 + tx] = (logo_base + j) | (n_scene + lpal[j]) << 10
        return words

    wave_data = []
    for k, layer in enumerate(falls):
        base, room = wave_region[k % 2]
        tiles, words = {}, []
        for ty in range(28):
            for tx in range(32):
                c = cell_tile(layer, ty, tx)
                if c is None:
                    words.append(blank_word)
                    continue
                t, pal, hf, vf = c
                n = tiles.setdefault(t, len(tiles))
                words.append((base + n) | pal << 10 | hf << 14 | vf << 15)
        if len(tiles) > room:
            raise ValueError(f"title: wave {k} needs {len(tiles)} tiles, its BG1 area has {room}")
        wave_data.append((base, b"".join(tiles), words))

    # ---- jobs -------------------------------------------------------------
    J = Jobs(put)
    b1 = lambda n: BG1_CHR + 16 * n
    sky_image = bytearray(32 * n_sky)
    for t in sky_tiles:
        sky_image[32 * slot[t]:32 * slot[t] + 32] = t
    sky_map = bg2_words(sky, range(sky_rows)) + [0] * (32 * (64 - sky_rows))
    logo_a = bytes(32) + logo_tiles
    empty_rows = [blank_word] * (32 * 36)

    init_a = J.chunks(0x0000, sky_image, "title: sky tiles (pan)")
    keep = 32 * (1 + len(in_final))    # blank + the sky tiles still seen behind the characters
    init_b = [j for j in init_a if J.rec[j // 8][0] * 2 < keep]
    init_a += J.chunks(BG2_MAP, words_bytes(sky_map), "title: BG2 map, sky 32x64")
    logo_jobs = J.chunks(b1(b1_blank), logo_a, "title: BG1 blank tile + logo tiles")
    empty_jobs = J.chunks(BG1_MAP + 32 * 28, words_bytes(empty_rows), "title: BG1 map, empty rows 28-63")
    init_a += logo_jobs + empty_jobs
    init_a += J.chunks(b1(wave_data[0][0]), wave_data[0][1], "title: falling wave 1 tiles")
    init_a += J.chunks(BG1_MAP, words_bytes(wave_data[0][2]), "title: BG1 map, wave 1")
    logo_map_job = J.add(BG1_MAP, words_bytes(logo_map(28)), label="title: BG1 map, logo")

    def runs(pairs):
        out = []
        for s, t in pairs:
            if out and out[-1][0] + len(out[-1][1]) // 32 == s:
                out[-1][1] += t
            else:
                out.append([s, bytearray(t)])
        return out

    hidden = 255                       # BG1 V scroll 256 (-1): rows 32-63, empty
    rest = 0x3FF                       # V scroll -1: screen line 1 = map line 0
    frames = []                        # [bg1v, bg2v, job]
    for f in range(P.pan_frames):
        frames.append([hidden, (P.pan_from - int(P.pan_from * ease((f + 1) / P.pan_frames)) - 1) & 0x3FF, None])
    flexible = []                      # (first frame, last frame, job)
    for k in range(len(P.waves)):
        t0 = len(frames)
        for i in range(P.drop_frames):
            frames.append([(round(256 * (1 - ease((i + 1) / P.drop_frames))) - 1) & 0x3FF, rest, None])
        first_row = min(ty for ty in range(28) for tx in range(32)
                        if cell_tile(stages[k], ty, tx) != cell_tile(sky, ty, tx))
        frames.append([hidden, rest, J.add(BG2_MAP + 32 * first_row,
                                           words_bytes(bg2_words(stages[k], range(first_row, 28))),
                                           label=f"title: BG2 rows, wave {k + 1} landed")])
        if k + 1 < len(P.waves):
            nxt = J.add(BG1_MAP, words_bytes(wave_data[k + 1][2]), label=f"title: BG1 map, wave {k + 2}")
        else:
            nxt = logo_map_job
        frames.append([hidden, rest, nxt])
        for s, data in runs(stage_new[k]):
            for j in J.chunks(16 * s, data, f"title: scene tiles of wave {k + 1}"):
                flexible.append((t0, t0 + P.drop_frames - 1, j))
                init_b.append(j)
        if k + 1 == len(P.waves):       # the last landing's rows end the scene loaded without the intro
            first_all = min(J.rec[f[2] // 8][0] for f in frames[P.pan_frames:] if f[2] is not None
                            and BG2_MAP <= J.rec[f[2] // 8][0] < BG2_MAP + 0x800)
            if first_all != J.rec[frames[-2][2] // 8][0]:
                raise ValueError("title: the last landing must rewrite every row an earlier one changed")
            init_b.append(J.add(BG2_MAP, words_bytes(bg2_words(sky, range(first_row))),
                                label="title: BG2 rows above the characters (no intro)"))
            init_b.append(frames[-2][2])
            init_b += logo_jobs + empty_jobs + [logo_map_job]
        if k + 1 < len(P.waves):
            base, data, _ = wave_data[k + 1]
            for j in J.chunks(b1(base), data, f"title: falling wave {k + 2} tiles"):
                flexible.append((t0, t0 + P.drop_frames - 1, j))
    for a, b, j in flexible:
        f = next((f for f in range(a, b + 1) if frames[f][2] is None), None)
        if f is None:
            raise ValueError("title: too many transfers for one wave; raise CHUNK or slow the drop")
        frames[f][2] = j
    play = b"".join(bytes([a & 0xFF, a >> 8, b & 0xFF, b >> 8]) + (b"\xFF\xFF" if j is None else bytes([j & 0xFF, j >> 8]))
                    for a, b, j in frames) + b"\x00\x00\x00\x00\xFE\xFF"

    drop = [(round(P.logo_start * (1 - ease((i + 1) / P.logo_frames))) - 1) & 0x3FF for i in range(P.logo_frames)]

    # colors of the logo palettes in every frame (entry 0 of each included: one DMA)
    n_frames = len(P.logos)
    logo_cg = []
    for k in range(n_frames):
        words = []
        for p in range(LOGO_PALETTES):
            words.append(0)
            for e in range(15):
                r, g, b_ = (int(v) for v in lentries[p, e, 3 * k:3 * k + 3])
                words.append(r | g << 5 | b_ << 10)
        logo_cg.append(words)

    # !ALT: per character (ALTREC bytes) conflicts, 1 = steps in both areas, restore
    # job, step list starting in area 0 / area 1; then the step lists: tile job,
    # tile job, cells job ($FFFF = none), frames, 0; frames 0 ends a list.
    heads, lists = bytearray(), bytearray()
    list_base = ALTREC * len(alt_info)
    for c, a in enumerate(alt_info):
        x0, y0, x1, y1 = a["box"]
        conf = 0
        for d, o in enumerate(alt_info):
            ox0, oy0, ox1, oy1 = o["box"]
            if not (ox1 < x0 or x1 < ox0 or oy1 < y0 or y1 < oy0):
                conf |= 1 << d
        vram = BG2_MAP + 32 * y0 + x0
        back = [final_words[ty * 32 + tx] for ty in range(y0, y1 + 1) for tx in range(x0, x1 + 1)]
        restore = J.add(vram, words_bytes(back), rows=y1 - y0 + 1, label=f"title: {P.names[c]} standing again")
        ptrs = []
        for s0 in ((0,) if a["multi"] else range(SCRATCH)):
            ptrs.append(list_base + len(lists))
            for k, (st, fr) in enumerate(zip(a["steps"], a["frames"])):
                if not 0 < fr < 256:
                    raise ValueError(f"title: {P.names[c]}'s alternate step {k} lasts {fr} frames (1-255)")
                s = (s0 + k) % SCRATCH
                look = {t: (scr_base[s] + v[1] if isinstance(v, tuple) else v) for t, v in st["look"].items()}
                js = J.chunks(16 * scr_base[s], b"".join(st["new"]),
                              f"title: {P.names[c]} alternate pose {k} tiles (scratch {s})") if st["new"] else []
                if len(js) > 2:
                    raise ValueError("title: an alternate pose must fit two jobs")
                js += [0xFFFF] * (2 - len(js))
                words = [w_ for ty in range(y0, y1 + 1)
                         for w_ in bg2_words(st["layer"], [ty], look)[x0:x1 + 1]]
                js.append(J.add(vram, words_bytes(words), rows=y1 - y0 + 1,
                                label=f"title: {P.names[c]} alternate pose {k} cells (scratch {s})"))
                lists += words_bytes(js) + bytes([fr, 0])
            lists += bytes(8)
        ptrs += ptrs[:1] * (2 - len(ptrs))
        heads += bytes([conf, int(a["multi"])]) + words_bytes([restore] + ptrs)
        a["conf"] = conf
    alt_table = heads + lists
    if len(alt_table) > 0x10000:
        raise ValueError("title: the alternate pose table passes 64 KB")

    def wlist(v):
        return b"".join(bytes([x & 0xFF, x >> 8]) for x in v)

    cg = cgram_block([type("S", (), dict(colors=np.asarray(c), free=f, index=i))()
                      for i, (c, f) in enumerate(zip(q["colors"], q["free"]))], reserved)
    cg[16 * n_scene:] = logo_cg[0]
    return dict(
        P=P, jobs=J, cgram=cg, error=q["error"], logo_error=lerr, start=q["start"],
        tables=dict(jobs=J.table(), init_a=wlist(init_a + [0xFFFF]), init_b=wlist(init_b + [0xFFFF]), play=play,
                    drop=wlist(drop), logocg=b"".join(wlist(w_) for w_ in logo_cg), alt=bytes(alt_table)),
        lists=dict(init_a=init_a, init_b=init_b, frames=frames, drop=drop, logo_cg=logo_cg, alts=alt_info),
        consts=dict(NDROP=len(drop), NLOGO=n_frames, NCHAR=len(P.names), PERIOD=P.logo_period,
                    ALTMIN=P.alt_interval[0], ALTSPAN=P.alt_interval[1] - P.alt_interval[0],
                    CGFIRST=16 * n_scene, CGLEN=32 * LOGO_PALETTES),
        stats=dict(sky=n_sky, scene=final_hi, scratch=scr_size, logo=n_logo, waves=[len(w[1]) // 32 for w in wave_data],
                   jobs=len(J.rec), frames=len(frames), rest=rest),
        quant=dict(colors=colors, free=free, pal_of=pal_of, stages=stages, alts=alts, sky=sky),
    )


# ---------------------------------------------------------------------------
# software VRAM: runs the tables like asm/title_anim.asm does
# ---------------------------------------------------------------------------
def render(vram, cgram, bg1v, bg2v, layers=(2, 1)):
    """256x224 RGB picture of BG2 and BG1 (line 1 of the screen = map line V + 1)."""
    pal = np.array([[(c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31] for c in cgram],
                   dtype=np.uint8)
    out = np.zeros((224, 256, 3), dtype=np.uint8)
    out[:] = pal[0]
    v16 = np.frombuffer(bytes(vram), dtype="<u2")
    for layer in layers:
        mp, chr_, v = (BG2_MAP, 0, bg2v) if layer == 2 else (BG1_MAP, BG1_CHR, bg1v)
        lines = [(y + 1 + v) & 511 for y in range(224)]
        cache = {}
        for row in sorted({ln >> 3 for ln in lines}):
            for tx in range(32):
                w = int(v16[mp + row * 32 + tx])
                key = (w & 0x3FF)
                if key not in cache:
                    a = (chr_ + 16 * key) * 2
                    cache[key] = decode_4bpp(bytes(vram[a:a + 32]))
                t = cache[key]
                if w & 0x4000:
                    t = t[:, ::-1]
                if w & 0x8000:
                    t = t[::-1]
                ys = [y for y, ln in enumerate(lines) if ln >> 3 == row]
                sub = t[[lines[y] & 7 for y in ys]]
                col = pal[(w >> 10 & 7) * 16 + sub]
                m = sub != 0
                blk = out[ys[0]:ys[-1] + 1, tx * 8:tx * 8 + 8]
                blk[m] = col[m]
    return out


def expected(res, layer):
    """The picture a registered layer should give with the chosen palettes (RGB, 5-bit expanded)."""
    rgb, mask, ids = layer
    q = res["quant"]
    th, tw = mask.shape[:2]
    out = np.zeros((th * 8, tw * 8, 3), dtype=np.uint8)
    for ty in range(th):
        for tx in range(tw):
            u = int(ids[ty, tx])
            s = q["pal_of"][u]
            d = (((rgb[ty, tx][:, None, :].astype(np.float64) - q["colors"][s][None]) ** 2) * W).sum(-1)
            col = np.asarray(q["colors"][s])[d.argmin(1)].astype(np.int64) * 255 // 31
            out[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = col.reshape(8, 8, 3)
    return out


def simulate(res, out_png=None):
    """Runs both openings and every alternate pose; raises if a stage is drawn wrong.

    Returns the frames of the preview strip (and saves it)."""
    J, L, cg = res["jobs"], res["lists"], res["cgram"]
    P = res["P"]
    q = res["quant"]
    shots = []
    vram = bytearray(0x10000)
    for j in L["init_a"]:
        J.run(vram, j)
    landing = [i for i, f in enumerate(L["frames"]) if f[2] is not None and i >= P.pan_frames
               and J.rec[f[2] // 8][0] >= BG2_MAP and J.rec[f[2] // 8][0] < BG2_MAP + 0x800]
    stage = 0
    want = {0, P.pan_frames // 2, P.pan_frames - 1}
    for k in range(len(P.waves)):
        t0 = P.pan_frames + k * (P.drop_frames + SWAP_FRAMES)
        want |= {t0 + P.drop_frames // 2, t0 + P.drop_frames - 1}
    for i, (b1v, b2v, job) in enumerate(L["frames"]):
        if job is not None:
            J.run(vram, job)
        if i in landing:
            got = render(vram, cg, 255, b2v, layers=(2,))
            if not (got == expected(res, q["stages"][stage])).all():
                raise ValueError(f"title: stage {stage} is not drawn as composed (frame {i})")
            stage += 1
        if i in want:
            shots.append(render(vram, cg, b1v, b2v))
    for i, v in enumerate(L["drop"]):
        if i in (len(L["drop"]) // 2, len(L["drop"]) - 1):
            shots.append(render(vram, cg, v, res["stats"]["rest"]))
    after_intro = bytes(vram)
    # the same screen without the intro
    v2 = bytearray(0x10000)
    for j in L["init_b"]:
        J.run(v2, j)
    rest = res["stats"]["rest"]
    a, b = render(vram, cg, rest, rest), render(v2, cg, rest, rest)
    if not (a == b).all():
        raise ValueError("title: the screen after the intro differs from the one loaded without it")
    # logo frames: colors only
    cg_first = res["consts"]["CGFIRST"]
    for k in (2, 4):
        cgk = list(cg)
        cgk[cg_first:] = L["logo_cg"][k]
        shots.append(render(v2, cgk, rest, rest))
    # alternate poses, each in each scratch area it may start in, step by step:
    # the next step's tiles must not change the step on screen
    tab = res["tables"]["alt"]
    n = res["consts"]["NCHAR"]

    def w(o):
        return tab[o] | tab[o + 1] << 8

    for c in range(n):
        h = ALTREC * c
        for s in ((0,) if tab[h + 1] else range(SCRATCH)):
            p, k, shown = w(h + 4 + 2 * s), 0, None
            while tab[p + 6]:
                for part in range(2):
                    if w(p + 2 * part) != 0xFFFF:
                        J.run(v2, w(p + 2 * part))
                if shown is not None and not (render(v2, cg, rest, rest, layers=(2,)) == shown).all():
                    raise ValueError(f"title: alternate pose {c} step {k}'s tiles change the step shown")
                J.run(v2, w(p + 4))
                shown = expected(res, q["alts"][c][k])
                if not (render(v2, cg, rest, rest, layers=(2,)) == shown).all():
                    raise ValueError(f"title: alternate pose {c} step {k} (scratch {s}) is not drawn as composed")
                if s == 0 and k in (0, len(q["alts"][c]) // 2):
                    shots.append(render(v2, cg, rest, rest))
                p, k = p + 8, k + 1
            if k != len(q["alts"][c]):
                raise ValueError(f"title: alternate pose {c} lists {k} steps")
            J.run(v2, w(h + 2))
            if not (render(v2, cg, rest, rest) == b).all():
                raise ValueError(f"title: alternate pose {c} does not restore the scene")
    if out_png:
        cols = 6
        rows = (len(shots) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 258, rows * 226), (40, 40, 40))
        for i, s in enumerate(shots):
            sheet.paste(Image.fromarray(s, "RGB"), (i % cols * 258 + 1, i // cols * 226 + 1))
        sheet.save(out_png)
    return shots, after_intro
