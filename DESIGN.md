# Design notes

## Rules

All numbers are in `src/config.py`. In short: 20 enemies per stage, 4 on screen (6 with
2 players), item carriers 4th / 11th / 18th, tank speeds 0.75 px/frame (player), 1.0 (fast
enemy), 0.5 (other enemies), a 2-second wait after the last kill, an extra life at 20 000 points.

## Our ideas

1. **Gun and ship items.** Each absorbs one hit, so the player gets a buffer without extra
   lives. The gun also gives max power. The ship lets the tank drive on water.
2. **Forest cutting.** Each star adds `0x20` and the gun adds `0x60` to a bullet-power
   counter. At `0xA0` or more, shells cut forest and fly on, so one shot clears a path.
3. **Items do not land on steel or water** (`ITEM_AVOID_BLOCKED`), so every item can be reached.
4. **The player tank looks different at each power level** (4 designs).
5. **The base is a radio tower.**
6. **Team and support items** (rules and times in `config.py`). Rescue and link drop only
   with 2 players.
   - **Rescue** (flag): a partner with no lives comes back with 1 life. If not, the player
     with fewer lives gets +1.
   - **Link** (chain): both players get a shield for 10 s, and partner shells pass through.
   - **Turret** (gun post): a fixed gun above the base for 20 s. It shoots enemies in its
     row or column. Tanks and shells pass over it.
   - **Repair** (+ on bricks): rebuilds the broken bricks of the base wall.
   - **Mystery** (?): 2 new random items appear on the field.
7. **AI partner** (`ml/`): a network trained with PPO drives player 2. One hard rule: it never
   fires at its own base (`env.safe_action`). All other behavior is learned from rewards.
8. **Map packs** (`src/maps.py`): stages are plain text files, so players can make their own.

## Ideas for later

- A new setting and theme (robots, boats, sci-fi).
- New terrain: mud (slow), mines, teleport pads, one-way gates, walls that grow back.
- Power-ups that also help the enemy (an enemy that drives over an item takes it).
- Random enemy armor, so you must think about your targets.
- A map editor in the game.
- A modern engine (Godot, LÖVE, Phaser) and online 2-player.
