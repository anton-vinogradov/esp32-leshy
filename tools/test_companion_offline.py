#!/usr/bin/env python3
"""Host checks for deterministic companion offline artifacts."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import companion_offline as offline  # noqa: E402


def fixture() -> dict[str, object]:
    sessions = [
        {
            "session_id": "product-passive-live",
            "source_id": "01" * 16,
            "generation": 7,
            "state": "stopped",
            "started_us": 10,
            "stopped_us": 20,
            "observations": 2,
            "dropped": 0,
        },
        {
            "session_id": "product-passive-live",
            "source_id": "02" * 16,
            "generation": 8,
            "state": "stopped",
            "started_us": 30,
            "stopped_us": 40,
            "observations": 3,
            "dropped": 0,
        },
    ]
    targets = [
        {
            "target_id": "A1" * 16,
            "revision": 3,
            "favorite": True,
            "name_hex": "D0A2D0B5D181D182",  # Тест
            "notes_hex": "D0A0D18FD0B4D0BED0BC",  # Рядом
            "tags_hex": ["D09BD0B0D0B1"],  # Лаб
            "identities": [{
                "kind": "wifi_bssid",
                "value": "7483C2C49C7C",
                "discriminator": 0,
            }],
            "evidence": [{
                "source_id": "02" * 16,
                "generation": 8,
                "sequence": 1,
                "observed_us": 35,
            }],
        },
    ]
    comparison = {
        "baseline": {"source_id": "01" * 16, "generation": 7},
        "current": {"source_id": "02" * 16, "generation": 8},
        "counts": {
            "added": 1, "changed": 0, "removed": 0, "unchanged": 0,
        },
        "items": [{
            "target_id": "A1" * 16,
            "class": "added",
            "changes": 0,
            "baseline_evidence": 0,
            "current_evidence": 1,
        }],
    }
    return offline.build_snapshot(sessions, targets, comparison)


class CompanionOfflineTests(unittest.TestCase):
    def test_export_is_deterministic_canonical_and_self_verifying(self) -> None:
        first = fixture()
        second = fixture()
        self.assertEqual(first, second)
        self.assertEqual(offline.canonical_bytes(first),
                         offline.canonical_bytes(second))
        self.assertTrue(offline.canonical_bytes(first).endswith(b"\n"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            offline.write_snapshot(path, first)
            self.assertEqual(offline.read_snapshot(path), first)
            parsed = json.loads(path.read_bytes())
            self.assertEqual(parsed["snapshot_id"], first["snapshot_id"])

    def test_local_web_export_is_versioned_and_self_verifying(self) -> None:
        usb = fixture()
        web = offline.build_snapshot(
            usb["sessions"], usb["targets"], usb["comparison"],
            offline.WEB_TRANSPORT)
        self.assertEqual(web["source_transport"], "local_web_json")
        self.assertNotEqual(web["snapshot_id"], usb["snapshot_id"])
        offline.validate_snapshot(web)
        tampered = copy.deepcopy(web)
        tampered["targets"][0]["favorite"] = not tampered["targets"][0]["favorite"]
        with self.assertRaises(offline.SnapshotError):
            offline.validate_snapshot(tampered)

    def test_search_is_unicode_casefolded_and_identity_normalized(self) -> None:
        snapshot = fixture()
        self.assertEqual(
            offline.search_snapshot(snapshot, "тЕСТ")[0]["matched_fields"],
            ["name"])
        self.assertEqual(
            offline.search_snapshot(snapshot, "рядом")[0]["matched_fields"],
            ["notes"])
        self.assertEqual(
            offline.search_snapshot(snapshot, "лаб")[0]["matched_fields"],
            ["tags"])
        self.assertEqual(
            offline.search_snapshot(snapshot, "74:83:c2:c4:9c:7c")[0]
            ["matched_fields"], ["identities"])
        self.assertEqual(
            offline.search_snapshot(snapshot, "wifi_bssid")[0]
            ["matched_fields"], ["identities"])

    def test_tamper_and_incomplete_snapshot_fail_closed(self) -> None:
        snapshot = fixture()
        tampered = copy.deepcopy(snapshot)
        tampered["targets"][0]["favorite"] = False
        with self.assertRaisesRegex(offline.SnapshotError, "digest mismatch"):
            offline.validate_snapshot(tampered)
        incomplete = copy.deepcopy(snapshot)
        incomplete["complete"] = False
        incomplete["snapshot_id"] = offline._snapshot_digest(incomplete)
        with self.assertRaisesRegex(offline.SnapshotError, "partial"):
            offline.validate_snapshot(incomplete)

    def test_counts_unknown_fields_and_invalid_utf8_fail_closed(self) -> None:
        snapshot = fixture()
        broken_count = copy.deepcopy(snapshot)
        broken_count["counts"]["targets"] = 2
        broken_count["snapshot_id"] = offline._snapshot_digest(broken_count)
        with self.assertRaisesRegex(offline.SnapshotError, "count mismatch"):
            offline.validate_snapshot(broken_count)
        unknown = copy.deepcopy(snapshot)
        unknown["extra"] = True
        unknown["snapshot_id"] = offline._snapshot_digest(unknown)
        with self.assertRaisesRegex(offline.SnapshotError, "fields mismatch"):
            offline.validate_snapshot(unknown)
        invalid_utf8 = copy.deepcopy(snapshot)
        invalid_utf8["targets"][0]["name_hex"] = "FF"
        invalid_utf8["snapshot_id"] = offline._snapshot_digest(invalid_utf8)
        with self.assertRaisesRegex(offline.SnapshotError, "valid UTF-8"):
            offline.validate_snapshot(invalid_utf8)

    def test_noncanonical_file_and_empty_query_fail_closed(self) -> None:
        snapshot = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(offline.SnapshotError, "canonical"):
                offline.read_snapshot(path)
        with self.assertRaisesRegex(offline.SnapshotError, "must not be empty"):
            offline.search_snapshot(snapshot, "  ")


if __name__ == "__main__":
    unittest.main()
