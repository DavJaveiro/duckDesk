"""Radial action wheel for the mascot duck (docs/05 section 11, ADR-0008).

Right-clicking the duck opens this wheel just above its head instead of the
native QMenu: the native menu now belongs to the system-tray icon only
(05 section 7). The wheel is a top-level ``QWidget`` with ``Qt.Popup``, so it
lives on the same Qt thread (ADR-0003), grabs the mouse like a real menu and
closes on Escape, on the centre button or on a click outside.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

MAX_ACTIONS = 8  # 45 deg sectors; more than that does not fit with legible labels
WHEEL_RADIUS_MIN = 100
WHEEL_RADIUS_MAX = 128
RADIUS_FRAC = 0.62  # of the mascot window side S (05 section 2)
SHADOW_PAD = 10  # transparent border around the wheel (drop shadow)
SCREEN_MARGIN = 8
GAP_ABOVE_HEAD = 10  # px between the wheel bottom and the top of the head
HUB_FRAC = 0.30  # centre button (close) radius, fraction of the wheel radius
LABEL_FRAC = 0.60  # label distance between hub and rim
SECTOR_GAP_DEG = 1.6  # transparent slit between neighbouring sectors
MIN_FONT_PT = 6.5
MAX_FONT_PT = 9.0

# DuckDesk palette: warm off-white like the duck's shell, amber like its feet.
_BASE = QColor(255, 251, 240, 246)
_BASE_DISABLED = QColor(228, 223, 211, 235)
_BASE_HOVER = QColor(250, 197, 84, 252)
_DISABLED_HOVER = QColor(216, 210, 196, 240)
_TEXT = QColor(58, 47, 28)
_TEXT_DISABLED = QColor(150, 142, 126)
_TEXT_HOVER = QColor(46, 35, 12)
_RIM = QColor(145, 112, 46, 200)
_HUB = QColor(56, 47, 30, 245)
_HUB_HOVER = QColor(224, 92, 64, 250)
_CLOSE_GLYPH = QColor(255, 248, 232)


@dataclass(frozen=True)
class WheelAction:
    """One sector of the wheel. ``label`` is pt-BR UI text; ``\\n`` breaks a line."""

    label: str
    callback: Callable[[], None]
    enabled: bool = True


def radius_for_duck(window_px: int) -> int:
    """Wheel radius (logical px) for a mascot window side S (05 section 2)."""
    return max(WHEEL_RADIUS_MIN, min(WHEEL_RADIUS_MAX, round(RADIUS_FRAC * window_px)))


def sector_index_at(
    dx: float, dy: float, count: int, hub_radius: float, radius: float
) -> int | None:
    """Sector under (dx, dy) relative to the wheel centre, or None outside it.

    Sector 0 is centred at 12 o'clock; the others follow clockwise. The hub
    (centre button) and everything outside the rim return None.
    """
    if count <= 0:
        return None
    distance = math.hypot(dx, dy)
    if distance < hub_radius or distance > radius:
        return None
    step = 360.0 / count
    # atan2 gives -90 at 12 o'clock and grows clockwise on screen coords.
    angle = (math.degrees(math.atan2(dy, dx)) + 90.0 + step / 2.0) % 360.0
    return int(angle // step) % count


def wheel_topleft(
    anchor: QPoint,
    radius: int,
    screen: QRect,
    gap: int = GAP_ABOVE_HEAD,
    pad: int = SHADOW_PAD,
    margin: int = SCREEN_MARGIN,
) -> QPoint:
    """Top-left for a wheel whose visible bottom sits ``gap`` px above ``anchor``.

    ``anchor`` is the top-centre of the duck's head in global logical pixels.
    The result is clamped to the screen's available geometry (no taskbar), so
    the wheel never leaves the monitor; clamped positions may overlap the head.
    """
    side = 2 * (radius + pad)
    x = anchor.x() - side // 2
    y = anchor.y() - gap - 2 * radius - pad
    return QPoint(
        _clamp(x, screen.left() + margin, screen.right() + 1 - side - margin),
        _clamp(y, screen.top() + margin, screen.bottom() + 1 - side - margin),
    )


def _clamp(value: int, low: int, high: int) -> int:
    if high < low:
        return low
    return max(low, min(high, value))


class RadialMenu(QWidget):
    """Eight-sector action wheel; the centre button closes it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._actions: list[WheelAction] = []
        self._radius = WHEEL_RADIUS_MIN
        self._hub = round(WHEEL_RADIUS_MIN * HUB_FRAC)
        self._hover_action: int | None = None
        self._hover_close = False
        self._filtering = False
        self._apply_size()

    # --- public API -----------------------------------------------------------

    @property
    def actions(self) -> list[WheelAction]:
        return list(self._actions)

    @property
    def radius(self) -> int:
        return self._radius

    @property
    def hub_radius(self) -> int:
        return self._hub

    @property
    def hovered_action(self) -> int | None:
        return self._hover_action

    @property
    def hovered_close(self) -> bool:
        return self._hover_close

    def set_actions(self, actions: list[WheelAction], radius: int) -> None:
        """Replace the sectors and (re)size the wheel. Reused between openings."""
        if len(actions) > MAX_ACTIONS:
            raise ValueError(f"a roda aceita no máximo {MAX_ACTIONS} ações")
        self._actions = list(actions)
        self._radius = max(WHEEL_RADIUS_MIN, min(WHEEL_RADIUS_MAX, int(radius)))
        self._hub = round(self._radius * HUB_FRAC)
        self._apply_size()
        self._set_hover(None, False)
        self.update()

    def popup_above(self, anchor: QPoint) -> None:
        """Show the wheel centred on ``anchor``, with its bottom just above it."""
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.move(wheel_topleft(anchor, self._radius, screen.availableGeometry()))
        self.show()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def sector_at(self, pos: QPoint) -> int | None:
        """Sector under widget-local ``pos`` (None on the hub or outside the rim)."""
        return sector_index_at(
            pos.x() - self.width() / 2.0,
            pos.y() - self.height() / 2.0,
            len(self._actions),
            self._hub,
            self._radius,
        )

    def is_close_hit(self, pos: QPoint) -> bool:
        dx = pos.x() - self.width() / 2.0
        dy = pos.y() - self.height() / 2.0
        return math.hypot(dx, dy) <= self._hub

    # --- geometry / painting ---------------------------------------------------

    def _apply_size(self) -> None:
        side = 2 * (self._radius + SHADOW_PAD)
        self.setFixedSize(side, side)

    def _centre(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _activate(self, index: int) -> None:
        action = self._actions[index]
        self.close()  # hide first: the callback may open windows or quit the app
        # Defer the callback out of mousePressEvent: actions like exit_mascot
        # deleteLater() this very widget — running them inside the click that
        # triggered them leaves a Qt popup grab/event stack half-unwound (the
        # interpreter ended up with a gutted module dict and a frozen app).
        QTimer.singleShot(0, action.callback)

    def paintEvent(self, _ev) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        centre = self._centre()
        radius = float(self._radius)
        hub = float(self._hub)

        self._paint_shadow(painter, centre, radius)
        count = len(self._actions)
        if count:
            step = 360.0 / count
            gap = SECTOR_GAP_DEG if count > 1 else 0.0
            for index, action in enumerate(self._actions):
                start = -90.0 + index * step - step / 2.0 + gap / 2.0
                path = self._sector_path(centre, hub + 2.0, radius, start, step - gap)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._sector_colour(index, action))
                painter.drawPath(path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_RIM, 1.5))
            painter.drawEllipse(centre, radius, radius)

        painter.setPen(QPen(QColor(80, 62, 28, 220), 1.5))
        painter.setBrush(_HUB_HOVER if self._hover_close else _HUB)
        painter.drawEllipse(centre, hub, hub)
        self._paint_close_glyph(painter, centre, hub)
        if count:
            self._paint_labels(painter, centre)

    def _paint_shadow(self, painter: QPainter, centre: QPointF, radius: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for extra, alpha in ((9, 14), (6, 18), (3, 22)):
            painter.setBrush(QColor(20, 16, 8, alpha))
            painter.drawEllipse(centre + QPointF(0, 4), radius + extra, radius + extra)

    def _sector_colour(self, index: int, action: WheelAction) -> QColor:
        hovered = index == self._hover_action
        if not action.enabled:
            return _DISABLED_HOVER if hovered else _BASE_DISABLED
        return _BASE_HOVER if hovered else _BASE

    def _paint_close_glyph(self, painter: QPainter, centre: QPointF, hub: float) -> None:
        painter.setPen(QPen(_CLOSE_GLYPH, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        d = hub * 0.34
        painter.drawLine(centre + QPointF(-d, -d), centre + QPointF(d, d))
        painter.drawLine(centre + QPointF(-d, d), centre + QPointF(d, -d))

    def _paint_labels(self, painter: QPainter, centre: QPointF) -> None:
        count = len(self._actions)
        step = 360.0 / count
        label_radius = self._hub + (self._radius - self._hub) * LABEL_FRAC
        max_width = 2.0 * label_radius * math.sin(math.radians(step) / 2.0) - 8.0
        for index, action in enumerate(self._actions):
            mid = -90.0 + index * step
            angle = math.radians(mid)
            tx = centre.x() + label_radius * math.cos(angle)
            ty = centre.y() + label_radius * math.sin(angle)
            lines = action.label.split("\n")
            font = self._fit_font(lines, max_width)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            line_height = metrics.height()
            top = ty - line_height * len(lines) / 2.0
            painter.setPen(self._label_colour(index, action))
            for line in lines:
                rect = QRectF(tx - self._radius, top, 2.0 * self._radius, line_height)
                painter.drawText(
                    rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, line
                )
                top += line_height

    def _label_colour(self, index: int, action: WheelAction) -> QColor:
        if not action.enabled:
            return _TEXT_DISABLED
        if index == self._hover_action:
            return _TEXT_HOVER
        return _TEXT

    def _fit_font(self, lines: list[str], max_width: float) -> QFont:
        """Largest bold font up to MAX_FONT_PT whose widest line fits the sector."""
        point = MAX_FONT_PT
        while True:
            font = QFont("Segoe UI")
            font.setPointSizeF(point)
            font.setWeight(QFont.Weight.DemiBold)
            metrics = QFontMetricsF(font)
            widest = max(metrics.horizontalAdvance(line) for line in lines)
            if widest <= max_width or point <= MIN_FONT_PT:
                return font
            point -= 0.5

    @staticmethod
    def _sector_path(
        centre: QPointF,
        r_in: float,
        r_out: float,
        start_deg: float,
        span_deg: float,
        samples: int = 18,
    ) -> QPainterPath:
        """Annular sector between two radii, angles in screen coords (-90 = up)."""

        def point(radius: float, degrees: float) -> QPointF:
            theta = math.radians(degrees)
            return QPointF(
                centre.x() + radius * math.cos(theta), centre.y() + radius * math.sin(theta)
            )

        path = QPainterPath()
        path.moveTo(point(r_out, start_deg))
        for sample in range(1, samples + 1):
            path.lineTo(point(r_out, start_deg + span_deg * sample / samples))
        for sample in range(samples, -1, -1):
            path.lineTo(point(r_in, start_deg + span_deg * sample / samples))
        path.closeSubpath()
        return path

    # --- input ------------------------------------------------------------------

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            self.close()
            return
        pos = ev.position().toPoint()
        if self.is_close_hit(pos):
            self.close()
            return
        index = self.sector_at(pos)
        if index is None:  # shadow margin / outside the rim: dismiss like a menu
            self.close()
            return
        if self._actions[index].enabled:
            self._activate(index)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        self._update_hover(ev.position().toPoint())

    def leaveEvent(self, _ev) -> None:
        self._set_hover(None, False)

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _update_hover(self, pos: QPoint) -> None:
        close = self.is_close_hit(pos)
        self._set_hover(None if close else self.sector_at(pos), close)

    def _set_hover(self, index: int | None, close: bool) -> None:
        if (index, close) == (self._hover_action, self._hover_close):
            return
        self._hover_action = index
        self._hover_close = close
        self.update()

    # --- popup lifecycle ---------------------------------------------------------

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        app = QApplication.instance()
        if app is not None and not self._filtering:
            app.installEventFilter(self)
            self._filtering = True
        self._set_hover(None, False)

    def hideEvent(self, ev) -> None:
        app = QApplication.instance()
        if app is not None and self._filtering:
            app.removeEventFilter(self)
            self._filtering = False
        self._set_hover(None, False)
        super().hideEvent(ev)

    def eventFilter(self, obj, ev) -> bool:
        """Close on a click outside the wheel (Qt does the same for QMenu)."""
        if (
            ev.type() == QEvent.Type.MouseButtonPress
            and self.isVisible()
            and not self.frameGeometry().contains(ev.globalPosition().toPoint())
        ):
            self.close()
        return super().eventFilter(obj, ev)

    def event(self, ev) -> bool:
        # A menu disappears when its window loses activation (e.g. Alt+Tab).
        if ev.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            self.close()
        return super().event(ev)
