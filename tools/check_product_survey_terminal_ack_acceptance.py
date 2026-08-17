#!/usr/bin/env python3
"""Machine-check the 0.60 terminal-ack race fix and physical regression."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from check_product_survey_worker_acceptance import digest, exact, load, require
from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-survey-terminal-ack-0.60.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-survey-terminal-ack-0.60"
CID = "FE343253440000002000000055019CB7"


def main() -> int:
    failures: list[str] = []
    evidence = load(EVIDENCE)
    exact(evidence, {
        "schema": "leshy.product_survey_terminal_ack_acceptance.v1",
        "status": "pass_progress_not_stage_gate",
        "trust_status": "unsigned_local_result",
        "runner_gate_eligible": True,
        "stage_gate_eligible": False,
        "release_gate_eligible": False,
        "evidence_ids": ["E-BUILD-062", "E-AUTO-025", "E-HIL-085"],
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
        "version": "0.60.0-product-survey-terminal-ack-measure",
        "firmware_sha256":
            "eadf8aeabc0cb2121fa038b9b082e8730234f450cc002fffa0ae2722e4775840",
        "factory_sha256":
            "b9ec7c22e3701c791b299f90d7f6104cb04b18853a32fb8e0e32b75080027cfd",
        "app_elf_sha256":
            "bb57fc841734f8f77306e7cdc484af66aa6d563612b683dd2a9433541b5a52b5",
        "map_sha256":
            "2f4708d7772e4b4c578a0c5f642380ee0a848442c726ffae854b105fc52e1c1c",
        "linked_flash_bytes": 1111128,
        "static_ram_bytes": 128800,
        "app_image_bytes": 1111280,
        "factory_image_bytes": 1176816,
        "rtc_noinit_bytes": 20,
        "flashed_and_verified": True,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "candidate.", failures)

    retained = evidence.get("retained", {})
    exact(retained, {
        "bundle_path":
            "tests/hil/evidence/board-01-product-survey-terminal-ack-0.60",
        "run_sha256":
            "529a63c687bfdc02918d2e35c805597de7b674e8c630a5a68b15d5a27d1f2346",
        "artifact_index_sha256":
            "769698be5d4a5754c5d0a095061ad48c96dcd350cd08d95aa18a7588675e4b7e",
        "runner_source_sha256":
            "bb870a0be77fd8568de65367e80a2882a4091c6d12e3c664f92f22df2685e65a",
        "runner_source_binding": "runtime_emitted_and_retained_exact_bytes",
    }, "retained.", failures)

    firmware = BUNDLE / "firmware.bin"
    run_path = BUNDLE / "run.json"
    runner_path = BUNDLE / "runner.py"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures,
            firmware.is_file() and
            firmware.stat().st_size == candidate.get("app_image_bytes") and
            digest(firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            "retained exact 0.60 candidate mismatch")
    require(failures, digest(run_path) == retained.get("run_sha256"),
            "retained 0.60 run hash mismatch")
    require(failures, digest(index_path) == retained.get("artifact_index_sha256"),
            "retained 0.60 artifact index hash mismatch")
    require(failures, digest(runner_path) == retained.get("runner_source_sha256"),
            "retained 0.60 runner hash mismatch")

    indexed: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append("malformed 0.60 artifact index line")
            continue
        expected, relative = parts
        require(failures, re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                f"invalid 0.60 artifact hash: {relative}")
        path = (BUNDLE / relative).resolve()
        try:
            path.relative_to(BUNDLE.resolve())
        except ValueError:
            failures.append(f"0.60 artifact escapes bundle: {relative}")
            continue
        require(failures, path.is_file() and digest(path) == expected,
                f"0.60 artifact hash mismatch: {relative}")
        indexed.add(relative)
    bundled_files = {
        str(path.relative_to(BUNDLE))
        for path in BUNDLE.rglob("*") if path.is_file()
    } - {"artifacts.sha256"}
    require(failures, indexed == bundled_files and len(indexed) == 20,
            "0.60 index does not exactly cover the retained bundle")

    run = load(run_path)
    require(failures,
            run.get("schema") == "leshy.product_survey_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("runner_source_sha256") == retained.get("runner_source_sha256") and
            run.get("candidate") == {
                "firmware_sha256": candidate.get("firmware_sha256"),
                "app_elf_sha256": candidate.get("app_elf_sha256"),
                "version": candidate.get("version"),
                "flashed": True,
            } and run.get("expected_cid") == CID,
            "0.60 runner result/identity mismatch")

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
        "worker_terminal_state_held_until_ui_acknowledgement": True,
        "start_action_budget_us": 10000,
        "stop_action_budget_us": 10000,
        "detail_back_budget_ms": 150,
        "active_scan_cancel_supported": True,
        "fail_closed_cleanup": True,
    }, "worker_contract.", failures)

    entry = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text(
        encoding="utf-8"
    )
    worker_start = entry.find("void runProductSurveyWorker(")
    worker_end = entry.find("bool initializeProductSurveyWorker()", worker_start)
    release_start = entry.find("void releaseProductSurveyAfterTerminal(")
    service_end = entry.find("void recoverProductCatalogForFingerprint(", release_start)
    require(failures, worker_start >= 0 and worker_end > worker_start,
            "0.60 worker source boundary missing")
    if worker_start >= 0 and worker_end > worker_start:
        require(failures,
                "setProductSurveyControl(ProductSurveyWorkerControl::Idle)" not in
                entry[worker_start:worker_end],
                "worker exposes Idle before terminal event consumption")
    require(failures, release_start >= 0 and service_end > release_start and
            entry[release_start:service_end].count(
                "setProductSurveyControl(ProductSurveyWorkerControl::Idle)") == 2,
            "UI does not exclusively acknowledge cleanup/commit terminals")
    require(failures,
            "product Survey worker exposes Idle before UI consumes terminal event" in
            (ROOT / "tools/check_clean_target.py").read_text(encoding="utf-8"),
            "static terminal-ownership regression guard missing")

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
        ("before", before, 67, 27), ("after", after, 68, 25)
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
        "survey_product_start_action_us": 12,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "start_ack.", failures)
    exact(running, {
        "survey_product_status": "running",
        "survey_product_source_active": True,
        "survey_product_backend_open": True,
        "survey_product_scan_cycles": 1,
        "survey_observations": 12,
        "survey_scan_accepted": 12,
        "survey_forwarded": 12,
        "survey_dropped": 0,
        "survey_product_start_action_us": 12,
        "runtime_owner": "survey",
        "lease_mask": 15,
    }, "running.", failures)
    for name, state, view in (
        ("running_detail", detail, "detail"),
        ("running_list_after_detail", returned, "list"),
    ):
        exact(state, {
            "survey_view": view,
            "survey_product_status": "running",
            "survey_product_source_active": True,
            "survey_product_backend_open": True,
            "survey_product_scan_cycles": 2,
            "survey_observations": 25,
            "survey_scan_accepted": 25,
            "survey_forwarded": 25,
            "survey_dropped": 0,
            "survey_running": True,
            "runtime_owner": "survey",
            "lease_mask": 15,
        }, f"{name}.", failures)
    exact(stop, {
        "survey_product_status": "stopping",
        "survey_product_source_active": True,
        "survey_product_backend_open": True,
        "survey_product_stop_action_us": 8,
        "survey_product_scan_cycles": 2,
        "survey_observations": 25,
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
        "survey_generation": 68,
        "library_generation": 68,
        "survey_observations": 25,
        "survey_received": 25,
        "survey_scan_accepted": 25,
        "survey_forwarded": 25,
        "survey_dropped": 0,
        "survey_queue_depth": 0,
        "survey_queue_high_water": 9,
        "survey_product_stop_action_us": 8,
    }, "committed.", failures)
    require(failures,
            0 < run.get("start_ack_ms", 999) <= 150 and
            0 < run.get("detail_back_ack_ms", 999) <= 150 and
            0 < run.get("stop_ack_ms", 999) <= 150,
            "0.60 Start/Detail Back/Stop budget mismatch")

    for name in ("cleanup_before_reboot", "cleanup_final"):
        cleanup = run.get(name, {})
        state = cleanup.get("final_state", {})
        require(failures,
                cleanup.get("attempted") is True and
                cleanup.get("complete") is True and cleanup.get("errors") == [] and
                state.get("page") == "home" and
                state.get("runtime_owner") == "none" and
                state.get("lease_mask") == 0 and
                state.get("survey_product_source_active") is False and
                state.get("survey_product_backend_open") is False,
                f"0.60 {name} mismatch")
    export = run.get("library_export", {})
    exact(export, {
        "status": "valid",
        "generation": 68,
        "integrity": "valid",
        "persistent": True,
        "simulated": False,
        "storage_backend": "persistent_media",
        "radio_touched": False,
    }, "library_export.", failures)
    exact(export.get("session", {}), {
        "id": "product-wifi-live",
        "observations": 25,
        "dropped": 0,
        "sources": {"wifi": 25},
    }, "library_export.session.", failures)

    captures = run.get("captures", {})
    states = ["setup", "running", "detail", "committed", "export"]
    require(failures, sorted(captures) == sorted(states), "0.60 capture set mismatch")
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
                f"0.60 {state} TFT capture mismatch")

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
        "final_page": run.get("cleanup_final", {}).get("final_state", {}).get("page"),
        "final_owner":
            run.get("cleanup_final", {}).get("final_state", {}).get("runtime_owner"),
        "final_lease_mask":
            run.get("cleanup_final", {}).get("final_state", {}).get("lease_mask"),
    }, "0.60 evidence summary is not exactly derived from retained run")

    exact(evidence.get("acceptance", {}), {
        "terminal_idle_race_removed_by_ui_acknowledgement": True,
        "static_contract_rejects_worker_side_idle_transition": True,
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
    }, "0.60 visual review scope mismatch")
    require(failures, evidence.get("s3_criteria", {}).get(
        "9_missing_source_visible_zero_lease") == "partial_host_contract_only",
        "0.60 S3 criterion 9 must remain partial")
    require(failures, evidence.get("open_gate_work") == [
        "missing_source_real_tft", "physical_cancel_during_scan",
        "physical_power_cut", "littlefs_parity", "independent_demo_goldens",
    ], "0.60 open S3 work mismatch")
    limitations = evidence.get("limitations", [])
    joined = "\n".join(limitations) if isinstance(limitations, list) else ""
    for phrase in ("unsigned", "repeated-Start", "physical cancel",
                   "missing-source", "physical power cut", "LittleFS",
                   "RF detector", "not S3 stage or release"):
        require(failures, phrase in joined, f"0.60 limitations missing {phrase!r}")

    if failures:
        print("Product Survey terminal-ack evidence failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Product Survey terminal-ack evidence passed: worker cannot expose Idle "
        "before UI terminal acknowledgement; exact 0.60 advances 67->68 with "
        "25/25 forwarded, live Detail progress, read-only reboot/export, and "
        "final lease 0; S3 gate remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
