#!/usr/bin/env python3
"""Play a game recording again (main.py --record, ml/compare.py) or make a GIF of it.

    nix develop --command python3 tools/replay.py recordings/FILE.rec.json.gz
    nix develop --command python3 tools/replay.py FILE --gif out.gif [--fps 30] [--scale 2] [--stage-index 1]
    nix develop --command python3 tools/replay.py FILE --webp out.webp [--scale 3]   (lossless, smaller)

Window keys: Space pause, + / - speed, Right: next stage, Esc quit.
A recording holds keys and the random seed, not pictures. If the game rules changed since it
was made, the replay differs from the real game: the tool then prints a warning ("desync").
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(GAME, "src"))
ART = os.path.join(GAME, "art")
TEXT = (252, 252, 252)


def init(headless):
    if headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    pygame.display.init()
    if headless:
        pygame.display.set_mode((1, 1))
    from assets import Assets
    return Assets(None, ART)


def cheat_fn():
    from main import apply_cheat
    return apply_cheat


def frames(assets, data, step=1, segments=None, banner=60, desync=None):
    """Yield (pygame Surface 256x224, segment index) for the recording, every step-th game frame.
    banner: frames of "STAGE N" before each stage (0: none). desync: list that gets
    (segment index, frame) for each segment that no longer replays like the real game."""
    import pygame
    from config import SCREEN_H, SCREEN_W
    from record import Replay
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    cheat = cheat_fn()
    for si, seg in enumerate(data["segments"]):
        if segments is not None and si not in segments:
            continue
        for _ in range(0, banner, step):
            from hud import draw_banner
            draw_banner(assets, surf, "STAGE %d" % seg["stage"])
            yield surf, si
        r = Replay(assets, seg, cheat)
        for n, w in enumerate(r):
            if n % step == 0:
                w.draw(surf)
                yield surf, si
        if r.desync is not None:
            print("warning: stage %d (segment %d) desync at frame %d: the rules changed since the recording"
                  % (seg["stage"], si, r.desync))
            if desync is not None:
                desync.append((si, r.desync))


def to_image(surf, scale=1):
    import pygame
    from PIL import Image
    img = Image.frombytes("RGB", surf.get_size(), pygame.image.tobytes(surf, "RGB"))
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


def save_gif(make_images, path, fps, sample=10):
    """make_images: a function that returns a new iterator of PIL RGB images (called twice:
    first every sample-th image gives the colors, then all images are written)."""
    import numpy as np
    from PIL import Image
    colors = set()
    for n, im in enumerate(make_images()):
        if n % sample == 0:
            a = np.asarray(im).reshape(-1, 3)
            colors.update(map(tuple, np.unique(a, axis=0)))
    colors = sorted(colors)
    if len(colors) > 256:                       # more colors than a GIF holds: a 256-color mix
        mix = Image.new("RGB", (len(colors), 1))
        mix.putdata(colors)
        colors = [tuple(c) for c in np.asarray(mix.quantize(256, dither=Image.Dither.NONE).convert("RGB"))
                  .reshape(-1, 3)]
        colors = sorted(set(colors))
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in colors for v in c] + [0] * (768 - 3 * len(colors)))
    frames = (im.quantize(palette=pal, dither=Image.Dither.NONE) for im in make_images())
    first = next(frames)
    first.save(path, save_all=True, append_images=frames, duration=round(1000 / fps), loop=0, optimize=False,
               disposal=1)


def save_webp(make_images, path, fps, lossless=True, quality=80, method=4):
    """Animated WebP, one frame at a time (Pillow's save() first makes a list of all frames: a
    4-game grid at scale 3 needed 9 GB). lossless: exact pixels (best for pixel art); quality:
    the effort for lossless (0-100, more = smaller and slower) or the picture quality for lossy.
    Uses Pillow's internal encoder (PIL._webp, as in WebPImagePlugin._save_all of Pillow 13)."""
    from PIL import _webp
    images = iter(make_images())
    first = next(images)
    step = 1000 / fps
    enc = _webp.WebPAnimEncoder(first.size, 0xff000000, 0, False, 9 if lossless else 3, 17 if lossless else 5,
                                False, False)
    n = 0
    for im in _chain(first, images):
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        enc.add(im.getim(), round(n * step), lossless, quality, 100, method)
        n += 1
    enc.add(None, round(n * step), lossless, quality, 100, 0)
    data = enc.assemble("", "", "")
    if data is None:
        raise OSError("cannot write %s (WebP encoder returned None)" % path)
    with open(path, "wb") as f:
        f.write(data)


def _chain(first, rest):
    yield first
    yield from rest


def save_anim(make_images, path, fps):
    """GIF or WebP, from the file name."""
    if path.lower().endswith(".webp"):
        save_webp(make_images, path, fps)
    else:
        save_gif(make_images, path, fps)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--gif", help="write a GIF instead of showing a window")
    ap.add_argument("--webp", help="write an animated WebP (lossless) instead of showing a window")
    ap.add_argument("--fps", type=int, default=30, help="GIF frames per second (the game runs at 60)")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--stage-index", type=int, help="only this segment (0 = the first stage played)")
    ap.add_argument("--speed", type=float, default=1, help="window: play speed")
    a = ap.parse_args()
    from record import load
    data = load(a.file)
    print("%s: code %s, %s, players %s, %d stage(s): %s" % (
        os.path.basename(a.file), data["code"], data["created"], data["pilots"], len(data["segments"]),
        ", ".join("%d (%d frames)" % (s["stage"], s["frames"]) for s in data["segments"])))
    segs = None if a.stage_index is None else {a.stage_index}
    out = a.webp or a.gif
    assets = init(bool(out))
    if out:
        step = max(1, round(60 / a.fps))
        save_anim(lambda: (to_image(s, a.scale) for s, _ in frames(assets, data, step, segs)), out, 60 / step)
        print("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))
        return
    import pygame
    from config import SCREEN_H, SCREEN_W
    screen = pygame.display.set_mode((SCREEN_W * a.scale, SCREEN_H * a.scale))
    pygame.display.set_caption("replay " + os.path.basename(a.file))
    clock = pygame.time.Clock()
    speed, paused, skip = a.speed, False, None
    it = frames(assets, data, 1, segs)
    surf, si = next(it)
    acc = 0.0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    speed = min(32, speed * 2)
                elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed = max(0.25, speed / 2)
                elif ev.key == pygame.K_RIGHT:
                    skip = si
        if not paused:
            acc += speed
            try:
                while acc >= 1 or (skip is not None and si == skip):
                    surf, si = next(it)
                    acc = max(0.0, acc - 1)
                skip = None
            except StopIteration:
                paused = True
        pygame.transform.scale(surf, screen.get_size(), screen)
        if speed != 1:
            pygame.display.set_caption("replay %s  x%g" % (os.path.basename(a.file), speed))
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
