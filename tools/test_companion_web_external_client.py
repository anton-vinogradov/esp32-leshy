#!/usr/bin/env python3
"""Host checks for the read-only external companion HTTP verifier."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import companion_web_external_client as client


SOURCE_A = "01" * 16
SOURCE_B = "02" * 16
TARGET_ID = "A1" * 16
SESSIONS = [
    {
        "session_id": "first", "source_id": SOURCE_A, "generation": 7,
        "state": "stopped", "started_us": 10, "stopped_us": 20,
        "observations": 2, "dropped": 0,
    },
    {
        "session_id": "second", "source_id": SOURCE_B, "generation": 8,
        "state": "stopped", "started_us": 30, "stopped_us": 40,
        "observations": 3, "dropped": 0,
    },
]
TARGET = {
    "target_id": TARGET_ID,
    "revision": 3,
    "favorite": True,
    "name_hex": "D0A2D0B5D181D182",
    "notes_hex": "D0A0D18FD0B4D0BED0BC",
    "tags_hex": ["D09BD0B0D0B1"],
    "identities": [{
        "kind": "wifi_bssid", "value": "7483C2C49C7C",
        "discriminator": 0,
    }],
    "evidence": [{
        "source_id": SOURCE_B, "generation": 8, "sequence": 1,
        "observed_us": 35,
    }],
}
COMPARE = {
    "target_id": TARGET_ID,
    "class": "added",
    "changes": 0,
    "baseline_evidence": 0,
    "current_evidence": 1,
}


def get_asset(url: str) -> tuple[int, str, bytes]:
    if url.endswith("/app.js"):
        return 200, "text/javascript", client.APP
    return 200, "text/html", client.INDEX


class FakeApi:
    def __init__(self) -> None:
        self.identity_drift = False

    def __call__(self, _url: str, request: dict[str, Any]) \
            -> tuple[int, str, dict[str, Any]]:
        kind = request["kind"]
        base: dict[str, Any] = {
            "schema": client.RESPONSE_SCHEMA,
            "kind": "wrong" if self.identity_drift else kind,
            "request_id": request["request_id"],
            "status": "ok",
            "reason": "none",
        }
        if kind == "connect":
            return 200, "application/json", {
                **base, "status": "ready", "protocol": 1,
                "transport": "local_web_json", "scopes": client.SCOPES,
                "capabilities": client.CAPABILITIES,
                "max_frame_bytes": 512,
            }
        if kind == "session.list":
            return 200, "application/json", {
                **base, "items": SESSIONS, "next_offset": None,
            }
        if kind == "session.detail":
            selected = next(item for item in SESSIONS
                            if item["source_id"] == request["source_id"])
            return 200, "application/json", {**base, **selected}
        if kind == "target.list":
            summary = {key: TARGET[key] for key in (
                "target_id", "revision", "favorite", "name_hex")}
            summary.update({"identity_count": 1, "evidence_count": 1})
            return 200, "application/json", {
                **base, "items": [summary], "next_offset": None,
            }
        if kind == "target.detail":
            section = request["section"]
            if section == "summary":
                summary = {key: TARGET[key] for key in (
                    "target_id", "revision", "favorite", "name_hex")}
                return 200, "application/json", {**base, **summary}
            if section == "notes":
                return 200, "application/json", {
                    **base, "value": TARGET["notes_hex"],
                    "next_offset": None,
                }
            values = TARGET["tags_hex"] if section == "tags" else TARGET[section]
            return 200, "application/json", {
                **base, "items": values, "next_offset": None,
            }
        if kind == "target.compare":
            return 200, "application/json", {
                **base, "items": [COMPARE], "next_offset": None,
                "counts": {
                    "added": 1, "changed": 0, "removed": 0,
                    "unchanged": 0,
                },
            }
        raise AssertionError(kind)


class CompanionWebExternalClientTests(unittest.TestCase):
    def test_read_only_probe_builds_privacy_safe_exact_report(self) -> None:
        report = client.run_probe(
            client.FIXED_ORIGIN, "12" * 16, get_asset, FakeApi())
        self.assertEqual("pass", report["status"])
        self.assertEqual(0, report["network_configuration_commands"])
        self.assertFalse(report["credential_material_handled"])
        self.assertTrue(report["assets"]["exact_production_match"])
        self.assertEqual(2, report["projection"]["sessions"])
        self.assertEqual(1, report["projection"]["targets"])
        self.assertEqual(1, report["projection"]["comparison_items"])
        self.assertRegex(
            report["projection"]["transport_neutral_sha256"],
            r"^[0-9a-f]{64}$")
        retained = json.dumps(report, sort_keys=True)
        self.assertNotIn(TARGET_ID, retained)
        self.assertNotIn(TARGET["name_hex"], retained)
        self.assertNotIn(SOURCE_A, retained)

    def test_origin_is_fixed_and_has_no_credential_slot(self) -> None:
        self.assertEqual(
            client.FIXED_ORIGIN, client.validate_origin(client.FIXED_ORIGIN))
        for invalid in (
            "https://192.168.4.1", "http://192.168.4.2",
            "http://user:secret@192.168.4.1", "http://192.168.4.1/path",
            "http://example.test",
        ):
            with self.assertRaises(ValueError, msg=invalid):
                client.validate_origin(invalid)

    def test_asset_or_response_identity_drift_fails_closed(self) -> None:
        def tampered(url: str) -> tuple[int, str, bytes]:
            status, content_type, payload = get_asset(url)
            return status, content_type, payload + b"x"

        with self.assertRaisesRegex(RuntimeError, "production asset"):
            client.run_probe(
                client.FIXED_ORIGIN, "34" * 16, tampered, FakeApi())
        api = FakeApi()
        api.identity_drift = True
        with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
            client.run_probe(
                client.FIXED_ORIGIN, "34" * 16, get_asset, api)

    def test_report_write_is_exclusive(self) -> None:
        report = client.run_probe(
            client.FIXED_ORIGIN, "56" * 16, get_asset, FakeApi())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            client._write_report(path, report)
            self.assertEqual(report, json.loads(path.read_text()))
            with self.assertRaises(FileExistsError):
                client._write_report(path, report)

    def test_source_contains_no_network_configuration_mechanism(self) -> None:
        source = Path(client.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "networksetup", "nmcli", "wpa_supplicant", "airport", "subprocess",
            "os.system", "WiFi.begin", "esp_wifi",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
