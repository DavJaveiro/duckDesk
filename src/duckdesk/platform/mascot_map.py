"""Sim <-> screen mapping for the mascot (docs/05 section 3).

Qt-free and Win32-free: everything is plain numbers so the synthetic-screen
unit tests can drive it (100/125/150% scale, taskbar bottom/hidden/top).
Physical<->logical pixel conversion lives ONLY in `Dpi`.
"""

from __future__ import annotations

from dataclasses import dataclass

# Fallback duck height (m) as SEEN by the mascot camera: ground -> top of head
# in the standing pose. The app measures the real value from the meshes at
# runtime (render.mascot.duck_screen_height_m); 0.1155 m (trunk z) was wrong —
# it cut the head off (ADR-0007).
H_M = 0.26
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
    """World <-> screen for the mascot (05 section 3, ADR-0007).

    The camera looks at the duck in 3/4, so a world displacement d moves the
    duck on screen by (d . right) * ppm, with right = (rx, ry, 0) the camera's
    horizontal axis. The duck walks along world x, so the usable x range is the
    screen band divided by ppm * rx.
    """

    def __init__(
        self,
        band: GroundBand,
        size_px: int,
        h_m: float = H_M,
        right: tuple[float, float] = (1.0, 0.0),
    ):
        self.band = band
        self.S = size_px
        self.h_m = h_m
        self.rx, self.ry = right
        if self.rx <= 0.1:
            raise ValueError("camera right axis must have a clear +x component")
        self.ppm = size_px / 1.6 / h_m  # S = 1.6 * H; H = duck height in px
        k = self.ppm * self.rx
        self.x_min = (band.left + size_px / 2 + EDGE_PAD_PX - band.center) / k
        self.x_max = (band.right - size_px / 2 - EDGE_PAD_PX - band.center) / k

    def screen_x(self, x_m: float, y_m: float = 0.0) -> float:
        """Logical screen x of the window center for a world ground point."""
        return self.band.center + (x_m * self.rx + y_m * self.ry) * self.ppm

    def world_x(self, screen_x_px: float, y_m: float = 0.0) -> float:
        return ((screen_x_px - self.band.center) / self.ppm - y_m * self.ry) / self.rx

    def clamp_x(self, x_m: float) -> float:
        return min(max(x_m, self.x_min), self.x_max)

    def x_limits_for_y(self, y_m: float) -> tuple[float, float]:
        """World-x limits that keep the window inside the band at depth ``y``.

        The 3/4 camera maps the ground point to ``center + (x*rx + y*ry)*ppm``,
        so a duck that left the y = 0 line is shifted sideways on screen. This
        solves the same band edges for x with the current y (05 section 3,
        ADR-0007); the result is ``[x_min, x_max]`` shifted by -y*ry/rx.
        """
        shift = y_m * self.ry / self.rx
        return self.x_min - shift, self.x_max - shift

    def window_top(self, floor_margin_px: int | None = None) -> float:
        m = floor_margin_px if floor_margin_px is not None else round(MARGIN_FRAC * self.S)
        return self.band.floor_y - self.S + m

    def ortho_height_m(self) -> float:
        """Visible world height of the ortho camera = S / ppm (05 section 3)."""
        return self.S / self.ppm


SIZES = {"pequeno": 80, "medio": 120, "grande": 180}  # logical px, 05 section 2
