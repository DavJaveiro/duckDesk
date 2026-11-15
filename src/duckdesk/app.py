"""AppController: single-Qt-thread main loop (ADR-0003, docs/02 "Laco
principal") wiring sim + policy + keyboard + window + tray.

Physics runs on an 8 ms Qt PreciseTimer through the SimClock accumulator;
rendering never blocks physics and never runs more often than needed.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import mujoco
import numpy as np
from PySide6.QtCore import QByteArray, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from duckdesk import assets
from duckdesk.brain.beak import BeakAnimator
from duckdesk.brain.commands import Request
from duckdesk.brain.gamepad_map import GamepadMapper
from duckdesk.brain.keyboard import AppIntent, KeyboardMapper
from duckdesk.policy.manager import PolicyManager
from duckdesk.policy.validate import validate_user_onnx
from duckdesk.render.camera import CameraController
from duckdesk.render.offscreen import OffscreenRenderer
from duckdesk.settings import Settings
from duckdesk.sim.clock import SimClock
from duckdesk.sim.core import CONTROL_DT, SimCore
from duckdesk.sim.watchdog import Watchdog
from duckdesk.ui.radial_menu import RadialMenu, WheelAction, radius_for_duck

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


def setup_logging(settings: Settings) -> Path | None:
    """Rotating log: %APPDATA%/DuckDesk/logs/duckdesk.log, 5 x 1 MB.

    A read-only profile (restricted sandbox, antivirus lock) must not stop the
    app from starting: fall back to %TEMP%/DuckDesk/logs, then to stderr only.
    Returns the log file path, or None when only stderr was available.
    """
    candidates = [settings.path.parent / "logs"]
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        candidates.append(Path(temp) / "DuckDesk" / "logs")
    target: Path | None = None
    handler: logging.Handler | None = None
    for log_dir in candidates:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            candidate = log_dir / "duckdesk.log"
            handler = RotatingFileHandler(
                candidate, maxBytes=1_048_576, backupCount=5, encoding="utf-8"
            )
        except OSError:
            continue
        target = candidate
        break

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if handler is None:
        fallback = logging.StreamHandler()
        fallback.setFormatter(formatter)
        root.addHandler(fallback)
        log.warning("nenhum diretório de log gravável; log apenas no console")
        return None
    handler.setFormatter(formatter)
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
            controller.open_simulator()

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
        self.gamepad = GamepadMapper()
        self.camera = CameraController(self.sim.model)
        self.renderer = OffscreenRenderer(self.sim.model, 960, 600)

        self._head = np.zeros(4, dtype=np.float32)
        self._body = np.zeros(6, dtype=np.float32)
        self._push_left = 0
        self.mascot = None  # MascotWindow while in mascot mode
        self.mascot_map = None
        self._radial_menu: RadialMenu | None = None  # duck right-click wheel (05 §11)
        self._mascot_renderer = None
        self._last_mascot_frame = 0.0
        self._dragging_duck = False
        self._drag_lift = 0
        self._fullscreen_hidden = False
        # 30 fps on an 8 ms tick: frames land on tick multiples, so allow half a
        # tick of slack or the 33.3 ms cap rounds up to 40 ms (25 fps).
        self._mascot_fps_cap = 1.0 / 30.0 - TICK_MS / 2000.0
        self._duck_h_m: float | None = None  # measured on first mascot entry (ADR-0007)
        self.autopilot = None
        self.beak = BeakAnimator()  # mouth servo animation (ADR-0010)
        from duckdesk.platform.voice import Voice

        self.voice = Voice(self.settings)  # generated voice (ADR-0011)
        from duckdesk.platform.ears import DuckEars

        self.ears = DuckEars(self.settings, assets.assets_dir(), self)
        self.ears.heard.connect(self.on_voice_command)
        QTimer.singleShot(0, self.ears.start)  # model load off the boot path
        self._kick_flip = False  # 'chuta' alternates legs (05 §6)
        self._voice_walk = 0  # 'anda/vem' forward impulse, control steps left
        self._bye = False
        self._rng = np.random.default_rng()
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
        # mascot housekeeping timers (05 sections 1-2)
        self._taskbar_timer = QTimer(self)
        self._taskbar_timer.setInterval(1000)
        self._taskbar_timer.timeout.connect(self.on_taskbar_timer)
        self._taskbar_timer.start()
        self._band_timer = QTimer(self)
        self._band_timer.setInterval(2000)
        self._band_timer.timeout.connect(self.on_band_poll)
        self._band_timer.start()

    # --- main loop ------------------------------------------------------------

    def _tick(self) -> None:
        now = time.perf_counter()
        if self.mascot is not None:
            self._tick_mascot(now)
            return
        n = self.clock.steps_due(now - self._last)
        self._last = now
        for _ in range(n):
            cmd, requests, intents = self.keyboard.poll(CONTROL_DT)
            gp_twist, gp_head, gp_req, gp_int = self.gamepad.poll(CONTROL_DT)
            if gp_twist is not None:
                cmd.twist = gp_twist
            if gp_head is not None:
                self._head[:] = gp_head
            requests += gp_req
            intents += gp_int
            self._handle_intents(intents)
            for req in requests:
                self.on_request(req)
            cmd.head = self._head
            cmd.body = self._body
            if self._voice_walk:  # 'anda/vem' voice impulse (ADR-0012)
                cmd.twist[0] = 0.3
                self._voice_walk -= 1
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
            self.mgr.walk_policy_name + (" · controle" if self.gamepad.connected else ""),
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
                self.toggle_mascot()

    def on_request(self, req: Request) -> None:
        ok, msg = self.mgr.request(req, self.sim)
        if not ok:
            self.window.flash(msg)
        elif req is Request.PECK:
            self._vocalise(self.voice.play("peck"))  # robotd: pecking -> 'peck'

    def _vocalise(self, env) -> None:
        """Drive the beak with a played sound's envelope (lip-sync, ADR-0010)."""
        if env:
            self.beak.vocalise(env)

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

    def _clear_push(self) -> None:
        """Drop a pending push force (e.g. when leaving mascot mode)."""
        self._push_left = 0
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

    def open_simulator(self) -> None:
        """Tray 'Abrir simulador' (05 section 8): leave mascot mode first.

        Plain show_simulator() while the mascot is up raises a window whose
        viewport never renders — _tick keeps running the mascot loop because
        self.mascot is not None, so the simulator looks frozen."""
        if self.mascot is not None:
            self.exit_mascot()
        else:
            self.show_simulator()

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
        if self.autopilot is not None:
            self.autopilot.enabled = on

    def on_toggle_autopilot(self) -> None:
        """Toggle autopilot from the duck wheel, keeping the tray check in sync."""
        on = not bool(self.settings["autopilot"])
        if self._tray_active:
            self.tray.act_autopilot.setChecked(on)  # toggled -> on_autopilot_toggled
        else:
            self.on_autopilot_toggled(on)

    def on_voice_toggled(self, on: bool) -> None:
        """Tray 'Voz do pato' (ADR-0011): flips the facade live — off cuts any
        held sound, on just re-arms the next play."""
        self.settings["voice"] = on
        self.voice.enabled = on and self.voice._bank is not None
        if not on:
            self.voice.wheee_end()  # a held ride lands immediately
            from duckdesk.platform.voice import winsound

            if winsound is not None:
                try:
                    winsound.PlaySound(None, 0)  # stop, not purge: leave the OS be
                except OSError:
                    pass

    def on_ears_toggled(self, on: bool) -> None:
        """Tray 'Ouvido do pato' (ADR-0012): grabs/releases the mic live."""
        self.settings["ears"] = on
        self.ears.set_enabled(on)

    def on_voice_command(self, phrase: str) -> None:
        """A recognized pt-BR phrase -> the same path clicks/keys take.

        Commands are semantic (brain/voice_commands); every accepted one gets
        a tiny beak blip as the 'heard you' ack, then routes to the matching
        handler — nothing here touches the policy bridge (regra 1)."""
        from duckdesk.brain.voice_commands import resolve

        cmd = resolve(phrase)
        if cmd is None:
            return
        log.info("ouvido: %r -> %s", phrase, cmd)
        self.beak.vocalise(((0.0, 0.45), (0.12, 0.0)))  # 'heard you' blip
        if cmd == "sit":
            self.on_request(Request.SIT)
        elif cmd == "stand":
            self.on_request(Request.STAND)
        elif cmd == "walk":
            if self.mascot is not None:
                self.on_autopilot_toggled(True)
            else:
                self._voice_walk = int(2.0 / CONTROL_DT)
        elif cmd == "stop":
            if self.mascot is not None:
                self.on_autopilot_toggled(False)
            else:
                self._voice_walk = 0  # cancel a pending impulse
        elif cmd == "come":
            if self.mascot is not None:
                self.on_autopilot_toggled(True)  # he wanders over by himself
            else:
                self._voice_walk = int(3.0 / CONTROL_DT)
        elif cmd == "roll":
            self.on_request(Request.ROLL)
        elif cmd == "peck":
            self.on_request(Request.PECK)
        elif cmd == "kick":
            self.on_request(Request.KICK_R if self._kick_flip else Request.KICK_L)
            self._kick_flip = not self._kick_flip
        elif cmd == "chirp":
            self._vocalise(self.voice.play("chirp"))
        elif cmd == "sleep":
            self.on_request(Request.SIT)
            self.beak.yawn()
            self._vocalise(self.voice.play("coo"))
        elif cmd == "look":
            self._head[2] = 0.6 * float(self._rng.choice((-1.0, 1.0)))
            self._vocalise(self.voice.play("inquire"))
        elif cmd == "poke":  # bare 'pato' — attention ack
            self._vocalise(self.voice.play("inquire"))
        elif cmd == "bye":
            self.on_request(Request.PECK)  # the goodbye (robotd shutdown ritual)

    def on_size_changed(self, scale: float) -> None:
        self.settings["mascot_scale"] = scale
        if self.mascot is not None:
            # rebuild window/mapping at the new size (05 section 2)
            self.exit_mascot()
            self.enter_mascot()

    def on_autostart_toggled(self, on: bool) -> None:
        from duckdesk.platform import autostart

        try:
            autostart.set_enabled(on)
            self.settings["autostart"] = on
        except OSError as e:
            log.error("falha ao escrever autostart: %s", e)
            self.window.flash("não foi possível alterar a inicialização")

    def on_mic_test(self) -> None:
        """Ajuda > Testar microfone: device list, level meter, recognition."""
        from duckdesk.ui.mic_test import MicTestDialog

        MicTestDialog(
            self.ears, assets.assets_dir(), Path(self.settings.path).parent, self.window
        ).exec()

    def on_about(self) -> None:
        from duckdesk.ui.about import AboutDialog

        AboutDialog(self.window).exec()

    def on_quit(self) -> None:
        self._close_duck_wheel()
        delay_ms = 0
        if not self._bye:
            self._bye = True  # robotd: 'peck' says goodbye before shutdown
            if self.voice.play("peck") is not None:
                delay_ms = 350  # let the goodbye play out
        self.timer.stop()
        if self.mascot is not None:
            self.settings["mascot_last_x"] = float(self.sim.trunk_pos()[0])
            self.settings["last_mode"] = "mascot"
        else:
            self.settings["last_mode"] = "simulator"
        self._save_geometry()
        QTimer.singleShot(delay_ms, self._finish_quit)

    def _finish_quit(self) -> None:
        """Audio teardown, then quit — runs after the goodbye peck's head start."""
        from duckdesk.platform import sound

        sound.close()  # release the MCI quack alias
        self.voice.close()  # winsound purge + waveOut
        self.ears.close()  # release the mic (ADR-0012)
        self.app.quit()

    # --- mascot mode (docs/05) ---------------------------------------------------

    def _mascot_band(self):
        """Poll taskbar + work area, rebuild the band/mapping (05 section 1)."""
        from PySide6.QtGui import QGuiApplication

        from duckdesk.platform import win_taskbar
        from duckdesk.platform.mascot_map import H_M, Dpi, MascotMapping, compute_band

        screen = QGuiApplication.primaryScreen()
        dpi = Dpi(screen.devicePixelRatio())
        wa = screen.availableGeometry()
        band = compute_band(
            win_taskbar.get_taskbar_rect(),
            (wa.left(), wa.top(), wa.right() + 1, wa.bottom() + 1),
            dpi,
            win_taskbar.taskbar_autohide(),
        )
        if band.hidden:
            log.info("barra oculta/topo/lateral — modo degradado (chão = base da área de trabalho)")
        from duckdesk.render.mascot import camera_axes

        # 05 section 2: the menu sizes (80/120/180) are the DUCK height H; the
        # window is S = 1.6 * H. Using 120 as S made the duck ~75 px tall.
        size = round(1.6 * float(self.settings["mascot_scale"]) * 120)
        _, right, _ = camera_axes()
        self.mascot_map = MascotMapping(
            band, size, h_m=self._duck_h_m or H_M, right=(float(right[0]), float(right[1]))
        )
        if self.autopilot is not None:
            self.autopilot.x_min, self.autopilot.x_max = (
                self.mascot_map.x_min,
                self.mascot_map.x_max,
            )
        return band

    def enter_mascot(self) -> None:
        """04 section 7 / 05 section 4: reset at mascot_last_x, ball parked,
        autopilot from IDLE."""
        from duckdesk.brain.autopilot import Autopilot
        from duckdesk.platform.mascot_map import MARGIN_FRAC
        from duckdesk.render.mascot import MascotRenderer, duck_screen_height_m
        from duckdesk.ui.mascot_window import MascotWindow

        if self._duck_h_m is None:
            # ADR-0007: ground -> top of head as the mascot camera sees it,
            # measured from the meshes in the standing pose (not trunk z).
            self.sim.reset()
            self._duck_h_m = duck_screen_height_m(self.sim.model, self.sim.data.qpos)
            log.info("altura do pato na tela: %.3f m", self._duck_h_m)
        self._mascot_band()
        mm = self.mascot_map
        last_x = mm.clamp_x(float(self.settings["mascot_last_x"]))
        # Always spawn facing the viewer: the camera sits at azimuth 140, so
        # the duck's front reads best in the yaw range [-0.7, 0] (ADR-0009).
        yaw = -0.7 * float(self._rng.random())
        self.mgr.request(Request.RESET, self.sim)
        self.sim.data.qpos[self.sim.trunk_qpos_adr] = last_x
        self._place_yaw(yaw)  # quaternion + mj_forward
        self.sim.park_ball()

        self.autopilot = Autopilot(
            np.random.default_rng(),
            x_range=(mm.x_min, mm.x_max),
            enabled=bool(self.settings["autopilot"]),
            beak=self.beak,
            voice=self.voice,  # alarm on falls, coo on yawns, inquire on glances
        )
        screen = self.window.screen()
        # 05 section 9: the renderer draws at 2x this and box-filters down
        size_phys = round(mm.S * screen.devicePixelRatio())
        self._mascot_renderer = MascotRenderer(self.sim.model, size_phys)
        self.mascot = MascotWindow(mm.S)
        m = round(MARGIN_FRAC * mm.S)
        self._mascot_margin = m
        self.mascot.move(round(mm.band.center), round(mm.window_top(m)))
        self._wire_mascot()
        self.mascot.show()
        self.window.hide()
        self.settings["last_mode"] = "mascot"
        if self._tray_active:
            self.tray.act_mascot.setText("Esconder pato")
        log.info("modo mascote: S=%dpx, faixa x=[%.2f, %.2f] m", mm.S, mm.x_min, mm.x_max)
        self._vocalise(self.voice.play("greet"))  # robotd: 'greet' at wake-up

    def _place_yaw(self, yaw: float) -> None:
        jid = mujoco.mj_name2id(self.sim.model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
        adr = self.sim.model.jnt_qposadr[jid]
        self.sim.data.qpos[adr + 3 : adr + 7] = (np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2))
        mujoco.mj_forward(self.sim.model, self.sim.data)

    def exit_mascot(self) -> None:
        """05 section 8: no reset — the duck continues where it is."""
        self._close_duck_wheel()
        self._clear_push()
        self.voice.wheee_end()  # a ride in progress lands
        self.beak.stop()
        self.sim.set_beak(0.0)  # mouth shut again in the simulator
        self.settings["mascot_last_x"] = float(self.sim.trunk_pos()[0])
        if self.mascot is not None:
            self.mascot.hide()
            self.mascot.deleteLater()
        self.mascot = None
        if self._mascot_renderer is not None:
            self._mascot_renderer.close()  # free the GL context
        self._mascot_renderer = None
        self.autopilot = None
        self.keyboard = KeyboardMapper()  # command starts at zero (05 section 8)
        self.gamepad = GamepadMapper()  # ... and so do held pad buttons
        self.settings["last_mode"] = "simulator"
        if self._tray_active:
            self.tray.act_mascot.setText("Mostrar pato na barra")
        self.show_simulator()
        self._last = time.perf_counter()

    def toggle_mascot(self) -> None:
        if self.mascot is None:
            self.enter_mascot()
        else:
            self.exit_mascot()

    def _wire_mascot(self) -> None:
        w = self.mascot
        w.clicked.connect(self._mascot_click)
        w.double_clicked.connect(self._mascot_double_click)  # "Quack! Quack!" (05 §6)
        w.right_clicked.connect(self._show_duck_wheel)  # wheel, not the tray menu (05 §11)
        w.drag_started.connect(self._mascot_drag_start)
        w.drag_moved.connect(self._mascot_drag_move)
        w.drag_finished.connect(self._mascot_drag_finish)

    # --- duck action wheel (05 section 11) -----------------------------------

    def _duck_head_global(self) -> QPoint:
        """Global top-centre of the duck's head; the wheel hangs just above it."""
        mascot = self.mascot
        if mascot is None:
            return QPoint()
        local = mascot.duck_head_point()
        if local is None:  # before the first frame: standing layout of 05 section 3
            mm = self.mascot_map
            local = QPoint(
                mascot.width() // 2,
                round(mm.S - self._mascot_margin - mm.S / 1.6),
            )
        return mascot.mapToGlobal(local)

    def duck_wheel_actions(self) -> list[WheelAction]:
        """Sectors clockwise from 12 o'clock; labels reflect the current state."""
        seated, busy = self.mgr.seated, self.mgr.busy
        can_act = not seated and not busy
        autopilot_on = bool(self.settings["autopilot"])
        return [
            WheelAction("Bicar", lambda: self.on_request(Request.PECK), enabled=can_act),
            WheelAction("Cambalhota", lambda: self.on_request(Request.ROLL), enabled=can_act),
            WheelAction("Levantar" if seated else "Sentar", self.on_toggle_sit, enabled=not busy),
            WheelAction("Empurrar", self.on_push),
            WheelAction("Continuar" if self.clock.paused else "Pausar", self.on_toggle_pause),
            WheelAction(
                "Piloto\nligado" if autopilot_on else "Piloto\ndesligado",
                self.on_toggle_autopilot,
            ),
            WheelAction("Abrir\nsimulador", self.exit_mascot),
            WheelAction("Sair", self.on_quit),
        ]

    def _show_duck_wheel(self, _global_pos: QPoint) -> None:
        """Right click on the duck: radial wheel above its head, not the tray menu."""
        if self.mascot is None:
            return
        if self._radial_menu is None:
            self._radial_menu = RadialMenu()
        self._radial_menu.set_actions(self.duck_wheel_actions(), radius_for_duck(self.mascot_map.S))
        self._radial_menu.popup_above(self._duck_head_global())

    def _close_duck_wheel(self) -> None:
        """05 section 11: hide the wheel; it is reused, never deleted.

        Never deleteLater() here: destroying this Python-subclassed popup while
        its Qt grab/event-filter state unwinds corrupts the interpreter —
        duckdesk.app.__dict__ was emptied, every _tick then died on NameError
        and the app froze (repro: scripts/probe_wheel_death.py)."""
        if self._radial_menu is not None:
            self._radial_menu.hide()  # == close(): WA_DeleteOnClose is not set

    def _tick_mascot(self, now: float) -> None:
        n = self.clock.steps_due(now - self._last)
        self._last = now
        if self._dragging_duck or self._fullscreen_hidden:
            return  # paused while dragged or a fullscreen app holds the screen
        for _ in range(n):
            if self.autopilot is not None:
                x, y = (float(v) for v in self.sim.trunk_pos()[:2])
                # The 3/4 camera shifts the duck sideways with depth, so the
                # usable x range depends on y (05 section 3).
                self.autopilot.x_min, self.autopilot.x_max = self.mascot_map.x_limits_for_y(y)
                self.autopilot.update(
                    CONTROL_DT,
                    x,
                    y,
                    self.sim.trunk_yaw(),
                    self.sim.trunk_tilt(),
                    self.mgr,
                )
            targets = self.mgr.step(self.sim)
            self.sim.step_control(targets)
            self.sim.set_beak(self.beak.mouth)  # beak pose (ADR-0010)
            self._apply_push(CONTROL_DT)  # same 0.1 s push as the simulator (04 §5)
            event = self.watchdog.check(self.sim, CONTROL_DT)
            if event:
                self.mgr.request(Request.RESET, self.sim)
        # keep the duck inside the band (05 section 4), depth-aware (3/4 camera)
        x, y = (float(v) for v in self.sim.trunk_pos()[:2])
        x_min, x_max = self.mascot_map.x_limits_for_y(y)
        if x < x_min - 0.05 or x > x_max + 0.05:
            self._soft_clamp()

        # 30 fps always: below that the gait reads as stutter (ADR-0007).
        if now - self._last_mascot_frame < self._mascot_fps_cap:
            return
        self._last_mascot_frame = now
        self._render_mascot_frame()

    def _soft_clamp(self) -> None:
        """Soft reset 0.1 m inside the nearest band edge (05 section 4).

        The limits come from the current depth: in the 3/4 view, y shifts the
        duck sideways, so the world edge is not at the y = 0 value.
        """
        mm = self.mascot_map
        x = float(self.sim.trunk_pos()[0])
        y = float(self.sim.trunk_pos()[1])
        x_min, x_max = mm.x_limits_for_y(y)
        inside = x_min + 0.1 if x < x_min else x_max - 0.1
        jid = mujoco.mj_name2id(self.sim.model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
        adr = self.sim.model.jnt_qposadr[jid]
        self.sim.data.qpos[adr] = inside
        mujoco.mj_forward(self.sim.model, self.sim.data)

    def _render_mascot_frame(self) -> None:
        mm = self.mascot_map
        rend = self._mascot_renderer
        x, y, _ = (float(v) for v in self.sim.trunk_pos())
        ground = np.array([x, y, 0.0])  # ground point under the trunk
        exact = mm.screen_x(x, y)  # logical px of the duck on screen
        # Hard clamp to the band: with the 3/4 camera, depth (pushes, falls,
        # rolls) shifts the duck sideways. The window must never leave the
        # monitor, so the duck is pinned at the edge instead.
        band = mm.band
        draw = min(max(exact, band.left + mm.S / 2), band.right - mm.S / 2)
        left = round(draw - mm.S / 2)  # windows sit on whole pixels
        # Shift the camera by the rounding remainder (and by any clamping) so
        # the duck lands at the intended position inside the window: the window
        # steps in whole pixels, the image compensates, nothing trembles
        # (ADR-0005).
        delta_px = (left + mm.S / 2) - exact
        lookat = (
            ground
            + rend.right * (delta_px / mm.ppm)
            + rend.up * ((mm.S / 2 - self._mascot_margin) / mm.ppm)
        )
        rend.set_view_height(mm.ortho_height_m())
        frame = rend.frame(self.sim.data, lookat)
        top = round(mm.window_top(self._mascot_margin)) - self._drag_lift
        if (left, top) != (self.mascot.x(), self.mascot.y()):
            self.mascot.move(left, top)
        self.mascot.set_frame(frame)

    def _mascot_double_click(self) -> None:
        """Double click: the generated 'chirp' — this install's own voice
        (05 §6, ADR-0011); the bundled MP3 is the silent-PC fallback."""
        env = self.voice.play("chirp")
        if env:
            self.beak.vocalise(env)
        else:
            from duckdesk.platform.sound import quack_quack

            quack_quack()
            self.beak.quack()

    def _mascot_click(self, _pos) -> None:
        if self.autopilot is None:
            return
        self.autopilot.poke()  # any motion wakes it (idle_head.rs)
        r = float(self._rng.random())
        if r < 0.40:
            self.on_request(Request.PECK)
        elif r < 0.70:
            self.on_toggle_sit()
        elif r < 0.85:
            self.on_request(Request.ROLL)
        else:  # look toward the cursor for 2 s (05 section 6)
            side = 1.0 if _pos.x() > self.mascot.width() / 2 else -1.0
            self._head[2] = 0.6 * side  # head_yaw
            self._vocalise(self.voice.play("inquire"))  # curious -> 'inquire'

    def _mascot_drag_start(self) -> None:
        self._dragging_duck = True
        self.voice.wheee_start()  # the held-ride loop (robotd 'wheee')
        if self.autopilot is not None:
            self.autopilot.poke()

    def _mascot_drag_move(self, pos) -> None:
        """Window follows the cursor horizontally, up to 200 px up (05 section 6)."""
        mm = self.mascot_map
        base_top = round(mm.window_top(self._mascot_margin))
        self._drag_lift = max(0, min(200, base_top - pos.y()))
        left = pos.x() - mm.S // 2
        # A drag must not park the window off-screen; clamp to the taskbar band.
        left = min(max(left, round(mm.band.left)), round(mm.band.right) - mm.S)
        self.mascot.move(left, base_top - self._drag_lift)

    def _mascot_drag_finish(self, pos) -> None:
        self._dragging_duck = False
        self._drag_lift = 0
        self.voice.wheee_end()  # cut the loop, play the landing
        x = self.mascot_map.clamp_x(self.mascot_map.world_x(pos.x()))
        yaw = self.sim.trunk_yaw()  # land facing the same way (05 section 6)
        self.mgr.request(Request.RESET, self.sim)
        self.sim.data.qpos[self.sim.trunk_qpos_adr] = x
        self._place_yaw(yaw)  # quaternion + mj_forward
        self.sim.park_ball()

    def on_taskbar_timer(self) -> None:
        """1 s: reassert TOPMOST + hide under fullscreen apps (05 section 2)."""
        if self.mascot is None:
            return
        from duckdesk.platform import win_topmost

        win_topmost.reassert_topmost(int(self.mascot.winId()))
        full = win_topmost.fullscreen_app_active()
        if full != self._fullscreen_hidden:
            self._fullscreen_hidden = full
            self.mascot.setVisible(not full)

    def on_band_poll(self) -> None:
        """2 s: taskbar rect / work area changes (05 section 1)."""
        if self.mascot is None:
            return
        self._mascot_band()

    # --- geometry persistence ---------------------------------------------------

    def _restore_geometry(self) -> None:
        blob = self.settings["window_geometry"]
        if blob:
            self.window.restoreGeometry(QByteArray.fromBase64(blob.encode()))

    def _save_geometry(self) -> None:
        self.settings["window_geometry"] = bytes(self.window.saveGeometry().toBase64()).decode()


def mujoco_flag(name: str):
    return getattr(mujoco.mjtVisFlag, f"mjVIS_{name}")


def _install_sigint(controller) -> None:
    """Ctrl+C in the launching terminal quits through on_quit (saves last_mode
    / geometry / closes the MCI alias). The Python handler runs as soon as
    the interpreter wakes — the 8 ms sim timer guarantees that."""
    signal.signal(signal.SIGINT, lambda _sig, _frame: controller.on_quit())


def run(argv=None) -> int:
    app = QApplication(argv or sys.argv)
    app.setWindowIcon(QIcon(str(assets.assets_dir() / "icons" / "duckdesk.png")))
    app.setQuitOnLastWindowClosed(False)  # tray keeps it alive
    if notify_existing_instance():
        return 0  # second launch: existing instance comes forward
    controller = AppController(app)
    _install_sigint(controller)
    controller.log_file = setup_logging(controller.settings)
    log.info("DuckDesk iniciando (modo=%s)", controller.settings["last_mode"])
    controller._instance_server = listen_for_raise(controller)
    controller.window.show()
    if controller.settings["last_mode"] == "mascot":
        controller.enter_mascot()  # restores the taskbar duck (hides the sim window)
    return app.exec()
