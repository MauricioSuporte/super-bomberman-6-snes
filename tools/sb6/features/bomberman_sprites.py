"""Bomberman (player character 1) sprite sheet and palettes, editable as PNG.

The bomber's art is two raw (uncompressed) 4bpp OBJ archives, `$01` and
`$02`, listed in the archive table at `$85:E22D` (8 bytes per archive: VRAM
word, size, src24, flags). Object pieces address them as a 16-tile-wide sheet
(a 16x16 sprite at tile t uses t, t+1, t+16, t+17), so the PNG keeps that
layout: 128 px wide, archive `$01` (256 tiles) on top of archive `$02` (192).

Its palettes are ids 1-7 of palette set 0 (table at `$C0:0379`, bank `$81`,
character 1 base id from `$C0:BB4E`): `[dest $80, count 9, 9 BGR555 colors]`.
Color 0 is transparent. While Bomberman rides a Louie, entries 8-15 of his
slot are overwritten with the Louie's colors (`$C4:53EB`), so art should use
indices 1-7 (index 8 is in the palette but changes while riding).

Files (assets/bomberman/):
  sheet.png     indexed PNG; pixel values are palette indices 0-15
  palettes.png  7 rows (one per color variant) x 9 swatches of 16x16 px
"""
import os

from PIL import Image

from ..romlib import off

ARCHIVE_TABLE = 0x85E22D
ARCHIVES = (0x01, 0x02)
PAL_SET_TABLE = 0xC00379          # word per set, bank $81
PAL_IDS = range(1, 8)             # white, black, red, blue, green, ... (character 1)
PAL_COUNT = 9
SW = 16                           # swatch size in palettes.png


def _rw(d, a):
    return d[off(a)] | d[off(a) + 1] << 8


def archive_src(d, archive):
    e = ARCHIVE_TABLE + (archive - 1) * 8
    size = _rw(d, e + 2)
    src = _rw(d, e + 4) | d[off(e + 6)] << 16
    return src, size


def palette_addr(d, pid):
    table = 0x810000 | _rw(d, PAL_SET_TABLE)
    p = 0x810000 | _rw(d, table + 2 * (pid - 1))
    if _rw(d, p + 2) != PAL_COUNT:
        raise ValueError(f"palette {pid} at ${p:06X} has {_rw(d, p + 2)} colors")
    return p + 4  # first color


def bgr555_to_rgb(v):
    return tuple(((v >> s) & 31) * 255 // 31 for s in (0, 5, 10))


def rgb_to_bgr555(rgb):
    r, g, b = (min(31, (c * 31 + 127) // 255) for c in rgb[:3])
    return r | g << 5 | b << 10


def decode_tiles(raw):
    n = len(raw) // 32
    out = []
    for t in range(n):
        tile = [[0] * 8 for _ in range(8)]
        base = t * 32
        for y in range(8):
            p = [raw[base + y * 2], raw[base + y * 2 + 1], raw[base + 16 + y * 2], raw[base + 17 + y * 2]]
            for x in range(8):
                tile[y][x] = sum(((p[b] >> (7 - x)) & 1) << b for b in range(4))
        out.append(tile)
    return out


def encode_tile(tile):
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = tile[y][x]
            for b in range(4):
                if (v >> b) & 1:
                    out[(b // 2) * 16 + y * 2 + (b % 2)] |= 0x80 >> x
    return bytes(out)


def _sheet_rows(d):
    """[(archive, src, size, first_tile_row)] in sheet order."""
    rows, y = [], 0
    for a in ARCHIVES:
        src, size = archive_src(d, a)
        rows.append((a, src, size, y))
        y += size // 32 // 16
    return rows, y


def read_palettes(d):
    return [[_rw(d, palette_addr(d, pid) + 2 * k) for k in range(PAL_COUNT)] for pid in PAL_IDS]


def extract(d, out_dir):
    """Writes sheet.png / palettes.png from a ROM image (base or built)."""
    os.makedirs(out_dir, exist_ok=True)
    pals = read_palettes(d)
    rows, h = _sheet_rows(d)
    im = Image.new("P", (128, h * 8), 0)
    flat = [c for v in pals[0] for c in bgr555_to_rgb(v)]
    flat += [255, 0, 255] * (16 - PAL_COUNT)  # unused indices 9-15: magenta
    im.putpalette(flat)
    px = im.load()
    for a, src, size, ty in rows:
        raw = d[off(src):off(src) + size]
        for t, tile in enumerate(decode_tiles(raw)):
            ox, oy = (t % 16) * 8, (ty + t // 16) * 8
            for y in range(8):
                for x in range(8):
                    px[ox + x, oy + y] = tile[y][x]
    im.save(os.path.join(out_dir, "sheet.png"), transparency=0)

    pim = Image.new("RGB", (PAL_COUNT * SW, len(pals) * SW))
    for r, pal in enumerate(pals):
        for k, v in enumerate(pal):
            pim.paste(bgr555_to_rgb(v), (k * SW, r * SW, (k + 1) * SW, (r + 1) * SW))
    pim.save(os.path.join(out_dir, "palettes.png"))


def _sheet_indices(path):
    im = Image.open(path)
    if im.mode != "P":
        raise ValueError(f"{path}: must be an indexed (paletted) PNG, got mode {im.mode}")
    return im


def apply(rb, asset_dir):
    """Re-encodes the PNGs; patches only bytes that changed. Returns counts."""
    d = rb.d
    sheet = os.path.join(asset_dir, "sheet.png")
    pal_png = os.path.join(asset_dir, "palettes.png")
    changed_tiles = changed_pals = 0

    rows, h = _sheet_rows(d)
    im = _sheet_indices(sheet)
    if im.size != (128, h * 8):
        raise ValueError(f"{sheet}: must be 128x{h * 8}, got {im.size[0]}x{im.size[1]}")
    px = im.load()
    for a, src, size, ty in rows:
        for t in range(size // 32):
            ox, oy = (t % 16) * 8, (ty + t // 16) * 8
            tile = [[px[ox + x, oy + y] for x in range(8)] for y in range(8)]
            if any(v > 15 for row in tile for v in row):
                raise ValueError(f"{sheet}: tile at ({ox},{oy}) uses a palette index above 15")
            new = encode_tile(tile)
            addr = src + t * 32
            old = bytes(d[off(addr):off(addr) + 32])
            if new != old:
                rb.patch(addr, old, new, f"bomberman sheet archive ${a:02X} tile {t}")
                changed_tiles += 1

    pim = Image.open(pal_png).convert("RGB")
    if pim.size != (PAL_COUNT * SW, len(PAL_IDS) * SW):
        raise ValueError(f"{pal_png}: must be {PAL_COUNT * SW}x{len(PAL_IDS) * SW}")
    for r, pid in enumerate(PAL_IDS):
        addr = palette_addr(d, pid)
        old = bytes(d[off(addr):off(addr) + 2 * PAL_COUNT])
        new = b"".join(rgb_to_bgr555(pim.getpixel((k * SW + SW // 2, r * SW + SW // 2))).to_bytes(2, "little")
                       for k in range(PAL_COUNT))
        if new != old:
            rb.patch(addr, old, new, f"bomberman palette {pid}")
            changed_pals += 1
    return {"tiles": changed_tiles, "palettes": changed_pals}


def guide(asset_dir, out_path, scale=4):
    """Enlarged sheet with a 16x16 grid, block numbers and archive bands (reference only)."""
    from PIL import ImageDraw
    im = Image.open(os.path.join(asset_dir, "sheet.png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, (48, 96, 48, 255))
    bg.alpha_composite(im)
    big = bg.resize((im.width * scale, im.height * scale), Image.NEAREST)
    g = ImageDraw.Draw(big)
    step = 16 * scale
    for x in range(0, big.width + 1, step):
        g.line([(x, 0), (x, big.height)], fill=(255, 255, 255, 90))
    for y in range(0, big.height + 1, step):
        g.line([(0, y), (big.width, y)], fill=(255, 255, 255, 90))
    for by in range(im.height // 16):
        for bx in range(8):
            t = by * 32 + bx * 2
            g.text((bx * step + 2, by * step + 1), f"{t if t < 256 else t - 256:02X}", fill=(255, 255, 0, 255))
    g.line([(0, 128 * scale), (big.width, 128 * scale)], fill=(255, 0, 0, 255), width=2)
    big.convert("RGB").save(out_path)
