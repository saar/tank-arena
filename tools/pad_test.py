#!/usr/bin/env python3
"""Show what the game reads from each gamepad (no window needed).

    nix develop --command python3 tools/pad_test.py [seconds]
"""
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pygame  # noqa: E402

pygame.init()
from pad import Pads  # noqa: E402

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
pads = Pads()
print("%d pad(s)" % len(pads), flush=True)
for i, p in enumerate(pads.list):
    print("  pad %d: %s (%s)" % (i, p.name, "standard layout" if p.ctl else "raw joystick"), flush=True)
print("press buttons now (%.0f s) ..." % secs, flush=True)
end = time.time() + secs
while time.time() < end:
    for ev in pygame.event.get():
        pads.event(ev)
        if ev.type == pygame.JOYDEVICEADDED or ev.type == pygame.JOYDEVICEREMOVED:
            print("pads changed: %d pad(s)" % len(pads), flush=True)
        if ev.type == pygame.JOYBUTTONDOWN:
            print("  raw: pad %d button %d" % (ev.instance_id, ev.button), flush=True)
    pads.poll()
    for i, p in enumerate(pads.list):
        for n in p.now:
            if p.now[n] != p.prev[n]:
                print("pad %d  %-5s %s" % (i, n, "DOWN" if p.now[n] else "up"), flush=True)
    time.sleep(1 / 120)
