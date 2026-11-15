"""Map packs: one folder with one text file per stage (01.txt, 02.txt, ...).

A stage file has 13 lines of 13 characters (the 13x13 block map) and one line with the
enemy list. Empty lines and comment lines ("# ...", not a full map row) are ignored.

    Map characters                     Enemy letters (spawn order)
    .  empty                            b  basic
    #  brick        @  steel            f  fast
    r l u d  half brick (right/left/    p  power
             up/down half)              a  armor
    R L U D  half steel
    ~  water   %  forest   -  ice

    enemies: bbbbbbbbbbbbbbbbbbff      (20 letters; spaces are allowed)

Keep the corners of the top row, the top center and the base area free: tanks spawn there
(see mapgen.KEEP_FREE). The game puts the base and its brick wall in place itself.

A pack can have any number of stages. After the last stage the maps start again from 1;
the enemy list of the last stage stays (the hardest one).
"""
import os

# character <-> block code (config.block_to_cells)
CHARS = {".": 13, "r": 0, "d": 1, "l": 2, "u": 3, "#": 4, "R": 5, "D": 6, "L": 7, "U": 8,
         "@": 9, "~": 10, "%": 11, "-": 12}
CODES = {v: k for k, v in CHARS.items()}
ENEMY_LETTERS = "bfpa"          # index = enemy type (config.ENEMY_TYPES)
N_ENEMIES = 20

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACK = os.path.normpath(os.path.join(HERE, "..", "maps", "default"))


class MapError(ValueError):
    pass


def parse(text, name="stage"):
    """Text -> (13x13 block grid, enemy type list)."""
    rows, enemies = [], None
    for n, line in enumerate(text.splitlines(), 1):
        s = line.rstrip()
        is_row = len(s) == 13 and all(ch in CHARS for ch in s)
        if not s or s.startswith("#") and not is_row:       # "#" is also brick: a full row is a map row
            continue
        if s.lower().startswith("enemies:"):
            letters = s.split(":", 1)[1].replace(" ", "").lower()
            if len(letters) != N_ENEMIES or any(ch not in ENEMY_LETTERS for ch in letters):
                raise MapError("%s line %d: need %d enemy letters from '%s'" % (name, n, N_ENEMIES, ENEMY_LETTERS))
            enemies = [ENEMY_LETTERS.index(ch) for ch in letters]
            continue
        if len(s) != 13 or any(ch not in CHARS for ch in s):
            raise MapError("%s line %d: a map row needs 13 characters from '%s'" % (name, n, "".join(CHARS)))
        rows.append([CHARS[ch] for ch in s])
    if len(rows) != 13:
        raise MapError("%s: %d map rows, need 13" % (name, len(rows)))
    if enemies is None:
        raise MapError("%s: no 'enemies:' line" % name)
    return rows, enemies


def format_stage(grid, enemies, comment=None):
    out = ["# " + comment] if comment else []
    out += ["".join(CODES[b] for b in row) for row in grid]
    out.append("enemies: " + "".join(ENEMY_LETTERS[e] for e in enemies))
    return "\n".join(out) + "\n"


class MapPack:
    def __init__(self, path=DEFAULT_PACK):
        self.path = os.path.abspath(path)
        if not os.path.isdir(self.path):
            raise MapError("map pack folder not found: %s" % path)
        files = sorted(f for f in os.listdir(self.path) if f.endswith(".txt") and f[:-4].isdigit())
        if not files:
            raise MapError("no stage files (01.txt, 02.txt, ...) in %s" % path)
        self.stages = []
        for f in files:
            with open(os.path.join(self.path, f), encoding="utf-8") as fh:
                self.stages.append(parse(fh.read(), f))

    @property
    def count(self):
        return len(self.stages)

    def stage_grid(self, stage):
        return [row[:] for row in self.stages[(stage - 1) % self.count][0]]

    def enemy_list(self, stage):
        return list(self.stages[min(stage, self.count) - 1][1])
