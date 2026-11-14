"""Settings in %APPDATA%/DuckDesk/settings.json (docs/02 file table).

Window geometry is stored as base64 of QByteArray from
QMainWindow.saveGeometry().
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("duckdesk.settings")

_DEFAULT = {
    "window_geometry": None,  # base64 str, simulator window
    "last_mode": "simulator",  # "simulator" | "mascot"
    "mascot_scale": 1.0,
    "mascot_last_x": 0.0,
    "autopilot": True,
    "speed": 1.0,
    "autostart": False,
    "voice": True,  # generated voice (platform/voice); off = silent duck
    "voice_seed": None,  # this install's vocal identity; drawn on first boot
}


def _app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "DuckDesk"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or (_app_dir() / "settings.json")
        self._data = dict(_DEFAULT)
        self._save_warned = False
        try:
            self._data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 - corrupt file -> defaults, logged
            log.warning("settings.json ilegível (%s); usando padrões", e)

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    def save(self) -> None:
        """Persist; a read-only profile must not take the app down (M4)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            if not self._save_warned:
                self._save_warned = True
                log.warning("settings.json não gravável (%s); mudanças não serão salvas", e)
            return
        self._save_warned = False
