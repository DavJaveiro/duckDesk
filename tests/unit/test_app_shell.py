"""M4 app shell: single instance, autostart registry, settings resilience, logging."""

from __future__ import annotations

import sys
import winreg

import pytest

from duckdesk.platform import autostart
from duckdesk.settings import Settings

pytestmark = pytest.mark.unit

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def test_autostart_writes_and_deletes_run_key():
    autostart.set_enabled(True)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "DuckDesk")
        assert "duckdesk" in value.lower() or value.endswith(".exe")
    finally:
        autostart.set_enabled(False)
    with (
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key,
        pytest.raises(FileNotFoundError),
    ):
        winreg.QueryValueEx(key, "DuckDesk")


def test_autostart_disable_idempotent():
    autostart.set_enabled(False)  # nothing there -> no raise


def test_corrupt_settings_falls_back_and_logs(tmp_path, caplog):
    p = tmp_path / "settings.json"
    p.write_text("{corrupted json!!", encoding="utf-8")
    with caplog.at_level("WARNING", logger="duckdesk.settings"):
        s = Settings(p)
    assert s["speed"] == 1.0 and s["last_mode"] == "simulator"
    assert any("padrões" in r.message for r in caplog.records)


def test_settings_persist(tmp_path):
    p = tmp_path / "settings.json"
    s = Settings(p)
    s["autopilot"] = False
    s["mascot_scale"] = 1.5
    s2 = Settings(p)
    assert s2["autopilot"] is False and s2["mascot_scale"] == 1.5


def test_rotating_log_written(tmp_path):
    import logging

    from duckdesk.app import setup_logging

    class _S:
        path = tmp_path / "settings.json"

    target = setup_logging(_S())
    logging.getLogger("duckdesk.test").info("hello-log")
    assert target.exists() and "hello-log" in target.read_text(encoding="utf-8")
    for h in logging.getLogger().handlers[:]:
        h.close()
        logging.getLogger().removeHandler(h)


def test_single_instance_notify():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    from duckdesk.app import INSTANCE_NAME, listen_for_raise, notify_existing_instance

    class _C:
        def __init__(self):
            self.raised = []

        def show_simulator(self):
            self.raised.append(True)

    server = listen_for_raise(_C(), name=INSTANCE_NAME + "-test")
    assert notify_existing_instance(INSTANCE_NAME + "-test") is True
    server.close()
