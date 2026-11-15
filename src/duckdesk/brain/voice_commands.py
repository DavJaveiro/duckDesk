"""pt-BR voice commands: the grammar phrase list and what each phrase means
(ADR-0012).

Vosk's grammar mode restricts recognition to exactly `PHRASES` — a short,
phonetically distinct list beats free dictation for a fixed command set.
Every phrase maps to one semantic command consumed by
`AppController.on_voice_command`; keeping the table here (no imports) makes
the whole contract unit-testable without a microphone.
"""

from __future__ import annotations

# phrase -> semantic command. Phrases are matched by the recognizer verbatim.
COMMANDS: dict[str, str] = {
    # posture ('pé' is not in the small model's vocabulary — no "em pé" phrases)
    "senta": "sit",
    "sentar": "sit",
    "levanta": "stand",
    "levantar": "stand",
    # motion
    "anda": "walk",
    "andar": "walk",
    "vai": "walk",
    "para": "stop",
    "parar": "stop",
    "quieto": "stop",
    "vem": "come",
    "vem aqui": "come",
    # tricks ('chão'/'cá'/'aí' are missing from the vocabulary too)
    "pirueta": "roll",
    "cambalhota": "roll",
    "rola": "roll",
    "mortal": "roll",
    "bica": "peck",
    "bicar": "peck",
    "chuta": "kick",
    "chutar": "kick",
    "chuta a bola": "kick",
    # voice / mood
    "pia": "chirp",
    "grasna": "chirp",
    "fala": "chirp",
    "dorme": "sleep",
    "dormir": "sleep",
    "vai dormir": "sleep",
    "olha": "look",
    "olha aqui": "look",
    "aqui": "look",
    "pato": "poke",
    "oi pato": "poke",
    "tchau": "bye",
    "adeus": "bye",
}

# What the grammar hands back on noise/unknown words. Always last in the list;
# `resolve` never maps it.
UNKNOWN = "[unk]"


def grammar() -> list[str]:
    """The recognizer's allowed phrase list (KaldiRecognizer's JSON grammar)."""
    return [*COMMANDS, UNKNOWN]


def resolve(phrase: str) -> str | None:
    """Map a recognized phrase to its command; None for noise/unknown."""
    return COMMANDS.get(phrase.strip().lower())
