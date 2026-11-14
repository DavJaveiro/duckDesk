"""Locate the bundled assets and check them against assets/lock.json."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def assets_dir() -> Path:
    """Return the assets directory for dev and installed (PyInstaller) layouts."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parents[2]
    return base / "assets"


def load_lock() -> dict:
    lock_path = assets_dir() / "lock.json"
    return json.loads(lock_path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets() -> list[str]:
    """Check every file listed in lock.json; return a list of problems (empty if OK)."""
    base = assets_dir()
    lock_path = base / "lock.json"
    if not lock_path.is_file():
        return [f"assets/lock.json not found under {base}"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    problems = []
    for rel, meta in lock.get("files", {}).items():
        path = base / rel
        if not path.is_file():
            problems.append(f"{rel}: missing")
        elif sha256_file(path) != meta["sha256"]:
            problems.append(f"{rel}: sha256 mismatch")
    return problems
