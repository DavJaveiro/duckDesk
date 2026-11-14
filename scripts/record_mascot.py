"""M5 visual evidence: captures the REAL taskbar while the mascot walks.

Run on the real desktop (NOT offscreen):
    uv run python scripts/record_mascot.py docs/relatorios/midia/m5_demo.mp4

For the 150 % DPI still (acceptance shot), run with:
    set QT_SCALE_FACTOR=1.5 && uv run python scripts/record_mascot.py out.mp4 --seconds 12
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import ImageGrab
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

SECONDS = float(next((a for a in sys.argv[1:] if a.replace(".", "").isdigit()), 35))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("m5_demo.mp4")
FPS = 8


def main() -> int:
    app = QApplication(sys.argv)
    from duckdesk.app import AppController
    from duckdesk.platform import win_taskbar

    ctrl = AppController(app)
    ctrl.enter_mascot()

    tb = win_taskbar.get_taskbar_rect() or (0, 1040, 2560, 1080)
    top = max(0, tb[1] - 200)  # mascot window + strip above the taskbar
    box = (0, top, 2560, 1080)
    frames: list[np.ndarray] = []
    stop = threading.Event()

    def grab() -> None:
        t0 = time.perf_counter()
        n = int(SECONDS * FPS)
        for _ in range(n):
            if stop.is_set():
                break
            im = ImageGrab.grab(bbox=box)
            frames.append(np.asarray(im))
            time.sleep(max(0.0, 1.0 / FPS - (time.perf_counter() - t0) % (1.0 / FPS)))

    th = threading.Thread(target=grab, daemon=True)
    th.start()
    QTimer.singleShot(int((SECONDS + 2) * 1000), app.quit)
    app.exec()
    th.join(timeout=5)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(str(OUT), fps=FPS, macro_block_size=16)
    for f in frames:
        writer.append_data(np.ascontiguousarray(f[..., :3]))
    writer.close()
    for i, frac in enumerate((0.25, 0.5, 0.75, 0.95)):
        if frames:
            idx = min(len(frames) - 1, int(len(frames) * frac))
            imageio.imwrite(str(OUT.with_suffix(f".f{i}.png")), frames[idx])
    print(f"{len(frames)} frames -> {OUT} (dpr={app.primaryScreen().devicePixelRatio()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
