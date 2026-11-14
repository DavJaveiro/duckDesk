"""Settings in %APPDATA%/DuckDesk/settings.json (docs/02 file table).

Window geometry is stored as base64 of QByteArray from
QMainWindow.saveGeometry().
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT = {
    "window_geometry": None,  # base64 str, simulator window
    "last_mode": "simulator",  # "simulator" | "mascot"
    "mascot_scale": 1.0,
    "autopilot": True,
    "speed": 1.0,
    "autostart": False,
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
        try:
            self._data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001,S110 - missing/corrupt file -> defaults
            pass

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
