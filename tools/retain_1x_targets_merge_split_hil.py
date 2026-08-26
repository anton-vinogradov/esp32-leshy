#!/usr/bin/env python3
"""Retain compact exact 0.165 reversible Targets merge/split evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERIFICATION_SOURCE = "b3a19e2a99b764d33b8de9eac802102a35fdb084"
EXPECTED_FIRMWARE_SOURCE = "19a322c428d6efa52fe18f62041141e0cf6669d8"
EXPECTED_VERSION = "0.165.0-targets-fixture-reopen"
EXPECTED_CID = "FE343253440000002000000055019CB7"
EXPECTED_FIRMWARE_SHA256 = (
    "40af5486e8525998e86aa3c864e0cb0e21e3aace0d3dc40c8dd4eb1923f01d4b"
)
EXPECTED_ELF_SHA256 = (
    "20968cb44e847c7e3b9338c462991b6710a2c23c1654e9b3692879c9f91a81ec"
)
EXPECTED_PARTITIONS_SHA256 = (
    "339bda68b7470d5ad1482d10183514b88971c6f1f20ff87c7e2f3dad96235ba2"
)
DEFAULT_BUNDLE = ROOT / "tests/hil/evidence/board-01-targets-merge-split-0.165"
DEFAULT_SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-merge-split-0.165.json"
FRAME_NAMES = (
    "targets-merge-destination-before",
    "targets-merge-source-list",
    "targets-merge-confirm",
    "targets-merge-saved",
    "targets-merge-cold-reopened",
    "targets-split-confirm",
    "targets-split-saved",
    "targets-split-destination-reopened",
    "targets-split-source-reopened",
)
SOURCE_PATHS = (
    "firmware/leshy1/platformio.ini",
    "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp",
    "tools/check_targets_product_contract.py",
    "tools/check_targets_stack_elf_contract.py",
    "tools/run_1x_targets_merge_split_hil.py",
    "tools/test_targets_merge_split_hil_runner.py",
    "tools/retain_1x_targets_merge_split_hil.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def selected(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: state[key] for key in (
            "selected_target_id", "selected_graph_fingerprint",
            "selected_identity_count", "selected_evidence_count",
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    run_dir = args.run.resolve()
    if args.bundle.exists() or args.summary.exists():
        parser.error("retained destination already exists")
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        candidate = run["candidate"]
        states = run["states"]
        before = states["destination_before"]
        confirm = states["merge_confirm"]
        merged = states["merged"]
        merged_reopened = states["merged_reopened"]
        split = states["split"]
        destination_reopened = states["destination_reopened"]
        source_reopened = states["source_reopened"]
        released = run["released"]
        require(run["schema"] == "leshy.targets_merge_split_hil.run.v1" and
                run["status"] == "pass", "passing merge/split run required")
        require(run["source_commit"] == EXPECTED_VERIFICATION_SOURCE,
                "exact verification source mismatch")
        require(candidate["version"] == EXPECTED_VERSION and
                candidate["firmware_sha256"] == EXPECTED_FIRMWARE_SHA256 and
                candidate["app_elf_sha256"] == EXPECTED_ELF_SHA256 and
                candidate["partitions_sha256"] == EXPECTED_PARTITIONS_SHA256 and
                run["exact_cid"] == EXPECTED_CID,
                "candidate identity mismatch")
        require(digest(run_dir / "firmware.bin") == EXPECTED_FIRMWARE_SHA256,
                "firmware hash mismatch")
        require(run["flash_count"] == 0 and
                run["candidate_installation"] == "reused_exact_flash",
                "exact-flash reuse mismatch")
        require(run["usb"] == {
                    "opened_ports": ["/dev/cu.usbmodem2101"],
                    "cardputer_ports_opened": 0,
                    "port_discovery_calls": 0,
                }, "exclusive original-DIV USB contract mismatch")
        require(before["catalog_count"] == 2 and before["target_count"] == 2 and
                before["target_state_generation"] == 0 and
                before["merge_history_count"] == 0 and
                before["selected_identity_count"] == 1 and
                before["selected_evidence_count"] == 1 and
                before["lease_mask"] == 13,
                "pre-merge graph mismatch")
        require(confirm["view"] == "merge_confirm" and
                confirm["selected_target_id"] == run["destination_id"] and
                confirm["merge_candidate_target_id"] == run["source_id"] and
                confirm["merge_candidate_identity_count"] == 1 and
                confirm["merge_candidate_evidence_count"] == 1 and
                confirm["lease_mask"] == 13,
                "merge ownership preview mismatch")
        require(merged["catalog_count"] == 1 and merged["target_count"] == 1 and
                merged["target_state_generation"] == 1 and
                merged["merge_history_count"] == 1 and
                merged["active_merge_available"] is True and
                merged["active_merge_operation_id"] == run["merge_operation_id"] and
                merged["selected_identity_count"] == 2 and
                merged["selected_evidence_count"] == 2 and
                merged["mutation_merge_status"] == "merged" and
                merged["mutation_generation"] == 1 and
                merged["mutation_persisted"] is True and
                merged["mutation_write_calls"] == 3 and
                merged["mutation_file_syncs"] == 3 and
                merged["mutation_directory_syncs"] == 3,
                "durable merge mismatch")
        require(selected(merged_reopened) == selected(merged) and
                merged_reopened["catalog_count"] == 1 and
                merged_reopened["target_state_generation"] == 1 and
                merged_reopened["merge_history_count"] == 1 and
                merged_reopened["active_merge_available"] is True and
                merged_reopened["lease_mask"] == 13,
                "cold-reopened merged graph mismatch")
        require(split["catalog_count"] == 2 and split["target_count"] == 2 and
                split["target_state_generation"] == 2 and
                split["merge_history_count"] == 1 and
                split["active_merge_available"] is False and
                split["mutation_merge_status"] == "split" and
                split["mutation_generation"] == 2 and
                split["mutation_persisted"] is True and
                split["mutation_write_calls"] == 3 and
                split["mutation_file_syncs"] == 3 and
                split["mutation_directory_syncs"] == 3,
                "durable split mismatch")
        fingerprints = run["graph_fingerprints"]
        require(fingerprints["destination_before"] ==
                fingerprints["destination_after_split"] and
                fingerprints["source_before"] ==
                fingerprints["source_after_split"] and
                selected(destination_reopened) == {
                    "selected_target_id": run["destination_id"],
                    "selected_graph_fingerprint": fingerprints["destination_before"],
                    "selected_identity_count": 1,
                    "selected_evidence_count": 1,
                } and selected(source_reopened) == {
                    "selected_target_id": run["source_id"],
                    "selected_graph_fingerprint": fingerprints["source_before"],
                    "selected_identity_count": 1,
                    "selected_evidence_count": 1,
                } and destination_reopened["target_state_generation"] == 2 and
                source_reopened["target_state_generation"] == 2 and
                destination_reopened["lease_mask"] == 13 and
                source_reopened["lease_mask"] == 13,
                "cold-reopened exact reversal mismatch")
        for reset in (run["resets"]["merged"], run["resets"]["split"]):
            fixture = reset["fixture"]
            require(fixture["continuity_valid"] is True and
                    fixture["mutation_worker_stack_min_free"] >= 8000 and
                    fixture["radio_touched"] is False and
                    fixture["rf_tx_attempts"] == 0 and
                    fixture["sd_accessed"] is False and
                    fixture["product_target_state_touched"] is False,
                    "fixture reset safety/continuity mismatch")
        target = run["disposable_target"]
        require(target["two_read_backup_verified"] is True and
                target["partition_table_two_read_backup_verified"] is True and
                target["restore_verified"] is True and
                target["partition_table_original_restored"] is True and
                target["before_sha256"] == target["after_sha256"] and
                target["partition_table_before_sha256"] ==
                target["partition_table_after_sha256"] and
                target["private_backup_deleted_after_verified_restore"] is True,
                "disposable partition restore mismatch")
        final_fixture = run["final_fixture"]
        recovery = run["final_recovery"]
        final = run["final_cleanup"]["final_state"]
        require(released["status"] == "not_loaded" and
                released["workspace_allocated"] is False and
                released["lease_mask"] == 0 and
                released["heap_free_after_release"] >= 93000,
                "Targets release mismatch")
        require(final_fixture["armed"] is False and
                final_fixture["ota1_restore_required"] is False and
                final_fixture["radio_touched"] is False and
                final_fixture["rf_tx_attempts"] == 0 and
                recovery["status"] == "admitted" and
                recovery["generation"] == 161 and
                recovery["observations"] == 59 and
                recovery["mounted_read_only"] is True and
                recovery["physical_write_calls"] == 0 and
                recovery["owned_after"] == 0 and
                recovery["observed_fingerprint"] == EXPECTED_CID and
                final["page"] == "home" and
                final["runtime_owner"] == "none" and
                final["lease_mask"] == 0 and
                final["library_generation"] == 161,
                "final product restoration mismatch")
        for name in FRAME_NAMES:
            require((run_dir / "frames" / f"{name}.json").is_file() and
                    (run_dir / "frames" / f"{name}.png").is_file(),
                    f"missing retained frame: {name}")
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    args.bundle.mkdir(parents=True)
    shutil.copyfile(run_dir / "run.json", args.bundle / "run.json")
    frames = args.bundle / "frames"
    frames.mkdir()
    for name in FRAME_NAMES:
        for suffix in (".json", ".png"):
            shutil.copyfile(run_dir / "frames" / f"{name}{suffix}",
                            frames / f"{name}{suffix}")
    provenance = {
        "schema": "leshy.targets_merge_split_hil.provenance.v1",
        "firmware_source_commit": EXPECTED_FIRMWARE_SOURCE,
        "verification_source_commit": EXPECTED_VERIFICATION_SOURCE,
        "candidate": candidate,
        "source_sha256": {path: digest(ROOT / path) for path in SOURCE_PATHS},
        "raw_run_sha256": digest(run_dir / "run.json"),
        "raw_artifacts_manifest_sha256": digest(run_dir / "artifacts.sha256"),
    }
    write_json(args.bundle / "provenance.json", provenance)
    manifest = {
        str(path.relative_to(args.bundle)): digest(path)
        for path in sorted(args.bundle.rglob("*")) if path.is_file()
    }
    write_json(args.bundle / "manifest.json", manifest)
    summary = {
        "schema": "leshy.targets_merge_split_hil.summary.v1",
        "status": "pass",
        "evidence_ids": ["E-AUTO-116", "E-HIL-176", "E-UX-052"],
        "board": {"id": "board-01", "rom_mac": "1c:db:d4:87:90:d4"},
        "firmware_source_commit": EXPECTED_FIRMWARE_SOURCE,
        "verification_source_commit": EXPECTED_VERIFICATION_SOURCE,
        "candidate": candidate,
        "exact_cid": EXPECTED_CID,
        "flash_count": run["flash_count"],
        "usb": run["usb"],
        "operation": {
            "id": run["merge_operation_id"],
            "destination_id": run["destination_id"],
            "source_id": run["source_id"],
        },
        "merge": {
            "catalog": [before["catalog_count"], merged["catalog_count"]],
            "generation": [before["target_state_generation"],
                           merged["target_state_generation"]],
            "history": [before["merge_history_count"],
                        merged["merge_history_count"]],
            "identities": merged["selected_identity_count"],
            "evidence": merged["selected_evidence_count"],
            "writes": merged["mutation_write_calls"],
            "file_syncs": merged["mutation_file_syncs"],
            "directory_syncs": merged["mutation_directory_syncs"],
            "cold_reopened": True,
        },
        "split": {
            "catalog": [merged["catalog_count"], split["catalog_count"]],
            "generation": [merged["target_state_generation"],
                           split["target_state_generation"]],
            "history": split["merge_history_count"],
            "destination_fingerprint": fingerprints["destination_after_split"],
            "source_fingerprint": fingerprints["source_after_split"],
            "writes": split["mutation_write_calls"],
            "file_syncs": split["mutation_file_syncs"],
            "directory_syncs": split["mutation_directory_syncs"],
            "cold_reopened": True,
        },
        "reset_stack_min_free": {
            key: run["resets"][key]["fixture"]["mutation_worker_stack_min_free"]
            for key in ("merged", "split")
        },
        "disposable_restore": {
            "ota1_sha256": target["after_sha256"],
            "partition_table_sha256": target["partition_table_after_sha256"],
            "verified": target["restore_verified"],
            "private_backup_deleted":
                target["private_backup_deleted_after_verified_restore"],
        },
        "released_heap": released["heap_free_after_release"],
        "final": {
            "fixture_armed": final_fixture["armed"],
            "generation": recovery["generation"],
            "observations": recovery["observations"],
            "mounted_read_only": recovery["mounted_read_only"],
            "physical_write_calls": recovery["physical_write_calls"],
            "page": final["page"],
            "runtime_owner": final["runtime_owner"],
            "lease_mask": final["lease_mask"],
            "radio_touched": final_fixture["radio_touched"],
            "rf_tx_attempts": final_fixture["rf_tx_attempts"],
        },
        "screens": {
            name: {
                "png": f"frames/{name}.png",
                "png_sha256": digest(frames / f"{name}.png"),
            } for name in FRAME_NAMES
        },
        "raw_run_sha256": provenance["raw_run_sha256"],
        "bundle": str(args.bundle.relative_to(ROOT)),
        "manifest_sha256": digest(args.bundle / "manifest.json"),
    }
    write_json(args.summary, summary)
    print(json.dumps({"schema": summary["schema"], "status": "pass",
                      "summary": str(args.summary.relative_to(ROOT))},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
