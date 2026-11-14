"""Gamepad device polling for the simulator (docs/04 section 3).

Pure ctypes, polled inside the Qt timer — no threads, no dependencies.
Two APIs cover "any controller" on Windows:

- **XInput** (``xinput1_4.dll``) — Xbox-compatible pads, slots 0-3;
- **WinMM** ``joyGetPosEx`` — everything else (DualShock/DualSense, Switch
  Pro, generic HID gamepads). Xbox pads never show up here, and non-XInput
  pads never show up in XInput, so both are needed.

Buttons are normalised to Xbox names: a, b, x, y, lb, rb, back, start,
l3, r3, up, down, left, right (dpad), lt, rt.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field

_MAX_STICK = 32767.0
_MAX_AXIS = 65535.0


@dataclass
class Pad:
    """One polled snapshot: sticks and triggers in [-1, 1], named buttons."""

    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    buttons: frozenset = field(default_factory=frozenset)


# --- XInput (Xbox-compatible) ---------------------------------------------------


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", wintypes.SHORT),
        ("sThumbLY", wintypes.SHORT),
        ("sThumbRX", wintypes.SHORT),
        ("sThumbRY", wintypes.SHORT),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", _XINPUT_GAMEPAD)]


_XI_BUTTONS = {
    0x1000: "a",
    0x2000: "b",
    0x4000: "x",
    0x8000: "y",
    0x0100: "lb",
    0x0200: "rb",
    0x0020: "back",
    0x0010: "start",
    0x0040: "l3",
    0x0080: "r3",
    0x0001: "up",
    0x0002: "down",
    0x0004: "left",
    0x0008: "right",
}


def _xinput() -> Pad | None:
    try:
        dll = ctypes.windll.xinput1_4
    except (OSError, AttributeError):
        return None
    for slot in range(4):
        st = _XINPUT_STATE()
        if dll.XInputGetState(slot, ctypes.byref(st)) != 0:
            continue
        g = st.Gamepad
        buttons = {name for bit, name in _XI_BUTTONS.items() if g.wButtons & bit}
        if g.bLeftTrigger > 76:  # ~30% pull counts as a press
            buttons.add("lt")
        if g.bRightTrigger > 76:
            buttons.add("rt")
        return Pad(
            lx=g.sThumbLX / _MAX_STICK,
            ly=g.sThumbLY / _MAX_STICK,
            rx=g.sThumbRX / _MAX_STICK,
            ry=g.sThumbRY / _MAX_STICK,
            buttons=frozenset(buttons),
        )
    return None


# --- WinMM joystick (generic HID pads) ------------------------------------------


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [
        (name, wintypes.DWORD)
        for name in (
            "dwSize",
            "dwFlags",
            "dwXpos",
            "dwYpos",
            "dwZpos",
            "dwRpos",
            "dwUpos",
            "dwVpos",
            "dwButtons",
            "dwButtonNumber",
            "dwPOV",
            "dwReserved1",
            "dwReserved2",
        )
    ]


_JOY_RETURNALL = 0xFF
_WINMM_BUTTONS = ["a", "b", "x", "y", "lb", "rb", "back", "start", "l3", "r3"]


def _norm_axis(v: int) -> float:
    return (v - _MAX_AXIS / 2) / (_MAX_AXIS / 2)


def _winmm() -> Pad | None:
    try:
        dll = ctypes.windll.winmm
    except (OSError, AttributeError):
        return None
    info = _JOYINFOEX()
    info.dwSize = ctypes.sizeof(info)
    info.dwFlags = _JOY_RETURNALL
    for joy_id in range(16):
        if dll.joyGetPosEx(joy_id, ctypes.byref(info)) != 0:
            continue
        buttons = {
            _WINMM_BUTTONS[i] for i in range(len(_WINMM_BUTTONS)) if info.dwButtons & (1 << i)
        }
        if info.dwPOV != 0xFFFF:  # neutral dpad; value is hundredths of a degree
            oct = int(info.dwPOV + 2250) // 4500 % 8  # 0=up, 1=up-right, ...
            dirs = ("up", "right", "down", "left")
            if oct % 2 == 0:
                buttons.add(dirs[oct // 2])
            else:
                buttons.update((dirs[oct // 2], dirs[(oct // 2 + 1) % 4]))
        # Generic dual-analog layout: X/Y = left stick, Z/R = right stick.
        return Pad(
            lx=_norm_axis(info.dwXpos),
            ly=-_norm_axis(info.dwYpos),  # WinMM Y grows downwards
            rx=_norm_axis(info.dwZpos),
            ry=-_norm_axis(info.dwRpos),
            buttons=frozenset(buttons),
        )
    return None


def gamepad_state() -> Pad | None:
    """First live pad, XInput preferred; ``None`` when nothing is plugged in."""
    return _xinput() or _winmm()
