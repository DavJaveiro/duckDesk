"""Unit tests for render/camera.py and settings.py (Qt-free)."""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from duckdesk import assets
from duckdesk.render.camera import CameraController, MouseAction
from duckdesk.render.offscreen import OffscreenRenderer
from duckdesk.settings import Settings
from duckdesk.sim.core import SimCore

pytestmark = pytest.mark.unit

SCENE = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck" / "scene_ball.xml"


@pytest.fixture(scope="module")
def sim():
    s = SimCore(SCENE)
    s.park_ball()
    return s


@pytest.fixture(scope="module")
def scene(sim):
    r = OffscreenRenderer(sim.model, 320, 240)
    r.render_rgb(sim.data)  # populate scene frustum before mjv_moveCamera calls
    return r.scene


@pytest.fixture
def cam(sim):
    return CameraController(sim.model)


def test_tracks_trunk_by_default(cam, sim):
    assert cam.cam.type == mujoco.mjtCamera.mjCAMERA_TRACKING
    assert cam.cam.trackbodyid == sim.trunk_base_id
    assert (cam.cam.azimuth, cam.cam.elevation) == (160.0, -20.0)


def test_orbit_changes_azimuth_and_drops_to_free(cam, scene):
    az0 = cam.cam.azimuth
    cam.mouse_move(MouseAction.ORBIT, 30, -20, scene, 300)
    assert cam.cam.azimuth != az0
    assert cam.cam.type == mujoco.mjtCamera.mjCAMERA_FREE


def test_wheel_zooms(cam, scene):
    d0 = cam.cam.distance
    cam.wheel(-2.0, scene, 300)
    assert cam.cam.distance > d0


def test_pan_moves_lookat(cam, scene):
    cam.toggle()  # free mode allows pan
    lo0 = cam.cam.lookat.copy()
    cam.mouse_move(MouseAction.PAN, 50, 0, scene, 300)
    assert not np.allclose(cam.cam.lookat, lo0)


def test_toggle_switches_tracking(cam):
    cam.toggle()
    assert cam.cam.type == mujoco.mjtCamera.mjCAMERA_FREE
    cam.toggle()
    assert cam.cam.type == mujoco.mjtCamera.mjCAMERA_TRACKING


def test_center_on_reenters_follow(cam, sim):
    cam.toggle()
    cam.cam.lookat[:] = 9.0
    cam.center_on(sim.data)
    np.testing.assert_allclose(cam.cam.lookat, sim.data.xpos[sim.trunk_base_id], atol=1e-6)
    assert cam.cam.type == mujoco.mjtCamera.mjCAMERA_TRACKING


def test_settings_roundtrip(tmp_path):
    p = tmp_path / "cfg.json"
    s = Settings(p)
    s["speed"] = 0.5
    s["window_geometry"] = "abc"
    s2 = Settings(p)
    assert s2["speed"] == 0.5 and s2["window_geometry"] == "abc"


def test_settings_corrupt_file_defaults(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text("{not json")
    s = Settings(p)
    assert s["speed"] == 1.0
