#!/usr/bin/env bash
# Build and run Tank Arena in a container (Podman or Docker) on Linux.
# Guide: docs/CONTAINER.md
#
#   ./container.sh pull [TAG]         get the ready image from ghcr.io (TAG: latest, 0.2.0,
#                                     latest-noai, ...)
#   ./container.sh build              make the image yourself (with the AI partner)
#   ./container.sh build --no-ai      make a small image without the AI
#   ./container.sh play [options]     play in a window, with sound
#   ./container.sh train --run ml/runs/my-ai --hours 1
#   ./container.sh help               all commands
#
# Settings (environment variables, all optional):
#   TA_ENGINE      podman or docker (default: podman; from `nix develop` if Nix is installed,
#                  else the installed podman, else docker)
#   TA_IMAGE       image name (default: tank-arena)
#   TA_DATA        host folder for all saved data (default: ~/.local/share/tank-arena,
#                  the same folder that the game uses without a container)
#   TA_MAPS        host folder for installed map packs   (default: $TA_DATA/maps)
#   TA_MODELS      host folder with your own AI models   (default: $TA_DATA/models)
#   TA_RECORDINGS  host folder for recorded games        (default: $TA_DATA/recordings)
#   TA_RUNS        host folder for training runs         (default: $TA_DATA/runs)
#   TA_GAMEPAD=1   give the container access to gamepads (/dev/input)
#   TA_WINDOW=0|1  force no window / a window (default: a window for play, replay, shell)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
# With Nix, run inside `nix develop`: it gives Podman (see flake.nix). Nothing to install.
if [[ -z "${TA_ENGINE:-}" && -z "${IN_NIX_SHELL:-}" ]] && command -v nix >/dev/null 2>&1; then
    exec nix develop "$here" --command "$here/container.sh" "$@"
fi
if [[ -n "${TA_ENGINE:-}" ]]; then engine="$TA_ENGINE"
elif command -v podman >/dev/null 2>&1; then engine=podman
else engine=docker; fi
image="${TA_IMAGE:-tank-arena}"
data="${TA_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/tank-arena}"

cmd="${1:-play}"
[[ $# -gt 0 ]] && shift

# ---- build -----------------------------------------------------------------
if [[ "$cmd" == build ]]; then
    args=(--build-arg WITH_AI=1)
    if [[ "${1:-}" == --no-ai ]]; then
        shift
        args=(--build-arg WITH_AI=0 --build-arg MODEL_URL=)
    fi
    commit="$(git -C "$here" rev-parse --short HEAD 2>/dev/null || true)"
    [[ -n "$commit" ]] && args+=(--build-arg "GIT_COMMIT=$commit")
    echo "Building image '$image' with $engine ..."
    exec "$engine" build -t "$image" "${args[@]}" "$@" "$here"
fi

# ---- pull: get the ready image from the GitHub package registry ------------
if [[ "$cmd" == pull ]]; then
    tag="${1:-latest}"
    remote="ghcr.io/saar/tank-arena:$tag"
    echo "Getting $remote with $engine ..."
    "$engine" pull "$remote"
    exec "$engine" tag "$remote" "$image"
fi

# ---- run -------------------------------------------------------------------
mkdir -p "$data"
# --init: a small init process, so that Ctrl+C and stop signals end the game.
opts=(run --rm --init -e TANK_ARENA_HOME=/data -v "$data:/data")

# Optional separate folders, each mounted over its part of /data.
for pair in MAPS:maps MODELS:models RECORDINGS:recordings RUNS:runs; do
    var="TA_${pair%%:*}"; sub="${pair#*:}"
    dir="${!var:-}"
    if [[ -n "$dir" ]]; then
        mkdir -p "$dir"
        opts+=(-v "$(cd "$dir" && pwd):/data/$sub")
    fi
done

# The current folder, read-only, at /work: to reach your files (for example
# --install-maps /work/my-pack, or replay /work/game.rec.json.gz).
opts+=(-v "$PWD:/work:ro")

# Host time zone, so recording names use your local time.
[[ -f /etc/localtime ]] && opts+=(-v /etc/localtime:/etc/localtime:ro)

# Files in the mounted folders belong to you, not to root.
if [[ "$engine" == podman ]]; then
    opts+=(--userns=keep-id)
else
    opts+=(--user "$(id -u):$(id -g)")
fi

# Keyboard and Ctrl+C work when the command runs in a terminal.
[[ -t 0 && -t 1 ]] && opts+=(-it)

# Window and sound.
case "$cmd" in play|replay|shell) window=1 ;; *) window=0 ;; esac
window="${TA_WINDOW:-$window}"
if [[ "$window" == 1 ]]; then
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "No DISPLAY: cannot open a window. Use TA_WINDOW=0 to run without a window." >&2
        exit 1
    fi
    # X11 works on X11 desktops and on Wayland desktops (through XWayland).
    opts+=(-e "DISPLAY=$DISPLAY" -e SDL_VIDEODRIVER=x11 -v /tmp/.X11-unix:/tmp/.X11-unix:ro)
    xauth="${XAUTHORITY:-$HOME/.Xauthority}"
    if [[ -f "$xauth" ]]; then
        opts+=(-e XAUTHORITY=/tmp/.Xauthority -v "$xauth:/tmp/.Xauthority:ro")
    fi
    # Sound through PulseAudio or PipeWire (pipewire-pulse).
    pulse="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/pulse/native"
    if [[ -S "$pulse" ]]; then
        opts+=(-e PULSE_SERVER=unix:/run/pulse/native -e SDL_AUDIODRIVER=pulseaudio
               -v "$pulse:/run/pulse/native")
    else
        echo "No PulseAudio/PipeWire socket found: no sound." >&2
        opts+=(-e SDL_AUDIODRIVER=dummy)
    fi
fi

# Gamepads (optional). The container gets the 'input' group to read /dev/input.
if [[ "${TA_GAMEPAD:-0}" == 1 && -d /dev/input ]]; then
    opts+=(--device /dev/input)
    gid="$(getent group input | cut -d: -f3 || true)"
    [[ -n "$gid" ]] && opts+=(--group-add "$gid")
fi

exec "$engine" "${opts[@]}" "$image" "$cmd" "$@"
