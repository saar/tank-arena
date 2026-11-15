"""Load the art kit (art/*.svg) into an Assets object. Only the "art" layer of
each SVG is used; a "grid" layer (a drawing help) is removed before loading.
"""
import io
import os
import re
import sys

import pygame

FONT_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-"
KEY = [(160, 160, 160), (80, 80, 80), (255, 255, 255)]    # palette index 1, 2, 3
TANKS = ["player_lv0", "player_lv1", "player_lv2", "player_lv3",
         "enemy_basic", "enemy_fast", "enemy_power", "enemy_armor"]
ITEMS = ["helmet", "clock", "shovel", "star", "grenade", "tank", "gun", "ship",
         "rescue", "link", "turret", "repair", "mystery"]
ROT = {"up": 0, "left": 90, "down": 180, "right": -90}


class MissingArt(Exception):
    pass


def render_svg(art_dir, fid):
    """The "art" layer of art/<fid>.svg as a surface, 1 SVG unit = 1 pixel."""
    path = os.path.join(art_dir, fid + ".svg")
    if not os.path.exists(path):
        raise MissingArt(path)
    txt = open(path, encoding="utf-8").read()
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', txt)
    w, h = int(m.group(1)), int(m.group(2))
    txt = re.sub(r'<g[^>]*id="grid".*?</g>', "", txt, flags=re.S)
    txt = re.sub(r'<sodipodi:namedview.*?</sodipodi:namedview>', "", txt, flags=re.S)
    txt = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"', r'\1 width="%d"' % w, txt, count=1)
    txt = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r'\1 height="%d"' % h, txt, count=1)
    surf = pygame.image.load(io.BytesIO(txt.encode()), "art.svg")
    if surf.get_size() != (w, h):
        surf = pygame.transform.scale(surf, (w, h))
    return surf


def load_svg(art_dir, fid, soft=False):
    """soft: keep real transparency (items: their fill is 70 % opaque). Else every
    pixel is fully opaque or fully transparent (no soft edges)."""
    png = os.path.join(art_dir, fid + ".png")    # browser build: drawn before (tools/web/svg2png.py)
    if sys.platform == "emscripten" and os.path.exists(png):
        surf = pygame.image.load(png).convert_alpha()
        w, h = surf.get_size()
    else:
        surf = render_svg(art_dir, fid).convert_alpha()
        w, h = surf.get_size()
    if soft:
        return surf
    # hard pixel edges: no half-transparent pixels
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            surf.set_at((x, y), (c.r, c.g, c.b, 255 if c.a >= 128 else 0))
    return surf


def recolor_key(src, pal):
    """Map the 3 tank key colors to palette entries 1..3."""
    out = src.copy()
    w, h = src.get_size()
    for y in range(h):
        for x in range(w):
            c = src.get_at((x, y))
            if c.a == 0:
                continue
            i = min(range(3), key=lambda k: sum((a - b) ** 2 for a, b in zip(KEY[k], (c.r, c.g, c.b))))
            out.set_at((x, y), pal[i + 1])
    return out


def pad(surf, size):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.blit(surf, ((size - surf.get_width()) // 2, (size - surf.get_height()) // 2))
    return s


def apply(assets, art_dir):
    """Load all graphics of the art kit into an Assets object."""
    L = lambda fid: load_svg(art_dir, fid)
    A = assets
    A.bg = {
        "brick": L("tiles/brick"),
        "steel": L("tiles/steel"),
        "water": [L("tiles/water_1"), L("tiles/water_2")],
        "ice": L("tiles/ice"),
        "forest": L("tiles/forest"),
    }
    A.tank_src = [[L("tanks/%s_%d" % (n, f)) for f in (1, 2)] for n in TANKS]
    A.items = [load_svg(art_dir, "items/" + n, soft=True) for n in ITEMS]
    A.sparkle = [L("effects/spawn_%d" % i) for i in range(1, 5)]
    A.explo = [L("effects/explosion_small_%d" % i) for i in range(1, 4)]
    A.boom_frames = [pad(s, 32) for s in A.explo[:2]] + \
                    [L("effects/explosion_big_%d" % i) for i in (1, 2)]
    A.shield = [L("effects/shield_%d" % i) for i in (1, 2)]
    b = L("effects/bullet")
    A.bullet = {d: pygame.transform.rotate(b, r) for d, r in ROT.items()}
    t = L("effects/turret")
    A.turret = {d: pygame.transform.rotate(t, r) for d, r in ROT.items()}
    A.score = {v: L("effects/score_%d" % v) for v in (100, 200, 300, 400, 500)}
    A.hq = L("base/hq")
    A.hq_dead = L("base/hq_dead")
    A.reserve_icon = L("ui/reserve_icon")
    A.lives_icon = L("ui/lives_icon")
    sheet = L("ui/font")
    A.glyph_mask = {}
    for i, ch in enumerate(FONT_CHARS):
        ox, oy = (i % 10) * 8, (i // 10) * 8
        A.glyph_mask[ch] = [[sheet.get_at((ox + x, oy + y)).r > 128 for x in range(8)] for y in range(8)]
    A._tank_cache = {}
    A._font = {}
