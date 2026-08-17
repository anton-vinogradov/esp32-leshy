#!/usr/bin/env python3
"""Fail closed unless retained combined release-HIL evidence is complete."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests/hil/evidence/board-01-release-hil-0.45.json"
SUITE = ROOT / "tests/hil/device-smoke.v1.json"


def main() -> int:
    errors: list[str] = []
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    if value.get("schema") != "leshy.release_hil_acceptance.v1":
        errors.append("unexpected combined release-HIL evidence schema")
    if value.get("status") != "pass":
        errors.append("combined release-HIL evidence is not a pass")
    if value.get("trust_status") != "unsigned_local_result":
        errors.append("retained local trust status changed")
    if value.get("firmware_version") != "0.45.0-product-survey-measure":
        errors.append("combined evidence firmware version changed")
    for field in ("firmware_sha256", "app_elf_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))):
            errors.append(f"invalid candidate identity: {field}")

    combined = value.get("combined", {})
    for field, wanted in {
        "script": "tools/run_1x_release_hil.py",
        "verifier": "tools/verify_1x_release_hil_bundle.py",
        "passed": True, "local_gate_eligible": True,
        "development_verified": True, "release_eligible": False,
        "files": 64,
    }.items():
        if combined.get(field) != wanted:
            errors.append(f"combined mismatch: {field}")
    for field in ("run_sha256", "artifact_index_sha256", "archive_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(combined.get(field, ""))):
            errors.append(f"invalid combined digest: {field}")

    product = value.get("product", {})
    if not re.fullmatch(r"[0-9a-f]{32}", str(product.get("run_id", ""))):
        errors.append("invalid product run ID")
    for field in ("run_sha256", "artifact_index_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(product.get(field, ""))):
            errors.append(f"invalid product digest: {field}")
    for field, wanted in {
        "generation_before": 4, "generation_after": 5,
        "observations": 20, "scan_reported": 20, "scan_read": 20,
        "scan_accepted": 20, "scan_forwarded": 20,
        "scan_rejected": 0, "scan_dropped": 0, "pipeline_dropped": 0,
        "queue_high_water": 20, "captures": 4,
        "cleanup_complete": True, "final_lease_mask": 0,
    }.items():
        if product.get(field) != wanted:
            errors.append(f"product mismatch: {field}")
    if (product.get("generation_after") != product.get("generation_before", 0) + 1 or
            product.get("cached_free_bytes", 0) < 64 * 1024 + 1024 * 1024 or
            product.get("cached_free_bytes", 0) > product.get("capacity_bytes", 0)):
        errors.append("product generation or bounded-space evidence is invalid")

    generic = value.get("generic", {})
    for field, wanted in {
        "suite": suite.get("id"), "revision": suite.get("revision"),
        "candidate_flashed": True, "passed": True,
        "local_gate_eligible": True, "captures": 10,
        "visual_mismatch_pixels": 0, "buzzer_inactive": True,
        "final_lease_mask": 0,
    }.items():
        if generic.get(field) != wanted:
            errors.append(f"generic mismatch: {field}")
    if not re.fullmatch(r"[0-9a-f]{32}", str(generic.get("run_id", ""))):
        errors.append("invalid generic run ID")
    for field in ("run_sha256", "artifact_index_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(generic.get(field, ""))):
            errors.append(f"invalid generic digest: {field}")

    isolation = value.get("state_isolation", {})
    for field, wanted in {
        "unenroll_status": "valid", "nvs_key_removed": True,
        "sd_accessed": False, "sd_data_untouched": True,
        "unenroll_physical_write_calls": 0, "reenroll_status": "valid",
        "fingerprint_matched": True, "read_only_guaranteed": True,
        "catalog_admitted": True, "generation": 5, "observations": 20,
        "enrollment_saved": True, "blocked_write_attempts": 0,
        "reenroll_physical_write_calls": 0, "cleanup_complete": True,
        "final_boot_status": "admitted", "final_runtime_owner": "none",
        "final_lease_mask": 0, "final_library_persistent": True,
        "final_library_simulated": False,
    }.items():
        if isolation.get(field) != wanted:
            errors.append(f"state isolation mismatch: {field}")

    visual = value.get("visual", {})
    if set(visual) != {
        "setup_png_sha256", "running_png_sha256",
        "committed_png_sha256", "export_png_sha256",
    } or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(digest))
        for digest in visual.values()
    ):
        errors.append("product visual digest set is incomplete")

    github = value.get("github_native", {})
    for field, wanted in {
        "workflow_run": 31987498533,
        "commit": "b878b956cb0d2a7b17e86ef0354a5ad0d77d2ee4",
        "status": "pass", "candidate_attestation_verified": True,
        "evidence_attestation_verified": True,
        "promotion_proof_verified": True, "build_seconds": 152,
        "physical_hil_seconds": 99, "promotion_proof_seconds": 30,
        "ephemeral_runners_after": 0, "release_created": False,
        "operator_result": "VALIDATION PASSED — NON-PUBLISHABLE VERSION",
    }.items():
        if github.get(field) != wanted:
            errors.append(f"GitHub-native mismatch: {field}")
    if github.get("workflow_url") != (
        "https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31987498533"
    ):
        errors.append("GitHub-native workflow URL changed")
    for section_name, fields in {
        "candidate": ("firmware_sha256", "factory_sha256", "elf_sha256", "map_sha256"),
        "evidence": ("archive_sha256", "run_sha256", "artifact_index_sha256"),
        "product": ("run_sha256", "artifact_index_sha256"),
        "generic": ("run_sha256", "artifact_index_sha256"),
    }.items():
        section = github.get(section_name, {})
        for field in fields:
            if not re.fullmatch(r"[0-9a-f]{64}", str(section.get(field, ""))):
                errors.append(f"invalid GitHub-native digest: {section_name}.{field}")
    github_product = github.get("product", {})
    for field, wanted in {
        "generation_before": 5, "generation_after": 6,
        "observations": 16, "scan_reported": 16, "scan_read": 16,
        "scan_accepted": 16, "scan_forwarded": 16,
        "scan_rejected": 0, "scan_dropped": 0, "pipeline_dropped": 0,
        "cleanup_complete": True, "final_lease_mask": 0,
    }.items():
        if github_product.get(field) != wanted:
            errors.append(f"GitHub-native product mismatch: {field}")
    github_generic = github.get("generic", {})
    for field, wanted in {
        "suite": suite.get("id"), "revision": suite.get("revision"),
        "captures": 10, "visual_mismatch_pixels": 0,
        "final_lease_mask": 0,
    }.items():
        if github_generic.get(field) != wanted:
            errors.append(f"GitHub-native generic mismatch: {field}")
    for section_name in ("product", "generic"):
        if not re.fullmatch(
            r"[0-9a-f]{32}", str(github.get(section_name, {}).get("run_id", ""))
        ):
            errors.append(f"invalid GitHub-native run ID: {section_name}")
    restored = github.get("restored_state", {})
    for field, wanted in {
        "unenroll_sd_accessed": False, "unenroll_physical_write_calls": 0,
        "reenroll_read_only_guaranteed": True,
        "reenroll_physical_write_calls": 0,
        "final_boot_status": "admitted", "generation": 6,
        "observations": 16, "runtime_owner": "none", "lease_mask": 0,
        "library_persistent": True, "library_simulated": False,
    }.items():
        if restored.get(field) != wanted:
            errors.append(f"GitHub-native restored state mismatch: {field}")
    if github.get("evidence", {}).get("independent_verifier_passed") is not True:
        errors.append("GitHub-native independent verifier did not pass")

    if errors:
        for error in errors:
            print(f"release HIL acceptance failed: {error}")
        return 1
    print(
        "release HIL acceptance passed: local + GitHub-native combined HIL, "
        "generic v6, read-only enrollment restored"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
