#!/usr/bin/env python3
"""Machine-check retained asynchronous Product Survey worker evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-survey-worker-0.59.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-survey-worker-0.59"
CID = "FE343253440000002000000055019CB7"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def exact(record: dict[str, Any], expected: dict[str, Any], prefix: str,
          failures: list[str]) -> None:
    for field, value in expected.items():
        if record.get(field) != value:
            failures.append(
                f"{prefix}{field}: {record.get(field)!r} != {value!r}"
            )


def main() -> int:
    failures: list[str] = []
    evidence = load(EVIDENCE)
    exact(evidence, {
        "schema": "leshy.product_survey_worker_acceptance.v1",
        "status": "pass_progress_not_stage_gate",
        "trust_status": "unsigned_local_result",
        "runner_gate_eligible": True,
        "stage_gate_eligible": False,
        "release_gate_eligible": False,
        "evidence_ids": ["E-BUILD-061", "E-AUTO-024", "E-HIL-084"],
        "board": "board-01",
        "profile": "esp32-div-v2-n16",
    }, "", failures)
    exact(evidence.get("media", {}), {
        "cid": CID,
        "product_root": "/leshy/sessions/v1",
        "disposable_test_card": True,
    }, "media.", failures)

    candidate = evidence.get("candidate", {})
    exact(candidate, {
        "version": "0.59.0-product-survey-worker-measure",
        "firmware_sha256":
            "bc817b951c19a45c6346b767bb6860d769f5048c0d85ba23e6418a9eee9c2764",
        "factory_sha256":
            "78f1655196beb9aea9780b51a6af563332aea9ca7a4bea49749ade105bcb730f",
        "app_elf_sha256":
            "fc4f371e2bc6f83b15c0ff678e78873b9a93c795028a3cb217b09c24bed2b662",
        "map_sha256":
            "48f08485607ed46484177c200893c989f046389066ac8e592477beb83226bb16",
        "linked_flash_bytes": 1111148,
        "static_ram_bytes": 128800,
        "app_image_bytes": 1111296,
        "factory_image_bytes": 1176832,
        "rtc_noinit_bytes": 20,
        "flashed_and_verified": True,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate.", failures)

    retained = evidence.get("retained", {})
    exact(retained, {
        "bundle_path":
            "tests/hil/evidence/board-01-product-survey-worker-0.59",
        "run_sha256":
            "30efac9b90afdb5d68918bfea35c2101a158c97836dd9a5c71bd6b5b6334866c",
        "artifact_index_sha256":
            "8a03c25a5cca0651f841aab115bba45bda2cdcfd4741409544af7b5d90d48b0b",
        "runner_source_sha256":
            "bb870a0be77fd8568de65367e80a2882a4091c6d12e3c664f92f22df2685e65a",
        "runner_source_binding": "runtime_emitted_and_retained_exact_bytes",
    }, "retained.", failures)

    firmware = BUNDLE / "firmware.bin"
    run_path = BUNDLE / "run.json"
    runner_path = BUNDLE / "runner.py"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures,
            firmware.is_file() and firmware.stat().st_size ==
            candidate.get("app_image_bytes") and
            digest(firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            "retained exact candidate mismatch")
    require(failures,
            digest(run_path) == retained.get("run_sha256"),
            "retained run hash mismatch")
    require(failures,
            digest(index_path) == retained.get("artifact_index_sha256"),
            "retained artifact index hash mismatch")
    require(failures,
            digest(runner_path) == retained.get("runner_source_sha256"),
            "retained runner source hash mismatch")

    indexed: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append("malformed artifact index line")
            continue
        expected, relative = parts
        require(failures,
                re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                f"invalid artifact hash: {relative}")
        path = (BUNDLE / relative).resolve()
        try:
            path.relative_to(BUNDLE.resolve())
        except ValueError:
            failures.append(f"artifact escapes bundle: {relative}")
            continue
        require(failures,
                path.is_file() and digest(path) == expected,
                f"artifact hash mismatch: {relative}")
        indexed.add(relative)
    bundled_files = {
        str(path.relative_to(BUNDLE))
        for path in BUNDLE.rglob("*") if path.is_file()
    } - {"artifacts.sha256"}
    require(failures, indexed == bundled_files and len(indexed) == 20,
            "artifact index does not exactly cover the retained bundle")

    run = load(run_path)
    require(failures,
            run.get("schema") == "leshy.product_survey_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("runner_source_sha256") ==
            retained.get("runner_source_sha256") and
            run.get("candidate") == {
                "firmware_sha256": candidate.get("firmware_sha256"),
                "app_elf_sha256": candidate.get("app_elf_sha256"),
                "version": candidate.get("version"),
                "flashed": True,
            } and run.get("expected_cid") == CID,
            "runner result/identity mismatch")

    worker = evidence.get("worker_contract", {})
    exact(worker, {
        "persistent_task": True,
        "task_core": 0,
        "task_stack_bytes": 8192,
        "event_queue_capacity": 8,
        "observation_queue_capacity": 64,
        "scan_interval_ms": 1000,
        "ui_owns_pipeline": True,
        "source_callback_nonblocking": True,
        "start_action_budget_us": 10000,
        "stop_action_budget_us": 10000,
        "detail_back_budget_ms": 150,
        "active_scan_cancel_supported": True,
        "fail_closed_cleanup": True,
    }, "worker_contract.", failures)
    entry = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text(
        encoding="utf-8"
    )
    scanner = (ROOT / "firmware/leshy1/src/platform/arduino/BoardWifiPassiveScanner.cpp").read_text(
        encoding="utf-8"
    )
    for token in (
        "kProductSurveyWorkerEventCapacity = 8",
        "kProductSurveyObservationCapacity =",
        "ObservationQueue::kCapacity",
        "kProductSurveyScanIntervalMs = 1000",
        'runProductSurveyWorker, "leshy-survey", 8192, nullptr, 1,',
        "&productSurveyWorkerTaskHandle, 0",
        "xQueueSend(productSurveyObservations, &observation, 0)",
        "serviceProductSurveyWorker();",
        "best_effort_cleanup",
    ):
        source = runner_path.read_text(encoding="utf-8") if token == "best_effort_cleanup" else entry
        require(failures, token in source, f"worker source contract missing: {token}")
    require(failures,
            "BoardWifiPassiveScanner::cancelActiveScan()" in scanner and
            "esp_wifi_scan_stop()" in scanner,
            "active scan cancellation contract missing")

    before_ready = run.get("boot_before", {}).get("ready", {})
    after_ready = run.get("boot_after", {}).get("ready", {})
    for name, ready in (("before", before_ready), ("after", after_ready)):
        exact(ready, {
            "version": candidate.get("version"),
            "app_elf_sha256": candidate.get("app_elf_sha256"),
            "profile": "esp32-div-v2-n16",
            "heap_total": 272704,
            "heap_free": 208928,
            "heap_min_free": 188736,
            "buzzer_inactive": True,
            "input_detected": True,
        }, f"boot_{name}.", failures)
    before = run.get("boot_before", {}).get("recovery", {})
    after = run.get("boot_after", {}).get("recovery", {})
    for name, recovery, generation, observations in (
        ("before", before, 66, 10),
        ("after", after, 67, 27),
    ):
        exact(recovery, {
            "status": "admitted",
            "expected_fingerprint": CID,
            "observed_fingerprint": CID,
            "generation": generation,
            "observations": observations,
            "attempts": 1,
            "transient_retries": 0,
            "timeout_restarts": 0,
            "mounted_read_only": True,
            "read_only_guaranteed": True,
            "catalog_admitted": True,
            "cleanup_complete": True,
            "blocked_write_attempts": 0,
            "physical_write_calls": 0,
            "owned_after": 0,
        }, f"boot_{name}_recovery.", failures)

    start = run.get("start_ack", {})
    running = run.get("running", {})
    detail = run.get("running_detail", {})
    returned = run.get("running_list_after_detail", {})
    stop = run.get("stop_ack", {})
    committed = run.get("committed", {})
    exact(start, {
        "survey_product_status": "preparing",
        "survey_product_worker_ready": True,
        "survey_product_source_active": False,
        "survey_product_backend_open": False,
        "survey_product_start_action_us": 13,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "start_ack.", failures)
    exact(running, {
        "survey_product_status": "running",
        "survey_product_worker_ready": True,
        "survey_product_source_active": True,
        "survey_product_backend_open": True,
        "survey_product_identity_status": "valid",
        "survey_product_identity_attempts": 1,
        "survey_product_identity_transient_retries": 0,
        "survey_product_expected_cid": CID,
        "survey_product_observed_cid": CID,
        "survey_product_scan_cycles": 1,
        "survey_observations": 14,
        "survey_scan_accepted": 14,
        "survey_forwarded": 14,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_product_start_action_us": 13,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "running.", failures)
    exact(detail, {
        "survey_view": "detail",
        "survey_product_source_active": True,
        "survey_product_scan_cycles": 2,
        "survey_observations": 27,
        "survey_running": True,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "running_detail.", failures)
    exact(returned, {
        "survey_view": "list",
        "survey_product_source_active": True,
        "survey_product_scan_cycles": 2,
        "survey_observations": 27,
        "survey_running": True,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "running_list_after_detail.", failures)
    exact(stop, {
        "survey_product_status": "stopping",
        "survey_product_source_active": True,
        "survey_product_backend_open": True,
        "survey_product_stop_action_us": 10,
        "survey_product_scan_cycles": 2,
        "survey_observations": 27,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "stop_ack.", failures)
    exact(committed, {
        "survey_product_status": "committed",
        "survey_workflow_status": "committed",
        "survey_pipeline_status": "committed",
        "survey_product_source_active": False,
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
        "survey_generation": 67,
        "library_generation": 67,
        "survey_observations": 27,
        "survey_received": 27,
        "survey_scan_accepted": 27,
        "survey_forwarded": 27,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_queue_high_water": 10,
        "survey_product_stop_action_us": 10,
    }, "committed.", failures)
    require(failures,
            0 < run.get("start_ack_ms", 999) <= 150 and
            0 < run.get("detail_back_ack_ms", 999) <= 150 and
            0 < run.get("stop_ack_ms", 999) <= 150,
            "Start/Detail Back/Stop acknowledgement budget mismatch")

    cleanup_before = run.get("cleanup_before_reboot", {})
    cleanup_final = run.get("cleanup_final", {})
    for name, cleanup in (
        ("before_reboot", cleanup_before), ("final", cleanup_final)
    ):
        state = cleanup.get("final_state", {})
        require(failures,
                cleanup.get("attempted") is True and
                cleanup.get("complete") is True and cleanup.get("errors") == [] and
                state.get("page") == "home" and
                state.get("runtime_owner") == "none" and
                state.get("lease_mask") == 0 and
                state.get("survey_product_source_active") is False and
                state.get("survey_product_backend_open") is False,
                f"{name} cleanup mismatch")

    export = run.get("library_export", {})
    exact(export, {
        "status": "valid",
        "generation": 67,
        "integrity": "valid",
        "persistent": True,
        "simulated": False,
        "storage_backend": "persistent_media",
        "radio_touched": False,
    }, "library_export.", failures)
    exact(export.get("session", {}), {
        "id": "product-wifi-live",
        "observations": 27,
        "dropped": 0,
        "sources": {"wifi": 27},
    }, "library_export.session.", failures)

    captures = run.get("captures", {})
    states = ["setup", "running", "detail", "committed", "export"]
    require(failures, sorted(captures) == sorted(states),
            "capture set mismatch")
    for state in states:
        record = captures.get(state, {})
        raw = BUNDLE / f"frames/{state}.rgb565"
        png = BUNDLE / f"frames/{state}.png"
        trace = BUNDLE / f"frames/{state}.json"
        require(failures,
                raw.stat().st_size == 153600 and
                digest(raw) == record.get("rgb565_sha256") and
                digest(png) == record.get("png_sha256") and
                load(trace) == record and
                record.get("frame_begin", {}).get("revision") ==
                record.get("frame_end", {}).get("revision") ==
                record.get("state", {}).get("revision"),
                f"{state}: retained TFT capture mismatch")

    summary = evidence.get("run", {})
    require(failures, summary == {
        "run_id": run.get("run_id"),
        "exact_cid": run.get("expected_cid"),
        "generation_before": before.get("generation"),
        "generation_after": after.get("generation"),
        "running_scan_cycles": running.get("survey_product_scan_cycles"),
        "running_observations": running.get("survey_observations"),
        "detail_scan_cycles": detail.get("survey_product_scan_cycles"),
        "detail_observations": detail.get("survey_observations"),
        "committed_observations": committed.get("survey_observations"),
        "accepted": committed.get("survey_scan_accepted"),
        "forwarded": committed.get("survey_forwarded"),
        "scan_drops": committed.get("survey_scan_dropped"),
        "pipeline_drops": committed.get("survey_dropped"),
        "queue_high_water": committed.get("survey_queue_high_water"),
        "start_action_us": running.get("survey_product_start_action_us"),
        "stop_action_us": committed.get("survey_product_stop_action_us"),
        "start_ack_ms": run.get("start_ack_ms"),
        "detail_back_ack_ms": run.get("detail_back_ack_ms"),
        "stop_ack_ms": run.get("stop_ack_ms"),
        "boot_before_attempts": before.get("attempts"),
        "boot_after_attempts": after.get("attempts"),
        "boot_transient_retries":
            before.get("transient_retries") + after.get("transient_retries"),
        "boot_timeout_restarts":
            before.get("timeout_restarts") + after.get("timeout_restarts"),
        "heap_total_bytes": before_ready.get("heap_total"),
        "heap_free_bytes": before_ready.get("heap_free"),
        "heap_min_free_bytes": before_ready.get("heap_min_free"),
        "heap_drift_bytes": max(
            abs(before_ready.get("heap_total") - after_ready.get("heap_total")),
            abs(before_ready.get("heap_free") - after_ready.get("heap_free")),
            abs(before_ready.get("heap_min_free") - after_ready.get("heap_min_free")),
        ),
        "captures": len(captures),
        "final_page": cleanup_final.get("final_state", {}).get("page"),
        "final_owner": cleanup_final.get("final_state", {}).get("runtime_owner"),
        "final_lease_mask": cleanup_final.get("final_state", {}).get("lease_mask"),
    }, "evidence summary is not exactly derived from retained run")

    exact(evidence.get("acceptance", {}), {
        "start_acknowledged_before_identity_scan_mount_or_storage_work": True,
        "source_active_in_list": True,
        "source_active_in_detail": True,
        "worker_progressed_while_detail_open": True,
        "detail_back_preserved_running_session": True,
        "stop_acknowledged_before_commit": True,
        "single_next_generation_committed": True,
        "source_stopped_before_commit_completed": True,
        "backend_closed_after_commit": True,
        "cleanup_complete_before_reboot": True,
        "reboot_recovered_exact_generation_read_only": True,
        "library_export_valid_persistent_non_simulated": True,
        "zero_final_resources": True,
    }, "acceptance.", failures)
    require(failures, evidence.get("visual_review") == {
        "manual_review": "pass",
        "independent_goldens": False,
        "states": states,
    }, "visual review scope mismatch")
    require(failures, evidence.get("s3_criteria") == {
        "1_clean_boot_probe": "pass",
        "2_user_start": "pass_async_worker",
        "3_passive_normalized_observations": "pass_continuous_two_cycles",
        "4_list_detail_back": "pass_live_worker_progress",
        "5_atomic_stop_commit": "pass_software_reset_only",
        "6_reboot_offline_reopen": "pass",
        "7_json_summary_export": "pass",
        "8_host_and_hil_coverage": "pass",
        "9_missing_source_visible_zero_lease": "partial_host_contract_only",
    }, "S3 criteria state mismatch")
    require(failures, evidence.get("open_gate_work") == [
        "missing_source_real_tft", "physical_cancel_during_scan",
        "physical_power_cut", "littlefs_parity", "independent_demo_goldens",
    ], "open S3 gate work mismatch")
    limitations = evidence.get("limitations", [])
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("unsigned", "physical cancel", "missing-source",
                   "physical power cut", "LittleFS", "RF detector",
                   "not S3 stage or release"):
        require(failures, phrase in joined,
                f"limitations missing {phrase!r}")

    if failures:
        print("Product Survey worker evidence failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Product Survey worker evidence passed: async Start 13 us, live Detail "
        "progress 14/1 -> 27/2, Stop 10 us, generation 66->67, zero drops, "
        "read-only reboot/export, final lease 0; S3 gate remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
