"""Voice commands (ADR-0012): the pt-BR grammar contract and the DuckEars
lifecycle — all without touching a real microphone."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest

from duckdesk.brain import voice_commands
from duckdesk.platform import ears

# ---------------------------------------------------------------- grammar ---


def test_grammar_lists_every_phrase_then_unknown():
    g = voice_commands.grammar()
    assert g[:-1] == list(voice_commands.COMMANDS)
    assert g[-1] == voice_commands.UNKNOWN


def test_grammar_has_no_duplicate_or_empty_phrases():
    phrases = list(voice_commands.COMMANDS)
    assert len(phrases) == len(set(phrases))
    assert all(p.strip() == p and p for p in phrases)


@pytest.mark.parametrize(
    ("phrase", "cmd"),
    [
        ("senta", "sit"),
        ("levanta", "stand"),
        ("anda", "walk"),
        ("para", "stop"),
        ("vem aqui", "come"),
        ("cambalhota", "roll"),
        ("bica", "peck"),
        ("chuta", "kick"),
        ("pia", "chirp"),
        ("vai dormir", "sleep"),
        ("olha", "look"),
        ("oi pato", "poke"),
        ("tchau", "bye"),
    ],
)
def test_resolve_maps_phrases(phrase, cmd):
    assert voice_commands.resolve(phrase) == cmd


def test_resolve_is_case_and_space_insensitive():
    assert voice_commands.resolve("  SENTA ") == "sit"


def test_resolve_rejects_noise_and_unknown():
    assert voice_commands.resolve("[unk]") is None
    assert voice_commands.resolve("qualquer outra frase") is None
    assert voice_commands.resolve("") is None


# ------------------------------------------------------------- ensure_model ---


def _zip_with_final_mdl(path: Path) -> None:
    """A minimal model-shaped zip: <name>/final.mdl + one sibling file."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{ears.MODEL_ZIP[:-4]}/final.mdl", b"mdl")
        z.writestr(f"{ears.MODEL_ZIP[:-4]}/mfcc.conf", b"conf")


def test_ensure_model_missing_zip_returns_none(tmp_path, caplog):
    assert ears.ensure_model(tmp_path / "assets", tmp_path / "cache") is None
    assert "modelo de voz ausente" in caplog.text


def test_ensure_model_extracts_zip_once(tmp_path):
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)

    model_dir = ears.ensure_model(assets, tmp_path / "cache")
    assert model_dir == tmp_path / "cache" / "vosk" / ears.MODEL_ZIP[:-4]
    assert (model_dir / "final.mdl").is_file()
    # second call short-circuits on the extracted dir (no re-extract)
    assert ears.ensure_model(assets, tmp_path / "cache") == model_dir


def test_ensure_model_bad_zip_returns_none(tmp_path, caplog):
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    (assets / "models" / ears.MODEL_ZIP).write_bytes(b"not a zip")
    assert ears.ensure_model(assets, tmp_path / "cache") is None
    assert "não extraível" in caplog.text


# ---------------------------------------------------------------- DuckEars ---


class _FakeStream:
    def __init__(self, **_kw):
        self.kw = _kw
        self.started = self.stopped = False
        self.cb = _kw["callback"]

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.stopped = True


class _FakeSd:
    def __init__(self):
        self.streams = []

    def RawInputStream(self, **kw):
        s = _FakeStream(**kw)
        self.streams.append(s)
        return s


class _FakeRecognizer:
    """AcceptWaveform consumes blocks; Result returns a fixed phrase."""

    next_result: ClassVar[str] = ""
    instances: ClassVar[list] = []

    def __init__(self, _model, rate, grammar_json):
        self.rate = rate
        self.grammar = json.loads(grammar_json)
        self.accepted = b""
        _FakeRecognizer.instances.append(self)

    def AcceptWaveform(self, data: bytes) -> bool:
        self.accepted += data
        return bool(_FakeRecognizer.next_result)  # finished utterance

    def Result(self) -> str:
        return json.dumps({"text": _FakeRecognizer.next_result})


def _settings(tmp_path, on=True):
    from duckdesk.settings import Settings

    s = Settings(tmp_path / "settings.json")
    s["ears"] = on
    return s


def test_ears_off_by_settings_stays_deaf(tmp_path):
    e = ears.DuckEars(_settings(tmp_path, on=False), tmp_path / "assets")
    assert not e.enabled
    e.start()  # no-op
    assert e._stream is None
    e.close()


def test_ears_without_sd_stays_deaf(tmp_path, monkeypatch):
    monkeypatch.setattr(ears, "sd", None)
    e = ears.DuckEars(_settings(tmp_path), tmp_path / "assets")
    assert not e.enabled
    e.start()
    assert e._stream is None


def test_ears_missing_model_stays_deaf(tmp_path):
    e = ears.DuckEars(_settings(tmp_path), tmp_path / "assets")  # no models/ dir
    assert not e.enabled
    e.start()
    assert e._stream is None


def test_ears_start_opens_mic_and_recognizer(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)
    fake_sd = _FakeSd()
    monkeypatch.setattr(ears, "sd", fake_sd)
    monkeypatch.setattr(ears, "Model", lambda _p: object())
    monkeypatch.setattr(ears, "KaldiRecognizer", _FakeRecognizer)

    e = ears.DuckEars(_settings(tmp_path), assets)
    e.start()
    assert e.enabled
    assert len(fake_sd.streams) == 1
    st = fake_sd.streams[0]
    assert st.started and st.kw["samplerate"] == ears.SAMPLE_RATE
    assert st.kw["channels"] == 1 and st.kw["dtype"] == "int16"
    rec = _FakeRecognizer.instances[-1]
    assert rec.grammar == voice_commands.grammar()  # restricted, not dictation

    e.start()  # idempotent
    assert len(fake_sd.streams) == 1
    e.stop()
    assert st.stopped and e._stream is None


def test_ears_callback_emits_heard_on_finished_utterance(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)
    fake_sd = _FakeSd()
    monkeypatch.setattr(ears, "sd", fake_sd)
    monkeypatch.setattr(ears, "Model", lambda _p: object())
    monkeypatch.setattr(ears, "KaldiRecognizer", _FakeRecognizer)

    e = ears.DuckEars(_settings(tmp_path), assets)
    heard = []
    e.heard.connect(heard.append)
    e.start()

    block = memoryview(b"\x00" * ears._BLOCK * 2)  # what PortAudio hands over
    _FakeRecognizer.next_result = "senta"
    e._on_audio(block, len(block), None, None)
    assert heard == ["senta"]

    heard.clear()
    _FakeRecognizer.next_result = ""  # partial — nothing emitted
    e._on_audio(block, len(block), None, None)
    assert heard == []

    e.close()
    assert fake_sd.streams[0].stopped


def test_ears_suspend_blocks_start_until_resume(tmp_path, monkeypatch):
    """The mic-test dialog borrows the mic via suspend(): a stray start()
    (e.g. tray toggle) must not reopen the stream and double-feed the
    shared recognizer while the hold lasts."""
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)
    fake_sd = _FakeSd()
    monkeypatch.setattr(ears, "sd", fake_sd)
    monkeypatch.setattr(ears, "Model", lambda _p: object())
    monkeypatch.setattr(ears, "KaldiRecognizer", _FakeRecognizer)

    e = ears.DuckEars(_settings(tmp_path), assets)
    e.start()
    st = fake_sd.streams[0]
    e.suspend()
    assert e._stream is None and st.stopped
    e.start()  # blocked by the hold
    assert e._stream is None and len(fake_sd.streams) == 1
    e.resume()
    assert e._stream is not None and len(fake_sd.streams) == 2
    e.close()


def test_ears_suspend_resume_deaf_stays_quiet(tmp_path, monkeypatch):
    """suspend()/resume() on a deaf ears object: no stream, no crash."""
    monkeypatch.setattr(ears, "sd", _FakeSd())
    e = ears.DuckEars(_settings(tmp_path, on=False), tmp_path / "assets")
    e.suspend()
    e.resume()
    assert e._stream is None


def test_ears_prepare_recognizer_booted_deaf(tmp_path, monkeypatch):
    """The test dialog can build the recognizer even when the ears booted
    deaf (settings['ears']=False skips model resolution at __init__)."""
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)
    monkeypatch.setattr(ears, "Model", lambda _p: object())
    monkeypatch.setattr(ears, "KaldiRecognizer", _FakeRecognizer)

    e = ears.DuckEars(_settings(tmp_path, on=False), assets)
    assert e.recognizer is None and e._model_dir is None
    assert e.prepare_recognizer(assets, tmp_path / "cache")
    assert e.recognizer is not None


def test_ears_prepare_recognizer_missing_model(tmp_path, monkeypatch):
    e = ears.DuckEars(_settings(tmp_path, on=False), tmp_path / "assets")
    assert not e.prepare_recognizer(tmp_path / "assets", tmp_path / "cache")
    assert e.recognizer is None


def test_ears_mic_failure_degrades(tmp_path, monkeypatch, caplog):
    assets = tmp_path / "assets"
    (assets / "models").mkdir(parents=True)
    _zip_with_final_mdl(assets / "models" / ears.MODEL_ZIP)
    monkeypatch.setattr(ears, "Model", lambda _p: object())
    monkeypatch.setattr(ears, "KaldiRecognizer", _FakeRecognizer)

    class _DeadSd:
        def RawInputStream(self, **_kw):
            raise OSError("no mic")

    monkeypatch.setattr(ears, "sd", _DeadSd())
    e = ears.DuckEars(_settings(tmp_path), assets)
    e.start()
    assert not e.enabled and e._stream is None
    assert "microfone indisponível" in caplog.text
