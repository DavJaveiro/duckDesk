"""PolicyManager: ONNX sessions per role, the 13D command encoder and the
one-move-at-a-time transition rules (docs/03 sections 6 and 8).

Timing and command encoding are ported from
vendor/microduck_rl/scripts/infer_policy.py @ 0daab16:
  - _update_command (13D)      — upstream L461-495
  - trigger_ground_pick/phase  — upstream L684-730
  - trigger/update behavior    — upstream L732-806
  - infer/apply_action         — upstream L857-894
  - _place_ball                — upstream L765-781 (via SimCore)

Durations and command encodings come from the v10 manifest (docs/03 section 8:
"use o manifesto"), not from infer_policy.py's CLI defaults (3.0 s / 2.0 s).

Intentional deviation (docs/03 section 8): after `sitstand_rise_s` seconds at
flag 0 we hand back to `walk` — the real robot does this (robotd control.rs);
the rehearsal script can't because it never unloads the sitstand session.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import onnxruntime as ort

from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.contract import ACTION_LEN, COMMAND_LEN, OBS_LEN, build_obs
from duckdesk.sim.core import CONTROL_DT

# Command limits for the velstand slot (docs/03 section 8 "Limites de comando").
VEL_MAX_X, VEL_MIN_X = 0.3, -0.3
VEL_MAX_Y, VEL_MIN_Y = 0.2, -0.2
VEL_MAX_ANG = 1.5
HEAD_MAX = 1.4  # head_roll is clipped further by the policy itself (~0.31)
BODY_CMD_MAX_XY = 0.02
BODY_CMD_MAX_Z = 0.03
BODY_CMD_MAX_ANGLE = math.radians(30)

ROLES = ("walk", "sitstand", "ground_pick", "roulade", "kick_left", "kick_right")
_EPISODIC_ROLES = ("ground_pick", "roulade", "kick_left", "kick_right")

REQUEST_TO_ROLE = {
    Request.PECK: "ground_pick",
    Request.ROLL: "roulade",
    Request.KICK_L: "kick_left",
    Request.KICK_R: "kick_right",
}


def _sess_opts() -> ort.SessionOptions:
    """Single-threaded ORT: the 61->14 net is tiny and its default thread pool
    spin-waits, which burned ~2 idle cores on the Qt thread's behalf (M5 CPU cap)."""
    o = ort.SessionOptions()
    o.intra_op_num_threads = 1
    o.inter_op_num_threads = 1
    return o


def _role_of(entry: dict) -> str | None:
    """Map a manifest entry to a DuckDesk role (docs/03 section 8 table)."""
    if entry.get("mode") == "roller":  # skate policies are out of scope
        return None
    if entry.get("slot") == "walk":
        return "walk"
    name = entry.get("name") or Path(entry["file"]).stem
    return name if name in ROLES else None


class PolicyManager:
    def __init__(
        self, policies_dir: str | Path, walk_onnx: str | Path | None = None, delay_lag: int = 0
    ):
        self.policies_dir = Path(policies_dir)
        manifest = json.loads((self.policies_dir / "manifest.json").read_text(encoding="utf-8"))
        self.manifest = manifest

        self.sessions: dict[str, ort.InferenceSession] = {}
        self.io_names: dict[str, tuple[str, str]] = {}
        self.action_scales: dict[str, float] = {}
        self.entries: dict[str, dict] = {}
        for entry in manifest.get("policies", []):
            role = _role_of(entry)
            if role is None or role in self.sessions:
                continue
            path = self.policies_dir / entry["file"]
            session = ort.InferenceSession(
                str(path), sess_options=_sess_opts(), providers=["CPUExecutionProvider"]
            )
            self._check_io_contract(entry["file"], session)
            self.sessions[role] = session
            self.io_names[role] = (
                session.get_inputs()[0].name,
                session.get_outputs()[0].name,
            )
            self.action_scales[role] = float(entry.get("action_scale", 1.0))
            self.entries[role] = entry

        missing = [
            role for role in ("walk", "sitstand", "ground_pick") if role not in self.sessions
        ]
        if missing:
            raise ValueError(f"manifest v10 sem as politicas necessarias: {missing}")

        if walk_onnx is not None:
            session = ort.InferenceSession(
                str(walk_onnx), sess_options=_sess_opts(), providers=["CPUExecutionProvider"]
            )
            self._check_io_contract(Path(walk_onnx).name, session)
            self.sessions["walk"] = session
            self.io_names["walk"] = (
                session.get_inputs()[0].name,
                session.get_outputs()[0].name,
            )
            self.action_scales["walk"] = 1.0
            self.entries["walk"] = dict(self.entries.get("walk", {}), file=str(walk_onnx))

        # Timing parameters from the manifest (docs/03 section 8).
        gp_cmd = self.entries["ground_pick"].get("command", {})
        self.gp_period = float(gp_cmd.get("period_s", 4.0))
        self.gp_end_phase = float(gp_cmd.get("end_phase", 0.7))
        self.rise_s = float(self.entries["sitstand"].get("unwind_s", 1.0))  # sitstand_rise_s
        self.durations = {
            role: float(self.entries[role].get("duration_s", 1.0))
            for role in ("roulade", "kick_left", "kick_right")
            if role in self.entries
        }

        # Active policy and runtime state.
        self.active = "walk"
        self.seated = False
        self.gp_active = False
        self.gp_phase = 0.0
        self.behavior_left = 0.0  # > 0 while an episodic role runs (not ground_pick)
        self.rise_left = 0.0  # > 0 while standing back up on the sitstand policy

        self.last_action = np.zeros(ACTION_LEN, dtype=np.float32)
        self.vel_cmd = np.zeros(3, dtype=np.float32)
        self.head_cmd = np.zeros(4, dtype=np.float32)
        self.body_cmd = np.zeros(6, dtype=np.float32)
        self.command = np.zeros(COMMAND_LEN, dtype=np.float32)
        self.last_obs: np.ndarray | None = None

        # Actuator delay ring buffer (upstream L446-459, L866-883), in CONTROL
        # steps. Default 0 = upstream infer_policy.py default (docs/03 section 5).
        # Measured in ADR-0006: lag 0 recovers from falls 5/5 and walks 0.11 m/s
        # at vx=0.3; lag 1 (20 ms) walks 0.15 but re-falls 2/5; lag 3 (60 ms, the
        # old default) is outside the 15-30 ms training DR (3..6 physics steps).
        self.delay_lag = delay_lag
        self.action_buffer = [np.zeros(ACTION_LEN, dtype=np.float32) for _ in range(delay_lag + 1)]
        self.buffer_index = 0
        self.walk_policy_name = "velstand.onnx"
        self._update_command()

    @staticmethod
    def _check_io_contract(name: str, session: ort.InferenceSession) -> None:
        in_shape = session.get_inputs()[0].shape
        out_shape = session.get_outputs()[0].shape
        if in_shape[-1] != OBS_LEN or out_shape[-1] != ACTION_LEN:
            raise ValueError(
                f"politica '{name}' fora do contrato 61->14: entrada {in_shape}, saida {out_shape}"
            )

    def load_walk_policy(self, path: str | Path) -> None:
        """Swap the walk-slot ONNX (docs/04 section 5). Assumes the caller ran
        validate_user_onnx first."""
        session = ort.InferenceSession(
            str(path), sess_options=_sess_opts(), providers=["CPUExecutionProvider"]
        )
        self._check_io_contract(Path(path).name, session)
        self.sessions["walk"] = session
        self.io_names["walk"] = (
            session.get_inputs()[0].name,
            session.get_outputs()[0].name,
        )
        self.walk_policy_name = Path(path).name

    @property
    def session(self) -> ort.InferenceSession:
        return self.sessions[self.active]

    @property
    def busy(self) -> bool:
        """An episodic behavior or the sitstand rise is running (docs/03 §8)."""
        return self.gp_active or self.behavior_left > 0 or self.rise_left > 0

    # --- commands -----------------------------------------------------------

    def set_command(self, cmd: DuckCommand) -> None:
        """Store a clipped command (docs/03 section 8 limits)."""
        vx = float(np.clip(cmd.twist[0], VEL_MIN_X, VEL_MAX_X))
        vy = float(np.clip(cmd.twist[1], VEL_MIN_Y, VEL_MAX_Y))
        wz = float(np.clip(cmd.twist[2], -VEL_MAX_ANG, VEL_MAX_ANG))
        # Seated ducks ignore twist commands (docs/03 section 8).
        self.vel_cmd = (
            np.zeros(3, dtype=np.float32)
            if self.seated
            else np.array([vx, vy, wz], dtype=np.float32)
        )
        head = np.zeros(4, dtype=np.float32) if cmd.head is None else cmd.head
        body = np.zeros(6, dtype=np.float32) if cmd.body is None else cmd.body
        self.head_cmd = np.clip(np.asarray(head, dtype=np.float32), -HEAD_MAX, HEAD_MAX)
        self.body_cmd = np.asarray(body, dtype=np.float32).copy()
        self.body_cmd[0:2] = np.clip(self.body_cmd[0:2], -BODY_CMD_MAX_XY, BODY_CMD_MAX_XY)
        self.body_cmd[2] = np.clip(self.body_cmd[2], -BODY_CMD_MAX_Z, BODY_CMD_MAX_Z)
        self.body_cmd[3:6] = np.clip(self.body_cmd[3:6], -BODY_CMD_MAX_ANGLE, BODY_CMD_MAX_ANGLE)
        self._update_command()

    def _update_command(self) -> None:
        """Assemble the 13D command block (upstream L461-495).

        Episodic zero-command roles get an all-zero block; ground_pick keeps
        head/body and its phase encoding is written by _advance_timers.
        """
        if self.active in ("roulade", "kick_left", "kick_right"):
            self.command = np.zeros(COMMAND_LEN, dtype=np.float32)
            return
        cmd = np.zeros(COMMAND_LEN, dtype=np.float32)
        if self.active == "walk":
            cmd[0:3] = self.vel_cmd
        elif self.active == "sitstand":
            cmd[0] = 1.0 if self.seated else 0.0  # posture flag (manifest command.slot)
        cmd[3:7] = self.head_cmd
        cmd[7:13] = self.body_cmd
        self.command = cmd

    # --- requests (the single place that accepts/refuses, docs/03 section 8) --

    def request(self, req: Request, sim=None) -> tuple[bool, str]:
        """Return (accepted, reason_pt). RESET is handled here too."""
        if req is Request.RESET:
            if sim is not None:
                sim.reset()
            self.reset_state()
            return True, "reiniciado"

        if req is Request.STAND:
            if not self.seated:
                return False, "o pato ja esta em pe"
            # Stay on the sitstand session at flag 0; hand back to walk after rise_s.
            self.seated = False
            self.rise_left = self.rise_s
            self._update_command()
            return True, "levantando"

        if self.seated:
            return False, "levante o pato primeiro"
        if self.busy:
            return False, "termine o movimento atual primeiro"

        if req is Request.SIT:
            self.seated = True
            self.active = "sitstand"
            self.vel_cmd = np.zeros(3, dtype=np.float32)
            self._update_command()
            return True, "sentando"

        if req in REQUEST_TO_ROLE:
            role = REQUEST_TO_ROLE[req]
            if role == "ground_pick":
                self.gp_active = True
                self.gp_phase = 0.0
            else:
                if role not in self.sessions:
                    return False, f"politica {role} nao carregada"
                if role in ("kick_left", "kick_right") and sim is not None:
                    sim.place_ball_for_kick(role.split("_")[1])
                self.behavior_left = self.durations.get(role, 1.0)
            self.active = role
            self.vel_cmd = np.zeros(3, dtype=np.float32)
            self._update_command()
            return True, "executando"

        return False, "pedido desconhecido"

    def reset_state(self) -> None:
        """Back to walk with zeroed command (docs/03 section 7)."""
        self.active = "walk"
        self.seated = False
        self.gp_active = False
        self.behavior_left = 0.0
        self.rise_left = 0.0
        self.last_action = np.zeros(ACTION_LEN, dtype=np.float32)
        self.vel_cmd = np.zeros(3, dtype=np.float32)
        self.head_cmd = np.zeros(4, dtype=np.float32)
        self.body_cmd = np.zeros(6, dtype=np.float32)
        for buf in self.action_buffer:
            buf[:] = 0.0
        self.buffer_index = 0
        self._update_command()

    # --- timers (upstream L1679-1680 ordering) -------------------------------

    def _advance_timers(self, dt: float) -> None:
        if self.gp_active:
            # upstream L717-730
            new_phase = self.gp_phase + dt / self.gp_period
            if new_phase >= self.gp_end_phase:
                self._end_ground_pick()
            else:
                self.gp_phase = new_phase
                self.command[0] = np.cos(2 * np.pi * self.gp_phase)
                self.command[1] = np.sin(2 * np.pi * self.gp_phase)
                self.command[2] = 0.0
        if self.behavior_left > 0:
            # upstream L783-789
            self.behavior_left -= dt
            if self.behavior_left <= 0.0:
                self._end_episode()
        if self.rise_left > 0:
            self.rise_left -= dt
            if self.rise_left <= 0.0:
                self._end_episode()

    def _end_ground_pick(self) -> None:
        self.gp_active = False
        self.vel_cmd = np.zeros(3, dtype=np.float32)
        self.active = "walk"
        self._update_command()

    def _end_episode(self) -> None:
        self.behavior_left = 0.0
        self.rise_left = 0.0
        self.vel_cmd = np.zeros(3, dtype=np.float32)
        self.active = "walk"
        self._update_command()

    # --- one control step (upstream L1679-1684 + L857-883) --------------------

    def step(self, sim, dt: float = CONTROL_DT) -> np.ndarray:
        """Advance timers, build obs, run the active ONNX, return the 14 motor
        targets (default_pose + action * action_scale)."""
        self._advance_timers(dt)
        obs = build_obs(
            sim.model,
            sim.data,
            sim.trunk_base_id,
            sim.imu_ang_vel_id,
            sim.joint_qpos_indices,
            sim.joint_qvel_indices,
            sim.default_pose,
            self.last_action,
            self.command,
            use_projected_gravity=sim.use_projected_gravity,
            imu_accel_id=sim.imu_accel_id,
        )
        self.last_obs = obs
        input_name, output_name = self.io_names[self.active]
        action = self.session.run([output_name], {input_name: obs.reshape(1, -1)})[0]
        action = action.squeeze(0).astype(np.float32)
        self.last_action = action.copy()
        # Delayed application (upstream L868-873): the obs sees the raw action,
        # the motors chase the one from delay_lag steps ago.
        if self.delay_lag > 0:
            self.action_buffer[self.buffer_index] = action
            delayed_index = (self.buffer_index - self.delay_lag) % len(self.action_buffer)
            delayed_action = self.action_buffer[delayed_index]
            self.buffer_index = (self.buffer_index + 1) % len(self.action_buffer)
        else:
            delayed_action = action
        return sim.default_pose + delayed_action * self.action_scales[self.active]
