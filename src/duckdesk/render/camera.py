"""Free / tracking camera controller (docs/04 section 2).

Wraps an ``mjvCamera``: left-drag orbits, right-drag pans, wheel zooms, double
click centers on the duck, ``C`` toggles free <-> follow (``trackbodyid =
trunk_base``). Delegates the actual math to ``mujoco.mjv_moveCamera`` like the
native viewer does.
"""

from __future__ import annotations

import enum

import mujoco


class MouseAction(enum.Enum):
    ORBIT = "orbit"  # left drag
    PAN = "pan"  # right drag
    ZOOM = "zoom"  # wheel


class CameraController:
    def __init__(self, model: mujoco.MjModel):
        self.model = model
        self.cam = mujoco.MjvCamera()
        # Scene default (docs/04 section 2): az 160 deg, el -20 deg, ~0.8 m.
        self.cam.azimuth = 160.0
        self.cam.elevation = -20.0
        self.cam.distance = 0.9
        self.trunk_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
        self.following = True
        self._apply_mode()

    def _apply_mode(self) -> None:
        if self.following:
            self.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
            self.cam.trackbodyid = self.trunk_id
        else:
            self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE

    def toggle(self) -> bool:
        self.following = not self.following
        self._apply_mode()
        return self.following

    def center_on(self, data: mujoco.MjData) -> None:
        """Double click: look at the duck and re-enter follow mode."""
        self.cam.lookat[:] = data.xpos[self.trunk_id]
        if not self.following:
            self.following = True
            self._apply_mode()

    def mouse_move(
        self,
        action: MouseAction,
        dx_px: float,
        dy_px: float,
        scene: mujoco.MjvScene,
        height_px: float,
    ) -> None:
        if self.following and action in (MouseAction.ORBIT, MouseAction.PAN):
            # Dragging while tracking drops to free mode (viewer behavior).
            self.following = False
            self._apply_mode()
        rel_x, rel_y = dx_px / max(height_px, 1), dy_px / max(height_px, 1)
        # One mjv_moveCamera call per action: it handles both axes (viewer-style).
        muj_action = {
            MouseAction.ORBIT: mujoco.mjtMouse.mjMOUSE_ROTATE_V,
            MouseAction.PAN: mujoco.mjtMouse.mjMOUSE_MOVE_V,
        }[action]
        mujoco.mjv_moveCamera(self.model, muj_action, rel_x, rel_y, scene, self.cam)

    def wheel(self, steps: float, scene: mujoco.MjvScene, height_px: float) -> None:
        # Viewer convention (simulate.cc): scroll up = positive -> zoom in.
        mujoco.mjv_moveCamera(
            self.model,
            mujoco.mjtMouse.mjMOUSE_ZOOM,
            0.0,
            steps * 0.05,
            scene,
            self.cam,
        )
