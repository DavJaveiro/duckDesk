"""Unit tests for the M1 headless core: no-Qt guard, SimClock, ONNX validation
and PolicyManager transition rules (docs/03 sections 8-9)."""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager
from duckdesk.policy.validate import validate_user_onnx
from duckdesk.sim.clock import MAX_STEPS_PER_TICK, SimClock
from duckdesk.sim.core import CONTROL_DT

pytestmark = pytest.mark.unit

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "duckdesk"
HEADLESS_PKGS = ("sim", "policy", "brain")


# --- no-PySide6 in the headless core (docs/08 M1 criterion 2) -----------------


@pytest.mark.parametrize("pkg", HEADLESS_PKGS)
def test_no_pyside6_imports(pkg):
    for path in sorted((SRC_ROOT / pkg).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            else:
                continue
            for mod in mods:
                assert not mod.split(".")[0].startswith("PySide"), (
                    f"{path}: import proibido '{mod}'"
                )


def test_headless_modules_importable_without_pyside():
    blocker = types.ModuleType("PySide6")
    blocker.QtCore = blocker.QtGui = blocker.QtWidgets = None
    sys.modules.setdefault("_pyside_block", blocker)
    import duckdesk.brain.commands
    import duckdesk.policy.contract
    import duckdesk.policy.manager
    import duckdesk.sim.clock
    import duckdesk.sim.core
    import duckdesk.sim.watchdog  # noqa: F401


# --- SimClock ----------------------------------------------------------------


def test_clock_accumulates_steps():
    clock = SimClock()
    assert clock.steps_due(CONTROL_DT * 2.5) == 2
    # The 0.5-step remainder carries over to the next tick.
    assert clock.steps_due(CONTROL_DT * 0.6) == 1


def test_clock_caps_backlog():
    clock = SimClock()
    assert clock.steps_due(1.0) == MAX_STEPS_PER_TICK
    # Backlog was discarded, not queued.
    assert clock.steps_due(0.0) == 0


def test_clock_pause_and_speed():
    clock = SimClock(speed=0.5)
    clock.paused = True
    assert clock.steps_due(1.0) == 0
    clock.paused = False
    # 1.0 s real at 0.5 speed = 0.5 s sim = 25 steps, capped at the backlog limit.
    assert clock.steps_due(1.0) == MAX_STEPS_PER_TICK
    assert clock.steps_due(6 * CONTROL_DT) == 3  # 0.12 s real -> 0.06 s sim


# --- validate_user_onnx -------------------------------------------------------


def test_validate_real_policy_ok():
    ok, msg = validate_user_onnx(assets.assets_dir() / "policies" / "v10" / "velstand.onnx")
    assert ok, msg


def test_validate_missing_file():
    ok, msg = validate_user_onnx("nao_existe.onnx")
    assert not ok and "ONNX" in msg


def test_validate_rejects_wrong_shape(monkeypatch):
    import onnxruntime as ort

    class _IODesc:
        def __init__(self, shape):
            self.shape = shape
            self.name = "io"

    class _FakeSession:
        def __init__(self, *a, **k):
            pass

        def get_inputs(self):
            return [_IODesc([1, 51])]  # legacy 51D contract must be refused

        def get_outputs(self):
            return [_IODesc([1, 14])]

    monkeypatch.setattr(ort, "InferenceSession", _FakeSession)
    ok, msg = validate_user_onnx("fake.onnx")
    assert not ok and "61" in msg


# --- PolicyManager transitions (docs/03 section 8) ----------------------------


@pytest.fixture(scope="module")
def policies_dir():
    return assets.assets_dir() / "policies" / "v10"


@pytest.fixture
def mgr(policies_dir):
    return PolicyManager(policies_dir)


def _cmd(vx=0.0, wz=0.0):
    return DuckCommand(twist=np.array([vx, 0.0, wz], dtype=np.float32))


def test_default_state_is_walk(mgr):
    assert mgr.active == "walk" and not mgr.seated and not mgr.busy
    assert np.all(mgr.command == 0.0)


def test_command_clipping(mgr):
    mgr.set_command(_cmd(vx=9.0, wz=-9.0))
    assert mgr.command[0] == pytest.approx(0.3)
    assert mgr.command[2] == pytest.approx(-1.5)


def test_sit_switches_policy_and_flag(mgr):
    ok, _ = mgr.request(Request.SIT)
    assert ok and mgr.active == "sitstand" and mgr.seated
    assert mgr.command[0] == pytest.approx(1.0)  # posture flag


def test_twist_ignored_while_seated(mgr):
    mgr.request(Request.SIT)
    mgr.set_command(_cmd(vx=0.2))
    assert np.all(mgr.vel_cmd == 0.0)


def test_requests_refused_while_seated(mgr):
    mgr.request(Request.SIT)
    for req in (Request.PECK, Request.ROLL, Request.KICK_L):
        ok, _ = mgr.request(req)
        assert not ok


def test_stand_refused_when_not_seated(mgr):
    ok, _ = mgr.request(Request.STAND)
    assert not ok


def test_stand_rise_returns_to_walk(mgr):
    mgr.request(Request.SIT)
    ok, _ = mgr.request(Request.STAND)
    assert ok and not mgr.seated and mgr.active == "sitstand"
    assert mgr.command[0] == pytest.approx(0.0)  # flag cleared -> rise
    mgr._advance_timers(mgr.rise_s + 0.01)
    assert mgr.active == "walk"


def test_episodic_roles_zero_command_and_return(mgr):
    mgr.set_command(_cmd(vx=0.2))
    ok, _ = mgr.request(Request.ROLL)
    assert ok and mgr.active == "roulade" and mgr.busy
    assert np.all(mgr.command == 0.0)  # constant-command episodic block
    mgr._advance_timers(mgr.durations["roulade"] + 0.01)
    assert mgr.active == "walk" and not mgr.busy


def test_one_move_at_a_time(mgr):
    mgr.request(Request.ROLL)
    ok, _ = mgr.request(Request.PECK)
    assert not ok  # busy


def test_ground_pick_phase_returns_to_walk(mgr):
    ok, _ = mgr.request(Request.PECK)
    assert ok and mgr.active == "ground_pick" and mgr.gp_active
    # Phase advances by dt/period; ends at end_phase (0.7 * 4.0 s = 2.8 s).
    for _ in range(int(2.9 / CONTROL_DT)):
        mgr._advance_timers(CONTROL_DT)
    assert mgr.active == "walk" and not mgr.gp_active


def test_ground_pick_phase_encoding(mgr):
    mgr.request(Request.PECK)
    mgr._advance_timers(CONTROL_DT)  # first tick writes phase into cmd[0:2]
    phase = mgr.gp_phase
    assert mgr.command[0] == pytest.approx(np.cos(2 * np.pi * phase))
    assert mgr.command[1] == pytest.approx(np.sin(2 * np.pi * phase))
    assert mgr.command[2] == 0.0


def test_reset_restores_walk(mgr):
    mgr.request(Request.SIT)
    ok, _ = mgr.request(Request.RESET)
    assert ok and mgr.active == "walk" and not mgr.seated and not mgr.busy


def test_delay_buffer_shape(policies_dir):
    m = PolicyManager(policies_dir, delay_lag=3)
    assert len(m.action_buffer) == 4
    m0 = PolicyManager(policies_dir, delay_lag=0)
    assert len(m0.action_buffer) == 1
