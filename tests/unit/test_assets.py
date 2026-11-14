"""M0 acceptance tests: the shipped assets load and satisfy the 61->14 contract."""

import onnxruntime as ort
import pytest

from duckdesk import assets
from duckdesk.sim.core import load_bam_model, load_mujoco_with_bam

pytestmark = pytest.mark.unit

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"
SCENE_BALL = ROBOT_DIR / "scene_ball.xml"

# The six in-scope policies (docs/03 section 8; roller + legacy alpha_* excluded).
IN_SCOPE_POLICIES = (
    "velstand.onnx",
    "alpha_sitstand.onnx",
    "alpha_ground_pick.onnx",
    "roulade.onnx",
    "ball_kick_left.onnx",
    "ball_kick_right.onnx",
)


def test_assets_match_lock_json():
    assert assets.verify_assets() == []


def test_no_part_files_or_testbench():
    robot_files = {p.name for p in ROBOT_DIR.rglob("*") if p.is_file()}
    assert not any(name.endswith(".part") for name in robot_files)
    assert not (
        assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "xl330_test_bench"
    ).exists()


def test_scene_ball_loads_via_bam_path():
    bam_model = load_bam_model(kp_fw=200.0, vin=7.4, max_current=None)
    model, _data, _ctrl, names = load_mujoco_with_bam(
        str(SCENE_BALL), bam_model, timestep=0.005, vin_drop_gain=0.1, vin_min=6.0
    )
    assert model.nu == 14
    assert len(names) == 14
    assert model.opt.timestep == pytest.approx(0.005)


@pytest.mark.parametrize("policy", IN_SCOPE_POLICIES)
def test_policy_io_contract(policy):
    session = ort.InferenceSession(str(POLICIES_DIR / policy), providers=["CPUExecutionProvider"])
    (model_in,) = session.get_inputs()
    (model_out,) = session.get_outputs()
    assert model_in.shape == [1, 61]
    assert model_out.shape == [1, 14]
