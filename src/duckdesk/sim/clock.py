"""Fixed-step accumulator for the 20 ms control loop (docs/02)."""

from __future__ import annotations

from duckdesk.sim.core import CONTROL_DT

MAX_STEPS_PER_TICK = 5


class SimClock:
    """Given the real elapsed time, says how many 20 ms control steps are due.

    At most MAX_STEPS_PER_TICK per tick: if the loop falls behind, the backlog
    is discarded instead of spiraling (docs/02 "Laço principal").
    """

    def __init__(self, speed: float = 1.0):
        self.speed = speed  # 0.5 or 1.0
        self.paused = False
        self._accumulator = 0.0

    def steps_due(self, elapsed_s: float) -> int:
        """Add real elapsed seconds (scaled by speed) and return the step count."""
        if self.paused:
            return 0
        self._accumulator += elapsed_s * self.speed
        steps = int(self._accumulator / CONTROL_DT)
        if steps > MAX_STEPS_PER_TICK:
            steps = MAX_STEPS_PER_TICK
            self._accumulator = 0.0  # discard the backlog
        else:
            self._accumulator -= steps * CONTROL_DT
        return steps
