"""winmm waveOut streaming for the theremin — ctypes, no deps, no threads.

winsound.PlaySound only fires one-shot WAVs; a held note needs a real PCM
sink. waveOut is the classic Win32 API for exactly that: a ring of prepared
buffers the driver drains, refilled from the Qt tick (ADR-0003 — the pump
runs on the Qt thread, a few ms every tick).
"""

from __future__ import annotations

import ctypes
import logging

import numpy as np

from duckdesk.platform.voice.synth import SR

log = logging.getLogger("duckdesk.voice")

WAVE_MAPPER = -1
CALLBACK_NULL = 0
WHDR_DONE = 0x00000001
WHDR_PREPARED = 0x00000002
WHDR_INQUEUE = 0x00000010


class _WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_uint16),
        ("nChannels", ctypes.c_uint16),
        ("nSamplesPerSec", ctypes.c_uint32),
        ("nAvgBytesPerSec", ctypes.c_uint32),
        ("nBlockAlign", ctypes.c_uint16),
        ("wBitsPerSample", ctypes.c_uint16),
        ("cbSize", ctypes.c_uint16),
    ]


class _WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint32),
        ("dwBytesRecorded", ctypes.c_uint32),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint32),
        ("dwLoops", ctypes.c_uint32),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


class WaveOut:
    """A mono 16-bit PCM sink with a small prepared-buffer ring.

    ``write`` fills one free header; callers pace on ``free`` so the queue
    stays 2-3 blocks ahead — an underrun just sounds like silence.
    """

    def __init__(self, rate: int = SR, block_ms: int = 20, depth: int = 4):
        self.block_n = max(1, rate * block_ms // 1000)
        self._hwo = ctypes.c_void_p()
        fmt = _WAVEFORMATEX(1, 1, rate, rate * 2, 2, 16, 0)
        rc = ctypes.windll.winmm.waveOutOpen(
            ctypes.byref(self._hwo), WAVE_MAPPER, ctypes.byref(fmt), 0, 0, CALLBACK_NULL
        )
        if rc != 0 or not self._hwo:
            raise OSError(f"waveOutOpen falhou (rc={rc})")
        self._pool = []
        for _ in range(depth):
            buf = (ctypes.c_int16 * self.block_n)()
            hdr = _WAVEHDR()
            hdr.lpData = ctypes.addressof(buf)
            hdr.dwBufferLength = self.block_n * 2
            rc = ctypes.windll.winmm.waveOutPrepareHeader(
                self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
            )
            if rc != 0:
                self.close()
                raise OSError(f"waveOutPrepareHeader falhou (rc={rc})")
            self._pool.append([hdr, buf])

    @property
    def free(self) -> int:
        """Headers available to fill (done or never queued)."""
        return sum(1 for hdr, _buf in self._pool if not hdr.dwFlags & WHDR_INQUEUE)

    def write(self, pcm_i16: np.ndarray) -> bool:
        """Queue one block of int16 samples; False if the ring is full."""
        for hdr, buf in self._pool:
            if hdr.dwFlags & WHDR_INQUEUE:
                continue
            n = min(len(pcm_i16), self.block_n)
            ctypes.memmove(buf, pcm_i16.ctypes.data, n * 2)
            if n < self.block_n:
                ctypes.memset(ctypes.addressof(buf) + n * 2, 0, (self.block_n - n) * 2)
            return (
                ctypes.windll.winmm.waveOutWrite(self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr))
                == 0
            )
        return False

    def close(self) -> None:
        if not getattr(self, "_hwo", None):
            return
        hwo, self._hwo = self._hwo, None
        ctypes.windll.winmm.waveOutReset(hwo)  # marks every header done
        for hdr, _buf in getattr(self, "_pool", []):
            ctypes.windll.winmm.waveOutUnprepareHeader(hwo, ctypes.byref(hdr), ctypes.sizeof(hdr))
        ctypes.windll.winmm.waveOutClose(hwo)
        self._pool = []
