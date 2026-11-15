#!/usr/bin/env python3
"""Measure a trained model (as player 2) with a partner bot, no UI.

    nix develop --command python3 ml/evaluate.py ml/runs/v1/latest.pt --partner bot
    nix develop --command python3 ml/evaluate.py random --partner bot      # baseline

--partner: bot (rule bot as player 1), idle (player 1 does nothing), random, self (model plays both).
"""
import argparse
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import env as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="checkpoint .pt, or 'random'")
    ap.add_argument("--partner", default="bot", choices=("bot", "idle", "random", "self", "past"))
    ap.add_argument("--partner-model", help="with --partner past: the model that drives player 1")
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--stages", default="1-35")
    ap.add_argument("--maps", metavar="NAME|DIR", help="map pack (default: the built-in pack)")
    ap.add_argument("--greedy", action="store_true", help="always the best action (default: sample)")
    ap.add_argument("--temp", type=float, default=1.0, help="sampling temperature (< 1: steadier)")
    ap.add_argument("--seed", type=int, default=123)
    a = ap.parse_args()
    random.seed(a.seed)
    stages = tuple(int(s) for s in a.stages.split("-")) if "-" in a.stages else (int(a.stages),) * 2
    E.init_pygame()
    A = E.load_assets(a.maps)
    env = E.TankEnv(A, stages, modes={a.partner: 1.0})
    pilot = None
    if a.model != "random":
        import torch
        torch.manual_seed(a.seed)
        from agent import AIPilot
        pilot = AIPilot(a.model, greedy=a.greedy, temp=a.temp)
    partner = pilot
    if a.partner == "past":
        from agent import AIPilot
        partner = AIPilot(a.partner_model or a.model, temp=0.5)

    def act(i):
        return random.randrange(E.N_ACTIONS) if pilot is None else pilot.choose(env.w, i)

    eps = []
    changes = steps = 0
    last = None
    for n in range(a.episodes):
        env.reset()
        done = False
        while not done:
            a1 = act(1)
            d = E.ACTIONS[a1][0]
            if env.w.players[1].alive:
                steps += 1
                changes += d != last
                last = d
            a0 = act(0) if a.partner == "self" else partner.choose(env.w, 0) if a.partner == "past" else 0
            _, done = env.step([a0, a1])
        s = env.stats
        eps.append(s)
        print("%3d stage %2d  %-8s  steps %4d  kills P1 %2d P2 %2d  deaths P1 %d P2 %d  %s" % (
            n + 1, s["stage"], s["mode"], s["steps"], s["kills"][0], s["kills"][1], s["deaths"][0],
            s["deaths"][1], "CLEAR" if s["cleared"] else "HQ LOST" if s["hq"] else
            "TIMEOUT" if s["timeout"] else "NO LIVES"), flush=True)
    m = lambda f: np.mean([f(x) for x in eps])  # noqa: E731
    print("\n%s, partner %s, %d episodes:" % (a.model, a.partner, len(eps)))
    print("  clear %.0f%%  hq lost %.0f%%  timeout %.0f%%  no lives %.0f%%" % (
        100 * m(lambda x: x["cleared"]), 100 * m(lambda x: x["hq"]), 100 * m(lambda x: x["timeout"]),
        100 * m(lambda x: 1 - x["cleared"] - x["hq"] - x["timeout"])))
    print("  per episode: P2 kills %.1f deaths %.1f | P1 kills %.1f deaths %.1f | steps %.0f" % (
        m(lambda x: x["kills"][1]), m(lambda x: x["deaths"][1]), m(lambda x: x["kills"][0]),
        m(lambda x: x["deaths"][0]), m(lambda x: x["steps"])))
    print("  P2 direction changes per second: %.1f" % (changes / max(1, steps) * 60 / E.FRAME_SKIP))


if __name__ == "__main__":
    main()
