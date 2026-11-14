"""MuJoCo scene loading with the BAM actuator model.

Ported from vendor/microduck_rl/scripts/infer_policy.py @ 0daab16:
  - load_bam_model          — upstream L49-56
  - load_mujoco_with_bam    — upstream L59-105
  - BAM constants           — upstream L30-46

Do not change semantics: the parity test (docs/03 section 10) proves numeric
equality with the upstream. Deviations must be recorded in
docs/relatorios/duvidas.md.

Note (duvidas.md): upstream calls MujocoController(vin_drop_gain=...) because its
uv.lock pins bam@62bd8ce. Our pinned bam@57d13ea renamed the parameter to
vin_drop_resistance (Rhoban/bam@e4bf1aa): the drop is now R * (sum|tau| / kt).
We keep the upstream signature and translate with R = gain * kt, which yields
the identical voltage sag.
"""

from __future__ import annotations

import math
from pathlib import Path

import mujoco
import numpy as np
from bam.model import load_model
from bam.mujoco import MujocoController

from duckdesk.policy.contract import DEFAULT_POSE, actuator_joint_indices, quat_rotate_inverse

# BAM M6 defaults — mirrors upstream L30-46.
BAM_MOTOR_NAME = "xl330"
BAM_MODEL = "m6"
BAM_KP_FW = 200.0
BAM_VIN_MIN = 6.0
BAM_MAX_CURRENT = None
# Stiff joint-friction constraint (upstream L43-46).
BAM_STIFF_SOLREF_FRICTION = (-5.0e4, -2.0e2)
BAM_STIFF_SOLIMP_FRICTION = (0.99, 0.9999, 0.001, 0.5, 2.0)

# Physics step and control decimation (upstream L1281-1285, L1432-1434).
SIM_TIMESTEP = 0.005  # 200 Hz
DECIMATION = 4  # 4 physics steps per control step -> 50 Hz
CONTROL_DT = SIM_TIMESTEP * DECIMATION

# Reset trunk height (upstream L1380).
TRUNK_RESET_Z = 0.125

# Ball placement for kick behaviors (upstream L113-117).
BALL_OFFSET_X = 0.09
BALL_OFFSET_ABS_Y = 0.042
BALL_RADIUS = 0.035


def load_bam_model(kp_fw: float, vin: float, max_current):
    """Build the BAM M6 model + XL330 voltage-controlled actuator (upstream L49-56)."""
    bam_model = load_model(motor_name=BAM_MOTOR_NAME, model=BAM_MODEL)
    bam_model.actuator.kp = kp_fw
    bam_model.actuator.vin = vin
    bam_model.actuator.max_current = max_current if (max_current and max_current > 0) else None
    return bam_model


def load_mujoco_with_bam(xml_path: str, bam_model, timestep: float, vin_drop_gain, vin_min):
    """Load the scene and hand every non-passive actuator to bam.mujoco.MujocoController.

    Mirrors upstream L59-105, which mirrors bam.mjlab.BamActuator.edit_spec:
    position actuators -> torque motors with the voltage-bounded forcerange,
    joint damping/frictionloss zeroed, stiff friction constraint. Armature is
    set on the dofs by MujocoController.
    Returns (model, data, bam_ctrl, actuator_names).
    """
    kt = bam_model.kt.value
    R = bam_model.R.value
    force_limit = bam_model.actuator.vin * kt / R
    # bam@57d13ea API: vin_drop_resistance [Ohm] replaces vin_drop_gain [V/(N*m)].
    # Upstream: V_drop = gain * sum|tau|; bam: V_drop = R * sum|tau| / kt.
    # R = gain * kt makes them identical (see module docstring / duvidas.md).
    vin_drop_resistance = None if vin_drop_gain is None else vin_drop_gain * kt

    spec = mujoco.MjSpec.from_file(xml_path)
    names = []
    for act in spec.actuators:
        tgt = act.target
        tgt_name = tgt.name if hasattr(tgt, "name") else str(tgt)
        if tgt_name.startswith("passive_"):
            continue
        act.set_to_motor()
        act.forcelimited = True
        act.forcerange = (-force_limit, force_limit)
        act.ctrllimited = False
        act.gear = [1.0, 0, 0, 0, 0, 0]
        names.append(act.name)
        for joint in spec.joints:
            if joint.name == tgt_name:
                joint.damping = np.zeros((3, 1))  # MjsJoint expects a (3,1) array
                joint.frictionloss = 0.0
                joint.solref_friction = BAM_STIFF_SOLREF_FRICTION
                joint.solimp_friction = BAM_STIFF_SOLIMP_FRICTION
                break

    model = spec.compile()
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    bam_ctrl = MujocoController(
        bam_model,
        names,
        model,
        data,
        vin_drop_resistance=vin_drop_resistance,
        vin_min=vin_min,
    )
    return model, data, bam_ctrl, names


class SimCore:
    """One MjModel/MjData pair with the BAM actuator, plus the scene state the
    policies and views need (ball, trunk ids).

    reset()/step_control() are ports of upstream L1375-1387 and L1770-1777.
    """

    def __init__(
        self,
        xml_path: str | Path,
        *,
        vin: float = 7.4,
        vin_drop_gain: float = 0.1,
        vin_min: float = BAM_VIN_MIN,
        kp_fw: float = BAM_KP_FW,
        max_current=None,
    ):
        bam_model = load_bam_model(kp_fw, vin, max_current)
        self.bam_model = bam_model
        self.model, self.data, self.bam_ctrl, self.actuator_names = load_mujoco_with_bam(
            str(xml_path), bam_model, SIM_TIMESTEP, vin_drop_gain, vin_min
        )
        self.n_actuators = self.model.nu

        # Sensor/body/joint ids (upstream L364-377).
        self.imu_ang_vel_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SENSOR, "imu_ang_vel"
        )
        self.imu_accel_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, "imu_accel")
        self.trunk_base_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
        # docs/03 §4 pins projected gravity; raw accelerometer kept as the
        # upstream's --raw-accelerometer option (see duvidas.md).
        self.use_projected_gravity = True
        trunk_jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
        self.trunk_qpos_adr = int(self.model.jnt_qposadr[trunk_jid])
        self.trunk_qvel_adr = int(self.model.jnt_dofadr[trunk_jid])
        ball_jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")
        if ball_jid >= 0:
            self.ball_qpos_adr = int(self.model.jnt_qposadr[ball_jid])
            self.ball_qvel_adr = int(self.model.jnt_dofadr[ball_jid])
        else:
            self.ball_qpos_adr = None
            self.ball_qvel_adr = None

        # Actuated-joint qpos/qvel indices from the transmissions (upstream L390-395).
        self.joint_qpos_indices, self.joint_qvel_indices = actuator_joint_indices(self.model)
        self.default_pose = DEFAULT_POSE[: self.n_actuators]

        self.reset()

    def reset(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        """Initial state (upstream L1375-1387): trunk at (x, y, 0.125) with a
        yaw-only quaternion, joints at DEFAULT_POSE, velocities zeroed."""
        data = self.data
        adr = self.trunk_qpos_adr
        data.qpos[adr + 0] = x
        data.qpos[adr + 1] = y
        data.qpos[adr + 2] = TRUNK_RESET_Z
        data.qpos[adr + 3 : adr + 7] = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
        for i, qpos_idx in enumerate(self.joint_qpos_indices):
            data.qpos[qpos_idx] = self.default_pose[i]
        data.qvel[:] = 0.0
        data.ctrl[:] = 0.0
        data.xfrc_applied[:] = 0.0
        # Pinned bam has no MujocoController.reset (upstream L1385 calls it);
        # its per-step state is only last_ts and q_target — sync them here.
        self.bam_ctrl.last_ts = data.time
        self.bam_ctrl.q_target[:] = self.default_pose
        mujoco.mj_forward(self.model, data)

    def step_control(self, targets: np.ndarray) -> None:
        """One 50 Hz control step: write motor targets, then DECIMATION physics
        steps of (bam.update + mj_step) — upstream L1770-1777 and L885-894."""
        self.bam_ctrl.q_target[:] = targets
        for _ in range(DECIMATION):
            self.bam_ctrl.update()
            mujoco.mj_step(self.model, self.data)

    def place_ball_for_kick(self, foot: str) -> None:
        """Teleport the ball in front of the kicking foot, in the robot's yaw
        frame — upstream L765-781 (reset_ball_in_front_of_foot in training)."""
        if self.ball_qpos_adr is None:
            return
        adr = self.trunk_qpos_adr
        x = float(self.data.qpos[adr])
        y = float(self.data.qpos[adr + 1])
        qw, qx, qy, qz = self.data.qpos[adr + 3 : adr + 7]
        yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        off_y = -BALL_OFFSET_ABS_Y if foot == "right" else BALL_OFFSET_ABS_Y
        bx = x + math.cos(yaw) * BALL_OFFSET_X - math.sin(yaw) * off_y
        by = y + math.sin(yaw) * BALL_OFFSET_X + math.cos(yaw) * off_y
        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 7] = [
            bx,
            by,
            BALL_RADIUS,
            1,
            0,
            0,
            0,
        ]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 6] = 0.0

    def park_ball(self, x: float = 10.0, y: float = 10.0) -> None:
        """Park the ball far away and still (mascot mode keeps the same scene)."""
        if self.ball_qpos_adr is None:
            return
        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 7] = [
            x,
            y,
            BALL_RADIUS,
            1,
            0,
            0,
            0,
        ]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 6] = 0.0

    def snapshot(self) -> dict:
        """Copy of (qpos, qvel, time) for rendering/metrics outside the step."""
        return {
            "time": float(self.data.time),
            "qpos": self.data.qpos.copy(),
            "qvel": self.data.qvel.copy(),
        }

    # --- state helpers used by the watchdog and the trials ------------------

    def trunk_pos(self) -> np.ndarray:
        return self.data.qpos[self.trunk_qpos_adr : self.trunk_qpos_adr + 3].copy()

    def trunk_quat(self) -> np.ndarray:
        return self.data.qpos[self.trunk_qpos_adr + 3 : self.trunk_qpos_adr + 7].copy()

    def trunk_tilt(self) -> float:
        """Angle between the trunk z-axis and world +z, in radians."""
        _qw, qx, qy, _qz = self.trunk_quat()
        z_world_z = 1.0 - 2.0 * (qx * qx + qy * qy)
        return math.acos(max(-1.0, min(1.0, z_world_z)))

    def trunk_yaw(self) -> float:
        """World yaw of the trunk x-axis, in radians (-pi, pi]."""
        qw, qx, qy, qz = self.trunk_quat()
        siny = 2.0 * (qw * qz + qx * qy)
        cosy = 1.0 - 2.0 * (qy * qy + qz * qz)
        return math.atan2(siny, cosy)

    def body_velocity(self) -> tuple[np.ndarray, float]:
        """Body-frame linear velocity and yaw rate (upstream L1698-1706)."""
        quat = self.trunk_quat().astype(np.float32)
        v_world = self.data.qvel[self.trunk_qvel_adr : self.trunk_qvel_adr + 3].astype(np.float32)
        v_body = quat_rotate_inverse(quat, v_world)
        yaw_rate = float(self.data.qvel[self.trunk_qvel_adr + 5])
        return v_body, yaw_rate

    def ball_pos(self) -> np.ndarray | None:
        if self.ball_qpos_adr is None:
            return None
        return self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3].copy()
