# /// script
# dependencies = ["numpy"]
# ///
"""Browser entry for pygbag (tools/web_build.sh copies it to the top of the build folder)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import pygame  # noqa: E402

import main as game  # noqa: E402  (src/main.py)


async def start():
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    app = game.App(None, 3, 0, None, game.ART_DIR, True)
    await app.run_async()


asyncio.run(start())
