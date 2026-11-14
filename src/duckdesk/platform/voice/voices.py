"""Recipes for each voice tag — port of sounds/src/voices.rs.

Recipes paint with the personality's traits — pitch center, register, glide
bias, harmonic tilt/formant, quackiness, warble — so the *same* recipe on two
different seeds gives two recognisably different ducks.
"""

from __future__ import annotations

import numpy as np

from duckdesk.platform.voice import synth as s
from duckdesk.platform.voice.personality import Personality
from duckdesk.platform.voice.synth import SR, TAU

TAGS = ("alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee")


def variant_count(tag: str) -> int:
    """Variants per tag (lib.rs): the most-heard tags get the most."""
    return {"greet": 12, "chirp": 12, "wheee": 6}.get(tag, 10)


def _attack(p: Personality, dur: float, snappy: float) -> float:
    """Attack time, modulated by attack_sharpness (voices.rs `attack`)."""
    soft = 0.04 * dur
    sharp = 0.003 * dur
    return max(0.001, soft + (sharp - soft) * p.attack_sharpness * snappy)


def _voice(p: Personality, t, freq, rng, am_scale: float, breath_scale: float):
    """Shared core: harmonic osc + vibrato + jitter + (optional) AM buzz + breath."""
    vib = s.vibrato(t, p.vibrato_rate_hz, p.vibrato_depth, rng.uniform(0.0, TAU))
    jit = s.jitter(t, p.jitter_depth, rng)
    f = freq * vib * jit
    phase = s.phase_from_freq(f)
    body = s.harmonic_osc(phase, p.harmonics())

    # Quackiness gates the AM buzz: pure-tone ducks have ~no AM.
    am_d = p.am_depth * am_scale * p.quackiness
    if am_d > 0.01:
        body = body * (1.0 - am_d * (0.5 + 0.5 * np.sin(TAU * p.am_rate_hz * t)))

    breath = p.breath * breath_scale
    if breath > 0.0:
        body = body + breath * s.pink_noise(len(t), rng)
    return body


def alarm(p: Personality, variant: int) -> np.ndarray:
    rng = p.variant_rng("alarm", variant)
    dur = (0.20 + 0.12 * rng.random()) / p.speed
    t = s.t_axis(dur)
    # Raised relative to this duck's center, but stays in honk range.
    f0 = p.pitch_center_hz * (1.25 + 0.35 * p.pitch_spread) * (0.94 + 0.12 * rng.random())
    peak_mul = 1.15 + 0.25 * p.pitch_spread + 0.10 * rng.random()
    fall_mul = 0.75 + 0.20 * (1.0 - p.pitch_spread)
    freq = s.lerp(t, [(0.0, f0), (0.05 * dur, f0 * peak_mul), (dur, f0 * fall_mul)])
    env = s.expdecay(t, _attack(p, dur, 1.0), dur * (0.40 + 0.20 * rng.random()))
    sig = _voice(p, t, freq, rng, 0.5, 1.0) * env
    # Crackle scales with brightness — bright ducks rasp, soft ducks just yelp.
    crackle = 0.04 + 0.10 * p.brightness
    sig = sig + crackle * rng.standard_normal_vec(len(t)) * env
    return s.normalise(sig, -3.0)


def _greet_syllable(p: Personality, rng, dur_scale: float, f0_scale: float) -> np.ndarray:
    dur = (0.32 + 0.25 * rng.random()) * dur_scale / p.speed
    t = s.t_axis(dur)
    f0 = p.pitch_center_hz * (0.9 + 0.15 * rng.random()) * f0_scale
    # glide_bias flips the contour: positive ducks bend up, negative down.
    bias = p.glide_bias
    bend = 0.10 + 0.15 * p.pitch_spread
    start = f0 * (1.0 - bias * bend * 0.5)
    mid = f0 * (1.0 + bias * bend)
    end = f0 * (1.0 - bias * bend * 0.3) * (0.92 + 0.08 * rng.random())
    freq = s.lerp(t, [(0.0, start), (0.18 * dur, mid), (dur, end)])
    env = s.expdecay(t, _attack(p, dur, 0.5), dur * 0.7)
    return _voice(p, t, freq, rng, 1.0, 1.0) * env


def greet(p: Personality, variant: int) -> np.ndarray:
    rng = p.variant_rng("greet", variant)
    sig = _greet_syllable(p, rng, 1.0, 1.0)
    # Some greets are double quacks — "wak-wak" (voices.rs).
    if rng.random() < 0.4:
        gap_n = int((0.05 + 0.06 * rng.random()) / p.speed * SR)
        sig = np.concatenate(
            [sig, np.zeros(gap_n), _greet_syllable(p, rng, 0.8, 0.95 + 0.06 * rng.random())]
        )
    return s.normalise(sig, -3.0)


def inquire(p: Personality, variant: int) -> np.ndarray:
    rng = p.variant_rng("inquire", variant)
    dur = (0.42 + 0.25 * rng.random()) / p.speed
    t = s.t_axis(dur)
    f0 = p.pitch_center_hz * (0.88 + 0.10 * rng.random())
    # Always rises (it's a question), but how much depends on spread + bias.
    rise = 1.15 + 0.50 * p.pitch_spread + 0.20 * max(0.0, p.glide_bias) + 0.10 * rng.random()
    freq = s.lerp(t, [(0.0, f0 * 0.92), (0.30 * dur, f0 * 0.95), (dur, f0 * rise)])
    env = s.bell(t, dur * (0.06 + 0.10 * (1.0 - p.attack_sharpness)), dur * 0.32)
    sig = _voice(p, t, freq, rng, 0.6, 1.0) * env
    return s.normalise(sig, -3.0)


def peck(p: Personality, variant: int) -> np.ndarray:
    rng = p.variant_rng("peck", variant)
    dur = (0.16 + 0.12 * rng.random()) / p.speed
    t = s.t_axis(dur)
    # Always low for this duck; bigger ducks (low register) get even lower pecks.
    f0 = p.pitch_center_hz * (0.45 + 0.20 * rng.random())
    freq = s.lerp(t, [(0.0, f0 * 1.5), (0.04 * dur, f0), (dur, f0 * 0.80)])
    env = s.expdecay(t, _attack(p, dur, 1.0), dur * 0.35)
    body = _voice(p, t, freq, rng, 0.3, 0.5) * env
    # Click amount depends on attack_sharpness — snappy ducks have a sharper "tock".
    click_len = int((0.003 + 0.006 * p.attack_sharpness) * SR)
    click_gain = 0.4 + 0.4 * p.attack_sharpness
    body = body + click_gain * s.click(len(t), rng, click_len)
    return s.normalise(body, -3.0)


def _chirp_syllable(p: Personality, rng, f0: float, dur: float, contour) -> np.ndarray:
    t = s.t_axis(dur)
    # Warble: rapid trill, depth & rate are personality-driven.
    warble = s.vibrato(t, p.warble_hz, p.warble_depth, rng.uniform(0.0, TAU))
    shape = s.lerp(t, contour)
    freq = f0 * shape * warble
    env = s.expdecay(t, _attack(p, dur, 0.7), dur * 0.55)
    # Softer than greet: gut quackiness and brightness.
    p_soft = p.replace(
        quackiness=p.quackiness * 0.2,
        brightness=p.brightness * 0.5,
        formant_gain=p.formant_gain * 0.5,
    )
    return _voice(p_soft, t, freq, rng, 1.0, 0.4) * env


def chirp(p: Personality, variant: int) -> np.ndarray:
    """Mouth-trigger sound. Variants cycle four distinct shapes — rise, fall,
    trill, double — so random picks read as different calls (voices.rs)."""
    rng = p.variant_rng("chirp", variant)
    shape = variant % 4
    f0 = p.pitch_center_hz * (0.95 + 0.75 * rng.random())
    if shape == 0:
        # Rising blip.
        dur = (0.10 + 0.10 * rng.random()) / p.speed
        peak = 1.12 + 0.10 * rng.random()
        sig = _chirp_syllable(p, rng, f0, dur, [(0.0, 0.88), (0.5 * dur, peak), (dur, 1.05)])
    elif shape == 1:
        # Falling blip.
        dur = (0.10 + 0.10 * rng.random()) / p.speed
        start = 1.12 + 0.10 * rng.random()
        sig = _chirp_syllable(p, rng, f0, dur, [(0.0, start), (0.3 * dur, 1.0), (dur, 0.78)])
    elif shape == 2:
        # Trill — longer, warble cranked up.
        dur = (0.22 + 0.14 * rng.random()) / p.speed
        p_trill = p.replace(warble_depth=max(p.warble_depth, 0.7) * 1.6)
        sig = _chirp_syllable(p_trill, rng, f0, dur, [(0.0, 1.0), (0.5 * dur, 1.06), (dur, 0.94)])
    else:
        # Double "wek-wek".
        dur = (0.08 + 0.05 * rng.random()) / p.speed
        head = _chirp_syllable(p, rng, f0, dur, [(0.0, 0.95), (0.4 * dur, 1.10), (dur, 0.88)])
        gap_n = int((0.03 + 0.03 * rng.random()) / p.speed * SR)
        dur_b = dur * 0.9
        tail = _chirp_syllable(
            p,
            rng,
            f0 * (0.92 + 0.10 * rng.random()),
            dur_b,
            [(0.0, 0.95), (0.4 * dur_b, 1.10), (dur_b, 0.88)],
        )
        sig = np.concatenate([head, np.zeros(gap_n), tail])
    return s.normalise(sig, -6.0)


def coo(p: Personality, variant: int) -> np.ndarray:
    rng = p.variant_rng("coo", variant)
    dur = (0.85 + 0.55 * rng.random()) / p.speed
    t = s.t_axis(dur)
    # Well below center — drowsy ducks drop further.
    f0 = (
        p.pitch_center_hz
        * (0.42 + 0.15 * (1.0 - p.attack_sharpness))
        * (0.94 + 0.12 * rng.random())
    )
    drift_a = 1.0 + 0.05 * rng.random() + 0.04 * p.glide_bias
    freq = s.lerp(t, [(0.0, f0 * 0.94), (dur * 0.5, f0 * drift_a), (dur, f0 * 0.90)])
    env = s.bell(t, dur * (0.18 + 0.10 * (1.0 - p.attack_sharpness)), dur * 0.30)
    # Breathier, much slower modulation, no buzz.
    p_soft = p.replace(
        breath=max(p.breath, 0.12) + 0.10,
        quackiness=p.quackiness * 0.25,
        am_rate_hz=p.am_rate_hz * 0.30,
        vibrato_rate_hz=p.vibrato_rate_hz * 0.45,
        vibrato_depth=p.vibrato_depth * 0.7,
    )
    sig = _voice(p_soft, t, freq, rng, 1.0, 1.0) * env
    return s.normalise(sig, -5.0)


def wheee_segments(p: Personality, variant: int):
    """(start, loop, end) for the held-trigger joy ride (voices.rs).

    Rendered as ONE continuous master and sliced, so jitter/breath/wobble
    carry across the start->loop cut with no seam; the loop tail is crossfaded
    onto the master just before the loop start so it wraps without a click.
    """
    rng = p.variant_rng("wheee", variant)
    d_start = (0.80 + 0.30 * rng.random()) / p.speed
    d_loop = (1.60 + 0.60 * rng.random()) / p.speed
    d_end = (0.55 + 0.25 * rng.random()) / p.speed
    total = d_start + d_loop + d_end
    t = s.t_axis(total)
    t1, t2 = d_start, d_start + d_loop

    f0 = p.pitch_center_hz * (0.95 + 0.10 * rng.random())
    top = 1.6 + 0.5 * p.pitch_spread + 0.25 * rng.random()
    base = s.lerp(
        t,
        [
            (0.0, f0 * 0.85),
            (0.15 * d_start, f0),
            (t1, f0 * top),
            (t2, f0 * top),
            (t2 + 0.25 * d_end, f0 * top * 1.04),
            (total, f0 * 0.60),
        ],
    )
    # Excitement wobble, swelling as the ride picks up, steady in the loop.
    wob_hz = 4.5 + 3.0 * rng.random()
    swell = s.lerp(t, [(0.0, 0.15), (t1, 1.0), (total, 1.0)])
    wob = np.sin(TAU * wob_hz * t)
    freq = base * 2.0 ** (0.5 * swell * wob / 12.0)

    env = s.lerp(
        t,
        [
            (0.0, 0.0),
            (min(0.06, 0.5 * d_start), 1.0),
            (t2 + 0.40 * d_end, 1.0),
            (total, 0.0),
        ],
    )
    # The wobble replaces vibrato; less buzz so the glide stays clean.
    p_joy = p.replace(vibrato_depth=p.vibrato_depth * 0.5, quackiness=p.quackiness * 0.5)
    sig = _voice(p_joy, t, freq, rng, 0.5, 0.5) * env
    # Normalise the master, THEN slice — segment levels must match.
    sig = s.normalise(sig, -4.0)

    n1, n2 = int(t1 * SR), int(t2 * SR)
    start, loop_seg, end = sig[:n1].copy(), sig[n1:n2].copy(), sig[n2:].copy()
    nx = min(int(0.08 * SR), len(loop_seg) // 2, n1)
    if nx > 1:
        w = np.arange(nx) / (nx - 1)
        tail = len(loop_seg) - nx + np.arange(nx)
        loop_seg[tail] = (1.0 - w) * loop_seg[tail] + w * sig[n1 - nx + np.arange(nx)]
    return start, loop_seg, end


def wheee(p: Personality, variant: int) -> np.ndarray:
    """One full ride — start, two loop passes (seam auditable), end."""
    start, loop_seg, end = wheee_segments(p, variant)
    return np.concatenate([start, loop_seg, loop_seg, end])


_RECIPES = {
    "alarm": alarm,
    "greet": greet,
    "inquire": inquire,
    "peck": peck,
    "chirp": chirp,
    "coo": coo,
    "wheee": wheee,
}


def render(tag: str, p: Personality, variant: int) -> np.ndarray:
    """One sound: personality + variant in, f32 mono at SR out."""
    return _RECIPES[tag](p, variant).astype(np.float32)
