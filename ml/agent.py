"""Trained AI pilot for the real game: gives one key dict per frame."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from env import FRAME_SKIP, Memory, action_keys, observe, safe_action  # noqa: E402

DEFAULT_MODEL = os.path.join(HERE, "..", "models", "partner.pt")   # see README: download from the release


class AIPilot:
    def __init__(self, path=DEFAULT_MODEL, greedy=False, temp=1.0):
        """temp < 1: steadier (picks likely actions more often); greedy: always the best action."""
        try:
            import torch
        except ImportError:                 # browser build or small install: numpy weights (.npz)
            torch = None
        self.torch = torch
        if torch and not path.endswith(".npz"):
            from model import load
            torch.set_num_threads(1)
            self.net, _ = load(path)
        else:
            from npnet import NpNet
            self.net = NpNet(os.path.splitext(path)[0] + ".npz")
            self.rng = np.random.default_rng()
        self.greedy = greedy
        self.temp = temp
        self.a, self.sub = 0, 0
        self.mem = {}                   # idx -> (world, Memory): the past moments (v8)

    def choose(self, world, idx):
        """One decision (call once per FRAME_SKIP frames, as in training)."""
        if idx not in self.mem or self.mem[idx][0] is not world:      # a new stage or game
            self.mem[idx] = (world, Memory())
        mem = self.mem[idx][1]
        g, v = observe(world, idx, mem)
        if self.torch is None or not hasattr(self.net, "forward"):
            logits = self.net.logits(g, v)
            if self.greedy:
                a = int(logits.argmax())
            else:
                p = np.exp((logits - logits.max()) / self.temp)
                a = int(self.rng.choice(len(p), p=p / p.sum()))
            mem.last_action = safe_action(world, idx, a)
            return a
        t = self.torch
        with t.no_grad():
            logits, _ = self.net(t.from_numpy(g)[None], t.from_numpy(v)[None])
        if self.greedy:
            a = int(logits.argmax(1))
        else:
            a = int(t.distributions.Categorical(logits=logits / self.temp).sample())
        mem.last_action = safe_action(world, idx, a)
        return a

    def keys(self, world, idx):
        """Call once per game frame. A new decision every FRAME_SKIP frames (as in training)."""
        if self.sub == 0:
            self.a = safe_action(world, idx, self.choose(world, idx))
        k = action_keys(self.a, self.sub)
        self.sub = (self.sub + 1) % FRAME_SKIP
        return k
