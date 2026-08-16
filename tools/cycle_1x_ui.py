#!/usr/bin/env python3
"""Run repeated capability-home open/back cycles and retain lease/heap evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, read_json


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = round((len(ordered) - 1) * percent)
    return round(ordered[index], 3)


def action(device: PassiveSerial, name: str) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    device.write(f"ui.key {name}\n".encode("ascii"))
    device.flush()
    state = read_json(device, "leshy.ui.v1", "state")
    return state, round((time.monotonic() - started) * 1000.0, 3)


def metrics(device: PassiveSerial) -> dict[str, Any]:
    device.write(b"metrics\n")
    device.flush()
    return read_json(device, "leshy.boot.v1", "ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--cycles", type=int, default=1000)
    parser.add_argument("--max-back-ms", type=float, default=150.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.cycles <= 0 or args.cycles > 10000:
        parser.error("cycles must be between 1 and 10000")

    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    device.open()
    open_latencies: list[float] = []
    back_latencies: list[float] = []
    start_revision: int | None = None
    final_revision: int | None = None
    with device:
        device.reset_input_buffer()
        before = metrics(device)
        for cycle in range(1, args.cycles + 1):
            opened, open_ms = action(device, "select")
            if start_revision is None:
                start_revision = int(opened["revision"])
            if (opened.get("page") != "diagnostics" or
                    opened.get("runtime_owner") != "diagnostics" or
                    int(opened.get("lease_mask", 0)) != 1):
                raise RuntimeError(f"invalid open state at cycle {cycle}: {opened}")
            closed, back_ms = action(device, "back")
            final_revision = int(closed["revision"])
            if (closed.get("page") != "home" or closed.get("runtime_owner") != "none" or
                    int(closed.get("lease_mask", -1)) != 0):
                raise RuntimeError(f"leaked close state at cycle {cycle}: {closed}")
            open_latencies.append(open_ms)
            back_latencies.append(back_ms)
            if cycle % 100 == 0 or cycle == args.cycles:
                print(json.dumps({"cycle": cycle, "back_max_ms": max(back_latencies),
                                  "revision": final_revision}), flush=True)
        after = metrics(device)

    expected_delta = args.cycles * 2 - 1
    actual_delta = int(final_revision) - int(start_revision)
    if actual_delta != expected_delta:
        raise RuntimeError(f"revision delta {actual_delta}, expected {expected_delta}")
    if (before["heap_free"] != after["heap_free"] or
            before["heap_min_free"] != after["heap_min_free"]):
        raise RuntimeError(f"heap changed: before={before}, after={after}")
    if max(back_latencies) > args.max_back_ms:
        raise RuntimeError(
            f"Back/release {max(back_latencies)} ms exceeds {args.max_back_ms} ms")

    evidence = {
        "schema": "leshy.ui.cycles.v1",
        "port": args.port,
        "cycles": args.cycles,
        "start_revision": start_revision,
        "final_revision": final_revision,
        "expected_revision_delta": expected_delta,
        "actual_revision_delta": actual_delta,
        "open_ms": {"p50": percentile(open_latencies, 0.50),
                    "p95": percentile(open_latencies, 0.95),
                    "p99": percentile(open_latencies, 0.99), "max": max(open_latencies)},
        "back_ms": {"p50": percentile(back_latencies, 0.50),
                    "p95": percentile(back_latencies, 0.95),
                    "p99": percentile(back_latencies, 0.99), "max": max(back_latencies)},
        "heap_before": {"free": before["heap_free"], "minimum": before["heap_min_free"]},
        "heap_after": {"free": after["heap_free"], "minimum": after["heap_min_free"]},
        "final_owner": "none",
        "final_lease_mask": 0,
        "max_back_ms": args.max_back_ms,
        "passed": True,
    }
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({**evidence, "output": str(args.output),
                      "sha256": hashlib.sha256(payload.encode()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
