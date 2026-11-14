"""KeyboardMapper unit tests (docs/04 section 3)."""

from __future__ import annotations

import pytest

from duckdesk.brain.commands import Request
from duckdesk.brain.keyboard import ANG_RAMP, LIN_RAMP, AppIntent, KeyboardMapper

pytestmark = pytest.mark.unit

DT = 0.02


def test_hold_forward_ramps_to_target():
    kb = KeyboardMapper()
    kb.press("w")
    cmd, _, _ = kb.poll(DT)
    assert 0 < cmd.twist[0] < 0.25  # ramping, not a step
    # After enough time it reaches the W target.
    for _ in range(30):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(0.25)


def test_release_ramps_back_to_zero():
    kb = KeyboardMapper()
    kb.press("w")
    for _ in range(30):
        kb.poll(DT)
    kb.release("w")
    cmd, _, _ = kb.poll(DT)
    assert 0 < cmd.twist[0] < 0.25  # decelerating
    for _ in range(30):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(0.0)


def test_ramp_rates():
    kb = KeyboardMapper()
    kb.press("w")
    kb.press("a")
    cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(LIN_RAMP * DT)
    assert cmd.twist[2] == pytest.approx(ANG_RAMP * DT)


def test_opposing_keys_net_target():
    kb = KeyboardMapper()
    kb.press("w")
    kb.press("s")
    cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(LIN_RAMP * DT)  # ramp toward +0.05
    for _ in range(30):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(0.25 - 0.20)


def test_shift_boosts_to_limit():
    kb = KeyboardMapper()
    kb.press("w")
    kb.press("shift")
    for _ in range(60):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(0.3)  # range max, not 0.25


def test_arrow_keys_match_letters():
    kb = KeyboardMapper()
    kb.press("up")
    for _ in range(30):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[0] == pytest.approx(0.25)


def test_strafe_and_turn():
    kb = KeyboardMapper()
    kb.press("q")
    kb.press("d")
    for _ in range(30):
        cmd, _, _ = kb.poll(DT)
    assert cmd.twist[1] == pytest.approx(0.15)
    assert cmd.twist[2] == pytest.approx(-1.0)


def test_one_shot_requests_fire_once():
    kb = KeyboardMapper()
    kb.press("g")
    _, reqs, _ = kb.poll(DT)
    assert reqs == [Request.PECK]
    _, reqs, _ = kb.poll(DT)  # held but already consumed
    assert reqs == []


def test_all_request_keys():
    kb = KeyboardMapper()
    expected = {
        "g": Request.PECK,
        "r": Request.ROLL,
        "k": Request.KICK_L,
        "l": Request.KICK_R,
        "backspace": Request.RESET,
    }
    for key, req in expected.items():
        kb.press(key)
        _, reqs, _ = kb.poll(DT)
        assert req in reqs


def test_intents():
    kb = KeyboardMapper()
    kb.press("y")
    _, _, intents = kb.poll(DT)
    assert AppIntent.TOGGLE_SIT in intents
    kb.press("space")
    _, _, intents = kb.poll(DT)
    assert AppIntent.ZERO_POSE in intents
    kb.press("p")
    _, _, intents = kb.poll(DT)
    assert AppIntent.PAUSE in intents


def test_ctrl_m_minimize():
    kb = KeyboardMapper()
    kb.press("ctrl")
    kb.press("m")
    _, _, intents = kb.poll(DT)
    assert AppIntent.MINIMIZE in intents
    # m without ctrl does not minimize
    kb.release("ctrl")
    kb.press("m")
    _, _, intents = kb.poll(DT)
    assert AppIntent.MINIMIZE not in intents
