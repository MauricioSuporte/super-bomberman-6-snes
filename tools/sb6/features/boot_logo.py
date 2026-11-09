"""Boot logo: the picture shown before the intro (SB5: the Hudson logo).

SB5 draws it from script $C7:0AC4 (mode 1):
    26 03 27 46 2A 2B   set 3, archive $46 (BG1 tiles), palette $2B (32 colors)
    FF 8D D3 04 01 00 00 arrangement $D3 of set 4 on BG1
Mode 1, BG1 only (map $3000, chr $0000, 768 tiles max), no sprites. The new
picture is a full 256x224 BG1 image with 8 palettes; title.py stores it in
graphics set 5 (archive 3, palette 2, arrangement 5) and redirects the script.
"""
from PIL import Image

from ..snesgfx import Layer, PaletteSlot, TileSet, best_palettes, build_layer_map, cgram_block

TILE_LIMIT = 0x300  # BG1 map at VRAM word $3000


def convert(path, starts=((1, "mean"), (1, "hist"), (2, "mean"))):
    img = Image.open(path).convert("RGBA")
    if img.size != (256, 224):
        raise ValueError(f"{path}: boot logo must be 256x224, got {img.size}")
    layer = Layer("boot", img, opaque_required=True)

    def make_slots():
        return [PaletteSlot(i, range(1, 16)) for i in range(8)]

    assignment, slots, err, start = best_palettes([layer], make_slots, starts)
    tiles = TileSet()
    words, preview = build_layer_map(layer, assignment, {s.index: s for s in slots}, tiles)
    if len(tiles.tiles) > TILE_LIMIT:
        raise ValueError(f"boot logo uses {len(tiles.tiles)} tiles; limit is {TILE_LIMIT}")
    colors = cgram_block(slots)
    return dict(tiles=tiles.data(), words=words, colors=colors, error=err, start=start,
                preview=preview, count=len(tiles.tiles))
