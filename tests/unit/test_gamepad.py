"""GamepadMapper tests (docs/04 section 3): deadzone, floor-scaled twist
(ADR-0006), head look, edge-triggered buttons and keyboard handoff."""

import pytest

from duckdesk.brain.commands import Request
from duckdesk.brain.gamepad_map import GamepadMapper
from duckdesk.brain.keyboard import AppIntent
from duckdesk.platform.gamepad import Pad

pytestmark = pytest.mark.unit
DT = 0.02


def _run(mapper, pad, seconds=1.0):
    """Feed the same pad for `seconds`, returning the last poll."""
    out = None
    for _ in range(int(seconds / DT)):
        out = mapper.poll_state(pad, DT)
    return out


def test_no_pad_returns_none_and_clears_state():
    m = GamepadMapper()
    _run(m, Pad(ly=1.0))
    twist, head, reqs, intents = m.poll_state(None, DT)
    assert twist is None and head is None
    assert reqs == [] and intents == []
    assert not m.connected


def test_stick_inside_deadzone_keeps_keyboard_in_control():
    m = GamepadMapper()
    twist, head, _, _ = m.poll_state(Pad(ly=0.15), DT)
    assert twist is None and head is None  # 0.15 < DEADZONE


def test_full_forward_commands_max_vx():
    m = GamepadMapper()
    twist, *_ = _run(m, Pad(ly=1.0))
    assert twist is not None
    assert twist[0] == pytest.approx(0.3, abs=1e-3)
    assert twist[1] == 0.0 and twist[2] == 0.0


def test_half_deflection_still_walks():
    """Floor-scaled magnitude: half the stick commands >= the 0.25 walk
    threshold (ADR-0006) — a soft push must still produce steps."""
    m = GamepadMapper()
    twist, *_ = _run(m, Pad(ly=0.5))
    assert twist is not None
    assert 0.26 <= twist[0] < 0.3


def test_stick_right_turns_right():
    m = GamepadMapper()
    twist, *_ = _run(m, Pad(lx=1.0))
    assert twist is not None
    assert twist[2] == pytest.approx(-1.5, abs=1e-3)  # like the D key


def test_dpad_strafes_like_q_and_e():
    m = GamepadMapper()
    twist, *_ = _run(m, Pad(buttons=frozenset({"left"})))
    assert twist[1] == pytest.approx(0.2, abs=1e-3)
    m2 = GamepadMapper()
    twist, *_ = _run(m2, Pad(buttons=frozenset({"right"})))
    assert twist[1] == pytest.approx(-0.2, abs=1e-3)


def test_right_stick_looks_around():
    m = GamepadMapper()
    _, head, _, _ = m.poll_state(Pad(rx=1.0, ry=1.0), DT)
    assert head is not None
    assert head[2] == pytest.approx(0.9)  # head_yaw
    assert head[0] == pytest.approx(0.4)  # neck pitch
    _, head, _, _ = m.poll_state(Pad(), DT)
    assert head is None  # released stick stops driving the head


def test_buttons_fire_once_per_press():
    m = GamepadMapper()
    _, _, reqs, _ = m.poll_state(Pad(buttons=frozenset({"a"})), DT)
    assert reqs == [Request.PECK]
    _, _, reqs, _ = m.poll_state(Pad(buttons=frozenset({"a"})), DT)
    assert reqs == []  # still held: no refire
    _, _, reqs, _ = m.poll_state(Pad(), DT)  # released
    _, _, reqs, _ = m.poll_state(Pad(buttons=frozenset({"a"})), DT)
    assert reqs == [Request.PECK]  # new press fires again


def test_button_intents_and_reset():
    m = GamepadMapper()
    _, _, _, intents = m.poll_state(Pad(buttons=frozenset({"back"})), DT)
    assert intents == [AppIntent.TOGGLE_SIT]
    _, _, _, intents = m.poll_state(Pad(buttons=frozenset({"start"})), DT)
    assert intents == [AppIntent.PAUSE]
    _, _, _, intents = m.poll_state(Pad(buttons=frozenset({"l3"})), DT)
    assert intents == [AppIntent.ZERO_POSE]
    _, _, reqs, _ = m.poll_state(Pad(buttons=frozenset({"r3"})), DT)
    assert reqs == [Request.RESET]


def test_release_decays_command_toward_keyboard_handoff():
    m = GamepadMapper()
    _run(m, Pad(ly=1.0))
    twist, *_ = _run(m, Pad())  # released: gamepad stops owning twist
    assert twist is None
