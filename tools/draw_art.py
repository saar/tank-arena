#!/usr/bin/env python3
"""The pixel art of the game. Each sprite is made here from small pixel
commands (rect, disc, stamp ...). The result goes into the "art" layer of each
SVG in art/.

    nix develop --command python3 tools/draw_art.py            # write all
    nix develop --command python3 tools/draw_art.py tanks/      # only ids that start with this
    nix develop --command python3 tools/draw_art.py --preview out.png   # contact sheet only

Safe: the script only replaces its own <g id="generated"> group. If you drew
other things in an art layer, that file is skipped (use --force to replace).
"""
import math
import os
import random
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ART = os.path.join(ROOT, "art")

# Tank key colors (the game recolors them): 1 light, 2 dark, 3 white.
KEY = {"1": "#a0a0a0", "2": "#505050", "3": "#ffffff"}


class Canvas:
    def __init__(self, w, h, pal):
        self.w, self.h, self.pal = w, h, dict(pal)
        self.px = [[None] * w for _ in range(h)]

    def set(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c

    def get(self, x, y):
        return self.px[y][x] if 0 <= x < self.w and 0 <= y < self.h else None

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def box(self, x, y, w, h, fill, light, dark):
        """Filled rect, light top/left edge, dark bottom/right edge."""
        self.rect(x, y, w, h, fill)
        self.rect(x, y, w, 1, light)
        self.rect(x, y, 1, h, light)
        self.rect(x, y + h - 1, w, 1, dark)
        self.rect(x + w - 1, y, 1, h, dark)

    def disc(self, cx, cy, r, c):
        for y in range(self.h):
            for x in range(self.w):
                if (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= r * r:
                    self.set(x, y, c)

    def stamp(self, x, y, rows, only=None):
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch not in ". ":
                    self.set(x + dx, y + dy, ch)

    def outline(self, c, src=None):
        """Draw c around every filled pixel (4-neighbour)."""
        pts = []
        for y in range(self.h):
            for x in range(self.w):
                if self.px[y][x] is None:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        v = self.get(x + dx, y + dy)
                        if v is not None and v != c and (src is None or v in src):
                            pts.append((x, y))
                            break
        for x, y in pts:
            self.set(x, y, c)

    def mirror_x(self):
        """Copy the left half to the right half (symmetric sprites)."""
        for y in range(self.h):
            for x in range(self.w // 2):
                self.px[y][self.w - 1 - x] = self.px[y][x]

    def rot_cw(self):
        self.px = [[self.px[self.h - 1 - x][y] for x in range(self.h)] for y in range(self.w)]
        self.w, self.h = self.h, self.w

    def rows(self):
        return ["".join(c or "." for c in r) for r in self.px]


# ---------------------------------------------------------------------------
# Tanks. Facing up. 16x16. Only the key colors 1/2/3.

def tracks(cv, x, y0, y1, w, frame):
    for y in range(y0, y1 + 1):
        groove = (y + frame) % 2 == 0
        for xx in range(x, x + w):
            cv.set(xx, y, "2" if groove else "1")
        if not groove and w >= 3:       # tread plate: dark edges, light middle
            cv.set(x, y, "2")
            cv.set(x + w - 1, y, "2")
    # round the track ends
    cv.set(x, y0, None); cv.set(x + w - 1, y0, None)
    cv.set(x, y1, None); cv.set(x + w - 1, y1, None)


def shape(cv, pts, fill="1", rim="2"):
    """Fill a set of pixels; pixels on its border get the rim color."""
    pts = set(pts)
    for x, y in pts:
        edge = any((x + dx, y + dy) not in pts for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        cv.set(x, y, rim if edge else fill)


def hull(cv, x, y, w, h):
    shape(cv, [(xx, yy) for yy in range(y, y + h) for xx in range(x, x + w)])
    cv.set(x + 1, y + 1, "3"); cv.set(x + 2, y + 1, "3"); cv.set(x + 1, y + 2, "3")


def turret(cv, cx, cy, r):
    pts = [(x, y) for y in range(16) for x in range(16)
           if (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= r * r]
    shape(cv, pts, "3")
    for x, y in pts:                       # shade the lower right side
        if cv.get(x, y) == "3" and (x + .5 - cx) + (y + .5 - cy) > r * 0.7:
            cv.set(x, y, "1")


def barrel(cv, x, y0, y1, w=2, muzzle=False):
    for y in range(y0, y1 + 1):            # dark outline only outside the hull
        for xx in range(x - 1, x + w + 1):
            if cv.get(xx, y) is None or y == y1:
                cv.set(xx, y, "2")
    cv.rect(x, y0, 1, y1 - y0, "3")
    cv.rect(x + 1, y0, w - 1, y1 - y0, "1")
    if muzzle:
        cv.rect(x - 1, y0, w + 2, 2, "3")
        cv.rect(x - 1, y0 + 1, w + 2, 1, "1")


def chamfer_rect(x, y, w, h, c=1, top=None, bottom=None):
    """Points of a rect with cut corners (c = cut size; top/bottom override)."""
    top = c if top is None else top
    bottom = c if bottom is None else bottom
    pts = []
    for yy in range(y, y + h):
        cut = max(top - (yy - y), bottom - (y + h - 1 - yy), 0)
        pts += [(xx, yy) for xx in range(x + cut, x + w - cut)]
    return pts


def gun(cv, x, y0, y1):
    """2 px barrel: light left, dark right."""
    cv.rect(x, y0, 1, y1 - y0 + 1, "3")
    cv.rect(x + 1, y0, 1, y1 - y0 + 1, "2")


def lit_turret(cv, pts, cx, cy):
    shape(cv, pts, "3")
    for x, y in pts:                            # lower right side in shade
        if cv.get(x, y) == "3" and (x + .5 - cx) + (y + .5 - cy) > 1.5:
            cv.set(x, y, "1")


# Hand-drawn grids. 1 = body, 2 = shadow/outline, 3 = highlight.
# a/b = track treads; they swap on frame 2 so the tracks roll.
PLAYER_GRIDS = [
    [  # level 0: light tank - narrow round hull, small turret, thin gun (symmetric about x = 8)
        "................",
        ".......32.......",
        ".......32.......",
        "..aa...32...aa..",
        "..bb..1322..bb..",
        "..aa11132112aa..",
        "..bb11333212bb..",
        "..aa13333212aa..",
        "..bb13333212bb..",
        "..aa11331212aa..",
        "..bb11222212bb..",
        "..aa11111112aa..",
        "..bb13131312bb..",
        "..aa11111112aa..",
        "..bb12222222bb..",
        "......2222......"],
    [  # level 1: medium tank - sloped front plate, hexagon turret, long gun
        ".......32.......",
        ".......32.......",
        ".......32.......",
        "..aaa..32..aaa..",
        "..bbb.3322.bbb..",
        "..aaa333222aaa..",
        "..bbb111321bbb..",
        "..aaa133332aaa..",
        "..bbb333332bbb..",
        "..aaa333312aaa..",
        "..bbb133122bbb..",
        "..aaa112221aaa..",
        "..bbb111112bbb..",
        "..aaa131312aaa..",
        "..bbb222222bbb..",
        "................"],
    [  # level 2: heavy tank - angled front plate, square turret, muzzle brake
        "......3332......",
        ".......32.......",
        ".......32.......",
        ".aa....32....aa.",
        ".bb.31132112.bb.",
        ".aa3113321112aa.",
        ".bb3133333212bb.",
        ".aa3131111212aa.",
        ".bb3131111212bb.",
        ".aa3131111212aa.",
        ".bb3132222212bb.",
        ".aa3111111112aa.",
        ".bb3131111312bb.",
        ".aa2222222222aa.",
        ".bb..........bb.",
        "................"],
    [  # level 3: super tank - very wide, square turret, twin guns, bolts
        ".....32..32.....",
        ".....32..32.....",
        "aaa..32..32..aaa",
        "bbb3111111113bbb",
        "aaa1333333331aaa",
        "bbb1322222231bbb",
        "aaa1321111231aaa",
        "bbb1321331231bbb",
        "aaa1321111231aaa",
        "bbb1322222231bbb",
        "aaa1333333331aaa",
        "bbb1111111111bbb",
        "aaa1131313111aaa",
        "bbb3111111113bbb",
        "aaa2222222222aaa",
        "................"],
]

FAST_GRID = [  # wedge racer: full-length treads, arrow-shaped hull, round turret, thin gun
    "................",
    ".......31.......",
    ".......31.......",
    ".aa....31....aa.",
    ".bb...2312...bb.",
    ".aa..223112..aa.",
    ".bb.22333112.bb.",
    ".aa2233333112aa.",
    ".bb2333113312bb.",
    ".aa2331221312aa.",
    ".bb2331221312bb.",
    ".aa2333113312aa.",
    ".bb2233333122bb.",
    ".aa1222222221aa.",
    ".bb.11111111.bb.",
    "................"]


def grid_tank(rows, frame):
    rows = [r.ljust(16, ".")[:16] for r in rows]
    swap = {"a": "2", "b": "1"} if frame == 0 else {"a": "1", "b": "2"}
    cv = Canvas(16, 16, KEY)
    cv.stamp(0, 0, ["".join(swap.get(c, c) for c in r) for r in rows])
    return cv


def tank_player(lv, frame):
    """4 different designs, one per power level."""
    return grid_tank(PLAYER_GRIDS[lv], frame)


def tank_enemy(kind, frame):
    cv = Canvas(16, 16, KEY)
    if kind == "basic":            # small scout
        tracks(cv, 2, 4, 14, 3, frame); tracks(cv, 11, 4, 14, 3, frame)
        hull(cv, 5, 5, 6, 9)
        turret(cv, 8, 10, 2.6)
        barrel(cv, 7, 1, 7)
    elif kind == "fast":           # beetle shell: curved body over the tracks
        return grid_tank(FAST_GRID, frame)
    elif kind == "power":          # long gun, turret at the back
        tracks(cv, 1, 5, 15, 3, frame); tracks(cv, 12, 5, 15, 3, frame)
        hull(cv, 4, 6, 8, 10)
        barrel(cv, 7, 0, 9)
        cv.rect(6, 0, 4, 1, "3"); cv.rect(6, 1, 4, 1, "2")   # muzzle brake
        turret(cv, 8, 11.5, 3)
    else:                          # heavy armour
        tracks(cv, 0, 1, 15, 4, frame); tracks(cv, 12, 1, 15, 4, frame)
        hull(cv, 3, 2, 10, 14)
        for y in (4, 13):
            cv.rect(4, y, 8, 1, "2")
        barrel(cv, 7, 0, 5)
        shape(cv, [(x, y) for y in range(5, 12) for x in range(5, 11)], "3")
        cv.rect(8, 8, 2, 3, "1"); cv.rect(6, 6, 1, 1, "1")
    return cv


# ---------------------------------------------------------------------------
# Terrain tiles, 8x8, real colors.

def tile_brick():
    pal = {"a": "#c8602a", "b": "#e8904a", "m": "#4a2a1e", "d": "#8a3a18"}
    return Canvas.from_rows(pal, [
        "bbbmbbbb",
        "aaamaaad",
        "dddmdddd",
        "mmmmmmmm",
        "bmbbbbbb",
        "amaaaaaa",
        "dmdddddd",
        "mmmmmmmm"])


def tile_steel():
    """Pillow-plate steel."""
    pal = {"w": "#f4f8fb", "l": "#c4cfd8", "m": "#8f9ca6", "d": "#56616a", "k": "#2e353b"}
    return Canvas.from_rows(pal, [
        "mllllllm",
        "lwwwwwld",
        "lwllllmd",
        "lwllllmd",
        "lwllllmd",
        "lwllllmd",
        "lmmmmmmd",
        "mdddddkk"])


def tile_water(frame):
    pal = {"b": "#1f5fbf", "l": "#4f9fef", "w": "#bfe8ff"}
    rows = ["bbbbbbbb",
            "bwwbbbbb",
            "wbblbbbb",
            "bbbbbbbb",
            "bbbbbwwb",
            "bbbbwbbl",
            "bbbbbbbb",
            "bblbbbbb"]
    if frame == 2:   # waves move right by 2 and down by 1
        rows = [r[-2:] + r[:-2] for r in rows]
        rows = rows[-1:] + rows[:-1]
    return Canvas.from_rows(pal, rows)


def tile_forest():
    pal = {"g": "#2f8f2f", "l": "#6fcf3f", "d": "#145a1e"}
    return Canvas.from_rows(pal, [
        ".lg..lg.",
        "lggddggd",
        "gggdgggd",
        "dgd.dgd.",
        "lg..lgg.",
        "ggdlggdd",
        "gdggggd.",
        ".d.ddd.."])


def tile_ice():
    pal = {"i": "#b8e4f4", "w": "#ffffff", "s": "#8cc4dc"}
    return Canvas.from_rows(pal, [
        "iiiiiwii",
        "iiiiwiii",
        "iiiwiiis",
        "iiiiiiii",
        "iisiiiii",
        "wiiiiiiw",
        "iiiiiiwi",
        "isiiiwii"])


# ---------------------------------------------------------------------------
# Items, 16x16: a tile with cut corners (light frame, dark fill) and a small
# monochrome icon (10x10, white + gray) inside. No colors: they read as "bonus".
# The dark fill is 70 % opaque, so the ground under the item shows a little.

ITEM_PAL = {"F": "#bcbcbc", "k": "#1c1c1c:0.7", "w": "#f8f8f8", "g": "#8c8c8c"}   # fill: 70 % (ground shows through)
ITEM_TILE = [
    "..FFFFFFFFFFFF..",
    ".FkkkkkkkkkkkkF.",
    "FkkkkkkkkkkkkkkF",
] + ["FkkkkkkkkkkkkkkF"] * 10 + [
    "FkkkkkkkkkkkkkkF",
    ".FkkkkkkkkkkkkF.",
    "..FFFFFFFFFFFF.."]


def item(icon):
    """icon: 10 rows of 10 ("." = tile fill), placed at (3, 3)."""
    rows = [list(r) for r in ITEM_TILE]
    for y, r in enumerate(icon):
        for x, c in enumerate(r):
            if c != ".":
                rows[3 + y][3 + x] = c
    cv = Canvas(16, 16, ITEM_PAL)
    cv.stamp(0, 0, ["".join(r) for r in rows])
    return cv


def item_shield():      # helmet -> shield
    return item([
        "wwwwwwwwww",
        "wwwwwggggw",
        "wwwwwggggw",
        "wwwwwggggw",
        ".wwwwgggw.",
        ".wwwwgggw.",
        "..wwwggw..",
        "..wwwggw..",
        "...wwgw...",
        "....ww...."])


def item_clock():       # stopwatch
    return item([
        "...wwww...",
        "....ww..w.",
        "..wwwwww..",
        ".wwwwkwww.",
        ".wwwwkwww.",
        ".wwwwkkkw.",
        ".wwwwwwww.",
        ".wwwwwwww.",
        "..wwwwww..",
        "...gggg..."])


def item_shovel():      # spade: "fortify the base"
    return item([
        "...gggg...",
        "....gg....",
        "....gg....",
        "....gg....",
        "..wwwwww..",
        "..wwwwwg..",
        "..wwwwwg..",
        "..wwwwgg..",
        "...wwgg...",
        "....gg...."])


def item_star():
    return item([
        "....ww....",
        "...wwww...",
        "...wwww...",
        "wwwwwwwwww",
        ".wwwwwwww.",
        "..wwwwww..",
        "..wwwwww..",
        ".www..www.",
        ".ww....ww.",
        ".........."])


def item_bomb():        # grenade -> round bomb
    return item([
        ".......w.w",
        "........w.",
        ".......g.w",
        "......g...",
        "...wwww...",
        "..wwwwww..",
        ".wwwwwwwg.",
        ".wwwwwwwg.",
        ".wwwwwwgg.",
        "..wwgggg.."])


def item_tank():        # extra life: a small tank
    return item([
        "....ww....",
        "....ww....",
        "gg..ww..gg",
        "ggwwwwwwgg",
        "ggwwggwwgg",
        "ggwgwwgwgg",
        "ggwgwwgwgg",
        "ggwwggwwgg",
        "ggwwwwwwgg",
        "gg......gg"])


def item_gun():         # two up-chevrons: full power
    return item([
        "....ww....",
        "...wwww...",
        "..ww..ww..",
        ".ww....ww.",
        "ww..ww..ww",
        "...wwww...",
        "..ww..ww..",
        ".ww....ww.",
        "ww......ww",
        ".........."])


def item_ship():        # boat
    return item([
        "....g.....",
        "....gww...",
        "....gwww..",
        "....gwwww.",
        "....g.....",
        "wwwwwwwwww",
        ".wwwwwwww.",
        "..wwwwww..",
        "..........",
        ".........."])


def item_rescue():      # flag: brings the partner back
    return item([
        "..g.......",
        "..gwww....",
        "..gwwwwww.",
        "..gwwwwww.",
        "..gwwwwww.",
        "..g...www.",
        "..g.......",
        "..g.......",
        ".ggg......",
        "ggggg....."])


def item_link():        # two chain rings: the players are linked
    return item([
        "..........",
        ".wwww.....",
        "ww..ww....",
        "ww..wgggg.",
        "ww..ww..gg",
        "ww..ww..gg",
        ".wwwwg..gg",
        "....gg..gg",
        ".....gggg.",
        ".........."])


def item_turret():      # gun post
    return item([
        "....ww....",
        "....ww....",
        "....ww....",
        "..wwwwww..",
        ".wwggggww.",
        ".wwgwwgww.",
        ".wwggggww.",
        ".wwwwwwww.",
        "gggggggggg",
        "gggggggggg"])


def item_repair():      # + over bricks
    return item([
        "....ww....",
        "....ww....",
        "..wwwwww..",
        "..wwwwww..",
        "....ww....",
        "....ww....",
        "wwwgwwwwgw",
        "gggggggggg",
        "wgwwwwgwww",
        "gggggggggg"])


def item_mystery():     # question mark
    return item([
        "...wwww...",
        "..wwggww..",
        "..ww..ww..",
        "......ww..",
        ".....ww...",
        "....ww....",
        "....ww....",
        "..........",
        "....ww....",
        "....ww...."])


def turret_post():
    """TURRET item: fixed gun above the base, facing up (the game rotates it)."""
    pal = {"o": "#1c1c1c", "F": "#bcbcbc", "g": "#8c8c8c", "w": "#f8f8f8", "d": "#5c5c5c"}
    return Canvas.from_rows(pal, [
        "................",
        ".......ww.......",
        ".......wg.......",
        ".......wg.......",
        "...oooowgoooo...",
        "..oFFFFwgFFFFo..",
        ".oFgggwwggggdFo.",
        ".oFgwwwwwwgdgFo.",
        ".oFgwwwwwwgdgFo.",
        ".oFgwwwwwwgdgFo.",
        ".oFgwwwwwwgdgFo.",
        ".oFggwwwwggdgFo.",
        ".oFgddddddddgFo.",
        "..oFFFFFFFFFFo..",
        "...oooooooooo...",
        "................"])


# ---------------------------------------------------------------------------
# Base: a radio tower (not a bird).

def base(dead):
    pal = {"s": "#c8ccd4", "d": "#6a7078", "r": "#e83a2a", "y": "#f8d040", "b": "#3a3a48", "x": "#5a3a2a"}
    if not dead:
        rows = [
            "....y......y....",
            "...y...rr...y...",
            "..y..y.rr.y..y..",
            "..y.y..ss..y.y..",
            "..y.y..ss..y.y..",
            "...y..sdds..y...",
            "......sdds......",
            "......sdds......",
            ".....sddds......",
            ".....sdsdds.....",
            ".....sddsds.....",
            "....sdsddsds....",
            "....sddsddds....",
            "...sdsddddsds...",
            "..bbbbbbbbbbbb..",
            "..bdddddddddbb.."]
        cv = Canvas(16, 16, pal)
        cv.stamp(0, 0, rows)
        # make it symmetric
        for y in range(16):
            for x in range(8):
                cv.px[y][15 - x] = cv.px[y][x]
        return cv
    rows = [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "..........x.....",
        "....x...........",
        "..........d.....",
        ".........ds.r...",
        "...x....dsd.....",
        "....s..dsds.x...",
        "...sdsdsddsd....",
        ".xsddsdsdsddsx..",
        "..bbbbbbbbbbbb..",
        "..bdddddddddbb.."]
    return Canvas.from_rows(pal, rows)


# ---------------------------------------------------------------------------
# Effects

def spawn(i):
    cv = Canvas(16, 16, {"w": "#ffffff", "c": "#a8e8ff", "b": "#4fa8ef"})
    L = [2, 4, 6, 7][i]
    for d in range(L + 1):
        c = "w" if d < L - 1 else "c"
        for x, y in ((8 + d, 8), (7 - d, 8), (8, 8 + d), (8, 7 - d)):
            cv.set(x, y, c)
        for x, y in ((7 - d, 7), (8 + d, 7), (7, 7 - d), (7, 8 + d)):
            cv.set(x, y, c)
    dg = [0, 1, 3, 4][i]
    for d in range(1, dg + 1):
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cv.set(7.5 + sx * (d + .5), 7.5 + sy * (d + .5), "b")
    cv.rect(7, 7, 2, 2, "w")
    return cv


FX = {"w": "#ffffff", "y": "#f8e060", "o": "#f89020", "r": "#c82818", "k": "#501010"}


def blob(size, radius, seed, rings):
    """Rough explosion cloud. rings: [(fraction of radius, color)], outer first."""
    rnd = random.Random(seed)
    cv = Canvas(size, size, FX)
    c = size / 2
    bumps = [rnd.uniform(0.75, 1.15) for _ in range(12)]
    for y in range(size):
        for x in range(size):
            dx, dy = x + .5 - c, y + .5 - c
            a = (math.atan2(dy, dx) + math.pi) / (2 * math.pi) * 12
            k = int(a) % 12
            t = a - int(a)
            rr = radius * (bumps[k] * (1 - t) + bumps[(k + 1) % 12] * t)
            d = math.hypot(dx, dy)
            for frac, col in rings:
                if d <= rr * frac:
                    cv.set(x, y, col)
    # a few loose sparks
    for _ in range(int(radius)):
        ang = rnd.uniform(0, 2 * math.pi)
        d = radius * rnd.uniform(1.05, 1.3)
        cv.set(c + math.cos(ang) * d, c + math.sin(ang) * d, rnd.choice("oy"))
    return cv


def explosion_small(i):
    r = [3.2, 5.5, 6.8][i]
    rings = [[(1, "o"), (.6, "y"), (.3, "w")],
             [(1, "r"), (.75, "o"), (.45, "y"), (.2, "w")],
             [(1, "k"), (.8, "r"), (.55, "o")]][i]
    return blob(16, r, 10 + i, rings)


def explosion_big(i):
    r = [11, 15][i]
    rings = [[(1, "r"), (.8, "o"), (.55, "y"), (.3, "w")],
             [(1, "k"), (.85, "r"), (.65, "o"), (.4, "y")]][i]
    return blob(32, r, 20 + i, rings)


def shield(i):
    cv = Canvas(16, 16, {"w": "#ffffff", "c": "#7fd8ff"})
    for y in range(16):
        for x in range(16):
            dx, dy = x + .5 - 8, y + .5 - 8
            d = math.hypot(dx, dy)
            if 6.6 <= d <= 8.0:
                seg = int((math.atan2(dy, dx) + math.pi) / (2 * math.pi) * 16 + i) % 4
                if seg in (0, 2):
                    cv.set(x, y, "w")
                elif seg == 1:
                    cv.set(x, y, "c")
    return cv


def bullet():
    return Canvas.from_rows({"w": "#ffffff", "g": "#b0b0b0"}, [
        "........",
        "........",
        "...ww...",
        "...ww...",
        "...wg...",
        "...gg...",
        "........",
        "........"])


DIG3 = {  # 3x5 digits for score popups
    "0": ["###", "#.#", "#.#", "#.#", "###"],
    "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"],
    "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"],
    "5": ["###", "#..", "###", "..#", "###"],
}


def score(v):
    cv = Canvas(16, 16, {"#": "#ffffff"})
    x = 2
    for ch in str(v):
        cv.stamp(x, 5, DIG3[ch]); x += 4
    return cv


# ---------------------------------------------------------------------------
# UI. Font: own 5x7 glyphs, drawn bold (each pixel doubled to the right) = 6x7 in an 8x8 cell.

FONT5 = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11100", "10010", "10001", "10001", "10001", "10010", "11100"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
}
FONT_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-"


def font_sheet():
    cv = Canvas(80, 32, {"#": "#ffffff", "k": "#000000"})
    cv.rect(0, 0, 80, 32, "k")
    for i, ch in enumerate(FONT_CHARS):
        ox, oy = (i % 10) * 8, (i // 10) * 8
        for y, row in enumerate(FONT5[ch]):
            for x, b in enumerate(row):
                if b == "1":
                    cv.set(ox + x, oy + y, "#")
                    cv.set(ox + x + 1, oy + y, "#")
    return cv


def reserve_icon():
    return Canvas.from_rows({"k": "#202020", "g": "#7a7a7a"}, [
        "gggggggg",
        "gggkkggg",
        "gkgkkgkg",
        "gkkkkkkg",
        "gkkggkkg",
        "gkkkkkkg",
        "gkgggg kg".replace(" ", "")[:8],
        "gggggggg"])


def lives_icon():
    return Canvas.from_rows({"k": "#202020", "g": "#7a7a7a", "r": "#c83a2a"}, [
        "gggggggg",
        "grrgrrgg",
        "rrrrrrrg",
        "rrrrrrrg",
        "grrrrrgg",
        "ggrrrggg",
        "gggrgggg",
        "gggggggg"])


def stage_flag():
    pal = {"g": "#7a7a7a", "p": "#202020", "f": "#e8b030", "d": "#a87010"}
    return Canvas.from_rows(pal, [
        "gggggggggggggggg",
        "gggpgggggggggggg",
        "gggpffffffffgggg",
        "gggpfffffffffggg",
        "gggpffffdfffffgg",
        "gggpfffddffffggg",
        "gggpffffffffgggg",
        "gggpfffffffggggg",
        "gggpgggggggggggg",
        "gggpgggggggggggg",
        "gggpgggggggggggg",
        "gggpgggggggggggg",
        "gggpgggggggggggg",
        "ggpppggggggggggg",
        "gpppppgggggggggg",
        "gggggggggggggggg"])


def cursor():
    cv = tank_player(0, 0)
    cv.rot_cw()
    cv.pal = {"1": "#e8b030", "2": "#a86a10", "3": "#fff0b0"}
    return cv


def _from_rows(pal, rows):
    cv = Canvas(len(rows[0]), len(rows), pal)
    for r in rows:
        assert len(r) == cv.w, (r, cv.w)
    cv.stamp(0, 0, rows)
    return cv


Canvas.from_rows = staticmethod(_from_rows)


# ---------------------------------------------------------------------------
def sprites():
    S = {}
    S["tiles/brick"] = tile_brick()
    S["tiles/steel"] = tile_steel()
    S["tiles/water_1"] = tile_water(1)
    S["tiles/water_2"] = tile_water(2)
    S["tiles/forest"] = tile_forest()
    S["tiles/ice"] = tile_ice()
    for lv in range(4):
        for f in range(2):
            S["tanks/player_lv%d_%d" % (lv, f + 1)] = tank_player(lv, f)
    for k in ("basic", "fast", "power", "armor"):
        for f in range(2):
            S["tanks/enemy_%s_%d" % (k, f + 1)] = tank_enemy(k, f)
    for n, fn in (("helmet", item_shield), ("clock", item_clock), ("shovel", item_shovel),
                  ("star", item_star), ("grenade", item_bomb), ("tank", item_tank),
                  ("gun", item_gun), ("ship", item_ship), ("rescue", item_rescue), ("link", item_link),
                  ("turret", item_turret), ("repair", item_repair),
                  ("mystery", item_mystery)):
        S["items/" + n] = fn()
    S["base/hq"] = base(False)
    S["base/hq_dead"] = base(True)
    for i in range(4):
        S["effects/spawn_%d" % (i + 1)] = spawn(i)
    for i in range(3):
        S["effects/explosion_small_%d" % (i + 1)] = explosion_small(i)
    for i in range(2):
        S["effects/explosion_big_%d" % (i + 1)] = explosion_big(i)
        S["effects/shield_%d" % (i + 1)] = shield(i)
    S["effects/bullet"] = bullet()
    S["effects/turret"] = turret_post()
    for v in (100, 200, 300, 400, 500):
        S["effects/score_%d" % v] = score(v)
    S["ui/font"] = font_sheet()
    S["ui/reserve_icon"] = reserve_icon()
    S["ui/lives_icon"] = lives_icon()
    S["ui/stage_flag"] = stage_flag()
    S["ui/cursor"] = cursor()
    return S


def to_svg_group(cv):
    """Merge each row into runs of one color -> <rect> elements."""
    out = []
    for y, row in enumerate(cv.px):
        x = 0
        while x < cv.w:
            c = row[x]
            if c is None:
                x += 1
                continue
            x2 = x
            while x2 < cv.w and row[x2] == c:
                x2 += 1
            col, _, op = cv.pal[c].partition(":")          # "#rrggbb:0.7" = 70 % opacity
            extra = ' fill-opacity="%s"' % op if op else ""
            out.append('<rect x="%d" y="%d" width="%d" height="1" fill="%s"%s/>' % (x, y, x2 - x, col, extra))
            x = x2
    return '<g id="generated">\n      ' + "\n      ".join(out) + "\n    </g>"


ART_RE = re.compile(r'(<g[^>]*id="art"[^>]*>)(.*?)(\n  </g>\n</svg>)', re.S)


def write(fid, cv, force):
    path = os.path.join(ART, fid + ".svg")
    txt = open(path, encoding="utf-8").read()
    m = ART_RE.search(txt)
    if not m:
        return "no art layer"
    inner = m.group(2)
    other = re.sub(r'<g id="generated">.*?</g>', "", inner, flags=re.S).strip()
    if other and not force:
        return "skipped (has your own drawing; use --force)"
    new = txt[:m.start()] + m.group(1) + "\n    " + to_svg_group(cv) + m.group(3) + txt[m.end():]
    open(path, "w", encoding="utf-8").write(new)
    return "ok"


def preview_tanks(S, path, s=8):
    """Tanks only, big, in two test colors (as the game recolors them)."""
    from PIL import Image
    pals = [{"1": (248, 196, 24), "2": (184, 120, 0), "3": (255, 240, 160)},
            {"1": (180, 180, 180), "2": (60, 70, 80), "3": (255, 255, 255)}]
    tanks = [(k, v) for k, v in S.items() if k.startswith("tanks/")]
    im = Image.new("RGB", (len(tanks) // 2 * 18 * s, 2 * 18 * s * 2), (20, 20, 20))
    for i, (fid, cv) in enumerate(tanks):
        for pi, pal in enumerate(pals):
            ox = (i // 2) * 18 * s
            oy = ((i % 2) + pi * 2) * 18 * s
            for y in range(16):
                for x in range(16):
                    c = cv.px[y][x]
                    if c:
                        for yy in range(s):
                            for xx in range(s):
                                im.putpixel((ox + x * s + xx, oy + y * s + yy), pal[c])
    im.save(path)


def preview(S, path, scale=4):
    from PIL import Image, ImageDraw
    items = list(S.items())
    cell = 32 * scale + 8
    cols = 8
    rows = (len(items) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * (cell + 12)), (40, 40, 44))
    dr = ImageDraw.Draw(im)
    for i, (fid, cv) in enumerate(items):
        ox, oy = (i % cols) * cell + 4, (i // cols) * (cell + 12) + 4
        s = scale * (2 if max(cv.w, cv.h) <= 16 else 1)
        if cv.w > 32:
            s = scale * 32 // cv.w * 1 or 1
        dr.rectangle([ox, oy, ox + cv.w * s - 1, oy + cv.h * s - 1], fill=(0, 0, 0))
        for y in range(cv.h):
            for x in range(cv.w):
                c = cv.px[y][x]
                if c is not None:
                    h = cv.pal[c].split(":")[0].lstrip("#")
                    dr.rectangle([ox + x * s, oy + y * s, ox + x * s + s - 1, oy + y * s + s - 1],
                                 fill=tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)))
        dr.text((ox, oy + cell - 6), fid.split("/")[1][:20], fill=(220, 220, 220))
    im.save(path)


def main():
    args = sys.argv[1:]
    force = "--force" in args
    prev = None
    if "--preview" in args:
        prev = args[args.index("--preview") + 1]
    prefixes = [a for a in args if not a.startswith("--") and a != prev]
    S = sprites()
    if prefixes:
        S = {k: v for k, v in S.items() if any(k.startswith(p) for p in prefixes)}
    if prev:
        preview(S, prev)
        preview_tanks(S, prev.replace(".png", "_tanks.png"))
        print("wrote", prev)
        return
    for fid, cv in S.items():
        print("%-28s %s" % (fid, write(fid, cv, force)))


if __name__ == "__main__":
    main()
