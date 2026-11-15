# Art kit

One SVG file for each graphic in the game. `src/art.py` loads the "art" layer of each file
and renders it at 1 SVG unit = 1 pixel.

## Edit a sprite

- **In code:** each sprite is a function or a pixel grid in `tools/draw_art.py`. Change it, then
  run `nix develop --command python3 tools/draw_art.py [id-prefix]`. The script writes into
  `<g id="generated">` in the art layer. It skips a file where you drew other things by hand
  (use `--force` to replace). Preview: `tools/draw_art.py --preview out.png`.
- **By hand:** open the SVG in Inkscape. Draw only in the layer **art - draw here**. The
  **grid** layer (pixel grid, red border) is only a help; the game ignores it. One grid square
  is one game pixel; draw squares or paths, no blur. Leave empty areas transparent.

## Rules for each group

| Group | Size | Rules |
|---|---|---|
| `tiles/` | 8×8 | The tile repeats across the map: the edges must join. `forest` is drawn above tanks: leave see-through gaps. `water_1`/`water_2` alternate every 16 frames. |
| `tanks/` | 16×16 | **Facing up only**; the game rotates it. 2 frames = tread animation. **Use only the 3 key colors** `#ffffff`, `#a0a0a0`, `#505050`: the game replaces them with team colors. |
| `items/` | 16×16 | Any colors. Easy to tell apart at small size. |
| `base/` | 16×16 | The base the players defend, and its destroyed look. |
| `effects/` | 16×16, big explosion 32×32 | Frames play in number order. `bullet` faces up. |
| `ui/` | various | `font` is a 10×4 sheet of 8×8 cells, in the order shown in the file description. |
