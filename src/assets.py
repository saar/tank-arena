"""All surfaces the game needs (from the art kit, art.py) and the map pack (maps.py)."""
import os

import pygame

from maps import DEFAULT_PACK, MapPack

HERE = os.path.dirname(os.path.abspath(__file__))
ART_DIR = os.path.join(HERE, "..", "art")

BLACK = (0, 0, 0)
PAL_BG = {
    "brick":  [BLACK, (203, 77, 12), (166, 0, 0), (117, 117, 117)],
    "steel":  [BLACK, (117, 117, 117), (190, 190, 190), (255, 255, 255)],
    "ice":    [BLACK, (117, 117, 117), (190, 190, 190), (255, 255, 255)],
    "water":  [BLACK, (158, 255, 243), (32, 56, 239), (32, 56, 239)],
    "water2": [BLACK, (32, 56, 239), (158, 255, 243), (32, 56, 239)],
    "forest": [BLACK, (130, 211, 16), (0, 69, 0), (0, 60, 20)],
    # Font glyphs use color index 3 only.
    "text":   [BLACK, BLACK, BLACK, (255, 255, 255)],
    "textgray": [BLACK, BLACK, BLACK, (117, 117, 117)],
    "textred": [BLACK, BLACK, BLACK, (203, 77, 12)],
    "panel":  [(117, 117, 117)] * 3 + [BLACK],
}
# Sprite palettes: index 0 is transparent.
PAL_SPR = {
    "player": [None, (248, 196, 24), (184, 120, 0), (255, 240, 160)],
    "player2": [None, (72, 208, 200), (0, 104, 112), (210, 255, 250)],
    "enemy":  [None, (190, 190, 190), (24, 60, 93), (255, 255, 255)],
    "red":    [None, (203, 77, 12), (166, 0, 0), (255, 255, 255)],
    "green":  [None, (130, 211, 16), (0, 81, 0), (178, 255, 207)],
    "gold":   [None, (231, 156, 33), (138, 113, 0), (255, 255, 255)],
    "item":   [None, (231, 156, 33), (117, 117, 117), (255, 255, 255)],
    "white":  [None, (255, 255, 255), (190, 190, 190), (255, 255, 255)],
    "hq":  [None, (255, 255, 255), (166, 0, 0), (117, 117, 117)],
}

class Assets:
    """All surfaces the game needs, built once."""
    DIRS = ["up", "left", "down", "right"]

    def __init__(self, map_dir=None, art_dir=None):
        from art import apply
        self.maps = MapPack(map_dir or DEFAULT_PACK)
        self._tank_cache = {}
        self._font = {}
        apply(self, art_dir or ART_DIR)

    def tank(self, kind, d, frame, pal):
        key = (kind, d, frame, pal)
        if key not in self._tank_cache:
            from art import recolor_key, ROT
            img = recolor_key(self.tank_src[kind][frame], PAL_SPR[pal])
            self._tank_cache[key] = pygame.transform.rotate(img, ROT[d])
        return self._tank_cache[key]

    def text_color(self, surf, s, x, y, color):
        """Text in any RGB color, transparent background."""
        for i, ch in enumerate(s.upper()):
            key = (ch, tuple(color))
            if key not in self._font:
                g = pygame.Surface((8, 8), pygame.SRCALPHA)
                for py, row in enumerate(self.glyph_mask.get(ch, [])):
                    for px, on in enumerate(row):
                        if on:
                            g.set_at((px, py), color)
                self._font[key] = g
            surf.blit(self._font[key], (x + i * 8, y))

    def text(self, surf, s, x, y, pal="text"):
        """Text in a named color (PAL_BG entry, color index 3), transparent background."""
        self.text_color(surf, s, x, y, PAL_BG[pal][3])
