# Tank Arena in a container (Docker or Podman).
# Human guide: docs/CONTAINER.md. Easy start: docker run --rm -p 127.0.0.1:8000:8000 IMAGE,
# then open http://localhost:8000 (the browser version; `play` opens a window on Linux).
#
# Build options (--build-arg NAME=VALUE):
#   WITH_AI=1      1: add PyTorch (AI partner, training). 0: game only, much smaller image.
#   MODEL_URL=...  the AI model put into the image. Empty: no model in the image.
#   GIT_COMMIT=... the code version, saved in recordings (container.sh and the CI set it).

# Full name (with the registry), so Podman does not ask which registry to use.
FROM docker.io/library/python:3.12-slim-trixie

ARG WITH_AI=1
ARG MODEL_URL=https://github.com/saar/tank-arena/releases/download/v0.1.0/partner.pt

# Libraries that SDL (inside pygame-ce) opens at run time: X11 window, sound, gamepads.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libx11-6 libxext6 libxrender1 libxrandr2 libxcursor1 libxi6 libxss1 libxfixes3 \
      libxkbcommon0 libgl1 libegl1 libpulse0 libasound2t64 libudev1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pygame-ce==2.5.* pillow==12.* \
 && if [ "$WITH_AI" = "1" ]; then \
      pip install --no-cache-dir numpy==2.* \
   && pip install --no-cache-dir torch==2.* --index-url https://download.pytorch.org/whl/cpu ; \
    fi

WORKDIR /app
COPY . /app

# The AI model (the same file as on the GitHub release page).
RUN mkdir -p /app/models \
 && if [ -n "$MODEL_URL" ]; then \
      python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/app/models/partner.pt')" "$MODEL_URL" ; \
    fi

# The browser version (pygbag), served by the `web` command (the default). pygbag is only
# needed for the build, so it is removed in the same step. The browser loads its Python
# runtime from the pygbag CDN; the AI partner is in it only when the image has the model.
ARG PYGBAG_VERSION=0.9.3
RUN pip install --no-cache-dir pygbag==${PYGBAG_VERSION} \
 && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy sh tools/web_build.sh \
 && mv build/web-src/build/web /app/web \
 && rm -rf build /root/.cache \
 && pip uninstall -y pygbag

# All data that must stay after the container stops goes to /data (mount a host folder there):
#   /data/maps, /data/settings.json   installed map packs, chosen pack
#   /data/models                      your own models (use: --ai-partner /data/models/NAME.pt)
#   /data/recordings                  recorded games (--record)
#   /data/runs                        training runs (ml/train.py --run ml/runs/NAME)
RUN rm -rf /app/recordings /app/ml/runs \
 && ln -s /data/recordings /app/recordings \
 && ln -s /data/runs /app/ml/runs \
 && mkdir -p /data && chmod 1777 /data \
 && chmod 755 /app/container/entrypoint.sh

# LIBGL_ALWAYS_SOFTWARE: the game is 2D. Without it, Mesa looks for the GPU (not in the
# container) and the window does not open.
ARG GIT_COMMIT=
ENV TANK_ARENA_HOME=/data \
    TANK_ARENA_CODE=${GIT_COMMIT} \
    LIBGL_ALWAYS_SOFTWARE=1 \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/app/container/entrypoint.sh"]
CMD ["web"]
