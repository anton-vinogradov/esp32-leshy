#!/usr/bin/env python3
"""Machine-check the retained 0.61 failure and exact 0.62 active-scan cancel."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from check_product_survey_worker_acceptance import digest, exact, load, require
from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-survey-active-cancel-0.62.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-product-survey-active-cancel-0.62"
FAILED = ROOT / "tests/hil/evidence/board-01-product-survey-active-cancel-0.61-failed"
CID = "FE343253440000002000000055019CB7"


def check_bundle(path: Path, expected_run: str, expected_index: str,
                 expected_runner: str, expected_files: int,
                 failures: list[str]) -> None:
    require(failures, digest(path / "run.json") == expected_run,
            f"{path.name} run hash mismatch")
    require(failures, digest(path / "artifacts.sha256") == expected_index,
            f"{path.name} index hash mismatch")
    require(failures, digest(path / "runner.py") == expected_runner,
            f"{path.name} runner hash mismatch")
    indexed: set[str] = set()
    for line in (path / "artifacts.sha256").read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"malformed {path.name} artifact index line")
            continue
        wanted, relative = parts
        require(failures, re.fullmatch(r"[0-9a-f]{64}", wanted) is not None,
                f"invalid artifact hash: {path.name}/{relative}")
        artifact = (path / relative).resolve()
        try:
            artifact.relative_to(path.resolve())
        except ValueError:
            failures.append(f"artifact escapes bundle: {path.name}/{relative}")
            continue
        require(failures, artifact.is_file() and digest(artifact) == wanted,
                f"artifact hash mismatch: {path.name}/{relative}")
        indexed.add(relative)
    files = {
        str(item.relative_to(path)) for item in path.rglob("*") if item.is_file()
    } - {"artifacts.sha256"}
    require(failures, indexed == files and len(indexed) == expected_files,
            f"{path.name} index does not exactly cover its bundle")


def main() -> int:
    failures: list[str] = []
    evidence = load(EVIDENCE)
    exact(evidence, {
        "schema": "leshy.product_survey_active_cancel_acceptance.v1",
        "status": "pass_progress_not_stage_gate",
        "trust_status": "unsigned_local_result",
        "runner_gate_eligible": True,
        "stage_gate_eligible": False,
        "release_gate_eligible": False,
        "evidence_ids": ["E-BUILD-063", "E-AUTO-026", "E-HIL-086"],
        "board": "board-01", "profile": "esp32-div-v2-n16",
    }, "", failures)
    exact(evidence.get("media", {}), {
        "cid": CID, "product_root": "/leshy/sessions/v1",
        "disposable_test_card": True,
    }, "media.", failures)

    candidate = evidence.get("candidate", {})
    exact(candidate, {
        "version": "0.62.0-input-probe-resilience-measure",
        "firmware_sha256":
            "9fd32690880be8a056a0f720b15061d1f96d6eb84876dd2382e4026c222ee0b1",
        "factory_sha256":
            "d6db0c4d104ee4521652755bccac1d638b37e930f66ac0b047d063ff7a55ec4d",
        "app_elf_sha256":
            "469d90263a0fb6dd4d0509577d0209c5db250353e4d4c50b93069c5d8e9ae4f5",
        "map_sha256":
            "8ce4dd29cf41daa60795ddf85c3bcf84bf397800ea593d172c5c1ec53e662b01",
        "linked_flash_bytes": 1111564, "static_ram_bytes": 128816,
        "app_image_bytes": 1111712, "factory_image_bytes": 1177248,
        "rtc_noinit_bytes": 20, "flashed_and_verified": True,
        "host_tests_passed": True, "firmware_build_passed": True,
    }, "candidate.", failures)

    retained = evidence.get("retained", {})
    exact(retained, {
        "bundle_path": "tests/hil/evidence/board-01-product-survey-active-cancel-0.62",
        "run_sha256":
            "e46e656a4543c52e578788762dd6de4e20e8f5906f1f8dd1d92551d9dce156f5",
        "artifact_index_sha256":
            "a19c8416fda67eb6c9bda09c68004d8cfaa73c97c43af1c38c6e175520af8fa4",
        "runner_source_sha256":
            "b436e4f33f0d78ff93753b4179bd478a71a89d7c23d559f61c0742485da9ae97",
        "runner_dependency_sha256":
            "e44c3e9ec5ae69466450d93b523ddea192004fde6bf9c3fb8360f30e4f8c345b",
        "runner_source_binding":
            "entrypoint_runtime_emitted_and_retained_with_exact_product_dependency",
    }, "retained.", failures)
    check_bundle(BUNDLE, retained.get("run_sha256", ""),
                 retained.get("artifact_index_sha256", ""),
                 retained.get("runner_source_sha256", ""), 12, failures)
    require(failures,
            digest(BUNDLE / "product_survey_runner.py") ==
            retained.get("runner_dependency_sha256"),
            "retained exact product-runner dependency mismatch")
    require(failures,
            (BUNDLE / "firmware.bin").stat().st_size == candidate.get("app_image_bytes") and
            digest(BUNDLE / "firmware.bin") == candidate.get("firmware_sha256") and
            app_elf_sha256(BUNDLE / "firmware.bin") == candidate.get("app_elf_sha256"),
            "retained exact 0.62 candidate mismatch")

    negative = evidence.get("retained_failed_run", {})
    exact(negative, {
        "bundle_path":
            "tests/hil/evidence/board-01-product-survey-active-cancel-0.61-failed",
        "candidate_version": "0.61.0-product-survey-active-cancel-measure",
        "candidate_firmware_sha256":
            "58ed4ba26be93e3daa0a8e86eb21fac9a4851610a99ace53c0223236d9dee002",
        "candidate_app_elf_sha256":
            "36f943611fe4bc0fdcd46fa931286048324fff5dcb3404c2203bf37c1d6367f4",
        "run_sha256":
            "b88ea56f1465cbbf38ef0871d4b76a398e0987cfd67de4a98ebe5cc8e92b840f",
        "artifact_index_sha256":
            "2e34c595875f662301e8adcf0234ca63d57d1d25c2b682f2717af5d95b3cea2c",
        "runner_source_sha256": retained.get("runner_source_sha256"),
        "passed": False, "gate_eligible": False,
        "failure": "boot.input_detected: False != True",
        "survey_cancel_path_itself_completed": True,
        "input_probe_implementation": "single_attempt",
    }, "retained_failed_run.", failures)
    check_bundle(FAILED, negative.get("run_sha256", ""),
                 negative.get("artifact_index_sha256", ""),
                 negative.get("runner_source_sha256", ""), 11, failures)
    failed_run = load(FAILED / "run.json")
    require(failures,
            failed_run.get("passed") is False and
            failed_run.get("gate_eligible") is False and
            failed_run.get("failures") == ["boot.input_detected: False != True"] and
            failed_run.get("boot_before", {}).get("ready", {}).get("input_detected") is True and
            failed_run.get("boot_after", {}).get("ready", {}).get("input_detected") is False and
            failed_run.get("cancelled", {}).get("survey_product_status") == "cancelled" and
            failed_run.get("cancelled", {}).get("lease_mask") == 0,
            "retained 0.61 negative run no longer proves the exact failure")

    source = (ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp").read_text(
        encoding="utf-8"
    )
    report = (ROOT / "firmware/leshy1/src/services/diagnostics/BootReport.cpp").read_text(
        encoding="utf-8"
    )
    for marker in (
        "kInputProbeMaxAttempts = 8", "kInputProbeRetryDelayMs = 5",
        "probeInputAtBoot(&lastInputRaw, &bootMetrics.inputProbeAttempts)",
        "setProductSurveyScanActive(true);",
        "productSurveyRuntime.cancelRequestedDuringScan = scanWasActive;",
        "BoardWifiPassiveScanner::cancelActiveScan();",
    ):
        require(failures, marker in source, f"0.62 source marker missing: {marker}")
    for marker in ("input_probe_attempts", "input_probe_transient_retries"):
        require(failures, marker in report, f"0.62 boot report marker missing: {marker}")

    run = load(BUNDLE / "run.json")
    require(failures,
            run.get("schema") == "leshy.product_survey_cancel_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and
            run.get("runner_source_sha256") == retained.get("runner_source_sha256") and
            run.get("candidate") == {
                "firmware_sha256": candidate.get("firmware_sha256"),
                "app_elf_sha256": candidate.get("app_elf_sha256"),
                "version": candidate.get("version"), "flashed": True,
            } and run.get("expected_cid") == CID,
            "0.62 runner result/identity mismatch")

    for name in ("boot_before", "boot_after"):
        ready = run.get(name, {}).get("ready", {})
        exact(ready, {
            "version": candidate.get("version"),
            "app_elf_sha256": candidate.get("app_elf_sha256"),
            "profile": "esp32-div-v2-n16",
            "heap_total": 272688, "heap_free": 208912,
            "heap_min_free": 188720, "buzzer_inactive": True,
            "input_detected": True, "input_probe_attempts": 1,
            "input_probe_transient_retries": 0,
        }, f"{name}.ready.", failures)
        recovery = run.get(name, {}).get("recovery", {})
        exact(recovery, {
            "status": "admitted", "expected_fingerprint": CID,
            "observed_fingerprint": CID, "generation": 68,
            "observations": 25, "attempts": 1, "transient_retries": 0,
            "timeout_restarts": 0, "mounted_read_only": True,
            "read_only_guaranteed": True, "catalog_admitted": True,
            "cleanup_complete": True, "blocked_write_attempts": 0,
            "physical_write_calls": 0, "owned_after": 0,
        }, f"{name}.recovery.", failures)

    active = run.get("active_scan", {})
    exact(active, {
        "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
        "survey_product_status": "running",
        "survey_product_source_active": True,
        "survey_product_scan_active": True,
        "survey_product_cancel_requested_during_scan": False,
        "survey_product_backend_open": True,
        "survey_product_cleanup_complete": False,
        "survey_product_start_action_us": 12,
    }, "active_scan.", failures)
    cancel = run.get("cancel_ack", {})
    exact(cancel, {
        "page": "survey", "runtime_owner": "survey", "lease_mask": 15,
        "survey_product_status": "cancelling",
        "survey_product_source_active": True,
        "survey_product_scan_active": False,
        "survey_product_cancel_requested_during_scan": True,
        "survey_product_backend_open": True,
        "survey_product_cleanup_complete": False,
        "survey_product_stop_action_us": 9,
    }, "cancel_ack.", failures)
    terminal = run.get("cancelled", {})
    exact(terminal, {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
        "survey_product_status": "cancelled",
        "survey_product_source_active": False,
        "survey_product_scan_active": False,
        "survey_product_cancel_requested_during_scan": True,
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
    }, "cancelled.", failures)
    require(failures, run.get("cancel_ack_ms") == 86.76170837134123,
            "0.62 cancel acknowledgement changed")
    require(failures,
            run.get("cleanup_before_reboot", {}).get("complete") is True and
            run.get("cleanup_final", {}).get("complete") is True,
            "0.62 terminal cleanup is incomplete")
    require(failures, set(run.get("captures", {})) == {"setup", "cancelled"},
            "0.62 exact TFT capture set changed")

    summary = evidence.get("run", {})
    require(failures,
            summary.get("generation_before") == 68 and
            summary.get("generation_after") == 68 and
            summary.get("observations_before") == 25 and
            summary.get("observations_after") == 25 and
            summary.get("heap_drift_bytes") == 0 and
            summary.get("final_owner") == "none" and
            summary.get("final_lease_mask") == 0,
            "0.62 evidence summary no longer matches retained run")

    docs = "\n".join(
        path.read_text(encoding="utf-8") for path in (
            ROOT / "docs/v1/STATUS.md", ROOT / "docs/v1/STATUS.ru.md",
            ROOT / "docs/v1/TRACEABILITY.md", ROOT / "docs/v1/TRACEABILITY.ru.md",
            ROOT / "docs/v1/RESOURCE_BUDGETS.md", ROOT / "docs/v1/RESOURCE_BUDGETS.ru.md",
        )
    )
    for marker in ("E-BUILD-063", "E-AUTO-026", "E-HIL-086", "0.62"):
        require(failures, marker in docs, f"0.62 docs marker missing: {marker}")

    if failures:
        print("Product Survey active-cancel acceptance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Product Survey active-cancel evidence passed: 0.61 input-probe failure "
        "retained; exact 0.62 cancels during active scan in 86.762 ms with "
        "generation 68/25 unchanged, bounded input boot probe, zero SD writes, "
        "and final lease 0; S3 gate remains open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
