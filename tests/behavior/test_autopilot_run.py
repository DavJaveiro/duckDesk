"""M2 acceptance: 10 minutes of headless autopilot (docs/08 section M2).

Runs the real SimCore + PolicyManager + Autopilot for 600 s of simulated time.
Checks: never leaves the x range, no state stuck > 60 s, |y| < 0.3 m
(duvidas.md #6, resolved by ADR-0006). Prints the state histogram +
falls/resets for the report.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import Trial

from duckdesk.brain.autopilot import Autopilot
from duckdesk.brain.commands import Request
from duckdesk.sim.core import CONTROL_DT
from duckdesk.sim.watchdog import Watchdog

pytestmark = pytest.mark.behavior

SECONDS = 600.0
X_RANGE = (-2.5, 2.5)


@pytest.fixture(scope="module")
def autopilot_log():
    t = Trial(seed=0)
    pilot = Autopilot(np.random.default_rng(0), x_range=X_RANGE)
    watchdog = Watchdog()

    xs, ys = [], []
    resets = 0
    steps = round(SECONDS / CONTROL_DT)
    for _ in range(steps):
        pos = t.sim.trunk_pos()
        pilot.update(
            CONTROL_DT,
            float(pos[0]),
            float(pos[1]),
            t.sim.trunk_yaw(),
            t.sim.trunk_tilt(),
            t.mgr,
        )
        targets = t.mgr.step(t.sim)
        t.sim.step_control(targets)
        if watchdog.check(t.sim, CONTROL_DT):
            resets += 1
            t.mgr.request(Request.RESET, t.sim)
        xs.append(float(pos[0]))
        ys.append(float(pos[1]))
    pilot.max_stint[pilot.state.value] = max(pilot.max_stint[pilot.state.value], pilot.state_s)
    return pilot, np.asarray(xs), np.asarray(ys), resets


def test_autopilot_stays_in_x_range(autopilot_log):
    _, xs, _, _ = autopilot_log
    out = int(((xs < X_RANGE[0]) | (xs > X_RANGE[1])).sum())
    print(f"\nx range: [{xs.min():.2f}, {xs.max():.2f}] | fora: {out} passos")
    assert out == 0


def test_no_state_stuck_over_60s(autopilot_log):
    pilot, *_ = autopilot_log
    worst = max(pilot.max_stint.values())
    print(f"\nmaior stint: {worst:.1f} s | por estado: {pilot.max_stint}")
    assert worst <= 60.0


def test_abs_y_under_0p3(autopilot_log):
    """[duro] in docs/08 M2. With ADR-0006 (lag 0, vx 0.3) seed 0 peaks at
    |y| = 0.12 m with one fall in 10 min (was an xfail under lag 3)."""
    _, _, ys, _ = autopilot_log
    print(f"\n|y| max {np.abs(ys).max():.3f} m")
    assert np.abs(ys).max() < 0.3


def test_autopilot_histogram_for_report(autopilot_log):
    pilot, _, _, resets = autopilot_log
    total = sum(pilot.time_in_state.values())
    print("\n=== piloto automatico 600 s ===")
    for st, secs in sorted(pilot.time_in_state.items(), key=lambda kv: -kv[1]):
        if secs > 0:
            print(
                f"  {st:8s} {secs:7.1f} s ({100 * secs / total:4.1f} %)"
                f" | stint max {pilot.max_stint[st]:5.1f} s"
            )
    print(f"quedas: {pilot.falls} | resets watchdog: {resets}")
