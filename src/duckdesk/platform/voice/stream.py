"""The duck's voice, held open: a block-wise synth driven by live parameters —
port of sounds/src/stream.rs (theremin path only).

The recipes render offline from a precomputed frequency curve; a theremin's
pitch is a distance arriving per tick, so frequency has to be integrated as it
arrives. `Stream.block` renders a block from the parameters as they stand now
and carries every piece of cross-block state (phase, LFO time, jitter/breath
filters, the slewed parameters themselves).

The Rust loop is per-sample; this port computes the same signal per block,
vectorised: the one-pole parameter slews are closed-form geometric decays and
the recursive jitter/breath filters become exponential-kernel convolutions
with carry state — the same character (stream.rs itself notes the streamed
filters differ in values, not in character, from the offline ones). Not
ported: the speaker-rolloff rebalance and the chorale vowel/formant shift
(neither exists here — full-range PC speaker, no score).
"""

from __future__ import annotations

import numpy as np

from duckdesk.platform.voice.personality import Personality
from duckdesk.platform.voice.synth import SR, TAU

# One-pole time constants (stream.rs). Pitch glides slowest — it is the slide
# you hear; level is the key (attack/release); open follows the mouth servo.
PITCH_TAU_S = 0.045
LEVEL_TAU_S = 0.030
OPEN_TAU_S = 0.060
# The offline jitter's 64-sample window at 22.05 kHz (~2.9 ms).
JITTER_TAU_S = 64.0 / 22_050.0

# Headroom under full scale for the static gain, before the tanh soft clip —
# deliberately under the bank's -4 dBFS (stream.rs PEAK).
PEAK = 0.62

# How much a wide-open mouth lifts the harmonic tilt (brighter timbre).
OPEN_TILT_LIFT = 0.8


def _pole(tau_s: float) -> float:
    """One-pole step coefficient for a time constant, at SR."""
    return 1.0 - np.exp(-1.0 / (tau_s * SR))


def _slew_series(start: float, target: float, a: float, n: int) -> np.ndarray:
    """Closed-form one-pole: x[i] after i+1 steps of x += (target - x) * a."""
    return target + (start - target) * (1.0 - a) ** np.arange(1, n + 1)


def _semitones(offset) -> np.ndarray:
    """A pitch offset in semitones, as a frequency multiplier."""
    return 2.0 ** (np.asarray(offset, dtype=np.float64) / 12.0)


def range_hz(p: Personality) -> tuple[float, float]:
    """A duck's playable range — the wheee's own span (stream.rs)."""
    lo = p.pitch_center_hz * 0.85
    top = 1.6 + 0.5 * p.pitch_spread
    return lo, p.pitch_center_hz * top


def hz_at(p: Personality, position: float) -> float:
    """Frequency for a 0..1 position — geometric (linear in semitones)."""
    lo, hi = range_hz(p)
    return lo * (hi / lo) ** min(1.0, max(0.0, position))


class Stream:
    """A voice driven sample-accurately from slowly-arriving parameters.

    Construct once per performance; `set` whenever new parameters arrive;
    `block` whenever the audio sink needs samples (stream.rs).
    """

    def __init__(self, p: Personality, seed_tag: str, variant: int):
        self.p = p
        rng = p.variant_rng(seed_tag, variant)
        self.wobble_hz = 4.5 + 3.0 * rng.random()
        self._rng = rng

        self._phase = 0.0  # carrier phase, kept in [0, TAU)
        self._t = 0.0  # seconds rendered — the LFOs' time axis

        # Recursive filter states (carried across blocks).
        self._jitter = 0.0
        self._pink = 0.0

        # Slewed parameters: _target is asked-for, the bare field where the
        # glide has reached (stream.rs).
        self.freq = p.pitch_center_hz
        self.freq_target = p.pitch_center_hz
        self.level = 0.0
        self.level_target = 0.0
        self.open = 0.0
        self.open_target = 0.0

        # Per-voice softening folded into the modulation depths (Stream::wheee).
        self.vibrato_depth = p.vibrato_depth
        self.quackiness = p.quackiness
        self.jitter_depth = p.jitter_depth
        self.breath = p.breath * 0.5
        self.wobble_depth = 0.0

        self._weights = p.harmonics()
        self._weights_open = np.nan
        self.gain = 1.0
        self._refresh_weights()

    @classmethod
    def wheee(cls, p: Personality, variant: int) -> Stream:
        """The joy-ride voice the theremin uses (stream.rs Stream::wheee)."""
        s = cls(p, "wheee", variant)
        s.vibrato_depth = p.vibrato_depth * 0.5
        s.quackiness = p.quackiness * 0.5
        s.wobble_depth = 0.5
        return s

    def range_hz(self) -> tuple[float, float]:
        return range_hz(self.p)

    def hz_at(self, position: float) -> float:
        return hz_at(self.p, position)

    def set(self, hz: float, level: float, open_: float) -> None:
        """Targets the stream glides toward (stream.rs set)."""
        self.freq_target = min(SR / 3.0, max(30.0, hz))
        self.level_target = min(1.0, max(0.0, level))
        self.open_target = min(1.0, max(0.0, open_))

    def set_level(self, level: float) -> None:
        """Silence without moving pitch — a note ending, not falling over."""
        self.level_target = min(1.0, max(0.0, level))

    def is_silent(self) -> bool:
        """Level faded out and nothing asked — safe to stop pulling blocks."""
        return self.level_target <= 0.0 and self.level < 1e-4

    def _refresh_weights(self) -> None:
        """Harmonic weights at the current `open`, plus the static gain."""
        p = self.p.replace(
            tilt=max(0.8, self.p.tilt - OPEN_TILT_LIFT * min(1.0, max(0.0, self.open)))
        )
        self._weights = p.harmonics()
        self._weights_open = self.open
        self.gain = PEAK / max(1e-6, sum(self._weights))

    def block(self, n: int) -> np.ndarray:
        """Render n samples, advancing every piece of state (stream.rs block)."""
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        dt = 1.0 / SR
        a_pitch, a_level, a_open = _pole(PITCH_TAU_S), _pole(LEVEL_TAU_S), _pole(OPEN_TAU_S)

        # Slewed parameters, closed-form over the block.
        freq = _slew_series(self.freq, self.freq_target, a_pitch, n)
        level = _slew_series(self.level, self.level_target, a_level, n)
        open_ = _slew_series(self.open, self.open_target, a_open, n)
        self.freq, self.level, self.open = float(freq[-1]), float(level[-1]), float(open_[-1])

        if abs(self.open - self._weights_open) > 0.005:
            self._refresh_weights()

        t = self._t + np.arange(n) * dt
        self._t = float(t[-1] + dt)

        # Pitch modulation: this duck's vibrato, its jitter, the ride wobble.
        vib = _semitones(self.vibrato_depth * np.sin(TAU * self.p.vibrato_rate_hz * t))
        jit = _semitones(self.jitter_depth * self._jitter_block(n))
        wob = _semitones(self.wobble_depth * np.sin(TAU * self.wobble_hz * t))

        # Integrate frequency to phase (phase_i = phase0 + cumsum(dphase), as
        # the Rust loop emits sin after each sample's own increment); keep the
        # running phase wrapped so sin stays accurate over a long ride.
        dphase = TAU * freq * vib * jit * wob * dt
        phase = self._phase + np.cumsum(dphase)
        self._phase = float(phase[-1] % TAU)

        v = np.zeros(n)
        for i, w in enumerate(self._weights, start=1):
            if w != 0.0:
                v += w * np.sin(i * phase)
        v *= self.gain

        am_depth = self.p.am_depth * 0.5 * self.quackiness
        if am_depth > 0.01:
            v *= 1.0 - am_depth * (0.5 + 0.5 * np.sin(TAU * self.p.am_rate_hz * t))

        if self.breath > 0.0:
            v += self.breath * self._pink_block(n)

        # Level last: the fade takes the buzz and breath with it; tanh soft-clips
        # what the AM adds on top (stream.rs).
        return np.tanh(v * level).astype(np.float32)

    # --- recursive filters, vectorised per block ------------------------------

    def _jitter_block(self, n: int) -> np.ndarray:
        """j[i] = j*(1-a) + a*N — leaky integrator of white noise (stream.rs).

        Closed form: j[i] = d^(i+1) * j0 + conv(x, a*d^k)[i], carried in
        `_jitter`; the kernel truncates below 1e-4 (inaudible).
        """
        a = _pole(JITTER_TAU_S)
        d = 1.0 - a
        x = self._rng.standard_normal_vec(n)
        kernel = a * d ** np.arange(_kernel_len(d))
        j = np.convolve(x, kernel)[:n] + d ** np.arange(1, n + 1) * self._jitter
        self._jitter = float(j[-1])
        return j

    def _pink_block(self, n: int) -> np.ndarray:
        a_pink = 0.985 ** (22_050.0 / SR)
        x = self._rng.standard_normal_vec(n)
        kernel = a_pink ** np.arange(_kernel_len(a_pink))
        conv = np.convolve(x, kernel)[:n] + (a_pink ** np.arange(1, n + 1)) * self._pink
        self._pink = float(conv[-1])
        pink_gain = np.sqrt(1.0 - a_pink * a_pink) * 0.25
        return conv * pink_gain


def _kernel_len(decay: float) -> int:
    """Samples until an exponential kernel is inaudible (<1e-4)."""
    if decay <= 0.0:
        return 1
    return max(1, int(np.ceil(-9.2 / np.log(decay))))
