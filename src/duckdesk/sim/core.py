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

import mujoco
import numpy as np
from bam.model import load_model
from bam.mujoco import MujocoController

# BAM M6 defaults — mirrors upstream L30-46.
BAM_MOTOR_NAME = "xl330"
BAM_MODEL = "m6"
BAM_KP_FW = 200.0
BAM_VIN_MIN = 6.0
BAM_MAX_CURRENT = None
# Stiff joint-friction constraint (upstream L43-46).
BAM_STIFF_SOLREF_FRICTION = (-5.0e4, -2.0e2)
BAM_STIFF_SOLIMP_FRICTION = (0.99, 0.9999, 0.001, 0.5, 2.0)


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
