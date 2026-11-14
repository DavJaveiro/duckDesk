"""Sim <-> screen mapping for the mascot (docs/05 section 3).

Qt-free and Win32-free: everything is plain numbers so the synthetic-screen
unit tests can drive it (100/125/150% scale, taskbar bottom/hidden/top).
Physical<->logical pixel conversion lives ONLY in `Dpi`.
"""

from __future__ import annotations

from dataclasses import dataclass

H_M = 0.1155  # standing duck height in meters (measured in M1, docs/relatorios/M1.md)
MARGIN_FRAC = 0.04  # ground line sits S - round(0.04*S) px from window bottom
EDGE_PAD_PX = 8  # keep the window this far inside the usable band


@dataclass(frozen=True)
class Dpi:
    """Single place owning physical<->logical conversion."""

    ratio: float  # devicePixelRatio of the primary screen

    def to_logical(self, phys_px: float) -> float:
        return phys_px / self.ratio

    def to_physical(self, logical_px: float) -> float:
        return logical_px * self.ratio


@dataclass(frozen=True)
class GroundBand:
    """Usable screen band (logical px) + the ground line.

    floor_y: logical screen y where z=0 of the world sits.
    hidden: degraded mode (autohide / top / side taskbar) -> work area bottom.
    """

    left: float
    right: float
    center: float
    floor_y: float
    hidden: bool


def compute_band(
    taskbar_rect_phys: tuple[float, float, float, float] | None,
    work_area_logical: tuple[float, float, float, float],
    dpi: Dpi,
    taskbar_autohide: bool,
) -> GroundBand:
    """05 section 1: taskbar at bottom+visible -> floor is its top edge and the
    band is its width; otherwise degraded to work-area bottom edge."""
    wa_l, _wa_t, wa_r, wa_b = work_area_logical
    if taskbar_rect_phys is not None and not taskbar_autohide:
        l, t, r, b = (dpi.to_logical(v) for v in taskbar_rect_phys)
        # bottom taskbar: wider than tall, top edge flush with work-area bottom
        is_bottom = (r - l) > (b - t) and abs(t - wa_b) <= 2
        if is_bottom:
            return GroundBand(left=l, right=r, center=(l + r) / 2, floor_y=t, hidden=False)
    return GroundBand(left=wa_l, right=wa_r, center=(wa_l + wa_r) / 2, floor_y=wa_b, hidden=True)


class MascotMapping:
    """screen_x(x) = center + x*ppm and the x range from 05 section 3."""

    def __init__(self, band: GroundBand, size_px: int):
        self.band = band
        self.S = size_px
        self.ppm = size_px / 1.6 / H_M  # S = 1.6 * H; H = duck height in px
        self.x_min = (band.left + size_px / 2 + EDGE_PAD_PX - band.center) / self.ppm
        self.x_max = (band.right - size_px / 2 - EDGE_PAD_PX - band.center) / self.ppm

    def screen_x(self, x_m: float) -> float:
        """Logical screen x of the window center for world x."""
        return self.band.center + x_m * self.ppm

    def world_x(self, screen_x_px: float) -> float:
        return (screen_x_px - self.band.center) / self.ppm

    def clamp_x(self, x_m: float) -> float:
        return min(max(x_m, self.x_min), self.x_max)

    def window_top(self, floor_margin_px: int | None = None) -> float:
        m = floor_margin_px if floor_margin_px is not None else round(MARGIN_FRAC * self.S)
        return self.band.floor_y - self.S + m

    def ortho_height_m(self) -> float:
        """Visible world height of the ortho camera = S / ppm (05 section 3)."""
        return self.S / self.ppm


SIZES = {"pequeno": 80, "medio": 120, "grande": 180}  # logical px, 05 section 2
