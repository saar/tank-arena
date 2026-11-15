"""Logic tests (no window, no sound).

    nix develop --command python3 src/test_logic.py
"""
import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))
from assets import Assets  # noqa: E402
from config import *       # noqa: E402,F403
from game import Bullet, World     # noqa: E402

A = Assets()
keys0 = {k: False for k in ("up", "down", "left", "right", "fire")}

# 1) map pack
import maps  # noqa: E402
n = A.maps.count
assert n >= 1 and all(len(A.maps.enemy_list(s)) == ENEMIES_PER_STAGE for s in range(1, n + 1))
assert A.maps.enemy_list(n + 5) == A.maps.enemy_list(n)       # second round: the last list
assert A.maps.stage_grid(n + 1) == A.maps.stage_grid(1)
g, e = maps.parse(maps.format_stage(A.maps.stage_grid(1), A.maps.enemy_list(1), "test"))
assert g == A.maps.stage_grid(1) and e == A.maps.enemy_list(1)
print("map pack ok")

# 1b) installed packs (in a temporary data folder)
import shutil  # noqa: E402
import tempfile  # noqa: E402
import packs  # noqa: E402
tmp = tempfile.mkdtemp()
os.environ["TANK_ARENA_HOME"] = os.path.join(tmp, "home")
src = os.path.join(tmp, "p")
os.makedirs(src)
shutil.copy(os.path.join(maps.DEFAULT_PACK, "01.txt"), src)
assert packs.install(src, "t") == "t" and "t" in packs.available()
packs.save_settings(maps="t")
assert os.path.samefile(packs.resolve(None), os.path.join(packs.maps_dir(), "t"))
open(os.path.join(src, "02.txt"), "w").write("bad\n")
try:
    packs.install(src, "t2")
    raise AssertionError("a bad pack was installed")
except maps.MapError:
    pass
packs.remove("t")
assert "t" not in packs.available() and packs.load_settings()["maps"] == "default"
shutil.rmtree(tmp)
del os.environ["TANK_ARENA_HOME"]
print("installed packs ok")

# 2) long random runs on a few stages
for st in (1, 17, 35, 36):
    random.seed(st)
    w = World(A, st)
    for f in range(6000):
        k = dict(keys0)
        k[random.choice(["up", "down", "left", "right"])] = True
        k["fire"] = f % 10 < 5
        w.update(k)
        assert len([e for e in w.enemies if e.alive]) <= MAX_ENEMIES_ON_SCREEN
        if f % 500 == 0:
            w.draw(pygame.Surface((256, 224)))
        if w.lost or w.cleared:
            break
print("random runs ok")

# 3) every item (1 and 2 players)
for k in range(N_ITEMS):
    w = World(A, 1, num_players=1 + (k % 2))
    p = w.players[0]
    w.player_item(p, k)
    for _ in range(50):
        w.update(keys0)
    print(ITEM_NAMES[k], "ok", "power", p.power, "lives", p.lives)

# 4) gun and ship absorb a hit
w = World(A, 1)
p = w.players[0]
p.shield = 0
p.ship = p.gun = True
p.power = 3
p.hit(); assert p.alive and not p.ship and p.gun
p.hit(); assert p.alive and not p.gun and p.power == 2
p.hit(); assert not p.alive and p.lives == 2

# 5) forest cutting: 3 stars + gun = 0x20*3 + 0x60 = 0xC0 >= 0xA0
w = World(A, 1)
p = w.players[0]
for k in (STAR, STAR, STAR, GUN):
    w.player_item(p, k)
assert p.cut_power >= CUT_FOREST_AT

# 6) 2 players: own spawn points, 6 enemies on screen, friendly fire freezes,
#    each player gets the points for their own kills
w = World(A, 1, num_players=2)
p1, p2 = w.players
assert (p1.x, p1.y) == PLAYER_SPAWNS[0] and (p2.x, p2.y) == PLAYER_SPAWNS[1]
assert w.max_enemies == MAX_ENEMIES_2P
p2.shield = 0
p2.x, p2.y = 100.0, 100.0
assert Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit()
assert p2.alive and p2.frozen == FRIENDLY_FREEZE and p2.lives == START_LIVES
p2.frozen, p2.shield = 0, 10                         # a shield stops the freeze
Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit()
assert p2.frozen == 0
for _ in range(400):
    w.update([{"up": False, "down": False, "left": False, "right": False, "fire": False}] * 2)
e = w.enemies[0]
e.carrier, e.hp = False, 1
e.hit(p2)
assert p2.score == ENEMY_TYPES[e.etype]["score"] and p1.score == 0 and sum(p2.kills) == 1
assert w.score == p2.score
print("2 players ok")

# 7) A frozen tank cannot move but can fire; a hit does not restart the timer
w = World(A, 1, num_players=2)
p1, p2 = w.players
w.cells = [[EMPTY] * GRID for _ in range(GRID)]
p1.shield = p2.shield = 0
p2.x, p2.y = 100.0, 100.0
Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit()
p2.frozen = 50
Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit()
assert p2.frozen == 50                                 # no restart
x0 = p2.x
w.update([keys0, dict(keys0, left=True, fire=True)])
assert p2.x == x0 and len(p2.bullets()) == 1          # no move, but a shot
print("frozen fire ok")

# 8) Tanks pass each other with a small side overlap (our change); head-on still blocks
w = World(A, 1, num_players=2)
w.cells = [[EMPTY] * GRID for _ in range(GRID)]
w.enemies = []
p1, p2 = w.players
p1.x, p1.y, p1.d = 80.0, 72.0, "right"
p2.x, p2.y = 96.0, 58.0                               # 2 px into p1's lane, touching p1 after the move
assert not p1.blocked(81.0, 72.0)                      # side overlap 2 px: pass
p2.y = 64.0                                            # 8 px into the lane
assert p1.blocked(81.0, 72.0)                          # blocked
p2.x, p2.y = 90.0, 72.0                                # overlapping, p2 ahead
p1.d = "left"
assert not p1.blocked(79.0, 72.0)                      # moving apart is free
p1.d = "right"
assert p1.blocked(81.0, 72.0)                          # moving further in is blocked
print("tank passing ok")

# 9) Our new items
def empty_world(n=2):
    w = World(A, 1, num_players=n)
    w.cells = [[EMPTY] * GRID for _ in range(GRID)]
    w.enemies, w.reserve, w.spawn_timer = [], 0, 10 ** 9
    for p in w.players:
        p.shield = 0
    return w

# RESCUE: a partner out of lives comes back; else the player with fewer lives gets +1
w = empty_world()
p1, p2 = w.players
p2.lives = 1
p2.die()
assert p2.lives == 0 and not p2.alive
w.player_item(p1, RESCUE)
for _ in range(61):
    w.update(keys0)
assert p2.alive and p2.lives == 1
w.player_item(p1, RESCUE)
assert p2.lives == 2 and p1.lives == START_LIVES
assert all(k not in COOP_ITEMS for k in World(A, 1).drop_table())

# LINK: both shielded, partner shells pass through (no freeze)
w = empty_world()
p1, p2 = w.players
w.player_item(p1, LINK)
assert p1.shield and p2.shield
p2.shield = 0
p2.x, p2.y = 100.0, 100.0
assert not Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit() and not p2.frozen
w.link = 0
Bullet(w, p1, 108, 108, "up", 2, False, False).step_hit()
assert p2.frozen

# TURRET: shoots an enemy in its column, never hurts players, ends after TURRET_TIME
from game import Enemy  # noqa: E402
w = empty_world()
w.player_item(w.players[0], TURRET)
e = Enemy(w, TURRET_POS[0], TURRET_POS[1] - 64, 0, False)
w.enemies.append(e)
w.players[1].x, w.players[1].y = TURRET_POS[0] - 40.0, float(TURRET_POS[1])
for _ in range(40):
    w.update(keys0)
    w.enemies = [e]                     # keep it in place for the test
    e.x, e.y = TURRET_POS[0], TURRET_POS[1] - 64
assert w.killed == 1 or not e.alive
assert all(p.alive and not p.frozen for p in w.players)
for _ in range(TURRET_TIME):
    w.update(keys0)
assert w.turret is None

# REPAIR: broken base wall bricks come back
w = World(A, 1)
for x, y in w.BASE_WALL[:3]:
    w.cells[y][x] = EMPTY
w.player_item(w.players[0], REPAIR)
assert all(w.cells[y][x] == BRICK for x, y in w.BASE_WALL)

# MYSTERY: 2 new items appear (not MYSTERY, not on each other); each times out like any item
w = empty_world()
p = w.players[0]
p.x, p.y = 0.0, 0.0
w.items = [[MYSTERY, 0, 0, ITEM_TIME]]
w.check_item()
assert len(w.items) == MYSTERY_ITEMS and all(it[0] != MYSTERY for it in w.items)
assert len({(it[1], it[2]) for it in w.items}) == MYSTERY_ITEMS
for _ in range(ITEM_TIME):
    w.update(keys0)
assert w.items == []

print("new items ok")

# 10) Forest cutting: the shell clears the forest and flies on
w = empty_world(1)
p = w.players[0]
for y in range(4, 10):
    w.cells[y][12] = w.cells[y][13] = FOREST
b = Bullet(w, p, 104, 100, "up", 2, False, True)
w.bullets.append(b)
for _ in range(60):
    w.update(keys0)
assert all(w.cells[y][c] == EMPTY for y in range(4, 10) for c in (12, 13))
b2 = Bullet(w, p, 104, 100, "up", 2, False, False)       # no cut power: forest stays, shell flies under
w.cells[6][12] = w.cells[6][13] = FOREST
assert not b2.step_hit() and w.cells[6][12] == FOREST
print("forest cutting ok")
print("all tests pass")
