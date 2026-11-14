"""Parity test (docs/03 section 10): our policy loop vs the upstream's.

Both sides run the same scene (scene_ball.xml), the same v10 policies,
new_cmd_obs=True, BAM on, vin=7.4, vin_drop_gain=0.1, manifest durations
(roulade 1.0 s, kick 0.5 s, ground_pick period 4.0 s / end 0.7).

Tolerances: obs/action atol 1e-5 every control step, qpos atol 1e-4 at the end.
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager
from duckdesk.sim.core import CONTROL_DT, DECIMATION, SimCore

pytestmark = pytest.mark.parity

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene_ball.xml"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"

OBS_ATOL = 1e-5
ACTION_ATOL = 1e-5
QPOS_ATOL = 1e-4

# Actuator delay in control steps: 0, the upstream default (ADR-0006). Both
# sides must run the same lag or the delayed-action buffers diverge.
DELAY_LAG = 0


def _make_upstream(infer_policy):
    """The upstream side: our SimCore's model/data/bam_ctrl + PolicyInference
    configured exactly as the manifest requires (durations from v10)."""
    sim = SimCore(SCENE)
    policy = infer_policy.PolicyInference(
        sim.model,
        sim.data,
        bam_ctrl=sim.bam_ctrl,
        walking_onnx_path=str(POLICIES_DIR / "velstand.onnx"),
        action_scale=1.0,
        delay_min_lag=DELAY_LAG,
        delay_max_lag=DELAY_LAG,
        use_projected_gravity=True,
        new_cmd_obs=True,
        ground_pick_onnx_path=str(POLICIES_DIR / "alpha_ground_pick.onnx"),
        ground_pick_period=4.0,
        roulade_onnx_path=str(POLICIES_DIR / "roulade.onnx"),
        roulade_duration=1.0,
        kick_left_onnx_path=str(POLICIES_DIR / "ball_kick_left.onnx"),
        kick_right_onnx_path=str(POLICIES_DIR / "ball_kick_right.onnx"),
        kick_duration=0.5,
        sitstand_onnx_path=str(POLICIES_DIR / "alpha_sitstand.onnx"),
    )
    return sim, policy


# Roteiros (docs/03 section 10): event tuples (t_start, kind, payload).
WALK_ROTEIRO = [
    (0.0, "twist", (0.0, 0.0, 0.0)),
    (2.0, "twist", (0.2, 0.0, 0.0)),
    (6.0, "twist", (0.0, 0.0, 1.0)),
    (8.0, "twist", (0.0, 0.0, 0.0)),
]
GROUND_PICK_ROTEIRO = [
    (0.0, "twist", (0.0, 0.0, 0.0)),
    (1.0, "request", "peck"),
    (6.0, "twist", (0.2, 0.0, 0.0)),
    (7.0, "twist", (0.0, 0.0, 0.0)),
]
ROULADE_ROTEIRO = [
    (0.0, "twist", (0.0, 0.0, 0.0)),
    (1.0, "request", "roll"),
    (4.0, "twist", (0.2, 0.0, 0.0)),
    (6.0, "twist", (0.0, 0.0, 0.0)),
]


def _apply_u(policy, kind, payload):
    if kind == "twist":
        policy.set_vel_cmd(*payload)
    elif payload == "peck":
        policy.trigger_ground_pick()
    else:
        policy.trigger_behavior("roulade")


def _apply_d(manager, sim, kind, payload):
    if kind == "twist":
        manager.set_command(DuckCommand(twist=np.asarray(payload, dtype=np.float32)))
    elif payload == "peck":
        manager.request(Request.PECK, sim)
    else:
        manager.request(Request.ROLL, sim)


@pytest.mark.parametrize(
    "roteiro,seconds",
    [(WALK_ROTEIRO, 10.0), (GROUND_PICK_ROTEIRO, 8.0), (ROULADE_ROTEIRO, 7.0)],
    ids=["walk", "ground_pick", "roulade"],
)
def test_parity(infer_policy, roteiro, seconds):
    sim_u, policy_u = _make_upstream(infer_policy)
    sim_d = SimCore(SCENE)
    manager = PolicyManager(POLICIES_DIR, delay_lag=DELAY_LAG)

    steps = int(seconds / CONTROL_DT)
    event_idx = 0
    max_obs_diff = 0.0
    max_action_diff = 0.0

    for step in range(steps):
        sim_time = step * CONTROL_DT
        while event_idx < len(roteiro) and roteiro[event_idx][0] <= sim_time:
            _, kind, payload = roteiro[event_idx]
            _apply_u(policy_u, kind, payload)
            _apply_d(manager, sim_d, kind, payload)
            event_idx += 1

        # Upstream loop order (L1679-1684): timers -> infer -> apply -> physics.
        policy_u.update_ground_pick_phase(CONTROL_DT)
        policy_u.update_behavior(CONTROL_DT)
        obs_u = policy_u.get_observations()
        action_u = policy_u.infer()
        policy_u.apply_action(action_u)
        for _ in range(DECIMATION):
            sim_u.bam_ctrl.update()
            mujoco.mj_step(sim_u.model, sim_u.data)

        targets_d = manager.step(sim_d)
        obs_d = manager.last_obs
        action_d = manager.last_action
        sim_d.step_control(targets_d)

        max_obs_diff = max(max_obs_diff, float(np.abs(obs_u - obs_d).max()))
        max_action_diff = max(max_action_diff, float(np.abs(action_u - action_d).max()))
        np.testing.assert_allclose(
            obs_d,
            obs_u,
            atol=OBS_ATOL,
            rtol=0,
            err_msg=f"obs diverge at step {step} ({sim_time:.2f}s)",
        )
        np.testing.assert_allclose(
            action_d,
            action_u,
            atol=ACTION_ATOL,
            rtol=0,
            err_msg=f"action diverge at step {step} ({sim_time:.2f}s)",
        )

    qpos_diff = float(np.abs(sim_u.data.qpos - sim_d.data.qpos).max())
    print(
        f"\nmax |obs diff| {max_obs_diff:.3e} | max |action diff| {max_action_diff:.3e} "
        f"| final |qpos diff| {qpos_diff:.3e}"
    )
    np.testing.assert_allclose(sim_d.data.qpos, sim_u.data.qpos, atol=QPOS_ATOL, rtol=0)
