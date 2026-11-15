"""Simulator window tests under the offscreen Qt platform (docs/04).

Covers: window builds with menus/panel/status, refused requests flash the
status bar, invalid ONNX shows a pt-BR warning without crashing, valid ONNX
swaps the walk policy, close hides while the tray is up, Sair quits.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from duckdesk import assets
from duckdesk.app import AppController
from duckdesk.brain.commands import Request
from duckdesk.ui.radial_menu import wheel_topleft


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

VELSTAND = assets.assets_dir() / "policies" / "v10" / "velstand.onnx"


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
    yield c
    c.on_quit()


def _pump(ctrl, ms=300):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_window_builds(ctrl):
    w = ctrl.window
    assert w.windowTitle() == "DuckDesk: Simulador"
    menus = [a.text() for a in w.menuBar().actions()]
    for m in ("&Arquivo", "&Simulação", "&Comportamentos", "&Visualização", "&Modo", "A&juda"):
        assert m in menus
    assert len(w.head_sliders) == 4 and len(w.body_sliders) == 6
    assert w.act_mascot.isEnabled()  # Ctrl+M enters mascot mode (M5)


def test_refused_request_flashes_status(ctrl):
    ctrl.mgr.request(Request.SIT, ctrl.sim)  # seat first
    ctrl.on_request(Request.PECK)  # refused while seated
    assert ctrl.window.statusBar().currentMessage() != ""


def test_invalid_onnx_warns_in_pt(ctrl, tmp_path, monkeypatch):
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not an onnx file at all")
    monkeypatch.setattr(ctrl.window, "pick_onnx_file", lambda: str(bad))
    warned = []
    monkeypatch.setattr(ctrl.window, "warn", lambda *a: warned.append(a))
    ctrl.on_load_policy()
    assert warned and ctrl.mgr.walk_policy_name == "velstand.onnx"


def test_valid_onnx_swaps_walk(ctrl, monkeypatch):
    monkeypatch.setattr(ctrl.window, "pick_onnx_file", lambda: str(VELSTAND))
    ctrl.on_load_policy()
    assert ctrl.mgr.walk_policy_name == "velstand.onnx"
    assert ctrl.mgr.active == "walk"


def test_close_hides_with_tray(ctrl):
    ctrl._tray_active = True
    ctrl.window.show()
    ev = _FakeCloseEvent()
    ctrl.window.closeEvent(ev)
    assert ev.ignored and not ctrl.window.isVisible()


def test_close_quits_without_tray(ctrl):
    ctrl._tray_active = False
    ev = _FakeCloseEvent()
    ctrl.window.closeEvent(ev)
    assert ev.accepted


class _FakeCloseEvent:
    def __init__(self):
        self.ignored = False
        self.accepted = False

    def ignore(self):
        self.ignored = True

    def accept(self):
        self.accepted = True


def test_quit_stops_timer(ctrl):
    ctrl.on_quit()
    assert not ctrl.timer.isActive()


def test_mascot_cycle_20x_no_leak(ctrl):
    """Acceptance #3: simulator <-> mascot 20x, RSS growth <= 30 MB."""
    import os

    import psutil

    proc = psutil.Process(os.getpid())
    # Acceptance #3 covers window/renderer churn. The generated voice (ADR-0011)
    # is silenced here: its own footprint is a bounded one-time plateau (audio
    # heap + lazy WAV bank, measured ~+3 MB steady-state standalone), but under
    # this loaded pytest heap its first plays shift the RSS baseline ~40 MB —
    # baseline drift, not per-cycle growth.
    ctrl.voice.enabled = False
    ctrl.enter_mascot()
    ctrl.exit_mascot()  # warm-up: allocate one-time structures
    rss0 = proc.memory_info().rss
    for _ in range(20):
        ctrl.enter_mascot()
        assert ctrl.mascot is not None
        ctrl.exit_mascot()
        assert ctrl.mascot is None
    rss1 = proc.memory_info().rss
    assert rss1 <= rss0 + 30 * 1048576


def test_mascot_hides_under_fullscreen(ctrl, monkeypatch):
    """Acceptance #6: a fullscreen app hides + pauses the mascot (05 section 2)."""
    from duckdesk.platform import win_topmost

    ctrl.enter_mascot()
    monkeypatch.setattr(win_topmost, "fullscreen_app_active", lambda: True)
    ctrl.on_taskbar_timer()
    assert ctrl._fullscreen_hidden
    assert not ctrl.mascot.isVisible()
    monkeypatch.setattr(win_topmost, "fullscreen_app_active", lambda: False)
    ctrl.on_taskbar_timer()
    assert ctrl.mascot.isVisible()  # returns when the fullscreen app exits
    ctrl.exit_mascot()


def test_mascot_frame_produces_alpha(ctrl):
    ctrl.enter_mascot()
    ctrl._tick_mascot(__import__("time").perf_counter() + 1.0)
    assert ctrl.mascot._alpha is not None
    assert ctrl.mascot._alpha.max() == 255  # duck pixels present
    assert ctrl.mascot._alpha.min() == 0  # transparent background
    ctrl.exit_mascot()


# --- duck action wheel (05 section 11, ADR-0008) ------------------------------


def test_duck_head_point_is_above_the_feet(ctrl):
    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    point = ctrl.mascot.duck_head_point()
    assert point is not None
    assert 0 < point.x() < ctrl.mascot.width()  # head is inside the window
    assert 0 < point.y() < ctrl.mascot.height() // 2  # head is in the upper half
    ctrl.exit_mascot()


def test_duck_right_click_opens_the_wheel_above_the_head(ctrl):
    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    head = ctrl._duck_head_global()
    ctrl.mascot.right_clicked.emit(QPoint(head.x(), head.y()))
    menu = ctrl._radial_menu
    assert menu is not None and menu.isVisible()
    assert [a.label for a in menu.actions] == [
        "Bicar",
        "Cambalhota",
        "Sentar",
        "Empurrar",
        "Pausar",
        "Piloto\nligado",
        "Abrir\nsimulador",
        "Sair",
    ]
    # The wheel is anchored above the head and centred on it, clamped to the screen.
    expected = wheel_topleft(head, menu.radius, ctrl.mascot.screen().availableGeometry())
    assert menu.pos() == expected
    ctrl.exit_mascot()
    assert not menu.isVisible()  # hidden, kept for reuse — never deleted


def test_duck_wheel_labels_and_enabled_state_track_the_duck(ctrl):
    ctrl.enter_mascot()
    actions = ctrl.duck_wheel_actions()
    assert actions[0].enabled and actions[1].enabled  # in pé: Bicar/Cambalhota liberados
    ctrl.on_request(Request.SIT)
    actions = ctrl.duck_wheel_actions()
    assert actions[2].label == "Levantar"
    assert not actions[0].enabled and not actions[1].enabled  # sentado: regras de 03 §8
    ctrl.on_toggle_pause()
    assert ctrl.duck_wheel_actions()[4].label == "Continuar"
    ctrl.on_toggle_autopilot()
    assert ctrl.duck_wheel_actions()[5].label == "Piloto\ndesligado"
    assert ctrl.settings["autopilot"] is False
    assert not ctrl.tray.act_autopilot.isChecked()  # tray menu stays in sync
    ctrl.on_toggle_autopilot()
    assert ctrl.tray.act_autopilot.isChecked()
    ctrl.exit_mascot()


def test_duck_wheel_closes_on_exit_mascot(ctrl):
    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    ctrl._show_duck_wheel(QPoint())
    assert ctrl._radial_menu is not None and ctrl._radial_menu.isVisible()
    menu = ctrl._radial_menu
    ctrl.exit_mascot()
    assert ctrl._radial_menu is menu  # hidden and kept for reuse, never deleted
    assert not menu.isVisible()


def test_wheel_open_simulator_sector_leaves_a_healthy_app(ctrl, qapp):
    """Regression for the wheel->simulator freeze: clicking 'Abrir simulador'
    must hide the wheel, leave mascot mode, show the live simulator and keep
    every duckdesk module intact — a deleteLater() on this popup used to gut
    duckdesk.app.__dict__, after which every _tick died on NameError."""
    import math

    import duckdesk.app as appmod
    from duckdesk.ui.radial_menu import sector_index_at

    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    ctrl._show_duck_wheel(QPoint())
    menu = ctrl._radial_menu
    index = next(i for i, a in enumerate(menu.actions) if "simulador" in a.label)
    # Real click at the sector centre, like the user does (05 section 11).
    angle = math.radians(-90.0 + index * 360.0 / len(menu.actions))
    r = (menu.hub_radius + menu.radius) / 2.0
    point = QPoint(
        round(menu.width() / 2 + r * math.cos(angle)),
        round(menu.height() / 2 + r * math.sin(angle)),
    )
    assert (
        sector_index_at(
            point.x() - menu.width() / 2,
            point.y() - menu.height() / 2,
            len(menu.actions),
            menu.hub_radius,
            menu.radius,
        )
        == index
    )
    QTest.mouseClick(menu, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert not menu.isVisible()  # closed before the callback runs
    qapp.processEvents()  # the deferred action fires here
    assert ctrl.mascot is None
    assert ctrl.settings["last_mode"] == "simulator"
    assert ctrl._radial_menu is menu  # reused, never deleted
    assert len(appmod.__dict__) > 50  # module not gutted
    for _ in range(3):  # the timer loop stays healthy
        ctrl._tick()


def test_tray_open_simulator_leaves_mascot_mode(ctrl):
    """Tray 'Abrir simulador' must exit mascot mode, not just raise the
    window: _tick keeps running the mascot loop while self.mascot lives, so
    the raised simulator viewport never renders and the window looks frozen
    (user report: opening the simulator hangs and the duck closes)."""
    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    assert ctrl.mascot is not None
    ctrl.open_simulator()
    assert ctrl.mascot is None
    assert ctrl.settings["last_mode"] == "simulator"


def test_open_simulator_without_mascot_just_shows_the_window(ctrl):
    ctrl.open_simulator()
    assert ctrl.mascot is None
    assert ctrl.settings["last_mode"] == "simulator"


# --- mascot stays inside the monitor (05 sections 3 and 10) ------------------


def _trunk_adr(ctrl) -> int:
    import mujoco

    jid = mujoco.mj_name2id(ctrl.sim.model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
    return int(ctrl.sim.model.jnt_qposadr[jid])


def test_push_force_is_cleared_in_mascot_mode(ctrl):
    """Wheel -> Empurrar must expire after 0.1 s like in the simulator; a
    leftover lateral force used to send the duck flying off the monitor."""
    ctrl.enter_mascot()
    ctrl.on_push()
    assert ctrl.sim.data.xfrc_applied[ctrl.sim.trunk_base_id, 1] != 0.0
    ctrl._tick_mascot(time.perf_counter() + 1.0)  # enough 20 ms control steps
    assert ctrl.sim.data.xfrc_applied[ctrl.sim.trunk_base_id, 1] == 0.0
    ctrl.exit_mascot()


def test_mascot_window_stays_inside_the_band(ctrl):
    """Even with a large depth offset (push/fall/roll), the window is clamped
    to the taskbar band instead of leaving the monitor."""
    import mujoco

    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    adr = _trunk_adr(ctrl)
    band = ctrl.mascot_map.band
    for depth in (2.0, -2.0):
        ctrl.sim.data.qpos[adr + 1] = depth
        mujoco.mj_forward(ctrl.sim.model, ctrl.sim.data)
        ctrl._render_mascot_frame()
        assert ctrl.mascot.x() >= round(band.left)
        assert ctrl.mascot.x() + ctrl.mascot.width() <= round(band.right)
    ctrl.exit_mascot()


def test_mascot_drag_does_not_leave_the_screen(ctrl):
    ctrl.enter_mascot()
    band = ctrl.mascot_map.band
    ctrl._mascot_drag_move(QPoint(-500, 900))
    assert ctrl.mascot.x() >= round(band.left)
    ctrl._mascot_drag_move(QPoint(5000, 900))
    assert ctrl.mascot.x() + ctrl.mascot.width() <= round(band.right)
    ctrl._drag_lift = 0
    ctrl.exit_mascot()


def test_mascot_drag_finish_lands_where_dropped(ctrl):
    """request(RESET) runs sim.reset() internally; the drop x must be written
    AFTER it or the duck snaps back to the band centre."""
    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    band = ctrl.mascot_map.band
    target_px = band.left + 0.25 * (band.right - band.left)
    ctrl._mascot_drag_finish(QPoint(round(target_px), 900))
    expected = ctrl.mascot_map.clamp_x(ctrl.mascot_map.world_x(target_px))
    assert float(ctrl.sim.trunk_pos()[0]) == pytest.approx(expected)
    ctrl.exit_mascot()


def test_mascot_drag_finish_keeps_the_facing(ctrl):
    """05 section 6: the duck lands facing the same way it was dragged."""
    import math

    ctrl.enter_mascot()
    ctrl._tick_mascot(time.perf_counter() + 1.0)
    ctrl._place_yaw(math.pi)  # face the other way before the drop
    ctrl._mascot_drag_finish(QPoint(round(ctrl.mascot_map.band.center), 900))
    assert ctrl.sim.trunk_yaw() == pytest.approx(math.pi)
    ctrl.exit_mascot()


def test_enter_mascot_honours_last_x(ctrl):
    """mascot_last_x was wiped by the same ordering bug: the duck always
    spawned at the band centre regardless of where it was left."""
    ctrl.settings["mascot_last_x"] = 0.25  # metres, well inside the band
    ctrl.enter_mascot()
    expected = ctrl.mascot_map.clamp_x(0.25)
    assert float(ctrl.sim.trunk_pos()[0]) == pytest.approx(expected)
    ctrl.exit_mascot()


def test_double_click_quacks_and_stays_in_mascot(ctrl, monkeypatch):
    """05 section 6: double-click plays the generated 'chirp' (ADR-0011);
    opening the simulator is the tray menu's job only."""
    played = []
    env = ((0.00, 0.0), (0.04, 0.5))
    monkeypatch.setattr(ctrl.voice, "play", lambda tag: played.append(tag) or env)
    ctrl.enter_mascot()
    played.clear()  # the greet on entry is not the click
    ctrl.mascot.double_clicked.emit()
    assert played == ["chirp"]
    assert ctrl.beak._env == env  # the beak lip-syncs the played variant
    assert ctrl.mascot is not None  # still in mascot mode
    ctrl.exit_mascot()


def test_double_click_falls_back_to_mp3_without_voice(ctrl, monkeypatch):
    """With the voice off/unavailable, the bundled quack still answers."""
    monkeypatch.setattr(ctrl.voice, "play", lambda _tag: None)
    calls = []
    monkeypatch.setattr("duckdesk.platform.sound.quack_quack", lambda: calls.append(1))
    ctrl._mascot_double_click()
    assert calls == [1]
    assert ctrl.beak.quacking  # beak still works on the MP3 envelope


def test_about_dialog_text():
    from duckdesk.ui.about import ABOUT_TEXT, notices_path

    for needle in ("não oficial", "Pollen Robotics", "CC BY-NC-SA 4.0", "Apache-2.0", "LGPLv3"):
        assert needle in ABOUT_TEXT
    assert notices_path().name == "THIRD_PARTY_NOTICES.md"


def test_tray_menu_shape(ctrl):
    menu = ctrl.tray.contextMenu()
    texts = [a.text() for a in menu.actions()]
    for t in (
        "Abrir simulador",
        "Mostrar pato na barra",
        "Comportamentos",
        "Piloto automático",
        "Voz do pato",
        "Pausar",
        "Tamanho",
        "Iniciar com o Windows",
        "Sobre e licenças",
        "Sair",
    ):
        assert t in texts
    assert ctrl.tray.act_mascot.isEnabled()
    assert ctrl.tray.act_autopilot.isEnabled()
    assert ctrl.tray.act_voice.isEnabled()
    assert ctrl.tray.act_autostart.isEnabled()
