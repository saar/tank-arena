# Train your own AI partner

This guide explains, in plain words, how the AI partner learns, how to train your own, and how
to change what it learns. The technical reference is in [ml/README.md](../ml/README.md).

You need the Python packages `numpy` and `torch` (Nix gives you both).

## How the AI learns

The AI is a small neural network. Every 4 frames it looks at the game (the map, the tanks,
the shells, the items) and picks one of 10 actions: stand or drive in one of 4 directions,
each with or without fire.

Training uses **reinforcement learning** (the PPO method). The AI plays thousands of games at
the same time, without a window and much faster than real time. After each action it gets a
**reward** (plus points) or a **punishment** (minus points). For example, it gets +1 for a
kill and −2.5 when it dies. Slowly, the network learns to choose actions that bring more
points over time.

So: **you do not program what the AI does. You set the points, and the AI finds its own way
to get them.** If the AI does something you do not like, change the points.

There is only one hard rule in the code: the AI never fires a shell that could hit its own
base (`safe_action` in `ml/env.py`). Everything else is learned.

During training the AI drives player 2. Player 1 is sometimes the AI itself, sometimes an
older copy of it, a simple bot, a random driver, or a tank that does nothing. So the AI learns
to work with many kinds of partners, also with a human.

## Train a model

```sh
nix develop --command python3 ml/train.py --run ml/runs/my-ai --hours 1
```

- `--run` is the folder for this training run. It gets `latest.pt` (the newest model),
  `ckpt_*.pt` (older copies), `log.csv` and a pool of older models.
- `--hours` is the time budget. Ctrl-C stops early and saves (press it twice to quit at once).
- Continue later with the same folder and `--resume`:
  `ml/train.py --run ml/runs/my-ai --hours 4 --resume`

Each line of output shows the progress, for example:

```
it  120   2.0M frames   5500 fps  eps 410  clear 0.12  hq 0.70  p2 kills 3.1 deaths 0.9 ret -2.4
```

| Field | Meaning |
|---|---|
| `it` | Training steps so far |
| `frames` | Game frames played so far (60 frames = 1 second of game time) |
| `fps` | Training speed |
| `clear` | Part of the games where the team cleared the stage (higher is better) |
| `hq` | Part of the games where the base was lost (lower is better) |
| `p2 kills`, `deaths` | Kills and deaths of the AI per game |
| `ret` | Total points per game (it should go up) |

**How long?** On a laptop CPU, training runs at about 5,000 frames per second (90 times real
time). After about an hour the AI drives, shoots and kills. A strong partner needs billions of
frames: the released model played about 3.3 billion (days on a laptop, or about a night on a
computer with a good GPU; `--device cuda` or `mps` is picked by itself when it is there).

**Start from the released model** to save time. Your run then begins with a strong player
and only learns your changes:

```sh
nix develop --command python3 ml/train.py --run ml/runs/my-ai --init models/partner.pt --hours 2
```

**Train on your own maps:** add `--maps my-pack` (a pack name or folder, see [MAPS.md](MAPS.md)).
Half of the games are always on random maps, so the AI also learns maps it has never seen.

## See what it learned

```sh
# Play with it
nix develop --command python3 src/main.py --ai-partner ml/runs/my-ai/latest.pt

# Watch it drive both tanks (faster: + and -), and record the games
nix develop --command python3 src/main.py --ai-watch --ai-partner ml/runs/my-ai/latest.pt --speed 4 --record

# Numbers: 40 games with a simple bot as partner
nix develop --command python3 ml/evaluate.py ml/runs/my-ai/latest.pt --partner bot

# A fixed test of 135 games (always the same games, so you can compare models fairly)
nix develop --command python3 ml/benchmark.py ml/runs/my-ai/latest.pt models/partner.pt

# Each model plays the same stage from the same start: one animation per model
nix develop --command python3 ml/compare.py ml/runs/my-ai/latest.pt models/partner.pt --stage 7 --format webp --scale 3 --grid
```

`benchmark.py` plays on three sets of maps: stages the training uses, 5 stages training
never uses (5, 12, 19, 26, 33), and random maps. If the AI is much worse on the last two, it
has learned the training maps by heart.

`compare.py` writes its animations to `ml/runs/compare/`. Use `--map-seed N` for a random map,
and `--partner bot` to give every model the same bot partner.

## Change rewards and punishments

All points are at the top of `ml/env.py` (names that start with `R_`). The most important ones:

| Name | Default | When |
|---|---|---|
| `R_KILL` | +1.0 | The AI destroys an enemy |
| `R_PARTNER_KILL` | +0.3 | The partner destroys an enemy (team spirit) |
| `R_DEATH` | −2.5 | The AI loses a life |
| `R_CLEAR` | +3.0 | The stage is cleared |
| `R_HQ_LOST` | −3.0 | The base is destroyed |
| `R_ITEM` | +1.5 | The AI takes a useful item |
| `R_COOP_ITEM` | +1.0 | Extra for a team item (rescue, link) |
| `R_PARTNER_ITEM` | −0.75 | The AI takes a power item that the partner needs more |
| `R_FREEZE_PARTNER` | −3.0 | The AI's shell freezes the partner |
| `R_RISKY_SHOT` | −0.3 | The AI fires on a path that could hit the partner |
| `R_KILL_NEAR_BASE` | +0.5 | Extra for a kill close to the base |
| `R_BASE_DANGER` | −0.02 | Each step, for each enemy close to the base |
| `R_WASTED_SHOT` | −0.01 | A shell ends on steel it cannot break, or on the map edge |
| `R_STUCK` | −0.02 | Each step the AI drives against a wall and does not move |
| `R_TURN` | −0.005 | Each change of direction (less nervous driving) |
| `R_POWER` | +0.5 | Each power level gained (lost: the same minus) |

The points are added up in `TankEnv.step()` in `ml/env.py`. One step = 4 game frames.

**Good habits:**

- Change one or two values at a time, then train and look (`--ai-watch`, `benchmark.py`).
- A reward that comes often (each step) must be small. −0.02 per step is already −15 per
  minute of game time. Compare that with +1 for a kill.
- Points shape behavior in ways you do not expect. If you pay much for items, the AI may
  hunt items and forget the base. Watch the games, not only the numbers.
- After a change of points, training with `--resume` or `--init` is fine: the network keeps
  what it knows and adapts.

### Example 1: a defender that stays near the base

The AI hunts enemies all over the map, but you want it to guard the base.

```python
R_KILL_NEAR_BASE = 1.5              # was 0.5: kills close to the base are worth much more
R_BASE_DANGER = -0.05               # was -0.02: enemies close to the base hurt more
```

### Example 2: a careful partner that never hits you

```python
R_FREEZE_PARTNER = -6.0             # was -3.0
R_RISKY_SHOT = -0.8                 # was -0.3: even a shot that only could hit you costs a lot
```

Expect fewer shots in general: the AI may also become slower to attack.

### Example 3: stop wasting shells

```python
R_WASTED_SHOT = -0.05               # was -0.01
```

### Example 4: a new reward — stay close to the partner

Add the value next to the others at the top of `ml/env.py`:

```python
R_NEAR_PARTNER = 0.003              # per step while within 3 blocks of the partner
```

Then add these lines in `TankEnv.step()`, inside the loop `for i, p in enumerate(P):`
(there, `p` is this tank, `q` is the partner, and `r[i]` is the reward of this step):

```python
            if p.alive and q.alive:
                (ax, ay), (bx, by) = p.center(), q.center()
                if max(abs(ax - bx), abs(ay - by)) < 48:      # 48 px = 3 blocks
                    r[i] += R_NEAR_PARTNER
```

0.003 per step is about +2.7 per minute: enough to matter, much less than a kill.

### Example 5: a new punishment — do not stand still

```python
R_IDLE = -0.01                      # per step without a move or a shot
```

In `TankEnv.step()`, the list `acts` holds the chosen action of each player, and
`ACTIONS[a]` is `(direction or None, fire)`:

```python
            d, fire = ACTIONS[acts[i]]
            if p.alive and d is None and not fire:
                r[i] += R_IDLE
```

### Test a change quickly

```sh
nix develop --command python3 src/test_logic.py                       # the game still works
nix develop --command python3 ml/train.py --run ml/runs/test --hours 0.05 --workers 2   # it trains
```

Then a real run, for example 2 hours from the released model with `--init models/partner.pt`,
and compare with `benchmark.py` and `compare.py`.

## What the AI sees (and how to change it)

The AI gets a picture of the map (a 26×26 grid with layers for terrain, tanks, shells,
items) and a list of numbers (its own state, the partner, the nearest enemies, shells and
items). It also sees the moving things from 2 and 4 steps ago, so it knows where they go.
This is built in `observe()` in `ml/env.py`.

If you add new inputs, old models no longer fit the network. Extend `model.upgrade()` in
`ml/model.py`, so old models load with zero weights for the new inputs (see
[ml/README.md](../ml/README.md)). Changing only rewards needs nothing like this.

## Share your model

Copy `ml/runs/my-ai/latest.pt` anywhere. Others play with it with
`src/main.py --ai-partner path/to/latest.pt`. Models are loaded in a safe mode (weights only),
so a model file cannot run code.
