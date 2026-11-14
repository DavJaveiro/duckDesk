#!/usr/bin/env python3
"""Live MuJoCo viewer for the headless core (development tool, not the app UI).

    uv run python scripts/view.py [--vx 0.2] [--wz 0.0]

The real-time loop mirrors headless_run.py: 20 ms control steps, watchdog
resets, one thread. Close the window to quit.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager
from duckdesk.sim.core import CONTROL_DT, SimCore
from duckdesk.sim.watchdog import Watchdog

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene_ball.xml"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vx", type=float, default=0.0, help="forward velocity command")
    parser.add_argument("--wz", type=float, default=0.0, help="yaw rate command")
    parser.add_argument("--speed", type=float, default=1.0, help="0.5 = slow motion")
    args = parser.parse_args()

    sim = SimCore(SCENE)
    sim.park_ball()
    manager = PolicyManager(POLICIES_DIR)
    manager.set_command(DuckCommand(twist=np.array([args.vx, 0.0, args.wz], dtype=np.float32)))
    watchdog = Watchdog()

    with mujoco.viewer.launch_passive(sim.model, sim.data) as viewer:
        viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = False
        next_step = time.perf_counter()
        while viewer.is_running():
            now = time.perf_counter()
            if now >= next_step:
                targets = manager.step(sim)
                sim.step_control(targets)
                if watchdog.check(sim, CONTROL_DT):
                    manager.request(Request.RESET, sim)
                viewer.sync()
                next_step += CONTROL_DT / max(args.speed, 1e-3)
            else:
                time.sleep(0.001)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
