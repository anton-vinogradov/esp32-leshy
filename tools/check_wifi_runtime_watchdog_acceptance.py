#!/usr/bin/env python3
"""Verify retained Wi-Fi runtime-watchdog incident-to-fix evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT / "tests/hil/evidence/"
    "board-01-wifi-runtime-watchdog-1.0.0-dev.374.json")
VERSION = "1.0.0-dev.374"
CID = "FE343253440000002000000055019CB7"
FIRMWARE_SOURCE = "57c7bb5cdf5cdbad2f595c8e1af0699cf5c0e6c8"
RUNNER_COMMIT = "32694d7e9ccdc12044577516ded5635f5010b6cc"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_file(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True,
        stdout=subprocess.PIPE).stdout


def main() -> int:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(EVIDENCE.is_file(), "retained evidence missing")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(evidence.get("schema") ==
            "leshy.wifi_runtime_watchdog.acceptance.v1" and
            evidence.get("status") ==
            "pass_wifi_runtime_watchdog_mitigation" and
            evidence.get("board") == "board-01",
            "evidence identity mismatch")
    require(evidence.get("evidence_ids") == [
        "E-BUILD-244", "E-AUTO-223", "E-HIL-240", "E-SAFETY-088",
        "RB-M257"], "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(candidate.get("version") == VERSION and
            candidate.get("firmware_source_commit") == FIRMWARE_SOURCE and
            candidate.get("source_commit") == FIRMWARE_SOURCE and
            candidate.get("runner_commit") == RUNNER_COMMIT and
            candidate.get("cid") == CID and
            len(str(candidate.get("firmware_sha256", ""))) == 64 and
            len(str(candidate.get("app_elf_sha256", ""))) == 64,
            "candidate provenance mismatch")

    incident = evidence.get("incident", {})
    require(incident.get("version") == "1.0.0-dev.372" and
            incident.get("reset_reason_code") == 6 and
            incident.get("safety_reason") == "runtime_watchdog" and
            incident.get("trip_count", 0) >= 1 and
            incident.get("worker_deadline_expired") is False and
            incident.get("heap_exhaustion_observed") is False and
            incident.get("input_failure_observed") is False and
            incident.get("post_reset_stable_ms", 0) >= 54_000_000 and
            incident.get("safe_outputs_quiesced") is True and
            incident.get("physical_write_calls") == 0 and
            incident.get("pre_reset_page_known") is False,
            "overnight incident facts mismatch")

    mitigation = evidence.get("mitigation", {})
    require(mitigation == {
        "finite_product_observation_drain": 16,
        "finite_product_worker_event_drain": 8,
        "finite_wifi_device_observation_drain": 16,
        "retained_first_watchdog_trace": True,
        "safety_quiesce_precedes_diagnostic": True,
        "wifi_data_inspect_interval_us": 1000,
        "wifi_device_queue_capacity": 64,
    }, "mitigation bounds mismatch")

    devices = evidence.get("exact_runs", {}).get("devices", {})
    networks = evidence.get("exact_runs", {}).get("networks", {})
    require(devices.get("elapsed_seconds", 0) >= 180.0 and
            devices.get("hops_completed", 0) >= 1000 and
            devices.get("checkpoint_count", 0) >= 12 and
            devices.get("frames_reported_last", 0) >
                devices.get("frames_reported_first", 0) and
            devices.get("clients_accepted_last", 0) >
                devices.get("clients_accepted_first", 0) and
            devices.get("clients_dropped") == 0 and
            devices.get("catalog_within_capacity") is True and
            devices.get("watchdog_trace_observed") is False and
            devices.get("zero_heap_drift_after_warmup") is True and
            devices.get("final_home_none_zero_lease") is True,
            "exact device endurance mismatch")
    require(networks.get("elapsed_seconds", 0) >= 180.0 and
            networks.get("cycles_completed", 0) >= 50 and
            networks.get("checkpoint_count", 0) >= 12 and
            networks.get("scan_dropped") == 0 and
            networks.get("catalog_within_capacity") is True and
            networks.get("watchdog_trace_observed") is False and
            networks.get("zero_heap_drift_after_warmup") is True and
            networks.get("final_home_none_zero_lease") is True,
            "exact network endurance mismatch")
    require(devices.get("heap_total") == networks.get("heap_total") and
            devices.get("heap_total", 0) > 0,
            "exact run heap-total continuity mismatch")

    diagnostic = evidence.get("diagnostic_stress", {})
    require(all(
        record.get("provenance_eligible") is False and
        record.get("reason") == "incorrect_full_source_commit_argument" and
        record.get("stress_hold_completed") is True and
        record.get("elapsed_seconds", 0) >= 600.0 and
        record.get("safety_latched") is False and
        record.get("watchdog_trace_observed") is False and
        record.get("drops_observed") is False
        for record in diagnostic.values()),
        "diagnostic predecessor classification mismatch")
    require(diagnostic.get("devices", {}).get("hops_completed", 0) >= 4000 and
            diagnostic.get("networks", {}).get("cycles_completed", 0) >= 150,
            "diagnostic stress progress mismatch")

    verified = evidence.get("verified", {})
    require(all(verified.get(key) is True for key in (
        "both_exact_runs_pass", "continuous_progress",
        "zero_radio_drops", "zero_watchdog_recurrence",
        "zero_post_warm_heap_drift", "read_only_storage_continuity",
        "final_home_none_zero_lease", "mac_wifi_untouched")),
        "verified acceptance flag mismatch")
    require(verified.get("rf_transmit_invoked") is False,
            "unexpected RF transmit claim")
    privacy = evidence.get("privacy", {})
    require(all(value is False for value in privacy.values()),
            "privacy-minimal retention mismatch")

    try:
        device_runner = git_file(
            RUNNER_COMMIT, "tools/run_1x_wifi_devices_hil.py")
        network_runner = git_file(
            RUNNER_COMMIT, "tools/run_1x_wifi_networks_hil.py")
        tools = evidence.get("tools", {})
        require(tools.get("device_runner_sha256") ==
                digest_bytes(device_runner) ==
                devices.get("runner_sha256"),
                "historical device runner hash mismatch")
        require(tools.get("network_runner_sha256") ==
                digest_bytes(network_runner) ==
                networks.get("runner_sha256"),
                "historical network runner hash mismatch")
        arduino = git_file(
            FIRMWARE_SOURCE,
            "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp")
        passive = git_file(
            FIRMWARE_SOURCE,
            "firmware/leshy1/src/platform/arduino/BoardWifiPassiveCapture.cpp")
        for token in (
                b"kProductSurveyWorkerEventCapacity = 8",
                b"kProductSurveyWorkerEventDrainBudget =",
                b"kProductSurveyObservationDrainBudget = 16",
                b"kWifiDeviceObservationDrainBudget = 16",
                b"RuntimeWatchdogTraceRecord",
                b"esp_task_wdt_print_triggered_tasks"):
            require(token in arduino,
                    f"firmware source guard missing: {token!r}")
        require(b"kDeviceDataInspectIntervalUs" in passive and
                b"nextDeviceDataInspectUs_" in passive,
                "passive data-frame throttle source guard missing")
    except (OSError, subprocess.CalledProcessError) as error:
        failures.append(f"historical source unavailable: {error}")

    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(
        "Wi-Fi runtime-watchdog acceptance passed: retained overnight WDT "
        "incident, bounded loop work, exact device/network endurance, zero "
        "drops/watchdog recurrence and final Home/none/lease 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
