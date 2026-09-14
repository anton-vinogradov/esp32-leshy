#!/usr/bin/env python3
"""Retain a privacy-minimal blocked two-product-DIV deployment, never a pass."""
import argparse
import hashlib
import json
from pathlib import Path
from esp_app_identity import app_elf_sha256


def retain(before, after):
    def records(path):
        result = []
        for line in path.read_text().splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict): result.append(value)
            except ValueError:
                pass
        return result

    observed = records(before / "source-postdeploy-safety.log")
    boot = next(v for v in observed if v.get("schema") == "leshy.boot.v1")
    safety = next(v for v in observed if v.get("schema") == "leshy.safety.v1")
    identity = app_elf_sha256(before / "firmware.bin")
    assert boot["app_elf_sha256"] == identity
    assert safety["watchdog_journal_app_elf_sha256"] == identity
    assert safety["latched"] and safety["reason"] == "runtime_watchdog"
    assert safety["watchdog_trace_valid"] and safety["watchdog_journal_nvs_verified"]
    assert safety["runtime_owner"] == "none" and safety["lease_mask"] == 0
    assert safety["buzzer_inactive"] and safety["nrf_ce_inactive"]
    retry = records(before / "source-clear-boot.log")
    attempts = [v["completed_attempts"] for v in retry
                if v.get("schema") == "leshy.storage.product_boot_retry.v1"]
    assert attempts == [1, 2, 3, 4]
    failed = (after / "source-deploy.log").read_text()
    assert "Failed to connect to ESP32-S3: No serial data received." in failed
    assert "Writing at" not in failed and "Hash of data verified" not in failed
    assert "'ready_ms': None" in (after / "source-usb-recovery.log").read_text()
    names = [before / n for n in (
        "deploy.log", "source-postdeploy-safety.log", "source-clear-boot.log",
        "source-clear-boot-continuation.log", "source-final-read.log")]
    names += [after / n for n in ("source-deploy.log", "source-usb-recovery.log")]
    return {
        "schema": "leshy.wifi_product_boot.blocker.v1", "status": "blocked",
        "two_board_acceptance": False, "test_network_started": False,
        "installed_source_version": boot["version"], "app_elf_sha256": identity,
        "image_sha256": hashlib.sha256((before / "firmware.bin").read_bytes()).hexdigest(),
        "retained_stop": {k: safety[k] for k in (
            "reason", "reset_reason_code", "watchdog_trip_stage",
            "watchdog_triggered_cpu_mask", "watchdog_incident_sequence",
            "watchdog_journal_nvs_verified", "watchdog_journal_sd_write_attempted",
            "runtime_owner", "lease_mask", "buzzer_inactive", "nrf_ce_inactive")},
        "observed_sd_retry_attempts": attempts,
        "followup_app_elf_sha256": app_elf_sha256(after / "firmware.bin"),
        "followup_image_sha256": hashlib.sha256((after / "firmware.bin").read_bytes()).hexdigest(),
        "followup_written": False, "receiver_unchanged_version": "1.0.0-dev.385",
        "cause": "unconfirmed: startup Task-WDT; later SD retries and unresponsive USB",
        "limits": "Follow-up adds startup-stage logging and a completed-recovery feed; neither its boot nor the AP role is physically accepted. No new feature/cadence credit.",
        "private_log_sha256": {str(p.parent.name + "/" + p.name):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in names},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.before, args.after)
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print("retained blocked deployment; no HIL acceptance")
