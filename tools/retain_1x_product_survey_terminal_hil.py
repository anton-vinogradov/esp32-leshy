#!/usr/bin/env python3
"""Validate and retain privacy-minimal Product Survey terminal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from verify_1x_product_survey_bundle import verify_product_bundle


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0-dev.276"
CID = "FE343253440000002000000055019CB7"
SOURCE_COMMIT = "6b5d27b2253bd7b335bab8754379a5ce51a0a5d2"
FIRMWARE_SHA256 = "e98bf5e4825c438ec5629ffd05ddf58168552a42fef3d40969aa0b9c1206cae9"
APP_ELF_SHA256 = "ae9782374b0a9b17da9e8d7a52c4ed86d9a71b74c10962660c79125d0e561dbd"
RAW_RUN_SHA256 = "898f8e5a25ef74534d69e25104f3f9a0363763fdce874886006ded6992fafb7a"
ARTIFACT_INDEX_SHA256 = "e66e443ad4060a02e3b8585285939f8f6fbc3351e861686ce951e67ad11d1aa4"
RAW_RUNNER_SHA256 = "6d10cbec20d7774615bd050d09532de3d308854169592de124f92679f767651d"
CORRECTED_RUNNER_SHA256 = "4cf6028f9e33e5934516554e90445341be17c719ba523c1998406048ced0431c"
VERIFIER_SHA256 = "1686f6890b4b2a5512208fb2ccc8203c5b0d9ae225e6870863e1e72db07f5a59"
RUNNER_TEST_SHA256 = "5c6a70c4ee25d0403cb268e87fc5a76afc5f65d571884d7524c3fcac0e2ccdad"
PRECURSOR_RUN_SHA256 = [
    "523288ad9f7844777ab9cb4d0a14d8b89df97d13becaa4c7b72b3eefc664a66a",
    "ba2d20bcf7c08c6659b4d9ffaed29c87ce6ac6eeef112c4888dd8f58c6f7f2a2",
]
EVIDENCE_IDS = [
    "E-BUILD-193", "E-AUTO-168", "E-HIL-206", "E-STORAGE-034",
    "E-SURVEY-018", "E-UX-063", "RB-M204",
]
CORRECTED_FAILURE = (
    "library_export.session.id: 'field-visit-live' != 'product-passive-live'"
)
SCREEN_SHA256 = {
    "committed": {
        "png_sha256": "0022937dbf7c92432ae8d5ce0379228da0a25afe1d4b052f2477db822f479905",
        "rgb565_sha256": "756d0d0fe8dd45ac8c6d245253c4c3bacc472de9f874304c578a324874edbee7",
    },
    "export": {
        "png_sha256": "0c31c83a19c11bb58444080a290a085e3ad8a43e171e22c94a92c70b77608b88",
        "rgb565_sha256": "7905f0ad463e5df74e2945c43726301859db8f5206fe24727e84c3d73a1ad30f",
    },
    "paused": {
        "png_sha256": "aae84e00e951d42deb0658422a2ca20315b939505b266bca19e45673752d3c4c",
        "rgb565_sha256": "63d9e5a137f3922c30531c9c5382a63ec982161acd2e23685ea6959bf6f075bb",
    },
    "setup": {
        "png_sha256": "85d3082ae0c9fc18ff6611c26c5599ff07e7010ea3d09e00283bb31059104b39",
        "rgb565_sha256": "6a1ff22c8eb750974490333685e2f6e5081c160d3a3081c9cd098a9f09f5b0b3",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(record: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, value in expected.items():
        require(record.get(key) == value,
                f"{label}.{key}: {record.get(key)!r} != {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    require(source.is_dir() and not source.is_symlink(),
            "regular source directory required")
    require(not destination.exists(), "destination must not exist")
    run_path = source / "run.json"
    index_path = source / "artifacts.sha256"
    candidate = source / "firmware.bin"
    require(digest(run_path) == RAW_RUN_SHA256, "raw run hash mismatch")
    require(digest(index_path) == ARTIFACT_INDEX_SHA256,
            "artifact index hash mismatch")
    require(digest(candidate) == FIRMWARE_SHA256, "candidate hash mismatch")
    require(digest(ROOT / "tools/run_1x_product_survey_hil.py") ==
            CORRECTED_RUNNER_SHA256, "corrected runner source hash mismatch")
    require(digest(ROOT / "tools/verify_1x_product_survey_bundle.py") ==
            VERIFIER_SHA256, "bundle verifier source hash mismatch")
    require(digest(ROOT / "tools/test_product_survey_hil_runner.py") ==
            RUNNER_TEST_SHA256, "runner test source hash mismatch")

    verification = verify_product_bundle(
        source, candidate, VERSION,
        expected_source_commit=SOURCE_COMMIT,
        allow_corrected_oracle=True,
    )
    exact(verification, {
        "verified": True, "raw_runner_passed": False,
        "corrected_oracle_recheck": True, "failures": [],
        "candidate_sha256": FIRMWARE_SHA256,
        "candidate_app_elf_sha256": APP_ELF_SHA256,
        "expected_cid": CID, "generation": 176, "observations": 51,
    }, "verification")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    exact(run, {
        "schema": "leshy.product_survey_hil.run.v1",
        "passed": False, "gate_eligible": False,
        "failures": [CORRECTED_FAILURE], "expected_cid": CID,
        "runner_source_sha256": RAW_RUNNER_SHA256,
        "release_cycle": True,
    }, "raw")
    exact(run["candidate"], {
        "version": VERSION, "source_commit": SOURCE_COMMIT,
        "firmware_sha256": FIRMWARE_SHA256,
        "app_elf_sha256": APP_ELF_SHA256,
        "flash_mode": "reuse_exact", "flash_requested": False,
        "flashed": False,
    }, "candidate")
    before = run["boot_before"]
    after = run["boot_after"]
    exact(before["ready"], {
        "version": VERSION, "app_elf_sha256": APP_ELF_SHA256,
        "heap_total": 148124, "heap_free": 74828,
        "buzzer_inactive": True, "input_detected": True,
    }, "before.ready")
    exact(after["ready"], {
        "version": VERSION, "app_elf_sha256": APP_ELF_SHA256,
        "heap_total": 148124, "heap_free": 74828,
        "buzzer_inactive": True, "input_detected": True,
    }, "after.ready")
    for label, recovery, generation in (
            ("before", before["recovery"], 175),
            ("after", after["recovery"], 176)):
        exact(recovery, {
            "status": "admitted", "generation": generation,
            "observations": 51, "expected_fingerprint": CID,
            "observed_fingerprint": CID, "fingerprint_matched": True,
            "mounted_read_only": True, "read_only_guaranteed": True,
            "blocked_write_attempts": 0, "physical_write_calls": 0,
            "cleanup_complete": True, "attempts": 1,
            "transient_retries": 0, "timeout_restarts": 0,
        }, f"{label}.recovery")

    cycle = run["running"]
    exact(cycle, {
        "survey_product_status": "paused",
        "survey_product_scan_cycles": 1,
        "survey_product_wifi_scan_cycles": 1,
        "survey_product_ble_scan_cycles": 1,
        "survey_observations": 51, "survey_scan_accepted": 20,
        "survey_ble_scan_accepted": 31, "survey_forwarded": 51,
        "survey_dropped": 0, "survey_scan_dropped": 0,
        "survey_ble_scan_dropped": 0, "survey_queue_depth": 0,
        "survey_product_source_active": False,
        "survey_product_expected_cid": CID,
        "survey_product_observed_cid": CID,
        "survey_product_identity_status": "valid",
        "survey_product_identity_attempts": 1,
        "survey_product_identity_transient_retries": 0,
    }, "cycle")
    exact(run["committed"], {
        "survey_generation": 176, "library_generation": 176,
        "survey_observations": 51, "survey_product_status": "committed",
        "survey_product_cleanup_complete": True,
        "survey_product_source_active": False,
    }, "committed")
    export = run["library_export"]
    exact(export, {
        "status": "valid", "generation": 176, "integrity": "valid",
        "persistent": True, "simulated": False,
        "storage_backend": "persistent_media", "radio_touched": False,
    }, "export")
    exact(export["session"], {
        "id": "field-visit-live", "observations": 51, "dropped": 0,
    }, "export.session")
    exact(export["session"]["sources"], {"wifi": 20, "ble": 31},
          "export.sources")
    exact(run["final_state"], {
        "page": "home", "runtime_owner": "none", "lease_mask": 0,
    }, "final")
    require(run["cleanup_before_reboot"].get("complete") is True and
            run["cleanup_final"].get("complete") is True,
            "terminal cleanup is incomplete")
    screen_hashes = {
        label: {
            "png_sha256": frame["png_sha256"],
            "rgb565_sha256": frame["rgb565_sha256"],
        }
        for label, frame in sorted(run["captures"].items())
    }
    require(screen_hashes == SCREEN_SHA256, "TFT capture hashes mismatch")

    summary = {
        "schema": "leshy.product_survey_terminal_hil.acceptance.v1",
        "status": "pass_terminal_commit_and_exact_cold_reopen",
        "board": "board-01", "evidence_ids": EVIDENCE_IDS,
        "exact_cid": CID,
        "candidate": run["candidate"],
        "build": {
            "static_ram_bytes": 230680, "linked_flash_bytes": 3480736,
            "firmware_bytes": 3480896, "factory_bytes": 3546432,
            "firmware_sha256": FIRMWARE_SHA256,
            "app_elf_sha256": APP_ELF_SHA256,
            "ota_slot_free_bytes": 713408,
        },
        "evidence": {
            "run_id": run["run_id"], "raw_run_sha256": RAW_RUN_SHA256,
            "artifact_index_sha256": ARTIFACT_INDEX_SHA256,
            "raw_runner_sha256": RAW_RUNNER_SHA256,
            "corrected_runner_sha256": CORRECTED_RUNNER_SHA256,
            "verifier_sha256": VERIFIER_SHA256,
            "runner_test_sha256": RUNNER_TEST_SHA256,
            "rejected_precursor_run_sha256": PRECURSOR_RUN_SHA256,
            "screenshots": screen_hashes,
        },
        "verified": {
            "raw_runner_passed": False,
            "corrected_oracle_recheck": True,
            "corrected_oracle_failure": CORRECTED_FAILURE,
            "generation_before": 175, "generation_after": 176,
            "observations": 51, "wifi_observations": 20,
            "ble_observations": 31, "forwarded": 51, "drops": 0,
            "scan_cycles": 1, "wifi_scan_cycles": 1,
            "ble_scan_cycles": 1, "queue_depth_final": 0,
            "identity_attempts": 1, "identity_transient_retries": 0,
            "cold_reopen_physical_write_calls": 0,
            "heap_total_before": 148124, "heap_total_after": 148124,
            "heap_free_before": 74828, "heap_free_after": 74828,
            "library_session_id": "field-visit-live",
            "final_page": "home", "final_runtime_owner": "none",
            "final_lease_mask": 0,
        },
        "privacy": {
            "raw_wifi_identifiers_retained": False,
            "raw_ble_addresses_retained": False,
            "raw_export_retained": False,
            "screenshots_retained": False,
            "screenshot_hashes_retained": True,
        },
        "scope": {
            "exact_firmware_reuse": True, "application_flash": False,
            "radio_cycles": 1, "manual_button_presses": 0,
            "host_wifi_control_calls": 0, "clone_touched": False,
            "cardputer_touched": False, "terminal_zero_lease": True,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "retained", "destination": str(destination)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
