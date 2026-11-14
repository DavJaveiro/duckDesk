"""Mascot rendering (docs/05 sections 3 and 9, ADR-0007).

- True orthographic free camera. For an orthographic camera MuJoCo reads
  ``vis.global_.fovy`` as the visible HEIGHT IN METERS, not an angle; giving it
  degrees is what produced black frames before.
- 3/4 view (azimuth 140, elevation -10): both legs, the head and the eye read
  as the real robot; a pure profile hid one leg behind the other.
- Only the duck is drawn: geom group 2 (visual meshes) on, everything else off
  (floor and ball live in group 0), no skybox/haze/fog. Alpha comes from the
  depth buffer of the SAME frame, so the silhouette never lags the image.
- 2x supersampling with GL MSAA off: hard samples at 2S, box-filtered to S
  in integer math -> clean, halo-free edges.
"""

from __future__ import annotations

import math

import mujoco
import numpy as np

CAM_AZIMUTH = 140.0  # deg; camera in front-left of a duck facing +x
CAM_ELEVATION = -10.0  # deg; slightly from above, feet still read as on the line
CAM_DISTANCE = 1.0  # m; irrelevant for ortho framing, only clipping
VISUAL_GROUP = 2  # onshape-to-robot puts visual meshes in group 2


def camera_axes(azimuth_deg: float = CAM_AZIMUTH, elevation_deg: float = CAM_ELEVATION):
    """(forward, right, up) unit vectors of MuJoCo's free camera, world frame."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    fwd = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    right = np.array([math.sin(az), -math.cos(az), 0.0])
    up = np.cross(right, fwd)
    return fwd, right, up / np.linalg.norm(up)


def _duck_geoms(model: mujoco.MjModel) -> np.ndarray:
    trunk = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    return np.array(
        [
            g
            for g in range(model.ngeom)
            if model.body_rootid[model.geom_bodyid[g]] == trunk
            and model.geom_group[g] == VISUAL_GROUP
        ],
        dtype=int,
    )


def duck_screen_height_m(model: mujoco.MjModel, qpos: np.ndarray) -> float:
    """Height of the standing duck as the mascot camera sees it: from the ground
    point under the trunk up to the highest mesh vertex, along the camera up
    axis. Uses a scratch MjData so the live simulation is untouched."""
    data = mujoco.MjData(model)
    data.qpos[:] = qpos
    mujoco.mj_kinematics(model, data)
    _, _, up = camera_axes()
    trunk = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    ground = np.array([data.xpos[trunk][0], data.xpos[trunk][1], 0.0])
    top = 0.0
    for g in _duck_geoms(model):
        rot = data.geom_xmat[g].reshape(3, 3)
        mesh = model.geom_dataid[g]
        if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and mesh >= 0:
            a, n = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            pts = data.geom_xpos[g] + model.mesh_vert[a : a + n] @ rot.T
        else:  # primitive: use its bounding box corners
            ctr, half = model.geom_aabb[g, :3], model.geom_aabb[g, 3:]
            corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
            pts = data.geom_xpos[g] + (ctr + corners * half) @ rot.T
        top = max(top, float(((pts - ground) @ up).max()))
    return top


class MascotRenderer:
    """Renders the duck with a transparent background at the window size."""

    def __init__(self, model: mujoco.MjModel, size_phys_px: int):
        self.model = model
        self.S = int(size_phys_px)
        ss = 2 * self.S
        # Hard samples: our own 2x box filter does the antialiasing. The
        # offscreen context reads offsamples at creation, so set it just for
        # this renderer and restore it for the simulator view.
        saved_samples = int(model.vis.quality.offsamples)
        model.vis.quality.offsamples = 0
        try:
            self.renderer = mujoco.Renderer(model, height=ss, width=ss)
        finally:
            model.vis.quality.offsamples = saved_samples
        flags = self.renderer.scene.flags
        flags[mujoco.mjtRndFlag.mjRND_SKYBOX] = 0
        flags[mujoco.mjtRndFlag.mjRND_FOG] = 0
        flags[mujoco.mjtRndFlag.mjRND_HAZE] = 0
        flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
        flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0

        self.option = mujoco.MjvOption()
        self.option.geomgroup[:] = 0
        self.option.geomgroup[VISUAL_GROUP] = 1

        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.azimuth = CAM_AZIMUTH
        self.cam.elevation = CAM_ELEVATION
        self.cam.distance = CAM_DISTANCE
        _, self.right, self.up = camera_axes()
        self.view_h = 0.4
        # Depth of an empty pixel = far plane (Renderer linearizes the buffer).
        self._far = float(model.vis.map.zfar * model.stat.extent)

    def set_view_height(self, height_m: float) -> None:
        self.view_h = float(height_m)

    def frame(self, data: mujoco.MjData, lookat: np.ndarray) -> np.ndarray:
        """(S, S, 4) uint8 premultiplied BGRA (QImage ARGB32_Premultiplied)."""
        g = self.model.vis.global_
        saved = (int(g.orthographic), float(g.fovy))
        g.orthographic, g.fovy = 1, self.view_h
        try:
            self.cam.lookat[:] = lookat
            r = self.renderer
            r.update_scene(data, camera=self.cam, scene_option=self.option)
            rgb = r.render()
            r.enable_depth_rendering()
            depth = r.render()  # same scene, depth readback
            r.disable_depth_rendering()
        finally:
            g.orthographic, g.fovy = saved

        return self._compose(rgb, depth < self._far * 0.999)

    def _compose(self, rgb: np.ndarray, cover: np.ndarray) -> np.ndarray:
        """2x box filter of the covered samples -> premultiplied BGRA.

        Only the duck's bounding box (on even sample boundaries) is processed;
        the duck fills ~15 % of the window, so this is most of the speed-up.
        """
        out = np.zeros((self.S, self.S, 4), np.uint8)
        rows = np.flatnonzero(cover.any(axis=1))
        if rows.size == 0:
            return out
        cols = np.flatnonzero(cover.any(axis=0))
        r0, r1 = rows[0] & ~1, (rows[-1] + 2) & ~1
        c0, c1 = cols[0] & ~1, (cols[-1] + 2) & ~1
        cov = cover[r0:r1, c0:c1]
        col = rgb[r0:r1, c0:c1].astype(np.uint16)
        col[~cov] = 0
        cov16 = cov.astype(np.uint16)
        # sum of the 4 samples of each output pixel, via strided views
        c4 = col[0::2, 0::2] + col[1::2, 0::2] + col[0::2, 1::2] + col[1::2, 1::2]
        a4 = cov16[0::2, 0::2] + cov16[1::2, 0::2] + cov16[0::2, 1::2] + cov16[1::2, 1::2]
        sub = out[r0 // 2 : r1 // 2, c0 // 2 : c1 // 2]
        sub[..., 0] = c4[..., 2] >> 2  # B (premultiplied: mean of 4 samples)
        sub[..., 1] = c4[..., 1] >> 2  # G
        sub[..., 2] = c4[..., 0] >> 2  # R
        sub[..., 3] = (a4 * 255 + 2) >> 2  # A
        return out

    def close(self) -> None:
        self.renderer.close()
