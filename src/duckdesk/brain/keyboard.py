"""Qt-independent keyboard mapping (docs/04 section 3).

Keys are plain strings ("w", "up", "shift", "ctrl", "space", ...) so any UI
layer can feed them. Directional keys apply *while held* (no step increments);
the command ramps at 1.5 m/s^2 (linear) and 6 rad/s^2 (yaw). One-shot keys emit
`Request` or `AppIntent` objects on press.

    mapper = KeyboardMapper()
    mapper.press("w"); mapper.press("shift")
    cmd, requests, intents = mapper.poll(dt)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import numpy as np

from duckdesk.brain.commands import DuckCommand, Request

# Ramp rates (docs/04 section 3).
LIN_RAMP = 1.5  # m/s^2
ANG_RAMP = 6.0  # rad/s^2

# Base directional targets and the Shift-boosted ones (docs/03 section 8 limits).
# velstand ignores |vx| below ~0.25 under BAM-CPU (ADR-0006): walk keys use the
# top of the trained range so a key press always produces steps.
_BASE = {"vx_f": 0.3, "vx_b": -0.3, "vy": 0.2, "wz": 1.5}
_BOOST = {"vx_f": 0.3, "vx_b": -0.3, "vy": 0.2, "wz": 1.5}

_FORWARD = frozenset(("w", "up"))
_BACK = frozenset(("s", "down"))
_LEFT = frozenset(("a", "left"))
_RIGHT = frozenset(("d", "right"))
_STRAFE_L = frozenset(("q",))
_STRAFE_R = frozenset(("e",))

_REQUEST_KEYS = {
    "g": Request.PECK,
    "r": Request.ROLL,
    "k": Request.KICK_L,
    "l": Request.KICK_R,
    "backspace": Request.RESET,
}


class AppIntent(enum.Enum):
    """Actions the caller must service (not PolicyManager requests)."""

    TOGGLE_SIT = "toggle_sit"  # caller maps to Request.SIT/STAND by state
    ZERO_POSE = "zero_pose"  # space: clear head/body command
    PAUSE = "pause"
    MINIMIZE = "minimize"  # Ctrl+M -> send to taskbar


_INTENT_KEYS = {
    "y": AppIntent.TOGGLE_SIT,
    "space": AppIntent.ZERO_POSE,
    "p": AppIntent.PAUSE,
}


def _ramp(current: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    return float(np.clip(target, current - step, current + step))


@dataclass
class KeyboardMapper:
    """Held-key command source with ramps (docs/04 section 3)."""

    _held: set = field(default_factory=set)
    _cmd: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )  # smoothed vx, vy, wz

    # --- key events ---------------------------------------------------------

    def press(self, key: str) -> None:
        self._held.add(key.lower())

    def release(self, key: str) -> None:
        self._held.discard(key.lower())

    def release_all(self) -> None:
        self._held.clear()

    @property
    def _boosted(self) -> bool:
        return "shift" in self._held

    # --- per-tick polling -----------------------------------------------------

    def _twist_target(self) -> np.ndarray:
        t = _BOOST if self._boosted else _BASE
        vx = vy = wz = 0.0
        held = self._held
        if held & _FORWARD:
            vx += t["vx_f"]
        if held & _BACK:
            vx += t["vx_b"]
        if held & _STRAFE_L:
            vy += t["vy"]
        if held & _STRAFE_R:
            vy -= t["vy"]
        if held & _LEFT:
            wz += t["wz"]
        if held & _RIGHT:
            wz -= t["wz"]
        return np.array([vx, vy, wz], dtype=np.float32)

    def poll(self, dt: float) -> tuple[DuckCommand, list[Request], list[AppIntent]]:
        """Advance the ramp by `dt` and drain one-shot key events.

        Returns (command, requests, intents)."""
        target = self._twist_target()
        self._cmd[0] = _ramp(self._cmd[0], target[0], LIN_RAMP, dt)
        self._cmd[1] = _ramp(self._cmd[1], target[1], LIN_RAMP, dt)
        self._cmd[2] = _ramp(self._cmd[2], target[2], ANG_RAMP, dt)

        requests = [_REQUEST_KEYS[k] for k in self._held if k in _REQUEST_KEYS]
        intents = [_INTENT_KEYS[k] for k in self._held if k in _INTENT_KEYS]
        if "ctrl" in self._held and "m" in self._held:
            intents.append(AppIntent.MINIMIZE)
        # One-shot keys fire once per press.
        for k in (*_REQUEST_KEYS, *_INTENT_KEYS, "m"):
            self._held.discard(k)

        cmd = DuckCommand()
        cmd.twist = self._cmd.copy()
        return cmd, requests, intents
