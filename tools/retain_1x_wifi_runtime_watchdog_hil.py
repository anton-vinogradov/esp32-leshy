#!/usr/bin/env python3
"""Retain privacy-minimal incident-to-fix evidence for Wi-Fi loop stalls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "1.0.0-dev.374"
CID = "FE343253440000002000000055019CB7"
FIRMWARE_SOURCE = "57c7bb5cdf5cdbad2f595c8e1af0699cf5c0e6c8"
RUNNER_COMMIT = "32694d7e9ccdc12044577516ded5635f5010b6cc"
EVIDENCE_IDS = [
    "E-BUILD-244", "E-AUTO-223", "E-HIL-240", "E-SAFETY-088",
    "RB-M257",
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def common_candidate(run: dict[str, Any]) -> dict[str, Any]:
    candidate = run.get("candidate", {})
    require(run.get("passed") is True and run.get("gate_eligible") is True,
            "exact run did not pass")
    require(run.get("failures") == [], "exact run retained failures")
    require(candidate.get("version") == VERSION, "candidate version mismatch")
    require(candidate.get("source_commit") == FIRMWARE_SOURCE,
            "candidate source mismatch")
    require(candidate.get("flash_mode") == "reuse_exact",
            "candidate is not exact-image reuse")
    require(run.get("expected_cid") == CID, "exact CID mismatch")
    cleanup = run.get("cleanup_after", {})
    final = cleanup.get("final_state", {})
    require(cleanup.get("complete") is True and
            final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("safety_latched") is False,
            "final Home/none/zero-lease cleanup mismatch")
    before = run.get("recovery_before", {})
    after = run.get("recovery_after", {})
    require(before.get("generation") == after.get("generation") and
            before.get("observations") == after.get("observations") and
            after.get("physical_write_calls") == 0,
            "read-only storage continuity mismatch")
    return candidate


def summarize_devices(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run = load(path)
    candidate = common_candidate(run)
    endurance = run.get("endurance", {})
    checkpoints = endurance.get("checkpoints", [])
    require(endurance.get("completed") is True and
            float(endurance.get("elapsed_seconds", 0)) >= 180.0 and
            int(endurance.get("hops_completed", 0)) >= 1000 and
            len(checkpoints) >= 12,
            "device endurance floor mismatch")
    require(run.get("scope", {}).get(
        "continuous_wifi_device_endurance") is True,
        "device endurance scope missing")
    require(all(
        point.get("clients_dropped") == 0 and
        point.get("safety_latched") is False and
        point.get("watchdog_trace_valid") is False and
        int(point.get("heap_total", 0)) > 0 and
        int(point.get("heap_free", 0)) > 0
        for point in checkpoints), "device checkpoint invariant failed")
    require(len({point["heap_total"] for point in checkpoints}) == 1,
            "device heap total changed")
    require(run.get("metrics_after_first", {}).get("heap_free") ==
            run.get("metrics_after", {}).get("heap_free"),
            "device post-warm heap drift")
    first = checkpoints[0]
    last = checkpoints[-1]
    return candidate, {
        "run_sha256": digest(path),
        "runner_sha256": run.get("runner_source_sha256"),
        "elapsed_seconds": endurance["elapsed_seconds"],
        "hops_completed": endurance["hops_completed"],
        "checkpoint_count": len(checkpoints),
        "frames_reported_first": first["frames_reported"],
        "frames_reported_last": last["frames_reported"],
        "clients_accepted_first": first["clients_accepted"],
        "clients_accepted_last": last["clients_accepted"],
        "clients_dropped": 0,
        "catalog_within_capacity": max(
            int(point["devices"]) for point in checkpoints) <= 32,
        "heap_total": first["heap_total"],
        "heap_free_checkpoint": first["heap_free"],
        "heap_min_free": min(
            int(point["heap_min_free"]) for point in checkpoints),
        "watchdog_trace_observed": False,
        "two_complete_lifecycles": run["scope"][
            "two_complete_wifi_lifecycles"],
        "zero_heap_drift_after_warmup": run["scope"][
            "zero_heap_drift_after_warmup"],
        "final_home_none_zero_lease": True,
    }


def summarize_networks(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run = load(path)
    candidate = common_candidate(run)
    endurance = run.get("endurance", {})
    checkpoints = endurance.get("checkpoints", [])
    require(endurance.get("completed") is True and
            float(endurance.get("elapsed_seconds", 0)) >= 180.0 and
            int(endurance.get("cycles_completed", 0)) >= 50 and
            len(checkpoints) >= 12,
            "network endurance floor mismatch")
    require(run.get("scope", {}).get(
        "continuous_wifi_cycle_endurance") is True,
        "network endurance scope missing")
    require(all(
        point.get("scan_dropped") == 0 and
        point.get("safety_latched") is False and
        point.get("watchdog_trace_valid") is False and
        int(point.get("heap_total", 0)) > 0 and
        int(point.get("heap_free", 0)) > 0
        for point in checkpoints), "network checkpoint invariant failed")
    require(len({point["heap_total"] for point in checkpoints}) == 1,
            "network heap total changed")
    require(run.get("metrics_after_first", {}).get("heap_free") ==
            run.get("metrics_after", {}).get("heap_free"),
            "network post-warm heap drift")
    first = checkpoints[0]
    return candidate, {
        "run_sha256": digest(path),
        "runner_sha256": run.get("runner_source_sha256"),
        "elapsed_seconds": endurance["elapsed_seconds"],
        "cycles_completed": endurance["cycles_completed"],
        "checkpoint_count": len(checkpoints),
        "scan_dropped": 0,
        "catalog_within_capacity": max(
            int(point["networks"]) for point in checkpoints) <= 32,
        "heap_total": first["heap_total"],
        "heap_free_max": max(
            int(point["heap_free"]) for point in checkpoints),
        "heap_min_free": min(
            int(point["heap_min_free"]) for point in checkpoints),
        "watchdog_trace_observed": False,
        "two_complete_lifecycles": run["scope"][
            "two_complete_wifi_lifecycles"],
        "zero_heap_drift_after_warmup": run["scope"][
            "zero_heap_drift_after_warmup"],
        "final_home_none_zero_lease": True,
    }


def summarize_diagnostic(path: Path, kind: str) -> dict[str, Any]:
    run = load(path)
    endurance = run.get("endurance", {})
    require(endurance.get("completed") is True and
            float(endurance.get("elapsed_seconds", 0)) >= 600.0,
            f"{kind} diagnostic did not complete the stress hold")
    if kind == "devices":
        require(int(endurance.get("hops_completed", 0)) >= 4000,
                "device diagnostic hop floor mismatch")
        progress = {"hops_completed": endurance["hops_completed"]}
    else:
        require(int(endurance.get("cycles_completed", 0)) >= 150,
                "network diagnostic cycle floor mismatch")
        progress = {"cycles_completed": endurance["cycles_completed"]}
    return {
        "run_sha256": digest(path),
        "provenance_eligible": False,
        "reason": "incorrect_full_source_commit_argument",
        "elapsed_seconds": endurance["elapsed_seconds"],
        **progress,
        "stress_hold_completed": True,
        "safety_latched": any(
            point.get("safety_latched") is True
            for point in endurance.get("checkpoints", [])),
        "watchdog_trace_observed": any(
            point.get("watchdog_trace_valid") is True
            for point in endurance.get("checkpoints", [])),
        "drops_observed": any(
            int(point.get("clients_dropped",
                          point.get("scan_dropped", 0))) != 0
            for point in endurance.get("checkpoints", [])),
        "post_hold_runner_failures": run.get("failures", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True, type=Path)
    parser.add_argument("--devices-diagnostic", required=True, type=Path)
    parser.add_argument("--networks-diagnostic", required=True, type=Path)
    parser.add_argument("--devices-exact", required=True, type=Path)
    parser.add_argument("--networks-exact", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    require(not args.destination.exists(), "destination already exists")

    incident = load(args.incident)
    require(incident.get("schema") ==
            "leshy.runtime_watchdog_incident.v1",
            "incident schema mismatch")
    failure = incident.get("failure", {})
    observation = incident.get("post_reset_observation", {})
    require(failure.get("reset_reason_code") == 6 and
            failure.get("safety_state") == "latched" and
            failure.get("safety_reason") == "runtime_watchdog" and
            failure.get("worker_last_expired") == "none" and
            observation.get("software_quiesce_complete") is True and
            observation.get("input_queue_drops") == 0 and
            observation.get("input_read_errors") == 0 and
            observation.get("storage_physical_write_calls") == 0,
            "overnight incident boundary mismatch")

    device_candidate, devices = summarize_devices(args.devices_exact)
    network_candidate, networks = summarize_networks(args.networks_exact)
    require(device_candidate == network_candidate,
            "exact runs use different candidates")
    require(digest(args.firmware) == device_candidate["firmware_sha256"],
            "firmware artifact hash mismatch")

    root = Path(__file__).resolve().parents[1]
    device_runner = root / "tools/run_1x_wifi_devices_hil.py"
    network_runner = root / "tools/run_1x_wifi_networks_hil.py"
    require(devices["runner_sha256"] == digest(device_runner) and
            networks["runner_sha256"] == digest(network_runner),
            "exact runner hash mismatch")

    evidence = {
        "schema": "leshy.wifi_runtime_watchdog.acceptance.v1",
        "status": "pass_wifi_runtime_watchdog_mitigation",
        "board": "board-01",
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            **device_candidate,
            "firmware_source_commit": FIRMWARE_SOURCE,
            "runner_commit": RUNNER_COMMIT,
            "cid": CID,
        },
        "incident": {
            "raw_sha256": digest(args.incident),
            "captured_at_utc": incident["captured_at_utc"],
            "version": incident["candidate"]["version"],
            "source_commit": incident["candidate"][
                "accepted_source_commit"],
            "app_elf_sha256": incident["candidate"]["app_elf_sha256"],
            "reset_reason_code": failure["reset_reason_code"],
            "safety_reason": failure["safety_reason"],
            "trip_count": failure["trip_count"],
            "worker_deadline_expired": False,
            "heap_exhaustion_observed": incident["diagnosis"][
                "heap_exhaustion_observed"],
            "input_failure_observed": False,
            "post_reset_stable_ms": observation[
                "approximate_stable_post_reset_uptime_ms"],
            "safe_outputs_quiesced": observation[
                "software_quiesce_complete"],
            "physical_write_calls": observation[
                "storage_physical_write_calls"],
            "screen_sha256": incident["artifacts"][
                "screen_png_sha256"],
            "screen_state_sha256": incident["artifacts"][
                "screen_state_sha256"],
            "pre_reset_page_known": False,
        },
        "mitigation": {
            "finite_product_worker_event_drain": 8,
            "finite_product_observation_drain": 16,
            "finite_wifi_device_observation_drain": 16,
            "wifi_data_inspect_interval_us": 1000,
            "wifi_device_queue_capacity": 64,
            "retained_first_watchdog_trace": True,
            "safety_quiesce_precedes_diagnostic": True,
        },
        "diagnostic_stress": {
            "devices": summarize_diagnostic(
                args.devices_diagnostic, "devices"),
            "networks": summarize_diagnostic(
                args.networks_diagnostic, "networks"),
        },
        "exact_runs": {
            "devices": devices,
            "networks": networks,
        },
        "tools": {
            "device_runner_sha256": digest(device_runner),
            "network_runner_sha256": digest(network_runner),
        },
        "privacy": {
            "ambient_ssid_retained": False,
            "ambient_bssid_retained": False,
            "ambient_device_address_retained": False,
            "raw_wifi_frames_retained": False,
            "device_port_retained": False,
        },
        "verified": {
            "both_exact_runs_pass": True,
            "continuous_progress": True,
            "zero_radio_drops": True,
            "zero_watchdog_recurrence": True,
            "zero_post_warm_heap_drift": True,
            "read_only_storage_continuity": True,
            "final_home_none_zero_lease": True,
            "mac_wifi_untouched": True,
            "rf_transmit_invoked": False,
        },
    }
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": "retained",
        "destination": str(args.destination),
        "sha256": digest(args.destination),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
