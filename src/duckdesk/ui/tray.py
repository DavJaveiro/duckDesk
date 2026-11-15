"""System tray menu (docs/05 section 7).

The native QMenu belongs to the tray icon only (including when it lives in the
hidden-icons area). Right-clicking the duck itself opens the radial action
wheel in ``radial_menu.py`` (05 section 11).
"""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from duckdesk import assets
from duckdesk.brain.commands import Request


def duck_icon() -> QIcon:
    return QIcon(str(assets.assets_dir() / "icons" / "duckdesk.png"))


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
        act_open.triggered.connect(self.ctrl.open_simulator)

        self.act_mascot = menu.addAction("Mostrar pato na barra")
        self.act_mascot.triggered.connect(self.ctrl.toggle_mascot)

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

        self.act_voice = menu.addAction("Voz do pato")
        self.act_voice.setCheckable(True)
        self.act_voice.setChecked(bool(self.ctrl.settings["voice"]))
        self.act_voice.toggled.connect(self.ctrl.on_voice_toggled)

        self.act_ears = menu.addAction("Ouvido do pato")
        self.act_ears.setCheckable(True)
        self.act_ears.setChecked(bool(self.ctrl.settings["ears"]))
        self.act_ears.toggled.connect(self.ctrl.on_ears_toggled)

        act_pause = menu.addAction("Pausar")
        act_pause.triggered.connect(self.ctrl.on_toggle_pause)

        sub_size = menu.addMenu("Tamanho")
        self._size_actions = {}
        current = float(self.ctrl.settings["mascot_scale"])
        for label, scale in (("Pequeno", 80 / 120), ("Médio", 1.0), ("Grande", 180 / 120)):
            a = sub_size.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(current - scale) < 0.01)
            self._size_actions[label] = a
        # Connect only after the initial check: setChecked() would otherwise
        # fire on_size_changed() (and a settings write) during startup.
        for label, scale in (("Pequeno", 80 / 120), ("Médio", 1.0), ("Grande", 180 / 120)):
            self._size_actions[label].toggled.connect(
                lambda on, s=scale: on and self.ctrl.on_size_changed(s)
            )

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
        # 05 section 7: a click on the icon shows/hides the duck, not the sim.
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.ctrl.toggle_mascot()
