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

cmd="${1:-web}"
[ $# -gt 0 ] && shift

case "$cmd" in
    web)       # The browser version. The server listens on all addresses inside the container;
               # publish the port with -p 127.0.0.1:8000:8000 so only your computer reaches it.
               port="${TA_WEB_PORT:-8000}"
               [ -f /app/web/index.html ] || { echo "No browser build in this image." >&2; exit 1; }
               echo "Tank Arena in the browser: open http://localhost:${TA_HOST_PORT:-$port}  (Ctrl+C stops)"
               exec python3 -m http.server "$port" --bind 0.0.0.0 --directory /app/web ;;
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

  web                  the game in your browser (default): open http://localhost:8000
                       (run the image with -p 127.0.0.1:8000:8000)
  play [options]       the game in a window (Linux, X11). Options: python3 src/main.py --help
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
