"""Shared rig for the behavior trials (docs/08 M1 acceptance items)."""

from __future__ import annotations

import numpy as np
import pytest

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager
from duckdesk.sim.core import CONTROL_DT, SimCore

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene_ball.xml"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"

FALL_TILT = np.radians(45.0)
FALL_Z = 0.055
STAND_TILT = np.radians(15.0)
STAND_Z = 0.08


class Trial:
    """One SimCore + PolicyManager pair, run control step by control step."""

    def __init__(self, seed: int = 0):
        self.sim = SimCore(SCENE)
        self.mgr = PolicyManager(POLICIES_DIR)
        self.rng = np.random.default_rng(seed)

    def command(self, vx=0.0, vy=0.0, wz=0.0, head=None, body=None):
        cmd = DuckCommand(
            twist=np.asarray([vx, vy, wz], dtype=np.float32),
            head=None if head is None else np.asarray(head, dtype=np.float32),
            body=None if body is None else np.asarray(body, dtype=np.float32),
        )
        self.mgr.set_command(cmd)

    def request(self, req: Request):
        return self.mgr.request(req, self.sim)

    def run(self, seconds: float, events=()):
        """Run the closed loop for `seconds` sim-time, applying (t, fn) events
        once their sim-time arrives. Returns a dict of per-step traces."""
        steps = round(seconds / CONTROL_DT)
        events = sorted(events, key=lambda e: e[0])
        ev_idx = 0
        log = {k: [] for k in ("time", "trunk_pos", "tilt", "vx", "yaw_rate", "ball", "role")}
        for step in range(steps):
            sim_time = step * CONTROL_DT
            while ev_idx < len(events) and events[ev_idx][0] <= sim_time:
                events[ev_idx][1](self)
                ev_idx += 1
            targets = self.mgr.step(self.sim)
            self.sim.step_control(targets)
            v_body, yaw_rate = self.sim.body_velocity()
            log["time"].append(self.sim.data.time)
            log["trunk_pos"].append(self.sim.trunk_pos())
            log["tilt"].append(self.sim.trunk_tilt())
            log["vx"].append(float(v_body[0]))
            log["yaw_rate"].append(yaw_rate)
            ball = self.sim.ball_pos()
            log["ball"].append(ball if ball is not None else np.full(3, np.nan))
            log["role"].append(self.mgr.active)
        return {k: np.asarray(v) if k != "role" else v for k, v in log.items()}

    def fallen(self) -> bool:
        return self.sim.trunk_tilt() > FALL_TILT or self.sim.trunk_pos()[2] < FALL_Z

    def standing(self) -> bool:
        return self.sim.trunk_tilt() < STAND_TILT and self.sim.trunk_pos()[2] > STAND_Z

    def push(self, fx: float, fy: float, fz: float = 0.0):
        self.sim.data.xfrc_applied[self.sim.trunk_base_id, 0:3] = [fx, fy, fz]

    def clear_push(self):
        self.sim.data.xfrc_applied[self.sim.trunk_base_id, 0:3] = 0.0

    def perturb(self, lin: float = 0.15, ang: float = 0.5):
        """Small random trunk-velocity nudge (rng-seeded per trial)."""
        adr = self.sim.trunk_qvel_adr
        self.sim.data.qvel[adr] += self.rng.uniform(-lin, lin)
        self.sim.data.qvel[adr + 1] += self.rng.uniform(-lin, lin)
        self.sim.data.qvel[adr + 5] += self.rng.uniform(-ang, ang)


@pytest.fixture
def trial_factory():
    return Trial
