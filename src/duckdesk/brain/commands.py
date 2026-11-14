"""Command payloads and behavior requests flowing into the DuckBrain/PolicyManager."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import numpy as np


@dataclass
class DuckCommand:
    """The 13D command blocks: twist[3], head_pose[4], body_pose[6] (docs/03 section 4)."""

    twist: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    head: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    body: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=np.float32))


class Request(enum.Enum):
    """Behavior requests (docs/03 section 8). DuckBrain decides which are accepted."""

    SIT = "sit"
    STAND = "stand"
    PECK = "peck"  # ground pick (bicar o chao)
    ROLL = "roll"  # roulade / cambalhota
    KICK_L = "kick_left"
    KICK_R = "kick_right"
    RESET = "reset"
