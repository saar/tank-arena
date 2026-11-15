# Run Tank Arena in a container (Docker or Podman)

With a container, you do not install Python or any packages on your computer. The image has
the game, the default map pack, the trained AI partner and the training tools.

This guide is for **Linux**. On macOS and Windows, the container cannot easily open a window:
use the normal install from the [README](../README.md#start-the-game) to play there. Training
and benchmarks without a window work on all systems.

- [Quick start](#quick-start)
- [What you can do](#what-you-can-do)
- [Where your data goes](#where-your-data-goes)
- [Your own maps and models](#your-own-maps-and-models)
- [Settings](#settings)
- [Without the script](#without-the-script)
- [Problems](#problems)

## Quick start

You need Podman or Docker. Then, in the repository folder:

```sh
./container.sh build      # one time; makes the image "tank-arena" (about 2 GB, a few minutes)
./container.sh play       # play in a window, with sound
```

Keys and game options are the same as in the [README](../README.md#how-to-play). Close the
window, press Esc on the title screen, or press Ctrl+C in the terminal to stop.

If you do not need the AI partner, make a smaller image (about 600 MB):

```sh
./container.sh build --no-ai
```

After you change the code, run `./container.sh build` again. The code is copied into the image.

## What you can do

`./container.sh COMMAND [options]`. The options go to the program, as in the README.

| Command | What it does | Example |
|---|---|---|
| `play` | The game (default command) | `./container.sh play --players 2 --stage 5` |
| `play --ai-partner` | Play with the AI partner | `./container.sh play --ai-partner` |
| `play --ai-watch` | Watch the AI play | `./container.sh play --ai-watch --speed 4 --record` |
| `replay FILE` | Play a recording again, or make an animation | `./container.sh replay /data/recordings/FILE.rec.json.gz` |
| `train` | Train your own AI (no window) | `./container.sh train --run ml/runs/my-ai --hours 1` |
| `evaluate MODEL` | Measure a model | `./container.sh evaluate ml/runs/my-ai/latest.pt --partner bot` |
| `benchmark MODEL...` | 135 fixed games per model | `./container.sh benchmark /app/models/partner.pt` |
| `compare MODEL...` | Same stage for each model, as animations | `./container.sh compare ml/runs/my-ai --stage 1` |
| `make-maps` | Make map packs | `./container.sh make-maps --out /data/new-pack` |
| `test` | Logic tests and a short run without a window | `./container.sh test` |
| `shell` | A shell inside the container | `./container.sh shell` |
| `help` | This list | `./container.sh help` |

Training uses the CPU only. A training keeps running until its time is over; to stop it
earlier, press Ctrl+C. To continue it later: `./container.sh train --run ml/runs/my-ai --hours 1 --resume`.
More about training: [TRAINING.md](TRAINING.md).

## Where your data goes

The container forgets everything when it stops, except one folder: **the data folder**.
On your computer it is `~/.local/share/tank-arena/`. This is the same folder that the game uses
without a container, so both see the same installed map packs and settings.

| On your computer (`~/.local/share/tank-arena/`) | In the container | What is in it |
|---|---|---|
| `maps/` | `/data/maps/` | Installed map packs |
| `settings.json` | `/data/settings.json` | The map pack you chose last |
| `models/` | `/data/models/` | Your own AI models |
| `recordings/` | `/data/recordings/` | Recorded games (`--record`) |
| `runs/` | `/data/runs/` | Training runs (`ml/runs/NAME` in the container) |

Inside the container, `ml/runs/` and `recordings/` point to the data folder. So the commands of
the README and TRAINING.md work without a change, and the results stay on your computer.

The files belong to your user, not to root.

**Your current folder** is also visible in the container, read-only, at `/work`. Use it to
give files to the game (see below).

## Your own maps and models

**Install a map pack** (copies it into the data folder):

```sh
cd folder/with/my-pack
/path/to/container.sh play --install-maps /work/my-pack --name mine
/path/to/container.sh play --list-maps
```

You can also copy a pack folder directly into `~/.local/share/tank-arena/maps/`.
To use a pack folder without installing it: `./container.sh play --maps /work/my-pack`.

**Use your own AI model:** put the `.pt` file into `~/.local/share/tank-arena/models/`, then:

```sh
./container.sh play --ai-partner /data/models/my-model.pt
```

The built-in model is `/app/models/partner.pt` (the file from the GitHub release page). Without
`--ai-partner MODEL`, the game uses this one.

A model that you trained in the container is in `~/.local/share/tank-arena/runs/NAME/latest.pt`
(in the container: `ml/runs/NAME/latest.pt`).

## Settings

Set these environment variables before the command, for example
`TA_DATA=~/tank-data ./container.sh play`.

| Variable | What it does | Default |
|---|---|---|
| `TA_DATA` | The data folder on your computer | `~/.local/share/tank-arena` |
| `TA_MAPS` | Another folder for installed map packs | `$TA_DATA/maps` |
| `TA_MODELS` | Another folder for your models | `$TA_DATA/models` |
| `TA_RECORDINGS` | Another folder for recordings | `$TA_DATA/recordings` |
| `TA_RUNS` | Another folder for training runs | `$TA_DATA/runs` |
| `TA_GAMEPAD=1` | Use gamepads (see [Problems](#problems)) | off |
| `TA_ENGINE` | `podman` or `docker` | `podman` if installed, else `docker` |
| `TA_IMAGE` | The image name | `tank-arena` |
| `TA_WINDOW` | `1`: always open a window; `0`: never | window for `play`, `replay`, `shell` |

Example: keep the training runs on a big disk:

```sh
TA_RUNS=/mnt/big/tank-runs ./container.sh train --run ml/runs/long --hours 8
```

**Build options** (for `./container.sh build`, or `--build-arg` of `docker build`):

| Option | What it does |
|---|---|
| `--no-ai` | No PyTorch and no AI model: a small image, the game only |
| `--build-arg MODEL_URL=URL` | Put another model file into the image (empty: no model) |

## Without the script

The script only adds the right options to `podman run` or `docker run`. To see what it does,
read `container.sh`; each part has a comment. The minimum:

```sh
docker build -t tank-arena .

# Training or tests (no window)
docker run --rm --init --user "$(id -u):$(id -g)" \
    -v ~/.local/share/tank-arena:/data \
    tank-arena train --run ml/runs/my-ai --hours 1

# Play (X11 window and PulseAudio/PipeWire sound)
docker run --rm -it --init --user "$(id -u):$(id -g)" \
    -v ~/.local/share/tank-arena:/data \
    -e DISPLAY -e SDL_VIDEODRIVER=x11 -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -e XAUTHORITY=/tmp/.Xauthority -v "${XAUTHORITY:-$HOME/.Xauthority}:/tmp/.Xauthority:ro" \
    -e PULSE_SERVER=unix:/run/pulse/native -v "$XDG_RUNTIME_DIR/pulse/native:/run/pulse/native" \
    tank-arena play
```

With Podman, write `podman` for `docker` and `--userns=keep-id` for `--user ...`.

The first word after the image name is the command (see [What you can do](#what-you-can-do)).
Any other first word runs as a program, for example `tank-arena python3 ml/benchmark.py --help`.

## Problems

| Problem | What to do |
|---|---|
| `No DISPLAY: cannot open a window` | You are not in a desktop session (for example over SSH). Use commands without a window (`train`, `test`, `benchmark`). |
| The window does not open, `Authorization required` | Your desktop does not let the container use the display. Run `xhost +SI:localuser:$(whoami)` one time, then try again. |
| No sound | The script needs the PulseAudio or PipeWire socket (`$XDG_RUNTIME_DIR/pulse/native`). It tells you when it does not find it. Play with `--mute` to hide the message. |
| The gamepad does not work | Start with `TA_GAMEPAD=1`. The gamepad must be connected **before** the start. This gives the container read access to all input devices of your computer (also the keyboard). |
| `permission denied ... docker.sock` | Your user may not use Docker. Use Podman (no root needed), or ask the admin. Note: the `docker` group gives root access to the computer. |
| Messages `MESA: error: Failed to query drm device` | Normal. The container draws without the GPU; the game is 2D and does not need it. |
| `NO AI MODEL` on the title screen | The image was built with `--no-ai`, or the model file is missing. Build again without `--no-ai`. |
