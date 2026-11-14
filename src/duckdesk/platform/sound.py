"""Bundled quack for the mascot's double-click (docs/05 section 6).

The MP3 ships inside the installer payload at ``assets/sounds/quack.mp3``.
``winsound`` only plays WAV — and cannot play memory sounds asynchronously —
so playback goes through the Win32 MCI (``winmm.mciSendStringW``): the file is
opened once as an alias and replayed ``from 0`` on every double-click. MCI is
asynchronous by nature, so the Qt thread never blocks.
"""

from __future__ import annotations

import ctypes
import logging

from duckdesk import assets

log = logging.getLogger("duckdesk.sound")

QUACK_MP3 = "sounds/quack.mp3"
_ALIAS = "duckdesk_quack"

_opened = False
_failed = False  # latch: warn once, then stay quiet


def _mci(command: str) -> int:
    """mciSendStringW return code; 0 = success."""
    return ctypes.windll.winmm.mciSendStringW(command, None, 0, None)


def _mci_error(code: int) -> str:
    buf = ctypes.create_unicode_buffer(128)
    ctypes.windll.winmm.mciGetErrorStringW(code, buf, 128)
    return buf.value


def _open() -> bool:
    global _opened, _failed
    path = assets.assets_dir() / QUACK_MP3
    if not path.is_file():
        log.warning("quack.mp3 não encontrado em %s", path)
        _failed = True
        return False
    code = _mci(f'open "{path}" type mpegvideo alias {_ALIAS}')
    if code != 0:
        log.warning("MCI não abriu %s: %s", path, _mci_error(code))
        _failed = True
        return False
    _opened = True
    return True


def quack_quack() -> None:
    """Replay the bundled quack from the start; silent failure on any error."""
    global _failed
    try:
        if not _opened and not _failed:
            _open()
        if _opened:
            _mci(f"play {_ALIAS} from 0")
    except (OSError, AttributeError) as e:  # winmm missing / non-Windows
        log.warning("sem áudio MCI para o quack: %s", e)
        _failed = True


def close() -> None:
    """Release the MCI alias; called when the app quits."""
    global _opened
    if _opened:
        _mci(f"close {_ALIAS}")
        _opened = False
