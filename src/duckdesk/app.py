"""AppController: single-Qt-thread main loop (ADR-0003, docs/02 "Laco
principal") wiring sim + policy + keyboard + window + tray.

Physics runs on an 8 ms Qt PreciseTimer through the SimClock accumulator;
rendering never blocks physics and never runs more often than needed.
"""

from __future__ import annotations

import logging
import sys
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import mujoco
import numpy as np
from PySide6.QtCore import QByteArray, QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from duckdesk import assets
from duckdesk.brain.commands import Request
from duckdesk.brain.keyboard import AppIntent, KeyboardMapper
from duckdesk.policy.manager import PolicyManager
from duckdesk.policy.validate import validate_user_onnx
from duckdesk.render.camera import CameraController
from duckdesk.render.offscreen import OffscreenRenderer
from duckdesk.settings import Settings
from duckdesk.sim.clock import SimClock
from duckdesk.sim.core import CONTROL_DT, SimCore
from duckdesk.sim.watchdog import Watchdog

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene_ball.xml"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"
OFFICIAL_WALK = POLICIES_DIR / "velstand.onnx"

PUSH_N = 2.0  # lateral newtons (docs/04 section 5)
PUSH_S = 0.1
TICK_MS = 8  # Qt PreciseTimer (ADR-0003)
MAX_FPS = 60  # simulator render cap (docs/02)
INSTANCE_NAME = "duckdesk-instance"

log = logging.getLogger("duckdesk.app")


def setup_logging(settings: Settings) -> Path:
    """Rotating log: %APPDATA%/DuckDesk/logs/duckdesk.log, 5 x 1 MB."""
    log_dir = settings.path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    target = log_dir / "duckdesk.log"
    handler = RotatingFileHandler(target, maxBytes=1_048_576, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return target


def notify_existing_instance(name: str = INSTANCE_NAME) -> bool:
    """If an instance is already running, ask it to come forward and report True."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"raise")
    sock.flush()
    sock.waitForBytesWritten(300)
    return True


def listen_for_raise(controller: AppController, name: str = INSTANCE_NAME) -> QLocalServer:
    server = QLocalServer(controller if isinstance(controller, QObject) else None)
    if not server.listen(name):
        QLocalServer.removeServer(name)  # stale socket after a crash
        server.listen(name)

    def _on_conn():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            conn.waitForReadyRead(200)
            conn.deleteLater()
            controller.show_simulator()

    server.newConnection.connect(_on_conn)
    return server


class AppController(QObject):
    def __init__(self, app: QApplication, settings: Settings | None = None, with_tray: bool = True):
        super().__init__()
        self.app = app
        self.settings = settings or Settings()
        self.sim = SimCore(SCENE)
        self.sim.park_ball()
        self.mgr = PolicyManager(POLICIES_DIR)
        self.clock = SimClock(speed=float(self.settings["speed"]))
        self.watchdog = Watchdog()
        self.keyboard = KeyboardMapper()
        self.camera = CameraController(self.sim.model)
        self.renderer = OffscreenRenderer(self.sim.model, 960, 600)

        self._head = np.zeros(4, dtype=np.float32)
        self._body = np.zeros(6, dtype=np.float32)
        self._push_left = 0
        self._vel_hist: deque = deque(maxlen=int(1.0 / CONTROL_DT))
        self._frame_times: deque = deque(maxlen=120)
        self._last_render = 0.0
        self._tray_active = False
        self._first_hide_notice = True

        from duckdesk.ui.simulator_window import SimulatorWindow

        self.window = SimulatorWindow(self)
        self._restore_geometry()
        if with_tray:
            self._build_tray()

        self._last = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # --- main loop ------------------------------------------------------------

    def _tick(self) -> None:
        now = time.perf_counter()
        n = self.clock.steps_due(now - self._last)
        self._last = now
        for _ in range(n):
            cmd, requests, intents = self.keyboard.poll(CONTROL_DT)
            self._handle_intents(intents)
            for req in requests:
                self.on_request(req)
            cmd.head = self._head
            cmd.body = self._body
            self.mgr.set_command(cmd)
            targets = self.mgr.step(self.sim)
            self.sim.step_control(targets)
            self._apply_push(CONTROL_DT)
            event = self.watchdog.check(self.sim, CONTROL_DT)
            if event:
                self.mgr.request(Request.RESET, self.sim)
                self.window.flash(f"watchdog: {event} — pato reiniciado")
            v_body, wz = self.sim.body_velocity()
            self._vel_hist.append((float(v_body[0]), float(v_body[1]), wz))

        self._render_if_due(now)
        self.window.update_button_states(self.mgr)
        self._update_status()

    def _render_if_due(self, now: float) -> None:
        if now - self._last_render < 1.0 / MAX_FPS:
            return
        self._last_render = now
        w = max(64, min(self.window.viewport.width(), 1920))
        h = max(64, min(self.window.viewport.height(), 1080))
        self.renderer.set_size(w, h)
        frame = self.renderer.render_rgb(self.sim.data, camera=self.camera.cam)
        self._frame_times.append(time.perf_counter())
        self.window.viewport.set_frame(frame)

    def _update_status(self) -> None:
        if self._vel_hist:
            arr = np.asarray(self._vel_hist).mean(axis=0)
            vel = (
                f"vx {self.mgr.vel_cmd[0]:+.2f}→{arr[0]:+.2f}  "
                f"vy {self.mgr.vel_cmd[1]:+.2f}→{arr[1]:+.2f}  "
                f"wz {self.mgr.vel_cmd[2]:+.2f}→{arr[2]:+.2f}"
            )
        else:
            vel = ""
        fps = 0.0
        if len(self._frame_times) >= 2:
            ts = list(self._frame_times)
            fps = (len(ts) - 1) / max(ts[-1] - ts[0], 1e-9)
        self.window.set_status(
            self.mgr.walk_policy_name,
            vel,
            f"render {fps:4.1f} fps",
            f"atrasados {self.clock.discarded}",
        )

    # --- input plumbing ---------------------------------------------------------

    def on_key(self, key: str, pressed: bool) -> None:
        (self.keyboard.press if pressed else self.keyboard.release)(key)

    def _handle_intents(self, intents) -> None:
        for intent in intents:
            if intent is AppIntent.TOGGLE_SIT:
                self.on_toggle_sit()
            elif intent is AppIntent.ZERO_POSE:
                self._head[:] = 0.0
                self._body[:] = 0.0
                self.window.zero_pose_sliders()
            elif intent is AppIntent.PAUSE:
                self.on_toggle_pause()
            elif intent is AppIntent.MINIMIZE:
                self.window.flash("modo mascote chega no M5")

    def on_request(self, req: Request) -> None:
        ok, msg = self.mgr.request(req, self.sim)
        if not ok:
            self.window.flash(msg)

    def on_toggle_sit(self) -> None:
        self.on_request(Request.STAND if self.mgr.seated else Request.SIT)

    def on_toggle_pause(self) -> None:
        self.clock.paused = not self.clock.paused
        self.window.flash("pausado" if self.clock.paused else "continuando")

    def on_speed(self, speed: float) -> None:
        self.clock.speed = speed
        self.settings["speed"] = speed
        self.window.flash(f"velocidade {speed}x")

    def on_pose_sliders(self, head: np.ndarray, body: np.ndarray) -> None:
        self._head = head.astype(np.float32)
        self._body = body.astype(np.float32)

    # --- menu actions -----------------------------------------------------------

    def on_load_policy(self) -> None:
        path = self.window.pick_onnx_file()
        if not path:
            return
        ok, msg = validate_user_onnx(path)
        if not ok:
            self.window.warn("Política recusada", msg)
            return
        self.mgr.load_walk_policy(path)
        self.mgr.request(Request.RESET, self.sim)
        self.window.flash(f"Política: {Path(path).name}")

    def on_restore_policy(self) -> None:
        self.mgr.load_walk_policy(OFFICIAL_WALK)
        self.mgr.request(Request.RESET, self.sim)
        self.window.flash("Política oficial (velstand.onnx)")

    def on_push(self) -> None:
        self._push_left = int(PUSH_S / CONTROL_DT)
        sign = float(np.random.default_rng().choice((-1.0, 1.0)))
        self.sim.data.xfrc_applied[self.sim.trunk_base_id, 1] = PUSH_N * sign
        self.window.flash("empurrão!")

    def _apply_push(self, dt: float) -> None:
        if self._push_left > 0:
            self._push_left -= 1
            if self._push_left <= 0:
                self.sim.data.xfrc_applied[self.sim.trunk_base_id, 0:3] = 0.0

    # --- camera ------------------------------------------------------------------

    def on_camera_drag(self, action, dx: float, dy: float, h: float) -> None:
        self.camera.mouse_move(action, dx, dy, self.renderer.scene, h)

    def on_camera_wheel(self, steps: float, h: float) -> None:
        self.camera.wheel(steps, self.renderer.scene, h)

    def on_camera_center(self) -> None:
        self.camera.center_on(self.sim.data)

    def on_camera_toggle(self) -> None:
        following = self.camera.toggle()
        self.window.flash("câmera: seguindo" if following else "câmera: livre")

    # --- view flags --------------------------------------------------------------

    def on_show_contacts(self, on: bool) -> None:
        self.renderer.option.flags[mujoco_flag("CONTACTPOINT")] = on
        self.renderer.option.flags[mujoco_flag("CONTACTFORCE")] = on

    def on_show_joints(self, on: bool) -> None:
        self.renderer.option.flags[mujoco_flag("JOINT")] = on

    # --- tray + lifecycle ---------------------------------------------------------

    def _build_tray(self) -> None:
        from duckdesk.ui.tray import Tray

        self.tray = Tray(self)
        self.tray.show()
        self._tray_active = True

    def show_simulator(self) -> None:
        self.window.showNormal()
        self.window.activateWindow()
        self.window.raise_()

    def on_close_request(self) -> bool:
        """True -> hide instead of quit (tray keeps the app alive)."""
        if not self._tray_active:
            return False
        if self._first_hide_notice:
            self._first_hide_notice = False
            self.tray.showMessage(
                "DuckDesk",
                "O app continua rodando na bandeja. 'Sair' encerra de vez.",
                QSystemTrayIcon.Information,
                2500,
            )
        return True

    def on_autopilot_toggled(self, on: bool) -> None:
        self.settings["autopilot"] = on

    def on_autostart_toggled(self, on: bool) -> None:
        from duckdesk.platform import autostart

        try:
            autostart.set_enabled(on)
            self.settings["autostart"] = on
        except OSError as e:
            log.error("falha ao escrever autostart: %s", e)
            self.window.flash("não foi possível alterar a inicialização")

    def on_about(self) -> None:
        from duckdesk.ui.about import AboutDialog

        AboutDialog(self.window).exec()

    def on_quit(self) -> None:
        self.timer.stop()
        self.settings["last_mode"] = "simulator"
        self._save_geometry()
        self.app.quit()

    # --- geometry persistence ---------------------------------------------------

    def _restore_geometry(self) -> None:
        blob = self.settings["window_geometry"]
        if blob:
            self.window.restoreGeometry(QByteArray.fromBase64(blob.encode()))

    def _save_geometry(self) -> None:
        self.settings["window_geometry"] = bytes(self.window.saveGeometry().toBase64()).decode()


def mujoco_flag(name: str):
    return getattr(mujoco.mjtVisFlag, f"mjVIS_{name}")


def run(argv=None) -> int:
    app = QApplication(argv or sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray keeps it alive
    if notify_existing_instance():
        return 0  # second launch: existing instance comes forward
    controller = AppController(app)
    controller.log_file = setup_logging(controller.settings)
    log.info("DuckDesk iniciando (modo=%s)", controller.settings["last_mode"])
    controller._instance_server = listen_for_raise(controller)
    controller.window.show()
    return app.exec()
