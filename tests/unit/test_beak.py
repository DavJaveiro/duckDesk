"""Beak animator, autopilot mouth wiring and SimCore beak posing
(ADR-0010, docs/05 section 6).

Upstream references are cited in the module under test (duck-control
model.rs, robotd idle_head.rs, robotd-params defaults); the tests pin the
observable contract, like the upstream's own idle_head tests.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from duckdesk import assets
from duckdesk.brain.autopilot import Autopilot, AutoState
from duckdesk.brain.beak import GLANCE_MOUTH, QUACK_ENV, YAWN_OPEN, YAWN_S, BeakAnimator
from duckdesk.sim.core import SimCore

pytestmark = pytest.mark.unit

DT = 0.02
SCENE = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck" / "scene_ball.xml"


def _run(b: BeakAnimator, seconds: float) -> np.ndarray:
    """Per-tick (mouth, head) trace."""
    out = []
    for _ in range(round(seconds / DT)):
        b.update(DT)
        out.append((b.mouth, b.head))
    return np.array(out)


# --- animator envelopes -------------------------------------------------------


def test_quack_follows_the_recording_envelope():
    b = BeakAnimator()
    b.quack()
    tr = _run(b, QUACK_ENV[-1][0] + 0.2)
    mouth = tr[:, 0]
    assert mouth.max() == pytest.approx(1.0, abs=0.05)  # the loudest quack
    assert mouth[-1] == pytest.approx(0.0)  # shut when the file ends
    assert not b.quacking
    # every burst in the file works the beak: >= 4 separated openings
    # (between neighbouring quacks the envelope only dips to ~0.06-0.15)
    peaks, open_ = 0, False
    for m in mouth:
        if not open_ and m > 0.3:
            peaks += 1
            open_ = True
        elif open_ and m < 0.15:
            open_ = False
    assert peaks >= 4


def test_quack_toss_tips_the_head_and_recovers():
    """autonomous.md: quacks come 'with the mouth and a head toss'."""
    b = BeakAnimator()
    b.quack()
    tr = _run(b, QUACK_ENV[-1][0] + 0.2)
    assert tr[:, 1].min() < 0.0  # head_pitch < 0 = beak up (emotion.rs)
    assert tr[-1, 1] == 0.0


def test_yawn_shape_slow_open_hold_quicker_close():
    """Port of upstream a_yawn_starts_and_ends_closed (idle_head.rs)."""
    b = BeakAnimator()
    b.yawn()
    tr = _run(b, YAWN_S + 0.5)
    mouth = tr[:, 0]
    peak_i = int(mouth.argmax())
    assert peak_i * DT >= 0.38 * YAWN_S  # slow open: 40% of the duration
    assert mouth[peak_i] == pytest.approx(YAWN_OPEN, abs=1e-6)
    plateau = np.flatnonzero(np.isclose(mouth, YAWN_OPEN))
    assert (plateau[-1] - plateau[0]) * DT >= 0.25 * YAWN_S  # the hold
    assert mouth[-1] == pytest.approx(0.0)  # ends exactly closed
    assert not b.yawning
    assert tr[:, 1].min() < -0.1  # the head tips (yawn_pitch = -0.15)
    assert tr[-1, 1] == 0.0


def test_yawn_does_not_restart_mid_yawn():
    b = BeakAnimator()
    b.yawn()
    _run(b, 1.0)
    b.yawn()  # second call ignored while the first plays
    _run(b, YAWN_S - 1.0)
    assert not b.yawning  # the first yawn finished on its own clock


def test_glance_opens_a_touch_and_closes():
    b = BeakAnimator()
    b.set_glance(GLANCE_MOUTH)
    b.update(DT)
    assert b.mouth == pytest.approx(GLANCE_MOUTH)
    b.set_glance(0.0)
    b.update(DT)
    assert b.mouth == 0.0


def test_mouth_composition_is_max():
    """robotd main.rs: mouth = max(intent, idle) — the quack wins."""
    b = BeakAnimator()
    b.quack()
    b.set_glance(GLANCE_MOUTH)
    b._quack_t = 0.16  # the loudest keyframe in the recording
    b.update(DT)
    assert b.mouth == pytest.approx(1.0, abs=0.06)


# --- autopilot wiring ---------------------------------------------------------


class FakeManager:
    """Same stand-in as test_autopilot.py: accepts and records."""

    def __init__(self):
        self.seated = False
        self.busy = False
        self.cmd = None
        self.requests = []

    def set_command(self, cmd):
        self.cmd = cmd

    def request(self, req):
        self.requests.append(req)
        return True, "ok"


def test_idle_glances_open_the_beak_a_touch():
    """idle_head.rs: every glance opens the beak a touch; its test pins > 0.02."""
    beak = BeakAnimator()
    pilot = Autopilot(np.random.default_rng(0), beak=beak)
    mgr = FakeManager()
    peak = 0.0
    for _ in range(round(3.0 / DT)):
        pilot.update(DT, 0, 0, 0, 0, mgr)
        pilot._idle_left = 3.0  # hold IDLE for the whole run
        peak = max(peak, beak.mouth)
    assert peak > 0.02
    assert peak <= GLANCE_MOUTH + 1e-9


def test_glance_beak_shuts_when_the_look_centres():
    beak = BeakAnimator()
    pilot = Autopilot(np.random.default_rng(0), beak=beak)
    mgr = FakeManager()
    pilot._look_left = 99.0  # no redraw: the held look is the zero target
    pilot._idle_left = 3.0
    for _ in range(round(2.0 / DT)):
        pilot.update(DT, 0, 0, 0, 0, mgr)
        pilot._idle_left = 3.0
    assert beak.mouth == pytest.approx(0.0, abs=1e-9)


def test_leaving_idle_shuts_the_glance_beak():
    beak = BeakAnimator()
    pilot = Autopilot(np.random.default_rng(0), beak=beak)
    mgr = FakeManager()
    beak.set_glance(GLANCE_MOUTH)
    pilot._goto(AutoState.RECOVER)
    pilot.update(DT, 0, 0, 0.0, math.radians(80), mgr)  # still falling
    assert beak.mouth == pytest.approx(0.0, abs=1e-9)


def test_yawn_needs_45s_of_stillness_then_the_coin():
    """robotd-params: yawn_after_s = 45, then a coin averaging yawn_every_s."""
    beak = BeakAnimator()
    pilot = Autopilot(np.random.default_rng(0), enabled=False, beak=beak)
    mgr = FakeManager()
    for _ in range(round(44.0 / DT)):
        pilot.update(DT, 0, 0, 0, 0, mgr)
        assert not beak.yawning

    class _Coin:
        def random(self):
            return 0.0  # every coin wins once the gate opens

        def uniform(self, *a, **k):
            return 0.0

        def choice(self, *a, **k):
            return 1.0

    pilot.rng = _Coin()
    for _ in range(round(1.2 / DT)):  # 45.2 s of stillness
        pilot.update(DT, 0, 0, 0, 0, mgr)
    assert beak.yawning


def test_poke_resets_the_stillness_clock():
    pilot = Autopilot(np.random.default_rng(0), beak=BeakAnimator())
    pilot._calm_s = 50.0
    pilot.poke()
    assert pilot._calm_s == 0.0


def test_quack_toss_reaches_the_head_command():
    """_send merges the beak's head offset into the policy's head command."""
    beak = BeakAnimator()
    pilot = Autopilot(np.random.default_rng(0), beak=beak)
    mgr = FakeManager()
    beak.quack()
    pilot.update(DT, 0, 0, 0, 0, mgr)
    assert mgr.cmd.head[1] < 0.0  # toss rides on top of the look pose


# --- SimCore posing -----------------------------------------------------------


def test_set_beak_poses_and_restores():
    """The jaw geoms and the mouth_tip ride the hinge; model layout untouched."""
    sim = SimCore(SCENE)
    g = sim._beak_geoms[0]
    pos0 = sim._beak_rest[0][0].copy()
    sim.set_beak(0.6)
    assert not np.allclose(sim.model.geom_pos[g], pos0)
    assert sim.model.nu == 14  # no actuator/joint crept in (61D obs intact)
    sim.set_beak(0.0)
    assert np.allclose(sim.model.geom_pos[g], pos0, atol=1e-9)
    assert np.allclose(sim.model.site_pos[sim._beak_site], sim._beak_site_rest[0])


def test_beak_open_drops_the_tip():
    """Hinge at the mouth corners: the tip swings down and slightly back —
    the jaw arc a real beak makes when it opens."""
    sim = SimCore(SCENE)
    sid = sim._beak_site
    tip0 = sim.data.site_xpos[sid].copy()
    sim.set_beak(1.0)
    tip1 = sim.data.site_xpos[sid].copy()
    assert tip1[2] < tip0[2] - 0.005  # drops visibly
    assert abs(tip1[1] - tip0[1]) < 1e-6  # no sideways drift
