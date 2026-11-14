"""Quack playback (docs/05 section 6): the bundled MP3 must ship in assets and
the MCI path must never raise — the duck is cute, not crash-prone."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def sound(monkeypatch):
    """Fresh module state + a fake _mci recorder per test."""
    from duckdesk.platform import sound

    monkeypatch.setattr(sound, "_opened", False)
    monkeypatch.setattr(sound, "_failed", False)
    calls = []
    monkeypatch.setattr(sound, "_mci", lambda cmd: calls.append(cmd) or 0)
    return sound, calls


def test_quack_mp3_is_bundled():
    from duckdesk import assets
    from duckdesk.platform import sound

    path = assets.assets_dir() / sound.QUACK_MP3
    assert path.is_file() and path.stat().st_size > 10_000
    data = path.read_bytes()
    assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)  # MP3 magic


def test_quack_opens_alias_once_and_plays_from_zero(sound):
    mod, calls = sound
    mod.quack_quack()
    mod.quack_quack()
    opens = [c for c in calls if c.startswith("open ")]
    plays = [c for c in calls if c.startswith("play ")]
    assert len(opens) == 1 and f"alias {mod._ALIAS}" in opens[0]
    assert "quack.mp3" in opens[0] and "mpegvideo" in opens[0]
    assert plays == [f"play {mod._ALIAS} from 0"] * 2


def test_quack_never_raises_when_mci_fails(sound, caplog, monkeypatch):
    mod, _calls = sound
    monkeypatch.setattr(mod, "_mci", lambda _cmd: 1)  # MCI error code
    with caplog.at_level("WARNING", logger="duckdesk.sound"):
        mod.quack_quack()
        mod.quack_quack()
    warns = [r.message for r in caplog.records if "quack" in r.message]
    assert len(warns) == 1  # failed latch: warn once, then stay quiet


def test_close_releases_the_alias(sound):
    mod, calls = sound
    mod.quack_quack()
    mod.close()
    assert calls[-1] == f"close {mod._ALIAS}"
    assert mod._opened is False
