"""Perf sampler (M7): CPU (fraction of one core) + RSS every 5 s -> CSV.

Usage:
    uv run python scripts/measure_perf.py --pid 1234 --seconds 7200 --out perf.csv
    uv run python scripts/measure_perf.py --name DuckDesk.exe --seconds 60 --out perf.csv
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import psutil


def find_pid(name: str) -> int:
    for p in psutil.process_iter(["name"]):
        if p.info["name"] == name:
            return p.pid
    raise SystemExit(f"processo '{name}' nao encontrado")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--name", default="DuckDesk.exe")
    ap.add_argument("--seconds", type=float, default=7200)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    pid = args.pid or find_pid(args.name)
    proc = psutil.Process(pid)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    rss_5min = None
    t_start = time.perf_counter()
    last_cpu = proc.cpu_times()
    last_wall = t_start
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["t_s", "cpu_pct_1core", "rss_mb"])
        while time.perf_counter() - t_start < args.seconds:
            time.sleep(args.interval)
            if not proc.is_running():
                print(f"processo {pid} terminou em t={time.perf_counter() - t_start:.0f}s")
                break
            now = time.perf_counter()
            cpu = proc.cpu_times()
            used = (cpu.user + cpu.system) - (last_cpu.user + last_cpu.system)
            pct = used / (now - last_wall) * 100.0
            last_cpu, last_wall = cpu, now
            rss_mb = proc.memory_info().rss / 1048576
            t = now - t_start
            if rss_5min is None and t >= 300:
                rss_5min = rss_mb
            w.writerow([f"{t:.1f}", f"{pct:.2f}", f"{rss_mb:.1f}"])
            fh.flush()
            rows += 1
    rss_last = proc.memory_info().rss / 1048576 if proc.is_running() else float("nan")
    print(f"{rows} amostras -> {args.out} | rss@5min={rss_5min} MB | rss_fim={rss_last:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
