"""Offscreen MuJoCo rendering (ADR-0004): RGB frames as numpy arrays."""

from __future__ import annotations

import mujoco
import numpy as np


class OffscreenRenderer:
    """Wraps mujoco.Renderer for headless RGB capture (MP4 evidence in reports)."""

    def __init__(self, model: mujoco.MjModel, width: int = 640, height: int = 360):
        self.renderer = mujoco.Renderer(model, height=height, width=width)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        self.camera.trackbodyid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
        self.camera.distance = 0.9
        self.camera.elevation = -20.0
        self.camera.azimuth = 160.0

    def render_rgb(self, data: mujoco.MjData) -> np.ndarray:
        self.renderer.update_scene(data, camera=self.camera)
        return self.renderer.render()  # (H, W, 3) uint8

    def close(self) -> None:
        self.renderer.close()
