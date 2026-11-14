"""Pinpoint WHEN duckdesk.app.__dict__ dies after the real wheel click."""

import math
import pathlib
import sys
import tempfile

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

import duckdesk.app as appmod
from duckdesk.app import AppController
from duckdesk.settings import Settings


def say(msg):
    print(msg, flush=True)


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
ctrl = AppController(app, settings=Settings(pathlib.Path(tempfile.mkdtemp()) / "s.json"))
ctrl.window.show()
ctrl.enter_mascot()

state = {"n": 0}


def stage():
    state["n"] += 1
    i = state["n"]
    say(f"stage {i} dict={len(appmod.__dict__)}")
    if i == 1:
        ctrl._show_duck_wheel(ctrl._duck_head_global())
    elif i == 2:
        menu = ctrl._radial_menu
        mid = math.radians(-90.0 + 6 * 360.0 / 8)
        r = menu.hub_radius + (menu.radius - menu.hub_radius) * 0.6
        pos = QPointF(menu.width() / 2 + r * math.cos(mid), menu.height() / 2 + r * math.sin(mid))
        ev = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            pos,
            menu.mapToGlobal(pos.toPoint()).toPointF(),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        say("posting click")
        app.postEvent(menu, ev)
    elif i >= 3:
        say(f"  t+{i}: dict={len(appmod.__dict__)} mascot={ctrl.mascot} menu={ctrl._radial_menu}")
        if len(appmod.__dict__) < 50:
            say("  *** MODULE DEAD ***")
            QTimer.singleShot(3000, ctrl.on_quit)
            timer.stop()
        if i == 6:
            ctrl.on_quit()


timer = QTimer()
timer.timeout.connect(stage)
timer.start(1500)
sys.exit(app.exec())
