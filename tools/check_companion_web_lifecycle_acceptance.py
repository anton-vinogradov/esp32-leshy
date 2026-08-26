#!/usr/bin/env python3
"""Fail closed unless exact 0.181 local-Web lifecycle evidence is intact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-companion-web-lifecycle-0.181.json"


def main() -> int:
    failures: list[str] = []
    try:
        value = json.loads(SUMMARY.read_text(encoding="utf-8"))
        candidate = value["candidate"]
        if not (
            value["schema"] ==
            "leshy.hil.companion_web_lifecycle.acceptance.v1"
            and value["status"] == "pass"
            and value["evidence_ids"] == [
                "E-BUILD-151", "E-AUTO-123", "E-HIL-181",
                "E-COMPANION-005"
            ]
            and value["firmware_source_commit"] ==
            "6e0f2be76240e38d12805cfd654a7d70c61ae3d8"
            and value["verification_source_commit"] ==
            "6e0f2be76240e38d12805cfd654a7d70c61ae3d8"
            and candidate == {
                "app_elf_sha256":
                "eb42e6f9002a708329cb2498b0b37dc7be4d26f74bd40676e331ca599a56c31e",
                "built_partitions_sha256":
                "325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3",
                "factory_bytes": 3425648,
                "factory_sha256":
                "b1a391215039621da8f7acc3d8cba5311d3d19bae10100b8ead1748d5ab98abb3",
                "firmware_bytes": 3360112,
                "firmware_sha256":
                "7491f450026c864f228df3164155afd1c388d1faa0b8a60bf9a9ef652933cd9d",
                "linked_flash_bytes": 3359608,
                "map_sha256":
                "585c0b9ec83193e1d8d239119359a934e111b1b3d7ce15b75a2f499004f92c84",
                "static_ram_bytes": 222800,
                "version": "0.181.0-companion-web-deferred-worker-restore",
            }
        ):
            failures.append("candidate/source/evidence identity mismatch")

        install = value["installation"]
        preflight = install["partition_preflight"]
        if not (
            value["exact_cid"] == "FE343253440000002000000055019CB7"
            and install["application_flash_count"] == 1
            and install["partition_flash_count"] == 0
            and preflight["matched"] is True
            and preflight["performed_before_application_flash"] is True
            and preflight["expected_sha256"] == preflight["observed_sha256"] ==
            "339bda68b7470d5ad1482d10183514b88971c6f1f20ff87c7e2f3dad96235ba2"
        ):
            failures.append("installation/partition/CID mismatch")

        lifecycle = value["lifecycle"]
        staged = lifecycle["staged"]
        active = lifecycle["active"]
        stopped = lifecycle["stopped"]
        released = lifecycle["released"]
        if not (
            staged["overlay_open"] is True
            and staged["authorized"] is False
            and staged["server_active"] is False
            and staged["credential_present"] is False
            and staged["lease_mask"] == 13
            and active["authorized"] is True
            and active["server_active"] is True
            and active["credential_present"] is True
            and active["credential_persisted"] is False
            and active["credential_exposed_over_diagnostic"] is False
            and active["begin_stage"] == "ready"
            and active["driver_error"] == 0
            and active["targets_suspended"] is True
            and active["survey_worker_suspended"] is True
            and active["heap_free_after_worker_suspend"] == 60788
            and active["heap_free_before_begin"] == 54764
            and active["heap_largest_before_begin"] == 23540
            and active["heap_free_after_begin"] == 16868
            and active["lease_mask"] == 15
            and stopped["cleanup_complete"] is True
            and stopped["server_active"] is False
            and stopped["credential_present"] is False
            and stopped["targets_suspended"] is False
            and stopped["survey_worker_suspended"] is True
            and stopped["stop_reason"] == "user"
            and released["cleanup_complete"] is True
            and released["server_active"] is False
            and released["credential_present"] is False
            and released["targets_suspended"] is False
            and released["survey_worker_suspended"] is False
            and released["lease_mask"] == 0
            and lifecycle["limits"] == {
                "idle_timeout_us": 600000000,
                "maximum_clients": 1,
                "maximum_lifetime_us": 1800000000,
            }
        ):
            failures.append("staged/active/stop/release lifecycle mismatch")

        product = value["product_state"]
        safety = value["safety_and_final"]
        if not (
            product["catalog_generation"] == 161
            and product["catalog_observations"] == 59
            and product["target_state_generation"] == 17
            and product["mounted_read_only"] is True
            and product["physical_write_calls"] == 0
            and product["boot_recovery_attempts"] == 1
            and product["boot_recovery_transient_retries"] == 0
            and product["boot_recovery_timeout_restarts"] == 0
            and product["boot_recovery_cleanup_complete"] is True
            and safety["heap_total"] == 156004
            and safety["heap_free_before"] == 83204
            and safety["heap_free_after"] == 75972
            and safety["heap_min_after"] == 14088
            and safety["radio_tx_scope"] == "explicit_ephemeral_softap_only"
            and safety["radio_tx_commands"] == 0
            and safety["storage_write_commands"] == 0
            and safety["input_queue_drops"] == 0
            and safety["input_read_errors"] == 0
            and safety["buzzer_inactive"] is True
            and safety["nrf_ce_inactive"] is True
            and safety["software_quiesce_complete"] is True
            and safety["safety_armed"] is True
            and safety["safety_latched"] is False
            and safety["safety_clear_performed"] is False
            and safety["lease_mask"] == 0
        ):
            failures.append("product continuity/final safety mismatch")

        if not (
            value["http_exchange"] == {
                "reason": "host_wifi_state_not_modified", "tested": False
            }
            and value["transport"] == {
                "cardputer_ports_opened": 0,
                "opened_ports": ["/dev/cu.usbmodem2101"],
                "serial_port_discovery_calls": 0,
            }
            and value["physical_cadence"] == {
                "accepted_since_full": 2, "full_gate_at": 15
            }
            and len(value["raw_run_sha256"]) == 64
        ):
            failures.append("HTTP boundary/USB isolation/cadence mismatch")

        precursors = value["failed_precursors"]
        if not (
            len(precursors) == 2
            and [item["version"] for item in precursors] == [
                "0.179.0-companion-web-single-client",
                "0.180.0-companion-web-worker-suspend",
            ]
            and [item["checkpoint"] for item in precursors] == [
                "explicit_authorization", "explicit_stop"
            ]
            and all(item["firmware_failure"] is True for item in precursors)
            and all(item["cleanup_complete"] is True for item in precursors)
            and all(len(item["run_sha256"]) == 64 for item in precursors)
        ):
            failures.append("failed precursor lineage mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "Companion Web lifecycle acceptance passed: explicit two-step consent, "
        "one ephemeral client, bounded zero-PSRAM admission and complete cleanup"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
