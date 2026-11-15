#!/usr/bin/env python3
"""Put game GIFs / WebPs side by side in one animation (a grid), to compare them.

    nix develop --command python3 tools/compose.py A.webp B.webp C.webp D.webp -o grid.webp [--cols 2]

Any GIF or animated WebP works (ml/compare.py, tools/replay.py). The output format comes from the
file name (.webp: lossless and much smaller; .gif). All games play from the start at the same
time, on the real frame times (both formats merge frames that do not change into one longer
frame); a game that ends earlier keeps its last picture. Frames are read one at a time, so large
games do not fill the memory.
"""
import argparse
import os
import struct

from PIL import Image


def durations(path):
    """Frame times in ms. Pillow does not give them for WebP, so they are read from the file."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
        out, i = [], 12
        while i + 8 <= len(d):
            tag, n = d[i:i + 4], struct.unpack("<I", d[i + 4:i + 8])[0]
            if tag == b"ANMF":
                out.append(int.from_bytes(d[i + 20:i + 23], "little"))
            i += 8 + n + (n & 1)
        return out or [100]
    im = Image.open(path)
    out = []
    for k in range(getattr(im, "n_frames", 1)):
        im.seek(k)
        out.append(im.info.get("duration", 100) or 100)
    return out


class Track:
    """One input on a time line: picture(t) gives the frame shown at time t (ms); t only grows."""

    def __init__(self, path):
        self.im = Image.open(path)
        self.durs = durations(path)
        self.k, self.end = 0, self.durs[0]
        self.im.seek(0)
        self.pic = self.im.convert("RGB")
        self.length = sum(self.durs)

    def picture(self, t):
        moved = False
        while t >= self.end and self.k + 1 < len(self.durs):
            self.k += 1
            self.end += self.durs[self.k]
            moved = True
        if moved:
            self.im.seek(self.k)
            self.pic = self.im.convert("RGB")
        return self.pic


def compose(paths, out, cols=0, gap=4, hold=2.0, bg=(40, 40, 40), tick=None):
    """tick: output frame time in ms (default: the shortest frame time of the inputs, at least 20)."""
    from replay import save_anim
    probe = [Track(p) for p in paths]
    tick = tick or max(20, min(min(t.durs) for t in probe))
    cols = cols or min(len(paths), 2)
    rows = (len(paths) + cols - 1) // cols
    tw = max(t.pic.width for t in probe)
    th = max(t.pic.height for t in probe)
    W, H = cols * tw + (cols - 1) * gap, rows * th + (rows - 1) * gap
    total = max(t.length for t in probe) + hold * 1000

    def images():                       # a new pass opens the files again (save_gif reads twice)
        tracks = [Track(p) for p in paths]
        t = 0.0
        while t < total:
            canvas = Image.new("RGB", (W, H), bg)
            for k, tr in enumerate(tracks):
                canvas.paste(tr.picture(t), ((k % cols) * (tw + gap), (k // cols) * (th + gap)))
            yield canvas
            t += tick
    save_anim(images, out, 1000 / tick)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="GIF or WebP files")
    ap.add_argument("-o", "--out", required=True, help=".webp or .gif")
    ap.add_argument("--cols", type=int, default=0, help="games per row (default 2)")
    a = ap.parse_args()
    compose(a.inputs, a.out, a.cols)
    print("wrote %s (%.1f MB)" % (a.out, os.path.getsize(a.out) / 1e6))


if __name__ == "__main__":
    main()
