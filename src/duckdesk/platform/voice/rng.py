"""Deterministic RNG for the voice stream — port of sounds/src/rng.rs.

xoshiro256++ seeded through splitmix64 (both public domain, Blackman & Vigna).
The generator IS the voice: the bank re-renders from the seed, so the stream
must never drift. Uniforms take the top 53 bits; normals are Box-Muller.
"""

from __future__ import annotations

import math
import zlib

import numpy as np

_M64 = (1 << 64) - 1
TAU = math.tau

# Upstream rng.rs uses "crc32 as zlib.crc32 computes it".
crc32 = zlib.crc32


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & _M64


class Rng:
    """Deterministic stream of the distributions the recipes use."""

    __slots__ = ("_s", "_spare")

    def __init__(self, seed: int):
        # splitmix64 expands the u32 into the four xoshiro words (rng.rs from_seed).
        x = seed & _M64
        s = []
        for _ in range(4):
            x = (x + 0x9E3779B97F4A7C15) & _M64
            z = x
            z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
            z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
            s.append((z ^ (z >> 31)) & _M64)
        self._s = s
        self._spare: float | None = None

    def _next_u64(self) -> int:
        s = self._s
        result = (_rotl((s[0] + s[3]) & _M64, 23) + s[0]) & _M64
        t = (s[1] << 17) & _M64
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = _rotl(s[3], 45)
        return result

    def random(self) -> float:
        """Uniform in [0, 1), from the top 53 bits."""
        return (self._next_u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.random()

    def integers(self, lo: int, hi: int) -> int:
        """Uniform integer in [lo, hi) — numpy's half-open convention."""
        return lo + math.floor(self.random() * (hi - lo))

    def choice(self, choices) -> float:
        return choices[self.integers(0, len(choices))]

    def standard_normal(self) -> float:
        """Standard normal, Box-Muller (the spare is handed out next call)."""
        if self._spare is not None:
            v, self._spare = self._spare, None
            return v
        r = 1.0 - self.random()  # in (0, 1], so ln stays finite
        theta = TAU * self.random()
        mag = math.sqrt(-2.0 * math.log(r))
        self._spare = mag * math.sin(theta)
        return mag * math.cos(theta)

    def standard_normal_vec(self, n: int) -> np.ndarray:
        """n standard normals, as the vectorised numpy calls drew them."""
        return np.array([self.standard_normal() for _ in range(n)], dtype=np.float64)
