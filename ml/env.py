"""Training environment for the AI partner (no torch here: worker processes stay small).

One TankEnv = one World with 2 players. Each step = FRAME_SKIP game frames.
Slot 0 = player 1, slot 1 = player 2. In "self" mode the policy drives both
players (self-play); in the other modes a simple bot drives player 1 and the
policy learns as player 2 (the seat it takes next to a human).
"""
import os
import random
import types
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
import pygame  # noqa: E402

import game  # noqa: E402
from config import *  # noqa: E402,F403
from game import DV, World, rects_overlap  # noqa: E402
from mapgen import random_grid  # noqa: E402

ART_DIR = os.path.join(HERE, "..", "art")

FRAME_SKIP = 4                      # game frames per decision
DIRS = ("up", "down", "left", "right")
ACTIONS = [(d, f) for f in (False, True) for d in (None,) + DIRS]   # 10 actions
N_ACTIONS = len(ACTIONS)
N_BASE_CH = 17                      # one moment: terrain, hq, tanks, shells, items, spawns
DYN_CH = slice(6, 17)               # the channels that move: me .. spawns (11)
MEM_STEPS = (2, 4)                  # v8 memory: the moving channels from 2 and 4 steps (8, 16 frames) ago
N_CH = N_BASE_CH + 11 * len(MEM_STEPS)  # 39 (v7 and older: 17)
N_ENEMY, N_BULLET = 6, 4
N_EXTRA = 23                        # v4: link, turret, my shells cut forest, partner lives
                                    # v5: I am stuck, partner power, gun, ship, shield
                                    # v6: nearest item: its gain for me, for the partner, partner's item
                                    # v7: a shot now (facing direction) could hit the partner
                                    # v8: my last action (one-hot, 10)
N_VEC = 15 + 9 + 5 + 3 + N_ITEMS + N_ENEMY * 15 + N_BULLET * 7 + N_EXTRA
# v3 layout (158): item one-hot had 8 entries. model.upgrade() maps v3 weights to this layout.
V3_N_VEC = 158
V3_ITEM_END = 40                    # end of the old 8-entry item one-hot
V4_N_VEC = 167                      # v4 layout: v5 and v6 only add inputs at the end
V5_N_VEC = 172
V6_N_VEC = 175
V7_N_VEC = 176
MAX_STEPS = 4000                    # 16000 frames (4.4 min) per episode

# Rewards
R_KILL = 1.0
R_PARTNER_KILL = 0.3                # team spirit: the partner's kill also counts a little
R_DEATH = -2.5                      # v4: was -1. Staying alive matters: 2 players are much stronger
R_ITEM = 1.5                        # v4: was 0.5 (the model often let items time out)
R_ITEM_NEAR = 0.5                   # v4: per FIELD px closer to the nearest item (back = minus: no farming)
R_COOP_ITEM = 1.0                   # v4: extra for a team item (rescue, link): help the human partner
R_FREEZE_PARTNER = -3.0             # friendly fire (v4: -2, v7: -3; a frozen partner is out for 3.3 s)
R_RISKY_SHOT = -0.3                 # v7: firing a shell whose path could hit the partner (felt at once,
                                    # even when it misses: clearer than the freeze alone)
R_HQ_LOST = -3.0
R_HQ_OWN_SHOT = -2.0             # extra, if this player shot the hq
R_OWN_BASE_WALL = -0.1              # per base-wall cell destroyed by this player
R_CLEAR = 3.0
# Defence (v2): the v1 model hunted well but let enemies reach the hq.
BASE_ZONE = 64                      # px from the hq center (4 blocks): "near the base"
R_KILL_NEAR_BASE = 0.5              # extra for a kill in the base zone
R_BASE_DANGER = -0.02               # team, per enemy in the base zone, per step
R_TURN = -0.005                     # per change of the held direction: less twitchy play (v2)
R_WASTED_SHOT = -0.01               # v4: a shell that ends on steel it cannot break or on the map edge
# v5
STUCK_FRAMES = 8                    # a direction held this long with no movement = stuck (wall, steel)
R_STUCK = -0.02                     # per step while stuck on steel, water, edge or a tank (not brick)
R_POWER = 0.5                       # per power level, gun or ship gained (lost: the same minus)
R_MATE_POWER = 0.5                  # the partner's power change counts too (v6: was 0.25)
R_PARTNER_ITEM = -0.75              # v6: per power step, taking a star/gun/ship the partner needs more
R_GRENADE_KILL = 0.5                # per enemy a grenade I took destroys (no kill credit in the game)
POWER_ITEMS = (STAR, GUN, SHIP)

# Partner (player 1) per episode. "past": a frozen older model from the pool in train.py
# (a smart partner that does not adapt to the learner, closer to a human; v3).
MODES = {"self": 0.30, "past": 0.25, "bot": 0.15, "random": 0.05, "idle": 0.25}

# Held out: training never plays these stages of the default map pack, so benchmark.py can test maps the AI has never
# seen (a future new map is such a map).
HOLDOUT_STAGES = (5, 12, 19, 26, 33)

# Variety (v4), so the model does not learn a few situations by heart:
GEN_MAPS = 0.5                      # part of the episodes on a random map (src/mapgen.py)
START_POWER = [0.6, 0.15, 0.12, 0.13]   # start power level 0..3 (each player, per episode)
START_GUN, START_SHIP = 0.05, 0.08
MORE_ITEMS = 0.5                    # part of the episodes with 6 item carriers (not 3)
HQ_C = (HQ_POS[0] + 8, HQ_POS[1] + 8)


def item_gain(p, k):
    """Power steps (levels, gun, ship) that power item k gives player p (0: no use)."""
    if not p.alive or k not in POWER_ITEMS:
        return 0
    if k == STAR:
        return int(p.power < 3)
    if k == GUN:
        return (3 - p.power) + (not p.gun)
    return int(not p.ship)


def partners_item(me, mate, k):
    """True if the partner needs power item k more than me (or the same, and the partner is weaker):
    the AI leaves it for the partner (v6)."""
    gm, gq = item_gain(me, k), item_gain(mate, k)
    return gq > 0 and (gq > gm or (gq == gm and power_value(mate) < power_value(me)))


def power_value(p):
    """Power levels + gun + ship: what a player loses when hit or killed."""
    return p.power + p.gun + p.ship


def brick_ahead(p):
    """True if brick blocks p's way (driving into it while shooting it is fine)."""
    dx, dy = DV[p.d]
    x, y = int(round(p.x)) + dx, int(round(p.y)) + dy
    cells = p.w.cells
    for cy in range(max(0, y // CELL), min(GRID - 1, (y + 15) // CELL) + 1):
        for cx in range(max(0, x // CELL), min(GRID - 1, (x + 15) // CELL) + 1):
            if cells[cy][cx] == BRICK:
                return True
    return False


def near_base(x, y):
    """x, y: tank top-left (px)."""
    return max(abs(x + 8 - HQ_C[0]), abs(y + 8 - HQ_C[1])) < BASE_ZONE


def init_pygame():
    """Headless pygame for training (the game itself does not call this)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.display.init()
    pygame.display.set_mode((1, 1))


def load_assets(maps=None):
    """maps: a pack name or folder (None: the built-in default pack, not the title-screen choice)."""
    from assets import Assets
    from packs import resolve
    return Assets(resolve(maps) if maps else None, ART_DIR)


# ---- hooks: who shot the hq / the base wall --------------------------------
_orig_step_hit = game.Bullet.step_hit
_orig_band = game.Bullet.damage_band


def _wasted(self):
    """True if the shell is now at the map edge, or on steel it cannot break (and no brick)."""
    r = self.rect
    if r[0] < 0 or r[1] < 0 or r[0] + 4 > FIELD or r[1] + 4 > FIELD:
        return True
    cells = {self.w.cells[cy][cx] for cy in range(r[1] // CELL, (r[1] + 3) // CELL + 1)
             for cx in range(r[0] // CELL, (r[0] + 3) // CELL + 1)}
    return STEEL in cells and BRICK not in cells and not self.steel


def _step_hit(self):
    w = self.w
    hq = w.hq_alive
    wasted = self.owner.side == "player" and _wasted(self)
    r = _orig_step_hit(self)
    if hq and not w.hq_alive:
        w.ml_hq_killer = self.owner
    if r and wasted:
        ws = w.__dict__.setdefault("ml_wasted", {})
        ws[self.owner.idx] = ws.get(self.owner.idx, 0) + 1
    return r


def _base_wall(w):
    return sum(w.cells[y][x] in (BRICK, STEEL) for x, y in World.BASE_WALL)


def _band(self, cell, only=None):
    w = self.w
    before = _base_wall(w)
    _orig_band(self, cell, only)
    lost = before - _base_wall(w)
    if lost > 0 and self.owner.side == "player":
        hits = w.__dict__.setdefault("ml_wall_hits", {})
        hits[self.owner.idx] = hits.get(self.owner.idx, 0) + lost


_orig_player_item = game.World.player_item


def _player_item(self, p, k):
    self.__dict__.setdefault("ml_items", []).append((p.idx, k))
    if k == GRENADE:
        g = self.__dict__.setdefault("ml_grenade", {})
        g[p.idx] = g.get(p.idx, 0) + sum(e.alive for e in self.enemies)
    _orig_player_item(self, p, k)


game.World.player_item = _player_item
_orig_fire = game.Tank.fire


def _fire(self, *a):
    n = len(self.w.bullets)
    _orig_fire(self, *a)
    if self.side == "player" and len(self.w.bullets) > n:
        f = self.w.__dict__.setdefault("ml_fired", {})
        f[self.idx] = f.get(self.idx, 0) + 1


game.Tank.fire = _fire
_orig_enemy_hit = game.Enemy.hit


def _enemy_hit(self, by=None):
    alive = self.alive
    _orig_enemy_hit(self, by)
    if alive and not self.alive and isinstance(by, game.Player) and near_base(self.x, self.y):
        nb = self.w.__dict__.setdefault("ml_base_kills", {})
        nb[by.idx] = nb.get(by.idx, 0) + 1


game.Enemy.hit = _enemy_hit
game.Bullet.step_hit = _step_hit
game.Bullet.damage_band = _band


# ---- observation -------------------------------------------------------------
def _mark(g, ch, x, y, w=16, h=16):
    x0, y0 = max(0, int(x) // CELL), max(0, int(y) // CELL)
    x1, y1 = min(GRID - 1, (int(x) + w - 1) // CELL), min(GRID - 1, (int(y) + h - 1) // CELL)
    g[ch, y0:y1 + 1, x0:x1 + 1] = 1


def _onehot(n, i):
    v = [0.0] * n
    if i is not None:
        v[i] = 1.0
    return v


class Memory:
    """The past moments one player's network sees (v8). One per world and player: call
    observe(w, idx, mem) exactly once per decision (every FRAME_SKIP frames)."""

    def __init__(self):
        self.past = []                  # moving channels of the last max(MEM_STEPS) moments
        self.last_action = None

    def add(self, g):
        dyn = g[DYN_CH]
        old = [self.past[-k] if len(self.past) >= k else (self.past[0] if self.past else dyn) for k in MEM_STEPS]
        self.past.append(dyn.copy())
        del self.past[:-max(MEM_STEPS)]
        return np.concatenate([g] + old)


def observe(w, idx, mem=None):
    """(grid uint8 [N_CH, 26, 26], vec float32 [N_VEC]) for player idx. mem: its Memory
    (None: no past, as if nothing moved)."""
    g, v = _observe_now(w, idx)
    if mem is None:
        mem = Memory()
    v = np.concatenate([v, np.asarray(_onehot(N_ACTIONS, mem.last_action), np.float32)])
    return mem.add(g), v


def _observe_now(w, idx):
    g = np.zeros((N_BASE_CH, GRID, GRID), np.uint8)
    cells = np.array(w.cells, np.int8)
    for ch, t in enumerate((BRICK, STEEL, WATER, FOREST, ICE)):
        g[ch] = cells == t
    if w.hq_alive:
        _mark(g, 5, *HQ_POS)
    me = w.players[idx]
    mate = w.players[1 - idx] if len(w.players) > 1 else None
    if me.alive:
        _mark(g, 6, me.x, me.y)
    if mate is not None and mate.alive:
        _mark(g, 7, mate.x, mate.y)
    for e in w.enemies:
        if e.alive:
            _mark(g, 8, e.x, e.y)
            if e.hp > 1:
                _mark(g, 9, e.x, e.y)
    for b in w.bullets:
        if not b.alive:
            continue
        cx, cy = min(GRID - 1, max(0, int(b.x) // CELL)), min(GRID - 1, max(0, int(b.y) // CELL))
        if b.owner.side == "enemy":
            g[10 + DIRS.index(b.d), cy, cx] = 1
        else:
            g[14, cy, cx] = 1
    for it in w.items:
        _mark(g, 15, it[1], it[2])
    for s in w.pending_spawns:
        _mark(g, 16, s[1], s[2])

    F = float(FIELD)
    mx, my = me.center()
    v = [mx / F, my / F] + _onehot(4, DIRS.index(me.d))
    v += [me.power / 3, me.shield > 0, me.frozen > 0, me.alive, min(me.lives, 5) / 5,
          me.ship, me.gun, idx, len(me.bullets()) / 2]
    if mate is not None:
        ox, oy = mate.center()
        v += [1.0, mate.alive, (ox - mx) / F, (oy - my) / F] + _onehot(4, DIRS.index(mate.d)) + [mate.frozen > 0]
    else:
        v += [0.0] * 9
    v += [w.hq_alive, w.enemy_freeze > 0, w.shovel > 0, w.reserve / 20,
          sum(e.alive for e in w.enemies) / 6]
    if w.items:                     # the nearest item (all items are on the grid)
        it = min(w.items, key=lambda i: abs(i[1] + 8 - mx) + abs(i[2] + 8 - my))
        v += [1.0, (it[1] + 8 - mx) / F, (it[2] + 8 - my) / F] + _onehot(N_ITEMS, it[0])
    else:
        v += [0.0] * (3 + N_ITEMS)
    es = []
    for e in w.enemies:
        if e.alive:
            ex, ey = e.center()
            es.append((abs(ex - mx) + abs(ey - my), ex - mx, ey - my, e))
    es.sort(key=lambda t: t[0])
    for i in range(N_ENEMY):
        if i < len(es):
            _, dx, dy, e = es[i]
            v += [1.0, dx / F, dy / F] + _onehot(4, DIRS.index(e.d)) + _onehot(4, e.etype)
            v += [e.hp / 4, e.carrier, abs(dx) < 8, abs(dy) < 8]
        else:
            v += [0.0] * 15
    bs = []
    for b in w.bullets:
        if b.alive and b.owner.side == "enemy":
            bs.append((abs(b.x - mx) + abs(b.y - my), b.x - mx, b.y - my, b))
    bs.sort(key=lambda t: t[0])
    for i in range(N_BULLET):
        if i < len(bs):
            _, dx, dy, b = bs[i]
            v += [1.0, dx / F, dy / F] + _onehot(4, DIRS.index(b.d))
        else:
            v += [0.0] * 7
    v += [w.link > 0, w.turret is not None, me.cut_power >= CUT_FOREST_AT,
          min(mate.lives, 5) / 5 if mate is not None else 0.0]
    v += [min(me.stuck, 2 * STUCK_FRAMES) / (2 * STUCK_FRAMES)]
    v += [me.alive and shell_danger(w, me, me.d) == "partner"]
    if w.items and mate is not None:
        k = it[0]
        v += [item_gain(me, k) / 4, item_gain(mate, k) / 4, partners_item(me, mate, k)]
    else:
        v += [0.0] * 3
    if mate is not None:
        v += [mate.power / 3, mate.gun, mate.ship, mate.shield > 0]
    else:
        v += [0.0] * 4
    return g, np.asarray(v, np.float32)


def shell_hits_base(w, p, d):
    return shell_danger(w, p, d) == "base"


PARTNER_MARGIN = 6                  # px beside the partner's tank that also count (it may drive in)


def shell_danger(w, p, d):
    """"base" if a shell fired now by p in direction d could hit our own hq or base wall,
    "partner" if it could freeze the partner, else None (the same path and 16 px damage band as
    game.Bullet). Bricks on the way do not protect the base: an earlier shell may break them.
    They do protect the partner. A tank on the way protects only when it is close and centered
    (it may move away before the shell arrives)."""
    dx, dy = DV[d]
    px, py = p.x, p.y
    if (d in ("up", "down")) != (p.d in ("up", "down")):      # a 90 degree turn snaps (Tank.turn)
        if d in ("up", "down"):
            px = round(px / CELL) * CELL
        else:
            py = round(py / CELL) * CELL
    cx, cy = px + 8, py + 8
    x, y = cx + dx * 6, cy + dy * 6
    base = set(w.BASE_WALL)
    tanks = [t for t in w.all_tanks() if t is not p and t.alive]
    steel = PLAYER_POWER[p.power][2]
    mate = next((q for q in w.players if q is not p and q.alive), None)
    wall = False
    found = None                        # "partner" once the path crosses the partner; the base still wins
    for _ in range(FIELD // 2 + 8):      # 2 px steps: the 4 px shell cannot skip an 8 px cell
        x, y = x + 2 * dx, y + 2 * dy
        r = (int(x) - 2, int(y) - 2, 4, 4)
        if r[0] < 0 or r[1] < 0 or r[0] + 4 > FIELD or r[1] + 4 > FIELD:
            return found
        hit = [(c, row) for row in range(r[1] // CELL, (r[1] + 3) // CELL + 1)
               for c in range(r[0] // CELL, (r[0] + 3) // CELL + 1) if w.cells[row][c] in (BRICK, STEEL)]
        if hit:
            hx, hy = hit[0]
            if d in ("up", "down"):
                c0 = (int(x) - 8) // CELL
                band = [(c0, hy), (c0 + 1, hy)]
            else:
                r0 = (int(y) - 8) // CELL
                band = [(hx, r0), (hx, r0 + 1)]
            if any(c in base and w.cells[c[1]][c[0]] in (BRICK, STEEL) for c in band):
                return "base"               # steel too: the shovel may end before the shell arrives
            if any(w.cells[row][c] == STEEL for c, row in hit) and not steel:
                return found                # steel it cannot break: the path ends here
            wall = True
        if w.hq_alive and rects_overlap(r, (*HQ_POS, 16, 16)):
            return "base"
        if mate is not None and not wall and not w.link:     # link: shells pass through the partner
            m = PARTNER_MARGIN
            q = (mate.x - m * (not dx), mate.y - m * (not dy), 16 + 2 * m * (not dx), 16 + 2 * m * (not dy))
            if rects_overlap(r, q):
                found = "partner"           # it may drive away: look further for the base
        for t in tanks:                 # only a sure hit protects: close, near the tank's middle
            if rects_overlap(r, t.rect):
                tx, ty = t.center()
                if t is not mate and abs(x - cx) + abs(y - cy) <= 24 and abs((ty - y) if dx else (tx - x)) <= 6:
                    return found
                tanks = [o for o in tanks if o is not t]     # it may move away: look further
    return found


def safe_action(w, i, a):
    """The action without fire if the shell could hit our own base (a hard rule: the AI never
    shoots its own base, in training and in the game). The partner is not protected by a rule:
    the AI must learn that (input "my shot would hit the partner", R_RISKY_SHOT, R_FREEZE_PARTNER)."""
    d, f = ACTIONS[a]
    p = w.players[i]
    if not f or not p.alive:
        return a
    shot_dir = p.d if (d is None or p.frozen) else d
    if shell_danger(w, p, shot_dir) == "base":
        return ACTIONS.index((d, False))
    return a


def action_keys(a, sub):
    """Key dict for action a on sub-frame sub (fire is pressed on sub-frame 0 only)."""
    d, f = ACTIONS[a]
    k = {n: False for n in ("up", "down", "left", "right", "fire")}
    if d:
        k[d] = True
    k["fire"] = f and sub == 0
    return k


# ---- partner bots (player 1 in the non-self modes) ------------------------------
def aims_at_hq(p, d):
    """True if a shot from p in direction d goes toward the hq."""
    px, py = p.center()
    ex, ey = HQ_POS[0] + 8, HQ_POS[1] + 8
    if d in ("left", "right"):
        return abs(py - ey) < 12 and (px < ex) == (d == "right")
    return d == "down" and abs(px - ex) < 12 and py < ey


class Bot:
    def __init__(self, kind):
        self.kind = kind
        self.a, self.t = 0, 0

    def act(self, w, idx):
        a = self._act(w, idx)
        d, f = ACTIONS[a]
        p = w.players[idx]
        if f and aims_at_hq(p, d or p.d):      # bots (like humans) do not shoot their own base
            a = ACTIONS.index((d, False))
        return a

    def _act(self, w, idx):
        p = w.players[idx]
        if self.kind == "idle" or not p.alive:
            return 0
        self.t -= 1
        if self.kind == "random":
            if self.t <= 0:
                self.a, self.t = random.randrange(N_ACTIONS), random.randint(2, 12)
            return self.a
        # "bot": shoot at aligned enemies, else wander
        px, py = p.center()
        for e in w.enemies:
            if not e.alive:
                continue
            ex, ey = e.center()
            if abs(ex - px) < 8:
                return ACTIONS.index(("down" if ey > py else "up", True))
            if abs(ey - py) < 8:
                return ACTIONS.index(("right" if ex > px else "left", True))
        if self.t <= 0 or not p.moving:
            self.a = ACTIONS.index((random.choice(DIRS), random.random() < 0.3))
            self.t = random.randint(5, 25)
        return self.a


# ---- environment ---------------------------------------------------------------
class TankEnv:
    def __init__(self, assets, stages=(1, 35), modes=None):
        self.A = assets
        self.stages = stages
        self.modes = modes or MODES

    def reset(self, stage=None, grid=None, mode=None):
        """A new episode. stage/grid/mode: fixed choices (benchmark.py); else random. Training
        never picks HOLDOUT_STAGES as a pack map."""
        fixed = stage is not None or grid is not None
        if stage is None:
            pick = [s for s in range(self.stages[0], self.stages[1] + 1) if s not in HOLDOUT_STAGES]
            stage = random.choice(pick or list(range(self.stages[0], self.stages[1] + 1)))
        self.stage = stage
        self.mode = mode or random.choices(list(self.modes), list(self.modes.values()))[0]
        self.bot = None if self.mode in ("self", "past") else Bot(self.mode)
        gen = grid is not None or (not fixed and random.random() < GEN_MAPS)
        if gen and grid is None:
            grid = random_grid()
        self.w = World(self.A, self.stage, num_players=2, grid=grid)
        if random.random() < MORE_ITEMS:
            self.w.carriers = tuple(sorted(random.sample(range(1, ENEMIES_PER_STAGE + 1), 6)))
        for p in self.w.players:
            p.power = random.choices(range(4), START_POWER)[0]
            p.cut_power = CUT_STAR * p.power
            if p.power == 3 and random.random() < START_GUN / START_POWER[3]:
                p.gun = True
                p.cut_power += CUT_GUN
            p.ship = random.random() < START_SHIP
        self.t = 0
        self.last_dir = [None, None]
        self.mem = [Memory(), Memory()]
        self.stats = dict(stage=self.stage, gen=int(gen), mode=self.mode, ret=[0.0, 0.0], kills=[0, 0],
                          freezes=[0, 0], items=[0, 0], power_items=[0, 0], partner_items=[0, 0], stuck=[0, 0],
                          base_cells=[0, 0], shells=[0, 0], wasted=[0, 0], alive_steps=[0, 0],
                          deaths=[0, 0], cleared=0, hq=0, timeout=0, steps=0)
        return self.obs()

    def nearest_item(self, p):
        """(distance px, item key) of the nearest item to live player p, or None."""
        if not p.alive or not self.w.items:
            return None
        cx, cy = p.center()
        return min((abs(it[1] + 8 - cx) + abs(it[2] + 8 - cy), (it[0], it[1], it[2])) for it in self.w.items)

    def controlled(self, i):
        return self.mode == "self" or i == 1

    def obs(self):
        w = self.w
        out = [observe(w, i, self.mem[i]) for i in (0, 1)]
        grid = np.stack([o[0] for o in out])
        vec = np.stack([o[1] for o in out])
        mask = np.array([self.controlled(i) and w.players[i].alive  # frozen tanks can still fire
                         for i in (0, 1)], bool)
        return grid, vec, mask, np.bool_(self.mode == "past")   # past: the caller drives player 1

    def step(self, acts):
        w = self.w
        acts = list(acts)
        if self.bot:
            acts[0] = self.bot.act(w, 0)
        P = w.players
        acts = [safe_action(w, i, a) for i, a in enumerate(acts)]
        for i, a in enumerate(acts):
            self.mem[i].last_action = a
        risky = [ACTIONS[a][1] and P[i].alive and
                 shell_danger(w, P[i], P[i].d if (ACTIONS[a][0] is None or P[i].frozen) else ACTIONS[a][0]) == "partner"
                 for i, a in enumerate(acts)]
        shots0 = [len(p.bullets()) for p in P]
        turned = [False, False]
        for i in (0, 1):
            d = ACTIONS[acts[i]][0]
            turned[i] = P[i].alive and d != self.last_dir[i]
            self.last_dir[i] = d
        kills0 = [sum(p.kills) for p in P]
        lives0 = [p.lives for p in P]
        frozen0 = [p.frozen for p in P]
        w.ml_wall_hits, w.ml_hq_killer, w.ml_base_kills, w.ml_items = {}, None, {}, []
        w.ml_wasted, w.ml_grenade, w.ml_fired = {}, {}, {}
        phi0 = [power_value(p) for p in P]
        pre = [types.SimpleNamespace(alive=p.alive, power=p.power, gun=p.gun, ship=p.ship) for p in P]
        near0 = [self.nearest_item(p) for p in P]
        for sub in range(FRAME_SKIP):
            w.update([action_keys(a, sub) for a in acts])
            w.sfx.clear()
            w.effects.clear()
            w.popups.clear()
            if w.lost or w.cleared:
                break
        self.t += 1
        r = np.zeros(2, np.float32)
        for i, p in enumerate(P):
            q = P[1 - i]
            dk = sum(p.kills) - kills0[i]
            r[i] += R_KILL * dk + R_PARTNER_KILL * (sum(q.kills) - kills0[1 - i])
            died = lives0[i] - p.lives
            r[i] += R_DEATH * died
            gain = power_value(p) - phi0[i]
            r[i] += R_POWER * gain + R_MATE_POWER * (power_value(q) - phi0[1 - i])
            for j, k in w.ml_items:
                if j != i:
                    continue
                self.stats["items"][i] += 1
                self.stats["power_items"][i] += k in POWER_ITEMS
                if k in POWER_ITEMS and partners_item(pre[i], pre[1 - i], k):    # v6: leave it
                    self.stats["partner_items"][i] += 1
                    r[i] += R_PARTNER_ITEM * (item_gain(pre[1 - i], k) - item_gain(pre[i], k) or 1)
                    self.stats["partner_item_taken"] = self.stats.get("partner_item_taken", 0) + 1
                elif k in POWER_ITEMS and gain <= 0:        # no use to anybody
                    pass
                else:
                    r[i] += R_ITEM
                if k in COOP_ITEMS:
                    r[i] += R_COOP_ITEM
            r[i] += R_GRENADE_KILL * w.ml_grenade.get(i, 0)
            if p.alive and p.stuck >= STUCK_FRAMES and not brick_ahead(p):
                r[i] += R_STUCK
                self.stats["stuck"][i] += 1
            self.stats["alive_steps"][i] += p.alive
            self.stats["base_cells"][i] += w.ml_wall_hits.get(i, 0)
            self.stats["shells"][i] += w.ml_fired.get(i, 0)
            if q.frozen > frozen0[1 - i]:
                r[i] += R_FREEZE_PARTNER
                self.stats["freezes"][i] += 1            # only a partner shell freezes
            if risky[i] and len(p.bullets()) > shots0[i]:     # the shell really left the gun
                r[i] += R_RISKY_SHOT
                self.stats["risky"] = self.stats.get("risky", 0) + 1
            r[i] += R_OWN_BASE_WALL * w.ml_wall_hits.get(i, 0)
            r[i] += R_KILL_NEAR_BASE * w.ml_base_kills.get(i, 0)
            r[i] += R_TURN * turned[i]
            r[i] += R_WASTED_SHOT * w.ml_wasted.get(i, 0)
            n1 = self.nearest_item(p)
            if near0[i] and n1 and near0[i][1] == n1[1] and not partners_item(p, q, n1[1][0]):
                # same item: reward getting closer (not to the partner's item, v6)
                r[i] += R_ITEM_NEAR * (near0[i][0] - n1[0]) / FIELD
            self.stats["wasted"][i] += w.ml_wasted.get(i, 0)
            if w.ml_hq_killer is p:
                r[i] += R_HQ_OWN_SHOT
            self.stats["kills"][i] += dk
            self.stats["deaths"][i] += max(0, died)          # an extra life is not a "minus death"
        danger = sum(1 for e in w.enemies if e.alive and near_base(e.x, e.y))
        r += R_BASE_DANGER * danger
        self.stats["danger"] = self.stats.get("danger", 0) + danger
        done = False
        if not w.hq_alive:
            r += R_HQ_LOST
            self.stats["hq"] = 1
            done = True
        elif w.lost:
            done = True
        elif w.cleared:
            r += R_CLEAR
            self.stats["cleared"] = 1
            done = True
        elif self.t >= MAX_STEPS:
            self.stats["timeout"] = 1
            done = True
        for i in (0, 1):
            self.stats["ret"][i] += float(r[i])
        self.stats["steps"] = self.t
        return r, done
