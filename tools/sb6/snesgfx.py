"""SNES 4bpp background conversion: per-tile palette assignment + tile dedup.

Several layers (e.g. BG1 logo + BG2 background) can share one VRAM tile area
and one set of 8 BG palettes. Each palette has 16 entries; entry 0 is
transparent. Palette slots can reserve entries (e.g. palette 0 entries 1-3 are
taken by the BG3 text colors in Mode 1), which the quantizer never uses.
"""
import numpy as np
from PIL import Image

# Perceptual-ish weights for squared RGB distance (5-bit channels).
W = np.array([3.0, 4.0, 2.0])


def to5(img):
    """RGBA PIL image -> (H,W,3) uint8 5-bit colors and (H,W) bool opaque mask."""
    a = np.asarray(img.convert("RGBA"), dtype=np.int32)
    rgb = (a[..., :3] * 31 + 127) // 255
    return rgb.astype(np.int16), a[..., 3] >= 128


def bgr555(c):
    r, g, b = (int(v) for v in c)
    return r | g << 5 | b << 10


class Layer:
    """An image split in 8x8 cells. Cells that are fully transparent stay empty."""

    def __init__(self, name, img, opaque_required):
        if img.width % 8 or img.height % 8:
            raise ValueError(f"{name}: size must be a multiple of 8")
        self.name = name
        self.rgb, self.mask = to5(img)
        if opaque_required and not self.mask.all():
            raise ValueError(f"{name}: background layer must be fully opaque")
        self.tw, self.th = img.width // 8, img.height // 8

    def cells(self):
        for ty in range(self.th):
            for tx in range(self.tw):
                sl = (slice(ty * 8, ty * 8 + 8), slice(tx * 8, tx * 8 + 8))
                yield tx, ty, self.rgb[sl].reshape(64, 3), self.mask[sl].reshape(64)


def _kmeans(pixels, weights, k, init, iters=12):
    """Weighted k-means in 5-bit RGB space. Returns integer centers."""
    centers = init.astype(np.float64)
    for _ in range(iters):
        d = (((pixels[:, None, :] - centers[None, :, :]) ** 2) * W).sum(-1)
        lab = d.argmin(1)
        new = centers.copy()
        for j in range(len(centers)):
            sel = lab == j
            if sel.any():
                new[j] = (pixels[sel] * weights[sel, None]).sum(0) / weights[sel].sum()
        if np.allclose(new, centers):
            break
        centers = new
    return np.clip(np.rint(centers), 0, 31).astype(np.int16)


def _fit_palette(pixels, capacity):
    """Best `capacity` colors for a pixel list: exact when few enough colors."""
    uniq, counts = np.unique(pixels, axis=0, return_counts=True)
    if len(uniq) <= capacity:
        return uniq.astype(np.int16)
    order = np.argsort(-counts)
    init = uniq[order[:capacity]]
    return _kmeans(uniq.astype(np.float64), counts.astype(np.float64), capacity, init)


def _tile_error(px, pal):
    d = (((px[:, None, :].astype(np.float64) - pal[None, :, :]) ** 2) * W).sum(-1)
    return d.min(1).sum()


class PaletteSlot:
    def __init__(self, index, free_entries):
        self.index = index
        self.free = list(free_entries)  # CGRAM entries (1..15) this slot may use
        self.colors = np.zeros((0, 3), dtype=np.int16)


def assign_palettes(layers, slots, iterations=25, seed=1, init="mean"):
    """Assigns every non-empty cell to one of `slots`, refining palette colors.

    Returns ({(layer_name, tx, ty): slot_index}, total_error). The result is
    deterministic for a given (seed, init).
    """
    cells = []
    for layer in layers:
        for tx, ty, px, m in layer.cells():
            if m.any():
                cells.append(((layer.name, tx, ty), px[m]))
    rng = np.random.default_rng(seed)
    k = len(slots)
    if init == "mean":
        # Initial split: k-means on each cell's mean color.
        means = np.array([c[1].mean(0) for c in cells])
        lab = _kmeans_labels(means, means[rng.choice(len(means), k, replace=False)])
    else:
        # Initial split: k-means on each cell's color histogram over a global
        # 48-color codebook, so cells that use the same colors end up together.
        allpx = np.concatenate([c[1] for c in cells]).astype(np.float64)
        uniq, counts = np.unique(allpx, axis=0, return_counts=True)
        book = _kmeans(uniq, counts.astype(np.float64), 48,
                       uniq[rng.choice(len(uniq), min(48, len(uniq)), replace=False)])
        feats = []
        for _, px in cells:
            d = (((px[:, None, :].astype(np.float64) - book[None]) ** 2) * W).sum(-1)
            h = np.bincount(d.argmin(1), minlength=len(book)).astype(np.float64)
            feats.append(np.sqrt(h / h.sum()))
        feats = np.array(feats)
        lab = _kmeans_labels(feats, feats[rng.choice(len(feats), k, replace=False)], weights=None)
    for _ in range(iterations):
        for j, slot in enumerate(slots):
            members = [cells[i][1] for i in range(len(cells)) if lab[i] == j]
            if members:
                slot.colors = _fit_palette(np.concatenate(members), len(slot.free))
        new = np.array([
            int(np.argmin([_tile_error(px, s.colors) if len(s.colors) else 1e18 for s in slots]))
            for _, px in cells
        ])
        if (new == lab).all():
            break
        lab = new
    for j, slot in enumerate(slots):
        members = [cells[i][1] for i in range(len(cells)) if lab[i] == j]
        if members:
            slot.colors = _fit_palette(np.concatenate(members), len(slot.free))
    total = sum(_tile_error(px, slots[lab[i]].colors) for i, (_, px) in enumerate(cells))
    return {cells[i][0]: slots[lab[i]].index for i in range(len(cells))}, total


def best_palettes(layers, make_slots, starts):
    """Runs assign_palettes for each (seed, init) start and keeps the best.

    Returns (assignment, slots, error, (seed, init))."""
    best = None
    for seed, init in starts:
        slots = make_slots()
        assignment, err = assign_palettes(layers, slots, seed=seed, init=init)
        if best is None or err < best[2]:
            best = (assignment, slots, err, (seed, init))
    return best


def _kmeans_labels(points, init, iters=20, weights=W):
    c = init.astype(np.float64)
    w = 1.0 if weights is None else weights
    for _ in range(iters):
        d = (((points[:, None, :] - c[None]) ** 2) * w).sum(-1)
        lab = d.argmin(1)
        for j in range(len(c)):
            if (lab == j).any():
                c[j] = points[lab == j].mean(0)
    return lab


def encode_4bpp(idx8x8):
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = int(idx8x8[y][x])
            bit = 0x80 >> x
            for p in range(4):
                if v >> p & 1:
                    out[(p // 2) * 16 + y * 2 + (p & 1)] |= bit
    return bytes(out)


class TileSet:
    """Deduplicated 4bpp tiles with H/V flip matching. Tile 0 is blank."""

    def __init__(self):
        self.tiles = [bytes(32)]
        self.lookup = {bytes(32): (0, False, False)}

    def add(self, idx):
        idx = np.asarray(idx)
        for hf in (False, True):
            for vf in (False, True):
                t = idx[:, ::-1] if hf else idx
                t = t[::-1, :] if vf else t
                key = encode_4bpp(t)
                if key in self.lookup:
                    n, h0, v0 = self.lookup[key]
                    return n, h0 ^ hf, v0 ^ vf
        n = len(self.tiles)
        enc = encode_4bpp(idx)
        self.tiles.append(enc)
        self.lookup[enc] = (n, False, False)
        return n, False, False

    def data(self):
        return b"".join(self.tiles)


def build_layer_map(layer, assignment, slots_by_index, tileset, priority=False):
    """Returns tilemap words (row-major, layer.tw x layer.th) and the preview."""
    words = []
    preview = np.zeros((layer.th * 8, layer.tw * 8, 4), dtype=np.uint8)
    for tx, ty, px, m in layer.cells():
        key = (layer.name, tx, ty)
        if key not in assignment:
            words.append(0)
            continue
        slot = slots_by_index[assignment[key]]
        pal = slot.colors.astype(np.float64)
        d = (((px[:, None, :].astype(np.float64) - pal[None]) ** 2) * W).sum(-1)
        nearest = d.argmin(1)
        entries = np.array(slot.free)[nearest]
        entries[~m] = 0
        idx = entries.reshape(8, 8)
        n, hf, vf = tileset.add(idx)
        words.append(n | slot.index << 10 | (0x2000 if priority else 0) | (0x4000 if hf else 0) | (0x8000 if vf else 0))
        col = slot.colors[nearest] * 255 // 31
        blk = np.zeros((64, 4), dtype=np.uint8)
        blk[:, :3] = col
        blk[:, 3] = np.where(m, 255, 0)
        preview[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = blk.reshape(8, 8, 4)
    return words, Image.fromarray(preview, "RGBA")


def cgram_block(slots, reserved=None, count=128):
    """128 BG colors (BGR555 words) from palette slots; reserved = {entry: word}."""
    words = [0] * count
    for s in slots:
        for c, entry in zip(s.colors, s.free):
            words[s.index * 16 + entry] = bgr555(c)
    for k, v in (reserved or {}).items():
        words[k] = v
    return words
