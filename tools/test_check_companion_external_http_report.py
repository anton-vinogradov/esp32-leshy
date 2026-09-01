#!/usr/bin/env python3
"""Host checks for external HTTP/native USB parity binding."""

from __future__ import annotations

import copy
import unittest

import check_companion_external_http_report as checker
import companion_offline
import companion_web_external_client as external
from test_companion_web_external_client import (
    COMPARE,
    FakeApi,
    SESSIONS,
    TARGET,
    get_asset,
)


def usb_snapshot() -> dict[str, object]:
    comparison = {
        "baseline": {
            "source_id": SESSIONS[0]["source_id"],
            "generation": SESSIONS[0]["generation"],
        },
        "current": {
            "source_id": SESSIONS[1]["source_id"],
            "generation": SESSIONS[1]["generation"],
        },
        "counts": {
            "added": 1, "changed": 0, "removed": 0, "unchanged": 0,
        },
        "items": [COMPARE],
    }
    return companion_offline.build_snapshot(
        SESSIONS, [TARGET], comparison, companion_offline.TRANSPORT)


class CompanionExternalHttpReportTests(unittest.TestCase):
    def test_exact_external_and_usb_projection_is_accepted(self) -> None:
        challenge = "78" * 16
        report = external.run_probe(
            external.FIXED_ORIGIN, challenge, get_asset, FakeApi())
        accepted = checker.verify(report, challenge, usb_snapshot())
        self.assertEqual("pass", accepted["status"])
        self.assertEqual(
            report["projection"]["transport_neutral_sha256"],
            accepted["projection_sha256"])
        self.assertEqual(0, accepted["network_configuration_commands"])

    def test_challenge_asset_projection_and_unknown_fields_fail_closed(self) \
            -> None:
        challenge = "9a" * 16
        report = external.run_probe(
            external.FIXED_ORIGIN, challenge, get_asset, FakeApi())
        cases = []
        wrong_challenge = copy.deepcopy(report)
        wrong_challenge["challenge_sha256"] = "0" * 64
        cases.append(wrong_challenge)
        wrong_asset = copy.deepcopy(report)
        wrong_asset["assets"]["application_sha256"] = "1" * 64
        cases.append(wrong_asset)
        wrong_projection = copy.deepcopy(report)
        wrong_projection["projection"]["transport_neutral_sha256"] = "2" * 64
        cases.append(wrong_projection)
        unknown = copy.deepcopy(report)
        unknown["extra"] = True
        cases.append(unknown)
        for value in cases:
            with self.assertRaises(ValueError):
                checker.verify(value, challenge, usb_snapshot())

    def test_usb_transport_and_canonical_identity_are_required(self) -> None:
        challenge = "bc" * 16
        report = external.run_probe(
            external.FIXED_ORIGIN, challenge, get_asset, FakeApi())
        web = copy.deepcopy(usb_snapshot())
        web["source_transport"] = companion_offline.WEB_TRANSPORT
        web["snapshot_id"] = companion_offline._snapshot_digest(web)
        with self.assertRaisesRegex(ValueError, "not native USB"):
            checker.verify(report, challenge, web)


if __name__ == "__main__":
    unittest.main()
