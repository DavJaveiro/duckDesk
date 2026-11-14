"""Simulator window tests under the offscreen Qt platform (docs/04).

Covers: window builds with menus/panel/status, refused requests flash the
status bar, invalid ONNX shows a pt-BR warning without crashing, valid ONNX
swaps the walk policy, close hides while the tray is up, Sair quits.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from duckdesk import assets
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

VELSTAND = assets.assets_dir() / "policies" / "v10" / "velstand.onnx"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def ctrl(qapp, tmp_path):
    from duckdesk.settings import Settings

    c = AppController(qapp, settings=Settings(tmp_path / "settings.json"))
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
        "Pausar",
        "Tamanho",
        "Iniciar com o Windows",
        "Sobre e licenças",
        "Sair",
    ):
        assert t in texts
    assert ctrl.tray.act_mascot.isEnabled()
    assert ctrl.tray.act_autopilot.isEnabled()
    assert ctrl.tray.act_autostart.isEnabled()
