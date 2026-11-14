"""Offscreen MuJoCo rendering (ADR-0004): frames as numpy arrays for both the
Qt viewport (RGB -> QImage) and MP4 evidence in reports."""

from __future__ import annotations

import mujoco
import numpy as np

MAX_W, MAX_H = 1920, 1080  # docs/02 "Renderização": viewport capped


class OffscreenRenderer:
    """Wraps mujoco.Renderer; the caller supplies the camera each frame."""

    def __init__(self, model: mujoco.MjModel, width: int = 640, height: int = 360):
        self.renderer = mujoco.Renderer(model, height=height, width=width)
        self.option = mujoco.MjvOption()
        # Default tracking camera for callers that don't pass one (scripts).
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        self.camera.trackbodyid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
        self.camera.distance = 0.9
        self.camera.elevation = -20.0
        self.camera.azimuth = 160.0

    @property
    def scene(self) -> mujoco.MjvScene:
        return self.renderer.scene

    def set_size(self, width: int, height: int) -> None:
        width = min(int(width), MAX_W)
        height = min(int(height), MAX_H)
        if width == self.renderer.width and height == self.renderer.height:
            return
        self.renderer.close()
        self.renderer = mujoco.Renderer(self.renderer.model, height=height, width=width)

    def render_rgb(self, data: mujoco.MjData, camera=None) -> np.ndarray:
        self.renderer.update_scene(data, camera=camera or self.camera, scene_option=self.option)
        return self.renderer.render()  # (H, W, 3) uint8

    def render_rgb_segmented(self, data: mujoco.MjData, camera=None) -> np.ndarray:
        """Segmentation mask (geom ids) — used by the mascot alpha cut (05 §9)."""
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SEGMENT] = True
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_IDCOLOR] = False
        self.renderer.update_scene(data, camera=camera or self.camera, scene_option=self.option)
        frame = self.renderer.render()
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SEGMENT] = False
        return frame

    def close(self) -> None:
        self.renderer.close()
