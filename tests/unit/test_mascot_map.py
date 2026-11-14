"""M5 mapping tests with synthetic screens (docs/05 sections 1-3).

Scales 100/125/150 %, taskbar bottom / autohide / top.
"""

from __future__ import annotations

import pytest

from duckdesk.platform.mascot_map import H_M, Dpi, MascotMapping, compute_band

pytestmark = pytest.mark.unit

# synthetic 2560x1440 physical screen
W_PHYS, H_PHYS = 2560, 1440
TB_H = 48  # physical taskbar height


def _work_area(dpr: float, tb_h_logical: float = 0.0):
    """Logical work area for a 2560x1440 screen, bottom taskbar visible."""
    w, h = W_PHYS / dpr, H_PHYS / dpr
    return (0.0, 0.0, w, h - tb_h_logical)


def _taskbar_bottom(dpr: float):
    """Physical rect of a bottom taskbar."""
    return (0, H_PHYS - TB_H, W_PHYS, H_PHYS)  # physical


@pytest.mark.parametrize("dpr", (1.0, 1.25, 1.5))
def test_bottom_taskbar_floor_at_top_edge(dpr):
    dpi = Dpi(dpr)
    tb = _taskbar_bottom(dpr)
    tb_h_log = TB_H / dpr
    wa = _work_area(dpr, tb_h_log)
    band = compute_band(tb, wa, dpi, taskbar_autohide=False)
    assert not band.hidden
    # floor = taskbar top edge in logical px
    assert band.floor_y == pytest.approx((H_PHYS - TB_H) / dpr)
    assert band.left == 0 and band.right == pytest.approx(W_PHYS / dpr)


@pytest.mark.parametrize("dpr", (1.0, 1.25, 1.5))
def test_mapping_center_and_range(dpr):
    dpi = Dpi(dpr)
    band = compute_band(_taskbar_bottom(dpr), _work_area(dpr, TB_H / dpr), dpi, False)
    mm = MascotMapping(band, 120)
    # x=0 maps to screen center; symmetric range
    assert mm.screen_x(0.0) == pytest.approx(band.center)
    assert mm.x_min == pytest.approx(-mm.x_max)
    # edges in pixels -> world clamp
    edge_left_px = band.left + 120 / 2 + 8
    assert mm.world_x(edge_left_px) == pytest.approx(mm.x_min)
    assert mm.clamp_x(99.0) == mm.x_max


@pytest.mark.parametrize("dpr", (1.0, 1.25, 1.5))
def test_ppm_constant_across_scale(dpr):
    """ppm = H/H_m -> same logical px-per-meter at any scale."""
    band = compute_band(_taskbar_bottom(dpr), _work_area(dpr, TB_H / dpr), Dpi(dpr), False)
    mm = MascotMapping(band, 120)
    assert mm.ppm == pytest.approx(120 / 1.6 / H_M)
    # window top: floor_y - S + margin
    m = round(0.04 * 120)
    assert mm.window_top() == pytest.approx(band.floor_y - 120 + m)


def test_autohide_degrades_to_work_area_bottom():
    dpr = 1.25
    band = compute_band(_taskbar_bottom(dpr), _work_area(dpr, TB_H / dpr), Dpi(dpr), True)
    assert band.hidden
    assert band.floor_y == pytest.approx(H_PHYS / dpr - TB_H / dpr)


def test_top_taskbar_degrades_to_work_area_bottom():
    dpr = 1.5
    tb_top = (0, 0, W_PHYS, TB_H)  # taskbar at top (physical)
    wa = _work_area(dpr)
    band = compute_band(tb_top, wa, Dpi(dpr), False)
    assert band.hidden
    assert band.floor_y == pytest.approx(wa[3])


def test_side_taskbar_degrades():
    dpr = 1.0
    tb_left = (0, 0, TB_H, H_PHYS)  # taskbar at left (physical)
    band = compute_band(tb_left, _work_area(dpr), Dpi(dpr), False)
    assert band.hidden


def test_no_taskbar_degrades():
    band = compute_band(None, _work_area(1.0), Dpi(1.0), False)
    assert band.hidden


@pytest.mark.parametrize("dpr", (1.0, 1.25, 1.5))
def test_three_quarter_camera_projection(dpr):
    """ADR-0007: with a 3/4 camera the duck moves rx*ppm px per world meter
    along x, and the clamp range still lands the window inside the band."""
    band = compute_band(_taskbar_bottom(dpr), _work_area(dpr, TB_H / dpr), Dpi(dpr), False)
    rx, ry = 0.64, 0.77
    mm = MascotMapping(band, 120, h_m=0.26, right=(rx, ry))
    assert mm.screen_x(1.0) - mm.screen_x(0.0) == pytest.approx(rx * mm.ppm)
    assert mm.screen_x(mm.x_max) == pytest.approx(band.right - 60 - 8)
    assert mm.world_x(mm.screen_x(0.3, 0.02), 0.02) == pytest.approx(0.3)


def test_head_fits_in_window():
    """Regression for the cut-off head: the view must be 1.6x the duck height."""
    band = compute_band(_taskbar_bottom(1.0), _work_area(1.0, TB_H), Dpi(1.0), False)
    mm = MascotMapping(band, 120, h_m=0.26)
    assert mm.ortho_height_m() == pytest.approx(1.6 * 0.26)
