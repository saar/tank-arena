"""Make the pictures for the docs (docs/img/): game screens and the AI rewards.

    nix develop --command python3 tools/doc_shots.py [--model models/partner.pt] [--out docs/img]

The AI drives both tanks (as --ai-watch) until each reward event happened once. Each event
is drawn from the real game, with a frame and a label. The reward values come from ml/env.py.
"""
import argparse
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "ml"))

import pygame  # noqa: E402

import env as E  # noqa: E402  (also installs the reward hooks on the game classes)
import game  # noqa: E402
from config import FIELD, SCREEN_H, SCREEN_W  # noqa: E402
from hud import field_pos  # noqa: E402

PLUS, MINUS = (90, 220, 120), (245, 85, 70)
BG, FG, DIM = (26, 29, 36), (235, 235, 235), (150, 155, 165)

def pts(v):
    """A reward value as text: +1.0, -2.5, -0.02."""
    return "%+.2f" % v if abs(v * 10 - round(v * 10)) > 1e-9 else "%+.1f" % v


# kind: (reward text, name in ml/env.py, plain meaning, frames to wait before the picture)
EVENTS = {
    "kill": (pts(E.R_KILL), "R_KILL", "the AI destroys an enemy", 6),
    "base_kill": (pts(E.R_KILL) + " " + pts(E.R_KILL_NEAR_BASE), "R_KILL_NEAR_BASE",
                  "extra for a kill close to the base", 6),
    "item": (pts(E.R_ITEM), "R_ITEM", "the AI takes a useful item", 3),
    "power": (pts(E.R_POWER), "R_POWER", "each power level gained (a star)", 3),
    "death": (pts(E.R_DEATH), "R_DEATH", "the AI loses a life", 6),
    "danger": (pts(E.R_BASE_DANGER), "R_BASE_DANGER", "each step, per enemy in the base zone", 0),
    "wasted": (pts(E.R_WASTED_SHOT), "R_WASTED_SHOT", "a shell ends on steel or the map edge", 2),
    "stuck": (pts(E.R_STUCK), "R_STUCK", "each step the AI is stuck (steel, water, a tank)", 0),
    "freeze": (pts(E.R_FREEZE_PARTNER), "R_FREEZE_PARTNER", "the AI's shell freezes the partner", 2),
    "clear": (pts(E.R_CLEAR), "R_CLEAR", "the stage is cleared", 0),
}
ORDER = ["kill", "base_kill", "item", "power", "death", "freeze", "danger", "wasted", "stuck", "clear"]


class Tracker:
    """Collects reward events of the running world (hooks on top of the env hooks)."""

    def __init__(self):
        self.events = []
        orig_hit, orig_step = game.Enemy.hit, game.Bullet.step_hit
        tr = self

        def enemy_hit(en, by=None):
            alive = en.alive
            orig_hit(en, by)
            if alive and not en.alive and isinstance(by, game.Player):
                kind = "base_kill" if E.near_base(en.x, en.y) else "kill"
                tr.events.append((kind, [(en.x, en.y, 16)]))

        def step_hit(b):
            wasted = b.owner.side == "player" and E._wasted(b)
            x, y = b.x, b.y
            r = orig_step(b)
            if r and wasted:
                tr.events.append(("wasted", [(x - 6, y - 6, 12)]))
            return r

        game.Enemy.hit, game.Bullet.step_hit = enemy_hit, step_hit


def hidden(w, mark):
    """True if the marked thing is under trees (not visible in the picture)."""
    x, y, size = mark
    cx, cy = int(x + size / 2) // game.CELL, int(y + size / 2) // game.CELL
    return 0 <= cx < game.GRID and 0 <= cy < game.GRID and w.cells[cy][cx] == game.FOREST


def field_image(w):
    screen = pygame.Surface((SCREEN_W, SCREEN_H))
    w.draw(screen)
    fx, fy = field_pos()
    return screen.subsurface((fx, fy, FIELD, FIELD)).copy()


def tile(field, kind, marks, scale, font, small, zone=False):
    """The field, scaled, with frames around marks and a caption bar."""
    value, name, text, _ = EVENTS[kind]
    color = MINUS if value.startswith("-") else PLUS
    W = FIELD * scale
    img = pygame.Surface((W, W + 54))
    img.fill(BG)
    img.blit(pygame.transform.scale(field, (W, W)), (0, 0))
    if zone:
        z = E.BASE_ZONE
        r = pygame.Rect((E.HQ_C[0] - z) * scale, (E.HQ_C[1] - z) * scale, 2 * z * scale, 2 * z * scale)
        r = r.clip(pygame.Rect(0, 0, W, W))
        pygame.draw.rect(img, color, r, 2)
    for x, y, s in marks:
        r = pygame.Rect(int(x * scale) - 4, int(y * scale) - 4, s * scale + 8, s * scale + 8)
        pygame.draw.rect(img, color, r, 3)
        lab = font.render(value, True, (0, 0, 0))
        box = pygame.Rect(0, 0, lab.get_width() + 10, lab.get_height() + 4)
        box.midbottom = (r.centerx, r.top - 3)
        if box.top < 2:
            box.midtop = (r.centerx, r.bottom + 3)
        box.clamp_ip(pygame.Rect(2, 2, W - 4, W - 4))
        pygame.draw.rect(img, color, box)
        img.blit(lab, (box.x + 5, box.y + 2))
    img.blit(font.render("%s  %s" % (name, value), True, color), (8, W + 6))
    img.blit(small.render(text, True, FG), (8, W + 31))
    return img


def sheet(tiles, cols, gap=8):
    w, h = tiles[0].get_size()
    rows = (len(tiles) + cols - 1) // cols
    out = pygame.Surface((cols * w + (cols + 1) * gap, rows * h + (rows + 1) * gap))
    out.fill((14, 16, 20))
    for n, t in enumerate(tiles):
        out.blit(t, (gap + (n % cols) * (w + gap), gap + (n // cols) * (h + gap)))
    return out


def save(surf, path):
    pygame.image.save(surf, path)
    try:                                    # smaller files with Pillow
        from PIL import Image
        Image.open(path).save(path, optimize=True)
    except ImportError:
        pass
    print("%s: %dx%d, %d KB" % (path, *surf.get_size(), os.path.getsize(path) // 1024))


def find_events(A, model, scale, font, small, max_games):
    from agent import AIPilot
    import torch
    tr = Tracker()
    found = {}
    rnd = random.Random(1)
    for g in range(max_games):
        if len(found) == len(EVENTS):
            break
        stage = rnd.choice([s for s in range(1, 36) if s not in E.HOLDOUT_STAGES])
        random.seed(100 + g)
        torch.manual_seed(100 + g)
        pilots = [AIPilot(model, temp=1.0), AIPilot(model, temp=1.0)]
        w = game.World(A, stage, num_players=2)
        P = w.players
        pending = []                        # (frame to draw, kind, marks, zone)
        last = [(p.x, p.y) for p in P]
        for f in range(60 * 60 * 4):
            lives = [p.lives for p in P]
            frozen = [p.frozen for p in P]
            power = [E.power_value(p) for p in P]
            w.ml_items = []
            tr.events = []
            w.update([p.keys(w, i) for i, p in enumerate(pilots)])
            w.sfx.clear()
            for kind, marks in tr.events:
                pending.append((f + EVENTS[kind][3], kind, marks, False))
            for i, p in enumerate(P):
                if p.lives < lives[i]:
                    pending.append((f + EVENTS["death"][3], "death", [(*last[i], 16)], False))
                if p.frozen > frozen[i]:
                    pending.append((f + EVENTS["freeze"][3], "freeze", [(p.x, p.y, 16)], False))
                if E.power_value(p) > power[i]:
                    pending.append((f + EVENTS["power"][3], "power", [(p.x, p.y, 16)], False))
                if p.alive and p.stuck >= E.STUCK_FRAMES and not E.brick_ahead(p) and f % 4 == 0:
                    pending.append((f, "stuck", [(p.x, p.y, 16)], False))
                if p.alive:
                    last[i] = (p.x, p.y)
            for j, k in w.ml_items:
                if k not in E.POWER_ITEMS:
                    pending.append((f + EVENTS["item"][3], "item", [(P[j].x, P[j].y, 16)], False))
            near = [(e.x, e.y, 16) for e in w.enemies if e.alive and E.near_base(e.x, e.y)]
            if near:
                pending.append((f, "danger", near, True))
            if w.cleared:
                pending.append((f, "clear", [], False))
            for item in [x for x in pending if x[0] <= f]:
                _, kind, marks, zone = item
                if kind == "freeze" and (w.frame // 8) % 2:
                    continue                # the frozen tank blinks: wait until it shows
                pending.remove(item)
                if kind not in found and not any(hidden(w, m) for m in marks):
                    found[kind] = tile(field_image(w), kind, marks, scale, font, small, zone)
                    print("game %d stage %d frame %d: %s" % (g, stage, f, kind))
            if w.lost or w.cleared:
                break
    missing = [k for k in ORDER if k not in found]
    if missing:
        print("not found:", " ".join(missing))
    return [found[k] for k in ORDER if k in found]


def screens(A, model, scale):
    """Title, a 1-player game, a game with the AI partner (full screen with the panel)."""
    import main as M
    from agent import AIPilot
    import torch
    out = []
    app = M.App(None, 1, 0, None, M.ART_DIR, False)
    app.draw_title()
    out.append(app.canvas.copy())
    for players, seed, frames in ((1, 5, 900), (2, 7, 1500)):
        random.seed(seed)
        torch.manual_seed(seed)
        pilots = [AIPilot(model, temp=0.5) for _ in range(players)]
        w = game.World(A, 3 if players == 1 else 7, num_players=players)
        for _ in range(frames):
            w.update([p.keys(w, i) for i, p in enumerate(pilots)])
            w.sfx.clear()
        s = pygame.Surface((SCREEN_W, SCREEN_H))
        w.draw(s)
        out.append(s)
    return [pygame.transform.scale(s, (SCREEN_W * scale, SCREEN_H * scale)) for s in out]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=os.path.join(HERE, "..", "models", "partner.pt"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "img"))
    ap.add_argument("--games", type=int, default=40, help="most games to search for the events")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    E.init_pygame()
    pygame.font.init()
    A = E.load_assets()
    font, small = pygame.font.Font(None, 30), pygame.font.Font(None, 24)
    save(sheet(screens(A, a.model, 2), 3), os.path.join(a.out, "screens.png"))
    save(sheet(find_events(A, a.model, 2, font, small, a.games), 2), os.path.join(a.out, "rewards.png"))


if __name__ == "__main__":
    main()
