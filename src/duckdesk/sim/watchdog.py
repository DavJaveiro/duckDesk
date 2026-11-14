"""Simulation watchdog (docs/02 "Laço principal").

- NaN in qpos -> immediate reset (caller performs it).
- Trunk tilted more than 60 deg for more than 6 s straight (velstand failed to
  get up) -> reset to standing.
"""

from __future__ import annotations

import math

import numpy as np

TILT_LIMIT_RAD = math.radians(60)
TILT_TIME_LIMIT_S = 6.0


class Watchdog:
    """Stateless checks per control step; the tilt timer accumulates here."""

    def __init__(self):
        self._tilted_s = 0.0

    def check(self, sim, control_dt: float) -> str | None:
        """Return the event to act on ('nan' or 'fallen'), or None."""
        if np.isnan(sim.data.qpos).any():
            self._tilted_s = 0.0
            return "nan"
        if sim.trunk_tilt() > TILT_LIMIT_RAD:
            self._tilted_s += control_dt
            if self._tilted_s > TILT_TIME_LIMIT_S:
                self._tilted_s = 0.0
                return "fallen"
        else:
            self._tilted_s = 0.0
        return None
