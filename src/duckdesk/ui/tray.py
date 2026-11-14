"""System tray menu (docs/05 section 7).

Mascot-only items stay disabled until M5; everything else is wired to the
AppController.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from duckdesk.brain.commands import Request


def duck_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.darkYellow)
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, controller, parent=None):
        super().__init__(duck_icon(), parent)
        self.ctrl = controller
        self.setToolTip("DuckDesk")
        menu = QMenu()

        act_open = menu.addAction("Abrir simulador")
        f = act_open.font()
        f.setBold(True)
        act_open.setFont(f)
        act_open.triggered.connect(self.ctrl.show_simulator)

        self.act_mascot = menu.addAction("Mostrar pato na barra")
        self.act_mascot.setEnabled(False)  # M5

        sub = menu.addMenu("Comportamentos")
        act_sit = sub.addAction("Sentar/Levantar")
        act_sit.triggered.connect(self.ctrl.on_toggle_sit)
        act_peck = sub.addAction("Bicar o chão")
        act_peck.triggered.connect(lambda: self.ctrl.on_request(Request.PECK))
        act_roll = sub.addAction("Cambalhota")
        act_roll.triggered.connect(lambda: self.ctrl.on_request(Request.ROLL))

        self.act_autopilot = menu.addAction("Piloto automático")
        self.act_autopilot.setCheckable(True)
        self.act_autopilot.setChecked(bool(self.ctrl.settings["autopilot"]))
        self.act_autopilot.toggled.connect(self.ctrl.on_autopilot_toggled)
        self.act_autopilot.setEnabled(False)  # M5 (autopilot só faz sentido no mascote)

        act_pause = menu.addAction("Pausar")
        act_pause.triggered.connect(self.ctrl.on_toggle_pause)

        sub_size = menu.addMenu("Tamanho")
        for label in ("Pequeno", "Médio", "Grande"):
            a = sub_size.addAction(label)
            a.setCheckable(True)
            a.setEnabled(False)  # M5
        sub_size.setEnabled(False)  # M5

        self.act_autostart = menu.addAction("Iniciar com o Windows")
        self.act_autostart.setCheckable(True)
        from duckdesk.platform import autostart

        self.act_autostart.setChecked(autostart.is_enabled())
        self.act_autostart.toggled.connect(self.ctrl.on_autostart_toggled)

        act_about = menu.addAction("Sobre e licenças")
        act_about.triggered.connect(self.ctrl.on_about)

        menu.addSeparator()
        act_quit = menu.addAction("Sair")
        act_quit.triggered.connect(self.ctrl.on_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.ctrl.show_simulator()
