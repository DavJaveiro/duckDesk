"""TOPMOST re-assert + fullscreen detection (docs/05 section 2)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4


def reassert_topmost(hwnd: int) -> None:
    """Every ~1 s: the taskbar is also TOPMOST and wins clicks otherwise."""
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        wintypes.HWND(HWND_TOPMOST),
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def fullscreen_app_active() -> bool:
    """True when another app holds the screen (05 section 2)."""
    try:
        return shell32.SHQueryUserNotificationState() in (
            QUNS_BUSY,
            QUNS_RUNNING_D3D_FULL_SCREEN,
            QUNS_PRESENTATION_MODE,
        )
    except Exception:  # noqa: BLE001 - old Windows without the API: never hide
        return False
