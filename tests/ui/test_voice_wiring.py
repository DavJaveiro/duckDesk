"""Voice event wiring in mascot mode (ADR-0011): a _FakeVoice records the tags
the controller/autopilot would trigger — robotd's mappings, offscreen."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from duckdesk.app import AppController
from duckdesk.brain.commands import Request


def _gl_available() -> bool:
    import mujoco

    try:
        r = mujoco.Renderer(mujoco.MjModel.from_xml_string("<mujoco/>"), 64, 64)
        r.close()
        return True
    except Exception:  # noqa: BLE001 - headless CI hosts lack a GL context
        return False


pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not _gl_available(), reason="no usable GL context"),
]

ENV = ((0.00, 0.0), (0.04, 0.8), (0.08, 0.0))


class _FakeEars:
    """DuckEars-shaped recorder for the tray-toggle wiring."""

    def __init__(self):
        self.state = None
        self.closed = False

    def set_enabled(self, on):
        self.state = on

    def start(self):
        pass

    def close(self):
        self.closed = True


class _FakeVoice:
    """Voice-shaped recorder: every facade entry point is observable."""

    def __init__(self):
        self.tags = []
        self.closed = False

    def play(self, tag):
        self.tags.append(tag)
        return ENV  # every sound "plays" and hands back a beak envelope

    def wheee_start(self):
        self.tags.append("wheee:start")

    def wheee_end(self):
        self.tags.append("wheee:end")

    def close(self):
        self.closed = True


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def ctrl(qapp, tmp_path):
    from duckdesk.settings import Settings

    s = Settings(tmp_path / "settings.json")
    s["ears"] = False  # tests never grab the real mic
    c = AppController(qapp, settings=s)
    c.voice = _FakeVoice()  # replace the real facade for wiring checks
    c.ears = _FakeEars()  # ...and the real mic wrapper
    yield c
    c.on_quit()


def test_double_click_plays_generated_chirp(ctrl):
    """05 §6: the double-click's call is the install's own 'chirp'."""
    ctrl._mascot_double_click()
    assert "chirp" in ctrl.voice.tags
    assert ctrl.beak.quacking
    assert ctrl.beak._env == ENV  # the beak lip-syncs the played variant


def test_enter_mascot_greets_and_wires_the_pilot(ctrl):
    """robotd: 'greet' on wake-up; the pilot hears alarm/coo/inquire itself."""
    ctrl.enter_mascot()
    assert "greet" in ctrl.voice.tags
    assert ctrl.autopilot.voice is ctrl.voice
    ctrl.exit_mascot()


def test_exit_mascot_lands_the_ride(ctrl):
    ctrl.enter_mascot()
    ctrl.voice.tags.clear()
    ctrl.exit_mascot()
    assert "wheee:end" in ctrl.voice.tags  # a ride in progress lands


def test_drag_rides_the_wheee(ctrl):
    """robotd: the held-ride voice — loop on drag start, landing on finish."""
    ctrl.enter_mascot()
    ctrl._mascot_drag_start()
    assert "wheee:start" in ctrl.voice.tags
    ctrl._mascot_drag_finish(ctrl.mascot.pos())
    assert "wheee:end" in ctrl.voice.tags
    ctrl.exit_mascot()


def test_peck_request_voices_peck(ctrl):
    """robotd: pecking -> 'peck' (the wheel's Bicar path goes through here)."""
    ctrl.on_request(Request.PECK)
    assert "peck" in ctrl.voice.tags


def test_look_click_voices_inquire(ctrl):
    """The click's look-toward-cursor reads curious -> 'inquire' (robotd)."""
    ctrl.enter_mascot()
    ctrl._rng = __import__("numpy").random.default_rng(0)  # land the look branch
    for _ in range(20):
        ctrl.voice.tags.clear()
        ctrl._mascot_click(type("P", (), {"x": lambda self: 10})())
        if "inquire" in ctrl.voice.tags:
            break
    assert "inquire" in ctrl.voice.tags
    ctrl.exit_mascot()


def test_quit_says_peck_and_releases_audio(ctrl):
    """robotd: 'peck' is also the goodbye before shutdown."""
    ctrl.on_quit()
    assert "peck" in ctrl.voice.tags
    ctrl._finish_quit()  # the delayed tail of on_quit
    assert ctrl.voice.closed
    assert ctrl.ears.closed


# ---------------------------------------------------------- voice commands ---


def test_voice_command_routes_posture_requests(ctrl):
    """ADR-0012: 'senta'/'levanta' take the same Request path as clicks/keys."""
    seen = []
    ctrl.on_request = seen.append  # record instead of driving the policy
    ctrl.on_voice_command("senta")
    ctrl.on_voice_command("levantar")
    assert seen == [Request.SIT, Request.STAND]


def test_voice_command_tricks_and_voice(ctrl):
    seen = []
    ctrl.on_request = seen.append
    ctrl.on_voice_command("cambalhota")  # -> roll
    ctrl.on_voice_command("bica")  # -> peck (also voices 'peck')
    ctrl.on_voice_command("chuta")  # -> kick, alternating legs
    ctrl.on_voice_command("pia")  # -> chirp
    assert seen == [Request.ROLL, Request.PECK, Request.KICK_L]
    assert "chirp" in ctrl.voice.tags


def test_voice_command_sleep_and_look(ctrl):
    seen = []
    ctrl.on_request = seen.append
    ctrl.on_voice_command("vai dormir")  # sit + yawn + coo
    ctrl.on_voice_command("olha")  # head glance + inquire
    assert seen == [Request.SIT]
    assert "coo" in ctrl.voice.tags and "inquire" in ctrl.voice.tags
    assert ctrl.beak.yawning
    assert ctrl._head[2] != 0.0


def test_voice_command_walk_impulse_and_stop(ctrl):
    """In the simulator, 'anda' feeds a forward impulse the control loop reads."""
    assert ctrl.mascot is None  # sim-mode fixture
    ctrl.on_voice_command("anda")
    assert ctrl._voice_walk > 0
    ctrl.on_voice_command("para")
    assert ctrl._voice_walk == 0


def test_voice_command_ignores_noise(ctrl):
    seen = []
    ctrl.on_request = seen.append
    ctrl.on_voice_command("[unk]")
    ctrl.on_voice_command("isso não é um comando")
    assert seen == [] and ctrl.voice.tags == []


def test_ears_toggle_reaches_the_mic_wrapper(ctrl):
    """Tray 'Ouvido do pato' persists settings and grabs/releases the mic."""
    ctrl.on_ears_toggled(False)
    assert ctrl.settings["ears"] is False
    assert ctrl.ears.state is False
    ctrl.on_ears_toggled(True)
    assert ctrl.settings["ears"] is True
    assert ctrl.ears.state is True
