#!/usr/bin/env python3
"""Tank Arena. Run:  nix develop --command python3 src/main.py

Keys (1 player): arrows/WASD move, Space/Z/J fire.
Keys (2 players): player 1 WASD + Space/F, player 2 arrows + Right Ctrl/Enter/L.
Gamepads (see pad.py): gamepad 1 controls player 1, gamepad 2 controls player 2.
  D-pad/left stick move, A/B/X/Y/right trigger fire, Start = start/pause, Back (Select) = to the title.
P pause, Esc back/quit.
Test keys (player 1): 1-8 and F1-F5 give an item, ] / PgUp power up, [ / PgDn power down, N clear stage.
Title: Up/Down 1 player, 2 players or "1P WITH AI", Left/Right choose the stage, Enter start.
"1P WITH AI": a trained AI drives player 2 (models/partner.pt, or --ai-partner MODEL);
--ai-watch: the AI drives both players. Train your own with ml/train.py.
  It starts by itself and plays game after game (a random stage after each game over).
--speed N: run N game frames per screen frame (1-32). Keys + and - change it while running.
  Above 2x the sound is off.
--record [DIR]: save each game (keys + random seed, small) to DIR (default recordings/);
  tools/replay.py plays it again or makes a GIF.
"""
import argparse
import os
import random
import sys
import time

import pygame

WEB = sys.platform == "emscripten"      # the browser build (pygbag, tools/web_build.sh)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assets import Assets  # noqa: E402
from config import *       # noqa: E402,F403
from game import World     # noqa: E402
import hud                 # noqa: E402
import packs               # noqa: E402
from maps import MapError, MapPack  # noqa: E402
from pad import Pads       # noqa: E402
from record import Recorder  # noqa: E402
from sound import Sound    # noqa: E402

GAME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ART_DIR = os.path.join(GAME_DIR, "art")
ML_DIR = os.path.join(GAME_DIR, "ml")
KEYMAP = {                       # 1 player: both key sets work
    "up": (pygame.K_UP, pygame.K_w), "down": (pygame.K_DOWN, pygame.K_s),
    "left": (pygame.K_LEFT, pygame.K_a), "right": (pygame.K_RIGHT, pygame.K_d),
    "fire": (pygame.K_SPACE, pygame.K_z, pygame.K_j),
}
KEYMAP_2P = [
    {"up": (pygame.K_w,), "down": (pygame.K_s,), "left": (pygame.K_a,), "right": (pygame.K_d,),
     "fire": (pygame.K_SPACE, pygame.K_f)},
    {"up": (pygame.K_UP,), "down": (pygame.K_DOWN,), "left": (pygame.K_LEFT,), "right": (pygame.K_RIGHT,),
     "fire": (pygame.K_RCTRL, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_l)},
]
NO_KEYS = {name: False for name in KEYMAP}
SPEED_KEYS = {pygame.K_EQUALS: 1, pygame.K_PLUS: 1, pygame.K_KP_PLUS: 1, pygame.K_MINUS: -1, pygame.K_KP_MINUS: -1}
TITLE_MODES = ("1p", "2p", "ai")     # 1 player, 2 players, 1 player + AI partner


# Test keys (play scene). 1-8: helmet clock shovel star grenade tank gun ship.
# F1-F5: our new items rescue link turret repair mystery.
CHEAT_KEYS = {getattr(pygame, "K_%d" % (i + 1)): i for i in range(8)}
CHEAT_KEYS.update({getattr(pygame, "K_F%d" % (i + 1)): RESCUE + i for i in range(5)})
CHEAT_KEYS.update({pygame.K_RIGHTBRACKET: "up", pygame.K_LEFTBRACKET: "down",
                   pygame.K_PAGEUP: "up", pygame.K_PAGEDOWN: "down", pygame.K_n: "clear"})


def apply_cheat(w, act):
    """A test key (CHEAT_KEYS value) for player 1; also used by tools/replay.py."""
    p = w.players[0]
    if not p.alive:
        return
    if isinstance(act, int):
        w.sound("extra_life" if act in (TANK, RESCUE) else "item_get")
        w.player_item(p, act)
    elif act == "up":
        p.power = min(3, p.power + 1)
        w.sound("item_get")
    elif act == "down":
        p.power = max(0, p.power - 1)
        p.gun = False
        w.sound("armor")
    elif act == "clear":
        for e in w.enemies:
            e.alive = False
        w.enemies, w.pending_spawns, w.reserve = [], [], 0


def read_keys(players, pads):
    """One key dict per player. Keyboard and gamepads are merged."""
    k = pygame.key.get_pressed()
    maps = [KEYMAP] if players == 1 else KEYMAP_2P
    out = [{name: any(k[c] for c in codes) for name, codes in m.items()} for m in maps]
    for i in range(min(players, len(pads))):
        for name in out[i]:
            out[i][name] = out[i][name] or pads[i].now[name]
    return out


class App:
    def __init__(self, maps, scale, autoplay=0, shot=None, art_dir=None, sound=True):
        self.screen = pygame.display.set_mode((SCREEN_W * scale, SCREEN_H * scale))
        pygame.display.set_caption(GAME_TITLE.title())
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H))
        self.assets = Assets(packs.resolve(maps), art_dir)
        self.packs = list(packs.available())          # pack names for the title screen
        self.pack = next((n for n, d in packs.available().items()
                          if os.path.abspath(d) == self.assets.maps.path), None)
        self.snd = Sound(sound)
        self.clock = pygame.time.Clock()
        self.stage = 1
        self.scene = "title"
        self.timer = 0
        self.world = None
        self.paused = False
        self.autoplay, self.shot = autoplay, shot
        self.hi = 20000
        self.players = 1
        self.mode = "1p"                # title entry: "1p", "2p" or "ai" (1 player + AI partner)
        self.ai = None                  # in a game: one AIPilot (or None = human) per player
        self.ai_model = None            # model path (None: models/partner.pt)
        self.ai_watch = False           # "ai" mode: the AI drives player 1 too
        self.pilots = None              # loaded AI pilots (loaded on first use)
        self.msg = ""                   # red message on the title
        self.pads = Pads()
        self.speed = 1                  # game frames per screen frame (fast watch)
        self.record_dir = None          # --record: save each game here
        self.rec = None                 # the Recorder of the running game
        self.frames = 0                 # screen frames since start

    # ---- scenes -----------------------------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        self.players = 1 if mode == "1p" else 2

    def load_ai(self):
        """Load the AI pilots once (torch is imported only here). False if not possible."""
        if self.pilots is None:
            try:
                sys.path.insert(0, ML_DIR)
                from agent import AIPilot, DEFAULT_MODEL
                path = self.ai_model or DEFAULT_MODEL
                self.pilots = [AIPilot(path, temp=0.5) if self.ai_watch else None, AIPilot(path, temp=0.5)]
            except Exception as e:     # no torch, no model file, old model
                print("AI partner not available:", e)
                self.msg = "NO AI MODEL"
                return False
        return True

    def new_game(self):
        if self.mode == "ai" and not self.load_ai():
            return
        self.ai = self.pilots if self.mode == "ai" else None
        self.msg = ""
        self.end_recording()
        self.start_recording()
        self.start_stage()

    def start_stage(self, carry=None):
        if self.rec:
            self.world = self.rec.new_world(self.assets, self.stage, carry, self.players)
            self.rec.save(self.rec_path)        # the stages so far (safe if the game crashes)
        else:
            self.world = World(self.assets, self.stage, carry, self.players)
        self.scene, self.timer = "intro", 90
        self.snd.engine(None)
        self.snd.play("stage_start")

    def title_key(self, key):
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            step = 1 if key in (pygame.K_RIGHT, pygame.K_d) else -1
            self.stage = max(1, min(self.assets.maps.count, self.stage + step))
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s):
            step = 1 if key in (pygame.K_DOWN, pygame.K_s) else -1
            i = max(0, min(len(TITLE_MODES) - 1, TITLE_MODES.index(self.mode) + step))
            self.set_mode(TITLE_MODES[i])
            self.msg = ""
        elif key in (pygame.K_m, pygame.K_TAB):
            self.next_pack()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.new_game()

    def next_pack(self):
        """Title screen: switch to the next installed map pack and remember it."""
        names = self.packs
        if len(names) < 2:
            self.msg = "NO OTHER MAP PACKS"
            return
        name = names[(names.index(self.pack) + 1) % len(names)] if self.pack in names else names[0]
        try:
            self.assets.maps = MapPack(packs.available()[name])
        except MapError as e:
            print(e)
            self.msg = "BAD MAP PACK"
            return
        self.pack, self.msg = name, ""
        self.stage = min(self.stage, self.assets.maps.count)
        packs.save_settings(maps=name)

    def draw_title(self):
        A, c = self.assets, self.canvas
        c.fill(hud.BG)
        hud.draw_title_logo(A, c, GAME_TITLE)
        y = 104
        labels = {"1p": "1 PLAYER", "2p": "2 PLAYERS", "ai": "AI WATCH" if self.ai_watch else "1P WITH AI"}
        for n, m in enumerate(TITLE_MODES):
            A.text(c, labels[m], 72, y + 14 * n)
        cy = y + 14 * TITLE_MODES.index(self.mode)
        c.blit(A.tank(0, "right", (self.timer // 8) % 2, "player"), (48, cy - 4))
        A.text(c, "STAGE", 72, 147)
        A.text(c, str(self.stage), 120, 147, "textred")
        name = (self.pack or "CUSTOM").upper()[:12]
        A.text(c, "MAPS", 72, 158)
        A.text(c, name, 112, 158, "textred")
        for n, hint in enumerate(("UP DOWN  MODE", "LEFT RIGHT  STAGE", "M  MAP PACK")):
            A.text(c, hint, 128 - len(hint) * 4, 170 + n * 9, "textgray")
        if self.msg:
            A.text(c, self.msg, 128 - len(self.msg) * 4, 200, "textred")
        else:
            A.text(c, "ENTER OR START", 72, 200)
        A.text(c, "HI " + str(self.hi), 128 - (3 + len(str(self.hi))) * 4, 211)

    def draw_banner(self, text):
        hud.draw_banner(self.assets, self.canvas, text)

    # ---- loop -------------------------------------------------------------
    def run(self):
        while self.frame():
            if not self.autoplay:
                self.clock.tick(FPS)

    async def run_async(self):
        """The same loop for the browser (pygbag): give control back after each frame."""
        import asyncio
        while self.frame():
            self.clock.tick(FPS)
            await asyncio.sleep(0)

    def frame(self):
        """One screen frame: input, game frames, draw. False: quit."""
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.end_recording()
                return False
            self.pads.event(ev)
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.scene == "title":
                        if not WEB:             # the browser page cannot quit
                            self.end_recording()
                            return False
                    else:
                        self.to_title()
                elif self.scene == "title":
                    self.title_key(ev.key)
                elif ev.key in SPEED_KEYS:
                    self.set_speed(self.speed * 2 if SPEED_KEYS[ev.key] > 0 else self.speed // 2)
                elif self.scene in ("play", "clear") and ev.key in CHEAT_KEYS:
                    self.cheat(ev.key)
                elif self.scene in ("play", "clear") and ev.key == pygame.K_p:
                    self.toggle_pause()
        self.pads.poll()
        self.pad_menu()
        for _ in range(self.speed):             # fast mode: several game frames per screen frame
            keys = self.input_keys()
            if self.autoplay:
                keys = [keys[i] if self.ai_drives(i) else self.fake_keys(self.frames, i) for i in range(self.players)]
            self.tick(keys)
        if self.speed > 1:
            self.assets.text_color(self.canvas, "X%d" % self.speed, 2, 214, (230, 230, 230))
        pygame.transform.scale(self.canvas, self.screen.get_size(), self.screen)
        pygame.display.flip()
        self.frames += 1
        if self.autoplay and self.frames == self.autoplay:
            if self.shot:
                pygame.image.save(self.canvas, self.shot)
            self.end_recording()
            return False
        return True

    def set_speed(self, n):
        self.speed = max(1, min(32, n))
        if self.speed > 2:
            self.snd.stop_all()

    def to_title(self):
        self.end_recording()
        self.scene = "title"
        self.timer = 0
        self.paused = False
        self.snd.stop_all()

    def toggle_pause(self):
        self.paused = not self.paused
        self.snd.engine(None)
        self.snd.play("pause")

    def pad_menu(self):
        """Gamepad menu buttons: the title menu, Start = pause, Back (Select) = to the title."""
        P = self.pads.pressed
        if self.scene == "title":
            for name, key in (("up", pygame.K_UP), ("down", pygame.K_DOWN),
                              ("left", pygame.K_LEFT), ("right", pygame.K_RIGHT)):
                if P(name):
                    self.title_key(key)
            if P("back"):
                self.next_pack()
            elif P("start") or P("fire"):
                self.new_game()
        elif self.scene in ("play", "clear"):
            if P("start"):
                self.toggle_pause()
            elif P("back"):
                self.to_title()

    def ai_drives(self, i):
        return bool(self.ai and self.players > 1 and self.ai[i])

    def input_keys(self):
        """One key dict per player: keyboard/gamepads, or the AI pilot for AI seats."""
        if not self.ai or self.players == 1:
            return read_keys(self.players, self.pads)
        human = read_keys(1, self.pads)[0]     # the 1-player key map (both key sets) + gamepad 1
        out = []
        for i in range(self.players):
            if not self.ai_drives(i):
                out.append(human)
            elif self.world is not None and self.scene in ("play", "clear") and not self.paused:
                out.append(self.ai[i].keys(self.world, i))
            else:
                out.append(dict(NO_KEYS))
        return out

    def fake_keys(self, n, i=0):
        """Smoke test: start a game and wander around firing."""
        if self.scene == "title" and n == 5:
            self.new_game()
        k = dict(NO_KEYS)
        n += i * 135
        if (n // 90) % 5 != 4:
            k[["up", "left", "up", "right", "down"][(n // 90) % 5]] = True
        k["fire"] = n % 12 < 6
        return k

    def cheat(self, key):
        """Test keys: 1-8 and F1-F5 give an item, [ and ] change the power, N clears the stage."""
        if not self.world.players[0].alive:
            return
        if self.rec:
            self.rec.cheat(CHEAT_KEYS[key])
        apply_cheat(self.world, CHEAT_KEYS[key])

    # ---- recording (--record) ----------------------------------------------
    def start_recording(self):
        if not self.record_dir:
            return
        os.makedirs(self.record_dir, exist_ok=True)
        pilots = ["ai:" + os.path.basename(self.ai_model or "partner.pt") if self.ai_drives(i) else "human"
                  for i in range(self.players)]
        self.rec = Recorder(self.players, pilots, dict(mode=self.mode, model=self.ai_model))
        self.rec_path = os.path.join(self.record_dir, "%s-%s.rec.json.gz" % (
            time.strftime("%Y%m%d-%H%M%S"), self.mode))

    def end_recording(self):
        if self.rec and self.rec.save(self.rec_path):
            print("recording saved: %s" % self.rec_path, flush=True)
        self.rec = None

    def step_world(self, keys):
        """keys: one key dict per player."""
        w = self.world
        if self.rec:
            self.rec.step(keys)
        w.update(keys)
        if self.speed > 2:                  # fast mode: no sound
            w.sfx.clear()
            return
        self.snd.play_events(w.sfx)
        w.sfx.clear()
        alive = [p for p in w.players if p.alive]
        self.snd.engine(None if not alive or self.scene == "over" else
                        "move" if any(p.moving for p in alive) else "idle")

    def tick(self, keys):
        if self.scene == "title":
            self.timer += 1
            self.draw_title()
            if self.ai_watch and self.mode == "ai" and self.timer > 60 and not self.msg:
                if self.world is not None:          # watch: after a game over, a random stage
                    self.stage = random.randint(1, self.assets.maps.count)
                self.new_game()
        elif self.scene == "intro":
            self.draw_banner("STAGE %d" % self.stage)
            self.timer -= 1
            if self.timer <= 0:
                self.scene = "play"
        elif self.scene in ("play", "clear"):
            # "clear": the game keeps running for CLEAR_DELAY frames after the
            # last kill, so the player can still take an item.
            w = self.world
            if not self.paused:
                self.step_world(keys)
            w.draw(self.canvas)
            if self.paused and (w.frame // 16) % 2 == 0:
                self.assets.text(self.canvas, "PAUSE", 104, 112, "textred")
            if self.scene == "clear":
                if not self.paused:
                    self.timer -= 1
                if self.timer <= 0:
                    self.snd.engine(None)
                    self.begin_tally("next")
            elif w.lost:
                self.scene, self.timer = "over", OVER_DELAY
                self.snd.engine(None)
                self.snd.play("game_over")
            elif w.cleared:
                self.scene, self.timer = "clear", CLEAR_DELAY
        elif self.scene == "over":
            # the enemies keep moving while GAME OVER rises (no player input)
            self.step_world([NO_KEYS] * self.players)
            self.world.draw(self.canvas)
            y = 104 + max(0, self.timer - 120)
            self.assets.text(self.canvas, "GAME", 112, y, "textred")
            self.assets.text(self.canvas, "OVER", 112, y + 9, "textred")
            self.timer -= 1
            if self.timer <= 0:
                self.snd.engine(None)
                self.begin_tally("title")
        elif self.scene == "tally":
            self.tick_tally(any(k["fire"] for k in keys))

    # ---- stage tally ------------------------------------------------------
    TALLY_ROW = 24          # frames before a row starts counting
    TALLY_STEP = 8          # frames per counted tank
    TALLY_HOLD = 150        # frames to show the result

    def begin_tally(self, after):
        w = self.world
        self.hi = max([self.hi] + [p.score for p in w.players])
        kills = [list(p.kills) for p in w.players]
        bonus = None
        if len(w.players) > 1 and after == "next":
            # 2P: the player with more kills gets TALLY_BONUS (no bonus on a tie)
            totals = [sum(k) for k in kills]
            if totals[0] != totals[1]:
                bonus = 0 if totals[0] > totals[1] else 1
        self.tally = dict(after=after, t=0, kills=kills, bonus=bonus, paid=False)
        self.scene = "tally"

    def tally_rows(self):
        """Number of tanks to count in each row (the larger of the players)."""
        return [max(k[i] for k in self.tally["kills"]) for i in range(4)]

    def tally_counts(self):
        """How many tanks of each row are shown at time t; done flag."""
        t, shown = self.tally["t"], []
        for k in self.tally_rows():
            n = max(0, min(k, (t - self.TALLY_ROW) // self.TALLY_STEP + 1)) if t >= self.TALLY_ROW else 0
            shown.append(n)
            t -= self.TALLY_ROW + k * self.TALLY_STEP
        return shown, t >= 0

    def tick_tally(self, fire):
        T = self.tally
        before, _ = self.tally_counts()
        T["t"] += 1
        shown, done = self.tally_counts()
        if shown != before:
            self.snd.play("tally")
        if done and T["bonus"] is not None and not T["paid"]:
            T["paid"] = True
            self.world.players[T["bonus"]].score += TALLY_BONUS
            self.snd.play("item_get")
        self.draw_tally(shown, done)
        skip = fire and T["t"] > 30
        if (done and T["t"] > sum(self.TALLY_ROW + k * self.TALLY_STEP for k in self.tally_rows()) + self.TALLY_HOLD) or skip:
            w = self.world
            if T["bonus"] is not None and not T["paid"]:
                T["paid"] = True
                w.players[T["bonus"]].score += TALLY_BONUS
            self.hi = max([self.hi] + [p.score for p in w.players])
            if T["after"] == "title":
                self.end_recording()
                self.scene = "title"
                self.timer = 0
                return
            self.stage += 1
            if self.stage > 2 * self.assets.maps.count:       # 2 rounds, then stage 1
                self.stage = 1
            self.start_stage(w.players)

    def draw_tally(self, shown, done):
        A, c, w, T = self.assets, self.canvas, self.world, self.tally
        two = len(w.players) > 1
        c.fill((0, 0, 0))
        A.text(c, "HI-SCORE", 64, 16, "textred")
        A.text(c, str(self.hi), 192 - len(str(self.hi)) * 8, 16)
        A.text(c, "STAGE %d" % w.stage, 96, 36)
        # player columns: (label x, score right edge, pts x, count x)
        cols = [(32, 104, 24, 112)] if not two else [(8, 80, 8, 88), (168, 248, 168, 144)]
        tank_x = 136 if not two else 120
        for p, (lx, sr, px, nx) in zip(w.players, cols):
            label = "PLAYER %d" % (p.idx + 1) if two else "PLAYER"
            A.text(c, label, lx, 56, "textred")
            A.text(c, str(p.score), sr - len(str(p.score)) * 8, 68)
            for i, n in enumerate(shown):
                y = 92 + i * 22
                m = min(n, T["kills"][p.idx][i])
                pts = m * ENEMY_TYPES[i]["score"]
                A.text(c, "%5d PTS" % pts, px, y)
                A.text(c, "%2d" % m, nx, y)
            if done:
                A.text(c, "TOTAL %2d" % sum(T["kills"][p.idx]), lx if two else 64, 188)
                if T["bonus"] == p.idx:
                    A.text(c, "BONUS", lx, 202, "textred")
                    A.text(c, "%d PTS" % TALLY_BONUS, lx + 8, 211)
        for i in range(4):
            c.blit(A.tank(4 + i, "up", 0, "enemy"), (tank_x, 92 + i * 22 - 4))
        pygame.draw.line(c, (255, 255, 255), (tank_x - 32, 180), (tank_x + 24, 180), 2)


def main():
    ap = argparse.ArgumentParser(description="Tank Arena")
    ap.add_argument("--maps", metavar="NAME|DIR", help="map pack: an installed name or a folder (default: the last one chosen)")
    ap.add_argument("--install-maps", metavar="DIR", help="check a map pack folder and install it for good, then quit")
    ap.add_argument("--name", help="name for --install-maps (default: the folder name)")
    ap.add_argument("--list-maps", action="store_true", help="list the installed map packs, then quit")
    ap.add_argument("--remove-maps", metavar="NAME", help="remove an installed map pack, then quit")
    ap.add_argument("--scale", type=int, default=SCALE)
    ap.add_argument("--autoplay", type=int, default=0, help="smoke test: run N frames with fake input")
    ap.add_argument("--shot", help="save a screenshot at the end of --autoplay")
    ap.add_argument("--stage", type=int, default=1)
    ap.add_argument("--players", type=int, choices=(1, 2), default=1, help="1 or 2 players (title default)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--mute", action="store_true", help="no sound")
    ap.add_argument("--ai-partner", nargs="?", const="", metavar="MODEL",
                    help="start on \"1P WITH AI\"; MODEL: other model (default models/partner.pt)")
    ap.add_argument("--ai-watch", action="store_true", help="the AI drives both players; games start by themselves")
    ap.add_argument("--record", nargs="?", const=os.path.join(GAME_DIR, "recordings"), metavar="DIR",
                    help="save each game to DIR (default recordings/); see tools/replay.py")
    ap.add_argument("--speed", type=int, default=1, help="game frames per screen frame (1-32; keys + and -)")
    a = ap.parse_args()
    if a.install_maps or a.list_maps or a.remove_maps:
        try:
            if a.install_maps:
                packs.install(a.install_maps, a.name)
            if a.remove_maps:
                packs.remove(a.remove_maps)
        except (MapError, ValueError) as e:
            sys.exit("error: %s" % e)
        for n, d in packs.available().items():
            print("%-16s %3d stages  %s" % (n, MapPack(d).count, d))
        print("(choose one on the title screen with M, or start with --maps NAME)")
        return
    if a.seed is not None:
        random.seed(a.seed)
    if a.autoplay:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    app = App(a.maps, a.scale, a.autoplay, a.shot, ART_DIR, not a.mute)
    app.stage = a.stage
    app.set_mode("2p" if a.players == 2 else "1p")
    app.ai_model, app.ai_watch = a.ai_partner or None, a.ai_watch
    app.set_speed(a.speed)
    app.record_dir = a.record
    if a.ai_partner is not None or a.ai_watch:
        app.set_mode("ai")
    app.run()
    pygame.quit()


if __name__ == "__main__":
    main()
