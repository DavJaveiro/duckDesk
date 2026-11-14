"""A Personality derives stable per-robot vocal traits from a single seed —
port of sounds/src/personality.rs.

Two robots with different seeds sound recognisably different; the same robot
is consistent across runs. Variants within a tag re-roll a small sub-seed so
the duck doesn't sound like a stuck recording.
"""

from __future__ import annotations

import dataclasses
import zlib
from dataclasses import dataclass

from duckdesk.platform.voice.rng import Rng

N_HARM = 7


@dataclass
class Personality:
    """Every field is a stable function of the seed.

    `replace()` mirrors the Rust `Copy` + field tweak pattern the recipes use
    to soften a voice per tag (e.g. chirp's gutted quackiness)."""

    seed: int

    # --- pitch ---
    pitch_center_hz: float
    register: float  # -1..+1, extra octave-ish shift on top of center
    pitch_spread: float  # 0..1+, how dramatic glides are
    glide_bias: float  # -1..+1, negative = falls, positive = rises

    # --- timbre ---
    brightness: float  # 0..1, harmonic rolloff (1 = bright/buzzy)
    tilt: float  # 1.4..2.8, exponent on harmonic decay (higher = darker)
    nasal: float  # 0..1, emphasis on 2nd/3rd harmonic
    harmonic_skew: float  # -1..+1, negative = odd-only, positive = even-leaning
    formant_n: int  # 1..5, which harmonic the formant boosts
    formant_gain: float  # 0..1.5, formant strength

    # --- modulation ---
    vibrato_rate_hz: float
    vibrato_depth: float  # 0..0.7 semitones
    jitter_depth: float  # 0..0.4 semitones, random pitch wobble
    breath: float  # 0..0.35, noise mix
    quackiness: float  # 0.2..1, blends pure-tone vs am-buzz
    am_rate_hz: float  # 18..55, quack/croak-buzz rate
    am_depth: float  # 0..0.7, modulation depth
    warble_hz: float  # 7..18, trill on chirp
    warble_depth: float  # 0..1.5 semitones

    # --- timing ---
    attack_sharpness: float  # 0..1, 0 = soft pad, 1 = snappy
    speed: float  # 0.8..1.25, global tempo multiplier

    @staticmethod
    def from_seed(seed: int) -> Personality:
        rng = Rng(seed & 0xFFFFFFFF)

        # Bimodal-ish register: some ducks smaller & higher, some big & low —
        # but the whole population sits low, duck/toad territory.
        register = rng.choice([-1.0, 0.0, 0.0, 1.0]) + rng.uniform(-0.4, 0.4)
        base = rng.uniform(160.0, 380.0)
        pitch = min(620.0, max(110.0, base * 2.0 ** (register * 0.45)))

        return Personality(
            seed=seed,
            pitch_center_hz=pitch,
            register=register,
            pitch_spread=rng.uniform(0.4, 1.2),
            glide_bias=rng.uniform(-1.0, 1.0),
            brightness=rng.uniform(0.05, 0.55),
            tilt=rng.uniform(1.4, 2.8),
            nasal=rng.uniform(0.1, 1.0),
            harmonic_skew=rng.uniform(-1.0, 1.0),
            formant_n=int(rng.integers(1, 6)),
            formant_gain=rng.uniform(0.0, 1.4),
            vibrato_rate_hz=rng.uniform(3.5, 9.5),
            vibrato_depth=rng.uniform(0.0, 0.7),
            jitter_depth=rng.uniform(0.03, 0.35),
            breath=rng.uniform(0.0, 0.30),
            quackiness=rng.uniform(0.2, 1.0),
            am_rate_hz=rng.uniform(18.0, 55.0),
            am_depth=rng.uniform(0.15, 0.70),
            warble_hz=rng.uniform(7.0, 18.0),
            warble_depth=rng.uniform(0.0, 1.4),
            attack_sharpness=rng.uniform(0.0, 1.0),
            speed=rng.uniform(0.82, 1.22),
        )

    def replace(self, **kw) -> Personality:
        """Softened copy, as the Rust recipes mutate a `Copy` (e.g. p_soft)."""
        return dataclasses.replace(self, **kw)

    def variant_rng(self, tag: str, variant: int) -> Rng:
        """Stable per-(seed, tag, variant) RNG for sub-randomisation.

        CRC-32, not a salted hasher — the bank's variants must survive
        regeneration (personality.rs).
        """
        h = (
            ((self.seed * 1_000_003) & 0xFFFFFFFFFFFFFFFF)
            ^ zlib.crc32(tag.encode())
            ^ ((variant * 2_654_435_761) & 0xFFFFFFFFFFFFFFFF)
        )
        return Rng(h & 0xFFFFFFFF)

    def harmonics(self) -> list:
        """Personality-shaped harmonic weights for the main oscillator.

        Tilt (overall rolloff), brightness (high-end tail), nasal (2nd/3rd),
        harmonic_skew (even-vs-odd), and a formant bump at one harmonic.
        """
        weights = []
        for n in range(1, N_HARM + 1):
            base = 1.0 / n**self.tilt
            high_lift = self.brightness * (n / N_HARM) ** 1.5
            nasal = self.nasal * (0.6 if n in (2, 3) else 0.0)
            if self.harmonic_skew >= 0.0:
                skew = self.harmonic_skew * (0.4 if n % 2 == 0 else -0.2)
            else:
                skew = -self.harmonic_skew * (-0.3 if n % 2 == 0 else 0.4)
            formant = self.formant_gain if n == self.formant_n else 0.0
            weights.append(max(0.0, base + high_lift + nasal + skew + formant * base * 1.5))
        # Keep f0 dominant so pitch is always perceptible.
        weights[0] = max(weights[0], 0.7)
        return weights
