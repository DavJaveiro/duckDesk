#!/usr/bin/env python3
"""Run the duck headless for N seconds with a scripted command roteiro.

    uv run python scripts/headless_run.py --policy walk --script roteiro.json --seconds 10

Script format (list of events, applied when sim time >= t, in order):
    [{"t": 0.0, "twist": [vx, vy, wz]},
     {"t": 2.0, "head": [neck_pitch, head_pitch, head_yaw, head_roll]},
     {"t": 2.0, "body": [x, y, z, roll, pitch, yaw]},
     {"t": 4.0, "request": "peck"}]    # peck | roll | kick_left | kick_right | sit | stand | reset

--policy: a role name ("walk") or a path to a user .onnx for the walk slot.
Prints control-step timing (mean/p50/p99/max), watchdog events and final state.
--mp4 records the run through the offscreen renderer (for reports).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from duckdesk import assets
from duckdesk.brain.commands import DuckCommand, Request
from duckdesk.policy.manager import PolicyManager
from duckdesk.policy.validate import validate_user_onnx
from duckdesk.sim.core import CONTROL_DT, SimCore
from duckdesk.sim.watchdog import Watchdog

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene_ball.xml"
POLICIES_DIR = assets.assets_dir() / "policies" / "v10"


def load_events(path: Path) -> list[dict]:
    events = json.loads(path.read_text(encoding="utf-8"))
    return sorted(events, key=lambda e: e["t"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--policy", default="walk", help="role name or .onnx path for the walk slot"
    )
    parser.add_argument("--script", type=Path, help="roteiro JSON (list of events)")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--mp4", type=Path, help="optional MP4 output via offscreen renderer")
    parser.add_argument("--fps", type=int, default=50)
    args = parser.parse_args()

    walk_onnx = None
    if args.policy != "walk":
        ok, msg = validate_user_onnx(args.policy)
        if not ok:
            print(f"politica recusada: {msg}")
            return 2
        walk_onnx = args.policy

    sim = SimCore(SCENE)
    sim.park_ball()
    manager = PolicyManager(POLICIES_DIR, walk_onnx=walk_onnx)
    watchdog = Watchdog()
    events = load_events(args.script) if args.script else []

    renderer = None
    frames = []
    if args.mp4:
        from duckdesk.render.offscreen import OffscreenRenderer

        renderer = OffscreenRenderer(sim.model, width=640, height=360)

    command = DuckCommand()
    times_ms: list[float] = []
    watchdog_events: list[str] = []
    steps = int(args.seconds / CONTROL_DT)
    event_idx = 0
    step = 0
    try:
        for step in range(steps):
            sim_time = step * CONTROL_DT
            while event_idx < len(events) and events[event_idx]["t"] <= sim_time:
                ev = events[event_idx]
                if "twist" in ev or "head" in ev or "body" in ev:
                    if "twist" in ev:
                        command.twist = np.asarray(ev["twist"], dtype=np.float32)
                    if "head" in ev:
                        command.head = np.asarray(ev["head"], dtype=np.float32)
                    if "body" in ev:
                        command.body = np.asarray(ev["body"], dtype=np.float32)
                    manager.set_command(command)
                if "request" in ev:
                    req = Request(ev["request"])
                    ok, msg = manager.request(req, sim)
                    print(
                        f"[{sim_time:5.1f}s] request {ev['request']}: {'ok' if ok else 'recusado'} ({msg})"
                    )
                event_idx += 1

            t0 = time.perf_counter()
            targets = manager.step(sim)
            sim.step_control(targets)
            times_ms.append((time.perf_counter() - t0) * 1000.0)

            event = watchdog.check(sim, CONTROL_DT)
            if event:
                watchdog_events.append(event)
                manager.request(Request.RESET, sim)
                print(f"[{sim_time:5.1f}s] watchdog: {event} -> reset")

            if renderer is not None and step % max(1, 50 // args.fps) == 0:
                frames.append(renderer.render_rgb(sim.data))
    except KeyboardInterrupt:
        print("interrompido")

    arr = np.asarray(times_ms)
    pos = sim.trunk_pos()
    v_body, wz = sim.body_velocity()
    print("\n=== metricas ===")
    print(f"passos de controle: {len(times_ms)} (alvo {steps})")
    print(
        f"tempo por passo: mean {arr.mean():.2f} ms | p50 {np.percentile(arr, 50):.2f} | "
        f"p99 {np.percentile(arr, 99):.2f} | max {arr.max():.2f}"
    )
    print(f"watchdog: {len(watchdog_events)} eventos {watchdog_events}")
    print(f"tronco final: pos {pos.round(3)} | tilt {np.degrees(sim.trunk_tilt()):.1f} deg")
    print(
        f"velocidade final (corpo): v=({v_body[0]:+.3f}, {v_body[1]:+.3f}) m/s | wz {wz:+.3f} rad/s"
    )

    if renderer is not None and frames:
        import imageio.v2 as imageio

        args.mp4.parent.mkdir(parents=True, exist_ok=True)
        imageio.mimsave(args.mp4, frames, fps=args.fps)
        print(f"mp4: {args.mp4} ({len(frames)} frames)")
        renderer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
