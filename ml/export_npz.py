"""Save a model (.pt) as numpy weights (.npz) for ml/npnet.py (browser build, no torch).
    nix develop --command python3 ml/export_npz.py models/partner.pt [out.npz]"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import load  # noqa: E402


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".npz"
    net, _ = load(src)                                     # upgraded to the current inputs
    st = {k: v.numpy().astype(np.float32) for k, v in net.state_dict().items()
          if not k.startswith("v.")}                       # the value head is not needed to play
    np.savez_compressed(out, **st)
    print("%s: %d arrays, %.1f MB" % (out, len(st), os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
