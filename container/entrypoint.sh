#!/bin/sh
# Entry point of the Tank Arena container. The first word picks the program;
# the other words go to that program. See docs/CONTAINER.md.
set -e
cd /app

# Make the data folders (the /data mount can be empty on the first start).
mkdir -p /data/maps /data/models /data/recordings /data/runs 2>/dev/null || true

# No display: run without a window and without sound (training, tests, benchmarks).
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-dummy}"
    export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"
fi

cmd="${1:-play}"
[ $# -gt 0 ] && shift

case "$cmd" in
    play)      exec python3 src/main.py "$@" ;;
    replay)    exec python3 tools/replay.py "$@" ;;
    train)     exec python3 ml/train.py "$@" ;;
    evaluate)  exec python3 ml/evaluate.py "$@" ;;
    benchmark) exec python3 ml/benchmark.py "$@" ;;
    compare)   exec python3 ml/compare.py "$@" ;;
    make-maps) exec python3 tools/make_maps.py "$@" ;;
    test)      python3 src/test_logic.py
               exec python3 src/main.py --autoplay 600 --seed 3 --mute ;;
    shell)     exec /bin/bash "$@" ;;
    help|-h|--help)
        cat <<'EOF'
Tank Arena container. Usage: <command> [options]

  play [options]       the game (default). Options: python3 src/main.py --help
  replay FILE [...]    play a recording again, or make a WebP/GIF
  train [options]      train an AI   (ml/train.py --run ml/runs/NAME --hours H)
  evaluate MODEL       measure a model
  benchmark MODEL...   fixed 135 games per model
  compare MODEL...     the same stage for each model, as animations
  make-maps [options]  make map packs
  test                 logic tests and a short run without a window
  shell                a shell inside the container

Data folder: /data (maps/, models/, recordings/, runs/, settings.json).
EOF
        ;;
    *)         exec "$cmd" "$@" ;;
esac
