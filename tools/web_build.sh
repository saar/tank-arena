#!/bin/sh
# Build the browser version of the game with pygbag (test build).
#   nix develop --command sh tools/web_build.sh          # build into build/web/
#   nix develop --command sh tools/web_build.sh --serve  # build and serve on http://localhost:8000
# The AI partner runs with numpy (ml/npnet.py); torch does not run in the browser.
set -eu
cd "$(dirname "$0")/.."
out=build/web-src
rm -rf "$out"
mkdir -p "$out/src"
cp src/*.py "$out/src/"
rm -f "$out/src/test_logic.py"
cp -r art maps "$out/"
mkdir -p "$out/ml" "$out/models"
cp ml/agent.py ml/env.py ml/npnet.py "$out/ml/"
if [ -f models/partner.pt ]; then              # the AI partner as numpy weights (no torch in the browser)
    python3 ml/export_npz.py models/partner.pt "$out/models/partner.npz"
else
    echo "no models/partner.pt: the browser build has no AI partner (see README: download the model)"
fi
cp tools/web/main.py "$out/main.py"
python3 tools/web/svg2png.py "$out/art"
if [ "${1:-}" = "--serve" ]; then
    python3 -m pygbag --template "$PWD/tools/web/tank-arena.tmpl" --title "Tank Arena" "$out"
else
    python3 -m pygbag --build --template "$PWD/tools/web/tank-arena.tmpl" --title "Tank Arena" "$out"
fi
