#!/usr/bin/env python3
"""Retain verified failure digests without ambient network/device identifiers."""
import argparse
import hashlib
import json
from pathlib import Path
from esp_app_identity import app_elf_sha256


def retain(paths):
    records = []
    for path in paths:
        raw = path.read_bytes()
        run = json.loads(raw)
        if run.get("status") != "failed" or not run.get("failures"):
            raise ValueError("expected an actual failed run")
        image = path.parent / "firmware.bin"
        if hashlib.sha256(image.read_bytes()).hexdigest() != run["image_sha256"]:
            raise ValueError("retained image mismatch")
        if app_elf_sha256(image) != run["app_elf_sha256"]:
            raise ValueError("retained app identity mismatch")
        final = {}
        for role in ("source", "receiver"):
            cleanup = run["cleanup"][role]
            state = cleanup["final_state"]
            if not (cleanup["complete"] and state["page"] == "home" and
                    state["runtime_owner"] == "none" and state["lease_mask"] == 0):
                raise ValueError("unverified cleanup")
            final[role] = {key: state[key] for key in
                           ("page", "runtime_owner", "lease_mask", "safety_latched")}
        traces = {}
        for role in ("source", "receiver"):
            trace = path.parent / (role + "-console.jsonl")
            if trace.exists():
                traces[role] = {"sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
                                **run.get("console_traces", {}).get(role, {})}
        # Only known, non-identifying errors are suitable for the public digest.
        allowed = ("TimeoutError: name_scan_resumed", "TimeoutError: timed out waiting for leshy.wifi.network_detail.v1/state",
                   "RuntimeError: name timer repaints static screen")
        if any(not any(error.startswith(prefix) for prefix in allowed) for error in run["failures"]):
            raise ValueError("unreviewed failure text: keep private")
        records.append({"run_sha256": hashlib.sha256(raw).hexdigest(),
            "source_commit": run["source_commit"], "image_sha256": run["image_sha256"],
            "app_elf_sha256": run["app_elf_sha256"], "status": "failed",
            "failures": run["failures"], "final": final, "console_traces": traces,
            "name_countdown_pixels": run.get("name_countdown_pixels"),
            "name_screen_transport_errors": {name: screen.get("transport_transient_errors", [])
                for name, screen in run["screens"].items()
                if name.startswith("name-") and screen.get("transport_transient_errors")}})
    return {"schema": "leshy.wifi_name_listen.failures.v1", "status": "failed_runs_retained",
            "acceptance_claimed": False, "records": records,
            "limits": "Digests bind private raw failures and verified Home cleanup. No raw identifiers or screenshots published; no inferred root cause."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = retain(args.runs)
    with args.output.open("x") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    print(f"Retained {len(result['records'])} checked failed runs; no acceptance credit")


if __name__ == "__main__":
    main()
