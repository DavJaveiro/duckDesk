"""Deterministic mascot autopilot (docs/05 section 5).

State machine driven per control tick with an injected
``numpy.random.Generator`` — fully testable without a window. It issues
``DuckCommand``/``Request`` through the PolicyManager, so the docs/03 section 8
rules still gate every behavior (the autopilot never bypasses them).

Deviations from docs/05 (documented in duvidas.md):
- WALK entry performs a short yaw "wiggle" (~0.35 s): velstand under
  BAM-CPU only leaves the standing basin when the command arrives during a
  transient — a settled duck ignores a pure vx step.
- WALK has a no-progress timeout (25 s without closing on the target) ->
  IDLE; the tracking floor of velstand+BAM-CPU can otherwise pin the state.
"""

from __future__ import annotations

import enum
import math

import numpy as np

from duckdesk.brain.commands import DuckCommand, Request

IDLE_MIN, IDLE_MAX = 2.0, 6.0
SIT_MIN, SIT_MAX = 5.0, 20.0
WALK_V_MIN, WALK_V_MAX = 0.15, 0.25
MIN_TARGET_DIST = 0.5
ARRIVE_TOL = 0.05
EDGE_MARGIN = 0.15
YAW_TOL = 0.15
FALL_TILT_RAD = math.radians(45)
UPRIGHT_S = 1.0
LOOK_YAW_MAX, LOOK_PITCH_MAX = 0.6, 0.3
LOOK_PERIOD = (1.0, 2.0)
LOOK_RAMP = 1.0  # rad/s
LAUNCH_S = 0.35  # yaw wiggle on WALK entry (see module docstring)
LAUNCH_WZ = 0.7
NO_PROGRESS_S = 25.0  # WALK bail-out (see module docstring)
ROLL_CLEAR = 0.4
ROLL_COOLDOWN_S = 180.0
# IDLE -> next-state lottery (docs/05 section 5).
_LOTTERY = (("walk", 0.55), ("sit", 0.15), ("peck", 0.15), ("idle", 0.10), ("roll", 0.05))


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class AutoState(enum.Enum):
    IDLE = "idle"
    WALK = "walk"
    TURN = "turn"
    SIT = "sit"
    PECK = "peck"
    ROLL = "roll"
    RECOVER = "recover"


class Autopilot:
    def __init__(
        self,
        rng: np.random.Generator,
        x_range: tuple[float, float] = (-2.5, 2.5),
        enabled: bool = True,
    ):
        self.rng = rng
        self.x_min, self.x_max = x_range
        self.enabled = enabled

        self.state = AutoState.IDLE
        self.state_s = 0.0  # time in current state (for the 60 s check)
        self.time_in_state = {s.value: 0.0 for s in AutoState}
        self.max_stint = {s.value: 0.0 for s in AutoState}  # longest single stay
        self.falls = 0

        self._prev = AutoState.IDLE  # state TURN returns to
        self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
        self._look_left = 0.0
        self._look_target = np.zeros(2, dtype=np.float32)  # head_yaw, head_pitch
        self._look_now = np.zeros(2, dtype=np.float32)

        self.target_x = 0.0
        self._v_walk = 0.2
        self._launch_left = 0.0
        self._launch_dir = 1.0
        self._progress_ref = math.inf  # best |target_x - x| this WALK
        self._no_progress = 0.0

        self._sit_left = 0.0
        self._stand_requested = False
        self._upright_s = 0.0
        self._req_sent = False
        self._last_roll_s = -ROLL_COOLDOWN_S
        self._now = 0.0

    def _draw(self, lo: float, hi: float) -> float:
        return float(self.rng.uniform(lo, hi))

    def _goto(self, state: AutoState) -> None:
        if state is not self.state:
            self.max_stint[self.state.value] = max(self.max_stint[self.state.value], self.state_s)
            self._prev, self.state = self.state, state
            self.state_s = 0.0
            self._req_sent = False

    # --- helpers -------------------------------------------------------------

    def _heading(self, x: float, y: float, yaw: float) -> tuple[float, float]:
        """wz/vx pair from the docs/05 control law (minus vx gating)."""
        base = 0.0 if self.target_x > x else math.pi
        direction = 1.0 if base == 0.0 else -1.0
        yaw_ref = base + float(np.clip(-0.8 * y * direction, -0.3, 0.3))
        err = _wrap(yaw_ref - yaw)
        wz = float(np.clip(2.0 * err, -1.0, 1.0))
        return wz, err

    def _clear_ahead(self, x: float, yaw: float) -> bool:
        facing = math.cos(yaw)  # +1 -> +x
        ahead = (self.x_max - x) if facing > 0 else (x - self.x_min)
        return ahead >= ROLL_CLEAR

    def _enter_walk(self, x: float) -> None:
        for _ in range(8):
            cand = float(self.rng.uniform(self.x_min, self.x_max))
            if abs(cand - x) >= MIN_TARGET_DIST:
                break
        self.target_x = cand
        self._v_walk = self._draw(WALK_V_MIN, WALK_V_MAX)
        self._launch_left = LAUNCH_S
        self._launch_dir = float(self.rng.choice((-1.0, 1.0)))
        self._progress_ref = math.inf
        self._no_progress = 0.0
        self._goto(AutoState.WALK)

    def _draw_idle_next(self, x: float, yaw: float) -> None:
        r = float(self.rng.uniform())
        acc = 0.0
        pick = "idle"
        for name, p in _LOTTERY:
            acc += p
            if r <= acc:
                pick = name
                break
        if pick == "walk":
            self._enter_walk(x)
        elif pick == "sit":
            self._goto(AutoState.SIT)
        elif pick == "peck":
            self._goto(AutoState.PECK)
        elif pick == "roll":
            if self._clear_ahead(x, yaw) and self._now - self._last_roll_s >= ROLL_COOLDOWN_S:
                self._goto(AutoState.ROLL)
            else:
                self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
        else:  # idle again
            self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)

    # --- per-tick update -------------------------------------------------------

    def update(self, dt: float, x: float, y: float, yaw: float, tilt: float, mgr) -> None:
        self._now += dt
        self.state_s += dt
        self.time_in_state[self.state.value] += dt

        # Fallen duck preempts everything (docs/05 RECOVER).
        if self.state is not AutoState.RECOVER and tilt > FALL_TILT_RAD:
            self.falls += 1
            self._goto(AutoState.RECOVER)
            self._upright_s = 0.0

        cmd = DuckCommand()

        if self.state is AutoState.RECOVER:
            if tilt <= FALL_TILT_RAD:
                self._upright_s += dt
                if self._upright_s >= UPRIGHT_S:
                    self._goto(AutoState.IDLE)
                    self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
            else:
                self._upright_s = 0.0
            mgr.set_command(cmd)
            return

        if not self.enabled:
            # Autopilot off: park in IDLE forever (docs/05 section 5); clicks
            # can still drive the manager from outside.
            if self.state is not AutoState.IDLE:
                self._goto(AutoState.IDLE)
            mgr.set_command(cmd)
            return

        if self.state is AutoState.IDLE:
            self._look_left -= dt
            if self._look_left <= 0.0:
                self._look_left = self._draw(*LOOK_PERIOD)
                self._look_target = np.array(
                    [
                        self.rng.uniform(-LOOK_YAW_MAX, LOOK_YAW_MAX),
                        self.rng.uniform(-LOOK_PITCH_MAX, LOOK_PITCH_MAX),
                    ],
                    dtype=np.float32,
                )
            step = LOOK_RAMP * dt
            self._look_now += np.clip(self._look_target - self._look_now, -step, step)
            cmd.head = np.array([0.0, self._look_now[1], self._look_now[0], 0.0], dtype=np.float32)
            self._idle_left -= dt
            if self._idle_left <= 0.0:
                self._draw_idle_next(x, yaw)

        elif self.state is AutoState.WALK:
            wz, err = self._heading(x, y, yaw)
            if self._launch_left > 0.0:
                self._launch_left -= dt
                vx, wz = 0.0, LAUNCH_WZ * self._launch_dir
            else:
                vx = 0.0 if abs(err) > 0.4 else self._v_walk
            cmd.twist = np.array([vx, 0.0, wz], dtype=np.float32)

            # Edge rule: near the limit and heading out -> flip target via TURN.
            facing = math.cos(yaw)
            if (x < self.x_min + EDGE_MARGIN and facing < -0.2) or (
                x > self.x_max - EDGE_MARGIN and facing > 0.2
            ):
                self.target_x = self.x_max if facing < -0.2 else self.x_min
                self._goto(AutoState.TURN)
            elif abs(self.target_x - x) < ARRIVE_TOL:
                self._goto(AutoState.IDLE)
                self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
            else:
                gap = abs(self.target_x - x)
                if gap < self._progress_ref - 0.02:
                    self._progress_ref = gap
                    self._no_progress = 0.0
                else:
                    self._no_progress += dt
                    if self._no_progress > NO_PROGRESS_S:
                        self._goto(AutoState.IDLE)
                        self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)

        elif self.state is AutoState.TURN:
            wz, err = self._heading(x, y, yaw)
            cmd.twist = np.array([0.0, 0.0, wz], dtype=np.float32)
            if abs(err) < YAW_TOL:
                self._goto(self._prev if self._prev is not AutoState.TURN else AutoState.IDLE)
                if self.state is AutoState.IDLE:
                    self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)

        elif self.state is AutoState.SIT:
            if self._stand_requested:
                # Waiting for the sitstand rise to finish (docs/03 section 8).
                if not mgr.busy and not mgr.seated:
                    self._stand_requested = False
                    self._goto(AutoState.IDLE)
                    self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
            elif not mgr.seated:
                if not mgr.busy:
                    mgr.request(Request.SIT)
            elif self._sit_left <= 0.0:
                self._sit_left = self._draw(SIT_MIN, SIT_MAX)
            else:
                self._sit_left -= dt
                if self._sit_left <= 0.0:
                    ok, _ = mgr.request(Request.STAND)
                    self._stand_requested = ok

        elif self.state in (AutoState.PECK, AutoState.ROLL):
            request = Request.PECK if self.state is AutoState.PECK else Request.ROLL
            if not self._req_sent:
                ok, _ = mgr.request(request)
                self._req_sent = ok
                if not ok:  # refused by the rules -> drop to IDLE
                    self._goto(AutoState.IDLE)
                    self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
            elif not mgr.busy:  # episode finished -> back to IDLE
                self._goto(AutoState.IDLE)
                self._idle_left = self._draw(IDLE_MIN, IDLE_MAX)
            elif self.state is AutoState.ROLL:
                self._last_roll_s = self._now

        mgr.set_command(cmd)

    def enter_role(self, role: str) -> None:
        """External trigger (e.g. a click): request a behavior if rules allow."""
        self._goto(AutoState[role.upper()])
