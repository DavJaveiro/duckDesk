"""Simulator window (docs/04): viewport, side panel, status bar, menus.

All behavior goes through the AppController — this file only owns widgets and
event plumbing.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QImage, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from duckdesk.brain.commands import Request
from duckdesk.render.camera import MouseAction

QT_KEY_MAP = {
    Qt.Key_W: "w",
    Qt.Key_S: "s",
    Qt.Key_A: "a",
    Qt.Key_D: "d",
    Qt.Key_Q: "q",
    Qt.Key_E: "e",
    Qt.Key_Up: "up",
    Qt.Key_Down: "down",
    Qt.Key_Left: "left",
    Qt.Key_Right: "right",
    Qt.Key_G: "g",
    Qt.Key_R: "r",
    Qt.Key_K: "k",
    Qt.Key_L: "l",
    Qt.Key_Y: "y",
    Qt.Key_P: "p",
    Qt.Key_M: "m",
    Qt.Key_Space: "space",
    Qt.Key_Backspace: "backspace",
    Qt.Key_Shift: "shift",
    Qt.Key_Control: "ctrl",
    Qt.Key_C: "c",
}

HEAD_LIMITS = [1.4, 1.4, 1.4, 1.4]  # neck_pitch, head_pitch, yaw, roll
HEAD_LABELS = ["neck_pitch", "head_pitch", "head_yaw", "head_roll"]
BODY_LABELS = ["body_x", "body_y", "body_z", "body_roll", "body_pitch", "body_yaw"]
BODY_LIMITS = [0.02, 0.02, 0.03, 0.5236, 0.5236, 0.5236]  # m / rad (30 deg)


class Viewport(QWidget):
    """Paints the latest RGB frame; forwards mouse to the camera."""

    def __init__(self, window: SimulatorWindow):
        super().__init__()
        self._win = window
        self._image: QImage | None = None
        self._drag: tuple[int, int] | None = None
        self.setMinimumSize(320, 200)
        self.setMouseTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_frame(self, rgb: np.ndarray) -> None:
        h, w, _ = rgb.shape
        self._image = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._image is not None:
            painter.drawImage(self.rect(), self._image)
        painter.end()

    # --- camera mouse (docs/04 section 2) -----------------------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self._drag = (int(ev.position().x()), int(ev.position().y()), ev.button())

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if not self._drag:
            return
        x0, y0, btn = self._drag
        x1, y1 = int(ev.position().x()), int(ev.position().y())
        action = MouseAction.ORBIT if btn == Qt.LeftButton else MouseAction.PAN
        self._win.controller.on_camera_drag(action, x1 - x0, y1 - y0, self.height())
        self._drag = (x1, y1, btn)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        self._win.controller.on_camera_center()

    def wheelEvent(self, ev: QWheelEvent) -> None:
        self._win.controller.on_camera_wheel(ev.angleDelta().y() / 120.0, self.height())


class SimulatorWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("DuckDesk: Simulador")
        self.resize(1280, 800)

        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)

        self._build_panel()
        self._build_status()
        self._build_menus()

    # --- side panel (docs/04 section 4) ---------------------------------------

    def _build_panel(self) -> None:
        self.dock = QDockWidget("Comportamentos", self)
        self.dock.setObjectName("behaviorDock")
        panel = QWidget()
        layout = QVBoxLayout(panel)

        grid = QGridLayout()
        self.btn_sit = QPushButton("Sentar")
        self.btn_peck = QPushButton("Bicar")
        self.btn_roll = QPushButton("Cambalhota")
        self.btn_kick_l = QPushButton("Chutar (esq.)")
        self.btn_kick_r = QPushButton("Chutar (dir.)")
        self.btn_reset = QPushButton("Reset")
        self.btn_sit.clicked.connect(lambda: self.controller.on_toggle_sit())
        self.btn_peck.clicked.connect(lambda: self._request(Request.PECK))
        self.btn_roll.clicked.connect(lambda: self._request(Request.ROLL))
        self.btn_kick_l.clicked.connect(lambda: self._request(Request.KICK_L))
        self.btn_kick_r.clicked.connect(lambda: self._request(Request.KICK_R))
        self.btn_reset.clicked.connect(lambda: self._request(Request.RESET))
        for i, b in enumerate(
            (
                self.btn_sit,
                self.btn_peck,
                self.btn_roll,
                self.btn_kick_l,
                self.btn_kick_r,
                self.btn_reset,
            )
        ):
            grid.addWidget(b, i // 2, i % 2)
        layout.addLayout(grid)

        self.head_sliders = []
        self.body_sliders = []
        layout.addWidget(QLabel("Cabeça"))
        for name, lim in zip(HEAD_LABELS, HEAD_LIMITS):
            layout.addWidget(QLabel(name))
            s = QSlider(Qt.Horizontal)
            s.setRange(-1000, 1000)
            s.setValue(0)
            s.setProperty("lim", lim)
            s.valueChanged.connect(self._pose_changed)
            layout.addWidget(s)
            self.head_sliders.append(s)
        layout.addWidget(QLabel("Corpo"))
        for name, lim in zip(BODY_LABELS, BODY_LIMITS):
            layout.addWidget(QLabel(name))
            s = QSlider(Qt.Horizontal)
            s.setRange(-1000, 1000)
            s.setValue(0)
            s.setProperty("lim", lim)
            s.valueChanged.connect(self._pose_changed)
            layout.addWidget(s)
            self.body_sliders.append(s)
        layout.addStretch(1)
        self.dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)

    def _pose_changed(self) -> None:
        head = np.array(
            [s.value() / 1000.0 * s.property("lim") for s in self.head_sliders],
            dtype=np.float32,
        )
        body = np.array(
            [s.value() / 1000.0 * s.property("lim") for s in self.body_sliders],
            dtype=np.float32,
        )
        self.controller.on_pose_sliders(head, body)

    def zero_pose_sliders(self) -> None:
        for s in (*self.head_sliders, *self.body_sliders):
            s.setValue(0)

    def _request(self, req: Request) -> None:
        self.controller.on_request(req)

    # --- status bar (docs/04 section 1) ---------------------------------------

    def _build_status(self) -> None:
        bar = self.statusBar()
        self.lbl_policy = QLabel("Política: velstand.onnx")
        self.lbl_vel = QLabel("")
        self.lbl_fps = QLabel("")
        self.lbl_late = QLabel("")
        for w in (self.lbl_policy, self.lbl_vel, self.lbl_fps, self.lbl_late):
            bar.addPermanentWidget(w)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.statusBar().clearMessage())

    def flash(self, msg: str, ms: int = 2000) -> None:
        self.statusBar().showMessage(msg, ms)

    def set_status(self, policy: str, vel: str, fps: str, late: str) -> None:
        self.lbl_policy.setText(f"Política: {policy}")
        self.lbl_vel.setText(vel)
        self.lbl_fps.setText(fps)
        self.lbl_late.setText(late)

    def update_button_states(self, mgr) -> None:
        busy, seated = mgr.busy, mgr.seated
        self.btn_sit.setText("Levantar" if seated else "Sentar")
        self.btn_sit.setEnabled(not busy)
        for b in (self.btn_peck, self.btn_roll, self.btn_kick_l, self.btn_kick_r):
            b.setEnabled(not busy and not seated)

    # --- menus (docs/04 section 5) --------------------------------------------

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("&Arquivo")
        self._act(m_file, "Carregar política de caminhada (.onnx)…", self.controller.on_load_policy)
        self._act(m_file, "Voltar à política oficial", self.controller.on_restore_policy)
        m_file.addSeparator()
        self._act(m_file, "Sair", self.controller.on_quit)

        m_sim = mb.addMenu("&Simulação")
        self._act(m_sim, "Pausar", self.controller.on_toggle_pause, shortcut="P")
        self._act(m_sim, "Reiniciar", lambda: self._request(Request.RESET), shortcut="Backspace")
        m_speed = m_sim.addMenu("Velocidade")
        for label, v in (("0,25×", 0.25), ("0,5×", 0.5), ("1×", 1.0)):
            self._act(m_speed, label, lambda _=False, s=v: self.controller.on_speed(s))
        self._act(m_sim, "Empurrar o pato", self.controller.on_push)

        m_beh = mb.addMenu("&Comportamentos")
        self._act(m_beh, "Sentar/Levantar", self.controller.on_toggle_sit, shortcut="Y")
        self._act(m_beh, "Bicar o chão", lambda: self._request(Request.PECK), shortcut="G")
        self._act(m_beh, "Cambalhota", lambda: self._request(Request.ROLL), shortcut="R")
        self._act(m_beh, "Chutar (esq.)", lambda: self._request(Request.KICK_L), shortcut="K")
        self._act(m_beh, "Chutar (dir.)", lambda: self._request(Request.KICK_R), shortcut="L")

        m_view = mb.addMenu("&Visualização")
        self._act(m_view, "Seguir o pato", self.controller.on_camera_toggle, shortcut="C")
        self.act_contacts = self._act(
            m_view, "Mostrar contatos", self.controller.on_show_contacts, checkable=True
        )
        self.act_joints = self._act(
            m_view, "Mostrar juntas", self.controller.on_show_joints, checkable=True
        )
        self.act_panel = self._act(m_view, "Painel lateral", self.dock.setVisible, checkable=True)
        self.act_panel.setChecked(True)

        m_mode = mb.addMenu("&Modo")
        self.act_mascot = self._act(
            m_mode,
            "Enviar para a barra de tarefas",
            self.controller.toggle_mascot,
            shortcut="Ctrl+M",
        )

        m_help = mb.addMenu("A&juda")
        self._act(m_help, "Atalhos de teclado", self._show_shortcuts)
        self._act(m_help, "Testar microfone…", self.controller.on_mic_test)
        self._act(m_help, "Sobre e licenças", self.controller.on_about)

    def _act(self, menu, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        if checkable:
            a.setCheckable(True)
            a.toggled.connect(slot)
        elif slot is not None:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Atalhos",
            "W/S/A/D ou setas: andar e girar   Q/E: passo lateral\n"
            "Shift+direção: velocidade máxima\n"
            "Y: sentar/levantar   G: bicar   R: cambalhota   K/L: chutar\n"
            "Espaço: zerar cabeça/corpo   Backspace: reset   P: pausar\n"
            "C: câmera seguir/livre   Ctrl+M: enviar para a bandeja",
        )

    def pick_onnx_file(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Carregar política de caminhada", "", "ONNX (*.onnx)"
        )
        return path or None

    def warn(self, title: str, msg: str) -> None:
        QMessageBox.warning(self, title, msg)

    # --- keyboard ---------------------------------------------------------------

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.isAutoRepeat():
            return
        key = QT_KEY_MAP.get(ev.key())
        if key == "c":
            self.controller.on_camera_toggle()
            return
        if key:
            self.controller.on_key(key, True)

    def keyReleaseEvent(self, ev: QKeyEvent) -> None:
        if ev.isAutoRepeat():
            return
        key = QT_KEY_MAP.get(ev.key())
        if key and key != "c":
            self.controller.on_key(key, False)

    # --- close = hide while tray is up (docs/04 section 1) ------------------------

    def closeEvent(self, ev) -> None:
        if self.controller.on_close_request():
            ev.ignore()
            self.hide()
        else:
            ev.accept()
