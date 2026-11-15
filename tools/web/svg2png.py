"""Draw every art/*.svg to a PNG next to it (in a copy of art/), for the browser build:
pygame in the browser cannot read SVG. Usage: python3 tools/web/svg2png.py ART_DIR"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import pygame  # noqa: E402

from art import render_svg  # noqa: E402

art = sys.argv[1]
pygame.init()
n = 0
for root, _, files in os.walk(art):
    for f in files:
        if f.endswith(".svg"):
            fid = os.path.relpath(os.path.join(root, f[:-4]), art)
            pygame.image.save(render_svg(art, fid), os.path.join(art, fid + ".png"))
            n += 1
print("svg2png: %d images" % n)
