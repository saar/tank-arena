"""Game rules in one place. Change freely while the design evolves."""

FPS = 60
CELL = 8                    # quarter-block size (px)
GRID = 26                   # 26x26 quarter cells = 13x13 blocks
FIELD = CELL * GRID         # 208 px
SCREEN_W, SCREEN_H = 256, 224
SCALE = 3

# Terrain codes in the cell grid
EMPTY, BRICK, STEEL, WATER, FOREST, ICE = range(6)

# Map block code (maps.py) -> 4 quarter cells (TL, TR, BL, BR)
def block_to_cells(n):
    half = {0: (0, 1, 0, 1), 1: (0, 0, 1, 1), 2: (1, 0, 1, 0), 3: (1, 1, 0, 0), 4: (1, 1, 1, 1)}
    if n <= 4:
        return [BRICK if f else EMPTY for f in half[n]]
    if n <= 9:
        return [STEEL if f else EMPTY for f in half[n - 5]]
    return [{10: WATER, 11: FOREST, 12: ICE}.get(n, EMPTY)] * 4

GAME_TITLE = "TANK ARENA"

# Spawn points (px, in field)
ENEMY_SPAWNS = [(96, 0), (192, 0), (0, 0)]
PLAYER_SPAWNS = [(64, 192), (128, 192)]   # 1P left of the base, 2P right
PLAYER_SPAWN = PLAYER_SPAWNS[0]
HQ_POS = (96, 192)

ENEMIES_PER_STAGE = 20
MAX_ENEMIES_ON_SCREEN = 4
MAX_ENEMIES_2P = 6
CARRIERS = (4, 11, 18)      # these enemies flash and drop an item
START_LIVES = 3


def spawn_delay(stage, players=1):
    """Frames between enemy spawns: shorter each stage (down to stage 35), 20 less with 2 players."""
    return 190 - 4 * min(stage, 35) - (20 if players > 1 else 0)


# Enemy types: speed px/frame, bullet speed, base hp, score
ENEMY_TYPES = [
    # The fast type moves every frame, the others every 2nd frame,
    # the player on 3 of 4 frames (PLAYER_SPEED 0.75).
    dict(name="basic", speed=0.5, bullet=2, hp=1, score=100),
    dict(name="fast", speed=1.0, bullet=2, hp=1, score=200),
    dict(name="power", speed=0.5, bullet=4, hp=1, score=300),
    dict(name="armor", speed=0.5, bullet=3, hp=4, score=400),
]
ENEMY_FIRE_CHANCE = 1 / 40

PLAYER_SPEED = 0.75
# Player power level -> (bullet speed, max bullets, breaks steel)
PLAYER_POWER = {0: (2, 1, False), 1: (4, 1, False), 2: (4, 2, False), 3: (4, 2, True)}

# Timers (frames)
SPAWN_SHIELD = 3 * FPS
HELMET_TIME = 10 * FPS
CLOCK_TIME = 10 * FPS
SHOVEL_TIME = 18 * FPS
ICE_SLIDE = 20
ITEM_TIME = 20 * FPS

# Items
HELMET, CLOCK, SHOVEL, STAR, GRENADE, TANK, GUN, SHIP = range(8)
RESCUE, LINK, TURRET, REPAIR, MYSTERY = range(8, 13)
ITEM_NAMES = ["HELMET", "CLOCK", "SHOVEL", "STAR", "GRENADE", "TANK", "GUN", "SHIP",
              "RESCUE", "LINK", "TURRET", "REPAIR", "MYSTERY"]
N_ITEMS = len(ITEM_NAMES)
# A carrier drops one item from this table (grenade and star twice as often).
DROP_TABLE = [HELMET, CLOCK, SHOVEL, STAR, GRENADE, TANK, GRENADE, STAR, GUN, SHIP,
              RESCUE, LINK, TURRET, REPAIR, MYSTERY]
COOP_ITEMS = (RESCUE, LINK)                   # only dropped with 2 players

# Team and support items:
# RESCUE  partner out of lives -> back with 1 life; else +1 life to the player with fewer lives.
# LINK    shield on both players for LINK_TIME; partner shells pass through (no freeze).
# TURRET  a fixed gun above the base for TURRET_TIME; it shoots enemies in its row or column.
# REPAIR  rebuilds the broken bricks of the base wall (no steel, no timer).
# MYSTERY 2 new random items appear on the field (each stays ITEM_TIME, like any item).
LINK_TIME = 10 * FPS
TURRET_TIME = 20 * FPS
TURRET_POS = (96, 168)        # just above the base wall; tanks and shells pass over it
TURRET_RANGE = 96             # px from the turret center
TURRET_AIM = 6                # px: enemy center this close to the turret row/column
TURRET_RELOAD = 30            # frames between shots
TURRET_BULLET = 4             # px/frame
MYSTERY_ITEMS = 2
# After the last kill the game keeps running this long (items can still be taken).
CLEAR_DELAY = 128
OVER_DELAY = 256

ITEM_SPOTS = [32, 80, 128, 176]              # item x and y: one of 4 spots each
ITEM_AVOID_BLOCKED = True                     # items do not land on steel or water
# Forest cutting: each star adds 0x20 and the gun adds 0x60 to a bullet-power counter.
# At CUT_FOREST_AT or more, bullets cut forest and fly on (one shot clears a path).
CUT_STAR, CUT_GUN, CUT_FOREST_AT = 0x20, 0x60, 0xA0

ENGINE_VOLUME = 1.0         # tank engine sound: 0 = off, 0.5 = half, 1 = normal

EXTRA_LIFE_AT = 20000       # one extra tank per player

# 2-player mode
FRIENDLY_FREEZE = 200       # a hit from the partner freezes the tank (not with a shield).
                            # A frozen tank cannot move but can still fire, and it blinks.
                            # A hit on a frozen tank does not restart the timer.

# Tanks can scrape past each other. Moving toward another tank is blocked only if
# the two overlap by more than this many px across the move direction; moving apart is always free.
TANK_PASS_OVERLAP = 4
TALLY_BONUS = 1000          # 2P tally: the player with more kills gets a bonus
