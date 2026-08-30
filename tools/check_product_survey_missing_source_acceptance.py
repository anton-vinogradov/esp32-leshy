#!/usr/bin/env python3
"""Fail closed unless exact 0.68 missing-source TFT evidence is complete."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-product-survey-missing-source-0.68.json"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
STRINGS = ROOT / "firmware/leshy1/src/ui/UiStrings.def"
PLATFORM = ROOT / "firmware/leshy1/platformio.ini"
RUNNER = ROOT / "tools/run_1x_product_survey_missing_source_hil.py"
RUNNER_TEST = ROOT / "tools/test_product_survey_missing_source_hil_runner.py"
DOCS = (
    ROOT / "docs/v1/STATUS.md",
    ROOT / "docs/v1/STATUS.ru.md",
    ROOT / "docs/v1/STORAGE_HIL.md",
    ROOT / "docs/v1/STORAGE_HIL.ru.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def retained(failures: list[str], relative: object,
             expected_sha: object) -> Path | None:
    if not isinstance(relative, str) or not isinstance(expected_sha, str):
        failures.append("retained path/hash missing")
        return None
    path = ROOT / relative
    require(failures, path.is_file(), f"retained file missing: {relative}")
    if path.is_file():
        require(failures, digest(path) == expected_sha,
                f"retained hash mismatch: {relative}")
    return path if path.is_file() else None


def exact(record: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in expected.items())


def main() -> int:
    failures: list[str] = []
    require(failures, EVIDENCE.is_file(), "acceptance evidence missing")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(failures,
            evidence.get("schema") ==
                "leshy.product_survey_missing_source_acceptance.v1" and
            evidence.get("status") == "pass" and
            evidence.get("gate_eligible") is False,
            "acceptance status mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-BUILD-069", "E-AUTO-032", "E-HIL-092", "E-SURVEY-007"
    ], "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.68.0-missing-source-tft-measure",
        "firmware_sha256":
            "a2703abaff05217084bbf5c1cc31ac40643fc1a006d7b80760cb7fba5b26ae64",
        "factory_sha256":
            "2eaaa12b85a88e2d201e1f5c81d4b863cde0d78b8365a0772171b2a3677f787d",
        "app_elf_sha256":
            "ef98e4f938578507033f58189a102674a34f02fe7fd927a26c6707ceb42632f0",
        "map_sha256":
            "c782efdc3fd4282f994eb3cfd451f059a28a54d45570686d99ee6971d86528d5",
        "linked_flash_bytes": 1114184,
        "static_ram_bytes": 128920,
        "app_image_bytes": 1114592,
        "factory_image_bytes": 1180128,
        "rtc_noinit_bytes": 20,
        "host_tests_passed": True,
        "firmware_build_passed": True,
    }, "exact candidate mismatch")

    physical = evidence.get("physical", {})
    run_path = retained(failures, physical.get("run_path"),
                        physical.get("run_sha256"))
    retained(failures, physical.get("runner_path"),
             physical.get("runner_sha256"))
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path else {}
    require(failures,
            run.get("schema") ==
                "leshy.product_survey_missing_source_hil.run.v1" and
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [],
            "physical run did not pass")
    require(failures, run.get("runner_source_sha256") ==
            physical.get("runner_sha256"), "runner source binding mismatch")
    require(failures, exact(run.get("candidate", {}), {
        "firmware_sha256": candidate.get("firmware_sha256"),
        "app_elf_sha256": candidate.get("app_elf_sha256"),
        "version": candidate.get("version"),
        "flashed": True,
    }), "run candidate mismatch")
    require(failures, run.get("expected_cid") == physical.get("exact_cid"),
            "exact CID mismatch")

    manifest = run_path.parent / "artifacts.sha256" if run_path else None
    require(failures, manifest is not None and manifest.is_file(),
            "artifact manifest missing")
    if manifest is not None and manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected_sha, relative = line.split("  ", 1)
            path = manifest.parent / relative
            require(failures, path.is_file(), f"artifact missing: {relative}")
            if path.is_file():
                require(failures, digest(path) == expected_sha,
                        f"artifact hash mismatch: {relative}")

    injection = run.get("injection", {})
    require(failures, exact(injection, {
        "status": "armed", "one_shot": True, "armed": True,
        "worker_idle": True, "ui_home": True,
        "runtime_owner": "none", "lease_mask": 0,
        "hardware_touched": False, "source_started": False,
        "storage_mounted": False, "storage_written": False,
    }), "one-shot injection contract mismatch")

    unavailable = run.get("source_unavailable", {})
    require(failures, exact(unavailable, {
        "language": "ru", "page": "survey", "runtime_owner": "none",
        "lease_mask": 0, "survey_workflow_state": "setup",
        "survey_running": False, "survey_observations": 0,
        "survey_received": 0, "survey_forwarded": 0, "survey_dropped": 0,
        "survey_product_status": "source_unavailable",
        "survey_product_admission_status": "source_unavailable",
        "survey_product_backend_open": False,
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
        "survey_product_source_start_attempted": False,
        "survey_product_source_failure_injected": True,
        "survey_product_source_injection_armed": False,
        "survey_product_store_open_attempted": False,
        "survey_product_store_bytes_written": 0,
        "survey_product_scan_active": False,
        "survey_product_scan_cycles": 0,
        "survey_scan_status": "not_started",
        "library_generation": 68, "library_persistent": True,
    }), "visible missing-source state mismatch")
    require(failures,
            unavailable.get("survey_product_identity_attempts") == 1 and
            unavailable.get("survey_product_identity_transient_retries") == 0 and
            unavailable.get("survey_product_expected_cid") ==
                physical.get("exact_cid") and
            unavailable.get("survey_product_observed_cid") ==
                physical.get("exact_cid"),
            "missing-source identity mismatch")
    retry = run.get("retry_blocked", {})
    require(failures, exact(retry, {
        "action": "select", "changed": False, "page": "survey",
        "runtime_event": "source_unavailable_waiting_back",
        "runtime_owner": "none", "lease_mask": 0,
        "survey_product_status": "source_unavailable",
    }), "hidden retry was not rejected")
    home = run.get("home", {})
    require(failures, exact(home, {
        "action": "back", "changed": True, "page": "home",
        "runtime_owner": "none", "lease_mask": 0,
        "survey_product_status": "cancelled",
        "survey_product_cleanup_complete": True,
    }), "Back did not reach clean Home")

    before = run.get("boot_before", {}).get("recovery", {})
    after = run.get("boot_after", {}).get("recovery", {})
    for label, record in (("before", before), ("after", after)):
        require(failures, exact(record, {
            "status": "admitted", "generation": 68, "observations": 25,
            "expected_fingerprint": physical.get("exact_cid"),
            "observed_fingerprint": physical.get("exact_cid"),
            "fingerprint_matched": True, "mounted_read_only": True,
            "read_only_guaranteed": True, "catalog_admitted": True,
            "blocked_write_attempts": 0, "physical_write_calls": 0,
            "cleanup_complete": True, "owned_after": 0,
        }), f"read-only recovery mismatch: {label}")
    require(failures,
            run.get("cleanup_before_reboot", {}).get("complete") is True and
            run.get("cleanup_final", {}).get("complete") is True,
            "terminal cleanup missing")

    capture_record = run.get("captures", {}).get("source-unavailable", {})
    require(failures,
            capture_record.get("png_sha256") ==
                physical.get("source_unavailable_png_sha256") and
            capture_record.get("rgb565_sha256") ==
                physical.get("source_unavailable_rgb565_sha256") and
            capture_record.get("frame_begin", {}).get("width") == 240 and
            capture_record.get("frame_begin", {}).get("height") == 320 and
            capture_record.get("frame_begin", {}).get("bytes") == 153600,
            "real-TFT capture mismatch")
    require(failures, physical == {
        "run_path": "tests/hil/evidence/board-01-product-survey-missing-source-0.68/run.json",
        "run_sha256": "10ac2ad9d7bcddac060547aa0b6d883493da544bffd47d23a5d9cc702860ee13",
        "runner_path": "tools/run_1x_product_survey_missing_source_hil.py",
        "runner_sha256": "cab0b6d30507dd1ab0afbf8973667eb28752f6ddc40e1f8fb7ba261ec5adf968",
        "exact_cid": "FE343253440000002000000055019CB7",
        "language": "ru",
        "source_unavailable_png_sha256": "2b129dc3a27537360a0b96c0ab7dc63e9c8add28364723429be65fe8647a9a00",
        "source_unavailable_rgb565_sha256": "3ced06f29306efbc7aa470f990e661ab0a9692474179f0d766cd8c992f8f50e5",
        "frame_width": 240, "frame_height": 320,
        "start_action_us": 14, "identity_attempts": 1,
        "identity_transient_retries": 0,
        "source_failure_injected": True,
        "source_start_attempted": False, "source_active": False,
        "scan_cycles": 0, "store_open_attempted": False,
        "store_bytes_written": 0, "session_observations_created": 0,
        "visible_runtime_owner": "none", "visible_lease_mask": 0,
        "cleanup_complete": True, "hidden_retry_blocked": True,
        "back_returns_home": True,
        "prior_generation_before": 68, "prior_generation_after": 68,
        "prior_observations_before": 25, "prior_observations_after": 25,
        "read_only_boot_physical_write_calls_before": 0,
        "read_only_boot_physical_write_calls_after": 0,
        "heap_total": 272584, "heap_free_before": 208168,
        "heap_free_after": 208168, "heap_min_before": 188116,
        "heap_min_after": 188116, "buzzer_inactive": True,
        "final_owner": "none", "final_lease_mask": 0,
    }, "physical acceptance summary mismatch")

    entry = ENTRY.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")
    platform = PLATFORM.read_text(encoding="utf-8")
    for marker in (
        "survey.product.test-source-unavailable once|clear",
        "consumeProductSurveySourceUnavailableInjection()",
        "productSurveySourceUnavailableVisible()",
        "report.sourceStartAttempted = false",
        "productSurveyRuntime.storeOpenAttempted = true;",
        "releaseProductSurveyAfterTerminal(event.report.status, !keepVisible)",
        "source_unavailable_waiting_back",
    ):
        require(failures, marker in entry, f"firmware marker missing: {marker}")
    source_failure = entry.find("report.sourceFailureInjected =")
    policy_only = entry.find(
        "surveyStoreRouter.bind(ramSessionStore)", source_failure)
    source_boundary = entry[source_failure:policy_only]
    require(failures,
            "if (report.sourceFailureInjected)" in source_boundary and
            "report.sourceStartAttempted = false" in source_boundary and
            "authorizeProductSurvey" in source_boundary and
            "return report;" in source_boundary and
            "openExistingWritable" not in source_boundary,
            "source failure is not ordered before policy-only admission")
    for marker in (
        "LESHY_UI_TEXT(SurveyUnavailable,",
        "LESHY_UI_TEXT(SourceUnavailableReason,",
        "LESHY_UI_TEXT(NoSessionCreated,",
        "LESHY_UI_TEXT(PriorLibraryPreserved,",
        "LESHY_UI_TEXT(BackNoRetry,",
    ):
        require(failures, marker in strings, f"UI text missing: {marker}")
    current_version = re.search(
        r'LESHY1_VERSION=\\"(\d+)\.(\d+)\.[^\\"]+\\"', platform
    )
    require(failures,
            current_version is not None and
            (int(current_version.group(1)), int(current_version.group(2))) >=
                (0, 68),
            "current baseline predates accepted 0.68 missing-source path")
    try:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
        ast.parse(RUNNER_TEST.read_text(encoding="utf-8"))
    except SyntaxError as error:
        failures.append(f"runner syntax error: {error}")
    for doc in DOCS:
        source = doc.read_text(encoding="utf-8")
        require(failures, "0.68" in source and "E-HIL-092" in source,
                f"documentation marker missing: {doc.name}")

    scope = evidence.get("scope", {})
    require(failures,
            scope.get("s3_criterion_9_missing_source") == "accepted" and
            scope.get("s3") == "in_progress" and
            scope.get("release_gate_eligible") is False and
            scope.get("remaining") == [
                "physical_power_cut", "littlefs_parity",
                "independent_demo_goldens", "reproducible_demo_s3"
            ], "scope/promotion mismatch")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Product Survey missing-source acceptance passed: visible RU TFT, "
          "zero source/store start, zero lease, generation 68/25 preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
