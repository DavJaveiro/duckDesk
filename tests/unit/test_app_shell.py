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


def test_unwritable_settings_does_not_raise(tmp_path, caplog):
    """A read-only profile must degrade quietly (the app keeps running)."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")  # mkdir(parents) fails
    with caplog.at_level("WARNING", logger="duckdesk.settings"):
        s = Settings(blocked / "settings.json")
        s["speed"] = 0.5
    assert s["speed"] == 0.5  # in-memory value still works
    assert any("não gravável" in record.message for record in caplog.records)


def test_rotating_log_written(tmp_path):
    import logging

    from duckdesk.app import setup_logging

    class _S:
        path = tmp_path / "settings.json"

    target = setup_logging(_S())
    logging.getLogger("duckdesk.test").info("hello-log")
    assert (
        target is not None and target.exists() and "hello-log" in target.read_text(encoding="utf-8")
    )
    for h in logging.getLogger().handlers[:]:
        h.close()
        logging.getLogger().removeHandler(h)


def test_logging_falls_back_when_profile_unwritable(tmp_path, monkeypatch):
    """Read-only profile: log must land in %TEMP%, and startup must not crash."""
    import logging

    from duckdesk.app import setup_logging

    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))

    class _S:
        path = blocked / "settings.json"

    target = setup_logging(_S())
    try:
        assert target is not None
        assert target.parent == temp / "DuckDesk" / "logs"
        logging.getLogger("duckdesk.test").info("hello-fallback")
        assert "hello-fallback" in target.read_text(encoding="utf-8")
    finally:
        for h in logging.getLogger().handlers[:]:
            h.close()
            logging.getLogger().removeHandler(h)


def test_ctrl_c_handler_calls_on_quit():
    """Ctrl+C in the terminal must quit via on_quit (it saves last_mode,
    geometry and the mascot x): run() installs that SIGINT handler."""
    import signal

    from duckdesk.app import _install_sigint

    class _Ctrl:
        quit_calls = 0

        def on_quit(self):
            self.quit_calls += 1

    old = signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        ctrl = _Ctrl()
        _install_sigint(ctrl)
        signal.raise_signal(signal.SIGINT)
        assert ctrl.quit_calls == 1
    finally:
        signal.signal(signal.SIGINT, old)


def test_tray_startup_does_not_fire_size_actions(tmp_path):
    """The initial check marks must not call on_size_changed (M4 startup write)."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    from duckdesk.ui.tray import Tray

    class _Ctrl:
        def __init__(self):
            self.settings = {"autopilot": True, "mascot_scale": 1.0, "voice": True}
            self.size_calls: list[float] = []

        def on_size_changed(self, scale):
            self.size_calls.append(scale)

        def show_simulator(self):
            pass

        def open_simulator(self):
            pass

        def toggle_mascot(self):
            pass

        def on_toggle_sit(self):
            pass

        def on_request(self, req):
            pass

        def on_autopilot_toggled(self, on):
            pass

        def on_voice_toggled(self, on):
            pass

        def on_toggle_pause(self):
            pass

        def on_autostart_toggled(self, on):
            pass

        def on_about(self):
            pass

        def on_quit(self):
            pass

    ctrl = _Ctrl()
    tray = Tray(ctrl)
    try:
        assert ctrl.size_calls == []
    finally:
        tray.hide()


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
