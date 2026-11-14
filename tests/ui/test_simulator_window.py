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

pytestmark = pytest.mark.unit

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
    assert not w.act_mascot.isEnabled()  # Ctrl+M disabled until M5


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
