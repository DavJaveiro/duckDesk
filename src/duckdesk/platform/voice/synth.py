"""DSP primitives for the duck voice — port of sounds/src/synth.rs.

The original Python rendered at 22.05 kHz and the installer resampled; the
Rust port renders at 48 kHz natively and rescales the two sample-count
constants (jitter window, pink-noise pole) by SR / TUNED_SR so they keep
their time-domain character. Same here.
"""

from __future__ import annotations

import numpy as np

from duckdesk.platform.voice.rng import Rng

SR = 48_000  # output sample rate (synth.rs)
TUNED_SR = 22_050.0  # rate the Python recipes were tuned at
TAU = float(np.tau) if hasattr(np, "tau") else 2.0 * np.pi


def t_axis(duration_s: float) -> np.ndarray:
    """Time axis for a duration, one entry per sample."""
    n = max(1, round(duration_s * SR))
    return np.arange(n, dtype=np.float64) / SR


def lerp(t: np.ndarray, points) -> np.ndarray:
    """Piecewise-linear curve through (time_s, value) points — np.interp,
    which clamps to the first/last value outside the range."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return np.interp(t, xs, ys)


def expdecay(t: np.ndarray, attack_s: float, decay_s: float) -> np.ndarray:
    """Fast attack, exponential decay envelope, peak ~1.0."""
    attack = max(attack_s, 1e-4)
    decay = max(decay_s, 1e-4)
    return np.clip(t / attack, 0.0, 1.0) * np.exp(-np.maximum(t - attack, 0.0) / decay)


def bell(t: np.ndarray, attack_s: float, release_s: float) -> np.ndarray:
    """Soft attack, plateau, soft release."""
    total = float(t[-1]) if len(t) else 0.0
    rel_start = max(total - release_s, 0.0)
    attack = max(attack_s, 1e-4)
    release = max(release_s, 1e-4)
    v = np.ones(len(t))
    in_attack = t < attack_s
    v[in_attack] = t[in_attack] / attack
    in_release = t > rel_start
    v[in_release] = np.maximum(0.0, 1.0 - (t[in_release] - rel_start) / release)
    return np.clip(v, 0.0, 1.0)


def phase_from_freq(freq: np.ndarray) -> np.ndarray:
    """Integrate instantaneous frequency to phase (radians)."""
    return np.cumsum(freq) * (TAU / SR)


def harmonic_osc(phase: np.ndarray, weights) -> np.ndarray:
    """Sum of sin(n*phase)*weight for each harmonic (n = 1..)."""
    out = np.zeros(len(phase))
    for n, w in enumerate(weights, start=1):
        if w != 0.0:
            out += w * np.sin(n * phase)
    return out


def vibrato(t: np.ndarray, rate_hz: float, depth_semitones: float, phase: float) -> np.ndarray:
    """Pitch multiplier from a slow LFO — multiply a frequency curve by it."""
    if rate_hz <= 0.0 or depth_semitones <= 0.0:
        return np.ones(len(t))
    return 2.0 ** (depth_semitones * np.sin(TAU * rate_hz * t + phase) / 12.0)


def moving_average_same(x: np.ndarray, k: int) -> np.ndarray:
    """np.convolve(x, ones(k)/k, 'same') — the Rust port's own semantics."""
    return np.convolve(x, np.ones(k) / k, mode="same")


def jitter(t: np.ndarray, depth_semitones: float, rng: Rng) -> np.ndarray:
    """Random pitch wobble, smoothed white noise — the organic, alive feel.

    The Python smoothed over 64 samples at 22.05 kHz (~2.9 ms); the window
    scales with the rate so the wobble keeps its speed (synth.rs).
    """
    if depth_semitones <= 0.0:
        return np.ones(len(t))
    raw = rng.standard_normal_vec(len(t))
    window = max(1, round(64.0 * SR / TUNED_SR))
    smoothed = moving_average_same(raw, window)
    return 2.0 ** (depth_semitones * smoothed / 12.0)


def pink_noise(n: int, rng: Rng) -> np.ndarray:
    """Cheap pink-ish noise via a leaky integrator over white.

    The pole (0.985/sample at 22.05 kHz) is rescaled so the noise keeps its
    colour at 48 kHz (synth.rs). Computed via an exponential-kernel
    convolution — identical to the recursive loop, only vectorised.
    """
    a = 0.985 ** (TUNED_SR / SR)
    white = rng.standard_normal_vec(n)
    # y[i] = sum_j a**j * white[i-j]; the kernel dies to <1e-4 after
    # ~9.2 / -ln(a) samples, so truncating there loses nothing audible.
    klen = min(n, max(1, int(np.ceil(-9.2 / np.log(a)))))
    kernel = a ** np.arange(klen)
    pink = np.convolve(white, kernel, mode="full")[:n]
    peak = float(np.max(np.abs(pink))) + 1e-9
    return pink / peak


def click(n: int, rng: Rng, length: int) -> np.ndarray:
    """Short transient click — the peck attack."""
    out = np.zeros(n)
    length = min(length, n)
    if length > 0:
        fade = 1.0 - np.arange(length) / length
        out[:length] = np.array(
            [rng.uniform(-1.0, 1.0) for _ in range(length)], dtype=np.float64
        ) * (fade * fade)
    return out


def normalise(x: np.ndarray, peak_dbfs: float) -> np.ndarray:
    """Scale to a peak level in dBFS."""
    peak = float(np.max(np.abs(x))) + 1e-9
    return x * (10.0 ** (peak_dbfs / 20.0) / peak)


def to_i16(x: np.ndarray) -> np.ndarray:
    """f32 -1..1 to int16 PCM samples."""
    return np.clip(x * 32767.0, -32768.0, 32767.0).astype(np.int16)
