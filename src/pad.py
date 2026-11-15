"""Gamepads.

Known pads (SDL game controller database: 8BitDo, Xbox, PlayStation, Switch Pro, ...)
use the standard layout: D-pad or left stick move, A/B/X/Y or right trigger fire,
Start, Back (Select). Unknown pads use the raw joystick: hat or left stick, buttons 0-3
fire, button 7, 9 or 11 Start, button 6, 8 or 10 Back.
"""
import pygame

try:
    import pygame._sdl2.controller as _ctl
except ImportError:          # pragma: no cover - old pygame
    _ctl = None

DEAD = 0.5                   # stick dead zone (part of full range)
NAMES = ("up", "down", "left", "right", "fire", "start", "back")


class Pad:
    def __init__(self, index):
        self.ctl = self.js = None
        if _ctl and _ctl.is_controller(index):
            self.ctl = _ctl.Controller(index)
            self.name = self.ctl.name
        else:
            self.js = pygame.joystick.Joystick(index)
            self.name = self.js.get_name()
        self.now = dict.fromkeys(NAMES, False)
        self.prev = dict(self.now)

    def poll(self):
        self.prev = self.now
        try:
            self.now = self._read()
        except pygame.error:          # unplugged
            self.now = dict.fromkeys(NAMES, False)

    def pressed(self, name):
        """True on the frame the button goes down."""
        return self.now[name] and not self.prev[name]

    def _read(self):
        out = dict.fromkeys(NAMES, False)
        if self.ctl:
            c, b = self.ctl, self.ctl.get_button
            ax = c.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32767
            ay = c.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32767
            out["up"] = b(pygame.CONTROLLER_BUTTON_DPAD_UP) or ay < -DEAD
            out["down"] = b(pygame.CONTROLLER_BUTTON_DPAD_DOWN) or ay > DEAD
            out["left"] = b(pygame.CONTROLLER_BUTTON_DPAD_LEFT) or ax < -DEAD
            out["right"] = b(pygame.CONTROLLER_BUTTON_DPAD_RIGHT) or ax > DEAD
            out["fire"] = any(b(x) for x in (pygame.CONTROLLER_BUTTON_A, pygame.CONTROLLER_BUTTON_B,
                                             pygame.CONTROLLER_BUTTON_X, pygame.CONTROLLER_BUTTON_Y)) \
                or c.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) > 16000
            out["start"] = b(pygame.CONTROLLER_BUTTON_START)
            out["back"] = b(pygame.CONTROLLER_BUTTON_BACK)
            return {k: bool(v) for k, v in out.items()}
        js = self.js
        nb = js.get_numbuttons()
        btn = lambda *ids: any(js.get_button(i) for i in ids if i < nb)  # noqa: E731
        hx, hy = js.get_hat(0) if js.get_numhats() else (0, 0)
        ax = js.get_axis(0) if js.get_numaxes() > 1 else 0
        ay = js.get_axis(1) if js.get_numaxes() > 1 else 0
        out["left"] = hx < 0 or ax < -DEAD
        out["right"] = hx > 0 or ax > DEAD
        out["up"] = hy > 0 or ay < -DEAD
        out["down"] = hy < 0 or ay > DEAD
        out["fire"] = btn(0, 1, 2, 3)
        out["start"] = btn(7, 9, 11)
        out["back"] = btn(6, 8, 10)
        return out


class Pads:
    """All connected pads; pad i drives player i."""
    def __init__(self):
        pygame.joystick.init()
        if _ctl:
            _ctl.init()
        self.scan()

    def scan(self):
        self.list = [Pad(i) for i in range(pygame.joystick.get_count())]

    def event(self, ev):
        if ev.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
            self.scan()

    def poll(self):
        for p in self.list:
            p.poll()

    def pressed(self, name):
        """True if this button went down on any pad."""
        return any(p.pressed(name) for p in self.list)

    def __getitem__(self, i):
        return self.list[i]

    def __len__(self):
        return len(self.list)
