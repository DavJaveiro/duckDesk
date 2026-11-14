"""Radial action wheel tests (docs/05 section 11, ADR-0008).

The wheel is plain Qt: sector geometry, screen placement, click handling and
state labels are checked here under the offscreen platform. The end-to-end
wiring with the mascot window lives in ``test_simulator_window.py``.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from duckdesk.ui.radial_menu import (
    GAP_ABOVE_HEAD,
    MAX_ACTIONS,
    SHADOW_PAD,
    RadialMenu,
    WheelAction,
    radius_for_duck,
    sector_index_at,
    wheel_topleft,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    return app


def _wheel(*, radius: int = 119, disabled: tuple[int, ...] = ()):
    calls: list[int] = []
    actions = [
        WheelAction(f"A{i}", lambda i=i: calls.append(i), enabled=i not in disabled)
        for i in range(MAX_ACTIONS)
    ]
    menu = RadialMenu()
    menu.set_actions(actions, radius)
    return menu, calls


def _sector_point(menu: RadialMenu, index: int) -> QPoint:
    angle = math.radians(-90.0 + index * 360.0 / len(menu.actions))
    radius = (menu.hub_radius + menu.radius) / 2.0
    return QPoint(
        round(menu.width() / 2.0 + radius * math.cos(angle)),
        round(menu.height() / 2.0 + radius * math.sin(angle)),
    )


def _click(menu: RadialMenu, point: QPoint) -> None:
    QTest.mouseClick(menu, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)


# --- pure geometry ------------------------------------------------------------


def test_sector_index_each_sector_centre():
    for index in range(MAX_ACTIONS):
        angle = math.radians(-90.0 + index * 45.0)
        assert sector_index_at(65 * math.cos(angle), 65 * math.sin(angle), 8, 30, 100) == index


def test_sector_index_ignores_hub_and_outside():
    assert sector_index_at(0.0, 0.0, 8, 30, 100) is None  # centre button
    assert sector_index_at(29.0, 0.0, 8, 30, 100) is None  # just inside the hub
    assert sector_index_at(101.0, 0.0, 8, 30, 100) is None  # outside the rim
    assert sector_index_at(10.0, 10.0, 0, 30, 100) is None  # no actions


def test_radius_grows_with_the_duck():
    assert radius_for_duck(128) == 100  # Pequeno: clamped to the minimum
    assert radius_for_duck(192) == 119  # Médio
    assert radius_for_duck(288) == 128  # Grande: clamped to the maximum


def test_wheel_sits_above_the_anchor_and_is_centred():
    screen = QRect(0, 0, 1920, 1080)
    anchor = QPoint(960, 900)
    top = wheel_topleft(anchor, 110, screen)
    side = 2 * (110 + SHADOW_PAD)
    assert top.x() + side // 2 == anchor.x()  # column of the head centre
    assert top.y() + side - SHADOW_PAD == anchor.y() - GAP_ABOVE_HEAD  # just above the head


def test_wheel_clamps_to_the_screen():
    screen = QRect(0, 0, 800, 600)
    top = wheel_topleft(QPoint(5, 5), 110, screen)
    assert top == QPoint(8, 8)  # SCREEN_MARGIN from the top-left corner


# --- widget behaviour ---------------------------------------------------------


def test_hit_testing_uses_the_sector_geometry(qapp):
    menu, _calls = _wheel()
    assert menu.sector_at(_sector_point(menu, 3)) == 3
    centre = QPoint(menu.width() // 2, menu.height() // 2)
    assert menu.is_close_hit(centre)
    assert not menu.is_close_hit(_sector_point(menu, 0))


def test_sector_click_runs_callback_and_closes(qapp):
    menu, calls = _wheel()
    menu.show()
    _click(menu, _sector_point(menu, 5))
    assert not menu.isVisible()
    assert calls == []  # deferred: runs after the click event unwinds
    qapp.processEvents()
    assert calls == [5]


def test_centre_click_closes_without_action(qapp):
    menu, calls = _wheel()
    menu.show()
    _click(menu, QPoint(menu.width() // 2, menu.height() // 2))
    assert calls == []
    assert not menu.isVisible()


def test_disabled_sector_ignores_the_click(qapp):
    menu, calls = _wheel(disabled=(2,))
    menu.show()
    _click(menu, _sector_point(menu, 2))
    assert calls == []
    assert menu.isVisible()  # stays open, like a disabled item in a native menu
    menu.close()


def test_escape_closes(qapp):
    menu, _calls = _wheel()
    menu.show()
    menu.setFocus()
    QTest.keyClick(menu, Qt.Key.Key_Escape)
    assert not menu.isVisible()


def test_set_actions_resizes_and_rejects_more_than_eight(qapp):
    menu, _calls = _wheel(radius=119)
    assert menu.width() == 2 * (119 + SHADOW_PAD)
    menu.set_actions([WheelAction("A", lambda: None)], 100)
    assert menu.width() == 2 * (100 + SHADOW_PAD)
    too_many = [WheelAction(f"A{i}", lambda: None) for i in range(MAX_ACTIONS + 1)]
    with pytest.raises(ValueError):
        menu.set_actions(too_many, 100)
