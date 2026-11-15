"""Mic self-check dialog (Ajuda > Testar microfone).

The GUI version of scripts/check_ears.py: lists the input devices PortAudio
sees, captures the chosen one and shows a live level meter (sensitivity
test); when the Vosk recognizer is available it also prints what it
understood — proof the mic reaches the *software*, not just Windows.

While a capture runs the duck's ears are suspended (suspend()/resume()), so
the test owns the mic and the shared recognizer exclusively — no double
feeding, no racing a tray toggle. Audio runs on PortAudio's callback thread
like DuckEars (no app thread added, ADR-0003); a QTimer polls the last
block's level for the meter.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QCoreApplication, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from duckdesk.platform import ears as ears_mod
from duckdesk.platform.ears import DuckEars

log = logging.getLogger("duckdesk.mic_test")

_BLOCK = 1024  # ~64 ms per audio block -> responsive level meter
_LEVEL_MS = 33  # meter refresh

# Sensitivity verdicts on the block peak, like scripts/check_ears.py.
DEAD_PEAK = 0.01
WEAK_PEAK = 0.05
HOT_PEAK = 0.80


class MicTestDialog(QDialog):
    """Device list + live capture level + recognition readout."""

    recognized = Signal(str)  # finished phrase from the shared recognizer
    partial = Signal(str)  # in-progress utterance (diagnostic feedback)

    def __init__(
        self, ears: DuckEars, assets_dir: Path, cache_dir: Path, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.ears = ears
        self._assets_dir = assets_dir
        self._cache_dir = cache_dir
        self._stream = None
        self._rec = None
        self._inst = 0.0  # latest block peak, consumed by the meter timer
        self._peak = 0.0  # loudest block since "Iniciar teste"
        self._ears_suspended = False
        self._last_partial = ""

        self.setWindowTitle("Teste de microfone")
        self.setModal(True)
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Microfone (entrada de áudio):"))
        self.combo = QComboBox(self)
        lay.addWidget(self.combo)

        row = QHBoxLayout()
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        row.addWidget(self.bar, stretch=1)
        self.lbl_peak = QLabel("—")
        self.lbl_peak.setMinimumWidth(64)
        self.lbl_peak.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.lbl_peak)
        lay.addLayout(row)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        self.lbl_rec = QLabel("")
        self.lbl_rec.setWordWrap(True)
        lay.addWidget(self.lbl_rec)

        btns = QHBoxLayout()
        self.btn = QPushButton("Iniciar teste")
        self.btn.clicked.connect(self._toggle)
        btns.addWidget(self.btn)
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        lay.addLayout(btns)

        self._timer = QTimer(self)
        self._timer.setInterval(_LEVEL_MS)
        self._timer.timeout.connect(self._tick)
        self.recognized.connect(self._on_recognized)
        self.partial.connect(self._on_partial)

        if ears_mod.sd is None:
            self.combo.addItem("componente de áudio indisponível", -1)
            self.combo.setEnabled(False)
            self.btn.setEnabled(False)
            self._set_status("O componente de áudio não está disponível nesta instalação.")
        else:
            self._fill_devices()

    # --- device list --------------------------------------------------------

    def _fill_devices(self) -> None:
        try:
            devs = ears_mod.sd.query_devices()
            default_in = int(ears_mod.sd.default.device[0])
        except Exception as e:  # noqa: BLE001 — broken audio stack
            devs, default_in = [], -1
            self._set_status(f"Não consegui listar os dispositivos: {e}")
        count = 0
        for i, d in enumerate(devs):
            if int(d["max_input_channels"]) <= 0:
                continue
            mark = " (padrão do sistema)" if i == default_in else ""
            self.combo.addItem(f"{d['name']}{mark}", i)
            count += 1
            if i == default_in:
                self.combo.setCurrentIndex(count - 1)
        if count == 0:
            self.combo.addItem("nenhum microfone detectado", -1)
            self.btn.setEnabled(False)
            self._set_status(
                "O Windows não expõe nenhuma entrada de áudio ao app. "
                "Confira a privacidade do microfone nas configurações."
            )
        else:
            self._set_status("Escolha o microfone e inicie o teste de nível.")

    # --- capture --------------------------------------------------------------

    def _toggle(self) -> None:
        if self._stream is None:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        dev = self.combo.currentData()
        if dev is None or int(dev) < 0 or ears_mod.sd is None:
            return
        # Own the mic + recognizer alone while the test runs.
        self.ears.suspend()
        self._ears_suspended = True
        self._set_status("Preparando o reconhecimento…")
        QCoreApplication.processEvents()  # the label paints before the model load
        ready = self.ears.prepare_recognizer(self._assets_dir, self._cache_dir)
        self._rec = self.ears.recognizer if ready else None
        self.lbl_rec.setText(
            'Reconhecimento ativo — fale "pato", "senta", "pia"…'
            if self._rec is not None
            else "Reconhecimento indisponível (modelo de voz ausente) — só o nível."
        )
        self._peak = self._inst = 0.0
        self._last_partial = ""
        try:
            self._stream = ears_mod.sd.RawInputStream(
                samplerate=ears_mod.SAMPLE_RATE,
                blocksize=_BLOCK,
                dtype="int16",
                channels=1,
                device=int(dev),
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:  # noqa: BLE001 — PortAudioError and friends
            self._stream = None
            self._set_status(f"Não abriu o microfone: {e}")
            self._restore_ears()
            return
        self.btn.setText("Parar teste")
        self._tick()
        self._timer.start()

    def _on_audio(self, indata, _frames, _t, _status) -> None:
        """PortAudio callback (same pattern as DuckEars._on_audio)."""
        try:
            pcm = np.frombuffer(indata, dtype=np.int16)
            if pcm.size:
                peak = float(np.abs(pcm.astype(np.int32)).max()) / 32768.0
                self._inst = peak
                self._peak = max(self._peak, peak)
            if self._rec is not None:
                if self._rec.AcceptWaveform(bytes(indata)):
                    text = json.loads(self._rec.Result()).get("text", "")
                    if text:
                        self.recognized.emit(text)
                else:
                    text = json.loads(self._rec.PartialResult()).get("partial", "")
                    if text and text != self._last_partial:
                        self._last_partial = text
                        self.partial.emit(text)
        except Exception as e:  # noqa: BLE001 — a bad block must not kill the stream
            log.debug("teste de mic: %s", e)

    def _stop(self) -> None:
        self._timer.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:  # noqa: BLE001 — already dead
                log.debug("teste de mic: stream já morto (%s)", e)
            self._stream = None
        if self._rec is not None:
            reset = getattr(self._rec, "Reset", None)
            if callable(reset):
                reset()  # drop the half-utterance before the ears take it back
            self._rec = None
        self.btn.setText("Iniciar teste")
        self._restore_ears()

    def _restore_ears(self) -> None:
        if self._ears_suspended:
            self._ears_suspended = False
            self.ears.resume()

    # --- meter + readout --------------------------------------------------------

    def _tick(self) -> None:
        inst, self._inst = self._inst, 0.0
        db = 20.0 * math.log10(max(inst, 1e-6))
        self.bar.setValue(int(min(100.0, max(0.0, (db + 60.0) / 0.6))))
        self.lbl_peak.setText(f"pico {self._peak * 100:.0f}%")
        if self._peak < DEAD_PEAK:
            self._set_status("Sem sinal até agora — fale algo ou confira o mic.")
        elif self._peak < WEAK_PEAK:
            self._set_status("Sinal fraco — chegue mais perto ou suba o ganho do mic.")
        elif self._peak > HOT_PEAK:
            self._set_status("Sinal MUITO alto — saturando (perto do clipping).")
        else:
            self._set_status("Microfone OK — nível de sensibilidade bom.")

    def _on_recognized(self, text: str) -> None:
        self.lbl_rec.setText(f"Reconhecido: “{text}”")

    def _on_partial(self, text: str) -> None:
        self.lbl_rec.setText(f"Ouvindo: “{text}”…")

    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def done(self, result: int) -> None:  # every close path funnels here
        self._stop()
        super().done(result)
