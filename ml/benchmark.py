#!/usr/bin/env python3
"""Fixed test of a model: the same games every time, so two models compare fairly.

    nix develop --command python3 ml/benchmark.py models/partner.pt [more.pt ...]

Three map sets, each with three partners (self: the model drives both tanks; bot: the rule bot
is player 1; idle: player 1 does nothing):
  seen      5 map-pack stages the training plays
  unseen    the 5 map-pack stages training never plays (env.HOLDOUT_STAGES)
  random    5 random maps from fixed seeds (training makes its own random maps, never these)
"unseen" and "random" show how the AI plays a map it has never seen (a new map in the future).
If they are much worse than "seen", the model has learned the training maps by heart.
Only the network-driven tanks count for freezes, items, stuck, shells and own base.
"""
import argparse
import multiprocessing as mp
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import env as E  # noqa: E402
from mapgen import random_grid  # noqa: E402

SEEN = (1, 8, 15, 22, 29)
RANDOM_MAPS = [(10000 + k, s) for k, s in enumerate((3, 10, 17, 24, 31))]   # (map seed, enemy list of stage)
PARTNERS = ("self", "bot", "idle")


def games(per):
    """(set, partner, stage, map seed or None, game seed) for every game."""
    out = []
    for name, maps in (("seen", [(s, None) for s in SEEN]), ("unseen", [(s, None) for s in E.HOLDOUT_STAGES]),
                       ("random", [(s, m) for m, s in RANDOM_MAPS])):
        for partner in PARTNERS:
            for stage, mseed in maps:
                for k in range(per):
                    out.append((name, partner, stage, mseed, stage * 1000 + k * 17 + PARTNERS.index(partner)))
    return out


_pilot = _env = None


def _init(model):
    global _pilot, _env
    import torch
    torch.set_num_threads(1)
    E.init_pygame()
    _env = E.TankEnv(E.load_assets())
    from agent import AIPilot
    _pilot = AIPilot(model, temp=0.5)


def _play(g):
    import torch
    name, partner, stage, mseed, seed = g
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    grid = random_grid(random.Random(mseed)) if mseed is not None else None
    env = _env
    env.reset(stage=stage, grid=grid, mode=partner)
    _pilot.mem = {}
    done = False
    while not done:
        a1 = _pilot.choose(env.w, 1)
        a0 = _pilot.choose(env.w, 0) if partner == "self" else 0
        _, done = env.step([a0, a1])
    s = dict(env.stats)
    s["set"], s["partner"] = name, partner
    return s


def summary(rows):
    def ai(s, key):                 # sum over the network-driven players
        idx = (0, 1) if s["partner"] == "self" else (1,)
        return sum(s[key][i] for i in idx)
    n = len(rows)
    minutes = sum(ai(s, "alive_steps") for s in rows) * E.FRAME_SKIP / 3600 or 1
    power = sum(ai(s, "power_items") for s in rows)
    shells = sum(ai(s, "shells") for s in rows) or 1
    return dict(
        games=n,
        clear=100 * np.mean([s["cleared"] for s in rows]),
        hq=100 * np.mean([s["hq"] for s in rows]),
        deaths=np.mean([s["deaths"][1] for s in rows]),
        kills=np.mean([s["kills"][1] for s in rows]),
        freezes=sum(ai(s, "freezes") for s in rows) / minutes,
        items=sum(ai(s, "items") for s in rows) / n,
        steal=100 * sum(ai(s, "partner_items") for s in rows) / max(1, power),
        stuck=100 * sum(ai(s, "stuck") for s in rows) / max(1, sum(ai(s, "alive_steps") for s in rows)),
        wasted=100 * sum(ai(s, "wasted") for s in rows) / shells,
        base=sum(ai(s, "base_cells") for s in rows))


COLS = [("clear", "clear %", "%7.0f"), ("hq", "hq %", "%7.0f"), ("kills", "P2 kills", "%8.1f"),
        ("deaths", "P2 deaths", "%9.2f"), ("freezes", "freeze/min", "%10.2f"), ("items", "items/game", "%10.1f"),
        ("steal", "partner's item %", "%16.0f"), ("stuck", "stuck %", "%7.1f"),
        ("wasted", "wasted shell %", "%14.0f"), ("base", "own base", "%8d")]


def table(title, groups):
    print("\n" + title)
    print("%-14s %5s " % ("", "games") + " ".join(h for _, h, _ in COLS))
    for label, rows in groups:
        m = summary(rows)
        print("%-14s %5d " % (label, m["games"]) + " ".join(f % m[k] for k, _, f in COLS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--per", type=int, default=3, help="games per map and partner (x 45)")
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    gs = games(a.per)
    for model in a.models:
        ctx = mp.get_context("fork" if sys.platform.startswith("linux") else "spawn")
        with ctx.Pool(a.procs, _init, (model,)) as pool:
            rows = pool.map(_play, gs, chunksize=1)
        groups = [(s, [r for r in rows if r["set"] == s]) for s in ("seen", "unseen", "random")]
        groups += [("partner " + p, [r for r in rows if r["partner"] == p]) for p in PARTNERS]
        groups.append(("all", rows))
        table("%s  (%d games, temp 0.5)" % (model, len(rows)), groups)


if __name__ == "__main__":
    main()
