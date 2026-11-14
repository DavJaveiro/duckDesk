"""Pure functions of the 61D observation contract (docs/03 sections 3-4).

Ported from vendor/microduck_rl/scripts/infer_policy.py @ 0daab16:
  - DEFAULT_POSE          — upstream L126-141 (copied literally, float32)
  - quat_rotate_inverse   — upstream L612-617
  - build_obs             — upstream L636-682 (get_observations + helpers)
  - joint index derivation — upstream L390-395

Do not change semantics: the parity test (docs/03 section 10) proves numeric
equality with the upstream.
"""

from __future__ import annotations

import numpy as np

OBS_LEN = 61
ACTION_LEN = 14
COMMAND_LEN = 13

# Default pose used by the policy (legs flexed, standing position) — upstream
# L126-141, copied literally as float32. Do NOT use the scene's STAND keyframe:
# it carries more decimal places and the parity test catches the difference.
DEFAULT_POSE = np.array(
    [
        0.0,  # left_hip_yaw
        -0.0873,  # left_hip_roll
        -0.4579,  # left_hip_pitch
        -0.0049,  # left_knee
        0.4530,  # left_ankle
        0.3491,  # neck_pitch
        0.3491,  # head_pitch
        0.0,  # head_yaw
        0.0,  # head_roll
        0.0,  # right_hip_yaw
        0.0873,  # right_hip_roll
        0.4579,  # right_hip_pitch
        0.0049,  # right_knee
        -0.4530,  # right_ankle
    ],
    dtype=np.float32,
)


def quat_rotate_inverse(quat, vec):
    """Rotate a vector by the inverse of a quaternion [w, x, y, z] (upstream L612-617)."""
    w = quat[0]
    xyz = quat[1:4]
    t = np.cross(xyz, vec) * 2
    return vec - w * t + np.cross(xyz, t)


def actuator_joint_indices(model) -> tuple[list[int], list[int]]:
    """qpos/qvel indices of the actuated joints, derived from the actuator
    transmissions (upstream L390-395). Never hardcode joint indices."""
    joint_qpos_indices = [
        int(model.jnt_qposadr[model.actuator_trnid[i, 0]]) for i in range(model.nu)
    ]
    joint_qvel_indices = [
        int(model.jnt_dofadr[model.actuator_trnid[i, 0]]) for i in range(model.nu)
    ]
    return joint_qpos_indices, joint_qvel_indices


def raw_accelerometer(model, data, trunk_base_id, imu_accel_id) -> np.ndarray:
    """Normalized negated accelerometer, gravity fallback when near-free
    (upstream L619-634)."""
    sensor_adr = model.sensor_adr[imu_accel_id]
    accel_negated = -data.sensordata[sensor_adr : sensor_adr + 3].copy().astype(np.float32)
    mag = np.linalg.norm(accel_negated)
    if mag > 0.1:
        return accel_negated / mag
    quat = data.xquat[trunk_base_id].copy().astype(np.float32)
    world_gravity = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    return quat_rotate_inverse(quat, world_gravity)


def projected_gravity(data, trunk_base_id) -> np.ndarray:
    """Projected gravity in trunk frame (upstream L636-640)."""
    quat = data.xquat[trunk_base_id].copy().astype(np.float32)
    world_gravity = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    return quat_rotate_inverse(quat, world_gravity)


def build_obs(
    model,
    data,
    trunk_base_id,
    imu_ang_vel_id,
    joint_qpos_indices,
    joint_qvel_indices,
    default_pose,
    last_action,
    command,
    use_projected_gravity=True,
    imu_accel_id=-1,
) -> np.ndarray:
    """61D observation in the trained order (upstream L636-682).

    [0:3]   base angular velocity, sensor `imu_ang_vel`
    [3:6]   projected gravity (default) or raw accelerometer, per flag
    [6:20]  joint positions minus DEFAULT_POSE
    [20:34] joint velocities
    [34:48] last raw policy action
    [48:61] 13D command block
    """
    # get_base_ang_vel (upstream L642-645)
    sensor_adr = model.sensor_adr[imu_ang_vel_id]
    ang_vel = data.sensordata[sensor_adr : sensor_adr + 3].copy().astype(np.float32)

    if use_projected_gravity:
        gravity = projected_gravity(data, trunk_base_id)
    else:
        gravity = raw_accelerometer(model, data, trunk_base_id, imu_accel_id)

    # get_joint_pos_relative (upstream L647-650)
    joint_pos = data.qpos[joint_qpos_indices].copy().astype(np.float32) - default_pose
    # get_joint_vel (upstream L652-654)
    joint_vel = data.qvel[joint_qvel_indices].copy().astype(np.float32)

    obs = np.concatenate([ang_vel, gravity, joint_pos, joint_vel, last_action, command])
    return obs.astype(np.float32)
