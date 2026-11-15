"""Game recordings: the keys of every frame plus the random seed, so a game can be played again
(tools/replay.py shows it or makes a GIF; ml/compare.py records AI snapshots side by side).

A file (.rec.json.gz) holds one game: a header and one segment per stage. A segment has the
stage, the random seed set just before World() was made, the player state after it was made,
the keys of each World.update() (1 byte per player per frame), cheat events and a check value
every CHECK_EVERY frames. Replay makes the same World, sets the same seed and feeds the keys.
The game must then only use `random` inside World while a stage runs (main.py does so).
If the rules changed since the recording, the check values differ: Replay.desync then holds the
first frame where they differ (the replay goes on, but no longer shows the real game).
"""
import base64
import gzip
import json
import random
import subprocess
import time
import zlib

from game import World

VERSION = 1
CHECK_EVERY = 60
KEYS = ("up", "down", "left", "right", "fire")
# player attributes saved at the start of a segment (all simple values of Player)
SIMPLE = (int, float, bool, str, type(None))


def code_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def pack_keys(k):
    return sum(1 << i for i, n in enumerate(KEYS) if k.get(n))


def unpack_keys(b):
    return {n: bool(b >> i & 1) for i, n in enumerate(KEYS)}


def player_state(p):
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in vars(p).items()
            if isinstance(v, SIMPLE) or (isinstance(v, (list, tuple)) and all(isinstance(x, SIMPLE) for x in v))}


def check_value(w):
    s = [w.frame, w.killed, w.hq_alive, w.score]
    s += [(round(t.x, 2), round(t.y, 2), t.d, t.alive) for t in w.all_tanks()]
    s += [(round(b.x, 2), round(b.y, 2)) for b in w.bullets]
    return zlib.crc32(repr(s).encode())


class Recorder:
    """Use: seg = rec.new_world(...) instead of World(...); rec.step(keys) before each
    w.update(keys); rec.cheat(name) for a test key; rec.save(path)."""

    def __init__(self, players, pilots=(), info=None):
        self.data = dict(version=VERSION, code=code_version(), created=time.strftime("%Y-%m-%d %H:%M:%S"),
                         players=players, pilots=list(pilots), info=info or {}, segments=[])
        self.seg = None
        self.keys = bytearray()

    def new_world(self, assets, stage, carry=None, num_players=1, grid=None, seed=None, carriers=None):
        """Seed `random`, make the World and start a new segment."""
        self.end_segment()
        seed = random.randrange(1 << 30) if seed is None else seed
        random.seed(seed)
        w = World(assets, stage, carry, num_players, grid)
        if carriers is not None:
            w.carriers = tuple(carriers)
        self.seg = dict(stage=stage, seed=seed, grid=grid, carriers=list(w.carriers),
                        num_players=len(w.players), start=[player_state(p) for p in w.players],
                        cheats=[], checks=[])
        self.world = w
        self.n = 0
        return w

    def step(self, keys):
        """Call just before world.update(keys) (keys: one dict per player, or one for all)."""
        if self.seg is None:
            return
        if isinstance(keys, dict):
            keys = [keys] * self.seg["num_players"]
        if self.n % CHECK_EVERY == 0:
            self.seg["checks"].append(check_value(self.world))
        self.keys.extend(pack_keys(k) for k in keys)
        self.n += 1

    def cheat(self, name):
        if self.seg is not None:
            self.seg["cheats"].append([self.n, name])

    def end_segment(self):
        if self.seg is not None:
            self.seg["frames"] = self.n
            self.seg["keys"] = base64.b64encode(zlib.compress(bytes(self.keys), 9)).decode()
            self.data["segments"].append(self.seg)
        self.seg, self.keys = None, bytearray()

    def save(self, path):
        """Write the file (the open segment is saved too and stays open)."""
        seg, keys, n = self.seg, self.keys, getattr(self, "n", 0)
        data = dict(self.data, segments=list(self.data["segments"]))
        if seg is not None:
            data["segments"].append(dict(seg, frames=n, keys=base64.b64encode(zlib.compress(bytes(keys), 9)).decode()))
        if not data["segments"]:
            return False
        with gzip.open(path, "wt") as f:
            json.dump(data, f)
        return True


def load(path):
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    assert data.get("version") == VERSION, "unknown recording version %r" % data.get("version")
    for s in data["segments"]:
        s["keys"] = zlib.decompress(base64.b64decode(s["keys"]))
    return data


class Replay:
    """Plays one segment again: for w in Replay(assets, seg, cheat_fn): draw w."""

    def __init__(self, assets, seg, cheat=None):
        self.assets, self.seg, self.cheat = assets, seg, cheat
        self.desync = None

    def __iter__(self):
        s = self.seg
        random.seed(s["seed"])
        w = World(self.assets, s["stage"], None, s["num_players"], s["grid"])
        w.carriers = tuple(s["carriers"])
        for p, st in zip(w.players, s["start"]):
            for k, v in st.items():
                setattr(p, k, v)
        n = s["num_players"]
        cheats = {}
        for f, name in s["cheats"]:
            cheats.setdefault(f, []).append(name)
        yield w
        for i in range(s["frames"]):
            for name in cheats.get(i, ()):      # cheats come before the check (as when recorded)
                if self.cheat:
                    self.cheat(w, name)
            if i % CHECK_EVERY == 0 and self.desync is None and i // CHECK_EVERY < len(s["checks"]):
                if check_value(w) != s["checks"][i // CHECK_EVERY]:
                    self.desync = i
            w.update([unpack_keys(b) for b in s["keys"][i * n:(i + 1) * n]])
            w.sfx.clear()
            yield w
