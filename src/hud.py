"""Screen layout: the field position, the info panel on the left, the title logo and the
stage banner."""
import pygame

import config as C

BG = (22, 26, 38)          # screen background around the field
FRAME = (70, 84, 120)      # 1 px line around the field
DIM = (120, 132, 160)
P_COL = [(248, 196, 24), (72, 208, 200)]      # player 1, player 2 (tank colors)

FIELD_POS = (44, 8)        # field on the 256x224 screen (the panel is on the left)


def field_pos():
    return FIELD_POS


def _text(A, surf, s, x, y, color):
    A.text_color(surf, s, x, y, color)


def _gauge(surf, x, y, w, h, left, total, color, vertical=False):
    """Enemies left: a segmented bar."""
    for i in range(total):
        on = i < left
        col = color if on else (50, 56, 72)
        if vertical:
            seg = h // total
            surf.fill(col, (x, y + h - (i + 1) * seg + 1, w, seg - 1))
        else:
            seg = w // total
            surf.fill(col, (x + i * seg, y, seg - 1, h))


def _frame(surf, fx, fy):
    pygame.draw.rect(surf, FRAME, (fx - 2, fy - 2, C.FIELD + 4, C.FIELD + 4), 1)


def draw_panel(w, surf):
    """Left panel: stage, enemies left (vertical bar), lives and score of each player."""
    A = w.assets
    fx, fy = FIELD_POS
    _frame(surf, fx, fy)
    _text(A, surf, "ST", 4, 8, DIM)
    _text(A, surf, "%02d" % w.stage, 22, 8, (230, 230, 230))
    surf.blit(A.reserve_icon, (6, 24))
    _gauge(surf, 18, 24, 8, 100, w.reserve, C.ENEMIES_PER_STAGE, (226, 80, 60), vertical=True)
    for p in w.players:
        y = 136 + p.idx * 40
        surf.fill(P_COL[p.idx], (4, y, 34, 2))
        surf.blit(A.lives_icon, (4, y + 6))
        _text(A, surf, str(max(p.lives - 1, 0)), 14, y + 6, P_COL[p.idx])
        _small(surf, p.score, 39, y + 18, (230, 230, 230))


def _small(surf, n, right, y, color):
    from game import draw_small_number
    draw_small_number(surf, n, right, y, color)


# ---- title and banner -----------------------------------------------------------
def big_text(A, surf, s, x, y, scale, face, shade):
    """Big letters from our font: each font pixel becomes a scale x scale block with a shadow."""
    for i, ch in enumerate(s.upper()):
        m = A.glyph_mask.get(ch)
        if not m:
            continue
        for py in range(8):
            for px in range(8):
                if m[py][px]:
                    X, Y = x + (i * 8 + px) * scale, y + py * scale
                    surf.fill(shade, (X + 1, Y + 1, scale, scale))
        for py in range(8):
            for px in range(8):
                if m[py][px]:
                    X, Y = x + (i * 8 + px) * scale, y + py * scale
                    surf.fill(face[min(py * len(face) // 8, len(face) - 1)], (X, Y, scale, scale))


def draw_title_logo(A, surf, title):
    """The game name in big yellow letters, one word per line."""
    face = [(255, 236, 120), (248, 196, 24), (220, 150, 10), (184, 110, 0)]
    for n, word in enumerate(title.split()[:2]):
        big_text(A, surf, word, 128 - len(word) * 16, 18 + n * 36, 4, face, (90, 40, 0))


def draw_banner(A, surf, text):
    surf.fill(BG)
    pygame.draw.rect(surf, FRAME, (40, 96, 176, 24), 1)
    A.text_color(surf, text, 128 - len(text) * 4, 104, (230, 230, 230))
