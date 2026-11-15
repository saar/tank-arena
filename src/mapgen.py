"""Random stage maps. Same model as the map packs (maps.py): a 13x13 grid of
block codes (see config.block_to_cells): 0-3 half brick, 4 brick, 5-8 half steel, 9 steel,
10 water, 11 forest, 12 ice, 13 empty.

The AI partner trains on these too, so it does not learn only the fixed maps by heart.
Every map keeps the spawn points and the base free, and enemies and players can reach the
base (brick and forest can be passed: shells break brick; steel and water block).
"""
import random

EMPTY_B = 13
# Block type weights (about half the blocks are empty)
KINDS = [((4,), 29), ((0, 1, 2, 3), 14), ((9,), 10), ((5, 6, 7, 8), 7), ((10,), 7), ((11,), 25), ((12,), 8)]
MIRROR = {0: 2, 2: 0, 5: 7, 7: 5}          # left/right halves swap in a mirrored map
KEEP_FREE = {(0, 0), (0, 6), (0, 12), (12, 4), (12, 8), (11, 5), (11, 6), (11, 7), (12, 5), (12, 6), (12, 7)}
STARTS = [(0, 0), (0, 6), (0, 12), (12, 4), (12, 8)]
GOAL = {(10, 5), (10, 6), (10, 7), (11, 4), (11, 8)}       # next to the base wall


def _kind(rng):
    codes = rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
    return rng.choice(codes)


def _open(grid, r, c):
    return grid[r][c] not in (5, 6, 7, 8, 9, 10)


def reachable(grid):
    """True if every start block reaches a block next to the base."""
    for s in STARTS:
        seen, todo = {s}, [s]
        while todo:
            r, c = todo.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (r + dr, c + dc)
                if 0 <= n[0] < 13 and 0 <= n[1] < 13 and n not in seen and _open(grid, *n):
                    seen.add(n)
                    todo.append(n)
        if not seen & GOAL:
            return False
    return True


def random_grid(rng=random):
    for _ in range(30):
        g = [[EMPTY_B] * 13 for _ in range(13)]
        mirror = rng.random() < 0.6
        density = rng.uniform(0.25, 0.55)
        cols = 7 if mirror else 13
        # walls: short lines of one kind (maps look built, not like noise)
        for _ in range(int(density * 40)):
            k = _kind(rng)
            r, c = rng.randrange(13), rng.randrange(cols)
            dr, dc = rng.choice(((1, 0), (0, 1)))
            for i in range(rng.randint(1, 5)):
                rr, cc = r + dr * i, c + dc * i
                if rr < 13 and cc < cols:
                    g[rr][cc] = k
        # single blocks
        for r in range(13):
            for c in range(cols):
                if g[r][c] == EMPTY_B and rng.random() < density * 0.3:
                    g[r][c] = _kind(rng)
        if mirror:
            for r in range(13):
                for c in range(6):
                    g[r][12 - c] = MIRROR.get(g[r][c], g[r][c])
        for r, c in KEEP_FREE:
            g[r][c] = EMPTY_B
        if reachable(g):
            return g
    for r in range(13):                     # rare: give up on steel and water
        for c in range(13):
            if not _open(g, r, c):
                g[r][c] = 4
    return g
