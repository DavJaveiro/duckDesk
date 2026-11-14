"""Plot the perf CSV from measure_perf.py -> PNG (PIL, no matplotlib).

Usage:
    uv run python scripts/plot_perf.py docs/relatorios/midia/m7_soak.csv \
        --out docs/relatorios/midia/m7_soak.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 700
MARGIN = 70
PANEL_H = (H - 3 * MARGIN) // 2


def _nice_step(span: float, target: int = 6) -> float:
    import math

    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _panel(
    draw: ImageDraw.ImageDraw,
    y0: int,
    title: str,
    t: list[float],
    v: list[float],
    color: tuple[int, int, int],
    ref: tuple[float, str] | None = None,
) -> None:
    x0, x1 = MARGIN, W - MARGIN
    y1 = y0 + PANEL_H
    t_max = t[-1] if t else 1.0
    vmax = max(max(v) * 1.1, 1e-6)
    if ref:
        vmax = max(vmax, ref[0] * 1.15)
    vstep = _nice_step(vmax)
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)

    draw.rectangle([x0, y0, x1, y1], outline=(60, 60, 60))
    draw.text((x0, y0 - 24), title, fill=(20, 20, 20), font=font)

    def px(t_i: float) -> float:
        return x0 + (t_i / t_max) * (x1 - x0)

    def py(v_i: float) -> float:
        return y1 - (v_i / vmax) * (y1 - y0)

    # grid + axis labels
    n_v = int(vmax / vstep)
    for i in range(n_v + 1):
        gy = py(i * vstep)
        draw.line([x0, gy, x1, gy], fill=(220, 220, 220))
        draw.text((8, gy - 7), f"{i * vstep:g}", fill=(90, 90, 90), font=small)
    tstep = _nice_step(t_max)
    n_t = int(t_max / tstep)
    for i in range(n_t + 1):
        gx = px(i * tstep)
        draw.line([gx, y0, gx, y1], fill=(235, 235, 235))
        m = i * tstep / 60
        draw.text((gx - 12, y1 + 6), f"{m:g}m", fill=(90, 90, 90), font=small)

    # series
    pts = [(px(a), py(b)) for a, b in zip(t, v, strict=True)]
    if len(pts) > 1:
        draw.line(pts, fill=color, width=2)

    # reference line (e.g. RSS @5min +10%)
    if ref:
        ry = py(ref[0])
        draw.line([x0, ry, x1, ry], fill=(200, 40, 40), width=2)
        draw.text((x0 + 8, ry - 18), ref[1], fill=(200, 40, 40), font=small)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rss5", type=float, default=None, help="RSS @5min +10% ref line (MB)")
    args = ap.parse_args()

    t, cpu, rss = [], [], []
    with args.csv.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t.append(float(row["t_s"]))
            cpu.append(float(row["cpu_pct_1core"]))
            rss.append(float(row["rss_mb"]))

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    _panel(draw, MARGIN + 20, "CPU (% de 1 nucleo)", t, cpu, (30, 100, 200))
    _panel(
        draw,
        MARGIN * 2 + PANEL_H + 20,
        "RSS (MB)",
        t,
        rss,
        (20, 140, 80),
        ref=(args.rss5, f"RSS@5min +10% = {args.rss5:.0f} MB") if args.rss5 else None,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"{args.out} ({len(t)} amostras, t_max={t[-1] / 60:.0f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
