#!/usr/bin/env python3
"""See how the AI got better: every model plays the same stage from the same start, and each
game becomes its own GIF (the full game screen with a label line: model, time, result).
tools/compose.py puts GIFs side by side later (or use --grid here).

    nix develop --command python3 ml/compare.py ml/runs/v1 --stage 1
    nix develop --command python3 ml/compare.py A.pt B.pt --stage 12 --partner bot --grid

A folder (a training run) means all ckpt_*.pt (or snap-it*.pt) in it (evenly picked down to --max). Output: one folder per test
(runs/compare/stage<N>-seed<S>-<partner>/) with <model>.gif (or .webp, -x<scale>) and <model>.rec.json.gz (the
recording; tools/replay.py plays it again).
partner self: the model drives both tanks; bot: the rule bot is player 1, the model player 2.
"""
import argparse
import glob
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, "..")
sys.path[:0] = [HERE, os.path.join(GAME, "src"), os.path.join(GAME, "tools")]

LAYOUTS = ("screen", "field", "field+bars")


def model_list(paths, most):
    out = []
    for p in paths:
        if os.path.isdir(p):
            snaps = glob.glob(os.path.join(p, "ckpt_*.pt")) + glob.glob(os.path.join(p, "snap-it*.pt"))
            snaps.sort(key=lambda f: int(re.findall(r"(\d+)", os.path.basename(f))[0]))
            if len(snaps) > most:           # evenly spread, always the first and the last
                snaps = [snaps[round(i * (len(snaps) - 1) / (most - 1))] for i in range(most)]
            out += snaps
        else:
            out.append(p)
    return out


def label(path):
    """Short tile label: "IT 2000" for ckpt_02000.pt or snap-it002000.pt, else the file name."""
    m = re.match(r"(?:snap-it|ckpt_)0*(\d+)\.pt$", os.path.basename(path))
    if m:
        return "IT " + m.group(1)
    return re.sub(r"\.pt$", "", os.path.basename(path)).replace("snap-", "")[:14]


class BotPilot:
    """The rule bot of the training (env.Bot), as key dicts per frame."""

    def __init__(self):
        import env as E
        self.E, self.bot, self.a, self.sub = E, E.Bot("bot"), 0, 0

    def keys(self, w, idx):
        if self.sub == 0:
            self.a = self.bot.act(w, idx)
        k = self.E.action_keys(self.a, self.sub)
        self.sub = (self.sub + 1) % self.E.FRAME_SKIP
        return k


def play(assets, model, stage, seed, grid, partner, max_frames, path):
    """One recorded game of one stage. Returns the result dict."""
    import torch
    from agent import AIPilot
    from config import CLEAR_DELAY, OVER_DELAY
    from record import Recorder
    torch.manual_seed(seed)
    pilots = [AIPilot(model, temp=0.5) if partner == "self" else BotPilot(), AIPilot(model, temp=0.5)]
    names = ["ai:" + os.path.basename(model) if partner == "self" else "bot", "ai:" + os.path.basename(model)]
    rec = Recorder(2, names, dict(tool="compare", model=model, partner=partner, label=label(model)))
    w = rec.new_world(assets, stage, None, 2, grid, seed=seed)
    end, result = None, "TIME"
    for f in range(max_frames):
        if end is None and w.lost:
            end, result = f + OVER_DELAY, "LOST"
        elif end is None and w.cleared:
            end, result = f + CLEAR_DELAY, "CLEAR"
        if end is not None and f >= end:
            break
        idle = {k: False for k in ("up", "down", "left", "right", "fire")}
        keys = [idle, idle] if result == "LOST" else [p.keys(w, i) for i, p in enumerate(pilots)]
        rec.step(keys)
        w.update(keys)
        w.sfx.clear()
    rec.data["info"]["result"] = result
    rec.data["info"]["kills"] = [sum(p.kills) for p in w.players]
    rec.save(path)
    return dict(result=result, frames=rec.n, kills=[sum(p.kills) for p in w.players])


def tile_size(layout):
    from config import FIELD, SCREEN_H, SCREEN_W
    w, h = (SCREEN_W, SCREEN_H) if layout == "screen" else (FIELD, FIELD)
    return w, h + 12 + (10 if layout == "field+bars" else 0)


def draw_tile(assets, surf, w, layout, name, result, n, total):
    """One tile: a label line, the game, and (field+bars) a line with kills/lives/time."""
    import pygame
    from config import ENEMIES_PER_STAGE, FIELD, SCREEN_H, SCREEN_W
    from hud import field_pos
    FIELD_X, FIELD_Y = field_pos()
    surf.fill((0, 0, 0))
    screen = pygame.Surface((SCREEN_W, SCREEN_H))
    w.draw(screen)
    if layout == "screen":
        surf.blit(screen, (0, 12))
    else:
        surf.blit(screen, (0, 12), (FIELD_X, FIELD_Y, FIELD, FIELD))
    assets.text(surf, name, 2, 2)
    done = n >= total
    sec = n // 60                           # the font has no ":"
    tag = ("%s %dS" % (result, sec)) if done else "%dS" % sec
    pal = {"CLEAR": "text", "LOST": "textred", "TIME": "text"}.get(result, "text") if done else "text"
    assets.text(surf, tag, surf.get_width() - 8 * len(tag) - 2, 2, pal)
    if layout == "field+bars":
        y = surf.get_height() - 8
        killed = min(w.killed, ENEMIES_PER_STAGE)
        bw = surf.get_width() - 4
        pygame.draw.rect(surf, (60, 60, 60), (2, y, bw, 5))
        pygame.draw.rect(surf, (220, 60, 40), (2, y, round(bw * killed / ENEMIES_PER_STAGE), 5))


def render(assets, recs, out, layout, cols, fps, scale, hold=2.0):
    """recs: [(label, recording dict)]. Writes one GIF with all games side by side."""
    import pygame
    from replay import save_anim, to_image
    from record import Replay
    from main import apply_cheat
    tw, th = tile_size(layout)
    cols = cols or min(len(recs), 2 if layout == "screen" else 5)
    rows = (len(recs) + cols - 1) // cols
    gap = 4
    W, H = cols * tw + (cols - 1) * gap, rows * th + (rows - 1) * gap
    step = max(1, round(60 / fps))
    longest = max(r["segments"][0]["frames"] for _, r in recs)
    total = longest + int(hold * 60)

    def images():
        canvas = pygame.Surface((W, H))
        tile = pygame.Surface((tw, th))
        its = [iter(Replay(assets, r["segments"][0], apply_cheat)) for _, r in recs]
        last = [next(it) for it in its]
        for f in range(total + 1):
            if f:
                for i, it in enumerate(its):
                    nw = next(it, None)
                    if nw is not None:
                        last[i] = nw
            if f % step:
                continue
            canvas.fill((40, 40, 40))
            for i, (name, r) in enumerate(recs):
                seg = r["segments"][0]
                draw_tile(assets, tile, last[i], layout, name, r["info"].get("result", ""), min(f, seg["frames"]),
                          seg["frames"])
                canvas.blit(tile, ((i % cols) * (tw + gap), (i // cols) * (th + gap)))
            yield to_image(canvas, scale)
    save_anim(images, out, 60 / step)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+", help="model files, or run folders (their ckpt_*.pt)")
    ap.add_argument("--stage", type=int, default=1, help="stage (its map and enemy list)")
    ap.add_argument("--map-seed", type=int, help="a random map (mapgen) from this seed instead of the stage map")
    ap.add_argument("--seed", type=int, default=1, help="game seed: the same for every model")
    ap.add_argument("--partner", default="self", choices=("self", "bot"))
    ap.add_argument("--minutes", type=float, default=3, help="longest game")
    ap.add_argument("--max", type=int, default=0, help="most snapshots taken from a folder (0: all)")
    ap.add_argument("--layout", default="screen", choices=LAYOUTS,
                    help="screen: the full game screen (user's choice); field: play field only; field+bars: + kill bar")
    ap.add_argument("--fps", type=int, default=30, help="GIF frames per second (it plays at real game speed)")
    ap.add_argument("--scale", type=int, default=1, help="picture size (3 = the game window)")
    ap.add_argument("--format", default="gif", choices=("gif", "webp"),
                    help="webp: lossless, ~5-10x smaller than gif, exact frame times")
    ap.add_argument("--grid", action="store_true", help="also put all GIFs in one grid GIF (tools/compose.py)")
    ap.add_argument("--cols", type=int, default=2, help="--grid: GIFs per row")
    ap.add_argument("--redo", action="store_true", help="play again even if the GIF is there")
    ap.add_argument("--out", help="output folder (default ml/runs/compare/<test>/)")
    a = ap.parse_args()
    models = model_list(a.models, a.max or 10 ** 6)
    if not models:
        sys.exit("no models found")
    out = a.out or os.path.join(HERE, "runs", "compare", "stage%d%s-seed%d-%s" % (
        a.stage, "" if a.map_seed is None else "-map%d" % a.map_seed, a.seed, a.partner))
    os.makedirs(out, exist_ok=True)
    import env as E
    E.init_pygame()
    assets = E.load_assets()
    grid = None
    if a.map_seed is not None:
        from mapgen import random_grid
        grid = random_grid(random.Random(a.map_seed))
    from record import load
    gifs = []
    for m in models:
        base = os.path.join(out, re.sub(r"\.pt$", "", os.path.basename(m)))
        anim = base + "." + a.format
        if a.scale != 1:
            anim = base + "-x%d.%s" % (a.scale, a.format)
        gifs.append(anim)
        if os.path.exists(anim) and not a.redo:
            print("%-16s (have it)" % label(m))
            continue
        r = play(assets, m, a.stage, a.seed, grid, a.partner, int(a.minutes * 3600), base + ".rec.json.gz")
        render(assets, [(label(m), load(base + ".rec.json.gz"))], anim, a.layout, 1, a.fps, a.scale)
        print("%-16s %-5s %5.1f s  kills %d + %d  -> %s (%.1f MB)" % (
            label(m), r["result"], r["frames"] / 60, *r["kills"], anim, os.path.getsize(anim) / 1e6),
            flush=True)
    if a.grid:
        from compose import compose
        g = os.path.join(out, "grid%s.%s" % ("" if a.scale == 1 else "-x%d" % a.scale, a.format))
        compose(gifs, g, a.cols)
        print("wrote %s (%.1f MB)" % (g, os.path.getsize(g) / 1e6))
    print("GIFs in %s" % out)


if __name__ == "__main__":
    main()
