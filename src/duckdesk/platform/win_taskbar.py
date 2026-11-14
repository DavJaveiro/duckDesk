"""Taskbar rect + auto-hide state via SHAppBarMessage (docs/05 section 1).

Win32 returns PHYSICAL pixels; callers convert through mascot_map.Dpi.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

shell32 = ctypes.windll.shell32

ABM_GETTASKBARPOS = 0x00000005
ABM_GETSTATE = 0x00000004
ABS_AUTOHIDE = 0x00000001
ABE_BOTTOM = 3


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


def get_taskbar_rect() -> tuple[int, int, int, int] | None:
    """Physical px (l, t, r, b) of the taskbar, or None if unavailable."""
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(data)
    if not shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
        return None
    rc = data.rc
    return rc.left, rc.top, rc.right, rc.bottom


def taskbar_autohide() -> bool:
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(data)
    return bool(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(data)) & ABS_AUTOHIDE)


def taskbar_edge() -> int | None:
    """uEdge of the taskbar (ABE_*), for logging degraded modes."""
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(data)
    if not shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
        return None
    return int(data.uEdge)
