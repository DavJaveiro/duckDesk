"""Mascot window (docs/05 sections 2 and 6): transparent, never steals focus,
click-through on transparent pixels (WM_NCHITTEST -> HTTRANSPARENT)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1


class MascotWindow(QWidget):
    clicked = Signal(QPoint)  # left click on the duck (widget coords)
    double_clicked = Signal()
    right_clicked = Signal(QPoint)  # global pos -> controller shows tray menu
    drag_started = Signal()
    drag_moved = Signal(QPoint)  # global pos
    drag_finished = Signal(QPoint)  # global pos

    def __init__(self, size_px: int, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(size_px, size_px)
        self._frame: QImage | None = None
        self._alpha: np.ndarray | None = None  # (S,S) uint8 of last frame
        self._drag_origin: QPoint | None = None
        self._dragging = False

        # WS_EX_NOACTIVATE so clicks never take focus (05 section 2)
        import ctypes

        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x08000000)  # WS_EX_NOACTIVATE

    def set_frame(self, bgra: np.ndarray) -> None:
        """(S,S,4) uint8 premultiplied BGRA from MascotRenderer.downsample."""
        h, w, _ = bgra.shape
        self._alpha = bgra[..., 3].copy()
        img = QImage(bgra.data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(w / self.width())  # physical -> logical size
        self._frame = img.copy()  # own the buffer
        self.update()

    def paintEvent(self, _ev) -> None:
        if self._frame is not None:
            QPainter(self).drawImage(0, 0, self._frame)

    def _over_duck(self, pos: QPoint) -> bool:
        if self._alpha is None:
            return False
        scale = self._alpha.shape[0] / self.width()  # physical per logical px
        x, y = int(pos.x() * scale), int(pos.y() * scale)
        if not (0 <= x < self._alpha.shape[1] and 0 <= y < self._alpha.shape[0]):
            return False
        return self._alpha[y, x] > 0

    # Windows layered windows let clicks fall through alpha=0 pixels natively
    # (05 section 2); if that ever fails the fallback is WM_NCHITTEST->HTTRANSPARENT.

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton:
            self._drag_origin = ev.globalPosition().toPoint()
        elif ev.button() == Qt.RightButton:
            self.right_clicked.emit(ev.globalPosition().toPoint())

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        cur = ev.globalPosition().toPoint()
        if (cur - self._drag_origin).manhattanLength() > 6:
            if not self._dragging:
                self._dragging = True
                self.drag_started.emit()
            self.drag_moved.emit(cur)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.LeftButton or self._drag_origin is None:
            return
        if self._dragging:
            self.drag_finished.emit(ev.globalPosition().toPoint())
        else:
            self.clicked.emit(ev.position().toPoint())
        self._drag_origin = None
        self._dragging = False

    def mouseDoubleClickEvent(self, _ev) -> None:
        self.double_clicked.emit()
