"""Load the upstream infer_policy.py from vendor/ for the parity test.

The upstream script imports termios and tty (Unix-only); AGENTS.md prescribes
fake modules in sys.modules before importing it. `select` exists on Windows.

Skipped entirely when vendor/ is absent — run
`uv run python scripts/fetch_assets.py --vendor` once.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Upstream prints non-ASCII ("→"); the Windows console default (cp1252) can't
# encode it and would crash the test.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parents[2]
INFER_POLICY = ROOT / "vendor" / "microduck_rl" / "scripts" / "infer_policy.py"

if not INFER_POLICY.is_file():
    pytest.skip(
        "vendor/microduck_rl ausente — rode scripts/fetch_assets.py --vendor",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def infer_policy():
    sys.modules.setdefault("termios", types.ModuleType("termios"))
    sys.modules.setdefault("tty", types.ModuleType("tty"))
    spec = importlib.util.spec_from_file_location("infer_policy_upstream", INFER_POLICY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
