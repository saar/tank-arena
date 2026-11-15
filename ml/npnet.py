"""The AI partner network in plain numpy (no torch): for the browser build and small installs.
Same math as model.Net.forward (policy only). Weights: a .npz made by ml/export_npz.py."""
import numpy as np


def _conv(x, w, b, stride, pad):
    """x: [C, H, W], w: [O, C, k, k] -> [O, Ho, Wo] (as torch Conv2d)."""
    o, c, k, _ = w.shape
    x = np.pad(x, ((0, 0), (pad, pad), (pad, pad)))
    win = np.lib.stride_tricks.sliding_window_view(x, (k, k), axis=(1, 2))[:, ::stride, ::stride]
    ho, wo = win.shape[1], win.shape[2]
    cols = win.transpose(1, 2, 0, 3, 4).reshape(ho * wo, c * k * k)
    return (cols @ w.reshape(o, -1).T + b).T.reshape(o, ho, wo)


def _relu(x):
    return np.maximum(x, 0, out=x)


class NpNet:
    STRIDES = (2, 2, 1)                     # conv layers in order (model.Net): 4x4/2, 3x3/2, 3x3/1 (big only)

    def __init__(self, path):
        z = np.load(path)
        self.p = {k: z[k].astype(np.float32) for k in z.files}
        self.convs = sorted(int(k.split(".")[1]) for k, v in self.p.items()
                            if k.startswith("conv.") and k.endswith(".weight") and v.ndim == 4)
        self.fc = max(int(k.split(".")[1]) for k in self.p if k.startswith("conv."))
        self.trunk = sorted(int(k.split(".")[1]) for k in self.p if k.startswith("trunk.") and k.endswith(".weight"))

    def _lin(self, name, x):
        return x @ self.p[name + ".weight"].T + self.p[name + ".bias"]

    def logits(self, grid, vec):
        """grid: [N_CH, 26, 26], vec: [N_VEC] (one sample) -> logits [N_ACTIONS]."""
        x = grid.astype(np.float32)
        for i, n in enumerate(self.convs):
            x = _relu(_conv(x, self.p["conv.%d.weight" % n], self.p["conv.%d.bias" % n], self.STRIDES[i], 1))
        h = _relu(self._lin("conv.%d" % self.fc, x.reshape(-1)))
        v = _relu(self._lin("vec.0", vec.astype(np.float32)))
        t = np.concatenate([h, v])
        for n in self.trunk:
            t = _relu(self._lin("trunk.%d" % n, t))
        return self._lin("pi", t)
