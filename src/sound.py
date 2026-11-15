"""Chiptune sound effects, made in code at start-up (no sound files).

All sounds are our own designs in an 8-bit style: square waves, a triangle wave
and noise. Change the recipes in make_sounds() freely.
"""
import array
import math
import random

import pygame

from config import ENGINE_VOLUME

RATE = 22050


def _env(n, attack=0.0, curve=1.0):
    a = int(n * attack)
    for i in range(n):
        if i < a:
            yield i / a
        else:
            yield (1 - (i - a) / max(1, n - a)) ** curve


def square(f0, f1, dur, vol=0.3, duty=0.5, curve=1.0):
    """Square wave, pitch slides from f0 to f1 (Hz)."""
    n = int(RATE * dur)
    out, ph = [], 0.0
    for i, e in enumerate(_env(n, curve=curve)):
        f = f0 + (f1 - f0) * i / n
        ph = (ph + f / RATE) % 1.0
        out.append((1 if ph < duty else -1) * vol * e)
    return out


def tri(f, dur, vol=0.4):
    n = int(RATE * dur)
    out, ph = [], 0.0
    for e in _env(n, curve=0.5):
        ph = (ph + f / RATE) % 1.0
        out.append((4 * abs(ph - 0.5) - 1) * vol * e)
    return out


def noise(r0, r1, dur, vol=0.35, curve=1.5, seed=1):
    """Sample-and-hold noise; r0/r1 = hold rate (Hz), high = hiss, low = rumble."""
    rnd = random.Random(seed)
    n = int(RATE * dur)
    out, ph, v = [], 0.0, 0.0
    for i, e in enumerate(_env(n, curve=curve)):
        r = r0 + (r1 - r0) * i / n
        ph += r / RATE
        if ph >= 1:
            ph -= 1
            v = rnd.choice((-1, 1))
        out.append(v * vol * e)
    return out


def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def melody(notes, step, vol=0.22, duty=0.5, bass=None):
    """notes: list of MIDI numbers (None = rest), one per step (seconds)."""
    out = []
    for m in notes:
        out += square(note(m), note(m), step, vol, duty, curve=0.6) if m else [0.0] * int(RATE * step)
    if bass:
        b = []
        for m in bass:
            b += tri(note(m), step * 2, 0.35) if m else [0.0] * int(RATE * step * 2)
        out = mix(out, b)
    return out


def mix(*parts):
    n = max(len(p) for p in parts)
    return [sum(p[i] for p in parts if i < len(p)) for i in range(n)]


def thump_loop(beats, period, vol, pitch=140.0, seed=7):
    """Engine loop of soft, short thumps ("putt-putt").
    beats: loudness of each thump (0..1) in one loop; period: seconds per thump.
    Each thump is a low tone plus a little rumble noise that both die out
    before the next thump, so the loop has no clicks."""
    rnd = random.Random(seed)
    n = int(RATE * period)
    out = []
    for amp in beats:
        hold, v = 0.0, 0.0
        for i in range(n):
            t = i / RATE
            env = math.exp(-t / 0.018) * (1 - math.exp(-t / 0.002))     # quick attack, fast decay
            tone = math.sin(2 * math.pi * pitch * t * (1 - 0.6 * t / period))  # pitch drops a little
            hold += 700 / RATE
            if hold >= 1:
                hold -= 1
                v = rnd.uniform(-1, 1)
            out.append(vol * amp * env * (0.75 * tone + 0.25 * v))
    return out


def at(samples, sec):
    """Start samples sec seconds later (for mix())."""
    return [0.0] * int(RATE * sec) + samples


def thud(f0, f1, dur, vol):
    """Low triangle 'knock': pitch falls f0 -> f1, fast exponential decay."""
    n = int(RATE * dur)
    out, ph = [], 0.0
    for i in range(n):
        t = i / RATE
        ph = (ph + (f0 + (f1 - f0) * i / n) / RATE) % 1.0
        out.append((4 * abs(ph - 0.5) - 1) * vol * math.exp(-t / (dur / 3)))
    return out


def metal(freqs, dur, vol, tau, duty=0.125):
    """Metallic ring: thin square waves at detuned (not harmonic) pitches that beat
    against each other, with a fast exponential decay (tau seconds)."""
    n = int(RATE * dur)
    out = [0.0] * n
    for f in freqs:
        ph = 0.0
        for i in range(n):
            ph = (ph + f / RATE) % 1.0
            out[i] += (1 if ph < duty else -1) * vol / len(freqs) * math.exp(-i / RATE / tau)
    return out


def make_sounds():
    S = {}
    S["fire"] = square(900, 260, 0.08, 0.28, 0.5)
    # Brick breaks: a dull knock, a crumbling noise that falls in pitch, and a few late bits of debris.
    S["hit_brick"] = mix(thud(190, 55, 0.10, 0.42),
                         noise(3200, 350, 0.20, 0.30, curve=2.2, seed=5),
                         at(noise(7000, 5000, 0.025, 0.12, seed=11), 0.07),
                         at(noise(6000, 4000, 0.02, 0.09, seed=12), 0.12),
                         at(noise(5000, 3000, 0.02, 0.06, seed=13), 0.17))
    # Steel, no damage (also the field edge): short click + bright metal "clank" that rings out.
    S["hit_steel"] = mix(noise(9000, 9000, 0.008, 0.28, seed=9),
                         metal((1568, 1661, 2489), 0.18, 0.34, 0.045))
    # Steel breaks (3-star bullet): lower, longer metal ring over a heavy crunch.
    S["break_steel"] = mix(metal((1175, 1245, 1865), 0.30, 0.28, 0.08),
                           noise(2600, 250, 0.26, 0.30, curve=1.8, seed=6),
                           thud(150, 45, 0.14, 0.38))
    S["armor"] = square(1100, 1100, 0.03, 0.2, 0.25) + [0.0] * 600 + square(1400, 1400, 0.04, 0.2, 0.25)
    S["explode"] = noise(2200, 150, 0.45, 0.45, 1.2, seed=2)
    S["player_boom"] = mix(noise(1500, 80, 0.7, 0.45, 1.0, seed=3), square(220, 40, 0.6, 0.18, 0.5))
    S["base_boom"] = mix(noise(900, 60, 1.3, 0.5, 0.8, seed=4), square(120, 30, 1.2, 0.2, 0.5))
    S["item_appear"] = sum((square(note(m), note(m), 0.045, 0.2, 0.25) for m in (76, 81, 84, 88) * 2), [])
    S["item_get"] = sum((square(note(m), note(m), 0.05, 0.24, 0.5) for m in (79, 83, 86, 91, 95)), [])
    S["extra_life"] = sum((square(note(m), note(m), d, 0.24, 0.5, 0.7)
                           for m, d in ((84, .08), (88, .08), (91, .08), (96, .3))), [])
    S["tally"] = square(988, 988, 0.03, 0.14, 0.25)
    S["pause"] = square(1047, 1047, 0.06, 0.2) + [0.0] * 1500 + square(1568, 1568, 0.08, 0.2)
    S["stage_start"] = melody(
        [72, 76, 79, 84, 83, 79, 76, 79, 81, 77, 74, 77, 79, None, 84, None], 0.11, duty=0.25,
        bass=[48, 43, 41, 43, 45, 41, 43, 48])
    S["game_over"] = melody([79, 78, 76, 72, 71, None, 67, None, 60, 60, 60, None], 0.16, duty=0.5,
                            bass=[43, 40, 36, 36, 36, None])
    # Engine: soft "putt-putt" thumps. ENGINE_VOLUME in config.py (0 = off).
    S["engine_idle"] = thump_loop([0.5, 0.35], 0.20, 0.30 * ENGINE_VOLUME)
    S["engine_move"] = thump_loop([1.0, 0.7, 0.85, 0.7], 0.085, 0.34 * ENGINE_VOLUME, pitch=165)
    return S


class Sound:
    """Plays sound events. Silent (no error) if there is no audio device."""

    def __init__(self, enabled=True):
        self.ok = False
        self.engine_state = None
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            freq, _, ch = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(12)
            pygame.mixer.set_reserved(1)
            self.engine_ch = pygame.mixer.Channel(0)
            self.snd = {}
            for k, v in make_sounds().items():
                self.snd[k] = self._to_sound(v, freq, ch)
            self.ok = True
        except pygame.error as e:
            print("sound off:", e)

    @staticmethod
    def _to_sound(samples, freq, channels):
        if freq != RATE:                      # simple resample
            k = RATE / freq
            samples = [samples[min(int(i * k), len(samples) - 1)] for i in range(int(len(samples) / k))]
        a = array.array("h", (max(-32767, min(32767, int(s * 32767))) for s in samples
                              for _ in range(channels)))
        return pygame.mixer.Sound(buffer=a.tobytes())

    def play(self, name):
        if self.ok and name in self.snd:
            ch = pygame.mixer.find_channel(True)
            if ch:
                ch.play(self.snd[name])

    def play_events(self, names):
        for n in sorted(names):
            self.play(n)

    def engine(self, state):
        """state: None, "idle" or "move"."""
        if not self.ok or state == self.engine_state:
            return
        self.engine_state = state
        if state is None:
            self.engine_ch.fadeout(80)
        else:
            self.engine_ch.play(self.snd["engine_" + state], loops=-1, fade_ms=60)

    def stop_all(self):
        if self.ok:
            pygame.mixer.stop()
            self.engine_state = None
