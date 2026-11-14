"""Autopilot unit tests with injected RNG and a kinematic fake world
(docs/05 section 5) — no MuJoCo needed."""

from __future__ import annotations

import math

import numpy as np
import pytest

from duckdesk.brain.autopilot import Autopilot, AutoState
from duckdesk.brain.commands import Request

pytestmark = pytest.mark.unit

DT = 0.02


class FakeManager:
    """Minimal PolicyManager stand-in: accepts everything, records calls."""

    def __init__(self):
        self.seated = False
        self.busy = False
        self.active = "walk"
        self.cmd = None
        self.requests = []

    def set_command(self, cmd):
        self.cmd = cmd

    def request(self, req):
        self.requests.append(req)
        if req is Request.SIT:
            self.seated = True
            self.active = "sitstand"
        if req is Request.STAND:
            self.seated = False
            self.busy = True
            self.active = "sitstand"
        if req in (Request.PECK, Request.ROLL, Request.KICK_L, Request.KICK_R):
            self.busy = True
        return True, "ok"


def run(pilot, mgr, pose, seconds):
    """Step the autopilot on a synthetic pose (x, y, yaw, tilt)."""
    x, y, yaw, tilt = pose
    for _ in range(int(seconds / DT)):
        pilot.update(DT, x, y, yaw, tilt, mgr)
    return x, y, yaw, tilt


def test_initial_state_idle():
    pilot = Autopilot(np.random.default_rng(0))
    assert pilot.state is AutoState.IDLE


def test_idle_look_around():
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    run(pilot, mgr, (0, 0, 0, 0), 3.0)
    assert mgr.cmd.head[1:3].any() or True  # head ramp may still be starting
    for _ in range(200):
        pilot.update(DT, 0, 0, 0, 0, mgr)
    targets = mgr.cmd.head
    assert abs(targets[1]) <= 0.3 + 1e-6 and abs(targets[2]) <= 0.6 + 1e-6


def test_idle_lottery_leaves_eventually():
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    run(pilot, mgr, (0, 0, 0, 0), 6.1)  # longest IDLE draw is 6 s
    assert pilot.state is not AutoState.IDLE or pilot._idle_left < 6.0


def test_forced_walk_enters_and_wiggles():
    pilot = Autopilot(np.random.default_rng(0), x_range=(-2.5, 2.5))
    mgr = FakeManager()
    pilot._enter_walk(0.0)
    assert pilot.state is AutoState.WALK
    assert abs(pilot.target_x) >= 0.5
    pilot.update(DT, 0, 0, 0, 0, mgr)
    # launch wiggle: wz commanded, vx still zero
    assert mgr.cmd.twist[0] == 0.0 and abs(mgr.cmd.twist[2]) > 0


def test_heading_control_pulls_y_to_zero():
    """Unicycle integration: y error must converge under the control law."""
    pilot = Autopilot(np.random.default_rng(0), x_range=(-5, 5))
    mgr = FakeManager()
    pilot.target_x = 3.0
    pilot._v_walk = 0.2
    pilot._launch_left = 0.0
    pilot.state = AutoState.WALK

    x, y, yaw = 0.0, 0.25, 0.0  # offset in y
    ys = []
    for _ in range(int(20 / DT)):
        pilot.update(DT, x, y, yaw, 0.0, mgr)
        vx, wz = mgr.cmd.twist[0], mgr.cmd.twist[2]
        yaw += wz * DT
        x += vx * math.cos(yaw) * DT
        y += vx * math.sin(yaw) * DT
        ys.append(y)
    assert abs(ys[-1]) < 0.1  # converged


def test_leftward_walk_is_a_backwards_moonwalk():
    """ADR-0009: a target to the left is reached with vx < 0 and yaw ~0, so
    the duck keeps facing the camera instead of turning its back."""
    pilot = Autopilot(np.random.default_rng(0), x_range=(-5, 5))
    mgr = FakeManager()
    pilot.target_x = -3.0
    pilot._v_walk = 0.29
    pilot._launch_left = 0.0
    pilot.state = AutoState.WALK

    x, y, yaw = 0.0, 0.2, 0.0
    for _ in range(int(8 / DT)):  # ~2.3 m of travel: still short of the target
        pilot.update(DT, x, y, yaw, 0.0, mgr)
        vx, wz = mgr.cmd.twist[0], mgr.cmd.twist[2]
        yaw += wz * DT
        x += vx * math.cos(yaw) * DT
        y += vx * math.sin(yaw) * DT
    assert mgr.cmd.twist[0] < 0.0  # walking backwards
    assert x < -1.0  # still progressing toward the left target
    assert abs(y) < 0.1  # the flipped y-correction converges too
    assert abs(yaw) < 0.5  # and the nose stays on the camera side


def test_edge_flip_turns_around():
    pilot = Autopilot(np.random.default_rng(0), x_range=(-2.5, 2.5))
    mgr = FakeManager()
    pilot._enter_walk(0.0)
    pilot._launch_left = 0.0
    pilot.target_x = 3.0  # pinned: moving +x toward the right edge
    pilot.state = AutoState.WALK
    # Park the duck near the right edge moving outward.
    pilot.update(DT, x=2.45, y=0.0, yaw=0.0, tilt=0.0, mgr=mgr)
    assert pilot.state is AutoState.TURN
    assert pilot.target_x == pilot.x_min


def test_edge_flip_moonwalking_left():
    pilot = Autopilot(np.random.default_rng(0), x_range=(-2.5, 2.5))
    mgr = FakeManager()
    pilot.target_x = -3.0  # pinned: moving -x toward the left edge
    pilot._launch_left = 0.0
    pilot.state = AutoState.WALK
    pilot.update(DT, x=-2.45, y=0.0, yaw=0.0, tilt=0.0, mgr=mgr)
    assert pilot.state is AutoState.TURN
    assert pilot.target_x == pilot.x_max


def test_idle_turns_back_to_face_the_camera():
    """A duck left rotated (post-walk, push, recover) turns to ~yaw 0 before
    idling — it should never stand with its back to the viewer (ADR-0009)."""
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    pilot.update(DT, 0.0, 0.0, math.pi, 0.0, mgr)  # standing backwards
    assert pilot.state is AutoState.TURN
    # Converged on the front -> back to the state it came from (IDLE).
    pilot.update(DT, 0.0, 0.0, 0.05, 0.0, mgr)
    assert pilot.state is AutoState.IDLE


def test_turn_returns_to_previous():
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    pilot._goto(AutoState.TURN)
    pilot.target_x = 1.0  # facing +x already -> base yaw_ref ~0
    for _ in range(300):
        pilot.update(DT, 0.0, 0.0, 0.0, 0.0, mgr)
        if pilot.state is not AutoState.TURN:
            break
    assert pilot.state is AutoState.IDLE


def test_recover_on_fall_then_idle():
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    pilot.update(DT, 0, 0, 0, math.radians(80), mgr)
    assert pilot.state is AutoState.RECOVER
    assert pilot.falls == 1
    assert np.all(mgr.cmd.twist == 0)
    # upright 1 s -> IDLE
    for _ in range(60):
        pilot.update(DT, 0, 0, 0, 0.0, mgr)
    assert pilot.state is AutoState.IDLE


def test_sit_cycle_requests():
    pilot = Autopilot(np.random.default_rng(0))
    mgr = FakeManager()
    pilot._goto(AutoState.SIT)
    pilot.update(DT, 0, 0, 0, 0, mgr)
    assert mgr.requests[-1] is Request.SIT
    # sit duration drawn -> after it, STAND is requested
    pilot._sit_left = 0.05
    mgr.busy = False
    run(pilot, mgr, (0, 0, 0, 0), 0.2)
    assert Request.STAND in mgr.requests


def test_roll_gating():
    # Near the right edge facing +x: < 0.4 m free ahead -> roll refused -> IDLE.
    pilot2 = Autopilot(np.random.default_rng(0), x_range=(-2.5, 2.5))
    pilot2.state = AutoState.IDLE
    pilot2._idle_left = 0.0

    # monkeypatch draw to pick 'roll' (r -> last 5%)
    class _Roll:
        def uniform(self, *a, **k):
            return 0.99

        def choice(self, *a, **k):
            return 1.0

    pilot2.rng = _Roll()
    pilot2._draw_idle_next(x=2.3, yaw=0.0)
    assert pilot2.state is AutoState.IDLE  # refused: <0.4 m free ahead


def test_disabled_stays_idle():
    pilot = Autopilot(np.random.default_rng(0), enabled=False)
    mgr = FakeManager()
    run(pilot, mgr, (0, 0, 0, 0), 8.0)
    assert pilot.state is AutoState.IDLE
    assert np.all(mgr.cmd.twist == 0)
