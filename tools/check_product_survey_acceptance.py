#!/usr/bin/env python3
"""Fail closed if retained real product-Survey acceptance is incomplete."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests" / "hil" / "evidence" / "board-01-product-survey-0.45.json"
ACCEPTED_VERSION = "0.45.0-product-survey-measure"
ACCEPTED_CID = "FE343253440000002000000055019CB7"


def main() -> int:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    errors: list[str] = []
    if value.get("schema") != "leshy.product_survey_acceptance.v1":
        errors.append("unexpected evidence schema")
    if value.get("status") != "pass":
        errors.append("retained evidence is not a pass")
    if value.get("firmware_version") != ACCEPTED_VERSION:
        errors.append("evidence is not bound to accepted 0.45")
    if value.get("media", {}).get("fingerprint") != ACCEPTED_CID:
        errors.append("media fingerprint changed")

    digests = [value.get("firmware_sha256"), value.get("app_elf_sha256")]
    runner = value.get("runner", {})
    digests.extend((runner.get("run_sha256"), runner.get("artifact_index_sha256")))
    visual = value.get("visual", {})
    digests.extend(visual.get(field) for field in (
        "setup_png_sha256", "running_png_sha256",
        "committed_png_sha256", "export_png_sha256",
    ))
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(digest)) for digest in digests):
        errors.append("candidate/runner/visual digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{32}", str(runner.get("run_id", ""))):
        errors.append("runner ID is invalid")
    if not runner.get("candidate_flashed") or not runner.get("passed"):
        errors.append("exact-candidate runner did not pass")

    isolation = value.get("state_isolation", {})
    unenroll = isolation.get("unenroll", {})
    if (unenroll.get("status") != "valid" or
            unenroll.get("nvs_key_removed") is not True or
            unenroll.get("sd_accessed") is not False or
            unenroll.get("sd_data_untouched") is not True or
            unenroll.get("physical_write_calls") != 0):
        errors.append("generic HIL was not isolated by safe unenrollment")
    generic = isolation.get("generic_hil", {})
    for field, wanted in {
        "suite": "device-smoke", "revision": 6,
        "candidate_flashed": True, "passed": True,
        "local_gate_eligible": True, "visual_captures": 10,
        "visual_mismatch_pixels": 0, "simulated_generation": 2,
        "simulated_observations": 3, "final_lease_mask": 0,
    }.items():
        if generic.get(field) != wanted:
            errors.append(f"generic HIL mismatch: {field}")
    if not re.fullmatch(r"[0-9a-f]{32}", str(generic.get("run_id", ""))):
        errors.append("generic HIL run ID is invalid")
    for field in ("run_sha256", "artifact_index_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(generic.get(field, ""))):
            errors.append(f"generic HIL digest is invalid: {field}")
    reenroll = isolation.get("read_only_reenroll", {})
    final_boot = isolation.get("final_enrolled_boot", {})
    for section_name, section in (("reenroll", reenroll), ("final_boot", final_boot)):
        for field, wanted in {
            "status": "valid" if section_name == "reenroll" else "admitted",
            "generation": 3, "observations": 15,
            "blocked_write_attempts": 0, "sd_physical_write_calls": 0,
            "owned_after": 0, "cleanup_complete": True,
        }.items():
            if section.get(field) != wanted:
                errors.append(f"{section_name} mismatch: {field}")
    if (reenroll.get("enrollment_saved") is not True or
            final_boot.get("final_lease_mask") != 0):
        errors.append("device was not returned to enrolled idle state")

    media = value.get("media", {})
    if media.get("full_fat_scan") is not False:
        errors.append("product admission used an unbounded FAT scan")
    if media.get("cached_free_bytes", 0) < (
            media.get("commit_byte_limit", 0) + media.get("reserve_bytes", 0)):
        errors.append("bounded free-space evidence is insufficient")

    before = value.get("boot_before", {})
    after = value.get("boot_after", {})
    for name, boot in (("before", before), ("after", after)):
        expected = {
            "status": "admitted", "read_only_guaranteed": True,
            "blocked_write_attempts": 0, "sd_physical_write_calls": 0,
            "owned_during": 12, "owned_after": 0, "cleanup_complete": True,
        }
        for field, wanted in expected.items():
            if boot.get(field) != wanted:
                errors.append(f"boot {name} mismatch: {field}")

    survey = value.get("survey", {})
    expected_survey = {
        "explicit_ui_start": True, "simulated": False, "persistent": True,
        "passive_only": True, "application_connect_calls": 0,
        "application_raw_tx_calls": 0, "lease_mask": 15,
        "store_status": "permitted", "admission_status": "permitted",
        "scan_status": "valid", "scan_rejected": 0, "scan_dropped": 0,
        "pipeline_dropped": 0, "wifi_event_errors": 0,
    }
    for field, wanted in expected_survey.items():
        if survey.get(field) != wanted:
            errors.append(f"Survey mismatch: {field}")
    accepted = survey.get("scan_accepted")
    if not isinstance(accepted, int) or accepted < 1 or accepted != survey.get("pipeline_forwarded"):
        errors.append("Survey observation accounting is incomplete")

    commit = value.get("commit", {})
    if commit.get("status") != "committed":
        errors.append("commit did not complete")
    if commit.get("generation_after") != commit.get("generation_before", 0) + 1:
        errors.append("commit did not publish exactly the next generation")
    if (after.get("generation") != commit.get("generation_after") or
            after.get("observations") != commit.get("observations") or
            after.get("integrity") != "valid"):
        errors.append("cold reboot did not recover the exact committed Session")
    for field, wanted in {
        "backend_open_after": False, "cleanup_complete": True,
        "lease_during_result": 15, "lease_after_back": 0,
    }.items():
        if commit.get(field) != wanted:
            errors.append(f"commit cleanup mismatch: {field}")

    library = value.get("persistent_library", {})
    for field, wanted in {
        "status": "valid", "storage_backend": "persistent_media",
        "persistent": True, "simulated": False, "radio_touched": False,
        "session_id": "product-wifi-live", "generation": 3,
        "observations": 15, "wifi_observations": 15,
        "library_lease_mask": 5, "final_lease_mask": 0,
    }.items():
        if library.get(field) != wanted:
            errors.append(f"Library mismatch: {field}")

    if (visual.get("captures") != 4 or visual.get("inspected") is not True or
            visual.get("viewport_rows") != 3 or
            visual.get("overflow_observed") is not False):
        errors.append("visual acceptance is incomplete")
    abort = value.get("abort_probe", {})
    if not abort.get("running_cancelled_without_commit"):
        errors.append("Running cancel was not exercised")
    if (abort.get("generation_before") != abort.get("generation_after") or
            abort.get("backend_open_after") is not False or
            abort.get("cleanup_complete") is not True or
            abort.get("final_lease_mask") != 0):
        errors.append("Running cancel mutated data or leaked resources")

    if errors:
        for error in errors:
            print(f"product Survey acceptance failed: {error}")
        return 1
    print("product Survey acceptance passed: real passive 15/15, generation 2->3, reboot/export valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
