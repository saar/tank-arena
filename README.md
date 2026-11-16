# Tank Arena

A top-down tank game for 1 or 2 players. Defend your base, destroy 20 enemy tanks in each
stage, and collect items. A trained AI can drive the second tank as your partner, or you can
watch the AI play both tanks.

Tank Arena is an original work, made from scratch: all code, pixel art, sounds, maps and
enemy waves are new and belong to this project.

- [Start the game](#start-the-game)
- [How to play](#how-to-play)
- [Play with the AI partner](#play-with-the-ai-partner)
- [Watch the AI, record and replay games](#watch-the-ai-record-and-replay-games)
- [Map packs](#map-packs)
- [Train your own AI](#train-your-own-ai)
- [Folders](#folders)
- [License](#license)

## Start the game

**Play online:** <https://saar.github.io/tank-arena/>. No install; it runs in your browser,
with sound, gamepads and the AI partner. Click into the page once to start.

**With Nix** (recommended: you get the same tools that we use):

```sh
git clone <this repo> tank-arena
cd tank-arena
nix develop --command python3 src/main.py
```

**With Docker or Podman** (Linux, macOS, Windows): no clone and no install, one command. It
gets the ready image from the GitHub package registry and serves the game to your browser:

```sh
docker run --rm -it --init -p 127.0.0.1:8000:8000 ghcr.io/saar/tank-arena:latest
```

Then open <http://localhost:8000>. Ctrl+C in the terminal stops it. The browser version has
sound, gamepads and the AI partner. The page loads its Python runtime from the pygbag web
site, so the browser needs the internet.

**In a window** (Linux only, X11 and PulseAudio/PipeWire): add the `play` command and the
display options. Saved data (map packs, recordings) works only in this mode:

```sh
docker run --rm -it --init --user "$(id -u):$(id -g)" \
  -v ~/.local/share/tank-arena:/data \
  -e DISPLAY -e SDL_VIDEODRIVER=x11 -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  -e XAUTHORITY=/tmp/.Xauthority -v "${XAUTHORITY:-$HOME/.Xauthority}":/tmp/.Xauthority:ro \
  -e PULSE_SERVER=unix:/run/pulse/native -v "$XDG_RUNTIME_DIR/pulse/native":/run/pulse/native \
  ghcr.io/saar/tank-arena:latest play
```

With Podman, write `podman` for `docker` and `--userns=keep-id` for `--user "$(id -u):$(id -g)"`.
Your maps, models, recordings and training runs stay in `~/.local/share/tank-arena`. Game options
go after `play` (for example `play --ai-partner`). The image also has the AI partner and the
training tools: `... ghcr.io/saar/tank-arena:latest train --run ml/runs/my-ai --hours 1`.

In a clone of this repo, the script `container.sh` does the same with less to type
(`./container.sh` for the browser, `./container.sh play` for a window). Guide, all commands and
problems: [docs/CONTAINER.md](docs/CONTAINER.md).

**Build the browser version yourself:** pygbag packs the game for the web. The AI partner runs
there with numpy (`ml/npnet.py`), not torch. The online page is the same build, published by
`.github/workflows/pages.yml` for each version tag.

```sh
nix develop --command sh tools/web_build.sh          # files in build/web-src/build/web/
nix develop --command sh tools/web_build.sh --serve  # build and serve on http://localhost:8000
```

**Without Nix:** install Python 3.11 or newer, then:

```sh
pip install pygame-ce pillow          # the game
pip install numpy torch               # only for the AI partner and training
python3 src/main.py
```

In this README, every command starts with `nix develop --command`. Without Nix, leave that part out.

Useful options:

| Option | What it does |
|---|---|
| `--players 2` | Start with 2 players selected |
| `--stage 13` | Start on stage 13 |
| `--maps NAME` | Use this map pack (see [Map packs](#map-packs)) |
| `--mute` | No sound |
| `--scale 4` | Bigger window (default 3) |

## How to play

Protect the radio tower at the bottom of the map. If an enemy shell hits it, the game is over.
Destroy all 20 enemy tanks to clear the stage. The red bar on the left shows how many enemies
are left.

| Key | Action |
|---|---|
| Arrows or WASD | Move (1 player) |
| Space, Z or J | Fire (1 player) |
| WASD + Space or F | Player 1 (2 players) |
| Arrows + Right Ctrl, Enter or L | Player 2 (2 players) |
| Gamepad | Gamepad 1 = player 1, gamepad 2 = player 2. Stick or D-pad moves, buttons fire, Start pauses |
| P | Pause |
| Esc | Back to the title, or quit |
| + and - | Game speed (useful when you watch the AI) |

On the title screen: Up/Down picks the mode (1 player, 2 players, 1 player with AI),
Left/Right picks the stage, **M** (or the gamepad Back button) switches the map pack, Enter starts.

**Terrain:** brick breaks, steel breaks only at full power, water stops tanks, forest hides
tanks, and tanks slide on ice.

**Enemies:** basic (slow), fast, power (fast shells) and armor (4 hits). Flashing enemies
drop an item when you hit them.

**Items:**

| Item | Effect |
|---|---|
| Helmet | Shield for 10 seconds |
| Clock | All enemies stop for 10 seconds |
| Shovel | The base wall becomes steel for a short time |
| Star | More power: faster shells, then 2 shells, then shells that break steel |
| Grenade | Destroys all enemies on the screen |
| Tank | One extra life |
| Chevrons (gun) | Full power at once, and it absorbs one hit |
| Ship | Drive on water; it absorbs one hit |
| Flag (rescue) | 2 players: brings a partner with no lives back |
| Chain (link) | 2 players: shields both tanks, and partner shells pass through |
| Turret | A gun post above the base shoots enemies for 20 seconds |
| Repair | Rebuilds the broken bricks of the base wall |
| ? (mystery) | 2 random items appear |

With enough power, your shells cut a path through forest. With 2 players, a hit from your
partner freezes your tank for a few seconds: watch where you shoot.

**Test keys** (to try things out): 1–8 and F1–F5 give an item to player 1, `]` and `[` change
the power, N clears the stage.

## Play with the AI partner

The trained AI model is not in git. Download `partner.pt` from the
[Releases](../../releases) page and save it as `models/partner.pt`. Then:

```sh
nix develop --command python3 src/main.py --ai-partner
```

Or choose **1P WITH AI** on the title screen. You drive player 1 (yellow); the AI drives
player 2 (cyan). To use another model: `--ai-partner path/to/model.pt`.

## Watch the AI, record and replay games

These tools are handy to see what a model has learned.

```sh
# The AI drives both tanks. Games start by themselves, one after the other.
nix develop --command python3 src/main.py --ai-watch --speed 4

# Record every game you play (or watch) to recordings/
nix develop --command python3 src/main.py --ai-watch --record

# Play a recording again in a window (Space pause, + and - speed, Right: next stage)
nix develop --command python3 tools/replay.py recordings/FILE.rec.json.gz

# Turn a recording into an animated WebP or GIF (to share or compare)
nix develop --command python3 tools/replay.py recordings/FILE.rec.json.gz --webp game.webp --scale 3

# Put several animations side by side in one picture
nix develop --command python3 tools/compose.py a.webp b.webp -o both.webp --cols 2
```

A recording is small: it keeps only the keys and the random seed, not pictures. If you change
the game rules later, an old recording plays differently, and `replay.py` warns you ("desync").

To let several models play the **same** stage from the same start, and get one animation per
model: `ml/compare.py` (see [docs/TRAINING.md](docs/TRAINING.md)).

## Map packs

A map pack is a folder of text files, one file per stage. You can draw maps in any text editor.
The game comes with the `default` pack (35 stages).

```sh
# Install a pack for good (it is copied into your user data folder)
nix develop --command python3 src/main.py --install-maps path/to/my-pack --name mine

# List the installed packs / remove one
nix develop --command python3 src/main.py --list-maps
nix develop --command python3 src/main.py --remove-maps mine
```

Then press **M** on the title screen to choose the pack. The game remembers your choice.
The file format, examples and tips are in [docs/MAPS.md](docs/MAPS.md).

## Train your own AI

The AI partner learns by playing the game millions of times, without a window. It gets
points for good actions (rewards) and loses points for bad ones (punishments). You can change
these points, and so teach the AI another style of play.

```sh
nix develop --command python3 ml/train.py --run ml/runs/my-ai --hours 1
nix develop --command python3 src/main.py --ai-watch --ai-partner ml/runs/my-ai/latest.pt
```

The full guide, with examples of reward changes, is in [docs/TRAINING.md](docs/TRAINING.md).
The technical details are in [ml/README.md](ml/README.md).

## Folders

| Folder | What is in it |
|---|---|
| `src/` | The game. `main.py` (window, menus), `game.py` (rules, tanks, items), `config.py` (all numbers), `hud.py` (screen layout), `maps.py` (map files), `packs.py` (installed packs), `mapgen.py` (random maps), `sound.py` (sounds made in code) |
| `art/` | The art kit: one SVG file per sprite (see [art/README.md](art/README.md)) |
| `maps/default/` | The built-in map pack |
| `ml/` | The AI partner: game environment, network, training, tests |
| `tools/` | `draw_art.py` (draws the sprites), `make_maps.py` (makes map packs), `replay.py` and `compose.py` (recordings to animations) |
| `docs/` | Guides: map packs, AI training, container |
| `container/`, `Dockerfile`, `container.sh` | The container image and its start script (see [docs/CONTAINER.md](docs/CONTAINER.md)) |

To check the game logic after a change: `nix develop --command python3 src/test_logic.py`.
Design notes and ideas: [DESIGN.md](DESIGN.md). Notes for AI coding assistants: [AGENTS.md](AGENTS.md).

## License

GPL-3.0 (see `LICENSE`). This covers the code, the art kit, the maps and the released AI model.
