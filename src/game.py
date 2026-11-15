"""Core game: terrain, tanks, bullets, items, stage flow."""
import random
import pygame
from config import *
import hud


def rects_overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


DV = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


# ---------------------------------------------------------------------------
class Tank:
    def __init__(self, world, x, y, d):
        self.w = world
        self.x, self.y, self.d = float(x), float(y), d
        self.anim = 0
        self.alive = True
        self.frozen = 0
        self.shield = 0
        self.ship = False
        self.gun = False
        self.slide = 0

    @property
    def rect(self):
        return (int(round(self.x)), int(round(self.y)), 16, 16)

    def center(self):
        return self.x + 8, self.y + 8

    def bullets(self):
        return [b for b in self.w.bullets if b.owner is self]

    def turn(self, d):
        if d == self.d:
            return
        if (d in ("up", "down")) != (self.d in ("up", "down")):
            # On a 90 degree turn, snap to the 8 px grid.
            if d in ("up", "down"):
                self.x = round(self.x / CELL) * CELL
            else:
                self.y = round(self.y / CELL) * CELL
        self.d = d

    def blocked(self, x, y):
        r = (int(round(x)), int(round(y)), 16, 16)
        if r[0] < 0 or r[1] < 0 or r[0] > FIELD - 16 or r[1] > FIELD - 16:
            return True
        w = self.w
        for cy in range(r[1] // CELL, (r[1] + 15) // CELL + 1):
            for cx in range(r[0] // CELL, (r[0] + 15) // CELL + 1):
                t = w.cells[cy][cx]
                if t in (BRICK, STEEL) or (t == WATER and not self.ship):
                    return True
        if rects_overlap(r, (*HQ_POS, 16, 16)):
            return True
        dx, dy = DV[self.d]
        for o in w.all_tanks():
            if o is self or not o.alive:
                continue
            q = o.rect
            if not rects_overlap(r, q):
                continue
            toward = (dx > 0 and q[0] > self.x) or (dx < 0 and q[0] < self.x) or \
                     (dy > 0 and q[1] > self.y) or (dy < 0 and q[1] < self.y)
            if not toward:                  # moving apart (or on top of each other): free
                continue
            if dx:
                side = min(r[1], q[1]) + 16 - max(r[1], q[1])
            else:
                side = min(r[0], q[0]) + 16 - max(r[0], q[0])
            if side > TANK_PASS_OVERLAP:    # our change: small side overlaps can pass
                return True
        return False

    def move(self, dist):
        """Move forward; return False if blocked."""
        dx, dy = DV[self.d]
        moved = False
        while dist > 0:
            step = min(1.0, dist)
            nx, ny = self.x + dx * step, self.y + dy * step
            if self.blocked(nx, ny):
                return moved
            self.x, self.y = nx, ny
            dist -= step
            moved = True
        self.anim ^= 1
        return True

    def on_ice(self):
        cx, cy = int(self.x + 8) // CELL, int(self.y + 8) // CELL
        return self.w.cells[min(cy, GRID - 1)][min(cx, GRID - 1)] == ICE

    def fire(self, speed, max_bullets, steel, cut):
        if len(self.bullets()) >= max_bullets:
            return
        cx, cy = self.center()
        dx, dy = DV[self.d]
        self.w.bullets.append(Bullet(self.w, self, cx + dx * 6, cy + dy * 6, self.d, speed, steel, cut))
        if self.side == "player":
            self.w.sound("fire")


class Player(Tank):
    def __init__(self, world, idx, lives):
        super().__init__(world, *PLAYER_SPAWNS[idx], "up")
        self.idx = idx                  # 0 = player 1, 1 = player 2
        self.lives = lives
        self.score = 0
        self.kills = [0, 0, 0, 0]       # shot kills per enemy type, this stage (tally)
        self.extra_life_given = False
        self.power = 0
        self.stuck = 0
        self.cut_power = 0          # bullets cut forest at CUT_FOREST_AT
        self.respawn = 0
        self.side = "player"
        self.fire_held = False
        self.moving = False

    def spawn(self, power):
        self.x, self.y, self.d = float(PLAYER_SPAWNS[self.idx][0]), float(PLAYER_SPAWNS[self.idx][1]), "up"
        self.alive = True
        self.frozen = self.respawn = 0
        self.power = power
        self.cut_power = 0
        self.ship = self.gun = False
        self.shield = max(SPAWN_SHIELD, self.w.link)
        self.w.effects.append(Effect(self.w.assets.sparkle, self.x, self.y, 4, loops=2))

    def update(self, keys):
        if not self.alive:
            if self.respawn > 0:
                self.respawn -= 1
                if self.respawn == 0:
                    self.spawn(0)
            return
        if self.shield:
            self.shield -= 1
        if self.frozen:                     # no move, but fire still works
            self.frozen -= 1
            self.moving = False
            self.stuck = 0
        else:
            want = None
            for d in ("up", "down", "left", "right"):
                if keys[d]:
                    want = d
                    break
            self.moving = bool(want)
            if want:
                x0, y0 = self.x, self.y
                self.turn(want)
                self.move(PLAYER_SPEED)
                # frames in a row with a direction held but no movement (the AI partner sees it)
                self.stuck = self.stuck + 1 if (self.x, self.y) == (x0, y0) else 0
                self.slide = ICE_SLIDE if self.on_ice() else 0
            else:
                self.stuck = 0
                if self.slide:
                    self.slide -= 1
                    self.move(PLAYER_SPEED)
        if keys["fire"] and not self.fire_held:
            spd, n, steel = PLAYER_POWER[self.power]
            cut = self.cut_power >= CUT_FOREST_AT
            self.fire(spd, n, steel, cut)
        self.fire_held = keys["fire"]

    def hit(self, by=None):
        if not self.alive or self.shield:
            return
        if by is not None and by.side == "player":    # partner's bullet: freeze
            if not self.frozen:                       # a frozen tank: the timer does not restart
                self.frozen = FRIENDLY_FREEZE
            self.moving = False
            return
        if self.ship:                       # the ship absorbs one hit
            self.ship = False
            self.w.sound("armor")
            return
        if self.gun:                        # the gun absorbs one hit, drop to 2 stars
            self.gun = False
            self.w.sound("armor")
            self.power = 2
            return
        self.die()

    def die(self):
        self.alive = False
        self.moving = False
        self.stuck = 0
        self.w.sound("player_boom")
        self.w.boom(self.x, self.y)
        self.lives -= 1
        if self.lives > 0:
            self.respawn = 60

    def sprite(self):
        kind = min(self.power, 3)
        return self.w.assets.tank(kind, self.d, self.anim, "player2" if self.idx else "player")


class Enemy(Tank):
    def __init__(self, world, x, y, etype, carrier):
        super().__init__(world, x, y, "down")
        self.etype = etype
        self.info = ENEMY_TYPES[etype]
        self.hp = self.info["hp"]
        self.carrier = carrier
        self.side = "enemy"
        self.think = random.randint(30, 90)

    def choose_dir(self):
        w = self.w
        r = random.random()
        if r < 0.45:                         # head for the base
            if self.y < HQ_POS[1] - 16:
                d = "down"
            else:
                d = "left" if self.x > HQ_POS[0] else "right"
        elif r < 0.6 and w.players_alive():
            p = random.choice(w.players_alive())
            dx, dy = p.x - self.x, p.y - self.y
            d = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
        else:
            d = random.choice(list(DV))
        self.turn(d)

    def update(self):
        if self.w.enemy_freeze:
            return
        spd = self.info["speed"]
        ok = self.move(spd)
        self.think -= 1
        aligned = int(self.x) % CELL == 0 and int(self.y) % CELL == 0
        if not ok or (self.think <= 0 and aligned):
            self.choose_dir()
            self.think = random.randint(40, 160)
        if random.random() < ENEMY_FIRE_CHANCE:
            self.fire(self.info["bullet"], 1, False, False)

    def hit(self, by=None):
        w = self.w
        if self.carrier:
            self.carrier = False
            w.drop_item()
        self.hp -= 1
        if self.hp > 0:
            w.sound("armor")
        if self.hp <= 0:
            self.alive = False
            w.sound("explode")
            w.boom(self.x, self.y)
            w.popups.append([w.assets.score[self.info["score"]], self.x, self.y, 40])
            w.killed += 1
            if isinstance(by, Player):
                by.score += self.info["score"]
                by.kills[self.etype] += 1

    def sprite(self):
        f = self.w.frame
        if self.carrier and (f // 8) % 2 == 0:
            pal = "red"
        elif self.hp >= 4:
            pal = "green"
        elif self.hp == 3:
            pal = "gold"
        elif self.hp == 2:
            pal = "white"
        else:
            pal = "enemy"
        return self.w.assets.tank(4 + self.etype, self.d, self.anim, pal)


# ---------------------------------------------------------------------------
class Turret:
    """Our change (TURRET item): a fixed gun above the base. Not a tank: nothing hits it,
    and tanks and shells pass over it. It shoots enemies in its row or column."""
    side = "turret"

    def __init__(self, world):
        self.w = world
        self.x, self.y = TURRET_POS
        self.d = "up"
        self.time = TURRET_TIME
        self.reload = 0
        self.alive = True

    @property
    def rect(self):
        return (self.x, self.y, 16, 16)

    def center(self):
        return self.x + 8, self.y + 8

    def target(self):
        """Direction to the nearest enemy in line (up, left or right), or None."""
        cx, cy = self.center()
        best = None
        for e in self.w.enemies:
            if not e.alive:
                continue
            ex, ey = e.center()
            if abs(ex - cx) <= TURRET_AIM and cy - TURRET_RANGE <= ey < cy:
                d, dist = "up", cy - ey
            elif abs(ey - cy) <= TURRET_AIM and abs(ex - cx) <= TURRET_RANGE:
                d, dist = ("left" if ex < cx else "right"), abs(ex - cx)
            else:
                continue
            if best is None or dist < best[1]:
                best = (d, dist)
        return best and best[0]

    def update(self):
        self.time -= 1
        if self.reload:
            self.reload -= 1
        d = self.target()
        if d:
            self.d = d
            if not self.reload and not any(b.owner is self for b in self.w.bullets):
                cx, cy = self.center()
                dx, dy = DV[d]
                self.w.bullets.append(Bullet(self.w, self, cx + dx * 8, cy + dy * 8, d, TURRET_BULLET,
                                             False, False))
                self.w.sound("fire")
                self.reload = TURRET_RELOAD
        return self.time > 0


class Bullet:
    def __init__(self, world, owner, x, y, d, speed, steel, cut):
        self.w, self.owner = world, owner
        self.x, self.y, self.d = x, y, d
        self.speed, self.steel, self.cut = speed, steel, cut
        self.alive = True

    @property
    def rect(self):
        return (int(self.x) - 2, int(self.y) - 2, 4, 4)

    def update(self):
        dx, dy = DV[self.d]
        for _ in range(int(self.speed)):
            self.x += dx
            self.y += dy
            if self.step_hit():
                self.alive = False
                return

    def step_hit(self):
        w = self.w
        r = self.rect
        mine = self.owner.side == "player"
        if r[0] < 0 or r[1] < 0 or r[0] + 4 > FIELD or r[1] + 4 > FIELD:
            if mine:
                w.sound("hit_steel")
            w.small_boom(self.x, self.y)
            return True
        # terrain
        hit_cells = []
        for cy in range(r[1] // CELL, (r[1] + 3) // CELL + 1):
            for cx in range(r[0] // CELL, (r[0] + 3) // CELL + 1):
                t = w.cells[cy][cx]
                if t in (BRICK, STEEL):
                    hit_cells.append((cx, cy))
                elif t == FOREST and self.cut:      # our change: cut the forest and fly on
                    self.damage_band((cx, cy), FOREST)
        if hit_cells:
            if mine:
                steel = any(w.cells[y][x] == STEEL for x, y in hit_cells)
                if steel and not self.steel:
                    w.sound("hit_steel")        # no damage: metal clank
                else:
                    w.sound("break_steel" if steel else "hit_brick")
            self.damage_band(hit_cells[0])
            w.small_boom(self.x, self.y)
            return True
        # hq
        if w.hq_alive and rects_overlap(r, (*HQ_POS, 16, 16)):
            w.hq_alive = False
            w.sound("base_boom")
            w.boom(*HQ_POS)
            return True
        # tanks
        side = self.owner.side
        for t in w.all_tanks():
            if t.side == "player" and (side == "turret" or (side == "player" and w.link)):
                continue                    # turret shells and LINK: pass through players
            if t.alive and t is not self.owner and (t.side != side or t.side == "player") \
                    and rects_overlap(r, t.rect):
                t.hit(self.owner)
                w.small_boom(self.x, self.y)
                return True
        # other side's bullets cancel
        for b in w.bullets:
            if b is not self and b.alive and b.owner.side != side and "enemy" in (side, b.owner.side) \
                    and rects_overlap(r, b.rect):
                b.alive = False
                return True
        return False

    def damage_band(self, cell, only=None):
        """Destroy a 16 px wide band (2 quarter cells) at the impact row/column.
        only: destroy only this terrain (forest cutting)."""
        w = self.w
        cx, cy = cell
        if self.d in ("up", "down"):
            c0 = (int(self.x) - 8) // CELL
            targets = [(c, cy) for c in (c0, c0 + 1)]
        else:
            r0 = (int(self.y) - 8) // CELL
            targets = [(cx, r) for r in (r0, r0 + 1)]
        for x, y in targets:
            if 0 <= x < GRID and 0 <= y < GRID:
                t = w.cells[y][x]
                if only is not None and t != only:
                    continue
                if t == BRICK or (t == STEEL and self.steel) or (t == FOREST and self.cut):
                    w.cells[y][x] = EMPTY


class Effect:
    def __init__(self, frames, x, y, speed, loops=1):
        self.frames, self.x, self.y, self.speed = frames, x, y, speed
        self.t = 0
        self.total = len(frames) * speed * loops

    def update(self):
        self.t += 1
        return self.t < self.total

    def image(self):
        return self.frames[(self.t // self.speed) % len(self.frames)]


# ---------------------------------------------------------------------------
DIGITS_3X5 = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111",
    "3": "111001011001111", "4": "101101111001001", "5": "111100111001111",
    "6": "111100111101111", "7": "111001001010010", "8": "111101111101111",
    "9": "111101111001111",
}


def draw_small_number(surf, n, right, y, color=(0, 0, 0)):
    """Small 3x5 digits, right-aligned at x = right."""
    s = str(n)
    x = right - len(s) * 4 + 1
    for ch in s:
        bits = DIGITS_3X5[ch]
        for i, b in enumerate(bits):
            if b == "1":
                surf.fill(color, (x + i % 3, y + i // 3, 1, 1))
        x += 4


class World:
    BASE_WALL = [(11, 23), (12, 23), (13, 23), (14, 23), (11, 24), (14, 24), (11, 25), (14, 25)]

    def __init__(self, assets, stage, players=None, num_players=1, grid=None):
        """grid: a 13x13 block map (mapgen.random_grid) instead of the stage map."""
        self.assets = assets
        self.grid = grid
        self.enemy_list = assets.maps.enemy_list(stage)
        self.spawned = 0
        self.stage = stage
        self.frame = 0
        self.load_map()
        self.bullets, self.effects, self.popups = [], [], []
        self.enemies = []
        self.reserve = ENEMIES_PER_STAGE
        self.killed = 0
        self.spawn_timer = 30
        self.spawn_point = 0
        self.pending_spawns = []          # [(frames_left, x, y)]
        self.enemy_freeze = 0
        self.shovel = 0
        self.link = 0                     # our change: LINK item timer
        self.turret = None                # our change: TURRET item
        self.items = []                   # [[type, x, y, timer], ...] (more than 1 after MYSTERY)
        self.sfx = set()                  # sound events this frame (main.py plays them)
        self.hq_alive = True
        if players is None:
            self.players = [Player(self, i, START_LIVES) for i in range(num_players)]
            for p in self.players:
                p.spawn(0)
        else:
            self.players = players
            for p in players:
                p.w = self
                p.kills = [0, 0, 0, 0]
                if p.alive:
                    keep = (p.power, p.cut_power, p.ship, p.gun)
                    p.spawn(p.power)
                    p.power, p.cut_power, p.ship, p.gun = keep
                elif p.lives > 0:             # died in the clear delay: comes back
                    p.spawn(0)
        self.carriers = CARRIERS          # which enemies drop an item (the AI training uses more)
        self.max_enemies = MAX_ENEMIES_2P if len(self.players) > 1 else MAX_ENEMIES_ON_SCREEN

    @property
    def score(self):
        """Total of all players (for the hi-score)."""
        return sum(p.score for p in self.players)

    def load_map(self):
        grid = self.grid or self.assets.maps.stage_grid(self.stage)
        self.cells = [[EMPTY] * GRID for _ in range(GRID)]
        for r in range(13):
            for c in range(13):
                q = block_to_cells(grid[r][c])
                for i in range(4):
                    self.cells[r * 2 + i // 2][c * 2 + i % 2] = q[i]
        for x, y in [(12, 24), (13, 24), (12, 25), (13, 25)]:
            self.cells[y][x] = EMPTY
        self.set_base_wall(BRICK)

    def set_base_wall(self, t):
        for x, y in self.BASE_WALL:
            self.cells[y][x] = t

    def sound(self, name):
        self.sfx.add(name)

    def all_tanks(self):
        return self.players + self.enemies

    def players_alive(self):
        return [p for p in self.players if p.alive]

    def boom(self, x, y):
        self.effects.append(Effect(self.assets.boom_frames, x - 8, y - 8, 6))

    def small_boom(self, x, y):
        self.effects.append(Effect(self.assets.explo[:1], x - 8, y - 8, 6))

    # ---- items ---------------------------------------------------------------
    def drop_table(self):
        if len(self.players) > 1:
            return DROP_TABLE
        return [k for k in DROP_TABLE if k not in COOP_ITEMS]

    def drop_item(self):
        """A carrier was hit: a new item replaces the items on the field (one item slot)."""
        self.items = []
        self.add_item(random.choice(self.drop_table()))

    def add_item(self, kind):
        # X and Y each from 4 spots (16 places). Try again while a player is
        # within 12 px. ITEM_AVOID_BLOCKED also rejects spots that are mostly
        # steel or water.
        for _ in range(40):
            x, y = random.choice(ITEM_SPOTS), random.choice(ITEM_SPOTS)
            if any(abs(p.x - x) < 12 and abs(p.y - y) < 12 for p in self.players_alive()):
                continue
            if any(it[1] == x and it[2] == y for it in self.items):     # MYSTERY: not on another item
                continue
            if ITEM_AVOID_BLOCKED:
                cx, cy = x // CELL, y // CELL
                blocked = sum(self.cells[cy + j][cx + i] in (STEEL, WATER) for i in (0, 1) for j in (0, 1))
                if blocked >= 3:
                    continue
            break
        self.items.append([kind, x, y, ITEM_TIME])
        self.sound("item_appear")

    def check_item(self):
        for it in self.items[:]:
            kind, x, y, _ = it
            for t in self.players_alive():
                if rects_overlap(t.rect, (x, y, 16, 16)):
                    self.items.remove(it)
                    self.sound("extra_life" if kind in (TANK, RESCUE) else "item_get")
                    self.player_item(t, kind)
                    t.score += 500
                    break

    def player_item(self, p, k):
        if k == HELMET:
            p.shield = HELMET_TIME
        elif k == CLOCK:
            self.enemy_freeze = CLOCK_TIME
        elif k == SHOVEL:
            self.shovel = SHOVEL_TIME
            self.set_base_wall(STEEL)
        elif k == STAR:
            p.power = min(3, p.power + 1)
            p.cut_power += CUT_STAR
        elif k == GRENADE:
            for e in self.enemies:
                if e.alive:
                    e.alive = False
                    self.boom(e.x, e.y)
                    self.killed += 1
        elif k == TANK:
            p.lives += 1
        elif k == GUN:
            p.power, p.gun = 3, True
            p.cut_power += CUT_GUN
        elif k == SHIP:
            p.ship = True
        elif k == RESCUE:
            mate = next((q for q in self.players if q is not p), None)
            if mate is not None and mate.lives <= 0 and not mate.alive:
                mate.lives, mate.respawn = 1, 60          # back in the game
            else:
                (mate if mate is not None and mate.lives < p.lives else p).lives += 1
        elif k == LINK:
            self.link = LINK_TIME
            for q in self.players_alive():
                q.shield = max(q.shield, LINK_TIME)
        elif k == TURRET:
            self.turret = Turret(self)
        elif k == REPAIR:
            for x, y in self.BASE_WALL:
                if self.cells[y][x] == EMPTY:
                    self.cells[y][x] = BRICK
        elif k == MYSTERY:
            for _ in range(MYSTERY_ITEMS):
                self.add_item(random.choice([q for q in self.drop_table() if q != MYSTERY]))

    # ---- spawning ------------------------------------------------------------
    def update_spawns(self):
        for s in self.pending_spawns[:]:
            s[0] -= 1
            if s[0] <= 0:
                self.pending_spawns.remove(s)
                self.spawned += 1
                carrier = self.spawned in self.carriers
                etype = self.enemy_list[self.spawned - 1]
                self.enemies.append(Enemy(self, s[1], s[2], etype, carrier))
        live = len([e for e in self.enemies if e.alive]) + len(self.pending_spawns)
        if self.reserve > 0 and live < self.max_enemies:
            self.spawn_timer -= 1
            if self.spawn_timer <= 0:
                for _ in range(3):
                    x, y = ENEMY_SPAWNS[self.spawn_point]
                    self.spawn_point = (self.spawn_point + 1) % 3
                    if not any(t.alive and rects_overlap((x, y, 16, 16), t.rect) for t in self.all_tanks()):
                        self.reserve -= 1
                        self.pending_spawns.append([60, x, y])
                        self.effects.append(Effect(self.assets.sparkle, x, y, 4, loops=4))
                        break
                self.spawn_timer = spawn_delay(self.stage, len(self.players))

    # ---- main tick ---------------------------------------------------------
    def update(self, keys):
        """keys: one dict (all players) or a list with one dict per player."""
        if isinstance(keys, dict):
            keys = [keys] * len(self.players)
        self.frame += 1
        if self.enemy_freeze:
            self.enemy_freeze -= 1
        if self.shovel:
            self.shovel -= 1
            if self.shovel == 0:
                self.set_base_wall(BRICK)
            elif self.shovel < 3 * FPS:
                self.set_base_wall(STEEL if (self.shovel // 15) % 2 else BRICK)
        if self.link:
            self.link -= 1
        if self.turret and not self.turret.update():
            self.turret = None
        for p, k in zip(self.players, keys):
            p.update(k)
        for e in self.enemies:
            if e.alive:
                e.update()
        self.enemies = [e for e in self.enemies if e.alive]
        for b in self.bullets:
            if b.alive:
                b.update()
        self.bullets = [b for b in self.bullets if b.alive]
        self.update_spawns()
        self.check_item()
        for p in self.players:                # one extra tank per player
            if not p.extra_life_given and p.score >= EXTRA_LIFE_AT and self.hq_alive:
                p.extra_life_given = True
                p.lives += 1
                self.sound("extra_life")
        for it in self.items:
            it[3] -= 1
        self.items = [it for it in self.items if it[3] > 0]
        self.effects = [e for e in self.effects if e.update()]
        for p in self.popups:
            p[3] -= 1
        self.popups = [p for p in self.popups if p[3] > 0]

    @property
    def cleared(self):
        return self.reserve == 0 and not self.pending_spawns and not self.enemies

    @property
    def lost(self):
        return not self.hq_alive or all(p.lives <= 0 and not p.alive for p in self.players)

    # ---- drawing -------------------------------------------------------------
    def draw(self, surf):
        A = self.assets
        surf.fill(hud.BG)
        field = pygame.Surface((FIELD, FIELD))
        field.fill((0, 0, 0))
        water = A.bg["water"][(self.frame // 16) % 2]
        tiles = {BRICK: A.bg["brick"], STEEL: A.bg["steel"], WATER: water, ICE: A.bg["ice"]}
        for y in range(GRID):
            row = self.cells[y]
            for x in range(GRID):
                t = tiles.get(row[x])
                if t:
                    field.blit(t, (x * CELL, y * CELL))
        field.blit(A.hq if self.hq_alive else A.hq_dead, HQ_POS)
        if self.turret and (self.turret.time > 3 * FPS or (self.frame // 8) % 2):
            tr = self.turret
            field.blit(A.turret[tr.d], tr.rect[:2])
        for t in self.all_tanks():
            if t.alive:
                if t.side == "player" and t.frozen and (self.frame // 8) % 2:
                    continue                  # a frozen player blinks
                field.blit(t.sprite(), t.rect[:2])
                if t.shield:
                    field.blit(A.shield[(self.frame // 4) % 2], t.rect[:2])
                if t.ship:
                    pygame.draw.line(field, (60, 188, 252), (t.rect[0], t.rect[1] + 15), (t.rect[0] + 15, t.rect[1] + 15))
        alive = self.players_alive()
        if self.link and len(alive) == 2 and (self.link > 2 * FPS or (self.frame // 6) % 2):
            (ax, ay), (bx, by) = alive[0].center(), alive[1].center()
            n = max(1, int(max(abs(bx - ax), abs(by - ay)) // 4))
            for i in range(n + 1):           # dotted line between the linked players
                if (i + self.frame // 3) % 2:
                    field.fill((120, 200, 252), (int(ax + (bx - ax) * i / n), int(ay + (by - ay) * i / n), 2, 2))
        for b in self.bullets:
            field.blit(A.bullet[b.d], (int(b.x) - 4, int(b.y) - 4))
        for y in range(GRID):
            for x in range(GRID):
                if self.cells[y][x] == FOREST:
                    field.blit(A.bg["forest"], (x * CELL, y * CELL))
        for it in self.items:
            if it[3] > 3 * FPS or (self.frame // 8) % 2:
                field.blit(A.items[it[0]], it[1:3])
        for e in self.effects:
            field.blit(e.image(), (int(e.x), int(e.y)))
        for img, x, y, _ in self.popups:
            field.blit(img, (int(x), int(y)))
        surf.blit(field, hud.field_pos())
        hud.draw_panel(self, surf)
