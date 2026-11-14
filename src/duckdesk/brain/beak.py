"""Mascot mouth animation (ADR-0010, docs/05 section 6).

On the real robot a dedicated mouth servo (duck-control model.rs:
``MOUTH_INDEX = 9``, Dynamixel id 34) sits outside every policy and is driven
by the daemon. The bundled MJCF models the jaw as rigid geometry, so the
SimCore poses the mouth parts kinematically and this animator produces the
0..1 opening plus the head-pitch offsets, mirroring upstream robotd:

- **Quacks open the beak, with a head toss** (autonomous.md: "one to four
  chirps, with the mouth and a head toss"). The bundled ``quack.mp3`` is one
  file, so the opening follows the recording's own loudness envelope —
  ``QUACK_ENV``, 40 ms RMS keyframes — like the chorale mapping each vowel to
  a mouth opening in robotd main.rs.
- **Glances open the beak "a touch"** (robotd idle_head.rs):
  ``glance_mouth = 0.4`` scaled by ``rng(0.5, 1)`` per glance.
- **Long stillness brings a yawn** (idle_head.rs ``yawn_shape``: slow open, a
  hold at the top, a quicker close), mouth to ``yawn_open = 0.6`` for
  ``yawn_s = 3.0`` while the head tips ``yawn_pitch = -0.15`` (robotd-params
  defaults). The stillness-then-coin scheduling lives in the Autopilot, which
  knows when the duck last moved.

Composition matches robotd main.rs (``mouth = max(intent, idle)``): the quack
envelope wins; otherwise glance + yawn add, capped at 1.
"""

from __future__ import annotations

import itertools

import numpy as np

# RMS envelope of assets/sounds/quack.mp3, 40 ms frames, peak-normalized
# (x1.25, clipped to 1) — the mouth opens with each burst in the recording.
QUACK_ENV = (
    (0.00, 0.00),
    (0.04, 0.21),
    (0.08, 0.51),
    (0.12, 0.92),
    (0.16, 1.00),
    (0.28, 0.77),
    (0.32, 0.43),
    (0.36, 0.16),
    (0.40, 0.06),
    (0.44, 0.17),
    (0.48, 0.41),
    (0.52, 0.67),
    (0.56, 0.73),
    (0.60, 0.63),
    (0.64, 0.36),
    (0.68, 0.19),
    (0.72, 0.00),
    (0.76, 0.07),
    (0.80, 0.25),
    (0.84, 0.51),
    (0.88, 0.55),
    (0.92, 0.37),
    (0.96, 0.18),
    (1.00, 0.24),
    (1.04, 0.41),
    (1.08, 0.52),
    (1.12, 0.40),
    (1.16, 0.22),
    (1.20, 0.11),
    (1.24, 0.20),
    (1.28, 0.29),
    (1.32, 0.34),
    (1.36, 0.22),
    (1.40, 0.13),
    (1.44, 0.09),
    (1.48, 0.25),
    (1.52, 0.39),
    (1.56, 0.47),
    (1.60, 0.33),
    (1.64, 0.22),
    (1.68, 0.19),
    (1.72, 0.31),
    (1.76, 0.36),
    (1.80, 0.27),
    (1.84, 0.12),
    (1.88, 0.00),
    (1.96, 0.12),
    (2.00, 0.20),
    (2.04, 0.25),
    (2.08, 0.20),
    (2.12, 0.11),
    (2.16, 0.00),
    (2.24, 0.09),
    (2.28, 0.18),
    (2.32, 0.22),
    (2.36, 0.20),
    (2.40, 0.11),
    (2.44, 0.06),
    (2.48, 0.08),
    (2.52, 0.15),
    (2.56, 0.22),
    (2.60, 0.21),
    (2.64, 0.14),
    (2.72, 0.00),
)

GLANCE_MOUTH = 0.4  # robotd-params default: a glance's beak opening, 0..1
GLANCE_BEAK = (0.5, 1.0)  # idle_head.rs: per-glance scale rng(0.5, 1)
YAWN_OPEN = 0.6  # robotd-params: mouth opening at the yawn's top
YAWN_S = 3.0  # yawn duration
YAWN_PITCH = -0.15  # head tip during the yawn (negative = beak up)
QUACK_TOSS = -0.10  # head_pitch offset while quacking (the toss)


def _ease(x: float) -> float:
    """Minimum-jerk ease (idle_head.rs `ease`): still at both ends."""
    x = min(1.0, max(0.0, x))
    return x * x * x * (10.0 + x * (-15.0 + 6.0 * x))


def _yawn_shape(x: float) -> float:
    """Slow open, a hold at the top, a quicker close (idle_head.rs)."""
    if x < 0.4:
        return _ease(x / 0.4)
    if x < 0.7:
        return 1.0
    return 1.0 - _ease((x - 0.7) / 0.3)


def _env_at(frames: tuple[tuple[float, float], ...], t: float) -> float:
    """Piecewise-linear keyframe lookup; 0 outside the table."""
    if t <= 0.0 or t >= frames[-1][0]:
        return 0.0
    for (t0, v0), (t1, v1) in itertools.pairwise(frames):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return 0.0


class BeakAnimator:
    """Mouth opening (``mouth``, 0..1) and head offsets (``head``, rad)."""

    def __init__(self) -> None:
        self.mouth = 0.0
        self.head = 0.0  # head_pitch offset; <0 tips the beak up
        self._quack_t: float | None = None
        self._env = QUACK_ENV  # envelope the quack timeline plays
        self._yawn_t: float | None = None
        self._glance = 0.0

    # --- triggers ------------------------------------------------------------

    def vocalise(self, frames: tuple[tuple[float, float], ...]) -> None:
        """(Re)start the beak timeline on any sound's envelope — generated
        voice calls drive the mouth exactly like the recording does."""
        self._env = frames
        self._quack_t = 0.0

    def quack(self) -> None:
        """(Re)start the bundled-quack lip-sync and head toss."""
        self.vocalise(QUACK_ENV)

    def yawn(self) -> None:
        """Start a yawn unless one is already playing."""
        if self._yawn_t is None:
            self._yawn_t = 0.0

    def stop(self) -> None:
        """Drop any running timeline (leaving mascot mode)."""
        self._quack_t = None
        self._yawn_t = None
        self._glance = 0.0
        self.mouth = 0.0
        self.head = 0.0

    def set_glance(self, opening: float) -> None:
        """The glance's touch of beak opening (idle_head.rs)."""
        self._glance = float(np.clip(opening, 0.0, GLANCE_MOUTH))

    @property
    def yawning(self) -> bool:
        return self._yawn_t is not None

    @property
    def quacking(self) -> bool:
        return self._quack_t is not None

    # --- per-tick -------------------------------------------------------------

    def update(self, dt: float) -> None:
        q = 0.0
        if self._quack_t is not None:
            q = _env_at(self._env, self._quack_t)
            self._quack_t += dt
            if self._quack_t >= self._env[-1][0]:
                self._quack_t = None
        y = 0.0
        if self._yawn_t is not None:
            y = _yawn_shape(self._yawn_t / YAWN_S)
            self._yawn_t += dt
            if self._yawn_t >= YAWN_S:
                self._yawn_t = None
        self.mouth = max(q, min(1.0, self._glance + YAWN_OPEN * y))
        self.head = QUACK_TOSS * q + YAWN_PITCH * y
