"""Ear self-check: reports exactly what the app sees — APPDATA, profile
writability, model extraction, recognizer build, mic device and a live
audio capture test. Run in the same terminal the app uses:

    uv run python scripts/check_ears.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    print(f"APPDATA = {os.environ.get('APPDATA')!r}")
    appdata = Path(os.environ.get("APPDATA") or "") / "DuckDesk"

    # 1. profile writable?
    try:
        appdata.mkdir(parents=True, exist_ok=True)
        probe = appdata / "probe.tmp"
        probe.write_text("x")
        probe.unlink()
        print(f"1) perfil {appdata} -> GRAVÁVEL")
    except OSError as e:
        print(f"1) perfil {appdata} -> FALHOU: {e}")
        print("   (voz e ouvido dependem daqui — corrija a permissão e reinicie o app)")
        return 1

    # 2. model extraction
    from duckdesk.platform.ears import ensure_model

    model_dir = ensure_model(Path("assets"), appdata)
    print(f"2) modelo -> {model_dir or 'FALHOU (zip ausente ou não extraível)'}")

    # 3. recognizer
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        from duckdesk.brain import voice_commands

        SetLogLevel(-1)
        rec = KaldiRecognizer(Model(str(model_dir)), 16000, str(voice_commands.grammar()))
        print("3) reconhecedor Vosk -> OK")
    except Exception as e:  # noqa: BLE001
        print(f"3) reconhecedor Vosk -> FALHOU: {e}")
        return 1

    # 4. mic devices
    import sounddevice as sd

    try:
        devs = sd.query_devices()
        ins = [
            (i, d["name"], int(d["max_input_channels"]))
            for i, d in enumerate(devs)
            if d["max_input_channels"] > 0
        ]
        print("4) entradas de áudio:")
        for i, name, ch in ins:
            print(f"     [{i}] {name} ({ch} ch)")
    except Exception as e:  # noqa: BLE001
        print(f"4) query_devices -> FALHOU: {e}")
        return 1

    # 5. live capture: 3 s de mic, mede o nível
    print("5) capturando 3 s — FALE algo agora (ex.: 'pia')...")
    peak = 0.0

    def cb(indata, frames, _t, status):
        nonlocal peak
        import numpy as np

        pcm = np.frombuffer(indata, dtype=np.int16)
        peak = max(peak, float(np.abs(pcm).max()) / 32768)
        if rec.AcceptWaveform(bytes(indata)):
            import json

            print(f"   RECONHECEU: {json.loads(rec.Result()).get('text')!r}")

    try:
        with sd.RawInputStream(
            samplerate=16000, blocksize=8000, dtype="int16", channels=1, callback=cb
        ):
            time.sleep(3)
    except Exception as e:  # noqa: BLE001
        print(f"   stream -> FALHOU: {e}")
        return 1

    if peak < 0.01:
        print(f"   nível de áudio {peak:.3f} — MIC MORTO (mudo? outro dispositivo?)")
    else:
        print(f"   nível de áudio {peak:.3f} — mic VIVO")
    print("diagnóstico completo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
