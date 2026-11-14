"""Exhaustive rules matrix: every manager state x every Request (docs/03
section 8 — "one move at a time, and none from the seat").

States: standing-free, seated, rising (post-STAND), busy-episodic (each role).
RESET is always accepted; STAND only while seated; every other request needs a
standing, idle duck.
"""

from __future__ import annotations

import numpy as np
import pytest

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager

pytestmark = pytest.mark.unit

POLICIES = assets.assets_dir() / "policies" / "v10"
BEHAVIOR_REQUESTS = (Request.SIT, Request.PECK, Request.ROLL, Request.KICK_L, Request.KICK_R)


@pytest.fixture(scope="module")
def fresh_manager():
    return PolicyManager(POLICIES)


def mk(fresh_manager):
    """Deep-ish reset without reloading ONNX sessions."""
    fresh_manager.request(Request.RESET)
    return fresh_manager


# --- standing & free -----------------------------------------------------------


def test_free_accepts_all_behaviors(fresh_manager):
    for req in BEHAVIOR_REQUESTS:
        mgr = mk(fresh_manager)
        ok, _ = mgr.request(req)
        assert ok, f"{req} recusado em pe/livre"


# --- seated ---------------------------------------------------------------------


def test_seated_accepts_only_stand(fresh_manager):
    mgr = mk(fresh_manager)
    mgr.request(Request.SIT)
    for req in BEHAVIOR_REQUESTS:
        ok, _ = mgr.request(req)
        assert not ok, f"{req} aceito sentado"
    ok, _ = mgr.request(Request.STAND)
    assert ok


def test_seated_twist_ignored(fresh_manager):
    mgr = mk(fresh_manager)
    mgr.request(Request.SIT)
    mgr.set_command(DuckCommand(twist=np.array([0.2, 0.1, 0.5], dtype=np.float32)))
    assert np.all(mgr.vel_cmd == 0.0)
    assert mgr.command[0] == pytest.approx(1.0)  # posture flag, not twist
    assert np.all(mgr.command[1:3] == 0.0)


# --- rising (post-STAND, still on sitstand) --------------------------------------


def test_rising_refuses_behaviors(fresh_manager):
    mgr = mk(fresh_manager)
    mgr.request(Request.SIT)
    mgr.request(Request.STAND)
    assert mgr.busy  # rise in progress
    for req in BEHAVIOR_REQUESTS:
        ok, _ = mgr.request(req)
        assert not ok, f"{req} aceito durante a subida"


def test_stand_refused_when_standing_or_rising(fresh_manager):
    mgr = mk(fresh_manager)
    ok, _ = mgr.request(Request.STAND)
    assert not ok  # already standing
    mgr.request(Request.SIT)
    mgr.request(Request.STAND)
    ok, _ = mgr.request(Request.STAND)
    assert not ok  # mid-rise


# --- busy with an episodic role ---------------------------------------------------


@pytest.mark.parametrize("first", [Request.PECK, Request.ROLL, Request.KICK_L, Request.KICK_R])
def test_episodic_refuses_other_behaviors(fresh_manager, first):
    mgr = mk(fresh_manager)
    ok, _ = mgr.request(first)
    assert ok and mgr.busy
    for req in BEHAVIOR_REQUESTS:
        ok2, _ = mgr.request(req)
        assert not ok2, f"{req} aceito durante {first}"


def test_episode_end_returns_to_walk(fresh_manager):
    mgr = mk(fresh_manager)
    mgr.request(Request.ROLL)
    mgr._advance_timers(mgr.durations["roulade"] + 0.05)
    assert mgr.active == "walk" and not mgr.busy
    ok, _ = mgr.request(Request.PECK)  # free again
    assert ok


# --- reset always wins ------------------------------------------------------------


@pytest.mark.parametrize("state", ["free", "seated", "busy"])
def test_reset_accepted_from_any_state(fresh_manager, state):
    mgr = mk(fresh_manager)
    if state == "seated":
        mgr.request(Request.SIT)
    elif state == "busy":
        mgr.request(Request.ROLL)
    ok, _ = mgr.request(Request.RESET)
    assert ok and mgr.active == "walk" and not mgr.seated and not mgr.busy
