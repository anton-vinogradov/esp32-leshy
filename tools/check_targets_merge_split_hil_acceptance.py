#!/usr/bin/env python3
"""Fail closed unless compact exact 0.165 merge/split evidence is intact."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-targets-merge-split-0.165.json"
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    try:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        bundle = ROOT / summary["bundle"]
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if digest(manifest_path) != summary["manifest_sha256"]:
            failures.append("manifest hash mismatch")
        expected = {"run.json", "provenance.json"}
        expected.update({f"frames/{name}{suffix}" for name in FRAME_NAMES
                         for suffix in (".json", ".png")})
        if set(manifest) != expected:
            failures.append("unexpected retained artifact set")
        for relative, expected_hash in manifest.items():
            path = bundle / relative
            if not path.is_file() or digest(path) != expected_hash:
                failures.append(f"retained artifact mismatch: {relative}")
        candidate = summary["candidate"]
        if not (summary["schema"] ==
                "leshy.targets_merge_split_hil.summary.v1" and
                summary["status"] == "pass" and
                summary["evidence_ids"] ==
                ["E-AUTO-116", "E-HIL-176", "E-UX-052"] and
                summary["firmware_source_commit"] ==
                "19a322c428d6efa52fe18f62041141e0cf6669d8" and
                summary["verification_source_commit"] ==
                "b3a19e2a99b764d33b8de9eac802102a35fdb084" and
                candidate["version"] == "0.165.0-targets-fixture-reopen" and
                candidate["firmware_sha256"] ==
                "40af5486e8525998e86aa3c864e0cb0e21e3aace0d3dc40c8dd4eb1923f01d4b" and
                candidate["app_elf_sha256"] ==
                "20968cb44e847c7e3b9338c462991b6710a2c23c1654e9b3692879c9f91a81ec" and
                candidate["partitions_sha256"] ==
                "339bda68b7470d5ad1482d10183514b88971c6f1f20ff87c7e2f3dad96235ba2"):
            failures.append("summary/candidate identity mismatch")
        if not (summary["exact_cid"] ==
                "FE343253440000002000000055019CB7" and
                summary["flash_count"] == 0 and
                summary["usb"] == {
                    "opened_ports": ["/dev/cu.usbmodem2101"],
                    "cardputer_ports_opened": 0,
                    "port_discovery_calls": 0,
                }):
            failures.append("candidate/CID/USB isolation mismatch")
        if summary["merge"] != {
                "catalog": [2, 1], "generation": [0, 1],
                "history": [0, 1], "identities": 2, "evidence": 2,
                "writes": 3, "file_syncs": 3, "directory_syncs": 3,
                "cold_reopened": True}:
            failures.append("merge invariant mismatch")
        split = summary["split"]
        if not (split == {
                "catalog": [1, 2], "generation": [1, 2], "history": 1,
                "destination_fingerprint": "4E0F6E23113F2A27",
                "source_fingerprint": "457C241F7BC2C2F5",
                "writes": 3, "file_syncs": 3, "directory_syncs": 3,
                "cold_reopened": True}):
            failures.append("split/exact reversal invariant mismatch")
        if not all(value >= 8000 for value in
                   summary["reset_stack_min_free"].values()):
            failures.append("mutation reset stack floor mismatch")
        restore = summary["disposable_restore"]
        if not (restore["verified"] is True and
                restore["private_backup_deleted"] is True and
                restore["ota1_sha256"] ==
                "3bf012ed2a6f9ae7026ec8eb5a080dcd75e343b7073e337ea72900ed97da9e33" and
                restore["partition_table_sha256"] ==
                "44539be51aeb592d44450059d7dbbb4d5a25d7fe5144cc68b8e85acba367ba87"):
            failures.append("disposable storage restore mismatch")
        if summary["released_heap"] < 93000:
            failures.append("Targets heap release mismatch")
        if summary["final"] != {
                "fixture_armed": False, "generation": 161,
                "observations": 59, "mounted_read_only": True,
                "physical_write_calls": 0, "page": "home",
                "runtime_owner": "none", "lease_mask": 0,
                "radio_touched": False, "rf_tx_attempts": 0}:
            failures.append("final product/safety state mismatch")
        for name, record in summary["screens"].items():
            path = bundle / record["png"]
            if name not in FRAME_NAMES or not path.is_file() or \
                    digest(path) != record["png_sha256"]:
                failures.append(f"screenshot mismatch: {record['png']}")
        if set(summary["screens"]) != set(FRAME_NAMES):
            failures.append("screenshot set mismatch")
        if digest(bundle / "run.json") != summary["raw_run_sha256"]:
            failures.append("raw run hash mismatch")
    except (KeyError, OSError, TypeError, ValueError) as error:
        failures.append(str(error))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Targets merge/split HIL acceptance passed: exact cold reversal, "
          "restored partitions, zero TX/Cardputer ports/leaked lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
