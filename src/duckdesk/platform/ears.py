"""The duck's ears — offline pt-BR voice commands via Vosk (ADR-0012).

Mic → sounddevice RawInputStream (16 kHz int16 mono) → KaldiRecognizer with a
small command grammar (brain/voice_commands.py) → the ``heard`` Qt signal.
PortAudio's own callback thread accepts the audio (~ms per block) and only
emits a signal; all Qt/sim work stays on the Qt thread (ADR-0003) — the same
pattern an audio callback always uses, no app thread created.

Everything degrades quietly: missing model zip, unwritable cache, no mic,
non-Windows host — the duck just stays deaf, never crashes. Model loading is
lazy inside ``start()`` so a deaf-by-settings install never pays for it.

Model: ``vosk-model-small-pt-0.3`` (Apache-2.0, alphacephei.com), pinned in
assets/lock.json and shipped as a zip; extracted once to the user cache
(``%APPDATA%/DuckDesk/vosk/``) because the installed dir is read-only.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("duckdesk.ears")

MODEL_ZIP = "vosk-model-small-pt-0.3.zip"  # assets/models/, pinned in lock.json
SAMPLE_RATE = 16000  # the model's contract; the mic resamples for us
_BLOCK = 8000  # 0.5 s per audio callback

try:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel
except ImportError:  # non-Windows dev host without the wheels
    sd = None
    KaldiRecognizer = Model = None

    def SetLogLevel(_lvl: int) -> None:
        return None


def ensure_model(assets_dir: Path, cache_dir: Path) -> Path | None:
    """Extract the bundled model zip to ``cache_dir/vosk/`` once; return the
    model dir or None when the asset is missing/unwritable."""
    target = cache_dir / "vosk" / "vosk-model-small-pt-0.3"
    if (target / "final.mdl").is_file():
        return target
    zip_path = Path(assets_dir) / "models" / MODEL_ZIP
    if not zip_path.is_file():
        log.warning("modelo de voz ausente: %s (rode scripts/fetch_assets.py)", zip_path)
        return None
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(target.parent)
    except (OSError, zipfile.BadZipFile) as e:
        log.warning("modelo de voz não extraível: %s", e)
        return None
    return target if (target / "final.mdl").is_file() else None


class DuckEars(QObject):
    """Continuous command recognition on the default input device.

    ``heard(phrase)`` carries the grammar string the recognizer settled on —
    dispatching/meaning lives in brain.voice_commands + the controller.
    """

    heard = Signal(str)

    def __init__(self, settings, assets_dir: Path, parent=None):
        super().__init__(parent)
        self.enabled = False
        self._model_dir = None
        self._model = None
        self._rec = None
        self._stream = None
        self._want = bool(settings["ears"])
        if not self._want or sd is None:
            return
        self._model_dir = ensure_model(Path(assets_dir), Path(settings.path).parent)
        self.enabled = self._model_dir is not None

    # --- recognition plumbing ---------------------------------------------------

    def _ensure_recognizer(self) -> bool:
        if self._rec is not None:
            return True
        try:
            if self._model is None:
                SetLogLevel(-1)  # kaldi logs to stderr otherwise
                self._model = Model(str(self._model_dir))
            from duckdesk.brain import voice_commands

            self._rec = KaldiRecognizer(
                self._model, SAMPLE_RATE, json.dumps(voice_commands.grammar())
            )
            return True
        except (OSError, RuntimeError) as e:
            log.warning("reconhecedor indisponível: %s", e)
            return False

    def _on_audio(self, indata, frames, _t, status) -> None:
        """PortAudio callback: accept the block, emit finished utterances."""
        try:
            if self._rec is not None and self._rec.AcceptWaveform(bytes(indata)):
                text = json.loads(self._rec.Result()).get("text", "")
                if text:
                    self.heard.emit(text)
        except Exception as e:  # noqa: BLE001 — a bad block must not kill the stream
            log.warning("ouvido: %s", e)

    # --- lifecycle --------------------------------------------------------------

    def set_enabled(self, on: bool) -> None:
        """Tray toggle: start listening / release the mic."""
        self._want = on
        if on:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        """Open the mic (idempotent). No-ops when deaf."""
        if self._stream is not None or not self._want or sd is None:
            return
        if self._model_dir is None or not self._ensure_recognizer():
            self.enabled = False
            return
        try:
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=_BLOCK,
                dtype="int16",
                channels=1,
                callback=self._on_audio,
            )
            self._stream.start()
            self.enabled = True
            log.info("ouvido do pato ligado (mic 16 kHz)")
        except Exception as e:  # noqa: BLE001 — PortAudioError and friends
            log.warning("microfone indisponível: %s", e)
            self._stream = None
            self.enabled = False

    def stop(self) -> None:
        """Release the mic (the recognizer keeps its state — cheap resume)."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:  # noqa: BLE001 — already dead
                log.debug("ouvido: stream já morto (%s)", e)
            self._stream = None
            log.info("ouvido do pato desligado")

    def close(self) -> None:
        """App quit."""
        self.stop()
        self._rec = self._model = None
