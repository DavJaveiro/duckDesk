"""Mascot rendering (docs/05 sections 3 and 9): side view, alpha mask from the
trunk_base tree, rendered at final size with GL MSAA (offsamples=4) for edge
antialiasing; the binary seg mask is feathered 3x3 to approximate coverage.

True orthographic via `model.vis.global_.orthographic` renders black under
mujoco 3.10 free cameras, so we approximate with a far camera + narrow fovy
(see duvidas.md): at D=3 m the depth-related scale drift is ~2 %, invisible.
"""

from __future__ import annotations

import mujoco
import numpy as np

from duckdesk.render.offscreen import OffscreenRenderer

CAM_DISTANCE = 3.0
CAM_AZIMUTH = 270.0  # camera at -y looking +y: side view, +x to the right


class MascotRenderer:
    """Renders the duck with transparent background at the physical window size."""

    def __init__(self, model: mujoco.MjModel, size_phys_px: int):
        self.model = model
        self.renderer = OffscreenRenderer(model, size_phys_px, size_phys_px)
        self._duck_ids = np.array(
            [
                g
                for g in range(model.ngeom)
                if model.body_rootid[model.geom_bodyid[g]]
                == mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
            ]
        )
        self._fovy_saved = float(model.vis.global_.fovy)
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.azimuth = CAM_AZIMUTH
        self.cam.elevation = 0.0
        self.cam.distance = CAM_DISTANCE
        self._seg_every = 4  # alpha mask refreshed every 4th frame (cost cut, M5 CPU)
        self._frame_n = 0
        self._alpha = None

    def set_view_height(self, height_m: float) -> None:
        """fovy so the view is height_m tall at CAM_DISTANCE (05 section 3)."""
        self.model.vis.global_.fovy = np.degrees(2 * np.arctan(height_m / (2 * CAM_DISTANCE)))

    @staticmethod
    def _feather(mask: np.ndarray) -> np.ndarray:
        """3x3 box mean on a binary 0/255 mask -> coverage-like alpha."""
        m = np.pad(mask.astype(np.uint16), 1)
        acc = np.zeros(mask.shape, np.uint16)
        for dy in range(3):
            for dx in range(3):
                acc += m[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
        return (acc // 9).astype(np.uint8)

    def frame(self, data: mujoco.MjData, lookat: np.ndarray) -> np.ndarray:
        """Returns (S, S, 4) uint8 premultiplied BGRA at renderer resolution."""
        self.cam.lookat[:] = lookat
        rgb = self.renderer.render_rgb(data, camera=self.cam)
        self._frame_n += 1
        if self._alpha is None or self._frame_n % self._seg_every == 0:
            # seg pass needs its own update_scene (seg colors are assigned at
            # scene build) — amortized to every 4th frame for CPU.
            self.renderer.renderer.enable_segmentation_rendering()
            seg = self.renderer.render_rgb_segmented(data, camera=self.cam)
            self.renderer.renderer.disable_segmentation_rendering()
            geom_id = seg[:, :, 0].astype(np.int32)
            is_geom = seg[:, :, 1].astype(np.int32) == int(mujoco.mjtObj.mjOBJ_GEOM)
            mask = (is_geom & np.isin(geom_id, self._duck_ids)).astype(np.uint8) * 255
            self._alpha = self._feather(mask)
        alpha = self._alpha
        out = np.empty(rgb.shape[:2] + (4,), np.uint8)
        # premultiply BGR in uint16 to avoid overflow, then drop to uint8
        out[..., :3] = (rgb[..., ::-1].astype(np.uint16) * alpha[..., None]) // 255
        out[..., 3] = alpha
        return out
