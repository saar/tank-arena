# AGENTS.md

Guide for AI coding agents that work on this repository. Human docs: `README.md`, `docs/`.

## Project

Tank Arena: a top-down tank game in Python + pygame-ce (1–2 players, 256×224 screen scaled up),
with an AI partner trained by PPO (PyTorch). Original work: all code, art, sounds, maps.

## Hard rules

- **Original content only.** Do not add names, art, sound, music, maps, level data or text
  from existing commercial games, and do not name or describe this game as a copy or clone of
  one. Game mechanics may be common to the genre; content must be new.
- Do not commit model files (`*.pt`), `models/`, `ml/runs/` or `recordings/` (all git-ignored).
  The released model is attached to a GitHub release, not stored in git.
- The AI partner learns its behavior from rewards. Do not add hard-coded action rules. The
  only accepted rule is `env.safe_action` (never fire at the own base).
- Keep all game numbers in `src/config.py`.

## Environment and commands

All tools come from `flake.nix`; run them with `nix develop --command ...` from the repo root.
Without Nix: Python 3.11+, `pip install pygame-ce pillow numpy torch`.

```sh
nix develop --command python3 src/test_logic.py                    # logic tests (plain script, no pytest)
nix develop --command python3 src/main.py --autoplay 900 --seed 3 --shot /tmp/x.png   # headless smoke run + screenshot
nix develop --command python3 src/main.py [--stage N] [--players 2] [--maps NAME|DIR] [--mute]
nix develop --command python3 src/main.py --ai-partner [MODEL] | --ai-watch [--speed 8] [--record [DIR]]
nix develop --command python3 src/main.py --install-maps DIR [--name N] | --list-maps | --remove-maps N
nix develop --command python3 tools/replay.py FILE.rec.json.gz [--webp out.webp --scale 3]
nix develop --command python3 tools/make_maps.py [--out DIR] [--only N --seed S] [--sheet out.png]
nix develop --command python3 tools/draw_art.py [id-prefix] [--preview out.png]
nix develop --command python3 ml/train.py --run ml/runs/NAME --hours H [--resume | --init MODEL] [--maps P]
nix develop --command python3 ml/evaluate.py MODEL --partner bot
nix develop --command python3 ml/benchmark.py MODEL [MODEL2 ...]          # fixed 135 games
nix develop --command python3 ml/compare.py MODEL|RUN_DIR ... --stage N [--format webp --grid]
```

Container (Docker/Podman): `./container.sh build`, then `./container.sh [web]|play|train|test ...` (`web`, the default, serves the browser build on port 8000); guide
`docs/CONTAINER.md`. `Dockerfile` copies the repo and builds the browser version into `/app/web`, `container/entrypoint.sh` maps the first word to a
program, all saved data goes to `/data`. Keep the container docs in sync when you add CLI options
or saved files.

After a change, run `src/test_logic.py` and the headless smoke run. For an ML change, also a
short training (`--hours 0.05 --workers 2`). Headless runs need `SDL_VIDEODRIVER=dummy`
(`--autoplay` sets it).

## Architecture

- `src/game.py`: `World` holds all game state and rules; it is headless. It never plays
  sound: it adds event names to `World.sfx`, and `main.App` plays them through `sound.Sound`.
  `World(assets, stage, players=None, num_players=1, grid=None)`; `World.update()` takes one
  key dict per player. Score, kills and lives live on each `Player`.
- `src/main.py`: window and scenes (title → intro → play → clear/tally → next stage; game over).
  `apply_cheat` is shared with `tools/replay.py`.
- `src/hud.py`: screen layout: field position `FIELD_POS`, the left info panel, the title logo,
  the stage banner. Use `hud.field_pos()`, not fixed numbers.
- `src/assets.py`: `Assets(map_dir, art_dir)` holds all surfaces (from the art kit via
  `art.apply`) and the map pack (`assets.maps`). Text: `Assets.text` / `text_color`.
- `src/maps.py`: map pack format (13 rows of 13 chars + `enemies:` line of 20 letters) and
  `MapPack`. `src/packs.py`: installed packs in the user data folder (`TANK_ARENA_HOME`
  overrides it; use it in tests) and `settings.json`.
- `src/mapgen.py`: random maps (AI training). `tools/make_maps.py`: the styled default pack.
- `src/record.py`: recordings (keys + seed per stage). The game must use `random` only inside
  `World` while a stage runs, or replays desync.
- `art/`: one SVG per sprite with an `art` layer (used) and a `grid` layer (ignored).
  Tank SVGs use only 3 key colors (`#a0a0a0`, `#505050`, `#ffffff`), recolored at run time
  from `PAL_SPR` in `assets.py`. `tools/draw_art.py` writes sprites into `<g id="generated">`
  and skips files with hand-drawn content unless `--force`.

### AI partner (`ml/`)

- `env.py` (no torch import, so forked workers stay small): `TankEnv` wraps a 2-player `World`;
  1 step = 4 frames, 10 actions. Rewards are the `R_*` constants and are applied in
  `TankEnv.step()`. Hooks on `Bullet`/`Enemy.hit` track who shot the base or an enemy.
- `observe()` builds the input: a 39×26×26 grid (17 channels now + 11 moving channels from 2
  and 4 steps ago, `Memory`) and a 186-number vector. **If you change the observation, extend
  `model.upgrade()`** so older checkpoints load (new inputs get zero weights).
- `model.py`: `Net` ("small" default, "big" option), `load()` with `weights_only=True`.
- `train.py`: PPO with worker processes (fork on Linux, spawn on macOS), opponent pool
  (`<run>/pool/`), checkpoints `ckpt_*.pt` and `latest.pt`.
- `benchmark.py` uses `env.HOLDOUT_STAGES` (5, 12, 19, 26, 33), which training never plays.
- `agent.py`: `AIPilot` for the game; default model `models/partner.pt`.

## Conventions

- Plain, short comments and docs (simple English). Docs for players go to `README.md` and
  `docs/`; ML internals to `ml/README.md`.
- A change of rules may need more AI training; say so in the change description.
- A change of the map format must keep `maps.parse` and `maps.format_stage` in sync and
  update `docs/MAPS.md`.
- New art: draw it in `tools/draw_art.py` (pixel grids), run it, check with `--preview`.
