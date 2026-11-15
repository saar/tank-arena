# AI partner (ml)

A neural network learns to play as player 2 next to a human. It trains with
PPO on the real game logic (`game.World`), without UI, as fast as the CPU goes.

This is the technical reference. For a plain-English guide with examples, see
[docs/TRAINING.md](../docs/TRAINING.md). The released model goes to `models/partner.pt`
(the game's default).

## Commands (from the repo root)

```sh
nix develop --command python3 ml/train.py --run ml/runs/v1 --hours 1            # train
nix develop --command python3 ml/train.py --run ml/runs/v1 --hours 4 --resume   # continue
nix develop --command python3 ml/train.py --run ml/runs/v4 --init ml/runs/v1/latest.pt   # new run from a model
nix develop --command python3 ml/evaluate.py ml/runs/v1/latest.pt --partner bot  # measure
nix develop --command python3 ml/evaluate.py random --partner bot                           # baseline
nix develop --command python3 ml/benchmark.py ml/runs/v1/latest.pt models/partner.pt       # fixed 135-game test
nix develop --command python3 src/main.py --ai-partner        # play with it ("1P WITH AI" on the title)
nix develop --command python3 src/main.py --ai-watch          # watch it play both tanks
```

Ctrl-C stops training after the current iteration and saves `latest.pt` (Ctrl-C twice: quit now).

`compare.py <folder or models> --stage N [--map-seed S] [--partner self|bot]` lets each model play the
same stage from the same start; each game becomes its own GIF (full game screen + a label line) with
its recording, in `runs/compare/<test>/` (a GIF that is there is not made again; `--redo`).
`tools/compose.py A.gif B.gif ... -o grid.gif` (or `compare.py --grid`) puts GIFs side by side.
`--format webp` (and `replay.py --webp`) writes lossless animated WebP: the same pixels, exact frame
times, ~5x smaller than GIF at scale 1 and ~10x at scale 3 (a 42 s game: GIF 2.6/5.0/8.2 MB, WebP
0.5/0.6/0.8 MB at scale 1/2/3). GIF frame times are in 10 ms steps, so a 30 fps GIF plays ~10 % fast.

Network size and learning rate (v9): `--arch small` (v1-v8, 1.0M weights, the default) or
`--arch big` (4.2M weights: 2x channels, a third conv layer, 512-wide layers; ~3.7x the update
work). A resume or `--init` keeps the size of its checkpoint; `model.load()` finds the size from
the weights. `--lr-end 2.5e-5 --lr-frames 4e9` lowers the rate linearly from `--lr` over the run's
frames (the frame count is in the checkpoint, so a restart keeps the schedule); without `--lr-end`
the rate stays at `--lr`.

Runs (checkpoints `latest.pt`, `ckpt_*.pt`, `log.csv`, `train.out`) go to `runs/`, which is git-ignored.

## How it works

- **env.py** (no torch): `TankEnv` = one 2-player `World`. One step = 4 frames (`FRAME_SKIP`).
  10 actions = {none, up, down, left, right} x {fire, no fire}. Fire is pressed on the first
  frame of the step only, so the fire edge works as with a human.
- **Observation**: a 17 x 26 x 26 grid (terrain types, hq, me, partner, enemies, armored
  enemies, enemy bullets per direction, player bullets, item, enemy spawn sparkles) and
  172 numbers (my state, partner, the item and its type (13 types), the 6 nearest enemies, the
  4 nearest enemy bullets, link/turret on, my shells cut forest, partner lives; v5: how long I
  am stuck (a direction held with no movement, `Player.stuck`), partner power, gun, ship, shield;
  v6: what the nearest item gives me and the partner, and if it is the partner's item;
  v7: a shot now, in my facing direction, could hit the partner; v8: my last action).
  v3 models had 158 numbers (8 item types), v4 167, v5 172, v6 175, v7 176 (now 186).
- **Memory** (v8, `env.Memory`): the grid has 39 channels: the 17 of now, plus the 11 moving
  ones (tanks, shells, items, spawns) from 2 and 4 steps (8 and 16 frames) ago, so the network
  sees where things go (1 step is less than a grid cell). One `Memory` per world and player;
  `observe(w, idx, mem)` must run once per decision (TankEnv and AIPilot do this). Older
  models (17 channels) get zero weights for the past channels. `model.upgrade()` maps them to the new layout with
  zero weights for the new inputs, so an old model plays as before. `load()`, `--resume`, `--init`
  and the pool all use it. If you change the observation again, extend `upgrade()`.
- **Variety** (v4): half of the episodes use a random map (`src/mapgen.py`: wall lines, a
  typical mix of terrain, often mirrored; spawns and base kept free, every start can reach the base).
  Each player starts at a random power level (60 % level 0, else 1-3; sometimes gun or ship),
  and half of the episodes have 6 item carriers (not 3), so the model sees more items.
- **Partners** (chosen per episode, `MODES`): `self` 30 % (the network drives both tanks:
  self-play), `past` 25 % (a frozen older model drives player 1, temperature 0.5: a smart partner
  that does not adapt to the learner), `bot` 15 % (rule bot: shoots enemies in line, else wanders),
  `random` 5 %, `idle` 25 %. The `past` models live in `<run>/pool/` (seeded from `ckpt_*.pt` every
  500 iterations; the current model is added every `--pool-every` 500 iterations; `--pool` 8 kept).
  The main process computes their moves. `evaluate.py --partner past --partner-model X` tests it. In the non-self modes the network learns only as player 2. The bots never
  shoot toward the hq.
- **Rewards** (`R_*` in env.py): kill +1, partner's kill +0.3, useful item +1.5 (team item rescue/link
  +1 more: the AI helps its human partner), +0.5 per field width it drives closer to the
  nearest item (minus when it drives away), stage clear +3, death -2.5 (v4; was -1: a team of 2 is much stronger), freezing the partner -2, hq lost -3 (and -2 more for the player who shot it),
  own base wall -0.1 per cell. Defence (v2): +0.5 more for a kill within 64 px of the hq,
  and -0.02 for the team per enemy within 64 px of the hq, per step. Hooks on `Bullet` and
  `Enemy.hit` find who shot the hq, the base wall or an enemy near the base.
  Each change of the held direction costs -0.005 (less twitchy play). A shell that ends on
  steel it cannot break or on the map edge costs -0.01 (v4: fewer useless shots; bricks are free).
  v5: power has a value: +0.5 per power level, gun or ship gained and -0.5 per one lost (a hit
  on gun/ship, a death at power 3 costs 1.5 more), and the partner's change counts x0.5 (v6).
  v6, the partner's item: a star, gun or ship the partner needs more (more power steps from it, or
  the same and the partner is weaker; `partners_item`) costs -0.75 per step of difference (at
  least one) when the AI takes it, gives no item reward and no reward for driving to it. Before
  v6 the AI took 44 % of such items. A power item that gives nothing gets no item reward. A grenade gives +0.5
  per enemy it destroys (the game gives no kill credit). Stuck for 8+ frames (a direction held,
  no movement; not brick ahead, which it may be shooting) costs -0.02 per step. The game samples the
  policy with temperature 0.5 (`AIPilot(temp=0.5)`): steadier than 1.0, with the same strength.
- **Own base: a hard rule** (`safe_action`, in training and in the game): fire is dropped when
  the shell could hit our own hq or base wall (`shell_hits_base` follows the shell path and
  its 16 px damage band, with the snap of a 90 degree turn; bricks on the way do not protect,
  since an earlier shell may break them; a tank on the way protects only when close and centered).
  Before: 0.5 base-wall cells per game; after: 0 in 200 games.
  The partner has no such rule (the AI must learn it): v7 gives the input "a shot now could hit
  the partner" (`shell_danger`), -0.3 for each shell fired on such a path (felt at once, also
  when it misses) and -3 for a freeze (was -2).
- **Benchmark** (`benchmark.py MODEL [MODEL ...]`, ~5 min on Linux): 135 fixed games (same seeds
  every time, so models compare fairly): 3 map sets x 3 partners (self, bot, idle) x 5 maps x 3.
  `seen`: stages of the default map pack that training plays; `unseen`: `env.HOLDOUT_STAGES` (5, 12, 19, 26, 33), which
  training skips; `random`: maps from fixed seeds that training never makes. A
  map the AI has never seen is like a future new map: if `unseen`/`random` fall far below `seen`,
  the model learned the maps by heart. Columns: clear and hq-lost %, P2 kills and deaths per game,
  freezes per minute, items per game, % of power items taken that were the partner's, stuck %,
  wasted shells (steel it cannot break, map edge) %, own base-wall cells broken (only
  network-driven tanks count).
- **model.py**: 2 conv layers + MLP for the numbers, policy head (10) + value head.
- **train.py**: up to 10 worker processes x 16 worlds (grids go to the main process packed to
  bits, 6.5x smaller) (fork before torch is imported), PPO with
  GAE. Only steps where the network really drove a live, not frozen tank are used to learn.
- **agent.py**: `AIPilot` for `main.py`: a new decision every 4 frames, sampled from the policy.

## Speed (i5-1235U laptop, no GPU)

The game logic alone runs at ~45,000 frames/s with 64 worlds (~750x real time).
Training is limited by the network update on the CPU: ~5,500 frames/s (~90x real time).
