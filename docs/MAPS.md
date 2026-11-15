# Map packs

A map pack is a folder with one text file per stage: `01.txt`, `02.txt`, `03.txt` ...
A pack can have any number of stages. After the last stage, the game starts again at stage 1
(the enemies stay as strong as in the last stage).

## The stage file

Each file has 13 lines of 13 characters (the map, one character = one block), and one line
that lists the 20 enemies. Lines that start with `# ` are comments.

```
# stage 1: my first map
.............
..%%.....%%..
..%%.###.%%..
.....#@#.....
.##.......##.
.#..~~.~~..#.
.#..~~.~~..#.
.....#.#.....
.@.#.....#.@.
...#.---.#...
.###.....###.
.............
.............
enemies: bbbbbbbbbbbbffffbbpp
```

### Map characters

| Char | Block | Char | Block |
|---|---|---|---|
| `.` | empty | `#` | brick |
| `@` | steel | `~` | water |
| `%` | forest | `-` | ice |
| `r` `l` `u` `d` | half brick: only the right, left, upper or lower half | `R` `L` `U` `D` | half steel (the same halves) |

One block is 16×16 pixels (as big as a tank). Brick and steel break in quarter blocks.

### Enemy letters

The `enemies:` line has exactly 20 letters, in the order the enemies appear. Spaces are allowed.

| Letter | Enemy |
|---|---|
| `b` | basic: slow, 1 hit |
| `f` | fast: fast tank, 1 hit |
| `p` | power: fast shells, 1 hit |
| `a` | armor: 4 hits |

Example of a hard wave: `enemies: aaaa pppp ffff bbbb aaaa`

### Rules for a good map

- Keep these blocks free (the game clears them anyway): the top-left corner, the top
  center and the top-right corner (enemies appear there), and the bottom row around the
  middle (the players and the base are there).
- The game draws the base and the brick wall around it by itself (bottom center).
- Every enemy must have a way to the base (shells break brick, so brick counts as a way).
  Steel and water are walls.
- A mirror-symmetric map often feels fair and looks good.

## Make a pack

1. Make a folder, for example `my-pack/`.
2. Copy a file from `maps/default/` into it as `01.txt` and change it, or write a new one.
3. Try it without installing:
   ```sh
   nix develop --command python3 src/main.py --maps my-pack
   ```
   If a file has a mistake, the game tells you the file and the line.
4. Install it for good:
   ```sh
   nix develop --command python3 src/main.py --install-maps my-pack --name my-pack
   ```

## Installed packs

`--install-maps` checks every file and copies the pack into your user data folder. The game
then finds it every time, also after you update or move the game.

| System | Folder |
|---|---|
| Linux | `~/.local/share/tank-arena/maps/` |
| macOS | `~/Library/Application Support/tank-arena/maps/` |
| Windows | `%APPDATA%\tank-arena\maps\` |

On the title screen, press **M** (or the gamepad Back button) to switch packs. The game
saves your choice in `settings.json` in the same folder. Other commands:

```sh
nix develop --command python3 src/main.py --list-maps            # list all packs
nix develop --command python3 src/main.py --remove-maps my-pack  # remove one
nix develop --command python3 src/main.py --maps my-pack         # start with a pack (name or folder)
```

To install a pack again after a change, run `--install-maps` again: it replaces the old copy.

## Generate maps

`tools/make_maps.py` builds maps from small patterns (rows of pillars, walls, rooms, forest,
rivers, ice, steel). It tries many maps for each stage and keeps the best one. Later stages
get more steel and water and harder enemy waves.

```sh
# A new pack of 35 stages, and a picture of all of them
nix develop --command python3 tools/make_maps.py --out my-pack --seed 7 --sheet my-pack.png --scale 2

# Make only stage 4 again, with another seed
nix develop --command python3 tools/make_maps.py --out my-pack --only 4 --seed 99

# Only the picture, for a pack you made by hand
nix develop --command python3 tools/make_maps.py --out my-pack --render-only --sheet my-pack.png
```

The picture shows each stage with its number and the enemy count (basic, fast, power, armor).

## Train the AI on your maps

The AI partner plays on any map, also on maps it has never seen. To make it better on your
maps, train it on them: `ml/train.py --maps my-pack` (see [TRAINING.md](TRAINING.md)).
