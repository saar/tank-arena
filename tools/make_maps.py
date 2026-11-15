#!/usr/bin/env python3
"""Make the default map pack (maps/default/) and a contact sheet to review it.

    nix develop --command python3 tools/make_maps.py                 # write maps/default/01..35.txt
    nix develop --command python3 tools/make_maps.py --sheet out.png # also render all stages
    nix develop --command python3 tools/make_maps.py --only 7 --seed 3   # make stage 7 again (other seed)
    nix develop --command python3 tools/make_maps.py --sheet out.png --render-only   # just render the pack

Each stage is built from "motifs" (pillar rows, walls, rooms, forest groves, rivers, ice
fields, steel studs) on a 13x13 block grid. Most maps are mirror-symmetric. Later stages get
more steel and water and harder enemy waves. Many candidates are made per stage; the one
with the best score (block mix, open space near the spawns, every spawn reaches the base)
is kept. Edit the .txt files by hand afterwards if you like (format: src/maps.py).
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import maps  # noqa: E402
from mapgen import KEEP_FREE, MIRROR, reachable  # noqa: E402

N = 13
E, BR, ST, WA, FO, IC = 13, 4, 9, 10, 11, 12
OUT = os.path.join(ROOT, "maps", "default")
STAGES = 35
# blocks next to spawns and the base that should stay open (more than KEEP_FREE)
ROOMY = {(1, 0), (0, 1), (1, 6), (0, 5), (0, 7), (1, 12), (0, 11), (12, 3), (11, 4), (12, 9), (11, 8)}


class Grid:
    def __init__(self, sym):
        self.g = [[E] * N for _ in range(N)]
        self.sym = sym
        self.cols = 7 if sym else N

    def set(self, r, c, b):
        if 0 <= r < N and 0 <= c < self.cols:
            self.g[r][c] = b

    def get(self, r, c):
        return self.g[r][c]

    def done(self):
        g = self.g
        if self.sym:
            for r in range(N):
                for c in range(6):
                    g[r][12 - c] = MIRROR.get(g[r][c], g[r][c])
        for r, c in KEEP_FREE:
            g[r][c] = E
        return g


# ---- motifs ------------------------------------------------------------------
def pillars(G, rng, d):
    """Vertical brick columns on every 2nd column (a classic arena look)."""
    c0 = rng.choice((1, 2))
    r0, r1 = rng.randint(1, 3), rng.randint(7, 10)
    cap = ST if rng.random() < 0.25 + 0.4 * d else None
    for c in range(c0, G.cols, 2):
        if rng.random() < 0.15:
            continue
        for r in range(r0, r1 + 1):
            G.set(r, c, BR)
        if cap:
            G.set(r0 if rng.random() < 0.5 else r1, c, cap)


def hwall(G, rng, d):
    """A horizontal wall with gaps, brick or steel."""
    r = rng.randint(3, 9)
    kind = ST if rng.random() < 0.15 + 0.35 * d else BR
    c0 = rng.randint(0, 2)
    for c in range(c0, G.cols):
        if rng.random() < 0.8:
            G.set(r, c, kind)
    if kind == ST:                          # keep gaps so the wall can be passed
        G.set(r, rng.randrange(G.cols), BR)
        G.set(r, rng.randrange(G.cols), E)


def room(G, rng, d):
    """A small brick room (outline), maybe with forest or steel in the middle."""
    h, w = rng.randint(3, 4), rng.randint(3, 4)
    r, c = rng.randint(1, N - h - 3), rng.randint(0, max(0, G.cols - w))
    for i in range(h):
        for j in range(w):
            edge = i in (0, h - 1) or j in (0, w - 1)
            if edge:
                G.set(r + i, c + j, BR)
            elif rng.random() < 0.5:
                G.set(r + i, c + j, FO if rng.random() < 0.6 else ST)
    G.set(r + h // 2, c + (0 if rng.random() < 0.5 else w - 1), E)     # a door


def grove(G, rng, d):
    """A group of forest blocks."""
    h, w = rng.randint(2, 3), rng.randint(2, 4)
    r, c = rng.randint(0, N - h - 2), rng.randint(0, max(0, G.cols - w))
    for i in range(h):
        for j in range(w):
            if rng.random() < 0.85:
                G.set(r + i, c + j, FO)


def river(G, rng, d):
    """A horizontal river with 2-3 crossings (bridges of empty, forest or ice)."""
    r = rng.choice((4, 5, 6, 7))
    for c in range(G.cols):
        G.set(r, c, WA)
    width = G.cols
    for _ in range(rng.randint(1, 2) if G.sym else rng.randint(2, 3)):
        G.set(r, rng.randrange(width), rng.choice((E, FO, IC)))
    if rng.random() < 0.4:
        for c in range(G.cols):
            if G.get(r, c) == WA and rng.random() < 0.5:
                G.set(r + 1, c, WA)


def lake(G, rng, d):
    """A small pond, often with a forest edge."""
    h, w = rng.randint(1, 2), rng.randint(2, 3)
    r, c = rng.randint(2, 8), rng.randint(0, max(0, G.cols - w))
    for i in range(h):
        for j in range(w):
            G.set(r + i, c + j, WA)
    if rng.random() < 0.6:
        for j in range(w):
            G.set(r + h, c + j, FO)


def ice(G, rng, d):
    """A wide ice field."""
    h, w = rng.randint(2, 4), rng.randint(3, 6)
    r, c = rng.randint(2, N - h - 3), rng.randint(0, max(0, G.cols - w))
    for i in range(h):
        for j in range(w):
            if G.get(r + i, c + j) == E:
                G.set(r + i, c + j, IC)


def studs(G, rng, d):
    """Single steel blocks on a regular raster."""
    off = rng.choice((0, 1))
    for r in range(2 + off, 10, 3):
        for c in range(1 + off, G.cols, 3):
            if rng.random() < 0.4 + 0.4 * d:
                G.set(r, c, ST)


def checker(G, rng, d):
    """A brick checkerboard area."""
    h, w = rng.randint(3, 5), rng.randint(3, 5)
    r, c = rng.randint(1, N - h - 3), rng.randint(0, max(0, G.cols - w))
    for i in range(h):
        for j in range(w):
            if (i + j) % 2 == 0:
                G.set(r + i, c + j, BR)


def bunker(G, rng, d):
    """A steel block with brick around it."""
    r, c = rng.randint(2, 8), rng.randint(1, max(1, G.cols - 2))
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            G.set(r + dr, c + dc, BR)
    G.set(r, c, ST)


def fort(G, rng, d):
    """Extra walls in front of the base (rows 9-10)."""
    for c in range(3, G.cols):
        if rng.random() < 0.6:
            G.set(9, c, BR if rng.random() < 0.8 else rng.choice((1, 3)))
    if rng.random() < 0.5:
        G.set(10, 2, BR)
        G.set(10, 3, BR)


MOTIFS = [(pillars, 3), (hwall, 3), (room, 3), (grove, 4), (river, 1.2), (lake, 1.5), (ice, 1),
          (studs, 1.5), (checker, 1.5), (bunker, 2), (fort, 3)]


def trim(g, rng):
    """Some brick blocks at a wall end become half bricks (finer shapes)."""
    for r in range(N):
        for c in range(N):
            if g[r][c] != BR or rng.random() > 0.3:
                continue
            open_l = c == 0 or g[r][c - 1] == E
            open_r = c == N - 1 or g[r][c + 1] == E
            open_u = r == 0 or g[r - 1][c] == E
            open_d = r == N - 1 or g[r + 1][c] == E
            if open_l and not open_r:
                g[r][c] = 0                 # right half stays
            elif open_r and not open_l:
                g[r][c] = 2
            elif open_u and not open_d:
                g[r][c] = 1
            elif open_d and not open_u:
                g[r][c] = 3


def make(stage, rng):
    d = (stage - 1) / (STAGES - 1)          # 0 .. 1: difficulty
    G = Grid(rng.random() < 0.8)
    weights = [w for _, w in MOTIFS]
    for i, (m, _) in enumerate(MOTIFS):     # water and steel more often later
        if m in (river, lake, studs, bunker):
            weights[i] *= 0.5 + 1.2 * d
    n = rng.randint(3, 5) if G.sym else rng.randint(5, 7)
    for m in rng.choices([m for m, _ in MOTIFS], weights, k=n):
        m(G, rng, d)
    g = G.done()
    if G.sym:
        trim_sym(g, rng)
    else:
        trim(g, rng)
    for r, c in KEEP_FREE:
        g[r][c] = E
    return g


def trim_sym(g, rng):
    trim(g, rng)
    for r in range(N):                      # keep the trim symmetric
        for c in range(6):
            g[r][12 - c] = MIRROR.get(g[r][c], g[r][c])


def score(g, d):
    """Higher is better. Target block mix, open spawn areas, reachable base."""
    if not reachable(g):
        return -1e9
    cells = [b for row in g for b in row]
    n = len(cells)
    frac = lambda ks: sum(b in ks for b in cells) / n
    empty, brick, steel = frac((E, IC)), frac((0, 1, 2, 3, BR)), frac((5, 6, 7, 8, ST))
    water, forest = frac((WA,)), frac((FO,))
    s = 0.0
    s -= abs(empty - (0.52 - 0.08 * d)) * 6
    s -= abs(brick - 0.22) * 5
    solid = sum(all(g[r + i][c + j] == BR for i in (0, 1) for j in (0, 1)) for r in range(N - 1) for c in range(N - 1))
    s -= solid * 0.04                       # big solid brick areas look plain
    s -= 0.3 if all(g[r][c] == E for r in (9, 10, 11) for c in range(N)) else 0
    s -= max(0, steel - (0.04 + 0.08 * d)) * 10
    s -= max(0, water - 0.10) * 10
    s -= max(0, forest - 0.18) * 6
    s -= sum(g[r][c] not in (E, IC, FO) for r, c in ROOMY) * 0.15
    if brick < 0.12:
        s -= 1
    s -= fire_lane(g)
    return s


SHOT_STOP = (0, 1, 2, 3, BR, 5, 6, 7, 8, ST)   # brick and steel stop shells; water, forest, ice do not


def fire_lane(g):
    """Penalty for an open shot line down the center column (6) to the base. An enemy that
    comes out of the top-center spawn drives straight down this column and fires at the base."""
    stops = sum(g[r][6] in SHOT_STOP for r in range(1, 11))
    steel = sum(g[r][6] in (5, 6, 7, 8, ST) for r in range(1, 11))
    if stops == 0:
        return 3.0
    if stops == 1 and not steel:
        return 0.75
    return 0.0


def enemy_wave(stage, rng):
    """20 enemies: mostly basic at first, more fast/power/armor later. Spawn order in groups."""
    d = (stage - 1) / (STAGES - 1)
    w = [max(0.08, 1.0 - 1.1 * d), 0.15 + 0.35 * d, 0.05 + 0.45 * d, 0.02 + 0.55 * d]
    if stage % 5 == 0:                      # every 5th stage: an armor-heavy wave
        w[3] += 0.3
    if stage % 7 == 3:                      # a fast-heavy wave now and then
        w[1] += 0.4
    total = sum(w)
    counts = [int(round(x / total * maps.N_ENEMIES)) for x in w]
    while sum(counts) > maps.N_ENEMIES:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < maps.N_ENEMIES:
        counts[0] += 1
    # groups: weak types first in early stages; strong first in late stages (a hard start)
    order = [0, 1, 2, 3] if d < 0.5 else rng.sample([0, 1, 2, 3], 4)
    out = []
    for t in order:
        out += [t] * counts[t]
    return out


def best_map(stage, seed, tries=400):
    rng = random.Random(seed)
    d = (stage - 1) / (STAGES - 1)
    best = max((make(stage, rng) for _ in range(tries)), key=lambda g: score(g, d))
    return best, enemy_wave(stage, rng)


def write_pack(out, only=None, seed=0):
    os.makedirs(out, exist_ok=True)
    for st in range(1, STAGES + 1):
        if only and st != only:
            continue
        g, e = best_map(st, st * 7919 + seed)
        with open(os.path.join(out, "%02d.txt" % st), "w", encoding="utf-8") as f:
            f.write(maps.format_stage(g, e, "stage %d (tools/make_maps.py, seed %d)" % (st, seed)))
    print("wrote", out)


def render_sheet(pack, path, cols=7, scale=1):
    """All stages on real terrain, small, with stage numbers."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    from assets import Assets
    from config import FIELD
    from hud import field_pos
    FIELD_X, FIELD_Y = field_pos()
    from game import World
    A = Assets(pack)
    n = A.maps.count
    pad = 14
    W, H = FIELD + 8, FIELD + pad
    rows = (n + cols - 1) // cols
    sheet = pygame.Surface((cols * W, rows * H))
    sheet.fill((40, 40, 40))
    for i in range(n):
        w = World(A, i + 1)
        for p in w.players:
            p.alive = False
        w.reserve = 0
        screen = pygame.Surface((256, 224))
        w.draw(screen)
        x, y = (i % cols) * W + 4, (i // cols) * H + pad
        sheet.blit(screen, (x, y), (FIELD_X, FIELD_Y, FIELD, FIELD))
        counts = [w.enemy_list.count(t) for t in range(4)]
        A.text(sheet, "%d  %s" % (i + 1, " ".join(map(str, counts))), x, y - 11)
    if scale != 1:
        sheet = pygame.transform.scale(sheet, (sheet.get_width() * scale, sheet.get_height() * scale))
    pygame.image.save(sheet, path)
    print("sheet:", path, "(per stage: number, then enemies basic fast power armor)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", type=int, help="make only this stage again")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sheet", help="render a contact sheet PNG")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--render-only", action="store_true")
    a = ap.parse_args()
    if not a.render_only:
        write_pack(a.out, a.only, a.seed)
    if a.sheet:
        render_sheet(a.out, a.sheet, scale=a.scale)


if __name__ == "__main__":
    main()
