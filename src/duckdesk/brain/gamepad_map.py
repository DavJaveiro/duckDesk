"""Gamepad -> duck command mapping (docs/04 section 3).

Layout (Xbox names; generic pads land on the first two axes + first
buttons via platform/gamepad.py):

- Left stick  : drive — up/down -> vx, left/right -> wz (turn)
- Right stick : look — left/right -> head_yaw, up/down -> neck pitch
- D-pad L/R   : strafe (vy), like Q/E on the keyboard
- A / B / X / Y        : bicar / cambalhota / chute esq. / chute dir.
- Back / Start / L3 / R3 : sentar-levantar / pausa / zerar pose / reset

Stick magnitudes are floor-scaled the same reason the keyboard uses the
top of the trained range: under BAM-CPU the velstand ignores |vx| < ~0.25
and |wz| < ~1.0 (ADR-0006), so any real deflection must command at least
the walking/turning threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from duckdesk.brain.commands import Request
from duckdesk.brain.keyboard import ANG_RAMP, LIN_RAMP, AppIntent, _ramp
from duckdesk.platform.gamepad import Pad, gamepad_state

DEADZONE = 0.18
VX_MIN_WALK = 0.26  # ADR-0006: |vx| < ~0.25 is ignored by the policy
WZ_MIN_TURN = 1.0  # ADR-0006: |wz| < ~1.0 does not turn
VX_MAX, VY_MAX, WZ_MAX = 0.3, 0.2, 1.5
HEAD_YAW = 0.9  # head_pose[2]
HEAD_PITCH = 0.4  # head_pose[0]

_BUTTON_REQUESTS = {
    "a": Request.PECK,
    "b": Request.ROLL,
    "x": Request.KICK_L,
    "y": Request.KICK_R,
    "r3": Request.RESET,
}

_BUTTON_INTENTS = {
    "back": AppIntent.TOGGLE_SIT,
    "start": AppIntent.PAUSE,
    "l3": AppIntent.ZERO_POSE,
}


def _scaled(axis: float, lo: float, hi: float) -> float:
    """Signed magnitude in [lo, hi] once past the deadzone, else 0."""
    m = abs(axis)
    if m <= DEADZONE:
        return 0.0
    return float(np.sign(axis) * (lo + (hi - lo) * (m - DEADZONE) / (1.0 - DEADZONE)))


@dataclass
class GamepadMapper:
    """Held-stick command source; mirrors KeyboardMapper's contract."""

    _prev: frozenset = field(default_factory=frozenset)
    _cmd: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    connected: bool = False

    def poll(self, dt: float):
        return self.poll_state(gamepad_state(), dt)

    def poll_state(self, pad: Pad | None, dt: float):
        """-> (twist|None, head|None, requests, intents).

        twist/head are None when the pad is disconnected or every stick is
        inside the deadzone, so the keyboard keeps owning that channel."""
        if pad is None:
            self.connected = False
            self._prev = frozenset()
            self._cmd[:] = 0.0
            return None, None, [], []
        self.connected = True

        target = self._twist_target(pad)
        if target is None:
            self._cmd[:] = 0.0
        else:
            self._cmd[0] = _ramp(self._cmd[0], target[0], LIN_RAMP, dt)
            self._cmd[1] = _ramp(self._cmd[1], target[1], LIN_RAMP, dt)
            self._cmd[2] = _ramp(self._cmd[2], target[2], ANG_RAMP, dt)

        pressed = pad.buttons - self._prev
        self._prev = pad.buttons
        requests = [_BUTTON_REQUESTS[b] for b in pressed if b in _BUTTON_REQUESTS]
        intents = [_BUTTON_INTENTS[b] for b in pressed if b in _BUTTON_INTENTS]
        head = self._head_target(pad)
        twist = self._cmd.copy() if target is not None else None
        return twist, head, requests, intents

    def _twist_target(self, pad: Pad) -> np.ndarray | None:
        vx = _scaled(pad.ly, VX_MIN_WALK, VX_MAX)
        wz = -_scaled(pad.lx, WZ_MIN_TURN, WZ_MAX)  # stick right = turn right
        vy = 0.0
        if "left" in pad.buttons:
            vy += VY_MAX
        if "right" in pad.buttons:
            vy -= VY_MAX
        if vx == vy == wz == 0.0:
            return None
        return np.array([vx, vy, wz], dtype=np.float32)

    def _head_target(self, pad: Pad) -> np.ndarray | None:
        yaw = _scaled(pad.rx, 0.0, HEAD_YAW)
        pitch = _scaled(pad.ry, 0.0, HEAD_PITCH)
        if yaw == 0.0 and pitch == 0.0:
            return None
        head = np.zeros(4, dtype=np.float32)
        head[0] = pitch
        head[2] = yaw
        return head
