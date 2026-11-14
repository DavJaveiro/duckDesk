"""Record the simulator window demo (docs/04 acceptance #1): drives the real
AppController offscreen, performs every behavior, grabs window frames to MP4.

Run:  set QT_QPA_PLATFORM=offscreen && uv run python scripts/record_demo.py out.mp4
"""

from __future__ import annotations

import sys
import time

import imageio.v2 as imageio
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from duckdesk.app import AppController
from duckdesk.brain.commands import Request

FPS = 12  # capture rate; widget.grab() is CPU-bound, keep modest


def script(ctrl: AppController):
    """Timed action list: (t_seconds, callable)."""
    K = ctrl.on_key
    R = ctrl.on_request
    P = ctrl.on_pose_sliders
    z4 = np.zeros(4, dtype=np.float32)
    z6 = np.zeros(6, dtype=np.float32)

    return [
        (1.0, lambda: R(Request.STAND)),
        (2.0, lambda: K("w", True)),  # walk forward ~8s
        (10.0, lambda: K("w", False)),
        (10.5, lambda: K("a", True)),  # turn ~6s
        (16.0, lambda: K("a", False)),
        (16.5, lambda: K("q", True)),  # lateral step ~5s
        (21.0, lambda: K("q", False)),
        (22.0, lambda: R(Request.SIT)),
        (27.0, lambda: R(Request.STAND)),
        (32.0, lambda: R(Request.PECK)),
        (38.0, lambda: R(Request.ROLL)),
        (46.0, lambda: R(Request.KICK_L)),
        (52.0, lambda: R(Request.KICK_R)),
        (58.0, lambda: ctrl.on_push()),  # push + recovery
        (66.0, lambda: P(np.array([0.4, -0.3, 0.5, -0.2], dtype=np.float32), z6)),
        (72.0, lambda: P(z4, np.array([0.3, 0.2, -0.2, 0.3, -0.3, 0.2], dtype=np.float32))),
        (78.0, lambda: P(z4, z6)),  # sliders back to zero
    ]


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "m3_demo.mp4"
    app = QApplication(sys.argv)
    ctrl = AppController(app)
    ctrl.window.show()
    app.processEvents()

    actions = script(ctrl)
    idx = [0]
    t0 = [None]
    frames_done = [0]
    writer = imageio.get_writer(out, fps=FPS, macro_block_size=16)

    def grab():
        if t0[0] is None:
            t0[0] = time.perf_counter()
        el = time.perf_counter() - t0[0]
        if el > 86:
            writer.close()
            ctrl.on_quit()
            print(f"done: {frames_done[0]} frames -> {out}")
            return
        while idx[0] < len(actions) and actions[idx[0]][0] <= el:
            actions[idx[0]][1]()
            idx[0] += 1
        img = ctrl.window.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(img.height(), img.width(), 4)
        writer.append_data(np.ascontiguousarray(buf[..., :3]))
        frames_done[0] += 1

    timer = QTimer()
    timer.timeout.connect(grab)
    timer.start(int(1000 / FPS))
    app.exec()


if __name__ == "__main__":
    main()
