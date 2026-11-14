"""The duck's generated voice — port of the upstream `sounds` daemon
(vendor/microduck, CC BY-NC-SA 4.0; module docs cite the Rust sources).

One integer seed derives a `Personality` — pitch register, harmonic tilt,
nasality, vibrato, quackiness, tempo — so each DuckDesk install gets a voice
that is recognisably its own, exactly like each robot getting its voice from
the SoC serial. Tags: greet (mascot wake), chirp (double-click), peck (peck +
goodbye), coo (yawn), inquire (curious look), alarm (fall), wheee (drag
ride), plus a streamed theremin driven by cursor distance.

Everything is local and cheap: numpy synthesis rendered lazily into a WAV
bank next to settings.json, played via winsound (files — the memory+async
limit that muted the first quack does not apply); the theremin streams
through winmm waveOut. No network, no threads (regras 6-7).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import wave
from pathlib import Path

import numpy as np

from duckdesk.platform.voice import voices
from duckdesk.platform.voice.personality import Personality
from duckdesk.platform.voice.stream import Stream
from duckdesk.platform.voice.synth import SR, to_i16

log = logging.getLogger("duckdesk.voice")

BANK_VERSION = 1  # bump when the synth changes enough to re-render banks
_ENV_FRAME_S = 0.04  # beak lip-sync keyframe step, like QUACK_ENV's 40 ms

try:
    import winsound

    _SND_FILE_ASYNC = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
except ImportError:  # non-Windows dev host
    winsound = None
    _SND_FILE_ASYNC = 0


def seed_from_id(text: str) -> int:
    """sha256(id), first 4 bytes big-endian — the upstream installer
    derivation (lib.rs seed_from_id)."""
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")


def resolve_seed(settings) -> int:
    """This install's voice seed: DUCK_IDENTITY override first (upstream's
    dev escape hatch), then a stable random one persisted in settings —
    our stand-in for the robot's SoC serial (lib.rs hardware_seed)."""
    if ident := os.environ.get("DUCK_IDENTITY"):
        return seed_from_id(ident)
    if settings["voice_seed"] is None:
        settings["voice_seed"] = int.from_bytes(os.urandom(4), "big")
    return int(settings["voice_seed"])


def envelope_of(buf: np.ndarray) -> tuple[tuple[float, float], ...]:
    """40 ms RMS keyframes, peak-normalised x1.25 and clipped — the same
    extraction the bundled QUACK_ENV was built with, so a generated call can
    drive the beak like the recording does (ADR-0010)."""
    frame = int(_ENV_FRAME_S * SR)
    n_frames = max(1, len(buf) // frame)
    rms = np.array(
        [float(np.sqrt(np.mean(buf[i * frame : (i + 1) * frame] ** 2))) for i in range(n_frames)]
    )
    peak = float(rms.max()) + 1e-9
    return tuple(
        (round(i * _ENV_FRAME_S, 2), float(min(1.0, v / peak * 1.25))) for i, v in enumerate(rms)
    )


def _write_wav(path: Path, buf: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(to_i16(buf).tobytes())


class VoiceBank:
    """This install's WAV bank: `<root>/<tag>/<tag>_<letter>.wav`, rendered
    lazily and kept across runs. A `.seed` marker with `<seed>:<version>`
    regenerates the bank when the synth or the identity changes (lib.rs)."""

    def __init__(self, seed: int, root: Path):
        self.personality = Personality.from_seed(seed)
        self.root = Path(root)
        marker = root / ".seed"
        want = f"{seed}:{BANK_VERSION}"
        if not marker.is_file() or marker.read_text().strip() != want:
            for tag_dir in root.glob("*"):
                if tag_dir.is_dir():
                    for f in tag_dir.glob("*.wav"):
                        f.unlink()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(want)
        self._env: dict[Path, tuple] = {}

    def file(self, tag: str, variant: int) -> Path:
        """The WAV path for (tag, variant), rendered on first use."""
        letter = chr(ord("a") + variant)
        path = self.root / tag / f"{tag}_{letter}.wav"
        if not path.is_file():
            _write_wav(path, voices.render(tag, self.personality, variant))
        return path

    def wheee_segment(self, name: str, variant: int) -> Path:
        """wheee_start/loop/end_<letter>.wav — the ride triad (lib.rs)."""
        letter = chr(ord("a") + variant)
        path = self.root / "wheee" / f"wheee_{name}_{letter}.wav"
        if not path.is_file():
            start, loop_seg, end = voices.wheee_segments(self.personality, variant)
            for seg_name, buf in (("start", start), ("loop", loop_seg), ("end", end)):
                _write_wav(self.root / "wheee" / f"wheee_{seg_name}_{letter}.wav", buf)
        return path

    def pick(self, tag: str) -> tuple[Path, tuple]:
        """A random variant's (path, beak envelope) — robotd's random pick."""
        variant = random.randrange(voices.variant_count(tag))
        path = self.file(tag, variant)
        if path not in self._env:
            with wave.open(str(path), "rb") as w:
                buf = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0
            self._env[path] = envelope_of(buf)
        return path, self._env[path]


class Voice:
    """The duck's voice at play time — pick a variant, hand it to the OS.

    Everything is a no-op when disabled (settings["voice"] off, no audio
    device, non-Windows), so callers never check.
    """

    def __init__(self, settings):
        self.enabled = bool(settings["voice"]) and winsound is not None
        self._bank = None
        self._wave = None
        self._stream = None
        self._wheee_variant: int | None = None
        self._rng = random.Random()
        if self.enabled:
            try:
                self._bank = VoiceBank(resolve_seed(settings), Path(settings.path).parent / "voice")
            except OSError as e:  # e.g. unwritable profile: stay quiet
                log.warning("banco de voz indisponível: %s", e)
                self.enabled = False

    @property
    def personality(self) -> Personality | None:
        return self._bank.personality if self._bank else None

    def play(self, tag: str) -> tuple | None:
        """One random variant; returns the beak envelope for lip-sync."""
        if not self.enabled:
            return None
        try:
            path, env = self._bank.pick(tag)
            winsound.PlaySound(str(path), _SND_FILE_ASYNC)
            return env
        except OSError as e:
            log.warning("voz %s falhou: %s", tag, e)
            return None

    # --- the wheee ride (drag) -------------------------------------------------

    def wheee_start(self) -> None:
        """Held-ride entry: loop segment on SND_LOOP until wheee_end()."""
        if not self.enabled:
            return
        self._wheee_variant = self._rng.randrange(voices.variant_count("wheee"))
        try:
            winsound.PlaySound(
                str(self._bank.wheee_segment("loop", self._wheee_variant)),
                winsound.SND_FILENAME
                | winsound.SND_ASYNC
                | winsound.SND_LOOP
                | winsound.SND_NODEFAULT,
            )
        except OSError as e:
            log.warning("wheee falhou: %s", e)

    def wheee_end(self) -> None:
        """Ride's landing: cut the loop, play the end segment once.

        No-op unless a ride actually started — otherwise every mascot exit
        would lazily render the whole ride bank for a landing nobody hears."""
        if not self.enabled or self._wheee_variant is None:
            return
        winsound.PlaySound(None, 0)
        try:
            winsound.PlaySound(
                str(self._bank.wheee_segment("end", self._wheee_variant)), _SND_FILE_ASYNC
            )
        except (OSError, AttributeError):
            pass
        finally:
            self._wheee_variant = None

    # --- the theremin (cursor distance) ----------------------------------------

    def theremin_tick(self, closeness: float | None, open_: float) -> None:
        """Pump the streamed voice once per mascot tick.

        ``closeness`` in (0, 1] raises a note that geometrically sweeps this
        duck's range (stream.rs hz_at); None/0 fades it out — a fade, not a
        click, because the level slews (stream.rs).
        """
        if not self.enabled:
            return
        try:
            if self._stream is None:
                if not closeness:
                    return
                from duckdesk.platform.voice.waveout import WaveOut

                self._wave = WaveOut()
                self._stream = Stream.wheee(self._bank.personality, 0)
            level = 1.0 if closeness else 0.0
            hz = self._stream.hz_at(closeness or 0.0)
            self._stream.set(hz, level, open_)
            while self._wave.free:
                self._wave.write(to_i16(self._stream.block(self._wave.block_n)))
            if self._stream.is_silent():
                self._wave.close()
                self._wave = self._stream = None
        except OSError as e:
            log.warning("theremin indisponível: %s", e)
            self.enabled = False

    def theremin_stop(self) -> None:
        """Leaving mascot mode: fade fast and drop the PCM sink."""
        if self._stream is not None:
            self._stream.set_level(0.0)
        if self._wave is not None:
            self._wave.close()
        self._wave = self._stream = None

    # --- lifecycle --------------------------------------------------------------

    def close(self) -> None:
        """App quit: cut winsound playback and release the waveOut handle."""
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except (OSError, RuntimeError):
                pass
        self.theremin_stop()
