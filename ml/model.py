"""Policy/value network of the AI partner."""
import torch
import torch.nn as nn

from env import N_ACTIONS, N_CH, N_ITEMS, N_VEC, V3_ITEM_END, V3_N_VEC, V4_N_VEC, V5_N_VEC, V6_N_VEC, V7_N_VEC, N_BASE_CH


ARCHS = ("small", "big")


def arch_of(state):
    """The network size of a saved state dict ("big" has a third conv layer)."""
    return "big" if "conv.4.weight" in state else "small"


class Net(nn.Module):
    def __init__(self, arch="small"):
        """small: v1-v8 (1.0M weights). big (v9): 2x channels, a third conv layer (it sees further
        across the map), 512-wide layers, 2 trunk layers (4.2M weights, ~3.7x the update work)."""
        super().__init__()
        assert arch in ARCHS, arch
        self.arch = arch
        if arch == "small":
            c1, c2, c3, fc, fv, tr = 32, 64, 0, 256, 128, 256
        else:
            c1, c2, c3, fc, fv, tr = 64, 128, 128, 512, 256, 512
        conv = [nn.Conv2d(N_CH, c1, 4, stride=2, padding=1), nn.ReLU(),    # 13x13 (1 cell = 16 px = 1 tank)
                nn.Conv2d(c1, c2, 3, stride=2, padding=1), nn.ReLU()]      # 7x7
        if c3:
            conv += [nn.Conv2d(c2, c3, 3, stride=1, padding=1), nn.ReLU()]  # 7x7, wider view
        self.conv = nn.Sequential(*conv, nn.Flatten(), nn.Linear((c3 or c2) * 7 * 7, fc), nn.ReLU())
        self.vec = nn.Sequential(nn.Linear(N_VEC, fv), nn.ReLU())
        trunk = [nn.Linear(fc + fv, tr), nn.ReLU()]
        if arch == "big":
            trunk += [nn.Linear(tr, tr), nn.ReLU()]
        self.trunk = nn.Sequential(*trunk)
        self.pi = nn.Linear(tr, N_ACTIONS)
        self.v = nn.Linear(tr, 1)
        nn.init.orthogonal_(self.pi.weight, 0.01)
        nn.init.zeros_(self.pi.bias)

    def forward(self, grid, vec):
        """grid: uint8 or float [B, N_CH, 26, 26]; vec: float [B, N_VEC]."""
        h = self.trunk(torch.cat([self.conv(grid.float()), self.vec(vec)], 1))
        return self.pi(h), self.v(h).squeeze(1)


def upgrade(state):
    """Map an older model to the current inputs: v3 (158 inputs, 8 item types), v4 (167), v5 (172), v6 (175), v7 (176);
    v7 and older have 17 grid channels (v8: 39, with the past moments).
    The new inputs get zero weights, so the upgraded model plays exactly as before until it
    learns them."""
    if state["conv.0.weight"].shape[1] == N_CH and state["vec.0.weight"].shape[1] == N_VEC:
        return state                                # the same object: train.py then keeps the optimizer
    state = dict(state)
    c = state["conv.0.weight"]
    if c.shape[1] != N_CH:                          # v8 memory: the past channels start at zero
        assert c.shape[1] == N_BASE_CH, "unknown grid channels %d" % c.shape[1]
        new = torch.zeros(c.shape[0], N_CH, *c.shape[2:], dtype=c.dtype, device=c.device)
        new[:, :N_BASE_CH] = c
        state["conv.0.weight"] = new
    w = state["vec.0.weight"]
    if w.shape[1] == N_VEC:
        return state
    assert w.shape[1] in (V3_N_VEC, V4_N_VEC, V5_N_VEC, V6_N_VEC, V7_N_VEC), "unknown model input size %d" % w.shape[1]
    new = torch.zeros(w.shape[0], N_VEC, dtype=w.dtype, device=w.device)
    if w.shape[1] == V3_N_VEC:
        rest = V3_N_VEC - V3_ITEM_END
        new[:, :V3_ITEM_END] = w[:, :V3_ITEM_END]
        off = V3_ITEM_END + N_ITEMS - 8             # after the new item types
        new[:, off:off + rest] = w[:, V3_ITEM_END:]     # the new extra inputs at the end stay 0
    else:                                           # v4-v7: new inputs only at the end
        new[:, :w.shape[1]] = w
    state["vec.0.weight"] = new
    return state


def load(path):
    ck = torch.load(path, map_location="cpu", weights_only=True)
    net = Net(arch_of(ck["model"]))
    net.load_state_dict(upgrade(ck["model"]))
    net.eval()
    return net, ck
