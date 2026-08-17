#!/usr/bin/env python3
"""Fail closed if retained product SD boot acceptance is incomplete."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests" / "hil" / "evidence" / "board-01-product-boot-0.44.json"
SUITE = ROOT / "tests" / "hil" / "device-smoke.v1.json"
ACCEPTED_FIRMWARE_VERSION = "0.44.0-sd-readonly-driver-measure"
ACCEPTED_MEDIA_FINGERPRINT = "FE343253440000002000000055019CB7"


def main() -> int:
    errors: list[str] = []
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    if value.get("schema") != "leshy.storage.product_boot_acceptance.v1":
        errors.append("unexpected product-boot evidence schema")
    if value.get("status") != "pass":
        errors.append("product-boot evidence is not a pass")
    if value.get("firmware_version") != ACCEPTED_FIRMWARE_VERSION:
        errors.append("product-boot evidence is not for the accepted firmware")
    if value.get("media", {}).get("fingerprint") != ACCEPTED_MEDIA_FINGERPRINT:
        errors.append("product-boot evidence media fingerprint changed")
    for field in ("firmware_sha256", "app_elf_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))):
            errors.append(f"invalid candidate identity: {field}")

    isolation = value.get("state_isolation", {})
    generic = isolation.get("generic_hil", {})
    if generic.get("suite") != suite.get("id") or generic.get("revision") != suite.get("revision"):
        errors.append("generic HIL evidence is not bound to the current suite")
    if not generic.get("passed") or not generic.get("candidate_flashed"):
        errors.append("generic exact-candidate HIL did not pass")
    if generic.get("visual_captures") != 10 or generic.get("visual_mismatch_pixels") != 0:
        errors.append("generic HIL visual regression is incomplete")
    if generic.get("final_lease_mask") != 0:
        errors.append("generic HIL leaked a resource lease")
    if not isolation.get("nvs_key_removed") or isolation.get("sd_accessed"):
        errors.append("generic HIL state was not safely isolated")
    if not isolation.get("sd_data_untouched"):
        errors.append("unenrollment did not retain SD data")

    for section_name in ("read_only_enrollment", "cold_boot"):
        section = value.get(section_name, {})
        for field in (
            "fingerprint_matched", "mounted_read_only", "read_only_guaranteed",
            "catalog_admitted", "cleanup_complete",
        ):
            if section.get(field) is not True:
                errors.append(f"{section_name} did not prove {field}")
        if section.get("generation") != 1 or section.get("observations") != 17:
            errors.append(f"{section_name} recovered the wrong catalog")
        for field in ("blocked_write_attempts", "sd_physical_write_calls", "owned_after"):
            if section.get(field) != 0:
                errors.append(f"{section_name} has nonzero {field}")
    if value.get("read_only_enrollment", {}).get("enrollment_saved") is not True:
        errors.append("read-only enrollment was not saved")
    cold_boot = value.get("cold_boot", {})
    if cold_boot.get("status") != "admitted" or cold_boot.get("integrity") != "valid":
        errors.append("cold boot did not admit a valid catalog")
    if cold_boot.get("owned_during") != 12:
        errors.append("cold boot did not hold the exact Storage+RadioSpi lease")

    library = value.get("persistent_library", {})
    expected_library = {
        "status": "valid", "storage_backend": "persistent_media",
        "persistent": True, "simulated": False, "radio_touched": False,
        "session_id": "product-wifi-boot", "generation": 1,
        "observations": 17, "wifi_observations": 17,
        "library_lease_mask": 5, "final_lease_mask": 0,
    }
    for field, expected in expected_library.items():
        if library.get(field) != expected:
            errors.append(f"persistent Library mismatch: {field}")

    digest_fields = [
        value.get("state_isolation", {}).get("unenroll_record_sha256"),
        generic.get("run_sha256"), generic.get("artifact_index_sha256"),
        value.get("read_only_enrollment", {}).get("record_sha256"),
        cold_boot.get("raw_sha256"), cold_boot.get("boot_recovery_record_sha256"),
        library.get("export_record_sha256"), library.get("export_ready_trace_sha256"),
        library.get("home_trace_sha256"),
    ]
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(digest)) for digest in digest_fields):
        errors.append("product-boot evidence contains an invalid retained digest")
    if not re.fullmatch(r"[0-9a-f]{32}", str(generic.get("run_id", ""))):
        errors.append("product-boot evidence contains an invalid HIL run ID")

    regression = value.get("bounded_boot_regression", {})
    if not regression.get("failure_observed") or not regression.get("fixed"):
        errors.append("cold-boot FAT-scan regression is not closed")
    if regression.get("static_guard_forbids") != ["freeBytes(", "filesystemCapacityBytes("]:
        errors.append("cold-boot scan regression guard changed")

    if errors:
        for error in errors:
            print(f"product boot acceptance failed: {error}")
        return 1
    print("product boot acceptance passed: generic HIL clean, RO generation 1/17 admitted, zero SD writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
