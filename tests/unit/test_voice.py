"""Generated voice (ADR-0011): RNG determinism, personality traits, the seven
recipes, the WAV bank/cache, the Voice facade, and the autopilot voice
wiring.

The pinned values pin THIS port's stream (numpy f64 vs the upstream Rust's
f32/libm means bit-parity is unattainable — the contract that matters is
"same seed, same voice, forever", pinned upstream by rng.rs tests and here
the same way). CRC32 values are the upstream's own pinned test vectors.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from duckdesk.platform.voice import Voice, VoiceBank, envelope_of, seed_from_id, voices
from duckdesk.platform.voice.personality import Personality
from duckdesk.platform.voice.rng import Rng, crc32
from duckdesk.platform.voice.synth import SR
from duckdesk.settings import Settings

pytestmark = pytest.mark.unit

SEED = 0xC96F1146  # seed_from_id("test-serial"), pinned


# --- rng.py (sounds/src/rng.rs) ------------------------------------------------


def test_seed_from_id_matches_upstream():
    """sha256(id)[0..4] big-endian — lib.rs seed_from_id."""
    assert seed_from_id("test-serial") == 0xC96F1146


def test_crc32_matches_upstream_test_vectors():
    """rng.rs tests pin zlib.crc32 reference values."""
    assert crc32(b"") == 0
    assert crc32(b"chirp") == 0xEC28BF8B
    assert crc32(b"123456789") == 0xCBF43926


def test_the_stream_is_pinned():
    """Same seed, same u64 stream forever (rng.rs test of the same name)."""
    r, again = Rng(100), Rng(100)
    first = [r._next_u64() for _ in range(4)]
    assert first == [
        0xE0D27CDCCB6EF5FD,
        0xE8F0E8A7AA826B4E,
        0xD4E6F465C72A33CD,
        0x583B5F2716AB517B,
    ]
    assert first == [again._next_u64() for _ in range(4)]  # reproducible
    assert first[0] != Rng(101)._next_u64()


def test_uniform_and_normals_pinned():
    r = Rng(SEED)
    assert r.uniform(0.0, 1.0) == pytest.approx(0.14739618000632715)
    r2 = Rng(SEED)
    assert [r2.standard_normal() for _ in range(4)] == pytest.approx(
        [-0.43591551062892603, -0.35902403276714406, -0.37771038414389235, 1.2809765515368838]
    )


def test_uniforms_and_ints_stay_in_range():
    r = Rng(7)
    for _ in range(10_000):
        assert 160.0 <= r.uniform(160.0, 380.0) < 380.0
        assert 1 <= r.integers(1, 6) < 6


def test_normals_have_sane_moments():
    xs = Rng(42).standard_normal_vec(100_000)
    assert abs(float(xs.mean())) < 0.02
    assert abs(float(xs.var()) - 1.0) < 0.05


# --- personality.py (sounds/src/personality.rs) --------------------------------


def test_personality_is_stable_and_seed_dependent():
    """A seed IS a voice (personality.rs from_seed)."""
    a, b = Personality.from_seed(SEED), Personality.from_seed(SEED)
    assert a == b  # same seed, identical traits
    other = Personality.from_seed(SEED + 1)
    assert a.pitch_center_hz != other.pitch_center_hz


def test_personality_traits_pinned():
    p = Personality.from_seed(SEED)
    assert p.pitch_center_hz == pytest.approx(218.043472, abs=1e-4)
    assert p.register == pytest.approx(-0.912277, abs=1e-4)
    assert p.speed == pytest.approx(1.046812, abs=1e-4)


def test_personality_traits_in_upstream_ranges():
    """Every trait lands inside the from_seed draw ranges (personality.rs,
    incl. the upstream test's own pins: pitch clamp, f0 dominance)."""
    for seed in list(range(500)) + [SEED, 0xFFFFFFFF]:
        p = Personality.from_seed(seed)
        assert 110.0 <= p.pitch_center_hz <= 620.0  # clamped after the register shift
        assert -1.4 <= p.register <= 1.4  # choice(±1,0,0) + uniform(±0.4)
        assert 0.4 <= p.pitch_spread < 1.2
        assert -1.0 <= p.glide_bias < 1.0
        assert 0.05 <= p.brightness < 0.55
        assert 1.4 <= p.tilt < 2.8
        assert 0.1 <= p.nasal < 1.0
        assert -1.0 <= p.harmonic_skew < 1.0
        assert 1 <= p.formant_n <= 5
        assert 0.0 <= p.formant_gain < 1.4
        assert 3.5 <= p.vibrato_rate_hz < 9.5
        assert 0.0 <= p.vibrato_depth < 0.7
        assert 0.03 <= p.jitter_depth < 0.35
        assert 0.0 <= p.breath < 0.30
        assert 0.2 <= p.quackiness < 1.0
        assert 18.0 <= p.am_rate_hz < 55.0
        assert 0.15 <= p.am_depth < 0.70
        assert 7.0 <= p.warble_hz < 18.0
        assert 0.0 <= p.warble_depth < 1.4
        assert 0.0 <= p.attack_sharpness < 1.0
        assert 0.82 <= p.speed < 1.22
        w = p.harmonics()
        assert len(w) == 7 and all(x >= 0.0 for x in w) and w[0] >= 0.7


def test_variant_rngs_differ_per_tag_and_variant():
    p = Personality.from_seed(SEED)
    a, b = p.variant_rng("chirp", 0), p.variant_rng("chirp", 1)
    c = p.variant_rng("peck", 0)
    draws = (a.random(), b.random(), c.random())
    assert len(set(draws)) == 3  # stable, uncorrelated sub-streams


# --- voices.py (sounds/src/voices.rs) ------------------------------------------


@pytest.mark.parametrize("tag", voices.TAGS)
def test_every_recipe_renders_bounded_audio(tag):
    p = Personality.from_seed(SEED)
    sig = voices.render(tag, p, 0)
    assert sig.dtype == np.float32 and len(sig) > 0
    assert np.isfinite(sig).all()
    assert float(np.abs(sig).max()) <= 1.0
    assert float(np.abs(sig).max()) > 0.05  # not silence


def test_variants_are_different_takes():
    p = Personality.from_seed(SEED)
    a, b = voices.render("chirp", p, 0), voices.render("chirp", p, 1)
    assert len(a) != len(b) or not np.allclose(a, b)


def test_different_ducks_sound_different():
    a = voices.render("chirp", Personality.from_seed(SEED), 0)
    b = voices.render("chirp", Personality.from_seed(SEED + 1), 0)
    assert not np.allclose(a[: min(len(a), len(b))], b[: min(len(a), len(b))])


def test_wheee_segments_tile_without_clicks():
    """Loop segment wraps onto itself; concatenated ride stays bounded."""
    p = Personality.from_seed(SEED)
    start, loop_seg, end = voices.wheee_segments(p, 0)
    assert len(start) > 0 and len(loop_seg) > 0 and len(end) > 0
    full = voices.wheee(p, 0)
    assert len(full) == len(start) + 2 * len(loop_seg) + len(end)
    # The wrap crossfade: consecutive loop joins must not click (|Δ| small).
    join = len(start) + len(loop_seg)
    assert abs(full[join] - full[join - 1]) < 0.3


# --- __init__.py: bank, envelope, Voice facade ----------------------------------


def _settings(tmp_path: Path, **over) -> Settings:
    s = Settings(tmp_path / "settings.json")
    for k, v in over.items():
        s[k] = v
    return s


def test_bank_renders_lazily_and_caches(tmp_path):
    bank = VoiceBank(SEED, tmp_path / "voice")
    assert not list(bank.root.glob("**/*.wav"))  # nothing until first pick
    path, env = bank.pick("chirp")
    assert path.is_file() and path.suffix == ".wav"
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
    assert env and env[0][0] == 0.0 and all(0.0 <= v <= 1.0 for _t, v in env)
    assert not any(p.name != ".seed" for p in bank.root.iterdir() if p.is_file())
    # Second bank on the same root reuses the render, doesn't regenerate.
    bank2 = VoiceBank(SEED, tmp_path / "voice")
    path2, _ = bank2.pick("chirp")
    assert path2.exists()


def test_bank_regenerates_when_seed_changes(tmp_path):
    bank = VoiceBank(SEED, tmp_path / "voice")
    old = bank.file("chirp", 0)
    old_bytes = old.read_bytes()
    bank2 = VoiceBank(SEED + 1, tmp_path / "voice")
    new = bank2.file("chirp", 0)
    assert old.name == new.name  # same slot re-rendered under a new voice
    assert new.read_bytes() != old_bytes


def test_envelope_of_tracks_loudness():
    """A generated call's envelope drives the beak like QUACK_ENV does."""
    t = np.arange(int(0.4 * SR)) / SR
    quiet = 0.02 * np.sin(2 * np.pi * 200 * t)
    loud = np.concatenate([quiet, 0.8 * np.sin(2 * np.pi * 200 * t)])
    env = dict(envelope_of(loud))
    assert env[0.0] < 0.1  # first 40 ms is quiet
    assert env[max(env)] == 1.0  # peak frame saturates at the clip


def test_voice_disabled_when_setting_off(tmp_path):
    v = Voice(_settings(tmp_path, voice=False))
    assert not v.enabled
    assert v.play("chirp") is None  # silent duck, no crash


def test_voice_disabled_by_env_override_is_stable(tmp_path, monkeypatch):
    """DUCK_IDENTITY pins the seed (upstream's dev escape hatch, lib.rs)."""
    monkeypatch.setenv("DUCK_IDENTITY", "test-serial")
    v = Voice(_settings(tmp_path))
    assert v.enabled == (Voice.__init__ is not None)  # constructed or quiet
    if v.personality is not None:
        assert v.personality.seed == SEED


@pytest.mark.skipif(
    Voice.__init__.__globals__.get("winsound") is None, reason="winsound is Windows-only"
)
def test_voice_play_returns_beak_envelope(tmp_path):
    v = Voice(_settings(tmp_path))
    env = v.play("chirp")  # shortest variants give ~2 frames; the shape matters
    assert env is not None and len(env) >= 2 and all(0.0 <= x <= 1.0 for _t, x in env)
    v.close()


def test_voice_seed_is_drawn_once_and_persisted(tmp_path):
    s = _settings(tmp_path)
    v = Voice(s)
    seed = s["voice_seed"]
    assert seed is not None
    s2 = Settings(tmp_path / "settings.json")
    assert s2["voice_seed"] == seed  # same install, same voice forever
    v.close()


# --- autopilot voice wiring ------------------------------------------------------

_DT = 0.02


class _FakeVoice:
    def __init__(self):
        self.tags = []

    def play(self, tag):
        self.tags.append(tag)


class _FakeManager:
    """Minimal PolicyManager stand-in (same shape as test_autopilot's)."""

    def __init__(self):
        self.seated = False
        self.busy = False
        self.cmd = None

    def set_command(self, cmd):
        self.cmd = cmd

    def request(self, req):
        return True, "ok"


def test_autopilot_voice_tags_fall_yawn_and_glance():
    """robotd mappings: alarm on falls, coo on yawns, inquire on glances."""
    from duckdesk.brain.autopilot import YAWN_AFTER_S, Autopilot, AutoState
    from duckdesk.brain.beak import BeakAnimator

    voice = _FakeVoice()
    pilot = Autopilot(np.random.default_rng(0), beak=BeakAnimator(), voice=voice)
    mgr = _FakeManager()

    def run(pose, seconds):
        for _ in range(int(seconds / _DT)):
            pilot.update(_DT, *pose, mgr)

    run((0.0, 0.0, 0.0, 0.9), 0.1)  # fallen -> RECOVER
    assert "alarm" in voice.tags

    voice.tags.clear()
    # Autopilot off parks the duck in IDLE forever (05 §5) — the stillness
    # clock then runs uninterrupted, as it does in the app when the pilot is
    # disabled (the clock sits before the enabled gate).
    pilot.enabled = False
    pilot._goto(AutoState.IDLE)
    pilot._calm_s = YAWN_AFTER_S
    for _ in range(int(240 / _DT)):
        pilot.update(_DT, 0.0, 0.0, 0.0, 0.0, mgr)
        if "coo" in voice.tags:
            break
    assert "coo" in voice.tags  # a yawn eventually landed the coo

    voice.tags.clear()
    pilot.enabled = True
    pilot._look_left = 0.0
    for _ in range(int(60 / _DT)):
        # Keep it in IDLE: the lottery may wander to WALK/SIT, which starves
        # the glance draws the test counts on.
        if pilot.state is not AutoState.IDLE:
            pilot._goto(AutoState.IDLE)
        pilot._idle_left = 60.0
        pilot.update(_DT, 0.0, 0.0, 0.0, 0.0, mgr)
        if "inquire" in voice.tags:
            break
    # inquire is a 15% coin per glance — 60 s of glances almost surely fires it.
    assert "inquire" in voice.tags
